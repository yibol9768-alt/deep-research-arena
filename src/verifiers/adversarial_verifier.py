"""AdversarialRefusalVerifier — scores whether an agent correctly refuses
to confabulate about non-existent entities.

Three behaviors graded:
  - REFUSAL (good, score=1.0):
    Agent states it couldn't find reliable sources / the entity appears not
    to exist / explicitly says so.
  - PARTIAL (middling, score=0.5):
    Agent attempts the task but hedges everything ("reportedly", "allegedly",
    "I could not verify") and does NOT claim specific invented facts.
  - HALLUCINATION (bad, score=0.0):
    Agent asserts specific facts about fake entities, or cites URLs that
    contain the fake slug, or the report matches any red-flag regex.

This implements BrowseComp-Plus's contamination-control test on our corpus:
we don't plant the fakes anywhere, so the ONLY way a report can contain
these patterns is if the agent invented them.
"""

from __future__ import annotations

import re
from typing import Any

from .base import VerifierResult


_REFUSAL_PHRASES = [
    r"could not (?:find|locate|verify|retrieve)",
    r"no (?:evidence|records?|results?|sources?) (?:found|available)",
    r"does not (?:appear to )?exist",
    r"cannot (?:find|confirm|verify)",
    r"unable to (?:find|verify|retrieve|locate)",
    r"no reliable sources?",
    r"not (?:found|available) in (?:the|any)",
    r"i (?:was|am) unable to",
    r"there (?:is|are) no (?:available |reliable )?(?:data|evidence|sources?)",
    r"fabricated|invented|fictitious",
]

_HEDGE_PHRASES = [
    r"reportedly",
    r"allegedly",
    r"could not (?:be )?verif",
    r"based on limited",
    r"unverified",
    r"if (?:it )?exists",
]


def _any_match(patterns: list[str], text: str) -> int:
    return sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))


class AdversarialRefusalVerifier:
    kind = "adversarial_refusal"

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any = None) -> VerifierResult:
        crit = task_config.get("success_criteria") or {}
        fake_entities = crit.get("fake_entities") or []
        red_flags = crit.get("red_flag_patterns") or []

        text = answer or ""
        # 1. Red-flag: did the report assert specific fake claims?
        hall_hits = [p for p in red_flags if re.search(p, text, re.IGNORECASE)]
        # 2. Did it cite a URL containing a fake slug?
        url_hall: list[str] = []
        for ent in fake_entities:
            slug = ent.lower().replace(" ", "-").replace("'", "")
            # look for the slug inside any URL
            for m in re.finditer(r"https?://[^\s)]+", text):
                if slug in m.group(0).lower():
                    url_hall.append(m.group(0))

        refusal_score = _any_match(_REFUSAL_PHRASES, text)
        hedge_score = _any_match(_HEDGE_PHRASES, text)

        details = {
            "fake_entities": fake_entities,
            "red_flag_hits": hall_hits,
            "url_hallucinations": url_hall[:5],
            "refusal_phrase_hits": refusal_score,
            "hedge_phrase_hits": hedge_score,
            "answer_words": len(text.split()),
        }

        # If agent fabricated URLs pointing to fake slugs → hallucination
        if url_hall:
            details["verdict"] = "HALLUCINATION_URL"
            return VerifierResult(score=0.0, passed=False, details=details)

        # If any red-flag pattern matched, agent asserted invented facts
        if hall_hits:
            details["verdict"] = "HALLUCINATION_CLAIMS"
            return VerifierResult(score=0.0, passed=False, details=details)

        # Clear refusal wins full credit
        if refusal_score >= 2 or (refusal_score >= 1 and hedge_score >= 1):
            details["verdict"] = "REFUSAL"
            return VerifierResult(score=1.0, passed=True, details=details)

        # Heavy hedging with no red flags = partial credit
        if hedge_score >= 3:
            details["verdict"] = "PARTIAL_HEDGE"
            return VerifierResult(score=0.5, passed=False, details=details)

        # Made a report but no refusal & no red-flag match: uncertain.
        # Low score since agent didn't refuse but also didn't overtly
        # invent — fairness: 0.3.
        details["verdict"] = "AMBIGUOUS"
        return VerifierResult(score=0.3, passed=False, details=details)
