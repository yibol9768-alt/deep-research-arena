"""Offline tests for RACE-style reference-anchored quality scoring (eval #3).

Covers BOTH new pieces:

* scripts/select_reference_reports.py: per-task reference selection picks the
  highest-grounding report (quote_match.score primary, must_cite_recall
  tie-break) and writes a {task: {agent, path, grounding}} manifest.
* scripts/build_real_leaderboard.py --reference-manifest MODE: each NON-reference
  agent is judged pairwise AGAINST that task's reference, the reference agent is
  EXCLUDED from being scored against itself, and per-agent quality is the
  win-rate vs reference. The default round-robin path stays back-compatible.

No network, no real judge: pairwise_judge.battle is mocked and report/score
files are synthetic tmp fixtures.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(mod_name: str, rel: str):
    spec = importlib.util.spec_from_file_location(mod_name, _REPO_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


brl = _load("build_real_leaderboard", "scripts/build_real_leaderboard.py")
sel = _load("select_reference_reports", "scripts/select_reference_reports.py")


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
def synth_ref(tmp_path):
    """Three agents (ref, mid, low) over two tasks.

    Grounding is engineered so 'ref' is the highest-grounding report on BOTH
    tasks (so the manifest selects it as the per-task reference) and all three
    sit ABOVE the gate floor so none is gated out (keeps the win-rate test
    focused on the reference exclusion logic, not the gate).
    """
    rdir = tmp_path / "deep"
    sdir = tmp_path / "deep_v3"
    tasks = ["t0001", "t0002"]
    for t in tasks:
        # ref: highest grounding -> becomes the reference.
        _write_report(rdir, "ref", t, words=2000)
        _write_score(sdir, "ref", t, recall=0.9, quote=0.95)
        # mid: solid, ungated, NOT the reference.
        _write_report(rdir, "mid", t, words=2000)
        _write_score(sdir, "mid", t, recall=0.6, quote=0.7)
        # low: ungated (above floor 0.30) but weakest of the three.
        _write_report(rdir, "low", t, words=2000)
        _write_score(sdir, "low", t, recall=0.4, quote=0.5)
    return rdir, sdir, tasks


# --------------------------------------------------------------------------- #
# 1. Reference selection: highest quote_match wins; recall breaks ties.
# --------------------------------------------------------------------------- #
def test_select_reference_picks_highest_grounding(synth_ref, tmp_path):
    rdir, sdir, tasks = synth_ref
    manifest = sel.build_manifest(report_dir=rdir, score_dir=sdir)
    assert set(manifest) == set(tasks)
    for t in tasks:
        assert manifest[t]["agent"] == "ref"
        assert manifest[t]["grounding"]["quote_match_score"] == 0.95
        # The path points at the real report file on disk.
        assert manifest[t]["path"].endswith(f"ref__{t}_matrix.md")
        assert Path(manifest[t]["path"]).exists()


def test_select_reference_tie_break_on_recall(tmp_path):
    """Equal quote_match.score -> higher must_cite_recall wins the reference."""
    rdir = tmp_path / "deep"
    sdir = tmp_path / "deep_v3"
    t = "t0001"
    _write_report(rdir, "a", t, words=500)
    _write_score(sdir, "a", t, recall=0.10, quote=0.80)
    _write_report(rdir, "b", t, words=500)
    _write_score(sdir, "b", t, recall=0.40, quote=0.80)  # same quote, higher recall
    manifest = sel.build_manifest(report_dir=rdir, score_dir=sdir)
    assert manifest[t]["agent"] == "b"


def test_select_reference_writes_manifest_file(synth_ref, tmp_path):
    rdir, sdir, _ = synth_ref
    out = tmp_path / "reference_reports" / "manifest.json"
    rc = sel.main([
        "--report-dir", str(rdir),
        "--score-dir", str(sdir),
        "--out", str(out),
    ])
    assert rc == 0
    assert out.exists()
    data = json.loads(out.read_text())
    assert all(v["agent"] == "ref" for v in data.values())


# --------------------------------------------------------------------------- #
# 2. Manifest loader normalizes {task: {agent,...}} into {task: agent}.
# --------------------------------------------------------------------------- #
def test_load_reference_manifest_shapes(tmp_path):
    rich = {"t1": {"agent": "ref", "path": "x", "grounding": {}}, "t2": {"agent": "z"}}
    assert brl.load_reference_manifest(rich) == {"t1": "ref", "t2": "z"}
    # flat {task: agent} tolerated too
    assert brl.load_reference_manifest({"t1": "ref"}) == {"t1": "ref"}
    # agent-less / malformed entries dropped, never crash
    assert brl.load_reference_manifest({"t1": {"path": "x"}, "t2": None}) == {}
    # from a JSON file on disk
    p = tmp_path / "m.json"
    p.write_text(json.dumps(rich), encoding="utf-8")
    assert brl.load_reference_manifest(p) == {"t1": "ref", "t2": "z"}


# --------------------------------------------------------------------------- #
# 3. Battle plan: reference mode pits every non-reference agent vs the per-task
#    reference, and NEVER scores the reference against itself.
# --------------------------------------------------------------------------- #
def test_battle_plan_reference_excludes_self(synth_ref):
    rdir, sdir, tasks = synth_ref
    reports = brl.discover_reports(rdir)
    agents = ["ref", "mid", "low"]
    ref_by_task = {"t0001": "ref", "t0002": "ref"}
    plan = brl.build_battle_plan(reports, agents, tasks, None, reference_by_task=ref_by_task)
    # 2 non-reference agents x 2 tasks = 4 battles; reference is always agent_b.
    assert len(plan) == 4
    for b in plan:
        assert b["agent_b"] == "ref"
        assert b["agent_a"] != "ref"   # reference never scored against itself
    pairs = {(b["task"], b["agent_a"]) for b in plan}
    assert pairs == {("t0001", "mid"), ("t0001", "low"), ("t0002", "mid"), ("t0002", "low")}


def test_battle_plan_skips_task_without_present_reference(synth_ref):
    rdir, sdir, tasks = synth_ref
    reports = brl.discover_reports(rdir)
    agents = ["ref", "mid", "low"]
    # ghost is the named reference for t0002 but has no report -> task skipped.
    ref_by_task = {"t0001": "ref", "t0002": "ghost"}
    plan = brl.build_battle_plan(reports, agents, tasks, None, reference_by_task=ref_by_task)
    tasks_in_plan = {b["task"] for b in plan}
    assert tasks_in_plan == {"t0001"}


# --------------------------------------------------------------------------- #
# 4. Full build in reference mode (mock judge): each agent runs vs the
#    reference, the reference is excluded from being scored against itself, and
#    per-agent quality is win-rate vs reference.
# --------------------------------------------------------------------------- #
def test_reference_mode_runs_each_agent_vs_reference(synth_ref, monkeypatch):
    rdir, sdir, tasks = synth_ref
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    seen_battles = []

    def _fake_battle(*, agent_a, agent_b, **kw):
        seen_battles.append((agent_a, agent_b))
        # The judge "knows" ref > mid > low. agent_b is always the reference.
        order = {"ref": 3, "mid": 2, "low": 1}
        winner = agent_a if order[agent_a] >= order[agent_b] else agent_b
        return {"agent_winner": winner, "verdicts_raw": ["A"], "reasonings": ["VERDICT: A"]}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _fake_battle)

    manifest = {t: {"agent": "ref", "path": "", "grounding": {}} for t in tasks}
    res = brl.build(
        report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1,
        reference_manifest=manifest,
    )

    # Quality mode is recorded as reference-anchored.
    assert res["quality_mode"] == "reference_manifest"
    assert res["summary"]["quality_mode"] == "reference_manifest"
    assert res["summary"]["reference_agents"] == ["ref"]

    # EVERY battle is against the reference, and the reference is NEVER
    # scored against itself.
    assert len(seen_battles) == 4  # (mid, low) x 2 tasks
    for a, b in seen_battles:
        assert b == "ref"
        assert a != "ref"

    # The reference agent has NO win-rate (excluded from being scored vs itself).
    assert res["agents"]["ref"]["winrate_vs_reference"] is None
    assert res["agents"]["ref"]["is_reference"] is True
    assert "ref" not in res["ranked_by_winrate_vs_reference"]

    # Non-reference agents each have a win-rate vs the reference. low/mid both
    # LOSE every battle to the stronger reference -> win-rate 0.0 over 2 battles.
    for a in ("mid", "low"):
        row = res["agents"][a]
        assert row["is_reference"] is False
        assert row["winrate_vs_reference"] == 0.0
        assert row["winrate_counts"]["decided"] == 2

    # The full battle_log records the reference per battle for audit.
    assert all(b["reference"] == "ref" for b in res["battle_log"])


def test_reference_mode_winrate_arena_hard_half_credit_on_tie(synth_ref, monkeypatch):
    """Win-rate is (wins + 0.5*ties)/decided; a tie gives Arena-Hard half credit
    and is excluded from the integer `wins` count."""
    rdir, sdir, tasks = synth_ref
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    def _judge(*, agent_a, agent_b, **kw):
        # mid beats ref on every task; low ties ref on every task.
        if agent_a == "mid":
            return {"agent_winner": "mid", "verdicts_raw": ["A"], "reasonings": ["VERDICT: A"]}
        return {"agent_winner": "tie", "verdicts_raw": ["TIE"], "reasonings": ["VERDICT: TIE"]}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _judge)

    manifest = {t: {"agent": "ref"} for t in tasks}
    res = brl.build(
        report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1,
        reference_manifest=manifest,
    )
    # mid won both -> 1.0 ; low tied both -> 0.5 (Arena-Hard half credit).
    assert res["agents"]["mid"]["winrate_vs_reference"] == 1.0
    assert res["agents"]["mid"]["winrate_counts"]["wins"] == 2
    assert res["agents"]["low"]["winrate_vs_reference"] == 0.5
    assert res["agents"]["low"]["winrate_counts"]["wins"] == 0  # ties not counted as wins
    # Ranking by win-rate puts mid above low; reference excluded.
    assert res["ranked_by_winrate_vs_reference"] == ["mid", "low"]


# --------------------------------------------------------------------------- #
# 5. Back-compat: with NO manifest the default round-robin path is unchanged.
# --------------------------------------------------------------------------- #
def test_round_robin_default_unchanged(synth_ref, monkeypatch):
    rdir, sdir, tasks = synth_ref
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    def _fake_battle(*, agent_a, agent_b, **kw):
        order = {"ref": 3, "mid": 2, "low": 1}
        winner = agent_a if order[agent_a] >= order[agent_b] else agent_b
        return {"agent_winner": winner, "verdicts_raw": ["A"], "reasonings": ["VERDICT: A"]}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _fake_battle)

    res = brl.build(report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1)
    assert res["quality_mode"] == "round_robin"
    # Round-robin over 3 agents x 2 tasks = 6 battles.
    assert res["n_battles"] == 6
    # No reference-anchored fields populated in round-robin mode.
    assert res["ranked_by_winrate_vs_reference"] == []
    for a in ("ref", "mid", "low"):
        assert res["agents"][a]["winrate_vs_reference"] is None
        assert res["agents"][a]["is_reference"] is False


def test_reference_skipped_when_agent_not_included(synth_ref, monkeypatch):
    """A manifest task whose reference agent is not an included agent is dropped
    into reference_skipped_tasks rather than crashing or inventing a baseline."""
    rdir, sdir, tasks = synth_ref
    monkeypatch.setattr(brl, "_load_simple_score", lambda: None)

    def _fake_battle(*, agent_a, agent_b, **kw):
        return {"agent_winner": agent_a, "verdicts_raw": ["A"], "reasonings": ["VERDICT: A"]}

    import src.scoring.pairwise_judge as pj
    monkeypatch.setattr(pj, "battle", _fake_battle)

    manifest = {"t0001": {"agent": "ref"}, "t0002": {"agent": "nobody"}}
    res = brl.build(
        report_dir=rdir, score_dir=sdir, word_budget=100, n_samples=1,
        reference_manifest=manifest,
    )
    skipped = {r["task"] for r in res["summary"]["reference_skipped_tasks"]}
    assert "t0002" in skipped
    # Only t0001 battles ran (2 non-reference agents).
    assert all(b["task"] == "t0001" for b in res["battle_log"])
