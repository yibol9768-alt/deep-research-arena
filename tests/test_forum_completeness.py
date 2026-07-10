"""Forum evidence is a real completeness requirement, not a URL-count shell."""

from __future__ import annotations

from types import SimpleNamespace

from scripts.build_answer_keys_v2 import build_key
from src.eval.answer_key import AnswerKey
from src.eval.decidable_scorer import score_completeness
from src.eval.url_registry import UrlRegistry


FORUM_URL = "http://localhost:9999/f/headphones/20234"
PAGE = (
    "Owners say active noise cancellation helps bus commuters and noisy office "
    "workers. Long listening sessions can still feel uncomfortable."
)
REPORT = (
    "Owners say [active noise cancellation helps bus commuters and noisy office "
    f"workers]({FORUM_URL})."
)


def _key() -> AnswerKey:
    return AnswerKey(
        task_id="forum-test",
        metadata={
            "forums": ["headphones"],
            "forum_core_keywords": ["headphones", "audio"],
            "forum_query_keywords": ["noise", "cancellation", "bus", "office"],
        },
    )


def _score(report: str, page: str = PAGE, fetched: bool = True):
    evidence = SimpleNamespace(
        available=True,
        fetched_ok={FORUM_URL} if fetched else set(),
    )
    return score_completeness(
        report,
        _key(),
        cache={FORUM_URL: {"status": 200, "text": page}},
        registry=UrlRegistry.load(),
        evidence=evidence,
    )


def test_fetched_on_topic_quoted_thread_covers_virtual_forum_slot():
    score, detail = _score(REPORT)
    assert score == 1.0
    assert detail["forum_slots"] == 1
    assert detail["forum_covered"] is True
    assert detail["covered_by_predicate"] == {"forum_coverage": 1}


def test_unfetched_forum_citation_gets_no_credit():
    score, detail = _score(REPORT, fetched=False)
    assert score == 0.0
    assert detail["forum_covered"] is False


def test_quoted_but_off_topic_thread_gets_no_credit():
    off_topic = "Owners discuss a birthday party and a garden renovation project."
    report = f"[Owners discuss a birthday party and garden renovation]({FORUM_URL})."
    score, detail = _score(report, page=off_topic)
    assert score == 0.0
    assert detail["forum_covered"] is False


def test_reference_list_url_shell_gets_no_credit():
    report = f"## References\n\n- [active noise cancellation helps bus commuters]({FORUM_URL})"
    score, detail = _score(report)
    assert score == 0.0
    assert detail["forum_covered"] is False


def test_builder_persists_declared_forums_and_relevance_terms():
    key = build_key(
        "t",
        {
            "cluster": "headphones_audio",
            "angle": "bus headphones with active noise cancellation",
            "forums": ["headphones", "technology"],
            "wiki_topics": [],
            "intent": "Which headphones work on a noisy bus?",
        },
        [],
        {},
    )
    assert key.metadata["forums"] == ["headphones", "technology"]
    assert key.metadata["forum_core_keywords"] == ["audio", "headphones"]
    assert "noise" in key.metadata["forum_query_keywords"]
