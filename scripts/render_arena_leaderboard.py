#!/usr/bin/env python3
"""Render the v3 Arena leaderboard (composite-Elo vs judge-Elo).

Reads:
  - data/results/final_*.json         (composite scores per run)
  - data/results/pairwise_*.json      (real pairwise battles per judge)

Emits:
  - data/results/LEADERBOARD_v3.md    (markdown tables + commentary)
  - data/results/arena_elo.json       (machine-readable raw data)

Both Elo streams are computed:
  * Composite-Elo: synthesised from per-task composite rankings
  * Judge-Elo   : from real LLM-judge pairwise battles (per-judge breakdown
                  so we can measure judge-model agreement / self-preference).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scoring.arena import (
    compute_elo,
    compute_elo_from_battles,
    compute_elo_per_judge,
    render_elo_table,
    per_pillar_elo,
    render_per_pillar_table,
)

RESULTS = ROOT / "data" / "results"


def load_composite_runs() -> list[dict]:
    """Load every final_<agent>_<task>.json into a flat list."""
    out = []
    for p in sorted(RESULTS.glob("final_*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        if not isinstance(d, dict) or "composite" not in d:
            continue
        out.append(d)
    return out


def load_battles() -> list[dict]:
    """Load every pairwise_*.json file into a flat battle list."""
    all_battles = []
    for p in sorted(RESULTS.glob("pairwise_*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        battles = d.get("battles") if isinstance(d, dict) else d
        if not isinstance(battles, list):
            continue
        # Attach the source file as a fallback judge id
        for b in battles:
            if isinstance(b, dict):
                b.setdefault("judge_model", d.get("judge_model") or p.stem)
                all_battles.append(b)
    return all_battles


def render_side_by_side(
    composite_elo: dict[str, dict],
    judge_elo_combined: dict[str, dict],
) -> str:
    agents = sorted(set(composite_elo.keys()) | set(judge_elo_combined.keys()))
    lines = [
        "## Composite-Elo vs Judge-Elo (side-by-side)",
        "",
        "| Agent | Composite-Elo | Judge-Elo (all judges) | Δ (Judge − Comp) |",
        "|---|---:|---:|---:|",
    ]
    rows = []
    for a in agents:
        ce = composite_elo.get(a, {}).get("elo")
        je = judge_elo_combined.get(a, {}).get("elo")
        delta = (je - ce) if (ce is not None and je is not None) else None
        rows.append((a, ce, je, delta))
    # Sort by max(ce, je) descending
    rows.sort(key=lambda r: -(max((r[1] or 0), (r[2] or 0))))
    for a, ce, je, delta in rows:
        ce_s = f"{ce:.1f}" if ce is not None else "—"
        je_s = f"{je:.1f}" if je is not None else "—"
        d_s = f"{delta:+.1f}" if delta is not None else "—"
        lines.append(f"| {a} | {ce_s} | {je_s} | {d_s} |")
    return "\n".join(lines)


def render_per_judge_block(per_judge: dict[str, dict]) -> str:
    lines = ["## Judge-Elo breakdown (per judge model)", ""]
    for judge_id, elos in per_judge.items():
        n_battles = sum(v["n_battles"] for v in elos.values()) // 2 if elos else 0
        lines.append(f"### Judge: `{judge_id}`  ({n_battles} battles)")
        lines.append(render_elo_table(elos))
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    runs = load_composite_runs()
    battles = load_battles()

    # Composite-Elo: one record per (agent, task)
    comp_records = [
        {"task_id": r["task_id"], "agent": r["agent"], "composite": float(r["composite"])}
        for r in runs
    ]
    comp_elo = compute_elo(comp_records, tie_eps=0.005)

    # Per-pillar composite-Elo (pillar-wise arena)
    pillar_runs = [
        {"task_id": r["task_id"], "agent": r["agent"],
         "pillars": {k: v.get("score", 0) for k, v in r.get("pillars", {}).items()}}
        for r in runs
    ]
    pillar_elo = per_pillar_elo(pillar_runs)

    # Judge-Elo (all judges combined + per-judge split)
    judge_elo = compute_elo_from_battles(battles)
    judge_per = compute_elo_per_judge(battles)

    # Render markdown
    n_agents = len({r["agent"] for r in runs})
    n_tasks = len({r["task_id"] for r in runs})
    n_runs = len(runs)
    n_battles = len(battles)

    md_parts = [
        "# Deep Research Arena — v3 Leaderboard",
        "",
        f"*Auto-generated from {n_runs} runs ({n_agents} agents × {n_tasks} tasks) "
        f"and {n_battles} pairwise battles.*",
        "",
        "## Headline — Composite-Elo (synthesised from per-task composite)",
        "",
        render_elo_table(comp_elo),
        "",
        render_side_by_side(comp_elo, judge_elo),
        "",
        render_per_judge_block(judge_per),
        "",
        "## Per-pillar Elo (composite pillars broken out)",
        "",
        render_per_pillar_table(pillar_elo),
        "",
        "---",
        "",
        "### Interpretation notes",
        "",
        "- **Composite-Elo** uses the 6-pillar composite score as the battle outcome",
        "  signal. Fast to produce but biased by pillar weight choices.",
        "- **Judge-Elo** uses LLM pairwise judgements (position-swapped). Closer to",
        "  Chatbot Arena methodology; susceptible to judge self-preference unless",
        "  dual-judged.",
        "- **Δ(Judge − Comp)** surfaces agents that score well on the pillar formula",
        "  but lose head-to-head judgement, or vice versa. A large |Δ| indicates",
        "  the composite weights may not reflect perceived research quality.",
        "",
    ]
    md = "\n".join(md_parts)
    out_md = RESULTS / "LEADERBOARD_v3.md"
    out_md.write_text(md)

    out_json = RESULTS / "arena_elo.json"
    out_json.write_text(json.dumps({
        "composite_elo": comp_elo,
        "judge_elo_all": judge_elo,
        "judge_elo_per": judge_per,
        "pillar_elo": pillar_elo,
        "counts": {
            "n_runs": n_runs, "n_agents": n_agents,
            "n_tasks": n_tasks, "n_battles": n_battles,
        },
    }, indent=2, ensure_ascii=False))

    print(f"Wrote {out_md}")
    print(f"Wrote {out_json}")
    print()
    print(md)


if __name__ == "__main__":
    main()
