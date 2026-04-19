"""Build the final paper-ready leaderboard: composite-Elo with bootstrap
95% CI + rank significance tests + per-pillar breakdown.

Reads every `final_*.json` in data/results/, emits:
  - data/results/FINAL_LEADERBOARD.md
  - data/results/arena_final.json (machine-readable)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scoring.arena import (
    compute_elo,
    compute_elo_with_ci,
    rank_significance_test,
    per_pillar_elo,
    render_elo_table,
    render_elo_table_with_ci,
    render_per_pillar_table,
)

RESULTS = ROOT / "data" / "results"


def main() -> None:
    # Load composite-based runs
    runs = []
    for p in sorted(RESULTS.glob("final_*.json")):
        if p.name.endswith(".ed.json"):
            continue
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        if not isinstance(d, dict) or "composite" not in d:
            continue
        runs.append(d)

    # Also include evidence-density rescored runs if present
    ed_runs = []
    for p in sorted(RESULTS.glob("final_*.ed.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        if isinstance(d, dict) and "composite" in d:
            ed_runs.append(d)

    # Prefer the .ed.json composite (v3.1 weights) if available
    by_key = {(r["agent"], r["task_id"]): r for r in runs}
    for r in ed_runs:
        by_key[(r["agent"], r["task_id"])] = r

    records = [{"task_id": r["task_id"], "agent": r["agent"],
                "composite": float(r["composite"])}
               for r in by_key.values()]

    # Synthesize battles from composites (same methodology as
    # existing render_arena_leaderboard)
    comp_elo = compute_elo(records, tie_eps=0.005)

    # Also synthesize battles for bootstrap
    from collections import defaultdict
    from src.scoring.arena import _battles_for_task, Record
    by_task = defaultdict(list)
    for r in records:
        by_task[r["task_id"]].append(Record(**r))
    synth_battles = []
    for task_id, recs in by_task.items():
        for a, b, sa in _battles_for_task(recs, tie_eps=0.005):
            synth_battles.append({"task": task_id, "a1": a, "a2": b,
                                   "agent_winner": a if sa == 1.0 else (b if sa == 0.0 else "tie")})

    ci = compute_elo_with_ci(synth_battles, n_resamples=1000)
    sig = rank_significance_test(synth_battles, n_permutations=1000)

    # Per-pillar
    pillar_runs = [
        {"task_id": r["task_id"], "agent": r["agent"],
         "pillars": {k: v.get("score", 0) for k, v in r.get("pillars", {}).items()}}
        for r in by_key.values()
    ]
    pillar_elo = per_pillar_elo(pillar_runs)

    # Also load real-judge pairwise battles if present
    real_battles = []
    for p in RESULTS.glob("pairwise_*.json"):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        battles = d.get("battles") if isinstance(d, dict) else d
        if isinstance(battles, list):
            for b in battles:
                if isinstance(b, dict):
                    b.setdefault("judge_model", d.get("judge_model") or p.stem)
                    real_battles.append(b)
    judge_ci = compute_elo_with_ci(real_battles, n_resamples=1000) if real_battles else {}

    n_agents = len({r["agent"] for r in records})
    n_tasks = len({r["task_id"] for r in records})

    md = [
        "# Deep Research Arena — FINAL Leaderboard (paper-ready)",
        "",
        f"*{len(records)} runs across {n_agents} agents × {n_tasks} tasks.  "
        f"**Dual-judge setup** (different-family from agent, per Wataoka 2024 NeurIPS): "
        f"GLM-agent runs are judged by DeepSeek V3.2; `-ds` suffix agents (DeepSeek agent) "
        f"are judged by GLM-4.5. Both directions of the role-swap are included to show "
        f"how judge identity shapes the ranking.  "
        f"Composite weights: v3.1 (cite 0.25 / evidence_density 0.20 / llm_judge 0.20 / "
        f"checklist 0.20 / fact_kg 0.05 / structure 0.05 / efficiency 0.05).*",
        "",
        "## Headline — Composite-Elo with 95% bootstrap CI",
        "",
        f"Bootstrap over N=1000 resamples of the synthesised battle set "
        f"(C({n_agents},2) × {n_tasks} tasks = {n_agents*(n_agents-1)//2*n_tasks} "
        f"battles). Reports point estimate plus 95% percentile interval.",
        "",
        render_elo_table_with_ci(ci),
        "",
        "## Rank significance (permutation test, N=1000)",
        "",
        "*p < 0.05 means the adjacent rank gap is unlikely under the null "
        "hypothesis that the battle outcomes are random.*",
        "",
        "| Higher | Lower | Gap (Elo) | p-value | Significant? |",
        "|---|---|---:|---:|---|",
    ]
    for p in sig.get("adjacent_pairs", []):
        star = "✅" if p["significant"] else "❌"
        md.append(f"| {p['higher']} | {p['lower']} | {p['gap']} | {p['p_value']} | {star} |")

    md += [
        "",
        "## Per-pillar Elo (which agent is best at what)",
        "",
        render_per_pillar_table(pillar_elo),
        "",
    ]

    if judge_ci:
        md += [
            "## Real pairwise LLM-judge Elo (reference)",
            "",
            "*From live head-to-head battles (position-swap for bias), "
            "judge = DeepSeek V3.2. Under-populated: only 12 battles, "
            "CIs very wide. Included for comparison with composite.*",
            "",
            render_elo_table_with_ci(judge_ci),
            "",
        ]

    md += [
        "## Caveats (for reviewers)",
        "",
        "1. **Sample size**: real LLM-judge battles N=12 → CI half-widths "
        "~60 Elo. Synthesized battles N=112 (C(8,2)×4) but still "
        "underpowered for tight ordering — see permutation p-values above.",
        "2. **Oracle v2 (filtered) available**: intent-aware rebuild ran on "
        "4 scored tasks (budget + category filter, rejects "
        "'Magic Home Nightstand in kitchen build'). `fact_kg` remains at "
        "0.05 weight until all scores re-run with the filtered oracle.",
        "3. **Citation metric**: default is ALCE substring. "
        "`CITATION_MODE=entailment` switches to claim-level NLI via "
        "DeepSeek (results not yet in headline, pending rescore).",
        "4. **Task domain**: benchmark now has 107 tasks across consumer/UGC "
        "(0001-0087) + scholarly/policy (0088-0107; medicine, economics, "
        "history, AI ethics, urban planning). Only 4 consumer tasks have "
        "been run so far — expanding the run set to cover the scholarly "
        "tier is next.",
        "5. **Framework incompatibilities documented**: "
        "(a) smolagents+GLM-4.7 emits `</code>` instead of the trained "
        "`<end_code>` sentinel, so its CodeAgent parser fails every step "
        "— the final report is a zero-tool-call hallucination. "
        "(b) LangChain open_deep_research and dzhng/deep-research both "
        "rely on structured-JSON output; GLM-4.7 via OpenAI-compat "
        "returns free text that fails zod/pydantic parsing. After the "
        "DeepSeek-agent swap these two frameworks also unlock, see `odr-ds`.",
        "6. **Agent role-swap (Phase 9, 2026-04-19)**: switched agents from "
        "GLM-4.7 to DeepSeek V3.2 and judge from DeepSeek to GLM-4.5 to "
        "unblock frameworks that require JSON-mode and to surface judge-"
        "identity effects. Observations: (a) DeepSeek agents consistently "
        "score lower than GLM agents under the same framework (e.g. "
        "camel-ai 1121 vs camel-ai-ds 975, gpt-researcher 1279 vs "
        "gpt-researcher-ds 691) — DeepSeek reports tend to cite "
        "hallucinated URLs (`onestopmarket.com/...`) instead of real "
        "sandbox URLs (`localhost:7770/...`), crushing the citation pillar. "
        "(b) dzhng-ds and react-ds remain blocked (tool-call format and "
        "Anthropic-compat issues respectively).",
        "",
    ]

    out_md = RESULTS / "FINAL_LEADERBOARD.md"
    out_md.write_text("\n".join(md))

    out_json = RESULTS / "arena_final.json"
    out_json.write_text(json.dumps({
        "composite_elo": comp_elo,
        "composite_elo_ci": ci,
        "rank_significance": sig,
        "judge_elo_ci": judge_ci,
        "pillar_elo": pillar_elo,
        "n_runs": len(records),
        "n_agents": n_agents,
        "n_tasks": n_tasks,
    }, indent=2, ensure_ascii=False))

    print(f"Wrote {out_md}")
    print(f"Wrote {out_json}")
    print()
    print("\n".join(md[:40]))


if __name__ == "__main__":
    main()
