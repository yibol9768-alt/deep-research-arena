from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.audit_v3_capture_graph_lineage import audit_capture_graph_lineage


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path, *, inventory_snapshot: str = "snapshot-one") -> tuple[Path, Path, Path]:
    capture = tmp_path / "capture"
    graph = tmp_path / "graph"
    search_path = capture / "searches" / "001-search.json"
    blob_path = capture / "blobs" / "document"
    _write_json(search_path, {"results": [{"url": "http://source"}]})
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_text("document body", encoding="utf-8")
    _write_json(
        capture / "capture_manifest.json",
        {
            "corpus_snapshot": "snapshot-one",
            "searches": [
                {
                    "response_path": "searches/001-search.json",
                    "response_sha256": _sha256(search_path),
                }
            ],
            "documents": [
                {
                    "blob_path": "blobs/document",
                    "content_sha256": _sha256(blob_path),
                }
            ],
        },
    )
    inventory = tmp_path / "inventory.json"
    _write_json(
        inventory,
        {
            "corpus_snapshot": inventory_snapshot,
            "documents": [
                {
                    "source_type": "search_result",
                    "blob_path": search_path.relative_to(tmp_path).as_posix(),
                    "content_sha256": _sha256(search_path),
                },
                {
                    "source_type": "magento",
                    "blob_path": blob_path.relative_to(tmp_path).as_posix(),
                    "content_sha256": _sha256(blob_path),
                },
                {
                    "source_type": "case_spec",
                    "blob_path": "case-spec.json",
                    "content_sha256": "0" * 64,
                },
            ],
        },
    )
    _write_json(graph / "manifest.json", {"corpus_snapshot": "snapshot-one"})
    return capture, inventory, graph


def test_capture_graph_lineage_accepts_exact_snapshot_and_artifacts(
    tmp_path: Path,
) -> None:
    capture, inventory, graph = _fixture(tmp_path)

    result = audit_capture_graph_lineage(
        capture_dir=capture,
        inventory_path=inventory,
        graph_dir=graph,
        blob_root=tmp_path,
    )

    assert result["status"] == "passed"
    assert result["snapshot_match"] is True
    assert result["artifact_set_match"] is True
    assert result["capture_artifact_count"] == 2


def test_capture_graph_lineage_rejects_run_id_used_as_snapshot(
    tmp_path: Path,
) -> None:
    capture, inventory, graph = _fixture(
        tmp_path, inventory_snapshot="run-id-not-corpus-snapshot"
    )

    result = audit_capture_graph_lineage(
        capture_dir=capture,
        inventory_path=inventory,
        graph_dir=graph,
        blob_root=tmp_path,
    )

    assert result["status"] == "failed"
    assert result["snapshot_match"] is False
    assert result["artifact_set_match"] is True
