from __future__ import annotations

import json
import math
from pathlib import Path

from src.eval.evaluator import ArenaEvaluator
from src.eval.reward_terms import CITATION_CAP
from src.eval.rollout import Rollout
from src.scoring.leaderboard_composites import composite_v3_softfloor
from src.verifiers.citation_format import canonicalize_url


URLS = [
    "http://localhost:7770/product-a.html",
    "http://localhost:9999/f/audio/1/thread",
    "http://localhost:8090/content/wikipedia_en_all_nopic/A/headphones",
]

SNIPPETS = {
    URLS[0]: "Alpha headphones have balanced sound and battery life, but fit limits matter for travel listeners.",
    URLS[1]: "Forum users praise comfort value and practical long term headphone use.",
    URLS[2]: "Headphones transduce electrical signals into sound near the listener ear.",
}


def _write_golden(tmp_path: Path, urls: list[str] | None = None) -> Path:
    path = tmp_path / "golden.json"
    golden_urls = urls or URLS
    rows = [{"url": u, "weight": 1.0} for u in golden_urls]
    path.write_text(json.dumps({
        "must_cite_urls": rows,
        "expected_pool_urls": [{"url": u} for u in golden_urls],
    }))
    return path


def _task_config(
    tmp_path: Path,
    *,
    max_words: int = 220,
    min_citations: int = 3,
    golden_urls: list[str] | None = None,
) -> dict:
    return {
        "task_id": "rl_synth",
        "intent": "Write a grounded report on audio headphones.",
        "sandbox_hosts": [
            "localhost:7770",
            "localhost:9999",
            "localhost:8090",
        ],
        "markdown_spec": {
            "min_words": 20,
            "max_words": max_words,
            "min_paragraphs": 3,
            "min_citations": min_citations,
            "min_pages_browsed": 0,
        },
        "citation_policy": {
            "must_be_in_domain": [],
        },
        "perspective_balance": {
            "evaluated_entities": ["Alpha headphones"],
            "min_score": 0.5,
        },
        "url_coverage": {
            "golden_pool_path": str(_write_golden(tmp_path, golden_urls)),
            "min_unique_urls_cited": 1,
            "min_must_cite_recall": 0.0,
            "min_expected_pool_coverage": 0.0,
            "min_domain_balance": 0.0,
        },
    }


def _report() -> str:
    return (
        "# Audio Headphones Report\n\n"
        f"Alpha headphones have balanced sound and battery life, but fit limits matter for travel listeners "
        f"[product]({URLS[0]}).\n\n"
        f"Forum users praise comfort value and practical long term headphone use "
        f"[thread]({URLS[1]}).\n\n"
        f"Wikipedia explains that headphones transduce electrical signals into "
        f"sound near the listener ear [wiki]({URLS[2]}).\n\n"
        "Together these sources support a compact recommendation with enough "
        "detail for a buyer to compare comfort, battery life, and sound quality."
    )


def _rollout(report: str | None = None, *, store: bool = True, calls: bool = True) -> Rollout:
    snippets = {
        canonicalize_url(url): text
        for url, text in SNIPPETS.items()
    } if store else {}
    tool_calls = [
        {"endpoint": "/search", "query": "alpha headphones", "n_results": 3, "ok": True},
        {"endpoint": "/search", "query": "headphone comfort forum", "n_results": 2, "ok": True},
        {"endpoint": "/extract", "query": None, "n_results": 3, "ok": True},
    ] if calls else []
    return Rollout(
        task_id="rl_synth",
        report_md=report if report is not None else _report(),
        retrieved_snippets=snippets,
        fetched_urls=list(URLS) if store else [],
        tool_calls=tool_calls,
        step_count=len(tool_calls),
    )


def _evaluator(config: dict, *, mode: str = "fast") -> ArenaEvaluator:
    ev = ArenaEvaluator("rl_synth", mode=mode)
    ev._task_config = config
    return ev


def test_honest_rollout_scores_and_is_not_nullified(tmp_path: Path):
    result = _evaluator(_task_config(tmp_path)).evaluate_rollout(_rollout())
    assert result.composite > 0.0
    assert result.signal_health == "ok"
    assert result.reward_terms["penalties"]["nullify"] is False


def test_proxy_grounding_with_tool_calls_does_not_nullify(tmp_path: Path):
    result = _evaluator(_task_config(tmp_path)).evaluate_rollout(
        _rollout(store=False, calls=True)
    )
    assert result.reward_terms["grounding"]["source"] == "proxy"
    assert result.reward_terms["penalties"]["nullify"] is False
    assert result.composite > 0.0


def test_small_reach_bench_trace_does_not_false_nullify(tmp_path: Path):
    rollout = _rollout(store=False, calls=True)
    rollout.trace = {
        "url_reachability": {"score": 0.1},
        "quote_match": {"score": 1.0},
    }
    result = _evaluator(_task_config(tmp_path)).evaluate_rollout(rollout)
    assert result.reward_terms["penalties"]["nullify"] is False
    assert result.composite > 0.0


def test_primary_proof_of_fetch_nullifies_when_no_cited_url_resolves(tmp_path: Path):
    alien_url = "http://localhost:7770/unrelated-page.html"
    rollout = Rollout(
        task_id="rl_synth",
        report_md=_report(),
        retrieved_snippets={
            canonicalize_url(alien_url): "This fetched page is real but unrelated."
        },
        fetched_urls=[alien_url],
        tool_calls=[
            {"endpoint": "/search", "query": "unrelated", "n_results": 1, "ok": True},
        ],
        step_count=1,
    )
    result = _evaluator(_task_config(tmp_path)).evaluate_rollout(rollout)
    assert result.reward_terms["grounding"]["source"] == "proof_of_fetch"
    assert result.reward_terms["grounding"]["n_resolved"] == 0
    assert result.reward_terms["penalties"]["nullify"] is True
    assert result.composite == 0.0


def test_off_topic_claim_on_real_page_has_low_leaf(tmp_path: Path):
    url = URLS[0]
    report = (
        f"Alpha headphones battery sound comfort cure migraines and replace "
        f"medical care [product]({url})."
    )
    rollout = Rollout(
        task_id="rl_synth",
        report_md=report,
        retrieved_snippets={
            canonicalize_url(url): (
                "Alpha headphones battery sound comfort details appear in "
                "ordinary product specifications, cable notes, and warranty text."
            )
        },
        fetched_urls=[url],
        tool_calls=[
            {"endpoint": "/search", "query": "alpha headphones", "n_results": 1, "ok": True},
        ],
        step_count=1,
    )
    config = _task_config(tmp_path, min_citations=1)
    config["markdown_spec"]["min_words"] = 1
    config["markdown_spec"]["min_paragraphs"] = 1
    result = _evaluator(config).evaluate_rollout(rollout)
    assert result.reward_terms["grounding"]["samples"][0]["leaf"] <= 0.5


def test_fetch_aware_cap_keeps_fetched_citations_ahead_of_unfetched(tmp_path: Path):
    real_urls = [
        f"http://localhost:7770/w-fetched-{i:02d}.html"
        for i in range(CITATION_CAP)
    ]
    fake_urls = [
        f"http://localhost:7770/a-unfetched-{i:02d}.html"
        for i in range(CITATION_CAP + 5)
    ]
    real_paragraphs = [
        (
            f"Fetched page {i:02d} documents battery comfort and sound "
            f"detail {i:02d} [real{i:02d}]({url})."
        )
        for i, url in enumerate(real_urls)
    ]
    fake_links = " ".join(
        f"[fake{i:02d}]({url})"
        for i, url in enumerate(fake_urls)
    )
    report = (
        "# Cap Ordering Report\n\n"
        + "\n\n".join(real_paragraphs)
        + "\n\n"
        + fake_links
        + "\n\nThese fetched citations should survive the cap."
    )
    rollout = Rollout(
        task_id="rl_synth",
        report_md=report,
        retrieved_snippets={
            canonicalize_url(url): (
                f"Fetched page {i:02d} documents battery comfort and sound detail {i:02d}."
            )
            for i, url in enumerate(real_urls)
        },
        fetched_urls=real_urls,
        tool_calls=[
            {"endpoint": "/search", "query": "cap ordering", "n_results": 20, "ok": True},
        ],
        step_count=1,
    )
    result = _evaluator(
        _task_config(
            tmp_path,
            max_words=2000,
            min_citations=CITATION_CAP,
            golden_urls=real_urls,
        )
    ).evaluate_rollout(rollout)
    assert result.reward_terms["grounding"]["n_resolved"] == CITATION_CAP
    assert result.reward_terms["penalties"]["nullify"] is False
    assert result.composite > 0.0


def test_fabricated_cites_past_cap_still_penalized(tmp_path: Path):
    # Regression: CITATION_CAP real fetched citations plus extra never-fetched
    # ones. The fetched-first reorder used to push every fabricated cite past the
    # cap so it was dropped before fabrication was measured (p_fabricate == 0).
    # Fabrication must be counted over the full deduped cited set.
    real_urls = [
        f"http://localhost:7770/w-fetched-{i:02d}.html"
        for i in range(CITATION_CAP)
    ]
    fake_urls = [
        f"http://localhost:7770/a-unfetched-{i:02d}.html"
        for i in range(5)
    ]
    real_paragraphs = [
        (
            f"Fetched page {i:02d} documents battery comfort and sound "
            f"detail {i:02d} [real{i:02d}]({url})."
        )
        for i, url in enumerate(real_urls)
    ]
    fake_links = " ".join(
        f"[fake{i:02d}]({url})" for i, url in enumerate(fake_urls)
    )
    report = (
        "# Fabricated Past Cap Report\n\n"
        + "\n\n".join(real_paragraphs)
        + "\n\n"
        + fake_links
        + "\n\nThe fabricated cites must not hide behind the cap."
    )
    rollout = Rollout(
        task_id="rl_synth",
        report_md=report,
        retrieved_snippets={
            canonicalize_url(url): (
                f"Fetched page {i:02d} documents battery comfort and sound detail {i:02d}."
            )
            for i, url in enumerate(real_urls)
        },
        fetched_urls=real_urls,
        tool_calls=[
            {"endpoint": "/search", "query": "fab past cap", "n_results": 20, "ok": True},
        ],
        step_count=1,
    )
    result = _evaluator(
        _task_config(
            tmp_path,
            max_words=2000,
            min_citations=CITATION_CAP,
            golden_urls=real_urls,
        )
    ).evaluate_rollout(rollout)
    # 5 fabricated out of 25 cited -> 0.20 fabrication signal, must survive.
    assert result.reward_terms["penalties"]["p_fabricate"] > 0.0
    # The honest fetched citations still ground, so this is not a full nullify.
    assert result.reward_terms["penalties"]["nullify"] is False


def test_compute_penalties_counts_fabrication_over_full_set(tmp_path: Path):
    # Unit-level check on the pure reward term: even when the caller passes the
    # capped (n_cited, n_resolved) that hide the fabricated cites, compute_penalties
    # recovers the fabrication from the uncapped cited set.
    from src.eval.reward_terms import compute_penalties

    real_urls = [
        f"http://localhost:7770/w-fetched-{i:02d}.html"
        for i in range(CITATION_CAP)
    ]
    fake_urls = [
        f"http://localhost:7770/a-unfetched-{i:02d}.html"
        for i in range(5)
    ]
    links = " ".join(
        f"[c]({u})" for u in (real_urls + fake_urls)
    )
    report = "# R\n\n" + links + "\n\nbody text for the report."
    rollout = Rollout(
        task_id="rl_synth",
        report_md=report,
        retrieved_snippets={canonicalize_url(u): "page text" for u in real_urls},
        fetched_urls=real_urls,
        tool_calls=[],
        step_count=0,
    )
    config = _task_config(tmp_path, golden_urls=real_urls)
    # Simulate the buggy capped counts the caller would have derived.
    penalties = compute_penalties(
        rollout,
        config,
        s_ground=0.5,
        n_cited=CITATION_CAP,
        n_resolved=CITATION_CAP,
    )
    # 5 fabricated / 25 cited == 0.2 over the full deduped set.
    assert penalties["p_fabricate"] == 0.2


def test_fabricated_url_rollout_nullifies(tmp_path: Path):
    config = _task_config(tmp_path)
    honest = _evaluator(config).evaluate_rollout(_rollout())
    alien_url = "http://localhost:7770/zzz-fabricated.html"
    fabricated_rollout = Rollout(
        task_id="rl_synth",
        report_md=_report(),
        retrieved_snippets={
            canonicalize_url(alien_url): "A fetched page that does not match any cited URL."
        },
        fetched_urls=[alien_url],
        tool_calls=[],
        step_count=0,
    )
    fabricated = _evaluator(config).evaluate_rollout(fabricated_rollout)
    assert fabricated.reward_terms["penalties"]["nullify"] is True
    assert fabricated.composite == 0.0
    assert honest.composite > fabricated.composite


def test_honest_beats_url_stuffing_and_verbose_copy(tmp_path: Path):
    config = _task_config(tmp_path)
    evaluator = _evaluator(config)
    honest = evaluator.evaluate_rollout(_rollout())
    assert honest.composite >= 0.5
    assert honest.per_dim["coverage"] > 0.0

    fake_links = " ".join(
        f"[fake{i}](http://localhost:7770/zzz-fabricated-{i}.html)"
        for i in range(200)
    )
    stuffed = evaluator.evaluate_rollout(_rollout(_report() + "\n\n" + fake_links))
    assert stuffed.reward_terms["penalties"]["p_fabricate"] > 0.0
    assert honest.composite > stuffed.composite

    verbose_report = _report() + "\n\n" + ("balanced sound battery comfort value " * 100)
    verbose = evaluator.evaluate_rollout(_rollout(verbose_report))
    assert verbose.reward_terms["penalties"]["p_verbose"] > 0.0
    assert honest.composite > verbose.composite


def test_rollout_reward_is_deterministic(tmp_path: Path):
    evaluator = _evaluator(_task_config(tmp_path))
    rollout = _rollout()
    first = evaluator.evaluate_rollout(rollout).to_dict()
    second = evaluator.evaluate_rollout(rollout).to_dict()
    assert first == second


def test_degraded_empty_trace_is_finite_not_frozen(tmp_path: Path):
    config = _task_config(tmp_path)
    config["markdown_spec"]["min_citations"] = 0
    report = (
        "# No Citation Report\n\n"
        "This answer has enough words and paragraphs for a structural check "
        "but it intentionally does not cite any sandbox source.\n\n"
        "It exists only to exercise degraded signal handling without the "
        "fabrication nullifier."
    )
    evaluator = _evaluator(config)
    degraded = evaluator.evaluate_rollout(_rollout(report, store=False, calls=False))
    honest = evaluator.evaluate_rollout(_rollout())
    assert degraded.signal_health == "degraded"
    assert degraded.reward_terms["process"]["R_process"] == 0.0
    assert degraded.reward_terms["penalties"]["nullify"] is False
    assert 0.0 <= degraded.composite <= 1.0
    assert degraded.composite != honest.composite


def test_full_mode_evaluate_output_unchanged_shape(tmp_path: Path, monkeypatch):
    async def fake_judges(self, task_config, report_md):
        return {
            "depth": (0.7, {}, None),
            "rigor": (0.6, {}, None),
            "style": (0.8, {}, None),
            "checklist": (0.9, {}, None),
        }

    async def fake_policy(self, task_config, report_md, trace):
        return 0.6, 0.6

    monkeypatch.setattr(ArenaEvaluator, "_run_judge_dims_async", fake_judges)
    monkeypatch.setattr(ArenaEvaluator, "_compute_policy_signals", fake_policy)

    result = _evaluator(_task_config(tmp_path), mode="full").evaluate(_report()).to_dict()
    assert result == {
        "composite": 0.656,
        "breakdown": {
            "reach_soft": 0.8,
            "q_value": 0.82,
            "per_dim_contribution": {
                "coverage": 0.2,
                "depth": 0.14,
                "rigor": 0.12,
                "style": 0.08,
                "checklist": 0.18,
                "spec": 0.1,
            },
            "composite": 0.656,
        },
        "per_dim": {
            "coverage": 1.0,
            "depth": 0.7,
            "rigor": 0.6,
            "style": 0.8,
            "checklist": 0.9,
            "spec": 1.0,
        },
        "policy": {
            "sandbox_violations": 0,
            "reachability": 0.6,
            "quote_match": 0.6,
        },
        "mode": "full",
        "judge_errors": [],
    }
    assert "signal_health" not in result
    assert "reward_terms" not in result


def test_composite_v3_softfloor_fixed_score_unchanged():
    score = {
        "coverage": 1.0,
        "depth": 0.5,
        "rigor": 0.25,
        "style": 0.75,
        "checklist": 0.5,
        "spec": 1.0,
        "quote_match": {"score": 0.8},
    }
    expected_q = 0.2 + 0.1 + 0.05 + 0.075 + 0.1 + 0.1
    assert math.isclose(composite_v3_softfloor(score), 0.9 * expected_q)
