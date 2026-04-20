"""Item Response Theory calibration over our agent × task composite scores.

Fits a 2-parameter logistic (2-PL) IRT model:
    P(correct | agent θ, task a, task b) = sigmoid( a * (θ - b) )
where:
    θ_agent      = agent ability (high = better)
    a_task       = task discrimination (high = separates good/bad)
    b_task       = task difficulty (high = harder)

We "dichotomize" continuous composite scores with a median-threshold:
    correct = 1 if composite >= median(task)
    correct = 0 otherwise

This is a rough binarization but standard in IRT-on-continuous literature
(and what DRACO-IRT 2026 uses).

Output:
    data/results/IRT_CALIBRATION.md     — item analysis table
    data/results/irt_calibration.json   — raw params + fit diagnostics

Critical for paper:
    - Tasks with |discrimination| < 0.5 → remove or rewrite (they don't
      separate good agents from bad)
    - Tasks with difficulty at extreme tail (< -2 or > 2) → saturated
      (everyone succeeds or everyone fails — no signal)

Sample-size caveat: with only ~14 agents and 4 tasks, IRT estimates are
WIDE. Treat as directional only. Report requires ≥ 30 agents and 20
tasks for publishable IRT.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results"


def _load_matrix() -> tuple[list[str], list[str], np.ndarray]:
    """Return (agents, tasks, M) where M[i,j] is agent i's composite on task j.
    NaN if agent didn't run task."""
    rows: dict[tuple[str, str], float] = {}
    for p in sorted(RESULTS.glob("final_*.json")):
        if p.name.endswith(".answer.md"):
            continue
        # Prefer .ed.json (v3.2 weights)
        ed = p.with_name(p.stem + ".ed.json")
        src = ed if ed.exists() else p
        try:
            d = json.loads(src.read_text())
        except Exception:
            continue
        a = d.get("agent")
        t = d.get("task_id")
        c = d.get("composite")
        if not a or not t or c is None:
            continue
        rows[(a, t)] = float(c)

    agents = sorted({a for a, _ in rows})
    tasks = sorted({t for _, t in rows})
    M = np.full((len(agents), len(tasks)), np.nan)
    ai = {a: i for i, a in enumerate(agents)}
    tj = {t: j for j, t in enumerate(tasks)}
    for (a, t), c in rows.items():
        M[ai[a], tj[t]] = c
    return agents, tasks, M


def _dichotomize(M: np.ndarray) -> np.ndarray:
    """Convert composite scores to 0/1 per task by median threshold."""
    out = np.full_like(M, np.nan)
    for j in range(M.shape[1]):
        col = M[:, j]
        valid = col[~np.isnan(col)]
        if valid.size < 2:
            continue
        thr = float(np.median(valid))
        out[:, j] = (col >= thr).astype(float)
    return out


def _fit_2pl(Y: np.ndarray, seed: int = 0, verbose: bool = False) -> dict:
    """Fit 2-PL IRT via joint MLE on θ (agents), a, b (items)."""
    rng = np.random.default_rng(seed)
    n_a, n_t = Y.shape
    # Pack: θ (n_a) + a (n_t) + b (n_t) = n_a + 2*n_t
    x0 = rng.normal(scale=0.1, size=n_a + 2 * n_t)

    def unpack(x):
        th = x[:n_a]
        a = x[n_a:n_a + n_t]
        b = x[n_a + n_t:]
        return th, a, b

    def neg_ll(x):
        th, a, b = unpack(x)
        ll = 0.0
        for i in range(n_a):
            for j in range(n_t):
                if np.isnan(Y[i, j]):
                    continue
                z = float(a[j]) * (float(th[i]) - float(b[j]))
                # stabilized sigmoid
                if z > 0:
                    log_sig = -math.log1p(math.exp(-z))
                    log_one_minus = -z - math.log1p(math.exp(-z))
                else:
                    log_sig = z - math.log1p(math.exp(z))
                    log_one_minus = -math.log1p(math.exp(z))
                y = float(Y[i, j])
                ll += y * log_sig + (1 - y) * log_one_minus
        return -ll

    # Identifiability: anchor θ to mean 0 and std 1 by soft penalty
    def penalty(x):
        th, _, _ = unpack(x)
        return 0.1 * (th.mean() ** 2) + 0.05 * ((th.var() - 1.0) ** 2)

    res = minimize(lambda x: neg_ll(x) + penalty(x), x0, method="L-BFGS-B",
                   options={"maxiter": 400})
    th, a, b = unpack(res.x)

    # Post-hoc sign correction: IRT 2-PL is identifiable up to sign of θ
    # and a (flip both → same likelihood). With n_tasks small, the MLE
    # may converge to the "inverted" branch. Detect and flip by
    # correlating θ with per-agent mean score on observed items.
    row_means = np.nanmean(
        np.where(np.isnan(Y), np.nan, Y), axis=1
    )
    try:
        corr = float(np.corrcoef(th, row_means)[0, 1])
    except Exception:
        corr = 0.0
    if corr < 0:
        th = -th
        a = -a
    # Clip extremes for readability (don't affect relative ranking)
    a = np.clip(a, -5, 5)
    b = np.clip(b, -5, 5)

    return {
        "theta": th.tolist(),
        "a": a.tolist(),
        "b": b.tolist(),
        "fun": float(res.fun),
        "converged": bool(res.success),
        "sign_flipped": corr < 0,
    }


def _item_analysis(tasks: list[str], params: dict) -> list[dict]:
    out = []
    for j, tid in enumerate(tasks):
        a = params["a"][j]
        b = params["b"][j]
        flag = "OK"
        if abs(a) < 0.5:
            flag = "LOW_DISCRIM"  # task doesn't separate agents
        elif abs(b) > 2.5:
            flag = "SATURATED"
        elif a < 0:
            flag = "INVERTED"  # bad agents score higher than good — suspicious
        out.append({
            "task_id": tid,
            "discrimination": round(a, 3),
            "difficulty": round(b, 3),
            "flag": flag,
        })
    return out


def render(agents: list[str], params: dict, items: list[dict], M: np.ndarray) -> str:
    lines = [
        "# IRT Calibration — 2-PL Item Analysis",
        "",
        f"**n_agents** = {len(agents)}    "
        f"**n_tasks** = {len(items)}    "
        f"**observations** = {int((~np.isnan(M)).sum())}",
        "",
        "Note: with n_tasks this small, IRT estimates are directional only. "
        "Treat flags as hypotheses to investigate, not verdicts.",
        "",
        "## Agent ability (θ, higher = better)",
        "",
        "| Agent | θ |",
        "|---|---:|",
    ]
    for a, th in sorted(zip(agents, params["theta"]), key=lambda x: -x[1]):
        lines.append(f"| {a} | {th:+.2f} |")

    lines += [
        "",
        "## Task calibration",
        "",
        "| Task | Discrimination (a) | Difficulty (b) | Flag |",
        "|---|---:|---:|:---:|",
    ]
    for it in sorted(items, key=lambda x: -x["discrimination"]):
        lines.append(
            f"| {it['task_id']} | {it['discrimination']:+.2f} | "
            f"{it['difficulty']:+.2f} | **{it['flag']}** |"
        )

    lines += [
        "",
        "## Interpretation",
        "",
        "- **θ (theta)**: agent ability on this test-set scale. θ≈0 means average, "
        "θ > 1 means clearly above-average across all tasks jointly.",
        "- **a (discrimination)**: how strongly the task separates good from bad "
        "agents. a<0.5 = task doesn't inform the ranking, consider dropping.",
        "- **b (difficulty)**: the θ value at which agents flip from mostly-fail to "
        "mostly-succeed. b < -2 = trivial; b > 2 = saturated-hard. Mid-range b "
        "(−1..+1) is ideal.",
        "",
        "## Flags",
        "",
        "- **OK**: mid-range b, healthy a. Keep.",
        "- **LOW_DISCRIM**: |a|<0.5, task doesn't separate agents. Rewrite or drop.",
        "- **SATURATED**: |b|>2.5, everyone succeeds or fails. No signal.",
        "- **INVERTED**: a<0, worse agents score higher — suspicious scorer bug "
        "(e.g. length-rewarding pillar pulls longer bad reports above shorter good ones).",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    agents, tasks, M = _load_matrix()
    if len(agents) < 2 or len(tasks) < 2:
        print("need at least 2 agents × 2 tasks")
        return 1
    print(f"Loaded matrix: {len(agents)} agents × {len(tasks)} tasks, "
          f"{int((~np.isnan(M)).sum())} observations")
    Y = _dichotomize(M)
    params = _fit_2pl(Y, seed=42)
    items = _item_analysis(tasks, params)

    out_json = RESULTS / "irt_calibration.json"
    out_md = RESULTS / "IRT_CALIBRATION.md"
    out_json.write_text(json.dumps({
        "agents": agents, "tasks": tasks,
        "params": params, "items": items,
        "n_obs": int((~np.isnan(M)).sum()),
    }, indent=2, ensure_ascii=False))
    out_md.write_text(render(agents, params, items, M))
    print(f"Wrote {out_md}")

    # Summary
    flagged = [i for i in items if i["flag"] != "OK"]
    print(f"\nFlagged tasks: {len(flagged)}/{len(items)}")
    for i in flagged:
        print(f"  {i['task_id']}: a={i['discrimination']:+.2f} b={i['difficulty']:+.2f} [{i['flag']}]")
    print("\nTop 3 θ:")
    for a, th in sorted(zip(agents, params["theta"]), key=lambda x: -x[1])[:3]:
        print(f"  {a}: θ={th:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
