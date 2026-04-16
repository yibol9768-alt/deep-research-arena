"""Run our Stage-B DR tasks through agent(s), score with the v2 composite
scorer, write a leaderboard markdown + raw JSON.

Usage:
    # Run GLM-5.1 ReAct on all 5 tasks, score with v2
    SHOPPING=http://localhost:7770 python scripts/bench_v2.py react
    # Score an existing markdown (e.g. DeerFlow prose report)
    python scripts/bench_v2.py --from-file dr_shop_0001:deerflow:data/results/deerflow_dr_shop_0001.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runner import PlaywrightRunner
from src.scoring import (
    score as score_composite, CompositeResult,
    compute_elo, render_elo_table,
    per_pillar_elo, render_per_pillar_table,
    pairwise_battle,
)
from src.metrics import EfficiencyMetrics


TASKS_ROOT = ROOT / "data" / "tasks" / "deep_research"
# Back-compat for pairwise log code that still references TASKS_DIR
TASKS_DIR = TASKS_ROOT / "shopping"
OUT_DIR = ROOT / "data" / "results"


def _resolve_task_path(task_id: str) -> Path:
    """Dispatch by task_id prefix to the right site subfolder."""
    prefix = task_id.split("_", 2)[1] if task_id.startswith("dr_") else ""
    site_map = {"shop": "shopping", "red": "reddit", "git": "gitlab"}
    site = site_map.get(prefix, "shopping")
    return TASKS_ROOT / site / f"{task_id}.json"


def _load_task(task_id: str) -> dict:
    return json.loads(_resolve_task_path(task_id).read_text())


def run_react(task_id: str, *, run_judge: bool = True, model: str = "glm-5.1") -> CompositeResult:
    import os, importlib
    os.environ["GLM_MODEL"] = model
    # Force re-import so MODEL constant is re-read
    if "src.agents.glm_react_agent" in __import__("sys").modules:
        del __import__("sys").modules["src.agents.glm_react_agent"]
    agent_mod = importlib.import_module("src.agents.glm_react_agent")
    glm_react_agent = agent_mod.glm_react_agent

    cfg = _load_task(task_id)
    runner = PlaywrightRunner(headless=True, timeout_ms=90_000)
    t0 = time.time()
    result = runner.run(cfg, agent=glm_react_agent)
    elapsed = time.time() - t0

    eff = agent_mod.LAST_METRICS or EfficiencyMetrics(model=model)
    if eff.wall_time_s == 0:
        eff.wall_time_s = elapsed

    # Resolve __SHOPPING__ in citation_policy for scorer
    resolved_cfg = runner.resolve(cfg)

    agent_name = f"react-{model.replace('-', '').replace('.', '')}"

    return score_composite(
        task_id=task_id,
        agent=agent_name,
        task_config=resolved_cfg,
        answer=result.answer,
        efficiency=eff,
        run_judge=run_judge,
    )


def score_from_file(task_id: str, agent_name: str, path: Path, *, eff: EfficiencyMetrics | None = None,
                    run_judge: bool = True) -> CompositeResult:
    cfg = _load_task(task_id)
    # Minimal resolve: substitute __SHOPPING__ in start_url and citation_policy
    import os as _os
    shopping = _os.environ.get("SHOPPING", "http://localhost:7770")
    cfg_resolved = json.loads(json.dumps(cfg).replace("__SHOPPING__", shopping))
    answer = path.read_text()
    return score_composite(
        task_id=task_id,
        agent=agent_name,
        task_config=cfg_resolved,
        answer=answer,
        efficiency=eff,
        run_judge=run_judge,
    )


def _run_pairwise_battles(results: list[CompositeResult]) -> tuple[list[dict], list[dict]]:
    """Pair every (agent_a, agent_b) on the same task; ask LLM judge.
    Returns (elo_records, raw_battle_logs).
    """
    by_task: dict[str, list[CompositeResult]] = {}
    for r in results:
        by_task.setdefault(r.task_id, []).append(r)

    elo_recs: list[dict] = []
    logs: list[dict] = []
    for tid, runs in by_task.items():
        if len(runs) < 2:
            continue
        cfg_path = _resolve_task_path(tid)
        intent = json.loads(cfg_path.read_text()).get("intent", "")
        for i in range(len(runs)):
            for j in range(i + 1, len(runs)):
                a, b = runs[i], runs[j]
                print(f"  pairwise: {a.agent} vs {b.agent} on {tid}")
                outcome = pairwise_battle(
                    task_intent=intent,
                    agent_a=a.agent, answer_a=a.answer,
                    agent_b=b.agent, answer_b=b.answer,
                )
                logs.append({"task": tid, "a": a.agent, "b": b.agent, **outcome})
                # IMPORTANT: each pairwise battle gets a UNIQUE task_id
                # so compute_elo emits exactly 1 battle (not C(N,2)) per
                # outcome. The per-pair task_id encodes (task, a, b).
                pair_id = f"{tid}-pw-{a.agent}-vs-{b.agent}"
                if outcome["winner"] == "a":
                    sa, sb = 1.0, 0.0
                elif outcome["winner"] == "b":
                    sa, sb = 0.0, 1.0
                else:
                    sa, sb = 0.5, 0.5
                elo_recs.append({"task_id": pair_id, "agent": a.agent, "composite": sa})
                elo_recs.append({"task_id": pair_id, "agent": b.agent, "composite": sb})
    return elo_recs, logs


def write_leaderboard(results: list[CompositeResult], out_md: Path, *, run_pairwise: bool = True) -> None:
    rows = [CompositeResult.markdown_header()]
    rows.extend(r.to_markdown_row() for r in sorted(results, key=lambda r: -r.composite))

    # Composite Elo
    elo_recs = [{"task_id": r.task_id, "agent": r.agent, "composite": r.composite} for r in results]
    elos = compute_elo(elo_recs, tie_eps=0.005)
    elo_table = render_elo_table(elos) if elos else "_(need ≥2 agents per task for Elo)_"

    # Per-pillar Elo
    pp_records = [
        {"task_id": r.task_id, "agent": r.agent,
         "pillars": {name: p.score for name, p in r.pillars.items()}}
        for r in results
    ]
    pp = per_pillar_elo(pp_records)
    pp_table = render_per_pillar_table(pp)

    # Pairwise judge Elo (Chatbot Arena style)
    pw_table = "_(skipped)_"
    pw_logs: list[dict] = []
    if run_pairwise:
        print("Running pairwise LLM-judge battles ...")
        pw_recs, pw_logs = _run_pairwise_battles(results)
        if pw_recs:
            pw_elos = compute_elo(pw_recs, tie_eps=0.0)
            pw_table = render_elo_table(pw_elos)

    lines = [
        "# Deep Research Benchmark v2 — Arena Leaderboard",
        f"_Generated {time.strftime('%Y-%m-%d %H:%M:%S')}_",
        "",
        "## Composite Elo (driven by the 6-pillar weighted score)",
        "",
        elo_table,
        "",
        "## Pairwise-judge Elo (LLM judge picks winner side-by-side, position-debiased)",
        "",
        pw_table,
        "",
        "## Per-pillar Elo (each pillar treated as its own arena)",
        "",
        pp_table,
        "",
        "## Per-task composite scores",
        "",
        *rows,
        "",
    ]
    if pw_logs:
        lines.append("## Pairwise battle logs")
        lines.append("")
        for log in pw_logs:
            lines.append(f"### {log['task']}: `{log['a']}` vs `{log['b']}` → **{log['agent_winner']}**")
            lines.append("")
            lines.append(f"- raw verdicts (both orderings): {log.get('verdicts_raw')}")
            lines.append(f"- judge: `{log.get('judge_model')}`")
            for i, r in enumerate(log.get("reasonings") or []):
                lines.append(f"  <details><summary>reasoning {i+1}</summary>\n\n```\n{r[:1200]}\n```\n  </details>")
            lines.append("")

    lines.extend(["## Per-run details", ""])
    for r in results:
        lines.append(f"### `{r.agent}` — `{r.task_id}` — composite **{r.composite:.3f}**")
        lines.append("")
        for name, p in r.pillars.items():
            lines.append(f"- **{name}**: {p.score:.3f} (passed={p.passed})")
        lines.append("")
        lines.append("<details><summary>Judge reasoning / details</summary>")
        lines.append("")
        j = r.pillars["llm_judge"].details
        if j.get("reason"):
            lines.append(f"> {j['reason']}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps({k: v.details for k, v in r.pillars.items()}, indent=2, ensure_ascii=False)[:3500])
        lines.append("```")
        lines.append("</details>")
        lines.append("")
    out_md.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent", nargs="?", default="")
    ap.add_argument("--tasks", default="dr_shop_0001,dr_shop_0002,dr_shop_0005")
    ap.add_argument("--model", default="glm-5.1", help="GLM model to use for react agent")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--from-file", action="append", default=[],
                    help="task_id:agent:path (score a pre-existing answer file)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-pairwise", action="store_true", help="skip pairwise LLM-judge battles")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_md = Path(args.out) if args.out else OUT_DIR / f"bench_v2_{ts}.md"

    results: list[CompositeResult] = []

    if args.agent == "react":
        for tid in args.tasks.split(","):
            tid = tid.strip()
            if not tid:
                continue
            agent_name = f"react-{args.model.replace('-', '').replace('.', '')}"
            print(f"\n=== {agent_name} :: {tid} ===")
            try:
                r = run_react(tid, run_judge=not args.no_judge, model=args.model)
                results.append(r)
                (OUT_DIR / f"{agent_name}_{tid}_{ts}.json").write_text(json.dumps(r.to_dict(), indent=2, ensure_ascii=False))
                (OUT_DIR / f"{agent_name}_{tid}_{ts}.answer.txt").write_text(r.answer or "")
                print(f"  composite = {r.composite:.3f}")
            except Exception as e:
                print(f"  FAILED: {e}")

    for spec in args.from_file:
        try:
            tid, agent, path = spec.split(":", 2)
        except ValueError:
            print(f"bad --from-file spec: {spec}", file=sys.stderr)
            continue
        print(f"\n=== {agent} :: {tid} (from {path}) ===")
        r = score_from_file(tid, agent, Path(path), run_judge=not args.no_judge)
        results.append(r)
        (OUT_DIR / f"{agent}_{tid}_{ts}.json").write_text(json.dumps(r.to_dict(), indent=2, ensure_ascii=False))
        print(f"  composite = {r.composite:.3f}")

    if results:
        write_leaderboard(results, out_md, run_pairwise=not args.no_pairwise)
        try:
            print(f"\nwrote {out_md.relative_to(ROOT)}")
        except ValueError:
            print(f"\nwrote {out_md}")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
