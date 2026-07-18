#!/usr/bin/env python3
"""Create or check the human-owned DRA v3 release-readiness handoff."""

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

from src.eval.release_gate_v3 import (  # noqa: E402
    RELEASE_READINESS_SCHEMA,
    RELEASE_READINESS_V2_SCHEMA,
    check_release_readiness,
    check_release_readiness_v2,
    new_release_readiness_template,
    new_release_readiness_v2_template,
)


def _write_json(value: object, output: Path | None) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(rendered)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp.{os.getpid()}")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--init-template",
        action="store_true",
        help="emit the frozen v1 Pilot-12 TODO document",
    )
    mode.add_argument(
        "--check",
        type=Path,
        metavar="READINESS_JSON",
        help="check the frozen v1 Pilot-12/validation-30 readiness document",
    )
    mode.add_argument(
        "--init-v2-template",
        action="store_true",
        help="emit the additive v2 Dev-14/Formal-86 TODO document",
    )
    mode.add_argument(
        "--check-v2",
        type=Path,
        metavar="READINESS_V2_JSON",
        help=(
            "check the additive v2 Dev-14/Formal-86 and acquisition-path "
            "coverage readiness document"
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="write JSON here instead of stdout (template or check result)",
    )
    return parser


def _invalid_result(message: str, *, schema: str) -> dict[str, Any]:
    return {
        "schema": schema,
        "status": "invalid",
        "code_ready": False,
        "manual_review_complete": False,
        "formal_release_eligible": False,
        "verified_machine_artifacts": [],
        "machine_pending": [],
        "manual_pending": [],
        "errors": [message],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.init_template:
        _write_json(new_release_readiness_template(), args.out)
        return 0
    if args.init_v2_template:
        _write_json(new_release_readiness_v2_template(), args.out)
        return 0

    is_v2 = args.check_v2 is not None
    source: Path = args.check_v2 if is_v2 else args.check
    schema = RELEASE_READINESS_V2_SCHEMA if is_v2 else RELEASE_READINESS_SCHEMA
    try:
        raw = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {token}")
            ),
        )
        if not isinstance(raw, dict):
            raise ValueError("readiness document must be a JSON object")
        checker = check_release_readiness_v2 if is_v2 else check_release_readiness
        result = checker(raw, base_dir=source.parent)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        result = _invalid_result(str(exc), schema=schema)
    _write_json(result, args.out)
    if result["status"] == "formal_release_eligible":
        return 0
    if result["status"] == "invalid":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
