"""Cohen's kappa between LLM-judge dim ranking and human prefs.

For each judge-driven v3 dim (depth, rigor, style, checklist) we form
the contingency between:

  human label  = winner of a pair WHERE that dim was cited as the reason
  judge label  = which agent has the higher per-dim score for that pair

and report Cohen's kappa. The lowest-kappa dim is the rubric to iterate
on next.

Inputs
------
  data/human_prefs/*.jsonl
  data/results/deep_v3/leaderboard_deep_v3.json
      (falls back to leaderboard_deep.json + pillar_elo approximation)

Output
------
  docs/JUDGE_HUMAN_KAPPA.md
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PREFS_DIR = ROOT / "data" / "human_prefs"
LB_V3_JSON = ROOT / "data" / "results" / "deep_v3" / "leaderboard_deep_v3.json"
LB_V2_JSON = ROOT / "data" / "results" / "deep_v3" / "leaderboard_deep.json"
OUT_MD = ROOT / "docs" / "JUDGE_HUMAN_KAPPA.md"

JUDGE_DIMS = ["depth", "rigor", "style", "checklist"]
ALL_DIMS = ["coverage", "depth", "rigor", "style", "checklist", "spec"]


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
                    out = {a: {d: float(dims.get(d, 0.0)) for d in ALL_DIMS}
                           for a, dims in block.items() if isinstance(dims, dict)}
                    return out, str(cand.relative_to(ROOT))
            pillar = data.get("pillar_elo") or {}
            if pillar:
                approx: dict[str, dict[str, float]] = {}
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


def _cohen_kappa(pairs: list[tuple[str, str]]) -> tuple[float, int]:
    """Cohen's kappa over binary labels in {'a', 'b'} (we ignore 'tie' to
    keep the calculation simple; this matches how the judge produces only
    a/b labels). Returns (kappa, n)."""
    n = len(pairs)
    if n == 0:
        return float("nan"), 0
    labels = ["a", "b"]
    counts = {l: defaultdict(int) for l in labels}
    for h, j in pairs:
        if h not in labels or j not in labels:
            continue
        counts[h][j] += 1
    n_used = sum(counts[l][m] for l in labels for m in labels)
    if n_used == 0:
        return float("nan"), 0
    po = sum(counts[l][l] for l in labels) / n_used
    pa = {l: sum(counts[l][m] for m in labels) / n_used for l in labels}
    pj = {l: sum(counts[m][l] for m in labels) / n_used for l in labels}
    pe = sum(pa[l] * pj[l] for l in labels)
    if abs(1 - pe) < 1e-12:
        return float("nan"), n_used
    return float((po - pe) / (1 - pe)), n_used


def main():
    prefs = _load_prefs()
    scores, src = _load_dim_scores()
    if not prefs:
        sys.exit("No prefs found in data/human_prefs/*.jsonl.")
    if not scores:
        sys.exit("No dim scores available; cannot compute judge labels.")

    # Build per-dim filtered pair lists, then compute kappa.
    per_dim: dict[str, list[tuple[str, str]]] = {d: [] for d in JUDGE_DIMS}
    for p in prefs:
        a, b, w = p.get("agent_a"), p.get("agent_b"), p.get("winner")
        if w not in ("a", "b"):
            continue
        sa, sb = scores.get(a), scores.get(b)
        if not (sa and sb):
            continue
        cited = set(p.get("dims_cited") or [])
        for d in JUDGE_DIMS:
            if d not in cited:
                continue
            judge_pick = "a" if sa.get(d, 0.0) > sb.get(d, 0.0) else (
                "b" if sb.get(d, 0.0) > sa.get(d, 0.0) else None
            )
            if judge_pick is None:
                continue
            per_dim[d].append((w, judge_pick))

    kappas = {d: _cohen_kappa(per_dim[d]) for d in JUDGE_DIMS}
    # Pick weakest dim that has at least 10 supporting rows.
    eligible = [(d, k) for d, (k, n) in kappas.items() if n >= 10 and k == k]  # k==k filters NaN
    if eligible:
        weakest_dim, weakest_kappa = min(eligible, key=lambda kv: kv[1])
    else:
        weakest_dim, weakest_kappa = "(insufficient data)", float("nan")

    lines = []
    lines.append("# Judge / Human Cohen kappa")
    lines.append("")
    lines.append(f"_Generated: {datetime.now(timezone.utc).isoformat()}_")
    lines.append(f"_Source: `{src}`  prefs={len(prefs)}_")
    lines.append("")
    lines.append("| dim | n_filtered | kappa | interpretation |")
    lines.append("|-----|-----------|-------|----------------|")
    for d in JUDGE_DIMS:
        k, n = kappas[d]
        ks = "nan" if k != k else f"{k:.3f}"
        interp = "(too few rows)" if n < 10 else (
            "near-chance" if k < 0.20 else
            "fair"        if k < 0.40 else
            "moderate"    if k < 0.60 else
            "substantial" if k < 0.80 else "almost perfect"
        )
        lines.append(f"| {d} | {n} | {ks} | {interp} |")
    lines.append("")
    lines.append("## Weakest judge")
    lines.append("")
    if weakest_dim == "(insufficient data)":
        lines.append("Not enough dim-cited prefs (>= 10 per dim) to choose a weakest judge yet.")
    else:
        lines.append(f"The lowest-kappa judge is **{weakest_dim}** (kappa={weakest_kappa:.3f}).")
        lines.append("Iterate the rubric for this dim next: tighten the criterion, add few-shot exemplars.")
    lines.append("")
    lines.append("## Method note")
    lines.append("")
    lines.append("For each pair `(A, B)` where the annotator cited dim D as a reason, we set the")
    lines.append("judge's label to whichever agent had the higher per-dim score in the v3 leaderboard.")
    lines.append("'Tie' human verdicts are dropped. Kappa is computed over the binary {A, B} contingency.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"[compute_judge_human_kappa] wrote {OUT_MD.relative_to(ROOT)}; "
          f"weakest={weakest_dim} kappa={weakest_kappa}")


if __name__ == "__main__":
    main()
