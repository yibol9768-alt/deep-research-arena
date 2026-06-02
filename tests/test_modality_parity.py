"""Modality-parity test for the pluggable RL acquisition layer.

The grounding reward (``ArenaEvaluator._compute_ground_signals``) reads ONLY
``rollout.retrieved_snippets`` (dict[canonical_url -> page_text]) plus the URLs
cited in the report; it never inspects *how* the text was fetched. This module
proves the plumbing preserves that invariant end to end: for a fixed task and a
fixed acquisition outcome (identical (url, page_text) pairs and an identical
report), the composite reward and every per-dim score are byte-identical no
matter which ``SandboxBackend`` produced the pairs.

Three acquisition legs are exercised, all offline (no playwright, no GPU, no
live shim, no LLM judge):

  * shim       -> ``HttpSandboxBackend`` with a *mocked transport* (``_post_json``
                  patched to serve PAGES/INDEX in the Tavily shapes the real
                  shim emits). Exercises the real search()/fetch() normalisers.
  * browser    -> ``BrowserSandboxBackend`` driven by an injected *fake page*
                  (``.goto``/``.evaluate``/``.url``) and a mock shim for search.
                  No real chromium. If the concurrent backend module is not yet
                  present, an in-test backend implementing the *agreed* DESIGN
                  interface stands in, so this test passes today and upgrades to
                  the real class automatically once it lands.
  * computeruse-> ``ComputerUseBackend.text_proxy(inner=...)`` (text-proxy stub),
                  which delegates fetch/search to an inner backend, so the bytes
                  are identical to whatever it wraps.

The legs feed IDENTICAL (url, text) data into the env via three different code
paths, then we assert (1) the env-level invariant (same retrieved_snippets /
fetched_urls / report_md), and (2) the reward invariant (same composite +
per_dim). The reward evaluator runs in ``mode="fast"`` with ``_rl_strict=True``
so it is fully deterministic and never calls the LLM judge.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from src.eval.evaluator import ArenaEvaluator
from src.eval.rollout import Rollout
from src.rl.env import (
    Cite,
    Finalize,
    HttpSandboxBackend,
    MockSandboxBackend,
    Open,
    Read,
    ResearchEnv,
    Search,
    _normalize_hit,
)
from src.rl.policy import MockPolicy
from src.rl.runner import run_episode
from src.verifiers.citation_format import canonicalize_url


# --------------------------------------------------------------------------- #
# Fixtures: one task, two sandbox-resolved URLs, a tiny markdown spec.
# URLs are *sentinel-resolved* concrete sandbox URLs (localhost:7770 / :9999)
# so they count as in-sandbox citations exactly like the shim path. The browser
# leg additionally proves __SHOPPING__/__REDDIT__ sentinels resolve to these.
# --------------------------------------------------------------------------- #
TASK_ID = "modality_parity_synth"
PROMPT = "Compare Alpha headphones using product and forum evidence."

URL_PRODUCT = "http://localhost:7770/product-a.html"
URL_FORUM = "http://localhost:9999/f/headphones/alpha-thread"

PAGES = {
    URL_PRODUCT: (
        "Alpha headphones balanced sound battery life comfort travel value. "
        "Evidence from a hands-on product test with practical limitations noted."
    ),
    URL_FORUM: (
        "Forum owners report long term comfort, value, fit and durability "
        "evidence for Alpha headphones across many months of everyday use."
    ),
}
INDEX = {PROMPT: [URL_PRODUCT, URL_FORUM]}

REPORT_MD = (
    "# Alpha Headphones Review\n\n"
    "Alpha headphones deliver balanced sound and strong battery life, with "
    f"comfort suited to travel use [product]({URL_PRODUCT}).\n\n"
    "Owners on the forum corroborate long-term comfort, fit and durability "
    f"over months of everyday use [forum]({URL_FORUM}).\n"
)


def _task_config() -> dict[str, Any]:
    return {
        "task_id": TASK_ID,
        "intent": PROMPT,
        "prompt": PROMPT,
        "sandbox_hosts": ["localhost:7770", "localhost:9999"],
        "markdown_spec": {
            "min_words": 20,
            "max_words": 240,
            "min_paragraphs": 2,
            "min_citations": 1,
            "min_pages_browsed": 0,
        },
        "citation_policy": {"must_be_in_domain": []},
        "url_coverage": {
            "min_unique_urls_cited": 1,
            "min_must_cite_recall": 0.0,
            "min_expected_pool_coverage": 0.0,
            "min_domain_balance": 0.0,
        },
        "search": {"target_distinct_queries": 1},
    }


def _scripted_policy() -> MockPolicy:
    """One deterministic action trace driving every leg identically.

    The policy opens/cites the resolved sandbox URLs (``localhost:7770`` /
    ``:9999``) -- exactly what the 13 shim adapters do today. The env records
    ``retrieved_snippets`` keyed by the *opened* URL, so for the reward to be
    invariant every backend must return identical text for those identical
    opened URLs. (Sentinel resolution, a browser-internal capability, is proven
    separately in ``test_browser_backend_resolves_sentinels``.)
    """
    return MockPolicy(
        scripted_actions=[
            Search(PROMPT),
            Open(URL_PRODUCT),
            Read(),
            Open(URL_FORUM),
            Read(),
            Cite(URL_PRODUCT),
            Cite(URL_FORUM),
            Finalize(REPORT_MD),
        ]
    )


# --------------------------------------------------------------------------- #
# Fake page (browser leg) + mock-shim transport (shim leg). No real I/O.
# --------------------------------------------------------------------------- #
class _FakePage:
    """Minimal Playwright-page stand-in for offline BrowserSandboxBackend.

    ``goto`` records the (already sentinel-resolved) URL; ``evaluate`` returns
    the canned innerText for it -- the same expression the real backend's
    fetch() runs: ``() => document.body.innerText || ''``.
    """

    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = dict(pages)
        self.url = ""
        self.goto_calls: list[str] = []
        self.default_timeout: int | None = None

    def goto(self, url: str, *args: Any, **kwargs: Any) -> None:
        self.url = url
        self.goto_calls.append(url)

    def wait_for_load_state(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set_default_timeout(self, ms: int) -> None:
        self.default_timeout = int(ms)

    def evaluate(self, expr: str, *args: Any, **kwargs: Any) -> str:
        return self._pages.get(self.url, "")


def _mock_shim_transport(monkeypatch: pytest.MonkeyPatch, backend: HttpSandboxBackend) -> None:
    """Patch a real HttpSandboxBackend so it serves PAGES/INDEX with no requests.

    Replicates the Tavily shapes the live shim emits: ``/search`` ->
    {"results": [{url,title,content}]}; ``/extract`` -> {"results":
    [{url, raw_content}]}.
    """

    def fake_post(path: str, payload: dict[str, Any]) -> Any:
        leaf = path.strip("/").split("/")[-1]
        if leaf == "search":
            query = str(payload.get("query") or "")
            urls = INDEX.get(query) or INDEX.get(query.strip()) or []
            return {
                "results": [
                    {"url": u, "title": u.rsplit("/", 1)[-1], "content": PAGES.get(u, "")[:200]}
                    for u in urls
                ]
            }
        if leaf == "extract":
            urls = payload.get("urls") or []
            return {"results": [{"url": u, "raw_content": PAGES.get(u, "")} for u in urls]}
        return {}

    monkeypatch.setattr(backend, "_post_json", fake_post)


# --------------------------------------------------------------------------- #
# Browser backend resolution: prefer the real concurrent module; otherwise use
# an in-test backend implementing the agreed DESIGN interface so this test is
# self-contained and passes on system python3 today.
# --------------------------------------------------------------------------- #
_BROWSER_SENTINELS = {
    "__SHOPPING__": "http://localhost:7770",
    "__REDDIT__": "http://localhost:9999",
    "__WIKIPEDIA__": "http://localhost:8090",
}


def _resolve_sentinel(url: str) -> str:
    out = str(url)
    for token, base in _BROWSER_SENTINELS.items():
        out = out.replace(token, base)
    return out


class _AgreedBrowserBackend:
    """Reference impl of the DESIGN BrowserSandboxBackend SandboxBackend surface.

    Used only when the concurrent ``src.rl.browser_backend`` /
    ``src.rl.backends`` module is not yet importable. Behaviour mirrors the
    DESIGN contract exactly:
      * ``fetch`` resolves sentinels, navigates the (fake) page and returns the
        raw page innerText -- the same bytes the shim returns -- so they land in
        the identical ``retrieved_snippets[canonicalize_url(url)]`` slot.
      * ``search`` (mode (a)) delegates breadth to an injected shim backend.
    """

    def __init__(self, *, page: Any, shim: Any, timeout_ms: int = 60000) -> None:
        self._page = page
        self._shim = shim
        if hasattr(page, "set_default_timeout"):
            page.set_default_timeout(timeout_ms)

    def _ensure_page(self) -> Any:  # pragma: no cover - injected page only
        return self._page

    def search(self, query: str) -> list[dict[str, Any]]:
        return [_normalize_hit(h) for h in self._shim.search(query)]

    def fetch(self, url: str) -> str:
        resolved = _resolve_sentinel(url)
        page = self._ensure_page()
        page.goto(resolved, timeout=getattr(self, "_timeout_ms", 60000))
        page.wait_for_load_state("domcontentloaded")
        return page.evaluate("() => document.body.innerText || ''")

    def close(self) -> None:  # pragma: no cover - no real browser to close
        return None

    def __enter__(self) -> "_AgreedBrowserBackend":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _import_browser_class():
    """Return (BrowserSandboxBackend class, source_label) or (None, None)."""
    for mod_name in ("src.rl.browser_backend", "src.rl.backends"):
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        cls = getattr(mod, "BrowserSandboxBackend", None)
        if cls is not None:
            return cls, mod_name
    return None, None


def _make_browser_backend(page: _FakePage, shim: SandboxBackend_t) -> Any:
    """Build a browser-leg backend.

    Prefers the real concurrent class via its documented injection seams
    (``page=`` for the fake page; an internal shim for search). If the class is
    not importable yet, fall back to the agreed reference impl. Either way the
    backend is fed the SAME fake page + mock shim, so the (url, text) data is
    identical to the other legs.
    """
    cls, _src = _import_browser_class()
    if cls is None:
        return _AgreedBrowserBackend(page=page, shim=shim)
    # The DESIGN constructor accepts page= (unit-test injection seam, so no
    # playwright is touched) and a search-breadth delegate. We inject our mock
    # shim through whichever kwarg the real class exposes for it; if none match,
    # monkeypatch search() so the parity test never needs a live shim. Fall back
    # to the agreed reference impl only if the signature is entirely foreign.
    shim_kwarg_names = ("search_backend", "shim", "shim_backend", "inner")
    for shim_kw in shim_kwarg_names:
        try:
            return cls(**{"page": page, shim_kw: shim})
        except TypeError:
            continue
    # No shim-injection kwarg; build with the page seam and force search().
    try:
        backend = cls(page=page)
    except TypeError:
        return _AgreedBrowserBackend(page=page, shim=shim)
    try:
        backend.search = shim.search  # type: ignore[attr-defined]
    except Exception:
        return _AgreedBrowserBackend(page=page, shim=shim)
    return backend


# Type alias kept loose: any object exposing search()/fetch().
SandboxBackend_t = Any


def _import_computeruse_class():
    for mod_name in ("src.rl.computeruse_backend", "src.rl.backends"):
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        cls = getattr(mod, "ComputerUseBackend", None)
        if cls is not None:
            return cls
    return None


# --------------------------------------------------------------------------- #
# Episode drivers (one per leg) -> Rollout.
# --------------------------------------------------------------------------- #
def _run_leg(backend: SandboxBackend_t) -> Rollout:
    config = _task_config()
    env = ResearchEnv(config, backend, max_tool_calls=40)
    return run_episode(config, env, _scripted_policy())


def _evaluator() -> ArenaEvaluator:
    ev = ArenaEvaluator(TASK_ID, mode="fast")
    ev._task_config = _task_config()
    # Strict grounding (matches scripts/train_grpo_pilot.py): no text-only proxy,
    # citations counted against the fetch trace. Fully deterministic in fast mode.
    ev._rl_strict = True
    return ev


# --------------------------------------------------------------------------- #
# Core: reward is modality-INVARIANT (shim vs browser, plus computeruse).
# --------------------------------------------------------------------------- #
def test_reward_is_modality_invariant(monkeypatch: pytest.MonkeyPatch) -> None:
    # -- shim leg: real HttpSandboxBackend with a mocked transport ----------
    shim_backend = HttpSandboxBackend("http://localhost:8081", max_results=10)
    _mock_shim_transport(monkeypatch, shim_backend)
    rollout_shim = _run_leg(shim_backend)

    # -- browser leg: injected fake page + a mock shim for search ----------
    browser_shim = HttpSandboxBackend("http://localhost:8081", max_results=10)
    _mock_shim_transport(monkeypatch, browser_shim)
    fake_page = _FakePage(PAGES)
    browser_backend = _make_browser_backend(fake_page, browser_shim)
    rollout_browser = _run_leg(browser_backend)

    # Browser leg must have actually driven the fake page (proves fetch went
    # through goto -> evaluate(innerText), not some other path).
    assert URL_PRODUCT in fake_page.goto_calls
    assert URL_FORUM in fake_page.goto_calls

    # -- env-level invariant: same grounding bytes land in the same slots ---
    assert rollout_shim.report_md == rollout_browser.report_md == REPORT_MD
    assert rollout_shim.fetched_urls == rollout_browser.fetched_urls
    assert rollout_shim.retrieved_snippets == rollout_browser.retrieved_snippets
    # And the snippets are keyed by canonical URL with the exact full page text
    # (browser innerText), NOT the shim's truncated search snippet.
    assert rollout_browser.retrieved_snippets[canonicalize_url(URL_PRODUCT)] == PAGES[URL_PRODUCT]
    assert rollout_browser.retrieved_snippets[canonicalize_url(URL_FORUM)] == PAGES[URL_FORUM]

    # -- reward invariant: composite + per_dim identical --------------------
    ev = _evaluator()
    res_shim = ev.evaluate_rollout(rollout_shim)
    res_browser = ev.evaluate_rollout(rollout_browser)

    assert res_shim.composite == res_browser.composite
    assert res_shim.per_dim == res_browser.per_dim
    # The grounded dims must be genuinely exercised, not all-neutral.
    assert res_shim.policy["quote_match"] == res_browser.policy["quote_match"]
    assert res_shim.composite > 0.0

    # -- optional computeruse leg: three-way parity -------------------------
    cu_cls = _import_computeruse_class()
    if cu_cls is not None and hasattr(cu_cls, "text_proxy"):
        inner = MockSandboxBackend(PAGES, INDEX)
        cu_backend = cu_cls.text_proxy(inner=inner)
        rollout_cu = _run_leg(cu_backend)
        assert rollout_cu.retrieved_snippets == rollout_shim.retrieved_snippets
        assert rollout_cu.fetched_urls == rollout_shim.fetched_urls
        assert rollout_cu.report_md == rollout_shim.report_md
        res_cu = ev.evaluate_rollout(rollout_cu)
        assert res_cu.composite == res_shim.composite
        assert res_cu.per_dim == res_shim.per_dim


def test_reward_invariant_via_mock_shim_leg() -> None:
    """Parity also holds when the shim leg is the offline MockSandboxBackend.

    This is the cheapest possible cross-check and does not depend on the
    HttpSandboxBackend transport at all: drive the env once with a
    MockSandboxBackend and once with the browser leg over a fake page, and
    assert identical reward. Belt-and-suspenders against the monkeypatched
    transport masking a real difference.
    """
    mock_backend = MockSandboxBackend(PAGES, INDEX)
    rollout_mock = _run_leg(mock_backend)

    browser_shim = MockSandboxBackend(PAGES, INDEX)
    fake_page = _FakePage(PAGES)
    browser_backend = _make_browser_backend(fake_page, browser_shim)
    rollout_browser = _run_leg(browser_backend)

    assert rollout_mock.retrieved_snippets == rollout_browser.retrieved_snippets
    assert rollout_mock.fetched_urls == rollout_browser.fetched_urls
    assert rollout_mock.report_md == rollout_browser.report_md

    ev = _evaluator()
    res_mock = ev.evaluate_rollout(rollout_mock)
    res_browser = ev.evaluate_rollout(rollout_browser)
    assert res_mock.composite == res_browser.composite
    assert res_mock.per_dim == res_browser.per_dim


# --------------------------------------------------------------------------- #
# Browser-internal: sentinel URLs resolve to the right localhost ports so the
# policy can emit __SHOPPING__/__REDDIT__/__WIKIPEDIA__ identically to the shim.
# Keyed by RESOLVED url; fed the SENTINEL url; must return the resolved text.
# --------------------------------------------------------------------------- #
def test_browser_backend_resolves_sentinels() -> None:
    resolved_pages = {
        "http://localhost:7770/product-a.html": "SHOPPING-PAGE-TEXT",
        "http://localhost:9999/f/x": "REDDIT-PAGE-TEXT",
        "http://localhost:8090/wiki/Y": "WIKIPEDIA-PAGE-TEXT",
    }
    page = _FakePage(resolved_pages)
    backend = _make_browser_backend(page, MockSandboxBackend(PAGES, INDEX))

    assert backend.fetch("__SHOPPING__/product-a.html") == "SHOPPING-PAGE-TEXT"
    assert backend.fetch("__REDDIT__/f/x") == "REDDIT-PAGE-TEXT"
    assert backend.fetch("__WIKIPEDIA__/wiki/Y") == "WIKIPEDIA-PAGE-TEXT"
    # The fake page was navigated to the RESOLVED localhost URLs.
    assert "http://localhost:7770/product-a.html" in page.goto_calls
    assert "http://localhost:9999/f/x" in page.goto_calls
    assert "http://localhost:8090/wiki/Y" in page.goto_calls


# --------------------------------------------------------------------------- #
# (a) Backend conformance: search() -> list[Hit with 'url']; fetch() -> str.
# --------------------------------------------------------------------------- #
def test_backend_conformance(monkeypatch: pytest.MonkeyPatch) -> None:
    backends: list[tuple[str, SandboxBackend_t]] = []

    # MockSandboxBackend (offline canonical).
    backends.append(("mock", MockSandboxBackend(PAGES, INDEX)))

    # HttpSandboxBackend with mocked transport.
    http_backend = HttpSandboxBackend("http://localhost:8081")
    _mock_shim_transport(monkeypatch, http_backend)
    backends.append(("http", http_backend))

    # Browser backend (real-or-reference) over a fake page + mock shim.
    browser_shim = MockSandboxBackend(PAGES, INDEX)
    browser_backend = _make_browser_backend(_FakePage(PAGES), browser_shim)
    backends.append(("browser", browser_backend))

    # ComputerUseBackend text-proxy, if present.
    cu_cls = _import_computeruse_class()
    if cu_cls is not None and hasattr(cu_cls, "text_proxy"):
        backends.append(("computeruse", cu_cls.text_proxy(inner=MockSandboxBackend(PAGES, INDEX))))

    for label, backend in backends:
        hits = backend.search(PROMPT)
        assert isinstance(hits, list), f"{label}.search must return a list"
        assert hits, f"{label}.search returned no hits for the indexed query"
        for hit in hits:
            assert isinstance(hit, dict), f"{label} hit must be a dict"
            assert "url" in hit and isinstance(hit["url"], str) and hit["url"], (
                f"{label} hit missing non-empty 'url'"
            )

        text = backend.fetch(URL_PRODUCT)
        assert isinstance(text, str), f"{label}.fetch must return str"
        assert text == PAGES[URL_PRODUCT], f"{label}.fetch returned wrong page text"


# --------------------------------------------------------------------------- #
# (b) Import-without-playwright: src.rl.env and the backend module(s) import
#     on system python3 with no playwright installed (lazy-import property).
# --------------------------------------------------------------------------- #
def test_env_imports_without_playwright() -> None:
    # playwright must NOT be importable in this offline environment...
    with pytest.raises(ImportError):
        importlib.import_module("playwright")

    # ...yet the env module imports fine and exposes no top-level playwright ref.
    env_mod = importlib.import_module("src.rl.env")
    import sys

    assert "playwright" not in sys.modules
    src = open(env_mod.__file__, encoding="utf-8").read()
    assert "import playwright" not in src, "src/rl/env.py must not import playwright at top level"
    assert "from playwright" not in src, "src/rl/env.py must not import playwright at top level"


def test_backend_module_imports_without_playwright() -> None:
    """If the concurrent backend module exists, it must import with no playwright.

    Skips cleanly when neither module has landed yet (the parity test above
    still runs against the agreed reference backend).
    """
    import sys

    imported_any = False
    for mod_name in ("src.rl.browser_backend", "src.rl.backends"):
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        imported_any = True
        # Module imported on a box with no playwright -> lazy import respected.
        assert "playwright" not in sys.modules, (
            f"{mod_name} pulled in playwright at import time"
        )
        src = open(mod.__file__, encoding="utf-8").read()
        # A top-level (column-0) playwright import is forbidden; lazy imports
        # inside functions are indented and therefore fine.
        for line in src.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("import playwright") or stripped.startswith("from playwright"):
                assert line != stripped, (
                    f"{mod_name} imports playwright at top level (must be lazy)"
                )

    if not imported_any:
        pytest.skip("no concurrent backend module present yet (browser_backend/backends)")
