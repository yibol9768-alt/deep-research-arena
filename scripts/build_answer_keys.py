#!/usr/bin/env python3
"""Build closed-world answer keys for all tasks (stage-1, no GPU).

Pipeline per task (METHODOLOGY_REDESIGN_2026-07-03.md):
  1. migrate the DB golden (data/golden/db/<id>.json) into the answer-key schema
  2. apply the relevance gate (deterministic backend; llm backend is stage 2)
  3. extract spec requirements from the task json (quotas -> axis-4 SPEC)
  4. generate the typed checklist and save both artifacts

Outputs:
  data/golden/answer_keys/<id>.json   the answer key (relevant set + nuggets + spec)
  data/golden/checklists/<id>.json    the typed, decidable checklist

Head terms for the relevance gate come from the topic config's shopping
keywords when present; else a generic fallback. Tasks without a DB golden are
skipped and listed (they need build_db_golden.py on the box first).

Usage:
  python3 scripts/build_answer_keys.py [--task dr_cross_deep_0001] [--all]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.answer_key import migrate_db_golden
from src.eval.relevance_gate import apply_gate
from src.eval import spec_extract, checklist_gen

DB_GOLDEN = ROOT / "data" / "golden" / "db"
TASK_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
TOPIC_DIR = ROOT / "configs" / "deep_topics"
OUT_KEYS = ROOT / "data" / "golden" / "answer_keys"
OUT_CHECK = ROOT / "data" / "golden" / "checklists"

_FALLBACK_HEADS = ["headphone", "earbud", "earphone", "headset", "earpiece", "airpod"]


def head_terms_for(task_id: str) -> list[str]:
    """Topic head nouns for the relevance gate, from the topic config's shopping
    keywords (single-word, product-type tokens)."""
    idx = task_id.split("_")[-1]
    for p in TOPIC_DIR.glob(f"{idx}_*.yaml"):
        try:
            import yaml
            cfg = yaml.safe_load(p.read_text()) or {}
        except Exception:
            continue
        kws = cfg.get("shopping_keywords") or []
        heads = []
        for kw in kws:
            for t in kw.lower().split():
                if len(t) >= 4:
                    heads.append(t)
        if heads:
            return sorted(set(heads))
    return _FALLBACK_HEADS


def build_one(task_id: str) -> dict | None:
    dbg = DB_GOLDEN / f"{task_id}.json"
    if not dbg.exists():
        return None
    ak = migrate_db_golden(dbg)
    heads = head_terms_for(task_id)
    gate = apply_gate(ak, heads)

    task_json = TASK_DIR / f"{task_id}.json"
    if task_json.exists():
        task = json.loads(task_json.read_text())
        ak.spec_requirements = spec_extract.extract(task)
        ak.metadata["natural_output_contract"] = spec_extract.natural_output_contract(task)
    ak.metadata["head_terms"] = heads

    OUT_KEYS.mkdir(parents=True, exist_ok=True)
    ak.save(OUT_KEYS / f"{task_id}.json")

    checklist = checklist_gen.generate(ak)
    OUT_CHECK.mkdir(parents=True, exist_ok=True)
    checklist_gen.save(checklist, OUT_CHECK / f"{task_id}.json")

    return {
        "task_id": task_id,
        "products_kept": gate.get("n_products_kept"),
        "products_dropped": gate.get("n_products_dropped"),
        "vital_relevant": gate.get("n_vital_relevant"),
        "spec_reqs": len(ak.spec_requirements),
        "checklist_items": len(checklist),
        "checklist": checklist_gen.summary(checklist),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.task:
        ids = [args.task]
    else:
        ids = sorted(p.stem for p in DB_GOLDEN.glob("dr_cross_deep_*.json"))
    if not ids:
        print("no DB goldens found under data/golden/db/ "
              "(run build_db_golden.py on the box first)")
        return 1

    built, skipped = [], []
    for tid in ids:
        r = build_one(tid)
        if r is None:
            skipped.append(tid)
            continue
        built.append(r)
        print(f"{tid}: products {r['products_kept']} kept / {r['products_dropped']} dropped, "
              f"{r['vital_relevant']} vital, {r['spec_reqs']} spec, "
              f"{r['checklist_items']} checklist items ({r['checklist']['decidable']} decidable)")
    if skipped:
        print(f"\nskipped (no DB golden): {skipped}")
    print(f"\nbuilt {len(built)} answer keys -> {OUT_KEYS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
