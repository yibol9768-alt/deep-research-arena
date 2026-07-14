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

