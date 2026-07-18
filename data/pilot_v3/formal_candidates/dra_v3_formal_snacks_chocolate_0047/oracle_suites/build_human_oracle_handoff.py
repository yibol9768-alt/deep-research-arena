#!/usr/bin/env python3
"""Build the blank, independent pending-human oracle handoff for Q47.

Reviewer-visible files contain only the public task/query and exact frozen
search/source bytes. Private case data, graph annotations, and every synthetic
artifact remain prohibited until the human submits.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
TASK_ID = "dra_v3_formal_snacks_chocolate_0047"
RUN_ID = "q47-human-formal-v1"
HUMAN_ROOT = HERE / "human_pending"
GRAPH_NAME = "dra-v3-formal-snacks-chocolate-0047-ten-week-stash-bloom-oxidation-20260716-r1"


def load_handoff_helpers():
    source = HERE.parents[1] / "dra_v3_formal_coffee_tea_0040" / "oracle_suites" / "build_human_oracle_handoff.py"
    spec = importlib.util.spec_from_file_location("q47_handoff_helpers", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load handoff helpers from {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = load_handoff_helpers()
H.ROOT = ROOT
H.TASK_ID = TASK_ID
H.RUN_ID = RUN_ID
H.HUMAN_ROOT = HUMAN_ROOT
H.CASE_PATH = ROOT / "data/golden/cases_v3/formal_candidates" / f"{TASK_ID}.json"
H.PUBLIC_TASK_PATH = ROOT / "data/tasks/deep_research/v3/formal_candidates" / f"{TASK_ID}.json"
H.QUERY_PATH = ROOT / "data/pilot_v3/formal_candidates" / TASK_ID / "query_candidates/attempt2.txt"
H.INVENTORY_PATH = ROOT / "data/pilot_v3/formal_candidates" / TASK_ID / "graph_inputs/inventory.json"
H.GRAPH_DIR = ROOT / "data/evidence_graph" / GRAPH_NAME
H.PROTOCOL_PATH = ROOT / "data/pilot_v3/formal_candidates" / TASK_ID / "protocol_manifests/protocol.json"
H.REVIEW_MANIFEST_PATH = HUMAN_ROOT / "evidence_review_packet/manifest.json"
H.SUITE_PATH = HERE / "synthetic/suite.json"
H.VALIDATION_PATH = HERE / "synthetic/validation.json"


def binding(path: Path, *, relative_to: Path | None = None) -> dict[str, str]:
    base = HUMAN_ROOT if relative_to is None else relative_to
    return {"path": path.relative_to(base).as_posix(), "sha256": H.sha256_file(path)}


H.binding = binding
_base_build_html = H.build_html


def build_html(query: str, search_rows: list[dict], source_rows: list[dict]) -> Path:
    output = _base_build_html(query, search_rows, source_rows)
    text = output.read_text(encoding="utf-8")
    output.write_text(text.replace("Q40", "Q47").replace("q40", "q47"), encoding="utf-8")
    return output


H.build_html = build_html


def replace_q40(value):
    if isinstance(value, dict):
        return {key: replace_q40(item) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_q40(item) for item in value]
    if isinstance(value, str):
        return value.replace("Q40", "Q47").replace("q40", "q47")
    return value


def main() -> None:
    H.main()
    packet_path = HUMAN_ROOT / "human_oracle_packet.json"
    packet = replace_q40(json.loads(packet_path.read_text(encoding="utf-8")))
    H.write_json(packet_path, packet)
    print(json.dumps({
        "status": "pending_human",
        "formal_oracle_gate_passed": False,
        "packet": str(packet_path.relative_to(ROOT)),
        "packet_sha256": H.sha256_file(packet_path),
        "offline_index": str((HUMAN_ROOT / "human_inputs/index.html").relative_to(ROOT)),
        "search_snapshots": len(packet["reviewer_inputs"]["allowed_starting_search_snapshots"]),
        "source_snapshots": len(packet["reviewer_inputs"]["allowed_source_snapshots_after_discovery"]),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
