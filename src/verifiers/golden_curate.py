"""Curate a small, high-value must-cite subset from an over-specified golden.

The deep-golden `must_cite_urls` lists *every* product page that the crawl
discovered (~121 entries for `dr_cross_deep_0001`), each carrying a `weight`
and a free-text `why` such as ``"?: $14.95, 2.15* , 12 reviews"``. Asking a
report to cite ~45% of 121 specific products is structurally unreachable, so
recall against the full set reads as "every agent fails grounding-recall".

This module derives, at scoring time and with no re-crawl, a CURATED top-K
subset of the most important must-cite entries, and scores recall against it.

Curation rule (deterministic, stable):
  1. `weight` descending (the golden's own importance signal).
  2. tie-break: review-count descending. The count is the integer parsed from
     the `why` string immediately preceding the word "review"
     (e.g. ``"12 reviews"`` -> 12). Missing -> 0.
  3. tie-break: entries that carry a star rating rank above those that do not
     (a rated product is a more concrete citation target than an unrated one).
  4. tie-break: original (stable) order in `must_cite_urls`.
Return the top-K entries.

Everything here is pure and lazy with no heavy dependencies.
"""

from __future__ import annotations

import re
from typing import Any, Callable

# integer that immediately precedes the word "review" (singular or plural)
_REVIEW_RE = re.compile(r"(\d+)\s*reviews?\b", re.IGNORECASE)
# a star rating like "2.15*" / "4.7 stars" / "3.90 star"
_STAR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:★|stars?\b)", re.IGNORECASE)


def _review_count(why: str) -> int:
    """Integer review count parsed from a `why` string, or 0 if absent."""
    m = _REVIEW_RE.search(why or "")
    return int(m.group(1)) if m else 0


def _has_star(why: str) -> bool:
    """Whether the `why` string carries a star rating."""
    return bool(_STAR_RE.search(why or ""))


def curate_must_cite(must_cite_urls: list[dict], k: int = 12) -> list[dict]:
    """Select the K most important must-cite entries.

    Sort by `weight` desc, then review-count desc, then star-rating presence,
    then stable original order; return the top-K. Returns a new list; inputs
    are not mutated. If ``k`` exceeds the number of entries, all are returned.
    """
    if k <= 0 or not must_cite_urls:
        return []
    indexed = list(enumerate(must_cite_urls))

    def sort_key(item: tuple[int, dict]) -> tuple:
        idx, e = item
        why = e.get("why", "") or ""
        weight = float(e.get("weight", 1.0) or 0.0)
        # negate the fields we want descending; idx ascending keeps stability
        return (-weight, -_review_count(why), 0 if _has_star(why) else 1, idx)

    indexed.sort(key=sort_key)
    return [e for _idx, e in indexed[:k]]


def curated_recall(
    cited_canon_set: set[str],
    must_cite_urls: list[dict],
    k: int = 12,
    canon: Callable[[str], str] | None = None,
) -> float:
    """Unweighted fraction of the curated top-K that was cited.

    ``cited_canon_set`` is a set of already-canonicalised cited URLs. The
    curated entries are canonicalised with ``canon`` (defaulting to the shared
    ``citation_format.canonicalize_url``) before membership testing. Returns
    |cited n curated| / |curated|, or 0.0 if the curated set is empty.
    """
    if canon is None:
        from .citation_format import canonicalize_url as canon  # lazy import
    curated = curate_must_cite(must_cite_urls, k=k)
    if not curated:
        return 0.0
    curated_canon = {canon(e["url"]) for e in curated if e.get("url")}
    if not curated_canon:
        return 0.0
    hit = cited_canon_set & curated_canon
    return len(hit) / len(curated_canon)
