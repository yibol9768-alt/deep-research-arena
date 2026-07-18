from __future__ import annotations

import scripts.freeze_v2_legacy_baseline as freeze
from scripts.freeze_v2_legacy_baseline import build_manifest, verify_manifest


def test_v2_freeze_records_replay_identity_and_rejects_v3_comparability():
    doc = build_manifest()
    assert doc["schema"] == "dra-v2-legacy-baseline-v1"
    assert doc["protocols"]["task_version"] == 2
    assert doc["protocols"]["comparable_to_verified_slots_v1"] is False
    assert doc["counts"] == {
        "tasks": 100,
        "answer_keys": 100,
        "checklists": 100,
    }
    assert len(doc["files"]["tasks"]) == 100
    assert len(doc["files"]["answer_keys"]) == 100
    assert len(doc["files"]["checklists"]) == 100
    scoring = set(doc["files"]["scoring"])
    assert {
        "scripts/score_deep_answer.py",
        "scripts/build_truth_board.py",
        "src/verifiers/url_coverage_verifier.py",
        "src/verifiers/url_reachability_verifier.py",
        "src/verifiers/quote_match_verifier.py",
        "src/verifiers/claim_nli_verifier.py",
        "src/verifiers/judge_client.py",
        "src/eval/answer_key.py",
    } <= scoring
    assert verify_manifest(doc) == []


def test_v2_freeze_detects_identity_drift():
    doc = build_manifest()
    doc["hashes"]["task_set"] = "tampered"
    assert "task/answer-key/checklist/scorer bytes changed" in verify_manifest(doc)


def test_v2_freeze_detects_score_entrypoint_byte_drift(monkeypatch):
    doc = build_manifest()
    original_sha = freeze._sha

    def changed_sha(path):
        if path.name == "score_deep_answer.py":
            return "0" * 64
        return original_sha(path)

    monkeypatch.setattr(freeze, "_sha", changed_sha)
    violations = verify_manifest(doc)
    assert "task/answer-key/checklist/scorer bytes changed" in violations
    assert "per-file identity changed" in violations
