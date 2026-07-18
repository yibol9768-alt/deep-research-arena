#!/usr/bin/env python3
"""Compile a reviewed corpus inventory into a strict DRA v3 evidence graph."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval.evidence_graph import (  # noqa: E402
    EVIDENCE_GRAPH_VERSION,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceGraphError,
    EvidenceGraphFormatError,
    EvidenceNode,
    FrozenCorpusEntry,
    FrozenCorpusRegistry,
    SupportSpan,
    canonical_json_bytes,
    load_json,
    load_jsonl,
    save_graph,
    sha256_bytes,
    verify_evidence_graph_manifest,
)


INVENTORY_SCHEMA = "evidence_graph_inventory_v1"

HELP_EPILOG = r"""
Accepted inventory shapes
=========================

JSON object (recommended):

  {
    "schema_version": "evidence_graph_inventory_v1",
    "corpus_snapshot": "corpus-v3-pilot",
    "documents": [
      {
        "registry_id": "doc_wiki_001",
        "source_url": "http://localhost:8090/content/book/A/Noise_control",
        "source_type": "concept",
        "content_sha256": "<64 lowercase hex>",
        "blob_path": "blobs/noise-control.html",
        "in_corpus": true
      }
    ],
    "nodes": [
      {
        "evidence_id": "ev_noise_001",
        "node_type": "mechanism",
        "subject": "active noise control",
        "predicate": "attenuates",
        "object": "low-frequency noise",
        "source_url": "http://localhost:8090/content/book/A/Noise_control",
        "body_support": true,
        "search_snippet_support": false,
        "verifier": {"kind": "typed_claim", "tolerance": null}
      }
    ],
    "edges": [],
    "support_spans": [
      {"support_span_id": "span_001", "evidence_id": "ev_noise_001",
       "start": 1204, "end": 1338, "sha256": "<slice SHA-256>",
       "support_type": "body"}
    ]
  }

``source_type``, ``content_sha256`` and ``corpus_snapshot`` are copied from
the matching document into nodes. If supplied on a node, they must match
exactly. ``source_url`` is similarly copied into a top-level support span and
must match if supplied. Support offsets address raw bytes: start inclusive,
end exclusive. A node may alternatively contain a ``support_spans`` list;
the compiler flattens it and injects that node's evidence_id/source_url.

Every document must explicitly say ``in_corpus: true``. This is the frozen
registry/allowlist decision and is checked independently of ``blob_path``;
the existence of a blob alone never proves corpus membership. ``blob_path``
must be relative to --blob-root (or the inventory file's directory).

JSONL form uses the same flat records. It requires exactly one metadata line:

  {"record_type":"meta","schema_version":"evidence_graph_inventory_v1",
   "corpus_snapshot":"corpus-v3-pilot"}
  {"record_type":"document", ...document fields...}
  {"record_type":"node", ...node fields...}
  {"record_type":"edge", ...edge fields...}
  {"record_type":"support_span", ...support-span fields...}

Output consists of nodes.jsonl, edges.jsonl, support_spans.jsonl, the full
typed corpus_registry.json, and a manifest.json commit marker containing the
raw graph/registry hashes, readable stamps and counts. The registry includes
valid frozen documents that no graph node currently uses, allowing a later
scorer to distinguish a real but unused citation from a fabricated URL.
Records and JSON keys are canonically sorted, so equivalent inventories
produce byte-identical output; the manifest contains no timestamp or path.
Any unknown field, duplicate ID, unknown URL, dangling edge, non-member URL,
whole-content hash mismatch or span hash mismatch aborts the build before
graph files are written.
"""


def _expect_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceGraphFormatError(f"{path}: expected a JSON object")
    return dict(value)


def _expect_list(value: object, path: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise EvidenceGraphFormatError(f"{path}: expected a JSON array")
    return [_expect_object(item, f"{path}[{index}]") for index, item in enumerate(value)]


def _check_keys(
    raw: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str],
    path: str,
) -> None:
    keys = set(raw)
    missing = sorted(required - keys)
    unknown = sorted(keys - required - optional)
    if missing:
        raise EvidenceGraphFormatError(
            f"{path}: missing required fields: {', '.join(missing)}"
        )
    if unknown:
        raise EvidenceGraphFormatError(
            f"{path}: unknown fields: {', '.join(unknown)}"
        )


def _load_inventory_json(path: Path) -> dict[str, Any]:
    raw = _expect_object(load_json(path), str(path))
    _check_keys(
        raw,
        required={"schema_version", "corpus_snapshot", "documents", "nodes"},
        optional={"edges", "support_spans", "metadata"},
        path=str(path),
    )
    return {
        "schema_version": raw["schema_version"],
        "corpus_snapshot": raw["corpus_snapshot"],
        "documents": _expect_list(raw["documents"], "documents"),
        "nodes": _expect_list(raw["nodes"], "nodes"),
        "edges": _expect_list(raw.get("edges", []), "edges"),
        "support_spans": _expect_list(raw.get("support_spans", []), "support_spans"),
        "metadata": raw.get("metadata", {}),
    }


def _load_inventory_jsonl(path: Path) -> dict[str, Any]:
    records = load_jsonl(path)
    grouped: dict[str, list[dict[str, Any]]] = {
        "meta": [],
        "document": [],
        "node": [],
        "edge": [],
        "support_span": [],
    }
    for index, record in enumerate(records):
        record_type = record.get("record_type")
        if record_type not in grouped:
            raise EvidenceGraphFormatError(
                f"{path}:{index + 1}: unknown record_type {record_type!r}"
            )
        payload = dict(record)
        payload.pop("record_type")
        grouped[record_type].append(payload)  # type: ignore[index]
    if len(grouped["meta"]) != 1:
        raise EvidenceGraphFormatError(
            f"{path}: JSONL requires exactly one record_type='meta' line"
        )
    meta = grouped["meta"][0]
    _check_keys(
        meta,
        required={"schema_version", "corpus_snapshot"},
        optional={"metadata"},
        path=f"{path}:meta",
    )
    return {
        "schema_version": meta["schema_version"],
        "corpus_snapshot": meta["corpus_snapshot"],
        "documents": grouped["document"],
        "nodes": grouped["node"],
        "edges": grouped["edge"],
        "support_spans": grouped["support_span"],
        "metadata": meta.get("metadata", {}),
    }


def load_inventory(path: str | Path) -> dict[str, Any]:
    """Load either the documented JSON object or tagged JSONL inventory."""

    source = Path(path)
    if source.suffix.lower() == ".jsonl":
        inventory = _load_inventory_jsonl(source)
    else:
        inventory = _load_inventory_json(source)
    if inventory["schema_version"] != INVENTORY_SCHEMA:
        raise EvidenceGraphFormatError(
            f"schema_version: expected {INVENTORY_SCHEMA!r}, "
            f"got {inventory['schema_version']!r}"
        )
    if not isinstance(inventory["corpus_snapshot"], str):
        raise EvidenceGraphFormatError("corpus_snapshot: must be a string")
    return inventory


def _read_declared_blob(blob_root: Path, blob_path: object, path: str) -> bytes:
    if not isinstance(blob_path, str) or not blob_path:
        raise EvidenceGraphFormatError(f"{path}: blob_path must be a relative string")
    relative = Path(blob_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise EvidenceGraphFormatError(
            f"{path}: blob_path must stay within --blob-root and may not contain '..'"
        )
    root = blob_root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EvidenceGraphFormatError(f"{path}: blob_path escapes --blob-root") from exc
    try:
        return resolved.read_bytes()
    except OSError as exc:
        raise EvidenceGraphFormatError(f"{path}: cannot read blob {resolved}: {exc}") from exc


def _compile_documents(
    raw_documents: list[dict[str, Any]],
    *,
    corpus_snapshot: str,
    blob_root: Path,
) -> tuple[FrozenCorpusRegistry, dict[str, bytes]]:
    if not raw_documents:
        raise EvidenceGraphFormatError("documents: inventory must not be empty")
    entries: list[FrozenCorpusEntry] = []
    blobs: dict[str, bytes] = {}
    for index, raw_document in enumerate(raw_documents):
        path = f"documents[{index}]"
        _check_keys(
            raw_document,
            required={
                "registry_id",
                "source_url",
                "source_type",
                "content_sha256",
                "blob_path",
                "in_corpus",
            },
            optional={"corpus_snapshot", "metadata"},
            path=path,
        )
        if raw_document["in_corpus"] is not True:
            raise EvidenceGraphFormatError(
                f"{path}.in_corpus: must be explicitly true; false/unknown is not membership"
            )
        declared_snapshot = raw_document.get("corpus_snapshot", corpus_snapshot)
        if declared_snapshot != corpus_snapshot:
            raise EvidenceGraphFormatError(
                f"{path}.corpus_snapshot: does not match inventory snapshot"
            )
        entry = FrozenCorpusEntry.from_dict(
            {
                "registry_id": raw_document["registry_id"],
                "source_url": raw_document["source_url"],
                "source_type": raw_document["source_type"],
                "content_sha256": raw_document["content_sha256"],
                "corpus_snapshot": corpus_snapshot,
                "in_corpus": True,
                "metadata": raw_document.get("metadata", {}),
            }
        )
        blob = _read_declared_blob(blob_root, raw_document["blob_path"], f"{path}.blob_path")
        actual_hash = sha256_bytes(blob)
        if actual_hash != entry.content_sha256:
            raise EvidenceGraphFormatError(
                f"{path}.content_sha256: expected {entry.content_sha256}, "
                f"blob hashes to {actual_hash}"
            )
        if entry.source_url in blobs:
            raise EvidenceGraphFormatError(
                f"{path}.source_url: duplicate registry URL {entry.source_url!r}"
            )
        entries.append(entry)
        blobs[entry.source_url] = blob
    return FrozenCorpusRegistry(corpus_snapshot, tuple(entries)), blobs


def _fill_exact(raw: dict[str, Any], key: str, expected: object, path: str) -> None:
    if key in raw and raw[key] != expected:
        raise EvidenceGraphFormatError(
            f"{path}.{key}: {raw[key]!r} conflicts with registry value {expected!r}"
        )
    raw[key] = expected


def _exact_quote_offsets(blob: bytes, quote: bytes) -> list[int]:
    """Return every byte offset of ``quote``, including overlapping matches."""

    offsets: list[int] = []
    cursor = 0
    while True:
        offset = blob.find(quote, cursor)
        if offset < 0:
            return offsets
        offsets.append(offset)
        cursor = offset + 1


def _resolve_exact_quote_span(
    raw: dict[str, Any],
    *,
    blob: bytes,
    path: str,
) -> dict[str, Any]:
    """Compile a reviewable exact quote into frozen byte coordinates.

    Inventories may provide ``exact_quote`` instead of hand-calculated
    ``start``/``end``/``sha256``.  A quote must be unique unless the reviewer
    explicitly selects a zero-based ``occurrence``.  Any simultaneously
    supplied coordinates are checked for exact agreement rather than silently
    overwritten.
    """

    out = dict(raw)
    has_quote = "exact_quote" in out
    if not has_quote:
        if "occurrence" in out:
            raise EvidenceGraphFormatError(
                f"{path}.occurrence: requires exact_quote"
            )
        return out

    quote = out.pop("exact_quote")
    occurrence = out.pop("occurrence", None)
    if not isinstance(quote, str) or not quote:
        raise EvidenceGraphFormatError(
            f"{path}.exact_quote: must be a non-empty UTF-8 string"
        )
    if occurrence is not None and (type(occurrence) is not int or occurrence < 0):
        raise EvidenceGraphFormatError(
            f"{path}.occurrence: must be a non-negative integer"
        )

    quote_bytes = quote.encode("utf-8")
    offsets = _exact_quote_offsets(blob, quote_bytes)
    if not offsets:
        raise EvidenceGraphFormatError(
            f"{path}.exact_quote: quote is absent from the frozen blob"
        )
    if occurrence is None:
        if len(offsets) != 1:
            raise EvidenceGraphFormatError(
                f"{path}.exact_quote: quote occurs {len(offsets)} times; "
                "declare zero-based occurrence"
            )
        selected = offsets[0]
    else:
        if occurrence >= len(offsets):
            raise EvidenceGraphFormatError(
                f"{path}.occurrence: {occurrence} is out of range for "
                f"{len(offsets)} matches"
            )
        selected = offsets[occurrence]

    _fill_exact(out, "start", selected, path)
    _fill_exact(out, "end", selected + len(quote_bytes), path)
    _fill_exact(out, "sha256", sha256_bytes(quote_bytes), path)
    metadata = out.get("metadata", {})
    if not isinstance(metadata, dict):
        raise EvidenceGraphFormatError(f"{path}.metadata: must be an object")
    out["metadata"] = {
        **metadata,
        "offset_origin": "exact_quote_v1",
        "quote_occurrence": offsets.index(selected),
    }
    return out


def compile_inventory(
    inventory: Mapping[str, object],
    *,
    blob_root: str | Path,
) -> tuple[EvidenceGraph, FrozenCorpusRegistry, dict[str, bytes]]:
    """Compile an already-loaded inventory and perform full validation."""

    schema_version = inventory.get("schema_version")
    if schema_version != INVENTORY_SCHEMA:
        raise EvidenceGraphFormatError(
            f"schema_version: expected {INVENTORY_SCHEMA!r}, got {schema_version!r}"
        )
    corpus_snapshot = inventory.get("corpus_snapshot")
    if not isinstance(corpus_snapshot, str):
        raise EvidenceGraphFormatError("corpus_snapshot: must be a string")
    documents = _expect_list(inventory.get("documents"), "documents")
    raw_nodes = _expect_list(inventory.get("nodes"), "nodes")
    raw_edges = _expect_list(inventory.get("edges", []), "edges")
    raw_spans = _expect_list(inventory.get("support_spans", []), "support_spans")

    registry, blobs = _compile_documents(
        documents,
        corpus_snapshot=corpus_snapshot,
        blob_root=Path(blob_root),
    )
    registry_by_url = {entry.source_url: entry for entry in registry.entries}

    nodes: list[EvidenceNode] = []
    nested_spans: list[dict[str, Any]] = []
    for index, original in enumerate(raw_nodes):
        path = f"nodes[{index}]"
        raw = dict(original)
        embedded = raw.pop("support_spans", [])
        if not isinstance(embedded, list):
            raise EvidenceGraphFormatError(f"{path}.support_spans: must be an array")
        source_url = raw.get("source_url")
        if not isinstance(source_url, str) or source_url not in registry_by_url:
            raise EvidenceGraphFormatError(
                f"{path}.source_url: URL is not in the explicit frozen document registry"
            )
        entry = registry_by_url[source_url]
        _fill_exact(raw, "source_type", entry.source_type.value, path)
        _fill_exact(raw, "content_sha256", entry.content_sha256, path)
        _fill_exact(raw, "corpus_snapshot", entry.corpus_snapshot, path)
        node = EvidenceNode.from_dict(raw)
        nodes.append(node)
        for span_index, embedded_span in enumerate(embedded):
            if not isinstance(embedded_span, dict):
                raise EvidenceGraphFormatError(
                    f"{path}.support_spans[{span_index}]: expected an object"
                )
            span = dict(embedded_span)
            _fill_exact(span, "evidence_id", node.evidence_id, path)
            _fill_exact(span, "source_url", node.source_url, path)
            nested_spans.append(span)

    spans: list[SupportSpan] = []
    for index, original in enumerate([*raw_spans, *nested_spans]):
        path = f"support_spans[{index}]"
        raw = dict(original)
        evidence_id = raw.get("evidence_id", raw.get("node_id"))
        matching = next((node for node in nodes if node.evidence_id == evidence_id), None)
        if matching is None:
            # SupportSpan/graph validation will also reject this, but this
            # message makes a missing source_url impossible to misdiagnose.
            if "source_url" not in raw:
                raise EvidenceGraphFormatError(
                    f"{path}.evidence_id: unknown node {evidence_id!r}"
                )
        else:
            _fill_exact(raw, "source_url", matching.source_url, path)
            raw = _resolve_exact_quote_span(
                raw,
                blob=blobs[matching.source_url],
                path=path,
            )
        spans.append(SupportSpan.from_dict(raw))

    graph = EvidenceGraph(
        corpus_snapshot=corpus_snapshot,
        nodes=tuple(nodes),
        edges=tuple(EvidenceEdge.from_dict(raw) for raw in raw_edges),
        support_spans=tuple(spans),
        version=EVIDENCE_GRAPH_VERSION,
    )
    graph.validate(blob_loader=blobs, corpus_membership=registry)
    return graph, registry, blobs


def build_from_path(
    inventory_path: str | Path,
    output_dir: str | Path,
    *,
    blob_root: str | Path | None = None,
    validate_only: bool = False,
) -> dict[str, object]:
    """Compile a path, optionally write graph files, and return stable stamps."""

    source = Path(inventory_path)
    inventory = load_inventory(source)
    effective_blob_root = Path(blob_root) if blob_root is not None else source.parent
    graph, registry, blobs = compile_inventory(inventory, blob_root=effective_blob_root)
    if not validate_only:
        save_graph(
            graph,
            output_dir,
            blob_loader=blobs,
            corpus_membership=registry,
        )
        verify_evidence_graph_manifest(output_dir)
    return {
        "ok": True,
        "schema_version": INVENTORY_SCHEMA,
        "evidence_graph": EVIDENCE_GRAPH_VERSION,
        "corpus_snapshot": graph.corpus_snapshot,
        "registry_stamp": registry.corpus_stamp,
        "registry_sha256": registry.corpus_sha256,
        "corpus_stamp": graph.corpus_stamp,
        "corpus_sha256": graph.corpus_sha256,
        "graph_stamp": graph.graph_stamp,
        "evidence_graph_hash": graph.graph_sha256,
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "support_spans": len(graph.support_spans),
        "written": not validate_only,
        "output_dir": str(Path(output_dir)),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--inventory",
        required=True,
        type=Path,
        help="reviewed inventory in the JSON or tagged JSONL shape below",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="directory for graph JSONL, registry, and manifest artifacts",
    )
    parser.add_argument(
        "--blob-root",
        type=Path,
        default=None,
        help="base for relative blob_path values (default: inventory directory)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate and print stamps without writing graph files",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = build_from_path(
            args.inventory,
            args.out_dir,
            blob_root=args.blob_root,
            validate_only=args.validate_only,
        )
    except (EvidenceGraphError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes(summary).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
