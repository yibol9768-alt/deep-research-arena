from __future__ import annotations

import math

import pytest

from src.scoring.three_axis_score import score_three_axis


def _packet() -> dict:
    return {
        "material_claims": [
            {"status": "supported"},
            {"status": "supported"},
            {"status": "wrong"},
        ],
        "core_atomic_facts": [{"covered": True}, {"covered": False}],
        "citation_bindings": [{"passed": True}, {"passed": False}],
        "citation_required_units": [
            {"grounded": True},
            {"grounded": False},
            {"grounded": False},
        ],
        "research_units": [
            {"facet": "a", "unit_type": "comparison", "covered": True},
            {"facet": "a", "unit_type": "comparison", "covered": False},
            {"facet": "b", "unit_type": "decision", "covered": True},
        ],
        "cited_urls": [{"legal_origin": True}, {"legal_origin": False}],
    }


def test_three_axis_uses_distinct_denominators_and_macro_completeness():
    score = score_three_axis(_packet())
    assert score["fact"]["precision"] == pytest.approx(2 / 3)
    assert score["fact"]["recall"] == pytest.approx(1 / 2)
    assert score["evidence"]["precision"] == pytest.approx(1 / 2)
    assert score["evidence"]["recall"] == pytest.approx(1 / 3)
    assert score["completeness"]["group_scores"] == {
        "a::comparison": 0.5,
        "b::decision": 1.0,
    }
    assert score["completeness"]["score"] == pytest.approx(0.75)
    assert score["provenance"]["score"] == pytest.approx(0.5)
    assert score["truth"] == pytest.approx(score["provenance"]["score"] * score["quality"])


def test_wrong_claim_cannot_increase_fact():
    packet = _packet()
    before = score_three_axis(packet)["fact"]["score"]
    packet["material_claims"].append({"status": "wrong"})
    after = score_three_axis(packet)["fact"]["score"]
    assert after < before


def test_mixed_claim_must_be_split_before_aggregation():
    packet = _packet()
    packet["material_claims"].append({"status": "mixed"})
    with pytest.raises(ValueError, match="must be split"):
        score_three_axis(packet)


def test_empty_collections_are_zero_not_nan():
    packet = {
        "material_claims": [],
        "core_atomic_facts": [],
        "citation_bindings": [],
        "citation_required_units": [],
        "research_units": [],
        "cited_urls": [],
    }
    score = score_three_axis(packet)
    assert score["truth"] == 0.0
    assert not math.isnan(score["truth"])
