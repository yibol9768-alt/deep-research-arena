#!/usr/bin/env python3
"""E-13 axis diagnostics (internal audit 2026-07-08).

Reads the two truth-board snapshots (qwen3-8b, deepseek-v4-flash) and, from
their per-report raw axis scores, computes three things the weight-defence
discipline requires:

  1. per-report axis-axis Pearson and Spearman correlation matrices
     (per backbone and pooled): do the five axes carry independent signal?
  2. variance-contribution decomposition: how much of the CROSS-AGENT
     leaderboard spread (Var of the per-agent macro truth) each axis explains,
     measured by freezing that axis at its pooled effective mean and rem+
     aggregating.
  3. the "effective weight" table: for every quality axis, the fraction of
     reports whose RAW value sits below the eps=0.05 floor (so the stored
     nominal weight is not what actually moves that report's truth).

Model-free, replays byte-for-byte from the board JSONs. No production formula
is modified; this only reports.

Usage:
  python3 scripts/axis_diagnostics_e13.py \
      --boards-dir <dir with truth_board_<bb>.json> [--out e13.json]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

EPS = 0.05
GAMMA = 1.5
W = {"fact_support": 0.35, "proof_of_fetch": 0.25,
     "completeness": 0.30, "spec": 0.10}
# board axis key -> short name
AXES = [
    ("grounding_reach", "reach"),
    ("correctness_fact_support", "fact_support"),
    ("grounding_proof_of_fetch", "proof_of_fetch"),
    ("completeness", "completeness"),
    ("spec", "spec"),
]
QUALITY_AXES = ["fact_support", "proof_of_fetch", "completeness", "spec"]
SHORT = [s for _, s in AXES]
BACKBONES = ["qwen3-8b", "deepseek-v4-flash"]


def _compose(reach, fact, pof, comp, spec, gamma=GAMMA, eps=EPS):
    vals = {
        "fact_support": max(eps, fact),
        "proof_of_fetch": max(eps, pof),
        "completeness": max(eps, comp),
        "spec": max(eps, spec),
    }
    quality = sum(W[k] * vals[k] for k in W)
    truth = (max(0.0, reach) ** gamma) * quality
    return truth


def _pearson(x, y):
    n = len(x)
    if n < 2:
        return float("nan")
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def _rank(v):
    # average ranks (ties shared)
    order = sorted(range(len(v)), key=lambda i: v[i])
    ranks = [0.0] * len(v)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _spearman(x, y):
    return _pearson(_rank(x), _rank(y))


def _corr_matrix(rows, fn):
    m = {}
    for a in SHORT:
        m[a] = {}
        for b in SHORT:
            m[a][b] = round(fn([r[a] for r in rows], [r[b] for r in rows]), 4)
    return m


def _load_reports(board):
    """per_task -> list of {axis short: raw value, agent, task}."""
    out = []
    for agent, tasks in board["per_task"].items():
        for tid, d in tasks.items():
            ax = d["axes"]
            rec = {short: float(ax[key]) for key, short in AXES}
            rec["_agent"] = agent
            rec["_task"] = tid
            rec["_truth_stored"] = float(d["truth"])
            out.append(rec)
    return out


def _agent_macro(reports, truth_fn):
    by = {}
    for r in reports:
        by.setdefault(r["_agent"], []).append(truth_fn(r))
    return {a: sum(v) / len(v) for a, v in by.items()}


def _variance(d):
    vals = list(d.values())
    n = len(vals)
    m = sum(vals) / n
    return sum((x - m) ** 2 for x in vals) / n


def analyse_backbone(board):
    reports = _load_reports(board)
    n = len(reports)

    # 1. correlation matrices (raw axes)
    pearson = _corr_matrix(reports, _pearson)
    spearman = _corr_matrix(reports, _spearman)

    # baseline agent-macro-truth leaderboard variance (recomputed from raw axes
    # via compose so the decomposition is internally consistent)
    def truth_full(r):
        return _compose(r["reach"], r["fact_support"], r["proof_of_fetch"],
                        r["completeness"], r["spec"])
    base_macro = _agent_macro(reports, truth_full)
    base_var = _variance(base_macro)

    # 2. variance contribution: freeze each axis at its pooled EFFECTIVE mean
    # (post-floor for quality axes; raw for reach) so it contributes no spread.
    eff = {}
    for short in SHORT:
        if short in QUALITY_AXES:
            eff[short] = [max(EPS, r[short]) for r in reports]
        else:
            eff[short] = [r[short] for r in reports]
    eff_mean = {short: sum(eff[short]) / n for short in SHORT}

    var_contrib = {}
    for froz in SHORT:
        def truth_frozen(r, froz=froz):
            g = {s: r[s] for s in SHORT}
            # freeze the axis at the value that yields its effective mean
            g[froz] = eff_mean[froz]
            return _compose(g["reach"], g["fact_support"], g["proof_of_fetch"],
                            g["completeness"], g["spec"])
        macro = _agent_macro(reports, truth_frozen)
        v = _variance(macro)
        var_contrib[froz] = {
            "leaderboard_var_frozen": v,
            "delta_var": base_var - v,
            "pct_of_base_var": (round(100.0 * (base_var - v) / base_var, 2)
                                if base_var > 0 else None),
        }

    # 3. effective-weight table: fraction of reports where the RAW quality axis
    # is below the floor (nominal weight is not what moves the report).
    eff_weight = {}
    for short in QUALITY_AXES:
        below = sum(1 for r in reports if r[short] < EPS)
        eqfloor = sum(1 for r in reports if r[short] <= EPS)
        eff_weight[short] = {
            "nominal_weight": W[short],
            "n_reports": n,
            "frac_below_floor": round(below / n, 4),
            "frac_at_or_below_floor": round(eqfloor / n, 4),
            "raw_mean": round(sum(r[short] for r in reports) / n, 4),
            "effective_mean_post_floor": round(eff_mean[short], 4),
        }
    # reach: fraction exactly zero (gate fully closed) and mean
    reach_zero = sum(1 for r in reports if r["reach"] <= 0.0)
    reach_info = {
        "unfloored": True,
        "frac_reach_zero": round(reach_zero / n, 4),
        "raw_mean": round(sum(r["reach"] for r in reports) / n, 4),
    }

    return {
        "n_reports": n,
        "pearson": pearson,
        "spearman": spearman,
        "leaderboard_var_base": base_var,
        "variance_contribution": var_contrib,
        "effective_weight_table": eff_weight,
        "reach_axis": reach_info,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards-dir", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    bdir = Path(args.boards_dir)
    result = {"eps": EPS, "gamma": GAMMA, "quality_weights": W, "by_backbone": {}}
    pooled = []
    for bb in BACKBONES:
        board = json.loads((bdir / f"truth_board_{bb}.json").read_text())
        result["by_backbone"][bb] = analyse_backbone(board)
        pooled.extend(_load_reports(board))
    # pooled correlations
    result["pooled"] = {
        "n_reports": len(pooled),
        "pearson": _corr_matrix(pooled, _pearson),
        "spearman": _corr_matrix(pooled, _spearman),
    }
    txt = json.dumps(result, indent=1)
    if args.out:
        Path(args.out).write_text(txt)
        print("wrote", args.out)
    else:
        print(txt)


if __name__ == "__main__":
    main()
