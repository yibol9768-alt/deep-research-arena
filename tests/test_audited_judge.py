from __future__ import annotations

import json

import pytest

from src.scoring.audited_judge import AuditedJudge


def test_unwraps_only_singleton_object_array_with_expected_key(tmp_path):
    raw = json.dumps([{"verdicts": [{"claim_id": "p_1", "verdict": "true"}]}])

    judge = AuditedJudge(
        tmp_path / "calls",
        judge_call=lambda *_args: (raw, None),
    )
    result = judge.call_json(
        "fact-verifier",
        "system",
        {"claims": []},
        expected_top_key="verdicts",
    )

    assert result == {
        "verdicts": [{"claim_id": "p_1", "verdict": "true"}]
    }
    call_dir = next((tmp_path / "calls").iterdir())
    assert json.loads((call_dir / "parsed-response.json").read_text()) == result
    metadata = json.loads((call_dir / "metadata.json").read_text())
    assert metadata["response_normalization"] == (
        "unwrap_singleton_object_array"
    )
    assert json.loads((call_dir / "raw-response.txt").read_text()) == [
        {"verdicts": [{"claim_id": "p_1", "verdict": "true"}]}
    ]


def test_does_not_guess_between_multiple_wrapped_objects(tmp_path):
    raw = json.dumps([{"verdicts": []}, {"verdicts": []}])
    judge = AuditedJudge(
        tmp_path / "calls",
        judge_call=lambda *_args: (raw, None),
    )

    with pytest.raises(RuntimeError, match="lacks top-level key"):
        judge.call_json(
            "fact-verifier",
            "system",
            {"claims": []},
            expected_top_key="verdicts",
        )


def test_wraps_bare_verdicts_array_without_editing_items(tmp_path):
    verdicts = [
        {
            "binding_id": "b_0001",
            "bound": True,
            "support_verdict": "support",
        },
        {
            "binding_id": "b_0002",
            "bound": False,
            "support_verdict": "insufficient",
        },
    ]
    raw = json.dumps(verdicts)
    judge = AuditedJudge(
        tmp_path / "calls",
        judge_call=lambda *_args: (raw, None),
    )

    result = judge.call_json(
        "evidence-binding-verifier",
        "system",
        {"bindings": []},
        expected_top_key="verdicts",
    )

    assert result == {"verdicts": verdicts}
    call_dir = next((tmp_path / "calls").iterdir())
    assert json.loads((call_dir / "raw-response.txt").read_text()) == verdicts
    metadata = json.loads((call_dir / "metadata.json").read_text())
    assert metadata["response_normalization"] == "wrap_bare_verdicts_array"


def test_wraps_bare_claims_array_without_editing_items(tmp_path):
    claims = [
        {
            "segment_id": "s_0001",
            "raw_text": "The product costs $40.",
            "normalized_claim": "The product costs $40.",
        }
    ]
    judge = AuditedJudge(
        tmp_path / "calls",
        judge_call=lambda *_args: (json.dumps(claims), None),
    )

    result = judge.call_json(
        "claim-proposal",
        "system",
        {"spans": []},
        expected_top_key="claims",
    )

    assert result == {"claims": claims}
    call_dir = next((tmp_path / "calls").iterdir())
    metadata = json.loads((call_dir / "metadata.json").read_text())
    assert metadata["response_normalization"] == "wrap_bare_claims_array"


def test_does_not_wrap_bare_array_for_an_unrelated_schema(tmp_path):
    raw = json.dumps([{"item_id": "i_1"}])
    judge = AuditedJudge(
        tmp_path / "calls",
        judge_call=lambda *_args: (raw, None),
    )

    with pytest.raises(RuntimeError, match="lacks top-level key"):
        judge.call_json(
            "compiler",
            "system",
            {"items": []},
            expected_top_key="items",
        )


def test_call_level_max_tokens_override_is_audited(tmp_path):
    observed: dict[str, int] = {}

    def fake_call(_system, _user, _model, max_tokens, _temperature):
        observed["max_tokens"] = max_tokens
        return '{"decisions":[]}', None

    judge = AuditedJudge(
        tmp_path / "calls",
        max_tokens=8192,
        judge_call=fake_call,
    )
    judge.call_json(
        "semantic-dedup",
        "system",
        {"claims": []},
        expected_top_key="decisions",
        max_tokens=6000,
        compact_payload=True,
    )

    assert observed["max_tokens"] == 6000
    call_dir = next((tmp_path / "calls").iterdir())
    request = json.loads((call_dir / "request.json").read_text())
    metadata = json.loads((call_dir / "metadata.json").read_text())
    assert request["max_tokens"] == 6000
    assert request["user"] == '{"claims":[]}'
    assert metadata["max_tokens"] == 6000
    assert metadata["payload_serialization"] == "compact_json"


def test_response_schema_is_bound_into_request_and_metadata(tmp_path):
    schema = {
        "type": "object",
        "properties": {"verdicts": {"type": "array", "maxItems": 1}},
        "required": ["verdicts"],
        "additionalProperties": False,
    }
    judge = AuditedJudge(
        tmp_path / "calls",
        judge_call=lambda *_args: ('{"verdicts":[]}', None),
    )
    judge.call_json(
        "bounded-output",
        "system",
        {"items": []},
        expected_top_key="verdicts",
        response_schema=schema,
    )

    call_dir = next((tmp_path / "calls").iterdir())
    request = json.loads((call_dir / "request.json").read_text())
    metadata = json.loads((call_dir / "metadata.json").read_text())
    assert request["response_schema"] == schema
    assert isinstance(metadata["response_schema_sha256"], str)
    assert len(metadata["response_schema_sha256"]) == 64
