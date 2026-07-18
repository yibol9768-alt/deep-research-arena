from __future__ import annotations

import hashlib

import pytest

from src.eval.protocol_v3 import (
    IncomparableProtocolError,
    ProtocolV3Error,
    assert_comparable,
    protocol_stamp,
    validate_protocol,
)


def _stamp(snapshot="corpus-v3-test", tasks=("t2", "t1")):
    return protocol_stamp(
        corpus_snapshot=snapshot,
        task_ids=tasks,
        case_hashes={t: hashlib.sha256(t.encode()).hexdigest() for t in tasks},
        public_task_hashes={
            t: hashlib.sha256(f"public:{t}".encode()).hexdigest() for t in tasks
        },
        evidence_graph_hash="f" * 64,
        corpus_registry_hash="e" * 64,
    )


def test_v3_stamp_is_order_independent_and_contains_no_quality_weights():
    a = _stamp(tasks=("t1", "t2"))
    b = _stamp(tasks=("t2", "t1", "t1"))
    assert a == b
    assert a["legacy_quality_used"] is False
    assert "weights" not in a and "quality" not in a
    assert a["headline_metrics"] == [
        "verified_research_completion_v1",
        "task_solve_rate_v1",
    ]
    assert a["diagnostic_metric"] == "verified_f1_v1"
    assert "headline_metric" not in a and "partial_metric" not in a
    validate_protocol(a, formal=True)


def test_v2_formula_cannot_masquerade_as_v3():
    with pytest.raises(ProtocolV3Error, match="invalid DRA v3 protocol"):
        validate_protocol({
            "formula_version": "tv2.5-linear-provenance-gate",
            "quality": 0.8,
        })


def test_obsolete_single_headline_stamp_is_rejected():
    stamp = _stamp()
    stamp["headline_metric"] = "task_solve_rate_v1"
    with pytest.raises(ProtocolV3Error, match="obsolete singular"):
        validate_protocol(stamp, formal=True)


def test_cross_snapshot_and_task_set_comparisons_are_refused():
    with pytest.raises(IncomparableProtocolError, match="not comparable"):
        assert_comparable(_stamp(), _stamp(snapshot="other"), formal=True)
    with pytest.raises(IncomparableProtocolError, match="task_set_hash"):
        assert_comparable(_stamp(), _stamp(tasks=("t1",)), formal=True)


def test_formal_stamp_requires_case_and_graph_hashes():
    draft = protocol_stamp(corpus_snapshot="snap", task_ids=["t1"])
    validate_protocol(draft, formal=False)
    with pytest.raises(ProtocolV3Error, match="case_set_hash"):
        validate_protocol(draft, formal=True)


def test_formal_hashes_and_case_set_membership_are_fail_closed():
    with pytest.raises(ProtocolV3Error, match="exactly match"):
        protocol_stamp(
            corpus_snapshot="snap",
            task_ids=["t1", "t2"],
            case_hashes={"t1": "a" * 64},
            public_task_hashes={"t1": "d" * 64, "t2": "e" * 64},
            evidence_graph_hash="b" * 64,
            corpus_registry_hash="c" * 64,
        )
    with pytest.raises(ProtocolV3Error, match="SHA-256"):
        protocol_stamp(
            corpus_snapshot="snap",
            task_ids=["t1"],
            case_hashes={"t1": "not-a-digest"},
            public_task_hashes={"t1": "d" * 64},
            evidence_graph_hash="b" * 64,
            corpus_registry_hash="c" * 64,
        )
    with pytest.raises(ProtocolV3Error, match="public_task_hashes keys"):
        protocol_stamp(
            corpus_snapshot="snap",
            task_ids=["t1", "t2"],
            case_hashes={"t1": "a" * 64, "t2": "b" * 64},
            public_task_hashes={"t1": "d" * 64},
            evidence_graph_hash="b" * 64,
            corpus_registry_hash="c" * 64,
        )
