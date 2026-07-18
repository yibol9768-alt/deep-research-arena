from __future__ import annotations

import hashlib

import pytest

from src.eval.protocol_v3 import (
    ACQUISITION_DIAGNOSTICS_METRIC,
    FULL_PASS_RATE_METRIC,
    IncomparableProtocolError,
    LEGACY_SCORING_SEMANTICS,
    PARTIAL_COMPLETION_RATE_METRIC,
    ProtocolV3Error,
    ROUTE_COVERAGE_METRIC,
    SCORING_SEMANTICS,
    assert_comparable,
    proof_steps_protocol_stamp,
    protocol_stamp,
    validate_proof_steps_protocol,
    validate_verified_slots_protocol,
    verified_slots_protocol_stamp,
)


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _formal_kwargs() -> dict:
    tasks = ("t2", "t1")
    return {
        "corpus_snapshot": "proof-snapshot-v1",
        "task_ids": tasks,
        "case_hashes": {task: _hash(f"case:{task}") for task in tasks},
        "public_task_hashes": {
            task: _hash(f"public:{task}") for task in tasks
        },
        "evidence_graph_hash": "f" * 64,
        "corpus_registry_hash": "e" * 64,
    }


def test_default_and_explicit_legacy_entrypoints_remain_identical() -> None:
    default = protocol_stamp(**_formal_kwargs())
    explicit = verified_slots_protocol_stamp(**_formal_kwargs())

    assert default == explicit
    assert default["scoring_semantics"] == LEGACY_SCORING_SEMANTICS
    validate_verified_slots_protocol(default, formal=True)


def test_proof_step_stamp_has_exact_new_metric_identity() -> None:
    stamp = proof_steps_protocol_stamp(**_formal_kwargs())

    assert stamp["scoring_semantics"] == SCORING_SEMANTICS
    assert stamp["headline_metrics"] == [
        PARTIAL_COMPLETION_RATE_METRIC,
        FULL_PASS_RATE_METRIC,
    ]
    assert stamp["diagnostic_metrics"] == [
        ROUTE_COVERAGE_METRIC,
        ACQUISITION_DIAGNOSTICS_METRIC,
    ]
    assert "diagnostic_metric" not in stamp
    assert "headline_metric" not in stamp
    assert "partial_metric" not in stamp
    validate_proof_steps_protocol(stamp, formal=True)


def test_semantics_specific_validators_reject_the_other_protocol() -> None:
    proof = proof_steps_protocol_stamp(**_formal_kwargs())
    legacy = verified_slots_protocol_stamp(**_formal_kwargs())

    with pytest.raises(ProtocolV3Error, match="expected 'proof_steps_v1'"):
        validate_proof_steps_protocol(legacy, formal=True)
    with pytest.raises(ProtocolV3Error, match="expected 'verified_slots_v1'"):
        validate_verified_slots_protocol(proof, formal=True)
    with pytest.raises(IncomparableProtocolError, match="not comparable"):
        assert_comparable(proof, legacy, formal=True)


def test_proof_protocol_rejects_mixed_legacy_diagnostic_fields() -> None:
    stamp = proof_steps_protocol_stamp(**_formal_kwargs())
    stamp["diagnostic_metric"] = "verified_f1_v1"

    with pytest.raises(ProtocolV3Error, match="forbids"):
        validate_proof_steps_protocol(stamp, formal=True)

