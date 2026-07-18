from __future__ import annotations

from src.verifiers import citation_alignment_verifier as cav


LOCAL_URL = "http://localhost:7770/product/headset"


def test_numbered_reference_binds_to_inline_claim_not_bibliography(monkeypatch):
    report = (
        "The retrieved product page lists thirty hours of battery life [1].\n\n"
        "## References\n\n"
        f"[1] {LOCAL_URL}\n"
    )
    judged_claims: list[str] = []

    monkeypatch.setattr(cav, "_fetch_url", lambda url: (url, "thirty hours battery life"))

    def judge(claim: str, _body: str):
        judged_claims.append(claim)
        return ("thirty hours" in claim, "VERDICT: SUPPORTED")

    monkeypatch.setattr(cav, "_judge_pair", judge)
    result = cav.CitationAlignmentVerifier().verify(
        task_config={"sandbox_hosts": ["localhost:7770"]},
        answer=report,
    )

    assert result.score == 1.0
    assert result.details["total_pairs"] == 1
    assert result.details["citation_recall"] == 1.0
    assert len(judged_claims) == 1
    assert "References" not in judged_claims[0]


def test_numbered_public_reference_is_filtered_while_local_reference_scores(monkeypatch):
    report = (
        "The sandbox page supports this claim [1]. A public-memory claim [2].\n\n"
        "## References\n\n"
        f"[1] {LOCAL_URL}\n"
        "[2] https://example.com/unretrieved\n"
    )
    monkeypatch.setattr(cav, "_fetch_url", lambda url: (url, "sandbox page support"))
    monkeypatch.setattr(
        cav,
        "_judge_pair",
        lambda claim, _body: ("sandbox page" in claim, "VERDICT: SUPPORTED"),
    )

    pairs = cav._extract_pairs(report, {"localhost:7770"})
    assert [pair["url"] for pair in pairs] == [LOCAL_URL]


def test_markdown_spec_counts_native_numbered_citations():
    from scripts.score_deep_answer import _citation_count

    report = f"A supported claim [1].\n\n## References\n[1] {LOCAL_URL}\n"
    assert _citation_count(report) >= 1
