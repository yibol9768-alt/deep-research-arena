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
        "My headphones just died and I need new ones, but every time I look it's a "
        "wall of brands and buzzwords and I have no clue what's actually worth it. "
        "I'm on the bus a lot and work in a noisy office, so blocking out sound "
        "matters to me. Is the expensive stuff genuinely better or am I just paying "
        "for the logo? And do things like active noise cancelling and the fancy "
        "Bluetooth codecs really do what the ads say? Honestly I'd just love a few "
        "solid picks at different prices and the reasons behind them."
    ),
    "dr_cross_deep_0002": (
        "I've been living on instant coffee and I'm finally ready to make the real "
        "thing at home, but the whole coffee world is kind of intimidating and it "
        "all seems overpriced. I don't want to drop a fortune or end up with gear I "
        "never touch. What do I actually need to get started, which brewing method "
        "is hardest to mess up as a beginner, and what do people who really make "
        "coffee at home swear by versus what's just hype? End me with a specific "
        "starter kit I can just go buy."
    ),
    "dr_cross_deep_0003": (
        "I've got maybe $300 to set something up at home so I stop paying for a gym "
        "I never go to. I keep going back and forth between adjustable dumbbells "
        "with a bench, a barbell and rack, or just resistance bands and bodyweight "
        "stuff. I actually want to build some muscle, not buy something that turns "
        "into a coat rack. For a beginner on that budget, which way really makes the "
        "most sense, and what do people who've gone each route say about living with "
        "it? Tell me what you'd pick and why."
    ),
    "dr_cross_deep_0004": (
        "I want to get seriously into photography this year and I've got around $800 "
        "for my first setup. I'm stuck between a new mirrorless camera with a lens or "
        "two, hunting for a used DSLR kit to save money, or something else entirely. "
        "I really don't want to outgrow it in three months or blow the budget on the "
        "wrong thing. What are my realistic options, what do actual photographers "
        "tell beginners, and what would you do with $800? Lay out the trade-offs for "
        "me."
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
