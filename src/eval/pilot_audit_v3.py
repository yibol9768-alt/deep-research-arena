"""Fail-closed workflow for selecting and auditing v3 pilot candidates.

Candidate selection is intentionally separate from case compilation.  A source
v2 task contributes only its scenario idea; none of its answer key, ranked
products, or legacy gold crosses this boundary.  Promotion requires human
review of frozen evidence IDs and every structural gate in the v3 plan.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path


MOTIFS = {
    "constraint_filter",
    "mechanism_application",
    "claim_reconciliation",
    "comparative_tradeoff",
    "counterexample_revision",
}
# Candidate reviewers may select two or more genuinely necessary roles.  The
# redesign explicitly forbids forcing product/mechanism/community into a
# symmetric quota merely to make a task look cross-source.
EVIDENCE_ROLES = ("product", "mechanism", "community", "case_spec")
FORBIDDEN_CANDIDATE_KEYS = {
    "gold",
    "answer_key",
    "answer_key_path",
    "source_url",
    "source_urls",
    "vital_product_urls",
    "acceptable_conclusions",
    "oracle",
    "slots",
}


class PilotAuditError(ValueError):
    """A candidate/audit document violates the corpus-first promotion rules."""


def _walk_keys(value):
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def validate_candidate_manifest(doc: Mapping, tasks_dir: Path) -> list[dict]:
    if doc.get("schema") != "dra-v3-pilot-candidates-v1":
        raise PilotAuditError("wrong candidate manifest schema")
    if doc.get("status") != "pending_corpus_audit":
        raise PilotAuditError("candidate manifest must remain pending_corpus_audit")
    candidates = doc.get("candidates")
    if not isinstance(candidates, list):
        raise PilotAuditError("candidates must be a list")
    expected = int(doc.get("target_count") or 0)
    if expected <= 0 or len(candidates) != expected:
        raise PilotAuditError(
            f"candidate count {len(candidates)} does not match target_count {expected}"
        )
    ids = [str(c.get("candidate_id") or "") for c in candidates]
    if not all(ids) or len(ids) != len(set(ids)):
        raise PilotAuditError("candidate_id values must be unique and non-empty")
    for candidate in candidates:
        forbidden = FORBIDDEN_CANDIDATE_KEYS & set(_walk_keys(candidate))
        if forbidden:
            raise PilotAuditError(
                f"{candidate.get('candidate_id')}: candidate leaks gold fields {sorted(forbidden)}"
            )
        task_id = str(candidate.get("source_task_id") or "")
        path = tasks_dir / f"{task_id}.json"
        if not path.is_file():
            raise PilotAuditError(f"{task_id}: source task does not exist")
        task = json.loads(path.read_text(encoding="utf-8"))
        if task.get("task_version") != 2:
            raise PilotAuditError(f"{task_id}: source must be a v2 scenario only")
        motifs = candidate.get("proposed_motifs")
        if not isinstance(motifs, list) or not motifs or not set(motifs) <= MOTIFS:
            raise PilotAuditError(f"{task_id}: invalid proposed_motifs {motifs!r}")
        if candidate.get("status") != "unreviewed":
            raise PilotAuditError(f"{task_id}: candidates start as unreviewed")
    return [dict(c) for c in candidates]


def build_audit_worksheet(doc: Mapping, tasks_dir: Path) -> dict:
    candidates = validate_candidate_manifest(doc, tasks_dir)
    return {
        "schema": "dra-v3-pilot-corpus-audit-v1",
        "candidate_manifest_schema": doc["schema"],
        "status": "human_review_required",
        "promotion_is_manual": True,
        "candidates": [
            {
                "candidate_id": c["candidate_id"],
                "source_task_id": c["source_task_id"],
                "proposed_motifs": c["proposed_motifs"],
                "verdict": "pending",
                "source_roles": {
                    role: {
                        "status": "unreviewed",
                        "on_critical_path": None,
                        "irreplaceable": None,
                        "evidence_ids": [],
                        "reviewer_note": "",
                    }
                    for role in EVIDENCE_ROLES
                },
                "decision_rule": {
                    "status": "unreviewed",
                    "rule_ids": [],
                    "reviewer_note": "",
                },
                "gates": {
                    "minimum_four_required_research_subgoals": None,
                    "minimum_two_irreplaceable_evidence_nodes": None,
                    "minimum_reasoning_depth_two": None,
                    "minimum_two_cross_source_bridges": None,
                    "single_page_sufficient_false": None,
                    "oracle_unique_or_admissible": None,
                    "all_critical_evidence_reachable": None,
                    "critical_node_ablation_passes": None,
                },
                "reviewers": [],
            }
            for c in candidates
        ],
    }


def promotion_readiness(audit: Mapping) -> dict:
    """Classify reviewed rows; never mutate or auto-promote them."""

    if audit.get("schema") != "dra-v3-pilot-corpus-audit-v1":
        raise PilotAuditError("wrong corpus audit schema")
    ready, rejected, pending, errors = [], [], [], []
    for row in audit.get("candidates") or []:
        cid = str(row.get("candidate_id") or "")
        verdict = row.get("verdict")
        if verdict == "rejected":
            rejected.append(cid)
            continue
        roles = row.get("source_roles") or {}
        decision_rule = row.get("decision_rule") or {}
        gates = row.get("gates") or {}
        selected_roles = [
            role
            for role in EVIDENCE_ROLES
            if (roles.get(role) or {}).get("on_critical_path") is True
        ]
        role_ok = len(selected_roles) >= 2 and all(
            (roles.get(role) or {}).get("status") == "present"
            and (roles.get(role) or {}).get("irreplaceable") is True
            and bool((roles.get(role) or {}).get("evidence_ids"))
            for role in selected_roles
        )
        unused_roles_ok = all(
            (roles.get(role) or {}).get("on_critical_path") is False
            for role in EVIDENCE_ROLES
            if role not in selected_roles
        )
        decision_ok = (
            decision_rule.get("status") == "present"
            and bool(decision_rule.get("rule_ids"))
        )
        gate_ok = bool(gates) and all(value is True for value in gates.values())
        reviewers = row.get("reviewers") or []
        if (
            verdict == "eligible"
            and role_ok
            and unused_roles_ok
            and decision_ok
            and gate_ok
            and reviewers
        ):
            ready.append(cid)
        elif verdict == "eligible":
            errors.append(f"{cid}: eligible without all evidence/gates/reviewer")
        else:
            pending.append(cid)
    return {
        "ready_for_manual_case_authoring": ready,
        "rejected": rejected,
        "pending": pending,
        "errors": errors,
    }


__all__ = [
    "MOTIFS",
    "EVIDENCE_ROLES",
    "PilotAuditError",
    "validate_candidate_manifest",
    "build_audit_worksheet",
    "promotion_readiness",
]
