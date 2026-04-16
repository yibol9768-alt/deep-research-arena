"""Tests for FactKGVerifier — v3 knowledge-graph fact checker.

These tests run against the shipped golden triples at data/golden/. They
cover both the recall-only fast path (no DB / no LLM needed) and the wiring
that would activate precision when credentials are present.

DB-hitting tests are guarded by `has_db_access()` so CI stays green when
the westd tunnel is down.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.verifiers.fact_kg_verifier import FactKGVerifier
from src.verifiers.fact_kg_verifier import (
    _strip_group_prefix,
    _subject_in,
    _number_in,
    _load_golden,
)


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "data" / "golden"
ORACLE_DIR = ROOT / "data" / "results"


# -------------------- unit tests --------------------


def test_strip_group_prefix():
    assert _strip_group_prefix("theme:Tech regulation") == "Tech regulation"
    assert _strip_group_prefix("tea-type:green") == "green"
    assert _strip_group_prefix("forum:news") == "news"
    assert _strip_group_prefix("author:Alice/forum:tech") == "Alice tech"
    assert _strip_group_prefix("PlainSubject") == "PlainSubject"


def test_subject_in_fuzzy():
    hay = "green tea category offers 5 products"
    assert _subject_in("tea-type:green", hay)
    assert not _subject_in("tea-type:oolong", hay)


def test_number_in_word_boundary():
    # 4.3 must NOT match within 14.35
    assert _number_in("4.3", "rating: 4.3 stars")
    assert not _number_in("4.3", "total 14.35 dollars")
    # trailing spaces / punctuation OK
    assert _number_in("12", "there are 12 reviews.")


def test_load_golden_known_task():
    triples = _load_golden("dr_shop_v3_0001")
    assert isinstance(triples, list)
    assert len(triples) == 18
    preds = {t["predicate"] for t in triples}
    assert "price" in preds


def test_load_golden_missing_task():
    assert _load_golden("dr_nonexistent") == []


# -------------------- recall acceptance --------------------

# Every task_id we expect to verify. recall_min is the target (set to the
# measured value during initial oracle run; tightens future regressions).
RECALL_TASKS = [
    ("dr_shop_v3_0001", "shopping", 0.95),
    ("dr_shop_v3_0002", "shopping", 0.95),
    ("dr_shop_v3_0003", "shopping", 0.80),
    ("dr_shop_v3_0004", "shopping", 0.95),
    ("dr_red_v3_0001",  "reddit",   0.80),
    ("dr_red_v3_0002",  "reddit",   0.80),
    ("dr_red_v3_0003",  "reddit",   0.80),
    ("dr_red_v3_0004",  "reddit",   0.80),
]


@pytest.mark.parametrize("task_id,site,recall_min", RECALL_TASKS)
def test_recall_against_oracle(task_id: str, site: str, recall_min: float):
    """Oracle reports were generated from the same triples → recall must be high."""
    oracle_md = ORACLE_DIR / f"oracle_v3_{task_id}.md"
    if not oracle_md.exists():
        pytest.skip(f"oracle file {oracle_md} missing")
    answer = oracle_md.read_text(encoding="utf-8")

    verifier = FactKGVerifier(do_precision=False)
    r = verifier.verify(
        task_config={"task_id": task_id, "sites": [site]},
        answer=answer,
        page=None,
    )
    assert r.passed, f"{task_id}: verifier marked failed — details={r.details}"
    assert r.details["recall"] >= recall_min, (
        f"{task_id}: recall {r.details['recall']:.3f} below threshold {recall_min}"
    )


def test_bogus_answer_scores_low():
    """Completely wrong answers must score well under 0.3 recall."""
    bogus = (
        "# Report\nThe Sony XM5 costs $9999. Bose has 1.1 stars. "
        "Fake post got 42 score in /f/madeup."
    )
    v = FactKGVerifier(do_precision=False)
    r = v.verify(
        task_config={"task_id": "dr_shop_v3_0001", "sites": ["shopping"]},
        answer=bogus,
        page=None,
    )
    assert r.details["recall"] < 0.3, f"bogus recall {r.details['recall']} too high"


def test_empty_golden_returns_fail():
    v = FactKGVerifier(do_precision=False)
    r = v.verify(
        task_config={"task_id": "dr_does_not_exist", "sites": ["shopping"]},
        answer="whatever",
        page=None,
    )
    assert not r.passed
    assert "no golden" in r.details["reason"]


# -------------------- DB integration (skipped if no tunnel) --------------------


def _has_db_access() -> bool:
    """Skip tests that need the westd tunnel if DBs are unreachable."""
    try:
        from src.golden.db_connect import probe_connectivity
        from src.golden.db_connect import DBRunner
        DBRunner._ensure_runner()
        status = probe_connectivity()
        return all(status.values())
    except Exception:
        return False


@pytest.mark.skipif(not _has_db_access(), reason="DBs not reachable — skip live integration")
def test_triple_store_roundtrip_known_fact():
    from src.golden.db_verifier import get_store
    store = get_store("shopping")
    # Harphonic E7 has price 34.99 in the seed.
    triples = json.loads((GOLDEN_DIR / "dr_shop_v3_0001.json").read_text())
    harphonic = next(t for t in triples if t["predicate"] == "price")
    r = store.verify(harphonic["subject"], "price", harphonic["object"])
    assert r.outcome is True, f"DB said {r.db_value}, golden {harphonic['object']!r}, reason={r.reason}"
