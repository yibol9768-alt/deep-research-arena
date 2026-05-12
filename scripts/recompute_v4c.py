#!/usr/bin/env python3
"""Recompute composite_v4c on all existing v4 row JSONs.

v4c = z-score normalisation of every pillar across the *whole sample*, then
the same v4b weight vector, then the same reachability multiplicative gate.

Why this helps discriminability vs v4b:
  - v4b multiplies the *raw* pillar value (∈ [0,1]) by a fixed weight, so a
    pillar where every agent lands in a narrow band (e.g. internal_consistency
    almost always 0.95-1.00) shifts everyone by the same ~constant and ranks
    nobody.
  - v4c first standardises each pillar to a population z-score, then sigmoids
    it back to [0,1]. Narrow-band pillars now contribute roughly 0.5 to
    everyone (≈ no information). Wide-spread pillars (source_diversity,
    factual_exactness, checklist) automatically dominate. No weight retune
    needed — z-score does the variance budgeting for us.

Per-agent aggregation reports four flavours so the user can pick the most
defensible one:
  - mean         : average across the agent's reports (what v4 / v4b use)
  - median       : robust to one outlier task
  - p25          : 25th percentile — rewards consistency, harsher on tails
  - min          : worst-case run — strict reliability view

The script never re-runs any verifier. It only reads the 44 existing v4
row JSONs (which already contain the 4 new-pillar measurements) plus their
linked v3 score JSONs (for the 7 original pillars). Output:
  - data/results/deep_v4/leaderboard_deep_v4c.json
  - data/results/deep_v4/LEADERBOARD_DEEP_V4C.md
  - each row JSON gets a `v4c_composite` field added.
"""
from __future__ import annotations

import glob
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scoring.leaderboard_composites import (  # noqa: E402
    spec_pass_fraction, checklist_pass_rate,
)
from src.scoring.arena import (  # noqa: E402
    compute_elo_with_ci,
    rank_significance_test,
)

V4_DIR = ROOT / "data" / "results" / "deep_v4"

# Same weight vector as v4b. v4c keeps the same weights deliberately —
# we want to show that z-score normalisation alone improves separation,
# without re-tuning weights (which would conflate two effects).
WEIGHTS = {
    "url_coverage":         0.10,
    "spec":                 0.05,
    "checklist":            0.10,
    "citation_alignment":   0.10,
    "quote_match":          0.05,
    "factual_exactness":    0.13,
    "internal_consistency": 0.07,
    "perspective_balance":  0.08,
    "source_diversity":     0.12,
    "analysis_depth":       0.10,
    "presentation":         0.10,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def pillar_score(blob, key):
    """Read a pillar's score with consistent dict-or-missing handling."""
    if key == "checklist":
        return checklist_pass_rate(blob.get("checklist") or {})
    if key == "spec":
        return spec_pass_fraction(blob.get("markdown_spec") or {})
    b = blob.get(key)
    if not isinstance(b, dict):
        return 0.0
    return float(b.get("score") or 0)


def harvest_pillars(v4_row, v3_score):
    """Pull all 11 pillar values out of a row+score pair."""
    return {
        "url_coverage":         pillar_score(v3_score, "url_coverage"),
        "spec":                 pillar_score(v3_score, "spec"),
        "checklist":            pillar_score(v3_score, "checklist"),
        "citation_alignment":   pillar_score(v3_score, "citation_alignment"),
        "quote_match":          pillar_score(v3_score, "quote_match"),
        "analysis_depth":       pillar_score(v3_score, "analysis_depth"),
        "presentation":         pillar_score(v3_score, "presentation"),
        "factual_exactness":    pillar_score(v4_row, "factual_exactness"),
        "internal_consistency": pillar_score(v4_row, "internal_consistency"),
        "perspective_balance":  pillar_score(v4_row, "perspective_balance"),
        "source_diversity":     pillar_score(v4_row, "source_diversity"),
    }


def sigmoid(x, sharpness=1.2):
    """Squash z-score back into [0, 1]. sharpness > 1 amplifies separation
    around the mean; sharpness=1 is plain sigmoid; > 2 starts to clip."""
    z = max(-6.0, min(6.0, x * sharpness))
    return 1.0 / (1.0 + math.exp(-z))


def main():
    files = sorted(V4_DIR.glob("*.v4.json"))
    if not files:
        print("no v4 rows found")
        return

    # ── pass 1: harvest every pillar value into rows[] ────────────────
    rows = []
    for fp in files:
        v4 = json.load(open(fp))
        score_path = Path(v4["score_path"])
        if not score_path.exists():
            print(f"  skip {fp.name}: score path missing {score_path}")
            continue
        v3 = json.load(open(score_path))
        reach = pillar_score(v3, "url_reachability")
        pillars = harvest_pillars(v4, v3)
        rows.append({
            "path":    fp,
            "agent":   v4["agent"],
            "task":    v4["task"],
            "reach":   reach,
            "pillars": pillars,
        })
    print(f"loaded {len(rows)} rows")

    # ── pass 2: per-pillar population stats ───────────────────────────
    stats = {}
    print()
    print(f"{'pillar':<24}{'mu':>8}{'sd':>8}{'span':>8}")
    for k in WEIGHTS:
        vals = [r["pillars"][k] for r in rows]
        mu = statistics.mean(vals)
        sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
        stats[k] = {"mu": mu, "sd": sd, "min": min(vals), "max": max(vals)}
        print(f"{k:<24}{mu:>8.3f}{sd:>8.3f}{max(vals)-min(vals):>8.3f}")
    print()

    # ── pass 3: compute v4c composite per row ────────────────────────
    def v4c_row_score(row):
        raw = 0.0
        for k, w in WEIGHTS.items():
            s = stats[k]
            if s["sd"] < 1e-6:
                normed = 0.5  # no information, neutral contribution
            else:
                z = (row["pillars"][k] - s["mu"]) / s["sd"]
                normed = sigmoid(z, sharpness=1.2)
            raw += w * normed
        return row["reach"] * raw

    for r in rows:
        r["v4c_composite"] = v4c_row_score(r)

    # ── pass 4: aggregate per agent, four flavours ────────────────────
    per_agent = defaultdict(list)
    for r in rows:
        per_agent[r["agent"]].append(r["v4c_composite"])

    agg = {}
    for a, lst in per_agent.items():
        lst_sorted = sorted(lst)
        agg[a] = {
            "n":      len(lst),
            "mean":   sum(lst) / len(lst),
            "median": statistics.median(lst),
            "p25":    lst_sorted[max(0, math.ceil(len(lst) * 0.25) - 1)],
            "min":    min(lst),
        }

    print("=== per-agent v4c aggregations ===")
    print(f"{'agent':<22}{'mean':>9}{'med':>9}{'P25':>9}{'min':>9}{'n':>4}")
    for a in sorted(agg.keys(), key=lambda x: -agg[x]["mean"]):
        v = agg[a]
        print(f"{a:<22}{v['mean']:>9.4f}{v['median']:>9.4f}"
              f"{v['p25']:>9.4f}{v['min']:>9.4f}{v['n']:>4}")

    # ── pass 5: BT/Elo on synthetic pairwise battles ──────────────────
    # Same battle synthesis as build_v4_leaderboard: for every pair of
    # agents that share a task, the higher v4c_composite wins. We use the
    # MEAN aggregation as the headline because it matches v2/v4/v4b
    # exactly; v4c-min is added as an "extreme view" leaderboard.
    def build_battles(score_key):
        by_task = defaultdict(dict)
        for r in rows:
            by_task[r["task"]].setdefault(r["agent"], r[score_key])
        battles = []
        for task, agents_to_score in by_task.items():
            agents = list(agents_to_score.items())
            for i in range(len(agents)):
                for j in range(i + 1, len(agents)):
                    a, sa = agents[i]
                    b, sb = agents[j]
                    if sa > sb:
                        battles.append({"a": a, "b": b, "score_a": 1.0})
                    elif sb > sa:
                        battles.append({"a": a, "b": b, "score_a": 0.0})
                    else:
                        battles.append({"a": a, "b": b, "score_a": 0.5})
        return battles

    battles_mean = build_battles("v4c_composite")

    # Also build per-agent min battles by precomputing agent-level min.
    agent_min = {a: agg[a]["min"] for a in agg}
    battles_min_synth = []
    agents_l = list(agent_min.items())
    for i in range(len(agents_l)):
        for j in range(i + 1, len(agents_l)):
            a, sa = agents_l[i]
            b, sb = agents_l[j]
            if sa > sb:
                battles_min_synth.append({"a": a, "b": b, "score_a": 1.0})
            elif sb > sa:
                battles_min_synth.append({"a": a, "b": b, "score_a": 0.0})
            else:
                battles_min_synth.append({"a": a, "b": b, "score_a": 0.5})

    elo_mean = compute_elo_with_ci(battles_mean, n_resamples=1000)
    elo_min = compute_elo_with_ci(battles_min_synth, n_resamples=1000)

    sig = rank_significance_test(battles_mean, n_permutations=1000)

    # ── pass 6: write artefacts ───────────────────────────────────────
    leaderboard_path = V4_DIR / "leaderboard_deep_v4c.json"
    out = {
        "formula": "v4c = reach × Σ w_i · sigmoid((p_i - μ_i)/σ_i · 1.2)",
        "weights": WEIGHTS,
        "pillar_stats": stats,
        "n_rows": len(rows),
        "per_agent": agg,
        "elo_mean": elo_mean,
        "elo_min":  elo_min,
        "rank_significance": sig,
    }
    leaderboard_path.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {leaderboard_path}")

    # Update each row JSON with v4c_composite
    for r in rows:
        d = json.load(open(r["path"]))
        d["v4c_composite"] = round(r["v4c_composite"], 4)
        json.dump(d, open(r["path"], "w"), indent=2)
    print(f"updated {len(rows)} row JSONs with v4c_composite")

    # ── pass 7: markdown report ───────────────────────────────────────
    lines = [
        "# Leaderboard — composite v4c (z-score normalised)",
        "",
        f"Sample: {len(rows)} rows across {len(per_agent)} agents.",
        "",
        "## Formula",
        "",
        "```",
        "v4c = url_reachability  ·  Σ  w_i · sigmoid( (p_i − μ_i) / σ_i  ·  1.2 )",
        "                            i∈11 pillars",
        "```",
        "",
        "Same weights as v4b. The z-score step ensures each pillar contributes",
        "in proportion to its *actual variance across the sample*, not its raw",
        "[0,1] band — so saturated pillars (internal_consistency) automatically",
        "stop dominating and high-variance pillars (source_diversity, factual",
        "_exactness) get to do real work.",
        "",
        "## Pillar variance budget",
        "",
        f"| Pillar | μ | σ | range | weight | effective info |",
        f"|---|---:|---:|---:|---:|---|",
    ]
    for k, w in WEIGHTS.items():
        s = stats[k]
        info_score = (s["sd"] / 0.5) * w  # rough info contribution
        lines.append(
            f"| {k} | {s['mu']:.2f} | {s['sd']:.2f} | "
            f"{s['min']:.2f}–{s['max']:.2f} | {w:.2f} | "
            f"{'★' * min(5, int(info_score * 20))} |"
        )

    lines += [
        "",
        "## Elo ranking — v4c mean aggregation",
        "",
        f"| Rank | Agent | Elo | CI (95%) | half-width | n |",
        f"|---:|---|---:|---|---:|---:|",
    ]
    ranked = sorted(elo_mean.items(), key=lambda kv: -kv[1]["elo"])
    for i, (a, v) in enumerate(ranked, 1):
        lines.append(
            f"| {i} | {a} | {v['elo']:.1f} | "
            f"[{v['elo_lo']:.0f}, {v['elo_hi']:.0f}] | "
            f"±{v['elo_half_width']:.0f} | {v['n_battles']} |"
        )

    # Adjacent gap analysis
    lines += ["", "## Adjacent-rank gaps", "",
              "| Pair | Gap (Elo) | p-value |",
              "|---|---:|---:|"]
    adj = {(p["higher"], p["lower"]): p for p in sig.get("adjacent_pairs", [])}
    for i in range(len(ranked) - 1):
        a, va = ranked[i]
        b, vb = ranked[i + 1]
        gap = va["elo"] - vb["elo"]
        pv = adj.get((a, b), adj.get((b, a), {})).get("p_value", None)
        lines.append(
            f"| {a} → {b} | {gap:.1f} | "
            f"{(f'{pv:.3f}' if pv is not None else '—')} |"
        )

    gaps = [ranked[i][1]["elo"] - ranked[i + 1][1]["elo"]
            for i in range(len(ranked) - 1)]
    if gaps:
        lines += [
            "",
            f"**min adj gap = {min(gaps):.1f} Elo · "
            f"mean adj gap = {sum(gaps)/len(gaps):.1f} Elo**",
        ]

    # min aggregation for reference
    lines += [
        "",
        "## Alternative — Elo on min aggregation (worst-case view)",
        "",
        "| Agent | mean | median | P25 | min |",
        "|---|---:|---:|---:|---:|",
    ]
    for a in sorted(agg.keys(), key=lambda x: -agg[x]["mean"]):
        v = agg[a]
        lines.append(
            f"| {a} | {v['mean']:.4f} | {v['median']:.4f} | "
            f"{v['p25']:.4f} | {v['min']:.4f} |"
        )

    md_path = V4_DIR / "LEADERBOARD_DEEP_V4C.md"
    md_path.write_text("\n".join(lines) + "\n")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
