from __future__ import annotations

from typing import Any

from .base import Verifier, VerifierResult


def _clean(s: str) -> str:
    s = (s or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1]
    return s.lower()


class StringVerifier:
    """Port of WebArena StringEvaluator (exact_match / must_include).

    Reads `task_config["eval"]["reference_answers"]` which may contain:
      - "exact_match": str
      - "must_include": list[str]  (all phrases must appear)
    """

    kind = "string_match"

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any = None) -> VerifierResult:
        refs = (task_config.get("eval") or {}).get("reference_answers") or {}
        if not refs:
            return VerifierResult.fail("no reference_answers in task_config")

        clean_pred = _clean(answer)
        score = 1.0
        breakdown: dict[str, Any] = {"pred": clean_pred}

        if "exact_match" in refs:
            ref = _clean(refs["exact_match"])
            breakdown["exact_match_ref"] = ref
            if clean_pred != ref:
                score = 0.0

        if "must_include" in refs:
            phrases = refs["must_include"]
            if not isinstance(phrases, list):
                return VerifierResult.fail("must_include must be a list", got=type(phrases).__name__)
            misses = [p for p in phrases if _clean(p) not in clean_pred]
            breakdown["must_include_misses"] = misses
            if misses:
                score = 0.0

        return VerifierResult.ok(score=score, **breakdown) if score > 0 else VerifierResult(
            score=0.0, passed=False, details=breakdown
        )
