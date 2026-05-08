"""V2 vs V1 leaderboard validation — Stage 6.

Re-scores the 30-task common subset under the V2 pipeline (BaseAgent +
canonical citation extractor + canonical composite formulas) and diffs
against the frozen V1 leaderboard. Exits non-zero if any agent's V3 Elo
drifts more than the threshold.

Usage:
    # 1. Snapshot V1 (do once, before deleting any V1 code)
    python -m scripts.migrate_validate --snapshot-v1

    # 2. Re-run all agents through V2, write to data/results/deep_v2/
    python -m scripts.migrate_validate --rescore-v2

    # 3. Compare
    python -m scripts.migrate_validate --diff
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

V1_DIR = ROOT / "data/results/deep_v3"
V2_DIR = ROOT / "data/results/deep_v2"
SNAPSHOT_PATH = ROOT / "data/results/LEADERBOARD_DEEP_v1_snapshot.json"

ELO_DRIFT_THRESHOLD = 10.0
REACH_DRIFT_PER_TASK = 0.05
COMPOSITE_DRIFT_TOTAL = 0.02


def _build_leaderboard(results_dir: Path) -> dict:
    """Run build_deep_leaderboard with DEEP_RESULTS_DIR override and return its
    JSON output."""
    env = dict(os.environ)
    env["DEEP_RESULTS_DIR"] = str(results_dir.relative_to(ROOT))
    rc = os.system(f"DEEP_RESULTS_DIR={env['DEEP_RESULTS_DIR']} "
                   f"python3 {ROOT}/scripts/build_deep_leaderboard.py >/dev/null 2>&1")
    if rc != 0:
        sys.exit(f"build_deep_leaderboard failed for {results_dir}")
    out_path = results_dir / "leaderboard_deep.json"
    return json.loads(out_path.read_text())


def snapshot_v1() -> None:
    """Lock the current V1 leaderboard before any V2 changes touch the data."""
    if not V1_DIR.exists():
        sys.exit(f"V1 dir {V1_DIR} not found")
    lb = _build_leaderboard(V1_DIR)
    SNAPSHOT_PATH.write_text(json.dumps(lb, indent=2))
    print(f"snapshot written: {SNAPSHOT_PATH.relative_to(ROOT)}")
    elo = lb.get("composite_v2_truthful", {}).get("elo", {})
    for agent, row in sorted(elo.items(), key=lambda kv: -kv[1].get("elo", 0)):
        print(f"  {agent:<24} {row.get('elo'):.0f}")


def rescore_v2(tasks: str, agents: Optional[list[str]] = None) -> None:
    """Re-run every (agent, task) under the V2 path: BaseAgent.run() →
    score_deep_answer.py → write to V2_DIR. Skips any (agent, task) that
    already has a V2 score file (resumable)."""
    from integrations.agents import REGISTRY, get_agent_class
    from integrations.agents.base import AgentServices

    V2_DIR.mkdir(parents=True, exist_ok=True)
    task_ids = _parse_task_range(tasks)
    target_agents = agents or [s for s in REGISTRY if not s.startswith("baseline-")]

    services = AgentServices(
        search_url=os.environ.get("SHIM_URL", "http://localhost:8081"),
        llm_url=os.environ.get("LLM_URL", "http://localhost:8081/llm/v1"),
        llm_key=os.environ.get("LLM_KEY", "any"),
        sandbox_hosts={
            "shopping": "localhost:7770",
            "reddit":   "localhost:9999",
            "wiki":     "localhost:8090",
        },
        model=os.environ.get("DR_MODEL", "deepseek-v4-flash"),
    )

    for slug in target_agents:
        cls = get_agent_class(slug)
        agent = cls()
        for tid in task_ids:
            md_path = V2_DIR / f"{slug}__{tid}_matrix.md"
            score_path = md_path.with_suffix(".score.json")
            if score_path.exists():
                continue   # resumable
            t0 = time.time()
            intent = _load_intent(tid)
            try:
                result = asyncio.run(agent.run(intent, services))
            except Exception as e:
                err_path = md_path.with_suffix(".md.error")
                err_path.write_text(f"{type(e).__name__}: {e}")
                print(f"[{slug}/{tid}] ERROR {type(e).__name__}: {e}")
                continue
            if result.error:
                md_path.with_suffix(".md.error").write_text(result.error)
                print(f"[{slug}/{tid}] runner-error: {result.error[:120]}")
                continue
            md_path.write_text(result.markdown)
            os.system(
                f"python3 {ROOT}/scripts/score_deep_answer.py "
                f"--task {tid} --answer {md_path} --out {score_path} "
                f">/dev/null 2>&1"
            )
            elapsed = time.time() - t0
            print(f"[{slug}/{tid}] {elapsed:.0f}s -> {score_path.name}")


def diff() -> int:
    if not SNAPSHOT_PATH.exists():
        sys.exit("no V1 snapshot — run --snapshot-v1 first")
    if not V2_DIR.exists():
        sys.exit(f"no V2 results — run --rescore-v2 first")
    v1 = json.loads(SNAPSHOT_PATH.read_text())
    v2 = _build_leaderboard(V2_DIR)

    elo_v1 = v1.get("composite_v2_truthful", {}).get("elo", {})
    elo_v2 = v2.get("composite_v2_truthful", {}).get("elo", {})
    print(f"\n{'agent':<24} {'V1 Elo':>8} {'V2 Elo':>8} {'Δ':>7}")
    print("-" * 52)
    fails = 0
    for agent in sorted(set(elo_v1) | set(elo_v2)):
        e1 = elo_v1.get(agent, {}).get("elo")
        e2 = elo_v2.get(agent, {}).get("elo")
        if e1 is None or e2 is None:
            print(f"  {agent:<24} {'(missing)' if e1 is None else f'{e1:.0f}':>8} "
                  f"{'(missing)' if e2 is None else f'{e2:.0f}':>8} {'?':>7}")
            fails += 1
            continue
        delta = e2 - e1
        flag = " " if abs(delta) < ELO_DRIFT_THRESHOLD else "✗"
        if abs(delta) >= ELO_DRIFT_THRESHOLD:
            fails += 1
        print(f"{flag} {agent:<24} {e1:>8.0f} {e2:>8.0f} {delta:>+7.1f}")

    if fails:
        print(f"\n✗ {fails} agent(s) drift > {ELO_DRIFT_THRESHOLD} Elo — investigate before locking V2")
        return 2
    print(f"\n✓ all agents within ±{ELO_DRIFT_THRESHOLD} Elo of V1")
    return 0


def _parse_task_range(s: str) -> list[str]:
    out: list[str] = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            for i in range(int(lo), int(hi) + 1):
                out.append(f"dr_cross_deep_{i:04d}")
        else:
            out.append(f"dr_cross_deep_{int(part):04d}")
    return out


def _load_intent(task_id: str) -> str:
    p = ROOT / "data/tasks/deep_research/cross_site_deep" / f"{task_id}.json"
    return json.loads(p.read_text()).get("intent", "")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-v1", action="store_true",
                    help="lock current V1 leaderboard")
    ap.add_argument("--rescore-v2", action="store_true",
                    help="run all agents under V2 pipeline")
    ap.add_argument("--tasks", default="0001-0030",
                    help="task range for rescore-v2")
    ap.add_argument("--agents", help="comma-separated agent slugs to rescore (default all)")
    ap.add_argument("--diff", action="store_true",
                    help="compare V2 to V1 snapshot; exit non-zero if any drift > threshold")
    args = ap.parse_args(argv)

    if args.snapshot_v1:
        snapshot_v1()
    if args.rescore_v2:
        agents = args.agents.split(",") if args.agents else None
        rescore_v2(args.tasks, agents)
    if args.diff:
        return diff()
    if not (args.snapshot_v1 or args.rescore_v2 or args.diff):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
