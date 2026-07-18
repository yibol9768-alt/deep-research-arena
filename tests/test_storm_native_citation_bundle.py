from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.score_deep_answer import (
    _markdown_spec_score,
    _resolve_native_citation_bundle,
    verify_report_seal,
)
from src.verifiers.citation_format import extract_citations


def _write_bundle(
    root: Path,
    report_text: str,
    url_to_index: dict[str, int],
) -> tuple[Path, Path, Path]:
    report = root / "storm__task_rep1.md"
    sidecar = report.with_suffix(".storm-url-to-info.json")
    meta = report.with_suffix(".meta.json")
    report.write_text(report_text, encoding="utf-8")
    payload = {
        "url_to_unified_index": url_to_index,
        "url_to_info": {url: {"url": url, "snippets": ["native"]}
                        for url in url_to_index},
    }
    sidecar_bytes = (json.dumps(payload, ensure_ascii=False) + "\n").encode()
    sidecar.write_bytes(sidecar_bytes)
    report_bytes = report.read_bytes()
    meta.write_text(json.dumps({
        "agent": "storm",
        "report_seal": {
            "sha256": hashlib.sha256(report_bytes).hexdigest(),
            "bytes": len(report_bytes),
        },
        "native_artifacts": {
            "storm_url_to_info": {
                "file": sidecar.name,
                "bytes": len(sidecar_bytes),
                "sha256": hashlib.sha256(sidecar_bytes).hexdigest(),
            }
        },
    }), encoding="utf-8")
    return report, sidecar, meta


def test_storm_bundle_resolves_only_inline_native_indices(tmp_path):
    urls = {
        "http://localhost:7770/used-one.html": 1,
        "http://localhost:9999/f/headphones/unused-two": 2,
        "http://localhost:8090/content/wikipedia_en_all_nopic/A/Headphones": 3,
    }
    original = "# Report\n\nProduct evidence is useful [1]. Concept evidence agrees [3].\n"
    report, _, _ = _write_bundle(tmp_path, original, urls)

    resolved, detail = _resolve_native_citation_bundle(
        report,
        original,
        seal_check=verify_report_seal(report),
    )

    assert detail["status"] == "applied"
    assert detail["resolved_indices"] == [1, 3]
    assert detail["unresolved_indices"] == []
    assert detail["unused_native_mappings"] == 1
    assert "http://localhost:7770/used-one.html" in resolved
    assert "http://localhost:8090/content/wikipedia_en_all_nopic/A/Headphones" in resolved
    assert "unused-two" not in resolved
    assert resolved.count("## References") == 1
    assert report.read_text() == original, "scoring must not mutate the sealed report"

    citations = extract_citations(resolved, sandbox_only=False)
    assert [c.style for c in citations] == ["numbered", "numbered"]
    assert {c.raw_url for c in citations} == {
        "http://localhost:7770/used-one.html",
        "http://localhost:8090/content/wikipedia_en_all_nopic/A/Headphones",
    }
    spec = _markdown_spec_score(
        original,
        {"min_words": 0, "min_citations": 2, "min_paragraphs": 0},
        citation_md=resolved,
    )
    assert spec["citation_count"] == 2
    assert spec["word_count"] == _markdown_spec_score(original, {})["word_count"]


def test_storm_bundle_rejects_artifact_changed_after_manifest(tmp_path):
    original = "A supported claim [1].\n"
    report, sidecar, _ = _write_bundle(
        tmp_path,
        original,
        {"http://localhost:7770/product.html": 1},
    )
    sidecar.write_text(sidecar.read_text() + " ", encoding="utf-8")

    resolved, detail = _resolve_native_citation_bundle(
        report,
        original,
        seal_check=verify_report_seal(report),
    )

    assert resolved == original
    assert detail["status"] == "rejected"
    assert detail["reason"] == "artifact_size_or_sha_mismatch"


def test_storm_bundle_requires_verified_report_seal(tmp_path):
    original = "A supported claim [1].\n"
    report, _, meta = _write_bundle(
        tmp_path,
        original,
        {"http://localhost:7770/product.html": 1},
    )
    document = json.loads(meta.read_text())
    document.pop("report_seal")
    meta.write_text(json.dumps(document))

    resolved, detail = _resolve_native_citation_bundle(
        report,
        original,
        seal_check=verify_report_seal(report),
    )

    assert resolved == original
    assert detail["status"] == "rejected"
    assert detail["reason"] == "report_seal_not_verified"


def test_storm_bundle_does_not_duplicate_native_reference_definitions(tmp_path):
    url = "http://localhost:7770/product.html"
    original = f"A supported claim [1].\n\n## References\n\n[1] {url}\n"
    report, _, _ = _write_bundle(tmp_path, original, {url: 1})

    resolved, detail = _resolve_native_citation_bundle(
        report,
        original,
        seal_check=verify_report_seal(report),
    )

    assert resolved == original
    assert detail["status"] == "already_resolved"
    assert detail["appended_reference_definitions"] == 0


def test_storm_bundle_preserves_conflicting_public_url_but_native_index_wins(tmp_path):
    native_url = "http://localhost:9999/f/headphones/native-source"
    public_url = "https://www.reddit.com/r/headphones/fabricated"
    original = (
        "A claim grounded in STORM's native source [1].\n\n"
        "**Sources**\n"
        f"[1] {public_url}\n"
    )
    report, _, _ = _write_bundle(tmp_path, original, {native_url: 1})

    resolved, detail = _resolve_native_citation_bundle(
        report,
        original,
        seal_check=verify_report_seal(report),
    )

    assert detail["status"] == "applied"
    assert detail["matching_reference_definitions"] == []
    assert detail["conflicting_reference_definitions"] == [{
        "index": 1,
        "report_url": public_url,
        "native_url": native_url,
    }]
    assert f"[1] {native_url}" in resolved
    assert "[1] https://www.reddit.com" not in resolved
    assert public_url in resolved, "the fabricated URL must remain visible for penalty"
    citations = extract_citations(resolved, sandbox_only=False)
    assert {(citation.style, citation.raw_url) for citation in citations} == {
        ("numbered", native_url),
        ("bare", public_url),
    }
    assert report.read_text() == original


def test_storm_bundle_leaves_ambiguous_native_index_unresolved(tmp_path):
    original = "A claim with an ambiguous source [1].\n"
    report, _, _ = _write_bundle(
        tmp_path,
        original,
        {
            "http://localhost:7770/one.html": 1,
            "http://localhost:7770/other.html": 1,
        },
    )

    resolved, detail = _resolve_native_citation_bundle(
        report,
        original,
        seal_check=verify_report_seal(report),
    )

    assert resolved == original
    assert detail["status"] == "verified_unresolved"
    assert detail["ambiguous_indices"] == [1]
    assert detail["unresolved_indices"] == [1]
