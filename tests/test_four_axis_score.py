from __future__ import annotations

import pytest

from src.scoring.four_axis_score import score_four_axis


def _packet() -> dict:
    return {
        "material_claims": [
            {"verdict": "true", "materiality": 2},
            {"verdict": "false", "materiality": 1},
            {"verdict": "unresolved", "materiality": 9},
        ],
        "citation_bindings": [
            {"passed": True},
            {"passed": False, "failure_reasons": ["wrong_binding"]},
        ],
        "citation_required_units": [
            {"grounded": True},
            {"grounded": False},
        ],
        "completeness_units": [
            {
                "facet_id": "a",
                "unit_type": "atomic",
                "importance": "core",
                "covered": True,
                "content_covered": True,
            },
            {
                "facet_id": "a",
                "unit_type": "atomic",
                "importance": "core",
                "covered": False,
                "content_covered": True,
            },
            {
                "facet_id": "b",
                "unit_type": "decision",
                "importance": "core",
                "covered": True,
                "content_covered": True,
            },
        ],
        "rubric_items": [
            {"verdict": "fulfilled", "weight": 1},
            {"verdict": "partially_fulfilled", "weight": 1},
            {"verdict": "not_fulfilled", "weight": 1},
        ],
        "cited_urls": [
            {
                "valid": True,
                "canonicalized": True,
                "in_registry": True,
                "snapshot_available": True,
            },
            {
                "valid": False,
                "canonicalized": True,
                "in_registry": False,
                "snapshot_available": False,
            },
        ],
    }


def test_four_axis_uses_pdf_denominators_and_equal_quality_weights():
    score = score_four_axis(_packet())
    assert score["fact"]["score"] == pytest.approx(2 / 3)
    assert score["fact"]["resolution_rate"] == pytest.approx(2 / 3)
    assert score["evidence"]["precision"] == pytest.approx(1 / 2)
    assert score["evidence"]["recall"] == pytest.approx(1 / 2)
    assert score["completeness"]["group_scores"] == {
        "a::atomic": 1.0,
        "b::decision": 1.0,
    }
    assert score["completeness"]["score"] == pytest.approx(1.0)
    assert score["rubric"]["score"] == pytest.approx(0.5)
    assert score["provenance"]["score"] == pytest.approx(0.5)
    expected_quality = ((2 / 3) + 0.5 + 1.0 + 0.5) / 4
    assert score["quality"] == pytest.approx(expected_quality)
    assert score["truth"] == pytest.approx(0.5 * expected_quality)


def test_ambiguous_rubric_is_conservative_but_numeric():
    packet = _packet()
    packet["rubric_items"] = [{"verdict": "ambiguous", "weight": 1}]
    score = score_four_axis(packet)
    assert score["rubric"]["score"] == 0
    assert score["rubric"]["ambiguous_count"] == 1
    assert isinstance(score["truth"], float)


def test_false_claim_can_never_raise_fact():
    packet = _packet()
    before = score_four_axis(packet)["fact"]["score"]
    packet["material_claims"].append({"verdict": "false", "materiality": 1})
    after = score_four_axis(packet)["fact"]["score"]
    assert after < before


def test_unresolved_claims_do_not_fake_adjudication_coverage():
    packet = _packet()
    packet["material_claims"] = [
        {"verdict": "true", "materiality": 1},
        *[{"verdict": "unresolved", "materiality": 1} for _ in range(99)],
    ]
    score = score_four_axis(packet)
    assert score["fact"]["score"] == 1.0
    assert score["fact"]["adjudication_coverage"] == pytest.approx(0.01)


def test_out_of_world_is_neutral_but_conflict_stays_in_fact_denominator():
    packet = _packet()
    packet["material_claims"] = [{"verdict": "true", "materiality": 1}]
    baseline = score_four_axis(packet)["fact"]["score"]
    packet["material_claims"].append(
        {"verdict": "out_of_world", "materiality": 100}
    )
    assert score_four_axis(packet)["fact"]["score"] == baseline
    packet["material_claims"].append(
        {"verdict": "conflicted", "materiality": 1}
    )
    assert score_four_axis(packet)["fact"]["score"] == pytest.approx(0.5)


def test_zero_evidence_zeroes_geometric_candidate():
    packet = _packet()
    packet["material_claims"] = [{"verdict": "true", "materiality": 1}]
    packet["citation_bindings"] = [{"passed": False}]
    packet["citation_required_units"] = [{"grounded": False}]
    packet["completeness_units"] = [
        {
            "facet_id": "a",
            "unit_type": "atomic",
            "importance": "core",
            "content_covered": True,
            "covered": True,
        }
    ]
    packet["rubric_items"] = [{"verdict": "fulfilled", "weight": 1}]
    packet["cited_urls"] = [
        {
            "valid": True,
            "canonicalized": True,
            "in_registry": True,
            "snapshot_available": True,
        }
    ]
    score = score_four_axis(packet)
    assert score["truth_linear_diagnostic"] == pytest.approx(0.75)
    assert score["truth_geometric_candidate"] == 0.0


def test_completeness_is_content_coverage_not_cross_axis_grounding():
    packet = _packet()
    packet["completeness_units"] = [
        {
            "facet_id": "a",
            "unit_type": "atomic",
            "importance": "core",
            "content_covered": True,
            "covered": False,
        }
    ]
    score = score_four_axis(packet)
    assert score["completeness"]["score"] == 1.0
    assert score["completeness"]["grounded_covered_units"] == 0


def test_evidence_deduplicates_only_same_claim_occurrence_and_citation():
    packet = _packet()
    duplicated = {
        "claim_id": "p1",
        "occurrence_index": 0,
        "citation_id": "c1",
        "passed": True,
    }
    packet["citation_bindings"] = [
        duplicated,
        dict(duplicated),
        {
            "claim_id": "p2",
            "occurrence_index": 0,
            "citation_id": "c1",
            "passed": False,
        },
    ]
    packet["citation_required_units"] = [
        {"unit_id": "claim:p1", "claim_id": "p1", "grounded": True},
        {"unit_id": "claim:p2", "claim_id": "p2", "grounded": False},
    ]
    score = score_four_axis(packet)
    assert score["evidence"]["binding_count"] == 2
    assert score["evidence"]["precision"] == pytest.approx(0.5)


def test_completeness_v2_rejects_legacy_covered_only_packets():
    packet = _packet()
    packet["completeness_units"] = [
        {
            "unit_id": "u1",
            "facet_id": "a",
            "unit_type": "atomic",
            "importance": "core",
            "covered": True,
        }
    ]
    with pytest.raises(ValueError, match="content_covered"):
        score_four_axis(packet)
