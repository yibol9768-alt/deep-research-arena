from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.eval.observation_ledger import sha256_text
from src.eval.oracle_validation_v3 import (
    OracleSuiteValidationError,
    REQUIRED_ADVERSARIAL_CATEGORIES,
    SUITE_SCHEMA,
    validate_oracle_suite,
    verify_validation_result,
)


U1 = "http://localhost:9999/products/alpha"
U2 = "http://localhost:8090/content/wikipedia_en_all_nopic/A/cabin-noise"
UNUSED = "http://localhost:3000/t/unused"
FABRICATED = "http://localhost:9999/not-in-frozen-corpus"
BODY1 = "The frozen Alpha page says Alpha battery life is 30 hours."
BODY2 = "The frozen concept page says cabin noise is low frequency."


def _event(run_id: str, i: int, kind: str, url: str, text: str, *, parent=None):
    return {
        "run_id": run_id,
        "event_id": i,
        "timestamp": float(i),
        "event_type": kind,
        "request_url": url,
        "canonical_url": url,
        "parent_event_id": parent,
        "content_sha256": sha256_text(text),
        "content_text_or_blob_ref": text,
        "http_status": 200 if kind in {"fetch_body", "extracted_body"} else None,
        "observable": True,
    }


def _ledger(run_id: str, mode: str = "full") -> dict:
    if mode == "empty":
        events = []
    elif mode == "guessed":
        events = [
            _event(run_id, 1, "fetch_body", U1, BODY1),
            _event(run_id, 2, "search_result", U2, "Cabin noise concept result"),
            _event(run_id, 3, "fetch_body", U2, BODY2, parent=2),
        ]
    else:
        events = [
            _event(run_id, 1, "search_result", U1, "Alpha catalog result"),
            _event(run_id, 2, "fetch_body", U1, BODY1, parent=1),
            _event(run_id, 3, "search_result", U2, "Cabin noise concept result"),
            _event(run_id, 4, "fetch_body", U2, BODY2, parent=3),
        ]
    return {
        "observation_semantics": "observation_ledger_v1",
        "run_id": run_id,
        "capture_complete": True,
        "events": events,
    }


def _case() -> dict:
    return {
        "task_id": "dra_v3_oracle_fixture_0001",
        "task_version": 3,
        "case_schema": "evidence_graph_case_v1",
        "corpus_snapshot": "synthetic-fixture-v1",
        "cluster_id": "oracle_fixture",
        "corpus_registry_urls": [U1, U2, UNUSED],
        "corpus_registry_hash": sha256_text("typed synthetic registry"),
        "slots": [
            {
                "slot_id": "E1",
                "type": "evidence",
                "required": True,
                "critical": True,
                "claim_id": "ev1",
            },
            {
                "slot_id": "E2",
                "type": "evidence",
                "required": True,
                "critical": True,
                "claim_id": "ev2",
            },
            {
                "slot_id": "B1",
                "type": "bridge",
                "required": True,
                "critical": True,
                "requires": ["E1", "E2"],
                "rule": "bridge_rule",
            },
            {
                "slot_id": "D1",
                "type": "decision",
                "required": True,
                "critical": True,
                "requires": ["B1"],
                "rule": "decision_rule",
            },
        ],
        "rule_definitions": {
            "bridge_rule": {
                "type": "bridge",
                "matcher": "normalized_text",
                "accepted_phrases": [
                    "Together these facts establish the travel tradeoff"
                ],
            },
            "decision_rule": {
                "type": "decision",
                "decision_matcher": {
                    "matcher": "normalized_text",
                    "accepted_phrases": [
                        "Noise control is the first priority",
                        "Battery endurance is the first priority",
                    ],
                },
                "conclusion_phrases": {
                    "Alpha": ["I recommend Alpha"],
                    "Beta": ["I recommend Beta"],
                },
                "admissible_conditions": [
                    {
                        "answer": "Alpha",
                        "when": "noise_priority",
                        "condition_matcher": {
                            "matcher": "normalized_text",
                            "accepted_phrases": ["Noise control is the first priority"],
                        },
                        "tradeoff_matchers": {
                            "battery_compromise": {
                                "matcher": "normalized_text",
                                "accepted_phrases": [
                                    "Alpha accepts the battery compromise"
                                ],
                            }
                        },
                    },
                    {
                        "answer": "Beta",
                        "when": "battery_priority",
                        "condition_matcher": {
                            "matcher": "normalized_text",
                            "accepted_phrases": [
                                "Battery endurance is the first priority"
                            ],
                        },
                        "tradeoff_matchers": {
                            "noise_compromise": {
                                "matcher": "normalized_text",
                                "accepted_phrases": [
                                    "Beta accepts the noise compromise"
                                ],
                            }
                        },
                    },
                ],
            },
        },
        "acceptable_conclusions": [
            {
                "answer": "Alpha",
                "when": "noise_priority",
                "required_tradeoffs": ["battery_compromise"],
            },
            {
                "answer": "Beta",
                "when": "battery_priority",
                "required_tradeoffs": ["noise_compromise"],
            },
        ],
        "decidable_claims": [
            {
                "claim_id": "contradictory_gamma",
                "contradicts_slot_id": "D1",
                "critical": True,
                "rejected_matcher": {
                    "matcher": "normalized_text",
                    "accepted_phrases": ["I recommend Gamma"],
                },
            }
        ],
        "research_subgoals": [
            {
                "subgoal_id": "G1",
                "description": "synthesize endurance and cabin-noise evidence",
                "critical": True,
                "requires": ["E1", "E2", "B1"],
                "local_conclusion_slot_id": "B1",
            },
            {
                "subgoal_id": "G2",
                "description": "make the priority-consistent decision",
                "critical": True,
                "requires": ["B1", "D1"],
                "local_conclusion_slot_id": "D1",
            },
        ],
    }


def _graph() -> dict:
    return {
        "schema_version": "evidence_graph_v1",
        "nodes": {
            "ev1": {
                "evidence_id": "ev1",
                "source_url": U1,
                "content_sha256": sha256_text(BODY1),
                "body_support": True,
                "search_snippet_support": False,
                "support_spans": [{"text": "Alpha battery life is 30 hours"}],
                "verifier": {
                    "kind": "typed_claim",
                    "matcher": "normalized_text",
                    "accepted_phrases": ["Alpha lasts 30 hours"],
                },
            },
            "ev2": {
                "evidence_id": "ev2",
                "source_url": U2,
                "content_sha256": sha256_text(BODY2),
                "body_support": True,
                "search_snippet_support": False,
                "support_spans": [{"text": "cabin noise is low frequency"}],
                "verifier": {
                    "kind": "typed_claim",
                    "matcher": "normalized_text",
                    "accepted_phrases": ["Cabin noise is low frequency"],
                },
            },
        },
    }


FACTS = (
    f"Alpha lasts 30 hours [product]({U1}). "
    f"Cabin noise is low frequency [concept]({U2})."
)
BRIDGE = "Together these facts establish the travel tradeoff."
ALPHA_DECISION = (
    "Noise control is the first priority. "
    "Alpha accepts the battery compromise. Therefore, I recommend Alpha."
)
BETA_DECISION = (
    "Battery endurance is the first priority. "
    "Beta accepts the noise compromise. Therefore, I recommend Beta."
)


def _report(answer: str = "Alpha") -> str:
    decision = ALPHA_DECISION if answer == "Alpha" else BETA_DECISION
    return f"{FACTS}\n\n{BRIDGE} {decision}"


def _inline(value):
    return {"inline": value}


def _oracle(run_id: str, kind: str, answer: str = "Alpha") -> dict:
    out = {
        "run_id": run_id,
        "kind": kind,
        "answer": answer,
        "report": _inline(_report(answer)),
        "ledger": _inline(_ledger(run_id)),
    }
    if kind == "minimal":
        out["minimal_evidence_ids"] = ["ev1", "ev2"]
    if kind == "human":
        out["manual_record"] = {
            "origin": "manual",
            "reviewer": "synthetic-fixture-reviewer",
            "solve_minutes": 1.5,
            "access_path": [U1, U2],
            "attested": True,
            "synthetic": True,
        }
    return out


def _negative(run_id: str, category: str) -> dict:
    report = ""
    ledger = _ledger(run_id)
    answer = None
    if category == "url_dump":
        report = f"Sources: [product]({U1}) [concept]({U2})"
    elif category == "correct_plus_fabricated":
        report = _report() + f"\n\nExtra fabricated source: {FABRICATED}"
    elif category == "fetch_all_no_answer":
        report = "I opened all relevant pages."
    elif category == "unsupported_answer":
        report = _report()
        ledger = _ledger(run_id, "empty")
        answer = "Alpha"
    elif category == "fact_dump":
        report = FACTS
    elif category == "single_source":
        report = (
            f"Alpha lasts 30 hours [product]({U1}).\n\n"
            f"{BRIDGE} {ALPHA_DECISION}"
        )
    elif category == "guessed_then_fetched":
        report = _report()
        ledger = _ledger(run_id, "guessed")
    elif category == "wrong_binding":
        report = (
            f"Alpha lasts 30 hours [wrong concept]({U2}). "
            f"Cabin noise is low frequency [wrong product]({U1}).\n\n"
            f"{BRIDGE} {ALPHA_DECISION}"
        )
    elif category == "contradictory_decision":
        report = (
            f"{FACTS}\n\n{BRIDGE} Noise control is the first priority. "
            "Alpha accepts the battery compromise. Therefore, I recommend Gamma."
        )
    elif category == "silence":
        report = ""
        ledger = _ledger(run_id, "empty")
    else:
        raise AssertionError(category)
    out = {
        "run_id": run_id,
        "category": category,
        "report": _inline(report),
        "ledger": _inline(ledger),
    }
    if answer is not None:
        out["answer"] = answer
    return out


def _suite() -> dict:
    return {
        "schema": SUITE_SCHEMA,
        "suite_id": "synthetic-oracle-closure-v1",
        "validation_scope": "synthetic_test",
        "case": _inline(_case()),
        "evidence_graph": _inline(_graph()),
        "oracles": [
            _oracle("oracle-machine", "machine"),
            _oracle("oracle-human", "human"),
            _oracle("oracle-minimal", "minimal"),
            _oracle("oracle-alpha", "admissible_alternative", "Alpha"),
            _oracle("oracle-beta", "admissible_alternative", "Beta"),
        ],
        "adversarial": [
            _negative(f"negative-{category}", category)
            for category in REQUIRED_ADVERSARIAL_CATEGORIES
        ],
    }


def test_complete_synthetic_suite_replays_scores_and_stays_non_formal():
    suite = _suite()
    first = validate_oracle_suite(suite)
    second = validate_oracle_suite(copy.deepcopy(suite))

    assert first == second
    assert verify_validation_result(first)
    assert first["status"] == "validated"
    assert first["validation_tier"] == "synthetic_mechanism_only"
    assert first["synthetic_only"] is True
    assert first["formal_pilot_passed"] is False
    assert first["formal_human_validation_passed"] is False
    assert all(
        row["score"]["case_artifact_sha256"] == first["artifacts"]["case"]["sha256"]
        for row in [*first["oracle_results"], *first["adversarial_results"]]
    )
    assert all(
        row["score"]["agent"]
        and row["score"]["replicate"] == 1
        for row in [*first["oracle_results"], *first["adversarial_results"]]
    )
    assert first["requires_real_human_followup"] is True
    assert first["manual_human_status"] == "synthetic_fixture_replayed"

    assert {row["kind"] for row in first["oracle_results"]} == {
        "machine",
        "human",
        "minimal",
        "admissible_alternative",
    }
    for row in first["oracle_results"]:
        score = row["score"]
        assert score["task_pass"] == 1
        assert score["verified_recall"] == 1.0
        assert score["critical_contradictions"] == 0
        assert score["fabricated_citations"] == 0

    negatives = {row["category"]: row["score"] for row in first["adversarial_results"]}
    assert set(negatives) == set(REQUIRED_ADVERSARIAL_CATEGORIES)
    assert all(score["task_pass"] == 0 for score in negatives.values())
    assert negatives["correct_plus_fabricated"]["fabricated_citations"] > 0
    assert negatives["silence"]["tp"] == 0
    assert negatives["silence"]["verified_f1"] == 0.0
    assert negatives["silence"]["verified_research_completion"] == 0.0


def test_missing_category_and_missing_conditional_alternative_fail_closed():
    missing_negative = _suite()
    missing_negative["adversarial"].pop()
    with pytest.raises(OracleSuiteValidationError, match="missing adversarial categories"):
        validate_oracle_suite(missing_negative)

    missing_answer = _suite()
    missing_answer["oracles"] = [
        row
        for row in missing_answer["oracles"]
        if not (row["kind"] == "admissible_alternative" and row["answer"] == "Beta")
    ]
    with pytest.raises(OracleSuiteValidationError, match="per answer"):
        validate_oracle_suite(missing_answer)


def test_automated_or_incomplete_human_record_and_fake_formal_data_are_rejected():
    automated = _suite()
    human = next(row for row in automated["oracles"] if row["kind"] == "human")
    human["manual_record"]["origin"] = "generated"
    with pytest.raises(OracleSuiteValidationError, match="origin=manual"):
        validate_oracle_suite(automated)

    missing_reviewer = _suite()
    human = next(row for row in missing_reviewer["oracles"] if row["kind"] == "human")
    human["manual_record"].pop("reviewer")
    with pytest.raises(OracleSuiteValidationError, match="missing"):
        validate_oracle_suite(missing_reviewer)

    fake_formal = _suite()
    fake_formal["validation_scope"] = "formal"
    with pytest.raises(OracleSuiteValidationError, match="formally compiled case"):
        validate_oracle_suite(fake_formal)


def test_declared_score_expectation_cannot_override_real_replay():
    suite = _suite()
    machine = next(row for row in suite["oracles"] if row["kind"] == "machine")
    machine["expected"] = {"task_pass": 0}
    with pytest.raises(OracleSuiteValidationError, match="expected task_pass=0"):
        validate_oracle_suite(suite)


def test_path_artifacts_require_stable_hash_and_cannot_escape(tmp_path):
    suite = _suite()
    machine = next(row for row in suite["oracles"] if row["kind"] == "machine")
    report_path = tmp_path / "machine.md"
    report_path.write_text(_report())
    digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
    machine["report"] = {"path": "machine.md", "sha256": digest}

    result = validate_oracle_suite(suite, base_dir=tmp_path)
    audit = next(row for row in result["oracle_results"] if row["kind"] == "machine")
    assert audit["report_artifact"] == {
        "source": "path",
        "relative_path": "machine.md",
        "sha256": digest,
        "hash_basis": "raw_bytes",
    }

    report_path.write_text("drifted")
    with pytest.raises(OracleSuiteValidationError, match="sha256 mismatch"):
        validate_oracle_suite(suite, base_dir=tmp_path)

    escaped = _suite()
    machine = next(row for row in escaped["oracles"] if row["kind"] == "machine")
    machine["report"] = {"path": "../outside.md", "sha256": "0" * 64}
    with pytest.raises(OracleSuiteValidationError, match="cannot traverse"):
        validate_oracle_suite(escaped, base_dir=tmp_path)


def test_cli_writes_self_hashed_result_and_returns_nonzero_on_failure(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "validate_oracle_suite_v3.py"
    suite_path = tmp_path / "suite.json"
    out_path = tmp_path / "validation.json"
    suite_path.write_text(json.dumps(_suite(), ensure_ascii=False))
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--suite",
            str(suite_path),
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(out_path.read_text())
    assert verify_validation_result(result)
    assert result["suite_sha256"] == hashlib.sha256(suite_path.read_bytes()).hexdigest()

    broken = _suite()
    broken["adversarial"].pop()
    suite_path.write_text(json.dumps(broken))
    failed = subprocess.run(
        [sys.executable, str(script), "--suite", str(suite_path), "--out", str(out_path)],
        capture_output=True,
        text=True,
    )
    assert failed.returncode != 0
    assert "missing adversarial categories" in failed.stderr
