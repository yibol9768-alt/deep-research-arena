#!/usr/bin/env python3
"""Read-only audit of the contradiction / verdict ground truth.

Purpose: make it impossible to quietly report a "cross-site contradiction
detection rate" without noticing that most tasks have no gold to score against.
Prints, per task, how many gold_contradictions and decidable_verdicts exist,
the empty rates, and a one-line honest conclusion.

This script WRITES NOTHING. It only reads data/golden/answer_keys/*.json.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

KEYS_DIR = Path("data/golden/answer_keys")


def audit() -> dict:
    rows = []
    for fp in sorted(glob.glob(str(KEYS_DIR / "*.json"))):
        d = json.loads(Path(fp).read_text())
        rows.append({
            "task_id": d.get("task_id", Path(fp).stem),
            "n_contradictions": len(d.get("gold_contradictions", []) or []),
            "n_verdicts": len(d.get("decidable_verdicts", {}) or {}),
        })
    total = len(rows)
    contra_empty = sum(1 for r in rows if r["n_contradictions"] == 0)
    verdict_empty = sum(1 for r in rows if r["n_verdicts"] == 0)
    return {
        "rows": rows,
        "total": total,
        "contra_empty": contra_empty,
        "verdict_empty": verdict_empty,
    }


def main() -> None:
    a = audit()
    total = a["total"]
    print(f"{'task_id':<24} {'gold_contradictions':>20} {'decidable_verdicts':>20}")
    print("-" * 66)
    for r in a["rows"]:
        print(f"{r['task_id']:<24} {r['n_contradictions']:>20} {r['n_verdicts']:>20}")
    print("-" * 66)

    ce, ve = a["contra_empty"], a["verdict_empty"]
    cpct = 100.0 * ce / total if total else 0.0
    vpct = 100.0 * ve / total if total else 0.0
    print(f"tasks: {total}")
    print(f"gold_contradictions empty: {ce}/{total} ({cpct:.0f}%)")
    print(f"decidable_verdicts  empty: {ve}/{total} ({vpct:.0f}%)")
    print()
    print("CONCLUSION: contradiction detection does NOT enter the `truth` score "
          "(decidable_scorer quality = 0.39*fact + 0.28*pof + 0.33*completeness; "
          "gold_contradictions is read only by checklist_gen for a non-decidable "
          "display item, never by the scorer). With "
          f"{cpct:.0f}% of tasks carrying no gold contradictions and "
          f"{vpct:.0f}% carrying no decidable verdicts, any quantitative claim "
          "about cross-site contradiction detection is unsupported: there is no "
          "ground truth to compute precision/recall against for most tasks.")


if __name__ == "__main__":
    main()
