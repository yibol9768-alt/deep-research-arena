from __future__ import annotations

import json
from pathlib import Path

from scripts.profile_qwen_judge_run import build_profile, read_call_records


def _write_call(
    root: Path,
    *,
    harness: str,
    stage_group: str,
    name: str,
    cache_hit: bool,
    timestamp: str,
) -> None:
    call_dir = root / harness / "03-score" / "judge_calls" / stage_group / name
    call_dir.mkdir(parents=True)
    (call_dir / "request.json").write_text(
        json.dumps({"system": "sys", "user": "payload"}),
        encoding="utf-8",
    )
    (call_dir / "raw-response.txt").write_text("{}", encoding="utf-8")
    (call_dir / "metadata.json").write_text(
        json.dumps(
            {
                "schema": "dra_audited_judge_call_v1",
                "stage": name,
                "timestamp_utc": timestamp,
                "cache_hit": cache_hit,
                "error": None,
            }
        ),
        encoding="utf-8",
    )


def test_profile_separates_logical_fresh_and_cache(tmp_path: Path) -> None:
    _write_call(
        tmp_path,
        harness="alpha",
        stage_group="fact",
        name="fact-001",
        cache_hit=False,
        timestamp="2026-07-30T00:00:00+00:00",
    )
    _write_call(
        tmp_path,
        harness="alpha",
        stage_group="fact",
        name="fact-002",
        cache_hit=True,
        timestamp="2026-07-30T00:00:01+00:00",
    )
    _write_call(
        tmp_path,
        harness="beta",
        stage_group="rubric",
        name="rubric-001",
        cache_hit=False,
        timestamp="2026-07-30T00:00:08+00:00",
    )

    records, warnings = read_call_records(tmp_path)
    profile = build_profile(tmp_path, records, warnings)

    assert profile["harness_count"] == 2
    assert profile["overall"]["logical_calls"] == 3
    assert profile["overall"]["fresh_calls"] == 2
    assert profile["overall"]["cache_hits"] == 1
    assert profile["overall"]["cache_hit_rate"] == 1 / 3
    assert profile["overall"]["fresh_window_seconds"] == 8.0
    assert profile["overall"]["fresh_mean_spacing_seconds"] == 8.0
    assert profile["overall"]["logical_input_chars"] == 30
    assert profile["overall"]["fresh_input_chars"] == 20


def test_profile_ignores_unrelated_metadata(tmp_path: Path) -> None:
    unrelated = tmp_path / "other" / "metadata.json"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text(json.dumps({"schema": "something_else"}), encoding="utf-8")
    _write_call(
        tmp_path,
        harness="alpha",
        stage_group="evidence",
        name="evidence-001",
        cache_hit=False,
        timestamp="2026-07-30T00:00:00Z",
    )

    records, warnings = read_call_records(tmp_path)

    assert warnings == []
    assert len(records) == 1
    assert records[0].harness == "alpha"
    assert records[0].stage_group == "evidence"
