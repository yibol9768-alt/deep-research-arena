"""Typed tool registry over the ``SandboxBackend`` acquisition seam.

This is the P0 foundation from ``docs/ACQUISITION_ROADMAP.md`` section 2: a small
registry of typed callables that the seven-action env loop dispatches into via
the single new ``CallTool`` opcode. The grounding reward stays modality-agnostic
by construction: a tool lands its ``(url, page_text)`` pairs into the SAME
``retrieved_snippets`` / ``fetched_urls`` stores the env already maintains
(see ``src/eval/evaluator.py::_compute_ground_signals``), so tool-acquired
evidence is indistinguishable from a ``Read`` at reward time.

Design contract (kept verbatim from the roadmap):

* The two floor tools ``search`` / ``fetch`` are thin wrappers over the live
  ``ToolContext.backend`` so the floor goes through the registry with zero
  behaviour change. The default env path does NOT route Search/Open/Read through
  them; those keep their dedicated opcodes. The tools exist so an explicit
  ``TOOL: search`` / ``TOOL: fetch`` is accepted uniformly and the MCP wrapper +
  allow-list have a single registry surface.
* :class:`StructuredLookupTool` (``structured_lookup``) is the first genuinely
  new tool: it POSTs to the shim ``/product_lookup`` or ``/post_lookup`` and
  lands a deterministic text rendering of the typed record into the grounding
  store so the reward credits the PDP/post URL like a fetched page.

No heavy/top-level imports: only ``dataclasses`` / ``typing`` and the cheap
``canonicalize_url`` helper. ``requests`` is imported lazily inside
:meth:`StructuredLookupTool.run`, so ``import src.rl.tools`` succeeds on a plain
``python3`` with no requests installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Protocol, runtime_checkable

# Cheap, dependency-free helper so tools key snippets exactly like ``_do_read``.
from src.verifiers.citation_format import canonicalize_url

# A search hit is the same loose dict shape the env uses.
Hit = dict[str, Any]


# ---------------------------------------------------------------------------
# Result / context value objects
# ---------------------------------------------------------------------------
@dataclass
class ToolResult:
    """The union return of every tool.

    A tool may land grounding pairs (``snippets`` / ``fetched_urls``), emit
    search-style ``hits`` for the SERP path, render ``display`` text into the
    observation, and/or record a ``state_delta`` for a non-grounding verifier
    (P3 write-actions only; unused by grounding).
    """

    snippets: dict[str, str] = field(default_factory=dict)
    fetched_urls: list[str] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    state_delta: dict | None = None
    display: str = ""
    ok: bool = True
    error: str | None = None
    n_results: int = 0


@dataclass
class ToolContext:
    """Env plumbing handed to a tool so it never reimplements fetch/canonicalize.

    ``fetch`` is the bound env helper (``lambda u: self._truncate_text(
    self.backend.fetch(u))``) so a tool reuses truncation + the live backend.
    ``extras`` is the injection seam: ``run_id``, allow-list, and the
    structured-lookup transport (``structured_lookup_post``) live here.
    """

    backend: Any
    task_config: dict[str, Any] = field(default_factory=dict)
    fetch: Callable[[str], str] = lambda url: ""  # noqa: E731 - replaced by env
    canonicalize: Callable[[str], str] = canonicalize_url
    extras: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tool protocol
# ---------------------------------------------------------------------------
@runtime_checkable
class Tool(Protocol):
    """A typed callable. Implementations are plain classes; no ABC needed."""

    name: str
    description: str
    args_schema: dict

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult: ...


# ---------------------------------------------------------------------------
# Floor tools: thin wrappers over the live backend
# ---------------------------------------------------------------------------
def _normalize_hit(hit: Any) -> Hit:
    """Loose hit normalization, mirroring ``src.rl.env._normalize_hit``.

    Kept local so this module imports without pulling ``src.rl.env`` (which
    would create an import cycle: env imports ``build_tool_registry`` lazily).
    """

    if isinstance(hit, dict):
        url = str(hit.get("url") or hit.get("link") or "").strip()
        return {
            "url": url,
            "title": str(hit.get("title") or url),
            "snippet": str(hit.get("snippet") or hit.get("content") or ""),
        }
    url = str(hit).strip()
    return {"url": url, "title": url, "snippet": ""}


def _serp_display(hits: list[Hit], limit: int = 5) -> str:
    """Compact SERP rendering for the obs/tool-result message."""

    lines: list[str] = []
    for idx, hit in enumerate(hits[:limit], start=1):
        title = str(hit.get("title") or hit.get("url") or "untitled")
        url = str(hit.get("url") or "").strip()
        lines.append(f"{idx}. {title}")
        if url:
            lines.append(f"   url: {url}")
    return "\n".join(lines)


class SearchTool:
    """``search`` floor tool: wraps ``ctx.backend.search`` -> ``hits``.

    The env folds ``hits`` into ``_state.search_results`` exactly like
    ``_do_search`` and records the call under ``/tool/search`` (whose endpoint
    substring still contains "search", so process-reward search-breadth parity
    is preserved for tool-issued searches).
    """

    name = "search"
    description = "Free-text search: query in, ranked (title,url,snippet) hits out."
    args_schema: dict = {
        "query": {"type": "string", "required": True},
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        query = str(args.get("query") or args.get("q") or "").strip()
        hits = [_normalize_hit(h) for h in (ctx.backend.search(query) or [])]
        hits = [h for h in hits if h.get("url")]
        return ToolResult(
            hits=hits,
            n_results=len(hits),
            display=_serp_display(hits),
            ok=True,
        )


class FetchTool:
    """``fetch`` floor tool: wraps ``ctx.fetch`` -> ``(url, text)``.

    Folding lands ``(url, text)`` into ``retrieved_snippets[canonicalize_url(
    url)]`` + ``fetched_urls`` -- the SAME slots ``_do_read`` writes, so a page
    fetched via ``TOOL: fetch`` is byte-identical to Open+Read at reward time.
    """

    name = "fetch"
    description = "Fetch a known URL and return boilerplate-stripped page text."
    args_schema: dict = {
        "url": {"type": "string", "required": True},
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("link") or "").strip()
        text = ctx.fetch(url) if url else ""
        text = str(text or "")
        if not text:
            return ToolResult(n_results=0, display="", ok=False, error="empty_fetch")
        return ToolResult(
            snippets={url: text},
            fetched_urls=[url],
            n_results=1,
            display=text,
            ok=True,
        )


# ---------------------------------------------------------------------------
# Structured lookup: the first genuinely-new tool (roadmap modality 5 / P1.5)
# ---------------------------------------------------------------------------
# Typed field order for the deterministic text rendering. Order is fixed so the
# rendered grounding text is reproducible across runs.
_PRODUCT_FIELDS = (
    "name",
    "price",
    "rating",
    "sku",
    "description",
    "review_count",
    "in_stock",
)
_POST_FIELDS = (
    "title",
    "author",
    "forum",
    "score",
    "comment_count",
    "body",
)


def _render_record(record: dict[str, Any], fields: Iterable[str]) -> str:
    """Deterministic ``key: value`` rendering of a typed record.

    Only the declared typed fields are rendered (in order); ``None`` values are
    skipped so the text is clean. ``top_comments`` (a list) is appended last for
    posts so its body text is grounding-creditable too.
    """

    lines: list[str] = []
    for key in fields:
        value = record.get(key)
        if value is None or value == "":
            continue
        lines.append(f"{key}: {value}")
    top = record.get("top_comments")
    if isinstance(top, list) and top:
        rendered_comments: list[str] = []
        for comment in top:
            if isinstance(comment, dict):
                body = str(comment.get("body") or comment.get("text") or "").strip()
                author = str(comment.get("author") or "").strip()
                if body:
                    rendered_comments.append(f"- {author}: {body}" if author else f"- {body}")
            else:
                text = str(comment).strip()
                if text:
                    rendered_comments.append(f"- {text}")
        if rendered_comments:
            lines.append("top_comments:")
            lines.extend(rendered_comments)
    return "\n".join(lines)


class StructuredLookupTool:
    """Schema-aware lookup: POST the shim ``/product_lookup`` or ``/post_lookup``.

    Returns the typed record (product or post) as ``display`` and lands a
    deterministic text rendering of it into ``snippets`` + ``fetched_urls`` so
    the grounding reward credits the PDP/post URL exactly like a fetched page.
    Read-only, so ``state_delta`` stays ``None``.

    Transport resolution (offline-safe):
        1. ``ctx.extras["structured_lookup_post"]`` -- an injected callable
           ``(path: str, payload: dict) -> dict`` (tests / DI). Used if present.
        2. Otherwise a lazy ``requests`` POST against the task's shim URL using
           the SAME ``proxies={"http": None, "https": None}`` pattern as
           ``HttpSandboxBackend._post_json``. ``requests`` is imported inside
           ``run`` so this module imports with no requests installed.
    """

    name = "structured_lookup"
    description = (
        "Schema-aware connector: returns a typed product or post record for a "
        "given PDP/post URL, and lands it into the grounding store."
    )
    args_schema: dict = {
        "url": {"type": "string", "required": True},
        "kind": {"type": "string", "required": False, "enum": ["product", "post", "auto"]},
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or "").strip()
        if not url:
            return ToolResult(ok=False, error="empty_url")
        kind = str(args.get("kind") or "auto").strip().lower() or "auto"

        path, fields = self._resolve_endpoint(url, kind)
        try:
            record = self._transport(ctx, path, {"url": url})
        except Exception as exc:  # transport failure is graceful, never a crash
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")

        if not isinstance(record, dict):
            return ToolResult(ok=False, error="malformed_lookup_response")
        if not record.get("ok", False):
            return ToolResult(ok=False, error=str(record.get("error") or "lookup_failed"))

        rendered = _render_record(record, fields)
        if not rendered:
            return ToolResult(ok=False, error="empty_record")

        return ToolResult(
            snippets={url: rendered},
            fetched_urls=[url],
            n_results=1,
            display=rendered,
            ok=True,
        )

    # -- endpoint / kind routing --
    def _resolve_endpoint(self, url: str, kind: str) -> tuple[str, tuple[str, ...]]:
        if kind == "product":
            return "/product_lookup", _PRODUCT_FIELDS
        if kind == "post":
            return "/post_lookup", _POST_FIELDS
        # auto: choose by host/path, product as the default fallback.
        lowered = url.lower()
        if (
            ":9999" in lowered
            or "reddit" in lowered
            or "/f/" in lowered
        ):
            return "/post_lookup", _POST_FIELDS
        # ":7770" / SHOPPING / anything else -> product.
        return "/product_lookup", _PRODUCT_FIELDS

    # -- transport: injected callable, else lazy requests against the shim --
    def _transport(self, ctx: ToolContext, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        injected = (ctx.extras or {}).get("structured_lookup_post")
        if callable(injected):
            return injected(path, payload)

        shim_url = (
            (ctx.extras or {}).get("shim_url")
            or (ctx.task_config.get("acquisition") or {}).get("shim_url")
            or ctx.task_config.get("shim_url")
        )
        if not shim_url:
            raise RuntimeError("structured_lookup requires a shim_url or an injected transport")

        try:
            import requests  # lazy: module imports without requests installed
        except Exception as exc:  # pragma: no cover - exercised on training box
            raise RuntimeError(
                "structured_lookup requires requests and the training sandbox"
            ) from exc

        base = str(shim_url).rstrip("/")
        bearer = (ctx.extras or {}).get("bearer_token", "sandbox")
        headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
        timeout = float((ctx.extras or {}).get("timeout", 60.0))
        response = requests.post(
            f"{base}/{path.lstrip('/')}",
            json=payload,
            headers=headers,
            timeout=timeout,
            # localhost shim: never route through an HTTP proxy.
            proxies={"http": None, "https": None},
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
class ToolRegistry:
    """Insertion-ordered name -> Tool map with an allow-list view."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register ``tool`` keyed by ``tool.name``; a later register overrides."""

        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(str(name))

    def list(self) -> list[str]:
        return list(self._tools.keys())

    def has(self, name: str) -> bool:
        return str(name) in self._tools

    def allowed(self, names: Iterable[str] | None) -> "ToolRegistry":
        """Return a filtered view containing only registered names in the allow-list.

        ``None`` falls back to the floor ``["search", "fetch"]``. Unknown
        requested names are silently dropped (the env enforces the allow-list at
        call time, returning ``tool_not_allowed`` for any missing name).
        """

        allow = list(names) if names is not None else ["search", "fetch"]
        view = ToolRegistry()
        for name in allow:
            tool = self._tools.get(str(name))
            if tool is not None:
                view.register(tool)
        return view


# Provider modules discovered at registry-build time. Each exposes
# provide_tools()->list[Tool]. Import is deferred to _discover_provider_tools
# so a missing heavy dep only omits that one provider, never breaks the build.
_PROVIDERS: tuple[str, ...] = (
    "src.rl.tools_rag",     # rag_search
    "src.rl.tools_sql",     # sql_query
    "src.rl.tools_crawl",   # crawl
    "src.rl.tools_exec",    # run_code, run_bash
    "src.rl.tools_write",   # cart_add, order_place, order_cancel
    "src.rl.tools_vision",  # read_image
)


def _discover_provider_tools() -> list[Tool]:
    import importlib

    tools: list[Tool] = []
    for modname in _PROVIDERS:
        try:
            mod = importlib.import_module(modname)
            provide = getattr(mod, "provide_tools", None)
            if callable(provide):
                tools.extend(provide() or [])
        except Exception:
            # ImportError (missing optional dep / module not yet created) or any
            # provider failure -> omit that provider's tools; registry build
            # never crashes.
            continue
    return tools


def _build_full_registry() -> ToolRegistry:
    """Construct the full registry: floor tools first, then new tools."""

    registry = ToolRegistry()
    # Floor first so it is always present and registered before everything else.
    registry.register(SearchTool())
    registry.register(FetchTool())
    # New tools.
    registry.register(StructuredLookupTool())
    # P1 provider tools (rag_search/sql_query/crawl/run_code/run_bash), discovered
    # via the provide_tools() contract. Best-effort: a missing optional dep or an
    # absent provider module is swallowed so the default floor path is unaffected.
    for tool in _discover_provider_tools():
        registry.register(tool)
    return registry


def build_default_registry() -> ToolRegistry:
    """Return the full registry with every built-in tool (unfiltered).

    Convenience for tests / the MCP wrapper that wants the complete tool surface
    without a per-task allow-list.
    """

    return _build_full_registry()


def build_tool_registry(task_config: dict[str, Any], ctx: ToolContext | None = None) -> ToolRegistry:
    """Build the per-task registry, filtered by ``acquisition.tools_allowed``.

    The full registry (search, fetch, structured_lookup, future tools) is
    constructed, then filtered to the task's allow-list. Default (field absent or
    null) is the floor ``["search", "fetch"]`` -- identical to today because the
    policy never emits ``TOOL:`` for those (Search/Open/Read keep their own
    opcodes), so the registry is built but never consulted on the default path.

    ``ctx`` is accepted for symmetry and future use (e.g. logging dropped names
    via ``ctx.extras``); it is not required to build the registry.
    """

    acq = task_config.get("acquisition") or {}
    allowed = acq.get("tools_allowed")
    full = _build_full_registry()

    if ctx is not None and allowed:
        # Best-effort: note any requested name that is not registered, so a
        # silent drop is observable in extras (never raised).
        dropped = [str(n) for n in allowed if not full.has(str(n))]
        if dropped:
            try:
                ctx.extras.setdefault("dropped_tools", []).extend(dropped)
            except Exception:
                pass

    return full.allowed(allowed or ["search", "fetch"])


__all__ = [
    "Tool",
    "ToolResult",
    "ToolContext",
    "ToolRegistry",
    "build_tool_registry",
    "build_default_registry",
    "SearchTool",
    "FetchTool",
    "StructuredLookupTool",
]
