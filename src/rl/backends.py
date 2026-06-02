"""Pluggable acquisition backends for the C1 research environment.

The reward in :mod:`src.eval.evaluator` is modality-agnostic: it credits
``rollout.retrieved_snippets`` (``dict[url] -> page_text``) plus the cited URLs
and never inspects *how* the text was acquired
(``s_ground = 0.6 * f1_claim + 0.4 * r_resolve``). Any object satisfying the
:class:`src.rl.env.SandboxBackend` protocol therefore earns identical reward as
long as it lands the same ``(url, page_text)`` pairs into the env.

This module adds two new acquisition channels and a factory, *without* touching
the existing ``HttpSandboxBackend`` / ``MockSandboxBackend`` in
:mod:`src.rl.env` (it imports/re-exports them instead):

* :class:`BrowserSandboxBackend` -- a real-browser channel over a persistent
  Playwright page. ``playwright`` is imported lazily inside ``_ensure_page`` so
  this module imports fine on a box without playwright; a ``page`` may be
  injected for offline unit tests.
* :class:`ComputerUseBackend` -- the *interface* for a vision/computer-use
  channel plus a shipped, offline-safe text-proxy stub. Full vision-RL (a VLM
  driving screenshots) is explicitly out of scope for the single-5090 pilot;
  this provides the seam and a stub, not a trained vision policy.
* :func:`make_backend` -- selects ``search_shim`` | ``browser`` |
  ``computer_use`` | ``mock`` and returns the matching backend, defaulting to
  ``search_shim`` so existing tasks are byte-for-byte unchanged.

All heavy dependencies (playwright, a real screen/VLM client) are imported
lazily inside the methods that need them; ``import src.rl.backends`` succeeds on
a plain system ``python3`` with neither playwright nor a VLM installed.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Optional, Protocol, runtime_checkable

# The existing backends and shared helpers live in env.py; reuse them so this
# module is purely additive and the Hit-normalization stays in one place.
from .env import Hit, HttpSandboxBackend, MockSandboxBackend, SandboxBackend, _normalize_hit


# Grounded sentinel ports. WIKIPEDIA is 8090 (Kiwix en) to match the shim
# allowlist / strict gate, NOT the 8888 in PlaywrightRunner's default map.
DEFAULT_SITE_MAP: dict[str, str] = {
    "SHOPPING": "http://localhost:7770",
    "REDDIT": "http://localhost:9999",
    "WIKIPEDIA": "http://localhost:8090",
}

# Page text expression -- the exact read_visible()/_summary() expression from
# src/agents/glm_react_agent.py so browser-fetched text matches that path.
_INNER_TEXT_EXPR = "() => document.body.innerText || ''"

_DEFAULT_SHIM_URL = "http://localhost:8081"


def _default_shim_url() -> str:
    return os.environ.get("DR_SHIM_URL") or os.environ.get("SEARCH_URL") or _DEFAULT_SHIM_URL


def _resolved_site_map(site_map: dict[str, str] | None) -> dict[str, str]:
    """Merge env-var overrides over the grounded defaults, then caller overrides."""
    env_map = {
        "SHOPPING": os.environ.get("SHOPPING", DEFAULT_SITE_MAP["SHOPPING"]),
        "REDDIT": os.environ.get("REDDIT", DEFAULT_SITE_MAP["REDDIT"]),
        "WIKIPEDIA": os.environ.get("WIKIPEDIA", DEFAULT_SITE_MAP["WIKIPEDIA"]),
    }
    return {**env_map, **(site_map or {})}


# ---------------------------------------------------------------------------
# Browser channel
# ---------------------------------------------------------------------------
class BrowserSandboxBackend:
    """Real-browser acquisition over a persistent Playwright page.

    Implements the :class:`SandboxBackend` protocol (``search`` / ``fetch``).
    The page is launched once and reused across every call in a rollout (a
    rollout is up to ~40 tool calls; relaunching per call would be fatal), then
    torn down by :meth:`close` / context-manager exit.

    ``fetch(url)`` is the load-bearing parity method: it resolves sentinels,
    navigates, and returns ``page.evaluate("() => document.body.innerText ...")``
    -- the same visible-text expression the shim path lands in
    ``retrieved_snippets``, so browser-fetched text is byte-comparable.

    Offline unit-testability:
        * ``page=<fake page>`` -- a stub exposing ``.goto(url)``, ``.evaluate``,
          (optionally ``.wait_for_load_state`` / ``.set_default_timeout`` /
          ``.url``). When supplied, playwright is never imported or launched.
        * ``page_factory=callable() -> page`` -- lazily build a (fake) page on
          first use without importing playwright.
    """

    def __init__(
        self,
        *,
        site_map: dict[str, str] | None = None,
        shim_url: str | None = None,
        page: Any | None = None,
        page_factory: Callable[[], Any] | None = None,
        search_backend: SandboxBackend | None = None,
        headless: bool = True,
        timeout_ms: int = 60_000,
    ) -> None:
        self.site_map = _resolved_site_map(site_map)
        # shim_url is optional: when set (or absent -> default), search() can
        # delegate breadth discovery to the shim. When explicitly None AND no
        # search_backend is injected, search() falls back to catalog scraping.
        self._shim_url = shim_url
        self.timeout_ms = int(timeout_ms)
        self.headless = bool(headless)

        # Injection seams (offline tests / DI).
        self._page = page
        self._page_factory = page_factory
        self._search_backend = search_backend

        # Lazily created playwright handles (only when we actually launch).
        self._pw = None
        self._browser = None
        self._context = None
        self._owns_page = page is None  # if injected, we don't tear it down

    # -- sentinel resolution (mirrors PlaywrightRunner.resolve's sub closure) --
    def _resolve(self, url: str) -> str:
        s = str(url)
        for key, base in self.site_map.items():
            s = s.replace(f"__{key}__", base)
        return s

    # -- persistent page lifecycle --
    def _ensure_page(self) -> Any:
        if self._page is not None:
            return self._page
        if self._page_factory is not None:
            self._page = self._page_factory()
            return self._page
        # Heavy import deferred to call time so the module imports without
        # playwright (same pattern as PlaywrightRunner.run).
        from playwright.sync_api import sync_playwright  # noqa: F401  (lazy)

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context()
        page = self._context.new_page()
        try:
            page.set_default_timeout(self.timeout_ms)
        except Exception:
            pass
        self._page = page
        return self._page

    # -- search() : breadth discovery --
    def _shim(self) -> SandboxBackend | None:
        if self._search_backend is not None:
            return self._search_backend
        if self._shim_url is None:
            return None
        # Build (and cache) an internal HttpSandboxBackend for SERP breadth.
        if not isinstance(getattr(self, "_internal_shim", None), HttpSandboxBackend):
            self._internal_shim = HttpSandboxBackend(self._shim_url)
        return self._internal_shim

    def search(self, query: str) -> list[Hit]:
        shim = self._shim()
        if shim is not None:
            # Breadth is modality-irrelevant for the reward (only fetched+cited
            # URLs are credited); delegating SERP to the shim is the simplest
            # correct design and avoids reimplementing SERP scraping.
            return [_normalize_hit(hit) for hit in shim.search(query) if _normalize_hit(hit).get("url")]
        return self._scrape_catalog_search(query)

    def _scrape_catalog_search(self, query: str) -> list[Hit]:
        """Fallback SERP: scrape the Magento catalog search result page.

        Uses the anchor-collection ``page.evaluate`` pattern from
        glm_react_agent.click_text (a JS expression returning a list of
        ``{href, text}`` dicts).
        """
        base = self.site_map.get("SHOPPING", DEFAULT_SITE_MAP["SHOPPING"])
        url = f"{base}/catalogsearch/result/?q={query}"
        page = self._ensure_page()
        page.goto(url, timeout=self.timeout_ms)
        try:
            page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass
        try:
            anchors = page.evaluate(
                "() => [...document.querySelectorAll('a.product-item-link, .product-item-name a')]"
                ".map(a => ({href: a.href, text: (a.innerText || '').trim()}))"
            ) or []
        except Exception:
            anchors = []
        hits: list[Hit] = []
        seen: set[str] = set()
        for a in anchors:
            href = str((a or {}).get("href") or "").strip()
            if not href or href in seen:
                continue
            seen.add(href)
            hits.append(_normalize_hit({"url": href, "title": (a or {}).get("text") or href, "snippet": ""}))
        return hits

    # -- fetch() : the parity method --
    def fetch(self, url: str) -> str:
        resolved = self._resolve(url)
        page = self._ensure_page()
        page.goto(resolved, timeout=self.timeout_ms)
        try:
            page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass
        try:
            text = page.evaluate(_INNER_TEXT_EXPR)
        except Exception:
            text = ""
        # Return raw innerText: ResearchEnv._do_read applies _truncate_text and
        # stores it into retrieved_snippets[canonicalize_url(url)]. No collapse,
        # no [:limit] here -- that keeps parity with the shim's raw_content.
        return str(text or "")

    # -- teardown --
    def close(self) -> None:
        if not self._owns_page:
            # Injected page is owned by the caller; do not tear it down.
            self._page = self._page  # no-op, keep handle for further calls
        else:
            try:
                if self._context is not None:
                    self._context.close()
            except Exception:
                pass
            try:
                if self._browser is not None:
                    self._browser.close()
            except Exception:
                pass
            try:
                if self._pw is not None:
                    self._pw.stop()
            except Exception:
                pass
            self._page = None
        self._pw = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "BrowserSandboxBackend":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Computer-use channel (interface + offline text-proxy stub)
# ---------------------------------------------------------------------------
@runtime_checkable
class ComputerUsePolicy(Protocol):
    """The seam a real VLM/computer-use policy attaches to (post-pilot).

    A trained policy would consume the multimodal ``observe`` output (a
    screenshot + accessibility tree + extracted text) and emit GUI ops from
    ``act`` (scroll / click / type / done). The shipped stub implements this
    with DOM text only and ``act -> {"action": "done"}``.
    """

    def observe(self, url: str) -> dict:
        """Return ``{"screenshot": bytes|None, "text": str, "elements": list}``."""

    def act(self, observation: dict) -> dict:
        """Return ``{"action": "scroll|click|type|done", ...}``."""


class _TextProxyPolicy:
    """DOM-to-text stub ComputerUsePolicy delegating page text to an inner backend.

    ``observe(url)`` returns the inner backend's ``fetch(url)`` text wrapped in
    the vision-shaped observation; ``act`` always terminates with ``done``. It
    holds NO screen and imports NO VLM -- fully offline.
    """

    def __init__(self, inner: SandboxBackend) -> None:
        self._inner = inner

    def observe(self, url: str) -> dict:
        return {"screenshot": None, "text": str(self._inner.fetch(url)), "elements": []}

    def act(self, observation: dict) -> dict:  # noqa: ARG002 - stub ignores obs
        return {"action": "done"}


class ComputerUseBackend:
    """Acquisition channel that drives a :class:`ComputerUsePolicy` over a screen.

    The shipped path is the offline text-proxy stub (:meth:`text_proxy`), which
    interposes the vision-shaped ``observe`` / ``act`` seam but obtains page text
    by delegating ``fetch`` / ``search`` to an *inner* :class:`SandboxBackend`.
    The bytes returned are therefore identical to that inner backend's --
    identical ``retrieved_snippets`` -> identical reward.

    Where a real vision policy attaches (post-pilot, documented, NOT
    implemented here):
        Replace ``_TextProxyPolicy`` with a real :class:`ComputerUsePolicy`
        whose ``observe()`` captures ``page.screenshot()`` (Playwright already
        gives this) plus an accessibility tree, and whose ``act()`` is the VLM's
        GUI decision. :meth:`fetch` would then loop ``observe -> act`` until
        ``action == "done"`` and return the accumulated visible text. The
        invariant the real policy MUST preserve: ``fetch()`` still returns the
        page's grounding text, because the reward credits ``retrieved_snippets``
        regardless of HOW the bytes were obtained. Swapping the stub for a VLM
        changes the acquisition mechanism, never the reward contract.
    """

    def __init__(
        self,
        policy: ComputerUsePolicy | None,
        *,
        inner: SandboxBackend | None = None,
        site_map: dict[str, str] | None = None,
        page: Any | None = None,
        page_factory: Callable[[], Any] | None = None,
        max_steps: int = 16,
        timeout_ms: int = 60_000,
    ) -> None:
        if policy is None and inner is None:
            raise ValueError(
                "ComputerUseBackend requires either a ComputerUsePolicy or an "
                "inner SandboxBackend (use ComputerUseBackend.text_proxy(...))."
            )
        self._policy = policy if policy is not None else _TextProxyPolicy(inner)  # type: ignore[arg-type]
        self._inner = inner
        self._page = page
        self._page_factory = page_factory
        self.site_map = _resolved_site_map(site_map)
        self.max_steps = int(max_steps)
        self.timeout_ms = int(timeout_ms)

    @classmethod
    def text_proxy(
        cls,
        *,
        inner: SandboxBackend | None = None,
        site_map: dict[str, str] | None = None,
        shim_url: str | None = None,
        max_steps: int = 16,
        timeout_ms: int = 60_000,
    ) -> "ComputerUseBackend":
        """Build an offline-safe backend whose policy is the DOM-to-text stub.

        ``inner`` is the byte source. If not given, prefer a
        :class:`BrowserSandboxBackend` (DOM innerText); if playwright is absent
        the caller should inject ``inner`` (e.g. a ``MockSandboxBackend`` for
        tests or an ``HttpSandboxBackend`` for the shim path).
        """
        if inner is None:
            # Default to the browser channel for real grounding; playwright is
            # imported lazily only when the backend actually fetches.
            inner = BrowserSandboxBackend(site_map=site_map, shim_url=shim_url)
        return cls(
            _TextProxyPolicy(inner),
            inner=inner,
            site_map=site_map,
            max_steps=max_steps,
            timeout_ms=timeout_ms,
        )

    def _resolve(self, url: str) -> str:
        s = str(url)
        for key, base in self.site_map.items():
            s = s.replace(f"__{key}__", base)
        return s

    def _has_page_seam(self) -> bool:
        return self._page is not None or self._page_factory is not None

    def _ensure_page(self) -> Any | None:
        if self._page is not None:
            return self._page
        if self._page_factory is not None:
            self._page = self._page_factory()
        return self._page

    def _navigate(self, url: str) -> Any | None:
        page = self._ensure_page()
        if page is None:
            return None
        resolved = self._resolve(url)
        current = str(getattr(page, "url", "") or "")
        if current != resolved:
            page.goto(resolved, timeout=self.timeout_ms)
            try:
                page.wait_for_load_state("domcontentloaded")
            except Exception:
                pass
        return page

    def _page_text(self, page: Any) -> str:
        evaluate = getattr(page, "evaluate", None)
        if callable(evaluate):
            try:
                return str(evaluate(_INNER_TEXT_EXPR) or "")
            except Exception:
                pass
        text_content = getattr(page, "text_content", None)
        if callable(text_content):
            try:
                return str(text_content("body") or "")
            except Exception:
                pass
        return ""

    def _screenshot(self, page: Any) -> bytes | None:
        screenshot = getattr(page, "screenshot", None)
        if not callable(screenshot):
            return None
        try:
            return screenshot()
        except Exception:
            return None

    def _a11y(self, page: Any) -> Any:
        for owner in (page, getattr(page, "context", None)):
            accessibility = getattr(owner, "accessibility", None)
            snapshot = getattr(accessibility, "snapshot", None)
            if callable(snapshot):
                try:
                    return snapshot()
                except Exception:
                    return None
        snapshot = getattr(page, "snapshot_accessibility", None)
        if callable(snapshot):
            try:
                return snapshot()
            except Exception:
                return None
        return None

    def observe(self, url: str | None = None) -> dict[str, Any]:
        """Capture screenshot, accessibility tree, text, elements, and URL."""
        if self._has_page_seam():
            page = self._navigate(url) if url is not None else self._ensure_page()
            if page is None:
                return {"screenshot": None, "a11y": None, "text": "", "elements": [], "url": url}
            a11y = self._a11y(page)
            return {
                "screenshot": self._screenshot(page),
                "a11y": a11y,
                "text": self._page_text(page),
                "elements": a11y if isinstance(a11y, list) else [],
                "url": str(getattr(page, "url", "") or (url or "")),
            }
        return dict(self._policy.observe(str(url or "")) or {})

    # -- SandboxBackend protocol --
    def search(self, query: str) -> list[Hit]:
        if self._inner is None:  # pragma: no cover - guarded in __init__
            raise NotImplementedError(
                "A real ComputerUsePolicy must implement SERP discovery; the "
                "shipped stub delegates search() to an inner SandboxBackend."
            )
        return [_normalize_hit(hit) for hit in self._inner.search(query) if _normalize_hit(hit).get("url")]

    def fetch(self, url: str) -> str:
        # Vision-shaped loop: observe -> act -> apply GUI action -> observe.
        # The text-proxy stub still terminates in one step and returns exactly
        # the inner backend's text. A page-backed policy returns visible page
        # text so grounding remains modality-agnostic.
        page = self._navigate(url) if self._has_page_seam() else None
        obs = self.observe(url) if page is not None else self._policy.observe(url)
        steps = 0
        while steps < self.max_steps:
            decision = self._policy.act(obs)
            action = _computer_action_name(decision)
            if action == "done":
                break
            steps += 1
            if page is not None:
                _perform_computer_action(page, decision)
                obs = self.observe()
            else:
                obs = self._policy.observe(url)
        return str(obs.get("text") or "")

    def close(self) -> None:
        closer = getattr(self._inner, "close", None)
        if callable(closer):
            closer()

    def __enter__(self) -> "ComputerUseBackend":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _computer_action_name(decision: dict[str, Any] | None) -> str:
    raw = str((decision or {}).get("action") or "").strip().lower()
    name = raw.replace("-", "_").replace(" ", "_")
    aliases = {
        "doubleclick": "double_click",
        "double_tap": "double_click",
        "key_press": "keypress",
        "press": "keypress",
        "press_key": "keypress",
        "mouse_move": "move",
        "sleep": "wait",
        "finish": "done",
        "complete": "done",
    }
    return aliases.get(name, name)


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _point(data: dict[str, Any], *keys: str) -> tuple[float, float] | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, dict) and value.get("x") is not None and value.get("y") is not None:
            return float(value["x"]), float(value["y"])
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return float(value[0]), float(value[1])
    x = _first(data, "x", "client_x", "screen_x")
    y = _first(data, "y", "client_y", "screen_y")
    if x is not None and y is not None:
        return float(x), float(y)
    return None


def _locator(page: Any, selector: str) -> Any | None:
    locator = getattr(page, "locator", None)
    if callable(locator):
        try:
            return locator(selector)
        except Exception:
            return None
    return None


def _click(page: Any, decision: dict[str, Any], *, double: bool = False) -> None:
    selector = _first(decision, "selector", "target")
    if selector:
        loc = _locator(page, str(selector))
        method = getattr(loc, "dblclick" if double else "click", None) if loc is not None else None
        if callable(method):
            method()
            return
        page_method = getattr(page, "dblclick" if double else "click", None)
        if callable(page_method):
            page_method(str(selector))
            return
    point = _point(decision, "point", "position", "coords")
    mouse = getattr(page, "mouse", None)
    if point is not None and mouse is not None:
        method = getattr(mouse, "dblclick" if double else "click", None)
        if callable(method):
            method(point[0], point[1])


def _perform_computer_action(page: Any, decision: dict[str, Any] | None) -> None:
    decision = dict(decision or {})
    action = _computer_action_name(decision)
    if action == "click":
        _click(page, decision)
    elif action == "double_click":
        _click(page, decision, double=True)
    elif action == "scroll":
        mouse = getattr(page, "mouse", None)
        wheel = getattr(mouse, "wheel", None) if mouse is not None else None
        dx = float(_first(decision, "dx", "delta_x") or 0)
        dy = float(_first(decision, "dy", "delta_y", "amount") or 0)
        if callable(wheel):
            wheel(dx, dy)
        else:
            evaluate = getattr(page, "evaluate", None)
            if callable(evaluate):
                evaluate(f"() => window.scrollBy({dx}, {dy})")
    elif action == "type":
        text = str(_first(decision, "text", "value") or "")
        selector = _first(decision, "selector", "target")
        if selector:
            loc = _locator(page, str(selector))
            fill = getattr(loc, "fill", None) if loc is not None else None
            if callable(fill):
                fill(text)
                return
        keyboard = getattr(page, "keyboard", None)
        type_fn = getattr(keyboard, "type", None) if keyboard is not None else None
        if callable(type_fn):
            type_fn(text)
    elif action == "keypress":
        key = str(_first(decision, "key", "text", "value") or "")
        keyboard = getattr(page, "keyboard", None)
        press = getattr(keyboard, "press", None) if keyboard is not None else None
        if callable(press) and key:
            press(key)
    elif action == "drag":
        start = _point(decision, "from", "start")
        end = _point(decision, "to", "end")
        mouse = getattr(page, "mouse", None)
        if start is not None and end is not None and mouse is not None:
            move = getattr(mouse, "move", None)
            down = getattr(mouse, "down", None)
            up = getattr(mouse, "up", None)
            if callable(move) and callable(down) and callable(up):
                move(start[0], start[1])
                down()
                move(end[0], end[1])
                up()
    elif action == "move":
        point = _point(decision, "point", "position", "coords")
        mouse = getattr(page, "mouse", None)
        move = getattr(mouse, "move", None) if mouse is not None else None
        if point is not None and callable(move):
            move(point[0], point[1])
    elif action == "wait":
        ms = float(_first(decision, "ms", "milliseconds") or 0)
        seconds = float(_first(decision, "seconds", "s") or 0)
        timeout = getattr(page, "wait_for_timeout", None)
        if callable(timeout) and ms:
            timeout(ms)
        else:
            time.sleep(max(0.0, min(seconds or (ms / 1000.0), 2.0)))
    elif action == "screenshot":
        screenshot = getattr(page, "screenshot", None)
        if callable(screenshot):
            screenshot()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
_MODALITY_ALIASES = {
    "shim": "search_shim",
    "search_shim": "search_shim",
    "search-shim": "search_shim",
    "http": "search_shim",
    "browser": "browser",
    "computeruse": "computer_use",
    "computer_use": "computer_use",
    "computer-use": "computer_use",
    "mock": "mock",
}


def make_backend(modality: str, **kw: Any) -> SandboxBackend:
    """Return the acquisition backend for ``modality``.

    Allowed modalities (with aliases): ``search_shim``/``shim`` (default),
    ``browser``, ``computer_use``/``computeruse``, ``mock``. An unknown value
    raises ``ValueError`` so a typo fails loud at construction, not silently at
    reward time.

    Keyword args are passed through to the chosen backend:
        * ``search_shim``: ``shim_url`` (default env/``localhost:8081``),
          ``max_results`` (default 10), plus any ``HttpSandboxBackend`` kwargs.
        * ``browser``: ``site_map``, ``shim_url``, ``page``, ``page_factory``,
          ``search_backend``, ``headless``, ``timeout_ms``.
        * ``computer_use``: ``inner`` (a ``SandboxBackend``), ``site_map``,
          ``shim_url``; defaults to a text-proxy stub wrapping a browser backend.
        * ``mock``: ``pages`` (``dict[url] -> text``), ``index``
          (``dict[query] -> [url|hit]``).
    """
    key = _MODALITY_ALIASES.get(str(modality).strip().lower())
    if key is None:
        raise ValueError(f"unknown acquisition modality: {modality!r}")

    if key == "search_shim":
        shim_url = kw.pop("shim_url", None) or _default_shim_url()
        max_results = int(kw.pop("max_results", 10))
        return HttpSandboxBackend(shim_url, max_results=max_results, **kw)

    if key == "browser":
        return BrowserSandboxBackend(**kw)

    if key == "computer_use":
        inner = kw.pop("inner", None)
        if inner is not None:
            return ComputerUseBackend.text_proxy(inner=inner, **kw)
        return ComputerUseBackend.text_proxy(**kw)

    if key == "mock":
        pages = kw.pop("pages", {}) or {}
        index = kw.pop("index", {}) or {}
        return MockSandboxBackend(pages, index)

    raise ValueError(f"unknown acquisition modality: {modality!r}")  # pragma: no cover


def make_backend_from_task(
    task_config: dict[str, Any],
    *,
    shim_url: str | None = None,
    mock: SandboxBackend | None = None,
    **kw: Any,
) -> SandboxBackend:
    """Select a backend from a task's ``acquisition`` block (default ``shim``).

    Shape of the optional top-level ``acquisition`` block::

        "acquisition": {
            "modalities": ["shim"],   # ordered preference; default ["shim"]
            "backend": "shim",        # optional scalar; wins if present
            "shim_url": "...",        # optional
            "max_results": 10         # optional passthrough
        }

    ``mock`` is a dependency-injection override (tests/offline): if given it is
    returned verbatim regardless of the configured modality.
    """
    if mock is not None:
        return mock
    acq = task_config.get("acquisition") or {}
    modality = (
        acq.get("backend")
        or (acq.get("modalities") or ["shim"])[0]
        or "shim"
    )
    passthrough: dict[str, Any] = dict(kw)
    eff_shim = shim_url or acq.get("shim_url")
    if eff_shim is not None:
        passthrough.setdefault("shim_url", eff_shim)
    if "max_results" in acq:
        passthrough.setdefault("max_results", acq.get("max_results"))
    return make_backend(str(modality), **passthrough)


__all__ = [
    "BrowserSandboxBackend",
    "ComputerUseBackend",
    "ComputerUsePolicy",
    "DEFAULT_SITE_MAP",
    "make_backend",
    "make_backend_from_task",
]
