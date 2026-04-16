"""Unit tests for deep-research verifiers (no browser / no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.verifiers import ReportVerifier, CitationVerifier


# ---------- ReportVerifier ----------

def _rtask(**extra):
    base = {
        "report_schema": {
            "type": "object",
            "properties": {
                "products": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "price", "rating"],
                        "properties": {
                            "name": {"type": "string"},
                            "price": {"type": "number"},
                            "rating": {"type": "number"},
                        },
                    },
                },
            },
            "required": ["products"],
        },
        "eval": {
            "eval_types": ["report_match"],
            "report_expected": {
                "products": [
                    {"name_contains": ["Blue", "Jacket"], "price_range": [50, 150], "rating_min": 4.0}
                ]
            },
        },
    }
    base.update(extra)
    return base


def test_report_match_pass():
    ans = json.dumps({"products": [{"name": "Navy Blue Winter Jacket", "price": 99.9, "rating": 4.5}]})
    r = ReportVerifier().verify(task_config=_rtask(), answer=ans)
    assert r.passed, r.details


def test_report_match_missing_name_token():
    ans = json.dumps({"products": [{"name": "Red Coat", "price": 99.9, "rating": 4.5}]})
    r = ReportVerifier().verify(task_config=_rtask(), answer=ans)
    assert not r.passed


def test_report_match_price_out_of_range():
    ans = json.dumps({"products": [{"name": "Blue Jacket", "price": 999.0, "rating": 4.5}]})
    r = ReportVerifier().verify(task_config=_rtask(), answer=ans)
    assert not r.passed


def test_report_match_answer_not_json():
    r = ReportVerifier().verify(task_config=_rtask(), answer="I am a prose answer")
    assert not r.passed


def test_report_match_accepts_markdown_fence():
    ans = "```json\n" + json.dumps({"products": [{"name": "Royal Blue Jacket", "price": 88, "rating": 4.8}]}) + "\n```"
    r = ReportVerifier().verify(task_config=_rtask(), answer=ans)
    assert r.passed


# ---------- CitationVerifier ----------

class FakeResp:
    def __init__(self, status: int, body: str = "") -> None:
        self.status = status
        self._body = body

    def text(self):
        return self._body


class FakeReq:
    def __init__(self, responses: dict[str, FakeResp]) -> None:
        self._responses = responses

    def get(self, url: str, timeout: int = 0):
        return self._responses.get(url, FakeResp(0))


class FakePage:
    def __init__(self, responses: dict[str, FakeResp]) -> None:
        self.request = FakeReq(responses)


def _ctask():
    return {
        "start_url": "http://shop.local/",
        "citation_policy": {
            "required_for": ["products[*].price"],
            "must_be_in_domain": ["http://shop.local"],
            "min_distinct_sources": 2,
        },
        "eval": {"eval_types": ["citation_check"]},
    }


def test_citation_pass_shape_b():
    ans = json.dumps({
        "products": [
            {"name": "A", "price": 10},
            {"name": "B", "price": 20},
        ],
        "citations": [
            {"field": "products[0].price", "url": "http://shop.local/p/1", "snippet": "10"},
            {"field": "products[1].price", "url": "http://shop.local/p/2", "snippet": "20"},
        ],
    })
    page = FakePage({
        "http://shop.local/p/1": FakeResp(200, "price is 10 dollars"),
        "http://shop.local/p/2": FakeResp(200, "price is 20 dollars"),
    })
    r = CitationVerifier().verify(task_config=_ctask(), answer=ans, page=page)
    assert r.passed, r.details


def test_citation_missing_required():
    ans = json.dumps({
        "products": [{"name": "A", "price": 10}],
        "citations": [],
    })
    page = FakePage({})
    r = CitationVerifier().verify(task_config=_ctask(), answer=ans, page=page)
    assert not r.passed


def test_citation_unreachable_url():
    ans = json.dumps({
        "products": [{"name": "A", "price": 10}, {"name": "B", "price": 20}],
        "citations": [
            {"field": "products[0].price", "url": "http://shop.local/p/1"},
            {"field": "products[1].price", "url": "http://shop.local/p/404"},
        ],
    })
    page = FakePage({
        "http://shop.local/p/1": FakeResp(200, "10"),
        "http://shop.local/p/404": FakeResp(404, "gone"),
    })
    r = CitationVerifier().verify(task_config=_ctask(), answer=ans, page=page)
    assert not r.passed


def test_citation_precision_value_mismatch():
    """Citation URL reachable but page content doesn't support the claim → both precision and recall drop."""
    ans = json.dumps({
        "products": [{"name": "A", "price": 999.0}, {"name": "B", "price": 888.0}],
        "citations": [
            {"field": "products[0].price", "url": "http://shop.local/p/1"},
            {"field": "products[1].price", "url": "http://shop.local/p/2"},
        ],
    })
    # Body mentions $10/$20 — but report claims $999/$888 → no citation supported
    page = FakePage({
        "http://shop.local/p/1": FakeResp(200, "price is 10 dollars"),
        "http://shop.local/p/2": FakeResp(200, "price is 20 dollars"),
    })
    r = CitationVerifier().verify(task_config=_ctask(), answer=ans, page=page)
    assert r.details["citation_precision"] == 0.0
    # New semantic: recall requires SUPPORTED citations, not just present ones
    assert r.details["citation_recall"] == 0.0
    assert not r.passed


def test_citation_prose_link_text_tokens_match_body():
    """DeerFlow-style markdown: link-text tokens must appear on the fetched page."""
    ans = (
        "# Report\n\n"
        "Top pick: [Harphonic E7 Headphones](http://shop.local/p/1) — great pick.\n"
        "Runner-up: [Sony WH-1000XM4](http://shop.local/p/2) for premium buyers.\n"
    )
    # Bodies contain the link-text tokens → supported
    page = FakePage({
        "http://shop.local/p/1": FakeResp(200, "Harphonic E7 Headphones product description ..."),
        "http://shop.local/p/2": FakeResp(200, "Sony WH-1000XM4 Wireless Noise Canceling Headphones ..."),
    })
    r = CitationVerifier().verify(task_config=_ctask(), answer=ans, page=page)
    assert r.details["prose_mode"] is True
    assert r.details["total_citations"] == 2
    assert r.details["citation_precision"] == 1.0


def test_citation_prose_unrelated_urls_fail():
    """Prose mode: URL reachable but link text doesn't match page body → NOT supported."""
    ans = (
        "# Report\n\n"
        "Top pick: [Harphonic E7](http://shop.local/p/1) is great.\n"
    )
    # Body about a completely different product
    page = FakePage({
        "http://shop.local/p/1": FakeResp(200, "Amazon Basics USB Charging Cable — 6ft"),
    })
    r = CitationVerifier().verify(task_config=_ctask(), answer=ans, page=page)
    assert r.details["prose_mode"] is True
    assert r.details["citation_precision"] == 0.0  # no token overlap
    assert r.details["citation_recall"] == 0.0


def test_citation_out_of_domain():
    ans = json.dumps({
        "products": [{"name": "A", "price": 10}, {"name": "B", "price": 20}],
        "citations": [
            {"field": "products[0].price", "url": "http://shop.local/p/1"},
            {"field": "products[1].price", "url": "http://evil.com/p/2"},
        ],
    })
    page = FakePage({"http://shop.local/p/1": FakeResp(200, "10")})
    r = CitationVerifier().verify(task_config=_ctask(), answer=ans, page=page)
    assert not r.passed
