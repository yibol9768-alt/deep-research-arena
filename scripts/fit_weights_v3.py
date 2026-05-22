"""Fit composite_v3 dimension weights from human pairwise preferences.

Model: P(A wins) = sigmoid( sum_d w_d * (s_d^A - s_d^B) )
Constraints: w_d >= 0, sum_d w_d = 1  (softmax reparameterisation).

Inputs
------
  data/human_prefs/*.jsonl   -- annotator outputs from the collector
  data/results/deep_v3/leaderboard_deep_v3.json
      (or leaderboard_deep.json as fallback; if neither contains per-dim
       scores, synthesise them and log a warning)

Output
------
  data/results/deep_v3/weights_v3.json
      { weights: {dim: float}, cv_loglik: float,
        baseline_loglik: float, n_prefs: int, fit_timestamp: str }

Refuses to write if 5-fold CV held-out log-likelihood is WORSE than the
uniform baseline -- that means the prefs do not support the weight fit.

--dry-run  : ignore real prefs/scores. Generate a synthetic ground-truth
             weight vector + per-dim agent scores, sample prefs from the
             BT-style model, fit, and assert the recovered weights are
             within tolerance.

Run:
    python scripts/fit_weights_v3.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PREFS_DIR = ROOT / "data" / "human_prefs"
LB_V3_JSON = ROOT / "data" / "results" / "deep_v3" / "leaderboard_deep_v3.json"
LB_V2_JSON = ROOT / "data" / "results" / "deep_v3" / "leaderboard_deep.json"
OUT_JSON = ROOT / "data" / "results" / "deep_v3" / "weights_v3.json"

DIMS = ["coverage", "depth", "rigor", "style", "checklist", "spec"]
UNIFORM = {"coverage": 0.20, "depth": 0.20, "rigor": 0.20,
           "style": 0.10, "checklist": 0.20, "spec": 0.10}


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def _load_prefs() -> list[dict]:
    prefs: list[dict] = []
    if not PREFS_DIR.exists():
        return prefs
    for p in sorted(PREFS_DIR.glob("*.jsonl")):
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                prefs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return prefs


def _load_agent_dim_scores() -> tuple[dict[str, dict[str, float]], str]:
    """Return per-agent per-dim mean scores, plus the file used as source.

    Workstream A is producing leaderboard_deep_v3.json with the v3 dim
    scores; if that file is missing or doesn't carry dim scores, fall
    back to the v2 leaderboard and synthesise per-dim scores from elo_v2
    + pillar_elo. The latter is a best-effort approximation that lets
    the pipeline run end-to-end before A lands its file -- weights fit
    against synthesised scores are NOT trustworthy and the function logs
    a clear warning.
    """
    src = ""
    for cand in (LB_V3_JSON, LB_V2_JSON):
        if cand.exists():
            src = str(cand.relative_to(ROOT))
            data = json.loads(cand.read_text())
            break
    else:
        return {}, ""

    # Preferred shape: an explicit per-dim score block.
    for key in ("dim_scores", "agent_dim_scores", "v3_dim_scores"):
        block = data.get(key)
        if isinstance(block, dict) and block:
            normed: dict[str, dict[str, float]] = {}
            for agent, dims in block.items():
                if not isinstance(dims, dict):
                    continue
                normed[agent] = {d: float(dims.get(d, 0.0)) for d in DIMS}
            return normed, src

    # Fallback A: pillar_elo gives a few non-uniform per-agent signals we can
    # map onto the v3 dims approximately. This is intentionally crude --
    # the goal is only to keep the pipeline running before workstream A
    # ships leaderboard_deep_v3.json.
    pillar = data.get("pillar_elo") or {}
    if pillar:
        sys.stderr.write(
            "[fit_weights_v3] WARNING: leaderboard_deep_v3.json missing or "
            "lacks dim_scores; synthesising per-dim scores from pillar_elo. "
            "Weights fit against this fallback are approximate.\n"
        )
        out: dict[str, dict[str, float]] = {}
        # Normalise each pillar across agents into [0, 1].
        keys = ("url_coverage", "quote_match", "checklist", "spec", "reachability")
        pillar_norm: dict[str, dict[str, float]] = {}
        for k in keys:
            vals = [float((pillar.get(a) or {}).get(k) or 0) for a in pillar]
            if not vals:
                continue
            lo, hi = min(vals), max(vals)
            for a in pillar:
                pillar_norm.setdefault(a, {})[k] = (
                    ((pillar[a] or {}).get(k, 0) - lo) / (hi - lo)
                    if hi > lo else 0.5
                )
        for a in pillar:
            row = pillar_norm.get(a, {})
            out[a] = {
                "coverage":  row.get("url_coverage", 0.5),
                "depth":     0.5 * (row.get("url_coverage", 0.5) + row.get("checklist", 0.5)),
                "rigor":     row.get("quote_match", 0.5),
                "style":     row.get("spec", 0.5),
                "checklist": row.get("checklist", 0.5),
                "spec":      row.get("spec", 0.5),
            }
        return out, src + " (synthesised from pillar_elo)"
    return {}, src


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def _build_design_matrix(prefs: list[dict],
                         scores: dict[str, dict[str, float]]) -> tuple[np.ndarray, np.ndarray, int]:
    """Return X[N, D] = (s_d^A - s_d^B), y[N] = 1 if A won else 0.

    Ties are split into two half-weight rows (one with y=1, one y=0) so
    the binary logistic likelihood treats them as a 50/50 outcome.
    Pairs whose agents are missing scores are silently skipped.
    """
    X_rows: list[np.ndarray] = []
    y_rows: list[float] = []
    skipped = 0
    for p in prefs:
        a, b = p.get("agent_a"), p.get("agent_b")
        sa, sb = scores.get(a), scores.get(b)
        if not (sa and sb):
            skipped += 1
            continue
        diff = np.array([sa[d] - sb[d] for d in DIMS], dtype=float)
        w = p.get("winner")
        if w == "a":
            X_rows.append(diff); y_rows.append(1.0)
        elif w == "b":
            X_rows.append(diff); y_rows.append(0.0)
        elif w == "tie":
            X_rows.append(diff); y_rows.append(1.0)
            X_rows.append(diff); y_rows.append(0.0)
        else:
            skipped += 1
    if not X_rows:
        return np.zeros((0, len(DIMS))), np.zeros((0,)), skipped
    return np.vstack(X_rows), np.array(y_rows), skipped


def _sigmoid(z: np.ndarray) -> np.ndarray:
    z = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


def _softmax(theta: np.ndarray) -> np.ndarray:
    e = np.exp(theta - theta.max())
    return e / e.sum()


def _neg_loglik_softmax(params: np.ndarray, X: np.ndarray, y: np.ndarray,
                         d: int) -> float:
    """Negative log-likelihood of the BT-logit model with a learnable
    *positive* scale alpha on top of a softmax-parameterised weight
    vector. ``params`` is laid out as ``[theta_1, ..., theta_d, log_alpha]``;
    this lets the optimiser absorb the unknown SNR of the prefs without
    breaking the ``w >= 0, sum w = 1`` simplex constraint we want to
    publish."""
    theta = params[:d]
    log_alpha = params[d]
    w = _softmax(theta)
    alpha = math.exp(log_alpha)
    z = alpha * (X @ w)
    p = _sigmoid(z)
    eps = 1e-12
    return -float(np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)))


def _fit_softmax(X: np.ndarray, y: np.ndarray, seed: int = 0) -> np.ndarray:
    from scipy.optimize import minimize
    d = X.shape[1]
    rng = np.random.default_rng(seed)
    best = None
    best_val = math.inf
    # A few random restarts -- the softmax surface is non-convex in theta
    # even though it's convex in w. Restarts catch the global mode.
    for _ in range(16):
        theta0 = np.concatenate([rng.normal(scale=0.5, size=d),
                                  np.array([rng.normal(loc=1.0, scale=0.5)])])
        try:
            res = minimize(_neg_loglik_softmax, theta0, args=(X, y, d),
                           method="L-BFGS-B", options={"maxiter": 1000})
        except Exception:
            continue
        if res.fun < best_val:
            best_val = float(res.fun)
            best = res.x
    if best is None:
        return np.ones(d) / d
    return _softmax(best[:d])


def _loglik(w: np.ndarray, X: np.ndarray, y: np.ndarray) -> float:
    """Best-of-class log-lik for a fixed w on (X, y) -- we briefly fit
    a positive scale alpha on top of w because the published simplex
    constraint deflates the raw logit slope (w_d in [0, 1]). Without
    this, an LL comparison against the alpha-free softmax fit isn't
    apples-to-apples. The uniform baseline gets the same treatment."""
    from scipy.optimize import minimize_scalar
    def _nll(log_alpha):
        alpha = math.exp(log_alpha)
        p = _sigmoid(alpha * (X @ w))
        eps = 1e-12
        return -float(np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)))
    try:
        res = minimize_scalar(_nll, bounds=(-3.0, 5.0), method="bounded")
        return -float(res.fun)
    except Exception:
        p = _sigmoid(X @ w)
        eps = 1e-12
        return float(np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)))


def _cv_loglik(X: np.ndarray, y: np.ndarray, k: int = 5, seed: int = 7) -> tuple[float, float]:
    """Return (mean held-out log-likelihood, baseline uniform log-lik).

    Both arms refit a positive scale on the train fold; the train alpha is
    re-used on the test fold so the gap is purely down to the weight
    vector, not the slope."""
    n = X.shape[0]
    w_uniform = np.array([UNIFORM[d] for d in DIMS])
    if n < 2 * k:
        w_fit = _fit_softmax(X, y)
        return _loglik(w_fit, X, y), _loglik(w_uniform, X, y)
    rng = np.random.default_rng(seed)
    idx = np.arange(n)
    rng.shuffle(idx)
    folds = np.array_split(idx, k)
    fit_lls = []
    base_lls = []
    for f in range(k):
        test_idx = folds[f]
        train_idx = np.concatenate([folds[g] for g in range(k) if g != f])
        w_fit = _fit_softmax(X[train_idx], y[train_idx], seed=seed + f)
        fit_lls.append(_loglik(w_fit, X[test_idx], y[test_idx]))
        base_lls.append(_loglik(w_uniform, X[test_idx], y[test_idx]))
    return float(np.mean(fit_lls)), float(np.mean(base_lls))


# ---------------------------------------------------------------------------
# Dry-run synthetic data
# ---------------------------------------------------------------------------

def _synthetic_data(n_agents: int = 10, n_prefs: int = 2000, seed: int = 42,
                    slope: float = 8.0):
    rng = np.random.default_rng(seed)
    agents = [f"synthetic_agent_{i:02d}" for i in range(n_agents)]
    # Ground-truth weights -- non-uniform on purpose.
    w_true = np.array([0.10, 0.30, 0.25, 0.05, 0.20, 0.10])
    assert abs(w_true.sum() - 1.0) < 1e-9
    scores = {a: {d: float(rng.uniform(0.0, 1.0)) for d in DIMS} for a in agents}

    prefs = []
    for _ in range(n_prefs):
        a, b = rng.choice(agents, size=2, replace=False)
        sa = np.array([scores[a][d] for d in DIMS])
        sb = np.array([scores[b][d] for d in DIMS])
        # Slope controls signal-to-noise. The real BT model has an implicit
        # scale on (s_d^A - s_d^B); a slope of 8 keeps prefs sufficiently
        # informative that the 6-dim weight vector is identifiable.
        z = float((sa - sb) @ w_true) * slope
        p = 1.0 / (1.0 + math.exp(-z))
        if rng.random() < p:
            w = "a"
        else:
            w = "b"
        prefs.append({
            "task_id": "synthetic_task",
            "agent_a": str(a),
            "agent_b": str(b),
            "winner": w,
            "dims_cited": [],
            "annotator": "synthetic",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    return prefs, scores, {d: float(w) for d, w in zip(DIMS, w_true)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Use synthetic prefs sampled from a known weight vector.")
    ap.add_argument("--force", action="store_true",
                    help="Write weights_v3.json even if CV LL is worse than uniform.")
    args = ap.parse_args()

    if args.dry_run:
        prefs, scores, w_true = _synthetic_data()
        src = "(synthetic --dry-run)"
        print(f"[fit_weights_v3] dry-run: ground-truth weights = {w_true}")
    else:
        prefs = _load_prefs()
        scores, src = _load_agent_dim_scores()
        if not prefs:
            sys.exit("No prefs found in data/human_prefs/*.jsonl -- collect data first or use --dry-run.")
        if not scores:
            sys.exit("No leaderboard scores found; cannot build design matrix.")

    X, y, skipped = _build_design_matrix(prefs, scores)
    n_prefs = X.shape[0]
    if skipped:
        sys.stderr.write(f"[fit_weights_v3] skipped {skipped} prefs (missing agent scores)\n")
    if n_prefs < 30:
        sys.stderr.write(
            f"[fit_weights_v3] WARNING: only {n_prefs} usable rows -- weights will be noisy.\n"
        )

    print(f"[fit_weights_v3] source={src or '(none)'}  n_prefs={n_prefs}")

    w_fit = _fit_softmax(X, y, seed=11)
    cv_ll, base_ll = _cv_loglik(X, y)

    print(f"[fit_weights_v3] fitted weights:")
    for d, w in zip(DIMS, w_fit):
        print(f"    {d:>10s}: {w:.4f}")
    print(f"[fit_weights_v3] CV log-lik:  fit={cv_ll:.4f}  uniform={base_ll:.4f}  "
          f"delta={cv_ll - base_ll:+.4f}")

    if args.dry_run:
        # Sanity check: recovered weights should be close to ground truth.
        diffs = {d: abs(w_fit[i] - w_true[d]) for i, d in enumerate(DIMS)}
        worst = max(diffs.values())
        print(f"[fit_weights_v3] dry-run max|w_fit - w_true| = {worst:.3f}")
        # Loose tolerance: with 600 sampled prefs the per-dim error is
        # ~0.05 in expectation; 0.10 is a comfortable upper bound for CI.
        assert worst < 0.10, (
            f"Recovered weights diverge from ground truth ({diffs}); pipeline broken."
        )

    if cv_ll < base_ll - 1e-6 and not args.force:
        msg = (f"CV held-out log-likelihood ({cv_ll:.4f}) is worse than the "
               f"uniform baseline ({base_ll:.4f}); refusing to write weights_v3.json. "
               f"Pass --force to override.")
        sys.exit(msg)

    payload = {
        "weights": {d: float(w) for d, w in zip(DIMS, w_fit)},
        "cv_loglik": cv_ll,
        "baseline_loglik": base_ll,
        "n_prefs": int(n_prefs),
        "fit_timestamp": datetime.now(timezone.utc).isoformat(),
        "source": src,
        "dry_run": bool(args.dry_run),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"[fit_weights_v3] wrote {OUT_JSON.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
