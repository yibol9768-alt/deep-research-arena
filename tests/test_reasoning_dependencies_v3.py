from __future__ import annotations

from copy import deepcopy

from src.eval.observation_ledger import ObservationLedger, sha256_text
from src.eval.slot_scorer import score_case


U1 = "http://localhost:9999/a"
U2 = "http://localhost:8090/content/wikipedia_en_all_nopic/A/b"
B1 = "Alpha source: battery life is 30 hours."
B2 = "Cabin noise is predominantly low frequency."
REGISTRY_HASH = sha256_text("reasoning fixture registry")


def _event(i, kind, url, text, status=None, parent=None):
    return {
        "run_id": "reasoning-run",
        "event_id": i,
        "timestamp": i,
        "event_type": kind,
        "request_url": url,
        "canonical_url": url,
        "parent_event_id": parent,
        "content_sha256": sha256_text(text),
        "content_text_or_blob_ref": text,
        "http_status": status,
        "observable": True,
    }


def _ledger():
    return ObservationLedger.from_records(
        [
            _event(1, "search_result", U1, "result A"),
            _event(2, "fetch_body", U1, B1, 200, 1),
            _event(3, "search_result", U2, "result B"),
            _event(4, "fetch_body", U2, B2, 200, 3),
        ],
        expected_run_id="reasoning-run",
        capture_complete=True,
    )


def _graph():
    return {
        "nodes": {
            "ev1": {
                "evidence_id": "ev1",
                "subject": "Alpha",
                "predicate": "battery_life",
                "object": "30 hours",
                "source_url": U1,
                "content_sha256": sha256_text(B1),
                "support_spans": [{"text": "battery life is 30 hours"}],
                "verifier": {"accepted_phrases": ["Alpha lasts 30 hours"]},
            },
            "ev2": {
                "evidence_id": "ev2",
                "subject": "cabin noise",
                "predicate": "frequency",
                "object": "low",
                "source_url": U2,
                "content_sha256": sha256_text(B2),
                "support_spans": [{"text": "Cabin noise is predominantly low frequency"}],
                "verifier": {"accepted_phrases": ["Cabin noise is low frequency"]},
            },
        }
    }


def _case():
    return {
        "task_id": "reasoning-deps",
        "task_version": 3,
        "corpus_registry_urls": [U1, U2],
        "corpus_registry_hash": REGISTRY_HASH,
        "research_subgoals": [
            {
                "subgoal_id": "G1",
                "critical": True,
                "requires": ["E1", "E2", "B1"],
                "local_conclusion_slot_id": "B1",
            },
            {
                "subgoal_id": "G2",
                "critical": True,
                "requires": ["B1", "D1"],
                "local_conclusion_slot_id": "D1",
            },
        ],
        "slots": [
            {"slot_id": "E1", "type": "evidence", "critical": True, "claim_id": "ev1"},
            {"slot_id": "E2", "type": "evidence", "critical": True, "claim_id": "ev2"},
            {
                "slot_id": "B1", "type": "bridge", "critical": True,
                "requires": ["E1", "E2"],
                "rule": {"accepted_phrases": ["Low-frequency noise makes battery endurance relevant"]},
            },
            {
                "slot_id": "D1", "type": "decision", "critical": True,
                "requires": ["B1"],
                "rule": {
                    "accepted_phrases": ["Noise reduction has first priority"],
                    "conclusion_matchers": {
                        "Alpha": {
                            "matcher": "normalized_text",
                            "accepted_phrases": ["recommend Alpha"],
                        }
                    },
                },
            },
        ],
        "acceptable_conclusions": ["Alpha"],
    }


def _slot(result, slot_id):
    return next(row for row in result["slot_results"] if row["slot_id"] == slot_id)


def _facts() -> str:
    return (
        f"Alpha lasts 30 hours [A]({U1}). "
        f"Cabin noise is low frequency [B]({U2})."
    )


def test_bridge_requires_both_verified_dependencies_even_if_bridge_words_exist():
    report = (
        f"Alpha lasts 30 hours [A]({U1}). "
        "Low-frequency noise makes battery endurance relevant. "
        "Noise reduction has first priority. Therefore, I recommend Alpha."
    )
    result = score_case(_case(), report, _ledger(), _graph())
    assert _slot(result, "E1")["verified"] is True
    assert _slot(result, "E2")["verified"] is False
    assert _slot(result, "B1")["checks"]["RULE_OK"]["passed"] is True
    assert _slot(result, "B1")["reason_codes"]["DEPENDENCIES"] == "dependency_unverified"
    assert _slot(result, "B1")["verified"] is False
    assert _slot(result, "D1")["verified"] is False


def test_bridge_requires_explicit_rule_not_just_verified_fact_dump():
    result = score_case(_case(), _facts(), _ledger(), _graph())
    assert _slot(result, "E1")["verified"]
    assert _slot(result, "E2")["verified"]
    assert _slot(result, "B1")["reason_codes"]["RULE_OK"] == "bridge_rule_missing"
    assert not _slot(result, "B1")["verified"]

    negated = score_case(
        _case(),
        _facts() + " It is false that Low-frequency noise makes battery endurance relevant.",
        _ledger(),
        _graph(),
    )
    assert _slot(negated, "B1")["reason_codes"]["RULE_OK"] == "bridge_rule_missing"
    assert negated["verified_research_completion"] == 0.0


def test_decision_requires_verified_bridge_rule_and_explicit_admissible_conclusion():
    base = _facts() + " Low-frequency noise makes battery endurance relevant."
    no_rule = score_case(_case(), base + " Therefore, I recommend Alpha.", _ledger(), _graph())
    assert _slot(no_rule, "B1")["verified"]
    assert _slot(no_rule, "D1")["reason_codes"]["RULE_OK"] == "decision_rule_missing"

    no_conclusion = score_case(
        _case(), base + " Noise reduction has first priority.", _ledger(), _graph()
    )
    assert _slot(no_conclusion, "D1")["reason_codes"]["CONCLUSION"] == "admissible_conclusion_missing"

    complete = score_case(
        _case(),
        base + " Noise reduction has first priority. Therefore, I recommend Alpha.",
        _ledger(),
        _graph(),
    )
    assert _slot(complete, "D1")["verified"]
    assert complete["task_pass"] == 1


def test_conditional_decision_requires_declared_condition_and_tradeoffs():
    conditional = _case()
    conditional["acceptable_conclusions"] = [
        {
            "answer": "Alpha",
            "when": "portability is a hard constraint",
            "required_tradeoffs": ["fit_risk"],
        }
    ]
    conditional["slots"][-1]["rule"] = {
        "decision_matcher": {
            "matcher": "normalized_text",
            "accepted_phrases": ["Portability is a hard constraint"],
        },
        "conclusion_matchers": {
            "Alpha": {
                "matcher": "normalized_text",
                "accepted_phrases": ["I choose Alpha"],
            }
        },
        "admissible_conditions": [
            {
                "answer": "Alpha",
                "when": "portability is a hard constraint",
                "condition_matcher": {
                    "matcher": "normalized_text",
                    "accepted_phrases": ["Portability is a hard constraint"],
                },
                "tradeoff_matchers": {
                    "fit_risk": {
                        "matcher": "normalized_text",
                        "accepted_phrases": ["Fit risk remains a tradeoff"],
                    }
                },
            }
        ],
    }
    prefix = _facts() + " Low-frequency noise makes battery endurance relevant. "
    missing = score_case(
        conditional,
        prefix + "Portability is a hard constraint. I choose Alpha.",
        _ledger(),
        _graph(),
    )
    assert _slot(missing, "D1")["admissibility"]["missing_tradeoffs"] == ["fit_risk"]
    assert not _slot(missing, "D1")["verified"]

    passed = score_case(
        conditional,
        prefix + "Portability is a hard constraint. Fit risk remains a tradeoff. I choose Alpha.",
        _ledger(),
        _graph(),
    )
    assert _slot(passed, "D1")["verified"]


def test_typed_claim_has_no_unsafe_subject_object_or_negation_fallback():
    no_matcher_graph = _graph()
    no_matcher_graph["nodes"]["ev1"].pop("verifier")
    report = (
        f"Alpha battery life is 30 hours [A]({U1}). "
        f"Cabin noise is low frequency [B]({U2})."
    )
    no_matcher = score_case(_case(), report, _ledger(), no_matcher_graph)
    assert _slot(no_matcher, "E1")["C"] is False

    negated = (
        f"Alpha does not last 30 hours [A]({U1}). "
        f"Cabin noise is low frequency [B]({U2})."
    )
    negative = score_case(_case(), negated, _ledger(), _graph())
    assert _slot(negative, "E1")["C"] is False


def test_string_rule_uses_typed_rule_definition():
    typed = _case()
    typed["slots"][2]["rule"] = "bridge_v1"
    typed["slots"][3]["rule"] = "decision_v1"
    typed["rule_definitions"] = {
        "bridge_v1": {
            "type": "bridge",
            "matcher": "normalized_text",
            "accepted_phrases": ["Low-frequency noise makes battery endurance relevant"],
        },
        "decision_v1": {
            "type": "decision",
            "decision_matcher": {
                "matcher": "normalized_text",
                "accepted_phrases": ["Noise reduction has first priority"],
            },
            "conclusion_matchers": {
                "Alpha": {
                    "matcher": "normalized_text",
                    "accepted_phrases": ["I choose Alpha"],
                }
            },
        },
    }
    report = (
        _facts()
        + " Low-frequency noise makes battery endurance relevant."
        + " Noise reduction has first priority. I choose Alpha."
    )
    result = score_case(typed, report, _ledger(), _graph())
    assert _slot(result, "B1")["verified"]
    assert _slot(result, "D1")["verified"]

    negated = score_case(
        typed,
        _facts()
        + " Low-frequency noise makes battery endurance relevant."
        + " Noise reduction has first priority. I do not choose Alpha.",
        _ledger(),
        _graph(),
    )
    assert _slot(negated, "D1")["checks"]["CONCLUSION"]["passed"] is False
    assert not _slot(negated, "D1")["verified"]

    typed["rule_definitions"]["decision_v1"]["conclusion_matchers"] = {
        "Alpha": {
            "matcher": "normalized_text",
            "accepted_phrases": ["recommend Alpha"],
        }
    }
    negated_recommendation = score_case(
        typed,
        _facts()
        + " Low-frequency noise makes battery endurance relevant."
        + " Noise reduction has first priority. I do not recommend Alpha.",
        _ledger(),
        _graph(),
    )
    assert not _slot(negated_recommendation, "D1")["verified"]
