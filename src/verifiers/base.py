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
