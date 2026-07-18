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
    assert args.harness_max_calls == []
    assert args.max_total_tokens == 750_000
    assert args.unlimited_token_harness == []
    assert args.score_timeout_s == 1800
    assert args.upstream_retry_max_attempts == 8
    assert args.price_namespace is None
    assert args.price_key is None


def test_one_harness_can_receive_unlimited_tokens_without_disabling_call_fuse(
    monkeypatch,
):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_harness_smoke_matrix.py",
            "--unlimited-token-harness",
            "langchain-odr",
        ],
    )
    args = smoke._parse_args()
    assert args.unlimited_token_harness == ["langchain-odr"]
    assert args.max_calls == 256
    assert args.max_total_tokens == 750_000


def test_one_harness_can_receive_a_larger_call_fuse():
    assert smoke._parse_call_overrides(["langchain-odr=512"]) == {
        "langchain-odr": 512,
    }


def test_provider_namespace_prices_backbone_and_auxiliary_scoring_models(
    monkeypatch,
):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_harness_smoke_matrix.py",
            "--price-namespace",
            "deepseek-official",
        ],
    )
    args = smoke._parse_args()
    assert smoke._pricing_env(
        price_namespace=args.price_namespace,
        price_key=args.price_key,
    ) == {"DRA_COST_PRICE_NAMESPACE": "deepseek-official"}


def test_pricing_env_refuses_ambiguous_contract():
    with pytest.raises(ValueError, match="mutually exclusive"):
        smoke._pricing_env(price_namespace="provider", price_key="model@provider")


@pytest.mark.parametrize(
    "value",
    ["unknown=512", "langchain-odr", "langchain-odr=bad", "langchain-odr=-1"],
)
def test_harness_call_override_rejects_malformed_values(value):
    with pytest.raises(ValueError):
        smoke._parse_call_overrides([value])


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
    assert summary["totals"]["pricing_status"] == "unpriced"


def test_summary_sums_complete_provider_priced_ledgers(tmp_path):
    model = "deepseek-v4-flash"
    task = "dr_cross_deep_0010"
    harness = "storm"
    run_dir = tmp_path / "results" / "rs" / model
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "scores").mkdir()
    (run_dir / "raw" / f"{harness}__{task}_rep1.md").write_text("report")
    (run_dir / "raw" / f"{harness}__{task}_rep1.meta.json").write_text(
        json.dumps({"status": "pass", "report_chars": 6})
    )
    (run_dir / "scores" / f"{harness}__{task}_rep1.score.json").write_text("{}")
    (run_dir / "api_costs.worker-111.json").write_text(json.dumps({
        "totals": {
            "n_calls": 53,
            "prompt_tokens": 51_350,
            "completion_tokens": 17_290,
            "total_tokens": 68_640,
            "usage_missing_calls": 0,
            "cost": 0.077704,
            "cost_currency": "CNY",
            "cost_complete": True,
        }
    }))
    lane = smoke.Lane(
        harness=harness,
        index=11,
        worker_id=111,
        run_set_id="rs",
        queue=tmp_path / "q.tsv",
        run_dir=run_dir,
        shim_port=18412,
        dsproxy_port=18512,
        egress_port=18210,
        qx_port=19111,
        shim_log=tmp_path / "shim.log",
        dsproxy_log=tmp_path / "ds.log",
        worker_log=tmp_path / "worker.log",
        usage_log=tmp_path / "usage.jsonl",
        worker_rc=0,
    )

    summary = smoke._summarize("tag", model, task, [lane])
    assert summary["totals"]["cost"] == 0.077704
    assert summary["totals"]["known_cost"] == 0.077704
    assert summary["totals"]["cost_currency"] == "CNY"
    assert summary["totals"]["cost_complete"] is True
    assert summary["totals"]["pricing_status"] == "complete"


def test_summary_excludes_probe_and_judge_usage_from_harness_cost(tmp_path):
    model = "deepseek-v4-flash"
    task = "dr_cross_deep_0010"
    harness = "qx-agents"
    run_id = f"{harness}__{task}__{model}__run"
    run_dir = tmp_path / "results" / "rs" / model
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "scores").mkdir()
    (run_dir / "raw" / f"{harness}__{task}_rep1.md").write_text("report")
    (run_dir / "raw" / f"{harness}__{task}_rep1.meta.json").write_text(
        json.dumps({"status": "pass", "report_chars": 6, "run_id": run_id})
    )
    (run_dir / "scores" / f"{harness}__{task}_rep1.score.json").write_text("{}")
    (run_dir / "api_costs.worker-109.json").write_text(json.dumps({
        "totals": {
            "n_calls": 784,
            "prompt_tokens": 5_315_381,
            "completion_tokens": 177_447,
            "total_tokens": 5_492_828,
            "usage_missing_calls": 0,
            "cost": 2.263216,
            "cost_currency": "CNY",
            "cost_complete": True,
        },
        "runs": [
            {
                "run_id": "_untagged",
                "n_calls": 195,
                "prompt_tokens": 178_714,
                "completion_tokens": 6_281,
                "total_tokens": 184_995,
                "usage_missing_calls": 0,
                "cost": 0.273331,
                "cost_currency": "CNY",
                "cost_complete": True,
            },
            {
                "run_id": run_id,
                "n_calls": 589,
                "prompt_tokens": 5_136_667,
                "completion_tokens": 171_166,
                "total_tokens": 5_307_833,
                "usage_missing_calls": 0,
                "cost": 1.989885,
                "cost_currency": "CNY",
                "cost_complete": True,
            },
        ],
    }))
    lane = smoke.Lane(
        harness=harness,
        index=9,
        worker_id=109,
        run_set_id="rs",
        queue=tmp_path / "q.tsv",
        run_dir=run_dir,
        shim_port=18410,
        dsproxy_port=18510,
        egress_port=18208,
        qx_port=19109,
        shim_log=tmp_path / "shim.log",
        dsproxy_log=tmp_path / "ds.log",
        worker_log=tmp_path / "worker.log",
        usage_log=tmp_path / "usage.jsonl",
        worker_rc=0,
    )

    summary = smoke._summarize("tag", model, task, [lane])

    row = summary["agents"][harness]
    assert row["usage_scope"] == "formal_run"
    assert row["usage"]["n_calls"] == 589
    assert row["usage"]["cost"] == 1.989885
    assert row["worker_usage"]["n_calls"] == 784
    assert row["worker_usage"]["cost"] == 2.263216
    assert summary["totals"]["n_calls"] == 589
    assert summary["totals"]["cost"] == 1.989885
    assert summary["worker_totals"]["n_calls"] == 784
    assert summary["worker_totals"]["cost"] == 2.263216
