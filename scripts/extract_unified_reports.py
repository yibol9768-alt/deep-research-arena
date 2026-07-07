#!/usr/bin/env python3
"""Extract scoreable reports from a unified results JSON into a report tree.

The unified handoff JSON produced by a run (metadata / tasks / records / ...)
mixes real markdown reports with runner-failure stubs ("(opencode timeout
after 360s)", "(qx-agents error: ValidationError: ...)", empty output, etc.).
This tool writes only the real reports to the ``<agent>/<task_id>.md`` layout
the truth board consumes, and records exactly what it dropped and why in an
extraction manifest so a broken lane is auditable instead of silent.

Usage:
  python3 scripts/extract_unified_reports.py --unified <json> --out <dir>

Writes:
  <out>/<agent>/<task_id>.md            for each record classified "ok"
  <out>/extraction_manifest.json        per-agent counts + stub breakdown
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.report_stubs import (  # noqa: E402
    MIN_REPORT_CHARS,
    classify_report,
)

# Every non-"ok" class the manifest tracks, so the schema is stable even when a
# given agent has zero of a class.
_STUB_CLASSES = ("stub_timeout", "stub_runner_failure", "stub_exception",
                 "too_short")


def extract(unified_path: Path, out_dir: Path) -> dict:
    data = json.loads(unified_path.read_text(encoding="utf-8"))
    records = data.get("records", [])

    per_agent: dict[str, dict] = defaultdict(
        lambda: {
            "n_records": 0,
            "n_written": 0,
            "n_stubs_by_class": {c: 0 for c in _STUB_CLASSES},
        }
    )

    for rec in records:
        agent = rec.get("agent")
        task_id = rec.get("task_id")
        if not agent or not task_id:
            continue
        stats = per_agent[agent]
        stats["n_records"] += 1
        cls = classify_report(rec.get("answer_text"))
        if cls == "ok":
            dest = out_dir / agent / f"{task_id}.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(rec.get("answer_text") or "", encoding="utf-8")
            stats["n_written"] += 1
        else:
            stats["n_stubs_by_class"][cls] += 1

    totals = {"n_records": 0, "n_written": 0, "n_stubs": 0}
    for stats in per_agent.values():
        totals["n_records"] += stats["n_records"]
        totals["n_written"] += stats["n_written"]
        totals["n_stubs"] += sum(stats["n_stubs_by_class"].values())

    manifest = {
        "source": str(unified_path),
        "min_report_chars": MIN_REPORT_CHARS,
        "totals": totals,
        "agents": {a: per_agent[a] for a in sorted(per_agent)},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "extraction_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unified", required=True, help="unified results JSON")
    ap.add_argument("--out", required=True, help="output reports dir")
    args = ap.parse_args()

    manifest = extract(Path(args.unified), Path(args.out))

    t = manifest["totals"]
    print(f"source: {manifest['source']}")
    print(f"wrote {t['n_written']} reports, dropped {t['n_stubs']} stubs "
          f"of {t['n_records']} records -> {args.out}")
    for agent, s in manifest["agents"].items():
        stubs = sum(s["n_stubs_by_class"].values())
        by = ", ".join(f"{k}={v}" for k, v in s["n_stubs_by_class"].items()
                       if v)
        print(f"  {agent:18s} records={s['n_records']:3d} "
              f"written={s['n_written']:3d} stubs={stubs:3d}"
              + (f"  [{by}]" if by else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
