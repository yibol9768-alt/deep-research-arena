"""URLReachabilityVerifier — verifies every URL cited in the agent's answer
is actually reachable on the sandbox (HTTP 200 from shopping/reddit/kiwix).

This is the single strongest signal against URL fabrication: if 0% of
cited URLs return 200, the agent invented every citation regardless of
how fluent the prose is. No LLM judge needed, no golden pool needed.

Design:
  - Extract canonical URLs from markdown
  - Filter to sandbox domains (to avoid externally-routable URLs dragging
    down the score — we only care about in-sandbox citation honesty)
  - HEAD each URL with tight timeout; fall back to GET on 405
  - Report 200 rate as `reachability_rate`, score = rate
  - Optional concurrency via thread pool for speed

Pass/fail gate: `min_reachability_rate` (default 0.30).
"""

from __future__ import annotations

import concurrent.futures
import os
import re
from typing import Any
from urllib.parse import urlparse

from .base import VerifierResult
from .url_coverage_verifier import _canonical, _extract_cited_urls


def _is_sandbox_url(url: str, sandbox_hosts: set[str]) -> bool:
    """Match a URL's host:port to one of `sandbox_hosts`. Use exact equality
    on hostname / hostname:port, NOT substring — `localhost:7770` would
    otherwise also match `localhost:77703` or any path containing the
    literal `localhost:7770`."""
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


def _probe(url: str, timeout: float = 10.0, retries: int = 3) -> int:
    """Return the HTTP status code (0 on persistent network failure).

    Magento under parallel probe pressure frequently resets; we retry with
    exponential back-off, prefer GET over HEAD (Magento responds 200 to GET
    but can close under HEAD connection pool pressure), and keep connections
    short-lived via `stream=True` + close.
    """
    try:
        import requests
    except ImportError:
        return 0
    backoff = 0.5
    last = 0
    for attempt in range(retries):
        try:
            r = requests.get(
                url, timeout=timeout, allow_redirects=True, stream=True,
                headers={"User-Agent": "deep-reach-verifier/1.0"},
            )
            r.close()
            return r.status_code
        except Exception:
            last = 0
        import time
        time.sleep(backoff)
        backoff *= 2.0
    return last


class URLReachabilityVerifier:
    kind = "url_reachability"

    def __init__(self, max_workers: int = 4, max_urls: int = 200):
        self.max_workers = max_workers
        self.max_urls = max_urls

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any = None) -> VerifierResult:
        rcfg = task_config.get("url_reachability") or {}
        min_rate = float(rcfg.get("min_reachability_rate", 0.30))
        probe_timeout = float(rcfg.get("probe_timeout_seconds", 6.0))
        sandbox_hosts: list[str] = task_config.get("sandbox_hosts") or (
            rcfg.get("sandbox_hosts") or ["localhost:7770", "localhost:9999", "localhost:8090"]
        )
        sandbox_host_set = {h.lower() for h in sandbox_hosts}

        cited, _ = _extract_cited_urls(answer)
        # Use the strict host:port matcher; substring `h in u` would
        # falsely match URLs that merely contain the literal sandbox host.
        sandbox_cited = {u for u in cited if _is_sandbox_url(u, sandbox_host_set)}
        others = cited - sandbox_cited

        if not sandbox_cited:
            return VerifierResult.fail(
                "no sandbox-domain URLs cited",
                cited_total=len(cited),
                cited_off_sandbox=len(others),
                reachability_rate=0.0,
            )

        # Cap to avoid runaway
        sample = sorted(sandbox_cited)[: self.max_urls]

        codes: dict[str, int] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = {ex.submit(_probe, u, probe_timeout): u for u in sample}
            for fut in concurrent.futures.as_completed(futs):
                codes[futs[fut]] = fut.result()

        hits_200 = sum(1 for c in codes.values() if c == 200)
        hits_4xx = sum(1 for c in codes.values() if c in (400, 401, 403, 404, 410))
        hits_5xx = sum(1 for c in codes.values() if 500 <= c < 600)
        hits_net = sum(1 for c in codes.values() if c == 0)
        total = len(codes) or 1
        rate = hits_200 / total

        passed = rate >= min_rate
        return VerifierResult(
            score=round(rate, 4),
            passed=passed,
            details={
                "cited_total": len(cited),
                "cited_sandbox": len(sandbox_cited),
                "cited_off_sandbox": len(others),
                "probed": total,
                "http_200": hits_200,
                "http_4xx": hits_4xx,
                "http_5xx": hits_5xx,
                "net_fail": hits_net,
                "reachability_rate": round(rate, 4),
                "threshold": min_rate,
            },
        )
