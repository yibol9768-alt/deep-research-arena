from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class VerifierResult:
    score: float
    passed: bool
    details: dict[str, Any]

    @classmethod
    def fail(cls, reason: str, **extra: Any) -> "VerifierResult":
        return cls(score=0.0, passed=False, details={"reason": reason, **extra})

    @classmethod
    def ok(cls, score: float = 1.0, **extra: Any) -> "VerifierResult":
        return cls(score=float(score), passed=score > 0, details=extra)


_DEGENERATE_PREFIXES = ("(empty ", "(runner error", "(error", "(timeout", "(no output")
_MD_LINK_RE_DEGEN = re.compile(r"\[[^\]]*\]\([^)]+\)")

# Citation-extraction regexes shared across all citation-aware verifiers.
# Matching only `[label](url)` was a bug: agents that emit bare URLs
# (ldr's report style) got quote_match / claim_nli / citation_alignment /
# analysis_depth scores of 0 despite citing real, reachable pages.
CITED_MD_LINK_RE = re.compile(r"\[(?P<label>[^\]]*)\]\((?P<url>https?://[^)\s]+)\)")
CITED_BARE_URL_RE = re.compile(r"(?<![(\[])(?<!\]\()https?://[^\s<>\"'`)\]]+")


def _strip_url_trail(url: str) -> str:
    """Strip trailing punctuation that Markdown / sentence breakers leave."""
    return url.rstrip(").,;:`'\"\\!?>")


def extract_cited_pairs(
    answer: str,
    sandbox_hosts: set[str] | None = None,
    *,
    window: int = 200,
    sandbox_only: bool = True,
) -> list[tuple[str, str, int]]:
    """Return ``(url, context, span_start)`` for every cited URL — both
    markdown-link and bare. Optionally filter to sandbox hosts.

    The context is `window` chars on each side of the URL with markdown
    syntax stripped; this is what the verifiers feed to the LLM judge.
    """
    pairs: list[tuple[str, str, int]] = []
    seen: set[tuple[int, str]] = set()
    for rx in (CITED_MD_LINK_RE, CITED_BARE_URL_RE):
        for m in rx.finditer(answer):
            url = _strip_url_trail(m.group("url") if "url" in (m.groupdict() or {}) else m.group(0))
            if not url:
                continue
            if sandbox_hosts is not None and sandbox_only:
                if not any(h in url for h in sandbox_hosts):
                    continue
            key = (m.start(), url)
            if key in seen:
                continue
            seen.add(key)
            a = max(0, m.start() - window)
            b = min(len(answer), m.start() + window)
            ctx = answer[a:b]
            ctx = CITED_MD_LINK_RE.sub(lambda mm: mm.group("label"), ctx)
            ctx = re.sub(r"`[^`]*`", " ", ctx)
            ctx = re.sub(r"\s+", " ", ctx).strip()
            pairs.append((url, ctx, m.start()))
    pairs.sort(key=lambda p: p[2])
    return pairs


def extract_cited_urls(answer: str, sandbox_hosts: set[str] | None = None) -> list[str]:
    """Return the list of distinct sandbox-host URLs cited (markdown + bare)."""
    seen: list[str] = []
    seen_set: set[str] = set()
    for rx in (CITED_MD_LINK_RE, CITED_BARE_URL_RE):
        for m in rx.finditer(answer):
            url = _strip_url_trail(m.group("url") if "url" in (m.groupdict() or {}) else m.group(0))
            if not url or url in seen_set:
                continue
            if sandbox_hosts is not None:
                if not any(h in url for h in sandbox_hosts):
                    continue
            seen_set.add(url)
            seen.append(url)
    return seen


def is_degenerate_answer(answer: str, *, min_words: int = 50, require_citations: bool = True) -> tuple[bool, str]:
    """Detect answers an LLM judge will mishandle without a deterministic pre-check.

    Returns (is_degenerate, reason). Centralised here so every verifier shares
    the same rule. DeepSeek-V4-flash has been observed to PASS-all on
    "(empty storm output)" — that's the failure mode this guards against.
    """
    s = (answer or "").strip()
    if not s:
        return True, "empty_answer"
    low = s.lower()
    for p in _DEGENERATE_PREFIXES:
        if low.startswith(p):
            return True, f"answer_starts_with:{p.strip()}"
    text = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", s)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"[#>*_~]", " ", text)
    wc = len([w for w in text.split() if w])
    if wc < min_words:
        return True, f"word_count_too_low:{wc}"
    if require_citations and not _MD_LINK_RE_DEGEN.search(s):
        return True, "zero_citations"
    return False, ""


class Verifier(Protocol):
    """Stateless predicate that scores an execution against a task's success criteria.

    Implementations receive the task spec, the agent's final answer, and a Playwright
    `Page` for live DOM / URL inspection. Must return a score in [0, 1].
    """

    kind: str

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any) -> VerifierResult:
        ...
