"""Offline tests for the decidable-verdict plumbing.

Covers the same honesty contract the contradiction pillar uses: machine-mined
candidates never become gold on their own, and only human/strong-model
adjudicated *.gold.json entries reach an answer key's decidable_verdicts.

  (a) load_adjudicated_verdicts returns {} on a missing / empty dir and
      attaches a synthetic gold fixture keyed by task_id -> {claim_id: verdict},
      enforcing the adjudicator + valid-verdict contract;
  (b) the miner emits the required adjudication-template fields (all null),
      derives DB verdicts, leaves wiki claims undecided, and writes no gold.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.build_answer_keys_v2 as bak  # noqa: E402
import scripts.build_verdict_candidates as bvc  # noqa: E402


def _gold(entries):
    return {"gold_verdicts": entries}


# ---------------------------------------------------------------- loader ----

def test_loader_missing_dir_returns_empty(tmp_path):
    assert bak.load_adjudicated_verdicts(tmp_path / "does_not_exist") == {}


def test_loader_empty_dir_returns_empty(tmp_path):
    assert bak.load_adjudicated_verdicts(tmp_path) == {}


def test_loader_ignores_non_gold_files(tmp_path):
    (tmp_path / "candidates.json").write_text(json.dumps(_gold([
        {"id": "v1", "task_id": "t", "adjudicated_verdict": "SUPPORTED",
         "adjudicator": "h"}])))
    assert bak.load_adjudicated_verdicts(tmp_path) == {}


def test_loader_attaches_synthetic_gold(tmp_path):
    (tmp_path / "batch.gold.json").write_text(json.dumps(_gold([
        {"id": "verdict-dr_cross_deep_0002-wiki-01",
         "task_id": "dr_cross_deep_0002",
         "adjudicated_verdict": "REFUTED", "adjudicator": "human-x",
         "rationale": "Caffeine article: dark roast is not higher"},
        {"id": "verdict-dr_cross_deep_0002-price-01",
         "task_id": "dr_cross_deep_0002",
         "adjudicated_verdict": "SUPPORTED", "adjudicator": "human-x",
         "rationale": "DB prices"},
    ])))
    assert bak.load_adjudicated_verdicts(tmp_path) == {
        "dr_cross_deep_0002": {
            "verdict-dr_cross_deep_0002-wiki-01": "REFUTED",
            "verdict-dr_cross_deep_0002-price-01": "SUPPORTED",
        }
    }


def test_loader_honesty_contract_skips_incomplete(tmp_path):
    (tmp_path / "b.gold.json").write_text(json.dumps(_gold([
        {"id": "no_adj", "task_id": "t", "adjudicated_verdict": "SUPPORTED",
         "adjudicator": ""},                       # unsigned -> skip
        {"id": "empty", "task_id": "t", "adjudicated_verdict": "",
         "adjudicator": "h"},                       # no verdict -> skip
        {"id": "bad", "task_id": "t", "adjudicated_verdict": "MAYBE",
         "adjudicator": "h"},                       # invalid value -> skip
        {"id": "ok", "task_id": "t", "adjudicated_verdict": "UNDETERMINED",
         "adjudicator": "h"},                       # valid -> keep
    ])))
    assert bak.load_adjudicated_verdicts(tmp_path) == {"t": {"ok": "UNDETERMINED"}}


def test_loader_merges_multiple_files_and_tasks(tmp_path):
    (tmp_path / "one.gold.json").write_text(json.dumps(_gold([
        {"id": "a", "task_id": "t1", "adjudicated_verdict": "SUPPORTED",
         "adjudicator": "h"}])))
    (tmp_path / "two.gold.json").write_text(json.dumps(_gold([
        {"id": "b", "task_id": "t2", "adjudicated_verdict": "REFUTED",
         "adjudicator": "h"}])))
    assert bak.load_adjudicated_verdicts(tmp_path) == {
        "t1": {"a": "SUPPORTED"}, "t2": {"b": "REFUTED"}}


# ----------------------------------------------------------------- miner ----

def test_adjudication_template_fields_all_null():
    doc = {"builder": "b", "candidates": [
        {"id": "x", "task_id": "t", "cluster": "c", "kind": "wiki_claim",
         "claim": "cc", "proposed_verdict": None, "evidence": {"a": 1}}]}
    tpl = bvc.adjudication_template(doc)
    entry = tpl["entries"][0]
    assert set(entry) == {"id", "task_id", "claim", "proposed_verdict",
                          "evidence", "adjudicated_verdict", "rationale",
                          "adjudicator"}
    assert entry["adjudicated_verdict"] is None
    assert entry["rationale"] is None
    assert entry["adjudicator"] is None
    assert tpl["allowed_verdicts"] == bvc.ALLOWED_VERDICTS


def test_is_claim_shaped():
    assert bvc.is_claim_shaped({"tri_source": {"archetype": "claim-check"}})
    assert bvc.is_claim_shaped({"tri_source": {"archetype": "community-vs-ratings"}})
    assert bvc.is_claim_shaped({"intent_type": "Debunking"})
    assert bvc.is_claim_shaped(
        {"intent": "Is it genuinely better, and do the ads really hold up?"})
    assert not bvc.is_claim_shaped(
        {"tri_source": {"archetype": "buying-dilemma"},
         "intent": "I have $800 for my first camera setup."})


def test_extract_wiki_claims_keeps_folklore_drops_instructions():
    intent = ("I've heard cheap chargers melt their ports over time. "
              "Walk me through what you'd actually buy in the end.")
    claims = bvc.extract_wiki_claims(intent)
    assert any("melt their ports" in c for c in claims)
    assert all("walk me" not in c.lower() for c in claims)


def test_db_candidates_derive_verdict_from_db(tmp_path, monkeypatch):
    tid = "dr_cross_deep_9999"
    ak = {"vital_nuggets": [
        {"predicate": "buyer_sentiment", "source_url": "u/hi"},
        {"predicate": "buyer_sentiment", "source_url": "u/lo"},
        {"predicate": "concept_coverage", "source_url": "u/wiki"}]}
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / f"{tid}.json").write_text(json.dumps(ak))
    monkeypatch.setattr(bvc, "KEYS_DIR", keys)
    db_doc = {"relevant_set": [
        {"name": "Hi Headphones", "url": "u/hi",
         "facts": {"price": "50.000000", "rating": "4.0", "review_count": "10"}},
        {"name": "Lo Earbuds", "url": "u/lo",
         "facts": {"price": "20.000000", "rating": "4.5", "review_count": "8"}}]}
    cands = bvc._db_candidates(tid, db_doc)
    by_kind = {c["kind"]: c for c in cands}
    assert set(by_kind) == {"price_comparison", "numeric_spec"}

    pc = by_kind["price_comparison"]
    assert pc["proposed_verdict"] == "SUPPORTED"
    assert pc["evidence"]["entity_a"]["price"] == 50.0
    assert pc["evidence"]["entity_b"]["price"] == 20.0

    ns = by_kind["numeric_spec"]
    assert ns["proposed_verdict"] == "SUPPORTED"
    assert ns["evidence"]["db_value"] == 4.5  # highest-rated topical entity


def test_miner_writes_candidates_and_template_no_gold(tmp_path):
    out = tmp_path / "verdicts"
    res = subprocess.run(
        [sys.executable, "scripts/build_verdict_candidates.py",
         "--out-dir", str(out)],
        cwd=ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert (out / "candidates.json").exists()
    assert (out / "verdicts.adjudication.json").exists()
    assert not list(out.glob("*.gold.json"))  # honesty contract: never gold

    doc = json.loads((out / "candidates.json").read_text())
    assert doc["auto_gold"] is False
    assert doc["candidates"], "expected at least one candidate"
    for c in doc["candidates"]:
        if c["kind"] == "wiki_claim":
            assert c["proposed_verdict"] is None
        else:
            assert c["proposed_verdict"] in bvc.ALLOWED_VERDICTS
