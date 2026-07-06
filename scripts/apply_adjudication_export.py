#!/usr/bin/env python3
"""Turn the browser export from adjudication_ui.html back into per-cluster
cluster_<name>.adjudication.json files and (optionally) promote them to gold.

The HTML UI downloads one combined JSON (format
dra-contradiction-adjudication-export-v1). This script:
  1. refuses drafts (doc.draft == true) unless --allow-draft is given
     (drafts are for resuming in the UI, never for promotion);
  2. for every cluster, loads cluster_<name>.adjudication.template.json,
     fills reference_verdict / verdict / adjudicator / note from the export,
     and writes cluster_<name>.adjudication.json next to it;
  3. with --promote, runs build_gold_contradictions.promote() on each
     cluster, which enforces the honesty contract (complete screening,
     complete verdicts, no SUPPORTED_CONFLICT on rejected references).

Usage:
  python3 scripts/apply_adjudication_export.py \
      --export ~/Downloads/contradiction_adjudication_export.json [--promote]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "golden" / "contradictions"

_spec = importlib.util.spec_from_file_location(
    "build_gold_contradictions", ROOT / "scripts" / "build_gold_contradictions.py")
_bgc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _bgc
_spec.loader.exec_module(_bgc)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--export", required=True, help="JSON downloaded from the UI")
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    ap.add_argument("--promote", action="store_true",
                    help="run promote() on every cluster after writing")
    ap.add_argument("--allow-draft", action="store_true")
    args = ap.parse_args()
    base = Path(args.dir)

    doc = json.loads(Path(args.export).read_text())
    if doc.get("format") != "dra-contradiction-adjudication-export-v1":
        print(f"error: unrecognized export format {doc.get('format')!r}")
        return 1
    if doc.get("draft") and not args.allow_draft:
        print("error: this is a DRAFT export (incomplete); finish in the UI "
              "and use the regular export, or pass --allow-draft to write "
              "files anyway (promote will still refuse incompleteness)")
        return 1

    failures = 0
    for tid, cl in sorted(doc.get("clusters", {}).items()):
        tpl_path = base / f"{tid}.adjudication.template.json"
        if not tpl_path.exists():
            print(f"error: {tpl_path} not found; export/repo mismatch")
            failures += 1
            continue
        tpl = json.loads(tpl_path.read_text())
        ref_by_key = {r["reference_key"]: r for r in cl.get("references", [])}
        for ref in tpl.get("references", []):
            src = ref_by_key.get(ref["reference_key"])
            if src is None:
                print(f"error: {tid}: reference {ref['reference_key']!r} "
                      "missing from export")
                failures += 1
                continue
            ref["reference_verdict"] = src.get("reference_verdict", "")
            ref["note"] = src.get("note", "")
        ent_by_id = {e["candidate_id"]: e for e in cl.get("entries", [])}
        for entry in tpl.get("entries", []):
            src = ent_by_id.get(entry["candidate_id"])
            if src is None:
                print(f"error: {tid}: candidate {entry['candidate_id']!r} "
                      "missing from export")
                failures += 1
                continue
            entry["verdict"] = src.get("verdict", "")
            entry["adjudicator"] = src.get("adjudicator", "")
            entry["note"] = src.get("note", "")
        out_path = base / f"{tid}.adjudication.json"
        out_path.write_text(json.dumps(tpl, indent=2, ensure_ascii=False) + "\n")
        n_gold_votes = sum(1 for e in tpl["entries"]
                           if e["verdict"] == "SUPPORTED_CONFLICT")
        print(f"wrote {out_path.name}: {len(tpl['entries'])} entries, "
              f"{n_gold_votes} SUPPORTED_CONFLICT")
        if args.promote:
            rc = _bgc.promote(tid, base, out_path)
            if rc != 0:
                failures += 1

    if failures:
        print(f"{failures} problem(s); fix and re-run")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
