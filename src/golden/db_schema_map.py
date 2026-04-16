"""Predicate → SQL template map for the v3 golden KG.

Each predicate has:
  - `site`: 'shopping' or 'reddit'
  - `verifiable`: True if we can ask the DB whether (subj, obj) is a fact
    (e.g. price=34.99 of product X). False for aggregates (avg, median, n_*).
  - `sql(subject)`: returns a single scalar string — the canonical object
    for that subject+predicate pair. Caller normalizes and compares to the
    candidate object.

The EAV attribute_ids below are from live probe of the shopping container:
  name     varchar attr_id=73 (entity_type_id=4 = catalog_product)
  price    decimal attr_id=77
  url_key  varchar attr_id=121
For rating/review_count we use `review_entity_summary.store_id=1`, which is
the default public storefront.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


# Magento EAV attribute ids (entity_type=catalog_product / type_id=4).
ATTR_NAME = 73
ATTR_PRICE = 77
ATTR_URL_KEY = 121

MAG_BASE_URL = "http://localhost:7770"


# --- helpers: SQL builders that accept a *subject* and return a query. ---


def _mag_name_match(subject: str) -> str:
    # Match subject against the full product name (varchar attr 73).
    # Use LIKE on the prefix — product names are unique-ish up to 64 chars.
    safe = subject.replace("'", "''")
    # Use first 60 chars as the match prefix to dodge truncation + punctuation drift.
    prefix = safe[:60]
    return (
        "SELECT p.entity_id "
        "FROM catalog_product_entity p "
        "JOIN catalog_product_entity_varchar v "
        "  ON v.entity_id=p.entity_id AND v.attribute_id=73 "
        f"WHERE v.value LIKE '{prefix}%' LIMIT 1"
    )


def _mag_price(subject: str) -> str:
    inner = _mag_name_match(subject)
    return (
        "SELECT CAST(d.value AS CHAR) "
        "FROM catalog_product_entity_decimal d "
        f"WHERE d.attribute_id=77 AND d.entity_id=({inner})"
    )


def _mag_rating(subject: str) -> str:
    inner = _mag_name_match(subject)
    # rating_summary is 0-100; convert to 5-star.
    return (
        "SELECT CAST(ROUND(rating_summary/20, 1) AS CHAR) "
        "FROM review_entity_summary "
        f"WHERE store_id=1 AND entity_pk_value=({inner})"
    )


def _mag_review_count(subject: str) -> str:
    inner = _mag_name_match(subject)
    return (
        "SELECT CAST(reviews_count AS CHAR) "
        "FROM review_entity_summary "
        f"WHERE store_id=1 AND entity_pk_value=({inner})"
    )


def _mag_product_url(subject: str) -> str:
    inner = _mag_name_match(subject)
    return (
        "SELECT v.value "
        "FROM catalog_product_entity_varchar v "
        f"WHERE v.attribute_id=121 AND v.entity_id=({inner})"
    )


# --- Postmill ---


def _pg_submission_match(subject: str) -> str:
    """Match a submission by title (subject) — trimmed to first 80 chars."""
    safe = subject.replace("'", "''")[:80]
    return (
        "SELECT id FROM submissions "
        f"WHERE title = '{safe}' "
        "ORDER BY id DESC LIMIT 1"
    )


def _pg_score(subject: str) -> str:
    inner = _pg_submission_match(subject)
    return f"SELECT net_score FROM submissions WHERE id=({inner})"


def _pg_comment_count(subject: str) -> str:
    inner = _pg_submission_match(subject)
    return f"SELECT comment_count FROM submissions WHERE id=({inner})"


def _pg_forum(subject: str) -> str:
    inner = _pg_submission_match(subject)
    return (
        "SELECT f.normalized_name FROM forums f "
        f"JOIN submissions s ON s.forum_id=f.id WHERE s.id=({inner})"
    )


def _pg_author(subject: str) -> str:
    inner = _pg_submission_match(subject)
    return (
        "SELECT u.username FROM users u "
        f"JOIN submissions s ON s.user_id=u.id WHERE s.id=({inner})"
    )


def _pg_post_title(subject: str) -> str:
    """Here subject IS the title — so this is an identity check."""
    inner = _pg_submission_match(subject)
    return f"SELECT title FROM submissions WHERE id=({inner})"


@dataclass(frozen=True)
class PredicateSpec:
    site: str  # 'shopping' | 'reddit'
    verifiable: bool
    sql_builder: Callable[[str], str] | None = None  # None → aggregate / skip


# Every predicate seen across all 8 v3 golden files.
PREDICATES: dict[str, PredicateSpec] = {
    # --- shopping (Magento) ---
    "price":         PredicateSpec("shopping", True,  _mag_price),
    "rating":        PredicateSpec("shopping", True,  _mag_rating),
    "review_count":  PredicateSpec("shopping", True,  _mag_review_count),
    "product_url":   PredicateSpec("shopping", True,  _mag_product_url),
    # category labels are oracle-assigned (e.g. 'over-ear') — not in DB.
    "category":      PredicateSpec("shopping", False, None),
    # Aggregates across product sets — object is a derived number.
    "avg_rating":    PredicateSpec("shopping", False, None),
    "n_products":    PredicateSpec("shopping", False, None),

    # --- reddit (Postmill) ---
    "score":           PredicateSpec("reddit", True, _pg_score),
    "comment_count":   PredicateSpec("reddit", True, _pg_comment_count),
    "forum":           PredicateSpec("reddit", True, _pg_forum),
    "post_title":      PredicateSpec("reddit", True, _pg_post_title),
    "author":          PredicateSpec("reddit", True, _pg_author),
    # Per-comment author lookup needs a different subject shape — treat as
    # non-DB-verifiable in v1 (subject is a comment body snippet, not stable).
    "comment_author":  PredicateSpec("reddit", False, None),
    # Aggregates:
    "avg_score":              PredicateSpec("reddit", False, None),
    "median_comments":        PredicateSpec("reddit", False, None),
    "avg_comments":           PredicateSpec("reddit", False, None),
    "n_posts":                PredicateSpec("reddit", False, None),
    "n_visible_submissions":  PredicateSpec("reddit", False, None),
}


def site_of(predicate: str) -> str | None:
    spec = PREDICATES.get(predicate)
    return spec.site if spec else None
