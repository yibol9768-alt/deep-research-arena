#!/usr/bin/env python3
"""Length-controlled Elo (AlpacaEval-LC style) for the jury battles.

Motivation (method audit 2026-07-02): on clean framework battles the longer
report wins 65.3% of non-tie battles, rising monotonically to 83.1% when one
side is >4x longer, despite the judge prompt instructing verbosity discount.
Following length-controlled AlpacaEval (arXiv 2404.04475), we refit the
pairwise preference model with a length covariate and report the ranking
with the length term zeroed (counterfactual equal-length preference).

Model (non-tie battles):
    P(a beats b) = sigmoid( theta_a - theta_b + phi * tanh(dlen / sigma) )
where dlen = words_a - words_b on the JUDGED text (4000-word truncation)
and sigma = std of dlen. LC score = theta (length term zeroed).

Inputs:
  data/results/real/leaderboard_jury_elo.json      (battle log)
  data/results/real/report_word_counts.txt         (wc -w of report files)
  data/results/deep_v3/leaderboard_deep_v3.json    (grounding profiles)

Outputs: printed comparison of raw-BT vs LC ranking, phi effect size, and
rho(Elo, grounding) under both. Excludes degraded claude-code/opencode
rounds (see scripts/analyze_jury_reliability.py).
"""

import json
import math
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "data/results/real/leaderboard_jury_elo.json"
WC = REPO / "data/results/real/report_word_counts.txt"
BOARD = REPO / "data/results/deep_v3/leaderboard_deep_v3.json"
DEGRADED = {"claude-code", "opencode"}
TRUNC = 4000


def load_battles():
    d = json.loads(LOG.read_text())
    last = {}
    for r in d["battle_log"]:
        last[(r["task"], tuple(sorted((r["agent_a"], r["agent_b"]))))] = r
    return [r for r in last.values()
            if not (DEGRADED & {r["agent_a"], r["agent_b"]})]


def load_wc():
    wc = {}
    for line in WC.read_text().splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        m = re.match(r"(.+?)__(.+?)_matrix\.md$", parts[1])
        if m:
            wc[(m.group(1), m.group(2))] = min(int(parts[0]), TRUNC)
    return wc


def spearman(x, y):
    def rk(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[o[j + 1]] == v[o[i]]:
                j += 1
            for k in range(i, j + 1):
                r[o[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = rk(x), rk(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den


def fit_logistic(obs, agents, with_length, iters=4000, lr=0.05, l2=1e-3):
    """obs: list of (ia, ib, y, z) with y=1 if a won, z=tanh(dlen/sigma)."""
    idx = {a: i for i, a in enumerate(agents)}
    theta = [0.0] * len(agents)
    phi = 0.0
    for it in range(iters):
        g_theta = [0.0] * len(agents)
        g_phi = 0.0
        for ia, ib, y, z in obs:
            m = theta[ia] - theta[ib] + (phi * z if with_length else 0.0)
            p = 1 / (1 + math.exp(-m))
            e = y - p
            g_theta[ia] += e
            g_theta[ib] -= e
            if with_length:
                g_phi += e * z
        for i in range(len(agents)):
            theta[i] += lr * (g_theta[i] / len(obs) - l2 * theta[i])
        if with_length:
            phi += lr * (g_phi / len(obs) - l2 * phi)
        # center for identifiability
        mean = sum(theta) / len(theta)
        theta = [t - mean for t in theta]
    return theta, phi


def main():
    rows = load_battles()
    wc = load_wc()
    agents = sorted({x for r in rows for x in (r["agent_a"], r["agent_b"])})
    idx = {a: i for i, a in enumerate(agents)}

    dlens = []
    pre = []
    for r in rows:
        w = r.get("winner")
        if w == "tie" or w is None:
            continue
        wa = wc.get((r["agent_a"], r["task"]))
        wb = wc.get((r["agent_b"], r["task"]))
        if not wa or not wb:
            continue
        dlens.append(wa - wb)
        pre.append((idx[r["agent_a"]], idx[r["agent_b"]],
                    1.0 if w == r["agent_a"] else 0.0, wa - wb))
    sigma = (sum(d * d for d in dlens) / len(dlens)) ** 0.5
    obs = [(ia, ib, y, math.tanh(d / sigma)) for ia, ib, y, d in pre]
    print(f"non-tie battles with lengths: {len(obs)}  sigma(dlen)={sigma:.0f} words")

    theta_raw, _ = fit_logistic(obs, agents, with_length=False)
    theta_lc, phi = fit_logistic(obs, agents, with_length=True)
    print(f"phi (length coefficient) = {phi:.3f}")
    print(f"  implied equal-strength win prob when 2x longer "
          f"(dlen ~ +{sigma:.0f}w): {1/(1+math.exp(-phi*math.tanh(1.0))):.1%}")

    board = json.loads(BOARD.read_text())
    grd = {a: (p["reachability_pct"] + p["url_veracity_pct"]) / 2
           for a, p in board["per_agent_profile"].items()}

    order_raw = sorted(agents, key=lambda a: -theta_raw[idx[a]])
    order_lc = sorted(agents, key=lambda a: -theta_lc[idx[a]])
    print(f"\n{'agent':20s} {'raw θ':>7s} {'LC θ':>7s} {'Δrank':>6s} {'grounding':>9s}")
    for a in order_raw:
        dr = order_raw.index(a) - order_lc.index(a)
        print(f"{a:20s} {theta_raw[idx[a]]:7.2f} {theta_lc[idx[a]]:7.2f} "
              f"{('+' if dr>0 else '')+str(dr) if dr else '--':>6s} {grd.get(a, float('nan')):9.1f}")

    g = [grd[a] for a in agents]
    print(f"\nrho(raw theta, grounding) = "
          f"{spearman([theta_raw[idx[a]] for a in agents], g):+.3f}")
    print(f"rho(LC theta,  grounding) = "
          f"{spearman([theta_lc[idx[a]] for a in agents], g):+.3f}")


if __name__ == "__main__":
    main()
