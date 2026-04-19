"""Rerun only the fact_kg pillar with Oracle v2 (filtered) and patch the
existing `final_<agent>_<task>.json` in-place. The judge-dependent pillars
(`llm_judge`, `checklist`) are left alone because they were scored by
the correct different-family judge in the original pass — re-running
those here would either introduce self-preference bias (if the current
env judge matches the agent's family) or spend tokens for no gain.

What this script does per file:
  1. Load final JSON.
  2. Re-run FactKGVerifier with ORACLE_VERSION=v2 (reads *.filtered.json).
  3. Replace pillars["fact_kg"] with the new score.
  4. Recompute composite using the v3.2 weights (fact_kg restored to 0.15).
  5. Write back, preserving everything else.

Usage:
    ORACLE_VERSION=v2 python scripts/rescore_fact_kg_only.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ORACLE_VERSION", "v2")

from src.verifiers.fact_kg_verifier import FactKGVerifier  # noqa: E402

RESULTS = ROOT / "data" / "results"

# v3.2 weights (fact_kg restored to 0.15 now that filtered oracle is clean).
W = {
    "markdown_structure": 0.05,
    "citation":           0.20,
    "fact_kg":            0.15,
    "llm_judge":          0.20,
    "checklist":          0.20,
    "evidence_density":   0.15,
    "efficiency":         0.05,
}


def main() -> None:
    patched = 0
    skipped = 0
    fk = FactKGVerifier(do_precision=False)  # recall-only, deterministic

    for final in sorted(RESULTS.glob("final_*_dr_cross_v3_*.json")):
        if final.name.endswith(".ed.json"):
            continue
        try:
            data = json.loads(final.read_text())
        except Exception:
            continue
        task_id = data.get("task_id")
        agent = data.get("agent")
        if not task_id or not agent:
            skipped += 1
            continue

        answer_path = RESULTS / f"{final.stem}.answer.md"
        answer = answer_path.read_text() if answer_path.exists() else ""
        if not answer.strip():
            skipped += 1
            continue

        result = fk.verify(task_config={"task_id": task_id}, answer=answer)
        old_fk = data.get("pillars", {}).get("fact_kg", {})
        data.setdefault("pillars", {})["fact_kg"] = {
            "score": result.score,
            "passed": result.passed,
            "details": result.details,
        }

        # Composite: use what pillars we have, apply W, renormalise if any
        # pillar is missing.
        pillar_scores = {k: v.get("score", 0.0) for k, v in data["pillars"].items() if isinstance(v, dict)}
        total_w = sum(W[k] for k in pillar_scores if k in W)
        if total_w <= 0:
            skipped += 1
            continue
        comp = sum(W[k] * pillar_scores[k] for k in pillar_scores if k in W) / total_w
        data["composite"] = round(comp, 4)
        data["weights"] = W

        final.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"  {agent}/{task_id}: fact_kg {old_fk.get('score', '—'):>5} → "
              f"{result.score:.3f}  comp={data['composite']:.3f}")
        patched += 1

    print(f"\nPatched {patched} files; skipped {skipped}.")


if __name__ == "__main__":
    main()
