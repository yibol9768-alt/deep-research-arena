"""Citation extractor — single source of truth for "what URLs did the agent cite?"

Before this module, six verifiers (url_coverage, url_reachability, quote_match,
claim_nli, citation_alignment, analysis_depth) each had their own ad-hoc URL
regex. The audit found that:

* Most only matched ``[label](url)`` markdown links — agents that emit raw
  ``https://...`` URLs (LDR) or numbered-reference style (STORM) silently
  scored 0 on those verifiers despite citing real, reachable pages.
* ``url_coverage`` canonicalised URLs (sorted query, lowercased host) for
  goldset matching, but ``url_reachability`` probed the raw form. An agent
  whose URL differed only in query-order or trailing slash could hit
  must_cite via canon but fail reachability via raw.

This module fixes both. ``extract_citations()`` returns Citation tuples with
BOTH the canonical URL (for set membership / dedup / goldset) AND the raw URL
(for HTTP probing — preserves what the agent actually emitted). It recognises
six citation styles emitted in the wild by DR frameworks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


# Public regex constants — kept exported so existing call sites can migrate
# gradually without breaking.
MD_LINK_RE = re.compile(r"\[(?P<label>[^\]]*)\]\((?P<url>https?://[^)\s]+)\)")
BARE_URL_RE = re.compile(r"(?<![(\[])(?<!\]\()https?://[^\s<>\"'`)\]]+")
NUMBERED_INLINE_RE = re.compile(r"\[(?P<n>\d{1,3})\]")
NUMBERED_REF_LINE_RE = re.compile(
    r"^\s*\[(?P<n>\d{1,3})\]\s*\.?\s*(?:[-:.]\s*)?(?P<rest>.+)$",
    re.MULTILINE,
)
FOOTNOTE_REF_LINE_RE = re.compile(
    r"^\s*\[\^(?P<n>[\w-]+)\]:\s*(?P<rest>.+)$",
    re.MULTILINE,
)
FOOTNOTE_INLINE_RE = re.compile(r"\[\^(?P<n>[\w-]+)\]")
SOURCE_PREFIX_RE = re.compile(
    r"\b(?:Source|URL|Link|See|Reference|Ref|Available\s+at|Cited\s+from)\s*[:=]\s*(?P<url>https?://\S+)",
    re.IGNORECASE,
)
BULLET_URL_RE = re.compile(
    r"^[-*+]\s+(?P<url>https?://\S+)\s*$",
    re.MULTILINE,
)

URL_TRAIL_PUNCT = ").,;:`'\"\\!?>]}"


# ---------------------------------------------------------------------------
# Canonicalisation
# ---------------------------------------------------------------------------

def canonicalize_url(url: str) -> str:
    """Return a stable form of ``url`` for set membership / goldset match.

    Rules applied (each addresses an observed mismatch in the audit):
    * Strip trailing punctuation that markdown / sentences leave.
    * Lowercase scheme and host.
    * Strip default ports (80, 443) but keep custom (7770/9999/8090).
    * Strip trailing slash on non-root paths; keep root as ``/``.
    * Sort query params.
    * Drop fragment (``#section``).
    """
    s = (url or "").strip().rstrip(URL_TRAIL_PUNCT)
    if not s:
        return ""
    try:
        p = urlparse(s)
        host = (p.hostname or "").lower()
        try:
            port = p.port
        except (ValueError, TypeError):
            port = None
        if port and port not in (80, 443):
            netloc = f"{host}:{port}"
        else:
            netloc = host
        path = p.path or "/"
        if path != "/":
            path = path.rstrip("/")
        qs = urlencode(sorted(parse_qsl(p.query, keep_blank_values=True)))
        return urlunparse((p.scheme.lower() or "http", netloc, path, "", qs, ""))
    except Exception:
        return s.lower()


def strip_url_trail(url: str) -> str:
    """Strip trailing punctuation only — does NOT canonicalise other parts."""
    return (url or "").rstrip(URL_TRAIL_PUNCT)


# ---------------------------------------------------------------------------
# Host filtering (moved from base.py — kept here so all citation logic
# lives in one module)
# ---------------------------------------------------------------------------

def host_in_set(url: str, sandbox_hosts: Iterable[str] | None) -> bool:
    """Strict host:port equality. Use this instead of substring ``h in url``
    matching — substring would match ``localhost:7770`` against
    ``localhost:77703`` or any URL whose path embeds the literal sandbox host.
    """
    if not sandbox_hosts:
        return False
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        port = p.port
    except Exception:
        return False
    if not host:
        return False
    hp = f"{host}:{port}" if port else host
    for h in sandbox_hosts:
        h = h.lower()
        if ":" in h:
            if hp == h:
                return True
        elif host == h:
            return True
    return False


# ---------------------------------------------------------------------------
# Citation dataclass + extractor
# ---------------------------------------------------------------------------

CITATION_STYLES = ("markdown", "bare", "numbered", "footnote", "source", "bullet")


@dataclass(frozen=True)
class Citation:
    """One citation found in an agent report.

    Attributes
    ----------
    canonical_url : str
        Stable form for set membership and goldset matching.
    raw_url : str
        Exactly what the agent emitted, post trailing-punct strip.
        HTTP probes use this so we test what the agent shipped.
    claim_context : str
        ~200 chars around the citation site, used by NLI / quote_match.
        Markdown links are flattened (label kept) so the LLM judge sees
        prose, not raw markdown syntax.
    char_offset : int
        Position of the citation in the original answer; used for ordering.
    style : str
        One of ``CITATION_STYLES``. Useful for analytics: e.g. agents that
        only emit ``numbered`` cite-style get extra credit fairness checks.
    """
    canonical_url: str
    raw_url: str
    claim_context: str
    char_offset: int
    style: str


def _claim_context(answer: str, span_start: int, window: int = 200) -> str:
    a = max(0, span_start - window)
    b = min(len(answer), span_start + window)
    chunk = answer[a:b]
    chunk = MD_LINK_RE.sub(lambda m: m.group("label"), chunk)
    chunk = re.sub(r"`[^`]*`", " ", chunk)
    chunk = re.sub(r"\s+", " ", chunk)
    return chunk.strip()


def _build_numbered_table(answer: str) -> dict[str, str]:
    """Parse ``[N] http://...`` reference list lines (under "## References"
    or anywhere in the doc) into ``{N: url}``."""
    table: dict[str, str] = {}
    for m in NUMBERED_REF_LINE_RE.finditer(answer):
        rest = m.group("rest").strip()
        url_m = BARE_URL_RE.search(rest)
        if not url_m:
            inner_md = MD_LINK_RE.search(rest)
            if inner_md:
                table[m.group("n")] = strip_url_trail(inner_md.group("url"))
            continue
        table[m.group("n")] = strip_url_trail(url_m.group(0))
    return table


def _build_footnote_table(answer: str) -> dict[str, str]:
    """Parse ``[^N]: http://...`` footnote definition lines."""
    table: dict[str, str] = {}
    for m in FOOTNOTE_REF_LINE_RE.finditer(answer):
        rest = m.group("rest").strip()
        url_m = BARE_URL_RE.search(rest)
        if not url_m:
            inner_md = MD_LINK_RE.search(rest)
            if inner_md:
                table[m.group("n")] = strip_url_trail(inner_md.group("url"))
            continue
        table[m.group("n")] = strip_url_trail(url_m.group(0))
    return table


def extract_citations(
    answer: str,
    sandbox_hosts: Iterable[str] | None = None,
    *,
    sandbox_only: bool = True,
    window: int = 200,
) -> list[Citation]:
    """Return every URL cited in ``answer`` regardless of citation style.

    Parameters
    ----------
    answer : str
        The agent's markdown report.
    sandbox_hosts : iterable of "host:port" or "host" strings, optional
        If given AND ``sandbox_only=True``, citations to URLs not under
        these hosts are dropped.
    sandbox_only : bool, default True
        Whether to filter by ``sandbox_hosts`` (if provided).
    window : int, default 200
        Context window (chars on each side) for ``claim_context``.

    Style precedence
    ----------------
    A given URL string is reported once. The first match in the iteration
    order wins; iteration order is: markdown → bare → numbered references
    → footnote references → ``Source:`` prefix → bullet-line. So a URL
    appearing both as ``[label](url)`` and bare is reported as ``markdown``,
    not bare.
    """
    if not answer:
        return []
    sandbox_set = set(sandbox_hosts) if sandbox_hosts else None
    out: list[Citation] = []
    seen_offsets: set[int] = set()
    seen_urls: set[str] = set()

    def _maybe_emit(raw: str, ctx_offset: int, style: str) -> None:
        raw = strip_url_trail(raw)
        if not raw:
            return
        if sandbox_only and sandbox_set and not host_in_set(raw, sandbox_set):
            return
        canon = canonicalize_url(raw)
        # Same offset reported multiple times by overlapping passes -> skip.
        if ctx_offset in seen_offsets:
            return
        # Same URL elsewhere already counted? Keep both — multiple cites of
        # the same URL are legitimate (different claims).
        seen_offsets.add(ctx_offset)
        seen_urls.add(canon)
        out.append(Citation(
            canonical_url=canon,
            raw_url=raw,
            claim_context=_claim_context(answer, ctx_offset, window=window),
            char_offset=ctx_offset,
            style=style,
        ))

    # Iteration order matters — `_maybe_emit` rejects re-counts of the same
    # offset. Sort styles from most-specific to least-specific so a URL
    # surrounded by an anchoring pattern (e.g. "Source: <url>") is reported
    # under that style instead of falling through to bare.

    # 1. Markdown links: [label](url) — most explicit, definite citation.
    for m in MD_LINK_RE.finditer(answer):
        _maybe_emit(m.group("url"), m.start(), "markdown")

    # 2. "Source: <url>" / "URL: <url>" / "See: <url>" — explicit prefix.
    for m in SOURCE_PREFIX_RE.finditer(answer):
        _maybe_emit(m.group("url"), m.start("url"), "source")

    # 3. Bullet-line URLs `- http://...` (alone on the line).
    for m in BULLET_URL_RE.finditer(answer):
        _maybe_emit(m.group("url"), m.start("url"), "bullet")

    # 4. Numbered references: parse `[N] url` table once, then each inline
    #    `[N]` anchor cites that URL. Style = "numbered".
    num_table = _build_numbered_table(answer)
    if num_table:
        for m in NUMBERED_INLINE_RE.finditer(answer):
            url = num_table.get(m.group("n"))
            if not url:
                continue
            _maybe_emit(url, m.start(), "numbered")

    # 5. Footnote references: `[^id]: url` definitions + inline `[^id]`.
    fn_table = _build_footnote_table(answer)
    if fn_table:
        for m in FOOTNOTE_INLINE_RE.finditer(answer):
            url = fn_table.get(m.group("n"))
            if not url:
                continue
            _maybe_emit(url, m.start(), "footnote")

    # 6. Bare URLs — catchall for anything not anchored above.
    for m in BARE_URL_RE.finditer(answer):
        _maybe_emit(m.group(0), m.start(), "bare")

    out.sort(key=lambda c: c.char_offset)
    return out


def extract_cited_urls(
    answer: str,
    sandbox_hosts: Iterable[str] | None = None,
    *,
    sandbox_only: bool = True,
) -> tuple[set[str], dict[str, set[str]]]:
    """Backward-compat wrapper for ``url_coverage_verifier``.

    Returns
    -------
    canonical : set[str]
        Distinct canonical URL strings cited in ``answer``.
    canon_to_raw : dict[str, set[str]]
        Map from canonical URL to the raw forms that produced it. Useful
        when reporting which exact string the agent emitted.
    """
    citations = extract_citations(answer, sandbox_hosts, sandbox_only=sandbox_only)
    canon_to_raw: dict[str, set[str]] = {}
    for c in citations:
        canon_to_raw.setdefault(c.canonical_url, set()).add(c.raw_url)
    return set(canon_to_raw.keys()), canon_to_raw


def extract_cited_pairs(
    answer: str,
    sandbox_hosts: Iterable[str] | None = None,
    *,
    window: int = 200,
    sandbox_only: bool = True,
) -> list[tuple[str, str, int]]:
    """Backward-compat wrapper for ``base.extract_cited_pairs`` callers
    (quote_match, claim_nli). Returns ``(raw_url, claim_context, char_offset)``
    so existing call sites keep working unchanged.
    """
    return [
        (c.raw_url, c.claim_context, c.char_offset)
        for c in extract_citations(
            answer, sandbox_hosts, sandbox_only=sandbox_only, window=window,
        )
    ]
