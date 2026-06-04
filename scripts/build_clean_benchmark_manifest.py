#!/usr/bin/env python3
"""Parse docs/EVAL_SET_REMEDIATION.md into a machine-readable benchmark manifest.

The remediation pass (data/golden/deep_clean/) recorded each task's verdict and
per-task ``valid_sources`` allow-list ONLY in the markdown doc (Section 2). The
scorer needs that in JSON, so this regenerates
``data/golden/deep_clean/_manifest.json`` from the doc. Committing the parser (not
just the JSON) keeps the canonical benchmark reproducible from the human-readable
source of truth.

Output schema:
  {
    "source_doc": "docs/EVAL_SET_REMEDIATION.md",
    "canonical_scorable": 75,
    "counts": {"valid": 65, "forum-invalid": 10, "quarantine": 25},
    "tasks": {
      "dr_cross_deep_0001": {"verdict": "valid", "valid_sources": ["shopping","forum","wiki"]},
      "dr_cross_deep_0012": {"verdict": "forum-invalid", "valid_sources": ["shopping","wiki"]},
      "dr_cross_deep_0014": {"verdict": "quarantine", "valid_sources": []},
      ...
    }
  }

Run: python3 scripts/build_clean_benchmark_manifest.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "EVAL_SET_REMEDIATION.md"
OUT = ROOT / "data" / "golden" / "deep_clean" / "_manifest.json"

_TASK = re.compile(r"^(dr_cross_deep_\d{4})\b")
# A "src1+src2+..." token using only the three known sources.
_SRC = re.compile(r"\b(shopping(?:\+forum)?(?:\+wiki)?|forum\+wiki|shopping\+wiki)\b")


def _sources(token: str) -> list[str]:
    order = {"shopping": 0, "forum": 1, "wiki": 2}
    parts = [p for p in token.split("+") if p in order]
    return sorted(set(parts), key=lambda p: order[p])


def main() -> int:
    text = DOC.read_text(encoding="utf-8")
    lines = text.splitlines()
    section = None  # "2a" | "2b" | "2c"
    tasks: dict[str, dict] = {}

    for ln in lines:
        h = ln.strip().lower()
        if h.startswith("### 2a"):
            section = "2a"; continue
        if h.startswith("### 2b"):
            section = "2b"; continue
        if h.startswith("### 2c"):
            section = "2c"; continue
        if h.startswith("## 3") or h.startswith("## 4"):
            section = None; continue
        if section is None:
            continue
        m = _TASK.match(ln.strip())
        if not m:
            continue
        tid = m.group(1)
        if section in ("2a", "2b"):
            # "task | usable sources | ..." -> take the FIRST source token after
            # the first pipe (the "usable sources" column).
            after = ln.split("|", 2)
            col = after[1] if len(after) > 1 else ln
            sm = _SRC.search(col)
            srcs = _sources(sm.group(1)) if sm else []
            verdict = "valid" if section == "2a" else "forum-invalid"
            tasks[tid] = {"verdict": verdict, "valid_sources": srcs}
        else:  # 2c quarantine
            tasks[tid] = {"verdict": "quarantine", "valid_sources": []}

    counts = {"valid": 0, "forum-invalid": 0, "quarantine": 0}
    for t in tasks.values():
        counts[t["verdict"]] = counts.get(t["verdict"], 0) + 1
    scorable = counts["valid"] + counts["forum-invalid"]

    # Hard invariants from the doc headline (fail loudly if the parse drifts).
    assert counts == {"valid": 65, "forum-invalid": 10, "quarantine": 25}, counts
    assert scorable == 75, scorable
    assert len(tasks) == 100, len(tasks)
    # Every forum-invalid task is shopping+wiki by definition.
    for tid, t in tasks.items():
        if t["verdict"] == "forum-invalid":
            assert t["valid_sources"] == ["shopping", "wiki"], (tid, t)
        if t["verdict"] == "valid":
            assert t["valid_sources"], (tid, "valid task with no sources")

    manifest = {
        "source_doc": "docs/EVAL_SET_REMEDIATION.md",
        "canonical_scorable": scorable,
        "counts": counts,
        "tasks": {k: tasks[k] for k in sorted(tasks)},
    }
    OUT.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  ({len(tasks)} tasks; scorable={scorable})")
    print(f"  counts: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
