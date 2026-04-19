"""Claim-level NLI entailment check for citations.

The legacy `citation_verifier.py` uses **substring match** between the
`[link text](url)` token and the fetched page body. CiteLab (ACL 2025
demo) and "On the Capacity of Citation Generation" (arXiv 2410.11217)
showed substring is (a) gameable (agent can trivially copy any token
from the page into the link text) and (b) over-penalises legitimate
citations that paraphrase.

This module replaces that with the same protocol DeepResearch Bench
**FACT** and RAGChecker (NeurIPS 2024) use:

  1. Parse the agent's markdown report into **atomic factual claims**
     (one per `[link-bearing]` sentence).
  2. For each (claim, fetched_page_text) pair, ask the judge LLM:
     **"Is claim entailed by the page?"** → SUPPORTED / NOT_SUPPORTED.
  3. Precision = supported / total_claims_with_citation.
  4. Recall unchanged (it uses the in-domain URL count;
     `citation_verifier.py` still owns that).

Toggle with env var `CITATION_MODE`:
    substring (default, legacy) — the current ALCE-style body.contains
    entailment                  — this file, DeepSeek/Claude judge NLI

We keep substring available as an ablation baseline.
"""

from __future__ import annotations

import os
import re
from typing import Any

from .judge_client import call_judge, judge_identity


_NLI_SYSTEM = (
    "You verify whether a web page SUPPORTS a citation-bearing claim. "
    "You see (1) a sentence from a research report that carries a cited "
    "URL, and (2) the page body. Your job: decide whether the page "
    "evidentially supports the claim.\n\n"
    "Apply textual-entailment style judgement (not literal string match):\n"
    "  - SUPPORTED: the page's content makes the claim true, or provides "
    "specific evidence (product exists, price/rating within ±2%, feature "
    "mentioned, post discusses the topic). Paraphrase is fine.\n"
    "  - SUPPORTED also for feature descriptions that any reasonable "
    "reader would accept after seeing the page (e.g. 'noise cancellation' "
    "for a product explicitly marketed as noise-cancelling).\n"
    "  - NOT_SUPPORTED: page content flatly contradicts claim, page is "
    "about a different product/topic, or the claim's specific numeric "
    "value is wrong outside ±5% tolerance.\n\n"
    "Be lenient on style, strict on facts. Output exactly ONE line: "
    "`VERDICT: SUPPORTED` or `VERDICT: NOT_SUPPORTED`. No other text."
)


_MD_LINK_RE = re.compile(r"\[([^\]]{1,120})\]\((https?://[^)]{1,800})\)")


def extract_claims_with_citations(markdown: str) -> list[tuple[str, str]]:
    """Return a list of (claim_sentence, url) for every sentence or bullet
    that carries a markdown link. Uses full-paragraph/sentence context
    so the judge has enough to evaluate the claim, not just a fragment."""
    if not markdown:
        return []
    # Split into logical chunks on sentence/line breaks, then find chunks
    # that contain a markdown link.
    chunks = re.split(r"(?<=[.!?])\s+|\n{2,}", markdown)
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        for url_match in _MD_LINK_RE.finditer(chunk):
            url = url_match.group(2).strip()
            # Build a readable claim: the surrounding sentence with the
            # markdown syntax removed (keep the link text as a phrase).
            cleaned = _MD_LINK_RE.sub(r"\1", chunk).strip()
            # Cap to ~600 chars so the judge prompt is bounded.
            cleaned = cleaned[:600]
            key = (cleaned[:80], url)
            if key in seen:
                continue
            seen.add(key)
            out.append((cleaned, url))
    return out


def nli_score_citations(
    markdown: str,
    page_bodies: dict[str, str],
    *,
    max_claims: int | None = None,
) -> dict[str, Any]:
    """Score the agent's citations via claim-level entailment.

    `page_bodies` must be `{url: body_text}` for every unique URL the
    agent cited (caller fetches once, passes in).

    Returns a dict with precision, per-claim verdicts, judge identity.
    """
    pairs = extract_claims_with_citations(markdown)
    if max_claims is not None:
        pairs = pairs[:max_claims]

    results: list[dict[str, Any]] = []
    supported = 0
    for claim, url in pairs:
        body = page_bodies.get(url, "")[:8000]
        if not body:
            results.append({"claim": claim[:200], "url": url, "supported": False,
                            "reason": "no page body"})
            continue
        user = (
            f"Claim: {claim[:500]}\n\n"
            f"Page body (truncated):\n{body}\n\n"
            f"Is the claim SUPPORTED by the page?"
        )
        text, err = call_judge(_NLI_SYSTEM, user, max_tokens=80, temperature=0.0)
        if text is None:
            results.append({"claim": claim[:200], "url": url, "supported": False,
                            "reason": f"judge error: {err}"})
            continue
        ok = "SUPPORTED" in text.upper() and "NOT_SUPPORTED" not in text.upper()
        if ok:
            supported += 1
        results.append({"claim": claim[:200], "url": url,
                        "supported": ok, "verdict": text.strip()[:120]})

    total = len(pairs)
    precision = (supported / total) if total else 0.0
    return {
        "mode": "entailment",
        "judge": judge_identity(),
        "total_claims_with_citation": total,
        "supported_claims": supported,
        "citation_precision_nli": round(precision, 3),
        "per_claim": results[:30],  # cap for log size
    }


def citation_mode() -> str:
    return os.environ.get("CITATION_MODE", "substring").lower()
