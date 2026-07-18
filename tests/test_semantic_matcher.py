from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.eval.semantic_matcher import (
    _validate_results,
    build_targets,
    semantic_index,
)


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = (
    ROOT
    / "data/golden/cases_v3/development/dra_v3_dev_audio_0002.json"
)


def test_build_targets_covers_steps_conclusion_and_rejected_claims() -> None:
    case = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    targets = build_targets(case)
    ids = {target["target_id"] for target in targets}
    assert {f"E{i}" for i in range(1, 11)} <= ids
    assert {"B1", "B2", "B3", "B4", "D1"} <= ids
    assert "D1::conclusion::soundcore_flare2" in ids
    assert len([target for target in targets if target["kind"] == "rejected_claim"]) == 3
    assert all(target["alternatives"] for target in targets)


def test_positive_verdict_without_exact_quote_fails_closed() -> None:
    report = "The report recommends Alpha after comparing the evidence."
    targets = [{"target_id": "D1", "kind": "decision", "alternatives": ["Choose Alpha."]}]
    raw = {
        "results": [{
            "target_id": "D1",
            "verdict": "entailed",
            "matched_quote": "a paraphrase not copied from the report",
            "reason": "semantic match",
        }]
    }
    row = _validate_results(report, targets, raw)[0]
    assert row["verdict"] == "ambiguous"
    assert row["matched_quote"] is None
    assert row["start"] is None


def test_semantic_index_rejects_report_hash_mismatch() -> None:
    artifact = {"report_sha256": "0" * 64, "results": []}
    with pytest.raises(ValueError, match="report SHA-256 mismatch"):
        semantic_index(artifact, "different report")


def test_exact_quote_gets_auditable_offsets() -> None:
    report = "First sentence. The report recommends Alpha. End."
    quote = "The report recommends Alpha."
    targets = [{"target_id": "D1", "kind": "decision", "alternatives": ["Choose Alpha."]}]
    raw = {
        "results": [{
            "target_id": "D1",
            "verdict": "entailed",
            "matched_quote": quote,
            "reason": "explicit recommendation",
        }]
    }
    row = _validate_results(report, targets, raw)[0]
    assert report[row["start"] : row["end"]] == quote
