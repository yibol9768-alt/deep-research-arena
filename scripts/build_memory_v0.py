#!/usr/bin/env python3
"""Cold-start build of hierarchical memory from existing deep-tier matrix results.

Usage:
    python3 scripts/build_memory_v0.py [--embed]

Without --embed: builds L1/L2/L3 from score files only (no API calls).
With --embed: also computes DashScope text-embedding-v4 for each L1 entry.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Direct imports to avoid src/__init__.py triggering pydantic
from src.memory.workflow_miner import mine_all  # noqa: E402
from src.memory.hierarchical import _embed_via_dashscope, L1_DIR, L2_DIR, L3_PATH  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed", action="store_true", help="Compute DashScope embeddings for L1")
    args = ap.parse_args()

    print("[build_memory] Mining existing results...")
    mem = mine_all()

    print(f"[build_memory] L1: {len(mem.l1)} task entries")
    for tid, entry in sorted(mem.l1.items()):
        runs = entry["best_runs"]
        best = runs[0]["composite_v2"] if runs else 0
        print(f"  {tid}: {len(runs)} runs, best composite_v2={best:.4f}, "
              f"type={entry['intent_type']}, sections={len(entry.get('section_skeleton', []))}")

    print(f"\n[build_memory] L2: {len(mem.l2)} intent clusters")
    for itype, data in sorted(mem.l2.items()):
        print(f"  {itype}: {data['n_tasks']} tasks, {data['n_runs']} runs, "
              f"avg_cite={data['avg_citation_count']:.0f}, dist={data['citation_distribution']}")

    print(f"\n[build_memory] L3: {mem.l3.get('n_total_l1_entries', 0)} entries, "
          f"{mem.l3.get('n_total_qualified_runs', 0)} qualified runs")

    if args.embed:
        print("\n[build_memory] Computing DashScope embeddings...")
        dashscope_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not dashscope_key:
            print("  ERROR: DASHSCOPE_API_KEY not set. Skipping embeddings.")
        else:
            task_dir = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
            texts = []
            tids = []
            for tid in sorted(mem.l1.keys()):
                tf = task_dir / f"{tid}.json"
                if tf.exists():
                    intent = json.loads(tf.read_text()).get("intent", "")[:500]
                    texts.append(intent)
                    tids.append(tid)

            batch_size = 10
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_ids = tids[i:i + batch_size]
                try:
                    embeddings = _embed_via_dashscope(batch)
                    for tid, emb in zip(batch_ids, embeddings):
                        mem.l1[tid]["embedding"] = emb
                    print(f"  Embedded {len(batch_ids)} entries ({batch_ids[0]}..{batch_ids[-1]})")
                except Exception as e:
                    print(f"  ERROR embedding batch {i}: {e}")

    mem.save()
    print(f"\n[build_memory] Saved to {L1_DIR.parent}")
    print(f"  L1: {len(list(L1_DIR.glob('*.json')))} files")
    print(f"  L2: {len(list(L2_DIR.glob('*.json')))} files")
    print(f"  L3: {L3_PATH.exists()}")


if __name__ == "__main__":
    main()
