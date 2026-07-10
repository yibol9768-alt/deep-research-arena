from __future__ import annotations

import json

import pytest

from scripts import run_usefulness_jury as jury


def _rec(judge, winner, *, sha_a="a", sha_b="b", backbone="bb"):
    return {
        "protocol": jury.PROTOCOL, "rubric_hash": jury.rubric_hash(),
        "word_budget": jury.DEFAULT_WORD_BUDGET, "backbone": backbone,
        "task": "t1", "a": "a", "b": "b", "order": "ab",
        "judge": judge, "winner": winner, "error": None,
        "report_sha_a": sha_a, "report_sha_b": sha_b,
    }


def test_fit_filters_to_requested_judges():
    rows = [_rec("wanted", "A"), _rec("stray1", "B"), _rec("stray2", "B")]
    fit = jury.fit_from_bank(rows, backbone="bb", judges=["wanted"])
    assert fit["agents"]["a"]["n_wins"] == 1
    assert fit["agents"]["b"]["n_wins"] == 0


def test_bank_key_changes_when_report_content_changes():
    a = _rec("j", "A", sha_a="old")
    b = _rec("j", "A", sha_a="new")
    assert jury.bank_key(a) != jury.bank_key(b)


def test_multi_backbone_panel_requires_explicit_choice():
    result = {
        "by_backbone": {
            "bb1": {"agents": {"a": {"winrate_vs_avg_opponent": 0.9}}},
            "bb2": {"agents": {"a": {"winrate_vs_avg_opponent": 0.1}}},
        }
    }
    with pytest.raises(ValueError, match="multiple backbones"):
        jury.panel_from_fit(result)
    panel = jury.panel_from_fit(result, backbone="bb1")
    prov = panel.pop("_provenance")
    assert panel == {"a": 0.9}
    assert prov["backbone"] == "bb1"


def test_panel_from_fit_keeps_the_fit_provenance_stamps():
    # SPEC_ISSUES §2 (presentation panel zero provenance binding): the panel
    # used to strip the fit's protocol/rubric_hash/word_budget stamps, making
    # --panel the only board input nothing could bind. Red on the old code,
    # which returned bare {agent: float}.
    result = {
        "protocol": "uj_v1",
        "rubric_hash": "abc123",
        "word_budget": 900,
        "generated_at": 1234.5,
        "agents": {"a": {"winrate_vs_avg_opponent": 0.7}},
    }
    panel = jury.panel_from_fit(result)
    prov = panel["_provenance"]
    assert prov["protocol"] == "uj_v1"
    assert prov["rubric_hash"] == "abc123"
    assert prov["word_budget"] == 900
    assert panel["a"] == 0.7


def test_board_load_panel_splits_stamp_and_flags_unstamped(tmp_path):
    import importlib
    btb = importlib.import_module("scripts.build_truth_board")

    stamped = tmp_path / "stamped.json"
    stamped.write_text(json.dumps({
        "a": 0.7, "_provenance": {"protocol": "uj_v1", "rubric_hash": "abc"},
    }))
    panel, prov = btb.load_panel(str(stamped))
    assert panel == {"a": 0.7}          # agent lookups unaffected
    assert prov["rubric_hash"] == "abc"

    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({"a": 0.7}))
    panel, prov = btb.load_panel(str(bare))
    assert panel == {"a": 0.7}
    assert prov == {"unstamped": True, "source_file": str(bare)}

    assert btb.load_panel(None) == ({}, None)


def test_missing_report_is_a_loss_not_a_sit_out(tmp_path):
    bb = tmp_path / "bb"
    (bb / "a").mkdir(parents=True)
    (bb / "b").mkdir(parents=True)
    (bb / "a" / "t1.md").write_text("# Real report\n" + "useful " * 200)
    # b has the lane directory but no t1 report.
    staged = jury.discover_staging(tmp_path, "bb", set())
    assert staged["t1"]["b"] is None
    plan = jury.build_plan(staged, only_agent=None, only_task=None,
                           order_audit=0.0, seed=1)
    item = plan[0]
    rec = jury.walkover_record(
        backbone="bb", task_id="t1", a=item["a"], b=item["b"],
        order=item["order"], judge="j",
        report_a=jury._report_text(staged["t1"][item["a"]]),
        report_b=jury._report_text(staged["t1"][item["b"]]),
        word_budget=100,
    )
    winner_agent = item["a"] if rec["winner"] == ("A" if item["order"] == "ab" else "B") else item["b"]
    assert winner_agent == "a"
    assert rec["walkover"] is True
