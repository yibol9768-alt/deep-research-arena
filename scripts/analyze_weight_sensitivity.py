#!/usr/bin/env python3
"""Weight-sensitivity of the decidable truth ranking.

The quality-axis weights in the truth composition
(truth = reach**gamma * (0.35 fact + 0.25 PoF + 0.30 completeness + 0.10 spec),
each quality axis floored at eps=0.05; see src/eval/decidable_scorer.py
QUALITY_WEIGHTS) are stated conventions, not fitted. This script asks whether
the induced agent ranking depends on that choice, so the paper can quote a
number instead of an assertion.

Method: read the truth board's per-task axis scores, recompose per-task truth
under a candidate weight vector (reach unfloored, the four quality axes floored
at eps then weighted), average per agent over that agent's own tasks (the
board's macro view), and rank. Agents whose baseline truth is zero are gated:
reach is zero on every one of their tasks, so truth is zero for EVERY weight
vector (the eps floor only lifts the parenthesized quality term, never the
multiplicative gate); they are excluded from the ranking and reported as
context. Over the rankable agents we compute, versus the baseline ranking:
equal-weight agreement, N Dirichlet(alpha=2) draws (fraction preserving the
full ranking, fraction preserving the top two, mean pairwise inversion count),
and four extreme single-axis vectors (0.85 on one axis, 0.05 on the rest).

Pure stdlib, deterministic given --seed (Dirichlet via normalized Gamma draws
from random.Random, no wall-clock, no numpy RNG-version dependence).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# Quality axes in the composition order (matches decidable_scorer.compose_truth
# and the board's stored axis names).
QUALITY_AXES = ("fact_support", "proof_of_fetch", "completeness", "spec")
AXIS_KEY = {
    "fact_support": "correctness_fact_support",
    "proof_of_fetch": "grounding_proof_of_fetch",
    "completeness": "completeness",
    "spec": "spec",
}
REACH_KEY = "grounding_reach"

BASELINE_WEIGHTS = (0.35, 0.25, 0.30, 0.10)
EQUAL_WEIGHTS = (0.25, 0.25, 0.25, 0.25)
EPS_FLOOR = 0.05
DIRICHLET_ALPHA = 2.0


def macro_truth(tasks: list, weights, gamma: float, eps: float) -> float:
    """Mean over an agent's tasks of recomposed per-task truth."""
    tot = 0.0
    for d in tasks:
        ax = d["axes"]
        reach = max(0.0, float(ax[REACH_KEY]))
        quality = sum(
            w * max(float(ax[AXIS_KEY[name]]), eps)
            for w, name in zip(weights, QUALITY_AXES)
        )
        tot += (reach ** gamma) * quality
    return tot / len(tasks) if tasks else 0.0


def ranking(agent_tasks: dict, weights, gamma: float, eps: float) -> list:
    """Agents ordered by macro truth descending; ties broken by name so the
    order is a deterministic function of the scores alone."""
    scored = [
        (macro_truth(tasks, weights, gamma, eps), name)
        for name, tasks in agent_tasks.items()
    ]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [name for _, name in scored]


def inversions(order: list, baseline: list) -> int:
    """Pairwise discordances: pairs whose relative order differs from
    baseline (Kendall distance)."""
    pos = {a: i for i, a in enumerate(baseline)}
    n = len(order)
    idx = [pos[a] for a in order]
    return sum(
        1
        for i in range(n)
        for j in range(i + 1, n)
        if idx[i] > idx[j]
    )


def dirichlet(rng: random.Random, alpha: float, k: int) -> tuple:
    g = [rng.gammavariate(alpha, 1.0) for _ in range(k)]
    s = sum(g)
    return tuple(x / s for x in g)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--board",
        default="data/results/my5090_qwen8_partial_reports/"
        "truth_board_qwen8_partial.json",
    )
    ap.add_argument("--n-samples", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="data/results/weight_sensitivity.json")
    ap.add_argument(
        "--macros-out",
        default="paper_iclr/tables/weight_sensitivity_macros.tex",
    )
    args = ap.parse_args()

    board_path = (REPO / args.board) if not Path(args.board).is_absolute() \
        else Path(args.board)
    board = json.loads(board_path.read_text())
    gamma = float(board["gamma"])
    per_task = board["per_task"]

    agent_tasks = {a: list(t.values()) for a, t in per_task.items()}

    # Split into rankable (baseline truth > 0) and gated (zero for every weight
    # vector because reach is zero on all their tasks).
    baseline_macro = {
        a: macro_truth(tasks, BASELINE_WEIGHTS, gamma, EPS_FLOOR)
        for a, tasks in agent_tasks.items()
    }
    rankable = {a: t for a, t in agent_tasks.items() if baseline_macro[a] > 0.0}
    gated = sorted(a for a in agent_tasks if baseline_macro[a] <= 0.0)
    # Confirm the gating claim: a gated agent has reach == 0 on every task, so
    # no weight vector can lift it (the floor only touches the quality term).
    gated_max_reach = {
        a: max((float(d["axes"][REACH_KEY]) for d in agent_tasks[a]),
               default=0.0)
        for a in gated
    }
    assert all(r == 0.0 for r in gated_max_reach.values()), \
        "a gated agent has nonzero reach: it is not weight-invariant"

    baseline_ranking = ranking(rankable, BASELINE_WEIGHTS, gamma, EPS_FLOOR)

    # Equal weights.
    equal_ranking = ranking(rankable, EQUAL_WEIGHTS, gamma, EPS_FLOOR)
    equal_same = equal_ranking == baseline_ranking

    # Dirichlet draws.
    rng = random.Random(args.seed)
    n_full = n_top2 = 0
    tot_inv = 0
    for _ in range(args.n_samples):
        w = dirichlet(rng, DIRICHLET_ALPHA, len(QUALITY_AXES))
        order = ranking(rankable, w, gamma, EPS_FLOOR)
        if order == baseline_ranking:
            n_full += 1
        if order[:2] == baseline_ranking[:2]:
            n_top2 += 1
        tot_inv += inversions(order, baseline_ranking)
    frac_full = n_full / args.n_samples if args.n_samples else 0.0
    frac_top2 = n_top2 / args.n_samples if args.n_samples else 0.0
    mean_inv = tot_inv / args.n_samples if args.n_samples else 0.0

    # Extreme single-axis vectors.
    extremes = []
    for i, axis in enumerate(QUALITY_AXES):
        w = tuple(0.85 if j == i else 0.05 for j in range(len(QUALITY_AXES)))
        order = ranking(rankable, w, gamma, EPS_FLOOR)
        extremes.append({
            "axis": axis,
            "weights": {name: w[j] for j, name in enumerate(QUALITY_AXES)},
            "ranking": order,
            "same_as_baseline": order == baseline_ranking,
            "top2_same": order[:2] == baseline_ranking[:2],
        })
    n_extreme_same = sum(1 for e in extremes if e["same_as_baseline"])
    n_extreme_top2 = sum(1 for e in extremes if e["top2_same"])

    result = {
        "board": str(board_path.relative_to(REPO))
        if board_path.is_relative_to(REPO) else str(board_path),
        "gamma": gamma,
        "eps_floor": EPS_FLOOR,
        "seed": args.seed,
        "n_samples": args.n_samples,
        "dirichlet_alpha": DIRICHLET_ALPHA,
        "quality_axis_order": list(QUALITY_AXES),
        "baseline_weights": dict(zip(QUALITY_AXES, BASELINE_WEIGHTS)),
        "equal_weights": dict(zip(QUALITY_AXES, EQUAL_WEIGHTS)),
        "n_agents_ranked": len(rankable),
        "n_agents_gated": len(gated),
        "gated_note": (
            "these agents have reach == 0 on every task, so truth == 0 for "
            "every weight vector (the eps floor lifts only the quality term, "
            "never the multiplicative reach gate); they are excluded from the "
            "ranking-stability metrics because their order is undefined and "
            "invariant"
        ),
        "gated_agents": gated,
        "baseline_ranking": baseline_ranking,
        "baseline_macro_truth": {
            a: round(baseline_macro[a], 6) for a in baseline_ranking
        },
        "equal_weights_result": {
            "ranking": equal_ranking,
            "same_as_baseline": equal_same,
            "macro_truth": {
                a: round(macro_truth(rankable[a], EQUAL_WEIGHTS, gamma,
                                     EPS_FLOOR), 6)
                for a in equal_ranking
            },
        },
        "dirichlet": {
            "n_samples": args.n_samples,
            "alpha": DIRICHLET_ALPHA,
            "frac_identical_full_ranking": round(frac_full, 6),
            "frac_identical_top2": round(frac_top2, 6),
            "mean_pairwise_inversions": round(mean_inv, 6),
            "n_pairs": len(rankable) * (len(rankable) - 1) // 2,
        },
        "extreme_vectors": {
            "n_vectors": len(extremes),
            "n_preserving_full_ranking": n_extreme_same,
            "n_preserving_top2": n_extreme_top2,
            "detail": extremes,
        },
    }

    out_path = (REPO / args.out) if not Path(args.out).is_absolute() \
        else Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n")

    # ---- macros ----
    def pct(x: float) -> str:
        return f"{100 * x:g}\\%"

    macros = [
        "% AUTO-GENERATED by scripts/analyze_weight_sensitivity.py -- "
        "do not edit by hand.",
        "% Weight-sensitivity of the decidable truth ranking on the "
        "diagnostic partial board.",
        "% REAL numbers: recomposed from the board's per-task axis scores; "
        "recomputed on the full run.",
        f"\\newcommand{{\\wsNAgents}}{{{len(rankable)}}}",
        f"\\newcommand{{\\wsNGated}}{{{len(gated)}}}",
        f"\\newcommand{{\\wsNSamples}}{{{args.n_samples:,}}}",
        f"\\newcommand{{\\wsDirichletAlpha}}{{{DIRICHLET_ALPHA:g}}}",
        f"\\newcommand{{\\wsStablePct}}{{{pct(frac_full)}}}",
        f"\\newcommand{{\\wsTopTwoPct}}{{{pct(frac_top2)}}}",
        f"\\newcommand{{\\wsMeanInversions}}{{{mean_inv:.2f}}}",
        f"\\newcommand{{\\wsEqualWeightsSame}}"
        f"{{{'identical' if equal_same else 'reordered'}}}",
        f"\\newcommand{{\\wsNExtreme}}{{{len(extremes)}}}",
        f"\\newcommand{{\\wsNExtremeSame}}{{{n_extreme_same}}}",
        f"\\newcommand{{\\wsNExtremeTopTwo}}{{{n_extreme_top2}}}",
    ]
    macros_path = (REPO / args.macros_out) \
        if not Path(args.macros_out).is_absolute() else Path(args.macros_out)
    macros_path.parent.mkdir(parents=True, exist_ok=True)
    macros_path.write_text("\n".join(macros) + "\n")

    print(f"wrote {out_path}")
    print(f"wrote {macros_path}")
    print(f"rankable={len(rankable)} gated={len(gated)} "
          f"baseline_ranking={baseline_ranking}")
    print(f"dirichlet: full={frac_full:.4f} top2={frac_top2:.4f} "
          f"mean_inv={mean_inv:.4f} | equal_same={equal_same} | "
          f"extreme_same={n_extreme_same}/{len(extremes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
