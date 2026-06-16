#!/usr/bin/env python3
"""De-specify the active deep tasks (CLOSED_WORLD_REDESIGN.md sec 5).

Rewrites each task's over-specified "scraping spec" intent into a natural research
question, moves the constraints out of the prompt and into the answer key (DB-derived
golden + rubric), and adds the closed-world config (difficulty axes, completeness
golden_path, grounding k_star/gamma, rubric_path). The original intent is preserved
as intent_v1_legacy; legacy scoring fields are left intact so nothing else breaks.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"

# Natural, de-specified intents: a real user's research question. The cross-site
# nature (shopping facts + community sentiment + technical grounding) is implicit
# and necessary, not dictated; no min-URL / keyword-list / mandated-section quotas.
INTENTS = {
    "dr_cross_deep_0001": (
        "I'm trying to get a clear, trustworthy picture of the consumer "
        "audio-headphone market before buying. Across what's actually available, "
        "what are the notable options at different price points, what do real users "
        "and communities say about the main brands, and where do product marketing "
        "claims fail to match the underlying technical reality? Pull it together "
        "into a grounded overview with a shortlist I can act on."
    ),
    "dr_cross_deep_0002": (
        "I want to set up home coffee brewing and need an honest lay of the land. "
        "What brewing gear is actually worth it across budgets, what do enthusiasts "
        "genuinely recommend versus marketing hype, and how do the main brewing "
        "methods really differ in practice? Give me a grounded guide that ends in a "
        "sensible starter setup."
    ),
    "dr_cross_deep_0003": (
        "I have about $300 to start working out at home and I'm torn between a few "
        "setups: adjustable dumbbells plus a bench, a barbell with plates, or a "
        "resistance/bodyweight-based path. Compare them on what actually matters, "
        "weigh in what people who've used each say, and tell me which gives the best "
        "results for the budget, with your reasoning."
    ),
    "dr_cross_deep_0004": (
        "I'm getting into photography with roughly $800 for my first year and I'm "
        "weighing a few starter routes: a new mirrorless body with a couple of "
        "lenses, a used DSLR kit, or another approach. Compare the realistic options, "
        "factor in what photographers actually recommend, and recommend the smartest "
        "way to start, with the reasoning and trade-offs."
    ),
}

DIFFICULTY = {
    "dr_cross_deep_0001": {"breadth": "high", "depth": "deep", "exploration": "medium"},
    "dr_cross_deep_0002": {"breadth": "high", "depth": "deep", "exploration": "medium"},
    "dr_cross_deep_0003": {"breadth": "high", "depth": "deep", "exploration": "high"},
    "dr_cross_deep_0004": {"breadth": "high", "depth": "deep", "exploration": "high"},
}


def main() -> int:
    for task_id, intent in INTENTS.items():
        p = TASK_DIR / f"{task_id}.json"
        d = json.loads(p.read_text())
        if "intent_v1_legacy" not in d:
            d["intent_v1_legacy"] = d.get("intent", "")
        d["intent"] = intent
        d["schema_version"] = "cw-1.0.0"
        d["difficulty"] = DIFFICULTY[task_id]
        # Relax the prompt-facing spec to a floor; quotas now live in the answer key.
        d["markdown_spec"] = {"min_words": 400}
        d["completeness"] = {
            "golden_path": f"data/golden/db/{task_id}.json",
            "min_completeness": 0.0,
        }
        d["grounding"] = {"k_star": 12, "gamma": 1.0, "min_grounding": 0.0}
        d["rubric_path"] = "data/tasks/deep_research/cross_site_deep/rubrics_cw.json"
        p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
        print(f"de-specified {task_id}: intent {len(intent)} chars (was "
              f"{len(d['intent_v1_legacy'])}); completeness -> {d['completeness']['golden_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
