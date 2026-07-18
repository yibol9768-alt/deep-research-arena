#!/usr/bin/env python3
"""Build the blank independent pending-human oracle handoff for Q42.

Only the public task/query and frozen search/source bytes are reviewer-visible.
The private case, graph annotations, synthetic reports, and synthetic results
remain explicitly prohibited until the independent submission is complete.
"""

from __future__ import annotations

import json
import runpy
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
TASK_ID = "dra_v3_formal_coffee_tea_0042"
RUN_ID = "q42-human-formal-v1"
HUMAN_ROOT = HERE / "human_pending"
CASE_PATH = ROOT / "data/golden/cases_v3/formal_candidates" / f"{TASK_ID}.json"
PUBLIC_TASK_PATH = ROOT / "data/tasks/deep_research/v3" / f"{TASK_ID}.json"
QUERY_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "query_candidates/attempt2.txt"
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
    / "dra-v3-formal-coffee-tea-0042-premium-loose-leaf-value-20260716-r1"
)
PROTOCOL_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "protocol_manifests/protocol.json"
)
REVIEW_MANIFEST_PATH = HUMAN_ROOT / "evidence_review_packet/manifest.json"
SUITE_PATH = HERE / "synthetic/suite.json"
VALIDATION_PATH = HERE / "synthetic/validation.json"


BASE_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates/dra_v3_formal_coffee_tea_0038/"
    "oracle_suites/build_human_oracle_handoff.py"
)
_loaded = runpy.run_path(str(BASE_PATH), run_name="q42_human_handoff_base")
_base_main = _loaded["main"]
_base_html = _loaded["build_html"]
_globals = _base_main.__globals__
_globals.update(
    {
        "HERE": HERE,
        "ROOT": ROOT,
        "TASK_ID": TASK_ID,
        "RUN_ID": RUN_ID,
        "HUMAN_ROOT": HUMAN_ROOT,
        "CASE_PATH": CASE_PATH,
        "PUBLIC_TASK_PATH": PUBLIC_TASK_PATH,
        "QUERY_PATH": QUERY_PATH,
        "INVENTORY_PATH": INVENTORY_PATH,
        "GRAPH_DIR": GRAPH_DIR,
        "PROTOCOL_PATH": PROTOCOL_PATH,
        "REVIEW_MANIFEST_PATH": REVIEW_MANIFEST_PATH,
        "SUITE_PATH": SUITE_PATH,
        "VALIDATION_PATH": VALIDATION_PATH,
    }
)
sha256_file = _loaded["sha256_file"]
write_json = _loaded["write_json"]
write_text = _loaded["write_text"]


def binding(path: Path, *, relative_to: Path = HUMAN_ROOT) -> dict[str, str]:
    return {
        "path": path.relative_to(relative_to).as_posix(),
        "sha256": sha256_file(path),
    }


def build_html(query: str, search_rows: list[dict], source_rows: list[dict]) -> Path:
    output = _base_html(query, search_rows, source_rows)
    page = output.read_text(encoding="utf-8").replace("Q38", "Q42")
    page = page.replace(
        "真人独立 oracle 冻结入口",
        "高价散茶价值题：真人独立 oracle 冻结入口",
    )
    write_text(output, page)
    return output


_globals["binding"] = binding
_globals["build_html"] = build_html


def main() -> None:
    _base_main()
    packet_path = HUMAN_ROOT / "human_oracle_packet.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    command = packet.get("replay_command", [])
    packet["replay_command"] = [
        "human-oracle-q42" if item == "human-oracle-q38" else item
        for item in command
    ]
    write_json(packet_path, packet)
    print(
        json.dumps(
            {
                "status": "pending_human",
                "formal_oracle_gate_passed": False,
                "packet": str(packet_path.relative_to(ROOT)),
                "packet_sha256": sha256_file(packet_path),
                "offline_index": str(
                    (HUMAN_ROOT / "human_inputs/index.html").relative_to(ROOT)
                ),
                "search_snapshots": len(
                    packet["reviewer_inputs"]["allowed_starting_search_snapshots"]
                ),
                "source_snapshots": len(
                    packet["reviewer_inputs"]
                    ["allowed_source_snapshots_after_discovery"]
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
