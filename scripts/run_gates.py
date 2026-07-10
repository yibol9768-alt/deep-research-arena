#!/usr/bin/env python3
"""Run the workstation-runnable goal gates (docs/GOAL_GATES_V1.md) in order
and print one PASS / FAIL / SKIP(reason) line per gate.

Currently wired: G1 (oracle tops out), G2 (shell zeroes), G3 (perturbation
must lose). The remaining gates are listed with an explicit SKIP reason so the
report always covers all seven; they flip to wired as their lanes land.

Usage:
    python3 scripts/run_gates.py            # full 100-task sweep (~10-15 min)
    python3 scripts/run_gates.py --quick    # 13-task subset (tuning runs)
    python3 scripts/run_gates.py --gates G1,G3

Exit code: 0 when every WIRED gate passes (skips do not fail the run),
1 otherwise. Deterministic: no network, no clock, no randomness.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# gate id -> (description, pytest node(s) or None, skip reason when not wired)
GATES: dict[str, tuple[str, list[str] | None, str]] = {
    "G0": ("协议对等与差异披露", None,
           "not wired in this lane (lane_protocol/check_parity lane)"),
    "G1": ("oracle 顶格(100 题)",
           ["tests/test_gate_oracle.py::test_g1_oracle_reach_tops_out",
            "tests/test_gate_oracle.py::test_g1_oracle_fact_axis_positive",
            "tests/test_gate_oracle.py::test_g1_oracle_structured_share_fully_covered",
            "tests/test_gate_oracle.py::test_g1_oracle_concept_share_fully_covered",
            "tests/test_gate_oracle.py::test_g1_oracle_completeness_equals_achievable_ceiling",
            "tests/test_gate_oracle.py::test_g1_oracle_completeness_literal_one"],
           ""),
    "G2": ("空壳归零(100 题)",
           ["tests/test_gate_oracle.py::test_g2_shell_scores_zero_on_every_axis",
            "tests/test_gate_oracle.py::test_g2_shell_zero_is_observed_not_withheld"],
           ""),
    "G3": ("扰动必降",
           ["tests/test_gate_perturbation.py"],
           ""),
    "G4": ("withhold 不打 0", None,
           "not wired in this lane (withhold-path enumeration lane)"),
    "G5": ("箱上 preflight 真实通过", None,
           "box-only: requires the my5090 sandbox, cannot run on the workstation"),
    "G6": ("端到端冒烟无静默零", None,
           "not wired in this lane (needs live backbone endpoints)"),
}


def run_gate(gate: str, nodes: list[str], extra: list[str]) -> tuple[str, str]:
    """Run one gate's pytest nodes; returns (status, detail)."""
    cmd = [sys.executable, "-m", "pytest", "-q", "--run-gates",
           *nodes, *extra]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    dt = time.time() - t0
    tail = "\n".join((proc.stdout or "").strip().splitlines()[-15:])
    if proc.returncode == 0:
        return "PASS", f"{dt:.0f}s\n{tail}"
    # pytest rc 5 == no tests collected
    if proc.returncode == 5:
        return "SKIP", f"no tests collected ({dt:.0f}s)\n{tail}"
    return "FAIL", f"rc={proc.returncode} {dt:.0f}s\n{tail}\n" \
        + "\n".join((proc.stderr or "").strip().splitlines()[-5:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true",
                    help="13-task subset (sets DRA_GATES_TASK_LIMIT=13)")
    ap.add_argument("--task-limit", type=int, default=0,
                    help="explicit task cap (overrides --quick)")
    ap.add_argument("--gates", default="",
                    help="comma-separated subset, e.g. G1,G3 (default: all)")
    args = ap.parse_args()

    if args.task_limit > 0:
        os.environ["DRA_GATES_TASK_LIMIT"] = str(args.task_limit)
    elif args.quick:
        os.environ["DRA_GATES_TASK_LIMIT"] = "13"

    wanted = [g.strip().upper() for g in args.gates.split(",") if g.strip()] \
        or list(GATES)
    limit = os.environ.get("DRA_GATES_TASK_LIMIT")
    print(f"== run_gates: tasks={'first ' + limit if limit else 'all 100'} "
          f"gates={','.join(wanted)} ==\n", flush=True)

    results: dict[str, tuple[str, str]] = {}
    failed = False
    for gate in wanted:
        if gate not in GATES:
            print(f"{gate}: SKIP (unknown gate id)")
            continue
        desc, nodes, skip_reason = GATES[gate]
        if nodes is None:
            results[gate] = ("SKIP", skip_reason)
            print(f"{gate} [{desc}]: SKIP ({skip_reason})", flush=True)
            continue
        print(f"{gate} [{desc}]: running ...", flush=True)
        status, detail = run_gate(gate, nodes, [])
        results[gate] = (status, detail)
        print(f"{gate} [{desc}]: {status} ({detail.splitlines()[0]})", flush=True)
        if status == "FAIL":
            failed = True
            print("  " + "\n  ".join(detail.splitlines()[1:]), flush=True)

    print("\n== summary ==")
    for gate, (status, detail) in results.items():
        line = f"{gate}: {status}"
        if status == "SKIP":
            line += f" ({detail.splitlines()[0]})"
        print(line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
