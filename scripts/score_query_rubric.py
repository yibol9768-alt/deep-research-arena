#!/usr/bin/env python3
"""Score one Route A report from a frozen rubric and observation ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.query_rubric_scorer import score_query_rubric  # noqa: E402
from src.eval.url_registry import DEFAULT_REGISTRY_PATH, UrlRegistry  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="score one DRA Route A report")
    parser.add_argument("--rubric", required=True)
    parser.add_argument("--report", required=True, help="report path, or - for stdin")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--url-registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--expected-run-id")
    parser.add_argument("--seed-url", action="append", default=[])
    parser.add_argument("--allow-non-frozen", action="store_true", help="development only")
    parser.add_argument("--fail-on-withhold", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = sys.stdin.read() if args.report == "-" else Path(args.report).read_text(encoding="utf-8")
    registry = UrlRegistry.load(args.url_registry)
    registry_hash = hashlib.sha256(Path(args.url_registry).read_bytes()).hexdigest() if Path(args.url_registry).exists() else None
    result = score_query_rubric(
        args.rubric,
        report,
        args.ledger,
        registry,
        expected_run_id=args.expected_run_id,
        seed_urls=args.seed_url,
        require_frozen=not args.allow_non_frozen,
        corpus_registry_hash=registry_hash,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    if args.fail_on_withhold and result.get("status") == "withheld":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
