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
# Kept for backward-compatible imports.  The authoritative markdown parser is
# ``iter_markdown_links`` below: a regex cannot distinguish the ``)`` in
# ``Qi_(standard)`` from the ``)`` that closes ``[label](destination)``.
# One level of balanced brackets is allowed inside the label: CommonMark says
# `[a [b] c](url)` is a link, every renderer shows it, and 35 store products
# across 23 tasks carry literal "[Discontinued]"-style markers in their names.
# With `[^\]]*` the extractor returned NO citation for a label that faithfully
# copies such a product title, so the same-line citation requirement silently
# made those nuggets uncoverable and the lane was scored as if it had not cited.
MD_LINK_RE = re.compile(
    r"\[(?P<label>(?:[^\[\]]|\[[^\]]*\])*)\]\((?P<url>https?://[^)\s]+)\)")
# Include parentheses in the candidate and let ``strip_url_trail`` remove only
# *unbalanced* closing punctuation.  This fixes bare Kiwix titles such as
# ``.../Ray_tracing_(graphics)`` as well as markdown destinations.
BARE_URL_RE = re.compile(r"(?<![(\[])(?<!\]\()https?://[^\s<>\"'`\]]+")
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
_URL_TRAIL_NONPAREN = ".,;:`'\"\\!?>]}"


@dataclass(frozen=True)
class MarkdownLink:
    """One parsed inline markdown link with balanced destination brackets."""

    label: str
    url: str
    start: int
    end: int
    url_start: int
    url_end: int


def iter_markdown_links(text: str):
    """Yield inline markdown links while preserving balanced ``(...)`` URLs.

    Python's regular-expression engine cannot recursively balance parentheses.
    The previous ``[^)]`` pattern therefore truncated three shipped concept
    sources at the first ``(``.  This small scanner treats parentheses inside
    the destination as nested and the first unmatched ``)`` as markdown's
    closing delimiter.  Whitespace remains illegal in a bare destination;
    angle-bracket destinations are accepted as Markdown permits.
    """
    if not text:
        return
    pos = 0
    n = len(text)
    while pos < n:
        lb = text.find("[", pos)
        if lb < 0:
            return
        # CommonMark allows balanced brackets inside the label: `[a [b] c](u)`
        # is a link in every renderer.  35 store products across 23 tasks carry
        # literal "[Discontinued]"-style markers in their names; taking the
        # FIRST `]` here dropped the citation of any agent that copied such a
        # title faithfully, making its nugget silently uncoverable.
        rb = -1
        bdepth = 0
        j = lb + 1
        while j < n:
            cj = text[j]
            if cj == "\\":
                j += 2
                continue
            if cj == "[":
                bdepth += 1
            elif cj == "]":
                if bdepth == 0:
                    rb = j
                    break
                bdepth -= 1
            j += 1
        if rb < 0:
            # This ``[`` has no balanced closing ``]`` (e.g. a stray "[4/5" or
            # "[TODO" in the prose). CommonMark treats such an unmatched bracket
            # as literal text, not a fatal parse error. Returning here -- as the
            # first version of this scanner did -- silently dropped EVERY later
            # markdown link in the report, so a single stray "[" zeroed a lane's
            # citations (the old MD_LINK_RE.finditer never had this failure mode).
            # Skip past this bracket and keep scanning.
            pos = lb + 1
            continue
        p = rb + 1
        while p < n and text[p] in " \t":
            p += 1
        if p >= n or text[p] != "(":
            pos = lb + 1
            continue
        p += 1
        while p < n and text[p] in " \t":
            p += 1
        angled = p < n and text[p] == "<"
        if angled:
            p += 1
        url_start = p
        if not text.startswith(("http://", "https://"), url_start):
            pos = lb + 1
            continue
        depth = 0
        escaped = False
        i = url_start
        url_end = end = None
        while i < n:
            ch = text[i]
            if escaped:
                escaped = False
                i += 1
                continue
            if ch == "\\":
                escaped = True
                i += 1
                continue
            if angled:
                if ch == ">":
                    url_end = i
                    j = i + 1
                    while j < n and text[j] in " \t":
                        j += 1
                    if j < n and text[j] == ")":
                        end = j + 1
                    break
                if ch in "\r\n":
                    break
            else:
                if ch.isspace():
                    break
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    if depth == 0:
                        url_end, end = i, i + 1
                        break
                    depth -= 1
            i += 1
        if url_end is None or end is None:
            pos = lb + 1
            continue
        raw = strip_url_trail(text[url_start:url_end])
        if raw:
            yield MarkdownLink(
                label=text[lb + 1:rb], url=raw, start=lb, end=end,
                url_start=url_start, url_end=url_end,
            )
        pos = end


def replace_markdown_links(text: str, repl) -> str:
    """Replace links parsed by :func:`iter_markdown_links` without regex drift.

    ``repl`` may be a constant string or a callable receiving ``MarkdownLink``.
    """
    links = list(iter_markdown_links(text or ""))
    if not links:
        return text or ""
    chunks, pos = [], 0
    for link in links:
        chunks.append(text[pos:link.start])
        chunks.append(repl(link) if callable(repl) else repl)
        pos = link.end
    chunks.append(text[pos:])
    return "".join(chunks)


# ---------------------------------------------------------------------------
# Canonicalisation
# ---------------------------------------------------------------------------

_KIWIX_HOSTS = {"localhost:8090"}


def _kiwix_normalize_path(path: str) -> str:
    """Collapse Kiwix article-URL aliases to one canonical path.

    Kiwix on localhost:8090 serves the same Wikipedia article under many URL
    forms, depending on the book name, the no-JS variant, and historical
    redirects:

        /content/wikipedia_en_all_nopic/A/Microplastics   <- canonical
        /A/Microplastics
        /wiki/Microplastics
        /wikipedia_en_all_maxi_2022-05/A/Microplastics
        /nojs/wikipedia_en_all/A/Microplastics
        /nojs/A/Microplastics
        /nojs/eng%20wikipedia/A/Microplastics
        /kiwix/content/wikipedia_en_all_maxi/A/Microplastics

    The article id keeps its ORIGINAL CASE (audit G-F3). kiwix-serve is
    case-sensitive, and the canonical form doubles as the probe/fetch
    fallback (url_reachability retries it on a non-200), so the historical
    ``.lower()`` here turned real wiki citations into 404s and recorded
    honest agents as fabricators. Case-insensitive comparison is still
    available, but only through the clearly named ``fuzzy_url_key()``
    helper, never in the canonical/probe form.
    """
    # /A/<id>  (Kiwix article namespace)
    idx = path.rfind("/A/")
    if idx != -1:
        return f"/content/wikipedia_en_all_nopic/A/{path[idx + 3:]}"
    # /wiki/<id>  (legacy Wikipedia path used by some Kiwix configs)
    idx = path.rfind("/wiki/")
    if idx != -1:
        return f"/content/wikipedia_en_all_nopic/A/{path[idx + 6:]}"
    return path


def canonicalize_url(url: str) -> str:
    """Return a stable form of ``url`` for set membership / goldset match.

    Rules applied (each addresses an observed mismatch in the audit):
    * Strip trailing punctuation that markdown / sentences leave.
    * Lowercase scheme and host.
    * Strip default ports (80, 443) but keep custom (7770/9999/8090).
    * Collapse Kiwix article-URL aliases (see ``_kiwix_normalize_path``).
    * Strip trailing slash on non-root paths; keep root as ``/``.
    * Sort query params.
    * Drop fragment (``#section``).
    """
    s = strip_url_trail((url or "").strip())
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
        if netloc in _KIWIX_HOSTS:
            path = _kiwix_normalize_path(path)
        if path != "/":
            path = path.rstrip("/")
        qs = urlencode(sorted(parse_qsl(p.query, keep_blank_values=True)))
        return urlunparse((p.scheme.lower() or "http", netloc, path, "", qs, ""))
    except Exception:
        return s.lower()


def fuzzy_url_key(url: str) -> str:
    """Lowercased canonical form for FUZZY comparison ONLY.

    Use for tolerant set matching (e.g. goldset membership where an agent's
    case typo, calisthenics vs Calisthenics, should not cost the match; the
    sandbox is small enough that same-name-different-case collisions do not
    occur). NEVER use this as a probe/fetch URL or as an HTTP-cache key:
    kiwix-serve article ids are case-sensitive (audit G-F3), and probing the
    lowercased form 404s real citations, recording them as fabricated.
    """
    return canonicalize_url(url).lower()


def strip_url_trail(url: str) -> str:
    """Strip sentence/markdown punctuation, preserving balanced ``(...)``.

    A final ``)`` is URL data when it closes an opening parenthesis inside the
    destination (Wikipedia titles are the common case).  It is punctuation only
    when there are more closing than opening parentheses.  Applying this one
    helper in extraction and canonicalisation prevents them from disagreeing.
    """
    s = (url or "").strip().rstrip(_URL_TRAIL_NONPAREN)
    while s.endswith(")") and s.count(")") > s.count("("):
        s = s[:-1].rstrip(_URL_TRAIL_NONPAREN)
    return s


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
    chunk = replace_markdown_links(chunk, lambda m: m.label)
    chunk = re.sub(r"`[^`]*`", " ", chunk)
    chunk = re.sub(r"\s+", " ", chunk)
    return chunk.strip()


_REF_HEAD_RE = re.compile(r"^\s*\[(?P<n>\d{1,3})\]\s*\.?\s*(?:[-:.]\s*)?(?P<rest>.*)$")


def _build_numbered_table(answer: str) -> dict[str, str]:
    """Parse ``[N] http://...`` reference list lines (under "## References"
    or anywhere in the doc) into ``{N: url}``.

    Two shapes are recognised:
      * single line   ``[N] <title> http://...`` (or a markdown link)
      * two line      ``[N] <title>`` then a following ``URL: http://...`` /
                      bare-URL continuation line (LDR's ``### Sources`` block:
                      the URL sits on the NEXT line, so the single-line pass
                      returned an empty table and every ``[N]`` inline anchor
                      silently lost its URL — audit E-3 §2.1).

    First definition of a given ``N`` wins. The two-line lookahead stops at the
    next numbered reference head so ``[1]``'s scan can never steal ``[2]``'s URL.
    """
    table: dict[str, str] = {}
    lines = answer.splitlines()
    for i, line in enumerate(lines):
        m = _REF_HEAD_RE.match(line)
        if not m:
            continue
        n = m.group("n")
        if n in table:
            continue
        rest = m.group("rest").strip()
        url = None
        url_m = BARE_URL_RE.search(rest)
        if url_m:
            url = strip_url_trail(url_m.group(0))
        else:
            inner_md = next(iter_markdown_links(rest), None)
            if inner_md:
                url = inner_md.url
        if url is None:
            # two-line continuation: look at the next few lines for a URL,
            # stopping at the next reference head so we bind the right entry.
            for j in range(i + 1, min(i + 4, len(lines))):
                nxt = lines[j]
                if _REF_HEAD_RE.match(nxt):
                    break
                src_m = SOURCE_PREFIX_RE.search(nxt)
                if src_m:
                    url = src_m.group("url")
                    break
                bare_m = BARE_URL_RE.search(nxt)
                if bare_m:
                    url = strip_url_trail(bare_m.group(0))
                    break
        if url:
            table[n] = strip_url_trail(url)
    return table


def _numbered_definition_anchor_offsets(
    answer: str, table: dict[str, str]
) -> set[int]:
    """Return ``[N]`` offsets that define bibliography entries, not claims.

    ``NUMBERED_INLINE_RE`` also matches the ``[N]`` at the start of a reference
    definition.  Counting that marker as another citation doubles citation
    density and source-diversity totals for every numbered-reference report.
    A definition is recognised when it is under a References/Sources heading,
    or when its line (plus STORM/LDR's short continuation window) contains the
    URL already resolved for that number.
    """
    if not table:
        return set()
    heading = re.search(
        r"(?im)^#{1,6}\s+(?:references?|sources?|bibliography)\s*:?\s*$",
        answer,
    )
    heading_offset = heading.start() if heading else None
    lines = answer.splitlines(keepends=True)
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)

    definitions: set[int] = set()
    for i, line in enumerate(lines):
        match = _REF_HEAD_RE.match(line.rstrip("\r\n"))
        if not match or match.group("n") not in table:
            continue
        anchor_offset = offsets[i] + match.start("n") - 1
        if heading_offset is not None and anchor_offset >= heading_offset:
            definitions.add(anchor_offset)
            continue

        expected = canonicalize_url(table[match.group("n")])
        for j in range(i, min(i + 4, len(lines))):
            if j > i and _REF_HEAD_RE.match(lines[j].rstrip("\r\n")):
                break
            candidates = [m.url for m in iter_markdown_links(lines[j])]
            candidates.extend(
                strip_url_trail(m.group(0)) for m in BARE_URL_RE.finditer(lines[j])
            )
            if any(canonicalize_url(url) == expected for url in candidates):
                definitions.add(anchor_offset)
                break
    return definitions


def _build_footnote_table(answer: str) -> dict[str, str]:
    """Parse ``[^N]: http://...`` footnote definition lines."""
    table: dict[str, str] = {}
    for m in FOOTNOTE_REF_LINE_RE.finditer(answer):
        rest = m.group("rest").strip()
        url_m = BARE_URL_RE.search(rest)
        if not url_m:
            inner_md = next(iter_markdown_links(rest), None)
            if inner_md:
                table[m.group("n")] = strip_url_trail(inner_md.url)
            continue
        table[m.group("n")] = strip_url_trail(url_m.group(0))
    return table


def materialize_reference_links(answer: str) -> str:
    """Return a verifier-only view with reference anchors made explicit.

    Numbered-reference frameworks such as STORM put ``[N]`` beside the claim
    and keep the URL in a bibliography (or in a verified native sidecar that
    the scorer has appended to its in-memory view).  Verifiers whose prompts
    operate on one paragraph cannot otherwise see which URL ``[N]`` names.

    This helper converts *inline* numbered and footnote anchors to ordinary
    Markdown links while leaving bibliography definition anchors untouched::

        Claim supported here [3].       -> Claim supported here [3](URL).
        [3] URL                          -> [3] URL

    It never invents a mapping: only entries parsed from ``answer`` are used.
    The returned string is an ephemeral verifier view; callers must not write
    it back over the sealed agent report.
    """
    if not answer:
        return answer or ""

    numbered = _build_numbered_table(answer)
    numbered_defs = _numbered_definition_anchor_offsets(answer, numbered)
    footnotes = _build_footnote_table(answer)

    replacements: list[tuple[int, int, str]] = []
    for match in NUMBERED_INLINE_RE.finditer(answer):
        if match.start() in numbered_defs:
            continue
        # Do not turn an already explicit ``[N](url)`` link into
        # ``[N](url)(url)``.
        if match.end() < len(answer) and answer[match.end()] == "(":
            continue
        url = numbered.get(match.group("n"))
        if url:
            replacements.append(
                (match.start(), match.end(), f"[{match.group('n')}]({url})")
            )

    footnote_definition_offsets = {
        match.start()
        for match in FOOTNOTE_REF_LINE_RE.finditer(answer)
    }
    for match in FOOTNOTE_INLINE_RE.finditer(answer):
        if match.start() in footnote_definition_offsets:
            continue
        url = footnotes.get(match.group("n"))
        if url:
            replacements.append(
                (match.start(), match.end(), f"[^{match.group('n')}]({url})")
            )

    if not replacements:
        return answer
    replacements.sort(key=lambda row: row[0])
    chunks: list[str] = []
    cursor = 0
    for start, end, replacement in replacements:
        if start < cursor:
            continue
        chunks.append(answer[cursor:start])
        chunks.append(replacement)
        cursor = end
    chunks.append(answer[cursor:])
    return "".join(chunks)


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
    A given URL string is reported once per distinct citation site. The
    iteration order is: markdown → ``Source:`` prefix → bullet-line →
    numbered references → footnote references → bare. The bare pass is a
    catchall and runs last; it skips any URL whose canonical form was
    already emitted by an earlier, more-specific pass. This prevents a
    numbered/footnote/source/bullet reference-line URL (e.g.
    ``[1] http://host/x`` on a References line) from being double-counted:
    once as the anchored citation and again as a bare URL.
    """
    if not answer:
        return []
    sandbox_set = set(sandbox_hosts) if sandbox_hosts else None
    out: list[Citation] = []
    seen_offsets: set[int] = set()
    # Canonical URLs already emitted by the anchored passes (steps 1-5).
    # The bare catchall (step 6) skips these so a reference-line URL that
    # backs a numbered/footnote/source/bullet citation is not counted a
    # second time as a standalone bare URL.
    bare_skip: set[str] = set()

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
        # Bare catchall: the reference-line URL backing a more-specific
        # citation (numbered/footnote/source/bullet) is the same citation,
        # not a new one. Skip it so numbered cites aren't double-counted.
        if style == "bare" and canon in bare_skip:
            return
        # Same URL at a different offset under an anchored style? Keep both
        # note: multiple distinct cites of the same URL are legitimate.
        seen_offsets.add(ctx_offset)
        if style != "bare":
            bare_skip.add(canon)
        out.append(Citation(
            canonical_url=canon,
            raw_url=raw,
            claim_context=_claim_context(answer, ctx_offset, window=window),
            char_offset=ctx_offset,
            style=style,
        ))

    # Iteration order matters. `_maybe_emit` rejects re-counts of the same
    # offset, and the bare catchall (step 6, last) skips any canonical URL
    # already emitted by an anchored pass (steps 1-5). Styles run from
    # most-specific to least-specific so a URL carried by an anchoring
    # pattern (e.g. "Source: <url>" or a "[N] <url>" reference line) is
    # reported under that style instead of also surfacing as a bare URL.

    # 1. Markdown links: [label](url) — most explicit, definite citation.
    for m in iter_markdown_links(answer):
        _maybe_emit(m.url, m.start, "markdown")

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
        definition_offsets = _numbered_definition_anchor_offsets(answer, num_table)
        for m in NUMBERED_INLINE_RE.finditer(answer):
            if m.start() in definition_offsets:
                continue
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
