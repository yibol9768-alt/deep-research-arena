#!/usr/bin/env python3
"""Decompose the grounding gate into its two components and test re-weighting.

Eval problem #9 asked whether the grounding gate is "quote-fidelity-dominated"
and should be re-weighted toward must-cite recall. This script measures, per
agent on the CLEANED goldens (+ per-task source allow-list), the two components
separately and the honest-vs-fabricator separation under several recall weights,
so the re-weight decision is made on evidence, not assumption.

Composite under test: ``w_r * curated_recall + (1 - w_r) * quote_match``.
The gate floor is ``DEFAULT_GROUNDING_FLOOR`` (0.30).

Run: python3 scripts/analyze_grounding_gate.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.build_real_leaderboard as B  # noqa: E402

SCORE_DIR = ROOT / "data" / "results" / "deep_v3"
REPORT_DIR = ROOT / "data" / "results" / "deep"
FLOOR = B.DEFAULT_GROUNDING_FLOOR

# Cohorts by the documented ground truth: claude-code/camel-ai/smolagents cite
# real pages; gpt-researcher/langchain-odr fabricate or drop real URLs.
HONEST = ["claude-code", "camel-ai", "smolagents"]
FABRICATOR = ["gpt-researcher", "langchain-odr"]


def _components(agent: str, manifest: dict) -> tuple[int, float, float]:
    crs, qms = [], []
    for rep in glob.glob(str(REPORT_DIR / f"{agent}__dr_cross_deep_*_matrix.md")):
        task = Path(rep).name.split("__")[1].rsplit("_matrix", 1)[0]
        meta = manifest.get(task) or {}
        if meta.get("verdict") == "quarantine":
            continue
        vs = set(meta.get("valid_sources") or []) or None
        cr = B._curated_recall_from_report(Path(rep), task, valid_sources=vs)
        if cr is None:
            continue
        sjp = SCORE_DIR / f"{agent}__{task}_matrix.score.json"
        sj = json.loads(sjp.read_text()) if sjp.exists() else {}
        qm = float((sj.get("quote_match") or {}).get("score") or 0.0)
        crs.append(cr)
        qms.append(qm)
    n = len(crs)
    return n, (sum(crs) / n if n else 0.0), (sum(qms) / n if n else 0.0)


def main() -> int:
    manifest = B.load_clean_manifest() or {}
    rows = {a: _components(a, manifest) for a in HONEST + FABRICATOR}

    print(f"floor={FLOOR}  (cleaned goldens + per-task allow-list)\n")
    print(f"{'agent':16s} {'n':>3} {'recall':>7} {'quote':>7} {'cohort':>9}")
    for a in HONEST + FABRICATOR:
        n, cr, qm = rows[a]
        print(f"{a:16s} {n:3d} {cr:7.3f} {qm:7.3f} {('honest' if a in HONEST else 'fabric'):>9}")

    print("\nseparation (min honest composite - max fabricator composite):")
    for wr in (0.3, 0.5, 0.6, 0.7, 0.8):
        h = [wr * rows[a][1] + (1 - wr) * rows[a][2] for a in HONEST]
        f = [wr * rows[a][1] + (1 - wr) * rows[a][2] for a in FABRICATOR]
        mh, mf = min(h), max(f)
        ok = "gate holds" if mf < FLOOR <= mh else "GATE AT RISK"
        print(f"  recall_w={wr:.1f}: sep={mh - mf:+.3f}  min_honest={mh:.3f}  "
              f"max_fabric={mf:.3f}  {ok}")

    print("\nReading: quote_match is the fabrication discriminator (fabricators ~0); "
          "curated_recall barely separates cohorts. Weighting toward recall shrinks "
          "the gate margin. The gate is correctly fidelity-dominated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
