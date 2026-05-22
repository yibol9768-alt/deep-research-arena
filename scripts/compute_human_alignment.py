"""Measure alignment between composite_v3 and human pairwise preferences.

For every annotated pair (A, B, winner) in data/human_prefs/*.jsonl we
compute the agent-level human winner-rate vs the agent-level composite_v3
score, then report Spearman, Pearson, and Kendall tau between the two.
A markdown summary lands in docs/HUMAN_ALIGNMENT_REPORT.md.

Composite source preference order:
  1. ``src.scoring.leaderboard_composites.composite_v3_softfloor``
     (workstream A's new entry point)
  2. ``src.scoring.leaderboard_composites.composite_v3``
     (currently-shipping floor=0.1 variant)
  3. A synthesised linear combination over the v3 dim scores in
     ``data/results/deep_v3/leaderboard_deep_v3.json``

--dry-run  : use a synthetic prefs/scores fixture so the pipeline can be
             validated before any real annotations are collected.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PREFS_DIR = ROOT / "data" / "human_prefs"
LB_V3_JSON = ROOT / "data" / "results" / "deep_v3" / "leaderboard_deep_v3.json"
LB_V2_JSON = ROOT / "data" / "results" / "deep_v3" / "leaderboard_deep.json"
OUT_MD = ROOT / "docs" / "HUMAN_ALIGNMENT_REPORT.md"

DIMS = ["coverage", "depth", "rigor", "style", "checklist", "spec"]
UNIFORM = {"coverage": 0.20, "depth": 0.20, "rigor": 0.20,
           "style": 0.10, "checklist": 0.20, "spec": 0.10}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _load_prefs() -> list[dict]:
    if not PREFS_DIR.exists():
        return []
    out: list[dict] = []
    for p in sorted(PREFS_DIR.glob("*.jsonl")):
        for ln in p.read_text().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out


def _load_dim_scores() -> tuple[dict[str, dict[str, float]], str]:
    for cand in (LB_V3_JSON, LB_V2_JSON):
        if cand.exists():
            data = json.loads(cand.read_text())
            for key in ("dim_scores", "agent_dim_scores", "v3_dim_scores"):
                block = data.get(key)
                if isinstance(block, dict) and block:
                    out: dict[str, dict[str, float]] = {}
                    for agent, dims in block.items():
                        if not isinstance(dims, dict):
                            continue
                        out[agent] = {d: float(dims.get(d, 0.0)) for d in DIMS}
                    return out, str(cand.relative_to(ROOT))
            # Fallback: approximate from pillar_elo (see fit_weights_v3).
            pillar = data.get("pillar_elo") or {}
            if pillar:
                approx: dict[str, dict[str, float]] = {}
                # Normalise pillar elos into [0, 1].
                keys = ("url_coverage", "quote_match", "checklist", "spec", "reachability")
                pn: dict[str, dict[str, float]] = {}
                for k in keys:
                    vals = [float((pillar.get(a) or {}).get(k) or 0) for a in pillar]
                    if not vals:
                        continue
                    lo, hi = min(vals), max(vals)
                    for a in pillar:
                        pn.setdefault(a, {})[k] = (
                            ((pillar[a] or {}).get(k, 0) - lo) / (hi - lo)
                            if hi > lo else 0.5
                        )
                for a in pillar:
                    row = pn.get(a, {})
                    approx[a] = {
                        "coverage":  row.get("url_coverage", 0.5),
                        "depth":     0.5 * (row.get("url_coverage", 0.5) + row.get("checklist", 0.5)),
                        "rigor":     row.get("quote_match", 0.5),
                        "style":     row.get("spec", 0.5),
                        "checklist": row.get("checklist", 0.5),
                        "spec":      row.get("spec", 0.5),
                    }
                return approx, str(cand.relative_to(ROOT)) + " (approx via pillar_elo)"
    return {}, ""


def _resolve_composite_fn() -> tuple[Callable[[dict], float], str]:
    """Pick the freshest composite_v3 callable available from src.scoring.

    Returns ``(fn, label)``. ``fn`` accepts a score JSON of the v3 shape;
    here we adapt it to a per-dim dict using ``_dims_as_score_blob``.
    """
    try:
        from src.scoring import leaderboard_composites as lc  # noqa: WPS433
    except Exception:
        return _uniform_composite, "uniform-fallback (import failed)"
    for name in ("composite_v3_softfloor", "composite_v3"):
        fn = getattr(lc, name, None)
        if callable(fn):
            return _wrap_v3(fn), f"src.scoring.leaderboard_composites.{name}"
    return _uniform_composite, "uniform-fallback"


def _dims_as_score_blob(dims: dict[str, float]) -> dict:
    """Pack per-dim scores into the dict shape composite_v3 expects."""
    return {
        "url_reachability":   {"score": 1.0},  # already factored into dims; neutral gate
        "url_coverage":       {"score": dims.get("coverage", 0.0)},
        "quote_match":        {"score": dims.get("rigor", 0.0)},
        "checklist":          {"pass_rate": dims.get("checklist", 0.0)},
        "markdown_spec":      {"words_ok": dims.get("spec", 0.0) >= 0.5,
                                "citations_ok": dims.get("spec", 0.0) >= 0.5,
                                "paragraphs_ok": dims.get("spec", 0.0) >= 0.5},
        "citation_alignment": {"score": dims.get("checklist", 0.0)},
        "analysis_depth":     {"score": dims.get("depth", 0.0)},
        "presentation":       {"score": dims.get("style", 0.0)},
    }


def _wrap_v3(fn):
    def _call(dims: dict[str, float]) -> float:
        return float(fn(_dims_as_score_blob(dims)))
    return _call


def _uniform_composite(dims: dict[str, float]) -> float:
    return sum(UNIFORM[d] * dims.get(d, 0.0) for d in DIMS)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _rank(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(len(x), dtype=float)
    # Average ties (simple implementation).
    uniq, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
    if counts.max() > 1:
        sums = np.zeros_like(uniq, dtype=float)
        for i, r in enumerate(ranks):
            sums[inv[i]] += r
        avg = sums / counts
        ranks = avg[inv]
    return ranks


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2:
        return float("nan")
    xd, yd = x - x.mean(), y - y.mean()
    denom = math.sqrt(float((xd ** 2).sum() * (yd ** 2).sum()))
    if denom == 0:
        return float("nan")
    return float((xd * yd).sum() / denom)


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    return _pearson(_rank(x), _rank(y))


def _kendall_tau(x: np.ndarray, y: np.ndarray) -> float:
    n = len(x)
    if n < 2:
        return float("nan")
    concord = discord = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = x[i] - x[j]; dy = y[i] - y[j]
            s = dx * dy
            if s > 0: concord += 1
            elif s < 0: discord += 1
    total = n * (n - 1) / 2
    if total == 0:
        return float("nan")
    return float((concord - discord) / total)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _human_winrates(prefs: list[dict]) -> dict[str, float]:
    wins = defaultdict(float); games = defaultdict(float)
    for p in prefs:
        a, b, w = p.get("agent_a"), p.get("agent_b"), p.get("winner")
        if not (a and b and w):
            continue
        games[a] += 1; games[b] += 1
        if w == "a": wins[a] += 1
        elif w == "b": wins[b] += 1
        else:
            wins[a] += 0.5; wins[b] += 0.5
    return {agent: wins[agent] / games[agent] for agent in games if games[agent] > 0}


def _disagreements(prefs: list[dict],
                   scores: dict[str, dict[str, float]],
                   composite_fn) -> list[dict]:
    """Per-pair disagreements between the human winner and the model's
    predicted winner, ranked by absolute composite gap."""
    rows = []
    for p in prefs:
        a, b, w = p.get("agent_a"), p.get("agent_b"), p.get("winner")
        sa, sb = scores.get(a), scores.get(b)
        if not (a and b and sa and sb and w in ("a", "b")):
            continue
        ca = composite_fn(sa); cb = composite_fn(sb)
        pred = "a" if ca > cb else "b" if cb > ca else "tie"
        if pred != w and pred != "tie":
            rows.append({
                "task_id": p.get("task_id"),
                "agent_a": a, "agent_b": b,
                "human_winner": w, "model_winner": pred,
                "ca": ca, "cb": cb, "gap": abs(ca - cb),
            })
    rows.sort(key=lambda r: -r["gap"])
    return rows


# ---------------------------------------------------------------------------
# Synthetic dry-run
# ---------------------------------------------------------------------------

def _synthetic_data():
    rng = np.random.default_rng(31)
    n_agents = 8
    agents = [f"agent_{i:02d}" for i in range(n_agents)]
    w_true = np.array([0.10, 0.30, 0.25, 0.05, 0.20, 0.10])
    scores = {a: {d: float(rng.uniform(0.0, 1.0)) for d in DIMS} for a in agents}
    prefs = []
    for _ in range(500):
        a, b = rng.choice(agents, size=2, replace=False)
        sa = np.array([scores[a][d] for d in DIMS])
        sb = np.array([scores[b][d] for d in DIMS])
        z = float((sa - sb) @ w_true) * 4.0
        p = 1.0 / (1.0 + math.exp(-z))
        w = "a" if rng.random() < p else "b"
        prefs.append({"task_id": "synthetic",
                      "agent_a": str(a), "agent_b": str(b),
                      "winner": w, "dims_cited": [],
                      "annotator": "synthetic",
                      "timestamp": datetime.now(timezone.utc).isoformat()})
    return prefs, scores


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        prefs, scores = _synthetic_data()
        score_src = "(synthetic --dry-run)"
    else:
        prefs = _load_prefs()
        scores, score_src = _load_dim_scores()
        if not prefs:
            sys.exit("No prefs found in data/human_prefs/*.jsonl -- collect data first or use --dry-run.")
        if not scores:
            sys.exit("No leaderboard scores available; cannot align.")

    composite_fn, comp_label = _resolve_composite_fn()
    win = _human_winrates(prefs)
    agents_common = sorted(set(scores) & set(win))
    if len(agents_common) < 2:
        sys.exit(f"Only {len(agents_common)} agents in common between prefs and scores -- nothing to correlate.")

    human_rates = np.array([win[a] for a in agents_common])
    composites = np.array([composite_fn(scores[a]) for a in agents_common])

    sp = _spearman(human_rates, composites)
    pe = _pearson(human_rates, composites)
    kt = _kendall_tau(human_rates, composites)
    disagreements = _disagreements(prefs, scores, composite_fn)

    # ---- Markdown report ----
    lines = []
    lines.append("# Human Alignment Report")
    lines.append("")
    lines.append(f"_Generated: {datetime.now(timezone.utc).isoformat()}_")
    lines.append(f"_Composite source: `{comp_label}`_")
    lines.append(f"_Dim-score source: `{score_src}`_")
    lines.append(f"_Prefs: {len(prefs)} rows, {len(agents_common)} agents in common_")
    lines.append("")
    lines.append("## Correlation summary")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|--------|-------|")
    lines.append(f"| Spearman rho     | {sp:.4f} |")
    lines.append(f"| Pearson r        | {pe:.4f} |")
    lines.append(f"| Kendall tau      | {kt:.4f} |")
    lines.append("")
    lines.append("Target: Spearman >= 0.85. ")
    lines.append("If Spearman < 0.75, refit weights with `python scripts/fit_weights_v3.py`.")
    lines.append("")
    lines.append("## Per-agent table")
    lines.append("")
    lines.append("| agent | n_battles | human_winrate | composite_v3 |")
    lines.append("|-------|-----------|---------------|--------------|")
    n_battles = defaultdict(int)
    for p in prefs:
        if p.get("agent_a") in agents_common: n_battles[p["agent_a"]] += 1
        if p.get("agent_b") in agents_common: n_battles[p["agent_b"]] += 1
    for a in sorted(agents_common, key=lambda x: -win[x]):
        lines.append(f"| `{a}` | {n_battles[a]} | {win[a]:.3f} | {composite_fn(scores[a]):.4f} |")
    lines.append("")
    lines.append("## Top 10 biggest disagreements")
    lines.append("")
    lines.append("Pairs where the model picked the opposite winner from the human.")
    lines.append("")
    lines.append("| task | agent_a | agent_b | human | model | composite gap |")
    lines.append("|------|---------|---------|-------|-------|---------------|")
    for r in disagreements[:10]:
        lines.append(
            f"| `{r['task_id']}` | `{r['agent_a']}` | `{r['agent_b']}` | "
            f"{r['human_winner']} | {r['model_winner']} | {r['gap']:.4f} |"
        )
    if not disagreements:
        lines.append("| _(none)_ | | | | | |")
    lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"[compute_human_alignment] wrote {OUT_MD.relative_to(ROOT)}  "
          f"spearman={sp:.4f}  pearson={pe:.4f}  tau={kt:.4f}  disagreements={len(disagreements)}")


if __name__ == "__main__":
    main()
