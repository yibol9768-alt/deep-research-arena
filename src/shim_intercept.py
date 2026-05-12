"""HTTP-level request interception for deep-research framework integrations.

Instead of monkey-patching individual Python objects (TavilyClient, AsyncTavilyClient),
this module intercepts ALL outgoing HTTP requests at the transport layer:
  - requests.Session.send
  - httpx.AsyncClient._send_single_request / httpx.Client._send_single_request
  - aiohttp.ClientSession._request
  - urllib.request.urlopen

Any request to `api.tavily.com` is redirected to the local shim (default localhost:8081).
Any request to `en.wikipedia.org` is redirected to the local Kiwix instance.

Requests to localhost services (7770, 8081, 8088, 8090, 9999, etc.) and to
external APIs (api.deepseek.com, open.bigmodel.cn) are left untouched.

Usage:
    import src.shim_intercept          # auto-patches on import
    # OR
    from src.shim_intercept import install_all
    install_all()
"""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlparse, urlunparse, quote

logger = logging.getLogger("shim_intercept")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[shim_intercept] %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.DEBUG if os.environ.get("SHIM_INTERCEPT_DEBUG") else logging.INFO)

SHIM_URL = os.environ.get("SHIM_URL", "http://localhost:8081")
WIKIPEDIA_KIWIX_URL = os.environ.get("WIKIPEDIA_KIWIX_URL", "http://localhost:8090")

_INSTALLED = False


def _rewrite_url(url: str) -> str:
    """Rewrite a URL if it targets Tavily or Wikipedia, else return unchanged."""
    if not url:
        return url
    parsed = urlparse(url)
    host = parsed.hostname or ""

    # --- Tavily API interception ---
    if "api.tavily.com" in host:
        # Rewrite https://api.tavily.com/search -> http://localhost:8081/search
        shim_parsed = urlparse(SHIM_URL)
        new = parsed._replace(
            scheme=shim_parsed.scheme,
            netloc=shim_parsed.netloc,
        )
        new_url = urlunparse(new)
        logger.info("TAVILY intercept: %s -> %s", url[:120], new_url[:120])
        return new_url

    # --- Wikipedia interception ---
    if "en.wikipedia.org" in host:
        # e.g. https://en.wikipedia.org/wiki/Python_(programming_language)
        # ->   http://localhost:8090/content/wikipedia_en_all_nopic/A/Python_(programming_language)
        path = parsed.path  # /wiki/Title or /w/api.php etc.
        if path.startswith("/wiki/"):
            title = path[len("/wiki/"):]
            kiwix_parsed = urlparse(WIKIPEDIA_KIWIX_URL)
            new_path = f"/content/wikipedia_en_all_nopic/A/{title}"
            new = parsed._replace(
                scheme=kiwix_parsed.scheme,
                netloc=kiwix_parsed.netloc,
                path=new_path,
                query="",  # Kiwix doesn't use query params
            )
            new_url = urlunparse(new)
            logger.info("WIKIPEDIA intercept: %s -> %s", url[:120], new_url[:120])
            return new_url
        elif path.startswith("/w/api.php"):
            # MediaWiki API call -- redirect to Kiwix search endpoint
            kiwix_parsed = urlparse(WIKIPEDIA_KIWIX_URL)
            new_path = "/search"
            new = parsed._replace(
                scheme=kiwix_parsed.scheme,
                netloc=kiwix_parsed.netloc,
                path=new_path,
            )
            new_url = urlunparse(new)
            logger.info("WIKIPEDIA API intercept: %s -> %s", url[:120], new_url[:120])
            return new_url

    return url


# ---------------------------------------------------------------------------
# 1. Patch requests.Session.send
# ---------------------------------------------------------------------------
def _patch_requests():
    try:
        import requests
    except ImportError:
        logger.debug("requests not installed, skip patch")
        return

    _orig_send = requests.Session.send

    def _patched_send(self, request, **kwargs):
        original_url = request.url
        new_url = _rewrite_url(original_url)
        if new_url != original_url:
            request.url = new_url
            # Also update Host header if present
            parsed = urlparse(new_url)
            if "Host" in request.headers:
                request.headers["Host"] = parsed.netloc
        return _orig_send(self, request, **kwargs)

    requests.Session.send = _patched_send
    logger.info("patched requests.Session.send")


# ---------------------------------------------------------------------------
# 2. Patch httpx (both sync Client and async AsyncClient)
# ---------------------------------------------------------------------------
def _patch_httpx():
    try:
        import httpx
    except ImportError:
        logger.debug("httpx not installed, skip patch")
        return

    # httpx uses URL objects, and the transport layer receives a Request object.
    # The cleanest intercept point is Client.send / AsyncClient.send which
    # wraps _send_handling_auth -> _send_handling_redirects -> _send_single_request.
    # We patch at .send() level to catch everything.

    # Sync client
    if hasattr(httpx, "Client"):
        _orig_client_send = httpx.Client.send

        def _patched_client_send(self, request, **kwargs):
            original_url = str(request.url)
            new_url = _rewrite_url(original_url)
            if new_url != original_url:
                request.url = httpx.URL(new_url)
                request.headers["host"] = urlparse(new_url).netloc
            return _orig_client_send(self, request, **kwargs)

        httpx.Client.send = _patched_client_send
        logger.info("patched httpx.Client.send")

    # Async client
    if hasattr(httpx, "AsyncClient"):
        _orig_async_send = httpx.AsyncClient.send

        async def _patched_async_send(self, request, **kwargs):
            original_url = str(request.url)
            new_url = _rewrite_url(original_url)
            if new_url != original_url:
                request.url = httpx.URL(new_url)
                request.headers["host"] = urlparse(new_url).netloc
            return await _orig_async_send(self, request, **kwargs)

        httpx.AsyncClient.send = _patched_async_send
        logger.info("patched httpx.AsyncClient.send")


# ---------------------------------------------------------------------------
# 3. Patch aiohttp.ClientSession._request
# ---------------------------------------------------------------------------
def _patch_aiohttp():
    try:
        import aiohttp
    except ImportError:
        logger.debug("aiohttp not installed, skip patch")
        return

    _orig_request = aiohttp.ClientSession._request

    async def _patched_request(self, method, str_or_url, **kwargs):
        url_str = str(str_or_url)
        new_url = _rewrite_url(url_str)
        if new_url != url_str:
            str_or_url = new_url
        return await _orig_request(self, method, str_or_url, **kwargs)

    aiohttp.ClientSession._request = _patched_request
    logger.info("patched aiohttp.ClientSession._request")


# ---------------------------------------------------------------------------
# 4. Patch urllib.request.urlopen (fallback, rarely used by frameworks)
# ---------------------------------------------------------------------------
def _patch_urllib():
    import urllib.request

    _orig_urlopen = urllib.request.urlopen

    def _patched_urlopen(url, *args, **kwargs):
        if isinstance(url, str):
            new_url = _rewrite_url(url)
            if new_url != url:
                url = new_url
        elif hasattr(url, "full_url"):
            # urllib.request.Request object
            original = url.full_url
            new_url = _rewrite_url(original)
            if new_url != original:
                url.full_url = new_url
        return _orig_urlopen(url, *args, **kwargs)

    urllib.request.urlopen = _patched_urlopen
    logger.info("patched urllib.request.urlopen")


# ---------------------------------------------------------------------------
# 5. Patch langchain_tavily TAVILY_API_URL at the module level AND in
#    any modules that already imported it (DeerFlow's wrapper etc.)
# ---------------------------------------------------------------------------
def _patch_langchain_tavily_url():
    """Patch the TAVILY_API_URL constant in langchain_tavily._utilities AND in
    any modules that have already done `from langchain_tavily._utilities import TAVILY_API_URL`.

    The key issue: Python `from X import Y` creates a NEW binding in the
    importing module. Patching X.Y only changes the original; the copy in
    the importing module is stale. So we scan sys.modules for any module
    that has a `TAVILY_API_URL` attribute pointing to the old value.
    """
    import sys
    try:
        import langchain_tavily._utilities as _ltu
        old_url = _ltu.TAVILY_API_URL
        _ltu.TAVILY_API_URL = SHIM_URL
        logger.info("patched langchain_tavily._utilities.TAVILY_API_URL -> %s", SHIM_URL)

        # Now scan all loaded modules for stale copies of the old URL
        for mod_name, mod in list(sys.modules.items()):
            if mod is None:
                continue
            if mod is _ltu:
                continue
            try:
                if hasattr(mod, "TAVILY_API_URL") and getattr(mod, "TAVILY_API_URL") == old_url:
                    setattr(mod, "TAVILY_API_URL", SHIM_URL)
                    logger.info("  also patched %s.TAVILY_API_URL", mod_name)
            except Exception:
                pass
    except ImportError:
        logger.debug("langchain_tavily not installed, skip TAVILY_API_URL patch")


# ---------------------------------------------------------------------------
# Install all patches (idempotent)
# ---------------------------------------------------------------------------
def install_all():
    """Install all HTTP-level intercept patches. Safe to call multiple times."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    logger.info("Installing HTTP intercept patches (SHIM=%s, WIKI=%s)",
                SHIM_URL, WIKIPEDIA_KIWIX_URL)

    _patch_requests()
    _patch_httpx()
    _patch_aiohttp()
    _patch_urllib()
    _patch_langchain_tavily_url()

    logger.info("All HTTP intercept patches installed.")


# Auto-install on import
install_all()
