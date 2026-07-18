from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from scripts.score_case_v3 import build_parser, main as score_cli
from src.eval.observation_ledger import ObservationLedger, sha256_text
from src.eval.slot_scorer import (
    ProofStepScorer,
    score_case,
    score_proof_steps,
)
from test_slot_scorer_v3 import (
    FABRICATED,
    BODY2,
    U2,
    _event,
    case as verified_slot_case,
    graph,
    ledger,
    oracle_report,
)


ALT_URL = "http://localhost:9999/products/alpha-equivalent"
ALT_CLAIM = "The equivalent page confirms thirty-hour Alpha endurance"
ALT_BODY = f"{ALT_CLAIM}."
UNRELATED_URL = "http://localhost:9999/products/unrelated-same-role"
UNRELATED_BODY = "An unrelated page also contains the words Alpha lasts 30 hours."


def _proof_case(*, include_non_vital_failure: bool = False) -> dict:
    payload = deepcopy(verified_slot_case())
    steps: list[dict] = []
    for legacy in payload["slots"]:
        step = deepcopy(legacy)
        step["step_id"] = step.pop("slot_id")
        step["vital"] = bool(step.pop("critical", True))
        step["required"] = True
        if step["type"] == "evidence":
            step["claim"] = step["claim_id"]
            step["acceptable_support"] = {
                "source_roles": ["mechanism"],
                "support_mode": "body",
                "condition_match": True,
            }
            step["provenance_contract"] = "discovery_then_visible_support"
        steps.append(step)
    if include_non_vital_failure:
        steps.append({
            "step_id": "E_non_vital",
            "type": "evidence",
            "required": True,
            "vital": False,
            "claim": "missing_diagnostic_claim",
            "claim_id": "missing_diagnostic_claim",
            "acceptable_support": {
                "source_roles": ["community"],
                "support_mode": "body",
                "condition_match": True,
            },
            "provenance_contract": "discovery_then_visible_support",
        })
    payload["scoring_semantics"] = "proof_steps_v1"
    payload["evaluator_view"] = {"required_proof_steps": steps}
    return payload


def _by_step(result: dict, step_id: str) -> dict:
    return next(
        row for row in result["step_results"] if row["step_id"] == step_id
    )


def test_default_scorer_remains_legacy_and_proof_entrypoint_is_explicit() -> None:
    legacy = score_case(
        verified_slot_case(), oracle_report(), ledger(), graph()
    )
    proof = score_proof_steps(
        _proof_case(), oracle_report(), ledger(), graph()
    )

    assert "slot_results" in legacy
    assert "step_results" not in legacy
    assert legacy["protocols"]["scoring_semantics"] == "verified_slots_v1"

    assert proof["scoring_semantics"] == "proof_steps_v1"
    assert proof["protocols"]["scoring_semantics"] == "proof_steps_v1"
    assert proof["passed_steps"] == proof["required_steps"] == 4
    assert proof["partial_completion"] == 1.0
    assert proof["full_pass"] == 1
    assert proof["final_answer_pass"] is True
    assert all(
        row["passed"] == all(row[axis] for axis in ("D", "O", "S", "B", "R"))
        for row in proof["step_results"]
    )
    # Draft migration output is clearly labelled; formal proof scores omit
    # these old aliases and the board rejects any that leak into formal rows.
    assert proof["legacy_compatibility_aliases"]["formal"] is False

    expected_identity = {
        "version": "dra_v3_scoring_input_v3",
        "run_id": proof["run_id"],
        "agent": None,
        "task_id": proof["task_id"],
        "replicate": None,
        "cluster_id": proof["cluster_id"],
        "report_sha256": proof["report_sha256"],
        "observation_ledger_sha256": proof["observation_ledger_sha256"],
        "case_artifact_sha256": None,
        "public_task_sha256": None,
        "protocol_manifest_sha256": None,
        "corpus_registry_hash": proof["corpus_registry_hash"],
    }
    assert proof["scoring_input_sha256"] == hashlib.sha256(
        json.dumps(
            expected_identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def test_legacy_node_precedence_is_unchanged_when_source_catalog_conflicts() -> None:
    graph_payload = graph()
    graph_payload["sources"] = {
        "ev1": {
            "evidence_id": "ev1",
            "source_url": ALT_URL,
            "content_sha256": sha256_text(ALT_BODY),
            "support_spans": [{"text": ALT_CLAIM}],
            "verifier": {
                "kind": "typed_claim",
                "accepted_phrases": [ALT_CLAIM],
            },
        }
    }

    case_payload = verified_slot_case()
    case_payload["corpus_registry_urls"].append(ALT_URL)
    result = score_case(
        case_payload,
        oracle_report(),
        ledger(),
        graph_payload,
    )
    e1 = next(row for row in result["slot_results"] if row["slot_id"] == "E1")

    assert e1["verified"] is True
    assert e1["citation_url"] == "http://localhost:9999/products/alpha"


def test_partial_is_exact_required_step_fraction_and_full_uses_hard_gates() -> None:
    partial = score_proof_steps(
        _proof_case(),
        oracle_report().replace(
            "Together these facts make Alpha suitable for travel. ", ""
        ),
        ledger(),
        graph(),
    )

    assert _by_step(partial, "E1")["passed"] is True
    assert _by_step(partial, "E2")["passed"] is True
    assert _by_step(partial, "B1")["passed"] is False
    assert _by_step(partial, "D1")["passed"] is False
    assert partial["passed_steps"] == 2
    assert partial["required_steps"] == 4
    assert partial["partial_completion"] == 0.5
    assert partial["full_pass"] == 0
    assert {
        reason["reason_code"]
        for reason in partial["full_pass_failure_reasons"]
    } == {"vital_proof_steps_failed", "final_answer_contract_failed"}


def test_non_vital_required_failure_lowers_partial_without_blocking_full() -> None:
    result = score_proof_steps(
        _proof_case(include_non_vital_failure=True),
        oracle_report(),
        ledger(),
        graph(),
    )

    assert _by_step(result, "E_non_vital")["passed"] is False
    assert result["partial_completion"] == pytest.approx(4 / 5)
    assert result["full_pass"] == 1
    assert result["full_pass_failure_reasons"] == []


def test_fabricated_citation_only_blocks_full_not_partial() -> None:
    clean = score_proof_steps(
        _proof_case(), oracle_report(), ledger(), graph()
    )
    contaminated = score_proof_steps(
        _proof_case(),
        oracle_report(f"\nExtra [fabricated]({FABRICATED})."),
        ledger(),
        graph(),
    )

    assert clean["partial_completion"] == contaminated["partial_completion"] == 1.0
    assert clean["full_pass"] == 1
    assert contaminated["full_pass"] == 0
    assert contaminated["fabricated_citations"] == 1
    assert contaminated["full_pass_failure_reasons"] == [{
        "reason_code": "fabricated_citations_present",
        "count": 1,
    }]


def _alternative_support_fixture() -> tuple[dict, dict]:
    payload = _proof_case()
    payload["corpus_registry_urls"].extend([ALT_URL, UNRELATED_URL])
    steps = payload["evaluator_view"]["required_proof_steps"]
    e1 = next(step for step in steps if step["step_id"] == "E1")
    e2 = next(step for step in steps if step["step_id"] == "E2")
    e1["acceptable_support"]["source_ids"] = ["ev1", "ev1_alt"]
    e2["acceptable_support"]["source_ids"] = ["ev2"]

    graph_payload = graph()
    graph_payload["nodes"]["ev1_alt"] = {
        "evidence_id": "ev1_alt",
        "subject": "Alpha",
        "predicate": "battery_life",
        "object": "30 hours",
        "source_url": ALT_URL,
        "source_type": "concept",
        "content_sha256": sha256_text(ALT_BODY),
        "support_spans": [{"text": ALT_CLAIM}],
        "verifier": {
            "kind": "typed_claim",
            "accepted_phrases": [ALT_CLAIM],
        },
    }
    unrelated = {
        "evidence_id": "ev_unrelated",
        "subject": "Alpha",
        "predicate": "unrelated",
        "object": True,
        "source_url": UNRELATED_URL,
        "source_type": "concept",
        "content_sha256": sha256_text(UNRELATED_BODY),
        "support_spans": [{"text": "Alpha lasts 30 hours"}],
        "verifier": {
            "kind": "typed_claim",
            "accepted_phrases": ["Alpha lasts 30 hours"],
        },
    }
    graph_payload["nodes"]["ev_unrelated"] = unrelated
    # Keep the unrelated record in the source catalog too.  Source-role
    # expansion would therefore make this test fail if it were reintroduced.
    graph_payload["sources"] = {"ev_unrelated": unrelated}
    return payload, graph_payload


def test_equivalent_support_page_uses_its_own_hash_span_and_verifier() -> None:
    payload, graph_payload = _alternative_support_fixture()
    observations = ObservationLedger.from_records(
        [
            _event(1, "search_result", ALT_URL, "equivalent Alpha result"),
            _event(2, "fetch_body", ALT_URL, ALT_BODY, status=200, parent=1),
            _event(3, "search_result", U2, "Cabin noise concept result"),
            _event(4, "fetch_body", U2, BODY2, status=200, parent=3),
        ],
        expected_run_id="run-v3",
        capture_complete=True,
    )
    report = (
        f"{ALT_CLAIM} [equivalent source]({ALT_URL}). "
        f"Cabin noise is low frequency [concept source]({U2}).\n\n"
        "Together these facts make Alpha suitable for travel. "
        "Noise control is the first priority. Therefore, I recommend Alpha."
    )

    result = score_proof_steps(payload, report, observations, graph_payload)
    e1 = _by_step(result, "E1")

    assert e1["passed"] is True
    assert e1["matched_support_source_id"] == "ev1_alt"
    assert e1["admissible_support_source_ids"] == ["ev1", "ev1_alt"]
    assert e1["expected_source_urls"] == sorted(
        [ALT_URL, "http://localhost:9999/products/alpha"]
    )
    assert result["full_pass"] == 1


def test_claim_match_from_one_alternative_cannot_be_spliced_to_another_url() -> None:
    payload, graph_payload = _alternative_support_fixture()
    observations = ObservationLedger.from_records(
        [
            _event(1, "search_result", ALT_URL, "equivalent Alpha result"),
            _event(2, "fetch_body", ALT_URL, ALT_BODY, status=200, parent=1),
            _event(3, "search_result", U2, "Cabin noise concept result"),
            _event(4, "fetch_body", U2, BODY2, status=200, parent=3),
        ],
        expected_run_id="run-v3",
        capture_complete=True,
    )
    report = (
        f"Alpha lasts 30 hours [mismatched alternative]({ALT_URL}). "
        f"Cabin noise is low frequency [concept source]({U2}).\n\n"
        "Together these facts make Alpha suitable for travel. "
        "Noise control is the first priority. Therefore, I recommend Alpha."
    )

    result = score_proof_steps(payload, report, observations, graph_payload)
    e1 = _by_step(result, "E1")

    assert e1["passed"] is False
    assert not (e1["S"] and e1["B"])
    assert result["full_pass"] == 0


def test_unbound_same_role_source_cannot_satisfy_proof_step() -> None:
    payload, graph_payload = _alternative_support_fixture()
    observations = ObservationLedger.from_records(
        [
            _event(1, "search_result", UNRELATED_URL, "unrelated result"),
            _event(
                2,
                "fetch_body",
                UNRELATED_URL,
                UNRELATED_BODY,
                status=200,
                parent=1,
            ),
            _event(3, "search_result", U2, "Cabin noise concept result"),
            _event(4, "fetch_body", U2, BODY2, status=200, parent=3),
        ],
        expected_run_id="run-v3",
        capture_complete=True,
    )
    report = (
        f"Alpha lasts 30 hours [wrong same-role page]({UNRELATED_URL}). "
        f"Cabin noise is low frequency [concept source]({U2}).\n\n"
        "Together these facts make Alpha suitable for travel. "
        "Noise control is the first priority. Therefore, I recommend Alpha."
    )

    result = score_proof_steps(payload, report, observations, graph_payload)
    e1 = _by_step(result, "E1")

    assert e1["passed"] is False
    assert e1["B"] is False
    assert e1["matched_support_source_id"] is None
    assert UNRELATED_URL not in e1["expected_source_urls"]
    assert result["full_pass"] == 0


def test_support_mode_separates_body_and_exact_snippet_observation() -> None:
    payload = _proof_case()
    e1 = next(
        step
        for step in payload["evaluator_view"]["required_proof_steps"]
        if step["step_id"] == "E1"
    )
    graph_payload = graph()
    graph_payload["nodes"]["ev1"]["search_snippet_support"] = True
    snippet_only = ObservationLedger.from_records(
        [
            _event(
                1,
                "search_result",
                "http://localhost:9999/products/alpha",
                "The frozen Alpha page says battery life is 30 hours.",
            ),
            _event(2, "search_result", U2, "Cabin noise concept result"),
            _event(3, "fetch_body", U2, BODY2, status=200, parent=2),
        ],
        expected_run_id="run-v3",
        capture_complete=True,
    )

    e1["acceptable_support"]["support_mode"] = "body"
    body_required = score_proof_steps(
        payload,
        oracle_report(),
        snippet_only,
        graph_payload,
    )
    assert _by_step(body_required, "E1")["S"] is False
    assert _by_step(body_required, "E1")["passed"] is False

    e1["acceptable_support"]["support_mode"] = "exact_snippet"
    snippet_allowed = score_proof_steps(
        payload,
        oracle_report(),
        snippet_only,
        graph_payload,
    )
    assert _by_step(snippet_allowed, "E1")["passed"] is True

    fetched = ledger()
    exact_snippet_required = score_proof_steps(
        payload,
        oracle_report(),
        fetched,
        graph_payload,
    )
    assert _by_step(exact_snippet_required, "E1")["S"] is False
    assert _by_step(exact_snippet_required, "E1")["passed"] is False


def test_proof_step_scorer_object_and_withhold_contract() -> None:
    scorer = ProofStepScorer(_proof_case(), graph())
    result = scorer.score(oracle_report(), ledger())
    assert result["full_pass"] == 1

    withheld = scorer.score(oracle_report(), None)
    assert withheld["status"] == "withheld"
    assert withheld["partial_completion"] is None
    assert withheld["full_pass"] is None
    assert withheld["step_results"] == []


def test_score_cli_default_is_legacy_and_proof_mode_is_explicit(
    tmp_path, capsys
) -> None:
    parser = build_parser()
    parsed = parser.parse_args([
        "--case", "case.json",
        "--report", "report.md",
        "--ledger", "ledger.json",
    ])
    assert parsed.scoring_semantics == "verified_slots_v1"

    case_path = tmp_path / "case.json"
    report_path = tmp_path / "report.md"
    ledger_path = tmp_path / "ledger.json"
    graph_path = tmp_path / "graph.json"
    case_path.write_text(json.dumps(_proof_case()), encoding="utf-8")
    report_path.write_text(oracle_report(), encoding="utf-8")
    ledger_path.write_text(json.dumps(ledger().to_dict()), encoding="utf-8")
    graph_path.write_text(json.dumps(graph()), encoding="utf-8")

    assert score_cli([
        "--case", str(case_path),
        "--report", str(report_path),
        "--ledger", str(ledger_path),
        "--evidence-graph", str(graph_path),
        "--scoring-semantics", "proof_steps_v1",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["scoring_semantics"] == "proof_steps_v1"
    assert output["full_pass"] == 1
