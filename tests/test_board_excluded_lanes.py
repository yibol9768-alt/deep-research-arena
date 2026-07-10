"""Structurally-unrunnable lanes are disclosed, not silently absent (ruling #12).

codex declares a protocol but runs `codex exec` over SSH; under the enforced
isolation boundary it can never satisfy remote_enforced(), so it is always
absent from the board. "Never ran" must be distinguishable from "ran and did
poorly": the lane is marked runnable:false in the protocol and the board
publishes its machine-readable excluded_reason in an excluded_lanes block. The
README's lane-count claim names the runnable set and the exclusion.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_truth_board import _excluded_lanes  # noqa: E402

TID = "dr_cross_deep_0001"


def test_excluded_lanes_names_codex_with_isolation_reason():
    excl = _excluded_lanes()
    assert "codex" in excl, "codex must be marked runnable:false in lane_protocol"
    reason = excl["codex"]
    assert reason["kind"] == "isolation_boundary"
    assert reason["code"] == "remote_isolation_unrunnable"
    assert reason["human_en"] and reason["human_zh"]


def test_board_json_carries_excluded_lanes(tmp_path):
    reports = tmp_path / "reports"
    (reports / "storm").mkdir(parents=True)
    (reports / "storm" / f"{TID}.md").write_text(
        "# F\n\nBluetooth ([s](http://localhost:8090/wiki/Bluetooth)).\n")
    out = tmp_path / "board.json"
    r = subprocess.run([
        sys.executable, "scripts/build_truth_board.py",
        "--reports-dir", str(reports), "--legacy-nested-layout",
        "--meta-dir", str(tmp_path), "--out", str(out),
        "--no-require-manifest", "--no-require-transport-pof",
        "--no-require-report-seals", "--no-require-verified-corpus",
        "--diagnostic",
    ], cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-500:]
    board = json.loads(out.read_text())
    assert "codex" in board["excluded_lanes"]
    assert board["excluded_lanes"]["codex"]["kind"] == "isolation_boundary"
    # An excluded lane must NOT appear as a scored 0-truth row.
    assert "codex" not in {row["agent"] for row in board["rows"]}


def test_readme_states_runnable_count_and_exclusion():
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split()).lower()
    assert "16 are runnable" in readme
    assert "excluded at the isolation boundary" in readme
