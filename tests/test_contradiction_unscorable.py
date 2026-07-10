"""P3: an empty contradiction gold set must be UNSCORABLE, never silently 0/1.

These tests pin the guarantee that a report cannot be assigned a contradiction
precision/recall against a key that was never adjudicated. A number from an
empty gold set is a claim-evidence break (see EmptyContradictionGoldError).
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

from src.eval.answer_key import AnswerKey, EmptyContradictionGoldError


def _key(gold):
    return AnswerKey(task_id="t", gold_contradictions=gold)


def test_empty_gold_is_not_scorable():
    assert _key([]).contradiction_scorable is False


def test_nonempty_gold_is_scorable():
    ak = _key([{"candidate_id": "c1", "summary": "x"}])
    assert ak.contradiction_scorable is True


def test_empty_gold_metrics_raise():
    ak = _key([])
    with pytest.raises(EmptyContradictionGoldError):
        ak.contradiction_metrics(found=[])


def test_empty_gold_metrics_raise_even_when_report_claims_contradictions():
    # A report inventing contradictions against an unadjudicated key must not
    # yield precision 0.0/1.0; it must raise, because there is no gold to judge.
    ak = _key([])
    with pytest.raises(EmptyContradictionGoldError):
        ak.contradiction_metrics(found=[{"candidate_id": "made_up"}])


def test_scorable_metrics_compute_precision_recall():
    gold = [{"candidate_id": "a"}, {"candidate_id": "b"}]
    ak = _key(gold)
    m = ak.contradiction_metrics(found=[{"candidate_id": "a"}, {"candidate_id": "z"}])
    assert m["n_gold"] == 2
    assert m["n_found"] == 2
    assert m["true_positive"] == 1
    assert m["precision"] == 0.5
    assert m["recall"] == 0.5


def test_metadata_flag_matches_gold_on_disk():
    # The backfilled metadata.contradiction_scorable must agree with the live
    # property for every real answer key, so the file-level flag is trustworthy.
    paths = sorted(glob.glob("data/golden/answer_keys/*.json"))
    assert paths, "no answer keys found"
    for p in paths:
        d = json.loads(Path(p).read_text())
        ak = AnswerKey.load(p)
        flag = d.get("metadata", {}).get("contradiction_scorable")
        assert flag is not None, f"{p} missing metadata.contradiction_scorable"
        assert flag == ak.contradiction_scorable, p
