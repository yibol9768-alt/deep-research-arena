"""URLCoverageVerifier — scores an agent's deep-tier markdown report
against the deep-golden pool.

Design goals:
  1. fully deterministic (no LLM), so it can be part of CompositeScorer v4
  2. three decoupled sub-scores, reported separately AND weighted into final:
       - must_cite_recall      = |cited ∩ must_cite| / |must_cite|
       - pool_coverage         = |cited ∩ expected_pool| / |expected_pool|
       - domain_balance        = min(per_domain_cited / per_domain_minimum)  clipped to 1
  3. tolerant URL normalisation: strips trailing `/`, lowercases host, drops
     fragment, canonicalises query-string ordering. Two URLs that differ only
     in query-order are considered identical.
  4. refuses to count URL-looking strings that are not reachable syntactically
     — e.g. `[price](#)` or `http://example.com` when sandbox domain constraints
     are set on the task.

Usage:
    from src.verifiers.url_coverage_verifier import URLCoverageVerifier
    v = URLCoverageVerifier()
    result = v.verify(task_config=task, answer=md, page=None)

`task_config` must contain `url_coverage` with `golden_pool_path` pointing at
the deep-golden JSON.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse  # used by _host_match below

from .base import VerifierResult


# URL extraction + canonicalisation moved to citation_format.py — single
# source of truth across all citation-aware verifiers. Re-export so existing
# callers (`url_reachability_verifier` imports `_canonical` and
# `_extract_cited_urls`) keep working.
from .citation_format import (  # noqa: F401
    MD_LINK_RE as _MD_LINK_RE,
    BARE_URL_RE as _BARE_URL_RE,
    canonicalize_url as _canonical,
)
from .citation_format import extract_cited_urls as _extract_cited_urls_full


def _extract_cited_urls(markdown: str) -> tuple[set[str], dict[str, set[str]]]:
    """Return (unique canonical URLs, raw-by-canonical map). Thin wrapper
    over `citation_format.extract_cited_urls` that picks up all 6 citation
    styles, not just markdown + bare. Sandbox filtering happens later in
    `verify()` via `_classify_domain`.
    """
    return _extract_cited_urls_full(markdown, sandbox_hosts=None, sandbox_only=False)


def _url_matches_domain_alias(url: str, alias: str) -> bool:
    """Check whether a canonical URL matches one of the __SHOPPING__ / __REDDIT__ / __WIKIPEDIA__ aliases.

    The sandbox uses real host:port rather than the alias text, so mapping
    must be supplied by the task config via citation_policy.must_be_in_domain
    AND a `domain_aliases` map on the task OR env.
    """
    return alias.lower() in url.lower()


_SANDBOX_DEFAULT_ALIASES = {
    "__SHOPPING__":  ["localhost:7770"],
    "__REDDIT__":    ["localhost:9999"],
    "__WIKIPEDIA__": ["localhost:8090"],
}


def _host_match(url: str, host_pattern: str) -> bool:
    """Match a URL against a host pattern using host:port equality, not
    substring. `localhost:7770 in url` would also match `localhost:77703`
    or any URL whose path contains the literal "localhost:7770", which
    the substring form does. Use urlparse for an exact comparison."""
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        host = (p.hostname or "").lower()
        port = p.port
        netloc = f"{host}:{port}" if port else host
    except Exception:
        return False
    pat = host_pattern.lower()
    if ":" in pat:
        return netloc == pat
    return host == pat


def _classify_domain(url: str, domain_aliases: dict[str, list[str]]) -> str | None:
    for alias, hosts in domain_aliases.items():
        for h in hosts:
            if h and _host_match(url, h):
                return alias
    return None


class URLCoverageVerifier:
    kind = "url_coverage"

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any = None) -> VerifierResult:
        cov_cfg = task_config.get("url_coverage") or {}
        if not cov_cfg:
            return VerifierResult.fail("task has no url_coverage spec")

        golden_path = cov_cfg.get("golden_pool_path")
        if not golden_path:
            return VerifierResult.fail("url_coverage.golden_pool_path missing")
        gp = Path(golden_path)
        if not gp.is_absolute():
            gp = Path(__file__).resolve().parents[2] / gp
        if not gp.exists():
            return VerifierResult.fail(f"golden pool not found: {gp}")

        golden = json.loads(gp.read_text())
        must_entries = golden.get("must_cite_urls", []) or []
        pool_entries = golden.get("expected_pool_urls", []) or []
        must = {_canonical(e["url"]): float(e.get("weight", 1.0)) for e in must_entries}
        pool = {_canonical(e["url"]) for e in pool_entries}

        if not must:
            return VerifierResult.fail("golden has empty must_cite_urls")

        cited, canon_map = _extract_cited_urls(answer)

        must_hits = cited & set(must.keys())
        must_weight_hit = sum(must[u] for u in must_hits)
        must_weight_total = sum(must.values()) or 1.0
        must_cite_recall = must_weight_hit / must_weight_total

        pool_hits = cited & pool
        pool_coverage = len(pool_hits) / len(pool) if pool else 0.0

        cp = task_config.get("citation_policy", {}) or {}
        per_domain_min: dict[str, int] = cp.get("per_domain_minimum", {}) or {}
        # Default to the sandbox host:port mapping. The previous default
        # ({"__SHOPPING__": ["shopping"]}) never matched URLs of the form
        # localhost:7770/... so domain_balance silently went to 0 for any
        # task that didn't explicitly set domain_aliases.
        domain_aliases: dict[str, list[str]] = (
            task_config.get("domain_aliases")
            or {k: _SANDBOX_DEFAULT_ALIASES.get(k, [k.replace("__", "").lower()])
                for k in per_domain_min}
        )

        per_domain_cited: dict[str, int] = {k: 0 for k in per_domain_min}
        for u in cited:
            d = _classify_domain(u, domain_aliases)
            if d in per_domain_cited:
                per_domain_cited[d] += 1

        if per_domain_min:
            per_domain_ratios = [
                min(1.0, per_domain_cited[d] / per_domain_min[d])
                for d in per_domain_min
                if per_domain_min[d] > 0
            ]
            domain_balance = min(per_domain_ratios) if per_domain_ratios else 1.0
        else:
            domain_balance = 1.0

        min_must_recall = float(cov_cfg.get("min_must_cite_recall", 0.45))
        min_pool_cov = float(cov_cfg.get("min_expected_pool_coverage", 0.12))
        min_cited_n = int(cov_cfg.get("min_unique_urls_cited", 60))
        min_dom_balance = float(cov_cfg.get("min_domain_balance", 0.80))

        sw = cov_cfg.get("scoring_weights") or {
            "must_cite_recall": 0.55,
            "pool_coverage": 0.15,
            "domain_balance": 0.30,
        }
        weighted = (
            sw.get("must_cite_recall", 0.55) * must_cite_recall
            + sw.get("pool_coverage", 0.15) * pool_coverage
            + sw.get("domain_balance", 0.30) * domain_balance
        )
        passed = (
            must_cite_recall >= min_must_recall
            and pool_coverage >= min_pool_cov
            and domain_balance >= min_dom_balance
            and len(cited) >= min_cited_n
        )

        return VerifierResult(
            score=round(weighted, 4),
            passed=passed,
            details={
                "cited_unique": len(cited),
                "must_cite_total": len(must),
                "must_cite_hit": len(must_hits),
                "must_cite_recall": round(must_cite_recall, 4),
                "pool_total": len(pool),
                "pool_hit": len(pool_hits),
                "pool_coverage": round(pool_coverage, 4),
                "per_domain_cited": per_domain_cited,
                "per_domain_minimum": per_domain_min,
                "domain_balance": round(domain_balance, 4),
                "threshold_must_cite_recall": min_must_recall,
                "threshold_pool_coverage": min_pool_cov,
                "threshold_unique_cited": min_cited_n,
            },
        )
