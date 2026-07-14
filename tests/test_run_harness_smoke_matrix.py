from __future__ import annotations

import json
import os
import sys

import pytest

from scripts import run_harness_smoke_matrix as smoke


def test_default_matrix_is_the_requested_twelve_harnesses():
    assert len(smoke.DEFAULT_HARNESSES) == 12
    assert len(set(smoke.DEFAULT_HARNESSES)) == 12
    assert {"deerflow", "qx-agents", "claude-code", "opencode"}.issubset(
        smoke.DEFAULT_HARNESSES
    )


def test_default_smoke_fuses_cover_native_qx_without_becoming_unbounded(
    monkeypatch,
):
    monkeypatch.setattr(sys, "argv", ["run_harness_smoke_matrix.py"])
    args = smoke._parse_args()
    assert args.max_calls == 256
    assert args.max_total_tokens == 750_000


def test_smoke_source_routes_separate_dial_address_from_public_identity():
    routes = smoke.SANDBOX_SOURCE_ENV
    assert routes["SHOPPING"] == "http://127.0.0.1:7770"
    assert routes["SHOPPING_PUBLIC"] == "http://localhost:7770"
    assert routes["REDDIT_PUBLIC"] == "http://localhost:9999"
    assert routes["KIWIX_PUBLIC"] == "http://localhost:8090"


@pytest.mark.skipif(os.geteuid() != 0, reason="production key file is root-owned")
def test_client_env_parser_never_needs_to_source_a_shell(tmp_path):
    path = tmp_path / "client.env"
    path.write_text("# comment\nexport OPENAI_API_KEY='secret-value'\n")
    path.chmod(0o600)
    assert smoke._read_client_key(path) == "secret-value"


def test_summary_collects_score_and_unpriced_usage(tmp_path):
    model = "gpt-5.6-luna"
    task = "dr_cross_deep_0010"
    harness = "camel-ai"
    run_dir = tmp_path / "results" / "rs" / model
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "scores").mkdir()
    (run_dir / "raw" / f"{harness}__{task}_rep1.md").write_text("report")
    (run_dir / "raw" / f"{harness}__{task}_rep1.meta.json").write_text(
        json.dumps({"status": "pass", "report_chars": 6})
    )
    (run_dir / "scores" / f"{harness}__{task}_rep1.score.json").write_text("{}")
    (run_dir / "api_costs.worker-100.json").write_text(json.dumps({
        "totals": {
            "n_calls": 3,
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "usage_missing_calls": 0,
            "cost": None,
            "cost_complete": False,
        }
    }))
    lane = smoke.Lane(
        harness=harness,
        index=0,
        worker_id=100,
        run_set_id="rs",
        queue=tmp_path / "q.tsv",
        run_dir=run_dir,
        shim_port=18401,
        dsproxy_port=18501,
        egress_port=18199,
        qx_port=19100,
        shim_log=tmp_path / "shim.log",
        dsproxy_log=tmp_path / "ds.log",
        worker_log=tmp_path / "worker.log",
        usage_log=tmp_path / "usage.jsonl",
        worker_rc=0,
    )

    summary = smoke._summarize("tag", model, task, [lane])
    assert summary["scoreable"] == 1
    assert summary["all_workers_zero"] is True
    assert summary["totals"]["n_calls"] == 3
    assert summary["totals"]["total_tokens"] == 120
    assert summary["totals"]["cost"] is None
