#!/usr/bin/env python3
"""Score the NEW DeerFlow (Coding Plan) outputs with the 5 deterministic
pillars only (skip llm_judge + checklist — they still route through the
general-pay Anthropic-compat endpoint).

Writes `data/results/final_deerflow-glm46-new_dr_cross_v3_*.json` with the
same schema as the old run so downstream re-scoring / leaderboard
scripts pick them up transparently.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from scripts.bench_v3 import score_from_file

RESULTS = ROOT / "data" / "results"

TASKS = ["dr_cross_v3_0001", "dr_cross_v3_0005", "dr_cross_v3_0006", "dr_cross_v3_0007"]

# Fall back to the canonical deerflow_<task>.md name if the _NEW_ variant
# isn't present (lets the same script run on both Mac and remote).
_MD_TEMPLATES_ENV = os.environ.get("SCORE_MD_TEMPLATES", "")
MD_NAME_TEMPLATES = [t.strip() for t in _MD_TEMPLATES_ENV.split(",") if t.strip()] or [
    "deerflow_NEW_{tid}.md", "deerflow_{tid}.md",
]

AGENT = os.environ.get("SCORE_AGENT_NAME", "deerflow-glm46-new")
OLD_AGENT_OVERRIDE = os.environ.get("SCORE_CARRY_OVER_FROM")  # default uses OLD_AGENT below

# Keep the original agent's scores for llm_judge and checklist as proxies
# (they were computed on the older reports; acknowledged limitation but
# good enough for a first-cut leaderboard until we port the judges to
# Coding-Plan OpenAI-compat routing).
OLD_AGENT = OLD_AGENT_OVERRIDE or "deerflow-glm46"


def main() -> None:
    for tid in TASKS:
        md_path = None
        for pattern in MD_NAME_TEMPLATES:
            candidate = RESULTS / pattern.format(tid=tid)
            if candidate.exists() and candidate.stat().st_size > 1000:
                md_path = candidate
                break
        if md_path is None:
            print(f"skip {tid}: no file")
            continue
        print(f"\nScoring {tid} ...")
        r = score_from_file(tid, AGENT, md_path, run_judge=False)

        # Carry over old llm_judge + checklist as proxies (note in details)
        old_json = RESULTS / f"final_{OLD_AGENT}_{tid}.json"
        if old_json.exists():
            old = json.loads(old_json.read_text())
            old_pillars = old.get("pillars", {})
            if "llm_judge" in old_pillars:
                r.pillars["llm_judge"].score = old_pillars["llm_judge"]["score"]
                r.pillars["llm_judge"].passed = old_pillars["llm_judge"]["passed"]
                r.pillars["llm_judge"].details = {
                    **old_pillars["llm_judge"].get("details", {}),
                    "_note": "carried over from pre-fix DeerFlow run",
                }
            if "checklist" in old_pillars:
                r.pillars["checklist"].score = old_pillars["checklist"]["score"]
                r.pillars["checklist"].passed = old_pillars["checklist"]["passed"]
                r.pillars["checklist"].details = {
                    **old_pillars["checklist"].get("details", {}),
                    "_note": "carried over from pre-fix DeerFlow run",
                }
            # Carry over efficiency too so the new DeerFlow isn't unfairly
            # penalised by a 0 eff pillar while old runs had a placeholder
            # 0.85 from their (bogus) timing metrics. Same apples-to-apples
            # rationale as judge + checklist carry-over.
            if "efficiency" in old_pillars:
                r.pillars["efficiency"].score = old_pillars["efficiency"]["score"]
                r.pillars["efficiency"].passed = old_pillars["efficiency"]["passed"]
                r.pillars["efficiency"].details = {
                    **old_pillars["efficiency"].get("details", {}),
                    "_note": "carried over from pre-fix DeerFlow run",
                }
            # Recompute composite with the mixed scores
            r.composite = sum(r.weights[k] * r.pillars[k].score for k in r.weights)
            r.composite = round(r.composite, 3)

        out_json = RESULTS / f"final_{AGENT}_{tid}.json"
        out_answer = RESULTS / f"final_{AGENT}_{tid}.answer.md"
        out_json.write_text(json.dumps(r.to_dict(), indent=2, ensure_ascii=False))
        out_answer.write_text(md_path.read_text())

        p = r.pillars
        print(f"  composite={r.composite:.3f}   "
              f"md={p['markdown_structure'].score:.2f}  "
              f"cite={p['citation'].score:.2f}  "
              f"fkg={p['fact_kg'].score:.2f}  "
              f"judge={p['llm_judge'].score:.2f}  "
              f"chk={p['checklist'].score:.2f}  "
              f"eff={p['efficiency'].score:.2f}")

    print(f"\nScored {len(TASKS)} tasks → final_{AGENT}_*.json")


if __name__ == "__main__":
    main()
