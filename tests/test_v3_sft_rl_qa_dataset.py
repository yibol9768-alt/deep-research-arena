from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.tasks.benchmark_sft_dataset_v3 import DatasetBuildError
from src.tasks.sft_rl_qa_dataset_v3 import (
    BuildOptions,
    _jsonl_bytes,
    _score_summary,
    build_sft_rl_qa_dataset,
)


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "data/pilot_v3/formal_candidates"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_sft_rl_export_requires_explicit_overlap_acknowledgement(tmp_path: Path):
    with pytest.raises(DatasetBuildError, match="allow_intentional_overlap"):
        build_sft_rl_qa_dataset(
            CANDIDATES,
            tmp_path / "out",
            options=BuildOptions(allow_synthetic=True),
        )


def test_jsonl_escapes_unicode_record_separators():
    raw = _jsonl_bytes([{"text": "a\u0085b\u2028c\u2029d"}])
    assert raw.count(b"\n") == 1
    assert b"\\u0085" in raw
    assert b"\\u2028" in raw
    assert b"\\u2029" in raw
    assert json.loads(raw.decode("utf-8"))["text"] == "a\u0085b\u2028c\u2029d"


def test_reward_summary_keeps_components_separate_and_applies_grounding_gate():
    clean = _score_summary(
        {
            "status": "scored",
            "partial_completion": 0.75,
            "full_pass": 0,
            "fabricated_citations": 0,
            "critical_contradictions": 0,
        }
    )
    fabricated = _score_summary(
        {
            "status": "scored",
            "partial_completion": 1.0,
            "full_pass": 0,
            "fabricated_citations": 1,
            "critical_contradictions": 0,
        }
    )
    assert clean["partial_completion"] == 0.75
    assert clean["grounding_gate_pass"] is True
    assert fabricated["partial_completion"] == 1.0
    assert fabricated["grounding_gate_pass"] is False


def test_current_validated_suites_build_complete_sft_and_rl_views(tmp_path: Path):
    output = tmp_path / "out"
    manifest = build_sft_rl_qa_dataset(
        CANDIDATES,
        output,
        options=BuildOptions(
            allow_synthetic=True,
            allow_intentional_overlap=True,
        ),
    )
    counts = manifest["counts"]
    assert counts["source_cases"] == 31
    assert counts["sft_full_qa"] == 31
    assert counts["proof_evidence"] == 440
    assert counts["proof_bridge"] == 195
    assert counts["proof_decision"] == 31
    assert counts["sft_proof_qa"] == 666
    assert counts["sft_all"] == 697
    assert counts["rl_oracle_positive"] == 31
    assert counts["rl_adversarial_negative"] == 310
    assert counts["rl_scored_qa"] == 341
    assert counts["rl_preference_pairs"] == 310

    full = _rows(output / "sft_full_qa.jsonl")
    proof = _rows(output / "sft_proof_qa.jsonl")
    rl_rows = _rows(output / "rl_scored_qa.jsonl")
    pairs = _rows(output / "rl_preference_pairs.jsonl")
    assert all(row["question"].strip() and row["answer"].strip() for row in full)
    assert all(row["question"].strip() and row["answer"].strip() for row in proof)
    assert all(
        row["score"]["full_pass"] == 1
        for row in rl_rows
        if row["candidate_kind"] == "oracle"
    )
    assert all(
        row["score"]["full_pass"] == 0
        for row in rl_rows
        if row["candidate_kind"] == "adversarial"
    )
    assert all(
        row["chosen_score"]["full_pass"] == 1
        and row["rejected_score"]["full_pass"] == 0
        for row in pairs
    )

