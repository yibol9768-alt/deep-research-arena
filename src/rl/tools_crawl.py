"""``crawl`` provider: bounded seed-URL link-following over the fixed sandbox.

This is P1 acquisition modality 3 from ``docs/ACQUISITION_ROADMAP.md`` section 3.
It is wired into the registry purely through the PROVIDER-DISCOVERY CONTRACT:
this module exposes a single module-level :func:`provide_tools` factory that the
``src.rl.tools._discover_provider_tools`` loop calls at registry-build time.
``src/rl/tools.py`` is never edited by this module's owner.

What ``crawl`` does
-------------------
Breadth-first link-following from a seed URL. It uses ``ctx.backend.fetch(url)``
(via ``ctx.fetch``) for each page's text and a cheap, dependency-free href
extractor (regex over the returned HTML/markdown) to discover links. Only links
that pass the host:port allowlist + optional ``path_filter`` are enqueued; the
crawl honours ``max_depth`` and ``max_pages``. ONE call returns MANY ``(url,
text)`` pairs.

Modality-agnostic reward (the HARD INVARIANT)
---------------------------------------------
For each page successfully fetched within the budget the tool lands a grounding
pair, so each pair credits EXACTLY like a ``fetch`` of that page:

* ``snippets``     -> ``{url: page_text}`` for every crawled page, which the env
  folds into ``retrieved_snippets[canonicalize_url(url)]`` (the SAME slot
  ``_do_read`` writes), so a report citing any crawled page resolves
  ``r_resolve`` / ``f1_claim`` identical to a ``fetch``.
* ``fetched_urls`` -> ``[all crawled urls]``; ``display`` -> a rendered list
  ``depth d: url (N chars)``. Read-only, so ``state_delta`` stays ``None``.

Security guards
---------------
* ALLOWLIST: every candidate URL (seed + every extracted link) must pass a
  host:port-equality check against the three sandbox hosts
  ``{localhost:7770, :9999, :8090}`` (plus the ``127.0.0.1`` variants), reusing
  the same logic as the shim's ``_url_is_sandbox`` (re-implemented locally here,
  or overridden via ``ctx.extras["url_is_sandbox"]`` injection so no shim
  import). Off-allowlist links are silently dropped (never fetched); an
  off-allowlist ``seed_url`` -> ``ToolResult(ok=False,
  error="seed_not_in_allowlist")``.
* BOUNDS: ``max_depth`` clamped to ``<= 3``, ``max_pages`` clamped to ``<= 25``;
  per-page fetch failures are skipped (graceful); URLs are deduped by their
  canonical form; an optional ``path_filter`` substring keeps the crawl tight.
  No JS, no recursion beyond the budget.

No heavy/top-level imports: only ``re`` / ``typing`` / the cheap ``ToolResult``
value object. ``import src.rl.tools_crawl`` and ``provide_tools()`` succeed on a
plain ``python3``.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

from src.rl.tools import ToolContext, ToolResult

# Default sandbox allowlist (host:port equality, mirrors the shim's
# SHIM_ALLOWLIST_HOSTS for the three corpus hosts + the 127.0.0.1 variants).
_ALLOWLIST_HOSTS: frozenset[str] = frozenset(
    {
        "localhost:7770",
        "localhost:9999",
        "localhost:8090",
        "127.0.0.1:7770",
        "127.0.0.1:9999",
        "127.0.0.1:8090",
    }
)

# Clamp limits from the DESIGN security guard.
_MAX_DEPTH_CAP = 3
_MAX_PAGES_CAP = 25
_DEFAULT_MAX_DEPTH = 1
_DEFAULT_MAX_PAGES = 10

# Cheap href extraction over HTML anchors AND markdown links. No HTML parser dep.
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"'#\s]+)["']""", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\]\(\s*([^)\s]+)\s*\)")
# Bare http(s) URLs that appear in plain text / markdown bodies.
_BARE_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")


# ---------------------------------------------------------------------------
# Allowlist (host:port equality, re-implemented locally; no shim import)
# ---------------------------------------------------------------------------
def _default_url_is_sandbox(url: str) -> bool:
    """Strict host:port equality check against the three corpus hosts.

    Substring matching (``"localhost:7770" in url``) is unsafe -- it would admit
    ``http://localhost:77703/leak`` because the literal is a prefix. We parse the
    URL and compare ``host:port`` netlocs exactly, mirroring the shim's
    ``_url_is_sandbox``.
    """
    if not url:
        return False
    try:
        p = urlparse(url)
    except Exception:
        return False
    host = (p.hostname or "").lower()
    if not host:
        return False
    try:
        port = p.port
    except (ValueError, TypeError):
        return False  # malformed / out-of-range port -> reject
    if port is None:
        # A bare host with no port is not one of our :7770/:9999/:8090 hosts.
        return False
    return f"{host}:{port}" in _ALLOWLIST_HOSTS


def _resolve_allowlist_fn(ctx: ToolContext) -> Any:
    """Resolve the allowlist predicate: injected first, else the local default."""
    injected = (ctx.extras or {}).get("url_is_sandbox")
    if callable(injected):
        return injected
    return _default_url_is_sandbox


# ---------------------------------------------------------------------------
# Link extraction
# ---------------------------------------------------------------------------
def _extract_links(base_url: str, text: str) -> list[str]:
    """Extract candidate absolute links from a page's HTML/markdown/text.

    Relative hrefs are resolved against ``base_url``; fragments are stripped.
    Returns deduped, order-preserving absolute URLs. No allowlist filtering here
    (the caller filters); this is a cheap parse with no HTML dependency.
    """
    if not text:
        return []
    raw: list[str] = []
    raw.extend(_HREF_RE.findall(text))
    raw.extend(_MD_LINK_RE.findall(text))
    raw.extend(_BARE_URL_RE.findall(text))

    out: list[str] = []
    seen: set[str] = set()
    for href in raw:
        href = str(href).strip()
        # Bare URLs in prose often capture trailing sentence punctuation
        # (e.g. "see http://host/page." or "(http://host/page)"). Strip a
        # trailing run of common punctuation so the link resolves cleanly.
        href = href.rstrip(".,;:!?)”’'\"")
        if not href:
            continue
        low = href.lower()
        # Skip non-navigational schemes.
        if low.startswith(("mailto:", "javascript:", "tel:", "data:")):
            continue
        try:
            absolute = urljoin(base_url, href)
            absolute, _frag = urldefrag(absolute)
        except Exception:
            continue
        absolute = absolute.strip()
        if not absolute or absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
    return out


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------
class CrawlTool:
    """``crawl``: bounded BFS link-following; lands many (url, text) pairs.

    From ``seed_url`` it fetches each page (``ctx.fetch``), extracts links,
    enqueues only allowlisted links that pass ``path_filter``, and continues
    until ``max_depth`` / ``max_pages`` is hit. Every successfully fetched page
    is landed into the grounding store keyed by its real sandbox URL, so a later
    ``Cite(url)`` resolves exactly like a ``fetch`` (the modality-agnostic
    invariant).

    Read-only: no exec, no writes. Off-allowlist links are silently dropped; an
    off-allowlist seed returns ``ToolResult(ok=False,
    error="seed_not_in_allowlist")`` and NEVER crashes.
    """

    name = "crawl"
    description = (
        "Bounded seed-URL link-following over the sandbox allowlist: BFS from a "
        "seed up to depth/page limits, returning many (url, text) pairs landed "
        "into grounding."
    )
    args_schema: dict = {
        "seed_url": {"type": "string", "required": True},
        "max_depth": {"type": "int", "required": False, "default": _DEFAULT_MAX_DEPTH},
        "max_pages": {"type": "int", "required": False, "default": _DEFAULT_MAX_PAGES},
        "path_filter": {"type": "string", "required": False},
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        seed_url = str(args.get("seed_url") or args.get("url") or "").strip()
        if not seed_url:
            return ToolResult(ok=False, error="empty_seed_url")

        is_sandbox = _resolve_allowlist_fn(ctx)
        if not is_sandbox(seed_url):
            return ToolResult(ok=False, error="seed_not_in_allowlist")

        max_depth = max(0, min(_MAX_DEPTH_CAP, _coerce_int(args.get("max_depth"), _DEFAULT_MAX_DEPTH)))
        max_pages = max(1, min(_MAX_PAGES_CAP, _coerce_int(args.get("max_pages"), _DEFAULT_MAX_PAGES)))
        path_filter = str(args.get("path_filter") or "").strip()

        canonicalize = ctx.canonicalize or (lambda u: u)
        fetch = ctx.fetch

        # BFS. Dedupe by canonical URL so trivial variants are not re-fetched.
        seed_canon = canonicalize(seed_url)
        queued: set[str] = {seed_canon}
        frontier: list[tuple[str, int]] = [(seed_url, 0)]

        snippets: dict[str, str] = {}
        fetched_urls: list[str] = []
        rendered_lines: list[str] = []

        while frontier and len(fetched_urls) < max_pages:
            url, depth = frontier.pop(0)
            try:
                text = fetch(url) if callable(fetch) else ""
            except Exception:
                # A per-page fetch failure is skipped, never fatal.
                continue
            text = str(text or "")
            if not text:
                continue

            snippets[url] = text
            fetched_urls.append(url)
            rendered_lines.append(f"depth {depth}: {url} ({len(text)} chars)")

            if len(fetched_urls) >= max_pages:
                break
            if depth >= max_depth:
                continue

            # Discover + enqueue allowlisted, path-filtered, deduped children.
            for child in _extract_links(url, text):
                if not is_sandbox(child):
                    continue  # off-allowlist links are silently dropped
                if path_filter and path_filter not in child:
                    continue
                child_canon = canonicalize(child)
                if child_canon in queued:
                    continue
                queued.add(child_canon)
                frontier.append((child, depth + 1))

        if not fetched_urls:
            return ToolResult(ok=False, error="crawl_no_pages_fetched", display="(no pages crawled)")

        return ToolResult(
            snippets=snippets,
            fetched_urls=fetched_urls,
            n_results=len(fetched_urls),
            display="\n".join(rendered_lines),
            ok=True,
        )


# ---------------------------------------------------------------------------
# Provider-discovery contract
# ---------------------------------------------------------------------------
def provide_tools() -> list[Any]:
    """Return this module's tools for the registry discovery loop.

    Called with NO args at registry-build time; cheap (no I/O, no heavy import).
    Returns exactly one tool: ``crawl``.
    """
    return [CrawlTool()]


__all__ = [
    "CrawlTool",
    "provide_tools",
]
