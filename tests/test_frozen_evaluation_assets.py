from __future__ import annotations

import hashlib
import json

import pytest

from src.scoring.frozen_claim_ledger import (
    ClaimLedgerValidationError,
    load_frozen_claim_ledger,
    seal_claim_ledger,
)
from src.scoring.frozen_fact_packets import (
    FactPacketValidationError,
    load_frozen_fact_packets,
    seal_fact_packet_bundle,
)
from src.scoring.four_axis_pipeline import run_four_axis_pipeline
from src.scoring.task_evaluation_contract import (
    ContractValidationError,
    canonical_json_sha256,
    load_task_evaluation_contract,
    seal_compiled_task_contract,
)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _compiled_task(tmp_path):
    task = {"task_id": "task-1", "prompt": "Compare A and B."}
    twm = {
        "task_id": "task-1",
        "assertions": [
            {
                "assertion_id": "A1",
                "statement": "A lists ten hours.",
            }
        ],
    }
    rts = {"task_id": "task-1", "facets": []}
    compiled = tmp_path / "compiled"
    _write_json(compiled / "facets.json", [{"facet_id": "f1", "label": "F"}])
    _write_jsonl(
        compiled / "atomic_facts.jsonl",
        [
            {
                "unit_id": "atomic:A1",
                "facet_id": "f1",
                "unit_type": "atomic",
                "statement": "A lists ten hours.",
            }
        ],
    )
    _write_jsonl(
        compiled / "research_units.jsonl",
        [
            {
                "unit_id": "research:R1",
                "facet_id": "f1",
                "unit_type": "comparison",
                "statement": "Compare the two products.",
            }
        ],
    )
    _write_jsonl(
        compiled / "rubric_items.jsonl",
        [
            {
                "rubric_id": "rubric:query:001",
                "requirement": "Compare A and B.",
            }
        ],
    )
    _write_json(
        compiled / "tec-manifest.json",
        {
            "schema": "dra_task_evidence_census_transition_v2",
            "task_id": "task-1",
            "query": task["prompt"],
            "compiled_without_report": True,
            "compiler_model": "fixed-compiler",
            "manual_semantic_decisions": 0,
            "source_hashes": {
                "task": canonical_json_sha256(task),
                "task_world_model": canonical_json_sha256(twm),
                "research_test_suite": canonical_json_sha256(rts),
            },
            "formal_eligible": False,
            "formal_eligibility_notes": ["transition asset"],
        },
    )
    return task, twm, rts, compiled


def test_task_contract_separates_answerability_from_completeness(tmp_path):
    task, twm, rts, compiled = _compiled_task(tmp_path)
    target = seal_compiled_task_contract(
        compiled_dir=compiled,
        output_dir=tmp_path / "contract",
        task=task,
        task_world_model=twm,
        research_test_suite=rts,
        contract_semantics="research_obligations_v1",
        frozen_before_report_input=True,
    )
    assert target["atomic_units"] == []
    assert len(target["answerability_facts"]) == 1
    assert target["answerability_facts"][0]["scored_in_completeness"] is False
    assert len(target["research_units"]) == 1
    assert target["manifest"]["contract_sha256"]

    legacy = seal_compiled_task_contract(
        compiled_dir=compiled,
        output_dir=tmp_path / "legacy-contract",
        task=task,
        task_world_model=twm,
        research_test_suite=rts,
        contract_semantics="transition_legacy_exact",
        frozen_before_report_input=False,
    )
    assert len(legacy["atomic_units"]) == 1
    assert legacy["manifest"]["contract_semantics"] == "transition_legacy_exact"


def test_task_contract_rejects_byte_tampering_and_wrong_query(tmp_path):
    task, twm, rts, compiled = _compiled_task(tmp_path)
    contract_dir = tmp_path / "contract"
    seal_compiled_task_contract(
        compiled_dir=compiled,
        output_dir=contract_dir,
        task=task,
        task_world_model=twm,
        research_test_suite=rts,
        contract_semantics="research_obligations_v1",
        frozen_before_report_input=True,
    )
    with pytest.raises(ContractValidationError, match="query"):
        load_task_evaluation_contract(
            contract_dir,
            expected_task={**task, "prompt": "Choose only A."},
            expected_task_world_model=twm,
            expected_research_test_suite=rts,
        )

    with (contract_dir / "research_units.jsonl").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write("{}\n")
    with pytest.raises(ContractValidationError, match="hash mismatch"):
        load_task_evaluation_contract(contract_dir)


def _claim_ledger_source(tmp_path):
    report = "Model A costs $50.\n"
    raw = "Model A costs $50."
    span = {
        "segment_id": "s_0001",
        "start": 0,
        "end": len(raw),
        "raw_text": raw,
        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }
    claims_dir = tmp_path / "claims"
    _write_jsonl(
        claims_dir / "report_claims.jsonl",
        [
            {
                "claim_id": "p_0001",
                "normalized_claim": "Model A costs $50.",
                "claim_kind": "external_atomic",
                "report_span": span,
                "occurrences": [
                    {
                        "report_span": span,
                        "report_context": raw,
                        "citation_ids": [],
                    }
                ],
            }
        ],
    )
    _write_jsonl(claims_dir / "report_segments.jsonl", [span])
    _write_json(
        claims_dir / "claim_extraction_summary.json",
        {
            "schema": "dra_report_claim_extraction_v1",
            "report_sha256": hashlib.sha256(report.encode("utf-8")).hexdigest(),
            "frozen_claim_count": 1,
            "proposal_model": "extractor-a",
            "nli_model": "extractor-b",
            "structural_model": "extractor-c",
            "dedup_model": "extractor-c",
            "manual_claim_decisions": 0,
        },
    )
    return report, claims_dir


def test_claim_ledger_binds_exact_report_and_detects_tampering(tmp_path):
    report, claims_dir = _claim_ledger_source(tmp_path)
    manifest = seal_claim_ledger(
        claims_dir,
        report,
        intended_for_cross_judge_reuse=True,
    )
    loaded = load_frozen_claim_ledger(claims_dir, report)
    assert len(loaded["claims"]) == 1
    assert loaded["manifest"]["claim_ledger_sha256"] == manifest[
        "claim_ledger_sha256"
    ]

    with pytest.raises(ClaimLedgerValidationError, match="different report"):
        load_frozen_claim_ledger(claims_dir, "Model A costs $60.\n")

    with (claims_dir / "report_claims.jsonl").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write("{}\n")
    with pytest.raises(ClaimLedgerValidationError, match="hash mismatch"):
        load_frozen_claim_ledger(claims_dir, report)


def test_fact_packet_bundle_is_bound_to_claim_ledger(tmp_path):
    report, claims_dir = _claim_ledger_source(tmp_path)
    claim_manifest = seal_claim_ledger(
        claims_dir,
        report,
        intended_for_cross_judge_reuse=True,
    )
    claims = load_frozen_claim_ledger(claims_dir, report)["claims"]
    packet_dir = tmp_path / "packets"
    _write_json(
        packet_dir / "p_0001.json",
        {
            "claim_id": "p_0001",
            "claim": "Model A costs $50.",
            "claim_kind": "external_atomic",
            "attribution": None,
            "qualifiers": {},
            "absence_certificate": None,
            "resolution_audit": {},
            "evidence_spans": [
                {
                    "span_id": "world:1",
                    "url": "http://localhost:7770/model-a.html",
                    "source_role": "retailer",
                    "text": "Model A costs $50.",
                }
            ],
        },
    )
    bundle = seal_fact_packet_bundle(
        packet_dir,
        claims,
        claim_ledger_sha256=claim_manifest["claim_ledger_sha256"],
    )
    loaded = load_frozen_fact_packets(
        packet_dir,
        claims,
        expected_claim_ledger_sha256=claim_manifest["claim_ledger_sha256"],
    )
    assert loaded["packets"][0]["claim_id"] == "p_0001"
    assert loaded["manifest"]["fact_packet_bundle_sha256"] == bundle[
        "fact_packet_bundle_sha256"
    ]
    with pytest.raises(
        FactPacketValidationError,
        match="different Claim Ledger",
    ):
        load_frozen_fact_packets(
            packet_dir,
            claims,
            expected_claim_ledger_sha256="0" * 64,
        )


def test_pipeline_reuses_frozen_contract_and_claims_without_recompiling(
    tmp_path,
    monkeypatch,
):
    task, twm, rts, compiled = _compiled_task(tmp_path)
    contract_dir = tmp_path / "contract"
    seal_compiled_task_contract(
        compiled_dir=compiled,
        output_dir=contract_dir,
        task=task,
        task_world_model=twm,
        research_test_suite=rts,
        contract_semantics="research_obligations_v1",
        frozen_before_report_input=True,
    )
    report, claims_dir = _claim_ledger_source(tmp_path)
    seal_claim_ledger(
        claims_dir,
        report,
        intended_for_cross_judge_reuse=True,
    )

    inputs = tmp_path / "inputs"
    _write_json(inputs / "task.json", task)
    (inputs / "report.md").write_text(report, encoding="utf-8")
    _write_json(inputs / "trace.json", {"tool_calls": []})
    _write_json(inputs / "citation-map.json", [])
    _write_json(inputs / "twm.json", twm)
    _write_json(inputs / "rts.json", rts)
    _write_json(inputs / "graph" / "manifest.json", {"task_id": "task-1"})
    _write_json(inputs / "graph" / "corpus_registry.json", {"entries": []})
    _write_json(
        inputs / "url-registry.json",
        {"version": 1, "hosts": {}, "products": [], "wiki": []},
    )

    def must_not_compile(*args, **kwargs):
        raise AssertionError("task compiler was called")

    def must_not_extract(*args, **kwargs):
        raise AssertionError("claim extractor was called")

    monkeypatch.setattr(
        "src.scoring.four_axis_pipeline.compile_task_manifest",
        must_not_compile,
    )
    monkeypatch.setattr(
        "src.scoring.four_axis_pipeline.extract_report_claims",
        must_not_extract,
    )
    monkeypatch.setattr(
        "src.scoring.four_axis_pipeline.judge_facts",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.scoring.four_axis_pipeline.judge_citation_bindings",
        lambda *args, **kwargs: ([], []),
    )
    monkeypatch.setattr(
        "src.scoring.four_axis_pipeline.judge_atomic_coverage",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "src.scoring.four_axis_pipeline.judge_research_coverage",
        lambda *args, **kwargs: ([], []),
    )
    monkeypatch.setattr(
        "src.scoring.four_axis_pipeline.judge_rubric",
        lambda *args, **kwargs: [],
    )

    result = run_four_axis_pipeline(
        task_path=inputs / "task.json",
        report_path=inputs / "report.md",
        trace_path=inputs / "trace.json",
        citation_map_path=inputs / "citation-map.json",
        task_world_model_path=inputs / "twm.json",
        research_test_suite_path=inputs / "rts.json",
        graph_dir=inputs / "graph",
        url_registry_path=inputs / "url-registry.json",
        output_dir=tmp_path / "score",
        task_contract_dir=contract_dir,
        frozen_claims_dir=claims_dir,
    )
    assert result["instrument_mode"] == {
        "task_contract": "frozen",
        "claim_ledger": "frozen",
        "fact_packets": "runtime_retrieved",
    }
    assert result["task_contract_sha256"]
    assert result["claim_ledger_sha256"]
    input_manifest = json.loads(
        (tmp_path / "score" / "input-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert input_manifest["models"]["task_compiler"] is None
    assert input_manifest["models"]["claim_proposal"] is None
