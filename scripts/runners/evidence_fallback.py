"""Shared source-grounded rescue writer for benchmark runners.

This module is intentionally small and dependency-light. It is used only after a
runner's native path fails to produce a usable report within its own budget.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Iterable

logger = logging.getLogger(__name__)


class EvidenceFallbackDisabled(RuntimeError):
    """Raised when the source-grounded rescue writer is invoked in benchmark mode.

    In a benchmark run the saved report MUST be the framework's own output. A
    harness-written stand-in synthesized from raw search evidence is a fairness
    violation: because the generator is deterministic given a fixed task+shim,
    several distinct frameworks that all fall through to it emit byte-identical
    reports (the canonical smoke8c symptom where flowsearcher-ds, smolagents,
    and storm produced the same 21052-byte file). The generator therefore
    survives ONLY when ``EVIDENCE_FALLBACK_ENABLE`` is explicitly set, mirroring
    the ``FLOWSEARCHER_MEMORY`` opt-in for the (equally unfair) memory channel.
    """


def fallback_enabled() -> bool:
    """True only when the evidence-fallback writer is explicitly opted in.

    Default is OFF so benchmark runs never ghostwrite a report on a framework's
    behalf. Set ``EVIDENCE_FALLBACK_ENABLE=1`` for non-benchmark experiments.
    """
    return os.environ.get("EVIDENCE_FALLBACK_ENABLE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def error_stub(lane: str, phase: str, reason: str) -> str:
    """Honest per-lane failure stub, shape ``(<lane> error: <phase>: <reason>)``.

    Classified as ``stub_exception`` by ``src.eval.report_stubs.classify_report``
    so a framework failure surfaces in the score/meta channel instead of being
    laundered into a scored report.
    """
    lane = " ".join(str(lane or "runner").split()) or "runner"
    phase = " ".join(str(phase or "unknown").split()) or "unknown"
    reason = " ".join(str(reason).split())[:200] or "unknown"
    return f"({lane} error: {phase}: {reason})"


_STUB_CLASSES = frozenset({"stub_timeout", "stub_runner_failure", "stub_exception"})


def keep_or_stub(lane: str, phase: str, reason: str, text: str | None) -> str:
    """Benchmark-mode policy for a weak-but-REAL framework report: keep it.

    Capture must not judge quality; the scorer does that. When the framework
    produced ANY non-stub textual output (``classify_report(text) == "ok"``,
    or nonempty text that is merely short), that output is saved VERBATIM and
    a one-line warning records that it was under threshold. ``error_stub`` is
    reserved for genuine non-output: empty/whitespace text, or text that
    ``classify_report`` already flags as a stub (timeout / runner-failure /
    exception placeholders). Timeout and exception call sites must keep
    calling ``error_stub`` directly instead of routing through here.
    """
    s = "" if text is None else str(text)
    if not s.lstrip("\ufeff").strip():
        return error_stub(lane, phase, reason)
    try:
        from src.eval.report_stubs import classify_report
    except ImportError:  # standalone import without the repo root on sys.path
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from src.eval.report_stubs import classify_report
    if classify_report(s) in _STUB_CLASSES:
        return error_stub(lane, phase, reason)
    logger.warning(
        "%s %s: %s; saving the framework's own output verbatim (%d chars) "
        "instead of an error stub",
        lane, phase, reason, len(s),
    )
    return s


_STOPWORDS = {
    "about", "above", "after", "again", "against", "also", "because", "before",
    "being", "between", "could", "every", "from", "have", "into", "only",
    "over", "source", "sources", "their", "there", "these", "this", "through",
    "using", "what", "when", "where", "which", "while", "with", "without",
    "would", "actually", "really", "honestly", "report", "final", "answer",
    "recommendation", "recommendations", "comparison", "compare",
}


def sandbox_url_count(text: str) -> int:
    return len(set(re.findall(r"https?://(?:localhost|127\.0\.0\.1):[0-9]+[^\s)\]]+", text or "")))


def is_weak_report(text: str, *, min_chars: int = 3000, min_urls: int = 3) -> bool:
    if len((text or "").strip()) < min_chars:
        return True
    lowered = (text or "").lower()
    bad_phrases = (
        "produced no report",
        "no report extracted",
        "runner error",
        "local-deep-research error",
        "cannot answer",
        "no information",
        "not present in the sources",
    )
    if any(p in lowered for p in bad_phrases):
        return True
    return sandbox_url_count(text) < min_urls


def _compact(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def _search_queries(intent: str) -> list[str]:
    compact_intent = _compact(intent, 520)
    tokens: list[str] = []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9+./-]{2,}", intent.lower()):
        if tok not in _STOPWORDS and not tok.startswith("http") and tok not in tokens:
            tokens.append(tok)
    keyword = " ".join(tokens[:14])
    queries = [compact_intent]
    if keyword:
        queries.extend(
            [
                keyword,
                f"{keyword} product price specifications",
                f"{keyword} reddit forum experience advice",
                f"{keyword} wikipedia background explanation",
                f"{keyword} tradeoffs buying guide",
            ]
        )
    seen = set()
    out = []
    for q in queries:
        q = _compact(q, 520)
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out[:6]


def collect_sandbox_evidence(
    intent: str,
    shim_url: str,
    *,
    max_items: int = 18,
    max_results: int = 8,
    snippet_chars: int = 1200,
    timeout_s: int = 25,
) -> list[dict[str, str]]:
    try:
        import requests
    except Exception as e:  # noqa: BLE001
        logger.warning("requests unavailable for evidence collection: %s", e)
        return []

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    endpoint = shim_url.rstrip("/") + "/search"
    for query in _search_queries(intent):
        try:
            resp = requests.post(
                endpoint,
                headers={"content-type": "application/json"},
                json={
                    "query": query,
                    "api_key": os.environ.get("TAVILY_API_KEY", "tvly-shim-fake"),
                    "max_results": max_results,
                    "include_raw_content": True,
                },
                timeout=timeout_s,
            )
            resp.raise_for_status()
            data = resp.json() or {}
        except Exception as e:  # noqa: BLE001
            logger.warning("evidence search failed for %r: %s", query, e)
            continue
        for item in data.get("results") or []:
            url = str(item.get("url") or "").strip()
            if not url or url in seen:
                continue
            if not re.match(r"https?://(?:localhost|127\.0\.0\.1):[0-9]+", url):
                continue
            seen.add(url)
            content = (
                item.get("raw_content")
                or item.get("raw_body_content")
                or item.get("content")
                or item.get("snippet")
                or ""
            )
            rows.append(
                {
                    "query": query,
                    "title": _compact(item.get("title") or "Untitled source", 180),
                    "url": url,
                    "content": _compact(content, snippet_chars),
                }
            )
            if len(rows) >= max_items:
                return rows
    return rows


def _render_evidence(evidence: Iterable[dict[str, str]], *, snippet_chars: int = 900) -> str:
    parts = []
    for idx, item in enumerate(evidence, 1):
        parts.append(
            "\n".join(
                [
                    f"Source {idx}",
                    f"Title: {item.get('title') or 'Untitled source'}",
                    f"URL: {item.get('url') or ''}",
                    f"Query: {item.get('query') or ''}",
                    f"Content: {_compact(item.get('content') or '', snippet_chars)}",
                ]
            )
        )
    return "\n\n".join(parts)


def _source_type(url: str) -> str:
    if ":17770" in url or ":7770" in url:
        return "product catalog"
    if ":9999" in url:
        return "forum discussion"
    if ":8090" in url:
        return "encyclopedia"
    return "sandbox source"


def deterministic_report(
    intent: str,
    evidence: list[dict[str, str]],
    *,
    min_chars: int = 4500,
) -> str:
    if not evidence:
        return (
            "# Source-Grounded Answer\n\n"
            "The available local source search did not return usable records for this task. "
            "A reliable recommendation cannot be made from the provided corpus alone.\n\n"
            "## References\n\n"
            "- No local source URLs were returned."
        )

    citations = [f"[{item['title']}]({item['url']})" for item in evidence]
    by_type = {"product catalog": 0, "forum discussion": 0, "encyclopedia": 0, "sandbox source": 0}
    for item in evidence:
        by_type[_source_type(item["url"])] = by_type.get(_source_type(item["url"]), 0) + 1

    lines = [
        "# Source-Grounded Answer",
        "",
        "## Short Answer",
        "",
        (
            "The safest answer is to make a cautious decision from the strongest local "
            f"records rather than from general knowledge. The retrieved set includes "
            f"{by_type.get('product catalog', 0)} product-catalog records, "
            f"{by_type.get('forum discussion', 0)} forum-discussion records, and "
            f"{by_type.get('encyclopedia', 0)} encyclopedia records. Start with "
            f"{citations[0]} and cross-check it against {citations[min(1, len(citations)-1)]} "
            f"and {citations[min(2, len(citations)-1)]} before treating any single source as decisive."
        ),
        "",
        "## Evidence Map",
        "",
    ]

    for idx, item in enumerate(evidence[:14], 1):
        title = item["title"]
        url = item["url"]
        source_type = _source_type(url)
        content = item.get("content") or "The record has little extractable text."
        lines.extend(
            [
                f"### {idx}. {title}",
                "",
                (
                    f"This {source_type} record was retrieved for the query "
                    f"`{_compact(item.get('query') or '', 120)}`: [{title}]({url}). "
                    f"The usable text says: {_compact(content, 700)}"
                ),
                "",
                (
                    "For the user's decision, treat this as direct evidence only when the "
                    "title and content match the product, service, community experience, or "
                    "background mechanism being asked about. When the match is broad rather "
                    "than exact, use it as context and give more weight to the more specific "
                    f"sources in the same set, especially {citations[0]}."
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## Source-Grounded Recommendation",
            "",
            (
                "The recommendation should follow three rules. First, prefer sources that "
                "directly discuss the user's stated constraints over sources that merely "
                "share a category label. Second, separate product claims from community "
                "experience: catalog pages are useful for specifications and availability, "
                "while forum records are more useful for comfort, failure modes, and lived "
                f"tradeoffs. Third, use encyclopedia records such as {next((c for c, item in zip(citations, evidence) if _source_type(item['url']) == 'encyclopedia'), citations[0])} "
                "only for background concepts, not for product-specific verdicts."
            ),
            "",
            (
                f"Based on the retrieved set, the best-supported answer should cite at least "
                f"these representative sources inline: {', '.join(citations[: min(6, len(citations))])}. "
                "If those records point in different directions, the final verdict should "
                "state the conflict plainly and recommend the option with the strongest match "
                "to the user's constraints."
            ),
            "",
            "## Practical Decision Rule",
            "",
            (
                "Use the following decision rule when applying the evidence. If a record gives "
                "specific measurements, prices, feature lists, or exact product names, use it "
                "for the concrete comparison. If a forum record gives repeated user experience "
                "around fit, comfort, reliability, or compatibility, use it to qualify the "
                "catalog claims. If an encyclopedia record explains a mechanism or term, use it "
                "to explain why a tradeoff exists, but do not let it override more specific "
                "catalog or forum evidence."
            ),
            "",
        ]
    )

    while len("\n".join(lines)) < min_chars:
        for item in evidence[:8]:
            lines.extend(
                [
                    f"Additional note from [{item['title']}]({item['url']}):",
                    (
                        "This source remains relevant because it anchors the answer to a "
                        f"retrieved local record rather than an unsupported assumption. "
                        f"Key extract: {_compact(item.get('content') or '', 420)}"
                    ),
                    "",
                ]
            )
            if len("\n".join(lines)) >= min_chars:
                break

    lines.extend(["## References", ""])
    for item in evidence:
        lines.append(f"- [{item['title']}]({item['url']})")
    return "\n".join(lines).strip()


def synthesize_report(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    min_chars: int = 4500,
    min_urls: int = 5,
    llm_timeout_s: int = 240,
    max_items: int = 18,
) -> str:
    # Fairness gate: in benchmark mode the saved report must be the framework's
    # own output, never a harness-synthesized stand-in. Refuse loudly unless the
    # caller has explicitly opted into the non-benchmark evidence writer. Callers
    # that want a clean per-lane stub should check ``fallback_enabled()`` first
    # and emit ``error_stub(...)`` instead of relying on this exception.
    if not fallback_enabled():
        raise EvidenceFallbackDisabled(
            "evidence-fallback writer is benchmark-disabled; set "
            "EVIDENCE_FALLBACK_ENABLE=1 for non-benchmark experiments only"
        )
    evidence = collect_sandbox_evidence(intent, shim_url, max_items=max_items)
    evidence_text = _render_evidence(evidence)
    skip_llm = os.environ.get("EVIDENCE_FALLBACK_SKIP_LLM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    try:
        llm_timeout_s = int(os.environ.get("EVIDENCE_FALLBACK_LLM_TIMEOUT_S", llm_timeout_s))
    except (TypeError, ValueError):
        pass

    if evidence_text and not skip_llm:
        try:
            import requests

            prompt = f"""You are writing a source-grounded deep research report.

User request:
{intent}

Local source evidence:
{evidence_text}

Write the final markdown report directly.

Requirements:
- Use only the local source evidence above.
- Start with the practical answer or verdict.
- Cite factual claims inline with exact URLs from the evidence.
- Cover product/catalog records, forum records, and encyclopedia records when present.
- Discuss tradeoffs, uncertainty, and edge cases.
- End with a References section listing cited URLs.
- Do not discuss process details or tool behavior.
"""
            resp = requests.post(
                proxy_url.rstrip("/") + "/chat/completions",
                headers={
                    "content-type": "application/json",
                    "authorization": "Bearer " + os.environ.get("OPENAI_API_KEY", "anything"),
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Return only a markdown report with citations."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 6144,
                },
                timeout=llm_timeout_s,
            )
            resp.raise_for_status()
            text = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
            text = str(text).strip()
            if not is_weak_report(text, min_chars=min_chars, min_urls=min_urls):
                return text
        except Exception as e:  # noqa: BLE001
            logger.warning("source-grounded writer failed: %s", e)

    return deterministic_report(intent, evidence, min_chars=min_chars)
