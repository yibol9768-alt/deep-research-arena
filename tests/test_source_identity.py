"""A source answers only to the origin it knows itself by.

The gateway dials Magento over the compose network as `http://shopping:80`.
Magento's base_url is `http://localhost:7770`. Magento answers a request whose
Host is not its base_url with a 302 to that base_url, dropping the query string,
and `localhost:7770` is a closed port inside the container. `_search_shopping`
followed the redirect, took the ConnectionError, and returned `[]`. The guard
was `if r.status_code >= 400`, which a 302 never trips, so the store never once
reported that it had been asked.

The store was therefore never searched, on any stack, in the whole life of the
project -- including the canonical release compose, which sets
`SHOPPING: "http://shopping:80"` at `infra/release/compose.yml:68` against a
store whose base_url is 7770. `fact` grades price and rating claims that only the
store can support. It read ~0 on 99% of reports. That was written off as the cost
of decidable scoring; it was a redirect.

Every test in this repo ran with the dial address equal to the public identity,
where no redirect happens. None of them could see this. These two can: the stub
below behaves like Magento, refusing any Host but its base_url.
"""

from __future__ import annotations

import http.server
import pathlib
import socketserver
import sys
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.search_shim import backend  # noqa: E402
from integrations.search_shim import app as shim_app  # noqa: E402

DIAL_PORT = 8791          # stands in for `shopping:80` on the compose network
PUBLIC_PORT = 8792        # stands in for `localhost:7770`; nothing listens here

GRID = (
    '<html><body><ol class="products list items product-items">'
    '<li class="item product product-item">'
    '<strong class="product name product-item-name">'
    f'<a class="product-item-link" href="http://localhost:{PUBLIC_PORT}/sony-xm4.html">'
    "Sony WH-1000XM4</a></strong>"
    '<span data-price-amount="279.99"></span>'
    "</li></ol></body></html>"
).encode()


class _Magento(http.server.BaseHTTPRequestHandler):
    """Serves the grid to its base_url, redirects everyone else and drops ?q."""

    def do_GET(self):  # noqa: N802
        if self.headers.get("Host") != f"localhost:{PUBLIC_PORT}":
            self.send_response(302)
            self.send_header(
                "Location", f"http://localhost:{PUBLIC_PORT}/catalogsearch/result/")
            self.end_headers()
            return
        if self.path == "/canon":
            # Same-origin canonicalisation, relative Location, as the forum does.
            self.send_response(302)
            self.send_header("Location", "/catalogsearch/result/?q=headphones")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(GRID)))
        self.end_headers()
        self.wfile.write(GRID)

    def log_message(self, *a):  # silence
        pass


@pytest.fixture(scope="module")
def store():
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", DIAL_PORT), _Magento)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield
    srv.shutdown()


@pytest.fixture(autouse=True)
def _clean_diag():
    backend._diag_store().clear()


def test_store_is_searchable_when_told_the_origin_it_answers_to(store, monkeypatch):
    monkeypatch.setattr(backend, "SHOPPING", f"http://127.0.0.1:{DIAL_PORT}")
    monkeypatch.setattr(backend, "SHOPPING_PUBLIC", f"http://localhost:{PUBLIC_PORT}")

    hits = backend._search_shopping("headphones", 5)

    assert hits, "the store answered nothing; `fact` has no source and reads 0"
    assert backend.last_source_diag().get("shopping", {}).get("error") is None
    # The agent must receive a URL it can open and the registry blesses, not the
    # compose-internal dial address.
    assert hits[0].url == f"http://localhost:{PUBLIC_PORT}/sony-xm4.html"


def test_a_redirect_is_reported_not_silently_returned_as_no_results(store, monkeypatch):
    """The production misconfiguration, reproduced.

    Dial address doubles as the public identity, so no Host is sent, so Magento
    redirects. The old code followed that into a closed port and returned `[]`,
    which is byte-for-byte what "this query matched no product" looks like.
    """
    monkeypatch.setattr(backend, "SHOPPING", f"http://127.0.0.1:{DIAL_PORT}")
    monkeypatch.setattr(backend, "SHOPPING_PUBLIC", f"http://127.0.0.1:{DIAL_PORT}")

    hits = backend._search_shopping("headphones", 5)

    assert hits == []
    err = backend.last_source_diag()["shopping"]["error"]
    assert err, "a dead source and an empty result set produced identical data"
    assert "302" in err and "SHOPPING_PUBLIC" in err, err


def test_same_origin_redirect_is_followed_not_treated_as_a_fault(store, monkeypatch):
    """The forum canonicalises `/f/<name>/new.atom` with a relative 302.

    A blanket "any 3xx is a misconfiguration" rule silently drops every board
    that needs canonicalising: the source still answers, with fewer results, and
    nothing says so. That is the same shape as the store bug, introduced by the
    fix for the store bug. It was caught by probing the live sandbox, not by any
    unit test.
    """
    monkeypatch.setattr(backend, "SHOPPING", f"http://localhost:{PUBLIC_PORT}")
    monkeypatch.setattr(backend, "SHOPPING_PUBLIC", f"http://localhost:{PUBLIC_PORT}")

    # `_Magento` only serves Host localhost:PUBLIC_PORT, and _canon 302s to a
    # relative path on the same origin.
    r = backend._get_source("shopping", f"http://127.0.0.1:{DIAL_PORT}",
                            f"http://localhost:{PUBLIC_PORT}", "/canon")
    assert r is not None and r.status_code == 200, \
        backend.last_source_diag().get("shopping")
    assert b"product-item-link" in r.content


def test_public_origin_is_allowlisted_or_the_agent_cannot_open_what_it_finds(monkeypatch):
    """Hits at the public origin are worthless if the shim's own gate blocks them."""
    monkeypatch.setattr(backend, "SHOPPING", "http://shopping:80")
    monkeypatch.setattr(backend, "SHOPPING_PUBLIC", "http://localhost:7770")

    hosts = backend._allowlist_hosts()

    assert "localhost:7770" in hosts
    assert "shopping:80" in hosts


@pytest.mark.parametrize("source", ["SHOPPING", "REDDIT", "KIWIX"])
@pytest.mark.parametrize("href_kind", ["relative", "absolute"])
def test_every_source_emits_public_identity_for_relative_and_absolute_links(
    monkeypatch, source, href_kind
):
    dial = f"http://dial-{source.lower()}:80"
    public = f"http://public-{source.lower()}:7777"
    monkeypatch.setattr(backend, source, dial)
    monkeypatch.setattr(backend, f"{source}_PUBLIC", public)
    href = "/article?q=1" if href_kind == "relative" else f"{dial}/article?q=1"
    assert backend._public_link(href, public) == f"{public}/article?q=1"


@pytest.mark.parametrize("source", ["SHOPPING", "REDDIT", "KIWIX"])
@pytest.mark.parametrize("entrypoint", ["fetch", "extract", "product_lookup"])
def test_three_page_read_entrypoints_route_each_source_but_record_public(
    monkeypatch, source, entrypoint
):
    """3 entrypoints x 3 sources: transport identity and evidence identity differ."""
    dial = f"http://dial-{source.lower()}:80"
    public = f"http://public-{source.lower()}:7777"
    public_url = f"{public}/page.html"
    dial_url = f"{dial}/page.html"
    monkeypatch.setattr(backend, source, dial)
    monkeypatch.setattr(backend, f"{source}_PUBLIC", public)
    monkeypatch.delenv("SHIM_MODE", raising=False)

    seen = []
    html = (
        '<html><body><main><h1>Page</h1><span itemprop="name">Page</span>'
        '<span data-price-amount="12.34"></span>body</main></body></html>'
    )

    def fake_get(url, **kwargs):
        seen.append((url, kwargs))
        return SimpleNamespace(
            status_code=200,
            url=url,
            text=html,
            content=html.encode(),
            headers={"content-type": "text/html"},
        )

    monkeypatch.setattr(backend.requests, "get", fake_get)
    monkeypatch.setattr(shim_app.httpx, "get", fake_get)
    recorded = []
    monkeypatch.setattr(
        shim_app.evidence,
        "record_fetch",
        lambda url, status, body, **kw: recorded.append((url, status, kw)),
    )
    client = TestClient(shim_app.app)
    if entrypoint == "fetch":
        response = client.get("/fetch", params={"url": public_url})
    elif entrypoint == "extract":
        response = client.post("/extract", json={"urls": [public_url]})
    else:
        response = client.post("/product_lookup", json={"url": public_url})

    assert response.status_code == 200, response.text
    assert seen and seen[0][0] == dial_url
    assert seen[0][1]["headers"]["Host"] == f"public-{source.lower()}:7777"
    assert recorded and recorded[0][0] == public_url
    assert all(dial not in rec[0] for rec in recorded)
