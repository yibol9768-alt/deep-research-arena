from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from integrations.search_shim import app as app_module
from integrations.search_shim.backend import SearchHit
from scripts.capture_v3_candidate_sources import (
    CandidateCaptureError,
    run_capture,
    validate_capture_plan,
    verify_capture,
)


SOURCE_URL = "http://localhost:7770/headphone-x.html"


def _plan() -> dict[str, Any]:
    return {
        "schema_version": "dra_v3_candidate_capture_plan_v1",
        "candidate_id": "cand_audio_budget_split",
        "corpus_snapshot": "dra-v3-pilot-audio-budget-r1",
        "run_id": "v3-corpus-audio-budget-r1",
        "searches": [
            {
                "search_id": "shopping-over-ear",
                "query": "noise cancelling over ear office",
                "max_results": 5,
                "include_domains": ["localhost:7770"],
                "required_urls": [SOURCE_URL],
            }
        ],
        "extracts": [
            {
                "registry_id": "reg_headphone_x",
                "source_type": "magento",
                "url": SOURCE_URL,
                "extract_depth": "advanced",
            }
        ],
        "source_identity": {"shopping_image": "sha256:test-shopping"},
        "metadata": {"authority": "test"},
    }


def test_atomic_candidate_capture_records_search_fetch_and_blob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    body = "Headphone X\n\nIn stock $199.95\n\nOver-ear adaptive ANC."
    seen: dict[str, Any] = {}

    def _fake_search(
        query: str, *, max_results: int = 10, **_kw: Any
    ) -> list[SearchHit]:
        assert query == "noise cancelling over ear office"
        return [
            SearchHit(
                url=SOURCE_URL,
                title="Headphone X",
                content="Over-ear ANC, $199.95",
                score=1.0,
                source="shopping",
            )
        ][:max_results]

    def _fake_extract(
        urls: Any, *, extract_depth: str = "basic"
    ) -> list[dict[str, Any]]:
        seen["extract_depth"] = extract_depth
        url = list(urls)[0]
        return [
            {
                "url": url,
                "raw_content": body,
                "title": "Headphone X",
                "source": "shopping",
                "status": 200,
                "links": ["http://localhost:7770/manual.html"],
            }
        ]

    monkeypatch.setattr(app_module, "search", _fake_search)
    monkeypatch.setattr(app_module, "extract", _fake_extract)
    output = tmp_path / "capture"
    manifest = run_capture(_plan(), output, app_override=app_module.app)

    assert seen["extract_depth"] == "advanced"
    assert manifest["status"] == "complete"
    assert manifest["counts"]["searches"] == 1
    assert manifest["counts"]["documents"] == 1

    digest = hashlib.sha256(body.encode()).hexdigest()
    assert (output / "blobs" / digest).read_text(encoding="utf-8") == body
    documents = json.loads((output / "documents.json").read_text(encoding="utf-8"))
    assert documents["documents"][0]["content_sha256"] == digest
    assert documents["documents"][0]["extract_depth"] == "advanced"

    observations = [
        json.loads(line)
        for line in (output / "observations_legacy.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [row["kind"] for row in observations] == [
        "mark",
        "search",
        "fetch",
        "mark",
    ]
    assert observations[0]["phase"] == "start"
    assert observations[-1]["phase"] == "end"
    assert observations[2]["body_sha256"] == digest

    files = json.loads((output / "capture_files.json").read_text(encoding="utf-8"))
    paths = {row["path"] for row in files["files"]}
    assert "capture_manifest.json" in paths
    assert "observations_legacy.jsonl" in paths
    assert "capture_files.json" not in paths
    verified = verify_capture(output)
    assert verified["status"] == "verified"
    assert verified["documents"] == 1
    assert verified["searches"] == 1

    (output / "blobs" / digest).write_text(body + "tampered", encoding="utf-8")
    with pytest.raises(CandidateCaptureError, match="SHA-256 mismatch"):
        verify_capture(output)


def test_capture_fails_closed_when_required_search_result_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _fake_search(_query: str, **_kw: Any) -> list[SearchHit]:
        return [
            SearchHit(
                url="http://localhost:7770/different.html",
                title="Different",
                content="not the required page",
                score=1.0,
                source="shopping",
            )
        ]

    monkeypatch.setattr(app_module, "search", _fake_search)
    output = tmp_path / "capture"
    with pytest.raises(CandidateCaptureError, match="required URLs missing"):
        run_capture(_plan(), output, app_override=app_module.app)
    assert not output.exists()


def test_capture_discovery_preflight_reports_every_missing_search(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _plan()
    plan["searches"].append(
        {
            "search_id": "forum-second-source",
            "query": "second missing source",
            "max_results": 5,
            "include_domains": ["localhost:9999"],
            "required_urls": ["http://localhost:9999/f/test/123/source"],
        }
    )

    def _fake_search(query: str, **_kw: Any) -> list[SearchHit]:
        return [
            SearchHit(
                url=f"http://localhost:7770/not-required-{query.replace(' ', '-')}",
                title="Different",
                content="not the required page",
                score=1.0,
                source="shopping",
            )
        ]

    monkeypatch.setattr(app_module, "search", _fake_search)
    output = tmp_path / "capture"
    with pytest.raises(CandidateCaptureError) as exc_info:
        run_capture(plan, output, app_override=app_module.app)

    message = str(exc_info.value)
    assert "shopping-over-ear" in message
    assert "forum-second-source" in message
    assert SOURCE_URL in message
    assert "http://localhost:9999/f/test/123/source" in message
    assert not output.exists()


def test_capture_plan_rejects_schema_drift_and_existing_output(tmp_path: Path) -> None:
    invalid = _plan()
    invalid["unexpected"] = True
    with pytest.raises(CandidateCaptureError, match="schema mismatch"):
        validate_capture_plan(invalid)

    output = tmp_path / "capture"
    output.mkdir()
    with pytest.raises(CandidateCaptureError, match="output already exists"):
        run_capture(_plan(), output, app_override=app_module.app)
