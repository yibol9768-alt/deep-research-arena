#!/usr/bin/env python3
"""Idempotently stamp `metadata.contradiction_scorable` into every answer key.

The flag mirrors AnswerKey.contradiction_scorable: True iff the key carries a
non-empty `gold_contradictions`. It does NOT invent data. It only surfaces, in
the file itself, whether contradiction precision/recall is even defined for that
task, so a downstream consumer cannot read an empty gold set as "0 found".

Idempotent: writes a file only when the flag is missing or wrong. Touches ONLY
metadata.contradiction_scorable; every other byte of content is preserved (we
round-trip through the same json.dumps(indent=2, ensure_ascii=False) AnswerKey
uses, so already-normalised files are byte-stable). Run again -> 0 writes.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

KEYS_DIR = Path("data/golden/answer_keys")


def backfill(write: bool = True) -> dict:
    counts = {"true": 0, "false": 0, "written": 0, "unchanged": 0, "total": 0}
    for fp in sorted(glob.glob(str(KEYS_DIR / "*.json"))):
        d = json.loads(Path(fp).read_text())
        counts["total"] += 1
        scorable = bool(d.get("gold_contradictions"))
        counts["true" if scorable else "false"] += 1
        meta = d.setdefault("metadata", {})
        if meta.get("contradiction_scorable") == scorable:
            counts["unchanged"] += 1
            continue
        meta["contradiction_scorable"] = scorable
        if write:
            # No trailing newline: matches AnswerKey.save() so the ONLY byte
            # delta vs the original file is the inserted metadata field.
            Path(fp).write_text(json.dumps(d, indent=2, ensure_ascii=False))
        counts["written"] += 1
    return counts


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    c = backfill(write=not dry)
    print(f"answer keys: {c['total']}")
    print(f"  contradiction_scorable=true : {c['true']}")
    print(f"  contradiction_scorable=false: {c['false']}")
    print(f"  files {'would change' if dry else 'written'}: {c['written']}")
    print(f"  unchanged: {c['unchanged']}")
