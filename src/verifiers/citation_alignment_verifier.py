"""CitationAlignmentVerifier -- ALCE/FACT-style citation-claim alignment.

For each ``[label](url)`` in a markdown report, fetches the cited URL's
page body from the sandbox and asks an LLM judge whether the page content
actually *supports* the claim being made.  This catches mis-attribution
(URL exists but says nothing related) and fabrication (claim has no
evidential basis on the cited page).

Metrics produced
~~~~~~~~~~~~~~~~
* **citation_precision** = supported_pairs / total_pairs
* **citation_recall**    = sentences_with_at_least_one_supported_cite
                           / sentences_with_any_cite

Algorithm
~~~~~~~~~
1. Regex-extract ``(claim_sentence, url)`` pairs from the markdown.
2. Deduplicate URLs, fetch page bodies in a 4-worker thread pool.
3. For each (claim, body) pair, call the judge LLM for a binary NLI
   verdict (SUPPORTED / NOT_SUPPORTED).
4. Aggregate into precision and recall.

Hard caps: 200 pairs per report, 8 000 chars per page body.
"""

from __future__ import annotations

import concurrent.futures
import re
from typing import Any

from .base import VerifierResult
from .judge_client import call_judge, judge_identity

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_PAIRS = 200
_MAX_PAGE_CHARS = 8_000
_FETCH_TIMEOUT = 8.0
_FETCH_RETRIES = 2
_FETCH_WORKERS = 4

# Markdown link: [label](url)
_MD_LINK_RE = re.compile(
    r"\[(?P<label>[^\]]{1,200})\]\((?P<url>https?://[^)\s]{1,800})\)"
)

# Sentence-ish splitter: split on period/exclamation/question followed by
# whitespace, or on double-newline (paragraph break).  Keeps bullets and
# list items as individual "sentences" too.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}|\n(?=[-*] )")

# ---------------------------------------------------------------------------
# NLI judge prompt
# ---------------------------------------------------------------------------

_NLI_SYSTEM = (
    "You verify whether a web page SUPPORTS a citation-bearing claim.\n"
    "Rules:\n"
    "- SUPPORTED: page content evidentially supports the claim "
    "(product exists, price/rating matches, feature mentioned, "
    "post discusses stated topic). Paraphrase is fine.\n"
    "- NOT_SUPPORTED: page is about a different product/topic, or "
    "the claim's specific factual content is wrong, or page does "
    "not contain relevant information.\n"
    "Output exactly: VERDICT: SUPPORTED or VERDICT: NOT_SUPPORTED"
)

# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    """Remove script/style/nav elements and HTML tags, return plain text."""
    # Remove entire blocks that never carry useful content.
    html = re.sub(
        r"<\s*(script|style|nav|footer|header|noscript|aside|svg)"
        r"[^>]*>.*?</\s*\1\s*>",
        " ", html, flags=re.DOTALL | re.IGNORECASE,
    )
    # Remove remaining tags.
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# ---------------------------------------------------------------------------
# URL fetching
# ---------------------------------------------------------------------------

def _fetch_url(url: str) -> tuple[str, str | None]:
    """Fetch *url*, strip HTML, return (url, body_or_None)."""
    try:
        import requests  # type: ignore
    except ImportError:
        return url, None

    for attempt in range(_FETCH_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                timeout=_FETCH_TIMEOUT,
                allow_redirects=True,
                headers={"User-Agent": "deep-citation-alignment/1.0"},
            )
            if resp.status_code != 200:
                if attempt == _FETCH_RETRIES:
                    return url, None
                continue
            body = _strip_html(resp.text)[:_MAX_PAGE_CHARS]
            return url, body
        except Exception:
            if attempt == _FETCH_RETRIES:
                return url, None
    return url, None

# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract_pairs(markdown: str, sandbox_hosts: set[str]) -> list[dict]:
    """Return list of ``{sentence, label, url, sent_idx}`` dicts.

    Only URLs whose host portion matches one of *sandbox_hosts* are kept.
    ``sent_idx`` is the index of the containing sentence. Catches both
    ``[label](url)`` and bare ``https://...`` (the bare-URL case is what
    breaks for agents like ldr).
    """
    if not markdown:
        return []
    from .base import CITED_BARE_URL_RE, _strip_url_trail, host_in_set

    sentences = _SENT_SPLIT_RE.split(markdown)
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for sent_idx, sent in enumerate(sentences):
        # First markdown links (we keep the label as the cleaned claim).
        urls_seen_in_sent: set[str] = set()
        for m in _MD_LINK_RE.finditer(sent):
            url = _strip_url_trail(m.group("url"))
            if not host_in_set(url, sandbox_hosts):
                continue
            urls_seen_in_sent.add(url)
            cleaned = _MD_LINK_RE.sub(r"\1", sent).strip()[:600]
            key = (cleaned[:80], url)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "sentence": cleaned,
                "label": m.group("label"),
                "url": url,
                "sent_idx": sent_idx,
            })
        # Then bare URLs in the same sentence (skip if already captured
        # via markdown wrapping).
        for m in CITED_BARE_URL_RE.finditer(sent):
            url = _strip_url_trail(m.group(0))
            if not host_in_set(url, sandbox_hosts):
                continue
            if url in urls_seen_in_sent:
                continue
            cleaned = _MD_LINK_RE.sub(r"\1", sent).strip()[:600]
            key = (cleaned[:80], url)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "sentence": cleaned,
                "label": "",
                "url": url,
                "sent_idx": sent_idx,
            })
    return out

# ---------------------------------------------------------------------------
# NLI judging
# ---------------------------------------------------------------------------

def _judge_pair(claim: str, body: str) -> tuple[bool, str]:
    """Ask the LLM judge. Return (supported, raw_verdict_text)."""
    user_prompt = (
        f"Claim: {claim[:500]}\n\n"
        f"Page body (truncated):\n{body}\n\n"
        f"Is the claim SUPPORTED by the page?"
    )
    text, err = call_judge(_NLI_SYSTEM, user_prompt, max_tokens=80, temperature=0.0)
    if text is None:
        return False, f"judge_error: {err}"
    upper = text.upper()
    supported = "SUPPORTED" in upper and "NOT_SUPPORTED" not in upper
    return supported, text.strip()[:120]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class CitationAlignmentVerifier:
    """ALCE/FACT citation-claim alignment verifier."""

    kind = "citation_alignment"

    def __init__(
        self,
        max_workers: int = _FETCH_WORKERS,
        max_pairs: int = _MAX_PAIRS,
        min_precision: float = 0.50,
    ):
        self.max_workers = max_workers
        self.max_pairs = max_pairs
        self.min_precision = min_precision

    # ---- standalone entry point (dict in, dict out) ----

    def verify(
        self,
        *,
        task_config: dict[str, Any],
        answer: str = "",
        page: Any = None,
    ) -> VerifierResult:
        """Score citation alignment of *answer* against sandbox pages.

        Parameters
        ----------
        task_config : dict
            Must contain ``sandbox_hosts`` (list of host:port strings) or
            defaults to the three standard sandbox ports.
        answer : str
            The agent's markdown report.
        page : Any
            Unused (kept for Verifier protocol compatibility).

        Returns
        -------
        VerifierResult
            ``score`` is citation_precision, ``passed`` iff precision
            >= ``min_precision``.  ``details`` carries both precision
            and recall plus per-pair samples.
        """
        sandbox_hosts: list[str] = task_config.get("sandbox_hosts") or [
            "localhost:7770", "localhost:9999", "localhost:8090",
        ]
        sandbox_set = {h.lower() for h in sandbox_hosts}

        # 1. Extract (claim, url) pairs ---------------------------------
        pairs = _extract_pairs(answer, sandbox_set)
        if not pairs:
            return VerifierResult.fail(
                "no sandbox-domain citation links found in answer",
                citation_precision=0.0,
                citation_recall=0.0,
                total_pairs=0,
            )
        pairs = pairs[: self.max_pairs]

        # 2. Fetch unique URLs in parallel ------------------------------
        unique_urls = list({p["url"] for p in pairs})
        page_cache: dict[str, str | None] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(_fetch_url, u): u for u in unique_urls}
            for fut in concurrent.futures.as_completed(futures):
                url, body = fut.result()
                page_cache[url] = body

        # 3. NLI judge each pair ---------------------------------------
        n_supported = 0
        n_fetch_fail = 0
        per_pair: list[dict[str, Any]] = []
        # Track per-sentence: did it have any cite? did it have a supported cite?
        sent_has_cite: set[int] = set()
        sent_has_supported: set[int] = set()

        for p in pairs:
            url = p["url"]
            claim = p["sentence"]
            sent_idx = p["sent_idx"]
            sent_has_cite.add(sent_idx)

            body = page_cache.get(url)
            if not body:
                n_fetch_fail += 1
                per_pair.append({
                    "claim": claim[:200],
                    "url": url[:120],
                    "supported": False,
                    "reason": "fetch_failed",
                })
                continue

            supported, verdict_text = _judge_pair(claim, body)
            if supported:
                n_supported += 1
                sent_has_supported.add(sent_idx)
            per_pair.append({
                "claim": claim[:200],
                "url": url[:120],
                "supported": supported,
                "verdict": verdict_text,
            })

        # 4. Compute metrics -------------------------------------------
        total = len(pairs)
        precision = n_supported / total if total else 0.0
        recall = (
            len(sent_has_supported) / len(sent_has_cite)
            if sent_has_cite
            else 0.0
        )

        threshold = float(
            (task_config.get("citation_alignment") or {}).get(
                "min_precision", self.min_precision
            )
        )
        passed = precision >= threshold

        return VerifierResult(
            score=round(precision, 4),
            passed=passed,
            details={
                "citation_precision": round(precision, 4),
                "citation_recall": round(recall, 4),
                "total_pairs": total,
                "supported_pairs": n_supported,
                "fetch_failures": n_fetch_fail,
                "sentences_with_cite": len(sent_has_cite),
                "sentences_with_supported_cite": len(sent_has_supported),
                "threshold": threshold,
                "judge": judge_identity(),
                "samples": per_pair[:20],
            },
        )


# ---- Module-level convenience (matches standalone dict-in/dict-out) ----

def verify(task_config: dict, answer: str) -> dict:
    """Standalone entry point: ``verify(task_config, answer) -> dict``.

    Returns a plain dict with ``score``, ``passed``, and ``details`` keys.
    """
    v = CitationAlignmentVerifier()
    result = v.verify(task_config=task_config, answer=answer)
    return {
        "score": result.score,
        "passed": result.passed,
        "details": result.details,
    }
