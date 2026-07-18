"""Score one or more deep-tier agent answers against the deep golden.

Combines:
  - URLCoverageVerifier  (deterministic: must-cite / pool / domain balance)
  - gpt-5-chat judge     (checklist verdicts via judge_client.py)
  - markdown spec checks (word count, citation count, paragraphs)

Usage:
    python3 scripts/score_deep_answer.py \
        --task dr_cross_deep_0001 \
        --answer data/results/deep/gpt-researcher__dr_cross_deep_0001_smoke.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.verifiers.url_coverage_verifier import URLCoverageVerifier  # noqa: E402
from src.verifiers.url_reachability_verifier import URLReachabilityVerifier  # noqa: E402
from src.verifiers.quote_match_verifier import QuoteMatchVerifier  # noqa: E402
from src.verifiers.claim_nli_verifier import ClaimNLIVerifier  # noqa: E402
from src.verifiers.judge_client import call_judge, judge_identity     # noqa: E402


def _word_count(md: str) -> int:
    text = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", md)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"[#>*_~]", " ", text)
    return len([w for w in text.split() if w])


def _citation_count(md: str) -> int:
    # Use the same six-style parser as every grounding verifier.  Native
    # frameworks commonly emit numbered references or bare source URLs; the
    # old markdown-only counter marked those reports as having zero citations
    # even while url_coverage and proof-of-fetch correctly resolved them.
    from src.verifiers.citation_format import extract_citations

    return len(extract_citations(md, sandbox_only=False))


def _paragraph_count(md: str) -> int:
    return len([p for p in re.split(r"\n\s*\n", md) if len(p.strip()) > 30])


def _markdown_spec_score(
    md: str,
    spec: dict,
    *,
    citation_md: str | None = None,
) -> dict:
    """Score body shape from the sealed report and citations from its bundle.

    Most lanes deliver one Markdown file, so ``citation_md`` is normally the
    same string as ``md``.  STORM natively delivers two files: the article has
    inline ``[N]`` anchors and ``url_to_info.json`` contains the corresponding
    URL table.  The scorer resolves that verified native table in memory.  Its
    deterministic reference definitions must count as citations, but must not
    inflate the report's word or paragraph counts.
    """
    wc = _word_count(md)
    cc = _citation_count(citation_md if citation_md is not None else md)
    pc = _paragraph_count(md)
    return {
        "word_count":      wc,
        "min_words":       spec.get("min_words", 0),
        "max_words":       spec.get("max_words", 100000),
        "words_ok":        spec.get("min_words", 0) <= wc <= spec.get("max_words", 100000),
        "citation_count":  cc,
        "min_citations":   spec.get("min_citations", 0),
        "citations_ok":    cc >= spec.get("min_citations", 0),
        "paragraph_count": pc,
        "min_paragraphs":  spec.get("min_paragraphs", 0),
        "paragraphs_ok":   pc >= spec.get("min_paragraphs", 0),
    }


def _is_degenerate_answer(answer: str) -> tuple[bool, str]:
    """Wrapper around `src.verifiers.base.is_degenerate_answer` so the
    checklist judge shares one rule with all the LLM-based verifiers."""
    from src.verifiers.base import is_degenerate_answer
    return is_degenerate_answer(answer, min_words=50, require_citations=True)


_GROUNDING_KEYWORDS_RE = re.compile(
    r"\b(URL|URLs|cite|cited|cites|citation|citations|linked|markdown-linked|"
    r"distinct|reachable|sandbox|domain|domains|reddit|wikipedia|shopping|"
    r"thread|threads|article|articles|page|pages|forum|forums)\b",
    re.I,
)


def _criterion_requires_grounding(criterion_text: str) -> bool:
    """Heuristic: does this checklist item depend on real cited URLs?

    Used to downgrade PASS verdicts on grounding-dependent criteria when
    `url_reachability` says the agent's URLs don't actually resolve. Catches
    the gpt-researcher 0009 failure mode (judge says PASS on text that's
    well-written but cites 93 fabricated URLs).
    """
    return bool(_GROUNDING_KEYWORDS_RE.search(str(criterion_text or "")))


def _load_checklist(path: Path, task_id: str) -> list[str | dict[str, Any]]:
    """Load both legacy ``{task_id: [...]}`` and v2 ``{task_id, items}`` files.

    The v2 generator emits structured item objects.  Keep those objects intact:
    their type and params are what make deterministic scoring possible.  The
    old scorer both missed the top-level schema and then discarded this data,
    reducing typed unit tests to permissive prose questions for an LLM judge.
    """
    try:
        document = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []

    raw_items: object = []
    if isinstance(document, dict):
        legacy = document.get(task_id)
        if isinstance(legacy, list):
            raw_items = legacy
        elif document.get("task_id") == task_id and isinstance(document.get("items"), list):
            raw_items = document["items"]
    elif isinstance(document, list):
        raw_items = document

    result: list[str | dict[str, Any]] = []
    for item in raw_items if isinstance(raw_items, list) else []:
        if isinstance(item, str):
            text = item.strip()
            if text:
                result.append(text)
        elif isinstance(item, dict):
            text = str(item.get("description") or item.get("text") or "").strip()
            if text:
                clean = dict(item)
                clean["description"] = text
                result.append(clean)
        else:
            text = ""
    return result


def _checklist_text(item: str | dict[str, Any]) -> str:
    if isinstance(item, dict):
        return str(item.get("description") or item.get("text") or "").strip()
    return str(item or "").strip()


def _structured_checklist(checklist: list[str | dict[str, Any]]) -> bool:
    return bool(checklist) and all(
        isinstance(item, dict) and item.get("type") and isinstance(item.get("params"), dict)
        for item in checklist
    )


def _load_answer_key(task_config: dict[str, Any] | None):
    """Load the v2 key used to derive a structured checklist, if available."""
    if not task_config:
        return None
    rel = ((task_config.get("golden") or {}).get("answer_key_path")
           or (task_config.get("url_coverage") or {}).get("golden_pool_path"))
    if not rel:
        return None
    path = Path(rel)
    if not path.is_absolute():
        path = ROOT / path
    try:
        from src.eval.answer_key import AnswerKey
        return AnswerKey.load(path)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _typed_item_nugget(item: dict[str, Any]):
    """Convert checklist params to the scorer's canonical Nugget shape."""
    from src.eval.answer_key import Nugget

    p = item.get("params") or {}
    return Nugget(
        text=_checklist_text(item),
        subject=str(p.get("subject") or ""),
        predicate=str(p.get("predicate") or ""),
        object=str(p.get("object") or ""),
        source_url=str(p.get("source_url") or ""),
        importance="vital",
        relevant=True,
    )


def _subject_explicitly_named(visible: str, nugget: Any, tokens: list[str]) -> bool:
    """Require a real product identity, not a collision on generic features."""
    from src.eval import decidable_scorer as ds

    if nugget.predicate == "concept_coverage":
        return ds._subject_discussed(visible, tokens)
    if ds._exact_subject_spans(visible, nugget.subject):
        return True

    generic_features = {
        "active", "audio", "black", "bluetooth", "built", "canceling",
        "cancelling", "charging", "compact", "earbuds", "earphone",
        "earphones", "flight", "foldable", "headphone", "headphones",
        "headset", "headsets", "hours", "microphone", "noise", "over",
        "playtime", "silver", "smart", "sports", "true", "wireless",
    }
    anchors = [t for t in tokens if t not in generic_features]
    present = [t for t in anchors if ds._word_token_pattern(t).search(visible)]
    if not present:
        return False

    # A model token is a decisive identity (660NC, WH1000XM3, X20).  A long
    # non-generic token is normally a brand (Harphonic, NyPots, Lenovo).  Short
    # or ordinary names need two nearby anchors.  This keeps a report about a
    # Sony XM5 from being scored as though it claimed facts about the gold Sony
    # XM3 merely because both paragraphs also say "noise cancelling".
    if any(any(c.isdigit() for c in t) for t in present):
        return True
    if any(len(t) >= 5 and t not in {"house", "first", "small"} for t in present):
        return True
    if len(present) < 2:
        return False
    spans = ds._token_spans(visible, present)
    return any(abs(a - b) <= 120 for i, (a, _) in enumerate(spans)
               for b, _ in spans[i + 1:])


def _typed_value_state(text: str, nugget: Any, generic: set[str]) -> tuple[bool, bool, str]:
    """Return (subject discussed, correct value present, value claim present).

    This deliberately reuses the closed-world scorer's subject binding and
    typed-value rules.  URL slugs are excluded by callers, so a citation alone
    cannot manufacture the subject or the value.
    """
    from src.eval import decidable_scorer as ds

    visible = ds._visible_prose(text or "")
    tokens = ds._subject_tokens(nugget, generic)
    if not _subject_explicitly_named(visible, nugget, tokens):
        return False, False, ""

    spans = ds._subject_value_spans(visible, nugget.subject, tokens)
    masked = ds._mask_numbers_in_spans(
        visible, ds._exact_subject_spans(visible, nugget.subject)
    )
    correct = False
    claim_present = False
    for start, end in spans:
        win_end = end + ds.BIND_WINDOW
        window = masked[max(0, start - ds.BIND_WINDOW):win_end]
        tail = masked[win_end:win_end + 16]
        if ds._typed_value_in_window(window, nugget, tail=tail):
            correct = True

        predicate = nugget.predicate
        if predicate in {"buyer_sentiment", "rating"}:
            guard = window + tail
            for match in ds._LABEL_NUM_RE.finditer(window):
                if ds._COUNT_NOUN_AFTER.match(guard, match.end()):
                    continue
                if ds._cue_near(window, match.start(), match.end(), ds._RATING_CUE):
                    claim_present = True
                    break
        elif predicate == "price":
            for match in ds._NUM_RE.finditer(window):
                cue = window[max(0, match.start() - ds.PRICE_CUE_WINDOW):
                             match.end() + ds.PRICE_CUE_WINDOW]
                if "$" in cue or ds._PRICE_CUE.search(cue):
                    claim_present = True
                    break
        elif predicate == "concept_coverage":
            claim_present = True
        else:
            obj = ds.norm(str(nugget.object))
            claim_present = bool(obj and obj in window)
        if correct:
            break
    return True, correct, "typed value stated" if claim_present else ""


def _inline_cited_prose(answer: str) -> dict[str, list[str]]:
    """Map canonical in-text citation URL to visible prose on the same line."""
    from src.eval import decidable_scorer as ds
    from src.verifiers.citation_format import canonicalize_url, extract_citations

    mapping: dict[str, list[str]] = {}
    ref_spans = ds._reference_region_offsets(answer)
    lines = list(ds._line_spans(answer))
    for citation in extract_citations(answer, sandbox_only=False):
        if (citation.style not in ds.POF_EVIDENCE_STYLES
                or ds._offset_in_spans(citation.char_offset, ref_spans)):
            continue
        for raw_line, start, end in lines:
            if start <= citation.char_offset <= end:
                prose = ds._visible_prose(raw_line)
                if prose:
                    mapping.setdefault(canonicalize_url(citation.raw_url), []).append(prose)
                break
    return mapping


def _contradiction_candidate(item: dict[str, Any], answer: str, generic: set[str]) -> bool:
    """Cheap strict prefilter before asking an LLM about a semi-decidable item."""
    from src.eval import decidable_scorer as ds

    p = item.get("params") or {}
    product = str(p.get("product_name") or "")
    if not product:
        return False
    probe = SimpleNamespace(subject=product, predicate="catalog_product")
    visible = ds._visible_prose(answer)
    tokens = ds._subject_tokens(probe, generic)
    if not ds._subject_discussed(visible, tokens):
        return False
    values = [str(row.get("value")) for row in p.get("values", []) if row.get("value") is not None]
    return len(values) >= 2 and all(re.search(rf"(?<!\d){re.escape(v)}(?!\d)", visible) for v in values)


def _score_structured_checklist(
    checklist: list[dict[str, Any]],
    answer: str,
    task_id: str,
    *,
    task_config: dict[str, Any] | None,
    reachability: float | None,
    quote_match: float | None,
) -> dict[str, Any]:
    """Score v2 typed checklist items using their declared evaluation route."""
    from src.eval import decidable_scorer as ds
    from src.eval.answer_key import SpecRequirement
    from src.verifiers.citation_format import canonicalize_url

    answer_key = _load_answer_key(task_config)
    generic = ds.build_generic_tokens(answer_key) if answer_key is not None else set()
    cited_prose = _inline_cited_prose(answer)
    item_results: list[dict[str, Any] | None] = [None] * len(checklist)
    llm_indices: list[int] = []

    for index, item in enumerate(checklist):
        item_type = str(item.get("type") or "").upper()
        params = item.get("params") or {}
        verdict = "FAIL"
        reason = "criterion not satisfied"

        if item_type == "COVERAGE":
            nugget = _typed_item_nugget(item)
            source = canonicalize_url(nugget.source_url) if nugget.source_url else ""
            candidates = cited_prose.get(source, []) if source else []
            if not candidates:
                reason = "required source URL not cited inline"
            else:
                states = [_typed_value_state(text, nugget, generic) for text in candidates]
                if any(discussed and correct for discussed, correct, _ in states):
                    verdict, reason = "PASS", "subject and DB value bound to source citation"
                elif any(discussed for discussed, _, _ in states):
                    reason = "source cited but required DB value absent or wrong"
                else:
                    reason = "source cited without conveying the required subject"

        elif item_type == "FACT":
            nugget = _typed_item_nugget(item)
            discussed, correct, claim = _typed_value_state(answer, nugget, generic)
            if not discussed or not claim:
                verdict, reason = "NOT_APPLICABLE", "report makes no matching typed claim"
            elif correct:
                verdict, reason = "PASS", "stated value matches DB value"
            else:
                verdict, reason = "FAIL", "stated value conflicts with DB value"

        elif item_type == "CONTRADICTION":
            if _contradiction_candidate(item, answer, generic):
                llm_indices.append(index)
                continue
            reason = "product and conflicting values were not both surfaced"

        elif item_type == "GROUNDING":
            metric = str(params.get("metric") or "")
            observed = reachability if metric == "reachability" else quote_match
            if observed is None:
                verdict, reason = "UNCLEAR", f"{metric or 'grounding'} metric unavailable"
            elif observed >= 0.999999:
                verdict, reason = "PASS", f"{metric} rate is complete"
            else:
                verdict, reason = "FAIL", f"{metric} rate is {observed:.4f}, not complete"

        elif item_type == "SPEC":
            req = SpecRequirement(
                id=str(item.get("id") or f"spec_{index}"),
                kind=str(params.get("kind") or ""),
                description=_checklist_text(item),
                params={k: v for k, v in params.items() if k != "kind"},
            )
            ok = ds._check_spec(answer, req)
            verdict = "PASS" if ok else "FAIL"
            reason = "deterministic spec check passed" if ok else "deterministic spec check failed"

        else:
            llm_indices.append(index)
            continue

        item_results[index] = {
            "id": item.get("id"), "type": item_type,
            "description": _checklist_text(item),
            "verdict": verdict, "reason": reason,
            "scoring": "deterministic",
        }

    judge_error = None
    if llm_indices:
        undecidable = [_checklist_text(checklist[i]) for i in llm_indices]
        judged = _judge_checklist_legacy(undecidable, answer, task_id)
        judge_error = judged.get("judge_error")
        judged_verdicts = [row[1] for row in judged.get("verdicts", [])]
        for offset, index in enumerate(llm_indices):
            verdict = judged_verdicts[offset] if offset < len(judged_verdicts) else "UNCLEAR"
            item = checklist[index]
            item_results[index] = {
                "id": item.get("id"), "type": str(item.get("type") or "").upper(),
                "description": _checklist_text(item),
                "verdict": verdict,
                "reason": "LLM judged after deterministic candidate prefilter",
                "scoring": "llm_semidecidable",
            }

    results = [row for row in item_results if row is not None]
    verdicts = [row["verdict"] for row in results]
    applicable = [v for v in verdicts if v != "NOT_APPLICABLE"]
    pass_count = sum(v == "PASS" for v in applicable)
    denominator = len(applicable)
    return {
        "verdicts": [[row["description"], row["verdict"]] for row in results],
        "item_results": results,
        "pass_count": pass_count,
        "fail_count": sum(v == "FAIL" for v in applicable),
        "unclear_count": sum(v == "UNCLEAR" for v in applicable),
        "not_applicable_count": sum(v == "NOT_APPLICABLE" for v in verdicts),
        "applicable_count": denominator,
        "pass_rate": round(pass_count / denominator, 4) if denominator else 0.0,
        "judge_error": judge_error,
        "scoring_mode": "structured_v2",
    }


def _judge_checklist_legacy(
    checklist: list[str],
    answer: str,
    task_id: str,
    *,
    reachability: float | None = None,
    fab_threshold: float = 0.30,
) -> dict:
    if not checklist:
        return {"verdicts": [], "pass_rate": 0.0, "judge_error": "no checklist"}

    # Deterministic guard: don't waste an LLM call on degenerate output.
    # A lenient judge (DeepSeek-V4-flash observed) will return PASS for
    # all criteria when fed an empty answer; that gameable behaviour is
    # the bug we are fixing.
    degenerate, why = _is_degenerate_answer(answer)
    if degenerate:
        verdicts = ["FAIL"] * len(checklist)
        return {
            "verdicts": list(zip(checklist, verdicts)),
            "pass_count": 0,
            "fail_count": len(checklist),
            "unclear_count": 0,
            "pass_rate": 0.0,
            "judge_error": None,
            "skipped_judge": True,
            "skip_reason": why,
        }

    system = (
        "You are an impartial evaluator scoring a deep-research report. "
        "For each criterion, output exactly one of: PASS, FAIL, UNCLEAR. "
        "Output one verdict per line in order, no preamble, no commentary.\n\n"
        "Decision rules:\n"
        "  * PASS only if the report contains explicit textual evidence for the criterion.\n"
        "  * If the report is empty, a placeholder (e.g. '(empty ... output)'), an error "
        "message, or under ~200 words, output FAIL for ALL criteria.\n"
        "  * If a criterion requires specific URLs / citations / counts and the report does "
        "not show them, FAIL.\n"
        "  * UNCLEAR is reserved for genuinely ambiguous cases."
    )
    numbered = "\n".join(f"{i+1}. {c}" for i, c in enumerate(checklist))
    user = (
        f"# Task: {task_id}\n\n"
        f"# Criteria\n{numbered}\n\n"
        f"# Agent Answer (truncated to 32k chars below; treat empty/placeholder as FAIL-all)\n"
        f"{answer[:32000]}\n\n"
        f"# Your output: {len(checklist)} lines, each PASS/FAIL/UNCLEAR."
    )
    text, err = call_judge(system=system, user=user, max_tokens=600, temperature=0.0)
    if err:
        return {"verdicts": [], "pass_rate": 0.0, "judge_error": err}

    raw = (text or "").strip().splitlines()
    verdicts: list[str] = []
    for line in raw:
        line = line.strip().rstrip(".")
        line = re.sub(r"^\d+[.)]\s*", "", line)
        m = re.search(r"\b(PASS|FAIL|UNCLEAR)\b", line, re.I)
        if m:
            verdicts.append(m.group(1).upper())
        if len(verdicts) >= len(checklist):
            break
    while len(verdicts) < len(checklist):
        verdicts.append("UNCLEAR")

    # Sanity floor: a 21/21 PASS on a near-empty answer is the bug
    # signature. If the answer is short AND every verdict is PASS, the
    # judge is hallucinating — downgrade to FAIL. Threshold is set well
    # above the degenerate cutoff so genuinely strong answers are unaffected.
    if all(v == "PASS" for v in verdicts) and _word_count(answer) < 500:
        verdicts = ["FAIL"] * len(verdicts)
        floor_applied = "all_pass_short_answer"
    else:
        floor_applied = None

    # Reachability cross-check: if the agent's URLs don't resolve, downgrade
    # any PASS on a grounding-dependent criterion to FAIL. Solves the
    # gpt-researcher 0009 case where 93 fab URLs got 21/21 from the judge.
    grounding_downgrades = 0
    if reachability is not None and reachability < fab_threshold:
        for i, c in enumerate(checklist):
            if verdicts[i] == "PASS" and _criterion_requires_grounding(c):
                verdicts[i] = "FAIL"
                grounding_downgrades += 1

    pass_rate = sum(v == "PASS" for v in verdicts) / len(checklist)
    return {
        "verdicts": list(zip(checklist, verdicts)),
        "pass_count": sum(v == "PASS" for v in verdicts),
        "fail_count": sum(v == "FAIL" for v in verdicts),
        "unclear_count": sum(v == "UNCLEAR" for v in verdicts),
        "pass_rate": round(pass_rate, 4),
        "judge_error": None,
        "sanity_floor": floor_applied,
        "grounding_downgrades": grounding_downgrades,
        "reachability_used": reachability,
    }


def _judge_checklist(
    checklist: list[str | dict[str, Any]],
    answer: str,
    task_id: str,
    *,
    reachability: float | None = None,
    quote_match: float | None = None,
    task_config: dict[str, Any] | None = None,
    fab_threshold: float = 0.30,
) -> dict[str, Any]:
    if _structured_checklist(checklist):
        return _score_structured_checklist(
            checklist,  # type: ignore[arg-type]
            answer,
            task_id,
            task_config=task_config,
            reachability=reachability,
            quote_match=quote_match,
        )
    return _judge_checklist_legacy(
        [_checklist_text(item) for item in checklist],
        answer,
        task_id,
        reachability=reachability,
        fab_threshold=fab_threshold,
    )


def _composite(
    reachability: float,
    quote_match: float,
    claim_nli: float,
    url_cov: float,
    checklist_pass_rate: float,
    spec: dict,
    *,
    citation_alignment: float = 0.0,
    analysis_depth: float = 0.0,
    presentation: float = 0.0,
) -> dict:
    """Composite scoring with v1, v2, and v3 formulas.

    v1 (legacy additive):
      composite_v1 = reachability × quality
      quality      = 0.4·url_cov + 0.4·judge + 0.2·spec

    v2 (truthfulness-first, 3-layer multiplicative):
      truth     = reach × (0.5 + 0.5·quote_match) × (0.5 + 0.5·claim_nli)
      quality   = 0.4·url_cov + 0.4·judge + 0.2·spec
      composite = truth × quality

    v3 (7-dimension weighted, grounding-gated):
      grounding_gate = max(0.1, reachability)
      raw_score = (
          0.20 × url_coverage +
          0.20 × quote_fidelity +
          0.20 × judge_pass +
          0.10 × spec_compliance +
          0.15 × citation_alignment +
          0.10 × analysis_depth +
          0.05 × presentation
      )
      composite_v3 = grounding_gate × raw_score
    """
    spec_pass = sum([spec["words_ok"], spec["citations_ok"], spec["paragraphs_ok"]]) / 3.0

    # --- v2 ---
    quality = (
        0.40 * url_cov
        + 0.40 * checklist_pass_rate
        + 0.20 * spec_pass
    )
    qm_factor  = 0.5 + 0.5 * quote_match
    nli_factor = 0.5 + 0.5 * claim_nli
    truth = reachability * qm_factor * nli_factor
    composite_v2 = truth * quality

    # --- v1 (backward compat) ---
    composite_v1 = reachability * quality
    legacy_composite = 0.50 * url_cov + 0.35 * checklist_pass_rate + 0.15 * spec_pass

    # --- v3 ---
    grounding_gate = max(0.1, reachability)
    raw_score = (
        0.20 * url_cov
        + 0.20 * quote_match
        + 0.20 * checklist_pass_rate
        + 0.10 * spec_pass
        + 0.15 * citation_alignment
        + 0.10 * analysis_depth
        + 0.05 * presentation
    )
    composite_v3 = grounding_gate * raw_score

    return {
        "spec_pass_fraction":   round(spec_pass, 4),
        "quality_score":        round(quality, 4),
        "truth_factor":         round(truth, 4),
        "qm_factor":            round(qm_factor, 4),
        "nli_factor":           round(nli_factor, 4),
        # v3 new fields
        "grounding_gate":       round(grounding_gate, 4),
        "raw_score_v3":         round(raw_score, 4),
        "citation_alignment":   round(citation_alignment, 4),
        "analysis_depth":       round(analysis_depth, 4),
        "presentation":         round(presentation, 4),
        # composites
        "composite_v3":         round(composite_v3, 4),
        "composite_score":      round(composite_v2, 4),   # v2 remains default
        "composite_v2":         round(composite_v2, 4),
        "composite_v1":         round(composite_v1, 4),
        "legacy_composite":     round(legacy_composite, 4),
    }


def verify_report_seal(answer_path: Path) -> dict:
    """Recompute the report sha and compare it to the seal in the meta sidecar.

    run_deep_task seals sha256(exact bytes written) into
    ``<stem>.meta.json:report_seal`` at the moment the runner returns. If a later
    stage grafts a "### Sources" block, rewrites URLs, or otherwise edits the
    saved report, the recomputed sha stops matching and this flags it. Before
    this function nothing ever read the seal back, so it protected nothing.

    Returns ``{checked, ok, reason, ...}``. ``checked=False`` (no sidecar / no
    seal / older run) is NOT a failure: historical reports carry no seal. Only a
    present seal that disagrees with the file is ``ok=False``.
    """
    meta_path = answer_path.with_suffix(".meta.json")
    if not meta_path.exists():
        return {"checked": False, "ok": True, "reason": "no_meta_sidecar"}
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as e:  # noqa: BLE001
        return {"checked": False, "ok": True, "reason": f"meta_unreadable: {e}"}
    seal = meta.get("report_seal") or {}
    want = seal.get("sha256")
    if not want:
        return {"checked": False, "ok": True, "reason": "no_seal_in_meta"}
    try:
        got = hashlib.sha256(answer_path.read_bytes()).hexdigest()
    except Exception as e:  # noqa: BLE001
        return {"checked": False, "ok": True, "reason": f"report_unreadable: {e}"}
    ok = (got == want)
    return {
        "checked": True,
        "ok": ok,
        "reason": "match" if ok else "sha_mismatch_report_tampered",
        "sealed_sha256": want,
        "actual_sha256": got,
    }


def _resolve_native_citation_bundle(
    answer_path: Path,
    answer: str,
    *,
    seal_check: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Resolve a verified framework-native citation table for scoring.

    Stanford STORM 1.1.1 deliberately emits a two-file result: the article
    contains numeric anchors (``[1]``) while ``url_to_info.json`` contains the
    native ``URL -> unified index`` table.  Treating only the article as the
    result loses STORM's citations; appending every retrieved URL to the sealed
    report would instead manufacture credit.

    This resolver is deliberately fail-closed:

    * the sealed report must verify;
    * ``meta.json`` must declare the native artifact and its byte count/hash;
    * the artifact filename must be a sibling basename (no path traversal);
    * each resolved URL must occur in STORM's native ``url_to_info`` table;
    * only indices actually cited inline are materialised; unused retrievals
      never enter the scoring view;
    * duplicate/ambiguous indices are left unresolved.

    The returned Markdown exists only in memory.  The report on disk and its
    seal remain byte-for-byte unchanged.
    """
    result: dict[str, Any] = {
        "schema": "dra.native-citation-resolution.v1",
        "status": "not_applicable",
        "applied": False,
        "report_modified": False,
        "policy": "verified_native_bundle_inline_indices_only",
    }

    meta_path = answer_path.with_suffix(".meta.json")
    if not meta_path.is_file():
        result["reason"] = "no_meta_sidecar"
        return answer, result
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result.update(status="rejected", reason=f"meta_unreadable: {exc}")
        return answer, result

    native = meta.get("native_artifacts") or {}
    artifact = native.get("storm_url_to_info")
    if not isinstance(artifact, dict):
        result["reason"] = "no_storm_native_citation_artifact"
        return answer, result
    result["status"] = "rejected"
    if str(meta.get("agent") or "") != "storm":
        result["reason"] = "artifact_declared_by_non_storm_lane"
        return answer, result
    if not seal_check.get("checked") or not seal_check.get("ok"):
        result["reason"] = "report_seal_not_verified"
        return answer, result

    filename = str(artifact.get("file") or "").strip()
    if not filename or Path(filename).name != filename:
        result["reason"] = "invalid_artifact_filename"
        return answer, result
    artifact_path = answer_path.parent / filename
    if not artifact_path.is_file():
        result["reason"] = "declared_artifact_missing"
        return answer, result
    try:
        payload_bytes = artifact_path.read_bytes()
    except OSError as exc:
        result["reason"] = f"artifact_unreadable: {exc}"
        return answer, result

    expected_bytes = artifact.get("bytes")
    expected_sha = str(artifact.get("sha256") or "").lower()
    actual_sha = hashlib.sha256(payload_bytes).hexdigest()
    result.update(
        artifact_file=filename,
        expected_sha256=expected_sha or None,
        actual_sha256=actual_sha,
        expected_bytes=expected_bytes,
        actual_bytes=len(payload_bytes),
    )
    if (
        not isinstance(expected_bytes, int)
        or expected_bytes != len(payload_bytes)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha)
        or expected_sha != actual_sha
    ):
        result["reason"] = "artifact_size_or_sha_mismatch"
        return answer, result

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        result["reason"] = f"artifact_json_invalid: {exc}"
        return answer, result
    if not isinstance(payload, dict):
        result["reason"] = "artifact_json_not_object"
        return answer, result
    url_to_index = payload.get("url_to_unified_index")
    url_to_info = payload.get("url_to_info")
    if not isinstance(url_to_index, dict) or not isinstance(url_to_info, dict):
        result["reason"] = "artifact_schema_invalid"
        return answer, result

    # Build an unambiguous index -> URL table.  Requiring the URL in both
    # native maps rejects a hand-edited index table that has no retrieved
    # Information object behind it.
    candidates: dict[int, list[str]] = {}
    invalid_entries = 0
    for raw_url, raw_index in url_to_index.items():
        if (
            not isinstance(raw_url, str)
            or not raw_url.startswith(("http://", "https://"))
            or isinstance(raw_index, bool)
            or not isinstance(raw_index, int)
            or not 1 <= raw_index <= 999
            or raw_url not in url_to_info
        ):
            invalid_entries += 1
            continue
        candidates.setdefault(raw_index, []).append(raw_url)
    index_to_url = {
        index: urls[0]
        for index, urls in candidates.items()
        if len(set(urls)) == 1
    }
    ambiguous_indices = sorted(
        index for index, urls in candidates.items() if len(set(urls)) != 1
    )

    # Strip existing numbered definition lines before finding inline anchors.
    # This prevents a pre-existing References block from citing itself.
    definition_re = re.compile(
        r"(?m)^\s*\[(?P<index>\d{1,3})\]\s*\.?\s*(?:[-:.]\s*)?"
        r"[^\n]*?(?P<url>https?://[^\s<>]+)[^\n]*$"
    )
    body_without_definitions = definition_re.sub("", answer)
    inline_indices = sorted({
        int(value)
        for value in re.findall(r"\[(\d{1,3})\]", body_without_definitions)
    })
    from src.verifiers.citation_format import canonicalize_url, strip_url_trail

    existing_records = [
        {
            "index": int(match.group("index")),
            "url": strip_url_trail(match.group("url")),
            "start": match.start(),
            "end": match.end(),
        }
        for match in definition_re.finditer(answer)
    ]
    existing_definitions = {record["index"] for record in existing_records}
    resolved = {
        index: index_to_url[index]
        for index in inline_indices
        if index in index_to_url
    }
    matching_existing = {
        record["index"]
        for record in existing_records
        if (
            record["index"] in resolved
            and canonicalize_url(record["url"])
            == canonicalize_url(resolved[record["index"]])
        )
    }
    conflicts = [
        {
            "index": record["index"],
            "report_url": record["url"],
            "native_url": resolved[record["index"]],
        }
        for record in existing_records
        if (
            record["index"] in resolved
            and canonicalize_url(record["url"])
            != canonicalize_url(resolved[record["index"]])
        )
    ]
    additions = {
        index: url
        for index, url in resolved.items()
        if index not in matching_existing
    }
    unresolved = sorted(set(inline_indices) - set(resolved))
    result.update(
        mappings_total=len(url_to_index),
        valid_unambiguous_mappings=len(index_to_url),
        invalid_mapping_entries=invalid_entries,
        ambiguous_indices=ambiguous_indices,
        inline_indices=inline_indices,
        resolved_indices=sorted(resolved),
        unresolved_indices=unresolved,
        existing_reference_definitions=sorted(existing_definitions),
        matching_reference_definitions=sorted(matching_existing),
        conflicting_reference_definitions=conflicts,
        appended_reference_definitions=len(additions),
        unused_native_mappings=max(0, len(index_to_url) - len(resolved)),
    )
    if not inline_indices:
        result.update(status="verified_no_inline_citations", reason="no_inline_indices")
        return answer, result
    if not additions:
        # The bundle is valid but either every inline anchor was already
        # defined in the report or none could be resolved.  In both cases the
        # original Markdown is already the correct scoring view.
        status = "already_resolved" if resolved and not unresolved else "verified_unresolved"
        result.update(status=status, reason=None if resolved else "no_resolvable_indices")
        return answer, result

    # A model-written reference line can conflict with STORM's authoritative
    # native index table.  Do not let the first (fabricated) definition hijack
    # every inline anchor, but do not hide it either: demote its numeric marker
    # to prose in the scoring view so the public URL remains a bare citation and
    # still lowers reachability, then append the verified native definition.
    conflicting_pairs = {
        (item["index"], canonicalize_url(item["report_url"]))
        for item in conflicts
    }

    def _demote_conflicting_definition(match: re.Match[str]) -> str:
        index = int(match.group("index"))
        url = strip_url_trail(match.group("url"))
        if (index, canonicalize_url(url)) not in conflicting_pairs:
            return match.group(0)
        return re.sub(
            rf"^(\s*)\[{index}\]",
            rf"\1- Report-emitted conflicting source index {index}:",
            match.group(0),
            count=1,
        )

    scoring_body = definition_re.sub(_demote_conflicting_definition, answer)
    heading = "" if re.search(
        r"(?im)^#{1,6}\s+(?:references?|sources?|bibliography)\s*:?\s*$",
        scoring_body,
    ) else "## References\n\n"
    definitions = "\n".join(f"[{index}] {url}" for index, url in additions.items())
    scoring_answer = scoring_body.rstrip() + "\n\n" + heading + definitions + "\n"
    result.update(
        status="applied",
        applied=True,
        reason=None,
        scoring_view_sha256=hashlib.sha256(
            scoring_answer.encode("utf-8")
        ).hexdigest(),
        scoring_view_chars=len(scoring_answer),
    )
    return scoring_answer, result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--answer", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    # Serve cited sandbox pages from a frozen cache when DRA_SANDBOX_CACHE is set,
    # so a bulk re-score does not hammer Magento (and is reproducible offline).
    if os.environ.get("DRA_SANDBOX_CACHE"):
        try:
            from src.verifiers.sandbox_http_cache import install as _install_cache
            _install_cache()
        except Exception as _e:
            print(f"[cache] install failed: {_e}", file=sys.stderr)
    else:
        # Without a cache this tool verifies citations against the LIVE sandbox.
        # That answers "does this URL exist", not "did the agent open it", and a
        # URL the model guessed is confirmed by our own request. Fine for eyeballing
        # one report; not the board's semantics. Board numbers come from the run's
        # transport-level evidence log (src/eval/fetch_log.py).
        print("[warn] no DRA_SANDBOX_CACHE: verifying against the live sandbox. "
              "These numbers are NOT comparable to leaderboard numbers.",
              file=sys.stderr)

    task_path = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / f"{args.task}.json"
    task_cfg = json.loads(task_path.read_text())

    sandbox_aliases = {
        "__SHOPPING__":  ["localhost:7770"],
        "__REDDIT__":    ["localhost:9999"],
        "__WIKIPEDIA__": ["localhost:8090"],
    }
    task_cfg.setdefault("domain_aliases", sandbox_aliases)

    answer_path = Path(args.answer)
    if not answer_path.exists():
        print(f"answer not found: {answer_path}", file=sys.stderr)
        return 2
    original_answer = answer_path.read_text(errors="ignore")

    print(f"=== scoring {answer_path.name} on task {args.task} ===")
    print(f"answer chars: {len(original_answer)}")

    seal_check = verify_report_seal(answer_path)
    if seal_check.get("checked") and not seal_check.get("ok"):
        # Loud, not fatal: surface a tampered report in the score record so a
        # board build can drop it, rather than silently scoring injected bytes.
        print(f"\n[report_seal] TAMPERED: {json.dumps(seal_check, ensure_ascii=False)}",
              file=sys.stderr)
    elif seal_check.get("checked"):
        print(f"[report_seal] verified (sha matches meta seal)")

    answer, native_citation_resolution = _resolve_native_citation_bundle(
        answer_path,
        original_answer,
        seal_check=seal_check,
    )
    if native_citation_resolution.get("status") != "not_applicable":
        print(
            "[native_citations] "
            f"status={native_citation_resolution.get('status')} "
            f"resolved={len(native_citation_resolution.get('resolved_indices') or [])} "
            f"unresolved={len(native_citation_resolution.get('unresolved_indices') or [])}"
        )

    url_v = URLCoverageVerifier()
    url_result = url_v.verify(task_config=task_cfg, answer=answer)
    print(f"\n[url_coverage] score={url_result.score} passed={url_result.passed}")
    print(f"  details: {json.dumps(url_result.details, ensure_ascii=False)}")

    reach_v = URLReachabilityVerifier(max_workers=4, max_urls=150)
    reach_result = reach_v.verify(task_config=task_cfg, answer=answer)
    print(f"\n[url_reachability] rate={reach_result.score} passed={reach_result.passed}")
    print(f"  details: {json.dumps(reach_result.details, ensure_ascii=False)}")

    if os.environ.get("SKIP_LAYER2", "0") != "1":
        qm_v = QuoteMatchVerifier(max_workers=3, max_urls=120)
        qm_result = qm_v.verify(task_config=task_cfg, answer=answer)
        print(f"\n[quote_match] rate={qm_result.score} passed={qm_result.passed}")
        print(f"  details: {json.dumps(qm_result.details, ensure_ascii=False)}")
    else:
        from src.verifiers.base import VerifierResult
        qm_result = VerifierResult.fail("skipped", skip_reason="SKIP_LAYER2=1")

    if os.environ.get("SKIP_LAYER3", "0") != "1":
        nli_v = ClaimNLIVerifier(theta=0.80, max_calls=60, max_workers=3)
        nli_result = nli_v.verify(task_config=task_cfg, answer=answer)
        print(f"\n[claim_nli] rate={nli_result.score} passed={nli_result.passed}")
        print(f"  details: {json.dumps(nli_result.details, ensure_ascii=False)}")
    else:
        from src.verifiers.base import VerifierResult
        nli_result = VerifierResult.fail("skipped", skip_reason="SKIP_LAYER3=1")

    spec_check = _markdown_spec_score(
        original_answer,
        task_cfg.get("markdown_spec", {}),
        citation_md=answer,
    )
    print(f"\n[markdown_spec] {json.dumps(spec_check, ensure_ascii=False)}")

    checklist_path = ROOT / task_cfg.get("coverage_checklist_path", "")
    checklist = []
    if checklist_path.exists():
        checklist = _load_checklist(checklist_path, args.task)
    print(f"\n[checklist] {len(checklist)} items, judge={judge_identity()}, reach={reach_result.score:.3f}")
    # Plumb reachability so the fab-URL cross-check fires (downgrades PASS
    # to FAIL on grounding-keyword criteria when reach < 0.30). Without
    # this kwarg the guard is dead in production scoring.
    checklist_result = _judge_checklist(
        checklist,
        answer,
        args.task,
        reachability=reach_result.score,
        quote_match=qm_result.score,
        task_config=task_cfg,
    )
    print(f"  pass={checklist_result.get('pass_count')}/{len(checklist)} "
          f"fail={checklist_result.get('fail_count')} unclear={checklist_result.get('unclear_count')} "
          f"rate={checklist_result.get('pass_rate')}")
    if checklist_result.get('judge_error'):
        print(f"  ! judge error: {checklist_result['judge_error']}")

    # --- v3 + v4 new verifiers (graceful fallback) ---
    # SKIP_V4=1 keeps the run cheap (skips the four v4 pillars but still
    # runs v3 ones). SKIP_V3=1 skips both, dropping back to pure v2 baseline.
    skip_v3 = os.environ.get("SKIP_V3", "0") == "1"
    skip_v4 = os.environ.get("SKIP_V4", "0") == "1" or skip_v3

    v3_scores = {}
    v3_details = {}

    v3_verifiers = [
        ("citation_alignment", "src.verifiers.citation_alignment_verifier", "CitationAlignmentVerifier"),
        ("analysis_depth",     "src.verifiers.analysis_depth_verifier",     "AnalysisDepthVerifier"),
        ("presentation",       "src.verifiers.presentation_verifier",       "PresentationVerifier"),
    ]
    v4_verifiers = [
        # source_diversity goes first because it's zero-LLM and we want
        # the cheap deterministic pillar to land even if heavy verifiers
        # crash or time out. perspective_balance second (light LLM).
        # factual_exactness and internal_consistency are the heavy V4 Pro
        # consumers — they go last so a budget-exhausted run still has
        # the cheap pillars.
        ("source_diversity",     "src.verifiers.source_diversity_verifier",     "SourceDiversityVerifier"),
        ("perspective_balance",  "src.verifiers.perspective_balance_verifier",  "PerspectiveBalanceVerifier"),
        ("factual_exactness",    "src.verifiers.factual_exactness_verifier",    "FactualExactnessVerifier"),
        ("internal_consistency", "src.verifiers.internal_consistency_verifier", "InternalConsistencyVerifier"),
    ]

    all_extras = list(v3_verifiers)
    if not skip_v3:
        # v3 verifiers always run by default — they predate this scorer
        # and the leaderboard composites depend on them.
        pass
    else:
        all_extras = []
    if not skip_v4:
        all_extras.extend(v4_verifiers)

    for verifier_name, verifier_module, verifier_class in all_extras:
        try:
            import importlib
            mod = importlib.import_module(verifier_module)
            cls = getattr(mod, verifier_class)
            v_inst = cls()
            # Native reference definitions are citation metadata, not report
            # prose.  Content-only pillars therefore see the sealed article;
            # citation-aware pillars see the verified in-memory bundle view.
            verifier_answer = (
                original_answer
                if verifier_name in {
                    "presentation", "perspective_balance", "internal_consistency"
                }
                else answer
            )
            v_result = v_inst.verify(task_config=task_cfg, answer=verifier_answer)
            v3_scores[verifier_name] = v_result.score
            v3_details[verifier_name] = {
                "score": v_result.score, "passed": v_result.passed,
                "details": v_result.details,
            }
            print(f"\n[{verifier_name}] score={v_result.score} passed={v_result.passed}")
        except ImportError:
            v3_scores[verifier_name] = 0.0
            v3_details[verifier_name] = {
                "score": 0.0, "passed": False,
                "details": {"note": f"{verifier_module} not available; scored 0"},
            }
            print(f"\n[{verifier_name}] not available (module not found), scored 0")
        except Exception as exc:
            v3_scores[verifier_name] = 0.0
            v3_details[verifier_name] = {
                "score": 0.0, "passed": False,
                "details": {"note": f"error: {type(exc).__name__}: {exc}"},
            }
            print(f"\n[{verifier_name}] error: {exc}, scored 0")

    composite = _composite(
        reach_result.score,
        qm_result.score,
        nli_result.score,
        url_result.score,
        checklist_result.get('pass_rate', 0.0),
        spec_check,
        citation_alignment=v3_scores.get("citation_alignment", 0.0),
        analysis_depth=v3_scores.get("analysis_depth", 0.0),
        presentation=v3_scores.get("presentation", 0.0),
    )

    # composite_v4 — computed via the canonical formula in
    # src.scoring.leaderboard_composites. We materialise a partial
    # "score-shaped" dict so the canonical function reads it the same
    # way it reads on-disk score JSONs.
    from src.scoring.leaderboard_composites import composite_v4, composite_v4_weights
    v4_input = {
        "url_reachability":     {"score": reach_result.score},
        "url_coverage":         {"score": url_result.score},
        "quote_match":          {"score": qm_result.score},
        "citation_alignment":   v3_details.get("citation_alignment", {}),
        "analysis_depth":       v3_details.get("analysis_depth", {}),
        "presentation":         v3_details.get("presentation", {}),
        "source_diversity":     v3_details.get("source_diversity", {}),
        "perspective_balance":  v3_details.get("perspective_balance", {}),
        "factual_exactness":    v3_details.get("factual_exactness", {}),
        "internal_consistency": v3_details.get("internal_consistency", {}),
        "markdown_spec":        spec_check,
        "checklist":            checklist_result,
    }
    composite["composite_v4"] = round(float(composite_v4(v4_input)), 4)
    composite["composite_v4_weights"] = composite_v4_weights()
    # Stamp the v4-only pillar scores so audit pages can show the
    # breakdown without reading individual verifier blobs.
    composite["source_diversity"]     = round(float(v3_scores.get("source_diversity", 0.0)), 4)
    composite["perspective_balance"]  = round(float(v3_scores.get("perspective_balance", 0.0)), 4)
    composite["factual_exactness"]    = round(float(v3_scores.get("factual_exactness", 0.0)), 4)
    composite["internal_consistency"] = round(float(v3_scores.get("internal_consistency", 0.0)), 4)
    print(f"\n[composite] {json.dumps(composite, ensure_ascii=False)}")

    out = {
        "task": args.task,
        "answer_path": str(answer_path),
        "answer_chars": len(original_answer),
        "scoring_answer_chars": len(answer),
        "report_seal_check": seal_check,
        "native_citation_resolution": native_citation_resolution,
        "url_coverage":     {"score": url_result.score,   "passed": url_result.passed,
                             "details": url_result.details},
        "url_reachability": {"score": reach_result.score, "passed": reach_result.passed,
                             "details": reach_result.details},
        "quote_match":      {"score": qm_result.score,    "passed": qm_result.passed,
                             "details": qm_result.details},
        "claim_nli":        {"score": nli_result.score,   "passed": nli_result.passed,
                             "details": nli_result.details},
        "citation_alignment":   v3_details.get("citation_alignment", {}),
        "analysis_depth":       v3_details.get("analysis_depth", {}),
        "presentation":         v3_details.get("presentation", {}),
        # v4 NEW pillars — each falls back to {} when SKIP_V4=1 was used.
        "source_diversity":     v3_details.get("source_diversity", {}),
        "perspective_balance":  v3_details.get("perspective_balance", {}),
        "factual_exactness":    v3_details.get("factual_exactness", {}),
        "internal_consistency": v3_details.get("internal_consistency", {}),
        "markdown_spec": spec_check,
        "checklist": checklist_result,
        "composite": composite,
        "judge_identity": judge_identity(),
    }
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
