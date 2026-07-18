from __future__ import annotations

import json
from pathlib import Path

from src.eval.pilot_audit_v3 import build_audit_worksheet, promotion_readiness


ROOT = Path(__file__).resolve().parents[1]


def _manifest():
    return json.loads((ROOT / "data/pilot_v3/candidate_20.json").read_text())


def test_candidate_20_contains_scenarios_only_and_builds_blank_audit():
    audit = build_audit_worksheet(
        _manifest(), ROOT / "data/tasks/deep_research/cross_site_deep"
    )
    assert len(audit["candidates"]) == 20
    assert audit["promotion_is_manual"] is True
    assert all(row["verdict"] == "pending" for row in audit["candidates"])
    assert promotion_readiness(audit)["ready_for_manual_case_authoring"] == []


def test_eligible_label_alone_cannot_promote_a_candidate():
    audit = build_audit_worksheet(
        _manifest(), ROOT / "data/tasks/deep_research/cross_site_deep"
    )
    audit["candidates"][0]["verdict"] = "eligible"
    result = promotion_readiness(audit)
    assert not result["ready_for_manual_case_authoring"]
    assert "eligible without all evidence" in result["errors"][0]


def test_all_evidence_gates_and_a_reviewer_are_required_for_readiness():
    audit = build_audit_worksheet(
        _manifest(), ROOT / "data/tasks/deep_research/cross_site_deep"
    )
    row = audit["candidates"][0]
    row["verdict"] = "eligible"
    row["reviewers"] = ["human-reviewer"]
    for index, (role, leg) in enumerate(row["source_roles"].items()):
        selected = index < 2
        leg["on_critical_path"] = selected
        leg["irreplaceable"] = True if selected else False
        leg["status"] = "present" if selected else "absent"
        leg["evidence_ids"] = [f"ev-{role}"] if selected else []
    row["decision_rule"] = {
        "status": "present",
        "rule_ids": ["decision-rule-v1"],
        "reviewer_note": "checked",
    }
    row["gates"] = {key: True for key in row["gates"]}
    result = promotion_readiness(audit)
    assert result["ready_for_manual_case_authoring"] == [row["candidate_id"]]


def test_audit_does_not_force_three_symmetric_source_roles():
    audit = build_audit_worksheet(
        _manifest(), ROOT / "data/tasks/deep_research/cross_site_deep"
    )
    row = audit["candidates"][0]
    row["verdict"] = "eligible"
    row["reviewers"] = ["human-reviewer"]
    for role, entry in row["source_roles"].items():
        selected = role in {"mechanism", "community"}
        entry.update({
            "status": "present" if selected else "absent",
            "on_critical_path": selected,
            "irreplaceable": selected,
            "evidence_ids": [f"ev-{role}"] if selected else [],
        })
    row["decision_rule"].update({
        "status": "present", "rule_ids": ["rule-v1"]
    })
    row["gates"] = {key: True for key in row["gates"]}
    assert promotion_readiness(audit)["ready_for_manual_case_authoring"] == [
        row["candidate_id"]
    ]


def test_one_source_role_cannot_claim_cross_source_readiness():
    audit = build_audit_worksheet(
        _manifest(), ROOT / "data/tasks/deep_research/cross_site_deep"
    )
    row = audit["candidates"][0]
    row["verdict"] = "eligible"
    row["reviewers"] = ["human-reviewer"]
    for role, entry in row["source_roles"].items():
        selected = role == "mechanism"
        entry.update({
            "status": "present" if selected else "absent",
            "on_critical_path": selected,
            "irreplaceable": selected,
            "evidence_ids": ["ev-mechanism"] if selected else [],
        })
    row["decision_rule"].update({
        "status": "present", "rule_ids": ["rule-v1"]
    })
    row["gates"] = {key: True for key in row["gates"]}
    result = promotion_readiness(audit)
    assert not result["ready_for_manual_case_authoring"]
    assert result["errors"]
