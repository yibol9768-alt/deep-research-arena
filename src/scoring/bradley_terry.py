"""Bradley-Terry MLE rating with bootstrap 95% CI.

Replaces sequential Elo for small-sample settings (< 500 battles total).
The BT model says P(i beats j) = s_i / (s_i + s_j), where s_k = exp(r_k).
MLE on log-scores (r_k) is convex and we solve with L-BFGS-B.

Output is on the same 400-Elo scale as traditional Elo: r_k * (400 / ln(10))
+ 1000 anchor. This makes BT ratings directly comparable to the sequential
Elo we reported before.

Bootstrap CI:
  - resample battles with replacement B=1000 times
  - refit BT each resample
  - report 2.5%/97.5% percentiles per agent as 95% CI half-width

Draws are split 50/50 as half-wins.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Iterable

import numpy as np
from scipy.optimize import minimize


ELO_SCALE = 400.0 / math.log(10.0)   # ≈ 173.718
ELO_ANCHOR = 1000.0


def _to_wins_matrix(battles: list[dict], agents: list[str]) -> np.ndarray:
    """Return W[i][j] = fractional wins of agent i over agent j (draws = 0.5).

    Accepts BOTH battle shapes used in this codebase:
      * {agent_a, agent_b, winner ∈ {agent_a, agent_b, 'tie'}}
      * {a1,      a2,      agent_winner ∈ {a1,      a2,      'tie'}}
    Previously only the first was honored, so any battle list produced by
    `arena._battles_for_task` (the shape `build_deep_leaderboard` uses)
    silently routed every game to a draw.
    """
    idx = {a: k for k, a in enumerate(agents)}
    W = np.zeros((len(agents), len(agents)))
    for b in battles:
        a = b.get("agent_a") or b.get("a1")
        c = b.get("agent_b") or b.get("a2")
        if a not in idx or c not in idx:
            continue
        w = b.get("winner") if "winner" in b else b.get("agent_winner", "")
        if w == a:
            W[idx[a], idx[c]] += 1
        elif w == c:
            W[idx[c], idx[a]] += 1
        else:
            W[idx[a], idx[c]] += 0.5
            W[idx[c], idx[a]] += 0.5
    return W


def _neg_log_lik(r: np.ndarray, W: np.ndarray, *, l2: float = 1e-2) -> float:
    """BT negative log-likelihood + L2 prior. r[0] pinned to 0 via caller.

    The L2 prior (default ``λ=0.01``) prevents an unbounded MLE for an
    agent with zero wins — without it the rating diverges to -∞ and the
    optimizer returns a machine-dependent outlier instead of regressing
    toward the prior. ``λ=0.01`` corresponds to a prior std of ~17 Elo
    (after the ELO_SCALE multiplication) so it's almost invisible for
    well-resolved agents but pulls floating zero-win agents toward 0.
    """
    n = len(r)
    ll = 0.0
    for i in range(n):
        for j in range(n):
            if i == j or W[i, j] == 0:
                continue
            log_pij = r[i] - np.logaddexp(r[i], r[j])
            ll += W[i, j] * log_pij
    return -ll + 0.5 * l2 * float(np.sum(r * r))


def fit_bradley_terry(battles: list[dict]) -> dict[str, float]:
    """Fit BT MLE and return Elo-scaled ratings per agent."""
    agents = sorted({b.get("agent_a") for b in battles} | {b.get("agent_b") for b in battles})
    agents = [a for a in agents if a]
    if len(agents) < 2:
        return {a: ELO_ANCHOR for a in agents}

    W = _to_wins_matrix(battles, agents)
    n = len(agents)
    # Pin r[0] = 0 for identifiability; optimize r[1..n-1].
    x0 = np.zeros(n - 1)

    def obj(x: np.ndarray) -> float:
        r = np.concatenate([[0.0], x])
        return _neg_log_lik(r, W)

    res = minimize(obj, x0, method="L-BFGS-B")
    r_full = np.concatenate([[0.0], res.x])
    # Center at mean 0 then scale to Elo.
    r_full = r_full - r_full.mean()
    elo = {a: float(ELO_ANCHOR + ELO_SCALE * r_full[i]) for i, a in enumerate(agents)}
    return elo


def bootstrap_ci(
    battles: list[dict],
    n_boot: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
) -> dict[str, dict[str, float]]:
    """Return {agent: {'elo': mean, 'lo': p_alpha/2, 'hi': p_1-alpha/2,
    'half_width': (hi-lo)/2}}.

    For benchmark papers, reporting half-width is cleanest: "BT-Elo 1123 ±47".
    """
    rng = random.Random(seed)
    n = len(battles)
    agents = sorted({b.get("agent_a") for b in battles} | {b.get("agent_b") for b in battles})
    agents = [a for a in agents if a]
    draws: dict[str, list[float]] = defaultdict(list)

    for _ in range(n_boot):
        sample = [battles[rng.randrange(n)] for _ in range(n)]
        try:
            elo = fit_bradley_terry(sample)
        except Exception:
            continue
        for a in agents:
            draws[a].append(elo.get(a, ELO_ANCHOR))

    base = fit_bradley_terry(battles)
    lo_q, hi_q = alpha / 2, 1 - alpha / 2
    out = {}
    for a in agents:
        vals = sorted(draws[a]) if draws[a] else [base.get(a, ELO_ANCHOR)]
        lo = float(np.quantile(vals, lo_q)) if vals else base.get(a, ELO_ANCHOR)
        hi = float(np.quantile(vals, hi_q)) if vals else base.get(a, ELO_ANCHOR)
        out[a] = {
            "elo": round(base.get(a, ELO_ANCHOR), 1),
            "lo": round(lo, 1),
            "hi": round(hi, 1),
            "half_width": round((hi - lo) / 2, 1),
            "n_boot": len(vals),
        }
    return out


def render_bt_table(ci: dict[str, dict[str, float]]) -> str:
    rows = sorted(ci.items(), key=lambda x: -x[1]["elo"])
    lines = ["| Rank | Agent | BT-Elo | 95% CI | ± |", "|---:|---|---:|---|---:|"]
    for i, (a, r) in enumerate(rows, 1):
        ci_str = f"[{r['lo']:.0f}, {r['hi']:.0f}]"
        lines.append(f"| {i} | {a} | {r['elo']:.0f} | {ci_str} | ±{r['half_width']:.0f} |")
    return "\n".join(lines)
