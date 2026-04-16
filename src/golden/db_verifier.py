"""Triple store wrappers — answer `verify((subj, pred, obj)) -> True | False | None`.

`None` means 'cannot verify' (predicate is an aggregate, or the subject
didn't resolve to a DB row). `True`/`False` means the fact was checkable and
agrees / disagrees with what the DB stores.

Object normalization is deliberately lenient:
  - numbers: parse to float, compare within 5% relative tolerance
  - URLs:    check the url_key slug appears in the candidate string
  - strings: case-insensitive substring / exact match

This is because golden objects are strings ('34.99', '4.3', 'over-ear') and
agent-extracted objects may be '$34.99', '4.3 stars', etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .db_connect import DBRunner
from .db_schema_map import PREDICATES, MAG_BASE_URL


@dataclass
class VerifyResult:
    outcome: Optional[bool]    # True=matches, False=disagrees, None=unverifiable
    db_value: Optional[str]    # what the DB returned, or None
    reason: str = ""


def _to_float(s: str) -> Optional[float]:
    if s is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(s).replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _nums_match(a: str, b: str, *, rel_tol: float = 0.05) -> bool:
    fa, fb = _to_float(a), _to_float(b)
    if fa is None or fb is None:
        return False
    if fa == 0 and fb == 0:
        return True
    denom = max(abs(fa), abs(fb), 1e-9)
    return abs(fa - fb) / denom <= rel_tol


class _BaseStore:
    def __init__(self, runner: Optional[DBRunner] = None) -> None:
        self.runner = runner or DBRunner()

    def verify(self, subject: str, predicate: str, obj: str) -> VerifyResult:
        spec = PREDICATES.get(predicate)
        if spec is None:
            return VerifyResult(None, None, f"unknown predicate: {predicate}")
        if not spec.verifiable or spec.sql_builder is None:
            return VerifyResult(None, None, f"aggregate/non-DB predicate: {predicate}")
        if spec.site != self.site:
            return VerifyResult(None, None, f"predicate {predicate} is for site {spec.site}, not {self.site}")

        sql = spec.sql_builder(subject)
        q = self._query(sql)
        if not q.ok:
            return VerifyResult(None, None, f"db error: {q.stderr[:200]}")
        db_value = q.scalar()
        if db_value is None or db_value == "":
            return VerifyResult(None, None, f"subject {subject[:40]!r} not found")

        return self._compare(predicate, db_value, obj)

    # --- hooks for subclasses ---
    site: str = ""

    def _query(self, sql: str):
        raise NotImplementedError

    def _compare(self, predicate: str, db_value: str, obj: str) -> VerifyResult:
        raise NotImplementedError


class MagentoTripleStore(_BaseStore):
    site = "shopping"

    def _query(self, sql):
        return self.runner.mysql(sql)

    def _compare(self, predicate: str, db_value: str, obj: str) -> VerifyResult:
        if predicate in ("price", "rating", "review_count"):
            ok = _nums_match(db_value, obj)
            return VerifyResult(ok, db_value, f"num_match={ok}")
        if predicate == "product_url":
            # DB gives the url_key slug (e.g. "harphonic-e7-active..."); the
            # candidate object is a full URL. Check slug appears in candidate,
            # OR full url == MAG_BASE_URL/{slug}.html
            slug = db_value.strip()
            candidate = (obj or "").lower()
            if slug.lower() in candidate:
                return VerifyResult(True, db_value, "slug in url")
            canonical = f"{MAG_BASE_URL}/{slug}.html".lower()
            return VerifyResult(candidate == canonical, db_value,
                                f"canonical={canonical}")
        # Fallback: case-insensitive substring either way.
        a, b = db_value.strip().lower(), (obj or "").strip().lower()
        return VerifyResult((a == b) or (a in b) or (b in a), db_value, "string fuzzy")


class PostmillTripleStore(_BaseStore):
    site = "reddit"

    def _query(self, sql):
        return self.runner.postgres(sql)

    def _compare(self, predicate: str, db_value: str, obj: str) -> VerifyResult:
        if predicate in ("score", "comment_count"):
            ok = _nums_match(db_value, obj, rel_tol=0.02)
            return VerifyResult(ok, db_value, f"num_match={ok}")
        if predicate in ("forum", "author", "post_title"):
            a = db_value.strip().lower()
            b = (obj or "").strip().lower()
            # Allow 'f/news' vs 'news' comparisons
            a_core = a.removeprefix("f/")
            b_core = b.removeprefix("f/").removeprefix("/f/")
            return VerifyResult(a == b or a_core == b_core or a in b or b in a,
                                db_value, "string fuzzy")
        return VerifyResult(None, db_value, f"no comparator for {predicate}")


def get_store(site: str, *, runner: Optional[DBRunner] = None) -> _BaseStore:
    if site == "shopping":
        return MagentoTripleStore(runner)
    if site == "reddit":
        return PostmillTripleStore(runner)
    raise ValueError(f"unknown site: {site}")
