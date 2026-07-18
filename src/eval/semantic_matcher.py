"""Auditable LLM semantic matching for frozen v3 proof steps.

The judge answers only the report-side question: does the report express the
frozen proposition?  It never decides whether a URL is valid, was observed,
or actually supports the proposition.  Those gates remain deterministic in
``slot_scorer``.
"""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import os
from typing import Any

from src.verifiers.judge_client import call_judge


VERDICTS = {"entailed", "contradicted", "not_mentioned", "ambiguous"}
PROMPT_VERSION = "route_b_semantic_match_v1"


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _phrases(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    raw = (
        value.get("accepted_phrases")
        or value.get("accepted_phrase")
        or value.get("phrases")
        or value.get("phrase")
        or []
    )
    if isinstance(raw, str):
        raw = [raw]
    return [str(item).strip() for item in raw if str(item).strip()]


def build_targets(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build stable semantic targets from the sealed evaluator view."""

    sources = {
        str(row.get("evidence_id") or row.get("source_id") or ""): row
        for row in case.get("evidence_sources", [])
        if isinstance(row, Mapping)
    }
    rules = case.get("rule_definitions", {})
    if not isinstance(rules, Mapping):
        rules = {}
    steps = (
        case.get("evaluator_view", {}).get("required_proof_steps", [])
        if isinstance(case.get("evaluator_view"), Mapping)
        else []
    )
    targets: list[dict[str, Any]] = []
    for raw_step in steps:
        if not isinstance(raw_step, Mapping):
            continue
        step_id = str(raw_step.get("step_id") or "")
        step_type = str(raw_step.get("type") or "")
        alternatives: list[str] = []
        if step_type == "evidence":
            support = raw_step.get("acceptable_support", {})
            source_ids = (
                support.get("source_ids", [])
                if isinstance(support, Mapping) else []
            )
            for source_id in source_ids:
                source = sources.get(str(source_id), {})
                alternatives.extend(_phrases(source.get("verifier", {})))
        else:
            rule = rules.get(str(raw_step.get("rule") or ""), {})
            if isinstance(rule, Mapping):
                alternatives.extend(
                    _phrases(rule.get("decision_matcher", rule))
                )
        targets.append({
            "target_id": step_id,
            "kind": step_type,
            "alternatives": list(dict.fromkeys(alternatives)),
        })

        if step_type == "decision":
            rule = rules.get(str(raw_step.get("rule") or ""), {})
            matchers = (
                rule.get("conclusion_matchers", {})
                if isinstance(rule, Mapping) else {}
            )
            if isinstance(matchers, Mapping):
                for answer, matcher in sorted(matchers.items()):
                    targets.append({
                        "target_id": f"{step_id}::conclusion::{answer}",
                        "kind": "conclusion",
                        "alternatives": _phrases(matcher),
                    })

    for index, raw_claim in enumerate(case.get("decidable_claims", [])):
        if not isinstance(raw_claim, Mapping):
            continue
        claim_id = str(raw_claim.get("claim_id") or f"decidable_{index}")
        targets.append({
            "target_id": f"rejected::{claim_id}",
            "kind": "rejected_claim",
            "alternatives": _phrases(raw_claim.get("rejected_matcher", {})),
        })
    return targets


def _extract_json(text: str) -> Any:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        left, right = stripped.find("{"), stripped.rfind("}")
        if left < 0 or right <= left:
            raise
        return json.loads(stripped[left : right + 1])


def _validate_results(
    report: str, targets: list[dict[str, Any]], raw: Any
) -> list[dict[str, Any]]:
    rows = raw.get("results") if isinstance(raw, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError("judge output must contain a results array")
    by_id: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("each judge result must be an object")
        target_id = str(row.get("target_id") or "")
        if not target_id or target_id in by_id:
            raise ValueError("judge target IDs must be present and unique")
        by_id[target_id] = row
    expected_ids = [str(target["target_id"]) for target in targets]
    if set(by_id) != set(expected_ids):
        raise ValueError("judge target IDs do not exactly match requested targets")

    validated: list[dict[str, Any]] = []
    for target_id in expected_ids:
        row = by_id[target_id]
        verdict = str(row.get("verdict") or "")
        if verdict not in VERDICTS:
            raise ValueError(f"invalid verdict for {target_id}")
        quote = str(row.get("matched_quote") or "")
        starts: list[int] = []
        if quote:
            cursor = 0
            while True:
                found = report.find(quote, cursor)
                if found < 0:
                    break
                starts.append(found)
                cursor = found + 1
        if verdict in {"entailed", "contradicted"} and not starts:
            # Fail closed: a positive semantic judgment without an exact,
            # auditable report span cannot affect the score.
            verdict = "ambiguous"
            quote = ""
        if verdict in {"not_mentioned", "ambiguous"}:
            quote = ""
            starts = []
        start = starts[0] if starts else None
        validated.append({
            "target_id": target_id,
            "verdict": verdict,
            "matched_quote": quote or None,
            "start": start,
            "end": start + len(quote) if start is not None else None,
            "reason": str(row.get("reason") or "")[:500],
        })
    return validated


def judge_semantic_matches(
    case: Mapping[str, Any],
    report: str,
    *,
    case_sha256: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    targets = build_targets(case)
    if not targets or any(not target["alternatives"] for target in targets):
        missing = [target["target_id"] for target in targets if not target["alternatives"]]
        raise ValueError(f"semantic targets missing frozen statements: {missing}")
    system = (
        "You are a conservative semantic entailment annotator. Judge only what "
        "the REPORT explicitly states; do not use outside knowledge and do not "
        "judge source validity. Each target may have paraphrases, but every "
        "material clause in at least one alternative must be preserved. A claim "
        "with a wrong number, product, polarity, scope, or omitted material "
        "qualification is not entailed. Return JSON only. For entailed or "
        "contradicted, matched_quote must be one exact contiguous substring copied "
        "from REPORT. For not_mentioned or ambiguous, use an empty matched_quote."
    )
    payload = {
        "instruction": (
            "Return {\"results\":[{\"target_id\":...,\"verdict\":"
            "\"entailed|contradicted|not_mentioned|ambiguous\","
            "\"matched_quote\":...,\"reason\":...}]} with every target exactly once."
        ),
        "targets": targets,
        "REPORT": report,
    }
    user = json.dumps(payload, ensure_ascii=False)
    response, error = call_judge(
        system, user, model=model, max_tokens=6000, temperature=0.0
    )
    if error or response is None:
        raise RuntimeError(error or "semantic judge returned no response")
    parsed = _extract_json(response)
    results = _validate_results(report, targets, parsed)
    judge_model = model or os.environ.get("JUDGE_MODEL") or os.environ.get(
        "CHECKLIST_JUDGE_MODEL"
    )
    return {
        "schema_version": 1,
        "matching_semantics": PROMPT_VERSION,
        "case_sha256": case_sha256,
        "report_sha256": sha256(report.encode("utf-8")).hexdigest(),
        "targets_sha256": _canonical_digest(targets),
        "prompt_sha256": sha256((system + "\n" + user).encode("utf-8")).hexdigest(),
        "raw_response_sha256": sha256(response.encode("utf-8")).hexdigest(),
        "judge": {
            "provider": os.environ.get("JUDGE_PROVIDER", "anthropic"),
            "model": judge_model,
        },
        "results": results,
    }


def semantic_index(
    artifact: Mapping[str, Any], report: str, *, case_sha256: str | None = None
) -> dict[str, dict[str, Any]]:
    report_digest = sha256(report.encode("utf-8")).hexdigest()
    if artifact.get("report_sha256") != report_digest:
        raise ValueError("semantic artifact report SHA-256 mismatch")
    if case_sha256 and artifact.get("case_sha256") != case_sha256:
        raise ValueError("semantic artifact case SHA-256 mismatch")
    rows = artifact.get("results")
    if not isinstance(rows, list):
        raise ValueError("semantic artifact results must be a list")
    return {
        str(row["target_id"]): dict(row)
        for row in rows
        if isinstance(row, Mapping) and row.get("target_id")
    }
