"""PresentationVerifier -- hybrid deterministic + LLM judge for report quality.

Evaluates 12 binary criteria in two tiers:

  Tier A (deterministic, 6 items):
    1. heading_hierarchy      -- >= 3 levels of markdown headings
    2. section_count          -- >= 5 distinct h2-level sections
    3. section_balance        -- CV of section word-counts < 1.5
    4. list_or_table_usage    -- at least one markdown table or list
    5. no_orphan_text         -- no block > 200 words without a heading above it
    6. flesch_readability     -- Flesch Reading Ease >= 30

  Tier B (LLM judge, 6 items, single call via judge_client):
    7.  logical_flow          -- sections follow logical progression
    8.  transition_quality    -- smooth transitions between sections
    9.  no_meta_filler        -- free of empty meta-commentary
    10. consistent_formatting -- consistent citation style / terminology
    11. conclusion_synthesizes-- final section synthesizes rather than repeats
    12. professional_tone     -- professional language, no AI filler phrases

Score = 0.4 * tier_a_rate + 0.6 * tier_b_rate
"""

from __future__ import annotations

import math
import re
from typing import Any

from .base import VerifierResult
from .judge_client import call_judge, judge_identity


# ---------------------------------------------------------------------------
# Tier A helpers
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+\S", re.MULTILINE)
_H2_SPLIT_RE = re.compile(r"(?=^##\s)", re.MULTILINE)
_TABLE_RE = re.compile(r"^\|.+\|", re.MULTILINE)
_LIST_RE = re.compile(r"^[\s]*[-*+]\s|\d+\.\s", re.MULTILINE)


def _heading_levels(text: str) -> set[int]:
    """Return the set of heading levels present (1-6)."""
    return {len(m.group(1)) for m in _HEADING_RE.finditer(text)}


def _h2_sections(text: str) -> list[str]:
    """Split on h2 headings and return each section body."""
    parts = _H2_SPLIT_RE.split(text)
    # First part is preamble before any h2; keep it only if non-trivial
    sections = []
    for p in parts:
        body = re.sub(r"^##\s+.*$", "", p, count=1, flags=re.MULTILINE).strip()
        if body:
            sections.append(body)
    return sections


def _word_count(text: str) -> int:
    return len(text.split())


def _cv(values: list[float]) -> float:
    """Coefficient of variation (std / mean). Returns 0 if empty/zero mean."""
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance) / mean


def _has_list_or_table(text: str) -> bool:
    return bool(_TABLE_RE.search(text)) or bool(_LIST_RE.search(text))


def _orphan_blocks(text: str, max_words: int = 200) -> int:
    """Count text blocks > max_words that have no heading above them.

    We split the document at every heading line. The first chunk (before
    any heading) is checked; subsequent chunks are fine since they each
    have a heading above.
    """
    parts = re.split(r"^#{1,6}\s+.*$", text, flags=re.MULTILINE)
    orphan_count = 0
    # parts[0] is text before the first heading (if any)
    if parts and _word_count(parts[0]) > max_words:
        orphan_count += 1
    # All later parts have a heading above them, but a very long
    # sub-block without an intervening sub-heading can also be "orphan".
    for part in parts[1:]:
        # Within a headed section, check for long runs without sub-headings
        # We only flag if the ENTIRE section body exceeds the threshold,
        # since it already has at least one heading above it.
        pass
    return orphan_count


def _syllable_count(word: str) -> int:
    """Simple English syllable estimator (no external deps)."""
    word = word.lower().strip(".,;:!?\"'()-")
    if not word:
        return 0
    # Remove trailing silent-e
    if word.endswith("e") and len(word) > 2:
        word = word[:-1]
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in "aeiouy"
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    return max(count, 1)


def _flesch_reading_ease(text: str) -> float:
    """Compute Flesch Reading Ease from raw text.

    Formula: 206.835 - 1.015*(words/sentences) - 84.6*(syllables/words)
    """
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    words = re.findall(r"[a-zA-Z]+", text)
    if not words or not sentences:
        return 0.0
    total_syllables = sum(_syllable_count(w) for w in words)
    asl = len(words) / len(sentences)  # average sentence length
    asw = total_syllables / len(words)  # average syllables per word
    return 206.835 - 1.015 * asl - 84.6 * asw


def _run_tier_a(text: str) -> list[dict[str, Any]]:
    """Evaluate the 6 deterministic criteria. Returns list of result dicts."""
    results: list[dict[str, Any]] = []

    # 1. heading_hierarchy: >= 3 levels
    levels = _heading_levels(text)
    results.append({
        "criterion": "heading_hierarchy",
        "passed": len(levels) >= 3,
        "detail": f"levels_found={sorted(levels)}",
    })

    # 2. section_count: >= 5 h2 sections
    sections = _h2_sections(text)
    results.append({
        "criterion": "section_count",
        "passed": len(sections) >= 5,
        "detail": f"h2_sections={len(sections)}",
    })

    # 3. section_balance: CV of section word counts < 1.5
    wcs = [_word_count(s) for s in sections] if sections else []
    cv = round(_cv([float(w) for w in wcs]), 3)
    results.append({
        "criterion": "section_balance",
        "passed": cv < 1.5 if wcs else False,
        "detail": f"cv={cv}, word_counts={wcs[:8]}",
    })

    # 4. list_or_table_usage
    results.append({
        "criterion": "list_or_table_usage",
        "passed": _has_list_or_table(text),
        "detail": "",
    })

    # 5. no_orphan_text
    orphans = _orphan_blocks(text)
    results.append({
        "criterion": "no_orphan_text",
        "passed": orphans == 0,
        "detail": f"orphan_blocks={orphans}",
    })

    # 6. flesch_readability >= 30
    fre = round(_flesch_reading_ease(text), 1)
    results.append({
        "criterion": "flesch_readability",
        "passed": fre >= 30.0,
        "detail": f"flesch_reading_ease={fre}",
    })

    return results


# ---------------------------------------------------------------------------
# Tier B: LLM judge
# ---------------------------------------------------------------------------

_TIER_B_CRITERIA = [
    "logical_flow: The report sections follow a logical progression (intro -> background -> analysis -> conclusion).",
    "transition_quality: Transitions between sections are smooth, with bridging sentences or logical connectors.",
    "no_meta_filler: The report is free of empty meta-commentary (e.g., 'In this section we will discuss...', 'As mentioned above...').",
    "consistent_formatting: Citation style, terminology, and formatting conventions are consistent throughout.",
    "conclusion_synthesizes: The final section synthesizes findings rather than merely repeating earlier points.",
    "professional_tone: Language is professional and free of AI filler phrases ('Certainly!', 'Great question!', 'It is important to note that...', 'delve').",
]

_JUDGE_SYSTEM = (
    "You are a strict quality judge for deep-research reports. "
    "For each numbered criterion you will output exactly one line: the criterion number, "
    "a period, a space, then PASS or FAIL, optionally followed by a dash and a "
    "brief reason (<=12 words). No other text.\n\n"
    "Be strict: if the report does not clearly satisfy the criterion, mark FAIL."
)


def _build_tier_b_prompt(answer: str) -> str:
    numbered = "\n".join(f"{i+1}. {c}" for i, c in enumerate(_TIER_B_CRITERIA))
    # Two of the criteria — conclusion_synthesizes and consistent_formatting —
    # depend on the END of the report. A pure head truncation systematically
    # FAILed long reports on those criteria. Send head + tail.
    a = (answer or "")
    if len(a) <= 16000:
        excerpt = a
    else:
        excerpt = a[:8000] + "\n\n[...trimmed...]\n\n" + a[-8000:]
    return (
        f"Presentation quality criteria (judge each independently):\n{numbered}\n\n"
        f"Agent report (head + tail; middle elided when long):\n---\n{excerpt}\n---\n\n"
        f"For each criterion, emit one line:\n"
        f"  1. PASS|FAIL  (reason <= 12 words)\n"
        f"  2. PASS|FAIL  (reason <= 12 words)\n"
        f"  ...\n"
    )


def _parse_tier_b(text: str, n: int) -> list[dict[str, Any]]:
    """Parse judge output into per-criterion results.

    Tolerates multiple output formats (numbered, unnumbered, etc.).
    """
    text = text or ""
    out: list[dict[str, Any]] = []

    # Pass 1: numbered parse
    for i in range(n):
        pat = rf"(?:^|\n)\s*{i+1}[\.\)]\s*(PASS|FAIL)\b\s*[-:.]?\s*(.*?)(?=\n\s*\d+[\.\)]|\Z)"
        m = re.search(pat, text, re.S | re.I)
        if m:
            out.append({
                "criterion": _TIER_B_CRITERIA[i].split(":")[0],
                "passed": m.group(1).upper() == "PASS",
                "reason": m.group(2).strip().split("\n")[0][:120],
            })
        else:
            out.append(None)

    # Pass 2: unnumbered PASS/FAIL fallback. Triggered whenever Pass 1
    # missed even one slot — the previous `> n // 2` threshold left
    # mixed-format outputs (e.g. 3 numbered + 3 unnumbered) with the
    # unnumbered half permanently FAILing.
    missing = [i for i, v in enumerate(out) if v is None]
    if missing:
        tokens = re.findall(r"(?:^|\n)\s*(PASS|FAIL)\b", text, re.I)
        if len(tokens) >= n:
            for i in range(n):
                out[i] = {
                    "criterion": _TIER_B_CRITERIA[i].split(":")[0],
                    "passed": tokens[i].upper() == "PASS",
                    "reason": "",
                }

    # Fill missing
    for i, v in enumerate(out):
        if v is None:
            out[i] = {
                "criterion": _TIER_B_CRITERIA[i].split(":")[0],
                "passed": False,
                "reason": "judge did not emit a verdict",
            }
    return out


# ---------------------------------------------------------------------------
# Main verifier
# ---------------------------------------------------------------------------

class PresentationVerifier:
    """Hybrid deterministic + LLM presentation quality verifier."""

    kind = "presentation"

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any = None) -> VerifierResult:
        from .base import is_degenerate_answer
        degen, why = is_degenerate_answer(answer, min_words=50, require_citations=False)
        if degen:
            return VerifierResult.fail(f"degenerate_answer:{why}")

        # --- Tier A (deterministic) ---
        tier_a_items = _run_tier_a(answer)
        tier_a_passed = sum(1 for x in tier_a_items if x["passed"])
        tier_a_rate = tier_a_passed / len(tier_a_items)

        # --- Tier B (LLM judge) ---
        tier_b_items: list[dict[str, Any]] = []
        judge_error: str | None = None
        judge_raw: str = ""

        text, err = call_judge(
            _JUDGE_SYSTEM,
            _build_tier_b_prompt(answer),
            max_tokens=1200,
        )
        if text is None:
            judge_error = err
            # All tier B items fail on judge error
            tier_b_items = [
                {"criterion": c.split(":")[0], "passed": False, "reason": f"judge error: {err}"}
                for c in _TIER_B_CRITERIA
            ]
        else:
            judge_raw = text
            tier_b_items = _parse_tier_b(text, len(_TIER_B_CRITERIA))

        tier_b_passed = sum(1 for x in tier_b_items if x["passed"])
        tier_b_rate = tier_b_passed / len(_TIER_B_CRITERIA)

        # --- Composite score ---
        score = round(0.4 * tier_a_rate + 0.6 * tier_b_rate, 4)

        return VerifierResult(
            score=score,
            passed=score >= 0.5,
            details={
                "tier_a_passed": tier_a_passed,
                "tier_a_total": len(tier_a_items),
                "tier_a_rate": round(tier_a_rate, 3),
                "tier_a_items": tier_a_items,
                "tier_b_passed": tier_b_passed,
                "tier_b_total": len(_TIER_B_CRITERIA),
                "tier_b_rate": round(tier_b_rate, 3),
                "tier_b_items": tier_b_items,
                "judge_model": judge_identity()["model"],
                "judge_provider": judge_identity()["provider"],
                "judge_error": judge_error,
                "raw_judge_output": judge_raw[:800],
            },
        )
