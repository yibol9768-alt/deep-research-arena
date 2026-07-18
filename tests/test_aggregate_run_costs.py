from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cost_ledger_totals_and_unpriced_status(tmp_path):
    log = tmp_path / "usage.jsonl"
    records = [
        {"model": "gpt-5.6-luna", "prompt_tokens": 100,
         "completion_tokens": 20, "total_tokens": 120, "ts": 1},
        {"non_call_event": True, "admission_wait": True,
         "wait_s": 2.5, "ts": 1.5},
        {"mark": True, "phase": "start", "run_id": "r1", "ts": 2},
        {"model": "gpt-5.6-luna", "prompt_tokens": 300,
         "completion_tokens": 40, "total_tokens": 340, "ts": 3},
        {"mark": True, "phase": "end", "run_id": "r1", "ts": 4},
    ]
    log.write_text("".join(json.dumps(row) + "\n" for row in records))
    out = tmp_path / "costs.json"

    result = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "aggregate_run_costs.py"),
            "--log", str(log), "--out", str(out),
            "--run-set-id", "rs", "--backbone", "gpt-5.6-luna",
            "--worker", "7",
        ],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    doc = json.loads(out.read_text())
    assert doc["run_set_id"] == "rs" and doc["worker"] == "7"
    assert doc["totals"] == {
        "n_calls": 2,
        "prompt_tokens": 400,
        "completion_tokens": 60,
        "total_tokens": 460,
        "usage_missing_calls": 0,
        "known_cost": 0,
        "cost_currency": None,
        "cost_complete": False,
        "cost": None,
        "pricing_status": "unpriced",
    }


def test_provider_price_key_uses_exact_cache_hit_and_miss_split(tmp_path):
    log = tmp_path / "usage.jsonl"
    records = [
        {"mark": True, "phase": "start", "run_id": "r1", "ts": 1},
        {
            "model": "deepseek-v4-flash",
            "prompt_tokens": 100_000,
            "prompt_cache_hit_tokens": 20_000,
            "prompt_cache_miss_tokens": 80_000,
            "completion_tokens": 10_000,
            "total_tokens": 110_000,
            "ts": 2,
        },
        {"mark": True, "phase": "end", "run_id": "r1", "ts": 3},
    ]
    log.write_text("".join(json.dumps(row) + "\n" for row in records))
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps({
        "prices": {
            "deepseek-official": {
                "input_cache_hit_per_mtok": 0.0028,
                "input_cache_miss_per_mtok": 0.14,
                "output_per_mtok": 0.28,
                "currency": "USD",
            }
        },
        "aliases": {},
    }))
    out = tmp_path / "costs.json"

    result = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "aggregate_run_costs.py"),
            "--log", str(log), "--prices", str(prices), "--out", str(out),
            "--backbone", "deepseek-v4-flash",
            "--price-key", "deepseek-official",
        ],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    doc = json.loads(out.read_text())
    assert doc["price_key"] == "deepseek-official"
    assert doc["totals"]["cost"] == 0.014056
    assert doc["totals"]["cost_currency"] == "USD"
    assert doc["totals"]["cost_complete"] is True
    model = doc["runs"][0]["per_model"]["deepseek-v4-flash"]
    assert model["prompt_cache_hit_tokens"] == 20_000
    assert model["prompt_cache_miss_tokens"] == 80_000
    assert model["cache_usage_missing_calls"] == 0


def test_provider_namespace_prices_auxiliary_judge_model(tmp_path):
    log = tmp_path / "usage.jsonl"
    records = [
        {
            "model": "deepseek-v4-flash",
            "prompt_tokens": 2546,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 2546,
            "completion_tokens": 170,
            "total_tokens": 2716,
        },
        {
            "model": "deepseek-v4-pro",
            "prompt_tokens": 1890,
            "prompt_cache_hit_tokens": 640,
            "prompt_cache_miss_tokens": 1250,
            "completion_tokens": 46,
            "total_tokens": 1936,
        },
    ]
    log.write_text("".join(json.dumps(row) + "\n" for row in records))
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps({"prices": {
        "deepseek-v4-flash@deepseek-official": {
            "input_cache_hit_per_mtok": 0.02,
            "input_cache_miss_per_mtok": 1.0,
            "output_per_mtok": 2.0,
            "currency": "CNY",
        },
        "deepseek-v4-pro@deepseek-official": {
            "input_cache_hit_per_mtok": 0.025,
            "input_cache_miss_per_mtok": 3.0,
            "output_per_mtok": 6.0,
            "currency": "CNY",
        },
    }}))
    out = tmp_path / "costs.json"

    result = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "aggregate_run_costs.py"),
            "--log", str(log), "--prices", str(prices), "--out", str(out),
            "--backbone", "deepseek-v4-flash",
            "--price-namespace", "deepseek-official",
        ],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    doc = json.loads(out.read_text())
    assert doc["price_namespace"] == "deepseek-official"
    assert doc["totals"]["cost"] == 0.006928
    assert doc["totals"]["cost_complete"] is True
    assert doc["totals"]["pricing_status"] == "complete"
