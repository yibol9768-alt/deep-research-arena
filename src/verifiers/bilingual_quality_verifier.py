"""Bilingual quality verifier for Chinese, English, and bilingual reports.

The verifier is intentionally standalone for Q4. It is imported directly by
callers that opt in, rather than being registered in src/verifiers/__init__.py.
"""

from __future__ import annotations

import re
from typing import Any

from src.utils.text_cjk import cjk_ratio, count_words, detect_languages, is_cjk_char

from .base import VerifierResult, is_degenerate_answer
from .judge_client import call_judge, judge_identity


LANGUAGE_MATCH_WEIGHT = 0.50
TERMINOLOGY_WEIGHT = 0.25
FLUENCY_WEIGHT = 0.25

ZH_STRONG_RATIO = 0.20
ZH_TRACE_RATIO = 0.08
EN_MAX_CJK_RATIO = 0.05
BILINGUAL_MIN_CJK_CHARS = 80
BILINGUAL_MIN_LATIN_WORDS = 80

_URL_RE = re.compile(r"https?://\S+")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_CODE_RE = re.compile(r"`[^`]*`")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'_/-]*")
_SCORE_RE = re.compile(
    r"\b(?:SCORE|LEVEL)\s*[:\-]\s*([0-9](?:\.[0-9]+)?)\b",
    re.IGNORECASE,
)

_ZH_PUNCT = set("。，；：？！")
_MOJIBAKE_MARKERS = ("Ã", "Â", "Ð", "å", "æ", "ä")

# Heuristic term map for deterministic consistency checks. The verifier
# inspects Chinese-dominant spans and penalizes repeated switching between
# multiple Chinese translations, or repeated use of an English token alongside
# its Chinese rendering in the same Chinese section.
_TERM_MAP: dict[str, tuple[str, tuple[str, ...]]] = {
    "citation": ("citation", ("引用", "引文", "出处", "标注")),
    "claim": ("claim", ("主张", "说法", "声明")),
    "evidence": ("evidence", ("证据", "佐证", "证明")),
    "source": ("source", ("来源", "信源", "资料源")),
    "risk": ("risk", ("风险", "隐患")),
    "method": ("method", ("方法", "方法论")),
    "model": ("model", ("模型",)),
    "data": ("data", ("数据",)),
    "price": ("price", ("价格",)),
    "rating": ("rating", ("评分", "评级")),
    "review": ("review", ("评论", "评价")),
    "forum": ("forum", ("论坛", "社区")),
    "product": ("product", ("产品", "商品")),
    "report": ("report", ("报告",)),
}


_FLUENCY_SYSTEM = (
    "You are a strict Chinese and bilingual report-quality judge. Score only "
    "fluency, naturalness, punctuation, and encoding quality. Do not judge "
    "factual correctness. Output exactly two lines:\n"
    "SCORE: <number from 0 to 1>\n"
    "EVIDENCE: <short phrase>"
)


def _visible_text(text: str) -> str:
    s = text or ""
    s = _MD_LINK_RE.sub(r"\1", s)
    s = _URL_RE.sub(" ", s)
    s = _CODE_RE.sub(" ", s)
    return s


def _section_language_counts(visible: str) -> dict[str, int]:
    sections = [part.strip() for part in re.split(r"\n{2,}", visible) if part.strip()]
    en_words = 0
    zh_chars = 0
    for section in sections:
        section_ratio = cjk_ratio(section)
        section_cjk = sum(1 for ch in section if is_cjk_char(ch))
        section_latin_words = len(_LATIN_WORD_RE.findall(section))
        if section_ratio <= 0.10:
            en_words += section_latin_words
        if section_ratio >= 0.25:
            zh_chars += section_cjk
    return {
        "english_section_latin_words": en_words,
        "chinese_section_cjk_chars": zh_chars,
    }


def _language_profile(text: str) -> dict[str, Any]:
    visible = _visible_text(text)
    nonspace = [ch for ch in visible if not ch.isspace()]
    cjk_chars = sum(1 for ch in visible if is_cjk_char(ch))
    latin_words = _LATIN_WORD_RE.findall(visible)
    latin_letters = sum(1 for ch in visible if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    section_counts = _section_language_counts(visible)
    return {
        "visible_text": visible,
        "nonspace_chars": len(nonspace),
        "cjk_chars": cjk_chars,
        "cjk_ratio": cjk_ratio(visible),
        "latin_words": len(latin_words),
        "latin_letters": latin_letters,
        "detected_languages": sorted(detect_languages(visible)),
        "word_count_cjk_aware": count_words(visible),
        **section_counts,
    }


def _language_match(requested: str, profile: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    ratio = float(profile["cjk_ratio"])
    cjk_chars = int(profile["cjk_chars"])
    latin_words = int(profile["latin_words"])
    detected = set(profile["detected_languages"])

    if requested == "en":
        if "en" not in detected:
            score = 0.0
        elif ratio <= EN_MAX_CJK_RATIO:
            score = 1.0
        elif ratio < 0.15:
            score = 0.75
        elif ratio < ZH_STRONG_RATIO:
            score = 0.45
        else:
            score = 0.20
        return score, {
            "rule": "en_requires_latin_text_and_cjk_ratio_at_or_below_0.05_for_full_credit",
            "detected": sorted(detected),
        }

    if requested == "zh":
        if cjk_chars >= BILINGUAL_MIN_CJK_CHARS and ratio >= ZH_STRONG_RATIO:
            score = 1.0
        elif cjk_chars >= 40 and ratio >= 0.15:
            score = 0.75
        elif cjk_chars >= 20 and ratio >= ZH_TRACE_RATIO:
            score = 0.40
        else:
            score = 0.0
        return score, {
            "rule": "zh_requires_cjk_ratio_at_or_above_0.20_for_full_credit",
            "detected": sorted(detected),
        }

    zh_section_chars = int(profile["chinese_section_cjk_chars"])
    en_section_words = int(profile["english_section_latin_words"])
    zh_substantial = zh_section_chars >= BILINGUAL_MIN_CJK_CHARS and ratio >= ZH_TRACE_RATIO
    en_substantial = en_section_words >= BILINGUAL_MIN_LATIN_WORDS
    if zh_substantial and en_substantial:
        score = 1.0
    elif zh_section_chars >= 30 and en_section_words >= 30:
        score = 0.55
    elif zh_substantial or en_substantial:
        score = 0.20
    else:
        score = 0.0
    return score, {
        "rule": "bilingual_requires_80_plus_cjk_chars_and_80_plus_latin_words",
        "detected": sorted(detected),
        "zh_substantial": zh_substantial,
        "en_substantial": en_substantial,
        "chinese_section_cjk_chars": zh_section_chars,
        "english_section_latin_words": en_section_words,
    }


def _zh_dominant_text(visible: str) -> str:
    spans = re.split(r"\n{2,}|(?<=[。！？])\s*|\r+", visible)
    zh_spans = [
        span
        for span in spans
        if sum(1 for ch in span if is_cjk_char(ch)) >= 8 and cjk_ratio(span) >= 0.25
    ]
    return "\n".join(zh_spans) if zh_spans else visible


def _count_latin_term(text: str, term: str) -> int:
    return len(
        re.findall(
            rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])",
            text,
            re.IGNORECASE,
        )
    )


def _terminology_consistency(requested: str, profile: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    if requested == "en":
        return 1.0, {"mode": "not_applicable_for_english"}

    if int(profile["cjk_chars"]) == 0:
        return 0.20, {"mode": "no_cjk_content", "heuristic": "term_map_in_chinese_dominant_spans"}

    zh_text = _zh_dominant_text(str(profile["visible_text"]))
    concept_hits: list[dict[str, Any]] = []
    variant_flips = 0
    script_flips = 0

    for concept, (english, zh_terms) in _TERM_MAP.items():
        english_count = _count_latin_term(zh_text, english)
        zh_counts = {term: zh_text.count(term) for term in zh_terms}
        repeated_zh_terms = {term: n for term, n in zh_counts.items() if n >= 2}
        total = english_count + sum(zh_counts.values())
        if total == 0:
            continue

        if len(repeated_zh_terms) > 1:
            variant_flips += 1
        if english_count >= 2 and sum(zh_counts.values()) >= 2:
            script_flips += 1

        concept_hits.append({
            "concept": concept,
            "english_count": english_count,
            "zh_counts": {k: v for k, v in zh_counts.items() if v},
        })

    if not concept_hits:
        return 0.65, {
            "mode": "no_mapped_terms",
            "heuristic": "term_map_in_chinese_dominant_spans",
        }

    score = max(0.0, 1.0 - 0.15 * variant_flips - 0.10 * script_flips)
    return score, {
        "mode": "term_map_in_chinese_dominant_spans",
        "variant_flips": variant_flips,
        "script_flips": script_flips,
        "concept_hits": concept_hits[:8],
        "heuristic": (
            "Penalize repeated switching among Chinese variants for the same "
            "concept, and repeated English-token/Chinese-token flips inside "
            "Chinese-dominant spans."
        ),
    }


def _sentence_lengths(text: str) -> list[int]:
    pieces = re.split(r"[.!?。！？；;]+|\n{2,}", text)
    return [count_words(piece) for piece in pieces if count_words(piece) > 0]


def _deterministic_fluency(requested: str, profile: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    visible = str(profile["visible_text"])
    score = 1.0
    penalties: list[str] = []

    mojibake_count = sum(visible.count(marker) for marker in _MOJIBAKE_MARKERS)
    if "�" in visible or mojibake_count >= 2:
        score -= 0.30
        penalties.append("mojibake_or_replacement_char")

    control_count = sum(1 for ch in visible if ord(ch) < 32 and ch not in "\n\r\t")
    if control_count:
        score -= 0.20
        penalties.append("control_characters")

    lengths = _sentence_lengths(visible)
    if lengths:
        very_short_ratio = sum(1 for n in lengths if n <= 2) / len(lengths)
        very_long_ratio = sum(1 for n in lengths if n >= 120) / len(lengths)
        if len(lengths) >= 6 and very_short_ratio > 0.50:
            score -= 0.15
            penalties.append("many_fragment_sentences")
        if very_long_ratio > 0.25:
            score -= 0.20
            penalties.append("many_overlong_sentences")

    if requested in {"zh", "bilingual"} and int(profile["cjk_chars"]) >= 50:
        no_urls = _URL_RE.sub(" ", visible)
        zh_punct_count = sum(1 for ch in no_urls if ch in _ZH_PUNCT)
        ascii_period_count = no_urls.count(".")
        if zh_punct_count == 0 and ascii_period_count >= 5:
            score -= 0.20
            penalties.append("zh_text_without_zh_punctuation")
        if re.search(r"\.{3,}", no_urls):
            score -= 0.10
            penalties.append("ascii_period_runs_in_zh_text")

    return max(0.0, min(1.0, score)), {
        "penalties": penalties,
        "sentence_count": len(lengths),
        "max_sentence_words": max(lengths) if lengths else 0,
    }


def _parse_judge_score(text: str | None) -> float | None:
    if not text:
        return None
    m = _SCORE_RE.search(text)
    if not m:
        return None
    value = float(m.group(1))
    if value > 1.0 and value <= 5.0:
        value = (value - 1.0) / 4.0
    return max(0.0, min(1.0, value))


def _fluency_score(
    requested: str,
    answer: str,
    profile: dict[str, Any],
    *,
    deterministic_only: bool,
) -> tuple[float, dict[str, Any]]:
    deterministic_score, det_details = _deterministic_fluency(requested, profile)
    details: dict[str, Any] = {
        "deterministic_score": deterministic_score,
        "deterministic_details": det_details,
    }

    if deterministic_only:
        details["fluency_mode"] = "deterministic_only"
        return deterministic_score, details

    if requested not in {"zh", "bilingual"}:
        details["fluency_mode"] = "deterministic_english"
        return deterministic_score, details

    user = (
        f"Requested language: {requested}\n\n"
        "Report excerpt, truncated to 5000 chars:\n---\n"
        f"{(answer or '')[:5000]}\n---\n\n"
        "Score only language fluency. Output SCORE and EVIDENCE."
    )
    try:
        raw, err = call_judge(_FLUENCY_SYSTEM, user, max_tokens=120, temperature=0.0)
    except Exception as exc:  # pragma: no cover - defensive fallback
        raw, err = None, f"{type(exc).__name__}: {exc}"

    judge_score = _parse_judge_score(raw)
    details.update({
        "fluency_mode": "deterministic_plus_judge" if judge_score is not None else "deterministic_fallback",
        "judge_score": judge_score,
        "judge_error": err,
        "raw_judge_output": (raw or "")[:500],
        "judge_model": judge_identity()["model"],
        "judge_provider": judge_identity()["provider"],
    })
    if judge_score is None:
        return deterministic_score, details
    return 0.70 * deterministic_score + 0.30 * judge_score, details


class BilingualQualityVerifier:
    """Score report language fit, terminology consistency, and fluency."""

    kind = "bilingual"

    def verify(
        self,
        *,
        task_config: dict[str, Any],
        answer: str,
        page: Any = None,
        deterministic_only: bool = False,
    ) -> VerifierResult:
        del page

        base_degenerate, reason = is_degenerate_answer(answer, min_words=1, require_citations=False)
        word_count = count_words(_visible_text(answer or ""))
        if base_degenerate or word_count < 30:
            return VerifierResult(
                score=0.0,
                passed=False,
                details={
                    "reason": f"degenerate_answer:{reason or f'cjk_word_count_too_low:{word_count}'}",
                    "word_count_cjk_aware": word_count,
                },
            )

        requested = str(task_config.get("language", "en") or "en").lower()
        if requested not in {"en", "zh", "bilingual"}:
            requested = "en"

        profile = _language_profile(answer)
        language_score, language_details = _language_match(requested, profile)
        terminology_score, terminology_details = _terminology_consistency(requested, profile)
        fluency_score, fluency_details = _fluency_score(
            requested,
            answer,
            profile,
            deterministic_only=deterministic_only,
        )

        score = (
            LANGUAGE_MATCH_WEIGHT * language_score
            + TERMINOLOGY_WEIGHT * terminology_score
            + FLUENCY_WEIGHT * fluency_score
        )
        return VerifierResult(
            score=round(score, 3),
            passed=score >= 0.60,
            details={
                "requested_language": requested,
                "language_match": round(language_score, 3),
                "terminology_consistency": round(terminology_score, 3),
                "fluency": round(fluency_score, 3),
                "weights": {
                    "language_match": LANGUAGE_MATCH_WEIGHT,
                    "terminology_consistency": TERMINOLOGY_WEIGHT,
                    "fluency": FLUENCY_WEIGHT,
                },
                "language_profile": {
                    k: v for k, v in profile.items() if k != "visible_text"
                },
                "language_details": language_details,
                "terminology_details": terminology_details,
                "fluency_details": fluency_details,
                "fluency_mode": fluency_details.get("fluency_mode"),
                "thresholds": {
                    "zh_strong_ratio": ZH_STRONG_RATIO,
                    "zh_trace_ratio": ZH_TRACE_RATIO,
                    "en_max_cjk_ratio": EN_MAX_CJK_RATIO,
                    "bilingual_min_cjk_chars": BILINGUAL_MIN_CJK_CHARS,
                    "bilingual_min_latin_words": BILINGUAL_MIN_LATIN_WORDS,
                },
            },
        )
