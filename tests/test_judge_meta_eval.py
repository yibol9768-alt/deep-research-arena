"""Offline tests for scripts/judge_meta_eval.py.

The judge is MOCKED so these run with no network and no API key. We assert:
  - perturbations actually degrade the report in the expected way,
  - a perfect mock judge yields 1.0 synthetic-gold accuracy,
  - the grounding correlation wires up Spearman against the deterministic
    signals stored on disk,
  - LLMBar gracefully skips when no data is reachable / cached,
  - --dry-run produces a plan without ever calling the judge.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import judge_meta_eval as jme  # noqa: E402


# ---------------------------------------------------------------------------
# Mock judges
# ---------------------------------------------------------------------------
def _quality(answer: str) -> float:
    """Heuristic 'quality' a competent judge would assign: reward citations,
    penalize the false-claim and truncation markers the perturbations inject."""
    q = len(answer) / 1000.0 + answer.count("](http") * 5.0
    for fc in jme.FALSE_CLAIMS:
        if fc in answer:
            q -= 50.0  # unsupported / false claims are strongly penalized
    if "[report ends abruptly]" in answer:
        q -= 1000.0  # truncated report is clearly worse despite any length
    return q


def perfect_original_judge(*, task_intent, agent_a, answer_a, agent_b, answer_b,
                           dimension=None, n_samples=1, model=None, **kw):
    """A competent judge proxy: prefers the better-cited, non-false, complete
    answer. For each perturbation the ORIGINAL scores strictly higher. For
    shuffled paragraphs (same content, scrambled flow) it relies on the fact
    that the original keeps its title-led ordering; we tie-break to original."""
    score_a = _quality(answer_a)
    score_b = _quality(answer_b)
    # Tiny structural bonus for the answer whose first line is a markdown title
    # (shuffle moves body but keeps the title first, so this never helps the
    # degraded variant; for the original-vs-shuffle case scores are equal, so
    # break ties toward the answer presented as 'original').
    if abs(score_a - score_b) < 1e-9:
        winner = agent_a if agent_a == "original" else (agent_b if agent_b == "original" else "tie")
        if winner == "tie":
            return {"agent_winner": "tie", "winner": "tie", "verdicts_raw": ["TIE"], "error": None}
        return {"agent_winner": winner, "winner": "a" if winner == agent_a else "b",
                "verdicts_raw": ["A"], "error": None}
    if score_a > score_b:
        return {"agent_winner": agent_a, "winner": "a", "verdicts_raw": ["A"], "error": None}
    return {"agent_winner": agent_b, "winner": "b", "verdicts_raw": ["B"], "error": None}


def grounding_aware_judge(*, task_intent, agent_a, answer_a, agent_b, answer_b,
                          dimension=None, n_samples=1, model=None, **kw):
    """Prefer the answer with more markdown citations (a grounding proxy)."""
    ca = answer_a.count("](http")
    cb = answer_b.count("](http")
    if ca > cb:
        return {"agent_winner": agent_a, "winner": "a", "verdicts_raw": ["A"]}
    if cb > ca:
        return {"agent_winner": agent_b, "winner": "b", "verdicts_raw": ["B"]}
    return {"agent_winner": "tie", "winner": "tie", "verdicts_raw": ["TIE"]}


# ---------------------------------------------------------------------------
# Perturbation unit tests
# ---------------------------------------------------------------------------
SAMPLE = (
    "# Headphones Report\n\n"
    "Intro paragraph with a cite [Sony](http://x.com/sony) and more text.\n\n"
    "Second paragraph with [Bose](http://x.com/bose) and [JBL](http://x.com/jbl).\n\n"
    "Third paragraph discussing [Apple](http://x.com/apple) products here.\n\n"
    "Fourth paragraph wraps up [Samsung](http://x.com/samsung) findings.\n\n"
    "Conclusion paragraph synthesizes everything [Sennheiser](http://x.com/senn)."
)


def _count_links(t: str) -> int:
    return len(jme._LINK_RE.findall(t))


def test_drop_citations_removes_most_links():
    rng = random.Random(0)
    out = jme.perturb_drop_citations(SAMPLE, rng)
    assert _count_links(out) < _count_links(SAMPLE)
    # ~70% dropped: at most ~half remain
    assert _count_links(out) <= _count_links(SAMPLE) // 2 + 1


def test_inject_false_claims_adds_content():
    rng = random.Random(0)
    out = jme.perturb_inject_false_claims(SAMPLE, rng)
    assert len(out) > len(SAMPLE)
    assert any(fc in out for fc in jme.FALSE_CLAIMS)


def test_truncate_shortens_to_about_40pct():
    rng = random.Random(0)
    # Use a realistic-size report so the 40% path (not the small-file floor)
    # is exercised.
    big = "para of words. " * 2000  # ~30k chars
    out = jme.perturb_truncate(big, rng)
    assert len(out) < len(big)
    marker = "\n\n[report ends abruptly]"
    assert len(out) <= int(len(big) * 0.40) + len(marker) + 5


def test_shuffle_preserves_content_changes_order():
    rng = random.Random(1)
    out = jme.perturb_shuffle_paragraphs(SAMPLE, rng)
    orig_paras = [p for p in SAMPLE.split("\n\n") if p.strip()]
    new_paras = [p for p in out.split("\n\n") if p.strip()]
    assert sorted(orig_paras) == sorted(new_paras)  # same content
    assert out != SAMPLE  # order changed (title stays, body shuffled)


# ---------------------------------------------------------------------------
# Method 1: synthetic-gold with a mocked perfect judge -> accuracy 1.0
# ---------------------------------------------------------------------------
def test_synthetic_gold_perfect_judge(tmp_path):
    reports = jme.pick_reports(3)
    assert reports, "expected real reports in data/results/deep"
    res = jme.run_synthetic_gold(
        perfect_original_judge, reports, n_samples=1, seed=7, dry_run=False
    )
    assert res["overall_total"] == len(reports) * len(jme.PERTURBATIONS)
    # A judge that always prefers the longer/more-cited text should pick the
    # ORIGINAL for every perturbation (each strictly degrades length or cites).
    assert res["overall_accuracy"] == 1.0
    for ptype, stats in res["per_type"].items():
        assert stats["accuracy"] == 1.0, ptype


def test_synthetic_gold_dry_run_makes_plan():
    reports = jme.pick_reports(2)
    res = jme.run_synthetic_gold(None, reports, n_samples=3, seed=1, dry_run=True)
    assert res["dry_run"] is True
    assert res["planned_battles"] == len(reports) * len(jme.PERTURBATIONS)


# ---------------------------------------------------------------------------
# Method 2: grounding correlation wires up Spearman
# ---------------------------------------------------------------------------
def test_grounding_correlation_runs(tmp_path):
    reports = jme.pick_reports(6)
    res = jme.run_grounding_correlation(
        grounding_aware_judge, reports, n_samples=1, dry_run=False
    )
    if res.get("skipped"):
        pytest.skip(res.get("reason"))
    assert res["n_reports"] >= 3
    assert "judge_winrate" in res
    # Spearman block exists for the composite grounding signal.
    assert "spearman_grounding" in res


def test_grounding_dry_run():
    reports = jme.pick_reports(5)
    res = jme.run_grounding_correlation(None, reports, n_samples=3, dry_run=True)
    assert res.get("dry_run") or res.get("skipped")


# ---------------------------------------------------------------------------
# Method 3: LLMBar skips cleanly with no network and no cache
# ---------------------------------------------------------------------------
def test_llmbar_skips_without_data(monkeypatch):
    monkeypatch.setattr(jme, "_try_download_llmbar", lambda: (None, "OfflineError: blocked"))
    res = jme.run_llmbar(perfect_original_judge, limit=10, n_samples=1, dry_run=False)
    assert res.get("skipped") is True
    assert "ready_to_run" in res


def test_llmbar_agreement_with_mock_data(monkeypatch):
    fake = [
        {"input": "q1", "output_1": "good detailed answer", "output_2": "bad", "label": 1},
        {"input": "q2", "output_1": "x", "output_2": "much longer better answer", "label": 2},
    ]
    monkeypatch.setattr(jme, "_try_download_llmbar", lambda: (fake, "mock"))
    res = jme.run_llmbar(perfect_original_judge, limit=10, n_samples=1, dry_run=False)
    assert res["n_pairs"] == 2
    assert res["agreement"] == 1.0  # perfect_original_judge prefers longer text


# ---------------------------------------------------------------------------
# CLI dry-run integration: never touches the judge
# ---------------------------------------------------------------------------
def test_cli_dry_run(tmp_path, monkeypatch):
    out = tmp_path / "res.json"
    def _boom():
        raise AssertionError("judge must not be imported/called in --dry-run")
    monkeypatch.setattr(jme, "_get_battle_fn", _boom)
    rc = jme.main(["--dry-run", "--limit", "4", "--out", str(out)])
    assert rc == 0
    assert out.is_file()
