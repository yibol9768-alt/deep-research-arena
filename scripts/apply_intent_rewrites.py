#!/usr/bin/env python3
"""Apply the P1/P2 rebuild outputs to the task set (EXECUTION_PLAN P1+P2).

Input: a JSON file {"intents": {task_id: text}, "mapping": [entry, ...]}
(the rebuild-tasks-p1p2 workflow return value, saved to disk).

Does three things, all idempotent:
  1. every task in `intents`: move the current over-specified `intent` to
     `intent_v1_legacy` (only if not already moved) and install the new
     real-user-voice text as `intent`;
  2. write `data/golden/task_category_map.json` from `mapping` (P1 artifact:
     per-task category ids + honest leg flags);
  3. quota scan (the acceptance check): grep every installed intent for
     residual quota phrasing; nonzero hits -> exit 1 and list them.

Usage: python3 scripts/apply_intent_rewrites.py <workflow_output.json> [--dry-run]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = ROOT / "data/tasks/deep_research/cross_site_deep"
MAP_OUT = ROOT / "data/golden/task_category_map.json"

QUOTA_RES = [
    re.compile(r"\bat least\s+\d+", re.I),
    re.compile(r"\b\d+\s*\+\s*(?:products?|threads?|posts?|articles?|urls?|sources?|sites?|pages?)", re.I),
    re.compile(r"\b(?:minimum|min\.?)\s+(?:of\s+)?\d+", re.I),
    re.compile(r"\benumerate\b", re.I),
    re.compile(r"\bexactly\s+\d+", re.I),
    re.compile(r"\b\d{3,5}\s*(?:-|to)\s*\d{3,5}\s*words", re.I),
    re.compile(r"\bcite\s+\d+", re.I),
    re.compile(r"\b(?:grounded|cross-source|deliverable)\b", re.I),
]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    payload = json.loads(Path(sys.argv[1]).read_text())
    dry = "--dry-run" in sys.argv
    intents: dict = payload.get("intents") or {}
    mapping: list = payload.get("mapping") or []

    applied = skipped = 0
    for tid, text in sorted(intents.items()):
        p = TASK_DIR / f"{tid}.json"
        if not p.exists():
            print(f"  ! missing task file {tid}")
            continue
        task = json.loads(p.read_text())
        if not isinstance(text, str) or len(text.split()) < 25:
            print(f"  ! {tid}: rewrite too short, skipped")
            skipped += 1
            continue
        if "intent_v1_legacy" not in task:
            task["intent_v1_legacy"] = task.get("intent", "")
        task["intent"] = text.strip()
        if not dry:
            p.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n")
        applied += 1

    if mapping and not dry:
        MAP_OUT.parent.mkdir(parents=True, exist_ok=True)
        MAP_OUT.write_text(json.dumps(
            {"generated": "2026-07-03",
             "source": "rebuild-tasks-p1p2 workflow (LLM-curated, spot-checked)",
             "census": "data/golden/registry_src/category_census.tsv",
             "tasks": {e["task_id"]: {k: e[k] for k in
                       ("mode", "category_ids", "category_names", "legs", "note")
                       if k in e}
                       for e in mapping if e.get("task_id")}},
            ensure_ascii=False, indent=2) + "\n")

    # acceptance: quota scan over ALL task intents (not only rewritten ones)
    hits = []
    for p in sorted(TASK_DIR.glob("dr_cross_deep_*.json")):
        intent = json.loads(p.read_text()).get("intent", "")
        if not isinstance(intent, str):
            hits.append((p.stem, "<non-string intent>"))
            continue
        for rx in QUOTA_RES:
            m = rx.search(intent)
            if m:
                hits.append((p.stem, m.group(0)))
    print(f"applied {applied}, skipped {skipped}, map entries {len(mapping)}")
    if hits:
        print(f"QUOTA SCAN FAILED ({len(hits)} hits):")
        for tid, frag in hits[:30]:
            print(f"  {tid}: {frag!r}")
        return 1
    print("quota scan clean over all task intents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
