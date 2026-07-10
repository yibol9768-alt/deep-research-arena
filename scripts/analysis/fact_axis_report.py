#!/usr/bin/env python3
"""fact axis EFFECTIVE-weight report (P2, read-only).

The board multiplies fact by its NOMINAL 0.39 quality weight. This script
measures its EFFECTIVE weight: on how many reports the axis actually fired.
`fact` scores only checkable structured claims (a price or overall rating bound
to a named DB entity). A report that asserts nothing checkable makes zero
testable claims and scores 0.0 by design, so the 0.39 weight contributes
nothing to truth there and truth is driven by pof + completeness. Main-session
finding on the qwen backbone: 2/140 reports made any checkable claim.

This tool NEVER writes and NEVER changes any score. It only reads reports and
answer keys and reruns score_fact_support to report the distribution.

Usage:
  python3 scripts/analysis/fact_axis_report.py --reports-dir <dir> \
      [--keys-dir data/golden/answer_keys] [--json out.json]

Report layout is auto-detected:
  * nested  <reports-dir>/<lane>/<task_id>.md
  * flat    <reports-dir>/.../<lane>__<task_id>[_matrix].md
Task ids are matched against <keys-dir>/<task_id>.json; a report whose task has
no key is skipped (and counted, so a silent mismatch cannot hide).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.answer_key import AnswerKey                 # noqa: E402
from src.eval import decidable_scorer as ds               # noqa: E402

# Task ids look like dr_cross_deep_0001 / dr_forum_shallow_0007: a dr_ prefix,
# word segments, a trailing numeric run index. Anchored to the id boundary so a
# "_matrix" / "_report" filename tail is not swallowed into the task.
_TASK_RE = re.compile(r"(dr_[a-z]+(?:_[a-z]+)*_\d+)")


def _lane_task(path: Path, reports_dir: Path) -> tuple[str, str] | None:
    """(lane, task_id) for one report file, for both supported layouts."""
    stem = path.stem
    if "__" in stem:
        lane, rest = stem.split("__", 1)
        m = _TASK_RE.search(rest)
        return (lane, m.group(1)) if m else None
    m = _TASK_RE.search(stem)
    if not m:
        return None
    # nested layout: lane is the immediate parent dir, unless the report sits
    # directly in reports_dir (then the lane is unknown -> "_unlaned").
    parent = path.parent
    lane = parent.name if parent != reports_dir else "_unlaned"
    return (lane, m.group(1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports-dir", required=True)
    ap.add_argument("--keys-dir", default="data/golden/answer_keys")
    ap.add_argument("--json", default=None,
                    help="optional path to also dump the machine-readable report")
    args = ap.parse_args()

    rdir = Path(args.reports_dir)
    if not rdir.is_dir():
        print(f"reports-dir not found: {rdir}", file=sys.stderr)
        return 2
    keys_dir = Path(args.keys_dir)
    if not keys_dir.is_absolute():
        keys_dir = ROOT / keys_dir

    # cache the loaded key AND its generic-token set per task: score_fact_support
    # rebuilds build_generic_tokens(answer_key) on every call otherwise, and the
    # same task recurs across every lane.
    key_cache: dict[str, object] = {}
    generic_cache: dict[str, set] = {}

    def _key(tid: str):
        if tid not in key_cache:
            p = keys_dir / f"{tid}.json"
            if not p.exists():
                key_cache[tid] = None
            else:
                ak = AnswerKey.load(p)
                key_cache[tid] = ak
                generic_cache[tid] = ds.build_generic_tokens(ak)
        return key_cache[tid]

    per_lane: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "active": 0, "supported": 0, "contradicted": 0,
                 "unbound": 0, "untestable": 0})
    n_files = n_scored = n_no_key = n_unparsed = 0
    active_reports: list[str] = []

    for path in sorted(rdir.rglob("*.md")):
        n_files += 1
        lt = _lane_task(path, rdir)
        if lt is None:
            n_unparsed += 1
            continue
        lane, tid = lt
        ak = _key(tid)
        if ak is None:
            n_no_key += 1
            continue
        md = path.read_text(errors="replace")
        _fact, fd = ds.score_fact_support(md, ak, generic=generic_cache.get(tid))
        n_scored += 1
        row = per_lane[lane]
        row["n"] += 1
        for k in ("supported", "contradicted", "unbound", "untestable"):
            row[k] += fd.get(k, 0)
        if fd.get("fact_active"):
            row["active"] += 1
            active_reports.append(f"{lane}/{tid} "
                                  f"(tested={fd['claims_tested']}, "
                                  f"supported={fd['supported']}, "
                                  f"contradicted={fd['contradicted']})")

    tot_active = sum(r["active"] for r in per_lane.values())
    tot_supported = sum(r["supported"] for r in per_lane.values())
    tot_contradicted = sum(r["contradicted"] for r in per_lane.values())
    tot_unbound = sum(r["unbound"] for r in per_lane.values())
    tot_untestable = sum(r["untestable"] for r in per_lane.values())
    active_frac = tot_active / n_scored if n_scored else 0.0
    inert_pct = 100.0 * (1.0 - active_frac)

    report = {
        "reports_dir": str(rdir),
        "keys_dir": str(keys_dir),
        "n_report_files": n_files,
        "n_scored": n_scored,
        "n_skipped_no_key": n_no_key,
        "n_skipped_unparsed": n_unparsed,
        "fact_active_reports": tot_active,
        "fact_active_rate": round(active_frac, 4),
        "claims": {
            "supported": tot_supported,
            "contradicted": tot_contradicted,
            "unbound": tot_unbound,
            "untestable": tot_untestable,
        },
        "per_lane": {
            lane: {
                "n": r["n"],
                "fact_active": r["active"],
                "fact_active_rate": round(r["active"] / r["n"], 4) if r["n"] else 0.0,
                "supported": r["supported"],
                "contradicted": r["contradicted"],
                "unbound": r["unbound"],
                "untestable": r["untestable"],
            }
            for lane, r in sorted(per_lane.items())
        },
        "active_report_ids": active_reports,
    }

    print(f"reports-dir : {rdir}")
    print(f"keys-dir    : {keys_dir}")
    print(f"scored      : {n_scored} report(s)"
          + (f"  (skipped {n_no_key} no-key, {n_unparsed} unparsed)"
             if (n_no_key or n_unparsed) else ""))
    print()
    print(f"fact_active : {tot_active}/{n_scored} "
          f"({round(100 * active_frac, 1)}%) reports made ANY checkable claim")
    print(f"claims      : supported={tot_supported} contradicted={tot_contradicted} "
          f"unbound={tot_unbound} untestable={tot_untestable}")
    print()
    print(f"{'lane':22s} {'n':>4s} {'active':>7s} {'act%':>6s} "
          f"{'sup':>4s} {'con':>4s} {'unb':>5s}")
    for lane, r in report["per_lane"].items():
        print(f"{lane:22s} {r['n']:>4d} {r['fact_active']:>7d} "
              f"{100 * r['fact_active_rate']:>5.1f}% {r['supported']:>4d} "
              f"{r['contradicted']:>4d} {r['unbound']:>5d}")
    print()
    if active_reports:
        print("active reports:")
        for a in active_reports:
            print(f"  {a}")
        print()
    # The one-line verdict the task asks for.
    print(f"CONCLUSION: fact's 0.39 weight is inert on {inert_pct:.1f}% of "
          f"scored reports; truth on those reports is driven by pof and "
          f"completeness, not fact.")

    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
