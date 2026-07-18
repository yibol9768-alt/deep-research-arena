from __future__ import annotations

import hashlib
import json

import pytest

from scripts.build_verified_slots_board import main as board_cli
from src.eval.board_v3 import V3BoardError, aggregate_scores
from src.eval.evidence_graph import (
    EVIDENCE_GRAPH_MANIFEST_VERSION,
    canonical_json_bytes,
)
from src.eval.protocol_manifest_v3 import (
    PROTOCOL_MANIFEST_SCHEMA,
    scorer_implementation_sha256,
)
from src.eval.protocol_v3 import protocol_stamp


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _protocol(tasks=("t1", "t2")):
    return protocol_stamp(
        corpus_snapshot="snap",
        task_ids=tasks,
        case_hashes={task: _digest(f"case:{task}") for task in tasks},
        public_task_hashes={
            task: _digest(f"public:{task}") for task in tasks
        },
        evidence_graph_hash="f" * 64,
        corpus_registry_hash="e" * 64,
    )


def _manifest(tasks=("t1", "t2"), clusters=None):
    tasks = tuple(tasks)
    clusters = dict(clusters or {task: f"cluster:{task}" for task in tasks})
    protocols = _protocol(tasks)
    payload = {
        "schema": PROTOCOL_MANIFEST_SCHEMA,
        "protocols": protocols,
        "task_ids": sorted(tasks),
        "task_clusters": {task: clusters[task] for task in sorted(tasks)},
        "task_contracts": {
            task: {
                "cluster_id": clusters[task],
                "motif": "comparative_tradeoff",
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
                "registry_entries": 1,
                "nodes": 1,
                "edges": 1,
                "support_spans": 1,
            },
        },
    }
    payload["manifest_sha256"] = hashlib.sha256(
        canonical_json_bytes(payload)
    ).hexdigest()
    return payload


def _resign(row):
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
    row["scoring_input_sha256"] = hashlib.sha256(json.dumps(
        {"version": "dra_v3_scoring_input_v2", **identity},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()).hexdigest()
    return row


def _row(
    agent,
    task,
    rep,
    passed,
    f1,
    cluster,
    *,
    manifest,
    completion=None,
    status="scored",
):
    row = {
        "agent": agent,
        "task_id": task,
        "replicate": rep,
        "cluster_id": cluster,
        "status": status,
        "task_pass": passed,
        "verified_research_completion": f1 if completion is None else completion,
        "verified_f1": f1,
        "evidence_completion": f1,
        "bridge_completion": f1,
        "decision_completion": float(passed),
        "fabricated_citations": 0,
        "critical_contradictions": 0,
        "scorer_observability_complete": True,
        "protocols": dict(manifest["protocols"]),
        "run_id": f"run:{agent}:{task}:{rep}",
        "report_sha256": _digest(f"report:{agent}:{task}:{rep}"),
        "observation_ledger_sha256": _digest(f"ledger:{agent}:{task}:{rep}"),
        "case_artifact_sha256": manifest["case_hashes"][task],
        "public_task_sha256": manifest["public_task_hashes"][task],
        "protocol_manifest_sha256": manifest["manifest_sha256"],
        "corpus_registry_hash": manifest["protocols"]["corpus_registry_hash"],
    }
    return _resign(row)


def _formal(rows, manifest, *, agents=None, replicates=None, **kwargs):
    return aggregate_scores(
        rows,
        protocol_manifest=manifest,
        expected_agents=agents or sorted({row["agent"] for row in rows}),
        expected_replicates=(
            replicates or sorted({row["replicate"] for row in rows})
        ),
        **kwargs,
    )


def test_replicates_average_inside_task_then_tasks_macro_average():
    manifest = _manifest(
        clusters={"t1": "shared", "t2": "other"}
    )
    rows = [
        _row("a", "t1", 1, 1, 1.0, "shared", manifest=manifest),
        _row("a", "t1", 2, 0, 0.5, "shared", manifest=manifest),
        _row("a", "t2", 1, 0, 0.25, "other", manifest=manifest),
        _row("a", "t2", 2, 0, 0.25, "other", manifest=manifest),
    ]
    board = _formal(rows, manifest, bootstrap_samples=20)
    out = board["rows"][0]
    assert out["task_solve_rate"] == 0.25
    assert out["verified_research_completion"] == 0.5
    assert out["macro_verified_f1"] == 0.5
    assert out["macro_evidence_completion"] == 0.5
    assert out["macro_bridge_completion"] == 0.5
    assert out["macro_decision_completion"] == 0.25
    assert out["tasks"][0]["n_replicates"] == 2
    assert out["verified_research_completion_ci95"] is not None
    assert board["protocol_manifest_sha256"] == manifest["manifest_sha256"]
    assert board["scorer_implementation_sha256"] == manifest[
        "scorer_implementation_sha256"
    ]
    assert board["formal_grid"]["n_expected_runs"] == 4
    assert board["aggregation"]["bootstrap"] == "evidence-subgraph cluster bootstrap"
    assert board["headline_metrics"] == [
        "verified_research_completion",
        "task_solve_rate",
    ]


def test_research_completion_is_a_required_independent_headline():
    manifest = _manifest(("t1",), {"t1": "c"})
    row = _row(
        "a", "t1", 1, 0, 0.75, "c", completion=0.5, manifest=manifest
    )
    board = _formal([row], manifest, bootstrap_samples=2)
    assert board["rows"][0]["verified_research_completion"] == 0.5
    assert board["rows"][0]["task_solve_rate"] == 0.0
    broken = dict(row)
    broken.pop("verified_research_completion")
    with pytest.raises(V3BoardError, match="verified_research_completion"):
        _formal([broken], manifest, bootstrap_samples=2)


def test_withheld_is_never_silently_zeroed():
    manifest = _manifest(clusters={"t1": "c1", "t2": "c2"})
    rows = [
        _row("a", "t1", 1, 1, 1.0, "c1", manifest=manifest),
        _row(
            "a", "t2", 1, 0, 0.0, "c2", status="withheld", manifest=manifest
        ),
    ]
    with pytest.raises(V3BoardError, match="complete attributable coverage"):
        _formal(rows, manifest)
    board = aggregate_scores(
        rows,
        expected_tasks=["t1", "t2"],
        require_complete=False,
        bootstrap_samples=2,
    )
    assert board["rows"][0]["n_attributable_tasks"] == 1
    assert board["rows"][0]["task_solve_rate"] == 1.0
    assert board["incomplete"][0]["withheld"]


def test_legacy_quality_fields_are_refused():
    manifest = _manifest(("t1",), {"t1": "c"})
    row = _row("a", "t1", 1, 1, 1.0, "c", manifest=manifest)
    row["quality"] = 0.9
    with pytest.raises(V3BoardError, match="forbidden"):
        _formal([row], manifest)


def test_task_pass_cannot_hide_fabrication_or_observation_damage():
    manifest = _manifest(("t1",), {"t1": "c"})
    row = _row("a", "t1", 1, 1, 1.0, "c", manifest=manifest)
    row["fabricated_citations"] = 1
    with pytest.raises(V3BoardError, match="contradicts fabricated"):
        _formal([row], manifest)
    row["fabricated_citations"] = 0
    row["scorer_observability_complete"] = False
    with pytest.raises(V3BoardError, match="must be withheld"):
        _formal([row], manifest)


def test_duplicate_replicates_and_cluster_drift_are_refused():
    manifest = _manifest(("t1",), {"t1": "c"})
    row = _row("a", "t1", 1, 1, 1.0, "c", manifest=manifest)
    with pytest.raises(V3BoardError, match="duplicate"):
        _formal([row, dict(row)], manifest)
    drift = _row("a", "t1", 2, 1, 1.0, "c", manifest=manifest)
    drift["cluster_id"] = "different"
    _resign(drift)
    with pytest.raises(V3BoardError, match="cluster_id"):
        _formal([row, drift], manifest)


def test_formal_board_must_cover_exact_manifest_task_set():
    manifest = _manifest(clusters={"t1": "c1", "t2": "c2"})
    row = _row("a", "t1", 1, 1, 1.0, "c1", manifest=manifest)
    with pytest.raises(V3BoardError, match="complete attributable coverage"):
        _formal([row], manifest)
    with pytest.raises(V3BoardError, match="validated protocol manifest"):
        _formal([row], manifest, expected_tasks=["t1"])


def test_score_outside_expected_task_set_is_rejected_in_diagnostic_mode():
    manifest = _manifest(("t2",), {"t2": "c"})
    row = _row("a", "t2", 1, 1, 1.0, "c", manifest=manifest)
    row["protocols"] = _protocol(("t1",))
    with pytest.raises(V3BoardError, match="outside the expected"):
        aggregate_scores(
            [row], expected_tasks=["t1"], require_complete=False
        )


def test_cluster_identity_is_checked_against_manifest():
    manifest = _manifest(("t1",), {"t1": "cluster-a"})
    rows = [
        _row("a", "t1", 1, 1, 1.0, "cluster-a", manifest=manifest),
        _row("b", "t1", 1, 1, 1.0, "cluster-a", manifest=manifest),
    ]
    rows[1]["cluster_id"] = "cluster-b"
    _resign(rows[1])
    with pytest.raises(V3BoardError, match="cluster_id"):
        _formal(rows, manifest)


def test_formal_board_requires_full_manifest_and_explicit_grid_axes():
    manifest = _manifest(("t1",), {"t1": "c"})
    row = _row("a", "t1", 1, 1, 1.0, "c", manifest=manifest)
    with pytest.raises(V3BoardError, match="protocol_manifest"):
        aggregate_scores([row], expected_agents=["a"], expected_replicates=[1])
    with pytest.raises(V3BoardError, match="expected_agents"):
        aggregate_scores(
            [row], protocol_manifest=manifest, expected_replicates=[1]
        )
    with pytest.raises(V3BoardError, match="expected_replicates"):
        aggregate_scores(
            [row], protocol_manifest=manifest, expected_agents=["a"]
        )


def test_formal_board_requires_verified_replay_identity_chain():
    manifest = _manifest(("t1",), {"t1": "c"})
    row = _row("a", "t1", 1, 1, 1.0, "c", manifest=manifest)
    missing = dict(row)
    missing.pop("observation_ledger_sha256")
    with pytest.raises(V3BoardError, match="observation_ledger_sha256"):
        _formal([missing], manifest)

    tampered = dict(row, scoring_input_sha256="0" * 64)
    with pytest.raises(V3BoardError, match="does not match replay identity"):
        _formal([tampered], manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("case_artifact_sha256", "0" * 64),
        ("public_task_sha256", "1" * 64),
        ("protocol_manifest_sha256", "2" * 64),
    ],
)
def test_formal_score_artifacts_must_equal_manifest(field, value):
    manifest = _manifest(("t1",), {"t1": "c"})
    row = _row("a", "t1", 1, 1, 1.0, "c", manifest=manifest)
    row[field] = value
    _resign(row)
    with pytest.raises(V3BoardError, match=field):
        _formal([row], manifest)


def test_attribution_and_public_task_are_in_scoring_input_hash():
    manifest = _manifest(("t1",), {"t1": "c"})
    row = _row("a", "t1", 1, 1, 1.0, "c", manifest=manifest)
    tampered = dict(row, agent="b")
    with pytest.raises(V3BoardError, match="scoring_input_sha256"):
        _formal([tampered], manifest, agents=["b"])


def test_formal_board_refuses_reused_run_identity():
    manifest = _manifest(("t1",), {"t1": "c"})
    first = _row("a", "t1", 1, 1, 1.0, "c", manifest=manifest)
    second = _row("b", "t1", 1, 1, 1.0, "c", manifest=manifest)
    second["run_id"] = first["run_id"]
    _resign(second)
    with pytest.raises(V3BoardError, match="run_id .* is reused"):
        _formal([first, second], manifest)


def test_formal_grid_refuses_missing_or_implicit_replicates():
    manifest = _manifest(("t1",), {"t1": "c"})
    row = _row("a", "t1", 1, 1, 1.0, "c", manifest=manifest)
    with pytest.raises(V3BoardError, match="complete attributable coverage"):
        _formal([row], manifest, replicates=[1, 2])
    missing = dict(row)
    missing.pop("replicate")
    with pytest.raises(V3BoardError, match="explicit replicate"):
        _formal([missing], manifest, replicates=[1])


def test_formal_bootstrap_must_be_positive():
    manifest = _manifest(("t1",), {"t1": "c"})
    row = _row("a", "t1", 1, 1, 1.0, "c", manifest=manifest)
    with pytest.raises(V3BoardError, match="bootstrap_samples > 0"):
        _formal([row], manifest, bootstrap_samples=0)


def test_diagnostic_mode_still_allows_incomplete_unsealed_inputs():
    manifest = _manifest(("t1",), {"t1": "c"})
    row = _row("a", "t1", 1, 1, 1.0, "c", manifest=manifest)
    row.pop("replicate")
    row.pop("public_task_sha256")
    board = aggregate_scores(
        [row], require_complete=False, bootstrap_samples=0
    )
    assert board["formal"] is False
    assert board["protocol_manifest_sha256"] is None
    assert board["rows"][0]["task_solve_rate_ci95"] is None


def test_formal_cli_requires_and_consumes_manifest_and_grid(tmp_path):
    manifest = _manifest(("t1",), {"t1": "c"})
    row = _row("a", "t1", 1, 1, 1.0, "c", manifest=manifest)
    score_path = tmp_path / "score.json"
    manifest_path = tmp_path / "protocol.json"
    output_path = tmp_path / "board.json"
    score_path.write_text(json.dumps(row), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SystemExit):
        board_cli([str(score_path), "--out", str(output_path)])

    assert board_cli([
        str(score_path),
        "--protocol-manifest", str(manifest_path),
        "--expected-agent", "a",
        "--expected-replicate", "1",
        "--bootstrap-samples", "2",
        "--out", str(output_path),
    ]) == 0
    board = json.loads(output_path.read_text(encoding="utf-8"))
    assert board["formal"] is True
    assert board["protocol_manifest_sha256"] == manifest["manifest_sha256"]
