from __future__ import annotations

from src.verifiers.longform_quality_verifier import LongformQualityVerifier


def _cfg(target_words: int, max_words: int | None = None) -> dict:
    spec = {"target_words": target_words}
    if max_words is not None:
        spec["max_words"] = max_words
    return {"markdown_spec": spec}


def _dense_report(section_count: int = 6, paragraphs_per_section: int = 3) -> str:
    section_names = [
        "Introduction",
        "Evidence Base",
        "Comparative Analysis",
        "Risks and Caveats",
        "Practical Decision Factors",
        "Conclusion and Recommendations",
    ][:section_count]
    citation_idx = 0
    parts = ["# Research Report"]

    for section_idx, section_name in enumerate(section_names):
        parts.append(f"## {section_name}")
        for paragraph_idx in range(paragraphs_per_section):
            sentences = []
            for sentence_idx in range(4):
                citation = ""
                if sentence_idx in (1, 3):
                    citation_idx += 1
                    citation = f" [source](http://example.com/source-{citation_idx})"
                sentences.append(
                    f"{section_name} finding {section_idx}-{paragraph_idx}-{sentence_idx} "
                    "compares verified evidence, decision constraints, cost tradeoffs, "
                    f"timing risk, and user impact{citation}."
                )
            parts.append(" ".join(sentences))

    return "\n\n".join(parts)


def _padded_report(sentence_count: int = 90) -> str:
    sentences = []
    for idx in range(sentence_count):
        citation = ""
        if idx in (2, 45):
            citation = f" [source](http://example.com/padded-{idx})"
        sentences.append(
            f"Generic filler sentence {idx} repeats background context, broad caveats, "
            f"vague observations, and unsupported implications{citation}."
        )
    midpoint = sentence_count // 2
    return (
        "# Research Report\n\n"
        "## Analysis\n\n"
        + " ".join(sentences[:midpoint])
        + "\n\n"
        + " ".join(sentences[midpoint:])
    )


def test_dense_target_length_report_beats_padded_shell():
    verifier = LongformQualityVerifier()
    cfg = _cfg(target_words=1100, max_words=1800)

    padded = verifier.verify(task_config=cfg, answer=_padded_report())
    dense = verifier.verify(task_config=cfg, answer=_dense_report())

    assert padded.details["subscores"]["length_fit"] == 1.0
    assert dense.details["subscores"]["length_fit"] == 1.0
    assert dense.details["word_count"] >= cfg["markdown_spec"]["target_words"]
    assert dense.score > padded.score
    assert dense.score > 0.6


def test_far_below_target_scores_low_on_length_fit():
    verifier = LongformQualityVerifier()
    report = _dense_report(section_count=4, paragraphs_per_section=3)

    result = verifier.verify(task_config=_cfg(target_words=4000, max_words=8000), answer=report)

    assert 700 <= result.details["word_count"] <= 900
    assert result.details["subscores"]["length_fit"] == 0.0


def test_good_report_at_target_scores_above_quality_bar():
    verifier = LongformQualityVerifier()
    report = _dense_report()
    probe = verifier.verify(task_config=_cfg(target_words=1000, max_words=2000), answer=report)
    target = probe.details["word_count"]

    result = verifier.verify(task_config=_cfg(target_words=target, max_words=target + 500), answer=report)

    assert result.details["subscores"]["length_fit"] == 1.0
    assert result.score >= 0.7
