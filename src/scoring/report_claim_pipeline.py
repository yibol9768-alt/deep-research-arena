"""Model-driven, source-preserving claim extraction for DRA reports.

The extractor never sees TEC truth labels or evidence pages.  Every accepted
claim is anchored to an exact report substring and passes two independent,
audited model stages: report-span NLI and structural/qualifier verification.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from src.scoring.audited_judge import AuditedJudge
from src.scoring.frozen_claim_ledger import seal_claim_ledger


CITE_RE = re.compile(r'<cite\s+id="([^"]+)"\s*>.*?</cite>', re.DOTALL)
MATERIAL_SIGNAL_RE = re.compile(
    r"(?:\d|[$%°]|(?:\b(?:is|are|has|have|claims?|lists?|means?|"
    r"indicates?|supports?|costs?|rated|hours?|watts?|mAh|IPX\d|Bluetooth|"
    r"better|worse|higher|lower|more|less|because|therefore)\b))",
    re.IGNORECASE,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def segment_report(report: str) -> list[dict[str, Any]]:
    """Split on physical lines while retaining exact character offsets."""

    segments: list[dict[str, Any]] = []
    offset = 0
    heading = ""
    for line_no, line_with_end in enumerate(report.splitlines(keepends=True), 1):
        raw = line_with_end.rstrip("\r\n")
        line_start = offset
        offset += len(line_with_end)
        if not raw.strip():
            continue
        is_heading = raw.lstrip().startswith("#")
        if is_heading or re.match(r"^\d+\)\s", raw.strip()):
            heading = raw.strip()
        segments.append(
            {
                "segment_id": f"s_{len(segments) + 1:04d}",
                "line_no": line_no,
                "start": line_start,
                "end": line_start + len(raw),
                "raw_text": raw,
                "sha256": _sha256(raw),
                "heading": heading,
                "is_heading": is_heading,
                "citation_ids": CITE_RE.findall(raw),
                "material_signal": bool(MATERIAL_SIGNAL_RE.search(raw)),
            }
        )
    return segments


def _batches(
    rows: list[dict[str, Any]],
    *,
    char_budget: int,
    count_budget: int,
) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for row in rows:
        row_size = len(json.dumps(row, ensure_ascii=False))
        if current and (size + row_size > char_budget or len(current) >= count_budget):
            batches.append(current)
            current = []
            size = 0
        current.append(row)
        size += row_size
    if current:
        batches.append(current)
    return batches


PROPOSAL_SYSTEM = """You are the claim-proposal stage of a report evaluator.
Use ONLY the supplied report spans. Do not use world knowledge and do not
decide whether a claim is true. Extract every material externally verifiable
atomic claim at high recall.

Rules:
1. segment_id must identify the supplied span that entails the claim. The
   evaluator anchors accepted claims to that exact input span; do not copy the
   source span into the response.
2. normalized_claim may normalize the atomic proposition, but must preserve
   model/version, number, unit, condition, negation, modality, comparison
   direction, and attribution such as "the listing claims".
3. Split conjunctions into separate claims when each could independently be
   true or false. Multiple claims may share the same raw_text.
4. Do not turn recommendations, preferences, instructions, or uncertainty into
   external facts. Classify them instead.
5. citation_ids may contain only citation IDs printed in that span and only
   citations locally attached to this claim.
6. Use bounded_absence only for a scoped negative page-content claim such as
   "neither listing mentions Hi-Res". Put the exact strings whose absence is
   asserted in qualifiers.absence_terms. The scope must be explicit in the
   report and represented by locally attached citations or
   qualifiers.scope_urls.
7. Classify statements about the report itself, its sections, citations,
   methodology, or what "this report" will do as report_meta. Classify a
   proposed action/product choice as recommendation and a counterfactual or
   illustrative scenario as hypothetical. These must not become Fact claims.

Return JSON only:
{"claims":[{"segment_id":"s_0001",
"normalized_claim":"one atomic proposition",
"claim_kind":"external_atomic|derived_arithmetic|bounded_absence|higher_order_relation|recommendation|hypothetical|report_meta|subjective|exempt",
"evidence_policy":"citation_required|citation_exempt",
"subject":"...","predicate":"...","object":"...",
"qualifiers":{},"polarity":"assert|deny","modality":"categorical|qualified|possible",
"attribution":"direct_fact|retailer_claim|manufacturer_claim|community_report|analysis",
"citation_ids":[]}]}
"""

PROPOSAL_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "maxItems": 48,
            "items": {
                "type": "object",
                "properties": {
                    "segment_id": {"type": "string", "maxLength": 64},
                    "normalized_claim": {
                        "type": "string",
                        "maxLength": 4000,
                    },
                    "claim_kind": {
                        "type": "string",
                        "enum": [
                            "external_atomic",
                            "derived_arithmetic",
                            "bounded_absence",
                            "higher_order_relation",
                            "recommendation",
                            "hypothetical",
                            "report_meta",
                            "subjective",
                            "exempt",
                        ],
                    },
                    "evidence_policy": {
                        "type": "string",
                        "enum": ["citation_required", "citation_exempt"],
                    },
                    "subject": {"type": "string", "maxLength": 2000},
                    "predicate": {"type": "string", "maxLength": 2000},
                    "object": {"type": "string", "maxLength": 3000},
                    "qualifiers": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                    "polarity": {
                        "type": "string",
                        "enum": ["assert", "deny"],
                    },
                    "modality": {
                        "type": "string",
                        "enum": ["categorical", "qualified", "possible"],
                    },
                    "attribution": {
                        "type": "string",
                        "enum": [
                            "direct_fact",
                            "retailer_claim",
                            "manufacturer_claim",
                            "community_report",
                            "analysis",
                        ],
                    },
                    "citation_ids": {
                        "type": "array",
                        "maxItems": 32,
                        "items": {"type": "string", "maxLength": 128},
                    },
                },
                "required": [
                    "segment_id",
                    "normalized_claim",
                    "claim_kind",
                    "evidence_policy",
                    "subject",
                    "predicate",
                    "object",
                    "qualifiers",
                    "polarity",
                    "modality",
                    "attribution",
                    "citation_ids",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}

NLI_SYSTEM = """You are a narrow NLI filter. For each item, decide only whether
the supplied report premise entails the proposed normalized claim. Do not use
world knowledge and do not judge truth. Numeric values, units, model/version,
conditions, negation, comparison direction, modality, and attribution must all
be preserved. Return JSON only:
{"judgments":[{"claim_id":"p_0001",
"nli_relation":"entailment|contradiction|neutral",
"qualifier_check":"pass|fail","reason_code":"short_code"}]}
"""

STRUCTURAL_SYSTEM = """You are a narrow structural verifier for report claims.
Use only raw_text, premise, and the proposed claim. Do not judge world truth.
Accept only if the premise entails the claim, the claim is atomic, and every
number, unit, version, condition, negation, modality, comparison direction,
and attribution is faithful.

Correct category errors. In particular, report/section/citation self-
descriptions are report_meta, product choices are recommendation, and
counterfactual examples are hypothetical. bounded_absence is permitted only
when the premise states a finite scope and qualifiers.absence_terms contains
the literal claim terms to audit. Return JSON only:
{"judgments":[{"claim_id":"p_0001","verdict":"accept|reject",
"nli_relation":"entailed|not_entailed","atomicity":"atomic|compound",
"qualifier_fidelity":"pass|fail",
"claim_kind":"external_atomic|derived_arithmetic|bounded_absence|higher_order_relation|recommendation|hypothetical|report_meta|subjective|exempt",
"evidence_policy":"citation_required|citation_exempt",
"reason_code":"short_code"}]}
"""

DEDUP_SYSTEM = """You are a pairwise semantic duplicate judge. Use only each
supplied pair. Return duplicate=true only when the two claims express the same
atomic proposition with the same subject/entity/model, predicate, object,
number, unit, qualifiers, polarity, modality, and attribution. Related claims,
implications, broader/narrower claims, different product variants, and
supporting reasons are not duplicates. Do not judge world truth.

Return one positional decision for every pair in exact input order. Do not
repeat pair IDs:
{"duplicate":[false,true],"reason_codes":["different_object","same_claim"]}
"""


def _dedup_response_schema(item_count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "duplicate": {
                "type": "array",
                "minItems": item_count,
                "maxItems": item_count,
                "items": {"type": "boolean"},
            },
            "reason_codes": {
                "type": "array",
                "minItems": item_count,
                "maxItems": item_count,
                "items": {"type": "string", "maxLength": 128},
            },
        },
        "required": ["duplicate", "reason_codes"],
        "additionalProperties": False,
    }


DEDUP_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[._+-][A-Za-z0-9]+)*")
DEDUP_NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")
DEDUP_CJK_RUN_RE = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
    r"\uf900-\ufaff\uac00-\ud7af]+"
)
DEDUP_SEMANTIC_OPERATORS = {
    "advertise",
    "advertised",
    "advertises",
    "allegedly",
    "apparently",
    "approximately",
    "around",
    "claim",
    "claimed",
    "claims",
    "could",
    "estimate",
    "estimated",
    "imply",
    "implied",
    "implies",
    "likely",
    "marketed",
    "may",
    "might",
    "often",
    "possibly",
    "probably",
    "rarely",
    "report",
    "reported",
    "reportedly",
    "reports",
    "roughly",
    "seem",
    "seems",
    "state",
    "stated",
    "states",
    "suggest",
    "suggested",
    "suggests",
    "typically",
    "usually",
}
DEDUP_SCOPE_OPERATORS = {
    "except",
    "excluding",
    "lacks",
    "never",
    "no",
    "none",
    "not",
    "only",
    "unless",
    "without",
}
DEDUP_CJK_SEMANTIC_OPERATORS = {
    "也许",
    "估计",
    "可能",
    "声称",
    "大概",
    "宣传",
    "宣称",
    "广告",
    "往往",
    "很少",
    "据称",
    "推测",
    "暗示",
    "看起来",
    "约",
    "表示",
    "报告",
    "通常",
    "预计",
}
DEDUP_CJK_SCOPE_OPERATORS = {
    "不",
    "仅",
    "从未",
    "只",
    "并非",
    "没有",
    "除外",
    "除非",
}
DEDUP_CLAUSE_OPERATORS = {
    "and",
    "but",
    "however",
    "or",
    "whereas",
    "while",
}
DEDUP_CJK_CLAUSE_OPERATORS = {
    "与",
    "且",
    "但是",
    "以及",
    "同时",
    "和",
    "并且",
    "或",
    "或者",
    "而",
    "而且",
}


def _dedup_tokens(value: Any) -> set[str]:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value or "")
    tokens = {
        token.casefold() for token in DEDUP_TOKEN_RE.findall(text)
    }
    for run in DEDUP_CJK_RUN_RE.findall(text):
        if len(run) == 1:
            tokens.add(f"cjk:{run}")
            continue
        tokens.update(
            f"cjk:{run[index:index + 2]}"
            for index in range(len(run) - 1)
        )
    return tokens


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _dedup_operator_signature(
    value: str,
    tokens: set[str],
) -> tuple[frozenset[str], ...]:
    """Preserve epistemic, reporting, and scope operators across a merge.

    The structured claim fields are model-produced and can occasionally omit
    words such as "likely", "claims", or "no lights".  Those words change the
    proposition, so the deterministic candidate gate also reads the normalized
    claim itself instead of trusting the structured fields alone.
    """

    semantic = set(tokens & DEDUP_SEMANTIC_OPERATORS)
    semantic.update(
        f"cjk-op:{operator}"
        for operator in DEDUP_CJK_SEMANTIC_OPERATORS
        if operator in value
    )
    scope = set(tokens & DEDUP_SCOPE_OPERATORS)
    scope.update(
        f"cjk-op:{operator}"
        for operator in DEDUP_CJK_SCOPE_OPERATORS
        if operator in value
    )
    return frozenset(semantic), frozenset(scope)


def _dedup_clause_signature(value: str) -> tuple[int, tuple[tuple[str, int], ...]]:
    """Return a conservative surface signature for compound-claim detection."""

    tokens = [token.casefold() for token in DEDUP_TOKEN_RE.findall(value)]
    sentence_count = max(
        1,
        len(
            re.findall(
                r"(?<!\d)[.!?](?:\s|$)|[;。！？；]",
                value,
            )
        ),
    )
    connector_counts = [
        (operator, tokens.count(operator))
        for operator in sorted(DEDUP_CLAUSE_OPERATORS)
        if operator in tokens
    ]
    connector_counts.extend(
        (f"cjk:{operator}", value.count(operator))
        for operator in sorted(DEDUP_CJK_CLAUSE_OPERATORS)
        if operator in value
    )
    return sentence_count, tuple(connector_counts)


def _semantic_dedup_candidate_pairs(
    claims: list[dict[str, Any]],
    *,
    max_candidates_per_claim: int = 4,
) -> list[dict[str, Any]]:
    """Build conservative semantic-dedup pairs without deciding duplicates.

    Blocking is intentionally recall-conservative: a missed pair leaves two
    claims separate, while an incompatible merge would corrupt every later
    axis. Pair truth remains a model judgment.
    """

    features: list[dict[str, Any]] = []
    for claim in claims:
        normalized = str(claim.get("normalized_claim") or "")
        all_tokens = _dedup_tokens(normalized)
        identity_tokens = {
            token
            for token in all_tokens
            if any(character.isdigit() for character in token)
            and any(character.isalpha() for character in token)
        }
        numbers = set(DEDUP_NUMBER_RE.findall(normalized))
        features.append(
            {
                "claim": claim,
                "all": all_tokens,
                "subject": _dedup_tokens(claim.get("subject")),
                "predicate": _dedup_tokens(claim.get("predicate")),
                "object": _dedup_tokens(claim.get("object")),
                "qualifiers": _dedup_tokens(claim.get("qualifiers", {})),
                "identity": identity_tokens,
                "numbers": numbers,
                "operators": _dedup_operator_signature(
                    normalized,
                    all_tokens,
                ),
                "clauses": _dedup_clause_signature(normalized),
                "invariants": (
                    claim.get("claim_kind"),
                    claim.get("polarity"),
                    claim.get("modality"),
                    claim.get("attribution"),
                ),
            }
        )

    pairs: list[dict[str, Any]] = []
    for right_index, right in enumerate(features):
        compatible: list[tuple[float, int]] = []
        for left_index in range(right_index):
            left = features[left_index]
            if left["invariants"] != right["invariants"]:
                continue
            if left["numbers"] != right["numbers"]:
                continue
            if left["identity"] != right["identity"]:
                continue
            if left["operators"] != right["operators"]:
                continue
            if left["clauses"] != right["clauses"]:
                continue
            subject_similarity = _jaccard(left["subject"], right["subject"])
            claim_similarity = _jaccard(left["all"], right["all"])
            predicate_similarity = _jaccard(
                left["predicate"], right["predicate"]
            )
            object_similarity = _jaccard(left["object"], right["object"])
            qualifier_similarity = (
                1.0
                if left["qualifiers"] == right["qualifiers"]
                else _jaccard(left["qualifiers"], right["qualifiers"])
            )
            subject_compatible = (
                left["subject"] == right["subject"]
                or subject_similarity >= 0.6
            )
            predicate_compatible = (
                left["predicate"] == right["predicate"]
                or predicate_similarity >= 0.65
            )
            object_compatible = (
                left["object"] == right["object"]
                or object_similarity >= 0.75
            )
            qualifier_compatible = left["qualifiers"] == right["qualifiers"]
            structured_proposition_exact = (
                left["predicate"] == right["predicate"]
                and left["object"] == right["object"]
                and qualifier_compatible
            )
            near_surface_paraphrase = (
                predicate_compatible
                and object_compatible
                and qualifier_compatible
                and claim_similarity >= 0.9
            )
            proposition_compatible = (
                (
                    structured_proposition_exact
                    and claim_similarity >= 0.5
                )
                or near_surface_paraphrase
            )
            if not subject_compatible or not proposition_compatible:
                continue
            score = (
                0.35 * claim_similarity
                + 0.25 * subject_similarity
                + 0.2 * predicate_similarity
                + 0.15 * object_similarity
                + 0.05 * qualifier_similarity
            )
            compatible.append((score, left_index))
        for score, left_index in sorted(
            compatible, key=lambda row: (-row[0], row[1])
        )[:max_candidates_per_claim]:
            left_claim = claims[left_index]
            right_claim = claims[right_index]
            pairs.append(
                {
                    "pair_id": f"d_{len(pairs) + 1:05d}",
                    "left_claim_id": left_claim["claim_id"],
                    "right_claim_id": right_claim["claim_id"],
                    "left": {
                        key: left_claim.get(key)
                        for key in (
                            "normalized_claim",
                            "claim_kind",
                            "subject",
                            "predicate",
                            "object",
                            "qualifiers",
                            "polarity",
                            "modality",
                            "attribution",
                        )
                    },
                    "right": {
                        key: right_claim.get(key)
                        for key in (
                            "normalized_claim",
                            "claim_kind",
                            "subject",
                            "predicate",
                            "object",
                            "qualifiers",
                            "polarity",
                            "modality",
                            "attribution",
                        )
                    },
                    "candidate_similarity": round(score, 6),
                }
            )
    return pairs


def _propose(
    judge: AuditedJudge,
    segments: list[dict[str, Any]],
    *,
    stage_prefix: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    proposals: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    initial_batches = _batches(
        segments,
        char_budget=2200,
        count_budget=6,
    )

    def process_batch(
        batch: list[dict[str, Any]],
        label: str,
        schema_retry: int = 0,
    ) -> None:
        compact = [
            {
                "segment_id": row["segment_id"],
                "heading": row["heading"],
                "raw_text": row["raw_text"],
                "available_citation_ids": row["citation_ids"],
            }
            for row in batch
        ]
        try:
            response = judge.call_json(
                f"{stage_prefix}-proposal-{label}",
                PROPOSAL_SYSTEM,
                {"spans": compact},
                expected_top_key="claims",
                compact_payload=True,
                response_schema=PROPOSAL_RESPONSE_SCHEMA,
            )
        except RuntimeError as exc:
            # Long high-recall claim lists occasionally hit a provider output
            # ceiling or lose their requested envelope even when the input is
            # modest. Retry by bisecting the same batch. For a singleton, one
            # fresh model call is allowed. Every failed and replacement call
            # remains in the audited transcript; JSON is never hand-completed.
            schema_failure = (
                "invalid JSON" in str(exc)
                or "lacks top-level key" in str(exc)
            )
            if not schema_failure:
                raise
            if len(batch) <= 1:
                if schema_retry >= 1:
                    raise
                process_batch(batch, f"{label}r", schema_retry + 1)
                return
            middle = len(batch) // 2
            process_batch(batch[:middle], f"{label}a")
            process_batch(batch[middle:], f"{label}b")
            return
        segment_map = {row["segment_id"]: row for row in batch}
        for raw_claim in response.get("claims", []):
            segment_id = raw_claim.get("segment_id")
            segment = segment_map.get(segment_id)
            reason = None
            if segment is None:
                reason = "unknown_segment"
            elif not isinstance(raw_claim.get("normalized_claim"), str):
                reason = "missing_normalized_claim"
            elif segment["is_heading"] and raw_claim.get("claim_kind") in {
                "external_atomic",
                "derived_arithmetic",
            }:
                reason = "heading_not_material_claim"
            citations = raw_claim.get("citation_ids") or []
            if not reason and (
                not isinstance(citations, list)
                or any(cite not in segment["citation_ids"] for cite in citations)
            ):
                reason = "citation_not_in_segment"
            if reason:
                rejected.append({"reason": reason, "proposal": raw_claim})
                continue
            proposal = dict(raw_claim)
            proposal["claim_id"] = f"p_{len(proposals) + 1:04d}"
            proposal["report_span"] = {
                "start": segment["start"],
                "end": segment["end"],
                "raw_text": segment["raw_text"],
                "sha256": segment["sha256"],
                "segment_id": segment_id,
            }
            proposal["premise"] = segment["raw_text"]
            proposals.append(proposal)

    for batch_no, batch in enumerate(initial_batches, 1):
        process_batch(batch, f"{batch_no:03d}")
    return proposals, rejected


def _preliminary_exact_dedup(
    proposals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse exact normalized duplicates before expensive model gates.

    This is not a semantic judgment.  The scored proposition is the complete
    normalized claim, not the model-produced predicate/object decomposition.
    Therefore identical claim text with the same subject, scope qualifiers,
    polarity, modality, attribution, and kind is one claim even when two
    proposal rows select different predicate/object substrings.  Every source
    occurrence remains attached so citation bindings are still scored
    individually.
    """

    groups: dict[str, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    for row in proposals:
        key_payload = {
            "normalized_claim": str(row.get("normalized_claim", "")).casefold(),
            "claim_kind": row.get("claim_kind"),
            "subject": str(row.get("subject", "")).casefold(),
            "qualifiers": row.get("qualifiers", {}),
            "polarity": row.get("polarity"),
            "modality": row.get("modality"),
            "attribution": row.get("attribution"),
        }
        key = json.dumps(
            key_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        occurrence = {
            "report_span": row["report_span"],
            "report_context": row["premise"],
            "citation_ids": list(row.get("citation_ids", [])),
        }
        if key not in groups:
            row["occurrences"] = [occurrence]
            groups[key] = row
            ordered.append(row)
        else:
            groups[key]["occurrences"].append(occurrence)
            groups[key]["citation_ids"] = sorted(
                set(groups[key].get("citation_ids", []))
                | set(row.get("citation_ids", []))
            )
    for index, row in enumerate(ordered, 1):
        row["claim_id"] = f"p_{index:04d}"
    return ordered


def extract_report_claims(
    report: str,
    proposal_judge: AuditedJudge,
    output_dir: Path,
    *,
    nli_judge: AuditedJudge | None = None,
    structural_judge: AuditedJudge | None = None,
    dedup_judge: AuditedJudge | None = None,
) -> dict[str, Any]:
    """Run proposal, NLI, structural verification, residual sweep, and dedup."""

    nli_judge = nli_judge or proposal_judge
    structural_judge = structural_judge or proposal_judge
    dedup_judge = dedup_judge or structural_judge
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    segments = segment_report(report)
    write_jsonl(output_dir / "report_segments.jsonl", segments)

    proposals, proposal_rejections = _propose(
        proposal_judge, segments, stage_prefix="claim-stage-a"
    )
    write_jsonl(output_dir / "claim_proposals.jsonl", proposals)
    proposals_before_exact_dedup = len(proposals)
    proposals = _preliminary_exact_dedup(proposals)
    write_jsonl(output_dir / "claim_proposals_exact_dedup.jsonl", proposals)

    nli_rows: list[dict[str, Any]] = []
    for batch_no, batch in enumerate(
        _batches(proposals, char_budget=10000, count_budget=20), 1
    ):
        items = [
            {
                "claim_id": row["claim_id"],
                "premise": row["premise"],
                "hypothesis": row["normalized_claim"],
            }
            for row in batch
        ]
        response = nli_judge.call_json(
            f"claim-stage-b-nli-{batch_no:03d}",
            NLI_SYSTEM,
            {"items": items},
            expected_top_key="judgments",
        )
        nli_rows.extend(response.get("judgments", []))
    nli_map = {row.get("claim_id"): row for row in nli_rows}
    write_jsonl(output_dir / "claim_nli_judgments.jsonl", nli_rows)
    nli_passed = [
        row
        for row in proposals
        if nli_map.get(row["claim_id"], {}).get("nli_relation") == "entailment"
        and nli_map.get(row["claim_id"], {}).get("qualifier_check") == "pass"
    ]

    structural_rows: list[dict[str, Any]] = []
    for batch_no, batch in enumerate(
        _batches(nli_passed, char_budget=11000, count_budget=18), 1
    ):
        items = [
            {
                "claim_id": row["claim_id"],
                "premise": row["premise"],
                "raw_text": row["report_span"]["raw_text"],
                "proposed_claim": row["normalized_claim"],
                "proposed_kind": row.get("claim_kind"),
                "proposed_evidence_policy": row.get("evidence_policy"),
            }
            for row in batch
        ]
        response = structural_judge.call_json(
            f"claim-stage-c-structural-{batch_no:03d}",
            STRUCTURAL_SYSTEM,
            {"items": items},
            expected_top_key="judgments",
        )
        structural_rows.extend(response.get("judgments", []))
    structural_map = {row.get("claim_id"): row for row in structural_rows}
    write_jsonl(output_dir / "claim_structural_judgments.jsonl", structural_rows)

    accepted = [
        row
        for row in nli_passed
        if structural_map.get(row["claim_id"], {}).get("verdict") == "accept"
        and structural_map.get(row["claim_id"], {}).get("atomicity") == "atomic"
        and structural_map.get(row["claim_id"], {}).get("qualifier_fidelity") == "pass"
    ]
    for row in accepted:
        verdict = structural_map[row["claim_id"]]
        row["claim_kind"] = verdict.get("claim_kind", row.get("claim_kind"))
        row["evidence_policy"] = verdict.get(
            "evidence_policy", row.get("evidence_policy")
        )

    accepted_per_segment: dict[str, int] = {}
    for row in accepted:
        segment_id = row["report_span"]["segment_id"]
        accepted_per_segment[segment_id] = (
            accepted_per_segment.get(segment_id, 0) + 1
        )

    def estimated_material_slots(row: dict[str, Any]) -> int:
        text = row["raw_text"]
        separators = len(
            re.findall(r"(?:[.;]\s+|\b(?:but|while|whereas|however)\b)", text)
        )
        # This is only a high-recall residual trigger. The downstream NLI,
        # structural, and semantic-dedup stages still decide accepted claims.
        return min(4, 1 + separators)

    residual_segments = [
        row
        for row in segments
        if row["material_signal"]
        and not row.get("is_heading", False)
        and accepted_per_segment.get(row["segment_id"], 0)
        < estimated_material_slots(row)
    ]
    residual_proposals: list[dict[str, Any]] = []
    residual_rejections: list[dict[str, Any]] = []
    # A second high-recall proposal pass is deliberately recorded.  We do not
    # silently accept it: it traverses the same NLI and structural gates below.
    if residual_segments:
        residual_proposals, residual_rejections = _propose(
            proposal_judge,
            residual_segments,
            stage_prefix="claim-stage-d-residual",
        )
        next_index = len(proposals) + 1
        for row in residual_proposals:
            row["claim_id"] = f"p_{next_index:04d}"
            next_index += 1

        residual_nli: list[dict[str, Any]] = []
        for batch_no, batch in enumerate(
            _batches(residual_proposals, char_budget=10000, count_budget=20), 1
        ):
            response = nli_judge.call_json(
                f"claim-stage-d-residual-nli-{batch_no:03d}",
                NLI_SYSTEM,
                {
                    "items": [
                        {
                            "claim_id": row["claim_id"],
                            "premise": row["premise"],
                            "hypothesis": row["normalized_claim"],
                        }
                        for row in batch
                    ]
                },
                expected_top_key="judgments",
            )
            residual_nli.extend(response.get("judgments", []))
        residual_nli_map = {row.get("claim_id"): row for row in residual_nli}
        residual_nli_passed = [
            row
            for row in residual_proposals
            if residual_nli_map.get(row["claim_id"], {}).get("nli_relation")
            == "entailment"
            and residual_nli_map.get(row["claim_id"], {}).get("qualifier_check")
            == "pass"
        ]
        residual_structural: list[dict[str, Any]] = []
        for batch_no, batch in enumerate(
            _batches(residual_nli_passed, char_budget=11000, count_budget=18), 1
        ):
            response = structural_judge.call_json(
                f"claim-stage-d-residual-structural-{batch_no:03d}",
                STRUCTURAL_SYSTEM,
                {
                    "items": [
                        {
                            "claim_id": row["claim_id"],
                            "premise": row["premise"],
                            "raw_text": row["report_span"]["raw_text"],
                            "proposed_claim": row["normalized_claim"],
                            "proposed_kind": row.get("claim_kind"),
                            "proposed_evidence_policy": row.get("evidence_policy"),
                        }
                        for row in batch
                    ]
                },
                expected_top_key="judgments",
            )
            residual_structural.extend(response.get("judgments", []))
        residual_structural_map = {
            row.get("claim_id"): row for row in residual_structural
        }
        for row in residual_nli_passed:
            verdict = residual_structural_map.get(row["claim_id"], {})
            if (
                verdict.get("verdict") == "accept"
                and verdict.get("atomicity") == "atomic"
                and verdict.get("qualifier_fidelity") == "pass"
            ):
                row["claim_kind"] = verdict.get("claim_kind", row.get("claim_kind"))
                row["evidence_policy"] = verdict.get(
                    "evidence_policy", row.get("evidence_policy")
                )
                accepted.append(row)
        nli_rows.extend(residual_nli)
        structural_rows.extend(residual_structural)

    expected_claim_ids = [row["claim_id"] for row in accepted]
    dedup_pairs = _semantic_dedup_candidate_pairs(
        accepted,
        max_candidates_per_claim=3,
    )
    dedup_pair_judgments: list[dict[str, Any]] = []

    def judge_dedup_batch(
        batch: list[dict[str, Any]], label: str
    ) -> None:
        try:
            response = dedup_judge.call_json(
                f"claim-stage-d-semantic-dedup-{label}",
                DEDUP_SYSTEM,
                {"pairs": batch},
                expected_top_key="duplicate",
                max_tokens=2048,
                compact_payload=True,
                response_schema=_dedup_response_schema(len(batch)),
            )
        except RuntimeError:
            if len(batch) <= 1:
                raise
            middle = len(batch) // 2
            judge_dedup_batch(batch[:middle], f"{label}a")
            judge_dedup_batch(batch[middle:], f"{label}b")
            return
        decisions = list(response.get("duplicate") or [])
        reason_codes = list(response.get("reason_codes") or [])
        if len(decisions) != len(batch) or len(reason_codes) != len(batch):
            raise RuntimeError(
                "semantic dedup response did not preserve one decision per pair"
            )
        for pair, duplicate, reason_code in zip(
            batch, decisions, reason_codes
        ):
            dedup_pair_judgments.append(
                {
                    "pair_id": pair["pair_id"],
                    "left_claim_id": pair["left_claim_id"],
                    "right_claim_id": pair["right_claim_id"],
                    "duplicate": bool(duplicate),
                    "reason_code": str(reason_code),
                }
            )

    for batch_no, batch in enumerate(
        _batches(dedup_pairs, char_budget=20000, count_budget=12), 1
    ):
        judge_dedup_batch(batch, f"{batch_no:03d}")

    claim_order = {
        claim_id: index for index, claim_id in enumerate(expected_claim_ids)
    }
    parent = {claim_id: claim_id for claim_id in expected_claim_ids}

    def find(claim_id: str) -> str:
        while parent[claim_id] != claim_id:
            parent[claim_id] = parent[parent[claim_id]]
            claim_id = parent[claim_id]
        return claim_id

    def union(left_id: str, right_id: str) -> None:
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root == right_root:
            return
        if claim_order[left_root] <= claim_order[right_root]:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    for judgment in dedup_pair_judgments:
        if judgment["duplicate"]:
            union(
                str(judgment["left_claim_id"]),
                str(judgment["right_claim_id"]),
            )

    dedup_map: dict[str, str | None] = {}
    for claim_id in expected_claim_ids:
        canonical = find(claim_id)
        dedup_map[claim_id] = (
            canonical if canonical != claim_id else None
        )
    write_jsonl(
        output_dir / "claim_semantic_dedup_candidates.jsonl",
        dedup_pairs,
    )
    write_jsonl(
        output_dir / "claim_semantic_dedup_judgments.jsonl",
        dedup_pair_judgments,
    )
    accepted_ids = {row["claim_id"] for row in accepted}
    accepted_map = {row["claim_id"]: row for row in accepted}
    for row in accepted:
        duplicate_of = dedup_map.get(row["claim_id"])
        if duplicate_of and duplicate_of in accepted_map:
            canonical = accepted_map[duplicate_of]
            canonical.setdefault("occurrences", []).extend(
                row.get(
                    "occurrences",
                    [
                        {
                            "report_span": row["report_span"],
                            "report_context": row["premise"],
                            "citation_ids": row.get("citation_ids", []),
                        }
                    ],
                )
            )
            canonical["citation_ids"] = sorted(
                set(canonical.get("citation_ids", []))
                | set(row.get("citation_ids", []))
            )
    frozen: list[dict[str, Any]] = []
    for row in accepted:
        duplicate_of = dedup_map.get(row["claim_id"])
        if duplicate_of and duplicate_of in accepted_ids:
            continue
        final = {key: value for key, value in row.items() if key != "premise"}
        final["report_context"] = row["premise"]
        final.setdefault(
            "occurrences",
            [
                {
                    "report_span": row["report_span"],
                    "report_context": row["premise"],
                    "citation_ids": row.get("citation_ids", []),
                }
            ],
        )
        final["dedup_group"] = row["claim_id"]
        final["materiality"] = 1.0
        final["extractor"] = {
            "proposal_model": proposal_judge.model,
            "nli_model": nli_judge.model,
            "nli_label": "entailment",
            "structural_verifier_model": structural_judge.model,
            "dedup_model": dedup_judge.model,
        }
        frozen.append(final)

    write_jsonl(output_dir / "report_claims.jsonl", frozen)
    (output_dir / "claim_extraction_summary.json").write_text(
        json.dumps(
            {
                "schema": "dra_report_claim_extraction_v1",
                "report_sha256": _sha256(report),
                "segment_count": len(segments),
                "proposal_count_before_exact_dedup": proposals_before_exact_dedup,
                "proposal_count": len(proposals) + len(residual_proposals),
                "proposal_rejection_count": len(proposal_rejections)
                + len(residual_rejections),
                "nli_pass_count": len(nli_passed),
                "accepted_before_dedup": len(accepted),
                "frozen_claim_count": len(frozen),
                "semantic_dedup_candidate_pair_count": len(dedup_pairs),
                "semantic_dedup_positive_edge_count": sum(
                    1
                    for row in dedup_pair_judgments
                    if row["duplicate"]
                ),
                "semantic_dedup_collapsed_claim_count": (
                    len(accepted) - len(frozen)
                ),
                "residual_segment_count": len(residual_segments),
                "proposal_model": proposal_judge.model,
                "nli_model": nli_judge.model,
                "structural_model": structural_judge.model,
                "dedup_model": dedup_judge.model,
                "manual_claim_decisions": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_jsonl(
        output_dir / "claim_proposal_rejections.jsonl",
        proposal_rejections + residual_rejections,
    )
    ledger_manifest = seal_claim_ledger(
        output_dir,
        report,
        intended_for_cross_judge_reuse=True,
    )
    return {
        "segments": segments,
        "claims": frozen,
        "summary": json.loads(
            (output_dir / "claim_extraction_summary.json").read_text(encoding="utf-8")
        ),
        "ledger_manifest": ledger_manifest,
    }


__all__ = ["extract_report_claims", "segment_report", "write_jsonl"]
