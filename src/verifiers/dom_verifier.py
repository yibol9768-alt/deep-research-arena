from __future__ import annotations

from typing import Any

from .base import Verifier, VerifierResult


class DOMVerifier:
    """Port of WebArena HTMLContentEvaluator (text_match mode).

    Reads `task_config["eval"]["program_html"]` which is a list of:
      {
        "url": <url to navigate to before check, or "last" for current>,
        "locator": <optional JS expression that returns a string>,
        "required_contents": {"exact_match"|"must_include": ...}
      }
    """

    kind = "dom_contains"

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any) -> VerifierResult:
        specs = (task_config.get("eval") or {}).get("program_html") or []
        if not specs:
            return VerifierResult.fail("no program_html in task_config")
        if page is None:
            return VerifierResult.fail("page required")

        misses: list[dict[str, Any]] = []
        for i, spec in enumerate(specs):
            url = spec.get("url") or "last"
            locator = spec.get("locator") or ""
            req = spec.get("required_contents") or {}

            if url != "last":
                page.goto(url)

            if locator:
                text = page.evaluate(locator)
            else:
                text = page.content()
            text = text or ""

            if "exact_match" in req:
                ref = (req["exact_match"] or "").strip().lower()
                if text.strip().lower() != ref:
                    misses.append({"i": i, "kind": "exact_match", "ref": ref, "got": text[:200]})
            if "must_include" in req:
                for phrase in req["must_include"]:
                    if phrase.lower() not in text.lower():
                        misses.append({"i": i, "kind": "must_include", "ref": phrase})

        if not misses:
            return VerifierResult.ok(checks=len(specs))
        return VerifierResult(score=0.0, passed=False, details={"misses": misses, "checks": len(specs)})
