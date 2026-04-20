"""Convert WebArena shopping tasks (188 JSONs) into our cross_site task format.

WebArena tasks are factoid-style (e.g., "What's the date of my first purchase?")
with deterministic string_match eval. Our existing tasks are long-form research
reports. These are COMPLEMENTARY — adding WebArena lets us measure agent
performance on a different task regime (transactional factoid vs. DR synthesis)
without changing the sandbox environment.

Output: data/tasks/webarena_factoid/wa_shop_<id>.json with our schema:
  {
    task_id, tier="webarena_factoid", sites, intent,
    start_url (resolved), require_login, require_reset,
    min_words: 0, min_citations: 0,    # factoid: short answer OK
    success_criteria: {
        type: "string_match",
        fuzzy_match: [...],
        eval_types: [...]
    }
  }

Scorer for these tasks lives in src/verifiers/factoid_verifier.py (created below).

Usage:
    python scripts/adapt_webarena_tasks.py
    # then point the runner at:
    TASKS=wa_shop_117,wa_shop_332 python scripts/run_gpt5.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "data" / "tasks" / "webarena" / "shopping"
OUT_DIR = ROOT / "data" / "tasks" / "webarena_factoid"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Default Magento base URL in our sandbox. The remote westd resolves
# __SHOPPING__ env variable; we bake it in so local tooling also works.
SHOPPING_URL = "http://localhost:7770"


def _resolve_url(raw: str) -> str:
    return raw.replace("__SHOPPING__", SHOPPING_URL)


def _difficulty_tier(wa: dict) -> int:
    """Rough difficulty proxy: factoid answers with short numeric values = 2;
    multi-value / date range = 4; require_login + reset + eval.html_check = 6."""
    eval_types = (wa.get("eval") or {}).get("eval_types") or []
    ref = (wa.get("eval") or {}).get("reference_answers") or {}
    fuzzy = (ref if isinstance(ref, dict) else {}).get("fuzzy_match") or []
    score = 2
    if wa.get("require_login"):
        score += 1
    if wa.get("require_reset"):
        score += 1
    if "program_html" in eval_types or "url_match" in eval_types:
        score += 2
    if len(fuzzy) > 2:
        score += 1
    return min(7, score)


def adapt_one(wa: dict) -> dict:
    tid = wa["task_id"]
    eval_block = wa.get("eval") or {}
    ref_raw = eval_block.get("reference_answers")
    ref = ref_raw if isinstance(ref_raw, dict) else {}
    return {
        "task_id": f"wa_shop_{tid:04d}",
        "tier": "webarena_factoid",
        "source": "webarena",
        "source_task_id": tid,
        "sites": wa.get("sites") or ["shopping"],
        "intent": wa.get("intent", ""),
        "intent_template": wa.get("intent_template", ""),
        "start_url": _resolve_url(wa.get("start_url", "")),
        "require_login": bool(wa.get("require_login")),
        "require_reset": bool(wa.get("require_reset")),
        "min_words": 0,
        "min_citations": 0,
        "difficulty": _difficulty_tier(wa),
        "success_criteria": {
            "type": "string_match",
            "eval_types": eval_block.get("eval_types") or [],
            "fuzzy_match": ref.get("fuzzy_match") or [],
            "exact_match": ref.get("exact_match") or [],
            "must_include": ref.get("must_include") or [],
        },
    }


def main() -> int:
    files = sorted(p for p in SRC_DIR.glob("*.json") if p.stem != "index")
    by_tier: dict[int, int] = {}
    by_eval: dict[str, int] = {}
    skipped = 0
    wrote = 0
    for f in files:
        try:
            wa = json.loads(f.read_text())
        except Exception:
            skipped += 1
            continue
        if not isinstance(wa, dict) or "task_id" not in wa:
            skipped += 1
            continue
        adapted = adapt_one(wa)
        out = OUT_DIR / f"{adapted['task_id']}.json"
        out.write_text(json.dumps(adapted, indent=2, ensure_ascii=False))
        wrote += 1
        by_tier[adapted["difficulty"]] = by_tier.get(adapted["difficulty"], 0) + 1
        for et in adapted["success_criteria"]["eval_types"]:
            by_eval[et] = by_eval.get(et, 0) + 1

    # Write an index for quick querying.
    index = {
        "count": wrote,
        "skipped": skipped,
        "by_difficulty": dict(sorted(by_tier.items())),
        "by_eval_type": dict(sorted(by_eval.items(), key=lambda x: -x[1])),
        "task_ids": [p.stem for p in sorted(OUT_DIR.glob("wa_shop_*.json"))],
    }
    (OUT_DIR / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False))
    print(f"Adapted {wrote} tasks → {OUT_DIR} (skipped {skipped})")
    print(f"Difficulty: {index['by_difficulty']}")
    print(f"Eval types: {index['by_eval_type']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
