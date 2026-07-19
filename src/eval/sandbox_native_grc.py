"""Sandbox-native Grounded Research Coverage scoring.

This module implements the deterministic half of the DRA v3.3 single-task
vertical slice.  A semantic evaluator still decides whether a report satisfies
each typed content contract and whether an observed page span supports a
premise.  The evaluator must seal those decisions to the report, test suite,
world index, and observation ledger.  Everything after that decision is
replayed here without network access.

The important unit is a research *check*.  A check contributes only when its
content contract is satisfied and one coherent evidence route passes in full.
Known witnesses certify answerability; they are never URL allowlists.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from hashlib import sha256
import json
from typing import Any
from urllib.parse import urlsplit

from src.eval.observation_ledger import ObservationLedger
from src.verifiers.citation_format import canonicalize_url, extract_citations


SUITE_SCHEMA = "dra_research_test_suite_v1"
WORLD_SCHEMA = "dra_task_world_index_v1"
JUDGMENT_SCHEMA = "dra_grc_judgment_v1"
SCORING_SEMANTICS = "dra_grounded_research_coverage_v1"

CONTENT_VERDICTS = {"satisfied", "not_satisfied", "contradicted", "ambiguous"}
SUPPORT_VERDICTS = {
    "supported",
    "unsupported",
    "contradicted",
    "wrong_binding",
    "ambiguous",
}
COHERENCE_VERDICTS = {"coherent", "incoherent", "ambiguous"}
CONFLICT_VERDICTS = {"not_material", "resolved", "unresolved", "ambiguous"}
URL_AUDIT_STATUSES = {
    "nonexistent_fabricated",
    "real_off_world",
    "registry_alias_error",
    "malformed_citation",
}


class SandboxNativeScoringError(ValueError):
    """Raised when a supposedly frozen scoring asset is malformed."""


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _canonical(url: Any) -> str:
    raw = str(url or "").strip()
    return canonicalize_url(raw) if raw else ""


def _all_checks(suite: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for facet in suite.get("facets") or []:
        for unit in facet.get("units") or []:
            for check in unit.get("checks") or []:
                row = dict(check)
                row["facet_id"] = str(facet.get("facet_id") or "")
                row["unit_id"] = str(unit.get("unit_id") or "")
                out.append(row)
    return out


def validate_suite(suite: Mapping[str, Any]) -> None:
    if suite.get("schema") != SUITE_SCHEMA:
        raise SandboxNativeScoringError(f"suite schema must be {SUITE_SCHEMA}")
    if not str(suite.get("task_id") or "").strip():
        raise SandboxNativeScoringError("suite task_id is required")
    facets = suite.get("facets")
    if not isinstance(facets, list) or not facets:
        raise SandboxNativeScoringError("suite facets must be a non-empty list")

    facet_ids: set[str] = set()
    unit_ids: set[str] = set()
    check_ids: set[str] = set()
    contract_ids = {
        str(row.get("contract_id") or "")
        for row in suite.get("evidence_contracts") or []
        if isinstance(row, Mapping)
    }
    certificate_ids = {
        str(row.get("certificate_id") or "")
        for row in suite.get("search_certificates") or []
        if isinstance(row, Mapping)
    }
    dependencies: dict[str, set[str]] = {}

    for facet in facets:
        if not isinstance(facet, Mapping):
            raise SandboxNativeScoringError("facet rows must be objects")
        facet_id = str(facet.get("facet_id") or "")
        if not facet_id or facet_id in facet_ids:
            raise SandboxNativeScoringError("facet IDs must be non-empty and unique")
        facet_ids.add(facet_id)
        units = facet.get("units")
        if not isinstance(units, list) or not units:
            raise SandboxNativeScoringError(f"{facet_id}: units are required")
        for unit in units:
            if not isinstance(unit, Mapping):
                raise SandboxNativeScoringError(f"{facet_id}: unit rows must be objects")
            unit_id = str(unit.get("unit_id") or "")
            if not unit_id or unit_id in unit_ids:
                raise SandboxNativeScoringError("unit IDs must be non-empty and globally unique")
            unit_ids.add(unit_id)
            checks = unit.get("checks")
            if not isinstance(checks, list) or not 2 <= len(checks) <= 5:
                raise SandboxNativeScoringError(
                    f"{unit_id}: each unit must contain 2 to 5 canonical checks"
                )
            for check in checks:
                if not isinstance(check, Mapping):
                    raise SandboxNativeScoringError(f"{unit_id}: check rows must be objects")
                check_id = str(check.get("check_id") or "")
                if not check_id or check_id in check_ids:
                    raise SandboxNativeScoringError(
                        "check IDs must be non-empty and globally unique"
                    )
                check_ids.add(check_id)
                if not str(check.get("content_contract") or "").strip():
                    raise SandboxNativeScoringError(
                        f"{check_id}: content_contract is required"
                    )
                if check.get("applicable") not in {True, False}:
                    raise SandboxNativeScoringError(
                        f"{check_id}: applicable must be a JSON boolean"
                    )
                routes = check.get("evidence_routes") or []
                if not check.get("evidence_exempt") and not routes:
                    raise SandboxNativeScoringError(
                        f"{check_id}: non-exempt checks need evidence routes"
                    )
                route_ids: set[str] = set()
                for route in routes:
                    route_id = str(route.get("route_id") or "")
                    if not route_id or route_id in route_ids:
                        raise SandboxNativeScoringError(
                            f"{check_id}: route IDs must be non-empty and unique"
                        )
                    route_ids.add(route_id)
                    premises = route.get("premises")
                    if not isinstance(premises, list) or not premises:
                        raise SandboxNativeScoringError(
                            f"{check_id}/{route_id}: premises are required"
                        )
                    premise_ids: set[str] = set()
                    for premise in premises:
                        premise_id = str(premise.get("premise_id") or "")
                        if not premise_id or premise_id in premise_ids:
                            raise SandboxNativeScoringError(
                                f"{check_id}/{route_id}: premise IDs must be unique"
                            )
                        premise_ids.add(premise_id)
                        kind = premise.get("kind", "evidence")
                        if kind == "evidence":
                            if str(premise.get("contract_id") or "") not in contract_ids:
                                raise SandboxNativeScoringError(
                                    f"{check_id}/{route_id}/{premise_id}: unknown contract"
                                )
                        elif kind == "search_certificate":
                            if str(premise.get("certificate_id") or "") not in certificate_ids:
                                raise SandboxNativeScoringError(
                                    f"{check_id}/{route_id}/{premise_id}: unknown certificate"
                                )
                        else:
                            raise SandboxNativeScoringError(
                                f"{check_id}/{route_id}/{premise_id}: invalid premise kind"
                            )
                dependencies[check_id] = {
                    str(value) for value in check.get("depends_on_checks") or []
                }

    for check_id, deps in dependencies.items():
        unknown = sorted(deps - check_ids)
        if unknown:
            raise SandboxNativeScoringError(
                f"{check_id}: unknown check dependencies {unknown}"
            )
        if check_id in deps:
            raise SandboxNativeScoringError(f"{check_id}: self dependency")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(check_id: str) -> None:
        if check_id in visited:
            return
        if check_id in visiting:
            raise SandboxNativeScoringError("check dependency graph contains a cycle")
        visiting.add(check_id)
        for dep in dependencies.get(check_id, set()):
            visit(dep)
        visiting.remove(check_id)
        visited.add(check_id)

    for check_id in check_ids:
        visit(check_id)


def validate_world_index(world: Mapping[str, Any]) -> None:
    if world.get("schema") != WORLD_SCHEMA:
        raise SandboxNativeScoringError(f"world schema must be {WORLD_SCHEMA}")
    registry = world.get("registry_urls")
    pages = world.get("pages")
    if not isinstance(registry, list) or not registry:
        raise SandboxNativeScoringError("world registry_urls are required")
    if not isinstance(pages, list):
        raise SandboxNativeScoringError("world pages must be a list")
    canonical_registry = [_canonical(url) for url in registry]
    if not all(canonical_registry) or len(set(canonical_registry)) != len(canonical_registry):
        raise SandboxNativeScoringError("world registry URLs must be canonicalizable and unique")
    page_urls: set[str] = set()
    span_ids: set[str] = set()
    for page in pages:
        url = _canonical(page.get("canonical_url"))
        if not url or url in page_urls or url not in set(canonical_registry):
            raise SandboxNativeScoringError("world page URL is duplicate or outside registry")
        page_urls.add(url)
        roles = page.get("source_roles")
        if not isinstance(roles, list) or not roles:
            raise SandboxNativeScoringError(f"{url}: source_roles are required")
        for span in page.get("spans") or []:
            span_id = str(span.get("span_id") or "")
            if not span_id or span_id in span_ids:
                raise SandboxNativeScoringError("world span IDs must be non-empty and unique")
            span_ids.add(span_id)
            text = str(span.get("text") or "")
            if not text or sha256(text.encode("utf-8")).hexdigest() != span.get("text_sha256"):
                raise SandboxNativeScoringError(f"{span_id}: span text hash mismatch")


def _observed_pages(ledger: ObservationLedger) -> dict[str, list[dict[str, Any]]]:
    pages: dict[str, list[dict[str, Any]]] = defaultdict(list)
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
        pages[event.canonical_url].append(
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "body": body,
                "content_sha256": event.content_sha256,
                "delivery_complete": (
                    event.event_type == "fetch_body"
                    and event.metadata.get("partial") is not True
                )
                or event.metadata.get("delivery_scope") == "complete_page",
            }
        )
    return pages


def _search_certificate_results(
    suite: Mapping[str, Any], ledger: ObservationLedger, observed: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    events_by_query: dict[str, set[str]] = defaultdict(set)
    capture_by_query: dict[str, set[str]] = defaultdict(set)
    for event in ledger.events:
        if event.event_type != "search_result":
            continue
        query = str(event.metadata.get("query") or "").strip()
        if not query:
            continue
        events_by_query[query].add(event.canonical_url)
        capture_url = _canonical(event.metadata.get("search_capture_url"))
        if capture_url:
            capture_by_query[query].add(capture_url)

    out: dict[str, dict[str, Any]] = {}
    for cert in suite.get("search_certificates") or []:
        cert_id = str(cert["certificate_id"])
        candidates: list[dict[str, Any]] = []
        for query, returned in events_by_query.items():
            low = " ".join(query.casefold().split())
            entity_ok = all(
                any(str(term).casefold() in low for term in group)
                for group in cert.get("required_entity_groups") or []
            )
            topic_ok = all(
                any(str(term).casefold() in low for term in group)
                for group in cert.get("required_topic_groups") or []
            )
            if not entity_ok or not topic_ok:
                continue
            missing = sorted(url for url in returned if url not in observed)
            capture_urls = sorted(capture_by_query.get(query, set()))
            candidates.append(
                {
                    "query": query,
                    "returned_urls": sorted(returned),
                    "missing_observed_urls": missing,
                    "capture_urls": capture_urls,
                    "capture_observed": any(url in observed for url in capture_urls),
                }
            )
        passed = any(
            (not cert.get("require_all_returned_results_observed") or not row["missing_observed_urls"])
            and (not cert.get("require_capture_page_observed") or row["capture_observed"])
            for row in candidates
        )
        out[cert_id] = {
            "certificate_id": cert_id,
            "passed": passed,
            "matching_queries": candidates,
        }
    return out


def _judgment_checks(judgment: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = judgment.get("checks")
    if not isinstance(rows, list):
        raise SandboxNativeScoringError("judgment checks must be a list")
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise SandboxNativeScoringError("judgment check rows must be objects")
        check_id = str(row.get("check_id") or "")
        if not check_id or check_id in out:
            raise SandboxNativeScoringError("judgment check IDs must be present and unique")
        out[check_id] = dict(row)
    return out


def _exact_report_span(report: str, row: Mapping[str, Any]) -> tuple[int, int, str] | None:
    quote = str(row.get("quote") or "")
    start = row.get("start")
    end = row.get("end")
    if not quote or type(start) is not int or type(end) is not int:
        return None
    if not 0 <= start < end <= len(report) or report[start:end] != quote:
        return None
    return start, end, quote


def _world_maps(world: Mapping[str, Any]):
    registry = {_canonical(url) for url in world["registry_urls"]}
    pages: dict[str, dict[str, Any]] = {}
    spans: dict[str, dict[str, Any]] = {}
    for raw_page in world.get("pages") or []:
        page = dict(raw_page)
        url = _canonical(page["canonical_url"])
        pages[url] = page
        for raw_span in page.get("spans") or []:
            span = dict(raw_span)
            span["canonical_url"] = url
            spans[str(span["span_id"])] = span
    contracts = {
        str(row["contract_id"]): dict(row)
        for row in world.get("evidence_contract_overrides") or []
    }
    return registry, pages, spans, contracts


def _suite_contracts(suite: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["contract_id"]): dict(row)
        for row in suite.get("evidence_contracts") or []
    }


def _local_citation(
    citations: list[Any], url: str, start: int, end: int, window: int
) -> dict[str, Any] | None:
    matches = [
        citation
        for citation in citations
        if citation.canonical_url == url
        and start - window <= citation.char_offset <= end + window
    ]
    if not matches:
        return None
    citation = min(matches, key=lambda item: abs(item.char_offset - end))
    return {
        "url": url,
        "offset": citation.char_offset,
        "style": citation.style,
    }


def _binding_result(
    *,
    binding: Mapping[str, Any],
    contract: Mapping[str, Any],
    report: str,
    citations: list[Any],
    registry: set[str],
    pages: Mapping[str, Mapping[str, Any]],
    spans: Mapping[str, Mapping[str, Any]],
    observed: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    url = _canonical(binding.get("url"))
    report_span = _exact_report_span(report, binding)
    local = None
    if report_span is not None and url:
        local = _local_citation(
            citations,
            url,
            report_span[0],
            report_span[1],
            int(contract.get("binding_window_chars", 1200)),
        )
    page = pages.get(url)
    allowed_roles = set(contract.get("acceptable_source_roles") or [])
    actual_roles = set(page.get("source_roles") or []) if page else set()
    observed_rows = observed.get(url) or []
    support_verdict = str(binding.get("support_verdict") or "")
    support_mode = str(contract.get("support_mode") or "body")
    evidence_quote = str(binding.get("evidence_quote") or "")
    span_id = str(binding.get("evidence_span_id") or "")
    span = spans.get(span_id) if span_id else None
    quote_observed = False
    complete_observation = False
    if support_mode == "closed_page_absence":
        complete_observation = any(row["delivery_complete"] for row in observed_rows)
        quote_observed = complete_observation
    elif evidence_quote:
        quote_observed = any(evidence_quote in row["body"] for row in observed_rows)

    known_span_valid = False
    if span is not None:
        known_span_valid = span.get("canonical_url") == url and (
            support_mode == "closed_page_absence"
            or evidence_quote == str(span.get("text") or "")
            or evidence_quote in str(span.get("text") or "")
            or str(span.get("text") or "") in evidence_quote
        )
    certificate = binding.get("evidence_certificate")
    certificate_valid = (
        isinstance(certificate, Mapping)
        and certificate.get("status") == "accepted"
        and bool(str(certificate.get("certificate_id") or ""))
    )
    support_asset_valid = known_span_valid or certificate_valid or (
        support_mode == "closed_page_absence" and bool(page)
    )

    checks = {
        "url_registered": url in registry,
        "report_span_exact": report_span is not None,
        "locally_bound": local is not None,
        "observed": bool(observed_rows),
        "evidence_quote_observed": quote_observed,
        "source_role_valid": bool(actual_roles & allowed_roles),
        "support_asset_valid": support_asset_valid,
        "semantic_support": support_verdict == "supported",
    }
    verified = all(checks.values())
    reason_codes = [name for name, value in checks.items() if not value]
    if support_verdict in SUPPORT_VERDICTS and support_verdict != "supported":
        reason_codes.append(f"support_{support_verdict}")
    return {
        "url": url,
        "verified": verified,
        "checks": checks,
        "support_verdict": support_verdict,
        "source_roles": sorted(actual_roles),
        "local_citation": local,
        "evidence_span_id": span_id or None,
        "reason_codes": sorted(set(reason_codes)),
    }


def _search_binding_result(
    *,
    binding: Mapping[str, Any],
    certificate_id: str,
    certificate_results: Mapping[str, Mapping[str, Any]],
    report: str,
    citations: list[Any],
    registry: set[str],
    observed: Mapping[str, Any],
    window: int,
) -> dict[str, Any]:
    url = _canonical(binding.get("url"))
    report_span = _exact_report_span(report, binding)
    local = None
    if report_span is not None and url:
        local = _local_citation(citations, url, report_span[0], report_span[1], window)
    cert = certificate_results.get(certificate_id) or {}
    checks = {
        "url_registered": url in registry,
        "report_span_exact": report_span is not None,
        "locally_bound": local is not None,
        "search_capture_observed": url in observed,
        "certificate_passed": cert.get("passed") is True,
    }
    return {
        "url": url,
        "verified": all(checks.values()),
        "checks": checks,
        "certificate_id": certificate_id,
        "local_citation": local,
        "reason_codes": [name for name, value in checks.items() if not value],
    }


def _macro_score(
    suite: Mapping[str, Any], values: Mapping[str, bool]
) -> tuple[float, list[dict[str, Any]]]:
    facet_scores: list[float] = []
    facet_rows: list[dict[str, Any]] = []
    for facet in suite["facets"]:
        unit_scores: list[float] = []
        unit_rows: list[dict[str, Any]] = []
        for unit in facet["units"]:
            applicable = [
                check
                for check in unit["checks"]
                if check.get("applicable") is True and check.get("tier", "core") == "core"
            ]
            if not applicable:
                continue
            score = sum(bool(values.get(str(check["check_id"]), False)) for check in applicable) / len(applicable)
            unit_scores.append(score)
            unit_rows.append(
                {
                    "unit_id": unit["unit_id"],
                    "score": score,
                    "passed_checks": sum(
                        bool(values.get(str(check["check_id"]), False)) for check in applicable
                    ),
                    "applicable_checks": len(applicable),
                }
            )
        if not unit_scores:
            continue
        facet_score = sum(unit_scores) / len(unit_scores)
        facet_scores.append(facet_score)
        facet_rows.append(
            {
                "facet_id": facet["facet_id"],
                "score": facet_score,
                "units": unit_rows,
            }
        )
    if not facet_scores:
        raise SandboxNativeScoringError("suite has no applicable core facets")
    return sum(facet_scores) / len(facet_scores), facet_rows


def score_grounded_research_coverage(
    *,
    suite: Mapping[str, Any],
    world: Mapping[str, Any],
    report: str,
    ledger: ObservationLedger,
    judgment: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay one sealed report judgment into DRA-GRC and diagnostics."""

    validate_suite(suite)
    validate_world_index(world)
    if not ledger.complete:
        return {
            "status": "invalid_run",
            "task_id": suite.get("task_id"),
            "scoring_semantics": SCORING_SEMANTICS,
            "reasons": ledger.withhold_reason_codes,
        }
    if judgment.get("schema") != JUDGMENT_SCHEMA:
        raise SandboxNativeScoringError(
            f"judgment schema must be {JUDGMENT_SCHEMA}"
        )
    seals = judgment.get("seals") or {}
    expected_seals = {
        "suite_sha256": canonical_sha256(suite),
        "world_sha256": canonical_sha256(world),
        "report_sha256": sha256(report.encode("utf-8")).hexdigest(),
        "ledger_sha256": canonical_sha256(ledger.to_dict()),
    }
    for key, expected in expected_seals.items():
        if seals.get(key) != expected:
            raise SandboxNativeScoringError(f"judgment {key} mismatch")

    checks = _all_checks(suite)
    check_map = {str(check["check_id"]): check for check in checks}
    judgment_map = _judgment_checks(judgment)
    if set(judgment_map) != set(check_map):
        raise SandboxNativeScoringError("judgment check set mismatch")

    registry, pages, spans, _ = _world_maps(world)
    contracts = _suite_contracts(suite)
    observed = _observed_pages(ledger)
    certificate_results = _search_certificate_results(suite, ledger, observed)
    citations = extract_citations(report, sandbox_only=False)
    cited_urls = sorted({citation.canonical_url for citation in citations})

    audit_rows: dict[str, str] = {}
    for raw in judgment.get("url_audits") or []:
        if not isinstance(raw, Mapping):
            raise SandboxNativeScoringError("url_audits rows must be objects")
        url = _canonical(raw.get("url"))
        status = str(raw.get("status") or "")
        if not url or url in audit_rows or status not in URL_AUDIT_STATUSES:
            raise SandboxNativeScoringError("invalid or duplicate URL audit")
        audit_rows[url] = status

    off_registry = sorted(set(cited_urls) - registry)
    url_diagnostics: list[dict[str, Any]] = []
    pending_urls: list[str] = []
    for url in off_registry:
        status = audit_rows.get(url, "unadjudicated_off_registry")
        if status == "unadjudicated_off_registry":
            pending_urls.append(url)
        url_diagnostics.append({"url": url, "status": status})
    fabricated_urls = sorted(
        row["url"]
        for row in url_diagnostics
        if row["status"] == "nonexistent_fabricated"
    )
    real_off_world_urls = sorted(
        row["url"] for row in url_diagnostics if row["status"] == "real_off_world"
    )
    repair_urls = sorted(
        row["url"]
        for row in url_diagnostics
        if row["status"] == "registry_alias_error"
    )

    content_values: dict[str, bool] = {}
    grounded_values: dict[str, bool] = {}
    pending_checks: set[str] = set()
    critical_errors: list[dict[str, Any]] = []
    check_results: list[dict[str, Any]] = []

    unresolved = set(check_map)
    while unresolved:
        progress = False
        for check_id in sorted(unresolved):
            check = check_map[check_id]
            deps = [str(value) for value in check.get("depends_on_checks") or []]
            if any(dep in unresolved for dep in deps):
                continue
            progress = True
            unresolved.remove(check_id)
            row = judgment_map[check_id]
            content = row.get("content") or {}
            verdict = str(content.get("verdict") or "")
            if verdict not in CONTENT_VERDICTS:
                raise SandboxNativeScoringError(
                    f"{check_id}: invalid content verdict {verdict!r}"
                )
            content_span = _exact_report_span(report, content)
            content_pass = verdict == "satisfied" and content_span is not None
            if verdict == "ambiguous":
                pending_checks.add(check_id)
            if verdict == "contradicted" and check.get("critical_error_on_contradiction"):
                critical_errors.append(
                    {"check_id": check_id, "type": "contradicted_content"}
                )

            route_rows = {
                str(route.get("route_id") or ""): route
                for route in row.get("route_attempts") or []
                if isinstance(route, Mapping)
            }
            route_results: list[dict[str, Any]] = []
            evidence_pass = bool(check.get("evidence_exempt"))
            for route in check.get("evidence_routes") or []:
                route_id = str(route["route_id"])
                attempted = route_id in route_rows
                attempt = route_rows.get(route_id) or {}
                coherence = str(
                    attempt.get("coherence_verdict")
                    or ("ambiguous" if attempted else "incoherent")
                )
                conflict = str(
                    attempt.get("conflict_verdict")
                    or ("ambiguous" if attempted else "not_material")
                )
                if coherence not in COHERENCE_VERDICTS:
                    raise SandboxNativeScoringError(
                        f"{check_id}/{route_id}: invalid coherence verdict"
                    )
                if conflict not in CONFLICT_VERDICTS:
                    raise SandboxNativeScoringError(
                        f"{check_id}/{route_id}: invalid conflict verdict"
                    )
                if attempted and (coherence == "ambiguous" or conflict == "ambiguous"):
                    pending_checks.add(check_id)
                premise_rows = {
                    str(premise.get("premise_id") or ""): premise
                    for premise in attempt.get("premises") or []
                    if isinstance(premise, Mapping)
                }
                premise_results: list[dict[str, Any]] = []
                for premise in route["premises"]:
                    premise_id = str(premise["premise_id"])
                    judged = premise_rows.get(premise_id) or {}
                    binding_results: list[dict[str, Any]] = []
                    if premise.get("kind", "evidence") == "search_certificate":
                        for binding in judged.get("bindings") or []:
                            binding_results.append(
                                _search_binding_result(
                                    binding=binding,
                                    certificate_id=str(premise["certificate_id"]),
                                    certificate_results=certificate_results,
                                    report=report,
                                    citations=citations,
                                    registry=registry,
                                    observed=observed,
                                    window=int(premise.get("binding_window_chars", 1600)),
                                )
                            )
                    else:
                        contract = contracts[str(premise["contract_id"])]
                        for binding in judged.get("bindings") or []:
                            result = _binding_result(
                                binding=binding,
                                contract=contract,
                                report=report,
                                citations=citations,
                                registry=registry,
                                pages=pages,
                                spans=spans,
                                observed=observed,
                            )
                            binding_results.append(result)
                            support_verdict = result["support_verdict"]
                            if support_verdict == "ambiguous":
                                pending_checks.add(check_id)
                            if (
                                support_verdict == "contradicted"
                                and check.get("critical_error_on_contradiction")
                            ):
                                critical_errors.append(
                                    {
                                        "check_id": check_id,
                                        "premise_id": premise_id,
                                        "type": "contradicted_citation",
                                        "url": result["url"],
                                    }
                                )
                    premise_results.append(
                        {
                            "premise_id": premise_id,
                            "passed": any(result["verified"] for result in binding_results),
                            "bindings": binding_results,
                        }
                    )
                coherent = coherence == "coherent"
                conflict_ok = conflict in {"not_material", "resolved"}
                route_pass = coherent and conflict_ok and all(
                    result["passed"] for result in premise_results
                )
                evidence_pass = evidence_pass or route_pass
                route_results.append(
                    {
                        "route_id": route_id,
                        "passed": route_pass,
                        "coherence_verdict": coherence,
                        "conflict_verdict": conflict,
                        "premises": premise_results,
                    }
                )

            dependency_pass = all(grounded_values.get(dep, False) for dep in deps)
            applicable = check.get("applicable") is True
            grounded_pass = (
                applicable and content_pass and evidence_pass and dependency_pass
            )
            content_values[check_id] = applicable and content_pass
            grounded_values[check_id] = grounded_pass
            check_results.append(
                {
                    "check_id": check_id,
                    "facet_id": check["facet_id"],
                    "unit_id": check["unit_id"],
                    "content_pass": content_values[check_id],
                    "evidence_pass": evidence_pass,
                    "dependency_pass": dependency_pass,
                    "grounded_pass": grounded_pass,
                    "content_verdict": verdict,
                    "depends_on_checks": deps,
                    "routes": route_results,
                }
            )
        if not progress:
            raise SandboxNativeScoringError("could not resolve check dependency order")

    raw_grc, grounded_facets = _macro_score(suite, grounded_values)
    content_breadth, content_facets = _macro_score(suite, content_values)
    core_check_ids = [
        str(check["check_id"])
        for check in checks
        if check.get("applicable") is True and check.get("tier", "core") == "core"
    ]
    output_contract_pass = judgment.get("output_contract", {}).get("verdict") == "satisfied"
    full_pass = int(
        all(grounded_values.get(check_id, False) for check_id in core_check_ids)
        and output_contract_pass
        and not critical_errors
        and not fabricated_urls
        and not pending_checks
        and not pending_urls
        and not repair_urls
    )

    repair_triggered = bool(repair_urls)
    if repair_triggered or pending_urls or pending_checks:
        official_grc: float | None = None
    elif fabricated_urls:
        official_grc = 0.0
    else:
        official_grc = raw_grc

    binding_failures: list[dict[str, Any]] = []
    for check in check_results:
        for route in check["routes"]:
            for premise in route["premises"]:
                for binding in premise["bindings"]:
                    if binding["verified"]:
                        continue
                    binding_failures.append(
                        {
                            "check_id": check["check_id"],
                            "route_id": route["route_id"],
                            "premise_id": premise["premise_id"],
                            "url": binding.get("url"),
                            "support_verdict": binding.get("support_verdict"),
                            "reason_codes": binding.get("reason_codes") or [],
                        }
                    )

    citation_failure_taxonomy: list[dict[str, Any]] = []
    for failure in binding_failures:
        reasons = set(failure.get("reason_codes") or [])
        verdict = failure.get("support_verdict")
        categories: set[str] = set()
        if "observed" in reasons:
            categories.add("unobserved_citation")
        elif "evidence_quote_observed" in reasons:
            categories.add("delivered_span_missing")
        if "locally_bound" in reasons or verdict == "wrong_binding":
            categories.add("wrong_binding")
        if verdict == "unsupported":
            categories.add("unsupported_citation")
        if verdict == "contradicted":
            categories.add("contradicted_citation")
        if "source_role_valid" in reasons:
            categories.add("wrong_source_role")
        if "url_registered" in reasons:
            categories.add("unregistered_evidence")
        if "support_asset_valid" in reasons:
            categories.add("uncertified_evidence_span")
        for category in sorted(categories):
            citation_failure_taxonomy.append(
                {
                    "category": category,
                    "check_id": failure["check_id"],
                    "route_id": failure["route_id"],
                    "premise_id": failure["premise_id"],
                    "url": failure.get("url"),
                }
            )
    failure_counts: dict[str, int] = defaultdict(int)
    for row in citation_failure_taxonomy:
        failure_counts[row["category"]] += 1

    observed_urls = set(observed)
    cited_registry_urls = sorted(set(cited_urls) & registry)
    unobserved_citations = sorted(set(cited_registry_urls) - observed_urls)
    formal_eligible = bool(judgment.get("evaluator", {}).get("formal_eligible"))
    formal_eligible = formal_eligible and official_grc is not None and not repair_triggered

    return {
        "status": "repair_triggered" if repair_triggered else "scored",
        "task_id": suite["task_id"],
        "scoring_semantics": SCORING_SEMANTICS,
        "raw_grc": raw_grc,
        "official_grc": official_grc,
        "content_breadth": content_breadth,
        "unsupported_breadth_gap": content_breadth - raw_grc,
        "full_pass": full_pass,
        "passed_checks": sum(grounded_values.values()),
        "applicable_checks": len(core_check_ids),
        "content_passed_checks": sum(content_values.values()),
        "facet_scores": grounded_facets,
        "content_facet_scores": content_facets,
        "check_results": sorted(check_results, key=lambda row: row["check_id"]),
        "integrity": {
            "cited_urls": cited_urls,
            "fabricated_urls": fabricated_urls,
            "real_off_world_urls": real_off_world_urls,
            "unadjudicated_off_registry_urls": pending_urls,
            "registry_alias_error_urls": repair_urls,
            "unobserved_citations": unobserved_citations,
            "url_diagnostics": url_diagnostics,
            "binding_failures": binding_failures,
            "citation_failure_taxonomy": citation_failure_taxonomy,
            "failure_counts": dict(sorted(failure_counts.items())),
            "critical_errors": critical_errors,
        },
        "search_certificates": certificate_results,
        "pending_checks": sorted(pending_checks),
        "output_contract_pass": output_contract_pass,
        "formal_eligible": formal_eligible,
        "seals": expected_seals,
    }
