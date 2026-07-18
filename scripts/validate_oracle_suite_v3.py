#!/usr/bin/env python3
"""Replay a DRA v3 oracle/adversarial suite and emit a sealed result."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.oracle_validation_v3 import (  # noqa: E402
    OracleSuiteValidationError,
    canonical_json_bytes,
    validate_oracle_suite,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "replay machine/human/minimal oracles and all required DRA v3 "
            "adversarial reports through the suite-selected scorer"
        )
    )
    parser.add_argument("--suite", required=True, help="oracle suite JSON")
    parser.add_argument(
        "--scoring-semantics",
        choices=("verified_slots_v1", "proof_steps_v1"),
        help=(
            "require this suite scoring semantics; proof_steps_v1 must also be "
            "declared inside the suite so the choice is bound by suite_sha256"
        ),
    )
    parser.add_argument("--out", help="write the self-hashed validation JSON here")
    parser.add_argument("--pretty", action="store_true", help="indent emitted JSON")
    return parser


def _serialize(result: dict, *, pretty: bool) -> str:
    if pretty:
        return json.dumps(
            result,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        ) + "\n"
    return canonical_json_bytes(result).decode("utf-8") + "\n"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    suite_path = Path(args.suite)
    try:
        suite_bytes = suite_path.read_bytes()
        suite = json.loads(suite_bytes.decode("utf-8"))
        if not isinstance(suite, dict):
            raise OracleSuiteValidationError("suite root must be a JSON object")
        declared_semantics = suite.get("scoring_semantics", "verified_slots_v1")
        if (
            args.scoring_semantics is not None
            and declared_semantics != args.scoring_semantics
        ):
            raise OracleSuiteValidationError(
                "suite scoring_semantics does not match --scoring-semantics"
            )
        result = validate_oracle_suite(
            suite,
            base_dir=suite_path.parent,
            suite_sha256=hashlib.sha256(suite_bytes).hexdigest(),
        )
        rendered = _serialize(result, pretty=args.pretty)
        if args.out:
            output = Path(args.out)
            if output.resolve() == suite_path.resolve():
                raise OracleSuiteValidationError("--out cannot overwrite the suite input")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, OracleSuiteValidationError) as exc:
        print(f"oracle suite validation failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
