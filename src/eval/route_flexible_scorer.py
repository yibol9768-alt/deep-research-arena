"""Route-flexible grounded-obligation scorer.

The scorer is deterministic once a sealed semantic judgment artifact exists.
The LLM may judge report semantics and page entailment, but it cannot waive URL
registry, observation, citation-binding, source-role, or dependency gates.
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


RUBRIC_SCHEMA = "route_flexible_rubric_v1"
JUDGMENT_SCHEMA = "route_flexible_judgment_v1"
SCORING_SEMANTICS = "route_flexible_grounded_obligations_v1"


class RouteFlexibleScoringError(ValueError):
    """Raised when a pilot artifact cannot be replayed safely."""


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def validate_rubric(rubric: Mapping[str, Any]) -> None:
    if rubric.get("schema") != RUBRIC_SCHEMA:
        raise RouteFlexibleScoringError(f"rubric schema must be {RUBRIC_SCHEMA}")
    if rubric.get("scoring_semantics") != SCORING_SEMANTICS:
        raise RouteFlexibleScoringError(
            f"rubric scoring_semantics must be {SCORING_SEMANTICS}"
        )
    targets = rubric.get("targets")
    obligations = rubric.get("obligations")
    if not isinstance(targets, list) or not targets:
        raise RouteFlexibleScoringError("rubric targets must be a non-empty list")
    if not isinstance(obligations, list) or not obligations:
        raise RouteFlexibleScoringError("rubric obligations must be a non-empty list")
    target_ids = [str(target.get("target_id") or "") for target in targets]
    if any(not value for value in target_ids) or len(set(target_ids)) != len(target_ids):
        raise RouteFlexibleScoringError("target IDs must be non-empty and unique")
    target_map = {str(target["target_id"]): target for target in targets}
    for target_id, target in target_map.items():
        if target.get("kind") not in {"evidence", "analysis"}:
            raise RouteFlexibleScoringError(f"{target_id}: invalid target kind")
        if not str(target.get("statement") or "").strip():
            raise RouteFlexibleScoringError(f"{target_id}: statement is required")
        if target.get("kind") == "evidence":
            roles = target.get("acceptable_source_roles")
            if not isinstance(roles, list) or not roles:
                raise RouteFlexibleScoringError(
                    f"{target_id}: evidence target needs acceptable_source_roles"
                )
            if target.get("support_mode") not in {"body", "closed_page_absence"}:
                raise RouteFlexibleScoringError(f"{target_id}: invalid support_mode")
            window = target.get("citation_binding_window_chars")
            if type(window) is not int or not 100 <= window <= 4000:
                raise RouteFlexibleScoringError(
                    f"{target_id}: citation binding window must be in [100, 4000]"
                )
            witnesses = target.get("known_witnesses")
            if not isinstance(witnesses, list) or not witnesses:
                raise RouteFlexibleScoringError(
                    f"{target_id}: known_witnesses are required for answerability"
                )

    certificate_ids = {
        str(cert.get("certificate_id") or "")
        for cert in rubric.get("certificates") or []
        if isinstance(cert, Mapping)
    }
    obligation_ids: list[str] = []
    seen_obligations: set[str] = set()
    for obligation in obligations:
        obligation_id = str(obligation.get("obligation_id") or "")
        if not obligation_id or obligation_id in seen_obligations:
            raise RouteFlexibleScoringError(
                "obligation IDs must be non-empty and unique"
            )
        weight = obligation.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
            raise RouteFlexibleScoringError(f"{obligation_id}: weight must be positive")
        routes = obligation.get("routes")
        if not isinstance(routes, list) or not routes:
            raise RouteFlexibleScoringError(f"{obligation_id}: routes are required")
        for route in routes:
            required_targets = set(route.get("requires_targets") or [])
            unknown_targets = sorted(required_targets - set(target_map))
            if unknown_targets:
                raise RouteFlexibleScoringError(
                    f"{obligation_id}: unknown targets {unknown_targets}"
                )
            unknown_certificates = sorted(
                set(route.get("requires_certificates") or []) - certificate_ids
            )
            if unknown_certificates:
                raise RouteFlexibleScoringError(
                    f"{obligation_id}: unknown certificates {unknown_certificates}"
                )
            prerequisite_ids = set(route.get("requires_obligations") or [])
            unknown_or_forward = sorted(prerequisite_ids - seen_obligations)
            if unknown_or_forward:
                raise RouteFlexibleScoringError(
                    f"{obligation_id}: prerequisites must refer to earlier obligations: "
                    f"{unknown_or_forward}"
                )
        seen_obligations.add(obligation_id)
        obligation_ids.append(obligation_id)


def _result_index(judgment: Mapping[str, Any], field: str) -> dict[str, dict[str, Any]]:
    rows = judgment.get(field)
    if not isinstance(rows, list):
        raise RouteFlexibleScoringError(f"judgment {field} must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise RouteFlexibleScoringError(f"judgment {field} rows must be objects")
        target_id = str(row.get("target_id") or "")
        if not target_id or target_id in result:
            raise RouteFlexibleScoringError(
                f"judgment {field} target IDs must be present and unique"
            )
        result[target_id] = dict(row)
    return result


def _citation_role(url: str, role_hosts: Mapping[str, Any]) -> str | None:
    host = urlsplit(url).netloc.lower()
    for role, hosts in role_hosts.items():
        if host in {str(value).lower() for value in hosts or []}:
            return str(role)
    return None


def _observed_bodies(ledger: ObservationLedger) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
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
        out[event.canonical_url].append(
            {
                "event_id": event.event_id,
                "content_sha256": event.content_sha256,
                "body": body,
            }
        )
    return out


def _bound_citations(report: str, row: Mapping[str, Any], window: int):
    start = row.get("start")
    end = row.get("end")
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(report):
        return []
    return [
        citation
        for citation in extract_citations(report, sandbox_only=False)
        if start - window <= citation.char_offset <= end + window
    ]


def _certificate_results(
    rubric: Mapping[str, Any], ledger: ObservationLedger
) -> dict[str, dict[str, Any]]:
    bodies = _observed_bodies(ledger)
    by_query: dict[str, set[str]] = defaultdict(set)
    for event in ledger.events:
        if event.event_type != "search_result":
            continue
        query = str(event.metadata.get("query") or "").strip()
        if query:
            by_query[query].add(event.canonical_url)
    results: dict[str, dict[str, Any]] = {}
    for cert in rubric.get("certificates") or []:
        cert_id = str(cert["certificate_id"])
        matches: list[dict[str, Any]] = []
        for query, urls in by_query.items():
            low = " ".join(query.casefold().split())
            if len(query) > int(cert.get("max_query_chars", 240)):
                continue
            entity_ok = all(
                any(str(term).casefold() in low for term in alternatives)
                for alternatives in cert.get("required_entity_groups") or []
            )
            topic_ok = all(
                any(str(term).casefold() in low for term in alternatives)
                for alternatives in cert.get("required_topic_groups") or []
            )
            if not entity_ok or not topic_ok:
                continue
            missing_observations = sorted(url for url in urls if url not in bodies)
            observed_ok = not missing_observations
            matches.append(
                {
                    "query": query,
                    "returned_urls": sorted(urls),
                    "missing_observed_urls": missing_observations,
                    "all_returned_results_observed": observed_ok,
                }
            )
        passed = bool(matches) and (
            not cert.get("require_all_returned_results_observed")
            or any(match["all_returned_results_observed"] for match in matches)
        )
        results[cert_id] = {
            "certificate_id": cert_id,
            "passed": passed,
            "scope_label": cert.get("scope_label"),
            "matching_queries": matches,
            "reason_code": (
                "scoped_negative_search_replayable"
                if passed
                else "scoped_negative_search_not_replayable"
            ),
        }
    return results


def score_route_flexible(
    rubric: Mapping[str, Any],
    case: Mapping[str, Any],
    report: str,
    ledger: ObservationLedger,
    judgment: Mapping[str, Any],
) -> dict[str, Any]:
    validate_rubric(rubric)
    if not ledger.complete:
        return {
            "status": "withheld",
            "withheld": True,
            "withhold_reasons": ledger.withhold_reason_codes,
            "task_id": rubric.get("task_id"),
            "scoring_semantics": SCORING_SEMANTICS,
        }
    if judgment.get("schema") != JUDGMENT_SCHEMA:
        raise RouteFlexibleScoringError(f"judgment schema must be {JUDGMENT_SCHEMA}")
    if judgment.get("rubric_sha256") != canonical_sha256(rubric):
        raise RouteFlexibleScoringError("judgment rubric SHA-256 mismatch")
    if judgment.get("report_sha256") != sha256(report.encode("utf-8")).hexdigest():
        raise RouteFlexibleScoringError("judgment report SHA-256 mismatch")

    report_rows = _result_index(judgment, "report_results")
    expected_targets = {str(row["target_id"]) for row in rubric["targets"]}
    if set(report_rows) != expected_targets:
        raise RouteFlexibleScoringError("judgment report target set mismatch")
    evidence_rows = judgment.get("evidence_results")
    if not isinstance(evidence_rows, list):
        raise RouteFlexibleScoringError("judgment evidence_results must be a list")
    evidence_index = {
        (str(row.get("target_id")), canonicalize_url(str(row.get("citation_url") or ""))): row
        for row in evidence_rows
        if isinstance(row, Mapping) and row.get("target_id") and row.get("citation_url")
    }

    registry = {
        canonicalize_url(str(url)) for url in case.get("corpus_registry_urls") or []
    }
    citations = extract_citations(report, sandbox_only=False)
    cited_urls = sorted({citation.canonical_url for citation in citations})
    fabricated_urls = sorted(set(cited_urls) - registry)
    observed = _observed_bodies(ledger)
    role_hosts = rubric.get("source_role_hosts") or {}
    target_results: list[dict[str, Any]] = []
    content_by_target: dict[str, bool] = {}
    grounded_by_target: dict[str, bool] = {}
    for target in rubric["targets"]:
        target_id = str(target["target_id"])
        row = report_rows[target_id]
        content_pass = row.get("verdict") == "satisfied"
        content_by_target[target_id] = content_pass
        if target["kind"] == "analysis":
            grounded_pass = content_pass
            binding_rows: list[dict[str, Any]] = []
        else:
            binding_rows = []
            window = int(target["citation_binding_window_chars"])
            for citation in _bound_citations(report, row, window):
                url = citation.canonical_url
                role = _citation_role(url, role_hosts)
                page_row = evidence_index.get((target_id, url))
                reasons = {
                    "url_registered": url in registry,
                    "source_role_valid": role in set(target["acceptable_source_roles"]),
                    "content_observed": url in observed,
                    "page_support": bool(page_row and page_row.get("verdict") == "supported"),
                }
                binding_rows.append(
                    {
                        "citation_url": url,
                        "citation_offset": citation.char_offset,
                        "citation_style": citation.style,
                        "source_role": role,
                        "checks": reasons,
                        "verified": content_pass and all(reasons.values()),
                    }
                )
            grounded_pass = content_pass and any(
                binding["verified"] for binding in binding_rows
            )
        grounded_by_target[target_id] = grounded_pass
        reason_codes: list[str] = []
        if not content_pass:
            reason_codes.append(str(row.get("verdict") or "semantic_target_failed"))
        elif target["kind"] == "evidence" and not binding_rows:
            reason_codes.append("no_locally_bound_citation")
        elif target["kind"] == "evidence" and not grounded_pass:
            reason_codes.append("no_verified_support_binding")
        target_results.append(
            {
                "target_id": target_id,
                "kind": target["kind"],
                "content_pass": content_pass,
                "grounded_pass": grounded_pass,
                "verdict": row.get("verdict"),
                "matched_quote": row.get("matched_quote"),
                "reason": row.get("reason"),
                "bindings": binding_rows,
                "reason_codes": reason_codes,
            }
        )

    certificates = _certificate_results(rubric, ledger)
    content_obligations: dict[str, bool] = {}
    grounded_obligations: dict[str, bool] = {}
    obligation_results: list[dict[str, Any]] = []
    for obligation in rubric["obligations"]:
        obligation_id = str(obligation["obligation_id"])
        route_rows: list[dict[str, Any]] = []
        for route in obligation["routes"]:
            target_ids = [str(value) for value in route.get("requires_targets") or []]
            prerequisite_ids = [
                str(value) for value in route.get("requires_obligations") or []
            ]
            certificate_ids = [
                str(value) for value in route.get("requires_certificates") or []
            ]
            content_pass = all(content_by_target[target] for target in target_ids) and all(
                content_obligations[value] for value in prerequisite_ids
            )
            grounded_pass = (
                all(grounded_by_target[target] for target in target_ids)
                and all(grounded_obligations[value] for value in prerequisite_ids)
                and all(certificates[value]["passed"] for value in certificate_ids)
            )
            route_rows.append(
                {
                    "route_id": route.get("route_id"),
                    "content_pass": content_pass,
                    "grounded_pass": grounded_pass,
                    "failed_content_targets": [
                        target for target in target_ids if not content_by_target[target]
                    ],
                    "failed_grounded_targets": [
                        target for target in target_ids if not grounded_by_target[target]
                    ],
                    "failed_content_obligations": [
                        value for value in prerequisite_ids if not content_obligations[value]
                    ],
                    "failed_grounded_obligations": [
                        value for value in prerequisite_ids if not grounded_obligations[value]
                    ],
                    "failed_certificates": [
                        value for value in certificate_ids if not certificates[value]["passed"]
                    ],
                }
            )
        content_pass = any(route["content_pass"] for route in route_rows)
        grounded_pass = any(route["grounded_pass"] for route in route_rows)
        content_obligations[obligation_id] = content_pass
        grounded_obligations[obligation_id] = grounded_pass
        obligation_results.append(
            {
                "obligation_id": obligation_id,
                "description": obligation.get("description"),
                "weight": obligation["weight"],
                "critical": obligation.get("critical") is True,
                "content_pass": content_pass,
                "grounded_pass": grounded_pass,
                "routes": route_rows,
            }
        )

    weight_total = sum(float(row["weight"]) for row in obligation_results)
    content_completion = sum(
        float(row["weight"]) for row in obligation_results if row["content_pass"]
    ) / weight_total
    grounded_completion = sum(
        float(row["weight"]) for row in obligation_results if row["grounded_pass"]
    ) / weight_total
    critical_pass = all(
        row["grounded_pass"] for row in obligation_results if row["critical"]
    )
    contradicted_targets = sorted(
        target_id
        for target_id, row in report_rows.items()
        if row.get("verdict") == "contradicted"
    )
    contract = rubric.get("full_pass_contract") or {}
    full_pass = (
        critical_pass
        and (not contract.get("forbid_fabricated_citations") or not fabricated_urls)
        and (not contract.get("forbid_contradicted_targets") or not contradicted_targets)
    )
    judge_metadata = dict(judgment.get("judge") or {})
    formal_eligible = judge_metadata.get("formal_eligible") is not False
    return {
        "status": "scored",
        "withheld": False,
        "formal_eligible": formal_eligible,
        "leaderboard_eligible": formal_eligible,
        "judge": judge_metadata,
        "task_id": rubric.get("task_id"),
        "scoring_semantics": SCORING_SEMANTICS,
        "rubric_sha256": canonical_sha256(rubric),
        "report_sha256": sha256(report.encode("utf-8")).hexdigest(),
        "run_id": ledger.run_id,
        "report_content_completion": content_completion,
        "grounded_obligation_completion": grounded_completion,
        "full_pass": int(full_pass),
        "passed_content_obligations": sum(row["content_pass"] for row in obligation_results),
        "passed_grounded_obligations": sum(row["grounded_pass"] for row in obligation_results),
        "required_obligations": len(obligation_results),
        "contradicted_targets": contradicted_targets,
        "url_integrity": {
            "cited_urls": cited_urls,
            "fabricated_urls": fabricated_urls,
            "fabricated_url_count": len(fabricated_urls),
            "observed_cited_urls": sorted(set(cited_urls) & set(observed)),
            "unobserved_cited_urls": sorted(set(cited_urls) - set(observed)),
        },
        "certificate_results": list(certificates.values()),
        "target_results": target_results,
        "obligation_results": obligation_results,
    }


__all__ = [
    "JUDGMENT_SCHEMA",
    "RUBRIC_SCHEMA",
    "SCORING_SEMANTICS",
    "RouteFlexibleScoringError",
    "canonical_sha256",
    "score_route_flexible",
    "validate_rubric",
]
