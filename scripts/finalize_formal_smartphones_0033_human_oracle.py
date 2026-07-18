#!/usr/bin/env python3
"""Seal a real Q33 human submission into a formal replay suite.

This command never writes or guesses the human answer.  It accepts only a
non-synthetic manual attestation whose chronological access path exactly
matches the submitted observation ledger, then delegates the remaining bound
artifact checks to the shared fail-closed finalizer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import finalize_formal_smartphones_0030_human_oracle as base


ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "dra_v3_formal_smartphones_0033"
DEFAULT_PACKET = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "oracle_suite/human_oracle_packet.json"
)


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _validate_access_path(packet_path: Path) -> None:
    packet = _load_object(packet_path, "human oracle packet")
    if packet.get("task_id") != TASK_ID:
        raise ValueError("human oracle packet is bound to a different task")
    if packet.get("status") != "pending_human":
        raise ValueError("human oracle packet is not pending_human")
    suite_root = packet_path.parent.resolve()
    contract = packet["submission_contract"]
    files = contract["files"]
    ledger = _load_object(
        suite_root / files["ledger"]["path"], "observation ledger"
    )
    manual = _load_object(
        suite_root / files["manual_record"]["path"], "manual record"
    )
    if ledger.get("run_id") != contract["run_id"]:
        raise ValueError("observation ledger run_id disagrees with handoff")
    events = ledger.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("observation ledger events must be a non-empty array")
    event_ids: list[int] = []
    content_path: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("every observation ledger event must be an object")
        event_id = event.get("event_id")
        if type(event_id) is not int:
            raise ValueError("every observation event requires an integer event_id")
        event_ids.append(event_id)
        if event.get("observable") is not True:
            raise ValueError("every submitted observation event must be observable")
        url = event.get("canonical_url") or event.get("request_url")
        if not isinstance(url, str) or not url:
            raise ValueError("every observation event requires a canonical URL")
        content_path.append(url)
    if event_ids != sorted(event_ids) or len(event_ids) != len(set(event_ids)):
        raise ValueError("observation event IDs must be unique and chronological")
    if manual.get("access_path") != content_path:
        raise ValueError(
            "manual_record access_path must exactly equal the ledger's "
            "chronological observable URL path"
        )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finalize(packet_path: Path) -> Path:
    _validate_access_path(packet_path)
    output = base.finalize(packet_path)
    suite = _load_object(output, "formal oracle suite")
    suite["suite_id"] = "dra-v3-smartphones-0033-formal-human-v1"
    output.write_text(
        json.dumps(suite, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    args = parser.parse_args()
    try:
        output = finalize(args.packet.resolve())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"human oracle finalization failed: {exc}")
        return 2
    print(
        json.dumps(
            {
                "status": "formal_suite_written",
                "suite": str(output),
                "suite_sha256": _sha256_file(output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
