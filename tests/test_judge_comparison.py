from __future__ import annotations

import json

from src.scoring.calibration_queue import build_calibration_queue
from src.scoring.judge_comparison import cohen_kappa, compare_judge_runs


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _run(tmp_path, name, *, fact_labels, contract_hash="contract"):
    run = tmp_path / name
    source_dir = tmp_path / "shared-inputs"
    _write_json(source_dir / "task.json", {"task_id": "task-1", "prompt": "Q"})
    (source_dir / "report.md").write_text(
        "A controlled report.\n",
        encoding="utf-8",
    )
    frozen = {
        "task_contract": {"contract_sha256": contract_hash},
        "claim_ledger": {"claim_ledger_sha256": "claims"},
        "fact_packets": {"fact_packet_bundle_sha256": "packets"},
    }
    inputs = {
        key: {"sha256": f"hash-{key}"}
        for key in (
            "task",
            "report",
            "trace",
            "citation_map",
            "task_world_model",
            "research_test_suite",
            "graph_manifest",
            "url_registry",
        )
    }
    inputs["task"]["path"] = str((source_dir / "task.json").resolve())
    inputs["report"]["path"] = str((source_dir / "report.md").resolve())
    _write_json(
        run / "input-manifest.json",
        {
            "scoring_protocol": {"protocol_sha256": "protocol"},
            "frozen_artifacts": frozen,
            "inputs": inputs,
        },
    )
    _write_json(
        run / "score.json",
        {
            "models": {"fact": name},
            "task_contract_sha256": contract_hash,
            "claim_ledger_sha256": "claims",
            "fact_packet_bundle_sha256": "packets",
            "truth": 0.5,
            "fact": {"score": 0.5},
            "evidence": {"score": 1.0},
            "completeness": {"score": 0.5},
            "rubric": {"score": 1.0},
        },
    )
    _write_jsonl(
        run / "fact_verdicts.jsonl",
        [
            {
                "claim_id": f"p{index}",
                "verdict": label,
                "normalized_claim": f"claim {index}",
            }
            for index, label in enumerate(fact_labels, 1)
        ],
    )
    for index, _label in enumerate(fact_labels, 1):
        _write_json(
            run / "fact_packets" / f"p{index}.json",
            {
                "claim_id": f"p{index}",
                "claim": f"claim {index}",
                "claim_kind": "external_atomic",
                "evidence_spans": [],
            },
        )
    _write_jsonl(
        run / "citation_bindings.jsonl",
        [
            {
                "claim_id": "p1",
                "occurrence_index": 0,
                "citation_id": "c1",
                "passed": True,
            }
        ],
    )
    _write_jsonl(
        run / "completeness_units.jsonl",
        [{"unit_id": "u1", "content_covered": True}],
    )
    _write_jsonl(
        run / "rubric_verdicts.jsonl",
        [{"rubric_id": "r1", "verdict": "fulfilled"}],
    )
    return run


def test_cohen_kappa_handles_perfect_and_mixed_agreement():
    assert cohen_kappa(["a", "b"], ["a", "b"]) == 1.0
    assert cohen_kappa([], []) is None
    assert cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0


def test_controlled_judge_comparison_reports_item_disagreements(tmp_path):
    run_a = _run(tmp_path, "a", fact_labels=["true", "false"])
    run_b = _run(tmp_path, "b", fact_labels=["true", "true"])
    compared = compare_judge_runs(run_a, run_b)
    assert compared["controlled_comparison"]
    assert compared["axes"]["fact"]["same_item_set"]
    assert compared["axes"]["fact"]["raw_agreement"] == 0.5
    assert compared["axes"]["fact"]["disagreement_count"] == 1
    assert compared["axes"]["fact"]["disagreement_examples"][0][
        "normalized_claim"
    ] == "claim 2"


def test_comparison_fails_closed_when_contract_hash_differs(tmp_path):
    run_a = _run(tmp_path, "a", fact_labels=["true"])
    run_b = _run(
        tmp_path,
        "b",
        fact_labels=["true"],
        contract_hash="different-contract",
    )
    compared = compare_judge_runs(run_a, run_b)
    assert not compared["controlled_comparison"]
    assert (
        "task_contract_sha256"
        in compared["control_failures"]["mismatched_frozen_hashes"]
    )


def test_calibration_queue_blinds_judge_labels_and_keeps_disagreements(
    tmp_path,
):
    run_a = _run(tmp_path, "a", fact_labels=["true", "false"])
    run_b = _run(tmp_path, "b", fact_labels=["true", "true"])
    output = tmp_path / "queue"
    manifest = build_calibration_queue(
        run_a,
        run_b,
        output,
        agreement_sample_per_axis=1,
        seed=7,
    )
    assert manifest["counts"]["fact"]["judge_disagreements"] == 1
    blind_text = (output / "annotation-items.blind.jsonl").read_text(
        encoding="utf-8"
    )
    assert "judge_a_label" not in blind_text
    assert '"label": null' in blind_text
    private = [
        json.loads(line)
        for line in (output / "judge-labels.private.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    fact_disagreements = [
        row
        for row in private
        if row["axis"] == "fact"
        and row["selection_reason"] == "judge_disagreement"
    ]
    assert fact_disagreements == [
        {
            "axis": "fact",
            "item_id": fact_disagreements[0]["item_id"],
            "item_key": "p2",
            "judge_a_label": "false",
            "judge_b_label": "true",
            "selection_reason": "judge_disagreement",
        }
    ]
