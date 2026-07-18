from __future__ import annotations

import hashlib

from src.eval.observation_ledger import ObservationLedger
from src.eval.route_flexible_scorer import canonical_sha256, score_route_flexible


ALT_URL = "http://localhost:7770/alternative-source.html"
WITNESS_URL = "http://localhost:7770/original-witness.html"


def _rubric(*, alternative_route: bool = False):
    routes = [{"route_id": "route_a", "requires_targets": ["E1"]}]
    if alternative_route:
        routes.append({"route_id": "route_b", "requires_targets": ["E2"]})
    return {
        "schema": "route_flexible_rubric_v1",
        "task_id": "dra_v3_dev_test_9999",
        "scoring_semantics": "route_flexible_grounded_obligations_v1",
        "source_role_hosts": {"product": ["localhost:7770"]},
        "targets": [
            {
                "target_id": "E1",
                "kind": "evidence",
                "statement": "Alpha costs ten dollars.",
                "acceptable_source_roles": ["product"],
                "support_mode": "body",
                "citation_binding_window_chars": 500,
                "known_witnesses": ["old_witness"],
            },
            {
                "target_id": "E2",
                "kind": "evidence",
                "statement": "Beta costs ten dollars.",
                "acceptable_source_roles": ["product"],
                "support_mode": "body",
                "citation_binding_window_chars": 500,
                "known_witnesses": ["another_old_witness"],
            },
        ],
        "obligations": [
            {
                "obligation_id": "O1",
                "description": "Resolve price through any admissible route.",
                "weight": 1,
                "critical": True,
                "routes": routes,
            }
        ],
        "full_pass_contract": {
            "require_all_critical_obligations": True,
            "forbid_fabricated_citations": True,
            "forbid_contradicted_targets": True,
        },
    }


def _ledger():
    body = "Alternative product page: Alpha costs ten dollars. Beta costs ten dollars."
    digest = hashlib.sha256(body.encode()).hexdigest()
    snippet = "Alternative product result"
    return ObservationLedger.from_records(
        [
            {
                "run_id": "run-1",
                "event_id": 1,
                "timestamp": 1.0,
                "event_type": "search_result",
                "request_url": "http://localhost:8081/search?q=alpha",
                "canonical_url": ALT_URL,
                "content_sha256": hashlib.sha256(snippet.encode()).hexdigest(),
                "content_text": snippet,
                "observable": True,
                "metadata": {"query": "alpha price"},
            },
            {
                "run_id": "run-1",
                "event_id": 2,
                "timestamp": 2.0,
                "event_type": "fetch_body",
                "request_url": ALT_URL,
                "canonical_url": ALT_URL,
                "content_sha256": digest,
                "content_text": body,
                "http_status": 200,
                "observable": True,
            },
        ],
        capture_complete=True,
    )


def _judgment(rubric, report, *, satisfied_target="E1"):
    rows = []
    for target in ("E1", "E2"):
        satisfied = target == satisfied_target
        quote = "Alpha costs ten dollars" if target == "E1" else "Beta costs ten dollars"
        start = report.find(quote) if satisfied else None
        rows.append(
            {
                "target_id": target,
                "verdict": "satisfied" if satisfied else "not_mentioned",
                "matched_quote": quote if satisfied else None,
                "start": start,
                "end": start + len(quote) if satisfied else None,
                "reason": "fixture",
            }
        )
    return {
        "schema": "route_flexible_judgment_v1",
        "rubric_sha256": canonical_sha256(rubric),
        "report_sha256": hashlib.sha256(report.encode()).hexdigest(),
        "judge": {"provider": "fixture", "formal_eligible": True},
        "report_results": rows,
        "evidence_results": [
            {
                "target_id": satisfied_target,
                "citation_url": ALT_URL,
                "verdict": "supported",
            }
        ],
    }


def test_alternative_observed_source_passes_without_matching_known_witness() -> None:
    rubric = _rubric()
    report = f"Alpha costs ten dollars [source]({ALT_URL})."
    case = {"corpus_registry_urls": [WITNESS_URL, ALT_URL]}
    result = score_route_flexible(
        rubric, case, report, _ledger(), _judgment(rubric, report)
    )
    assert result["grounded_obligation_completion"] == 1.0
    assert result["full_pass"] == 1
    assert result["leaderboard_eligible"] is True


def test_content_is_reported_separately_when_citation_is_missing() -> None:
    rubric = _rubric()
    report = "Alpha costs ten dollars."
    case = {"corpus_registry_urls": [WITNESS_URL, ALT_URL]}
    result = score_route_flexible(
        rubric, case, report, _ledger(), _judgment(rubric, report)
    )
    assert result["report_content_completion"] == 1.0
    assert result["grounded_obligation_completion"] == 0.0
    assert result["full_pass"] == 0


def test_second_route_can_pass_without_reproducing_first_route() -> None:
    rubric = _rubric(alternative_route=True)
    report = f"Beta costs ten dollars [source]({ALT_URL})."
    case = {"corpus_registry_urls": [WITNESS_URL, ALT_URL]}
    result = score_route_flexible(
        rubric,
        case,
        report,
        _ledger(),
        _judgment(rubric, report, satisfied_target="E2"),
    )
    assert result["obligation_results"][0]["routes"][0]["grounded_pass"] is False
    assert result["obligation_results"][0]["routes"][1]["grounded_pass"] is True
    assert result["full_pass"] == 1


def test_manual_pilot_score_is_machine_readably_ineligible_for_leaderboard() -> None:
    rubric = _rubric()
    report = f"Alpha costs ten dollars [source]({ALT_URL})."
    case = {"corpus_registry_urls": [WITNESS_URL, ALT_URL]}
    judgment = _judgment(rubric, report)
    judgment["judge"] = {
        "provider": "manual_adjudication",
        "formal_eligible": False,
    }
    result = score_route_flexible(rubric, case, report, _ledger(), judgment)
    assert result["full_pass"] == 1
    assert result["formal_eligible"] is False
    assert result["leaderboard_eligible"] is False
