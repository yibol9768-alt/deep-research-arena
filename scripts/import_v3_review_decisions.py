#!/usr/bin/env python3
"""Validate one DRA v3 review export and write a non-mutating gate report.

The review packet manifest is verified before the decision file is consumed.
This command never edits the frozen graph.  A valid but blocked review still
returns success; callers must read ``status`` and ``candidate_gate``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_v3_review_packet import verify_review_packet  # noqa: E402
from src.eval.evidence_graph import load_json, sha256_bytes  # noqa: E402
from src.eval.review_decisions_v3 import (  # noqa: E402
    REVIEW_AUTHORITIES,
    REVIEW_GATE_REPORT_SCHEMA,
    ReviewDecisionError,
    evaluate_review_decisions,
)


def _write_json(path: Path, value: object) -> None:
    rendered = (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review-packet",
        type=Path,
        required=True,
        help="directory containing manifest.json and review_queue.json",
    )
    parser.add_argument(
        "--decisions",
        type=Path,
        required=True,
        help="exported review decision JSON",
    )
    parser.add_argument(
        "--authority",
        choices=sorted(REVIEW_AUTHORITIES),
        required=True,
        help="human formal review or non-gold LLM simulation",
    )
    parser.add_argument("--out", type=Path, required=True, help="gate report JSON")
    return parser


def _invalid_result(message: str) -> dict[str, Any]:
    return {
        "schema_version": REVIEW_GATE_REPORT_SCHEMA,
        "status": "invalid",
        "candidate_gate": {
            "eligible_for_case_generation": False,
            "blocker_codes": ["invalid_review_input"],
        },
        "errors": [message],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        verify_review_packet(args.review_packet)
        queue = load_json(args.review_packet / "review_queue.json")
        decisions = load_json(args.decisions)
        if not isinstance(queue, dict) or not isinstance(decisions, dict):
            raise ReviewDecisionError("review queue and decisions must be JSON objects")
        manifest_sha256 = sha256_bytes(
            (args.review_packet / "manifest.json").read_bytes()
        )
        result = evaluate_review_decisions(
            queue,
            decisions,
            review_authority=args.authority,
            review_packet_manifest_sha256=manifest_sha256,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        _write_json(args.out, _invalid_result(str(exc)))
        return 1
    _write_json(args.out, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
