from __future__ import annotations

import pytest

from src.utils.text_cjk import cjk_ratio, count_words
import src.verifiers.bilingual_quality_verifier as bilingual_module
from src.verifiers.bilingual_quality_verifier import BilingualQualityVerifier


@pytest.fixture(autouse=True)
def no_judge_network(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "JUDGE_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    def fail_call_judge(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("call_judge must not be called in deterministic_only mode")

    monkeypatch.setattr(bilingual_module, "call_judge", fail_call_judge)


def test_english_only_report_fails_zh_language_match() -> None:
    answer = (
        "# Safety Audit\n\n"
        "This report reviews a cookware safety claim using product evidence, "
        "community evidence, and encyclopedia context. The central claim is "
        "that the coating remains safe at every cooking temperature. The "
        "available evidence does not support that absolute framing. Product "
        "pages describe ordinary use cases, forum reports discuss overheating "
        "incidents, and reference material explains that high heat can create "
        "hazardous fumes. The report should therefore reject the broad claim "
        "and recommend low-heat use, ventilation, and replacement of warped "
        "pans. The discussion is coherent and detailed, but it is written "
        "only in English, so it should not satisfy a Chinese-language task."
    )

    result = BilingualQualityVerifier().verify(
        task_config={"language": "zh"},
        answer=answer,
        deterministic_only=True,
    )

    assert result.details["language_match"] <= 0.1
    assert result.score < 0.4
    assert result.details["fluency_mode"] == "deterministic_only"


def test_substantial_bilingual_report_passes_language_match() -> None:
    english = (
        "English section. This research report compares product evidence, "
        "forum evidence, and encyclopedia evidence before giving a cautious "
        "recommendation. It explains the claim, the source quality, the risk "
        "model, the data limits, and the practical decision path. The report "
        "uses consistent terminology for evidence, source, citation, claim, "
        "risk, model, data, product, forum, review, price, and rating. It also "
        "separates direct observations from interpretation, then describes why "
        "the strongest conclusion is partial support rather than full support. "
        "Readers can follow the reasoning without needing hidden assumptions, "
        "and every section keeps the same technical vocabulary across the "
        "analysis and final recommendation."
    )
    chinese = (
        "中文部分。这个研究报告比较产品证据、论坛证据和百科证据，然后给出谨慎建议。"
        "报告先说明核心主张，再说明来源质量、风险模型、数据限制和实际决策路径。"
        "全文稳定使用证据、来源、引用、主张、风险、模型、数据、产品、论坛、评论、价格和评分等术语。"
        "它把直接观察和解释判断分开，并说明为什么最强结论是部分支持而不是完全支持。"
        "读者可以顺着论证看到每个来源如何支持或限制结论，最后建议在高风险场景中保留不确定性。"
    )
    answer = f"# Bilingual Research Report\n\n{english}\n\n# 双语研究报告\n\n{chinese}"

    result = BilingualQualityVerifier().verify(
        task_config={"language": "bilingual"},
        answer=answer,
        deterministic_only=True,
    )

    assert result.details["language_match"] >= 0.9
    assert result.score > 0.6
    assert result.details["fluency_mode"] == "deterministic_only"


def test_cjk_word_count_and_ratio_are_sensible() -> None:
    text = "中文研究报告 hello world"

    assert count_words(text) >= 6
    assert 0.30 <= cjk_ratio(text) <= 0.80
