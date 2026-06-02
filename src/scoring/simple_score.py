"""Simple, deterministic GROUNDING pillar + truth GATE.

Per SCORING_REDESIGN.md sec 2.A. The field consensus across grounding
metrics (ALCE / FActScore / SAFE / RAGAS) reduces to one idea:

    grounding = supported_units / total_units

made anti-volume by construction:
  * adding UNSUPPORTED citations LOWERS precision (more total, same supported);
  * adding NON-GOLDEN citations does NOT raise recall (recall counts golden
    must-cite hits only).

We deliberately do NOT use ``domain_balance`` or any raw-count / volume term
(those were the gameable parts the audit flagged). Quality (pairwise / Elo)
stays a SEPARATE number; ``gate_and_rank`` only applies the truth gate.

Everything here is tiny and pure. Heavy deps (NLI entailment) are never
imported; the default support check is deterministic token overlap. Callers
that want NLI inject it via ``support_fn``.
"""

from __future__ import annotations

import re
from typing import Callable, Iterable, Optional, Sequence


# ---------------------------------------------------------------------------
# Token-overlap support check (default support_fn) — mirrors the cheap,
# deterministic logic in quote_match_verifier so behaviour is consistent.
# ---------------------------------------------------------------------------

_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "of", "to", "in", "on", "for", "with", "and", "or", "but", "as", "at",
    "by", "from", "this", "that", "these", "those", "it", "its", "their",
    "his", "her", "our", "your", "we", "you", "they", "i", "he", "she",
    "has", "have", "had", "do", "does", "did", "will", "would", "can",
    "could", "should", "may", "might", "shall", "must",
}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", (s or "").lower()) if t not in _STOP}


def default_support_fn(claim: str, snippet: str, *, threshold: float = 0.30) -> bool:
    """Deterministic claim-support check: fraction of claim tokens present in
    the retrieved snippet >= threshold. Bounded, offline, no network. This is
    the same surface-overlap idea as quote_match_verifier; swap in an NLI
    entailment checker via the ``support_fn`` argument for stronger judging.
    """
    claim_tokens = _tokens(claim)
    if not claim_tokens:
        return False
    snippet_tokens = _tokens(snippet)
    overlap = len(claim_tokens & snippet_tokens) / len(claim_tokens)
    return overlap >= threshold


# ---------------------------------------------------------------------------
# URL canonicalisation — reuse the single source of truth so proof-of-fetch
# and must-cite matching agree with the rest of the citation stack.
# ---------------------------------------------------------------------------

def _canon(url: str) -> str:
    from src.verifiers.citation_format import canonicalize_url
    return canonicalize_url(url)


def _normalize_cited_pairs(
    cited_pairs: object,
    report_text: Optional[str],
) -> list[tuple[str, str]]:
    """Accept either:
      * a list of ``(url, claim_text)`` tuples, or
      * a list of urls + ``report_text`` (extract pairs from the report).
    Returns a list of ``(raw_url, claim_text)``.
    """
    items = list(cited_pairs or [])
    if not items:
        return []

    # Already (url, claim) pairs?
    first = items[0]
    if isinstance(first, (tuple, list)) and len(first) >= 2:
        return [(str(u), str(c)) for u, c, *_ in items]

    # Otherwise treat as a list of bare URLs. If report_text is given, recover
    # the claim context per citation via the shared extractor.
    urls = {str(u) for u in items}
    if report_text:
        from src.verifiers.citation_format import extract_cited_pairs
        pairs = extract_cited_pairs(report_text, sandbox_hosts=None, sandbox_only=False)
        out: list[tuple[str, str]] = []
        matched: set[str] = set()
        for raw_url, claim_ctx, _off in pairs:
            if _canon(raw_url) in {_canon(u) for u in urls}:
                out.append((raw_url, claim_ctx))
                matched.add(_canon(raw_url))
        # Any url not found in the report still counts as a cited pair with an
        # empty claim (it will be unsupported -> lowers precision, as intended).
        for u in urls:
            if _canon(u) not in matched:
                out.append((u, ""))
        return out

    # No report text: bare urls with empty claims.
    return [(u, "") for u in urls]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def grounding_score(
    cited_pairs: object,
    retrieved_snippets: dict,
    golden: dict,
    *,
    support_fn: Optional[Callable[[str, str], bool]] = None,
    report_text: Optional[str] = None,
) -> dict:
    """Deterministic grounding score = F1(citation_precision, must_cite_recall).

    Parameters
    ----------
    cited_pairs
        Either a list of ``(url, claim_text)`` tuples, or a list of bare URLs
        (pass ``report_text`` so claim context can be recovered via
        ``citation_format.extract_cited_pairs``).
    retrieved_snippets
        ``{url: snippet_text}`` mapping of what the agent actually fetched.
        A cited URL absent here fails proof-of-fetch and is unsupported.
        Keys may be raw or canonical; both are matched canonically.
    golden
        Golden spec with ``must_cite_urls`` (list of ``{"url": ...}`` or bare
        url strings). Recall counts canonical hits against these only.
    support_fn
        ``(claim, snippet) -> bool``. Defaults to deterministic token overlap.
        Inject an NLI entailment checker here for stronger judging.
    report_text
        Optional report text used to recover claim context when ``cited_pairs``
        is a list of bare URLs.

    Returns
    -------
    dict with keys precision, recall, f1, n_cited, n_supported,
    must_cite_recall.

    Anti-volume guarantees:
      * UNSUPPORTED citations raise ``n_cited`` but not ``n_supported`` ->
        precision drops.
      * NON-GOLDEN citations do not appear in ``must_cite_urls`` -> recall
        unchanged.
    """
    if support_fn is None:
        support_fn = default_support_fn

    pairs = _normalize_cited_pairs(cited_pairs, report_text)

    # Build a canonical-keyed snippet index for proof-of-fetch.
    snip_index: dict[str, str] = {}
    for u, text in (retrieved_snippets or {}).items():
        snip_index[_canon(u)] = text or ""

    n_cited = len(pairs)
    n_supported = 0
    for url, claim in pairs:
        c = _canon(url)
        snippet = snip_index.get(c)
        if snippet is None:
            # proof-of-fetch failed: url never fetched -> unsupported.
            continue
        if support_fn(claim, snippet):
            n_supported += 1

    precision = (n_supported / n_cited) if n_cited else 0.0

    # ---- recall: golden must-cite hits only (no volume term) ----
    must_entries = (golden or {}).get("must_cite_urls", []) or []
    must_canon: set[str] = set()
    for e in must_entries:
        url = e.get("url") if isinstance(e, dict) else e
        if url:
            must_canon.add(_canon(url))

    cited_canon = {_canon(u) for u, _ in pairs}
    if must_canon:
        hits = cited_canon & must_canon
        must_cite_recall = len(hits) / len(must_canon)
    else:
        must_cite_recall = 0.0
    recall = must_cite_recall

    if precision > 0.0 and recall > 0.0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "n_cited": n_cited,
        "n_supported": n_supported,
        "must_cite_recall": must_cite_recall,
    }


def gate_and_rank(
    grounding_f1: float,
    quality: float,
    *,
    floor: float = 0.15,
    fabricated: bool = False,
) -> float:
    """Truth GATE: grounding is a gate, NOT a weighted addend to quality.

    Returns 0.0 if the report fabricated a citation (a cited url never
    fetched) OR its grounding F1 falls below ``floor``. Otherwise passes the
    externally-supplied ``quality`` (pairwise / Elo) number through unchanged.

    Quality and grounding stay TWO separate numbers; this only applies the
    gate. Per SCORING_REDESIGN.md: report two numbers, never a single gameable
    composite.
    """
    if fabricated:
        return 0.0
    if grounding_f1 is None or grounding_f1 < floor:
        return 0.0
    return float(quality)
