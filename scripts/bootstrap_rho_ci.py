#!/usr/bin/env python3
"""Two-level bootstrap for the Elo-vs-grounding correlations.

Registry findings S1/S2/S3/S7/S8/S10/S11 (paper_iclr/UNREASONABLE_PARTS_REGISTRY.md):
the headline Spearman rho values are printed as point estimates although both
axes (judge Elo and grounding) are noisy estimates. This script propagates both
noise sources so every rho/tau in the paper can carry an honest CI.

Per bootstrap replicate (default B=2000 per board):
  1. resample battles with replacement (multinomial over deduped battles);
  2. refit Bradley-Terry (MM updates, pattern from scripts/select_rl_subset.py);
  3. resample per-task grounding with replacement for agents with >= 3 scored
     tasks; agents with fewer keep their fixed aggregate (recorded as
     "grounding_not_resampled", which UNDERCOUNTS uncertainty for them);
  4. recompute Spearman rho(Elo, grounding) and Kendall tau(raw Elo rank,
     gated rank) with gated = elo * grounding_pct / 100.

Also computed per board:
  - permutation two-sided p for the observed rho (grounding labels permuted;
    exact enumeration when n! <= 50000, else 10000 Monte Carlo permutations);
  - leave-one-out rho (drop each agent, refit BT) and its range;
  - bootstrap rank-stability matrix P(agent at rank r) for the Elo axis.

Boards:
  - framework: data/results/real/leaderboard_jury_elo.json.battles.jsonl,
    dedupe key (task, sorted pair) keeping LAST; battles involving claude-code
    or opencode are excluded (degraded rounds). Grounding from per-task
    (reach+quote)/2 in per_task_grounding.json, profile fallback from
    leaderboard_deep_v3.json.
  - backbone: data/results/real/leaderboard_jury_models.json.battles.jsonl
    (judge-error battles dropped, matching the published 643-clean-battle
    board); grounding fixed at the aggregate profile from
    leaderboard_models_v3.json (no per-task data), so its CI reflects Elo
    noise only.

Output: data/results/real/rho_bootstrap.json plus a compact stdout table.
Pure stdlib, deterministic given --seed.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from datetime import date
from itertools import permutations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "data" / "results" / "real"
DEEP = ROOT / "data" / "results" / "deep_v3"

FRAMEWORK_BATTLES = REAL / "leaderboard_jury_elo.json.battles.jsonl"
BACKBONE_BATTLES = REAL / "leaderboard_jury_models.json.battles.jsonl"
PER_TASK_GROUNDING = REAL / "per_task_grounding.json"
FRAMEWORK_PROFILE = DEEP / "leaderboard_deep_v3.json"
BACKBONE_PROFILE = DEEP / "leaderboard_models_v3.json"
OUT_PATH = REAL / "rho_bootstrap.json"

EXCLUDED_FRAMEWORK_AGENTS = ("claude-code", "opencode")  # degraded rounds
MIN_TASKS_FOR_RESAMPLE = 3
EXACT_PERM_LIMIT = 50000


# ---------------------------------------------------------------- loading


def load_battles(path, exclude_agents=(), drop_errors=False):
    """Parse battles jsonl -> (battles, stats).

    battles: list of (agent_a, agent_b, w) with w in {"a","b","tie"}.
    Dedupe key = (task, sorted pair), keeping the LAST occurrence.
    res.winner is relative to _a/_b of each line, so it is remapped to the
    winning agent name before dedupe (later reruns may swap sides).
    """
    dedup = {}
    n_raw = n_err = 0
    tasks = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        n_raw += 1
        res = rec.get("res") or {}
        if drop_errors and res.get("error"):
            n_err += 1
            continue
        a, b, task = rec["_a"], rec["_b"], rec["_task"]
        w = res.get("winner")
        if w not in ("a", "b", "tie"):
            continue
        winner = a if w == "a" else b if w == "b" else "tie"
        dedup[(task, tuple(sorted((a, b))))] = (task, a, b, winner)

    battles = []
    n_excluded = 0
    excl = set(exclude_agents)
    for task, a, b, winner in dedup.values():
        if a in excl or b in excl:
            n_excluded += 1
            continue
        tasks.add(task)
        battles.append((a, b, "a" if winner == a else "b" if winner == b else "tie"))
    stats = {
        "n_raw_lines": n_raw,
        "n_error_dropped": n_err,
        "n_after_dedupe": len(dedup),
        "n_excluded_degraded": n_excluded,
        "n_battles": len(battles),
        "n_tasks": len(tasks),
    }
    return battles, stats


def load_per_task_grounding(path):
    """per_task_grounding.json -> {agent: [per-task (reach+quote)/2, ...]} in [0,1]."""
    data = json.loads(path.read_text())
    per = {}
    for key, sc in data["scores"].items():
        agent = key.split("|", 1)[0]
        per.setdefault(agent, []).append(
            (float(sc.get("reach", 0.0)) + float(sc.get("quote", 0.0))) / 2.0
        )
    return per


def load_profile_grounding(path):
    """per_agent_profile -> {agent: (reach_pct+quote_pct)/2 / 100} in [0,1]."""
    data = json.loads(path.read_text())
    out = {}
    for agent, prof in (data.get("per_agent_profile") or {}).items():
        reach = float(prof.get("reachability_pct", 0.0))
        quote = float(prof.get("url_veracity_pct", 0.0))
        out[agent] = ((reach + quote) / 2.0) / 100.0
    return out


# ---------------------------------------------------------------- statistics
# _ranks/spearman/kendall follow scripts/select_rl_subset.py.


def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def _pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return num / den if den else 0.0


def spearman(x, y):
    return _pearson(_ranks(x), _ranks(y))


def kendall(x, y):
    n, c, d = len(x), 0, 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (x[i] - x[j]) * (y[i] - y[j])
            c += s > 0
            d += s < 0
    return (c - d) / (n * (n - 1) / 2)


def percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    pos = (len(sorted_vals) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def ci95(vals):
    s = sorted(vals)
    return [round(percentile(s, 0.025), 4), round(percentile(s, 0.975), 4)]


# ---------------------------------------------------------------- BT fit


def compress_battles(battles, agents):
    """Battles -> multinomial categories (i, j, w) with base counts.

    Only the (pair, outcome) triple matters for BT, so resampling N battles
    with replacement == a multinomial draw over these categories.
    """
    idx = {a: i for i, a in enumerate(agents)}
    counts = Counter((idx[a], idx[b], w) for a, b, w in battles)
    cats = sorted(counts)
    base = [counts[c] for c in cats]
    return cats, base


def bt_elo_from_counts(n_agents, cats, weights, iters):
    """Bradley-Terry via MM updates (ties count half a win each side)."""
    wins = [[0.0] * n_agents for _ in range(n_agents)]
    for (i, j, w), c in zip(cats, weights):
        if not c:
            continue
        if w == "a":
            wins[i][j] += c
        elif w == "b":
            wins[j][i] += c
        else:
            wins[i][j] += 0.5 * c
            wins[j][i] += 0.5 * c
    p = [1.0] * n_agents
    rng_i = range(n_agents)
    for _ in range(iters):
        newp = []
        for i in rng_i:
            num = sum(wins[i][j] for j in rng_i if j != i)
            den = 0.0
            for j in rng_i:
                if j == i:
                    continue
                nij = wins[i][j] + wins[j][i]
                if nij:
                    den += nij / (p[i] + p[j])
            newp.append(num / den if den else p[i])
        s = sum(newp) / n_agents
        p = [x / s for x in newp]
    return [400 * math.log10(max(x, 1e-12)) + 1000 for x in p]


# ---------------------------------------------------------------- inference


def perm_pvalue(elo_vec, ground_vec, rng, mc_iters):
    """Two-sided permutation p for rho: permute grounding labels across agents.

    Spearman == Pearson on ranks, and permuting labels permutes midranks
    identically, so only rank vectors are needed. Exact enumeration when
    n! <= EXACT_PERM_LIMIT, else Monte Carlo with add-one smoothing.
    """
    n = len(elo_vec)
    rx, ry = _ranks(elo_vec), _ranks(ground_vec)
    obs = abs(_pearson(rx, ry))
    eps = 1e-12
    if math.factorial(n) <= EXACT_PERM_LIMIT:
        hits = total = 0
        for pm in permutations(range(n)):
            hits += abs(_pearson(rx, [ry[i] for i in pm])) >= obs - eps
            total += 1
        return hits / total, "exact_%d_perms" % total
    ry2 = list(ry)
    hits = 0
    for _ in range(mc_iters):
        rng.shuffle(ry2)
        hits += abs(_pearson(rx, ry2)) >= obs - eps
    return (hits + 1) / (mc_iters + 1), "monte_carlo_%d_perms" % mc_iters


def leave_one_out_rhos(battles, agents, ground_point, bt_iters):
    out = {}
    for drop in agents:
        keep = [a for a in agents if a != drop]
        sub = [(a, b, w) for a, b, w in battles if a != drop and b != drop]
        cats, base = compress_battles(sub, keep)
        elo = bt_elo_from_counts(len(keep), cats, base, bt_iters)
        out[drop] = round(spearman(elo, [ground_point[a] for a in keep]), 4)
    return out


def resample_weights(rng, base, n_total):
    drawn = Counter(rng.choices(range(len(base)), weights=base, k=n_total))
    return [drawn.get(i, 0) for i in range(len(base))]


# ---------------------------------------------------------------- per board


def run_board(name, battles, stats, per_task, profile_fallback, boot, bt_iters,
              perm_iters, rng, extra_caveats):
    agents = sorted({x for a, b, _ in battles for x in (a, b)})
    n_agents = len(agents)

    # grounding point estimate per agent: per-task mean, else profile aggregate
    ground_point = {}
    used_fallback = []
    for a in agents:
        vals = per_task.get(a)
        if vals:
            ground_point[a] = sum(vals) / len(vals)
        elif a in profile_fallback:
            ground_point[a] = profile_fallback[a]
            used_fallback.append(a)
        else:
            raise SystemExit("%s: no grounding available for agent %s" % (name, a))
    resampled = sorted(a for a in agents
                       if len(per_task.get(a, [])) >= MIN_TASKS_FOR_RESAMPLE)
    not_resampled = sorted(set(agents) - set(resampled))

    cats, base = compress_battles(battles, agents)
    n_battles = len(battles)

    # point estimates (full data, long MM run)
    elo_point = bt_elo_from_counts(n_agents, cats, base, iters=200)
    g_vec = [ground_point[a] for a in agents]
    rho_point = spearman(elo_point, g_vec)
    # gated = elo * grounding_pct / 100 == elo * grounding_fraction
    gated_point = [e * g for e, g in zip(elo_point, g_vec)]
    tau_point = kendall(elo_point, gated_point)

    perm_p, perm_method = perm_pvalue(elo_point, g_vec, rng, perm_iters)
    loo = leave_one_out_rhos(battles, agents, ground_point, bt_iters=200)
    loo_vals = list(loo.values())

    # two-level bootstrap
    rhos, taus = [], []
    rank_counts = [[0] * n_agents for _ in range(n_agents)]  # [agent][rank]
    n_missing_agent = 0
    for _ in range(boot):
        w = resample_weights(rng, base, n_battles)
        appear = [0] * n_agents
        for (i, j, _), c in zip(cats, w):
            if c:
                appear[i] = 1
                appear[j] = 1
        if not all(appear):
            n_missing_agent += 1  # BT leaves the missing agent at prior 1000
        elo = bt_elo_from_counts(n_agents, cats, w, bt_iters)
        g = []
        for a in agents:
            vals = per_task.get(a, [])
            if a in ground_point and len(vals) >= MIN_TASKS_FOR_RESAMPLE:
                g.append(sum(rng.choices(vals, k=len(vals))) / len(vals))
            else:
                g.append(ground_point[a])
        rhos.append(spearman(elo, g))
        taus.append(kendall(elo, [e * x for e, x in zip(elo, g)]))
        for r, i in enumerate(sorted(range(n_agents), key=lambda i: -elo[i])):
            rank_counts[i][r] += 1

    # rank-stability matrix P(agent at rank r), rank 1 = highest Elo
    point_order = sorted(range(n_agents), key=lambda i: -elo_point[i])
    point_rank = {agents[i]: r + 1 for r, i in enumerate(point_order)}
    matrix = {agents[i]: [round(c / boot, 4) for c in rank_counts[i]]
              for i in range(n_agents)}
    top3 = []
    for r, i in enumerate(point_order[:3]):
        a = agents[i]
        top3.append({
            "agent": a,
            "point_rank": r + 1,
            "p_at_point_rank": round(rank_counts[i][r] / boot, 4),
            "p_in_top3": round(sum(rank_counts[i][:3]) / boot, 4),
        })

    caveats = list(extra_caveats)
    if not_resampled:
        caveats.append(
            "grounding_not_resampled agents (%s) keep a fixed aggregate "
            "grounding inside the bootstrap, so the reported CIs UNDERCOUNT "
            "their grounding uncertainty." % ", ".join(not_resampled))
    if used_fallback:
        caveats.append(
            "agents %s had no per-task grounding; used per_agent_profile "
            "aggregate fallback." % ", ".join(used_fallback))
    if n_missing_agent:
        caveats.append(
            "%d/%d replicates dropped an agent entirely from the battle "
            "resample (its Elo stayed at the 1000 prior)." % (n_missing_agent, boot))
    caveats.append(
        "tau compares the raw Elo ranking with gated = elo*grounding/100, a "
        "deterministic transform of the same two inputs; it is descriptive "
        "reordering evidence, not an independent finding (registry S8).")
    caveats.append(
        "the bootstrap CI captures measurement noise conditional on this "
        "fixed set of systems; it is NOT a test against zero. Use rho_perm_p "
        "for that: a CI away from zero with a large permutation p means the "
        "measured association is stable but indistinguishable from label "
        "exchangeability at this n (registry S1).")
    if per_task:
        cov = sorted((len(per_task.get(a, [])) for a in agents))
        caveats.append(
            "per-task grounding coverage is uneven (min %d, max %d tasks per "
            "agent); agents with few tasks contribute noisier grounding "
            "resamples (registry S10)." % (cov[0], cov[-1]))

    board = {
        "n_agents": n_agents,
        "n_battles": n_battles,
        "n_tasks": stats["n_tasks"],
        "battle_filtering": stats,
        "agents": {a: {
            "elo_point": round(elo_point[agents.index(a)], 1),
            "grounding_point": round(ground_point[a], 4),
            "n_grounding_tasks": len(per_task.get(a, [])),
            "point_rank": point_rank[a],
        } for a in agents},
        "rho_point": round(rho_point, 4),
        "rho_ci95": ci95(rhos),
        "rho_boot_mean": round(sum(rhos) / len(rhos), 4),
        "rho_perm_p": round(perm_p, 4),
        "rho_perm_method": perm_method,
        "loo_rho": loo,
        "loo_range": [round(min(loo_vals), 4), round(max(loo_vals), 4)],
        "tau_point": round(tau_point, 4),
        "tau_ci95": ci95(taus),
        "grounding_not_resampled": not_resampled,
        "rank_stability": {
            "rank1_is_highest_elo": True,
            "top3_diag": top3,
            "matrix": matrix,
        },
        "caveats": caveats,
    }
    return board


# ---------------------------------------------------------------- main


def fmt_ci(ci):
    return "[%+.2f, %+.2f]" % (ci[0], ci[1])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--boot", type=int, default=2000, help="bootstrap replicates per board")
    ap.add_argument("--bt-iters", type=int, default=60, help="MM iterations inside the bootstrap")
    ap.add_argument("--perm", type=int, default=10000, help="Monte Carlo permutations (when not exact)")
    ap.add_argument("--seed", type=int, default=20260702)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()

    per_task = load_per_task_grounding(PER_TASK_GROUNDING)
    fw_profile = load_profile_grounding(FRAMEWORK_PROFILE)
    bb_profile = load_profile_grounding(BACKBONE_PROFILE)

    fw_battles, fw_stats = load_battles(
        FRAMEWORK_BATTLES, exclude_agents=EXCLUDED_FRAMEWORK_AGENTS)
    bb_battles, bb_stats = load_battles(BACKBONE_BATTLES, drop_errors=True)

    boards = {}
    boards["framework"] = run_board(
        "framework", fw_battles, fw_stats, per_task, fw_profile,
        boot=args.boot, bt_iters=args.bt_iters, perm_iters=args.perm,
        rng=random.Random(args.seed),
        extra_caveats=[
            "battles involving %s excluded (degraded rounds); dedupe key "
            "(task, sorted pair) keeping the LAST rerun."
            % " / ".join(EXCLUDED_FRAMEWORK_AGENTS),
        ])
    boards["backbone"] = run_board(
        "backbone", bb_battles, bb_stats, per_task={}, profile_fallback=bb_profile,
        boot=args.boot, bt_iters=args.bt_iters, perm_iters=args.perm,
        rng=random.Random(args.seed + 1),
        extra_caveats=[
            "backbone battles derived from leaderboard_jury_models.json."
            "battles.jsonl with judge-error battles dropped (%d of %d raw), "
            "matching the published clean-battle board." % (
                bb_stats["n_error_dropped"], bb_stats["n_raw_lines"]),
            "no per-task grounding exists for the backbone board: grounding "
            "is fixed at the leaderboard_models_v3 aggregate, so the CI "
            "reflects Elo (battle) resampling only and UNDERCOUNTS total "
            "uncertainty.",
        ])

    out = {
        "generated": date.today().isoformat(),
        "script": "scripts/bootstrap_rho_ci.py",
        "registry_findings": ["S1", "S2", "S3", "S7", "S8", "S10", "S11"],
        "config": {
            "boot_replicates": args.boot,
            "bt_iters_bootstrap": args.bt_iters,
            "bt_iters_point": 200,
            "mc_perm_iters": args.perm,
            "exact_perm_limit": EXACT_PERM_LIMIT,
            "seed": args.seed,
            "min_tasks_for_grounding_resample": MIN_TASKS_FOR_RESAMPLE,
            "grounding_def": "(reach + quote) / 2, per task where available",
            "gated_def": "elo * grounding_pct / 100 (== elo * grounding_fraction)",
        },
        "boards": boards,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n")

    print("wrote %s" % args.out)
    hdr = ("board", "n_ag", "n_btl", "rho", "rho_ci95", "perm_p", "tau",
           "tau_ci95", "loo_range")
    rows = [hdr]
    for name, b in boards.items():
        rows.append((
            name, str(b["n_agents"]), str(b["n_battles"]),
            "%+.2f" % b["rho_point"], fmt_ci(b["rho_ci95"]),
            "%.3f" % b["rho_perm_p"], "%+.2f" % b["tau_point"],
            fmt_ci(b["tau_ci95"]), fmt_ci(b["loo_range"]),
        ))
    widths = [max(len(r[i]) for r in rows) for i in range(len(hdr))]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))
    for name, b in boards.items():
        t3 = ", ".join("%s r%d p=%.2f" % (t["agent"], t["point_rank"],
                                          t["p_at_point_rank"])
                       for t in b["rank_stability"]["top3_diag"])
        print("%s top-3 rank stability: %s" % (name, t3))


if __name__ == "__main__":
    main()
