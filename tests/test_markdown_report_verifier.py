"""Tests for MarkdownReportVerifier — v3 structural floor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.verifiers.markdown_report_verifier import MarkdownReportVerifier


ROOT = Path(__file__).resolve().parents[1]


def _cfg(**md_spec):
    return {
        "markdown_spec": md_spec,
        "citation_policy": {"must_be_in_domain": ["__SHOPPING__"]},
    }


def test_all_floors_pass_on_rich_report():
    ans = (
        "# Report\n\nParagraph one with a link [prod](http://localhost:7770/a.html).\n\n"
        "Paragraph two also cites [b](http://localhost:7770/b.html) and [c](http://localhost:7770/c.html).\n\n"
        + ("This is paragraph three with more words to meet word floor. " * 30)
        + "\n\nParagraph four closes the report.\n"
    )
    cfg = _cfg(min_words=120, max_words=2000, min_paragraphs=3, min_citations=3, min_pages_browsed=0)
    r = MarkdownReportVerifier().verify(task_config=cfg, answer=ans)
    assert r.passed, r.details
    assert r.score == 1.0


def test_word_floor_fails():
    r = MarkdownReportVerifier().verify(
        task_config=_cfg(min_words=500, min_paragraphs=1, min_citations=0),
        answer="tiny report.",
    )
    assert r.score < 1.0
    assert r.details["checks"]["min_words"] == 0.0


def test_max_words_fails_on_bloat():
    long = ("word " * 3000)
    r = MarkdownReportVerifier().verify(
        task_config=_cfg(min_words=1, max_words=200, min_paragraphs=1, min_citations=0),
        answer=long,
    )
    # 3000 words vs cap=200 is 14× over → well beyond the 20% tolerance → 0.
    assert r.details["checks"]["max_words"] == 0.0


def test_max_words_soft_near_cap_keeps_most_credit():
    # 1% over the cap should keep almost full credit — a binary fail would
    # be too punitive for such a small overage (regression fix for DeerFlow
    # 0007 where 3504 / 3500 gave score 0.80 = 4/5 binary checks).
    ans = ("word " * 101) + "."  # ~101 words
    r = MarkdownReportVerifier().verify(
        task_config=_cfg(min_words=1, max_words=100, min_paragraphs=1, min_citations=0),
        answer=ans,
    )
    # 101/100 = 1.01 over, 1% / 20% tolerance → 0.95 credit
    assert 0.94 <= r.details["checks"]["max_words"] <= 1.0
    # 10% over gets mid-range credit
    ans2 = ("word " * 110) + "."
    r2 = MarkdownReportVerifier().verify(
        task_config=_cfg(min_words=1, max_words=100, min_paragraphs=1, min_citations=0),
        answer=ans2,
    )
    assert 0.4 <= r2.details["checks"]["max_words"] <= 0.55


def test_citation_counting_uses_domain_whitelist():
    ans = "See [bad](http://evil.example.com) and [good](http://localhost:7770/x.html)."
    r = MarkdownReportVerifier().verify(
        task_config=_cfg(min_words=1, min_paragraphs=1, min_citations=1),
        answer=ans,
    )
    assert r.details["citations"] == 1  # only the localhost link counts


def test_paragraph_counting():
    ans = "Para 1.\n\nPara 2.\n\nPara 3."
    r = MarkdownReportVerifier().verify(
        task_config=_cfg(min_words=1, min_paragraphs=3, min_citations=0),
        answer=ans,
    )
    assert r.details["paragraphs"] == 3


def test_pages_browsed_passes_when_unknown():
    # If runner didn't attach it, don't penalize the agent.
    r = MarkdownReportVerifier().verify(
        task_config=_cfg(min_words=1, min_paragraphs=1, min_citations=0, min_pages_browsed=5),
        answer="hi",
    )
    assert r.details["checks"]["min_pages_browsed"] == 1.0


def test_skip_when_no_spec():
    r = MarkdownReportVerifier().verify(
        task_config={"foo": "bar"},
        answer="anything",
    )
    assert r.passed and r.score == 1.0


def test_reddit_domain_translation():
    ans = "Link [post](http://localhost:9999/f/news/x)."
    cfg = {
        "markdown_spec": {"min_words": 1, "min_paragraphs": 1, "min_citations": 1},
        "citation_policy": {"must_be_in_domain": ["__REDDIT__"]},
    }
    r = MarkdownReportVerifier().verify(task_config=cfg, answer=ans)
    assert r.details["citations"] == 1
