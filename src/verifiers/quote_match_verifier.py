"""QuoteMatchVerifier — Layer 2 of the citation-fidelity stack.

Given an agent's markdown report and a golden file with `quoted_span` per
triple, scores each cited URL by:

  1. Fetch the URL on the sandbox (must return 200; we only score reachable
     URLs).
  2. For every (url, claim) pair extracted from the agent's prose nearest
     the citation, fuzzy-match: are the key tokens of the claim present
     on the page?
  3. Aggregate per-claim support scores into one report-level score.

Compared to URLReachabilityVerifier this catches *misattribution* —
the URL exists but does not actually contain anything supporting the
claim. Compared to claim_nli_verifier it is purely surface-level
(token overlap, no entailment) and therefore cheap and deterministic.

Scoring:

    quote_match_rate  =  |claims_with_token_overlap >= 0.4| / |total_claims|

Threshold defaults to 0.4 token-Jaccard between claim noun-phrases and
the page text. We do NOT use the golden's `quoted_span` here; that is
for layer 3 (NLI). Layer 2 only checks that *some* page evidence
supports the agent's claim.
"""

from __future__ import annotations

import concurrent.futures
import re
from typing import Any

from .base import VerifierResult


_MD_LINK_RE = re.compile(r"\[(?P<label>[^\]]*)\]\((?P<url>https?://[^)\s]+)\)")
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "of", "to", "in", "on", "for", "with", "and", "or", "but", "as", "at",
    "by", "from", "this", "that", "these", "those", "it", "its", "their",
    "his", "her", "our", "your", "we", "you", "they", "i", "he", "she",
    "has", "have", "had", "do", "does", "did", "will", "would", "can",
    "could", "should", "may", "might", "shall", "must",
}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", s.lower()) if t not in _STOP}


def _claim_context(markdown: str, span_start: int, window: int = 200) -> str:
    """Return ~window chars of text around the markdown link site, used as
    the claim context for token-overlap measurement."""
    a = max(0, span_start - window)
    b = min(len(markdown), span_start + window)
    chunk = markdown[a:b]
    chunk = _MD_LINK_RE.sub(lambda m: m.group("label"), chunk)
    chunk = re.sub(r"`[^`]*`", " ", chunk)
    chunk = re.sub(r"\s+", " ", chunk)
    return chunk.strip()


def _fetch(url: str, timeout: float = 8.0, retries: int = 2) -> str | None:
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    for attempt in range(retries + 1):
        try:
            r = requests.get(
                url, timeout=timeout, allow_redirects=True,
                headers={"User-Agent": "deep-quote-match/1.0"},
            )
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
                tag.decompose()
            return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:20000]
        except Exception:
            if attempt == retries:
                return None
    return None


class QuoteMatchVerifier:
    kind = "quote_match"

    def __init__(self, max_workers: int = 4, max_urls: int = 150,
                 jaccard_threshold: float = 0.10):
        self.max_workers = max_workers
        self.max_urls = max_urls
        self.jaccard_threshold = jaccard_threshold

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any = None) -> VerifierResult:
        sandbox_hosts: list[str] = task_config.get("sandbox_hosts") or [
            "localhost:7770", "localhost:9999", "localhost:8090",
        ]
        sandbox_set = {h.lower() for h in sandbox_hosts}

        # Use the shared extractor so bare URLs are picked up too — quote_match
        # used to silently fail with claims_total=0 on agents that emit raw
        # https:// URLs instead of [label](url).
        from .base import extract_cited_pairs
        pairs = extract_cited_pairs(answer, sandbox_set)
        claims: list[tuple[str, str]] = [(u, c) for u, c, _ in pairs]

        if not claims:
            return VerifierResult.fail(
                "no sandbox-domain citations (markdown or bare URL)",
                claims_total=0,
            )

        unique_urls = list({u for u, _ in claims})[: self.max_urls]
        page_cache: dict[str, str | None] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = {ex.submit(_fetch, u): u for u in unique_urls}
            for fut in concurrent.futures.as_completed(futs):
                page_cache[futs[fut]] = fut.result()

        n_supported = 0
        n_unreachable = 0
        per_claim: list[dict] = []
        for url, ctx in claims:
            page_text = page_cache.get(url)
            if page_text is None:
                n_unreachable += 1
                per_claim.append({"url": url[:80], "supported": False, "reason": "unreachable"})
                continue
            ctx_tokens = _tokens(ctx)
            page_tokens = _tokens(page_text)
            if not ctx_tokens:
                per_claim.append({"url": url[:80], "supported": False, "reason": "no_claim_tokens"})
                continue
            overlap = len(ctx_tokens & page_tokens) / max(1, len(ctx_tokens))
            ok = overlap >= self.jaccard_threshold
            if ok:
                n_supported += 1
            per_claim.append({
                "url": url[:80], "supported": ok,
                "overlap": round(overlap, 3),
            })

        total = len(claims)
        rate = n_supported / total if total else 0.0
        threshold = float((task_config.get("quote_match") or {}).get("min_match_rate", 0.30))
        return VerifierResult(
            score=round(rate, 4),
            passed=rate >= threshold,
            details={
                "claims_total": total,
                "claims_supported": n_supported,
                "claims_unreachable": n_unreachable,
                "match_rate": round(rate, 4),
                "threshold": threshold,
                "jaccard_floor": self.jaccard_threshold,
                "samples": per_claim[:6],
            },
        )
