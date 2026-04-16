"""Run v3 deep-research tasks through agent(s), score with composite v3,
emit a markdown leaderboard + raw JSON + optional pairwise battles.

Usage:
    # ReAct agent on all 8 v3 tasks, skipping the LLM pillars (faster dry run):
    python scripts/bench_v3.py react --no-judge \\
        --tasks dr_shop_v3_0001,dr_shop_v3_0002,dr_shop_v3_0003,dr_shop_v3_0004,\\
dr_red_v3_0001,dr_red_v3_0002,dr_red_v3_0003,dr_red_v3_0004

    # Score a pre-existing markdown answer (e.g. oracle or DeerFlow output):
    python scripts/bench_v3.py \\
        --from-file dr_shop_v3_0001:oracle:data/results/oracle_v3_dr_shop_v3_0001.md

Differences vs bench_v2:
  - Uses `src.scoring.composite_v3.score` (fact_kg 0.30, checklist 0.20 ...).
  - Task resolution understands the v3 task_id pattern `dr_<site>_v3_NNNN`.
  - System prompt automatically switches to markdown mode when task has
    `markdown_spec` — handled inside glm_react_agent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runner import PlaywrightRunner
from src.scoring import (
    score_v3, CompositeResultV3, V3_WEIGHTS,
    compute_elo, render_elo_table,
    per_pillar_elo, render_per_pillar_table,
    pairwise_battle,
)
from src.metrics import EfficiencyMetrics


TASKS_ROOT = ROOT / "data" / "tasks" / "deep_research"
OUT_DIR = ROOT / "data" / "results"


def _resolve_task_path(task_id: str) -> Path:
    # v3 ids look like dr_shop_v3_0001 / dr_red_v3_0003 / dr_cross_v3_0001
    parts = task_id.split("_")
    if len(parts) >= 2:
        site_map = {"shop": "shopping", "red": "reddit", "git": "gitlab", "cross": "cross_site"}
        site = site_map.get(parts[1], "shopping")
    else:
        site = "shopping"
    return TASKS_ROOT / site / f"{task_id}.json"


def _load_task(task_id: str) -> dict:
    return json.loads(_resolve_task_path(task_id).read_text())


def run_react(task_id: str, *, run_judge: bool = True, model: str = "glm-5.1") -> CompositeResultV3:
    os.environ["GLM_MODEL"] = model
    # Reimport so MODEL is re-read
    if "src.agents.glm_react_agent" in sys.modules:
        del sys.modules["src.agents.glm_react_agent"]
    import importlib
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

    resolved_cfg = runner.resolve(cfg)
    # Attach pages_browsed count if the runner tracks it.
    pages = getattr(result, "pages_browsed", None)
    if pages is not None:
        resolved_cfg["pages_browsed"] = int(pages)

    agent_name = f"react-{model.replace('-', '').replace('.', '')}"
    return score_v3(
        task_id=task_id,
        agent=agent_name,
        task_config=resolved_cfg,
        answer=result.answer,
        efficiency=eff,
        run_judge=run_judge,
    )


def score_from_file(task_id: str, agent_name: str, path: Path,
                    *, eff: EfficiencyMetrics | None = None,
                    run_judge: bool = True) -> CompositeResultV3:
    cfg = _load_task(task_id)
    shopping = os.environ.get("SHOPPING", "http://localhost:7770")
    reddit   = os.environ.get("REDDIT",   "http://localhost:9999")
    cfg_resolved = json.loads(
        json.dumps(cfg)
        .replace("__SHOPPING__", shopping)
        .replace("__REDDIT__", reddit)
    )
    answer = path.read_text()
    return score_v3(
        task_id=task_id,
        agent=agent_name,
        task_config=cfg_resolved,
        answer=answer,
        efficiency=eff,
        run_judge=run_judge,
    )


def _run_pairwise_battles(results: list[CompositeResultV3]) -> tuple[list[dict], list[dict]]:
    by_task: dict[str, list[CompositeResultV3]] = {}
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


def write_leaderboard(results: list[CompositeResultV3], out_md: Path,
                      *, run_pairwise: bool = True) -> None:
    rows = [CompositeResultV3.markdown_header()]
    rows.extend(r.to_markdown_row() for r in sorted(results, key=lambda r: -r.composite))

    elo_recs = [{"task_id": r.task_id, "agent": r.agent, "composite": r.composite}
                for r in results]
    elos = compute_elo(elo_recs, tie_eps=0.005)
    elo_table = render_elo_table(elos) if elos else "_(need ≥2 agents per task for Elo)_"

    pp_records = [
        {"task_id": r.task_id, "agent": r.agent,
         "pillars": {name: p.score for name, p in r.pillars.items()}}
        for r in results
    ]
    pp_table = render_per_pillar_table(per_pillar_elo(pp_records))

    pw_table = "_(skipped)_"
    pw_logs: list[dict] = []
    if run_pairwise:
        print("Running pairwise LLM-judge battles ...")
        pw_recs, pw_logs = _run_pairwise_battles(results)
        if pw_recs:
            pw_table = render_elo_table(compute_elo(pw_recs, tie_eps=0.0))

    lines = [
        "# Deep Research Benchmark v3 — Arena Leaderboard",
        f"_Generated {time.strftime('%Y-%m-%d %H:%M:%S')}_",
        "",
        f"Composite weights (v3): `{V3_WEIGHTS}`",
        "",
        "## Composite Elo (driven by the 6-pillar weighted score)",
        "",
        elo_table,
        "",
        "## Pairwise-judge Elo (LLM judge, position-debiased)",
        "",
        pw_table,
        "",
        "## Per-pillar Elo (each pillar → its own arena)",
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
            lines.append("")

    lines.extend(["## Per-run details", ""])
    for r in results:
        lines.append(f"### `{r.agent}` — `{r.task_id}` — composite **{r.composite:.3f}**")
        lines.append("")
        for name, p in r.pillars.items():
            lines.append(f"- **{name}**: {p.score:.3f} (passed={p.passed})")
        lines.append("")
    out_md.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent", nargs="?", default="")
    ap.add_argument(
        "--tasks",
        default=",".join([
            "dr_shop_v3_0001", "dr_shop_v3_0002", "dr_shop_v3_0003", "dr_shop_v3_0004",
            "dr_red_v3_0001",  "dr_red_v3_0002",  "dr_red_v3_0003",  "dr_red_v3_0004",
        ]),
    )
    ap.add_argument("--model", default="glm-5.1")
    ap.add_argument("--no-judge", action="store_true",
                    help="skip LLM-hitting pillars (llm_judge, checklist, fact_kg precision)")
    ap.add_argument("--no-pairwise", action="store_true")
    ap.add_argument("--from-file", action="append", default=[],
                    help="task_id:agent:path (score a pre-existing markdown)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_md = Path(args.out) if args.out else OUT_DIR / f"bench_v3_{ts}.md"

    results: list[CompositeResultV3] = []

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
                (OUT_DIR / f"{agent_name}_{tid}_{ts}.json").write_text(
                    json.dumps(r.to_dict(), indent=2, ensure_ascii=False)
                )
                (OUT_DIR / f"{agent_name}_{tid}_{ts}.answer.md").write_text(r.answer or "")
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
        (OUT_DIR / f"{agent}_{tid}_{ts}.json").write_text(
            json.dumps(r.to_dict(), indent=2, ensure_ascii=False)
        )
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
