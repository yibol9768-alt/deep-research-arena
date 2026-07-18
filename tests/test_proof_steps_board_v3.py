from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from scripts.build_verified_slots_board import main as board_cli
from src.eval.board_v3 import V3BoardError, aggregate_proof_step_scores
from src.eval.evidence_graph import (
    EVIDENCE_GRAPH_MANIFEST_VERSION,
    canonical_json_bytes,
)
from src.eval.protocol_manifest_v3 import (
    PROTOCOL_MANIFEST_SCHEMA,
    scorer_implementation_sha256,
)
from src.eval.protocol_v3 import proof_steps_protocol_stamp


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _manifest(tasks=("t1", "t2"), clusters=None) -> dict:
    tasks = tuple(tasks)
    clusters = dict(clusters or {task: f"cluster:{task}" for task in tasks})
    protocols = proof_steps_protocol_stamp(
        corpus_snapshot="proof-board-snapshot-v1",
        task_ids=tasks,
        case_hashes={task: _digest(f"case:{task}") for task in tasks},
        public_task_hashes={
            task: _digest(f"public:{task}") for task in tasks
        },
        evidence_graph_hash="f" * 64,
        corpus_registry_hash="e" * 64,
    )
    payload = {
        "schema": PROTOCOL_MANIFEST_SCHEMA,
        "protocols": protocols,
        "task_ids": sorted(tasks),
        "task_clusters": {
            task: clusters[task] for task in sorted(tasks)
        },
        "task_contracts": {
            task: {
                "cluster_id": clusters[task],
                "motif": "claim_verification",
                "declared_proof_depth": 2,
                "minimum_reasoning_depth": 2,
                "required_research_subgoals": 4,
                "cross_source_bridges": 2,
                "single_page_sufficient": False,
            }
            for task in sorted(tasks)
        },
        "proof_subgraph_fingerprints": {
            task: _digest(f"proof:{task}") for task in sorted(tasks)
        },
        "case_hashes": {
            task: _digest(f"case:{task}") for task in sorted(tasks)
        },
        "public_task_hashes": {
            task: _digest(f"public:{task}") for task in sorted(tasks)
        },
        "scorer_implementation_sha256": scorer_implementation_sha256(),
        "evidence_graph_artifact": {
            "manifest_schema": EVIDENCE_GRAPH_MANIFEST_VERSION,
            "evidence_graph_hash": "f" * 64,
            "corpus_registry_hash": "e" * 64,
            "graph_corpus_hash": "d" * 64,
            "counts": {
                "registry_entries": 2,
                "nodes": 2,
                "edges": 1,
                "support_spans": 2,
            },
        },
    }
    payload["manifest_sha256"] = hashlib.sha256(
        canonical_json_bytes(payload)
    ).hexdigest()
    return payload


def _step(
    step_id: str,
    step_type: str,
    passed: bool,
    *,
    vital: bool = True,
    requires=(),
    branches=(),
) -> dict:
    if step_type == "evidence":
        axes = {
            "D": passed,
            "O": passed,
            "S": passed,
            "B": passed,
            "R": True,
        }
    else:
        axes = {
            "D": passed,
            "O": passed,
            "S": passed,
            "B": passed,
            "R": passed,
        }
    row = {
        "step_id": step_id,
        "type": step_type,
        "vital": vital,
        "required": True,
        "requires": list(requires),
        "route_branches": list(branches),
        **axes,
        "passed": all(axes.values()),
    }
    if step_type == "evidence":
        row["discovery_class"] = "searched" if passed else "not_discovered"
    return row


def _coverage(rows: list[dict]) -> dict:
    return {
        "required_steps": len(rows),
        "passed_steps": sum(1 for row in rows if row["passed"]),
        "coverage": (
            sum(1 for row in rows if row["passed"]) / len(rows)
            if rows
            else 0.0
        ),
    }


def _route(steps: list[dict]) -> dict:
    by_branch: dict[str, list[dict]] = {}
    for step in steps:
        for branch in step["route_branches"]:
            by_branch.setdefault(branch, []).append(step)
    return {
        "metric": "route_coverage_v1",
        "overall": _coverage(steps),
        "by_type": {
            "evidence": _coverage(
                [step for step in steps if step["type"] == "evidence"]
            ),
            "bridge": _coverage(
                [step for step in steps if step["type"] == "bridge"]
            ),
            "final_answer": _coverage(
                [step for step in steps if step["type"] == "decision"]
            ),
        },
        "by_branch": {
            branch: _coverage(rows)
            for branch, rows in sorted(by_branch.items())
        },
        "score_bearing": False,
    }


def _failure_reasons(
    steps: list[dict], *, fabricated: int, contradictions: int
) -> list[dict]:
    reasons: list[dict] = []
    vital_failed = [
        step["step_id"]
        for step in steps
        if step["vital"] and not step["passed"]
    ]
    final = [step for step in steps if step["type"] == "decision"]
    final_pass = bool(final) and all(step["passed"] for step in final)
    if vital_failed:
        reasons.append({
            "reason_code": "vital_proof_steps_failed",
            "step_ids": vital_failed,
        })
    if not final_pass:
        reasons.append({
            "reason_code": "final_answer_contract_failed",
            "step_ids": [step["step_id"] for step in final],
        })
    if contradictions:
        reasons.append({
            "reason_code": "critical_contradictions_present",
            "count": contradictions,
        })
    if fabricated:
        reasons.append({
            "reason_code": "fabricated_citations_present",
            "count": fabricated,
        })
    return reasons


def _resign(row: dict) -> dict:
    identity = {
        key: row[key]
        for key in (
            "run_id",
            "agent",
            "task_id",
            "replicate",
            "cluster_id",
            "report_sha256",
            "observation_ledger_sha256",
            "case_artifact_sha256",
            "public_task_sha256",
            "protocol_manifest_sha256",
            "corpus_registry_hash",
        )
    }
    row["scoring_input_sha256"] = hashlib.sha256(
        json.dumps(
            {"version": "dra_v3_scoring_input_v3", **identity},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return row


def _row(
    agent: str,
    task: str,
    replicate: int,
    passes: tuple[bool, bool, bool],
    *,
    cluster: str,
    manifest: dict,
    fabricated: int = 0,
    contradictions: int = 0,
    extra_steps: list[dict] | None = None,
) -> dict:
    evidence_pass, bridge_pass, decision_pass = passes
    steps = [
        _step(
            "E1",
            "evidence",
            evidence_pass,
            branches=("source_role:mechanism",),
        ),
        _step(
            "B1",
            "bridge",
            bridge_pass,
            requires=("E1",),
            branches=("synthesis",),
        ),
        _step(
            "D1",
            "decision",
            decision_pass,
            requires=("B1",),
            branches=("final_answer",),
        ),
        *(extra_steps or []),
    ]
    evidence = [step for step in steps if step["type"] == "evidence"]
    passed = sum(1 for step in steps if step["passed"])
    final = [step for step in steps if step["type"] == "decision"]
    final_answer_pass = bool(final) and all(step["passed"] for step in final)
    full_pass = int(
        all(step["passed"] for step in steps if step["vital"])
        and final_answer_pass
        and fabricated == 0
        and contradictions == 0
    )
    row = {
        "agent": agent,
        "task_id": task,
        "replicate": replicate,
        "cluster_id": cluster,
        "scoring_semantics": "proof_steps_v1",
        "status": "scored",
        "step_results": steps,
        "required_step_ids": [step["step_id"] for step in steps],
        "passed_steps": passed,
        "required_steps": len(steps),
        "partial_completion": passed / len(steps),
        "full_pass": full_pass,
        "final_answer_pass": final_answer_pass,
        "full_pass_failure_reasons": _failure_reasons(
            steps,
            fabricated=fabricated,
            contradictions=contradictions,
        ),
        "route_coverage": _route(steps),
        "acquisition_diagnostics": {
            "metric": "acquisition_diagnostics_v1",
            "required_evidence_steps": len(evidence),
            "discovery_licensed": sum(1 for step in evidence if step["D"]),
            "content_observed": sum(1 for step in evidence if step["O"]),
            "content_supported": sum(1 for step in evidence if step["S"]),
            "guessed_then_fetched": sum(
                1
                for step in evidence
                if step.get("discovery_class") == "guessed_then_fetched"
            ),
            "score_bearing": False,
        },
        "fabricated_citations": fabricated,
        "critical_contradictions": contradictions,
        "scorer_observability_complete": True,
        "protocols": dict(manifest["protocols"]),
        "run_id": f"run:{agent}:{task}:{replicate}",
        "report_sha256": _digest(f"report:{agent}:{task}:{replicate}"),
        "observation_ledger_sha256": _digest(
            f"ledger:{agent}:{task}:{replicate}"
        ),
        "case_artifact_sha256": manifest["case_hashes"][task],
        "public_task_sha256": manifest["public_task_hashes"][task],
        "protocol_manifest_sha256": manifest["manifest_sha256"],
        "corpus_registry_hash": manifest["protocols"][
            "corpus_registry_hash"
        ],
    }
    return _resign(row)


def _formal(rows: list[dict], manifest: dict) -> dict:
    return aggregate_proof_step_scores(
        rows,
        protocol_manifest=manifest,
        expected_agents=sorted({row["agent"] for row in rows}),
        expected_replicates=sorted({row["replicate"] for row in rows}),
        bootstrap_samples=20,
    )


def test_proof_board_averages_replicates_inside_task_then_macro_tasks() -> None:
    manifest = _manifest(clusters={"t1": "topic-a", "t2": "topic-b"})
    rows = [
        _row("a", "t1", 1, (True, True, True), cluster="topic-a", manifest=manifest),
        _row("a", "t1", 2, (True, False, False), cluster="topic-a", manifest=manifest),
        _row("a", "t2", 1, (True, True, False), cluster="topic-b", manifest=manifest),
        _row("a", "t2", 2, (True, True, False), cluster="topic-b", manifest=manifest),
    ]

    board = _formal(rows, manifest)
    result = board["rows"][0]

    assert board["schema"] == "dra_proof_steps_board_v1"
    assert board["headline_metrics"] == [
        "partial_completion_rate_v1",
        "full_pass_rate_v1",
    ]
    assert result["partial_completion_rate"] == 0.666667
    assert result["full_pass_rate"] == 0.25
    assert result["tasks"][0]["partial_completion"] == pytest.approx(2 / 3)
    assert result["tasks"][0]["full_pass"] == 0.5
    assert board["aggregation"]["bootstrap"] == (
        "topic_cluster x graph_motif cluster bootstrap"
    )


def test_non_vital_failure_reduces_partial_but_does_not_block_full_pass() -> None:
    manifest = _manifest(("t1",), {"t1": "topic-a"})
    non_vital = _step(
        "E2",
        "evidence",
        False,
        vital=False,
        branches=("source_role:community",),
    )
    row = _row(
        "a",
        "t1",
        1,
        (True, True, True),
        cluster="topic-a",
        manifest=manifest,
        extra_steps=[non_vital],
    )

    board = _formal([row], manifest)
    assert board["rows"][0]["partial_completion_rate"] == 0.75
    assert board["rows"][0]["full_pass_rate"] == 1.0


def test_fabrication_blocks_full_pass_without_erasing_completed_steps() -> None:
    manifest = _manifest(("t1",), {"t1": "topic-a"})
    row = _row(
        "a",
        "t1",
        1,
        (True, True, True),
        cluster="topic-a",
        manifest=manifest,
        fabricated=1,
    )

    board = _formal([row], manifest)
    assert board["rows"][0]["partial_completion_rate"] == 1.0
    assert board["rows"][0]["full_pass_rate"] == 0.0


def test_formal_board_rejects_step_alias_and_diagnostic_tampering() -> None:
    manifest = _manifest(("t1",), {"t1": "topic-a"})
    original = _row(
        "a",
        "t1",
        1,
        (True, True, True),
        cluster="topic-a",
        manifest=manifest,
    )

    bad_step = deepcopy(original)
    bad_step["step_results"][0]["passed"] = False
    with pytest.raises(V3BoardError, match="D AND O AND S AND B AND R"):
        _formal([bad_step], manifest)

    old_alias = deepcopy(original)
    old_alias["precision"] = 1.0
    with pytest.raises(V3BoardError, match="legacy aliases"):
        _formal([old_alias], manifest)

    bad_acquisition = deepcopy(original)
    bad_acquisition["acquisition_diagnostics"]["discovery_licensed"] += 1
    with pytest.raises(V3BoardError, match="evidence-step axes"):
        _formal([bad_acquisition], manifest)


def test_board_cli_requires_explicit_proof_semantics(tmp_path) -> None:
    manifest = _manifest(("t1",), {"t1": "topic-a"})
    row = _row(
        "a",
        "t1",
        1,
        (True, True, True),
        cluster="topic-a",
        manifest=manifest,
    )
    manifest_path = tmp_path / "manifest.json"
    score_path = tmp_path / "score.json"
    output_path = tmp_path / "board.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    score_path.write_text(json.dumps(row), encoding="utf-8")

    assert board_cli([
        str(score_path),
        "--scoring-semantics",
        "proof_steps_v1",
        "--protocol-manifest",
        str(manifest_path),
        "--expected-agent",
        "a",
        "--expected-replicate",
        "1",
        "--bootstrap-samples",
        "5",
        "--out",
        str(output_path),
    ]) == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["schema"] == (
        "dra_proof_steps_board_v1"
    )

