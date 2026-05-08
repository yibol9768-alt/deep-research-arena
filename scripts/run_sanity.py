"""Sanity-baseline runner: 3 baselines x 5 fixed tasks, sequential.

Generates each baseline's markdown report under
    data/results/sanity/<agent>__<task>_matrix.md

Does NOT score against the live judge (no network). Prints a summary table
with the report length per (agent, task); reach/qm/ck/ad/V3 columns are left
blank for the user to fill in by piping each .md through
    scripts/score_deep_answer.py
once shim+ds_proxy are running.

Usage:
    python3 scripts/run_sanity.py
    python3 scripts/run_sanity.py --agents random,stuffer
    python3 scripts/run_sanity.py --tasks dr_cross_deep_0001
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEEP_TASK_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
SANITY_OUT_DIR = ROOT / "data" / "results" / "sanity"
SANITY_OUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TASKS = [
    "dr_cross_deep_0001",
    "dr_cross_deep_0006",
    "dr_cross_deep_0009",
    "dr_cross_deep_0011",
    "dr_cross_deep_0012",
]
DEFAULT_AGENTS = ["random", "stuffer", "golden_dump"]


def _resolve_intent(task_cfg: dict) -> str:
    subs = {
        "__SHOPPING__":  os.environ.get("SHOPPING",  "http://localhost:7770"),
        "__REDDIT__":    os.environ.get("REDDIT",    "http://localhost:9999"),
        "__WIKIPEDIA__": os.environ.get("WIKIPEDIA", "http://localhost:8090"),
    }
    intent = task_cfg.get("intent", "")
    for k, v in subs.items():
        intent = intent.replace(k, v)
    return intent


def _load_task(task_id: str) -> dict:
    p = DEEP_TASK_DIR / f"{task_id}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


async def _run_one(agent: str, task_id: str, intent: str, model: str,
                   shim_url: str, proxy_url: str) -> tuple[Path, int, float, str | None]:
    from integrations.agents.baselines import BASELINES
    fn = BASELINES[agent]
    os.environ["_FLOWSEARCHER_TASK_ID"] = task_id  # used by random/golden_dump

    t0 = time.time()
    err: str | None = None
    try:
        report = await fn(intent=intent, model=model,
                          shim_url=shim_url, proxy_url=proxy_url)
    except Exception as exc:  # surface but don't abort the whole run
        report = f"(sanity baseline error: {type(exc).__name__}: {exc})"
        err = f"{type(exc).__name__}: {exc}"
    elapsed = time.time() - t0

    out_md = SANITY_OUT_DIR / f"{agent}__{task_id}_matrix.md"
    out_md.write_text(report or "(empty)")
    return out_md, len(report or ""), elapsed, err


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(DEFAULT_AGENTS),
                    help="Comma-separated agent names")
    ap.add_argument("--tasks", default=",".join(DEFAULT_TASKS),
                    help="Comma-separated task ids")
    ap.add_argument("--shim-url", default=os.environ.get("SHIM_URL",
                                                          "http://localhost:8081"))
    ap.add_argument("--proxy-url", default=os.environ.get("DS_PROXY_URL",
                                                           "http://localhost:8088/v1"))
    ap.add_argument("--model", default=os.environ.get("AGENT_LLM_MODEL",
                                                       "deepseek-v4-flash"))
    args = ap.parse_args()

    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]

    print(f"[sanity] agents={agents}")
    print(f"[sanity] tasks={tasks}")
    print(f"[sanity] shim={args.shim_url} proxy={args.proxy_url} model={args.model}")
    print(f"[sanity] out_dir={SANITY_OUT_DIR}\n")

    rows: list[dict] = []
    for agent in agents:
        for tid in tasks:
            cfg = _load_task(tid)
            intent = _resolve_intent(cfg) if cfg else ""
            if not intent:
                print(f"[sanity] SKIP {agent}/{tid} (no intent)")
                continue
            out_md, n_chars, elapsed, err = await _run_one(
                agent, tid, intent, args.model, args.shim_url, args.proxy_url,
            )
            status = "OK" if err is None else "ERR"
            print(f"[sanity] {status:3s} {agent:>11s}  {tid}  "
                  f"chars={n_chars:>7d}  t={elapsed:5.1f}s  -> {out_md.name}")
            if err:
                print(f"            err: {err}")
            rows.append({
                "agent": agent, "task": tid,
                "chars": n_chars, "elapsed_s": round(elapsed, 1),
                "out": out_md.name, "err": err,
            })

    # Summary table. Score columns are deliberately blank: the live judge
    # requires the shim/ds_proxy/sandbox stack and would route network calls,
    # so we let the user pipe each .md through scripts/score_deep_answer.py.
    print("\n=== SANITY SUMMARY ===")
    hdr = f"{'agent':<12} {'task':<22} {'chars':>7}  reach   qm    ck    ad   V3"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['agent']:<12} {r['task']:<22} {r['chars']:>7}  "
              f"  -     -     -     -    -")

    print("\nTo score one report:")
    print("  python3 scripts/score_deep_answer.py "
          "--task <task_id> --answer data/results/sanity/<agent>__<task>_matrix.md "
          "--out data/results/sanity/<agent>__<task>_matrix.score.json")
    return 0 if all(r["err"] is None for r in rows) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
