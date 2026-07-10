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


def test_missing_report_is_a_healthy_empty_loss_not_a_sit_out(tmp_path):
    """Ruling #10: a MISSING/empty report is a healthy-run empty delivery, so it
    still records a loss (enters BT). Only a runner FAILURE placeholder becomes
    an infra debt (next test)."""
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
    # empty delivery is NOT an infra failure: it stays a loss inside BT.
    assert rec["walkover_infra"] is False
    assert rec["walkover_class"] == "healthy_empty"


def test_infra_stub_walkover_is_attributed_as_debt(tmp_path):
    """Ruling #10: a runner-failure placeholder (timeout / crash / framework
    exception) is classified an infra debt on the walkover record. Red on old
    code, which had no attribution fields."""
    rec = jury.walkover_record(
        backbone="bb", task_id="t1", a="a", b="b", order="ab", judge="j",
        report_a="(DeerFlow produced no report after 1256s, exit=1)",
        report_b="# Real report\n" + "useful " * 200,
        word_budget=100,
    )
    assert rec["walkover_infra"] is True
    assert rec["walkover_class"] == "infra_debt"
    assert rec["infra_a"] is True and rec["infra_b"] is False
    assert rec["stub_a"] is True and rec["stub_b"] is False


def _walkover_recs(**kw):
    """Three per-judge copies of one walkover record (walkovers are dispatched
    once per judge, all identical)."""
    return [jury.walkover_record(judge=f"j{i}", **kw) for i in range(3)]


def _judged_recs(task, a, b, order, winner):
    return [{
        "protocol": jury.PROTOCOL, "rubric_hash": jury.rubric_hash(),
        "word_budget": jury.DEFAULT_WORD_BUDGET, "backbone": "bb",
        "task": task, "a": a, "b": b, "order": order,
        "judge": f"j{i}", "winner": winner, "error": None,
        "report_sha_a": "sa", "report_sha_b": "sb", "walkover": False,
    } for i in range(3)]


def test_infra_debt_walkover_excluded_from_bt_but_healthy_empty_is_a_loss():
    """Ruling #10 end to end. Two agents fail to deliver against real reports:
    `a` with a framework crash (infra debt -> OUT of BT, counted as debt), `c`
    with an empty answer (healthy empty -> a real BT loss). Red on old code,
    which folded both into the fit and never surfaced n_infra_debt."""
    real = "# Real report\n" + "useful " * 200
    recs = []
    # t1: infra crash by `a` vs real `b`  -> infra debt, excluded from BT
    recs += _walkover_recs(backbone="bb", task_id="t1", a="a", b="b", order="ab",
                           report_a="(qx-agents error: ValidationError: boom)",
                           report_b=real, word_budget=jury.DEFAULT_WORD_BUDGET)
    # t2: empty delivery by `c` vs real `b` -> healthy empty, a real BT loss
    recs += _walkover_recs(backbone="bb", task_id="t2", a="b", b="c", order="ab",
                           report_a=real, report_b="",
                           word_budget=jury.DEFAULT_WORD_BUDGET)
    # t3: a real judged battle so BT has ordinary content (position "A" = b wins)
    recs += _judged_recs("t3", "b", "c", "ab", "A")

    fit = jury.fit_from_bank(recs, backbone="bb", judges=["j0", "j1", "j2"])

    assert fit["n_infra_debt_walkovers"] == 1
    ag = fit["agents"]
    # `a` only ever appeared in the infra-debt walkover: NOT in BT at all,
    # counted purely as a delivery debt.
    assert ag["a"]["n_battles"] == 0
    assert ag["a"]["n_losses"] == 0
    assert ag["a"]["n_infra_debt"] == 1
    assert ag["a"]["n_delivered"] == 0
    assert ag["a"]["delivery_rate"] == 0.0
    # `c` delivered nothing on t2 but that healthy-empty walkover IS a BT loss.
    assert ag["c"]["n_infra_debt"] == 0
    assert ag["c"]["n_losses"] >= 1
    # `b` faced the crash (t1) and delivered; it earns no phantom BT win for the
    # opponent's framework failure -- t1 is not in its battle count.
    assert ag["b"]["n_infra_debt"] == 0
    assert ag["b"]["delivery_rate"] == 1.0
