#!/usr/bin/env python3
"""Seal a real Q28 human submission into a formal oracle suite.

This command never generates or fills a human answer.  It only validates the
four submitted files, checks the frozen base-suite binding, replaces the
synthetic human-shaped fixture, and writes a new formal suite for replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / "dra_v3_formal_smartphones_0030"
    / "oracle_suite/human_oracle_packet.json"
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _non_empty_text(path: Path, label: str) -> str:
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    value = path.read_text(encoding="utf-8")
    if not value.strip():
        raise ValueError(f"{label} must be non-empty")
    return value.strip() if label == "answer" else value


def _relative_artifact(path: Path, root: Path) -> dict[str, str]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"submission path escapes oracle-suite directory: {path}") from exc
    return {"path": str(relative), "sha256": _sha256_file(resolved)}


def finalize(packet_path: Path) -> Path:
    packet = _load_object(packet_path, "human oracle packet")
    if packet.get("schema") != "dra_v3_human_oracle_handoff_v1":
        raise ValueError("unsupported human oracle packet schema")
    if packet.get("status") != "pending_human":
        raise ValueError("human oracle packet is not pending_human")
    suite_root = packet_path.parent.resolve()

    base_binding = packet["bindings"]["synthetic_base_suite"]
    base_suite_path = suite_root / base_binding["path"]
    if _sha256_file(base_suite_path) != base_binding["sha256"]:
        raise ValueError("synthetic base suite no longer matches the handoff binding")
    suite = _load_object(base_suite_path, "synthetic base suite")

    contract = packet["submission_contract"]
    run_id = contract["run_id"]
    files = contract["files"]
    answer_path = suite_root / files["answer"]["path"]
    report_path = suite_root / files["report"]["path"]
    ledger_path = suite_root / files["ledger"]["path"]
    manual_path = suite_root / files["manual_record"]["path"]
    answer = _non_empty_text(answer_path, "answer")
    report_text = _non_empty_text(report_path, "report")
    if answer not in report_text:
        raise ValueError("the natural-language answer must appear in report.md")
    ledger = _load_object(ledger_path, "ledger")
    manual = _load_object(manual_path, "manual_record")

    if ledger.get("observation_semantics") != "observation_ledger_v1":
        raise ValueError("ledger must declare observation_ledger_v1")
    if ledger.get("run_id") != run_id or ledger.get("capture_complete") is not True:
        raise ValueError("ledger run_id/capture_complete does not match the handoff")
    expected_manual_fields = {
        "origin",
        "reviewer",
        "solve_minutes",
        "access_path",
        "attested",
        "synthetic",
    }
    if set(manual) != expected_manual_fields:
        raise ValueError(
            "manual_record fields must be exactly " + repr(sorted(expected_manual_fields))
        )
    if not (
        manual.get("origin") == "manual"
        and manual.get("attested") is True
        and manual.get("synthetic") is False
    ):
        raise ValueError(
            "manual_record requires origin=manual, attested=true, synthetic=false"
        )
    reviewer = manual.get("reviewer")
    minutes = manual.get("solve_minutes")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("manual_record reviewer must be non-empty")
    if type(minutes) not in {int, float} or float(minutes) <= 0:
        raise ValueError("manual_record solve_minutes must be positive")
    if not isinstance(manual.get("access_path"), list) or not manual["access_path"]:
        raise ValueError("manual_record access_path must be a non-empty array")

    human_indexes = [
        index
        for index, entry in enumerate(suite.get("oracles", []))
        if isinstance(entry, dict) and entry.get("kind") == "human"
    ]
    if len(human_indexes) != 1:
        raise ValueError("base suite must contain exactly one human-shaped run")
    suite["oracles"][human_indexes[0]] = {
        "run_id": run_id,
        "kind": "human",
        "report": _relative_artifact(report_path, suite_root),
        "ledger": _relative_artifact(ledger_path, suite_root),
        "manual_record": manual,
    }
    suite["suite_id"] = "dra-v3-smartphones-0030-formal-human-v1"
    suite["validation_scope"] = "formal"

    output = suite_root / "formal_suite.json"
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


