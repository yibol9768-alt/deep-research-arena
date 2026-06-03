"""Offline tests for the Kiwix canonicalization fairness fix (BUG A).

Goldset matching canonicalizes Kiwix `/wiki/<id>` URLs to
`/content/wikipedia_en_all_nopic/A/<id>`, but the proof-of-fetch verifiers
probe the RAW URL as the agent emitted it. Kiwix serves only the `/content/...`
form, so a legitimate `localhost:8090/wiki/<id>` citation 404s on the raw probe
and was wrongly scored unsupported/unreachable.

These tests mock `requests` (no network) and assert that when the raw URL
returns non-200 the verifier retries the canonicalized Kiwix form before
declaring the URL unreachable, while URLs that already resolve are NOT
double-probed.
"""

from __future__ import annotations

import sys
import types

import pytest

from src.verifiers import quote_match_verifier as qmv
from src.verifiers import url_reachability_verifier as urv
from src.verifiers.citation_format import canonicalize_url


RAW = "http://localhost:8090/wiki/Microplastics"
CANON = canonicalize_url(RAW)  # -> http://localhost:8090/content/wikipedia_en_all_nopic/A/microplastics


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def close(self) -> None:  # url_reachability uses stream=True + close()
        pass


def _install_fake_requests(monkeypatch, status_by_url, calls):
    """Install a fake `requests` module whose GET returns a status per URL.

    `status_by_url`: dict mapping exact URL -> (status_code, body). Any URL not
    present returns 404. `calls` is a list the fake appends each requested URL
    to, so tests can assert the probe order / that resolving URLs aren't
    re-probed.
    """
    fake = types.ModuleType("requests")

    def _get(url, *a, **kw):
        calls.append(url)
        status, body = status_by_url.get(url, (404, ""))
        return _Resp(status, body)

    fake.get = _get
    monkeypatch.setitem(sys.modules, "requests", fake)
    return fake


# --------------------------------------------------------------------------- #
# url_reachability._probe
# --------------------------------------------------------------------------- #
def test_probe_retries_canonical_kiwix_on_404(monkeypatch):
    calls: list[str] = []
    _install_fake_requests(
        monkeypatch,
        {RAW: (404, ""), CANON: (200, "")},
        calls,
    )
    code = urv._probe(RAW, timeout=0.1, retries=1)
    assert code == 200, "canonical /content/... form should resolve the 404"
    assert calls == [RAW, CANON], "raw probed first, then the canonical variant"


def test_probe_does_not_double_probe_resolving_url(monkeypatch):
    calls: list[str] = []
    _install_fake_requests(monkeypatch, {RAW: (200, "")}, calls)
    code = urv._probe(RAW, timeout=0.1, retries=1)
    assert code == 200
    assert calls == [RAW], "a URL that already resolves must not be re-probed"


def test_probe_returns_raw_status_when_canonical_is_noop(monkeypatch):
    # A non-Kiwix URL that 404s: canonicalize_url is effectively a no-op (same
    # host/path), so no second probe and the raw 404 is reported.
    other = "http://localhost:7770/catalog/missing"
    calls: list[str] = []
    _install_fake_requests(monkeypatch, {}, calls)  # everything 404
    code = urv._probe(other, timeout=0.1, retries=1)
    assert code == 404
    assert calls == [other], "non-Kiwix 404 should not trigger a variant probe"


# --------------------------------------------------------------------------- #
# quote_match._fetch
# --------------------------------------------------------------------------- #
def _install_fake_requests_and_bs4(monkeypatch, status_by_url, calls):
    _install_fake_requests(monkeypatch, status_by_url, calls)
    # quote_match also imports bs4. Provide a trivial fake that returns the
    # page body text unchanged.
    fake_bs4 = types.ModuleType("bs4")

    class _Soup:
        def __init__(self, text, parser):
            self._text = text

        def __call__(self, tags):  # soup(["script", ...]) -> iterable of tags
            return []

        def get_text(self, sep=" ", strip=True):
            return self._text

    fake_bs4.BeautifulSoup = _Soup
    monkeypatch.setitem(sys.modules, "bs4", fake_bs4)


def test_fetch_retries_canonical_kiwix_on_404(monkeypatch):
    calls: list[str] = []
    _install_fake_requests_and_bs4(
        monkeypatch,
        {RAW: (404, ""), CANON: (200, "microplastics are tiny plastic particles")},
        calls,
    )
    text = qmv._fetch(RAW, timeout=0.1, retries=0)
    assert text is not None
    assert "microplastics" in text
    assert calls == [RAW, CANON]


def test_fetch_does_not_double_probe_resolving_url(monkeypatch):
    calls: list[str] = []
    _install_fake_requests_and_bs4(
        monkeypatch, {RAW: (200, "body text here")}, calls,
    )
    text = qmv._fetch(RAW, timeout=0.1, retries=0)
    assert text == "body text here"
    assert calls == [RAW]
