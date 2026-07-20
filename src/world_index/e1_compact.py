"""Compact, task-blind World Index storage for E1 scale validation.

The row-oriented E1 schema is deliberately retained as a fidelity baseline.
This module stores each document's complete structural payload as a
deterministically compressed canonical artifact, uses integer document keys in
secondary indexes, and keeps FTS5 contentless.  It preserves the same public
render/search/round-trip behavior without paying one SQLite row and several
long-text indexes per block or link.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping
from urllib.parse import urljoin
import zlib

from .e1 import (
    AddResult,
    LOCATOR_VERSION,
    PARSER_VERSION,
    RENDERER_VERSION,
    canonical_json,
    document_title,
    normalize_text,
    parse_html_document,
    projection_roundtrip_failures,
    render_document_html,
    sha256_text,
    stable_id,
    _assign_offsets,
)


COMPACT_SCHEMA_VERSION = "dra_world_index_compact_v1"
COMPACT_SEARCH_VERSION = "sqlite-fts5-contentless-bm25-v1"
ARTIFACT_CODEC = "canonical-json-zlib-6-v1"


SCHEMA_SQL = """
PRAGMA foreign_keys=ON;
PRAGMA page_size=32768;
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
CREATE TABLE documents (
    doc_id INTEGER PRIMARY KEY,
    page_snapshot_id TEXT NOT NULL UNIQUE,
    pack_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    canonical_url TEXT NOT NULL UNIQUE,
    archive_entry_path TEXT,
    redirect_target TEXT,
    http_status INTEGER,
    source_family TEXT NOT NULL,
    page_type TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    mime_type TEXT,
    language TEXT,
    title TEXT,
    raw_content_hash TEXT NOT NULL,
    parsed_content_hash TEXT NOT NULL,
    rendered_content_hash TEXT NOT NULL,
    capture_or_archive_locator TEXT NOT NULL,
    rights_class TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    renderer_version TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    artifact_codec TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    artifact_blob BLOB NOT NULL,
    artifact_raw_bytes INTEGER NOT NULL,
    artifact_compressed_bytes INTEGER NOT NULL,
    body_chars INTEGER NOT NULL,
    block_count INTEGER NOT NULL,
    table_cell_count INTEGER NOT NULL,
    link_count INTEGER NOT NULL,
    structured_field_count INTEGER NOT NULL,
    interaction_count INTEGER NOT NULL,
    review_count INTEGER NOT NULL,
    reply_count INTEGER NOT NULL,
    invalid_block_offset_count INTEGER NOT NULL,
    orphan_interaction_parent_count INTEGER NOT NULL,
    empty_link_target_count INTEGER NOT NULL,
    empty_field_name_count INTEGER NOT NULL,
    search_content_hash TEXT NOT NULL,
    UNIQUE(pack_id, source_id)
);
CREATE TABLE aliases (
    normalized_alias TEXT NOT NULL,
    doc_id INTEGER NOT NULL REFERENCES documents(doc_id),
    alias_type TEXT NOT NULL,
    alias TEXT NOT NULL,
    PRIMARY KEY(normalized_alias, doc_id, alias_type)
) WITHOUT ROWID;
CREATE TABLE duplicate_clusters (
    content_hash TEXT NOT NULL,
    doc_id INTEGER NOT NULL REFERENCES documents(doc_id),
    cluster_size INTEGER NOT NULL,
    PRIMARY KEY(content_hash, doc_id)
) WITHOUT ROWID;
CREATE VIRTUAL TABLE search_fts USING fts5(
    title,
    aliases,
    body_text,
    content='',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE INDEX idx_documents_pack_type ON documents(pack_id, page_type);
CREATE INDEX idx_documents_parsed_hash ON documents(parsed_content_hash);
CREATE INDEX idx_aliases_doc ON aliases(doc_id);
"""


@dataclass
class PreparedRecord:
    record: dict[str, Any]
    page_snapshot_id: str
    title: str
    blocks: list[dict[str, Any]]
    links: list[dict[str, Any]]
    fields: list[dict[str, Any]]
    interactions: list[dict[str, Any]]
    body_text: str
    raw_hash: str
    parsed_hash: str
    rendered_hash: str
    artifact_json: str
    aliases: list[tuple[str, str]]
    search_text: str


def _prepare_record(
    raw_record: Mapping[str, Any], *, snapshot_id: str
) -> PreparedRecord:
    record = dict(raw_record)
    pack_id = str(record["pack_id"])
    source_id = str(record["source_id"])
    canonical_url = str(record["canonical_url"])
    page_snapshot_id = str(
        record.get("page_snapshot_id")
        or stable_id("ps", snapshot_id, pack_id, source_id)
    )

    blocks = [dict(block) for block in (record.get("blocks") or [])]
    links = [dict(link) for link in (record.get("links") or [])]
    parsed_title = ""
    if record.get("html_content"):
        parsed = parse_html_document(
            str(record["html_content"]), base_url=canonical_url
        )
        blocks = parsed["blocks"]
        links = parsed["links"]
        parsed_title = parsed["title"]
    _assign_offsets(blocks)
    title = document_title(
        record.get("title"),
        parsed_title=parsed_title,
        source_id=source_id,
        page_type=record.get("page_type"),
        archive_entry_path=record.get("archive_entry_path"),
    )
    fields = [
        dict(item) for item in (record.get("structured_fields") or [])
    ]
    interactions = [
        dict(item) for item in (record.get("interactions") or [])
    ]

    interaction_ids: dict[str, str] = {}
    for ordinal, interaction in enumerate(interactions):
        source_interaction_id = str(
            interaction.get("interaction_id")
            or interaction.get("source_id")
            or f"{interaction.get('kind', 'interaction')}:{ordinal}"
        )
        interaction["_source_interaction_id"] = source_interaction_id
        interaction_ids[source_interaction_id] = stable_id(
            "ix", page_snapshot_id, source_interaction_id
        )
    for ordinal, interaction in enumerate(interactions):
        source_interaction_id = interaction.pop("_source_interaction_id")
        source_parent_id = interaction.get("parent_interaction_id")
        interaction["interaction_id"] = interaction_ids[
            source_interaction_id
        ]
        interaction["parent_interaction_id"] = (
            interaction_ids.get(str(source_parent_id))
            if source_parent_id is not None
            else None
        )
        metadata = dict(interaction.get("metadata") or {})
        metadata.setdefault("source_interaction_id", source_interaction_id)
        if source_parent_id is not None:
            metadata.setdefault(
                "source_parent_interaction_id", str(source_parent_id)
            )
        interaction["metadata"] = metadata
        interaction.setdefault("ordinal", ordinal)

    blocks = [
        {
            "ordinal": ordinal,
            "block_type": str(block.get("block_type") or "paragraph"),
            "section_path": list(block.get("section_path") or []),
            "dom_path": block.get("dom_path"),
            "char_start": int(block.get("char_start") or 0),
            "char_end": int(block.get("char_end") or 0),
            "text": normalize_text(block.get("text")),
            "structural": dict(block.get("structural") or {}),
        }
        for ordinal, block in enumerate(blocks)
    ]
    links = [
        {
            "ordinal": ordinal,
            "href": str(
                link.get("href") or link.get("canonical_target") or ""
            ),
            "canonical_target": str(
                link.get("canonical_target")
                or urljoin(canonical_url, str(link.get("href") or ""))
            ),
            "anchor_text": normalize_text(link.get("anchor_text")),
            "dom_path": link.get("dom_path"),
        }
        for ordinal, link in enumerate(links)
    ]
    fields = [
        {
            "ordinal": ordinal,
            "name": normalize_text(field.get("name")),
            "value": normalize_text(field.get("value")),
            "unit": normalize_text(field.get("unit")),
            "field_type": field.get("field_type"),
            "provenance_locator": field.get("provenance_locator"),
            "metadata": dict(field.get("metadata") or {}),
        }
        for ordinal, field in enumerate(fields)
    ]
    interactions = [
        {
            "interaction_id": str(interaction["interaction_id"]),
            "parent_interaction_id": interaction.get(
                "parent_interaction_id"
            ),
            "kind": str(interaction.get("kind") or "interaction"),
            "ordinal": ordinal,
            "author_key": normalize_text(interaction.get("author_key")),
            "timestamp": interaction.get("timestamp"),
            "score": interaction.get("score"),
            "text": normalize_text(interaction.get("text")),
            "metadata": dict(interaction.get("metadata") or {}),
        }
        for ordinal, interaction in enumerate(interactions)
    ]

    body_parts = [
        normalize_text(block.get("text")) for block in blocks
        if normalize_text(block.get("text"))
    ]
    body_parts.extend(
        normalize_text(item.get("text")) for item in interactions
        if normalize_text(item.get("text"))
    )
    body_text = "\n".join(body_parts)
    normalized_record = {
        **record,
        "title": title,
        "blocks": blocks,
        "links": links,
        "interactions": interactions,
        "structured_fields": fields,
    }
    rendered_html = render_document_html(normalized_record)
    raw_hash = str(
        record.get("raw_content_hash")
        or sha256_text(canonical_json(record.get("raw") or record))
    )

    alias_pairs = {(title, "title"), (source_id, "source_id")}
    for alias in record.get("aliases") or []:
        if isinstance(alias, Mapping):
            alias_text = normalize_text(alias.get("value"))
            alias_type = str(alias.get("type") or "alias")
        else:
            alias_text = normalize_text(alias)
            alias_type = "alias"
        if (
            str(record.get("page_type") or "") == "wiki_resource"
            and alias_text.casefold() in {"null", "none", "undefined"}
        ):
            continue
        alias_pairs.add((alias_text, alias_type))
    aliases = sorted(
        (alias, alias_type)
        for alias, alias_type in alias_pairs if alias
    )
    field_text = " ".join(
        " ".join(filter(None, [
            normalize_text(field.get("name")),
            normalize_text(field.get("value")),
            normalize_text(field.get("unit")),
        ]))
        for field in fields
    )
    search_text = " ".join(
        part for part in (body_text, field_text) if part
    ).strip()
    artifact = {
        "blocks": blocks,
        "links": links,
        "structured_fields": fields,
        "interactions": interactions,
    }
    return PreparedRecord(
        record=record,
        page_snapshot_id=page_snapshot_id,
        title=title,
        blocks=blocks,
        links=links,
        fields=fields,
        interactions=interactions,
        body_text=body_text,
        raw_hash=raw_hash,
        parsed_hash=sha256_text(body_text),
        rendered_hash=sha256_text(rendered_html),
        artifact_json=canonical_json(artifact),
        aliases=aliases,
        search_text=search_text,
    )


class CompactWorldIndexWriter:
    """Write and audit a compact structural World Index."""

    def __init__(
        self, path: str | Path, *, snapshot_id: str,
        overwrite: bool = False,
    ):
        self.path = Path(path)
        if self.path.exists():
            if not overwrite:
                raise FileExistsError(self.path)
            self.path.unlink()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_id = snapshot_id
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=DELETE")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.executescript(SCHEMA_SQL)
        self.set_metadata("schema_version", COMPACT_SCHEMA_VERSION)
        self.set_metadata("snapshot_id", snapshot_id)
        self.set_metadata("parser_version", PARSER_VERSION)
        self.set_metadata("renderer_version", RENDERER_VERSION)
        self.set_metadata("search_version", COMPACT_SEARCH_VERSION)
        self.set_metadata("artifact_codec", ARTIFACT_CODEC)

    @classmethod
    def open_existing(
        cls, path: str | Path, *, snapshot_id: str
    ) -> "CompactWorldIndexWriter":
        """Open a checkpointed compact index without recreating its schema."""

        resolved = Path(path)
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        self = cls.__new__(cls)
        self.path = resolved
        self.snapshot_id = snapshot_id
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA synchronous=FULL")
        required = {
            "schema_version": COMPACT_SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "parser_version": PARSER_VERSION,
            "renderer_version": RENDERER_VERSION,
            "search_version": COMPACT_SEARCH_VERSION,
            "artifact_codec": ARTIFACT_CODEC,
        }
        for key, expected in required.items():
            observed = self.metadata_value(key)
            if observed != expected:
                self.conn.close()
                self.conn = None  # type: ignore[assignment]
                raise ValueError(
                    f"checkpoint metadata mismatch for {key}: "
                    f"{observed!r} != {expected!r}"
                )
        return self

    def close(self) -> None:
        if self.conn is not None:
            self.conn.commit()
            self.conn.close()
            self.conn = None  # type: ignore[assignment]

    def abort(self) -> None:
        """Roll back the uncheckpointed transaction and close the database."""

        if self.conn is not None:
            self.conn.rollback()
            self.conn.close()
            self.conn = None  # type: ignore[assignment]

    def set_metadata(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO metadata(key,value_json) VALUES (?,?)",
            (key, canonical_json(value)),
        )

    def metadata_value(self, key: str) -> Any:
        row = self.conn.execute(
            "SELECT value_json FROM metadata WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            raise KeyError(key)
        return json.loads(row[0])

    def commit_checkpoint(self, key: str, value: Any) -> None:
        """Commit pending records and their resume cursor atomically."""

        self.set_metadata(key, value)
        self.conn.commit()

    def add_record_atomic(
        self, raw_record: Mapping[str, Any]
    ) -> AddResult:
        if not self.conn.in_transaction:
            self.conn.execute("BEGIN")
        self.conn.execute("SAVEPOINT dra_add_compact_record")
        try:
            result = self.add_record(raw_record)
        except Exception:
            self.conn.execute("ROLLBACK TO SAVEPOINT dra_add_compact_record")
            self.conn.execute("RELEASE SAVEPOINT dra_add_compact_record")
            raise
        self.conn.execute("RELEASE SAVEPOINT dra_add_compact_record")
        return result

    def add_record(self, raw_record: Mapping[str, Any]) -> AddResult:
        prepared = _prepare_record(raw_record, snapshot_id=self.snapshot_id)
        record = prepared.record
        artifact_raw = prepared.artifact_json.encode("utf-8")
        artifact_blob = zlib.compress(artifact_raw, level=6)
        interaction_source_ids = {
            str((item.get("metadata") or {}).get("source_interaction_id"))
            for item in prepared.interactions
        }
        orphan_parents = sum(
            1 for item in prepared.interactions
            if (item.get("metadata") or {}).get(
                "source_parent_interaction_id"
            ) is not None
            and str((item.get("metadata") or {}).get(
                "source_parent_interaction_id"
            )) not in interaction_source_ids
        )
        invalid_offsets = sum(
            1 for block in prepared.blocks
            if int(block.get("char_start") or 0) < 0
            or int(block.get("char_end") or 0)
            < int(block.get("char_start") or 0)
            or int(block.get("char_end") or 0)
            - int(block.get("char_start") or 0)
            != len(normalize_text(block.get("text")))
        )
        empty_links = sum(
            1 for link in prepared.links
            if not str(
                link.get("canonical_target") or link.get("href") or ""
            ).strip()
        )
        empty_fields = sum(
            1 for field in prepared.fields
            if not normalize_text(field.get("name"))
        )
        alias_text = " ".join(alias for alias, _ in prepared.aliases)
        search_hash = sha256_text(
            canonical_json({
                "title": prepared.title,
                "aliases": alias_text,
                "body_text": prepared.search_text,
            })
        )
        cursor = self.conn.execute(
            """
            INSERT INTO documents(
              page_snapshot_id,pack_id,source_id,canonical_url,
              archive_entry_path,redirect_target,http_status,source_family,
              page_type,snapshot_id,mime_type,language,title,
              raw_content_hash,parsed_content_hash,rendered_content_hash,
              capture_or_archive_locator,rights_class,parser_version,
              renderer_version,metadata_json,artifact_codec,artifact_hash,
              artifact_blob,artifact_raw_bytes,artifact_compressed_bytes,
              body_chars,block_count,table_cell_count,link_count,
              structured_field_count,interaction_count,review_count,
              reply_count,
              invalid_block_offset_count,orphan_interaction_parent_count,
              empty_link_target_count,empty_field_name_count,
              search_content_hash
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                      ?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                prepared.page_snapshot_id,
                str(record["pack_id"]),
                str(record["source_id"]),
                str(record["canonical_url"]),
                record.get("archive_entry_path"),
                record.get("redirect_target"),
                record.get("http_status"),
                str(record.get("source_family") or record["pack_id"]),
                str(record.get("page_type") or "document"),
                self.snapshot_id,
                record.get("mime_type"),
                record.get("language"),
                prepared.title,
                prepared.raw_hash,
                prepared.parsed_hash,
                prepared.rendered_hash,
                str(record.get("capture_or_archive_locator")
                    or f"{record['pack_id']}:{record['source_id']}"),
                str(record.get("rights_class") or "frozen-benchmark-use"),
                PARSER_VERSION,
                RENDERER_VERSION,
                canonical_json(record.get("metadata") or {}),
                ARTIFACT_CODEC,
                sha256(artifact_raw).hexdigest(),
                artifact_blob,
                len(artifact_raw),
                len(artifact_blob),
                len(prepared.body_text),
                len(prepared.blocks),
                sum(1 for block in prepared.blocks
                    if block.get("block_type") == "table_cell"),
                len(prepared.links),
                len(prepared.fields),
                len(prepared.interactions),
                sum(1 for item in prepared.interactions
                    if item.get("kind") == "review"),
                sum(1 for item in prepared.interactions
                    if item.get("kind") == "reply"),
                invalid_offsets,
                orphan_parents,
                empty_links,
                empty_fields,
                search_hash,
            ),
        )
        doc_id = int(cursor.lastrowid)
        for alias, alias_type in prepared.aliases:
            self.conn.execute(
                "INSERT OR IGNORE INTO aliases("
                "normalized_alias,doc_id,alias_type,alias) VALUES (?,?,?,?)",
                (alias.casefold(), doc_id, alias_type, alias),
            )
        self.conn.execute(
            "INSERT INTO search_fts(rowid,title,aliases,body_text) "
            "VALUES (?,?,?,?)",
            (doc_id, prepared.title, alias_text, prepared.search_text),
        )
        return AddResult(
            page_snapshot_id=prepared.page_snapshot_id,
            canonical_url=str(record["canonical_url"]),
            block_count=len(prepared.blocks),
            link_count=len(prepared.links),
            structured_field_count=len(prepared.fields),
            interaction_count=len(prepared.interactions),
        )

    def finalize(self) -> None:
        self.conn.execute("DELETE FROM duplicate_clusters")
        self.conn.execute(
            """
            INSERT INTO duplicate_clusters(content_hash,doc_id,cluster_size)
            WITH duplicate_hashes AS (
              SELECT parsed_content_hash,COUNT(*) AS cluster_size
                FROM documents
               WHERE body_chars > 0
               GROUP BY parsed_content_hash
              HAVING COUNT(*) > 1
            )
            SELECT d.parsed_content_hash,d.doc_id,h.cluster_size
              FROM documents d JOIN duplicate_hashes h
                ON h.parsed_content_hash=d.parsed_content_hash
            """
        )
        self.conn.commit()

    def _artifact_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        raw = zlib.decompress(row["artifact_blob"])
        if len(raw) != row["artifact_raw_bytes"]:
            raise ValueError("artifact byte length mismatch")
        if sha256(raw).hexdigest() != row["artifact_hash"]:
            raise ValueError("artifact hash mismatch")
        return json.loads(raw.decode("utf-8"))

    def document_artifact(self, page_snapshot_id: str) -> dict[str, Any]:
        """Return the complete decoded artifact with derived stable IDs."""

        row = self.conn.execute(
            "SELECT * FROM documents WHERE page_snapshot_id=?",
            (page_snapshot_id,),
        ).fetchone()
        if row is None:
            raise KeyError(page_snapshot_id)
        artifact = self._artifact_from_row(row)
        for ordinal, block in enumerate(artifact["blocks"]):
            block.setdefault(
                "span_id", stable_id("span", page_snapshot_id, ordinal)
            )
            block.setdefault("ordinal", ordinal)
            block.setdefault("locator_version", LOCATOR_VERSION)
        for ordinal, link in enumerate(artifact["links"]):
            link.setdefault(
                "link_id", stable_id("link", page_snapshot_id, ordinal)
            )
            link.setdefault("ordinal", ordinal)
        return artifact

    def span_by_ordinal(
        self, page_snapshot_id: str, ordinal: int
    ) -> dict[str, Any]:
        artifact = self.document_artifact(page_snapshot_id)
        if ordinal < 0 or ordinal >= len(artifact["blocks"]):
            raise KeyError((page_snapshot_id, ordinal))
        return dict(artifact["blocks"][ordinal])

    def render_by_id(self, page_snapshot_id: str) -> str:
        row = self.conn.execute(
            "SELECT * FROM documents WHERE page_snapshot_id=?",
            (page_snapshot_id,),
        ).fetchone()
        if row is None:
            raise KeyError(page_snapshot_id)
        artifact = self._artifact_from_row(row)
        return render_document_html({
            "source_id": row["source_id"],
            "canonical_url": row["canonical_url"],
            "page_type": row["page_type"],
            "title": row["title"],
            "archive_entry_path": row["archive_entry_path"],
            "mime_type": row["mime_type"],
            "raw_content_hash": row["raw_content_hash"],
            "capture_or_archive_locator": row[
                "capture_or_archive_locator"
            ],
            "metadata": json.loads(row["metadata_json"]),
            **artifact,
        })

    def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT d.page_snapshot_id,d.canonical_url,d.title,
                   bm25(search_fts) AS score
              FROM search_fts f JOIN documents d ON d.doc_id=f.rowid
             WHERE search_fts MATCH ?
             ORDER BY score,d.page_snapshot_id
             LIMIT ?
            """,
            (query, limit),
        )
        return [dict(row) for row in rows]

    def census(self) -> dict[str, Any]:
        scalar = lambda sql: self.conn.execute(sql).fetchone()[0]
        return {
            "documents": scalar("SELECT COUNT(*) FROM documents"),
            "blocks": scalar("SELECT COALESCE(SUM(block_count),0) FROM documents"),
            "links": scalar("SELECT COALESCE(SUM(link_count),0) FROM documents"),
            "structured_fields": scalar(
                "SELECT COALESCE(SUM(structured_field_count),0) FROM documents"
            ),
            "interactions": scalar(
                "SELECT COALESCE(SUM(interaction_count),0) FROM documents"
            ),
            "aliases": scalar("SELECT COUNT(*) FROM aliases"),
            "duplicate_clusters": scalar(
                "SELECT COUNT(DISTINCT content_hash) FROM duplicate_clusters"
            ),
            "artifact_raw_bytes": scalar(
                "SELECT COALESCE(SUM(artifact_raw_bytes),0) FROM documents"
            ),
            "artifact_compressed_bytes": scalar(
                "SELECT COALESCE(SUM(artifact_compressed_bytes),0) FROM documents"
            ),
            "documents_by_pack": {
                row[0]: row[1] for row in self.conn.execute(
                    "SELECT pack_id,COUNT(*) FROM documents "
                    "GROUP BY pack_id ORDER BY pack_id"
                )
            },
            "documents_by_pack_and_type": {
                f"{row[0]}:{row[1]}": row[2]
                for row in self.conn.execute(
                    "SELECT pack_id,page_type,COUNT(*) FROM documents "
                    "GROUP BY pack_id,page_type ORDER BY pack_id,page_type"
                )
            },
        }

    def structural_audit(self, *, expected_documents: int) -> dict[str, Any]:
        checks = {
            "document_count_mismatch": abs(
                self.conn.execute(
                    "SELECT COUNT(*) FROM documents"
                ).fetchone()[0] - expected_documents
            ),
            "empty_evidence_documents": self.conn.execute(
                "SELECT COUNT(*) FROM documents WHERE page_type IN "
                "('product','forum_thread','wiki_article') AND body_chars=0"
            ).fetchone()[0],
            "invalid_block_offsets": self.conn.execute(
                "SELECT COALESCE(SUM(invalid_block_offset_count),0) "
                "FROM documents"
            ).fetchone()[0],
            "orphan_interaction_parents": self.conn.execute(
                "SELECT COALESCE(SUM(orphan_interaction_parent_count),0) "
                "FROM documents"
            ).fetchone()[0],
            "empty_link_targets": self.conn.execute(
                "SELECT COALESCE(SUM(empty_link_target_count),0) FROM documents"
            ).fetchone()[0],
            "empty_structured_field_names": self.conn.execute(
                "SELECT COALESCE(SUM(empty_field_name_count),0) FROM documents"
            ).fetchone()[0],
            "bad_raw_hashes": self.conn.execute(
                "SELECT COUNT(*) FROM documents "
                "WHERE length(raw_content_hash) NOT IN (64,71)"
            ).fetchone()[0],
            "artifact_size_mismatches": self.conn.execute(
                "SELECT COUNT(*) FROM documents "
                "WHERE length(artifact_blob) != artifact_compressed_bytes"
            ).fetchone()[0],
        }
        return {"checks": checks, "passed": all(v == 0 for v in checks.values())}

    def roundtrip_audit(
        self, page_ids: Iterable[str] | None = None
    ) -> dict[str, Any]:
        if page_ids is None:
            page_ids = [row[0] for row in self.conn.execute(
                "SELECT page_snapshot_id FROM documents "
                "ORDER BY page_snapshot_id"
            )]
        checked = 0
        failures: list[dict[str, Any]] = []
        for page_id in page_ids:
            row = self.conn.execute(
                "SELECT * FROM documents WHERE page_snapshot_id=?",
                (page_id,),
            ).fetchone()
            if row is None:
                failures.append({
                    "page_snapshot_id": page_id,
                    "reason": "missing_document",
                })
                continue
            try:
                artifact = self._artifact_from_row(row)
                rendered = self.render_by_id(page_id)
            except (ValueError, zlib.error, json.JSONDecodeError) as exc:
                failures.append({
                    "page_snapshot_id": page_id,
                    "reason": "artifact_decode_failure",
                    "error": repr(exc),
                })
                continue
            checked += 1
            if sha256_text(rendered) != row["rendered_content_hash"]:
                failures.append({
                    "page_snapshot_id": page_id,
                    "reason": "rendered_hash_mismatch",
                })
                continue
            projection_failures = projection_roundtrip_failures(
                rendered,
                canonical_url=row["canonical_url"],
                artifact=artifact,
            )
            failures.extend({
                "page_snapshot_id": page_id,
                **failure,
            } for failure in projection_failures)
        return {
            "checked": checked,
            "failed": len(failures),
            "passed": checked - len(failures),
            "failures": failures,
        }

    def logical_digest(
        self, *, exclude_metadata_keys: Iterable[str] = ()
    ) -> str:
        """Hash logical rows while optionally excluding operational metadata."""

        excluded_metadata = set(exclude_metadata_keys)
        digest = sha256()
        queries = [
            (
                "metadata",
                "SELECT key,value_json FROM metadata ORDER BY key,value_json",
            ),
            (
                "documents",
                "SELECT page_snapshot_id,pack_id,source_id,canonical_url,"
                "archive_entry_path,redirect_target,http_status,source_family,"
                "page_type,snapshot_id,mime_type,language,title,"
                "raw_content_hash,parsed_content_hash,rendered_content_hash,"
                "capture_or_archive_locator,rights_class,parser_version,"
                "renderer_version,metadata_json,artifact_codec,artifact_hash,"
                "artifact_raw_bytes,artifact_compressed_bytes,body_chars,"
                "block_count,table_cell_count,link_count,"
                "structured_field_count,interaction_count,review_count,"
                "reply_count,"
                "invalid_block_offset_count,orphan_interaction_parent_count,"
                "empty_link_target_count,empty_field_name_count,"
                "search_content_hash FROM documents ORDER BY page_snapshot_id",
            ),
            (
                "aliases",
                "SELECT a.normalized_alias,d.page_snapshot_id,a.alias_type,a.alias "
                "FROM aliases a JOIN documents d USING(doc_id) "
                "ORDER BY a.normalized_alias,d.page_snapshot_id,a.alias_type,a.alias",
            ),
            (
                "duplicate_clusters",
                "SELECT c.content_hash,d.page_snapshot_id,c.cluster_size "
                "FROM duplicate_clusters c JOIN documents d USING(doc_id) "
                "ORDER BY c.content_hash,d.page_snapshot_id,c.cluster_size",
            ),
        ]
        for label, query in queries:
            for row in self.conn.execute(query):
                if label == "metadata" and row[0] in excluded_metadata:
                    continue
                digest.update(label.encode("utf-8"))
                digest.update(b"\0")
                digest.update(canonical_json(list(row)).encode("utf-8"))
                digest.update(b"\n")
        return digest.hexdigest()
