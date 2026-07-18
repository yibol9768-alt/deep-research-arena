"""Create sealed LLM judgments for route-flexible rubric replay."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from hashlib import sha256
import json
import os
from typing import Any, Callable

from src.eval.observation_ledger import ObservationLedger
from src.eval.route_flexible_scorer import (
    JUDGMENT_SCHEMA,
    canonical_sha256,
    validate_rubric,
)
from src.verifiers.citation_format import canonicalize_url, extract_citations
from src.verifiers.judge_client import call_judge


REPORT_VERDICTS = {"satisfied", "contradicted", "not_mentioned", "ambiguous"}
EVIDENCE_VERDICTS = {"supported", "contradicted", "not_supported", "ambiguous"}
PROMPT_VERSION = "route_flexible_judge_v1"


def _extract_json(text: str) -> Any:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:] if lines and lines[0].startswith("```") else lines
        lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
        stripped = "\n".join(lines).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        left, right = stripped.find("{"), stripped.rfind("}")
        if left < 0 or right <= left:
            raise
        return json.loads(stripped[left : right + 1])


JudgeCall = Callable[[str, str, str | None, int, float], tuple[str | None, str | None]]


def _call(
    system: str,
    payload: Mapping[str, Any],
    *,
    model: str | None,
    judge_call: JudgeCall | None = None,
) -> tuple[str, Any]:
    user = json.dumps(payload, ensure_ascii=False)
    if judge_call is None:
        response, error = call_judge(
            system, user, model=model, max_tokens=8000, temperature=0.0
        )
    else:
        response, error = judge_call(system, user, model, 8000, 0.0)
    if error or response is None:
        raise RuntimeError(error or "route-flexible judge returned no response")
    return response, _extract_json(response)


def _validate_report_results(
    report: str, targets: list[Mapping[str, Any]], raw: Any
) -> list[dict[str, Any]]:
    rows = raw.get("results") if isinstance(raw, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError("report judge output must contain results")
    by_id = {
        str(row.get("target_id")): row
        for row in rows
        if isinstance(row, Mapping) and row.get("target_id")
    }
    expected = [str(target["target_id"]) for target in targets]
    if set(by_id) != set(expected) or len(by_id) != len(rows):
        raise ValueError("report judge target set mismatch")
    out: list[dict[str, Any]] = []
    for target_id in expected:
        row = by_id[target_id]
        verdict = str(row.get("verdict") or "")
        if verdict not in REPORT_VERDICTS:
            raise ValueError(f"invalid report verdict for {target_id}")
        quote = str(row.get("matched_quote") or "")
        start = report.find(quote) if quote else -1
        if verdict in {"satisfied", "contradicted"} and start < 0:
            verdict, quote, start = "ambiguous", "", -1
        if verdict in {"not_mentioned", "ambiguous"}:
            quote, start = "", -1
        out.append(
            {
                "target_id": target_id,
                "verdict": verdict,
                "matched_quote": quote or None,
                "start": start if start >= 0 else None,
                "end": start + len(quote) if start >= 0 else None,
                "reason": str(row.get("reason") or "")[:800],
            }
        )
    return out


def _observed_bodies(ledger: ObservationLedger) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for event in ledger.events:
        if (
            event.event_type not in {"fetch_body", "extracted_body"}
            or event.http_status != 200
            or event.observable is not True
        ):
            continue
        body = event.visible_text(ledger.blob_loader)
        if body is None:
            continue
        out[event.canonical_url] = {
            "event_id": event.event_id,
            "content_sha256": event.content_sha256,
            "body": body,
        }
    return out


def _candidate_bindings(
    rubric: Mapping[str, Any], report: str, report_results: list[Mapping[str, Any]], ledger: ObservationLedger
) -> dict[str, list[dict[str, Any]]]:
    targets = {str(target["target_id"]): target for target in rubric["targets"]}
    citations = extract_citations(report, sandbox_only=False)
    bodies = _observed_bodies(ledger)
    by_url: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report_results:
        target_id = str(row["target_id"])
        target = targets[target_id]
        if target["kind"] != "evidence" or row.get("verdict") != "satisfied":
            continue
        start, end = row.get("start"), row.get("end")
        if type(start) is not int or type(end) is not int:
            continue
        window = int(target["citation_binding_window_chars"])
        for citation in citations:
            if not start - window <= citation.char_offset <= end + window:
                continue
            url = citation.canonical_url
            if url not in bodies:
                continue
            by_url[url].append(
                {
                    "target_id": target_id,
                    "statement": target["statement"],
                    "support_mode": target["support_mode"],
                    "report_quote": row.get("matched_quote"),
                    "citation_url": url,
                    "citation_offset": citation.char_offset,
                    "observed_content_sha256": bodies[url]["content_sha256"],
                }
            )
    return by_url


def _validate_evidence_results(
    requested: list[Mapping[str, Any]], body: str, raw: Any
) -> list[dict[str, Any]]:
    rows = raw.get("results") if isinstance(raw, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError("evidence judge output must contain results")
    by_id = {
        str(row.get("target_id")): row
        for row in rows
        if isinstance(row, Mapping) and row.get("target_id")
    }
    expected = [str(row["target_id"]) for row in requested]
    if set(by_id) != set(expected) or len(by_id) != len(rows):
        raise ValueError("evidence judge target set mismatch")
    out: list[dict[str, Any]] = []
    request_by_id = {str(row["target_id"]): row for row in requested}
    for target_id in expected:
        row = by_id[target_id]
        request = request_by_id[target_id]
        verdict = str(row.get("verdict") or "")
        if verdict not in EVIDENCE_VERDICTS:
            raise ValueError(f"invalid evidence verdict for {target_id}")
        quote = str(row.get("matched_evidence_quote") or "")
        if (
            verdict in {"supported", "contradicted"}
            and request["support_mode"] == "body"
            and (not quote or quote not in body)
        ):
            verdict, quote = "ambiguous", ""
        if request["support_mode"] == "closed_page_absence":
            quote = ""
        elif verdict in {"not_supported", "ambiguous"}:
            quote = ""
        out.append(
            {
                "target_id": target_id,
                "citation_url": request["citation_url"],
                "verdict": verdict,
                "matched_evidence_quote": quote or None,
                "observed_content_sha256": request["observed_content_sha256"],
                "reason": str(row.get("reason") or "")[:800],
            }
        )
    return out


def judge_route_flexible(
    rubric: Mapping[str, Any],
    report: str,
    ledger: ObservationLedger,
    *,
    model: str | None = None,
    judge_call: JudgeCall | None = None,
) -> dict[str, Any]:
    validate_rubric(rubric)
    if not ledger.complete:
        raise ValueError(f"observation ledger incomplete: {ledger.withhold_reason_codes}")
    targets = [dict(target) for target in rubric["targets"]]
    report_system = (
        "You are a conservative rubric annotator. Judge only whether the REPORT "
        "satisfies each semantic target. Do not assume citations are valid and do "
        "not use outside knowledge. A target is satisfied only when all material "
        "clauses are preserved and none of its failure_conditions occurs. Use "
        "contradicted when the report explicitly asserts an incompatible or "
        "over-strong claim. For satisfied or contradicted, matched_quote must be "
        "one exact contiguous substring from REPORT, preferably the shortest full "
        "paragraph that demonstrates the judgment. Return JSON only."
    )
    report_payload = {
        "instruction": (
            "Return {\"results\":[{\"target_id\":...,\"verdict\":"
            "\"satisfied|contradicted|not_mentioned|ambiguous\"," 
            "\"matched_quote\":...,\"reason\":...}]} with every target once."
        ),
        "targets": [
            {
                "target_id": target["target_id"],
                "kind": target["kind"],
                "statement": target["statement"],
                "failure_conditions": target.get("failure_conditions") or [],
            }
            for target in targets
        ],
        "REPORT": report,
    }
    report_response, report_raw = _call(
        report_system, report_payload, model=model, judge_call=judge_call
    )
    report_results = _validate_report_results(report, targets, report_raw)

    bindings = _candidate_bindings(rubric, report, report_results, ledger)
    bodies = _observed_bodies(ledger)
    evidence_results: list[dict[str, Any]] = []
    evidence_response_hashes: list[str] = []
    evidence_system = (
        "You are a conservative claim-to-page support annotator. Judge only the "
        "provided observed PAGE BODY. The page must support the report claim and "
        "the frozen target with the same entity, polarity, numbers, and scope. "
        "Marketing pages support that the listing makes a claim, not that the "
        "marketed performance is independently true. For support_mode=body, copy "
        "one exact contiguous supporting substring into matched_evidence_quote. "
        "For support_mode=closed_page_absence, inspect the complete supplied page "
        "and leave matched_evidence_quote empty. Return JSON only."
    )
    for url, requested in sorted(bindings.items()):
        # Deduplicate a target that saw the same URL twice in the same section.
        unique = {str(row["target_id"]): row for row in requested}
        requested = list(unique.values())
        body = bodies[url]["body"]
        evidence_payload = {
            "instruction": (
                "Return {\"results\":[{\"target_id\":...,\"verdict\":"
                "\"supported|contradicted|not_supported|ambiguous\"," 
                "\"matched_evidence_quote\":...,\"reason\":...}]} once per target."
            ),
            "citation_url": url,
            "targets": requested,
            "PAGE_BODY": body,
        }
        response, raw = _call(
            evidence_system,
            evidence_payload,
            model=model,
            judge_call=judge_call,
        )
        evidence_response_hashes.append(sha256(response.encode("utf-8")).hexdigest())
        evidence_results.extend(_validate_evidence_results(requested, body, raw))

    return {
        "schema": JUDGMENT_SCHEMA,
        "prompt_version": PROMPT_VERSION,
        "rubric_sha256": canonical_sha256(rubric),
        "report_sha256": sha256(report.encode("utf-8")).hexdigest(),
        "run_id": ledger.run_id,
        "judge": {
            "provider": os.environ.get("JUDGE_PROVIDER", "anthropic"),
            "model": model or os.environ.get("JUDGE_MODEL"),
            "formal_eligible": True,
        },
        "report_prompt_sha256": sha256(
            (report_system + "\n" + json.dumps(report_payload, ensure_ascii=False)).encode("utf-8")
        ).hexdigest(),
        "report_response_sha256": sha256(report_response.encode("utf-8")).hexdigest(),
        "evidence_response_sha256s": evidence_response_hashes,
        "report_results": report_results,
        "evidence_results": evidence_results,
    }


__all__ = ["judge_route_flexible"]
