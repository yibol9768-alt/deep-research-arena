from __future__ import annotations

import json
from pathlib import Path

from src.eval.query_rubric_schema import load_query_rubric


ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "data/golden/query_rubric_drafts/route_a_dev14_20260716"


def test_dev14_draft_packet_is_complete_and_fail_closed() -> None:
    manifest = json.loads((PACKET / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["task_count"] == 14
    assert manifest["atom_count"] == 58
    assert manifest["status"] == "draft"
    assert manifest["evidence_answerability"] == "not_assessed"
    assert manifest["formal_calibration_eligible"] is False

    task_ids = {f"dr_cross_deep_{index:04d}" for index in range(1, 15)}
    assert {row["task_id"] for row in manifest["tasks"]} == task_ids

    for row in manifest["tasks"]:
        rubric = load_query_rubric(ROOT / row["path"])
        assert rubric.status == "draft"
        assert rubric.content_sha256 == row["rubric_sha256"]
        assert len(rubric.atoms) == row["atom_count"]
        assert sum(atom.atom_type == "synthesis" for atom in rubric.atoms) >= 1
        assert all(atom.approved is False for atom in rubric.atoms)
        assert all(not atom.evidence.known_support for atom in rubric.atoms)
        assert all(not atom.evidence.acceptable_source_urls for atom in rubric.atoms)
        assert rubric.authoring["source"] == "public_query_only"
        assert rubric.authoring["evidence_answerability"] == "not_assessed"
        assert rubric.authoring["formal_calibration_eligible"] is False


def test_dev14_atoms_are_unweighted_and_unique_within_task() -> None:
    for path in sorted(PACKET.glob("dr_cross_deep_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        atom_ids = [atom["atom_id"] for atom in payload["atoms"]]
        descriptions = [atom["description"].strip().casefold() for atom in payload["atoms"]]
        assert len(atom_ids) == len(set(atom_ids))
        assert len(descriptions) == len(set(descriptions))
        assert all("weight" not in atom for atom in payload["atoms"])
        assert all(atom.get("required") is True for atom in payload["atoms"])
