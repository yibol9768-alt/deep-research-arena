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
