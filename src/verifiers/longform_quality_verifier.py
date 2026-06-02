"""Deterministic long-form quality signal for deep-research markdown reports."""

from __future__ import annotations

import math
import re
from typing import Any

from .base import VerifierResult, is_degenerate_answer
from .citation_format import extract_citations


WEIGHTS: dict[str, float] = {
    "length_fit": 0.40,
    "section_structure": 0.25,
    "paragraph_depth": 0.15,
    "citation_density": 0.20,
}

_DEFAULT_TARGET_WORDS = 4000
_DEFAULT_MAX_MULTIPLIER = 2.0
_MIN_NON_DEGENERATE_WORDS = 50

_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(https?://[^)\s]+\)")
_URL_RE = re.compile(r"https?://\S+")
_CODE_RE = re.compile(r"`[^`]*`")
_CJK_RE = re.compile(
    "[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]"
)
_NON_CJK_TOKEN_RE = re.compile(r"[A-Za-z0-9]")
_PARA_SPLIT_RE = re.compile(r"\n\s*\n+")
_HEADING_RE = re.compile(r"^(?P<marks>#{1,6})[ \t]+(?P<title>\S.*)$", re.MULTILINE)
_LIST_LINE_RE = re.compile(r"^\s{0,3}(?:[-*+]\s+|\d+\.\s+)")
_TABLE_LINE_RE = re.compile(r"^\s*\|")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?。！？]+")

_COMPLEXITY_TARGETS = {
    "low": 2500,
    "simple": 2500,
    "short": 2500,
    "medium": 4000,
    "standard": 4000,
    "default": 4000,
    "high": 6000,
    "hard": 6000,
    "complex": 6000,
    "very_high": 7500,
    "expert": 7500,
}

_INTRO_TERMS = (
    "introduction",
    "overview",
    "executive summary",
    "background",
    "context",
    "scope",
    "question",
)
_CONCLUSION_TERMS = (
    "conclusion",
    "recommendation",
    "recommendations",
    "takeaway",
    "takeaways",
    "summary",
    "verdict",
    "bottom line",
    "implications",
    "next steps",
)
_CLOSING_PHRASES = (
    "overall",
    "in conclusion",
    "taken together",
    "bottom line",
    "the evidence suggests",
)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _text_for_count(text: str) -> str:
    text = _MD_LINK_RE.sub(r"\1", text or "")
    text = _URL_RE.sub(" ", text)
    text = _CODE_RE.sub(" ", text)
    return text


def _word_count(text: str) -> int:
    """Count CJK characters as words plus non-CJK whitespace tokens."""
    cleaned = _text_for_count(text)
    cjk_count = len(_CJK_RE.findall(cleaned))
    non_cjk = _CJK_RE.sub(" ", cleaned)
    tokens = [
        token
        for token in non_cjk.split()
        if _NON_CJK_TOKEN_RE.search(token)
    ]
    return cjk_count + len(tokens)


def _sentence_count(text: str) -> int:
    chunks = [chunk.strip() for chunk in _SENTENCE_SPLIT_RE.split(text or "")]
    count = sum(1 for chunk in chunks if _word_count(chunk) >= 3)
    return count or (1 if _word_count(text) > 0 else 0)


def _complexity_level(task_config: dict[str, Any], spec: dict[str, Any]) -> tuple[str, bool]:
    raw = task_config.get("complexity_level") or spec.get("complexity_level")
    if raw is None:
        return "default", False
    return str(raw).strip().lower() or "default", True


def _target_words(task_config: dict[str, Any], spec: dict[str, Any]) -> tuple[int, str, str]:
    complexity, has_complexity = _complexity_level(task_config, spec)
    explicit_target = _positive_int(spec.get("target_words"))
    if explicit_target is not None:
        return explicit_target, "markdown_spec.target_words", complexity

    min_words = _positive_int(spec.get("min_words"))
    max_words = _positive_int(spec.get("max_words"))
    if min_words is not None and max_words is not None:
        return max(1, int(round((min_words + max_words) / 2))), "markdown_spec.midpoint", complexity

    if has_complexity and complexity in _COMPLEXITY_TARGETS:
        return _COMPLEXITY_TARGETS[complexity], "complexity_level", complexity
    return _DEFAULT_TARGET_WORDS, "default", complexity


def _max_words(spec: dict[str, Any], target: int) -> tuple[int, str]:
    explicit_max = _positive_int(spec.get("max_words"))
    if explicit_max is not None:
        return max(target, explicit_max), "markdown_spec.max_words"
    return max(target, int(round(target * _DEFAULT_MAX_MULTIPLIER))), "target_multiplier"


def _length_fit_score(words: int, target: int, max_words: int) -> tuple[float, dict[str, Any]]:
    lower_zero = 0.4 * target
    decay_end = 1.5 * max_words

    if words <= lower_zero:
        score = 0.0
        band = "too_short"
    elif words < target:
        score = (words - lower_zero) / max(target - lower_zero, 1.0)
        band = "ramp_up"
    elif words <= max_words:
        score = 1.0
        band = "fit"
    else:
        decay_span = max(decay_end - max_words, 1.0)
        score = max(0.6, 1.0 - 0.4 * ((words - max_words) / decay_span))
        band = "overlong_decay"

    return _clamp(score), {
        "band": band,
        "target_words": target,
        "max_words": max_words,
        "zero_until_words": int(math.floor(lower_zero)),
        "decays_to_0_6_at_words": int(math.ceil(decay_end)),
    }


def _paragraph_blocks(text: str) -> list[str]:
    return [block.strip() for block in _PARA_SPLIT_RE.split(text or "") if block.strip()]


def _is_heading_only(block: str) -> bool:
    lines = [line for line in block.splitlines() if line.strip()]
    return bool(lines) and all(_HEADING_RE.match(line.strip()) for line in lines)


def _is_list_block(block: str) -> bool:
    lines = [line for line in block.splitlines() if line.strip()]
    return bool(lines) and all(_LIST_LINE_RE.match(line) for line in lines)


def _is_table_block(block: str) -> bool:
    lines = [line for line in block.splitlines() if line.strip()]
    return bool(lines) and all(_TABLE_LINE_RE.match(line) for line in lines)


def _paragraph_depth_score(text: str, total_words: int) -> tuple[float, dict[str, Any]]:
    blocks = _paragraph_blocks(text)
    paragraphs: list[str] = []
    list_blocks = 0

    for block in blocks:
        if _is_heading_only(block) or _is_table_block(block):
            continue
        if _is_list_block(block):
            list_blocks += 1
            continue
        paragraph_text = _HEADING_RE.sub(" ", block).strip()
        if _word_count(paragraph_text) >= 8:
            paragraphs.append(paragraph_text)

    if not paragraphs:
        return 0.0, {
            "paragraphs": 0,
            "avg_sentences_per_paragraph": 0.0,
            "list_block_ratio": round(list_blocks / max(len(blocks), 1), 3),
            "reason": "no_substantive_paragraphs",
        }

    sentence_counts = [_sentence_count(paragraph) for paragraph in paragraphs]
    word_counts = [_word_count(paragraph) for paragraph in paragraphs]
    avg_sentences = sum(sentence_counts) / len(sentence_counts)

    if 3.0 <= avg_sentences <= 8.0:
        band_score = 1.0
    elif avg_sentences < 3.0:
        band_score = avg_sentences / 3.0
    else:
        band_score = max(0.0, 1.0 - ((avg_sentences - 8.0) / 12.0))

    one_line_ratio = sum(1 for n in sentence_counts if n <= 1) / len(sentence_counts)
    giant_ratio = sum(
        1 for words, sentences in zip(word_counts, sentence_counts, strict=True)
        if words > 250 or sentences > 10
    ) / len(word_counts)
    list_block_ratio = list_blocks / max(len(blocks), 1)

    score = band_score
    score *= max(0.40, 1.0 - (0.45 * one_line_ratio))
    score *= max(0.30, 1.0 - (0.65 * giant_ratio))
    score *= max(0.20, 1.0 - (0.75 * list_block_ratio))
    if len(paragraphs) == 1 and total_words > 500:
        score *= 0.50

    return _clamp(score), {
        "paragraphs": len(paragraphs),
        "avg_sentences_per_paragraph": round(avg_sentences, 3),
        "one_line_paragraph_ratio": round(one_line_ratio, 3),
        "giant_paragraph_ratio": round(giant_ratio, 3),
        "list_block_ratio": round(list_block_ratio, 3),
    }


def _h2_sections(text: str) -> tuple[list[dict[str, Any]], str]:
    headings = list(_HEADING_RE.finditer(text or ""))
    h2s = [heading for heading in headings if len(heading.group("marks")) == 2]
    if not h2s:
        return [], text or ""

    sections: list[dict[str, Any]] = []
    for idx, heading in enumerate(h2s):
        end = h2s[idx + 1].start() if idx + 1 < len(h2s) else len(text)
        body = text[heading.end():end]
        body_without_headings = _HEADING_RE.sub(" ", body)
        sections.append({
            "title": heading.group("title").strip(),
            "words": _word_count(body_without_headings),
        })
    return sections, text[:h2s[0].start()]


def _coefficient_of_variation(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    if mean <= 0:
        return 0.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance) / mean


def _section_structure_score(text: str) -> tuple[float, dict[str, Any]]:
    headings = list(_HEADING_RE.finditer(text or ""))
    sections, preamble = _h2_sections(text)
    h2_count = len(sections)

    if h2_count <= 1:
        h2_score = 0.0
    else:
        h2_score = min(1.0, h2_count / 4.0)

    section_words = [int(section["words"]) for section in sections]
    total_section_words = sum(section_words)
    if h2_count >= 2 and total_section_words > 0:
        max_share = max(section_words) / total_section_words
        share_score = 1.0 if max_share <= 0.60 else max(0.0, 1.0 - ((max_share - 0.60) / 0.40))
        cv = _coefficient_of_variation([float(words) for words in section_words])
        cv_score = max(0.0, 1.0 - (cv / 1.25))
        balance_score = (0.70 * share_score) + (0.30 * cv_score)
    else:
        max_share = 1.0 if section_words else 0.0
        cv = 0.0
        balance_score = 0.0

    first_title = sections[0]["title"].lower() if sections else ""
    last_title = sections[-1]["title"].lower() if sections else ""
    opening_ok = (
        any(term in first_title for term in _INTRO_TERMS)
        or _word_count(preamble) >= 40
    )

    tail = text[-800:].lower() if text else ""
    closing_ok = (
        any(term in last_title for term in _CONCLUSION_TERMS)
        or any(phrase in tail for phrase in _CLOSING_PHRASES)
    )
    intro_conclusion_score = (float(opening_ok) + float(closing_ok)) / 2.0

    short_sections = sum(1 for words in section_words if words < 40)
    spam_ratio = short_sections / max(h2_count, 1)
    spam_score = max(0.0, 1.0 - spam_ratio)

    score = (
        (0.35 * h2_score)
        + (0.30 * balance_score)
        + (0.20 * intro_conclusion_score)
        + (0.15 * spam_score)
    )
    if h2_count <= 1:
        score = min(score, 0.20)
    if h2_count > 14:
        score *= max(0.50, 1.0 - ((h2_count - 14) / 20.0))

    return _clamp(score), {
        "heading_count": len(headings),
        "h2_sections": h2_count,
        "section_word_counts": section_words[:20],
        "max_section_share": round(max_share, 3),
        "section_word_cv": round(cv, 3),
        "has_intro_like_opening": opening_ok,
        "has_conclusion_like_closing": closing_ok,
        "short_heading_sections": short_sections,
        "heading_spam_ratio": round(spam_ratio, 3),
    }


def _citation_density_score(text: str, words: int) -> tuple[float, dict[str, Any]]:
    citations = extract_citations(text, sandbox_hosts=None, sandbox_only=False)
    citation_count = len(citations)
    density = (citation_count / max(words, 1)) * 1000.0

    if density <= 0.0:
        score = 0.0
    elif density < 8.0:
        score = density / 8.0
    elif density <= 30.0:
        score = 1.0
    else:
        score = max(0.20, 1.0 - ((density - 30.0) / 60.0))

    return _clamp(score), {
        "citations": citation_count,
        "citations_per_1000_words": round(density, 3),
        "healthy_band_per_1000_words": [8, 30],
    }


class LongformQualityVerifier:
    """Grade whether a markdown report is long enough, structured, and dense."""

    kind = "longform_quality"

    def verify(
        self,
        *,
        task_config: dict[str, Any],
        answer: str,
        page: Any = None,
    ) -> VerifierResult:
        text = answer or ""
        degenerate, reason = is_degenerate_answer(text, min_words=1, require_citations=False)
        if degenerate:
            return VerifierResult.fail(reason, kind=self.kind)

        words = _word_count(text)
        if words < _MIN_NON_DEGENERATE_WORDS:
            return VerifierResult.fail(f"word_count_too_low:{words}", kind=self.kind, word_count=words)

        spec = task_config.get("markdown_spec") or {}
        target, target_source, complexity = _target_words(task_config, spec)
        max_words, max_words_source = _max_words(spec, target)

        length_fit, length_details = _length_fit_score(words, target, max_words)
        section_structure, section_details = _section_structure_score(text)
        paragraph_depth, paragraph_details = _paragraph_depth_score(text, words)
        citation_density, citation_details = _citation_density_score(text, words)

        subscores = {
            "length_fit": length_fit,
            "section_structure": section_structure,
            "paragraph_depth": paragraph_depth,
            "citation_density": citation_density,
        }
        score = sum(WEIGHTS[name] * subscores[name] for name in WEIGHTS)
        score = _clamp(score)

        rounded_subscores = {name: round(value, 3) for name, value in subscores.items()}
        return VerifierResult(
            score=round(score, 3),
            passed=score >= 0.5,
            details={
                "word_count": words,
                "target_words": target,
                "target_source": target_source,
                "max_words": max_words,
                "max_words_source": max_words_source,
                "complexity_level": complexity,
                "weights": WEIGHTS,
                "subscores": rounded_subscores,
                "length_fit": rounded_subscores["length_fit"],
                "section_structure": rounded_subscores["section_structure"],
                "paragraph_depth": rounded_subscores["paragraph_depth"],
                "citation_density": rounded_subscores["citation_density"],
                "length_details": length_details,
                "section_details": section_details,
                "paragraph_details": paragraph_details,
                "citation_details": citation_details,
            },
        )


__all__ = ["LongformQualityVerifier"]
