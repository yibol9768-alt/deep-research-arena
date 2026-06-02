from __future__ import annotations

import re


def is_cjk_char(ch: str) -> bool:
    """Return True for Han characters commonly used in Chinese text."""
    if not ch:
        return False
    cp = ord(ch)
    return (
        0x3400 <= cp <= 0x4DBF
        or 0x4E00 <= cp <= 0x9FFF
        or 0xF900 <= cp <= 0xFAFF
        or 0x20000 <= cp <= 0x2A6DF
        or 0x2A700 <= cp <= 0x2B73F
        or 0x2B740 <= cp <= 0x2B81F
        or 0x2B820 <= cp <= 0x2CEAF
        or 0x2CEB0 <= cp <= 0x2EBEF
        or 0x30000 <= cp <= 0x3134F
    )


def cjk_ratio(text: str) -> float:
    """Fraction of CJK characters among all non-space characters."""
    chars = [ch for ch in (text or "") if not ch.isspace()]
    if not chars:
        return 0.0
    return sum(1 for ch in chars if is_cjk_char(ch)) / len(chars)


_LATIN_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_/-]*")


def count_words(text: str) -> int:
    """CJK-aware word count.

    Each CJK character counts as one word because Chinese normally has no
    whitespace boundaries. Non-CJK runs are whitespace-tokenized, with tokens
    kept only when they contain an ASCII letter or digit.
    """
    total = 0
    run: list[str] = []

    def flush_run() -> None:
        nonlocal total
        if not run:
            return
        chunk = "".join(run)
        total += sum(1 for token in chunk.split() if _LATIN_WORD_RE.search(token))
        run.clear()

    for ch in text or "":
        if is_cjk_char(ch):
            flush_run()
            total += 1
        else:
            run.append(ch)
    flush_run()
    return total


def detect_languages(text: str) -> set[str]:
    """Detect English and Chinese with transparent threshold heuristics.

    Returns a subset of {"en", "zh"}. Chinese is detected when the CJK ratio
    is at least 0.15, or when there are at least 20 CJK characters and the
    CJK ratio is at least 0.08. English is detected from Latin word presence.
    """
    s = text or ""
    ratio = cjk_ratio(s)
    cjk_chars = sum(1 for ch in s if is_cjk_char(ch))
    latin_words = len(_LATIN_WORD_RE.findall(s))

    langs: set[str] = set()
    if ratio >= 0.15 or (cjk_chars >= 20 and ratio >= 0.08):
        langs.add("zh")
    if latin_words >= 5:
        langs.add("en")
    return langs
