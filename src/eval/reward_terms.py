"""Pure reward terms for the Phase 2 grounded RL path."""

from __future__ import annotations

from statistics import mean
from typing import Any

from src.verifiers.citation_format import canonicalize_url, extract_citations, extract_cited_urls


CITATION_CAP = 20
JACCARD_FLOOR = 0.10
PENALTY_CAP = 0.30
SEARCH_BREADTH_TARGET = 8

_DEFAULT_SANDBOX_HOSTS = (
    "localhost:7770",
    "localhost:8090",
    "localhost:9999",
    "localhost:8081",
    "127.0.0.1:7770",
    "127.0.0.1:8090",
    "127.0.0.1:9999",
    "127.0.0.1:8081",
)


def _sandbox_hosts(task_config: dict[str, Any]) -> tuple[str, ...]:
    hosts = task_config.get("sandbox_hosts")
    if hosts:
        return tuple(str(h) for h in hosts)
    return _DEFAULT_SANDBOX_HOSTS


def _ordered_cited_urls(rollout, task_config: dict[str, Any]) -> list[str]:
    citations = extract_citations(
        rollout.report_md or "",
        _sandbox_hosts(task_config),
        sandbox_only=True,
    )
    seen: set[str] = set()
    out: list[str] = []
    for c in citations:
        if c.canonical_url in seen:
            continue
        seen.add(c.canonical_url)
        out.append(c.canonical_url)

    fetched = {
        canonicalize_url(u)
        for u in (getattr(rollout, "fetched_urls", None) or [])
        if u
    }
    raw_store = getattr(rollout, "retrieved_snippets", None) or {}
    fetched.update(
        canonicalize_url(str(url))
        for url, text in raw_store.items()
        if str(url).strip() and str(text or "")
    )
    if fetched:
        out = [u for u in out if u in fetched] + [u for u in out if u not in fetched]
    return out[:CITATION_CAP]


def _coverage_growth(rollout, task_config: dict[str, Any] | None = None) -> float:
    """Proxy for whether cited URLs were actually fetched during the run."""
    cfg = task_config or {}
    cited = _ordered_cited_urls(rollout, cfg)
    if not cited:
        return 0.0
    fetched = {canonicalize_url(u) for u in (rollout.fetched_urls or []) if u}
    return len([u for u in cited if u in fetched]) / len(cited)


def compute_process(rollout, task_config: dict[str, Any]) -> dict[str, Any]:
    calls = list(rollout.tool_calls or [])
    if not calls:
        return {
            "R_process": 0.0,
            "valid_search": 0.0,
            "search_breadth": 0.0,
            "query_diversity": 0.0,
            "search_quality": 0.0,
            "tool_valid": 0.0,
            "coverage_growth": 0.0,
            "n_calls": 0,
            "n_valid_nonempty_searches": 0,
            "n_distinct_queries": 0,
            "signal_health": "degraded",
        }

    def _n_results(call: dict[str, Any]) -> int:
        try:
            return int(call.get("n_results") or 0)
        except (TypeError, ValueError):
            return 0

    valid_nonempty_searches = [
        c for c in calls
        if "search" in str(c.get("endpoint") or "")
        and str(c.get("query") or "").strip()
        and bool(c.get("ok", True))
        and _n_results(c) > 0
    ]
    n_valid = len(valid_nonempty_searches)
    distinct_queries = {
        " ".join(str(c.get("query")).lower().split())
        for c in valid_nonempty_searches
    }
    n_distinct = len(distinct_queries)

    search_cfg = task_config.get("search") or {}
    raw_target = (
        search_cfg.get("target_distinct_queries", SEARCH_BREADTH_TARGET)
        if isinstance(search_cfg, dict)
        else SEARCH_BREADTH_TARGET
    )
    try:
        target = float(raw_target)
    except (TypeError, ValueError):
        target = float(SEARCH_BREADTH_TARGET)
    if target <= 0:
        target = float(SEARCH_BREADTH_TARGET)

    search_breadth = min(1.0, n_distinct / target)
    query_diversity = (n_distinct / n_valid) if n_valid else 0.0
    search_quality = mean([search_breadth, query_diversity]) if n_valid else 0.0
    valid_tool_calls = [
        c for c in calls
        if bool(c.get("ok", True)) and _n_results(c) > 0
    ]
    tool_valid = len(valid_tool_calls) / len(calls) if calls else 0.0
    coverage_growth = _coverage_growth(rollout, task_config)
    r_process = mean([search_quality, tool_valid, coverage_growth])
    return {
        "R_process": round(float(r_process), 6),
        "valid_search": round(float(search_breadth), 6),
        "search_breadth": round(float(search_breadth), 6),
        "query_diversity": round(float(query_diversity), 6),
        "search_quality": round(float(search_quality), 6),
        "tool_valid": round(float(tool_valid), 6),
        "coverage_growth": round(float(coverage_growth), 6),
        "n_calls": len(calls),
        "n_valid_nonempty_searches": n_valid,
        "n_distinct_queries": n_distinct,
        "signal_health": "ok",
    }


def compute_penalties(
    rollout,
    task_config: dict[str, Any],
    *,
    s_ground: float,
    n_cited: int,
    n_resolved: int,
) -> dict[str, Any]:
    cited, _ = extract_cited_urls(
        rollout.report_md or "",
        _sandbox_hosts(task_config),
        sandbox_only=True,
    )
    fetched = {canonicalize_url(u) for u in (rollout.fetched_urls or []) if u}

    if n_cited > 0:
        p_fabricate = min(PENALTY_CAP, max(0, n_cited - n_resolved) / n_cited)
    else:
        p_fabricate = 0.0

    fetched_not_cited = fetched - cited
    p_unused = 0.10 * (len(fetched_not_cited) / len(fetched)) if fetched else 0.0

    p_verbose = 0.0
    words = 0
    max_words = int(((task_config.get("markdown_spec") or {}).get("max_words") or 0) or 0)
    if max_words > 0:
        try:
            from src.verifiers.markdown_report_verifier import _word_count

            words = _word_count(rollout.report_md or "")
        except Exception:
            words = len((rollout.report_md or "").split())
        if words > max_words:
            over = (words - max_words) / max(max_words, 1)
            p_verbose = 0.10 * min(1.0, over / 0.20)

    total = min(PENALTY_CAP, p_fabricate + p_unused + p_verbose)
    nullify = bool(n_cited > 0 and n_resolved == 0)
    return {
        "P_hack": round(float(total), 6),
        "p_fabricate": round(float(p_fabricate), 6),
        "p_unused": round(float(p_unused), 6),
        "p_verbose": round(float(p_verbose), 6),
        "fetched_not_cited": len(fetched_not_cited),
        "fetched_total": len(fetched),
        "n_cited": int(n_cited),
        "n_resolved": int(n_resolved),
        "s_ground": round(float(s_ground), 6),
        "words": words,
        "max_words": max_words,
        "nullify": nullify,
    }


__all__ = [
    "CITATION_CAP",
    "JACCARD_FLOOR",
    "PENALTY_CAP",
    "SEARCH_BREADTH_TARGET",
    "_ordered_cited_urls",
    "_coverage_growth",
    "compute_process",
    "compute_penalties",
]
