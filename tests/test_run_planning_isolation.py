from __future__ import annotations

import json

from scripts.plan_full_leaderboard import _score_is_resumable


def test_resume_rejects_score_from_other_backbone(tmp_path):
    score = tmp_path / "x.score.json"
    meta = tmp_path / "x.meta.json"
    score.write_text("{}")
    meta.write_text(json.dumps({
        "status": "pass", "backbone": "deepseek-v4",
        "report_seal": {"sha256": "abc"},
    }))
    # A legacy sidecar with no run-set/replicate/manifest binding is not a
    # cache hit even when its backbone label happens to match.
    assert not _score_is_resumable(score, meta, "qwen3-8b")
    assert not _score_is_resumable(score, meta, "deepseek-v4")


def test_resume_requires_pass_meta_and_report_seal(tmp_path):
    score = tmp_path / "x.score.json"
    meta = tmp_path / "x.meta.json"
    score.write_text("{}")
    meta.write_text(json.dumps({"status": "fail", "backbone": "m"}))
    assert not _score_is_resumable(score, meta, "m")
