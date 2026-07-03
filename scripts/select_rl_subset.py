#!/usr/bin/env python3
"""Select a small RL-training task subset whose evaluation agrees with the
full benchmark.

Motivation: RL on the full 70-task battle set is expensive. We want the
smallest task subset S such that ranking agents using only S reproduces
the full-set ranking, so cheap training-time evals remain predictive.

Method
  1. Fit Bradley-Terry Elo on ALL clean jury battles (rounds where every
     juror produced verdicts; the degraded claude-code/opencode rounds are
     excluded, see scripts/analyze_jury_reliability.py) -> reference
     ranking over agents.
  2. Greedy forward selection over tasks (candidates restricted to
     manifest-valid tasks by default): at each step add the task that
     maximizes Spearman rho between subset-Elo and reference Elo; stop at
     --target-rho sustained or --max-size.
  3. Validate: battle bootstrap (500x) on the selected subset -> CI for
     rho/tau vs reference; plus a grounding-rank consistency check over
     agents with wide per-task grounding coverage.

Outputs data/tasks/deep_research/rl_small/rl_small_manifest.json.
"""

import argparse
import collections
import json
import math
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BATTLES = REPO / "data/results/real/leaderboard_jury_elo.json.battles.jsonl"
MANIFEST = REPO / "data/golden/deep_clean/_manifest.json"
GROUNDING = None  # optional per-task grounding json path (agent|task -> reach/quote)
OUT_DIR = REPO / "data/tasks/deep_research/rl_small"
DEGRADED_AGENTS = {"claude-code", "opencode"}


def load_clean_battles():
    last = {}
    for line in open(BATTLES):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        last[(r["_task"], tuple(sorted((r["_a"], r["_b"]))))] = r
    out = []
    for r in last.values():
        if DEGRADED_AGENTS & {r["_a"], r["_b"]}:
            continue
        w = r["res"]["winner"]
        out.append((r["_task"], r["_a"], r["_b"], w))  # w in {a,b,tie}
    return out


def bt_elo(battles, agents=None, iters=200):
    """Bradley-Terry via MM updates; ties count half a win each side."""
    if agents is None:
        agents = sorted({x for _, a, b, _ in battles for x in (a, b)})
    idx = {a: i for i, a in enumerate(agents)}
    wins = [[0.0] * len(agents) for _ in agents]
    for _, a, b, w in battles:
        i, j = idx[a], idx[b]
        if w == "a":
            wins[i][j] += 1
        elif w == "b":
            wins[j][i] += 1
        else:
            wins[i][j] += 0.5
            wins[j][i] += 0.5
    p = [1.0] * len(agents)
    for _ in range(iters):
        newp = []
        for i in range(len(agents)):
            num = sum(wins[i][j] for j in range(len(agents)) if j != i)
            den = 0.0
            for j in range(len(agents)):
                if j == i:
                    continue
                nij = wins[i][j] + wins[j][i]
                if nij:
                    den += nij / (p[i] + p[j])
            newp.append(num / den if den else p[i])
        s = sum(newp) / len(newp)
        p = [x / s for x in newp]
    return {a: 400 * math.log10(max(p[idx[a]], 1e-12)) + 1000 for a in agents}


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


def spearman(x, y):
    rx, ry = _ranks(x), _ranks(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def kendall(x, y):
    n, c, d = len(x), 0, 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (x[i] - x[j]) * (y[i] - y[j])
            c += s > 0
            d += s < 0
    return (c - d) / (n * (n - 1) / 2)


def subset_rho(battles_by_task, tasks, ref_elo, agents):
    sub = [b for t in tasks for b in battles_by_task[t]]
    # require every agent to appear, else rank undefined -> heavy penalty
    seen = {x for _, a, b, _ in sub for x in (a, b)}
    if seen != set(agents):
        return -1.0, None
    elo = bt_elo(sub, agents)
    rho = spearman([elo[a] for a in agents], [ref_elo[a] for a in agents])
    return rho, elo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-size", type=int, default=15)
    ap.add_argument("--target-rho", type=float, default=0.95)
    ap.add_argument("--valid-only", action="store_true", default=True)
    ap.add_argument("--bootstrap", type=int, default=500)
    ap.add_argument("--grounding-json", default=None,
                    help="optional per-task grounding json for the secondary check")
    args = ap.parse_args()

    battles = load_clean_battles()
    agents = sorted({x for _, a, b, _ in battles for x in (a, b)})
    ref = bt_elo(battles, agents)
    print(f"clean battles={len(battles)} agents={len(agents)}")
    print("reference ranking:",
          [a for a in sorted(agents, key=lambda a: -ref[a])])

    battles_by_task = collections.defaultdict(list)
    for b in battles:
        battles_by_task[b[0]].append(b)

    verdicts = json.load(open(MANIFEST))["tasks"]
    def is_valid(t):
        v = verdicts.get(t)
        vd = v.get("verdict") if isinstance(v, dict) else v
        return vd == "valid"
    candidates = sorted(t for t in battles_by_task if (not args.valid_only) or is_valid(t))
    print(f"candidate tasks: {len(candidates)} (valid-only={args.valid_only})")

    selected, history = [], []
    hit = 0
    while len(selected) < args.max_size:
        best_t, best_rho = None, -2.0
        for t in candidates:
            if t in selected:
                continue
            rho, _ = subset_rho(battles_by_task, selected + [t], ref, agents)
            if rho > best_rho or (rho == best_rho and best_t and
                                  len(battles_by_task[t]) > len(battles_by_task[best_t])):
                best_t, best_rho = t, rho
        selected.append(best_t)
        history.append({"task": best_t, "rho_after": round(best_rho, 4),
                        "battles": len(battles_by_task[best_t])})
        print(f"  +{best_t}: rho={best_rho:.4f} (|S|={len(selected)})")
        hit = hit + 1 if best_rho >= args.target_rho else 0
        if hit >= 2:  # sustained across two consecutive additions
            break

    # bootstrap validation for every prefix size -> stability curve
    ref_vec = [ref[a] for a in agents]
    ci = lambda xs: (round(xs[int(0.025 * len(xs))], 4),
                     round(xs[int(0.975 * len(xs))], 4)) if xs else None

    def bootstrap_prefix(tasks, n_boot):
        sub = [b for t in tasks for b in battles_by_task[t]]
        rng = random.Random(42)
        rhos, taus = [], []
        for _ in range(n_boot):
            sample = [sub[rng.randrange(len(sub))] for _ in range(len(sub))]
            seen = {x for _, a, b, _ in sample for x in (a, b)}
            if seen != set(agents):
                continue
            elo = bt_elo(sample, agents, iters=100)
            vec = [elo[a] for a in agents]
            rhos.append(spearman(vec, ref_vec))
            taus.append(kendall(vec, ref_vec))
        rhos.sort(); taus.sort()
        return rhos, taus

    curve = []
    recommended = None
    for size in range(3, len(selected) + 1):
        rhos, taus = bootstrap_prefix(selected[:size], args.bootstrap)
        row = {"size": size,
               "rho_mean": round(sum(rhos) / len(rhos), 4) if rhos else None,
               "rho_ci95": ci(rhos), "tau_ci95": ci(taus)}
        curve.append(row)
        print(f"  size={size}: rho_mean={row['rho_mean']} ci={row['rho_ci95']}")
        if recommended is None and rhos and row["rho_ci95"][0] >= 0.85:
            recommended = size
    rhos, taus = bootstrap_prefix(selected, args.bootstrap)
    sub = [b for t in selected for b in battles_by_task[t]]
    final_rho, sub_elo = subset_rho(battles_by_task, selected, ref, agents)

    result = {
        "method": "greedy forward selection on clean-jury BT-Elo rank agreement; "
                  "degraded rounds excluded; candidates manifest-valid only",
        "n_agents": len(agents),
        "agents": agents,
        "reference_battles": len(battles),
        "tasks": selected,
        "n_tasks": len(selected),
        "subset_battles": len(sub),
        "battle_cost_fraction": round(len(sub) / len(battles), 4),
        "spearman_vs_full": round(final_rho, 4),
        "kendall_vs_full": round(kendall([sub_elo[a] for a in agents], ref_vec), 4),
        "bootstrap": {"n": len(rhos), "rho_mean": round(sum(rhos) / len(rhos), 4),
                      "rho_ci95": ci(rhos), "tau_mean": round(sum(taus) / len(taus), 4),
                      "tau_ci95": ci(taus)},
        "stability_curve": curve,
        "recommended_size": recommended,
        "selection_history": history,
    }

    # optional grounding-rank consistency over widely covered agents
    gpath = args.grounding_json
    if gpath and Path(gpath).exists():
        g = json.load(open(gpath))["scores"]
        cov = collections.defaultdict(dict)
        for k, v in g.items():
            a, t = k.split("|", 1)
            if v["reach"] is not None and v["quote"] is not None:
                cov[a][t] = (v["reach"] + v["quote"]) / 2
        wide = [a for a, m in cov.items() if len(m) >= 40 and a in agents]
        if len(wide) >= 5:
            full_g = [sum(cov[a].values()) / len(cov[a]) for a in wide]
            sub_g = []
            ok = True
            for a in wide:
                vals = [cov[a][t] for t in selected if t in cov[a]]
                if len(vals) < max(3, len(selected) // 3):
                    ok = False
                    break
                sub_g.append(sum(vals) / len(vals))
            if ok:
                result["grounding_check"] = {
                    "agents": wide,
                    "spearman_vs_full": round(spearman(sub_g, full_g), 4),
                }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "rl_small_manifest.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nwrote {out}")
    print(json.dumps({k: result[k] for k in
                      ("n_tasks", "battle_cost_fraction", "spearman_vs_full",
                       "kendall_vs_full", "bootstrap")}, indent=2))


if __name__ == "__main__":
    main()
