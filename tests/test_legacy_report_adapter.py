from __future__ import annotations

import json
from pathlib import Path

from src.scoring.legacy_report_adapter import (
    adapt_legacy_run,
    documents_from_observation_ledger,
)


def test_numbered_sources_are_projected_without_inference(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text(
        "The product costs $10 [1]. Missing source [2].\n\n"
        "### Sources\n"
        "[1] Product: http://localhost:7770/product.html\n",
        encoding="utf-8",
    )
    ledger = tmp_path / "observation-ledger.json"
    (tmp_path / "blobs").mkdir()
    body = "Product\nPrice $10"
    digest = "a" * 64
    (tmp_path / "blobs" / digest).write_text(body, encoding="utf-8")
    ledger.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_type": "fetch_body",
                        "http_status": 200,
                        "observable": True,
                        "canonical_url": "http://localhost:7770/product.html",
                        "content_text_or_blob_ref": {"blob_ref": digest},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = adapt_legacy_run(
        report_path=report,
        observation_ledger_path=ledger,
        output_dir=tmp_path / "adapted",
    )
    normalized = result["report"].read_text(encoding="utf-8")
    assert '<cite id="legacyobs-0">[1]</cite>' in normalized
    assert "Missing source [2]." in normalized
    assert "[1] Product: http://localhost:7770/product.html" in normalized
    manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
    assert manifest["semantic_inference_used"] is False
    assert manifest["observed_citation_id_count"] == 1


def test_explicit_unobserved_markdown_link_stays_unobserved(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text(
        "Claim [source](https://example.com/source).\n",
        encoding="utf-8",
    )
    sources = tmp_path / "sources.json"
    sources.write_text("[]", encoding="utf-8")

    result = adapt_legacy_run(
        report_path=report,
        sources_path=sources,
        output_dir=tmp_path / "adapted",
    )
    citation_map = json.loads(result["citation_map"].read_text(encoding="utf-8"))
    assert len(citation_map) == 1
    assert citation_map[0]["url"] == "https://example.com/source"
    assert citation_map[0]["adapter_status"] == "explicit_but_unobserved"
    assert citation_map[0]["evidence_id"].startswith("legacy-unobserved-")


def test_search_endpoint_body_is_not_promoted_to_full_page(tmp_path: Path) -> None:
    (tmp_path / "blobs").mkdir()
    digest = "b" * 64
    (tmp_path / "blobs" / digest).write_text(
        "Short search snippet",
        encoding="utf-8",
    )
    ledger = tmp_path / "observation-ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_type": "fetch_body",
                        "http_status": 200,
                        "observable": True,
                        "canonical_url": "http://localhost:7770/product.html",
                        "content_text_or_blob_ref": {"blob_ref": digest},
                        "metadata": {"endpoint": "/search"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    documents = documents_from_observation_ledger(ledger)
    assert documents[0]["observation_tier"] == "search_snippet"
    assert documents[0]["raw_content"] == ""


def test_multi_number_source_header_with_following_url_is_projected(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.md"
    report.write_text(
        "The listing states 12-hour playtime [1] and the repeated source "
        "supports the same listing [23].\n\n"
        "## Sources\n\n"
        "[1, 23, 33] Soundcore Flare 2 (source nr: 1, 23, 33)\n"
        "   URL: http://localhost:7770/flare2.html\n",
        encoding="utf-8",
    )
    sources = tmp_path / "sources.json"
    sources.write_text(
        json.dumps(
            [
                {
                    "url": "http://localhost:7770/flare2.html",
                    "title": "Soundcore Flare 2",
                    "raw_content": "12-hour playtime",
                    "observation_tier": "full_page",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = adapt_legacy_run(
        report_path=report,
        sources_path=sources,
        output_dir=tmp_path / "adapted",
    )
    normalized = result["report"].read_text(encoding="utf-8")
    assert '<cite id="legacyobs-0">[1]</cite>' in normalized
    assert '<cite id="legacyobs-0">[23]</cite>' in normalized
    assert "[1, 23, 33] Soundcore Flare 2" in normalized
    assert "<cite" not in normalized.split("## Sources", 1)[1]


def test_bare_sandbox_url_is_an_explicit_citation(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text(
        "Source: `http://localhost:7770/product.html`\n",
        encoding="utf-8",
    )
    sources = tmp_path / "sources.json"
    sources.write_text(
        json.dumps(
            [
                {
                    "url": "http://localhost:7770/product.html",
                    "raw_content": "Product page",
                    "observation_tier": "full_page",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = adapt_legacy_run(
        report_path=report,
        sources_path=sources,
        output_dir=tmp_path / "adapted",
    )
    normalized = result["report"].read_text(encoding="utf-8")
    assert (
        '`<cite id="legacyobs-0">'
        "http://localhost:7770/product.html</cite>`"
    ) in normalized
