#!/usr/bin/env python3
"""Produce a sealed semantic-match artifact for one v3 case/report pair."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.semantic_matcher import judge_semantic_matches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model")
    args = parser.parse_args()
    case_bytes = args.case.read_bytes()
    case = json.loads(case_bytes)
    report = args.report.read_text(encoding="utf-8")
    artifact = judge_semantic_matches(
        case,
        report,
        case_sha256=sha256(case_bytes).hexdigest(),
        model=args.model,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "entailed": sum(r["verdict"] == "entailed" for r in artifact["results"]),
        "contradicted": sum(r["verdict"] == "contradicted" for r in artifact["results"]),
        "judge": artifact["judge"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
