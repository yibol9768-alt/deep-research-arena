#!/usr/bin/env python3
"""Build the blank, independent pending-human oracle handoff for Q37.

Only the public task/query, frozen search bytes, and frozen target-page bytes
are reviewer-visible.  The private case, graph annotations, and synthetic
fixtures stay explicitly prohibited until the independent submission exists.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
TASK_ID = "dra_v3_formal_gaming_0037"
RUN_ID = "q37-human-formal-v1"
HUMAN_ROOT = HERE / "human_pending"
CASE_PATH = ROOT / "data/golden/cases_v3/formal_candidates" / f"{TASK_ID}.json"
PUBLIC_TASK_PATH = (
    ROOT / "data/tasks/deep_research/v3/formal_candidates" / f"{TASK_ID}.json"
)
QUERY_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "query_candidates/attempt1.txt"
)
INVENTORY_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "graph_inputs/inventory.json"
)
GRAPH_DIR = (
    ROOT
    / "data/evidence_graph"
    / "dra-v3-formal-gaming-0037-retro-mini-evidence-boundary-20260716-r1"
)
PROTOCOL_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "protocol_manifests/protocol.json"
)
REVIEW_MANIFEST_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "oracle_suites/human_pending/evidence_review_packet/manifest.json"
)
SUITE_PATH = HERE / "synthetic/suite.json"
VALIDATION_PATH = HERE / "synthetic/validation.json"


def _load_handoff_helpers():
    helper_path = (
        ROOT
        / "data/pilot_v3/formal_candidates/dra_v3_formal_gaming_0035"
        / "oracle_suites/build_human_oracle_handoff.py"
    )
    spec = importlib.util.spec_from_file_location("dra_v3_q37_handoff_helpers", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load handoff helpers: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = HERE
    module.ROOT = ROOT
    module.TASK_ID = TASK_ID
    module.RUN_ID = RUN_ID
    module.HUMAN_ROOT = HUMAN_ROOT
    module.CASE_PATH = CASE_PATH
    module.PUBLIC_TASK_PATH = PUBLIC_TASK_PATH
    module.QUERY_PATH = QUERY_PATH
    module.INVENTORY_PATH = INVENTORY_PATH
    module.GRAPH_DIR = GRAPH_DIR
    module.PROTOCOL_PATH = PROTOCOL_PATH
    module.REVIEW_MANIFEST_PATH = REVIEW_MANIFEST_PATH
    module.SUITE_PATH = SUITE_PATH
    module.VALIDATION_PATH = VALIDATION_PATH

    # The source helper's default argument captured its own HUMAN_ROOT at
    # definition time, so rebind this tiny path helper for Q37 explicitly.
    def binding(path: Path, *, relative_to: Path = HUMAN_ROOT) -> dict[str, str]:
        return {
            "path": path.relative_to(relative_to).as_posix(),
            "sha256": module.sha256_file(path),
        }

    module.binding = binding
    return module


H = _load_handoff_helpers()


def main() -> None:
    H.main()

    # The reusable HTML renderer and replay label contain their source fixture's
    # display tag.  Correct only those public labels; hashes are recomputed below.
    html_path = HUMAN_ROOT / "human_inputs/index.html"
    html_text = html_path.read_text(encoding="utf-8").replace("Q35", "Q37")
    H.write_text(html_path, html_text)

    packet_path = HUMAN_ROOT / "human_oracle_packet.json"
    packet = H.load_object(packet_path, "human handoff packet")
    replay = packet.get("replay_command")
    if not isinstance(replay, list):
        raise ValueError("human handoff replay_command must be an array")
    packet["replay_command"] = [
        "human-oracle-q37" if value == "human-oracle-q35" else value
        for value in replay
    ]
    offline = packet["reviewer_inputs"]["offline_index"]
    offline["sha256"] = H.sha256_file(html_path)
    H.write_json(packet_path, packet)
    print(
        json.dumps(
            {
                "status": "pending_human",
                "formal_oracle_gate_passed": False,
                "packet": str(packet_path.relative_to(ROOT)),
                "packet_sha256": H.sha256_file(packet_path),
                "offline_index": str(html_path.relative_to(ROOT)),
                "search_snapshots": len(
                    packet["reviewer_inputs"]["allowed_starting_search_snapshots"]
                ),
                "source_snapshots": len(
                    packet["reviewer_inputs"]["allowed_source_snapshots_after_discovery"]
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
