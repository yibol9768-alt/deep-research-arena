"""Score CAMEL-AI's 4 reports using the live DeepSeek V3.2 judge.

This exercises the **third-party judge** path (peer-review audit P0-1),
producing fresh llm_judge + checklist scores that are NOT
self-preference-biased. The citation pillar runs in substring mode by
default; re-run with `CITATION_MODE=entailment` to get NLI scores.

Outputs:
  data/results/final_camel-ai_dr_cross_v3_<TASK>.json
  data/results/final_camel-ai_dr_cross_v3_<TASK>.answer.md

Env required:
    JUDGE_PROVIDER=openai
    JUDGE_BASE_URL=https://api.deepseek.com
    JUDGE_API_KEY=<user-provided deepseek key>
    JUDGE_MODEL=deepseek-chat
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
AGENT = "camel-ai"
TASKS = [
    "dr_cross_v3_0001",
    "dr_cross_v3_0005",
    "dr_cross_v3_0006",
    "dr_cross_v3_0007",
]


def main() -> None:
    print(f"Judge provider: {os.environ.get('JUDGE_PROVIDER')}")
    print(f"Judge model:    {os.environ.get('JUDGE_MODEL')}")
    print(f"Judge base_url: {os.environ.get('JUDGE_BASE_URL')}")
    print()

    for tid in TASKS:
        md_path = RESULTS / f"camel-ai_{tid}.md"
        if not md_path.exists() or md_path.stat().st_size < 500:
            print(f"skip {tid}: missing or too small")
            continue
        print(f"\n== Scoring {tid} with live DeepSeek judge ==")
        r = score_from_file(tid, AGENT, md_path, run_judge=True)

        out_json = RESULTS / f"final_{AGENT}_{tid}.json"
        out_answer = RESULTS / f"final_{AGENT}_{tid}.answer.md"
        out_json.write_text(json.dumps(r.to_dict(), indent=2, ensure_ascii=False))
        out_answer.write_text(md_path.read_text())
        p = r.pillars
        print(
            f"  composite={r.composite:.3f}  "
            f"md={p['markdown_structure'].score:.2f}  "
            f"cite={p['citation'].score:.2f}  "
            f"fkg={p['fact_kg'].score:.2f}  "
            f"judge={p['llm_judge'].score:.2f}  "
            f"chk={p['checklist'].score:.2f}  "
            f"eff={p['efficiency'].score:.2f}"
        )


if __name__ == "__main__":
    main()
