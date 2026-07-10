"""Mechanically generate the *oracle report* for a closed-world answer key.

The oracle report is the report a perfect agent would write: it states every
vital fact the key demands, with the source page cited on the SAME Markdown line
(the keys carry ``inline_nugget_citation_required=true``), and it grounds every
concept / forum nugget in a verbatim quote of that page's cached text. Scored by
``decidable_scorer`` it must saturate every axis the observable world allows:

    reach         = 1.0   (every cited URL is in the frozen corpus)
    fact          > 0     (one DB-true, inline-cited price claim)
    completeness  = 1.0   when the page cache makes concept + forum coverable;
                          otherwise the ceiling the cache DOES allow, and the
                          uncovered share is reported so the gate can skip it.

This is the shared substrate of gate G1 (oracle tops out) and G3 (a corrupted
oracle must lose the corresponding axis). It is a pure library: it takes an
``AnswerKey`` object and an optional page cache; it hard-codes no path, reads no
file and touches no network. The gate supplies the cache (the box fixture when
present, a synthetic one otherwise) and the ``UrlRegistry``.

Cache format is the scorer's own: ``{url: {"status": 200, "text": "..."}}``.
The box fixture ships as ``{url: page_text}``; convert it with
``page_cache_from_fixture`` before passing it here.

Nothing in this module changes scoring semantics; it only produces text and
records, in ``OracleReport.plan``, exactly which nuggets it made coverable so a
gate can assert the scorer credits precisely those and no more.
"""

from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from src.eval import decidable_scorer as ds

# Re-used verbatim so the oracle's own coverage predicate matches the scorer's.
from src.eval.decidable_scorer import (
    K_STAR_DEFAULT,
    build_vital_pool,
    norm,
    strip_html,
    _page_identity,
)

_SENTIMENT_OBJECT_RE = re.compile(r"([\d.]+)%/(\d+)rev")


@dataclass
class OracleReport:
    """The generated report plus a machine-readable coverage plan.

    ``plan`` is what a gate asserts against. It is computed BY CONSTRUCTION (the
    generator knows which lines it emitted), not by re-running the scorer, so an
    assertion of ``scorer_covered == plan['expected_covered']`` is a real check
    of the scorer rather than a tautology.
    """

    markdown: str
    cited_urls: list[str]
    plan: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

# Repo-root-relative location of the box concept-page cache fixture.  A gate
# resolves it against the repository root (never a hard-coded worktree path) and
# skips the concept assertions cleanly when the file is absent.
CONCEPT_CACHE_REL = "data/golden/concept_page_cache.json.gz"


def load_concept_cache(repo_root=None) -> dict | None:
    """Load the box concept-page cache fixture in scorer shape, or ``None`` when
    the fixture is not present.

    The fixture ships as ``{url: page_text}`` (gzipped JSON, keyed on the answer
    key ``source_url``); this returns the scorer's ``{url: {"status": 200,
    "text": ...}}`` shape ready to hand to the scorer. ``repo_root`` defaults to
    the repository root inferred from this file's location, so a test never
    hard-codes a worktree path. Returns ``None`` (not ``{}``) when absent so a
    caller can distinguish "no fixture" from "empty fixture"."""
    root = Path(repo_root) if repo_root is not None \
        else Path(__file__).resolve().parents[2]
    path = root / CONCEPT_CACHE_REL
    if not path.exists():
        return None
    with gzip.open(path, "rt") as fh:
        fixture = json.load(fh)
    return page_cache_from_fixture(fixture)


def _concept_subject_creditable(subject: str) -> bool:
    """Whether the scorer's completeness gate CAN credit a concept with this
    subject, independent of any page text.

    Ruling #5 (docs/SPEC_DECISIONS.md lane addendum): the scorer's
    ``_subject_discussed`` no longer deadlocks a short-token subject (``Tea``).
    When every identity token is short it falls back to WORD-BOUNDARY exact
    matching, which the oracle line ``[Tea](url)`` satisfies (the subject sits in
    the link label, at a word boundary, in the visible prose). So every concept
    with at least one identity token (``len > 2``, first 6) is now creditable;
    only a subject with NO such token (``AI``) remains uncreditable, matching the
    scorer's ``_subject_tokens`` empty-token skip. This mirrors the scorer so the
    plan equals the ceiling the scorer actually allows."""
    toks = [t for t in re.findall(r"[a-z0-9]+", (subject or "").lower())
            if len(t) > 2][:6]
    return bool(toks)


def page_cache_from_fixture(fixture: dict) -> dict:
    """Lift the box fixture ``{url: page_text}`` into the scorer's cache shape
    ``{url: {"status": 200, "text": page_text}}``.

    Entries already in scorer shape (a dict carrying ``text``/``status``) pass
    through unchanged, so a caller may hand either form."""
    out: dict = {}
    for url, val in (fixture or {}).items():
        if isinstance(val, dict) and ("text" in val or "status" in val):
            out[url] = val
        else:
            out[url] = {"status": 200, "text": val or ""}
    return out


def _cache_entry_for(source_url: str, cache: dict, registry=None):
    """Return the (key, entry) in ``cache`` whose page identity matches
    ``source_url`` and which carries usable status-200 text, else (None, None).
    Identity matching mirrors ``_concept_quote_supported`` so a fixture keyed on
    the ``/wiki/X`` alias still resolves the ``/content/.../A/X`` nugget URL."""
    target = _page_identity(source_url, registry)
    for key, val in (cache or {}).items():
        if _page_identity(key, registry) != target:
            continue
        try:
            status = int((val or {}).get("status", 0) or 0)
        except (TypeError, ValueError):
            status = 0
        if status == 200 and (val or {}).get("text"):
            return key, val
    return None, None


# The scorer's verbatim judge reads the 400 chars of prose before a citation.
# A quote shorter than that leaves the window dominated by the NEIGHBOUR line's
# off-page tokens, so IDF containment fails no matter where the line is placed:
# a page whose whole extracted body is shorter than the window (a title-only
# stub such as the fixture's "Input lag Input lag") cannot ground a quote for
# ANY report. By-construction precondition, not a re-run of the scorer.
MIN_GROUNDABLE_QUOTE_CHARS = 400


def _page_quote(text: str, *, n_words: int = 90, skip_head: int = 12) -> str:
    """A verbatim, content-bearing run of words from a cached page, usable as a
    grounding quote.

    The scorer's verbatim judge (``_pof_occurrence_ok``) reads the 400 chars of
    prose BEFORE the citation and requires (a) IDF-weighted containment of that
    context in the page above ``POF_THRESHOLD`` and (b) a contiguous 3-token run
    present verbatim on the page. Two things dilute (a): tokens from a NEIGHBOUR
    line bleeding into the 400-char window, and any glue words that are not on
    the page. So we (i) emit no glue between the quote and the citation, and
    (ii) make the quote long enough (~90 words ~= 600 chars) that the 400-char
    window is pure page text. Words are drawn from the same ``strip_html`` stream
    the scorer tokenises, so trigrams line up after normalisation. A short real
    page yields its whole body, which is what the agent would have quoted."""
    words = strip_html(text or "").split()
    if not words:
        return ""
    if len(words) <= n_words:
        return " ".join(words)
    start = skip_head if len(words) > skip_head + n_words else 0
    return " ".join(words[start:start + n_words])


def _forum_quote_ok(text: str, core: set[str], query: set[str]) -> bool:
    """Does a cached forum page carry the task terms ``_forum_coverage_supported``
    requires (>=1 core AND (>=1 query OR no query), or >=2 query)?"""
    doc = set(re.findall(r"[a-z0-9]+", norm(strip_html(text or ""))))

    def hit(term: str) -> bool:
        if term in doc:
            return True
        if len(term) < 5:
            return False
        stem = term[:5]
        return any(len(t) >= 5 and t[:5] == stem for t in doc)

    core_hits = sum(hit(t) for t in core)
    query_hits = sum(hit(t) for t in query)
    return (core_hits >= 1 and (query_hits >= 1 or not query)) or query_hits >= 2


def _find_forum_thread(answer_key, cache: dict, registry):
    """Return (url, entry) for a cached forum thread that would satisfy the
    completeness forum slot: a status-200 forum content page in one of the key's
    allowed forums whose text carries the task terms. None when the cache has no
    such page (then the forum slot is not coverable by the oracle)."""
    meta = getattr(answer_key, "metadata", {}) or {}
    allowed = {str(f).strip().casefold() for f in meta.get("forums", [])
               if str(f).strip()}
    if not allowed or registry is None:
        return None, None
    core = {str(t).strip().lower() for t in meta.get("forum_core_keywords", [])
            if str(t).strip()}
    query = {str(t).strip().lower() for t in meta.get("forum_query_keywords", [])
             if str(t).strip()}
    for key, val in (cache or {}).items():
        try:
            info = registry.classify(key)
        except Exception:
            continue
        if (not isinstance(info, dict) or info.get("host_role") != "forums"
                or info.get("kind") != "content" or info.get("in_corpus") is not True):
            continue
        canonical = info.get("canonical") or key
        parts = [unquote(p) for p in urlparse(canonical).path.split("/") if p]
        if len(parts) < 3 or parts[0].casefold() != "f" \
                or parts[1].casefold() not in allowed:
            continue
        try:
            status = int((val or {}).get("status", 0) or 0)
        except (TypeError, ValueError):
            status = 0
        if status != 200 or not (val or {}).get("text"):
            continue
        if _forum_quote_ok(val["text"], core, query):
            return canonical, val
    return None, None


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def build_oracle_report(answer_key, cache: dict | None = None, registry=None, *,
                        k_star: int = K_STAR_DEFAULT,
                        pool_size: int | None = None) -> OracleReport:
    """Generate the oracle report and its coverage plan for one answer key.

    ``cache`` (scorer shape) drives concept and forum grounding: a concept
    nugget is only made coverable when its page is cached (a verbatim quote is
    required), and the forum slot only when a qualifying thread is cached.
    Without a cache the report still states every structured nugget and one
    price claim, so reach and fact top out and completeness reaches the
    structured-only ceiling."""
    cache = cache or {}
    pool = build_vital_pool(answer_key, k_star=k_star, pool_size=pool_size)
    meta = getattr(answer_key, "metadata", {}) or {}
    ents = {e.url: e for e in answer_key.relevant_set}

    lines: list[str] = ["# Oracle research report", ""]
    struct_urls: list[str] = []
    struct_by_predicate: dict[str, int] = {}
    concept_covered: list[str] = []
    concept_uncovered: list[str] = []
    concept_uncreditable: list[str] = []
    concept_stub_page: list[str] = []

    for n in pool:
        if n.predicate == "buyer_sentiment":
            m = _SENTIMENT_OBJECT_RE.match(str(n.object))
            if not m:
                continue
            pct, nrev = m.group(1), m.group(2)
            lines.append(
                f"[{n.subject}]({n.source_url}) is rated {pct}% positive across "
                f"{nrev} reviews on the store product page.")
            struct_urls.append(n.source_url)
            struct_by_predicate[n.predicate] = struct_by_predicate.get(n.predicate, 0) + 1
        elif n.predicate == "concept_coverage":
            _key, entry = _cache_entry_for(n.source_url, cache, registry)
            quote = _page_quote(entry["text"]) if entry else ""
            if quote:
                # Verbatim page text immediately BEFORE the citation grounds the
                # concept (no glue words, which would be off-page tokens diluting
                # the containment score); the concept name in the link label
                # makes the subject discussed.
                lines.append(f"{quote} [{n.subject}]({n.source_url}).")
                # A cached, quoted concept only earns completeness when (i) the
                # scorer's subject gate can credit its subject (a strong token:
                # short-subject concepts such as "Tea" cannot be credited for
                # any report) and (ii) the quote is long enough to fill the
                # scorer's 400-char containment window (a title-only stub page
                # cannot ground). Both lines are still emitted -- a perfect
                # agent would write them -- but excluded from the ceiling.
                if len(quote) < MIN_GROUNDABLE_QUOTE_CHARS:
                    concept_stub_page.append(n.source_url)
                elif _concept_subject_creditable(n.subject):
                    concept_covered.append(n.source_url)
                else:
                    concept_uncreditable.append(n.source_url)
            else:
                concept_uncovered.append(n.source_url)
        else:
            # generic structured nugget (price / rating / thread_score): state the
            # typed object next to an inline citation.
            lines.append(f"[{n.subject}]({n.source_url}): {n.object}.")
            struct_urls.append(n.source_url)
            struct_by_predicate[n.predicate] = struct_by_predicate.get(n.predicate, 0) + 1

    # --- forum slot ---------------------------------------------------------
    forum_slot = bool(meta.get("forums")) and not any(
        getattr(n, "predicate", "") == "forum_coverage" for n in pool)
    forum_url = None
    if forum_slot:
        furl, fentry = _find_forum_thread(answer_key, cache, registry)
        if furl and fentry:
            quote = _page_quote(fentry["text"])
            # Same stub-page guard as concepts: the quote must fill the
            # scorer's 400-char containment window to ground.
            if len(quote) >= MIN_GROUNDABLE_QUOTE_CHARS:
                lines.append(f"{quote} [community discussion thread]({furl}).")
                forum_url = furl

    # --- one inline-cited price claim to activate the fact axis -------------
    # The fact axis binds claims per SENTENCE, so the citation and the price
    # value must share one sentence. A product NAME can carry an internal
    # abbreviation period ("Japanese Ver.", "That's It.") which the sentence
    # splitter treats as a boundary, detaching the citation from the value and
    # scoring the correct price as supported-but-uncited (recall 0). So the link
    # label here is a period-free constant: the claim binds to the entity via the
    # sole markdown link (fact scorer's forced_id), not via the name.
    fact_url = None
    for n in pool:
        e = ents.get(n.source_url)
        price = (e.facts or {}).get("price") if e is not None else None
        if e is not None and price is not None:
            try:
                lines.append(
                    f"The [product listing]({e.url}) gives a current "
                    f"price of ${float(price):.2f}.")
                fact_url = e.url
            except (TypeError, ValueError):
                continue
            break

    markdown = "\n\n".join(lines)
    cited_urls = ds._cited_urls(markdown)

    total_pool = len(pool) + int(forum_slot)
    denom = min(k_star, total_pool) or k_star
    expected_covered = len(struct_urls) + len(concept_covered) + int(bool(forum_url))
    plan = {
        "task_id": getattr(answer_key, "task_id", None),
        "k_star": k_star,
        "pool": len(pool),
        "total_pool": total_pool,
        "forum_slot": forum_slot,
        "denom": denom,
        "n_struct": len(struct_urls),
        "struct_urls": struct_urls,
        "struct_by_predicate": struct_by_predicate,
        "n_concept_in_pool": sum(1 for n in pool
                                 if n.predicate == "concept_coverage"),
        "concept_covered_urls": concept_covered,
        # cached + quoted but scorer cannot credit (short subject, no strong
        # token): emitted in the report, excluded from the ceiling.
        "concept_uncreditable_urls": concept_uncreditable,
        # cached but the page body is a title-only stub shorter than the
        # scorer's 400-char containment window: ungroundable for any report.
        "concept_stub_page_urls": concept_stub_page,
        # no cached page => not coverable by any report without the box fixture.
        "concept_uncovered_urls": concept_uncovered,
        "forum_url": forum_url,
        "fact_url": fact_url,
        "expected_covered": expected_covered,
        "expected_completeness": min(expected_covered, denom) / denom if denom else 0.0,
        # every cited URL is an in-corpus page by construction
        "expected_reach": 1.0,
        # True only when the achievable set fills the whole denominator (every
        # concept creditable AND cached, AND a forum thread cached): only then is
        # a literal completeness of 1.0 reachable. The forum virtual slot and any
        # short-subject concept both keep this False under the current fixture
        # (see docs/SPEC_ISSUES.md). The oracle still tops out at
        # expected_completeness, the ceiling the closed world actually allows.
        "full_ceiling": expected_covered >= denom,
    }
    return OracleReport(markdown=markdown, cited_urls=cited_urls, plan=plan)
