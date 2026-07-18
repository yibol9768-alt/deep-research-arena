#!/usr/bin/env python3
"""Aggregate Route A result JSON/JSONL without constructing a quality sum."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.query_rubric_scorer import aggregate_query_rubric_scores  # noqa: E402


def _rows(path: str) -> list[dict]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("rows"), list):
        return value["rows"]
    if isinstance(value, dict):
        return [value]
    raise SystemExit("input must be a result object, list, or JSONL")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="aggregate DRA Route A scores")
    parser.add_argument("--input", required=True, help="result JSON/JSONL, or - for stdin")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    result = aggregate_query_rubric_scores(_rows(args.input))
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

