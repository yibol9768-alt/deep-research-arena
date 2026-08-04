"""End-to-end DRA four-axis scoring pipeline.

Semantic judgments are delegated to an audited, fixed model.  Deterministic
code owns only provenance, observation reconstruction, identifier/span
validation, boolean gates, and score aggregation.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable

from src.scoring.audited_judge import AuditedJudge
from src.scoring.fact_evidence_resolver import (
    FrozenFactEvidenceResolver,
    HttpFrozenWorldGateway,
    SshPowerShellFrozenWorldGateway,
    claim_search_queries,
)
from src.scoring.frozen_claim_ledger import load_frozen_claim_ledger
from src.scoring.frozen_fact_packets import (
    load_frozen_fact_packets,
    seal_fact_packet_bundle,
)
from src.scoring.four_axis_score import FACT_VERDICTS, score_four_axis
from src.scoring.report_claim_pipeline import (
    CITE_RE,
    extract_report_claims,
    write_jsonl,
)
from src.scoring.task_evaluation_contract import (
    load_task_evaluation_contract,
)
from src.scoring.task_manifest_compiler import compile_task_manifest
from src.scoring.url_registry import FrozenURLRegistry


TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[._+-][A-Za-z0-9]+)*", re.UNICODE)
RAW_URL_RE = re.compile(r"https?://[^\s<>\])}\"']+")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scoring_protocol_manifest() -> dict[str, Any]:
    """Return a content-addressed snapshot of the executable score protocol."""

    scoring_dir = Path(__file__).resolve().parent
    source_files = {
        name: scoring_dir / filename
        for name, filename in {
            "four_axis_pipeline": "four_axis_pipeline.py",
            "four_axis_score": "four_axis_score.py",
            "audited_judge": "audited_judge.py",
            "report_claim_pipeline": "report_claim_pipeline.py",
            "task_manifest_compiler": "task_manifest_compiler.py",
            "task_evaluation_contract": "task_evaluation_contract.py",
            "frozen_claim_ledger": "frozen_claim_ledger.py",
            "frozen_fact_packets": "frozen_fact_packets.py",
            "fact_evidence_resolver": "fact_evidence_resolver.py",
        }.items()
    }
    prompt_texts = {
        "fact": FACT_SYSTEM,
        "fact_false_guard": FACT_FALSE_GUARD_SYSTEM,
        "fact_false_appeal": FACT_FALSE_APPEAL_SYSTEM,
        "fact_final_nli": FACT_FINAL_NLI_SYSTEM,
        "evidence_binding": EVIDENCE_SYSTEM,
        "atomic_coverage": ATOMIC_COVERAGE_SYSTEM,
        "research_coverage": RESEARCH_COVERAGE_SYSTEM,
        "rubric": RUBRIC_SYSTEM,
    }
    protocol = {
        "schema": "dra_scoring_protocol_snapshot_v1",
        "source_sha256": {
            name: _sha256_file(path) for name, path in source_files.items()
        },
        "prompt_sha256": {
            name: hashlib.sha256(text.encode("utf-8")).hexdigest()
            for name, text in prompt_texts.items()
        },
        "batch_contract": {
            "fact": 4,
            "fact_false_guard": 8,
            "fact_false_appeal": 8,
            "fact_final_nli": 8,
            "evidence_binding": 10,
            "atomic_coverage": 8,
            "research_coverage": 6,
            "rubric": 7,
        },
        "judge_contract": {
            "temperature": 0.0,
            "max_tokens": 8192,
            "response_format": "audited_json",
        },
        "retrieval_contract": {
            "graph_chunk_chars": 1100,
            "graph_overlap_chars": 180,
            "fact_candidate_top_k": 12,
            "candidate_similarity_directly_scores": False,
        },
        "aggregation_contract": {
            "quality": "equal_mean(Fact,Evidence,Completeness,Rubric)",
            "truth": "Provenance*Quality",
            "writing_elo_included": False,
        },
    }
    return {
        **protocol,
        "protocol_sha256": hashlib.sha256(
            json.dumps(
                protocol,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }


def _source_role(source_type: str) -> str:
    return {
        "product": "retailer",
        "forum": "community",
        "wikipedia": "encyclopedic_reference",
        "magento": "retailer",
        "postmill": "community",
        "search_result": "search_index",
    }.get(source_type, "unknown")


def reconstruct_native_observations(
    trace: dict[str, Any],
    citation_map: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rebuild observations solely from the harness-native trace."""

    documents: dict[str, dict[str, Any]] = {}
    searches: list[dict[str, Any]] = []
    for call in trace.get("tool_calls", []):
        call_id = str(call.get("call_id") or "")
        docs = call.get("documents") or []
        if not docs:
            docs = (call.get("raw_output") or {}).get("organic") or []
        urls: list[str] = []
        for index, doc in enumerate(docs):
            evidence_id = f"{call_id}-{index}"
            url = str(doc.get("url") or doc.get("link") or "")
            explicit_tier = str(doc.get("observation_tier") or "")
            full_text = str(doc.get("raw_content") or "")
            snippet = str(
                full_text
                or doc.get("snippet")
                or doc.get("summary")
                or doc.get("text")
                or ""
            )
            if explicit_tier in {"full_page", "search_snippet"}:
                observation_tier = explicit_tier
            elif full_text:
                observation_tier = "full_page"
            else:
                # ``text`` is an overloaded field in legacy harnesses and
                # often contains a search response.  Only raw_content or an
                # explicit adapter tier can certify a complete page.
                observation_tier = "search_snippet"
            documents[evidence_id] = {
                "evidence_id": evidence_id,
                "call_id": call_id,
                "document_index": index,
                "tool_name": call.get("tool_name"),
                "query": (call.get("raw_output") or {}).get("query")
                or call.get("query"),
                "url": url,
                "title": str(doc.get("title") or ""),
                "observed_text": snippet,
                "observation_tier": observation_tier,
                "observed": bool(snippet),
                "delivery_sha256": hashlib.sha256(
                    snippet.encode("utf-8")
                ).hexdigest(),
            }
            if url:
                urls.append(url)
        searches.append(
            {
                "call_id": call_id,
                "tool_name": call.get("tool_name"),
                "called": bool(call.get("called")),
                "error": call.get("error"),
                "urls_returned": urls,
            }
        )

    map_checks: list[dict[str, Any]] = []
    for row in citation_map:
        evidence_id = str(row.get("evidence_id") or "")
        native = documents.get(evidence_id)
        map_url = str(row.get("url") or (row.get("document") or {}).get("url") or "")
        map_checks.append(
            {
                "evidence_id": evidence_id,
                "present_in_native_trace": native is not None,
                "url_matches": bool(native and native["url"] == map_url),
                "text_present": bool(native and native["observed_text"]),
            }
        )
    return {
        "schema": "dra_native_observation_projection_v1",
        "tool_call_count": len(trace.get("tool_calls", [])),
        "document_count": len(documents),
        "documents": documents,
        "searches": searches,
        "citation_map_checks": map_checks,
        "citation_map_fully_attributable": all(
            row["present_in_native_trace"] and row["url_matches"]
            for row in map_checks
        ),
    }


def _blob_to_text(blob: Path) -> str:
    text = blob.read_text(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text

    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in {
                    "title",
                    "snippet",
                    "text",
                    "body",
                    "content",
                    "description",
                    "query",
                }:
                    if isinstance(child, str):
                        parts.append(child)
                    else:
                        walk(child)
                elif isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return "\n".join(parts) if parts else text


def load_fact_corpus(
    graph_dir: Path,
    *,
    chunk_chars: int = 1100,
    overlap_chars: int = 180,
) -> list[dict[str, Any]]:
    registry = _read_json(graph_dir / "corpus_registry.json")
    chunks: list[dict[str, Any]] = []
    for entry in registry.get("entries", []):
        source_type = str(entry.get("source_type") or "unknown")
        if source_type in {"case_spec", "search_result"}:
            continue
        blob = graph_dir / "blobs" / str(entry["content_sha256"])
        if not blob.exists():
            continue
        text = _blob_to_text(blob).strip()
        if not text:
            continue
        step = max(1, chunk_chars - overlap_chars)
        for start in range(0, len(text), step):
            chunk_text = text[start : start + chunk_chars]
            if len(chunk_text.strip()) < 80:
                continue
            chunks.append(
                {
                    "span_id": f"world:{entry['registry_id']}:{start}",
                    "url": entry["source_url"],
                    "source_type": source_type,
                    "source_role": _source_role(source_type),
                    "start": start,
                    "end": start + len(chunk_text),
                    "text": chunk_text,
                    "sha256": hashlib.sha256(
                        chunk_text.encode("utf-8")
                    ).hexdigest(),
                }
            )
    return chunks


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def value_blind_fact_query(claim: dict[str, Any]) -> str:
    """Build retrieval text without the report's asserted object or value.

    Entity/model qualifiers remain discoverable, but numeric values, units,
    polarity, and the claim object are deliberately excluded from first-stage
    ranking. Structured value comparison belongs after retrieval.
    """

    queries = claim_search_queries(claim)
    return " ".join(_tokens(queries[0])) if queries else ""


def retrieve_fact_packet(
    claim: dict[str, Any],
    chunks: list[dict[str, Any]],
    *,
    top_k: int = 12,
    preferred_urls: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Deterministic value-blind lexical candidate retrieval.

    This remains a transition retriever, not the protocol-complete
    BM25+dense+structured+graph union required for a formal TEC.
    """

    query = value_blind_fact_query(claim)
    preferred_urls = preferred_urls or set()
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return []
    document_frequency: Counter[str] = Counter()
    tokenized: list[list[str]] = []
    for chunk in chunks:
        tokens = _tokens(str(chunk.get("text") or ""))
        tokenized.append(tokens)
        document_frequency.update(set(tokens) & query_tokens)
    n_docs = max(1, len(chunks))
    scored: list[tuple[float, int]] = []
    for index, (chunk, tokens) in enumerate(zip(chunks, tokenized)):
        counts = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            if counts[token]:
                idf = math.log((n_docs + 1) / (document_frequency[token] + 1)) + 1
                score += (1.0 + math.log(counts[token])) * idf
        chunk_text = str(chunk.get("text") or "")
        if str(claim.get("subject") or "").casefold() in chunk_text.casefold():
            score += 3.0
        if str(chunk.get("url") or "") in preferred_urls:
            # The report's own cited page is the first adjudication route, but
            # it is not an allowlist: globally retrieved alternatives remain.
            score += 5.0
        if chunk.get("retrieval_mode") == "structured_product_lookup":
            score += 2.0
        if score > 0.0:
            scored.append((score, index))
    scored.sort(key=lambda pair: (-pair[0], chunks[pair[1]]["span_id"]))

    selected: list[dict[str, Any]] = []
    per_url: Counter[str] = Counter()
    for score, index in scored:
        chunk = dict(chunks[index])
        url = str(chunk.get("url") or "")
        if per_url[url] >= 3:
            continue
        chunk["retrieval_score"] = round(score, 6)
        chunk["retrieval_query"] = query
        chunk["retrieval_mode"] = "value_blind_lexical_transition"
        selected.append(chunk)
        per_url[url] += 1
        if len(selected) >= top_k:
            break
    return selected


def _json_char_batches(
    rows: list[dict[str, Any]],
    *,
    char_budget: int,
    count_budget: int,
) -> list[list[dict[str, Any]]]:
    """Batch complete records without exceeding a serialized-input budget."""

    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for row in rows:
        row_chars = len(
            json.dumps(
                row,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        if current and (
            current_chars + row_chars > char_budget
            or len(current) >= count_budget
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(row)
        current_chars += row_chars
    if current:
        batches.append(current)
    return batches


FACT_SYSTEM = """You are the Fact verifier for a frozen-world report evaluator.
Judge each report claim using ONLY that claim's supplied evidence packet. The
packet was independently retrieved and does not reveal which pages the report
cited. Do not use parametric knowledge, browse, or fill gaps.

Preserve model/version, number, unit, condition, polarity, modality, comparison
direction, and attribution. A retailer page proves that the retailer made a
claim, not that performance was independently measured. A forum post proves
that a user reported an experience, not that all products behave that way.

Verdicts:
- true: packet spans establish the complete claim at the stated attribution
- false: packet spans directly refute the complete claim
- conflicted: credible packet spans support and refute it under matching scope
- unresolved: relevant packet exists but cannot establish or refute it
- out_of_world: packet contains no material evidence for this claim
- census_gap: reserved for a separately certified census omission; do not use
  it when the packet does not explicitly provide such a certificate
- exempt: not an external factual claim
- instrument_ambiguous: entity/claim/span cannot be judged reliably

For bounded_absence only, a true verdict may cite a supplied complete-scope
absence certificate instead of a positive text span. The certificate must name
the finite pages, their snapshot hashes, and the literal audited terms. Never
infer non-mention from a truncated packet.

Return each claim once as JSON:
{"verdicts":[{"claim_id":"p_0001","verdict":"true|false|conflicted|unresolved|out_of_world|census_gap|exempt|instrument_ambiguous",
"support_span_ids":[],"contradiction_span_ids":[],
"absence_certificate_ids":[],
"confidence":"high|medium|low","reason_code":"short_code",
"explanation":"brief packet-grounded explanation"}]}
"""


FACT_FALSE_GUARD_SYSTEM = """You are the false-verdict guard for a
frozen-world evaluator. Review only claims initially labeled false and the
exact spans cited as contradictions.

Uphold false ONLY when a supplied span directly concerns the same
entity/product/model/version, scope, condition, attribution, and time and
states an incompatible value or proposition. These are NOT contradictions:
- the packet discusses a different model or product
- the packet lacks the claimed fact
- a claimed page is absent from the packet
- a generic source differs from a model-specific claim without addressing it
- a rounded value is compatible with the source value

When there is no direct same-scope contradiction, downgrade to unresolved if
the packet is relevant but insufficient, or out_of_world if the target
entity/fact is absent. If the normalized claim dropped or blurred an
entity/model/version qualifier that is present in raw_text or report_context,
return instrument_ambiguous rather than treating another variant as a
contradiction. Do not use outside knowledge. Return JSON only:
{"verdicts":[{"claim_id":"p_0001",
"guard_verdict":"uphold_false|downgrade_unresolved|downgrade_out_of_world|instrument_ambiguous",
"validated_contradiction_span_ids":[],
"reason_code":"short_code","explanation":"brief span-grounded rationale"}]}
"""


FACT_FALSE_APPEAL_SYSTEM = """You are the final burden-of-proof appeal for a
Fact verdict. Each item survived an initial verifier and a false guard. Confirm
false only if the cited text directly states an incompatible proposition about
the same entity/model/version, condition, attribution, and time.

Mandatory rules:
- absence or non-mention is not contradiction
- a different product/model is not contradiction
- a standard definition does not refute a claim that some users reported a
  belief or experience
- compatible rounding is not contradiction (for example 77 percent equals
  3.85 out of 5 and is compatible with a displayed 3.9 out of 5)
- an extractor that dropped a model/version qualifier is instrument ambiguous

Use only the supplied text. Return JSON only:
{"verdicts":[{"claim_id":"p_0001",
"appeal_verdict":"confirmed_direct_false|not_direct_false|instrument_ambiguous",
"reason_code":"short_code","explanation":"brief rationale"}]}
"""


FACT_FINAL_NLI_SYSTEM = """You are the final same-scope NLI gate for proposed
false claims. Use only the supplied premise spans and hypothesis claim.
Return contradiction only when the premise explicitly asserts an incompatible
proposition about the same entity/model/version, condition, attribution, and
time. Missing information, non-mention, a different model, or a generic source
is neutral. Return JSON only:
{"judgments":[{"claim_id":"p_0001",
"nli_relation":"contradiction|entailment|neutral",
"same_scope":"pass|fail","reason_code":"short_code"}]}
"""


EVIDENCE_SYSTEM = """You are the citation-binding verifier. Judge only the
relationship between each report claim/local context and the exact source text
the harness observed. Do not judge world truth and do not use outside
knowledge.

For each binding decide:
- bound: the citation is locally attached to this claim, rather than merely
  appearing somewhere nearby
- support_verdict: support, refute, insufficient, wrong_scope, wrong_role, or
  ambiguous
- role_ok: the source role can support the wording and attribution strength

A search snippet can fully support a shallow fact only when the snippet itself
contains the complete support. URL/title alone cannot support a deeper claim.
A search snippet can never establish bounded absence or non-mention on a page;
that requires an observed complete page for the entire stated scope.
A different model/product or generic category does not support a same-model
claim. Return JSON only:
{"verdicts":[{"binding_id":"b_0001","bound":true,
"support_verdict":"support|refute|insufficient|wrong_scope|wrong_role|ambiguous",
"role_ok":true,"confidence":"high|medium|low",
"reason_code":"short_code","explanation":"brief text-only rationale"}]}
"""


ATOMIC_COVERAGE_SYSTEM = """You are matching frozen atomic TEC units to
accepted report claims. Use only the supplied unit statements and report
claims. Do not use world knowledge. A unit is content-covered only when one or
more claims preserve its subject, predicate, object, direction, conditions,
polarity, and attribution. Merely naming the entity is not coverage.
matched_claim_ids is a compact witness list, not an exhaustive list: return at
most four best-matching IDs per unit and return [] when content_covered is
false. Return every unit once:
{"verdicts":[{"unit_id":"atomic:F1","content_covered":true,
"matched_claim_ids":[],"reason_code":"short_code"}]}
"""


RESEARCH_COVERAGE_SYSTEM = """You are matching higher-order Deep Research units
to a report. Use only the report and unit contracts. Do not judge external
truth. A comparison must align the required candidates and constraint; a
mechanism needs direction and conditions; a conflict needs both sides and
scope; synthesis must combine rather than list sources; a decision must connect
constraints, evidence limits, and conclusion.

For each unit, return a compact witness set rather than every remotely related
claim: at most four matched_claim_ids and at most three exact_quotes. Each
quote must be copied verbatim from the report and should be no longer than 300
characters. When content_covered is false, return both arrays empty. Return
JSON:
{"verdicts":[{"unit_id":"research:K_X","content_covered":true,
"matched_claim_ids":[],"exact_quotes":[],
"reason_code":"short_code","explanation":"brief rationale"}]}
"""


RUBRIC_SYSTEM = """You are judging fulfillment of frozen task requirements.
Use only the report and the supplied requirement. Do not award credit for
related facts when the requested comparison, audit, caveat, procedure, or
decision was not performed. Do not judge source truth here.

Use fulfilled, partially_fulfilled, not_fulfilled, or ambiguous. Partial is
allowed only when a naturally divisible requirement is genuinely completed in
part. Return at most three exact_quotes per item; each must be copied verbatim
from the report and no longer than 300 characters. Copy each rubric_id
byte-for-byte from valid_rubric_ids, return every input item exactly once and
in input order, and never emit a placeholder identifier. Return JSON:
{"verdicts":[{"rubric_id":"EXACT_ID_FROM_VALID_RUBRIC_IDS",
"verdict":"fulfilled|partially_fulfilled|not_fulfilled|ambiguous",
"exact_quotes":[],"reason_code":"short_code",
"explanation":"brief rationale"}]}
"""


def _fact_response_schema(item_count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "minItems": item_count,
                "maxItems": item_count,
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string", "maxLength": 32},
                        "verdict": {
                            "type": "string",
                            "enum": sorted(FACT_VERDICTS),
                        },
                        "support_span_ids": {
                            "type": "array",
                            "maxItems": 16,
                            "items": {"type": "string", "maxLength": 256},
                        },
                        "contradiction_span_ids": {
                            "type": "array",
                            "maxItems": 16,
                            "items": {"type": "string", "maxLength": 256},
                        },
                        "absence_certificate_ids": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {"type": "string", "maxLength": 256},
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                        "reason_code": {"type": "string", "maxLength": 128},
                        "explanation": {"type": "string", "maxLength": 1000},
                    },
                    "required": [
                        "claim_id",
                        "verdict",
                        "support_span_ids",
                        "contradiction_span_ids",
                        "absence_certificate_ids",
                        "confidence",
                        "reason_code",
                        "explanation",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["verdicts"],
        "additionalProperties": False,
    }


def _evidence_response_schema(item_count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "minItems": item_count,
                "maxItems": item_count,
                "items": {
                    "type": "object",
                    "properties": {
                        "binding_id": {"type": "string", "maxLength": 32},
                        "bound": {"type": "boolean"},
                        "support_verdict": {
                            "type": "string",
                            "enum": [
                                "support",
                                "refute",
                                "insufficient",
                                "wrong_scope",
                                "wrong_role",
                                "ambiguous",
                            ],
                        },
                        "role_ok": {"type": "boolean"},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                        "reason_code": {"type": "string", "maxLength": 128},
                        "explanation": {"type": "string", "maxLength": 1000},
                    },
                    "required": [
                        "binding_id",
                        "bound",
                        "support_verdict",
                        "role_ok",
                        "confidence",
                        "reason_code",
                        "explanation",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["verdicts"],
        "additionalProperties": False,
    }


def _research_coverage_response_schema(
    item_count: int,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "minItems": item_count,
                "maxItems": item_count,
                "items": {
                    "type": "object",
                    "properties": {
                        "unit_id": {"type": "string", "maxLength": 128},
                        "content_covered": {"type": "boolean"},
                        "matched_claim_ids": {
                            "type": "array",
                            "maxItems": 4,
                            "items": {"type": "string", "maxLength": 32},
                        },
                        "exact_quotes": {
                            "type": "array",
                            "maxItems": 3,
                            "items": {
                                "type": "string",
                                "maxLength": 300,
                            },
                        },
                        "reason_code": {"type": "string", "maxLength": 128},
                        "explanation": {"type": "string", "maxLength": 1000},
                    },
                    "required": [
                        "unit_id",
                        "content_covered",
                        "matched_claim_ids",
                        "exact_quotes",
                        "reason_code",
                        "explanation",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["verdicts"],
        "additionalProperties": False,
    }


def _atomic_coverage_response_schema(
    item_count: int,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "minItems": item_count,
                "maxItems": item_count,
                "items": {
                    "type": "object",
                    "properties": {
                        "unit_id": {"type": "string", "maxLength": 128},
                        "content_covered": {"type": "boolean"},
                        "matched_claim_ids": {
                            "type": "array",
                            "maxItems": 4,
                            "items": {"type": "string", "maxLength": 32},
                        },
                        "reason_code": {"type": "string", "maxLength": 128},
                    },
                    "required": [
                        "unit_id",
                        "content_covered",
                        "matched_claim_ids",
                        "reason_code",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["verdicts"],
        "additionalProperties": False,
    }


def judge_facts(
    claims: list[dict[str, Any]],
    corpus_chunks: list[dict[str, Any]],
    judge: AuditedJudge,
    output_dir: Path,
    *,
    resolver: FrozenFactEvidenceResolver | None = None,
    frozen_packets: list[dict[str, Any]] | None = None,
    claim_ledger_sha256: str | None = None,
) -> list[dict[str, Any]]:
    material = [
        row
        for row in claims
        if row.get("claim_kind")
        in {"external_atomic", "derived_arithmetic", "bounded_absence"}
    ]
    packets: list[dict[str, Any]]
    if frozen_packets is not None:
        packets = list(frozen_packets)
    else:
        if resolver is not None:
            resolver.prepare(material)
        packets = []
        for claim in material:
            resolved = (
                resolver.resolve(claim)
                if resolver is not None
                else {
                    "chunks": corpus_chunks,
                    "preferred_urls": set(),
                    "absence_certificate": None,
                    "resolution_audit": {
                        "claim_id": claim["claim_id"],
                        "gateway_available": False,
                        "chunk_count": len(corpus_chunks),
                    },
                }
            )
            spans = retrieve_fact_packet(
                claim,
                resolved["chunks"],
                preferred_urls=set(resolved.get("preferred_urls") or set()),
            )
            absence_certificate = resolved.get("absence_certificate")
            packets.append(
                {
                    "claim_id": claim["claim_id"],
                    "claim": claim["normalized_claim"],
                    "claim_kind": claim.get("claim_kind"),
                    "attribution": claim.get("attribution"),
                    "qualifiers": claim.get("qualifiers", {}),
                    "absence_certificate": absence_certificate,
                    "resolution_audit": resolved.get("resolution_audit", {}),
                    "evidence_spans": [
                        {
                            "span_id": row["span_id"],
                            "url": row["url"],
                            "source_role": row["source_role"],
                            "text": row["text"],
                        }
                        for row in spans
                    ],
                }
            )
    if resolver is not None and frozen_packets is None:
        write_jsonl(
            output_dir / "fact_evidence_resolution.jsonl",
            sorted(
                resolver.audit_rows,
                key=lambda row: str(row.get("claim_id") or ""),
            ),
        )
        gateway_rows = getattr(resolver.gateway, "audit_rows", [])
        write_jsonl(
            output_dir / "evaluator-fetch-ledger.jsonl",
            sorted(
                gateway_rows,
                key=lambda row: (
                    str(row.get("operation") or ""),
                    str(row.get("query") or ""),
                    str(row.get("url") or ""),
                ),
            ),
        )
    packet_dir = output_dir / "fact_packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    for packet in packets:
        (packet_dir / f"{packet['claim_id']}.json").write_text(
            json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if claim_ledger_sha256:
        seal_fact_packet_bundle(
            packet_dir,
            claims,
            claim_ledger_sha256=claim_ledger_sha256,
        )

    verdicts: list[dict[str, Any]] = []

    def verify_batch(batch: list[dict[str, Any]], label: str) -> None:
        try:
            response = judge.call_json(
                f"fact-verifier-{label}",
                FACT_SYSTEM,
                {"claims": batch},
                expected_top_key="verdicts",
                max_tokens=4096,
                compact_payload=True,
                response_schema=_fact_response_schema(len(batch)),
            )
        except RuntimeError:
            # Provider context accounting can differ from character estimates.
            # Preserve every complete claim packet and retry smaller groups.
            if len(batch) <= 1:
                raise
            middle = len(batch) // 2
            verify_batch(batch[:middle], f"{label}a")
            verify_batch(batch[middle:], f"{label}b")
            return
        verdicts.extend(response.get("verdicts", []))

    fact_batches = _json_char_batches(
        packets,
        char_budget=70000,
        count_budget=4,
    )
    for batch_index, batch in enumerate(fact_batches, 1):
        verify_batch(batch, f"{batch_index:03d}")

    packet_map = {row["claim_id"]: row for row in packets}
    material_map = {row["claim_id"]: row for row in material}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in verdicts:
        claim_id = row.get("claim_id")
        if claim_id not in packet_map or claim_id in seen:
            continue
        seen.add(claim_id)
        allowed_spans = {
            span["span_id"] for span in packet_map[claim_id]["evidence_spans"]
        }
        raw_support_spans = list(row.get("support_span_ids", []))
        raw_contradiction_spans = list(row.get("contradiction_span_ids", []))
        raw_absence_certificates = list(
            row.get("absence_certificate_ids", [])
        )
        cited_spans = set(raw_support_spans) | set(raw_contradiction_spans)
        packet_certificate = packet_map[claim_id].get("absence_certificate")
        allowed_certificate_ids = {
            str(packet_certificate["certificate_id"])
        } if packet_certificate else set()
        verdict = row.get("verdict")
        if (
            verdict not in FACT_VERDICTS
            or not cited_spans.issubset(allowed_spans)
            or not set(raw_absence_certificates).issubset(
                allowed_certificate_ids
            )
        ):
            verdict = "instrument_ambiguous"
        elif verdict == "true" and not (
            raw_support_spans
            or (
                material_map[claim_id].get("claim_kind") == "bounded_absence"
                and raw_absence_certificates
            )
        ):
            verdict = "instrument_ambiguous"
        elif verdict == "false" and not raw_contradiction_spans:
            verdict = "instrument_ambiguous"
        elif verdict == "conflicted" and (
            not raw_support_spans or not raw_contradiction_spans
        ):
            verdict = "instrument_ambiguous"
        claim = next(item for item in material if item["claim_id"] == claim_id)
        normalized.append(
            {
                **row,
                "claim_id": claim_id,
                "verdict": verdict,
                "support_span_ids": [
                    span_id
                    for span_id in raw_support_spans
                    if span_id in allowed_spans
                ],
                "contradiction_span_ids": [
                    span_id
                    for span_id in raw_contradiction_spans
                    if span_id in allowed_spans
                ],
                "absence_certificate_ids": [
                    certificate_id
                    for certificate_id in raw_absence_certificates
                    if certificate_id in allowed_certificate_ids
                ],
                "materiality": float(claim.get("materiality", 1.0)),
                "normalized_claim": claim["normalized_claim"],
                "semantic_verdict": dict(row),
            }
        )
    for claim in material:
        if claim["claim_id"] not in seen:
            normalized.append(
                {
                    "claim_id": claim["claim_id"],
                    "verdict": "instrument_ambiguous",
                    "materiality": float(claim.get("materiality", 1.0)),
                    "normalized_claim": claim["normalized_claim"],
                    "reason_code": "missing_model_verdict",
                    "support_span_ids": [],
                    "contradiction_span_ids": [],
                }
            )

    false_rows = [row for row in normalized if row["verdict"] == "false"]
    false_guard_rows: list[dict[str, Any]] = []
    for batch_no in range(0, len(false_rows), 8):
        batch = false_rows[batch_no : batch_no + 8]
        guard_items: list[dict[str, Any]] = []
        for row in batch:
            packet = packet_map[row["claim_id"]]
            spans = {
                span["span_id"]: span
                for span in packet.get("evidence_spans", [])
            }
            guard_items.append(
                {
                    "claim_id": row["claim_id"],
                    "claim": row["normalized_claim"],
                    "raw_text": material_map[row["claim_id"]]["report_span"][
                        "raw_text"
                    ],
                    "report_context": material_map[row["claim_id"]].get(
                        "report_context",
                        material_map[row["claim_id"]]["report_span"]["raw_text"],
                    ),
                    "structured_subject": material_map[row["claim_id"]].get(
                        "subject"
                    ),
                    "structured_qualifiers": material_map[row["claim_id"]].get(
                        "qualifiers", {}
                    ),
                    "initial_reason": row.get("explanation"),
                    "contradiction_spans": [
                        {
                            "span_id": span_id,
                            "url": spans[span_id]["url"],
                            "source_role": spans[span_id]["source_role"],
                            "text": spans[span_id]["text"],
                        }
                        for span_id in row.get("contradiction_span_ids", [])
                        if span_id in spans
                    ],
                }
            )
        response = judge.call_json(
            f"fact-false-guard-{batch_no // 8 + 1:03d}",
            FACT_FALSE_GUARD_SYSTEM,
            {"items": guard_items},
            expected_top_key="verdicts",
        )
        false_guard_rows.extend(response.get("verdicts", []))
    guard_map = {
        row.get("claim_id"): row
        for row in false_guard_rows
        if row.get("claim_id")
    }
    guard_to_fact = {
        "uphold_false": "false",
        "downgrade_unresolved": "unresolved",
        "downgrade_out_of_world": "out_of_world",
        "instrument_ambiguous": "instrument_ambiguous",
    }
    for row in normalized:
        if row["verdict"] != "false":
            continue
        guard = guard_map.get(row["claim_id"])
        row["initial_verdict"] = "false"
        row["false_guard"] = guard or {
            "guard_verdict": "instrument_ambiguous",
            "reason_code": "missing_guard_verdict",
        }
        row["verdict"] = guard_to_fact.get(
            (guard or {}).get("guard_verdict"),
            "instrument_ambiguous",
        )
    write_jsonl(output_dir / "fact_false_guard.jsonl", false_guard_rows)

    appealed_rows = [row for row in normalized if row["verdict"] == "false"]
    appeal_verdicts: list[dict[str, Any]] = []
    for batch_no in range(0, len(appealed_rows), 8):
        batch = appealed_rows[batch_no : batch_no + 8]
        appeal_items: list[dict[str, Any]] = []
        for row in batch:
            packet = packet_map[row["claim_id"]]
            spans = {
                span["span_id"]: span
                for span in packet.get("evidence_spans", [])
            }
            claim = material_map[row["claim_id"]]
            appeal_items.append(
                {
                    "claim_id": row["claim_id"],
                    "claim": row["normalized_claim"],
                    "raw_text": claim["report_span"]["raw_text"],
                    "report_context": claim.get(
                        "report_context", claim["report_span"]["raw_text"]
                    ),
                    "structured_subject": claim.get("subject"),
                    "structured_qualifiers": claim.get("qualifiers", {}),
                    "guard_explanation": row["false_guard"].get("explanation"),
                    "contradiction_spans": [
                        {
                            "span_id": span_id,
                            "url": spans[span_id]["url"],
                            "source_role": spans[span_id]["source_role"],
                            "text": spans[span_id]["text"],
                        }
                        for span_id in row.get("contradiction_span_ids", [])
                        if span_id in spans
                    ],
                }
            )
        response = judge.call_json(
            f"fact-false-appeal-{batch_no // 8 + 1:03d}",
            FACT_FALSE_APPEAL_SYSTEM,
            {"items": appeal_items},
            expected_top_key="verdicts",
        )
        appeal_verdicts.extend(response.get("verdicts", []))
    appeal_map = {
        row.get("claim_id"): row
        for row in appeal_verdicts
        if row.get("claim_id")
    }
    for row in normalized:
        if row["verdict"] != "false":
            continue
        appeal = appeal_map.get(row["claim_id"])
        row["false_appeal"] = appeal or {
            "appeal_verdict": "instrument_ambiguous",
            "reason_code": "missing_appeal_verdict",
        }
        if (appeal or {}).get("appeal_verdict") == "not_direct_false":
            row["verdict"] = "unresolved"
        elif (appeal or {}).get("appeal_verdict") != "confirmed_direct_false":
            row["verdict"] = "instrument_ambiguous"
    write_jsonl(output_dir / "fact_false_appeal.jsonl", appeal_verdicts)

    final_false_rows = [row for row in normalized if row["verdict"] == "false"]
    final_nli_rows: list[dict[str, Any]] = []
    for batch_no in range(0, len(final_false_rows), 8):
        batch = final_false_rows[batch_no : batch_no + 8]
        items: list[dict[str, Any]] = []
        for row in batch:
            packet = packet_map[row["claim_id"]]
            spans = {
                span["span_id"]: span
                for span in packet.get("evidence_spans", [])
            }
            items.append(
                {
                    "claim_id": row["claim_id"],
                    "hypothesis": row["normalized_claim"],
                    "premise_spans": [
                        {
                            "span_id": span_id,
                            "source_role": spans[span_id]["source_role"],
                            "text": spans[span_id]["text"],
                        }
                        for span_id in row.get("contradiction_span_ids", [])
                        if span_id in spans
                    ],
                }
            )
        response = judge.call_json(
            f"fact-final-same-scope-nli-{batch_no // 8 + 1:03d}",
            FACT_FINAL_NLI_SYSTEM,
            {"items": items},
            expected_top_key="judgments",
        )
        final_nli_rows.extend(response.get("judgments", []))
    final_nli_map = {
        row.get("claim_id"): row
        for row in final_nli_rows
        if row.get("claim_id")
    }
    for row in normalized:
        if row["verdict"] != "false":
            continue
        nli = final_nli_map.get(row["claim_id"])
        row["final_false_nli"] = nli or {
            "nli_relation": "neutral",
            "same_scope": "fail",
            "reason_code": "missing_final_nli",
        }
        if not (
            (nli or {}).get("nli_relation") == "contradiction"
            and (nli or {}).get("same_scope") == "pass"
        ):
            row["verdict"] = "unresolved"
    write_jsonl(output_dir / "fact_final_false_nli.jsonl", final_nli_rows)
    write_jsonl(output_dir / "fact_verdicts.jsonl", normalized)
    return normalized


def _citation_map_by_id(
    citation_map: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("evidence_id")): row
        for row in citation_map
        if row.get("evidence_id")
    }


def _claim_relevant_observation_excerpt(
    claim_text: str,
    report_context: str,
    observed_text: str,
    *,
    chunk_chars: int = 1800,
    overlap_chars: int = 260,
    max_chunks: int = 3,
) -> dict[str, Any]:
    """Select deterministic claim-relevant windows from an observation.

    The complete observation remains in the execution ledger. This projection
    only bounds the semantic judge input and records exact offsets and hashes.
    """

    text = str(observed_text or "")
    document_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if len(text) <= chunk_chars * max_chunks:
        return {
            "text": text,
            "excerpted": False,
            "document_chars": len(text),
            "document_sha256": document_sha256,
            "windows": [
                {
                    "start": 0,
                    "end": len(text),
                    "sha256": document_sha256,
                }
            ]
            if text
            else [],
        }

    query_tokens = set(_tokens(f"{claim_text} {report_context}"))
    step = max(1, chunk_chars - overlap_chars)
    scored: list[tuple[float, int, str]] = []
    for start in range(0, len(text), step):
        value = text[start : start + chunk_chars]
        token_counts = Counter(_tokens(value))
        score = sum(
            (2.0 if any(character.isdigit() for character in token) else 1.0)
            * min(3, token_counts[token])
            for token in query_tokens
            if token_counts[token]
        )
        scored.append((score, start, value))
    chosen = sorted(
        sorted(scored, key=lambda row: (-row[0], row[1]))[:max_chunks],
        key=lambda row: row[1],
    )
    windows = [
        {
            "start": start,
            "end": start + len(value),
            "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        }
        for _score, start, value in chosen
    ]
    excerpt = "\n\n".join(
        f"[observed excerpt {start}:{start + len(value)}]\n{value}"
        for _score, start, value in chosen
    )
    return {
        "text": excerpt,
        "excerpted": True,
        "document_chars": len(text),
        "document_sha256": document_sha256,
        "windows": windows,
    }


def judge_citation_bindings(
    claims: list[dict[str, Any]],
    citation_map: list[dict[str, Any]],
    observations: dict[str, Any],
    registry: FrozenURLRegistry,
    judge: AuditedJudge,
    output_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cmap = _citation_map_by_id(citation_map)
    observed_docs = observations["documents"]
    candidates: list[dict[str, Any]] = []
    seen_binding_keys: set[tuple[str, int, str]] = set()
    for claim in claims:
        if claim.get("evidence_policy") != "citation_required":
            continue
        occurrences = claim.get("occurrences") or [
            {
                "report_span": claim["report_span"],
                "report_context": claim.get(
                    "report_context", claim["report_span"]["raw_text"]
                ),
                "citation_ids": claim.get("citation_ids", []),
            }
        ]
        for occurrence_index, occurrence in enumerate(occurrences):
            for citation_id in dict.fromkeys(
                occurrence.get("citation_ids", [])
            ):
                citation_id = str(citation_id)
                binding_key = (
                    str(claim["claim_id"]),
                    occurrence_index,
                    citation_id,
                )
                if binding_key in seen_binding_keys:
                    continue
                seen_binding_keys.add(binding_key)
                mapped = cmap.get(citation_id, {})
                observed = observed_docs.get(citation_id, {})
                url = str(
                    mapped.get("url")
                    or (mapped.get("document") or {}).get("url")
                    or observed.get("url")
                    or ""
                )
                inspected = registry.inspect(url) if url else {
                    "canonical_url": "",
                    "canonicalized": False,
                    "in_registry": False,
                    "snapshot_available": False,
                    "valid": False,
                    "source_type": "unknown",
                }
                observed_text = str(observed.get("observed_text") or "")
                local_report_context = occurrence.get(
                    "report_context",
                    occurrence["report_span"]["raw_text"],
                )
                observed_projection = _claim_relevant_observation_excerpt(
                    str(claim["normalized_claim"]),
                    str(local_report_context),
                    observed_text,
                )
                candidates.append(
                    {
                        "binding_id": f"b_{len(candidates) + 1:04d}",
                        "claim_id": claim["claim_id"],
                        "claim": claim["normalized_claim"],
                        "claim_kind": claim.get("claim_kind"),
                        "claim_raw_text": occurrence["report_span"]["raw_text"],
                        "local_report_context": local_report_context,
                        "occurrence_index": occurrence_index,
                        "citation_id": citation_id,
                        "citation_display_text": "",
                        "url": url,
                        "canonical_url": inspected.get("canonical_url"),
                        "source_role": _source_role(
                            str(inspected.get("source_type", "unknown"))
                        ),
                        "source_title": str(
                            mapped.get("title")
                            or (mapped.get("document") or {}).get("title")
                            or observed.get("title")
                            or ""
                        ),
                        "observed_text": observed_text,
                        "observed_text_projection": observed_projection,
                        "observation_tier": observed.get("observation_tier"),
                        "valid": bool(inspected.get("valid")),
                        "observed": bool(observed.get("observed")),
                        "url_inspection": inspected,
                    }
                )

    verdicts: list[dict[str, Any]] = []

    def verify_binding_batch(
        batch: list[dict[str, Any]], label: str
    ) -> None:
        semantic_input = [
            {
                "binding_id": row["binding_id"],
                "claim": row["claim"],
                "claim_kind": row["claim_kind"],
                "claim_raw_text": row["claim_raw_text"],
                "local_report_context": row["local_report_context"],
                "citation_id": row["citation_id"],
                "url": row["url"],
                "source_role": row["source_role"],
                "source_title": row["source_title"],
                "observed_text": row["observed_text_projection"]["text"],
                "observed_text_projection": {
                    key: value
                    for key, value in row["observed_text_projection"].items()
                    if key != "text"
                },
                "observation_tier": row["observation_tier"],
            }
            for row in batch
        ]
        try:
            response = judge.call_json(
                f"evidence-binding-verifier-{label}",
                EVIDENCE_SYSTEM,
                {"bindings": semantic_input},
                expected_top_key="verdicts",
                max_tokens=4096,
                compact_payload=True,
                response_schema=_evidence_response_schema(len(batch)),
            )
        except RuntimeError:
            if len(batch) <= 1:
                raise
            middle = len(batch) // 2
            verify_binding_batch(batch[:middle], f"{label}a")
            verify_binding_batch(batch[middle:], f"{label}b")
            return
        verdicts.extend(response.get("verdicts", []))

    semantic_candidates = [
        {
            **row,
            # Batch sizing uses the exact projected judge text, not the full
            # observation retained in the audit result.
            "observed_text": row["observed_text_projection"]["text"],
        }
        for row in candidates
    ]
    binding_batches = _json_char_batches(
        semantic_candidates,
        char_budget=70000,
        count_budget=8,
    )
    for batch_index, batch in enumerate(binding_batches, 1):
        verify_binding_batch(batch, f"{batch_index:03d}")
    verdict_map = {
        row.get("binding_id"): row for row in verdicts if row.get("binding_id")
    }
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        semantic = verdict_map.get(candidate["binding_id"], {})
        bound = bool(semantic.get("bound"))
        supports = semantic.get("support_verdict") == "support"
        role_ok = bool(semantic.get("role_ok"))
        complete_scope_observed = not (
            candidate.get("claim_kind") == "bounded_absence"
        ) or candidate.get("observation_tier") == "full_page"
        failure_reasons: list[str] = []
        if not candidate["valid"]:
            failure_reasons.append("fabricated_url")
        if not candidate["observed"]:
            failure_reasons.append("unobserved_citation")
        if not bound:
            failure_reasons.append("wrong_binding")
        if not supports:
            failure_reasons.append(
                "contradicted_citation"
                if semantic.get("support_verdict") == "refute"
                else "unsupported_citation"
            )
        if not role_ok:
            failure_reasons.append("wrong_role")
        if not complete_scope_observed:
            failure_reasons.append("incomplete_scope_observation")
        # URL existence is scored by Provenance. Evidence asks whether the
        # harness actually observed text that is locally bound, supportive,
        # and role-appropriate. An invalid URL normally also fails observation,
        # but is not counted a second time as an Evidence predicate.
        passed = (
            candidate["observed"]
            and bound
            and supports
            and role_ok
            and complete_scope_observed
        )
        results.append(
            {
                **candidate,
                "semantic_verdict": semantic,
                "bound": bound,
                "supports": supports,
                "role_ok": role_ok,
                "complete_scope_observed": complete_scope_observed,
                "passed": passed,
                "failure_reasons": failure_reasons,
            }
        )
    write_jsonl(output_dir / "citation_bindings.jsonl", results)

    grounded_claims = {
        row["claim_id"] for row in results if row["passed"]
    }
    required_claim_units = [
        {
            "unit_id": f"claim:{row['claim_id']}",
            "unit_kind": "atomic_claim",
            "claim_id": row["claim_id"],
            "grounded": row["claim_id"] in grounded_claims,
        }
        for row in claims
        if row.get("evidence_policy") == "citation_required"
    ]
    return results, required_claim_units


def judge_atomic_coverage(
    atomic_units: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    fact_verdicts: list[dict[str, Any]],
    passing_claim_ids: set[str],
    judge: AuditedJudge,
) -> list[dict[str, Any]]:
    fact_map = {row["claim_id"]: row["verdict"] for row in fact_verdicts}
    claim_rows = [
        {
            "claim_id": row["claim_id"],
            "claim": row["normalized_claim"],
            "attribution": row.get("attribution"),
            "qualifiers": row.get("qualifiers", {}),
            "fact_verdict": fact_map.get(row["claim_id"]),
            "has_passing_binding": row["claim_id"] in passing_claim_ids,
        }
        for row in claims
        if row.get("claim_kind")
        in {"external_atomic", "derived_arithmetic", "bounded_absence"}
    ]
    verdicts: list[dict[str, Any]] = []
    for batch_no in range(0, len(atomic_units), 8):
        batch = atomic_units[batch_no : batch_no + 8]
        response = judge.call_json(
            f"completeness-atomic-matcher-{batch_no // 8 + 1:03d}",
            ATOMIC_COVERAGE_SYSTEM,
            {
                "units": [
                    {
                        "unit_id": row["unit_id"],
                        "statement": row["statement"],
                    }
                    for row in batch
                ],
                "report_claims": claim_rows,
            },
            expected_top_key="verdicts",
            max_tokens=4096,
            compact_payload=True,
            response_schema=_atomic_coverage_response_schema(len(batch)),
        )
        verdicts.extend(response.get("verdicts", []))
    verdict_map = {row.get("unit_id"): row for row in verdicts}
    claim_ids = {row["claim_id"] for row in claim_rows}
    results: list[dict[str, Any]] = []
    for unit in atomic_units:
        verdict = verdict_map.get(unit["unit_id"], {})
        matched = [
            claim_id
            for claim_id in verdict.get("matched_claim_ids", [])
            if claim_id in claim_ids
        ]
        content = bool(verdict.get("content_covered")) and bool(matched)
        fact_ok = bool(matched) and all(
            fact_map.get(claim_id) == "true" for claim_id in matched
        )
        evidence_ok = (
            not unit.get("evidence_required", True)
            or any(claim_id in passing_claim_ids for claim_id in matched)
        )
        results.append(
            {
                **unit,
                "content_covered": content,
                # Completeness is pure semantic content coverage. Fact and
                # Evidence remain separate axes; grounded_covered is retained
                # as a diagnostic cross-axis view.
                "grounded_covered": content and fact_ok and evidence_ok,
                "matched_claim_ids": matched,
                "fact_gate_passed": fact_ok,
                "evidence_gate_passed": evidence_ok,
                "semantic_verdict": verdict,
            }
        )
    return results


def judge_research_coverage(
    report: str,
    research_units: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    passing_claim_ids: set[str],
    judge: AuditedJudge,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    claim_summary = [
        {
            "claim_id": row["claim_id"],
            "claim": row["normalized_claim"],
            "has_passing_binding": row["claim_id"] in passing_claim_ids,
        }
        for row in claims
    ]
    claim_ids = {row["claim_id"] for row in claims}
    verdicts: list[dict[str, Any]] = []
    # Small batches keep local 8B judges inside a bounded output contract.
    # The full report is still visible for every decision; only independent
    # unit verdicts are divided across calls.
    research_batch_size = 3
    for batch_no in range(0, len(research_units), research_batch_size):
        batch = research_units[batch_no : batch_no + research_batch_size]
        response = judge.call_json(
            (
                "completeness-research-matcher-"
                f"{batch_no // research_batch_size + 1:03d}"
            ),
            RESEARCH_COVERAGE_SYSTEM,
            {
                "report": report,
                "units": [
                    {
                        "unit_id": row["unit_id"],
                        "unit_type": row["unit_type"],
                        "statement": row["statement"],
                        "evidence_required": row["evidence_required"],
                    }
                    for row in batch
                ],
                "accepted_report_claims": claim_summary,
            },
            expected_top_key="verdicts",
            max_tokens=4096,
            compact_payload=True,
            response_schema=_research_coverage_response_schema(len(batch)),
        )
        verdicts.extend(response.get("verdicts", []))
    verdict_map = {row.get("unit_id"): row for row in verdicts}
    results: list[dict[str, Any]] = []
    required_units: list[dict[str, Any]] = []
    for unit in research_units:
        verdict = verdict_map.get(unit["unit_id"], {})
        quotes = [
            quote
            for quote in verdict.get("exact_quotes", [])
            if isinstance(quote, str) and quote in report
        ]
        matched = [
            claim_id
            for claim_id in verdict.get("matched_claim_ids", [])
            if claim_id in claim_ids
        ]
        content = bool(verdict.get("content_covered")) and bool(quotes)
        evidence_ok = (
            not unit.get("evidence_required", False)
            or (
                bool(matched)
                and any(claim_id in passing_claim_ids for claim_id in matched)
            )
        )
        grounded_covered = content and evidence_ok
        result = {
            **unit,
            "content_covered": content,
            "grounded_covered": grounded_covered,
            "matched_claim_ids": matched,
            "exact_quotes": quotes,
            "evidence_gate_passed": evidence_ok,
            "semantic_verdict": verdict,
        }
        results.append(result)
        if unit.get("evidence_required", False):
            required_units.append(
                {
                    "unit_id": unit["unit_id"],
                    "unit_kind": "higher_order",
                    "grounded": grounded_covered,
                }
            )
    return results, required_units


def judge_rubric(
    report: str,
    rubric_items: list[dict[str, Any]],
    judge: AuditedJudge,
) -> list[dict[str, Any]]:
    verdicts: list[dict[str, Any]] = []
    for batch_no in range(0, len(rubric_items), 7):
        batch = rubric_items[batch_no : batch_no + 7]
        response = judge.call_json(
            f"rubric-fulfillment-{batch_no // 7 + 1:03d}",
            RUBRIC_SYSTEM,
            {
                "report": report,
                "valid_rubric_ids": [row["rubric_id"] for row in batch],
                "rubric_items": [
                    {
                        "rubric_id": row["rubric_id"],
                        "origin": row["origin"],
                        "requirement": row["requirement"],
                    }
                    for row in batch
                ],
            },
            expected_top_key="verdicts",
        )
        verdicts.extend(response.get("verdicts", []))
    verdict_map = {row.get("rubric_id"): row for row in verdicts}
    results: list[dict[str, Any]] = []
    allowed = {
        "fulfilled",
        "partially_fulfilled",
        "not_fulfilled",
        "ambiguous",
    }
    for item in rubric_items:
        verdict = verdict_map.get(item["rubric_id"], {})
        quotes = [
            quote
            for quote in verdict.get("exact_quotes", [])
            if isinstance(quote, str) and quote in report
        ]
        label = verdict.get("verdict")
        if label not in allowed:
            label = "ambiguous"
        elif label in {"fulfilled", "partially_fulfilled"} and not quotes:
            # A positive model verdict without a verbatim report witness is
            # not auditable and cannot receive credit.
            label = "ambiguous"
        results.append(
            {
                **item,
                "verdict": label,
                "exact_quotes": quotes,
                "semantic_verdict": verdict,
            }
        )
    return results


def cited_url_rows(
    report: str,
    citation_map: list[dict[str, Any]],
    registry: FrozenURLRegistry,
) -> list[dict[str, Any]]:
    cmap = _citation_map_by_id(citation_map)
    by_canonical: dict[str, dict[str, Any]] = {}
    citation_ids = CITE_RE.findall(report)
    for citation_id in citation_ids:
        mapped = cmap.get(citation_id, {})
        url = str(
            mapped.get("url")
            or (mapped.get("document") or {}).get("url")
            or ""
        )
        inspected = registry.inspect(url) if url else {
            "raw_url": f"unresolved-citation-id:{citation_id}",
            "canonical_url": f"unresolved-citation-id:{citation_id}",
            "canonicalized": False,
            "in_registry": False,
            "snapshot_available": False,
            "valid": False,
            "source_type": "unknown",
            "registry_key": None,
            "registry_version": registry.version,
        }
        key = str(inspected["canonical_url"])
        row = by_canonical.setdefault(
            key,
            {
                **inspected,
                "citation_ids": [],
            },
        )
        row["citation_ids"].append(citation_id)
    for url in RAW_URL_RE.findall(report):
        inspected = registry.inspect(url)
        key = str(inspected["canonical_url"])
        by_canonical.setdefault(key, {**inspected, "citation_ids": []})
    return sorted(by_canonical.values(), key=lambda row: row["canonical_url"])


def build_execution_audit(
    observations: dict[str, Any],
    citation_map: list[dict[str, Any]],
    report: str,
) -> dict[str, Any]:
    cmap = _citation_map_by_id(citation_map)
    cited_ids = sorted(set(CITE_RE.findall(report)))
    cited_docs = [
        observations["documents"][citation_id]
        for citation_id in cited_ids
        if citation_id in observations["documents"]
    ]
    cited_urls = {
        str(
            cmap.get(citation_id, {}).get("url")
            or (cmap.get(citation_id, {}).get("document") or {}).get("url")
            or ""
        )
        for citation_id in cited_ids
    }
    cited_urls.discard("")
    search_urls = {
        url
        for search in observations.get("searches", [])
        for url in search.get("urls_returned", [])
        if url
    }
    snippet_urls = {
        row["url"]
        for row in cited_docs
        if row.get("observation_tier") == "search_snippet" and row.get("url")
    }
    full_page_urls = {
        row["url"]
        for row in cited_docs
        if row.get("observation_tier") == "full_page" and row.get("url")
    }
    tier_counts = Counter(
        row.get("observation_tier", "unknown") for row in cited_docs
    )
    return {
        "schema": "dra_execution_audit_v1",
        "native_tool_calls": observations.get("tool_call_count", 0),
        "native_observed_documents": observations.get("document_count", 0),
        "unique_search_returned_urls": len(search_urls),
        "unique_cited_urls": len(cited_urls),
        "search_discovered_url_rate": (
            len(cited_urls & search_urls) / len(cited_urls) if cited_urls else 0.0
        ),
        "snippet_observation_rate": (
            len(cited_urls & snippet_urls) / len(cited_urls) if cited_urls else 0.0
        ),
        "full_page_observation_rate": (
            len(cited_urls & full_page_urls) / len(cited_urls) if cited_urls else 0.0
        ),
        "fetched_200_rate": (
            len(cited_urls & full_page_urls) / len(cited_urls) if cited_urls else 0.0
        ),
        "search_returned_but_unopened_rate": (
            len(search_urls - full_page_urls) / len(search_urls) if search_urls else 0.0
        ),
        "observation_tier_counts": dict(sorted(tier_counts.items())),
        "citation_map_fully_attributable": observations.get(
            "citation_map_fully_attributable", False
        ),
        "shared_ledger_used": False,
    }


def _diagnostic_label(scores: dict[str, Any]) -> str:
    truth = scores["truth"]
    inner = [
        scores["fact"]["score"],
        scores["evidence"]["score"],
        scores["completeness"]["score"],
        scores["rubric"]["score"],
    ]
    resolution = scores["fact"]["resolution_rate"]
    if truth >= 0.80 and min(inner) >= 0.80 and resolution >= 0.80:
        return "strong_across_axes"
    if truth >= 0.70:
        return "high_aggregate_with_material_gaps"
    if truth >= 0.55:
        return "good_with_gaps"
    if truth >= 0.35:
        return "mixed"
    if truth >= 0.15:
        return "weak"
    return "very_weak"


def run_four_axis_pipeline(
    *,
    task_path: Path,
    report_path: Path,
    trace_path: Path,
    citation_map_path: Path,
    task_world_model_path: Path,
    research_test_suite_path: Path,
    graph_dir: Path,
    url_registry_path: Path,
    output_dir: Path,
    model: str = "deepseek-v4-flash",
    claim_proposal_model: str | None = None,
    nli_model: str | None = None,
    structural_model: str | None = None,
    fact_model: str | None = None,
    evidence_model: str | None = None,
    fact_search_base_url: str | None = None,
    fact_ssh_host: str | None = None,
    task_contract_dir: Path | None = None,
    frozen_claims_dir: Path | None = None,
    frozen_fact_packets_dir: Path | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    claim_proposal_model = claim_proposal_model or model
    nli_model = nli_model or model
    structural_model = structural_model or model
    fact_model = fact_model or model
    evidence_model = evidence_model or model
    task_contract_dir = (
        Path(task_contract_dir) if task_contract_dir is not None else None
    )
    frozen_claims_dir = (
        Path(frozen_claims_dir) if frozen_claims_dir is not None else None
    )
    frozen_fact_packets_dir = (
        Path(frozen_fact_packets_dir)
        if frozen_fact_packets_dir is not None
        else None
    )
    compiler_judge = (
        None
        if task_contract_dir is not None
        else AuditedJudge(
            output_dir / "judge_calls" / "compiler",
            model=structural_model,
        )
    )
    proposal_judge = (
        None
        if frozen_claims_dir is not None
        else AuditedJudge(
            output_dir / "judge_calls" / "claim_proposal",
            model=claim_proposal_model,
        )
    )
    nli_judge = (
        None
        if frozen_claims_dir is not None
        else AuditedJudge(
            output_dir / "judge_calls" / "claim_nli",
            model=nli_model,
        )
    )
    structural_judge = (
        None
        if frozen_claims_dir is not None
        else AuditedJudge(
            output_dir / "judge_calls" / "claim_structural",
            model=structural_model,
        )
    )
    fact_judge = AuditedJudge(
        output_dir / "judge_calls" / "fact",
        model=fact_model,
    )
    evidence_judge = AuditedJudge(
        output_dir / "judge_calls" / "evidence_coverage_rubric",
        model=evidence_model,
    )

    task = _read_json(task_path)
    report = report_path.read_text(encoding="utf-8")
    trace = _read_json(trace_path)
    citation_map = _read_json(citation_map_path)
    task_world_model = _read_json(task_world_model_path)
    research_test_suite = _read_json(research_test_suite_path)
    registry = FrozenURLRegistry.load(url_registry_path)
    if fact_search_base_url and fact_ssh_host:
        raise ValueError(
            "choose either fact_search_base_url or fact_ssh_host, not both"
        )
    if frozen_fact_packets_dir is not None and (
        fact_search_base_url or fact_ssh_host
    ):
        raise ValueError(
            "frozen Fact packets already define retrieval inputs; do not also "
            "configure a live Fact gateway"
        )

    if task_contract_dir is not None:
        tec = load_task_evaluation_contract(
            task_contract_dir,
            expected_task=task,
            expected_task_world_model=task_world_model,
            expected_research_test_suite=research_test_suite,
        )
        (output_dir / "task-contract-reference.json").write_text(
            json.dumps(
                {
                    "schema": "dra_task_contract_reference_v1",
                    "path": str(task_contract_dir.resolve()),
                    "contract_sha256": tec["manifest"]["contract_sha256"],
                    "contract_semantics": tec["manifest"][
                        "contract_semantics"
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        if compiler_judge is None:  # pragma: no cover - defensive invariant
            raise RuntimeError("runtime contract compilation has no judge")
        tec = compile_task_manifest(
            task,
            task_world_model,
            research_test_suite,
            compiler_judge,
            output_dir / "tec",
        )

    if frozen_claims_dir is not None:
        claims_artifact = load_frozen_claim_ledger(
            frozen_claims_dir,
            report,
        )
        (output_dir / "claim-ledger-reference.json").write_text(
            json.dumps(
                {
                    "schema": "dra_claim_ledger_reference_v1",
                    "path": str(frozen_claims_dir.resolve()),
                    "claim_ledger_sha256": claims_artifact["manifest"][
                        "claim_ledger_sha256"
                    ],
                    "report_sha256": claims_artifact["manifest"][
                        "report_sha256"
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        if (
            proposal_judge is None
            or nli_judge is None
            or structural_judge is None
        ):  # pragma: no cover - defensive invariant
            raise RuntimeError("runtime claim extraction has no judge")
        claims_artifact = extract_report_claims(
            report,
            proposal_judge,
            output_dir / "claims",
            nli_judge=nli_judge,
            structural_judge=structural_judge,
            dedup_judge=structural_judge,
        )
    claims = claims_artifact["claims"]
    claim_ledger_sha256 = (
        claims_artifact["manifest"]["claim_ledger_sha256"]
        if frozen_claims_dir is not None
        else claims_artifact["ledger_manifest"]["claim_ledger_sha256"]
    )
    frozen_fact_packets_artifact = None
    if frozen_fact_packets_dir is not None:
        frozen_fact_packets_artifact = load_frozen_fact_packets(
            frozen_fact_packets_dir,
            claims,
            expected_claim_ledger_sha256=claim_ledger_sha256,
        )

    input_paths = {
        "task": task_path,
        "report": report_path,
        "trace": trace_path,
        "citation_map": citation_map_path,
        "task_world_model": task_world_model_path,
        "research_test_suite": research_test_suite_path,
        "graph_manifest": graph_dir / "manifest.json",
        "url_registry": url_registry_path,
    }
    if task_contract_dir is not None:
        input_paths["task_contract_manifest"] = (
            task_contract_dir / "contract-manifest.json"
        )
    else:
        input_paths["runtime_tec_manifest"] = (
            output_dir / "tec" / "tec-manifest.json"
        )
    if frozen_claims_dir is not None:
        input_paths["claim_ledger_manifest"] = (
            frozen_claims_dir / "claim-ledger-manifest.json"
        )
    else:
        input_paths["runtime_claim_ledger_manifest"] = (
            output_dir / "claims" / "claim-ledger-manifest.json"
        )
    if frozen_fact_packets_dir is not None:
        input_paths["fact_packet_bundle_manifest"] = (
            frozen_fact_packets_dir / "fact-packet-bundle-manifest.json"
        )
    input_manifest = {
        "schema": "dra_four_axis_input_manifest_v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scoring_protocol": _scoring_protocol_manifest(),
        "models": {
            "default": model,
            "task_compiler": (
                None if task_contract_dir is not None else structural_model
            ),
            "claim_proposal": (
                None if frozen_claims_dir is not None else claim_proposal_model
            ),
            "nli": None if frozen_claims_dir is not None else nli_model,
            "structural": (
                None if frozen_claims_dir is not None else structural_model
            ),
            "fact": fact_model,
            "evidence_coverage_rubric": evidence_model,
        },
        "instrument_mode": {
            "task_contract": (
                "frozen" if task_contract_dir is not None else "runtime_compiled"
            ),
            "claim_ledger": (
                "frozen" if frozen_claims_dir is not None else "runtime_extracted"
            ),
            "fact_packets": (
                "frozen"
                if frozen_fact_packets_dir is not None
                else "runtime_retrieved"
            ),
        },
        "frozen_artifacts": {
            "task_contract": (
                {
                    "contract_sha256": tec["manifest"].get(
                        "contract_sha256"
                    ),
                    "contract_semantics": tec["manifest"].get(
                        "contract_semantics"
                    ),
                    "compiler_model": (
                        tec["manifest"].get("compiler") or {}
                    ).get("model"),
                }
                if task_contract_dir is not None
                else None
            ),
            "claim_ledger": (
                {
                    "claim_ledger_sha256": claims_artifact["manifest"][
                        "claim_ledger_sha256"
                    ],
                    "extractor_models": claims_artifact["manifest"].get(
                        "extractor_models"
                    ),
                }
                if frozen_claims_dir is not None
                else None
            ),
            "fact_packets": (
                {
                    "fact_packet_bundle_sha256": (
                        frozen_fact_packets_artifact["manifest"][
                            "fact_packet_bundle_sha256"
                        ]
                    ),
                    "claim_ledger_sha256": (
                        frozen_fact_packets_artifact["manifest"][
                            "claim_ledger_sha256"
                        ]
                    ),
                }
                if frozen_fact_packets_artifact is not None
                else None
            ),
        },
        "manual_claim_decisions": 0,
        "inputs": {
            name: {
                "path": str(path.resolve()),
                "sha256": _sha256_file(path),
            }
            for name, path in input_paths.items()
        },
    }
    (output_dir / "input-manifest.json").write_text(
        json.dumps(input_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    observations = reconstruct_native_observations(trace, citation_map)
    (output_dir / "native-observation-ledger.json").write_text(
        json.dumps(observations, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    corpus_chunks = load_fact_corpus(graph_dir)
    fact_gateway = None
    if frozen_fact_packets_artifact is not None:
        fact_gateway = None
    elif fact_ssh_host:
        fact_gateway = SshPowerShellFrozenWorldGateway(
            ssh_host=fact_ssh_host,
            search_base_url=fact_search_base_url or "http://localhost:8081",
        )
    elif fact_search_base_url:
        fact_gateway = HttpFrozenWorldGateway(
            search_base_url=fact_search_base_url,
        )
    fact_resolver = FrozenFactEvidenceResolver(
        seed_chunks=corpus_chunks,
        citation_map=citation_map,
        observations=observations,
        registry=registry,
        gateway=fact_gateway,
    )
    (output_dir / "fact-corpus-summary.json").write_text(
        json.dumps(
            {
                "schema": "dra_fact_evidence_resolver_summary_v2",
                "seed_chunk_count": len(corpus_chunks),
                "seed_source_url_count": len(
                    {row["url"] for row in corpus_chunks}
                ),
                "graph_dir": str(graph_dir.resolve()),
                "seed_is_world_boundary": False,
                "resolver_mode": (
                    "frozen_fact_packets"
                    if frozen_fact_packets_artifact is not None
                    else "ssh_frozen_world"
                    if fact_ssh_host
                    else "http_frozen_world"
                    if fact_search_base_url
                    else "seed_plus_agent_observations"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    fact_verdicts = judge_facts(
        claims,
        corpus_chunks,
        fact_judge,
        output_dir,
        resolver=fact_resolver,
        frozen_packets=(
            frozen_fact_packets_artifact["packets"]
            if frozen_fact_packets_artifact is not None
            else None
        ),
        claim_ledger_sha256=claim_ledger_sha256,
    )
    bindings, claim_required_units = judge_citation_bindings(
        claims,
        citation_map,
        observations,
        registry,
        evidence_judge,
        output_dir,
    )
    passing_claim_ids = {
        row["claim_id"] for row in bindings if row["passed"]
    }
    atomic_coverage = judge_atomic_coverage(
        tec["atomic_units"],
        claims,
        fact_verdicts,
        passing_claim_ids,
        evidence_judge,
    )
    research_coverage, research_grounding_diagnostics = judge_research_coverage(
        report,
        tec["research_units"],
        claims,
        passing_claim_ids,
        evidence_judge,
    )
    completeness_units = atomic_coverage + research_coverage
    write_jsonl(output_dir / "completeness_units.jsonl", completeness_units)
    # Evidence is report-conditional: every citation-required claim the report
    # chose to make enters the recall denominator.  Task-fixed research breadth
    # belongs to Completeness and is not counted a second time here.
    citation_required_units = claim_required_units
    write_jsonl(
        output_dir / "citation_required_units.jsonl",
        citation_required_units,
    )
    write_jsonl(
        output_dir / "research_grounding_diagnostics.jsonl",
        research_grounding_diagnostics,
    )
    rubric_verdicts = judge_rubric(
        report,
        tec["rubric_items"],
        evidence_judge,
    )
    write_jsonl(output_dir / "rubric_verdicts.jsonl", rubric_verdicts)
    urls = cited_url_rows(report, citation_map, registry)
    write_jsonl(output_dir / "cited_urls.jsonl", urls)
    execution_audit = build_execution_audit(observations, citation_map, report)
    (output_dir / "execution-audit.json").write_text(
        json.dumps(execution_audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    packet = {
        "schema": "dra_four_axis_judgment_packet_v2",
        "task_id": task.get("task_id") or tec["manifest"].get("task_id"),
        "material_claims": fact_verdicts,
        "citation_bindings": bindings,
        "citation_required_units": citation_required_units,
        "completeness_units": completeness_units,
        "rubric_items": rubric_verdicts,
        "cited_urls": urls,
    }
    (output_dir / "score-packet.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    scores = score_four_axis(packet)
    formal_notes = list(tec["manifest"]["formal_eligibility_notes"])
    instrument_warnings: list[str] = []
    if task_contract_dir is None:
        formal_notes.append(
            "task evaluation contract was compiled inside this report-scoring run"
        )
    if frozen_claims_dir is None:
        instrument_warnings.append(
            "Claim Ledger was extracted in this run; cross-judge comparisons "
            "must reuse its sealed ledger rather than re-extract claims"
        )
    if fact_gateway is None and frozen_fact_packets_artifact is None:
        formal_notes.append(
            "Fact resolver could not query and fetch the complete frozen sandbox"
        )
    if not registry.formal_snapshot_attestation_available:
        formal_notes.append(
            "URL registry lacks per-snapshot hashes and build attestation"
        )
    if frozen_claims_dir is None:
        instrument_warnings.append(
            "the official fixed-judge protocol uses one Qwen snapshot for "
            "claim extraction and semantic scoring; formal publication still "
            "requires an axis-level human calibration certificate"
        )
    else:
        instrument_warnings.append(
            "model-name separation is not treated as a validity certificate; "
            "the frozen extractor and active judges still require human calibration"
        )
    if not observations["citation_map_fully_attributable"]:
        formal_notes.append(
            "citation map is not fully attributable to the native harness trace"
        )
    if scores["fact"]["verdict_counts"].get("instrument_ambiguous", 0):
        formal_notes.append("Fact contains unresolved instrument-ambiguous verdicts")
    for gap_verdict in ("retrieval_failure", "census_gap", "world_scope_gap"):
        if scores["fact"]["verdict_counts"].get(gap_verdict, 0):
            formal_notes.append(
                f"Fact contains scorer-side {gap_verdict} verdicts"
            )
    if scores["rubric"]["ambiguous_count"]:
        formal_notes.append("Rubric contains ambiguous model verdicts")
    formal_eligible = not formal_notes
    result = {
        "schema": "dra_four_axis_score_v2",
        "task_id": packet["task_id"],
        "models": input_manifest["models"],
        "manual_claim_decisions": claims_artifact["summary"].get(
            "manual_claim_decisions", 0
        ),
        "instrument_mode": input_manifest["instrument_mode"],
        "instrument_warnings": instrument_warnings,
        "task_contract_sha256": (
            tec["manifest"].get("contract_sha256")
            if task_contract_dir is not None
            else None
        ),
        "claim_ledger_sha256": (
            claims_artifact["manifest"].get("claim_ledger_sha256")
            if frozen_claims_dir is not None
            else claims_artifact.get("ledger_manifest", {}).get(
                "claim_ledger_sha256"
            )
        ),
        "fact_packet_bundle_sha256": (
            frozen_fact_packets_artifact["manifest"][
                "fact_packet_bundle_sha256"
            ]
            if frozen_fact_packets_artifact is not None
            else (
                _read_json(
                    output_dir
                    / "fact_packets"
                    / "fact-packet-bundle-manifest.json"
                ).get("fact_packet_bundle_sha256")
                if (
                    output_dir
                    / "fact_packets"
                    / "fact-packet-bundle-manifest.json"
                ).is_file()
                else None
            )
        ),
        "formal_eligible": formal_eligible,
        "formal_eligibility_notes": formal_notes,
        "formal_truth": scores["truth"] if formal_eligible else None,
        "diagnostic_score_available": True,
        "diagnostic_label": _diagnostic_label(scores),
        "execution_audit": execution_audit,
        **scores,
    }
    (output_dir / "score.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    weakest = min(
        ("Fact", scores["fact"]["score"]),
        ("Evidence", scores["evidence"]["score"]),
        ("Completeness", scores["completeness"]["score"]),
        ("Rubric", scores["rubric"]["score"]),
        key=lambda pair: pair[1],
    )
    strongest = max(
        ("Fact", scores["fact"]["score"]),
        ("Evidence", scores["evidence"]["score"]),
        ("Completeness", scores["completeness"]["score"]),
        ("Rubric", scores["rubric"]["score"]),
        key=lambda pair: pair[1],
    )
    summary = f"""# DRA four-axis diagnostic score

- Task: `{packet['task_id']}`
- Judge: `{model}` at temperature 0
- Manual claim decisions: `0`
- Diagnostic label: **{result['diagnostic_label']}**
- Diagnostic linear Truth: **{scores['truth_linear_diagnostic']:.4f}**
- Geometric formal candidate: **{scores['truth_geometric_candidate']:.4f}**
- Published formal Truth: **{result['formal_truth']}**
- Quality: {scores['quality']:.4f}
- Provenance: {scores['provenance']['score']:.4f}
- Fact: {scores['fact']['score']:.4f}
- Fact resolution rate: {scores['fact']['resolution_rate']:.4f}
- Fact adjudication coverage: {scores['fact']['adjudication_coverage']:.4f}
- Evidence: {scores['evidence']['score']:.4f}
- Completeness: {scores['completeness']['score']:.4f}
- Rubric: {scores['rubric']['score']:.4f}
- Strongest inner axis: {strongest[0]} ({strongest[1]:.4f})
- Weakest inner axis: {weakest[0]} ({weakest[1]:.4f})
- Formal eligible: `{str(formal_eligible).lower()}`
- Full-page observation rate: {execution_audit['full_page_observation_rate']:.4f}
- Snippet observation rate: {execution_audit['snippet_observation_rate']:.4f}

The diagnostic score is always emitted. Formal eligibility is a separate
publication/audit status and does not erase the report's measured result.
"""
    (output_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    return result


__all__ = [
    "build_execution_audit",
    "load_fact_corpus",
    "reconstruct_native_observations",
    "retrieve_fact_packet",
    "run_four_axis_pipeline",
    "value_blind_fact_query",
]
