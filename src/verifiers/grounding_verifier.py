"""GroundingVerifier (CLOSED_WORLD_REDESIGN.md section 7).

Orchestrates the decidable, anti-fabrication-first grounding metric. It composes
the existing citation stack (extract_citations, the quote_match fetcher, optional
NLI) and feeds resolved per-claim evidence to the pure
``src.scoring.closed_world_grounding`` scorer.

Pipeline:
  1. Split the report into sentences; a sentence carrying >= 1 citation is a claim,
     and a sentence that needs a citation (NeedCite) but has none is a claim too.
  2. Fetch every cited URL on the sandbox. reachable = serves non-empty content.
     An unreachable URL is a FAILED citation, never excluded (the FACT bug fix).
  3. Per claim, compute support (supp in {0, 0.5, 1.0}) of the sentence by the
     UNION of its reachable cited pages, and ALCE load-bearing flags per citation.
  4. Build ClaimEvidence and call closed_world_grounding.

Determinism / no-API: support defaults to token-overlap (same idea as
quote_match), so the whole metric runs offline with no model. Inject a stronger
``support_fn`` (local NLI deberta, or the my5090 vLLM via the OpenAI path) for
sharper judging without changing the score's shape.

The fetch is injectable (``fetch_fn``); the evidence builder
``build_claim_evidence`` is pure and unit-tested with mock page text.
"""

from __future__ import annotations

import concurrent.futures
import re
from typing import Any, Callable

from .base import VerifierResult
from .citation_format import extract_citations, canonicalize_url
from ..scoring.closed_world_grounding import (
    CiteFlags,
    ClaimEvidence,
    closed_world_grounding,
)


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


def _overlap(claim: str, page: str) -> float:
    """Fraction of claim tokens present in the page text. 0 if no claim tokens."""
    ct = _tokens(claim)
    if not ct:
        return 0.0
    return len(ct & _tokens(page)) / len(ct)


def default_support_level(claim: str, page_union: str, *, hi: float = 0.5, lo: float = 0.2) -> float:
    """Deterministic 3-level support from token overlap: 1.0 / 0.5 / 0.0.

    The token-overlap proxy mirrors quote_match. Replace via ``support_fn`` with
    an NLI / LLM entailment call for sharper judging (the levels stay the same).
    """
    o = _overlap(claim, page_union)
    if o >= hi:
        return 1.0
    if o >= lo:
        return 0.5
    return 0.0


def default_needs_citation(sentence: str) -> bool:
    """Heuristic NeedCite: a sentence states a checkable fact if it carries a
    number, price, or percent. High-precision for product/forum/wiki facts;
    non-numeric synthesis claims are left to the rubric layer. Pluggable.
    """
    s = sentence or ""
    if len(s.split()) < 4:
        return False
    return bool(re.search(r"\d", s) or re.search(r"[$¥%]", s))


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[])")


def _sentence_spans(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, sentence_text) for each sentence in the report.

    Markdown link syntax is kept here (offsets must line up with the original
    text so citations map to the right sentence); the cleaned claim text used for
    overlap strips the link syntax.
    """
    spans: list[tuple[int, int, str]] = []
    # Split on newlines first so headings / list items are separate claims, then
    # on sentence boundaries within each line.
    pos = 0
    for line in text.split("\n"):
        line_start = pos
        pos += len(line) + 1  # account for the consumed newline
        if not line.strip():
            continue
        start = line_start
        for piece in _SENT_SPLIT_RE.split(line):
            if not piece:
                continue
            idx = text.find(piece, start)
            if idx < 0:
                idx = start
            spans.append((idx, idx + len(piece), piece))
            start = idx + len(piece)
    return spans


def _clean_claim(text: str) -> str:
    t = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", text)  # markdown link -> label
    t = re.sub(r"`[^`]*`", " ", t)
    t = re.sub(r"[#>*_~]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def build_claim_evidence(
    answer: str,
    page_texts: dict[str, str | None],
    *,
    support_fn: Callable[[str, str], float] | None = None,
    lb_support_fn: Callable[[str, str], float] | None = None,
    needcite_fn: Callable[[str], bool] | None = None,
) -> list[ClaimEvidence]:
    """Pure evidence builder. ``page_texts`` maps a cited URL (canonical or raw)
    to its fetched text, or None if unreachable. Returns ClaimEvidence per claim.

    ``support_fn`` judges the claim's overall support by the union of its reachable
    sources (this is the one that may be an LLM). ``lb_support_fn`` is the cheaper
    per-citation necessity check used for ALCE load-bearing flags; it defaults to
    the deterministic token-overlap so load-bearing does not multiply LLM calls.

    Offline-testable: pass a mock ``page_texts`` and no fetch happens.
    """
    support_fn = support_fn or default_support_level
    lb_support_fn = lb_support_fn or default_support_level
    needcite_fn = needcite_fn or default_needs_citation

    # Canonical-keyed page index so reachability matches regardless of URL form.
    page_index: dict[str, str | None] = {}
    for u, txt in (page_texts or {}).items():
        page_index[canonicalize_url(u)] = txt

    citations = extract_citations(answer, sandbox_hosts=None, sandbox_only=False)
    spans = _sentence_spans(answer)

    # Map each citation to the sentence span that contains its char offset.
    def _sentence_of(offset: int) -> int:
        for i, (a, b, _t) in enumerate(spans):
            if a <= offset < b:
                return i
        return -1

    grouped: dict[int, list] = {}
    for c in citations:
        si = _sentence_of(c.char_offset)
        grouped.setdefault(si, []).append(c)

    claims: list[ClaimEvidence] = []
    cited_sentences: set[int] = set()

    for si, cites in grouped.items():
        sent_text = spans[si][2] if 0 <= si < len(spans) else cites[0].claim_context
        claim_text = _clean_claim(sent_text)
        cited_sentences.add(si)

        # Resolve reachability + per-page text for this claim's citations.
        resolved = []  # (citation, reachable, page_text)
        for c in cites:
            page = page_index.get(c.canonical_url)
            reachable = bool(page)
            resolved.append((c, reachable, page or ""))

        reachable_pages = [pt for (_c, reach, pt) in resolved if reach]
        union = " ".join(reachable_pages)
        # supp is 0 when no reachable citation backs the claim (NeedCite/FACT-fix).
        supp = support_fn(claim_text, union) if reachable_pages else 0.0

        union_level = supp
        cite_flags: list[CiteFlags] = []
        for (c, reach, pt) in resolved:
            if not reach:
                load_bearing = False
            else:
                # ALCE: load-bearing if it supports the claim alone, OR removing
                # it drops the joint support level. Uses the cheap lb_support_fn
                # (token overlap) so this O(cites) test never fans out LLM calls.
                alone = lb_support_fn(claim_text, pt)
                others = " ".join(
                    p for (_c2, r2, p) in resolved if r2 and _c2 is not c
                )
                without_level = lb_support_fn(claim_text, others) if others else 0.0
                load_bearing = (alone > 0.0) or (without_level < union_level)
            cite_flags.append(CiteFlags(url=c.canonical_url, reachable=reach, load_bearing=load_bearing))

        needs = needcite_fn(claim_text)
        claims.append(ClaimEvidence(needs_citation=needs, supp=supp, cites=cite_flags))

    # NeedCite: factual sentences with NO citation are required claims scoring 0.
    for i, (_a, _b, sent_text) in enumerate(spans):
        if i in cited_sentences:
            continue
        claim_text = _clean_claim(sent_text)
        if needcite_fn(claim_text):
            claims.append(ClaimEvidence(needs_citation=True, supp=0.0, cites=[]))

    return claims


def _fetch_pages(urls: list[str], *, max_workers: int = 4) -> dict[str, str | None]:
    """Fetch sandbox pages concurrently, reusing the quote_match fetcher."""
    from .quote_match_verifier import _fetch
    out: dict[str, str | None] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_fetch, u): u for u in urls}
        for fut in concurrent.futures.as_completed(futs):
            out[futs[fut]] = fut.result()
    return out


def llm_support_fn(claim: str, source: str) -> float:
    """vLLM (Qwen3-8B) grounding verdict, with deterministic fallback on miss."""
    from ..scoring import local_llm
    v = local_llm.support_level(claim, source)
    return default_support_level(claim, source) if v < 0 else v


def llm_needcite_fn(sentence: str) -> bool:
    """vLLM NeedCite verdict, with deterministic fallback on server miss."""
    from ..scoring import local_llm
    v = local_llm.needs_citation(sentence)
    return default_needs_citation(sentence) if v is None else v


class GroundingVerifier:
    """Closed-world grounding: ReachRate**gamma * GroundF1@K* (section 7)."""

    kind = "grounding"

    def __init__(
        self,
        *,
        gamma: float = 1.0,
        k_star: int | None = None,
        use_llm: bool = False,
        support_fn: Callable[[str, str], float] | None = None,
        lb_support_fn: Callable[[str, str], float] | None = None,
        needcite_fn: Callable[[str], bool] | None = None,
        fetch_fn: Callable[[list[str]], dict[str, str | None]] | None = None,
        max_urls: int = 150,
        max_workers: int = 4,
    ) -> None:
        self.gamma = gamma
        self.k_star = k_star
        # use_llm routes the claim-support verdict to the self-hosted vLLM judge
        # (Qwen3-8B) with a deterministic token-overlap fallback. Load-bearing
        # stays on the cheap token-overlap so LLM calls are ~1 per claim.
        self.use_llm = use_llm
        self.support_fn = support_fn
        self.lb_support_fn = lb_support_fn
        self.needcite_fn = needcite_fn
        self.fetch_fn = fetch_fn
        self.max_urls = max_urls
        self.max_workers = max_workers

    def _k_star(self, task_config: dict[str, Any]) -> int:
        if self.k_star is not None:
            return self.k_star
        cfg = task_config.get("grounding") or {}
        if cfg.get("k_star"):
            return int(cfg["k_star"])
        # Default: number of vital fact-nuggets in the golden, if available.
        vital = cfg.get("vital_nugget_count")
        return int(vital) if vital else 8

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any = None) -> VerifierResult:
        citations = extract_citations(answer, sandbox_hosts=None, sandbox_only=False)
        unique_raw = list({c.raw_url for c in citations})[: self.max_urls]
        if not unique_raw:
            # No citations at all -> ungrounded. Report 0 (the gate crushes it).
            return VerifierResult(
                score=0.0, passed=False,
                details={"grounding": 0.0, "ground_f1": 0.0, "ground_precision": 0.0,
                         "ground_recall": 0.0, "reach_rate": 0.0, "supported_mass": 0.0,
                         "n_required": 0, "n_citations": 0, "n_reachable": 0,
                         "reason": "no_citations", "flags": ["no_citations"]},
            )

        fetch = self.fetch_fn or (lambda urls: _fetch_pages(urls, max_workers=self.max_workers))
        raw_pages = fetch(unique_raw)
        # Re-key by canonical so build_claim_evidence matches regardless of form.
        page_texts = {u: raw_pages.get(u) for u in unique_raw}

        support_fn = self.support_fn
        needcite_fn = self.needcite_fn
        if self.use_llm:
            support_fn = support_fn or llm_support_fn
            needcite_fn = needcite_fn or llm_needcite_fn
        claims = build_claim_evidence(
            answer, page_texts,
            support_fn=support_fn,
            lb_support_fn=self.lb_support_fn,
            needcite_fn=needcite_fn,
        )
        k_star = self._k_star(task_config)
        result = closed_world_grounding(claims, k_star=k_star, gamma=self.gamma)

        floor = float((task_config.get("grounding") or {}).get("min_grounding", 0.0))
        return VerifierResult(
            score=result["grounding"],
            passed=result["grounding"] >= floor,
            details={**result, "k_star": k_star, "gamma": self.gamma},
        )
