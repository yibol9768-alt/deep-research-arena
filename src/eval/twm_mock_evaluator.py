"""Deterministic Task-World-Model-backed evaluator for development pilots.

This is intentionally a *mock*, not a leaderboard judge.  It executes frozen,
inspectable regex contracts against a report, then binds locally cited and
observed pages to task-world spans (or to a deterministic on-demand matcher).
It exists to exercise the complete World Model -> judgment -> deterministic
scorer path without smuggling a hand-authored verdict table into the pilot.
"""

from __future__ import annotations

from hashlib import sha256
import re
from typing import Any

from src.eval.observation_ledger import ObservationLedger
from src.eval.sandbox_native_grc import (
    JUDGMENT_SCHEMA,
    canonical_sha256,
    validate_suite,
    validate_world_index,
)
from src.verifiers.citation_format import canonicalize_url, extract_citations


MOCK_PROVIDER = "twm_backed_mock_evaluator"
MOCK_VERSION = "v1"
_FLAGS = re.IGNORECASE | re.DOTALL


class TWMBuildError(ValueError):
    """Raised when a mock-evaluator input is not internally sealed."""


def _canonical(url: Any) -> str:
    raw = str(url or "").strip()
    return canonicalize_url(raw) if raw else ""


def _all_checks(suite: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        check
        for facet in suite["facets"]
        for unit in facet["units"]
        for check in unit["checks"]
    ]


def _compile(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern, _FLAGS)
    except re.error as exc:
        raise TWMBuildError(f"invalid mock regex {pattern!r}: {exc}") from exc


def _matches(patterns: list[str], text: str) -> list[re.Match[str]]:
    found: list[re.Match[str]] = []
    for pattern in patterns:
        found.extend(_compile(str(pattern)).finditer(text))
    return found


def _paragraph_span(report: str, start: int, end: int) -> tuple[int, int, str]:
    left = report.rfind("\n\n", 0, start)
    left = 0 if left < 0 else left + 2
    right = report.find("\n\n", end)
    right = len(report) if right < 0 else right
    while left < right and report[left].isspace():
        left += 1
    while right > left and report[right - 1].isspace():
        right -= 1
    if left >= right:
        left, right = start, end
    return left, right, report[left:right]


def _semantic_verdict(
    report: str, contract: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    contradiction_patterns = [
        str(value) for value in contract.get("contradiction_patterns") or []
    ]
    contradiction_matches = _matches(contradiction_patterns, report)
    if contradiction_matches and contract.get("contradiction_scope", "window") == "report":
        hit = min(contradiction_matches, key=lambda row: row.start())
        start, end, quote = _paragraph_span(report, hit.start(), hit.end())
        return (
            {
                "verdict": "contradicted",
                "quote": quote,
                "start": start,
                "end": end,
                "reason": "frozen mock contradiction pattern matched",
            },
            {
                "matched_contradiction": hit.group(0),
                "matched_required_groups": 0,
            },
        )

    groups = [
        [str(pattern) for pattern in group]
        for group in contract.get("required_groups") or []
    ]
    anchors = [str(value) for value in contract.get("anchors") or []]
    if not groups:
        raise TWMBuildError("mock semantic contract requires required_groups")

    anchor_matches = _matches(anchors, report) if anchors else []
    if not anchor_matches:
        anchor_matches = _matches(groups[0], report)
    window_chars = int(contract.get("selection_window_chars", 3500))
    candidates: list[tuple[int, int, list[re.Match[str]], re.Match[str]]] = []
    for anchor in anchor_matches:
        window_start = max(0, anchor.start() - window_chars)
        window_end = min(len(report), anchor.end() + window_chars)
        window = report[window_start:window_end]
        chosen: list[re.Match[str]] = []
        complete = True
        for group in groups:
            group_matches = _matches(group, window)
            if not group_matches:
                complete = False
                break
            nearest = min(
                group_matches,
                key=lambda row: abs((window_start + row.start()) - anchor.start()),
            )
            chosen.append(nearest)
        if not complete:
            continue
        absolute_starts = [window_start + row.start() for row in chosen]
        absolute_ends = [window_start + row.end() for row in chosen]
        selected_start = min([anchor.start(), *absolute_starts])
        selected_end = max([anchor.end(), *absolute_ends])
        candidates.append((selected_start, selected_end, chosen, anchor))

    if not candidates:
        return (
            {
                "verdict": "not_satisfied",
                "quote": "",
                "start": None,
                "end": None,
                "reason": "frozen mock required pattern groups did not co-occur",
            },
            {
                "matched_contradiction": None,
                "matched_required_groups": 0,
            },
        )

    selected_start, selected_end, chosen, anchor = min(
        candidates, key=lambda row: (row[1] - row[0], row[0])
    )
    if contradiction_patterns:
        local_text = report[
            max(0, selected_start - window_chars) : min(
                len(report), selected_end + window_chars
            )
        ]
        local_contradictions = _matches(contradiction_patterns, local_text)
        if local_contradictions:
            local = min(local_contradictions, key=lambda row: row.start())
            offset = max(0, selected_start - window_chars)
            start, end, quote = _paragraph_span(
                report, offset + local.start(), offset + local.end()
            )
            return (
                {
                    "verdict": "contradicted",
                    "quote": quote,
                    "start": start,
                    "end": end,
                    "reason": "frozen mock contradiction pattern matched in check window",
                },
                {
                    "matched_contradiction": local.group(0),
                    "matched_required_groups": len(chosen),
                },
            )

    start, end, quote = _paragraph_span(report, selected_start, selected_end)
    return (
        {
            "verdict": "satisfied",
            "quote": quote,
            "start": start,
            "end": end,
            "reason": "all frozen mock required pattern groups matched",
        },
        {
            "matched_anchor": anchor.group(0),
            "matched_required_groups": len(chosen),
            "matched_contradiction": None,
        },
    )


def _observed_pages(ledger: ObservationLedger) -> dict[str, list[dict[str, Any]]]:
    pages: dict[str, list[dict[str, Any]]] = {}
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
        pages.setdefault(event.canonical_url, []).append(
            {
                "body": body,
                "event_id": event.event_id,
                "complete": (
                    event.event_type == "fetch_body"
                    and event.metadata.get("partial") is not True
                )
                or event.metadata.get("delivery_scope") == "complete_page",
            }
        )
    return pages


def _world_maps(world: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pages: dict[str, Any] = {}
    spans: dict[str, Any] = {}
    for page in world["pages"]:
        url = _canonical(page["canonical_url"])
        pages[url] = page
        for span in page.get("spans") or []:
            row = dict(span)
            row["canonical_url"] = url
            spans[str(span["span_id"])] = row
    return pages, spans


def _matcher_excerpt(body: str, matcher: dict[str, Any]) -> str | None:
    groups = matcher.get("required_groups") or []
    chosen: list[re.Match[str]] = []
    for raw_group in groups:
        matches = _matches([str(value) for value in raw_group], body)
        if not matches:
            return None
        chosen.append(min(matches, key=lambda row: row.start()))
    if not chosen:
        return None
    start = min(row.start() for row in chosen)
    end = max(row.end() for row in chosen)
    if end - start > 12000:
        return None
    return body[start:end]


def _local_citation_urls(
    *, citations: list[Any], content: dict[str, Any], window: int
) -> list[str]:
    start = content.get("start")
    end = content.get("end")
    if type(start) is not int or type(end) is not int:
        return []
    rows = [
        citation
        for citation in citations
        if start - window <= citation.char_offset <= end + window
    ]
    rows.sort(key=lambda row: abs(row.char_offset - end))
    out: list[str] = []
    for citation in rows:
        if citation.canonical_url not in out:
            out.append(citation.canonical_url)
    return out


def _evidence_binding(
    *,
    contract: dict[str, Any],
    content: dict[str, Any],
    citations: list[Any],
    pages: dict[str, Any],
    spans: dict[str, Any],
    observed: dict[str, list[dict[str, Any]]],
    matcher: dict[str, Any] | None,
) -> dict[str, Any] | None:
    window = int(contract.get("binding_window_chars", 1200))
    local_urls = _local_citation_urls(
        citations=citations, content=content, window=window
    )
    allowed_roles = set(contract.get("acceptable_source_roles") or [])
    mode = str(contract.get("support_mode") or "body")
    witnesses = [str(value) for value in contract.get("known_witnesses") or []]
    witness_urls: set[str] = set()
    witness_spans_by_url: dict[str, list[dict[str, Any]]] = {}
    for witness in witnesses:
        if witness.startswith(("http://", "https://")):
            witness_urls.add(_canonical(witness))
        elif witness in spans:
            span = spans[witness]
            url = str(span["canonical_url"])
            witness_urls.add(url)
            witness_spans_by_url.setdefault(url, []).append(span)

    for url in local_urls:
        page = pages.get(url)
        observed_rows = observed.get(url) or []
        if page is None or not observed_rows:
            continue
        if not (set(page.get("source_roles") or []) & allowed_roles):
            continue
        binding: dict[str, Any] = {
            "url": url,
            "quote": content["quote"],
            "start": content["start"],
            "end": content["end"],
            "evidence_span_id": None,
            "evidence_quote": "",
            "support_verdict": "supported",
        }
        if mode == "closed_page_absence":
            if url not in witness_urls or not any(row["complete"] for row in observed_rows):
                continue
            return binding

        for span in witness_spans_by_url.get(url, []):
            evidence_quote = str(span["text"])
            if any(evidence_quote in row["body"] for row in observed_rows):
                binding["evidence_span_id"] = span["span_id"]
                binding["evidence_quote"] = evidence_quote
                return binding

        if matcher is None:
            continue
        for observed_row in observed_rows:
            excerpt = _matcher_excerpt(observed_row["body"], matcher)
            if excerpt is None:
                continue
            binding["evidence_quote"] = excerpt
            binding["evidence_certificate"] = {
                "status": "accepted",
                "certificate_id": (
                    "twm-mock-"
                    + sha256(
                        f"{contract['contract_id']}\n{url}\n{excerpt}".encode("utf-8")
                    ).hexdigest()[:20]
                ),
                "method": "twm_mock_on_demand_match",
                "contract_id": contract["contract_id"],
            }
            return binding
    return None


def _search_binding(
    *, premise: dict[str, Any], content: dict[str, Any], citations: list[Any]
) -> dict[str, Any] | None:
    urls = _local_citation_urls(
        citations=citations,
        content=content,
        window=int(premise.get("binding_window_chars", 1800)),
    )
    if not urls:
        return None
    return {
        "url": urls[0],
        "quote": content["quote"],
        "start": content["start"],
        "end": content["end"],
    }


def _validate_twm(twm: dict[str, Any], world: dict[str, Any]) -> None:
    if twm.get("schema") != "dra_task_world_model_v1":
        raise TWMBuildError("unexpected Task World Model schema")
    if twm.get("world_sha256") != canonical_sha256(world):
        raise TWMBuildError("Task World Model is not sealed to this World Index")
    _, spans = _world_maps(world)
    assertion_ids = {
        str(assertion.get("assertion_id") or "")
        for assertion in twm.get("assertions") or []
    }
    for assertion in twm.get("assertions") or []:
        for span_id in assertion.get("known_support_span_ids") or []:
            if str(span_id) not in spans:
                raise TWMBuildError(
                    f"TWM assertion references missing span: {span_id}"
                )
    trace_ids = {
        str(row.get("span_id") or "") for row in twm.get("extraction_trace") or []
    }
    if not trace_ids or not trace_ids.issubset(spans):
        raise TWMBuildError("TWM extraction trace is incomplete")
    for row in twm.get("extraction_trace") or []:
        unknown = set(row.get("assertion_ids") or []) - assertion_ids
        if unknown:
            raise TWMBuildError(
                f"TWM extraction trace references unknown assertions: {sorted(unknown)}"
            )
    relation_ids: set[str] = set()
    for relation in twm.get("relations") or []:
        relation_id = str(relation.get("relation_id") or "")
        if not relation_id or relation_id in relation_ids:
            raise TWMBuildError("TWM relation IDs must be non-empty and unique")
        relation_ids.add(relation_id)
        referenced = set(relation.get("source_assertion_ids") or []) | set(
            relation.get("target_assertion_ids") or []
        )
        unknown = referenced - assertion_ids
        if unknown:
            raise TWMBuildError(
                f"TWM relation references unknown assertions: {sorted(unknown)}"
            )


def evaluate_report_with_twm_mock(
    *,
    suite: dict[str, Any],
    world: dict[str, Any],
    twm: dict[str, Any],
    report: str,
    ledger: ObservationLedger,
) -> dict[str, Any]:
    """Create a sealed, replayable development judgment from frozen assets."""

    validate_suite(suite)
    validate_world_index(world)
    _validate_twm(twm, world)
    semantic_contracts = suite.get("mock_semantic_contracts") or {}
    evidence_matchers = suite.get("mock_evidence_matchers") or {}
    checks = _all_checks(suite)
    if set(semantic_contracts) != {str(check["check_id"]) for check in checks}:
        raise TWMBuildError("mock semantic contracts must cover every check exactly")

    contracts = {
        str(row["contract_id"]): row for row in suite.get("evidence_contracts") or []
    }
    pages, spans = _world_maps(world)
    observed = _observed_pages(ledger)
    citations = extract_citations(report, sandbox_only=False)
    rows: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for check in checks:
        check_id = str(check["check_id"])
        content, trace = _semantic_verdict(report, semantic_contracts[check_id])
        route_attempts: list[dict[str, Any]] = []
        if content["verdict"] == "satisfied":
            for route in check.get("evidence_routes") or []:
                premise_rows: list[dict[str, Any]] = []
                route_complete = True
                for premise in route["premises"]:
                    if premise.get("kind", "evidence") == "search_certificate":
                        binding = _search_binding(
                            premise=premise, content=content, citations=citations
                        )
                    else:
                        contract = contracts[str(premise["contract_id"])]
                        binding = _evidence_binding(
                            contract=contract,
                            content=content,
                            citations=citations,
                            pages=pages,
                            spans=spans,
                            observed=observed,
                            matcher=evidence_matchers.get(contract["contract_id"]),
                        )
                    if binding is None:
                        route_complete = False
                        break
                    premise_rows.append(
                        {"premise_id": premise["premise_id"], "bindings": [binding]}
                    )
                if route_complete:
                    route_attempts.append(
                        {
                            "route_id": route["route_id"],
                            "coherence_verdict": "coherent",
                            "conflict_verdict": (
                                "resolved"
                                if check_id == "K_DISTORTION_COMPARISON"
                                else "not_material"
                            ),
                            "premises": premise_rows,
                        }
                    )
        rows.append(
            {
                "check_id": check_id,
                "content": content,
                "route_attempts": route_attempts,
            }
        )
        traces.append(
            {
                "check_id": check_id,
                "content_verdict": content["verdict"],
                "coherent_route_ids": [row["route_id"] for row in route_attempts],
                **trace,
            }
        )

    decision = next(
        row for row in rows if row["check_id"] == "K_DECISION_ACTION"
    )
    return {
        "schema": JUDGMENT_SCHEMA,
        "task_id": suite["task_id"],
        "evaluator": {
            "provider": MOCK_PROVIDER,
            "version": MOCK_VERSION,
            "formal_eligible": False,
        },
        "seals": {
            "suite_sha256": canonical_sha256(suite),
            "world_sha256": canonical_sha256(world),
            "report_sha256": sha256(report.encode("utf-8")).hexdigest(),
            "ledger_sha256": canonical_sha256(ledger.to_dict()),
            "task_world_model_sha256": canonical_sha256(twm),
        },
        "checks": rows,
        "url_audits": [],
        "output_contract": {
            "verdict": (
                "satisfied"
                if decision["content"]["verdict"] == "satisfied"
                else "not_satisfied"
            )
        },
        "mock_trace": traces,
        "calibration_note": (
            "Development-only deterministic mock. It exercises Task World Model "
            "construction and evidence binding, but is not human-calibrated and "
            "must not be used for formal leaderboard ranking."
        ),
    }
