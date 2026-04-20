"""FactoidVerifier — for WebArena-style string_match tasks.

Complementary to the long-form research pillars (markdown_structure / citation /
fact_kg / llm_judge / checklist / evidence_density). Those pillars all assume
the answer is a multi-paragraph report; for WebArena factoid tasks ("What's
the date of my first purchase?"), the answer is a single string and needs a
different eval.

Supported eval types (from WebArena schema):
  - string_match   → check reference_answers.fuzzy_match / exact_match / must_include
  - url_match      → (tolerated but not implemented here; requires runtime URL capture)
  - program_html   → (not implemented; requires DOM access)

Score is 1.0 (full match) / 0.5 (partial must_include hit) / 0.0 (miss).
"""

from __future__ import annotations

import re
from typing import Any

from .base import VerifierResult


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _fuzzy_hit(needle: str, hay: str) -> bool:
    """Fuzzy match = normalized needle appears in normalized hay."""
    return _normalize(needle) in _normalize(hay)


def _number_hit(needle: str, hay: str) -> bool:
    """For answers like '3/2/22' or '$572.8', match the digit/punctuation core."""
    m = re.search(r"[\d][\d./:-]*", needle)
    if not m:
        return False
    core = m.group(0)
    return core in hay.replace(",", "")


class FactoidVerifier:
    """Score a short answer against WebArena reference_answers."""

    kind = "factoid"

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any = None) -> VerifierResult:
        crit = task_config.get("success_criteria") or {}
        eval_types = crit.get("eval_types") or []
        fuzzy = crit.get("fuzzy_match") or []
        exact = crit.get("exact_match") or []
        must = crit.get("must_include") or []

        details: dict[str, Any] = {
            "eval_types": eval_types,
            "fuzzy_hits": [],
            "exact_hits": [],
            "must_hits": [],
        }

        # Non-string_match evals (url_match, program_html) can't be scored
        # without runtime state. Degrade gracefully.
        if eval_types and not any(t == "string_match" for t in eval_types):
            return VerifierResult(
                score=0.0, passed=False,
                details={"reason": f"unsupported eval_types={eval_types}; needs browser runtime"},
            )

        ans = answer or ""

        # 1) Exact match (any one ref = full credit)
        for ref in exact:
            if _normalize(ref) == _normalize(ans):
                details["exact_hits"].append(ref)
                return VerifierResult(score=1.0, passed=True, details=details)

        # 2) Fuzzy match — require ALL fuzzy refs to appear (WebArena semantics)
        if fuzzy:
            hit = []
            miss = []
            for ref in fuzzy:
                if _fuzzy_hit(ref, ans) or _number_hit(ref, ans):
                    hit.append(ref)
                else:
                    miss.append(ref)
            details["fuzzy_hits"] = hit
            details["fuzzy_miss"] = miss
            if not miss:
                return VerifierResult(score=1.0, passed=True, details=details)
            frac = len(hit) / len(fuzzy)
            if frac >= 0.5:
                return VerifierResult(score=0.5, passed=False, details=details)
            return VerifierResult(score=0.0, passed=False, details=details)

        # 3) must_include — partial credit by fraction
        if must:
            hit = [r for r in must if _fuzzy_hit(r, ans)]
            details["must_hits"] = hit
            frac = len(hit) / len(must)
            if frac == 1.0:
                return VerifierResult(score=1.0, passed=True, details=details)
            return VerifierResult(score=frac * 0.5, passed=False, details=details)

        # No criteria at all → can't score
        return VerifierResult(score=0.0, passed=False, details={"reason": "no criteria"})
