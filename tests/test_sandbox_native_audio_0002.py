from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from src.eval.observation_ledger import load_observation_ledger
from src.eval.sandbox_native_grc import score_grounded_research_coverage


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/pilot_v33/dra_v3_dev_audio_0002"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _replay(name: str):
    suite = _json(BASE / "research-test-suite.json")
    world = _json(BASE / "world-index.json")
    report = (BASE / "controlled/reports" / f"{name}.md").read_text(
        encoding="utf-8"
    )
    ledger = load_observation_ledger(BASE / "controlled/ledgers" / f"{name}.json")
    judgment = _json(BASE / "controlled/judgments" / f"{name}.json")
    return score_grounded_research_coverage(
        suite=suite,
        world=world,
        report=report,
        ledger=ledger,
        judgment=judgment,
    )


def _check(result, check_id: str):
    return next(row for row in result["check_results"] if row["check_id"] == check_id)


def test_compiled_suite_has_balanced_hierarchy_and_no_url_allowlist() -> None:
    suite = _json(BASE / "research-test-suite.json")
    facets = suite["facets"]
    units = [unit for facet in facets for unit in facet["units"]]
    checks = [check for unit in units for check in unit["checks"]]
    assert len(facets) == 5
    assert len(units) == 8
    assert len(checks) == 25
    assert all(2 <= len(unit["checks"]) <= 5 for unit in units)
    assert all(
        contract["known_witnesses_are_allowlist"] is False
        for contract in suite["evidence_contracts"]
    )
    assert "acceptable_conclusions" not in json.dumps(suite)


def test_reference_and_bounded_search_routes_are_equivalent() -> None:
    reference = _replay("oracle_reference")
    alternative = _replay("oracle_alternative")
    assert reference["raw_grc"] == alternative["raw_grc"] == 1.0
    assert reference["full_pass"] == alternative["full_pass"] == 1
    community = _check(alternative, "K_COMMUNITY_EVIDENCE")
    assert next(route for route in community["routes"] if route["passed"])[
        "route_id"
    ] == "bounded_search"


def test_null_url_dump_and_fluent_unsupported_have_zero_grc() -> None:
    null = _replay("null")
    url_dump = _replay("url_dump")
    fluent = _replay("fluent_unsupported")
    assert null["raw_grc"] == 0.0
    assert url_dump["raw_grc"] == 0.0
    assert fluent["content_breadth"] == 1.0
    assert fluent["raw_grc"] == 0.0


def test_frankenstein_cannot_mix_partial_routes() -> None:
    result = _replay("frankenstein")
    comparison = _check(result, "K_DISTORTION_COMPARISON")
    assert comparison["content_pass"] is True
    assert comparison["evidence_pass"] is False
    assert not any(route["passed"] for route in comparison["routes"])
    assert result["full_pass"] == 0


def test_unobserved_and_wrong_binding_fail_locally() -> None:
    unobserved = _replay("unobserved_ipx7")
    assert _check(unobserved, "K_IPX7_SCOPE")["grounded_pass"] is False
    assert _check(unobserved, "K_PRICE_FLARE")["grounded_pass"] is True
    assert (
        "http://localhost:8090/content/wikipedia_en_all_nopic/IP_code"
        in unobserved["integrity"]["unobserved_citations"]
    )
    assert unobserved["integrity"]["failure_counts"]["unobserved_citation"] >= 1

    wrong = _replay("wrong_binding")
    watt = _check(wrong, "K_WATT_CONTEXT")
    assert watt["content_pass"] is True
    assert watt["grounded_pass"] is False
    failures = wrong["integrity"]["binding_failures"]
    assert any(
        row["check_id"] == "K_WATT_CONTEXT"
        and row["support_verdict"] == "wrong_binding"
        for row in failures
    )
    assert wrong["integrity"]["failure_counts"]["wrong_binding"] >= 1


def test_fabricated_and_real_off_world_urls_are_not_conflated() -> None:
    fabricated = _replay("fabricated_url")
    assert fabricated["raw_grc"] == 1.0
    assert fabricated["official_grc"] == 0.0
    assert fabricated["integrity"]["fabricated_urls"] == [
        "http://localhost:7770/not-a-real-speaker.html"
    ]

    off_world = _replay("real_off_world_only")
    assert off_world["integrity"]["fabricated_urls"] == []
    assert off_world["integrity"]["real_off_world_urls"] == [
        "https://example.com/audio-power"
    ]
    assert off_world["official_grc"] == off_world["raw_grc"] < 1.0


def test_contradicted_citation_is_a_critical_error() -> None:
    result = _replay("contradicted_citation")
    assert result["full_pass"] == 0
    assert any(
        row["type"] == "contradicted_citation"
        and row["check_id"] == "K_IPX7_SCOPE"
        for row in result["integrity"]["critical_errors"]
    )
    assert result["integrity"]["failure_counts"]["contradicted_citation"] >= 1


def test_real_report_replays_as_partial_and_ineligible() -> None:
    suite = _json(BASE / "research-test-suite.json")
    world = _json(BASE / "world-index.json")
    report = (BASE / "real_run/report.md").read_text(encoding="utf-8")
    ledger = load_observation_ledger(BASE / "real_run/observation-ledger-projection.json")
    judgment = _json(BASE / "real_run/judgment-manual.json")
    result = score_grounded_research_coverage(
        suite=suite,
        world=world,
        report=report,
        ledger=ledger,
        judgment=judgment,
    )
    assert result["passed_checks"] == 6
    assert result["applicable_checks"] == 25
    assert result["raw_grc"] == 0.19166666666666665
    assert result["content_breadth"] == 0.6333333333333333
    assert result["full_pass"] == 0
    assert result["formal_eligible"] is False
    assert result["integrity"]["fabricated_urls"] == []


def test_experiment_summary_has_no_pending_controlled_case() -> None:
    summary = _json(BASE / "experiment-summary.json")
    assert summary["all_release_gates_passed"] is True
    assert all(summary["release_gates"].values())
    assert all(
        row["pending_checks"] == 0
        for row in summary["controlled_scenarios"].values()
    )


def test_public_replay_cli_scores_without_network() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/score_sandbox_native_grc.py"),
            "--suite",
            str(BASE / "research-test-suite.json"),
            "--world",
            str(BASE / "world-index.json"),
            "--report",
            str(BASE / "controlled/reports/oracle_alternative.md"),
            "--ledger",
            str(BASE / "controlled/ledgers/oracle_alternative.json"),
            "--judgment",
            str(BASE / "controlled/judgments/oracle_alternative.json"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["raw_grc"] == 1.0
    assert result["full_pass"] == 1
