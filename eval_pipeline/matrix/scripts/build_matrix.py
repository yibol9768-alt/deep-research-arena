#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "config" / "matrix.source.json"
OUTPUT = ROOT / "generated" / "matrix.manifest.json"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def build(source: dict, selection: dict | None = None) -> dict:
    harnesses = source["harnesses"]
    models = source["models"]
    if len(harnesses) != 17 or len({x["harness_id"] for x in harnesses}) != 17:
        raise ValueError("exactly 17 unique harnesses required")
    if len(models) != 6 or len({x["model_id"] for x in models}) != 6:
        raise ValueError("exactly 6 unique models required")
    if source.get("execution_mode") != "EXPERIMENTAL_ENABLED":
        raise ValueError("this workspace is experimental-only")
    if source.get("formal_eligible") is not False:
        raise ValueError("experimental matrix must not upgrade formal_eligible")
    slug = source["task_slug"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug):
        raise ValueError("unsafe task slug")
    by_harness = {x["harness_id"]: x for x in harnesses}
    by_model = {x["model_id"]: x for x in models}
    first = source["first_cell"]
    if selection is None:
        pairs = [(first["harness_id"], first["model_id"])]
        pairs += [
            (h["harness_id"], model["model_id"])
            for model in models
            for h in harnesses
            if (h["harness_id"], model["model_id"]) != pairs[0]
        ]
        expected_total = 102
    else:
        if selection.get("design") != "CROSS5_FIXED_HARNESS_FIXED_MODEL":
            raise ValueError("unsupported explicit selection design")
        pairs = [
            (str(row["harness_id"]), str(row["model_id"]))
            for row in selection.get("cells", [])
        ]
        expected_pairs = [
            ("deerflow", "gpt-5-6-sol"),
            ("deerflow", "gemini-3-1-pro-preview"),
            ("deerflow", "claude-opus-5"),
            ("opencode", "gpt-5-6-sol"),
            ("claude-code", "gpt-5-6-sol"),
        ]
        if pairs != expected_pairs:
            raise ValueError("Cross-5 selection is not the frozen five-cell order")
        if selection.get("fixed_harness") != "deerflow":
            raise ValueError("Cross-5 fixed harness must be deerflow")
        if selection.get("fixed_model") != "gpt-5-6-sol":
            raise ValueError("Cross-5 fixed model must be gpt-5-6-sol")
        expected_total = 5
    cells = []
    for ordinal, (harness_id, model_id) in enumerate(pairs, 1):
        harness = by_harness[harness_id]
        runnable = bool(harness["runnable"])
        cells.append({
            "ordinal": ordinal,
            "cell_id": f"{slug}--{harness_id}--{model_id}",
            "harness_id": harness_id,
            "model_id": model_id,
            "model_request_name": by_model[model_id]["request_name"],
            "runnable": runnable,
            "status": "pending" if runnable else "blocked",
            "status_reason": None if runnable else harness["blocked_reason"],
        })
    if len(cells) != expected_total or len({x["cell_id"] for x in cells}) != expected_total:
        raise AssertionError("matrix expansion failed")
    out = dict(source)
    if selection is not None:
        out["schema_version"] = "2.1.0"
        out["matrix_id"] = selection["matrix_id"]
        out["design"] = selection["design"]
        out["design_rationale"] = "3 model cells at fixed DeerFlow plus 3 harness cells at fixed GPT-5.6-Sol, with the shared intersection counted once"
        out["fixed_harness"] = selection["fixed_harness"]
        out["fixed_model"] = selection["fixed_model"]
        out["selection_sha256"] = hashlib.sha256(canonical(selection)).hexdigest()
        out["base_source_sha256"] = hashlib.sha256(canonical(source)).hexdigest()
        out["concurrency"] = {
            **source["concurrency"],
            "model_lanes": 3,
            "global_cells": 3,
            "execution_policy": "CROSS5_PARALLEL_MODEL_LANES_ONE_CELL_PER_MODEL",
        }
    out["cells"] = cells
    out["cell_summary"] = {"total": expected_total, "runnable": sum(x["runnable"] for x in cells), "blocked": sum(not x["runnable"] for x in cells)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--selection", type=Path)
    ap.add_argument("--output", type=Path, default=OUTPUT)
    args = ap.parse_args()
    source = json.loads(args.source.read_text())
    selection = json.loads(args.selection.read_text()) if args.selection else None
    expected = canonical(build(source, selection))
    if args.check:
        ok = not args.output.exists() or args.output.read_bytes() == expected
        print("PASS (in-memory manifest; not materialized)" if ok and not args.output.exists() else ("PASS" if ok else "STALE"))
        return 0 if ok else 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(expected)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
