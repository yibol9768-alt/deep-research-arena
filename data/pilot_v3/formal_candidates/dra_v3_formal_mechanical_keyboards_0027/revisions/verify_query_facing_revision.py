#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
CANDIDATE = ROOT / "data/pilot_v3/formal_candidates/dra_v3_formal_mechanical_keyboards_0027"
OLD_DRAFT = CANDIDATE / "case_drafts/draft.json"
OLD_MOTIF = CANDIDATE / "motif_compilations/motif.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--new-draft", required=True, type=Path)
    parser.add_argument("--new-motif", required=True, type=Path)
    parser.add_argument("--revision", required=True, type=int)
    args = parser.parse_args()

    old_draft = load(OLD_DRAFT)
    new_draft = load(args.new_draft)
    old_motif = load(OLD_MOTIF)
    new_motif = load(args.new_motif)

    old_without_generator = copy.deepcopy(old_draft)
    new_without_generator = copy.deepcopy(new_draft)
    old_without_generator.pop("generator_view")
    new_without_generator.pop("generator_view")
    assert old_without_generator == new_without_generator
    assert old_draft["generator_view"] != new_draft["generator_view"]

    invariant_fields = [
        "evaluator_view",
        "rule_definitions",
        "decidable_claims",
        "oracle",
        "evidence_sources",
    ]
    for field in invariant_fields:
        assert old_draft[field] == new_draft[field], field

    old_compilation = old_motif["compilation"]
    new_compilation = new_motif["compilation"]
    assert old_motif["graph_stamp"] == new_motif["graph_stamp"]
    assert old_compilation["candidate_id"] == new_compilation["candidate_id"]
    assert old_compilation["evaluator_view"] == new_compilation["evaluator_view"]
    assert old_compilation["topology_checks"] == new_compilation["topology_checks"]
    criticality = [
        {
            "step_id": item["step_id"],
            "type": item["type"],
            "required": item["required"],
            "vital": item["vital"],
        }
        for item in old_compilation["evaluator_view"]["required_proof_steps"]
    ]

    print(
        json.dumps(
            {
                "schema": "dra_v3_query_facing_revision_equivalence_v1",
                "revision": args.revision,
                "status": "passed",
                "only_generator_view_changed": True,
                "graph_stamp": old_motif["graph_stamp"],
                "candidate_id": old_compilation["candidate_id"],
                "old_generator_view_sha256": digest(old_draft["generator_view"]),
                "new_generator_view_sha256": digest(new_draft["generator_view"]),
                "draft_without_generator_view_sha256": digest(
                    old_without_generator
                ),
                "evaluator_view_sha256": digest(old_draft["evaluator_view"]),
                "required_proof_steps_sha256": digest(
                    old_compilation["evaluator_view"]["required_proof_steps"]
                ),
                "criticality_sha256": digest(criticality),
                "rule_definitions_sha256": digest(old_draft["rule_definitions"]),
                "decidable_claims_sha256": digest(old_draft["decidable_claims"]),
                "acceptable_conclusions_sha256": digest(
                    old_draft["acceptable_conclusions"]
                ),
                "proof_subgraph_sha256": "2268da078fbc3fda919b4298d68b805085e958d1121b9ad4a8feb757da8c755e",
                "old_motif_compilation_sha256": old_compilation[
                    "compilation_sha256"
                ],
                "new_motif_compilation_sha256": new_compilation[
                    "compilation_sha256"
                ],
                "invariant_fields": invariant_fields
                + ["evaluator_view.required_proof_steps"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

