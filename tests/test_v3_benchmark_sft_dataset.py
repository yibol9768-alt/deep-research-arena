from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.tasks.benchmark_sft_dataset_v3 import (
    BuildOptions,
    DatasetBuildError,
    build_same_task_pilot,
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path: Path, payload: bytes) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"path": path.name, "sha256": _sha(payload)}


def _fixture(tmp_path: Path, *, layout: str = "old") -> Path:
    candidates = tmp_path / "candidates"
    if layout == "old":
        suite_dir = candidates / "case-001" / "oracle_suite"
    elif layout == "new":
        suite_dir = candidates / "case-001" / "oracle_suites" / "synthetic"
    else:
        raise AssertionError(f"unknown test layout: {layout}")
    suite_dir.mkdir(parents=True)

    case_ref = _write(suite_dir / "case.json", b'{"case":"ok"}\n')
    graph_ref = _write(suite_dir / "graph.json", b'{"graph":"ok"}\n')
    protocol_ref = _write(suite_dir / "protocol.json", b'{"protocol":"ok"}\n')
    public_raw = json.dumps(
        {
            "task_id": "case-001",
            "cluster_id": "cluster-a",
            "motif": "constraint_composition",
            "corpus_snapshot": "snapshot-a",
            "intent": "Compare the two options and give an evidence-grounded answer.",
        },
        sort_keys=True,
    ).encode("utf-8")
    public_ref = _write(suite_dir / "public.json", public_raw)
    report_raw = (
        "Option A is preferable under the stated condition "
        "[source](http://localhost:7770/a).\n"
    ).encode("utf-8")
    report_ref = _write(suite_dir / "report.md", report_raw)
    ledger_ref = _write(
        suite_dir / "ledger.json",
        b'{"capture_complete":true,"events":[]}\n',
    )

    suite = {
        "schema": "dra_v3_oracle_suite_v1",
        "suite_id": "suite-case-001",
        "validation_scope": "synthetic_test",
        "case": case_ref,
        "evidence_graph": graph_ref,
        "public_task": public_ref,
        "protocols": protocol_ref,
        "scoring_semantics": "proof_steps_v1",
        "oracles": [
            {
                "kind": "machine",
                "run_id": "run-machine-001",
                "answer": "option_a_conditionally",
                "report": report_ref,
                "ledger": ledger_ref,
            }
        ],
        "adversarial": [],
    }
    suite_raw = json.dumps(suite, sort_keys=True).encode("utf-8")
    (suite_dir / "suite.json").write_bytes(suite_raw)
    validation = {
        "schema": "dra_v3_oracle_suite_validation_v1",
        "status": "validated",
        "suite_id": "suite-case-001",
        "suite_sha256": _sha(suite_raw),
        "task_id": "case-001",
        "validation_scope": "synthetic_test",
        "validation_tier": "mechanism_test",
        "synthetic_only": True,
        "formal_human_validation_passed": False,
        "requires_real_human_followup": True,
        "oracle_results": [
            {
                "kind": "machine",
                "run_id": "run-machine-001",
                "report_artifact": {"sha256": _sha(report_raw)},
                "score": {
                    "scoring_semantics": "proof_steps_v1",
                    "required_steps": 3,
                    "passed_steps": 3,
                    "partial_completion": 1.0,
                    "full_pass": 1,
                    "fabricated_citations": 0,
                    "critical_contradictions": 0,
                    "used_citations": ["http://localhost:7770/a"],
                },
            }
        ],
    }
    (suite_dir / "validation.json").write_text(
        json.dumps(validation, sort_keys=True), encoding="utf-8"
    )
    return candidates


def test_same_task_export_requires_explicit_overlap_acknowledgement(tmp_path: Path):
    candidates = _fixture(tmp_path)
    with pytest.raises(DatasetBuildError, match="exact benchmark/SFT task overlap"):
        build_same_task_pilot(
            candidates,
            tmp_path / "out",
            options=BuildOptions(allow_synthetic=True),
        )


def test_same_task_export_builds_training_and_benchmark_views(tmp_path: Path):
    candidates = _fixture(tmp_path)
    output = tmp_path / "out"
    manifest = build_same_task_pilot(
        candidates,
        output,
        options=BuildOptions(
            allow_synthetic=True,
            allow_intentional_overlap=True,
        ),
    )

    assert manifest["counts"] == {
        "benchmark_items": 1,
        "sft_examples": 1,
        "unique_tasks": 1,
        "synthetic_examples": 1,
        "human_validated_examples": 0,
        "skipped_synthetic_suites": 0,
    }
    assert manifest["formal_benchmark_eligible"] is False
    assert manifest["overlap_policy"]["kind"] == "intentional_exact_task_overlap"

    benchmark = json.loads((output / "benchmark.jsonl").read_text())
    sft = json.loads((output / "sft_qa.jsonl").read_text())
    messages = json.loads((output / "sft_messages.jsonl").read_text())
    provenance = json.loads((output / "provenance.jsonl").read_text())
    assert benchmark["query"] == sft["question"]
    assert "answer" not in benchmark
    assert sft["answer"].startswith("Option A is preferable")
    assert messages == {"messages": sft["messages"]}
    assert provenance["score_summary"]["full_pass"] == 1
    assert provenance["source_validation"]["synthetic_only"] is True


def test_same_task_export_discovers_new_plural_oracle_suite_layout(tmp_path: Path):
    candidates = _fixture(tmp_path, layout="new")
    output = tmp_path / "out"
    manifest = build_same_task_pilot(
        candidates,
        output,
        options=BuildOptions(
            allow_synthetic=True,
            allow_intentional_overlap=True,
        ),
    )
    assert manifest["counts"]["sft_examples"] == 1
    provenance = json.loads((output / "provenance.jsonl").read_text())
    assert provenance["source_artifacts"]["suite"]["path"] == (
        "case-001/oracle_suites/synthetic/suite.json"
    )


def test_same_task_export_rejects_tampered_oracle_report(tmp_path: Path):
    candidates = _fixture(tmp_path)
    report = candidates / "case-001" / "oracle_suite" / "report.md"
    report.write_text("tampered", encoding="utf-8")
    with pytest.raises(DatasetBuildError, match="oracle_report hash mismatch"):
        build_same_task_pilot(
            candidates,
            tmp_path / "out",
            options=BuildOptions(
                allow_synthetic=True,
                allow_intentional_overlap=True,
            ),
        )


def test_same_task_export_rejects_non_passing_oracle(tmp_path: Path):
    candidates = _fixture(tmp_path)
    validation_path = candidates / "case-001" / "oracle_suite" / "validation.json"
    validation = json.loads(validation_path.read_text())
    validation["oracle_results"][0]["score"]["full_pass"] = 0
    validation_path.write_text(json.dumps(validation, sort_keys=True), encoding="utf-8")
    with pytest.raises(DatasetBuildError, match="not a clean FullPass target"):
        build_same_task_pilot(
            candidates,
            tmp_path / "out",
            options=BuildOptions(
                allow_synthetic=True,
                allow_intentional_overlap=True,
            ),
        )
