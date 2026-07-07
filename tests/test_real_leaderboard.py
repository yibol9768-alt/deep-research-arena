"""Offline tests for scripts/build_real_leaderboard.py.

No network, no real judge: pairwise_judge.battle is mocked and report/score
files are synthetic tmp fixtures. Verifies the work-list/battle-count plan,
that a better report wins the BT ranking, that an agent with NO files is
SKIPPED (not fabricated), and the non-synthetic output markers.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "build_real_leaderboard", _REPO_ROOT / "scripts" / "build_real_leaderboard.py"
)
brl = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(brl)


# --------------------------------------------------------------------------- #
# Fixtures: synthetic report + score files on disk.
# --------------------------------------------------------------------------- #
def _write_report(report_dir: Path, agent: str, task: str, words: int) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    body = " ".join([f"w{i}" for i in range(words)])
    (report_dir / f"{agent}__{task}_matrix.md").write_text(body, encoding="utf-8")


def _write_score(score_dir: Path, agent: str, task: str, recall: float, quote: float) -> None:
    score_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "task": task,
        "url_coverage": {"details": {"must_cite_recall": recall, "domain_balance": 1.0, "pool_coverage": 0.9}},
        "quote_match": {"score": quote},
    }
    (score_dir / f"{agent}__{task}_matrix.score.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture()
def synth(tmp_path):
    """Two real agents (good, bad) over two tasks; 'ghost' has NO files."""
    rdir = tmp_path / "deep"
    sdir = tmp_path / "deep_v3"
    tasks = ["t0001", "t0002"]
    for t in tasks:
        # good: long, high grounding
        _write_report(rdir, "good", t, words=2000)
        _write_score(sdir, "good", t, recall=0.9, quote=0.9)
        # bad: short, low grounding (below default floor 0.30)
        _write_report(rdir, "bad", t, words=50)
        _write_score(sdir, "bad", t, recall=0.05, quote=0.1)
    return rdir, sdir, tasks


# --------------------------------------------------------------------------- #
# 1. dry-run plan correctness, no judge calls.
# --------------------------------------------------------------------------- #
def test_dry_run_plan(synth, monkeypatch):
    rdir, sdir, tasks = synth

    called = {"n": 0}

    def _boom(**kwargs):
        called["n"] += 1
        raise AssertionError("judge must NOT be called in dry-run")

    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)
    # battle is imported inside build() only for the real path; patch the module too.
    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _boom)

    res = brl.build(report_dir=rdir, score_dir=sdir, dry_run=True)

    assert res["mode"] == "dry-run"
    assert res["synthetic_placeholder"] is False
    assert res["summary"]["agents_included"] == ["bad", "good"]
    # round-robin, 2 agents, 2 tasks => 2 battles
    assert res["summary"]["n_battles_planned"] == 2
    plan_keys = {(b["task"], frozenset((b["agent_a"], b["agent_b"]))) for b in res["battle_plan"]}
    assert plan_keys == {(t, frozenset(("good", "bad"))) for t in tasks}
    assert called["n"] == 0


# --------------------------------------------------------------------------- #
# 2. mocked judge prefers the better report -> BT ranking order.
# --------------------------------------------------------------------------- #
def test_bt_ranking_order(synth, monkeypatch):
    rdir, sdir, tasks = synth
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    def _fake_battle(*, agent_a, agent_b, answer_a, answer_b, **kw):
        # The judge "knows" good > bad. Truncation is length control, so both
        # may be the same length here; we decide on agent identity.
        winner = "good" if "good" in (agent_a, agent_b) else "tie"
        # winner must be one of the two agents in this battle
        if winner not in (agent_a, agent_b):
            winner = "tie"
        return {"winner": "a", "agent_winner": winner}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _fake_battle)

    res = brl.build(report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1)

    assert res["agents"]["good"]["quality_elo"] > res["agents"]["bad"]["quality_elo"]
    # good is above the grounding floor; bad is gated out.
    assert res["agents"]["good"]["gated"] is False
    assert res["agents"]["bad"]["gated"] is True
    # gated ranking only contains ungated agents, good first.
    assert res["ranked_by_quality_elo_gated"] == ["good"]
    # grounding ranking has good before bad.
    assert res["ranked_by_grounding"] == ["good", "bad"]


# --------------------------------------------------------------------------- #
# 3. agent with NO files is skipped, never fabricated.
# --------------------------------------------------------------------------- #
def test_ghost_agent_skipped(synth, monkeypatch):
    rdir, sdir, tasks = synth
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    res = brl.build(
        report_dir=rdir, score_dir=sdir,
        agents_filter=["good", "bad", "ghost"],
        dry_run=True,
    )
    assert "ghost" not in res["summary"]["agents_included"]
    skipped_agents = {s["agent"] for s in res["summary"]["agents_skipped"]}
    assert "ghost" in skipped_agents
    # ghost never appears anywhere in the output as a scored row.
    assert "ghost" not in res.get("grounding_mean", {})


# --------------------------------------------------------------------------- #
# 4. output markers + per-agent fields.
# --------------------------------------------------------------------------- #
def test_output_markers(synth, monkeypatch):
    rdir, sdir, tasks = synth
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    def _fake_battle(*, agent_a, agent_b, **kw):
        return {"winner": "tie", "agent_winner": "good" if "good" in (agent_a, agent_b) else "tie"}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _fake_battle)

    res = brl.build(report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1)
    assert res["synthetic_placeholder"] is False
    assert res["source"] == "real"
    for a in ("good", "bad"):
        row = res["agents"][a]
        assert "quality_elo" in row
        assert "grounding" in row
        assert row["n_tasks"] == 2


# --------------------------------------------------------------------------- #
# 5. fallback grounding ignores citation volume.
# --------------------------------------------------------------------------- #
def test_fallback_grounding_ignores_volume():
    sj = {
        "url_coverage": {"details": {"must_cite_recall": 0.2, "domain_balance": 1.0, "pool_coverage": 1.0}},
        "quote_match": {"score": 0.4},
    }
    # 0.5*0.2 + 0.5*0.4 = 0.3 ; volume fields must not change this.
    assert abs(brl._fallback_grounding(sj) - 0.3) < 1e-9


# --------------------------------------------------------------------------- #
# 6. length control: equal truncation regardless of raw length.
# --------------------------------------------------------------------------- #
def test_truncate_words():
    text = " ".join(str(i) for i in range(500))
    assert brl.word_count(brl.truncate_words(text, 100)) == 100
    short = "a b c"
    assert brl.truncate_words(short, 100) == short


# --------------------------------------------------------------------------- #
# 7. BUG C: invalid-capture reports land in invalid_runs, NOT in the ranking.
# --------------------------------------------------------------------------- #
def test_detect_invalid_report():
    assert brl.detect_invalid_report("(empty storm output)") is not None
    assert brl.detect_invalid_report("(runner error: Boom)") is not None
    assert brl.detect_invalid_report("") == "empty_report"
    assert brl.detect_invalid_report("a\nTraceback (most recent call last):\n  ...") is not None
    assert brl.detect_invalid_report("too short") is not None  # < 50 words
    # A genuine (if weak) report is NOT flagged.
    assert brl.detect_invalid_report(" ".join(f"w{i}" for i in range(200))) is None


def test_invalid_capture_excluded_from_ranking(tmp_path, monkeypatch):
    """A '(empty storm output)' report must be bucketed into invalid_runs and
    never ranked, grounded, or battled."""
    rdir = tmp_path / "deep"
    sdir = tmp_path / "deep_v3"
    tasks = ["t0001", "t0002"]
    for t in tasks:
        # good agent: real long report, high grounding.
        _write_report(rdir, "good", t, words=2000)
        _write_score(sdir, "good", t, recall=0.9, quote=0.9)
        # storm agent: capture failure -> invalid, even though a score.json exists.
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / f"storm__{t}_matrix.md").write_text("(empty storm output)", encoding="utf-8")
        _write_score(sdir, "storm", t, recall=0.0, quote=0.0)

    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    def _fake_battle(*, agent_a, agent_b, **kw):
        return {"winner": "tie", "agent_winner": "good" if "good" in (agent_a, agent_b) else "tie"}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _fake_battle)

    res = brl.build(report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1)

    # storm appears in invalid_runs with a reason, NOT as a scored/gated agent.
    inv_agents = {ir["agent"] for ir in res["invalid_runs"]}
    assert inv_agents == {"storm"}
    assert len(res["invalid_runs"]) == 2  # one per task
    for ir in res["invalid_runs"]:
        assert "empty" in ir["reason"].lower()

    # storm is neither ranked, grounded, nor a battle participant.
    assert "storm" not in res["agents"]
    assert "storm" not in res["ranked_by_grounding"]
    assert "storm" not in res["ranked_by_quality_elo_gated"]
    assert res["summary"]["n_invalid_runs"] == 2
    # The valid agent is unaffected.
    assert res["agents"]["good"]["gated"] is False


# --------------------------------------------------------------------------- #
# Fixtures with THREE agents: two UNGATED (good1, good2) and one GATED (junk).
# Used by the BUG-D ungated-only Bradley-Terry tests.
# --------------------------------------------------------------------------- #
@pytest.fixture()
def synth3(tmp_path):
    rdir = tmp_path / "deep"
    sdir = tmp_path / "deep_v3"
    tasks = ["t0001", "t0002"]
    for t in tasks:
        _write_report(rdir, "good1", t, words=2000)
        _write_score(sdir, "good1", t, recall=0.9, quote=0.9)
        _write_report(rdir, "good2", t, words=2000)
        _write_score(sdir, "good2", t, recall=0.8, quote=0.8)
        # junk: grounded BELOW the floor -> gated.
        _write_report(rdir, "junk", t, words=2000)
        _write_score(sdir, "junk", t, recall=0.02, quote=0.05)
    return rdir, sdir, tasks


# --------------------------------------------------------------------------- #
# 8. Integrity: preferred simple_score path is INAPPLICABLE (wrong arity), so
#    the deterministic additive formula is used; a real single-arg scorer that
#    raises must FAIL LOUDLY (no bare-except swallow).
# --------------------------------------------------------------------------- #
def test_load_simple_score_rejects_wrong_arity():
    # The real grounding_score requires 3 positional args -> not the single-dict
    # convention this path assumes, so _load_simple_score returns None and the
    # additive fallback is used.
    from src.scoring.simple_score import grounding_score
    assert brl._required_positional_count(grounding_score) == 3
    assert brl._load_simple_score() is None


def test_simple_score_from_json_does_not_swallow_errors():
    """A genuine runtime error inside an applicable single-arg scorer must
    propagate, NOT be swallowed into a silent None fallback."""
    def boom(_score_json):
        raise ValueError("scorer exploded")

    with pytest.raises(ValueError, match="scorer exploded"):
        brl._simple_score_from_json(boom, {"any": "json"})


def test_simple_score_from_json_dict_and_float_shapes():
    assert brl._simple_score_from_json(lambda j: {"grounding": 0.7}, {}) == 0.7
    assert brl._simple_score_from_json(lambda j: 0.42, {}) == 0.42
    assert brl._simple_score_from_json(lambda j: {"nope": 1}, {}) is None
    assert brl._simple_score_from_json(lambda j: None, {}) is None


def test_grounding_for_uses_additive_not_f1():
    """grounding_for must report the additive formula source, never an F1 that
    it does not compute (the real grounding_score is inapplicable here)."""
    sj = {
        "url_coverage": {"details": {"must_cite_recall": 0.2}},
        "quote_match": {"score": 0.4},
    }
    val, src = brl.grounding_for(sj)
    assert abs(val - 0.3) < 1e-9  # 0.5*0.2 + 0.5*0.4
    assert src == "fallback_recall_quote"


def test_output_states_actual_additive_formula(synth, monkeypatch):
    """The output JSON composite_formula / grounding_description must describe
    the additive citation-fidelity + curated recall actually in use, NOT F1."""
    rdir, sdir, _ = synth
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    def _fake_battle(*, agent_a, agent_b, **kw):
        return {"winner": "tie", "agent_winner": "good" if "good" in (agent_a, agent_b) else "tie"}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _fake_battle)

    res = brl.build(report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1)
    s = res["summary"]
    assert "curated" in s["composite_formula"].lower()
    assert "quote_match" in s["composite_formula"].lower()
    # The primary formula is the closed-world composite (which legitimately
    # names GroundF1@K); the legacy fallback half must stay additive and its
    # description must keep disclaiming F1 for the fallback path.
    assert "reachrate^gamma" in s["composite_formula"].lower()
    assert "legacy fallback: 0.5 * curated_must_cite_recall" in s["composite_formula"].lower()
    assert "additive" in s["grounding_description"].lower()
    assert "not an f1" in s["grounding_description"].lower()


# --------------------------------------------------------------------------- #
# 9. BUG B3: judge-error detection + smoke abort + fraction abort + persistence.
# --------------------------------------------------------------------------- #
def test_is_judge_error_result():
    # Hard failure: outer error key.
    assert brl.is_judge_error_result({"error": "RuntimeError: down"}) is True
    # Every round reported a (judge error ...) reasoning.
    assert brl.is_judge_error_result({
        "agent_winner": "tie",
        "verdicts_raw": ["TIE"],
        "reasonings": ["(judge error: timeout)"],
    }) is True
    # All verdicts None.
    assert brl.is_judge_error_result({"verdicts_raw": [None, None], "reasonings": []}) is True
    # A clean result is NOT a judge error.
    assert brl.is_judge_error_result({
        "agent_winner": "good",
        "verdicts_raw": ["A", "A"],
        "reasonings": ["- good is better\nVERDICT: A"],
    }) is False
    # Bare mocked result (no verdicts/reasonings) is NOT a judge error.
    assert brl.is_judge_error_result({"winner": "tie", "agent_winner": "tie"}) is False


def test_smoke_abort_on_judge_error(synth, monkeypatch):
    """The pre-flight 1-battle SMOKE must ABORT loudly if the judge errors,
    before the full plan is run."""
    rdir, sdir, _ = synth
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    calls = {"n": 0}

    def _error_battle(*, agent_a, agent_b, **kw):
        calls["n"] += 1
        return {"winner": "tie", "agent_winner": "tie",
                "error": "RuntimeError: judge backend unreachable"}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _error_battle)

    with pytest.raises(brl.JudgeErrorAbort) as ei:
        brl.build(report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1)
    # Smoke aborts after exactly ONE battle, never burning the full plan.
    assert calls["n"] == 1
    assert ei.value.error_fraction == 1.0


def test_judge_error_fraction_abort(synth3, monkeypatch):
    """If more than ~5% of battles error (past the smoke), ABORT instead of
    emitting a flat ~1000-Elo board."""
    rdir, sdir, _ = synth3
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    state = {"n": 0}

    def _mostly_error_battle(*, agent_a, agent_b, **kw):
        state["n"] += 1
        # First battle (the smoke) succeeds so we get PAST the smoke; the rest
        # error, pushing the fraction well past 5%.
        if state["n"] == 1:
            return {"agent_winner": "good1", "verdicts_raw": ["A"],
                    "reasonings": ["VERDICT: A"]}
        return {"agent_winner": "tie", "verdicts_raw": ["TIE"],
                "reasonings": ["(judge error: timeout)"]}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _mostly_error_battle)

    with pytest.raises(brl.JudgeErrorAbort) as ei:
        brl.build(report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1)
    assert ei.value.error_fraction is not None
    assert ei.value.error_fraction > 0.05


def test_judge_errors_flagged_not_aborted_when_disabled(synth3, monkeypatch):
    """With abort disabled, a degenerate run is loudly FLAGGED (summary +
    persisted verdicts/error) instead of silently scoring everyone tied."""
    rdir, sdir, _ = synth3
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    def _all_error_battle(*, agent_a, agent_b, **kw):
        return {"agent_winner": "tie", "verdicts_raw": ["TIE"], "error": "down"}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _all_error_battle)

    res = brl.build(report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1,
                    abort_on_judge_error=False)
    # Degenerate run is detectable: every battle flagged, fraction == 1.0.
    assert res["summary"]["judge_error_fraction"] == 1.0
    assert res["summary"]["n_judge_errors"] == res["n_battles"]
    # Persisted verdicts_raw + error per battle (BUG B3.iii).
    for blog in res["battle_log"]:
        assert blog["judge_error"] is True
        assert blog["error"] == "down"
        assert blog["verdicts_raw"] == ["TIE"]


def test_battle_log_persists_verdicts(synth3, monkeypatch):
    """verdicts_raw + error are persisted into the battle_log on a healthy run
    too, so a board can always be audited."""
    rdir, sdir, _ = synth3
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    def _ok_battle(*, agent_a, agent_b, **kw):
        winner = "good1" if "good1" in (agent_a, agent_b) else (
            "good2" if "good2" in (agent_a, agent_b) else "tie")
        if winner not in (agent_a, agent_b):
            winner = "tie"
        return {"agent_winner": winner, "verdicts_raw": ["A", "A"],
                "reasonings": ["VERDICT: A"], "error": None}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _ok_battle)

    res = brl.build(report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1)
    assert res["summary"]["n_judge_errors"] == 0
    for blog in res["battle_log"]:
        assert "verdicts_raw" in blog
        assert "error" in blog
        assert blog["judge_error"] is False


# --------------------------------------------------------------------------- #
# 10. BUG D: headline Bradley-Terry ranking drops battles vs GATED agents.
# --------------------------------------------------------------------------- #
def test_headline_bt_drops_gated_battles(synth3, monkeypatch):
    """Battles where either side is gated are excluded from the headline
    (ungated-only) fit, so beating gated junk does not inflate the Elo."""
    rdir, sdir, _ = synth3
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    def _judge(*, agent_a, agent_b, **kw):
        # good1 > good2 > junk. Resolve to the stronger agent present.
        order = {"good1": 3, "good2": 2, "junk": 1}
        winner = agent_a if order[agent_a] >= order[agent_b] else agent_b
        return {"agent_winner": winner, "verdicts_raw": ["A"], "reasonings": ["VERDICT: A"]}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _judge)

    res = brl.build(report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1)

    # junk is gated; good1/good2 are not.
    assert res["agents"]["junk"]["gated"] is True
    assert res["agents"]["good1"]["gated"] is False
    assert res["agents"]["good2"]["gated"] is False

    # Round-robin over 3 agents x 2 tasks = 6 battles total; battles touching
    # junk (good1-junk, good2-junk per task = 4) are dropped from the headline.
    assert res["n_battles"] == 6
    assert res["n_battles_dropped_gated"] == 4
    assert res["n_ranked_battles"] == 2  # only good1-vs-good2, one per task

    # Headline ranking contains ONLY ungated agents, good1 first.
    assert res["ranked_by_quality_elo_gated"] == ["good1", "good2"]
    assert "junk" not in res["ranked_by_quality_elo_gated"]

    # Headline (ungated-only) Elo exists for the ungated agents and gives
    # good1 the edge; the gated junk has no headline Elo.
    assert res["agents"]["good1"]["quality_elo_ranked"] is not None
    assert res["agents"]["good2"]["quality_elo_ranked"] is not None
    assert res["agents"]["junk"]["quality_elo_ranked"] is None
    assert (res["agents"]["good1"]["quality_elo_ranked"]
            > res["agents"]["good2"]["quality_elo_ranked"])

    # The full battle_log is kept unfiltered (all 6 battles, including vs junk).
    assert len(res["battle_log"]) == 6
    assert any(b["agent_a"] == "junk" or b["agent_b"] == "junk" for b in res["battle_log"])
