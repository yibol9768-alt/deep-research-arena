#!/usr/bin/env python3
"""Build a focused human-annotation pair bundle for the /annotate page (kappa).

Unlike build_annotate_pairs.py (which dumped 30 pairs onto one task and included
thin/junk agents), this samples pairs that actually validate the leaderboard:
  - across DIVERSE scorable tasks (spread, not all task 0001),
  - among the board agents (the competent set we rank) + a few fabricator
    contrasts (so humans confirm fabricators are worse),
  - balanced agent coverage, capped.

Self-contained bundle (static site): each pair carries the task intent + both
truncated report texts. Output schema matches frontend/public/annotate-pairs.json.

Run ON the box (reports under data/results/deep/):
  python3 scripts/build_kappa_pairs.py --out frontend/public/annotate-pairs.json
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data" / "results" / "deep"
TASKS = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"

# competent/board agents (where ranking decisions matter) + fabricator contrasts
COMPETENT = ["deerflow", "camel-ai", "smolagents", "flowsearcher-ds", "ii-researcher"]
FABRICATOR = ["gpt-researcher", "storm", "langchain-odr", "ldr"]
TARGET = COMPETENT + FABRICATOR
TRUNC = 8000
MIN_WORDS = 120


def _read(md: Path) -> str:
    try:
        return md.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _trunc(t: str) -> str:
    if len(t) <= TRUNC:
        return t
    return t[:TRUNC].rstrip() + "\n\n---\n\n_[truncated for annotation]_"


def _intent(task_id: str) -> str:
    p = TASKS / f"{task_id}.json"
    if p.exists():
        try:
            it = (json.loads(p.read_text()).get("intent") or "").strip()
            it = re.sub(r"\s+", " ", it)
            return it[:600] + (" ..." if len(it) > 600 else "")
        except Exception:
            pass
    return task_id


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "frontend" / "public" / "annotate-pairs.json"))
    ap.add_argument("--max-pairs", type=int, default=48)
    ap.add_argument("--manifest", default=str(ROOT / "data/golden/deep_clean/_manifest.json"))
    args = ap.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text())["tasks"]
    scorable = sorted(t for t, m in manifest.items() if m.get("verdict") != "quarantine")

    # present(target) reports per task
    present: dict[str, dict[str, Path]] = {}
    words: dict[tuple, int] = {}
    for md in glob.glob(str(REPORTS / "*__dr_cross_deep_*_matrix.md")):
        name = Path(md).name
        agent = name.split("__")[0]
        task = name.split("__")[1].rsplit("_matrix", 1)[0]
        if agent not in TARGET or task not in scorable:
            continue
        txt = _read(Path(md))
        if len(txt.split()) < MIN_WORDS:
            continue
        present.setdefault(task, {})[agent] = Path(md)
        words[(agent, task)] = len(txt.split())

    # spread tasks: iterate scorable tasks in order, round-robin pair types,
    # balance agent appearances.
    appear = {a: 0 for a in TARGET}
    pairs: list[dict] = []
    # task order: interleave to spread coverage
    task_order = [t for t in scorable if t in present]

    def add_pair(task, a, b):
        if len(pairs) >= args.max_pairs:
            return False
        ra, rb = present[task].get(a), present[task].get(b)
        if not ra or not rb:
            return False
        pairs.append({
            "task_id": task, "agent_a": a, "agent_b": b,
            "intent": _intent(task),
            "words_a": words[(a, task)], "words_b": words[(b, task)],
            "report_a": _trunc(_read(ra)), "report_b": _trunc(_read(rb)),
        })
        appear[a] += 1; appear[b] += 1
        return True

    # pass 1: one competent-vs-competent + one competent-vs-fabricator per task,
    # choosing the least-covered agents for balance.
    for typ in ("cc", "cf"):
        for task in task_order:
            if len(pairs) >= args.max_pairs:
                break
            avail = present[task]
            comps = [a for a in COMPETENT if a in avail]
            fabs = [a for a in FABRICATOR if a in avail]
            if typ == "cc" and len(comps) >= 2:
                comps.sort(key=lambda a: appear[a])
                add_pair(task, comps[0], comps[1])
            elif typ == "cf" and comps and fabs:
                comps.sort(key=lambda a: appear[a]); fabs.sort(key=lambda a: appear[a])
                add_pair(task, comps[0], fabs[0])

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "truncate_chars": TRUNC,
        "note": "Focused kappa set: board agents across diverse tasks; competent-vs-competent and competent-vs-fabricator.",
        "pairs": pairs,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    from collections import Counter
    ac = Counter()
    for p in pairs:
        ac[p["agent_a"]] += 1; ac[p["agent_b"]] += 1
    print(f"wrote {args.out}: {len(pairs)} pairs across {len({p['task_id'] for p in pairs})} tasks")
    print("agent coverage:", dict(ac.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
