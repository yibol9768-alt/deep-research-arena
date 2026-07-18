from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_v3_review_packet import build_review_packet, verify_review_packet
from src.eval.evidence_graph import EvidenceGraphFormatError


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data/evidence_graph/dra-v3-pilot-my5090-20260715-r2"
INVENTORY = SNAPSHOT / "inventory.json"
TRANSLATIONS = (
    ROOT
    / "data/pilot_v3/review_translations"
    / "cand_audio_glasses_flight.zh-CN.json"
)


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_review_packet_renders_exact_frozen_context_and_blank_decisions(
    tmp_path: Path,
) -> None:
    summary = build_review_packet(
        INVENTORY,
        tmp_path,
        snapshot_root=SNAPSHOT,
    )
    assert summary["counts"] == {
        "review_items": 28,
        "semantic_items": 18,
        "structured_items": 10,
        "support_items": 0,
        "support_spans": 28,
        "sources": 14,
        "evidence_gaps": 3,
    }
    assert summary["verified_files"] == 17

    queue = _json(tmp_path / "review_queue.json")
    assert queue["review_policy"] == {
        "frozen_bytes_are_authoritative": True,
        "live_page_may_override_snapshot": False,
        "review_does_not_auto_promote": True,
        "semantic_claims_require_scope_review": True,
        "structured_claims_require_span_review": True,
    }
    glasses = next(
        item
        for item in queue["items"]
        if item["review_item_id"] == "assert_forum_glasses_pain"
    )
    assert glasses["support_spans"][0]["exact_text"].startswith(
        "I wear reading glasses"
    )
    assert glasses["proposed_propositions"][0]["evidence_id"] == (
        "prop_forum_glasses_pain"
    )
    assert glasses["metadata"]["scope"] == "single_user_report"

    decisions = _json(tmp_path / "review_decisions.template.json")
    assert decisions["candidate_verdict"] == "pending"
    assert decisions["reviewer_id"] == ""
    assert all(item["decision"] == "pending" for item in decisions["items"])
    assert all(
        gap["resolution"] == "unresolved" for gap in decisions["evidence_gaps"]
    )

    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "以本页展示的英文冻结 bytes 为准" in page
    assert "实时网页只能核对来源身份，不能覆盖冻结快照" in page
    assert "No captured source directly states that eyeglass temples" in page
    assert "导出审核 JSON" in page
    assert "JSON.stringify(output, null, 2) + '\\n'" in page


def test_review_packet_copies_byte_identical_source_snapshots(tmp_path: Path) -> None:
    build_review_packet(INVENTORY, tmp_path, snapshot_root=SNAPSHOT)
    queue = _json(tmp_path / "review_queue.json")
    assert len(queue["sources"]) == 14
    for source in queue["sources"]:
        content = (tmp_path / source["raw_snapshot_path"]).read_bytes()
        assert len(content) == source["bytes"]
        assert hashlib.sha256(content).hexdigest() == source["content_sha256"]


def test_review_packet_renders_complete_chinese_aid_without_replacing_original(
    tmp_path: Path,
) -> None:
    summary = build_review_packet(
        INVENTORY,
        tmp_path,
        snapshot_root=SNAPSHOT,
        translations_path=TRANSLATIONS,
    )
    assert summary["verified_files"] == 18
    queue = _json(tmp_path / "review_queue.json")
    assert queue["translation"]["authority"] == "translation_aid_only"
    assert queue["translation"]["language"] == "zh-CN"
    assert all("translation_zh" in item for item in queue["items"])

    seal = next(
        item
        for item in queue["items"]
        if item["review_item_id"] == "assert_over_ear_seal"
    )
    assert seal["translation_zh"]["claim_zh"]["object"].startswith("包耳式耳机")
    assert seal["support_spans"][0]["exact_text"].startswith(
        "Because these headphones"
    )
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert page.count("中文标注辅助（非证据）") == 28
    assert "中文是理解辅助，不是独立证据" in page
    assert "眼镜腿会削弱包耳式耳机的声学密封" in page
    assert "Because these headphones completely surround the ear" in page
    assert (tmp_path / "translations.zh-CN.json").read_bytes() == (
        TRANSLATIONS.read_bytes()
    )


def test_review_packet_build_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_summary = build_review_packet(INVENTORY, first, snapshot_root=SNAPSHOT)
    second_summary = build_review_packet(INVENTORY, second, snapshot_root=SNAPSHOT)
    assert first_summary["manifest_sha256"] == second_summary["manifest_sha256"]

    first_files = sorted(
        path.relative_to(first).as_posix()
        for path in first.rglob("*")
        if path.is_file()
    )
    second_files = sorted(
        path.relative_to(second).as_posix()
        for path in second.rglob("*")
        if path.is_file()
    )
    assert first_files == second_files
    for relative in first_files:
        assert (first / relative).read_bytes() == (second / relative).read_bytes()


def test_review_packet_manifest_rejects_tampered_snapshot(tmp_path: Path) -> None:
    build_review_packet(INVENTORY, tmp_path, snapshot_root=SNAPSHOT)
    manifest = _json(tmp_path / "manifest.json")
    source_record = next(
        record for record in manifest["files"] if record["path"].startswith("sources/")
    )
    source = tmp_path / source_record["path"]
    source.write_bytes(source.read_bytes() + b"tampered")
    with pytest.raises(EvidenceGraphFormatError, match="byte length mismatch"):
        verify_review_packet(tmp_path)
