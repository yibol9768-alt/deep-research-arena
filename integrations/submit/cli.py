"""Submit your DR agent against the public benchmark.

Quick start
-----------
1. Bring up the sandbox locally:

    docker compose -f infra/sandbox.docker-compose.yml up -d
    export DEEPSEEK_API_KEY=sk-...   # required by ds_proxy

2. Implement BaseAgent in your own package (see integrations/agents/base.py
   docstring for a 30-line example).

3. Run:

    python -m integrations.submit my_pkg.MyAgent --tasks 0001-0005
    # or, for a registered framework:
    python -m integrations.submit --agent storm --tasks 0001-0005

The submitter runs your agent against each task, scores the resulting
markdown with `scripts/score_deep_answer.py`, and prints a leaderboard
preview row showing where you would land vs. the published v1 corpus.

Output
------
* per-task scores written to data/results/submitted/<agent>__<task>.md(score.json)
* summary table to stdout
* aggregate V3-Elo (vs frozen public leaderboard) printed at the end

This file is intentionally simple — it composes existing
`scripts/run_deep_task.py` + `scripts/score_deep_answer.py` machinery
through the BaseAgent contract.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]


def _load_agent_class(spec: str):
    """Resolve "module.path.ClassName" or registered slug to a BaseAgent class."""
    if "." in spec and not spec.startswith("baseline-"):
        module_path, _, cls = spec.rpartition(".")
        mod = importlib.import_module(module_path)
        return getattr(mod, cls)
    # Registered slug
    from integrations.agents import REGISTRY, get_agent_class
    if spec not in REGISTRY:
        sys.exit(f"unknown agent {spec!r}; registered: {sorted(REGISTRY)}")
    return get_agent_class(spec)


def _parse_task_range(s: str) -> list[str]:
    """``"0001-0005,0011"`` → list of task ids."""
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


async def _run_one(agent, task_id: str, services) -> dict:
    """Run the agent, score the result, return a row dict."""
    # Some baselines (random, golden_dump) need the task id in env to load
    # the per-task golden pool. The harness sets this; we mirror it here so
    # standalone `python -m integrations.submit` also works.
    os.environ["_FLOWSEARCHER_TASK_ID"] = task_id

    t0 = time.time()
    result = await agent.run(intent=_load_intent(task_id), services=services)
    elapsed = time.time() - t0
    out_dir = ROOT / "data" / "results" / "submitted"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{agent.name}__{task_id}_matrix.md"
    if result.error:
        err_path = md_path.with_suffix(".md.error")
        err_path.write_text(result.error)
        return {
            "task": task_id, "agent": agent.name,
            "error": result.error, "elapsed_s": round(elapsed, 1),
            "skipped_scoring": True,
        }
    md_path.write_text(result.markdown)
    score_path = md_path.with_suffix(".score.json")
    # Use the same Python interpreter that's running this CLI so judge_client
    # finds the same openai/anthropic SDKs the agent venv installed.
    rc = os.system(
        f"{sys.executable} {ROOT}/scripts/score_deep_answer.py "
        f"--task {task_id} --answer {md_path} --out {score_path}"
    )
    score = json.loads(score_path.read_text()) if score_path.exists() else {}
    return {
        "task": task_id, "agent": agent.name,
        "elapsed_s": round(elapsed, 1),
        "reach": score.get("url_reachability", {}).get("score", 0),
        "qm":    score.get("quote_match", {}).get("score", 0),
        "ck":    score.get("checklist", {}).get("pass_rate", 0),
        "ad":    (score.get("analysis_depth") or {}).get("score", 0),
        "v3":    score.get("composite", {}).get("composite_v3", 0),
        "score_path": str(score_path.relative_to(ROOT)),
    }


def _load_intent(task_id: str) -> str:
    p = ROOT / "data/tasks/deep_research/cross_site_deep" / f"{task_id}.json"
    return json.loads(p.read_text()).get("intent", "")


def _print_summary(rows: list[dict]) -> None:
    print()
    print(f"{'task':<24} {'reach':>6} {'qm':>6} {'ck':>6} {'ad':>6} {'V3':>6} {'time':>6}")
    print("-" * 64)
    for r in rows:
        if r.get("error"):
            print(f"{r['task']:<24} {'ERROR':>30}  ({r['elapsed_s']}s)")
            continue
        print(
            f"{r['task']:<24} "
            f"{r['reach']:>6.3f} {r['qm']:>6.3f} {r['ck']:>6.3f} "
            f"{r['ad']:>6.3f} {r['v3']:>6.3f} {r['elapsed_s']:>5.0f}s"
        )
    valid = [r for r in rows if not r.get("error")]
    if valid:
        mean_v3 = sum(r["v3"] for r in valid) / len(valid)
        print("-" * 64)
        print(f"{'mean V3':<24} {' ':>20} {mean_v3:>6.3f}  ({len(valid)}/{len(rows)} scored)")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="integrations.submit")
    ap.add_argument("agent", nargs="?",
                    help="dotted-path to BaseAgent subclass (e.g. my_pkg.MyAgent), or use --agent")
    ap.add_argument("--agent", dest="agent_slug",
                    help="registered slug (e.g. storm, baseline-stuffer)")
    ap.add_argument("--tasks", default="0001-0005",
                    help="task range, e.g. 0001-0005,0011")
    ap.add_argument("--search-url", default=os.environ.get("SHIM_URL", "http://localhost:8081"))
    ap.add_argument("--llm-url",    default=os.environ.get("LLM_URL", "http://localhost:8081/llm/v1"))
    ap.add_argument("--llm-key",    default=os.environ.get("LLM_KEY", "any"))
    ap.add_argument("--model",      default=os.environ.get("DR_MODEL", "deepseek-v4-flash"))
    args = ap.parse_args(argv)

    spec = args.agent or args.agent_slug
    if not spec:
        ap.error("provide either a positional dotted path or --agent <slug>")

    cls = _load_agent_class(spec)
    agent = cls()
    from integrations.agents.base import AgentServices
    services = AgentServices(
        search_url=args.search_url,
        llm_url=args.llm_url,
        llm_key=args.llm_key,
        sandbox_hosts={
            "shopping": "localhost:7770",
            "reddit":   "localhost:9999",
            "wiki":     "localhost:8090",
        },
        model=args.model,
    )

    tasks = _parse_task_range(args.tasks)
    print(f"Running {agent.name} on {len(tasks)} task(s) → {args.search_url}")
    rows: list[dict] = []
    for tid in tasks:
        try:
            row = asyncio.run(_run_one(agent, tid, services))
        except Exception as e:
            row = {"task": tid, "agent": agent.name, "error": f"{type(e).__name__}: {e}",
                   "elapsed_s": 0.0, "skipped_scoring": True}
        rows.append(row)
        if row.get("error"):
            print(f"[{tid}] ERROR: {row['error']}")
        else:
            print(f"[{tid}] reach={row['reach']:.2f} qm={row['qm']:.2f} ck={row['ck']:.2f} V3={row['v3']:.3f} ({row['elapsed_s']}s)")

    _print_summary(rows)
    log_path = ROOT / "data/results/submitted" / f"{agent.name}__submission.json"
    log_path.write_text(json.dumps(rows, indent=2))
    print(f"\nlog: {log_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
