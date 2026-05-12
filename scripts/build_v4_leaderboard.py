#!/usr/bin/env python3
"""Build a v4 leaderboard JSON + Markdown from v4 score files.

Reads `data/results/deep_v4/<agent>__<task>_matrix.v4.json` produced by
`run_v4_experiment.py`, then:

  1. Computes per-agent means for the 4 new pillars
     (source_diversity / perspective_balance / factual_exactness /
     internal_consistency) and for composite_v4.
  2. Pairs v4 against v2 (the v4 row JSONs already carry the v2 score
     from when each report was originally scored) to compute Bradley-
     Terry / Elo over `v4_composite`.
  3. Writes:
       data/results/deep_v4/leaderboard_deep_v4.json   (machine)
       data/results/deep_v4/LEADERBOARD_DEEP_V4.md     (human)

Usage:
    python scripts/build_v4_leaderboard.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

V4_DIR  = ROOT / "data" / "results" / "deep_v4"
OUT_JSON = V4_DIR / "leaderboard_deep_v4.json"
OUT_MD   = V4_DIR / "LEADERBOARD_DEEP_V4.md"

from src.scoring.arena import (    # noqa: E402
    compute_elo_with_ci,
    rank_significance_test,
)


def _is_real_row(row: dict) -> bool:
    """Skip empty / degenerate rows (placeholder reports score 0/0)."""
    return float(row.get("v2_composite") or 0) > 0 or float(row.get("v4_composite") or 0) > 0


def _load_rows() -> list[dict]:
    rows: list[dict] = []
    for p in sorted(V4_DIR.glob("*_matrix.v4.json")):
        try:
            row = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append(row)
    return rows


def _per_agent_summary(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if not _is_real_row(r):
            continue
        grouped[r["agent"]].append(r)

    def m(lst: list, key_chain: tuple[str, ...]) -> float | None:
        vals: list[float] = []
        for r in lst:
            cur = r
            for k in key_chain:
                if not isinstance(cur, dict) or k not in cur:
                    cur = None
                    break
                cur = cur[k]
            if isinstance(cur, (int, float)):
                vals.append(float(cur))
        return round(sum(vals) / len(vals), 4) if vals else None

    for agent, lst in grouped.items():
        out[agent] = {
            "n_runs": len(lst),
            "v2_mean":            m(lst, ("v2_composite",)),
            "v4_mean":            m(lst, ("v4_composite",)),
            "source_diversity":   m(lst, ("source_diversity",     "score")),
            "perspective_balance":m(lst, ("perspective_balance",  "score")),
            "factual_exactness":  m(lst, ("factual_exactness",    "score")),
            "internal_consistency":m(lst, ("internal_consistency","score")),
            "url_reachability":   m(lst, ("v2_pillars", "url_reachability")),
            "url_coverage":       m(lst, ("v2_pillars", "url_coverage")),
            "checklist_pass":     m(lst, ("v2_pillars", "checklist_pass")),
        }
        if out[agent]["v2_mean"] is not None and out[agent]["v4_mean"] is not None:
            out[agent]["delta_v4_v2"] = round(out[agent]["v4_mean"] - out[agent]["v2_mean"], 4)
    return out


def _v4_battles(rows: list[dict]) -> list[dict]:
    """Synthesize pairwise battles over composite_v4 per task.

    Returns the dict shape expected by `compute_elo_with_ci`:
        {"a": agent_a, "b": agent_b, "score_a": 1.0 / 0.5 / 0.0}

    For each task, every pair of agents that both have a non-zero v4
    score plays a battle. The higher score wins; |Δ| < 0.005 → draw.
    """
    by_task: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        if not _is_real_row(r):
            continue
        v4 = float(r.get("v4_composite") or 0)
        if v4 <= 0:
            continue
        by_task[r["task"]][r["agent"]] = v4

    battles: list[dict] = []
    EPS = 0.005
    for task, agent_to_v4 in by_task.items():
        agents = sorted(agent_to_v4)
        for i, a in enumerate(agents):
            for b in agents[i + 1:]:
                va, vb = agent_to_v4[a], agent_to_v4[b]
                if abs(va - vb) < EPS:
                    score_a = 0.5
                elif va > vb:
                    score_a = 1.0
                else:
                    score_a = 0.0
                battles.append({"a": a, "b": b, "score_a": score_a})
    return battles


def _render_md(rows: list[dict], summary: dict[str, dict], elo: dict, sig: list[dict]) -> str:
    L = []
    L.append("# Deep-Research Leaderboard — composite_v4\n")
    L.append("Reach-gated 11-dimension composite that adds four new pillars (atomic factuality, intra-document consistency, perspective balance, source diversity) on top of the original v2 verifiers.\n")
    L.append(f"\n* Source: `data/results/deep_v4/*.v4.json`")
    L.append(f"* Total rows on disk: **{len(rows)}**")
    L.append(f"* Real (non-degenerate) rows: **{sum(1 for r in rows if _is_real_row(r))}**\n")

    # --- Headline Elo table ---
    L.append("## Headline ranking (composite_v4)\n")
    L.append("| # | Agent | Elo | 95% CI | n | source_div | persp_bal | factual_ex | intl_cons | v2 mean | v4 mean | Δ |")
    L.append("|---|-------|-----|--------|---|------------|-----------|------------|-----------|---------|---------|---|")

    ranked = sorted(elo.items(), key=lambda kv: -kv[1]["elo"])
    for i, (agent, e) in enumerate(ranked, start=1):
        s = summary.get(agent, {})
        def f(x): return f"{x:.3f}" if isinstance(x, (int, float)) else "—"
        def fci(lo, hi): return f"[{lo:.0f}, {hi:.0f}]" if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) else "—"
        L.append(
            f"| {i} | **{agent}** | "
            f"{e['elo']:.0f} | {fci(e['elo_lo'], e['elo_hi'])} | "
            f"{s.get('n_runs', 0)} | "
            f"{f(s.get('source_diversity'))} | {f(s.get('perspective_balance'))} | "
            f"{f(s.get('factual_exactness'))} | {f(s.get('internal_consistency'))} | "
            f"{f(s.get('v2_mean'))} | {f(s.get('v4_mean'))} | "
            f"{f(s.get('delta_v4_v2'))} |"
        )
    L.append("")

    # --- Significance ---
    if sig:
        L.append("## Adjacent-rank significance (permutation N=1000)\n")
        L.append("| Higher | Lower | Gap | p-value | α=0.05 |")
        L.append("|--------|-------|-----|---------|--------|")
        for p in sig:
            L.append(f"| {p['higher']} | {p['lower']} | {p['gap']:.0f} | {p['p_value']:.3f} | {'**yes**' if p['significant'] else 'no'} |")
        L.append("")

    # --- Where v4 disagrees most with v2 ---
    L.append("## Top |v4 − v2| rows (where new pillars rewrote the verdict)\n")
    L.append("Positive Δ = v4 rates higher (multi-perspective / good sourcing despite middling URL coverage). Negative Δ = v4 rates lower (URL-true but factually wrong / one-sided / self-contradicting).\n")
    L.append("| Agent × Task | v2 | v4 | Δ | sd | pb | fe | ic |")
    L.append("|---|---|---|---|---|---|---|---|")
    real_rows = [r for r in rows if _is_real_row(r)]
    real_rows.sort(key=lambda r: -abs(float(r.get("v4_minus_v2") or 0)))
    for r in real_rows[:15]:
        def g(blob):
            if not isinstance(blob, dict):
                return "—"
            s = blob.get("score")
            return f"{s:.2f}" if isinstance(s, (int, float)) else "—"
        L.append(
            f"| {r['agent']} × {r['task']} | "
            f"{r.get('v2_composite', 0):.2f} | {r.get('v4_composite', 0):.2f} | "
            f"{r.get('v4_minus_v2', 0):+.2f} | "
            f"{g(r.get('source_diversity'))} | {g(r.get('perspective_balance'))} | "
            f"{g(r.get('factual_exactness'))} | {g(r.get('internal_consistency'))} |"
        )
    L.append("")

    # --- Pillar coverage ---
    L.append("## Pillar coverage diagnostics\n")
    for pname in ("source_diversity", "perspective_balance", "factual_exactness", "internal_consistency"):
        present = sum(1 for r in rows if isinstance(r.get(pname), dict))
        scored  = sum(1 for r in rows
                      if isinstance(r.get(pname), dict)
                      and isinstance(r[pname].get("score"), (int, float)))
        L.append(f"* `{pname}`: present={present}, scored={scored}, of {len(rows)}")
    L.append("")

    return "\n".join(L)


def main() -> int:
    rows = _load_rows()
    print(f"loaded {len(rows)} v4 row JSONs from {V4_DIR}")
    if not rows:
        print("no v4 row JSONs yet — run scripts/run_v4_experiment.py first")
        return 1

    summary = _per_agent_summary(rows)
    print(f"per-agent summary built for {len(summary)} agents")

    battles = _v4_battles(rows)
    print(f"synthesized {len(battles)} pairwise battles over composite_v4")

    if not battles:
        print("no battles — every agent has a single run or scores collide; skipping Elo")
        elo = {}
        sig: list[dict] = []
    else:
        elo = compute_elo_with_ci(battles, n_resamples=1000)
        # Adjacent-rank significance: rank_significance_test takes the
        # whole battle list and returns p-values for all adjacent pairs.
        rs = rank_significance_test(battles, n_permutations=1000)
        # rs schema: {"adjacent_pairs": [{"higher": ..., "lower": ..., "gap": ..., "p_value": ...}, ...]}
        adj_pairs = rs.get("adjacent_pairs") if isinstance(rs, dict) else []
        sig = []
        for pair in adj_pairs or []:
            sig.append({
                "higher": pair.get("higher"),
                "lower":  pair.get("lower"),
                "gap":    float(pair.get("gap", 0.0)),
                "p_value": float(pair.get("p_value", 1.0)),
                "significant": float(pair.get("p_value", 1.0)) < 0.05,
            })

    V4_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "elo": elo,
        "per_agent": summary,
        "significance": sig,
        "n_rows_total": len(rows),
        "n_rows_real":  sum(1 for r in rows if _is_real_row(r)),
        "n_battles":    len(battles),
        "formula": "composite_v4 = reach · (0.10·url_cov + 0.05·spec + 0.10·checklist + 0.10·cit_align + 0.05·qm + 0.13·factual_exactness + 0.13·internal_consistency + 0.08·perspective_balance + 0.06·source_diversity + 0.10·analysis_depth + 0.10·presentation)",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_MD.write_text(_render_md(rows, summary, elo, sig), encoding="utf-8")

    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
