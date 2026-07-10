"""Forum search must query the full Postmill index, not recent feeds only."""

from __future__ import annotations

from types import SimpleNamespace

from integrations.search_shim import backend


HTML = """
<article class="submission submission--expanded">
  <a class="submission__link" href="https://example.invalid/review">Old burr grinder review</a>
  <a class="submission__forum" href="/f/food">food</a>
  <a class="text-sm" href="/f/food/42/old-burr-grinder-review">12 comments</a>
  <div class="submission__body">Coffee grinder burrs stayed aligned for five years.</div>
</article>
<article class="submission submission--expanded">
  <a class="submission__link" href="/f/BuyItForLife/7/durable-coffee-grinder">Durable coffee grinder</a>
  <a class="submission__forum" href="/f/BuyItForLife">BuyItForLife</a>
  <a class="text-sm" href="/f/BuyItForLife/7/durable-coffee-grinder">3 comments</a>
  <div class="submission__body">A repairable burr mechanism matters.</div>
</article>
"""


def test_full_index_results_include_old_task_forums(monkeypatch):
    calls = []

    def get_source(source, base, public, path, **kwargs):
        calls.append((source, path, kwargs.get("params")))
        assert path == "/search", "recent-feed fallback should not run when index is full"
        return SimpleNamespace(text=HTML, status_code=200)

    monkeypatch.setattr(backend, "_get_source", get_source)
    hits = backend._search_reddit("coffee grinder burr", 2)

    assert calls[0] == ("forum", "/search", {"q": "coffee grinder burr"})
    assert all(source == "forum" and path == "/search"
               for source, path, _params in calls)
    assert [h.url for h in hits] == [
        "http://localhost:9999/f/food/42/old-burr-grinder-review",
        "http://localhost:9999/f/BuyItForLife/7/durable-coffee-grinder",
    ]
    assert all(h.source == "reddit" for h in hits)
    assert "five years" in hits[0].raw_content


def test_zero_result_and_query_relaxes_without_accepting_off_topic_rows(monkeypatch):
    calls = []

    def get_source(source, base, public, path, **kwargs):
        q = kwargs.get("params", {}).get("q")
        calls.append(q)
        text = HTML if q == "coffee grinder" else "<html><body>No results</body></html>"
        return SimpleNamespace(text=text, status_code=200)

    monkeypatch.setattr(backend, "_get_source", get_source)
    hits = backend._search_reddit("coffee grinder burr durability", 2)

    assert calls[:2] == ["coffee grinder burr durability", "coffee grinder"]
    assert set(calls[2:]) >= {"coffee", "grinder"}
    assert len(hits) == 2
    assert {h.url.split("/f/", 1)[1].split("/", 1)[0] for h in hits} \
        == {"food", "BuyItForLife"}
