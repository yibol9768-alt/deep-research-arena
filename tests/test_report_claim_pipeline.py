from __future__ import annotations

from src.scoring.report_claim_pipeline import (
    _dedup_response_schema,
    _preliminary_exact_dedup,
    _propose,
    _semantic_dedup_candidate_pairs,
    segment_report,
)


class ProposalJudge:
    model = "test-judge"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def call_json(self, _stage, _system, payload, **kwargs):
        self.calls.append({"payload": payload, "kwargs": kwargs})
        span = payload["spans"][0]
        return {
            "claims": [
                {
                    "segment_id": span["segment_id"],
                    "normalized_claim": "Model X costs $40.",
                    "claim_kind": "external_atomic",
                    "evidence_policy": "citation_required",
                    "subject": "Model X",
                    "predicate": "costs",
                    "object": "$40",
                    "qualifiers": {},
                    "polarity": "assert",
                    "modality": "categorical",
                    "attribution": "retailer_claim",
                    "citation_ids": ["c1"],
                }
            ]
        }


def test_proposal_anchors_to_input_segment_without_model_copying_raw_text():
    report = 'Model X costs $40. <cite id="c1">listing</cite>\n'
    judge = ProposalJudge()

    proposals, rejected = _propose(
        judge,
        segment_report(report),
        stage_prefix="claim-stage-a",
    )

    assert rejected == []
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["report_span"]["raw_text"] == report.rstrip("\n")
    assert report[
        proposal["report_span"]["start"] : proposal["report_span"]["end"]
    ] == proposal["report_span"]["raw_text"]
    schema = judge.calls[0]["kwargs"]["response_schema"]
    claim_schema = schema["properties"]["claims"]["items"]
    assert "raw_text" not in claim_schema["properties"]
    assert "raw_text" not in claim_schema["required"]


def test_semantic_dedup_schema_only_requests_positional_pair_decisions():
    schema = _dedup_response_schema(3)

    assert set(schema["properties"]) == {"duplicate", "reason_codes"}
    decisions = schema["properties"]["duplicate"]
    assert decisions["minItems"] == 3
    assert decisions["maxItems"] == 3
    assert schema["required"] == ["duplicate", "reason_codes"]


def test_semantic_dedup_pairs_reject_incompatible_models_and_numbers():
    base = {
        "claim_kind": "external_atomic",
        "predicate": "has battery capacity",
        "qualifiers": {},
        "polarity": "assert",
        "modality": "categorical",
        "attribution": "retailer_claim",
    }
    claims = [
        {
            **base,
            "claim_id": "p_0001",
            "normalized_claim": "Soundcore Flare2 has a 5200 mAh battery.",
            "subject": "Soundcore Flare2",
            "object": "5200 mAh",
        },
        {
            **base,
            "claim_id": "p_0002",
            "normalized_claim": "The Soundcore Flare2 battery is 5200 mAh.",
            "subject": "Soundcore Flare2",
            "object": "5200 mAh",
        },
        {
            **base,
            "claim_id": "p_0003",
            "normalized_claim": "Ortizan X10 has a 6600 mAh battery.",
            "subject": "Ortizan X10",
            "object": "6600 mAh",
        },
    ]

    pairs = _semantic_dedup_candidate_pairs(claims)

    assert [
        (row["left_claim_id"], row["right_claim_id"])
        for row in pairs
    ] == [("p_0001", "p_0002")]


def test_semantic_dedup_pairs_keep_claim_and_inference_separate():
    common = {
        "claim_kind": "external_atomic",
        "subject": "power rating",
        "qualifiers": {},
        "polarity": "assert",
        "modality": "categorical",
        "attribution": "direct_fact",
    }
    claims = [
        {
            **common,
            "claim_id": "p_0001",
            "normalized_claim": "The power rating claimed is 30W.",
            "predicate": "claimed to be",
            "object": "30W",
        },
        {
            **common,
            "claim_id": "p_0002",
            "normalized_claim": (
                "The power rating is likely about 30W RMS."
            ),
            "predicate": "likely RMS",
            "object": "about 30W",
        },
    ]

    assert _semantic_dedup_candidate_pairs(claims) == []


def test_semantic_dedup_pairs_reject_shared_template_with_different_object():
    common = {
        "claim_kind": "external_atomic",
        "subject": "listing title of Soundcore Flare 2",
        "predicate": "states",
        "qualifiers": {},
        "polarity": "assert",
        "modality": "categorical",
        "attribution": "direct_fact",
    }
    claims = [
        {
            **common,
            "claim_id": "p_0001",
            "normalized_claim": (
                "The listing title states that it is a renewed model."
            ),
            "object": "it is a renewed model",
        },
        {
            **common,
            "claim_id": "p_0002",
            "normalized_claim": (
                "The listing title states that it is a wireless speaker."
            ),
            "object": "it is a wireless speaker",
        },
    ]

    assert _semantic_dedup_candidate_pairs(claims) == []


def test_semantic_dedup_pairs_keep_marketing_claim_and_capability_separate():
    common = {
        "claim_kind": "bounded_absence",
        "subject": "Ortizan and Flare 2",
        "object": "",
        "qualifiers": {"absence_terms": ["hi-res over Bluetooth"]},
        "polarity": "deny",
        "modality": "categorical",
        "attribution": "direct_fact",
    }
    claims = [
        {
            **common,
            "claim_id": "p_0001",
            "normalized_claim": (
                "The Ortizan and Flare 2 do not claim to support "
                "hi-res over Bluetooth."
            ),
            "predicate": "claim to support hi-res over Bluetooth",
        },
        {
            **common,
            "claim_id": "p_0002",
            "normalized_claim": (
                "The Ortizan and Flare 2 do not support "
                "hi-res over Bluetooth."
            ),
            "predicate": "support hi-res over Bluetooth",
        },
    ]

    assert _semantic_dedup_candidate_pairs(claims) == []


def test_semantic_dedup_pairs_preserve_epistemic_hedges():
    common = {
        "claim_kind": "external_atomic",
        "subject": "Bluetooth version",
        "predicate": "is",
        "object": "5.0 with SBC and AAC codecs",
        "qualifiers": {},
        "polarity": "assert",
        "modality": "categorical",
        "attribution": "direct_fact",
    }
    claims = [
        {
            **common,
            "claim_id": "p_0001",
            "normalized_claim": (
                "Bluetooth version is 5.0 with SBC and AAC codecs."
            ),
        },
        {
            **common,
            "claim_id": "p_0002",
            "normalized_claim": (
                "Bluetooth version is 5.0 with SBC and likely AAC codecs."
            ),
        },
    ]

    assert _semantic_dedup_candidate_pairs(claims) == []


def test_semantic_dedup_pairs_preserve_conditions():
    common = {
        "claim_kind": "external_atomic",
        "subject": "battery life",
        "predicate": "is",
        "object": "6–8 hours",
        "qualifiers": {},
        "polarity": "assert",
        "modality": "categorical",
        "attribution": "direct_fact",
    }
    claims = [
        {
            **common,
            "claim_id": "p_0001",
            "normalized_claim": "At 70% volume, no lights: ~6–8 hours.",
        },
        {
            **common,
            "claim_id": "p_0002",
            "normalized_claim": (
                "At 70% volume, the battery life is ~6–8 hours."
            ),
        },
    ]

    assert _semantic_dedup_candidate_pairs(claims) == []


def test_semantic_dedup_pairs_reject_broader_compound_claim():
    common = {
        "claim_kind": "external_atomic",
        "subject": "both speakers",
        "predicate": "should be rinsed",
        "object": "with fresh water and dried thoroughly",
        "qualifiers": {},
        "polarity": "assert",
        "modality": "categorical",
        "attribution": "direct_fact",
    }
    claims = [
        {
            **common,
            "claim_id": "p_0001",
            "normalized_claim": (
                "After pool exposure, both speakers should be rinsed with "
                "fresh water and dried thoroughly. The charging port cover "
                "must be sealed before any water exposure."
            ),
        },
        {
            **common,
            "claim_id": "p_0002",
            "normalized_claim": (
                "After pool exposure, both speakers should be rinsed with "
                "fresh water and dried thoroughly."
            ),
        },
    ]

    assert _semantic_dedup_candidate_pairs(claims) == []


def test_semantic_dedup_pairs_reject_chinese_different_propositions():
    common = {
        "claim_kind": "external_atomic",
        "subject": "Flare 2",
        "predicate": "",
        "object": "",
        "qualifiers": {},
        "polarity": "assert",
        "modality": "categorical",
        "attribution": "direct_fact",
    }
    claims = [
        {
            **common,
            "claim_id": "p_0001",
            "normalized_claim": (
                "Flare 2 的低频由两个被动振膜提供，"
                "在中等音量下低音扎实、有弹性"
            ),
        },
        {
            **common,
            "claim_id": "p_0002",
            "normalized_claim": (
                "Flare 2 的中频人声清晰、靠前，"
                "适合播客、流行乐、民谣"
            ),
        },
    ]

    assert _semantic_dedup_candidate_pairs(claims) == []


def test_semantic_dedup_pairs_preserve_chinese_uncertainty():
    common = {
        "claim_kind": "external_atomic",
        "subject": "续航",
        "predicate": "达到",
        "object": "8 小时",
        "qualifiers": {},
        "polarity": "assert",
        "modality": "categorical",
        "attribution": "direct_fact",
    }
    claims = [
        {
            **common,
            "claim_id": "p_0001",
            "normalized_claim": "续航达到 8 小时。",
        },
        {
            **common,
            "claim_id": "p_0002",
            "normalized_claim": "续航可能达到约 8 小时。",
        },
    ]

    assert _semantic_dedup_candidate_pairs(claims) == []


def test_semantic_dedup_pairs_allow_identical_chinese_claim_candidate():
    common = {
        "claim_kind": "external_atomic",
        "subject": "Soundcore Flare 2",
        "predicate": "重量是",
        "object": "680g",
        "qualifiers": {},
        "polarity": "assert",
        "modality": "categorical",
        "attribution": "direct_fact",
    }
    claims = [
        {
            **common,
            "claim_id": "p_0001",
            "normalized_claim": "Soundcore Flare 2 的重量是 680g。",
        },
        {
            **common,
            "claim_id": "p_0002",
            "normalized_claim": "Soundcore Flare 2 的重量是 680g。",
        },
    ]

    pairs = _semantic_dedup_candidate_pairs(claims)
    assert [
        (row["left_claim_id"], row["right_claim_id"])
        for row in pairs
    ] == [("p_0001", "p_0002")]


def test_preliminary_exact_dedup_ignores_decomposition_labels():
    common = {
        "normalized_claim": (
            "Flare 2 整体声音偏均衡，中频突出，低频有量感。"
        ),
        "claim_kind": "external_atomic",
        "subject": "Flare 2",
        "qualifiers": {},
        "polarity": "assert",
        "modality": "categorical",
        "attribution": "direct_fact",
    }
    proposals = [
        {
            **common,
            "claim_id": "p_0001",
            "predicate": "整体声音偏",
            "object": "均衡",
            "report_span": {"segment_id": "s_0001"},
            "premise": "first occurrence",
            "citation_ids": ["c1"],
        },
        {
            **common,
            "claim_id": "p_0002",
            "predicate": "中频",
            "object": "突出",
            "report_span": {"segment_id": "s_0002"},
            "premise": "second occurrence",
            "citation_ids": ["c2"],
        },
    ]

    deduplicated = _preliminary_exact_dedup(proposals)

    assert len(deduplicated) == 1
    assert deduplicated[0]["citation_ids"] == ["c1", "c2"]
    assert len(deduplicated[0]["occurrences"]) == 2


def test_preliminary_exact_dedup_preserves_subject_and_scope():
    common = {
        "normalized_claim": "The product page makes no Hi-Res claim.",
        "claim_kind": "bounded_absence",
        "predicate": "makes",
        "object": "no Hi-Res claim",
        "polarity": "deny",
        "modality": "categorical",
        "attribution": "direct_fact",
        "report_span": {"segment_id": "s_0001"},
        "premise": "absence statement",
        "citation_ids": ["c1"],
    }
    proposals = [
        {
            **common,
            "claim_id": "p_0001",
            "subject": "Ortizan page",
            "qualifiers": {"scope_urls": ["ortizan"]},
        },
        {
            **common,
            "claim_id": "p_0002",
            "subject": "Flare 2 page",
            "qualifiers": {"scope_urls": ["flare2"]},
        },
    ]

    assert len(_preliminary_exact_dedup(proposals)) == 2
