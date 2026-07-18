#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
CANDIDATE = ROOT / "data/pilot_v3/formal_candidates/dra_v3_formal_smartphones_0029"
OLD_DRAFT = CANDIDATE / "case_drafts/draft.json"
NEW_DRAFT = CANDIDATE / "case_drafts/draft.revision2.json"
OLD_MOTIF = CANDIDATE / "motif_compilations/motif.json"
NEW_MOTIF = CANDIDATE / "motif_compilations/motif.revision2.json"


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
    old_draft = load(OLD_DRAFT)
    new_draft = load(NEW_DRAFT)
    old_motif = load(OLD_MOTIF)
    new_motif = load(NEW_MOTIF)

    old_without_public_wording = copy.deepcopy(old_draft)
    new_without_public_wording = copy.deepcopy(new_draft)
    old_without_public_wording.pop("generator_view")
    new_without_public_wording.pop("generator_view")

    invariant_fields = [
        "evaluator_view",
        "rule_definitions",
        "decidable_claims",
        "oracle",
        "evidence_sources",
    ]
    for field in invariant_fields:
        assert old_draft[field] == new_draft[field], field
    assert old_without_public_wording == new_without_public_wording
    assert old_draft["generator_view"] != new_draft["generator_view"]

    old_compilation = old_motif["compilation"]
    new_compilation = new_motif["compilation"]
    assert old_motif["graph_stamp"] == new_motif["graph_stamp"]
    assert old_compilation["candidate_id"] == new_compilation["candidate_id"]
    assert old_compilation["evaluator_view"] == new_compilation["evaluator_view"]
    assert old_compilation["topology_checks"] == new_compilation["topology_checks"]
    assert (
        old_compilation["evaluator_view"]["required_proof_steps"]
        == new_compilation["evaluator_view"]["required_proof_steps"]
    )

    print(
        json.dumps(
            {
                "schema": "dra_v3_query_facing_revision_equivalence_v1",
                "status": "passed",
                "only_generator_view_changed": True,
                "graph_stamp": old_motif["graph_stamp"],
                "candidate_id": old_compilation["candidate_id"],
                "old_generator_view_sha256": digest(old_draft["generator_view"]),
                "new_generator_view_sha256": digest(new_draft["generator_view"]),
                "draft_without_generator_view_sha256": digest(
                    old_without_public_wording
                ),
                "evaluator_view_sha256": digest(old_draft["evaluator_view"]),
                "required_proof_steps_sha256": digest(
                    old_compilation["evaluator_view"]["required_proof_steps"]
                ),
                "proof_subgraph_sha256": "cf30168063df4106be9b310a5698eaf11ca4947f5d8af32dc6f9acb695c52d99",
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
