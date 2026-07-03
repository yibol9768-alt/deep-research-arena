#!/usr/bin/env python3
"""Apply the tri-source task redesign (EXECUTION_PLAN P1-P3; user directive
2026-07-03: EVERY task must span all three sources).

Input: data/golden/task_tri_source_specs.json (the tri-source-task-redesign
workflow output: {"specs": {task_id: {cluster, archetype, angle, wiki_topics,
intent}}, "kept": {task_id: cluster}}).

Steps, all idempotent:
  1. task JSONs: install the new intent (original v1 spec text stays in
     intent_v1_legacy), set task_version=2, domain=cluster, and a tri_source
     block {cluster, category_ids, forums, wiki_topics, archetype, angle};
     kept tasks (already human-voice + on-cluster) get the tri_source block
     without touching their intent.
  2. task_category_map.json v2: every task curated onto its cluster's
     category ids, all three legs true by construction.
  3. eval manifest v2 (data/golden/tri_source/_manifest_v2.json): all 100
     tasks valid-pending-golden-validation; the v1 manifest under
     deep_clean/ is untouched (it describes the frozen v1 boards).
  4. acceptance: quota scan over all 100 installed intents (same regexes as
     apply_intent_rewrites) + tri_source block completeness. Nonzero -> exit 1.

Usage: python3 scripts/apply_tri_source_redesign.py [--dry-run]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from apply_intent_rewrites import QUOTA_RES, TASK_DIR  # noqa: E402

SPECS = ROOT / "data/golden/task_tri_source_specs.json"
CLUSTERS = ROOT / "data/golden/tri_source_clusters.json"
MAP_OUT = ROOT / "data/golden/task_category_map.json"
MANIFEST_OUT = ROOT / "data/golden/tri_source/_manifest_v2.json"


def main() -> int:
    dry = "--dry-run" in sys.argv
    payload = json.loads(SPECS.read_text())
    specs: dict = payload["specs"]
    kept: dict = payload.get("kept") or {}
    clusters = json.loads(CLUSTERS.read_text())["clusters"]

    all_assign = dict(kept)
    for tid, s in specs.items():
        all_assign[tid] = s["cluster"]

    n_new = n_kept = 0
    problems = []
    for tid, cl in sorted(all_assign.items()):
        p = TASK_DIR / f"{tid}.json"
        if not p.exists():
            problems.append(f"missing task file {tid}")
            continue
        c = clusters.get(cl)
        if not c:
            problems.append(f"{tid}: unknown cluster {cl}")
            continue
        task = json.loads(p.read_text())
        spec = specs.get(tid)
        if spec:
            if "intent_v1_legacy" not in task:
                task["intent_v1_legacy"] = task.get("intent", "")
            if not isinstance(spec["intent"], str) or len(spec["intent"].split()) < 25:
                problems.append(f"{tid}: intent too short, not applied")
            else:
                task["intent"] = spec["intent"].strip()
            n_new += 1
        else:
            n_kept += 1
        task["task_version"] = 2
        task["domain"] = cl
        task["tri_source"] = {
            "cluster": cl,
            "category_ids": c["category_ids"] + c.get("box_validated_ids", []),
            "keyword_filter": c.get("keyword_filter"),
            "forums": c["forums"],
            "wiki_topics": (spec or {}).get("wiki_topics") or c["wiki_topics"],
            "archetype": (spec or {}).get("archetype"),
            "angle": (spec or {}).get("angle"),
        }
        if not dry:
            p.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n")

    if not dry:
        MAP_OUT.write_text(json.dumps({
            "generated": "2026-07-03", "version": 2,
            "rule": "every task tri-source by construction (user directive)",
            "tasks": {tid: {
                "mode": "curated", "cluster": cl,
                "category_ids": clusters[cl]["category_ids"] + clusters[cl].get("box_validated_ids", []),
                "legs": {"shopping": True, "forum": True, "wiki": True}}
                for tid, cl in sorted(all_assign.items()) if cl in clusters}},
            ensure_ascii=False, indent=1) + "\n")
        MANIFEST_OUT.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_OUT.write_text(json.dumps({
            "generated": "2026-07-03", "task_set_version": 2,
            "note": ("tri-source redesign: 13 clusters, all legs live by "
                     "construction; v1 manifest (deep_clean/_manifest.json) "
                     "still describes the frozen v1 boards"),
            "tasks": {tid: {"verdict": "valid", "cluster": cl}
                      for tid, cl in sorted(all_assign.items())}},
            ensure_ascii=False, indent=1) + "\n")

    # acceptance
    hits = []
    for p in sorted(TASK_DIR.glob("dr_cross_deep_*.json")):
        t = json.loads(p.read_text())
        intent = t.get("intent", "")
        for rx in QUOTA_RES:
            m = rx.search(intent if isinstance(intent, str) else "")
            if m:
                hits.append((p.stem, m.group(0)))
        if t.get("task_version") == 2 and not (t.get("tri_source") or {}).get("category_ids"):
            hits.append((p.stem, "<tri_source missing category_ids>"))

    print(f"applied: {n_new} redesigned + {n_kept} kept; problems: {len(problems)}")
    for pr in problems[:10]:
        print("  !", pr)
    if hits:
        print(f"ACCEPTANCE FAILED ({len(hits)}):")
        for tid, frag in hits[:20]:
            print(f"  {tid}: {frag!r}")
        return 1
    print("acceptance clean: zero quota phrasing, tri_source complete on all v2 tasks")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
