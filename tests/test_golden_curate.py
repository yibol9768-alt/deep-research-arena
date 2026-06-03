"""Offline tests for the curated must-cite subset and its use in url_coverage.

Covers:
  (a) curate_must_cite picks the highest-weight / most-reviewed K;
  (b) a report citing the curated top-K scores high curated recall while full
      (whole-crawl) recall stays low;
  (c) URLCoverageVerifier reports BOTH recalls and the headline must_cite_recall
      is the curated one.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.verifiers.golden_curate import (
    curate_must_cite,
    curated_recall,
    _review_count,
    _has_star,
)
from src.verifiers.citation_format import canonicalize_url
from src.verifiers.url_coverage_verifier import URLCoverageVerifier

ROOT = Path(__file__).resolve().parents[1]


def _entry(url, weight, why=""):
    return {"url": url, "weight": weight, "why": why}


def test_review_count_and_star_parsing():
    assert _review_count("?: $14.95, 2.15★, 12 reviews") == 12
    assert _review_count("?: $9.99, 1 review") == 1
    assert _review_count("Aoutecen: $55.59") == 0
    assert _has_star("?: $14.95, 2.15★, 12 reviews") is True
    assert _has_star("?: $49.99") is False
    assert _has_star("?: 4.7 stars") is True


def test_curate_picks_highest_weight_then_reviews():
    entries = [
        _entry("http://h/a", 0.5, "?: $1, 5★, 99 reviews"),   # low weight, many reviews
        _entry("http://h/b", 1.0, "?: $2, 4★, 10 reviews"),
        _entry("http://h/c", 1.0, "?: $3, 4★, 50 reviews"),   # top: w1.0, most reviews
        _entry("http://h/d", 1.0, "?: $4"),                   # w1.0, no reviews, no star
        _entry("http://h/e", 0.6, "?: $5, 3★, 100 reviews"),
    ]
    top3 = curate_must_cite(entries, k=3)
    urls = [e["url"] for e in top3]
    # weight 1.0 entries come first; among them review-count desc: c(50) > b(10) > d(0)
    assert urls == ["http://h/c", "http://h/b", "http://h/d"]


def test_curate_star_tiebreak_and_stability():
    # same weight, same (zero) review count: star presence wins, then order.
    entries = [
        _entry("http://h/a", 1.0, "?: $1"),            # no star
        _entry("http://h/b", 1.0, "?: $2, 4★"),        # has star -> ranks above a
        _entry("http://h/c", 1.0, "?: $3"),            # no star, after a
    ]
    top = curate_must_cite(entries, k=3)
    assert [e["url"] for e in top] == ["http://h/b", "http://h/a", "http://h/c"]


def test_curate_k_bounds():
    entries = [_entry(f"http://h/{i}", 1.0, "") for i in range(5)]
    assert curate_must_cite(entries, k=12) == entries  # k > n returns all
    assert curate_must_cite(entries, k=0) == []
    assert curate_must_cite([], k=12) == []


def test_curated_recall_high_while_full_low():
    # 50-entry crawl: 12 high-value (w1.0 with reviews) + 38 filler (w0.5).
    must = []
    for i in range(12):
        must.append(_entry(f"http://localhost:7770/hi-{i}.html", 1.0,
                           f"?: $9, 4★, {100 - i} reviews"))
    for i in range(38):
        must.append(_entry(f"http://localhost:7770/lo-{i}.html", 0.5, "?: $1"))

    curated = curate_must_cite(must, k=12)
    # the curated set is exactly the 12 high-value entries
    assert {e["url"] for e in curated} == {e["url"] for e in must[:12]}

    # report cites ALL 12 curated URLs and nothing else
    cited = {canonicalize_url(e["url"]) for e in curated}
    cur = curated_recall(cited, must, k=12, canon=canonicalize_url)
    assert cur == 1.0

    # full weighted recall over the whole crawl stays low
    full_hit = sum(1.0 for _ in range(12))
    full_total = 12 * 1.0 + 38 * 0.5
    full = full_hit / full_total
    assert full < 0.40
    assert cur > full  # headline (curated) is far higher than full


def _write_golden(tmp_path):
    must = []
    for i in range(12):
        must.append(_entry(f"http://localhost:7770/hi-{i}.html", 1.0,
                           f"?: $9, 4★, {100 - i} reviews"))
    for i in range(38):
        must.append(_entry(f"http://localhost:7770/lo-{i}.html", 0.5, "?: $1"))
    pool = [{"url": e["url"]} for e in must] + [
        {"url": f"http://localhost:7770/pool-{i}.html"} for i in range(20)
    ]
    golden = {"must_cite_urls": must, "expected_pool_urls": pool}
    p = tmp_path / "golden.json"
    p.write_text(json.dumps(golden))
    return p, must


def test_url_coverage_reports_both_recalls_headline_is_curated(tmp_path):
    gp, must = _write_golden(tmp_path)
    curated = curate_must_cite(must, k=12)
    # report cites the 12 curated URLs
    md = "\n".join(f"See [product]({e['url']})" for e in curated)

    task = {"url_coverage": {"golden_pool_path": str(gp)}}
    res = URLCoverageVerifier().verify(task_config=task, answer=md, page=None)
    d = res.details

    # both recalls present
    assert "must_cite_recall" in d
    assert "must_cite_recall_full" in d
    assert "curated_must_cite_n" in d
    assert d["curated_must_cite_n"] == 12

    # headline == curated (high), full stays low
    assert d["must_cite_recall"] == 1.0
    assert d["must_cite_recall_full"] < 0.40
    assert d["must_cite_recall"] > d["must_cite_recall_full"]

    # prior detail keys preserved
    for key in ("cited_unique", "must_cite_total", "must_cite_hit",
                "pool_total", "pool_hit", "pool_coverage", "domain_balance",
                "threshold_must_cite_recall"):
        assert key in d

    # default gate lowered to 0.30 and now reachable
    assert d["threshold_must_cite_recall"] == 0.30
    assert res.passed is True


def test_url_coverage_k_and_gate_config_overridable(tmp_path):
    gp, must = _write_golden(tmp_path)
    curated6 = curate_must_cite(must, k=6)
    md = "\n".join(f"[p]({e['url']})" for e in curated6)  # cite only top-6

    # with curated_k=6 the report cites all 6 -> recall 1.0, passes gate 0.9
    task = {"url_coverage": {"golden_pool_path": str(gp),
                             "curated_k": 6,
                             "min_must_cite_recall": 0.9,
                             "min_expected_pool_coverage": 0.0}}
    res = URLCoverageVerifier().verify(task_config=task, answer=md, page=None)
    assert res.details["curated_must_cite_n"] == 6
    assert res.details["must_cite_recall"] == 1.0
    assert res.details["threshold_must_cite_recall"] == 0.9
    assert res.passed is True

    # with curated_k=12 the same 6-URL report only covers 6/12 -> 0.5 < 0.9 gate
    task2 = {"url_coverage": {"golden_pool_path": str(gp),
                              "curated_k": 12,
                              "min_must_cite_recall": 0.9,
                              "min_expected_pool_coverage": 0.0}}
    res2 = URLCoverageVerifier().verify(task_config=task2, answer=md, page=None)
    assert res2.details["curated_must_cite_n"] == 12
    assert res2.details["must_cite_recall"] == 0.5
    assert res2.passed is False


def test_real_golden_curated_beats_full():
    gp = ROOT / "data/golden/deep/dr_cross_deep_0001.json"
    md_path = ROOT / "data/results/deep/camel-ai__dr_cross_deep_0001_matrix.md"
    if not gp.exists() or not md_path.exists():
        import pytest
        pytest.skip("real golden / camel-ai report not present")
    task = {"url_coverage": {"golden_pool_path": str(gp)}}
    res = URLCoverageVerifier().verify(
        task_config=task, answer=md_path.read_text(), page=None
    )
    d = res.details
    assert d["curated_must_cite_n"] == 12
    # curated headline strictly exceeds full whole-crawl recall for camel-ai
    assert d["must_cite_recall"] > d["must_cite_recall_full"]
