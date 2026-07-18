from __future__ import annotations

import src.verifiers.factual_exactness_verifier as factual
from src.verifiers.citation_format import materialize_reference_links


URL = "http://localhost:9999/comments/source-1"


def _numbered_answer() -> str:
    words = " ".join(f"grounded{i}" for i in range(60))
    return (
        "# Report\n\n"
        f"The cited source identifies the example product as Model One. {words} [1]\n\n"
        "## References\n\n"
        f"[1] {URL}\n"
    )


def test_materialize_reference_links_converts_claim_not_definition() -> None:
    resolved = materialize_reference_links(_numbered_answer())

    assert f"[1]({URL})" in resolved
    assert f"[1] {URL}" in resolved
    assert resolved.count(f"[1]({URL})") == 1


def test_factual_exactness_accepts_numbered_native_citation(monkeypatch) -> None:
    seen_paragraphs: list[str] = []

    def fake_extract(paragraph: str):
        seen_paragraphs.append(paragraph)
        return [{
            "subject": "example product",
            "predicate": "is identified as",
            "value": "Model One",
            "value_type": "entity",
            "source_url": URL,
            "raw_span": "the example product as Model One",
        }]

    monkeypatch.setattr(factual, "_extract_from_paragraph", fake_extract)
    monkeypatch.setattr(
        factual,
        "_fetch_url",
        lambda url: (url, "The example product is identified as Model One."),
    )

    result = factual.FactualExactnessVerifier(max_paragraphs=2).verify(
        task_config={"sandbox_hosts": ["localhost:9999"]},
        answer=_numbered_answer(),
    )

    assert result.score == 1.0
    assert result.details["paragraphs_attempted"] == 1
    assert seen_paragraphs == [
        next(
            paragraph
            for paragraph in materialize_reference_links(_numbered_answer()).split("\n\n")
            if f"[1]({URL})" in paragraph
        )
    ]
