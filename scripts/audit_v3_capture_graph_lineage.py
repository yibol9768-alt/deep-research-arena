#!/usr/bin/env python3
"""Verify that one v3 graph is built from the declared frozen capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


AUDIT_SCHEMA = "dra_v3_capture_graph_lineage_audit_v1"


class CaptureGraphLineageError(ValueError):
    """Raised when capture, inventory, and graph lineage is ambiguous."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CaptureGraphLineageError(f"{label}: cannot read {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise CaptureGraphLineageError(f"{label}: {path} must contain an object")
    return dict(value)


def _non_empty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptureGraphLineageError(f"{label}: expected a non-empty string")
    return value.strip()


def _sha256(path: Path, label: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CaptureGraphLineageError(f"{label}: cannot read {path}: {exc}") from exc


def _artifact_path(root: Path, value: object, label: str) -> Path:
    relative = Path(_non_empty(value, label))
    if relative.is_absolute() or ".." in relative.parts:
        raise CaptureGraphLineageError(f"{label}: path must stay under its root")
    return (root / relative).resolve()


def _capture_artifacts(
    capture_dir: Path, manifest: Mapping[str, Any]
) -> Counter[tuple[str, str]]:
    artifacts: Counter[tuple[str, str]] = Counter()
    searches = manifest.get("searches")
    documents = manifest.get("documents")
    if not isinstance(searches, list) or not isinstance(documents, list):
        raise CaptureGraphLineageError(
            "capture manifest searches and documents must be arrays"
        )
    for index, raw in enumerate(searches):
        if not isinstance(raw, Mapping):
            raise CaptureGraphLineageError(
                f"capture searches[{index}] must be an object"
            )
        path = _artifact_path(
            capture_dir, raw.get("response_path"), f"capture searches[{index}].response_path"
        )
        digest = _non_empty(
            raw.get("response_sha256"), f"capture searches[{index}].response_sha256"
        )
        if _sha256(path, f"capture search artifact[{index}]") != digest:
            raise CaptureGraphLineageError(
                f"capture searches[{index}] response hash mismatch"
            )
        artifacts[(path.as_posix(), digest)] += 1
    for index, raw in enumerate(documents):
        if not isinstance(raw, Mapping):
            raise CaptureGraphLineageError(
                f"capture documents[{index}] must be an object"
            )
        path = _artifact_path(
            capture_dir, raw.get("blob_path"), f"capture documents[{index}].blob_path"
        )
        digest = _non_empty(
            raw.get("content_sha256"), f"capture documents[{index}].content_sha256"
        )
        if _sha256(path, f"capture document artifact[{index}]") != digest:
            raise CaptureGraphLineageError(
                f"capture documents[{index}] content hash mismatch"
            )
        artifacts[(path.as_posix(), digest)] += 1
    return artifacts


def _inventory_capture_artifacts(
    inventory: Mapping[str, Any], blob_root: Path
) -> Counter[tuple[str, str]]:
    documents = inventory.get("documents")
    if not isinstance(documents, list):
        raise CaptureGraphLineageError("inventory documents must be an array")
    artifacts: Counter[tuple[str, str]] = Counter()
    for index, raw in enumerate(documents):
        if not isinstance(raw, Mapping):
            raise CaptureGraphLineageError(
                f"inventory documents[{index}] must be an object"
            )
        if raw.get("source_type") == "case_spec":
            continue
        path = _artifact_path(
            blob_root, raw.get("blob_path"), f"inventory documents[{index}].blob_path"
        )
        digest = _non_empty(
            raw.get("content_sha256"),
            f"inventory documents[{index}].content_sha256",
        )
        if _sha256(path, f"inventory document artifact[{index}]") != digest:
            raise CaptureGraphLineageError(
                f"inventory documents[{index}] content hash mismatch"
            )
        artifacts[(path.as_posix(), digest)] += 1
    return artifacts


def audit_capture_graph_lineage(
    *,
    capture_dir: Path,
    inventory_path: Path,
    graph_dir: Path,
    blob_root: Path,
) -> dict[str, Any]:
    capture_manifest_path = capture_dir / "capture_manifest.json"
    graph_manifest_path = graph_dir / "manifest.json"
    capture = _load_object(capture_manifest_path, "capture manifest")
    inventory = _load_object(inventory_path, "inventory")
    graph = _load_object(graph_manifest_path, "graph manifest")

    snapshots = {
        "capture_manifest": _non_empty(
            capture.get("corpus_snapshot"), "capture manifest corpus_snapshot"
        ),
        "inventory": _non_empty(
            inventory.get("corpus_snapshot"), "inventory corpus_snapshot"
        ),
        "graph_manifest": _non_empty(
            graph.get("corpus_snapshot"), "graph manifest corpus_snapshot"
        ),
    }
    snapshot_match = len(set(snapshots.values())) == 1
    capture_artifacts = _capture_artifacts(capture_dir.resolve(), capture)
    inventory_artifacts = _inventory_capture_artifacts(inventory, blob_root.resolve())
    missing_from_inventory = sorted((capture_artifacts - inventory_artifacts).elements())
    unexpected_in_inventory = sorted((inventory_artifacts - capture_artifacts).elements())
    artifact_set_match = not missing_from_inventory and not unexpected_in_inventory
    status = "passed" if snapshot_match and artifact_set_match else "failed"
    return {
        "schema": AUDIT_SCHEMA,
        "status": status,
        "snapshots": snapshots,
        "snapshot_match": snapshot_match,
        "capture_artifact_count": sum(capture_artifacts.values()),
        "inventory_capture_artifact_count": sum(inventory_artifacts.values()),
        "artifact_set_match": artifact_set_match,
        "missing_from_inventory": [
            {"path": path, "sha256": digest}
            for path, digest in missing_from_inventory
        ],
        "unexpected_in_inventory": [
            {"path": path, "sha256": digest}
            for path, digest in unexpected_in_inventory
        ],
        "capture_manifest_sha256": _sha256(
            capture_manifest_path, "capture manifest"
        ),
        "inventory_sha256": _sha256(inventory_path, "inventory"),
        "graph_manifest_sha256": _sha256(graph_manifest_path, "graph manifest"),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--graph-dir", type=Path, required=True)
    parser.add_argument("--blob-root", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = audit_capture_graph_lineage(
            capture_dir=args.capture_dir,
            inventory_path=args.inventory,
            graph_dir=args.graph_dir,
            blob_root=args.blob_root,
        )
        rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.out is None:
            sys.stdout.write(rendered)
        else:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(rendered, encoding="utf-8")
    except (OSError, UnicodeError, CaptureGraphLineageError) as exc:
        print(f"capture-graph lineage audit failed: {exc}", file=sys.stderr)
        return 2
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
