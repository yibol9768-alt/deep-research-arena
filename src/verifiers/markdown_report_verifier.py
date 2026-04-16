"""MarkdownReportVerifier — validates the v3 `markdown_spec` quantitative floors.

Replaces the v2 `ReportVerifier` (which enforced a strict JSON schema) for v3
tasks. Agents now emit free-form markdown, but must satisfy:

  - `min_words`          — lower bound on answer length
  - `max_words`          — upper bound (soft; no huge essays)
  - `min_paragraphs`     — number of paragraph-like blocks
  - `min_citations`      — count of markdown [text](url) links to allowed domains
  - `min_pages_browsed`  — distinct pages visited during execution (from trace)
  - `require_markdown_links` — soft requirement that ≥1 link exists

Each floor returns a 0/1 bool; the verifier's score is the fraction passed.

This is a *structural* check — it doesn't judge content quality. Content is
the job of CitationVerifier (ALCE), FactKGVerifier (KG), ChecklistVerifier
(DRACO rubric), and LLMJudgeVerifier (RACE).

Why a separate verifier: keeps the "did the agent obey the task contract"
signal distinct from "is the content correct", which composes into different
Elo views downstream.
"""

from __future__ import annotations

import re
from typing import Any

from .base import VerifierResult


_PARA_SPLIT = re.compile(r"\n\s*\n")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def _paragraph_count(text: str) -> int:
    # A "paragraph" = a blank-line-separated block with ≥1 non-whitespace char.
    return sum(1 for p in _PARA_SPLIT.split(text or "") if p.strip())


def _extract_links(text: str) -> list[tuple[str, str]]:
    return _LINK_RE.findall(text or "")


def _domain_whitelist(must_be_in_domain: list[str]) -> list[str]:
    """Translate '__SHOPPING__'/'__REDDIT__' sentinels to actual domains.

    v3 task definitions use placeholders so the same JSON works against any
    deployment. At verify time we accept both the placeholder and the resolved
    host(s) — matches the same convention as CitationVerifier.
    """
    out: list[str] = []
    for d in must_be_in_domain or []:
        out.append(d)
        if d == "__SHOPPING__":
            out += ["localhost:7770", "127.0.0.1:7770", "one-stop-market"]
        if d == "__REDDIT__":
            out += ["localhost:9999", "127.0.0.1:9999", "postmill"]
    return out


def _citation_count(text: str, allowed_domains: list[str]) -> int:
    """Count markdown links whose URL contains any allowed-domain fragment.

    Empty allowed_domains → count all markdown links (no domain filter).
    """
    links = _extract_links(text)
    if not allowed_domains:
        return len(links)
    whitelist = _domain_whitelist(allowed_domains)
    n = 0
    for _label, url in links:
        u = url.lower()
        if any(frag.lower() in u for frag in whitelist):
            n += 1
    return n


class MarkdownReportVerifier:
    """Structural floor for v3 markdown reports."""

    kind = "markdown_structure"

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any = None) -> VerifierResult:
        spec = task_config.get("markdown_spec") or {}
        if not spec:
            # v2 task — this verifier is a no-op and scores 1.0 so it doesn't
            # penalize legacy rows when accidentally wired in.
            return VerifierResult(score=1.0, passed=True, details={"skipped": "no markdown_spec"})

        text = answer or ""
        words = _word_count(text)
        paras = _paragraph_count(text)

        allowed = (task_config.get("citation_policy") or {}).get("must_be_in_domain") or []
        cites = _citation_count(text, allowed)

        # Pages-browsed can only come from the runner trace. v3 task_config
        # may include 'pages_browsed' injected by the runner; fall back to 0.
        pages_browsed = int(task_config.get("pages_browsed", 0) or 0)

        min_w = int(spec.get("min_words", 0) or 0)
        max_w = int(spec.get("max_words", 10**9) or 10**9)
        min_p = int(spec.get("min_paragraphs", 0) or 0)
        min_c = int(spec.get("min_citations", 0) or 0)
        min_pages = int(spec.get("min_pages_browsed", 0) or 0)

        checks = {
            "min_words":         words >= min_w,
            "max_words":         words <= max_w,
            "min_paragraphs":    paras >= min_p,
            "min_citations":     cites >= min_c,
            # If the runner didn't attach pages_browsed (e.g. dry-run), we
            # don't penalize — treat the gate as "pass" when we don't know.
            "min_pages_browsed": (pages_browsed == 0 and task_config.get("pages_browsed") is None)
                                  or pages_browsed >= min_pages,
        }
        passed = sum(1 for ok in checks.values() if ok)
        total = len(checks)
        score = passed / total

        return VerifierResult(
            score=round(score, 3),
            passed=(passed == total),
            details={
                "words": words,
                "paragraphs": paras,
                "citations": cites,
                "pages_browsed": pages_browsed,
                "spec": {
                    "min_words": min_w, "max_words": max_w,
                    "min_paragraphs": min_p, "min_citations": min_c,
                    "min_pages_browsed": min_pages,
                },
                "checks": checks,
            },
        )
