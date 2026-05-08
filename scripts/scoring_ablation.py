#!/usr/bin/env python3
"""Scoring ablation study for deep-tier benchmark.

Analyses:
1. Leave-one-out ablation: drop each dimension, recompute composite, check rank changes
2. Inter-dimension correlation matrix (Pearson + Spearman)
3. Weight sensitivity: sweep each weight ±50%, measure rank stability (Kendall tau)
4. Per-agent dimension profiles (radar data)

Reads existing score files (v2 era: url_cov, reach, quote, nli, spec, judge).
Outputs: SCORING_ABLATION.md + scoring_ablation.json

Usage:
    python3 scripts/scoring_ablation.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy import stats as sp_stats

import os as _os
ROOT = Path(__file__).resolve().parents[1]
# Defaults to deep_v3 (10-agent paper corpus). Old 5-agent runs in
# data/results/deep/ via DEEP_RESULTS_DIR override.
DEEP_RESULTS = ROOT / _os.environ.get("DEEP_RESULTS_DIR", "data/results/deep_v3")


def load_all_scores() -> list[dict]:
    rows = []
    for p in sorted(DEEP_RESULTS.glob("*_matrix.score.json")):
        name = p.name
        if "__" not in name:
            continue
        agent = name.split("__")[0]
        task = name.split("__")[1].split("_matrix")[0]
        d = json.load(open(p))
        rows.append({
            "agent": agent,
            "task": task,
            "url_cov": d["url_coverage"]["score"],
            "reach": d["url_reachability"]["score"],
            "quote": d["quote_match"]["score"],
            "nli": d["claim_nli"]["score"],
            "spec": d["composite"]["spec_pass_fraction"],
            "judge": d["checklist"]["pass_rate"],
            "v2": d["composite"]["composite_score"],
            "v1": d["composite"]["composite_v1"],
        })
    return rows


# ---------- V2 formula reconstruction ----------
# v2: truth = reach * (0.5+0.5*quote) * (0.5+0.5*nli)
#     quality = 0.4*url_cov + 0.4*judge + 0.2*spec
#     composite = truth * quality

V2_DIMS = ["url_cov", "judge", "spec", "reach", "quote", "nli"]

V2_WEIGHTS = {
    "url_cov": 0.40,
    "judge":   0.40,
    "spec":    0.20,
}


def compute_v2(row: dict) -> float:
    quality = (V2_WEIGHTS["url_cov"] * row["url_cov"]
               + V2_WEIGHTS["judge"] * row["judge"]
               + V2_WEIGHTS["spec"] * row["spec"])
    qm = 0.5 + 0.5 * row["quote"]
    nli = 0.5 + 0.5 * row["nli"]
    truth = row["reach"] * qm * nli
    return truth * quality


def compute_v2_drop(row: dict, drop_dim: str) -> float:
    """Recompute v2 with one dimension zeroed out."""
    r = dict(row)
    r[drop_dim] = 0.0
    return compute_v2(r)


def compute_v2_reweight(row: dict, weight_overrides: dict) -> float:
    """Recompute v2 with modified quality weights (renormalized)."""
    w = dict(V2_WEIGHTS)
    w.update(weight_overrides)
    total = sum(w.values())
    if total == 0:
        return 0.0
    quality = sum(w[k] * row[k] / total for k in ["url_cov", "judge", "spec"])
    qm = 0.5 + 0.5 * row["quote"]
    nli = 0.5 + 0.5 * row["nli"]
    truth = row["reach"] * qm * nli
    return truth * quality


def agent_mean_scores(rows: list[dict], score_fn) -> dict[str, float]:
    by_agent = defaultdict(list)
    for r in rows:
        by_agent[r["agent"]].append(score_fn(r))
    return {a: float(np.mean(vs)) for a, vs in by_agent.items()}


def ranking(means: dict[str, float]) -> list[str]:
    return sorted(means, key=means.get, reverse=True)


def kendall_tau(rank_a: list[str], rank_b: list[str]) -> float:
    idx_a = {name: i for i, name in enumerate(rank_a)}
    idx_b = {name: i for i, name in enumerate(rank_b)}
    agents = list(idx_a.keys())
    n = len(agents)
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = agents[i], agents[j]
            diff = (idx_a[a] - idx_a[b]) * (idx_b[a] - idx_b[b])
            if diff > 0:
                concordant += 1
            elif diff < 0:
                discordant += 1
    pairs = n * (n - 1) / 2
    return (concordant - discordant) / pairs if pairs > 0 else 1.0


# ---------- Main ----------
def main():
    rows = load_all_scores()
    if not rows:
        print("No score files found.", file=sys.stderr)
        return 1

    agents = sorted(set(r["agent"] for r in rows))
    tasks = sorted(set(r["task"] for r in rows))
    print(f"Loaded {len(rows)} scores: {len(agents)} agents × {len(tasks)} tasks")

    lines = []
    lines.append("# Scoring Ablation Study\n")
    lines.append(f"*{len(rows)} score files, {len(agents)} agents, {len(tasks)} tasks.*\n")

    # ===== 1. Baseline ranking =====
    baseline_means = agent_mean_scores(rows, compute_v2)
    baseline_rank = ranking(baseline_means)
    lines.append("## 1. Baseline V2 Ranking\n")
    lines.append("| Rank | Agent | Mean V2 |")
    lines.append("|---:|---|---:|")
    for i, a in enumerate(baseline_rank):
        lines.append(f"| {i+1} | {a} | {baseline_means[a]:.4f} |")
    lines.append("")

    # ===== 2. Leave-one-out ablation =====
    lines.append("## 2. Leave-One-Out Ablation\n")
    lines.append("Drop each dimension (set to 0), recompute V2, check rank change.\n")
    lines.append("| Dropped Dim | Ranking | Kendall τ vs Baseline | Rank Changes |")
    lines.append("|---|---|---:|---|")

    ablation_results = {}
    for dim in V2_DIMS:
        means = agent_mean_scores(rows, lambda r, d=dim: compute_v2_drop(r, d))
        rank = ranking(means)
        tau = kendall_tau(baseline_rank, rank)
        changes = []
        for a in agents:
            b_pos = baseline_rank.index(a) + 1
            n_pos = rank.index(a) + 1
            if b_pos != n_pos:
                changes.append(f"{a}: {b_pos}→{n_pos}")
        changes_str = "; ".join(changes) if changes else "none"
        lines.append(f"| {dim} | {' > '.join(rank)} | {tau:.2f} | {changes_str} |")
        ablation_results[dim] = {"rank": rank, "tau": tau, "means": means}
    lines.append("")

    # ===== 3. Inter-dimension correlation =====
    lines.append("## 3. Inter-Dimension Correlation Matrix\n")

    dim_arrays = {}
    for dim in V2_DIMS:
        dim_arrays[dim] = np.array([r[dim] for r in rows])

    lines.append("### Pearson r\n")
    header = "| | " + " | ".join(V2_DIMS) + " |"
    sep = "|---|" + "|".join(["---:"] * len(V2_DIMS)) + "|"
    lines.append(header)
    lines.append(sep)
    pearson_matrix = {}
    for d1 in V2_DIMS:
        row_vals = []
        for d2 in V2_DIMS:
            if d1 == d2:
                row_vals.append("1.00")
            else:
                r, p = sp_stats.pearsonr(dim_arrays[d1], dim_arrays[d2])
                row_vals.append(f"{r:.2f}")
                pearson_matrix[(d1, d2)] = r
        lines.append(f"| {d1} | " + " | ".join(row_vals) + " |")
    lines.append("")

    lines.append("### Spearman ρ\n")
    lines.append(header)
    lines.append(sep)
    spearman_matrix = {}
    for d1 in V2_DIMS:
        row_vals = []
        for d2 in V2_DIMS:
            if d1 == d2:
                row_vals.append("1.00")
            else:
                r, p = sp_stats.spearmanr(dim_arrays[d1], dim_arrays[d2])
                row_vals.append(f"{r:.2f}")
                spearman_matrix[(d1, d2)] = r
        lines.append(f"| {d1} | " + " | ".join(row_vals) + " |")
    lines.append("")

    # Flag highly correlated pairs
    lines.append("### Highly correlated pairs (|Spearman ρ| > 0.7)\n")
    high_corr = []
    for d1, d2 in combinations(V2_DIMS, 2):
        rho = spearman_matrix.get((d1, d2), 0)
        if abs(rho) > 0.7:
            high_corr.append((d1, d2, rho))
    if high_corr:
        for d1, d2, rho in sorted(high_corr, key=lambda x: -abs(x[2])):
            lines.append(f"- **{d1}** ↔ **{d2}**: ρ = {rho:.3f}")
    else:
        lines.append("None found — all pairwise |ρ| ≤ 0.7.")
    lines.append("")

    # ===== 4. Weight sensitivity =====
    lines.append("## 4. Weight Sensitivity Analysis\n")
    lines.append("Sweep each quality weight from 50% to 150% of default (renormalized). "
                 "Measure Kendall τ stability of agent ranking.\n")

    multipliers = [0.5, 0.75, 1.0, 1.25, 1.5]
    quality_dims = ["url_cov", "judge", "spec"]

    lines.append("| Dim | Default W | 0.5× | 0.75× | 1.0× | 1.25× | 1.5× | Min τ |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")

    sensitivity_results = {}
    for dim in quality_dims:
        taus = []
        for m in multipliers:
            override = {dim: V2_WEIGHTS[dim] * m}
            means = agent_mean_scores(rows, lambda r, o=override: compute_v2_reweight(r, o))
            rank = ranking(means)
            tau = kendall_tau(baseline_rank, rank)
            taus.append(tau)
        min_tau = min(taus)
        tau_strs = " | ".join(f"{t:.2f}" for t in taus)
        lines.append(f"| {dim} | {V2_WEIGHTS[dim]:.2f} | {tau_strs} | {min_tau:.2f} |")
        sensitivity_results[dim] = {"taus": taus, "min_tau": min_tau}
    lines.append("")

    # Also test: what if we completely drop the truth gate (reach)?
    # NOTE: leaderboard v1 = pure additive quality (NO reach gate), NOT the scorer's stored composite_v1
    lines.append("### Truth gate removal test\n")
    lines.append("What happens if we drop the reachability gate entirely?\n")
    lines.append("(Leaderboard v1 = 0.4·url_cov + 0.4·judge + 0.2·spec, **no** reachability gate)\n")

    def compute_additive_v1(row):
        return (0.40 * row["url_cov"] + 0.40 * row["judge"] + 0.20 * row["spec"])

    v1_means = agent_mean_scores(rows, compute_additive_v1)
    v1_rank = ranking(v1_means)
    tau_v1 = kendall_tau(baseline_rank, v1_rank)
    lines.append(f"- V2 ranking (reach-gated): {' > '.join(baseline_rank)}")
    lines.append(f"- V1 ranking (additive, no gate): {' > '.join(v1_rank)}")
    lines.append(f"- Kendall τ = **{tau_v1:.2f}** — {'ranking inverts!' if tau_v1 < 0 else 'stable' if tau_v1 > 0.6 else 'partially changed'}")
    if tau_v1 < 0.6:
        changes = []
        for a in sorted(set(r["agent"] for r in rows)):
            b_pos = baseline_rank.index(a) + 1
            n_pos = v1_rank.index(a) + 1
            if b_pos != n_pos:
                changes.append(f"{a}: {b_pos}→{n_pos}")
        lines.append(f"- Rank changes: {'; '.join(changes)}")
    lines.append("")

    # ===== 5. Per-agent dimension profiles =====
    lines.append("## 5. Per-Agent Dimension Profiles\n")
    lines.append("Mean score per dimension per agent.\n")
    header = "| Agent | " + " | ".join(V2_DIMS) + " |"
    sep = "|---|" + "|".join(["---:"] * len(V2_DIMS)) + "|"
    lines.append(header)
    lines.append(sep)

    agent_profiles = {}
    for agent in agents:
        agent_rows = [r for r in rows if r["agent"] == agent]
        profile = {}
        row_vals = []
        for dim in V2_DIMS:
            mean = float(np.mean([r[dim] for r in agent_rows]))
            profile[dim] = mean
            row_vals.append(f"{mean:.3f}")
        agent_profiles[agent] = profile
        lines.append(f"| {agent} | " + " | ".join(row_vals) + " |")
    lines.append("")

    # ===== 6. Dimension variance contribution =====
    lines.append("## 6. Dimension Discriminative Power\n")
    lines.append("Inter-agent variance vs intra-agent variance (F-ratio, higher = more discriminative).\n")
    lines.append("| Dimension | Inter-agent var | Intra-agent var | F-ratio |")
    lines.append("|---|---:|---:|---:|")

    for dim in V2_DIMS:
        grand_mean = np.mean([r[dim] for r in rows])
        inter = np.mean([len([r for r in rows if r["agent"] == a]) *
                         (np.mean([r[dim] for r in rows if r["agent"] == a]) - grand_mean) ** 2
                         for a in agents])
        intra = np.mean([np.var([r[dim] for r in rows if r["agent"] == a]) for a in agents])
        f_ratio = inter / intra if intra > 1e-10 else float("inf")
        lines.append(f"| {dim} | {inter:.4f} | {intra:.4f} | {f_ratio:.2f} |")
    lines.append("")

    # ===== 7. Summary =====
    lines.append("## 7. Summary & Recommendations\n")

    # Auto-generate findings
    findings = []

    # Check truth gate impact
    if tau_v1 < 0.8:
        findings.append("**F1: Truth gate is decisive.** Removing reachability gate changes ranking substantially "
                        f"(τ={tau_v1:.2f}), confirming that URL truthfulness is the primary discriminator. "
                        "Agents with fluent but fabricated URLs rise; grounded agents fall.")

    # Check redundant dimensions
    for d1, d2, rho in high_corr:
        findings.append(f"**Redundancy warning:** {d1} and {d2} are highly correlated (ρ={rho:.3f}). "
                        "Consider merging or dropping one.")

    # Check dimensions that don't discriminate
    for dim in V2_DIMS:
        vals = [r[dim] for r in rows]
        if np.std(vals) < 0.05:
            findings.append(f"**Low variance:** {dim} (σ={np.std(vals):.3f}) barely varies across runs — "
                            "it contributes weight but little discrimination.")

    # Check ablation stability
    unstable = [(d, v["tau"]) for d, v in ablation_results.items() if v["tau"] < 0.8]
    for dim, tau in unstable:
        findings.append(f"**Sensitive dimension:** dropping {dim} changes ranking (τ={tau:.2f}).")

    if not findings:
        findings.append("All dimensions appear well-calibrated: no high correlations, "
                        "no zero-variance dimensions, ranking is stable under ablation.")

    for f in findings:
        lines.append(f"- {f}")
    lines.append("")

    # Write outputs
    md_path = ROOT / "SCORING_ABLATION.md"
    md_path.write_text("\n".join(lines))
    print(f"Wrote {md_path}")

    json_out = {
        "n_scores": len(rows),
        "n_agents": len(agents),
        "n_tasks": len(tasks),
        "baseline_ranking": baseline_rank,
        "baseline_means": baseline_means,
        "ablation": {k: {"rank": v["rank"], "tau": v["tau"]} for k, v in ablation_results.items()},
        "pearson": {f"{k[0]}__{k[1]}": v for k, v in pearson_matrix.items()},
        "spearman": {f"{k[0]}__{k[1]}": v for k, v in spearman_matrix.items()},
        "sensitivity": sensitivity_results,
        "agent_profiles": agent_profiles,
        "v1_vs_v2_tau": tau_v1,
    }
    json_path = ROOT / "scoring_ablation.json"
    json_path.write_text(json.dumps(json_out, indent=2))
    print(f"Wrote {json_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
