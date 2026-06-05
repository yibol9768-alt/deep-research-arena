"""Transparent sandbox HTTP cache for scoring.

Scoring a report fetches every cited sandbox URL multiple times (reachability,
quote-match, citation-alignment, factual-exactness all call ``requests.get``),
and popular URLs are re-fetched across all ~900 reports. Magento PHP-FPM resets
under that concurrent load, so a bulk re-score times out.

This installs a process-wide ``requests.get`` shim that serves a pre-built
{url: {status, text}} cache (data/results/sandbox_cache.json, built once by
scripts/build_sandbox_cache.py with redirects followed). On a cache hit it
returns a lightweight fake Response; on a miss it falls through to the real
``requests.get`` (and records the result so the cache self-extends). This makes
re-scoring fast AND reproducible: the cache is a frozen snapshot of the sandbox
pages, so anyone can re-score offline without a live Magento.

Activate by setting ``DRA_SANDBOX_CACHE=/path/to/sandbox_cache.json`` and calling
``install()`` once (score_deep_answer does this automatically when the env is set).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_LOCK = threading.Lock()
_INSTALLED = False
_CACHE: dict[str, dict] = {}
_CACHE_PATH: Path | None = None
_DIRTY = False


class _FakeResponse:
    """Minimal requests.Response stand-in covering what the verifiers use."""

    def __init__(self, url: str, status: int, text: str):
        self.url = url
        self.status_code = int(status)
        self._text = text or ""
        self.headers = {}
        self.encoding = "utf-8"

    @property
    def text(self) -> str:
        return self._text

    @property
    def content(self) -> bytes:
        return self._text.encode("utf-8", "ignore")

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400

    def json(self):
        return json.loads(self._text)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} for {self.url}")

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_content(self, chunk_size=1):
        yield self.content


def _key(url: str) -> str:
    return (url or "").strip()


def install(cache_path: str | None = None, store_text: bool = True) -> bool:
    """Monkeypatch requests.get to serve the cache. Idempotent. Returns True if active."""
    global _INSTALLED, _CACHE, _CACHE_PATH
    if _INSTALLED:
        return True
    path = cache_path or os.environ.get("DRA_SANDBOX_CACHE")
    if not path:
        return False
    _CACHE_PATH = Path(path)
    if _CACHE_PATH.exists():
        try:
            _CACHE = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {}
    import requests
    _real_get = requests.get

    def _cached_get(url, *args, **kwargs):
        k = _key(url)
        hit = _CACHE.get(k)
        if hit is not None:
            return _FakeResponse(url, hit.get("status", 0), hit.get("text", "") if store_text else "")
        # miss: real fetch, then record (cap text so the cache stays modest)
        try:
            r = _real_get(url, *args, **kwargs)
        except Exception:
            with _LOCK:
                _CACHE[k] = {"status": 0, "text": ""}
            raise
        try:
            txt = r.text if store_text else ""
        except Exception:
            txt = ""
        with _LOCK:
            global _DIRTY
            _CACHE[k] = {"status": int(getattr(r, "status_code", 0)), "text": (txt or "")[:40000]}
            _DIRTY = True
        return r

    requests.get = _cached_get
    _INSTALLED = True
    return True


def flush() -> None:
    """Persist any cache misses fetched live (so the cache self-extends)."""
    global _DIRTY
    if _CACHE_PATH is None or not _DIRTY:
        return
    with _LOCK:
        tmp = _CACHE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_CACHE), encoding="utf-8")
        tmp.replace(_CACHE_PATH)
        _DIRTY = False
