from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

from src.world_index.e1 import (
    WorldIndexWriter,
    canonical_json,
    document_title,
    parse_html_document,
    projection_roundtrip_failures,
    render_document_html,
    stable_id,
    stable_bucket,
    write_jsonl,
)
from src.world_index.e1_compact import CompactWorldIndexWriter
from scripts.export_e1_shard_sources import (
    html_soft_redirect,
    wiki_served_path,
)
from scripts.serve_e1_world_shard import open_writer
from scripts.render_e1_manual_audit_packet import (
    projection_structure_failures,
)
from scripts.create_e1_manual_audit_queue import queue_definition_id
from scripts.verify_e1_reproducibility import canonical_sqlite_sha256
from scripts.compile_e2_wikimedia_backbone import (
    CHECKPOINT_KEY,
    initial_checkpoint,
    nested_view_contracts,
    selected_for_view,
    view_contract,
)
from scripts.export_e1_shard_sources import build_wikimedia_record


def _records():
    return [
        {
            "pack_id": "commerce-test",
            "source_id": "42",
            "canonical_url": "http://localhost:7770/example.html",
            "source_family": "shop",
            "page_type": "product",
            "title": "Example Speaker 40W",
            "mime_type": "text/html",
            "raw_content_hash": "a" * 64,
            "capture_or_archive_locator": "fixture:product:42",
            "blocks": [
                {
                    "block_type": "paragraph",
                    "section_path": ["Description"],
                    "dom_path": "/main/p[1]",
                    "text": "Portable speaker with a passive radiator.",
                    "structural": {},
                }
            ],
            "structured_fields": [
                {"name": "price", "value": "49.99", "unit": "USD"}
            ],
            "interactions": [
                {
                    "interaction_id": "review:1",
                    "kind": "review",
                    "author_key": "author_a",
                    "timestamp": "2026-01-01",
                    "score": 80,
                    "text": "Battery life was good on a long trip.",
                }
            ],
            "aliases": ["SKU-42"],
            "links": [
                {
                    "href": "/other.html",
                    "canonical_target": "http://localhost:7770/other.html",
                    "anchor_text": "Other",
                }
            ],
        },
        {
            "pack_id": "community-test",
            "source_id": "7",
            "canonical_url": "http://localhost:9999/f/audio/7",
            "source_family": "community",
            "page_type": "forum_thread",
            "title": "Speaker field report",
            "mime_type": "text/html",
            "raw_content_hash": "b" * 64,
            "capture_or_archive_locator": "fixture:thread:7",
            "blocks": [
                {
                    "block_type": "post",
                    "section_path": ["Post"],
                    "dom_path": "/main/article[1]",
                    "text": "The seal failed after rain.",
                    "structural": {},
                }
            ],
            "interactions": [
                {
                    "interaction_id": "post:7",
                    "kind": "post",
                    "author_key": "author_b",
                    "timestamp": "2026-01-02",
                    "score": 5,
                    "text": "The seal failed after rain.",
                },
                {
                    "interaction_id": "comment:8",
                    "parent_interaction_id": "post:7",
                    "kind": "reply",
                    "author_key": "author_c",
                    "timestamp": "2026-01-03",
                    "score": 2,
                    "text": "Mine survived a splash.",
                },
            ],
            "structured_fields": [],
            "links": [],
        },
    ]


def test_canonical_sqlite_hash_ignores_only_transaction_header_state(
    tmp_path,
):
    first = tmp_path / "first.sqlite"
    second = tmp_path / "second.sqlite"
    connection = sqlite3.connect(first)
    connection.execute("CREATE TABLE example(value TEXT)")
    connection.execute("INSERT INTO example VALUES ('same content')")
    connection.commit()
    connection.close()
    shutil.copyfile(first, second)

    with second.open("r+b") as handle:
        handle.seek(24)
        handle.write((123).to_bytes(4, "big"))
        handle.seek(92)
        handle.write((123).to_bytes(4, "big"))

    assert sha256(first.read_bytes()).hexdigest() != sha256(
        second.read_bytes()
    ).hexdigest()
    assert canonical_sqlite_sha256(first) == canonical_sqlite_sha256(
        second
    )

    with second.open("r+b") as handle:
        handle.seek(101)
        original = handle.read(1)
        handle.seek(101)
        handle.write(bytes([original[0] ^ 1]))
    assert canonical_sqlite_sha256(first) != canonical_sqlite_sha256(
        second
    )


def _build(path, records):
    writer = WorldIndexWriter(path, snapshot_id="world-test", overwrite=True)
    for record in records:
        writer.add_record(record)
    writer.finalize()
    digest = writer.logical_digest()
    audit = writer.roundtrip_audit()
    return writer, digest, audit


def test_stable_bucket_is_reproducible_and_pack_scoped():
    first = stable_bucket("world", "pack-a", "doc-1")
    assert first == stable_bucket("world", "pack-a", "doc-1")
    assert 0 <= first < 100
    assert stable_bucket("world", "pack-a", "doc-1", modulus=7) < 7
    assert stable_bucket("world", "pack-a", "doc-1") != stable_bucket(
        "world", "pack-b", "doc-1"
    )


def test_e2_rank_views_are_nested_and_task_blind():
    population = 19_551_505
    contracts = nested_view_contracts(population)
    assert contracts["w100k"]["rank_threshold_exclusive"] < (
        contracts["w1m"]["rank_threshold_exclusive"]
    )
    assert contracts["w1m"]["rank_threshold_exclusive"] < (
        contracts["wfull"]["rank_threshold_exclusive"]
    )
    w100k = view_contract("w100k", population)
    w1m = view_contract("w1m", population)
    wfull = view_contract("wfull", population)
    observed_100k = 0
    observed_1m = 0
    for index in range(20_000):
        source_id = f"A/example_{index}"
        in_100k = selected_for_view(
            snapshot_id="world",
            source_id=source_id,
            contract=w100k,
        )
        in_1m = selected_for_view(
            snapshot_id="world",
            source_id=source_id,
            contract=w1m,
        )
        in_full = selected_for_view(
            snapshot_id="world",
            source_id=source_id,
            contract=wfull,
        )
        assert not in_100k or in_1m
        assert not in_1m or in_full
        observed_100k += int(in_100k)
        observed_1m += int(in_1m)
    assert 50 <= observed_100k <= 160
    assert 800 <= observed_1m <= 1_300


class _FakeWikiItem:
    def __init__(self, content: bytes, mimetype: str):
        self.content = content
        self.mimetype = mimetype
        self.size = len(content)


class _FakeWikiEntry:
    def __init__(
        self,
        *,
        path: str,
        title: str | None,
        item: _FakeWikiItem | None = None,
        redirect: "_FakeWikiEntry | None" = None,
    ):
        self.path = path
        self.title = title
        self.is_redirect = redirect is not None
        self._item = item
        self._redirect = redirect

    def get_item(self):
        assert self._item is not None
        return self._item

    def get_redirect_entry(self):
        assert self._redirect is not None
        return self._redirect


class _FakeWikiArchive:
    uuid = "fixture-zim"


def test_shared_wikimedia_record_builder_preserves_page_roles():
    archive = _FakeWikiArchive()
    article = _FakeWikiEntry(
        path="A/Example",
        title="Example",
        item=_FakeWikiItem(
            b"<html><body><table><tr><td></td><td>x</td></tr></table>"
            b"</body></html>",
            "text/html",
        ),
    )
    built_article = build_wikimedia_record(
        archive, index=3, entry=article
    )
    assert built_article.page_type == "wiki_article"
    assert built_article.record["html_content"].startswith("<html>")
    assert built_article.content_bytes_read > 0

    target = _FakeWikiEntry(path="A/Target", title="Target")
    redirect = _FakeWikiEntry(
        path="A/Alias", title="Alias", redirect=target
    )
    built_redirect = build_wikimedia_record(
        archive, index=4, entry=redirect
    )
    assert built_redirect.page_type == "wiki_redirect"
    assert built_redirect.content_bytes_read == 0
    assert built_redirect.record["structured_fields"][0]["value"] == (
        "A/Target"
    )

    resource = _FakeWikiEntry(
        path="_assets/example.svg",
        title="null",
        item=_FakeWikiItem(b"<svg/>", "image/svg+xml"),
    )
    built_resource = build_wikimedia_record(
        archive, index=5, entry=resource
    )
    assert built_resource.page_type == "wiki_resource"
    assert built_resource.record["title"] == "example.svg"
    assert built_resource.record["metadata"][
        "resource_content_omitted"
    ] is True


def test_compact_checkpoint_resume_rolls_back_uncommitted_chunk(tmp_path):
    path = tmp_path / "resume.sqlite"
    writer = CompactWorldIndexWriter(
        path, snapshot_id="world-test", overwrite=True
    )
    first = _records()[0]
    second = _records()[1]
    writer.add_record_atomic(first)
    contract = {
        "pipeline_contract_id": "a" * 64,
        "source_identity_id": "b" * 64,
        "snapshot_id": "world-test",
        "view": {"view_id": "w100k"},
        "scan_end": 2,
    }
    source = {"entry_count": 2}
    state = initial_checkpoint(contract=contract, source=source)
    state.update({
        "next_entry_index": 1,
        "scanned": 1,
        "compiled": 1,
    })
    writer.commit_checkpoint(CHECKPOINT_KEY, state)
    writer.close()

    resumed = CompactWorldIndexWriter.open_existing(
        path, snapshot_id="world-test"
    )
    assert resumed.metadata_value(CHECKPOINT_KEY)["compiled"] == 1
    resumed.add_record_atomic(second)
    resumed.abort()

    recovered = CompactWorldIndexWriter.open_existing(
        path, snapshot_id="world-test"
    )
    assert recovered.conn.execute(
        "SELECT COUNT(*) FROM documents"
    ).fetchone()[0] == 1
    assert recovered.conn.execute(
        "SELECT COUNT(*) FROM search_fts"
    ).fetchone()[0] == 1
    recovered.close()


def test_e2_logical_digest_excludes_checkpoint_schedule(tmp_path):
    full_digests = []
    content_digests = []
    for sequence in (1, 9):
        writer = CompactWorldIndexWriter(
            tmp_path / f"logical-{sequence}.sqlite",
            snapshot_id="world-test",
            overwrite=True,
        )
        writer.add_record_atomic(_records()[0])
        writer.commit_checkpoint(
            CHECKPOINT_KEY,
            {
                "checkpoint_sequence": sequence,
                "elapsed_seconds": float(sequence),
                "resource_curve": [{"sequence": sequence}],
            },
        )
        writer.finalize()
        full_digests.append(writer.logical_digest())
        content_digests.append(writer.logical_digest(
            exclude_metadata_keys=(CHECKPOINT_KEY,)
        ))
        writer.close()

    assert full_digests[0] != full_digests[1]
    assert content_digests[0] == content_digests[1]


def test_wiki_served_path_preserves_or_adds_namespace():
    assert wiki_served_path("A/Noise-cancelling_headphones") == (
        "A/Noise-cancelling_headphones"
    )
    assert wiki_served_path("Noise-cancelling_headphones") == (
        "A/Noise-cancelling_headphones"
    )
    assert wiki_served_path("-/style.css") == "-/style.css"


def test_html_soft_redirect_extracts_meta_refresh_target():
    assert html_soft_redirect(
        """
        <html><head><meta http-equiv="refresh"
        content="0;URL='./List_of_stars#11_Cancri'"></head></html>
        """
    ) == "./List_of_stars#11_Cancri"
    assert html_soft_redirect(
        "<html><body><p>Real article.</p></body></html>"
    ) is None


def test_html_parser_preserves_table_coordinates_and_links():
    parsed = parse_html_document(
        """
        <html><head><title>Specs</title></head><body><main>
          <h2>Battery</h2>
          <table><tr><th>Mode</th><th>Hours</th></tr>
                 <tr><td>ANC</td><td>10</td></tr></table>
          <p>See <a href="/manual">manual</a>.</p>
        </main></body></html>
        """,
        base_url="http://example.test/item",
    )
    cells = [
        block for block in parsed["blocks"]
        if block["block_type"] == "table_cell"
    ]
    assert len(cells) == 4
    assert cells[-1]["structural"]["row_index"] == 1
    assert cells[-1]["structural"]["column_index"] == 1
    assert parsed["links"][0]["canonical_target"] == (
        "http://example.test/manual"
    )


def test_html_parser_preserves_empty_cells_and_logical_rowspan_columns():
    parsed = parse_html_document(
        """
        <html><body><table><caption>Grid</caption>
          <tr><th rowspan="2">Group</th><th>Value</th><th></th></tr>
          <tr><td colspan="2">Second row</td></tr>
        </table></body></html>
        """,
        base_url="http://example.test/grid",
    )
    caption = next(
        block for block in parsed["blocks"]
        if block["block_type"] == "table_caption"
    )
    cells = [
        block for block in parsed["blocks"]
        if block["block_type"] == "table_cell"
    ]
    assert caption["structural"]["table_index"] == 0
    assert len(cells) == 4
    assert cells[2]["text"] == ""
    second_row = cells[3]["structural"]
    assert second_row["cell_index"] == 0
    assert second_row["column_index"] == 1
    assert second_row["grid_column_index"] == 1
    assert second_row["colspan"] == 2


def test_resource_title_falls_back_without_changing_real_null_article():
    assert document_title(
        "null",
        source_id="_assets/icon.svg",
        page_type="wiki_resource",
        archive_entry_path="_assets/icon.svg",
    ) == "icon.svg"
    assert document_title(
        "Null", source_id="A/Null", page_type="wiki_article"
    ) == "Null"


def test_audit_projection_exposes_tables_reply_depth_and_resource_identity():
    record = {
        "source_id": "_assets/icon.svg",
        "canonical_url": "http://example.test/icon.svg",
        "archive_entry_path": "_assets/icon.svg",
        "page_type": "wiki_resource",
        "title": "null",
        "mime_type": "image/svg+xml",
        "raw_content_hash": "d" * 64,
        "capture_or_archive_locator": "zim:test/1/_assets/icon.svg",
        "metadata": {"resource_content_omitted": True},
        "structured_fields": [{
            "name": "item_size", "value": "12", "unit": "bytes"
        }],
        "blocks": [
            {
                "block_type": "table_cell",
                "text": "Head",
                "section_path": [],
                "dom_path": "/table/tr/th[1]",
                "structural": {
                    "table_index": 0, "row_index": 0,
                    "cell_index": 0, "column_index": 0,
                    "grid_column_index": 0, "rowspan": 1,
                    "colspan": 1, "is_header": True,
                },
            },
            {
                "block_type": "table_cell",
                "text": "",
                "section_path": [],
                "dom_path": "/table/tr/td[1]",
                "structural": {
                    "table_index": 0, "row_index": 1,
                    "cell_index": 0, "column_index": 0,
                    "grid_column_index": 0, "rowspan": 1,
                    "colspan": 1, "is_header": False,
                },
            },
        ],
        "interactions": [
            {
                "interaction_id": "root", "parent_interaction_id": None,
                "kind": "post", "author_key": "a", "text": "Root",
            },
            {
                "interaction_id": "child", "parent_interaction_id": "root",
                "kind": "reply", "author_key": "b", "text": "Reply",
            },
        ],
        "links": [],
    }
    rendered = render_document_html(record)
    artifact = {
        key: record[key]
        for key in (
            "blocks", "links", "structured_fields", "interactions"
        )
    }
    assert projection_structure_failures(rendered, record, artifact) == []
    assert "<title>icon.svg</title>" in rendered
    assert 'data-dra-audit-depth="1"' in rendered
    assert 'data-dra-audit-table-index="0"' in rendered


def test_exact_projection_roundtrip_rejects_text_preserving_structure_changes():
    record = _records()[1]
    artifact = {
        key: record[key]
        for key in (
            "blocks", "links", "structured_fields", "interactions"
        )
    }
    rendered = render_document_html(record)
    assert projection_roundtrip_failures(
        rendered,
        canonical_url=record["canonical_url"],
        artifact=artifact,
    ) == []

    wrong_parent = rendered.replace(
        'data-dra-parent-id="post:7"',
        'data-dra-parent-id="post:wrong"',
        1,
    )
    reasons = {
        failure["reason"] for failure in projection_roundtrip_failures(
            wrong_parent,
            canonical_url=record["canonical_url"],
            artifact=artifact,
        )
    }
    assert "interaction_stream_mismatch" in reasons

    table_record = {
        **record,
        "blocks": [{
            "block_type": "table_cell",
            "section_path": [],
            "dom_path": "/table/tr/td[1]",
            "text": "same text",
            "structural": {
                "table_index": 0, "row_index": 0,
                "cell_index": 0, "column_index": 0,
                "grid_column_index": 0, "rowspan": 1,
                "colspan": 1, "is_header": False,
            },
        }],
        "interactions": [],
    }
    table_artifact = {
        key: table_record[key]
        for key in (
            "blocks", "links", "structured_fields", "interactions"
        )
    }
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(render_document_html(table_record), "lxml")
    node = soup.select_one("[data-dra-canonical-block-ordinal]")
    assert node is not None
    structural = json.loads(node["data-dra-structural"])
    structural["column_index"] = 9
    node["data-dra-structural"] = canonical_json(structural)
    reasons = {
        failure["reason"] for failure in projection_roundtrip_failures(
            str(soup),
            canonical_url=table_record["canonical_url"],
            artifact=table_artifact,
        )
    }
    assert "canonical_block_stream_mismatch" in reasons


def test_html_parser_preserves_invalid_table_span_source_value():
    parsed = parse_html_document(
        """
        <html><body><table><tr>
          <td rowspan="100%" colspan="2,">value</td>
        </tr></table></body></html>
        """,
        base_url="http://example.test/item",
    )
    structural = parsed["blocks"][0]["structural"]
    assert structural["rowspan"] == 1
    assert structural["rowspan_raw_invalid"] == "100%"
    assert structural["colspan"] == 1
    assert structural["colspan_raw_invalid"] == "2,"


def test_html_parser_indexes_large_table_coordinates_once():
    rows = "".join(
        "<tr><td>r%d-a</td><td>r%d-b</td></tr>" % (index, index)
        for index in range(100)
    )
    parsed = parse_html_document(
        f"<html><body><table>{rows}</table></body></html>",
        base_url="http://example.test/table",
    )
    cells = [
        block for block in parsed["blocks"]
        if block["block_type"] == "table_cell"
    ]
    assert len(cells) == 200
    assert cells[-1]["structural"]["table_index"] == 0
    assert cells[-1]["structural"]["row_index"] == 99
    assert cells[-1]["structural"]["column_index"] == 1
    assert cells[-1]["dom_path"].endswith("/td[2]")


def test_world_index_is_order_invariant_and_roundtrips(tmp_path):
    records = _records()
    first, digest_a, audit_a = _build(tmp_path / "a.sqlite", records)
    second, digest_b, audit_b = _build(
        tmp_path / "b.sqlite", list(reversed(records))
    )
    try:
        assert digest_a == digest_b
        assert audit_a["failed"] == 0
        assert audit_b["failed"] == 0
        assert first.census()["documents"] == 2
        assert first.census()["interactions"] == 3
        hits = first.search('"Battery" OR "trip"', limit=10)
        assert hits[0]["canonical_url"].endswith("example.html")
        assert first.conn.execute(
            "SELECT target_page_snapshot_id FROM links"
        ).fetchone()[0] is None
    finally:
        first.close()
        second.close()


def test_compact_world_index_preserves_behavior_and_is_order_invariant(
    tmp_path,
):
    records = _records()
    outputs = []
    for name, ordered in (
        ("compact-a.sqlite", records),
        ("compact-b.sqlite", list(reversed(records))),
    ):
        writer = CompactWorldIndexWriter(
            tmp_path / name, snapshot_id="world-test", overwrite=True
        )
        for record in ordered:
            writer.add_record_atomic(record)
        writer.finalize()
        outputs.append((writer, writer.logical_digest()))
    first, second = outputs[0][0], outputs[1][0]
    try:
        assert outputs[0][1] == outputs[1][1]
        assert first.census()["documents"] == 2
        assert first.census()["blocks"] == 2
        assert first.census()["links"] == 1
        assert first.census()["interactions"] == 3
        assert first.structural_audit(expected_documents=2)["passed"]
        assert first.roundtrip_audit()["failed"] == 0
        assert second.roundtrip_audit()["failed"] == 0
        hits = first.search('"Battery" OR "trip"', limit=10)
        assert hits[0]["canonical_url"].endswith("example.html")
        first_ids = [row[0] for row in first.conn.execute(
            "SELECT page_snapshot_id FROM documents ORDER BY page_snapshot_id"
        )]
        second_ids = [row[0] for row in second.conn.execute(
            "SELECT page_snapshot_id FROM documents ORDER BY page_snapshot_id"
        )]
        assert first_ids == second_ids
        for page_id in first_ids:
            assert first.render_by_id(page_id) == second.render_by_id(page_id)
        first_span = first.span_by_ordinal(first_ids[0], 0)
        assert first_span["span_id"] == stable_id(
            "span", first_ids[0], 0
        )
        assert first_span["ordinal"] == 0
    finally:
        first.close()
        second.close()

    reopened = open_writer(tmp_path / "compact-a.sqlite")
    try:
        assert reopened.census()["documents"] == 2
        assert reopened.render_by_id(first_ids[0])
    finally:
        reopened.close()


def test_duplicate_clusters_are_recorded(tmp_path):
    records = _records()
    clone = dict(records[0])
    clone["source_id"] = "43"
    clone["canonical_url"] = "http://localhost:7770/example-copy.html"
    clone["raw_content_hash"] = "c" * 64
    writer, _, _ = _build(
        tmp_path / "duplicates.sqlite", [records[0], clone]
    )
    try:
        sizes = {
            row[0] for row in writer.conn.execute(
                "SELECT cluster_size FROM duplicate_clusters"
            )
        }
        assert sizes == {2}
    finally:
        writer.close()


def test_singletons_are_not_reported_as_duplicate_clusters(tmp_path):
    writer, _, _ = _build(tmp_path / "singletons.sqlite", _records())
    try:
        assert writer.conn.execute(
            "SELECT COUNT(*) FROM duplicate_clusters"
        ).fetchone()[0] == 0
    finally:
        writer.close()


def test_atomic_record_insert_rolls_back_partial_rows(tmp_path):
    bad = dict(_records()[0])
    bad["links"] = [{
        "span_id": "missing-span",
        "href": "/broken",
        "canonical_target": "http://localhost:7770/broken",
        "anchor_text": "Broken",
    }]
    writer = WorldIndexWriter(
        tmp_path / "atomic.sqlite",
        snapshot_id="world-test",
        overwrite=True,
    )
    try:
        with pytest.raises(sqlite3.IntegrityError):
            writer.add_record_atomic(bad)
        assert writer.conn.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0] == 0
        assert writer.conn.execute(
            "SELECT COUNT(*) FROM blocks"
        ).fetchone()[0] == 0
        writer.add_record_atomic(_records()[0])
        assert writer.conn.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0] == 1
        writer.conn.commit()
        assert writer.conn.in_transaction is False
        writer.add_record_atomic(_records()[1])
        assert writer.conn.in_transaction is True
        assert writer.conn.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0] == 2
    finally:
        writer.close()


def test_compressed_jsonl_is_byte_reproducible(tmp_path):
    first = tmp_path / "first.jsonl.gz"
    second = tmp_path / "second.jsonl.gz"
    write_jsonl(first, _records())
    write_jsonl(second, _records())
    assert first.read_bytes() == second.read_bytes()


def test_compile_script_builds_auditable_artifact(tmp_path):
    source = tmp_path / "source"
    records_dir = source / "records"
    records_dir.mkdir(parents=True)
    paths = []
    packs = []
    for index, record in enumerate(_records()):
        path = records_dir / f"pack-{index}.jsonl.gz"
        write_jsonl(path, [record])
        paths.append(path)
        packs.append({
            "pack_id": record["pack_id"],
            "population": 100,
            "selected": 1,
            "records_path": str(path.relative_to(source)),
            "records_sha256": sha256(path.read_bytes()).hexdigest(),
            "errors": 0,
        })
    manifest = {
        "schema": "dra_e1_source_manifest_v1",
        "snapshot_id": "world-test",
        "source_manifest_id": "source-test",
        "selection": {
            "algorithm": "fixture",
            "modulus": 100,
            "bucket": 0,
        },
        "task_conditioned": False,
        "task_or_witness_inputs": [],
        "packs": packs,
    }
    (source / "source-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    output = tmp_path / "compiled"
    result = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parents[1]
                / "scripts/compile_e1_world_shard.py"
            ),
            "--source-dir", str(source),
            "--out", str(output),
            "--roundtrip-per-pack", "1",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr + result.stdout
    build = json.loads(
        (output / "build-manifest.json").read_text(encoding="utf-8")
    )
    quality = json.loads(
        (output / "quality-report.json").read_text(encoding="utf-8")
    )
    assert build["task_conditioned"] is False
    assert build["formal_eligible"] is False
    assert build["source_and_build_gates_pass"] is False
    assert len(build["compiler_sha256"]) == 64
    assert len(build["world_index_module_sha256"]) == 64
    assert build["census"]["documents"] == 2
    assert quality["gates"]["roundtrip_failures_zero"] is True
    assert quality["gates"]["bm25_top20_at_least_0_90"] is True

    resume_output = tmp_path / "compiled-resumed"
    resume_output.mkdir()
    partial = WorldIndexWriter(
        resume_output / "world-index.sqlite",
        snapshot_id="world-test",
        overwrite=True,
    )
    partial.set_metadata("source_manifest_id", "source-test")
    partial.add_record_atomic(_records()[0])
    partial.close()
    resume_result = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parents[1]
                / "scripts/compile_e1_world_shard.py"
            ),
            "--source-dir", str(source),
            "--out", str(resume_output),
            "--roundtrip-per-pack", "1",
            "--resume-existing",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert resume_result.returncode == 0, (
        resume_result.stderr + resume_result.stdout
    )
    resume_build = json.loads(
        (resume_output / "build-manifest.json").read_text(encoding="utf-8")
    )
    resume_resource = json.loads(
        (resume_output / "resource-report.json").read_text(encoding="utf-8")
    )
    assert resume_build["census"]["documents"] == 2
    assert resume_build["resumed_existing_documents"] == 1
    assert resume_resource["complete_build_resource_measurement"] is False

    compact_output = tmp_path / "compiled-compact"
    compact_result = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parents[1]
                / "scripts/compile_e1_world_shard_compact.py"
            ),
            "--source-dir", str(source),
            "--out", str(compact_output),
            "--roundtrip-per-pack", "1",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert compact_result.returncode == 0, (
        compact_result.stderr + compact_result.stdout
    )
    compact_build = json.loads(
        (compact_output / "build-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    compact_quality = json.loads(
        (compact_output / "quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert compact_build["storage_profile"] == (
        "compact-document-artifact-v1"
    )
    assert compact_build["census"]["documents"] == 2
    assert compact_quality["gates"]["roundtrip_failures_zero"] is True
    assert compact_quality["gates"]["exact_alias_complete"] is True
    canonical_structure_path = tmp_path / "canonical-structures.json"
    canonical_structure_result = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parents[1]
                / "scripts/audit_e1_canonical_structures.py"
            ),
            "--build-dir", str(compact_output),
            "--out", str(canonical_structure_path),
            "--progress-every", "0",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert canonical_structure_result.returncode == 0, (
        canonical_structure_result.stderr
        + canonical_structure_result.stdout
    )
    assert json.loads(
        canonical_structure_path.read_text(encoding="utf-8")
    )["passed"] is True
    compact_queue_path = tmp_path / "compact-audit.json"
    compact_queue_result = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parents[1]
                / "scripts/create_e1_manual_audit_queue.py"
            ),
            "--build-dir", str(compact_output),
            "--per-stratum", "1",
            "--out", str(compact_queue_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert compact_queue_result.returncode == 0, (
        compact_queue_result.stderr + compact_queue_result.stdout
    )
    compact_queue = json.loads(
        compact_queue_path.read_text(encoding="utf-8")
    )
    assert compact_queue["sampling"]["storage_profile"] == (
        "compact-document-artifact-v1"
    )
    assert compact_queue["summary"]["total"] == 2
    packet_dir = tmp_path / "manual-packet"
    packet_result = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parents[1]
                / "scripts/render_e1_manual_audit_packet.py"
            ),
            "--queue", str(compact_queue_path),
            "--build-dir", str(compact_output),
            "--source-dir", str(source),
            "--out-dir", str(packet_dir),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert packet_result.returncode == 0, (
        packet_result.stderr + packet_result.stdout
    )
    assert (packet_dir / "index.html").exists()
    machine_preaudit = json.loads(
        (packet_dir / "machine-preaudit.json").read_text(
            encoding="utf-8"
        )
    )
    assert machine_preaudit["summary"]["failed"] == 0
    assert all(
        Path(item["source_record"]).exists()
        for item in machine_preaudit["items"]
    )
    assert "② 打开原始记录" in (
        packet_dir / "index.html"
    ).read_text(encoding="utf-8")
    packet_html = (packet_dir / "index.html").read_text(encoding="utf-8")
    assert "导出最终审阅 JSON" in packet_html
    assert "保存当前进度" in packet_html
    assert "导入之前的进度 JSON" in packet_html
    assert "不需要看代码，也不评价网页是否美观" in packet_html
    assert "我已对照，结构与来源一致" in packet_html
    assert "非原站、非 harness 页面" in packet_html
    assert "我发现了问题" in packet_html
    assert "localStorage.setItem(storageKey" in packet_html
    assert "function validateImportedQueue(candidate)" in packet_html
    assert "candidate[key] !== queue[key]" in packet_html
    assert "抽查项目身份不匹配" in packet_html
    assert 'class="audit-check"' in packet_html
    node = shutil.which("node")
    if node:
        script_marker = "<script>\nconst queue ="
        script_start = packet_html.index(script_marker) + len("<script>\n")
        script_end = packet_html.index("</script>", script_start)
        ui_script = tmp_path / "manual-audit-ui.js"
        ui_script.write_text(
            packet_html[script_start:script_end], encoding="utf-8"
        )
        syntax_result = subprocess.run(
            [node, "--check", str(ui_script)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert syntax_result.returncode == 0, (
            syntax_result.stderr + syntax_result.stdout
        )
    fidelity_path = tmp_path / "storage-fidelity.json"
    fidelity_result = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parents[1]
                / "scripts/compare_e1_storage_profiles.py"
            ),
            "--row-build", str(output),
            "--compact-build", str(compact_output),
            "--per-pack", "1",
            "--out", str(fidelity_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert fidelity_result.returncode == 0, (
        fidelity_result.stderr + fidelity_result.stdout
    )
    assert json.loads(
        fidelity_path.read_text(encoding="utf-8")
    )["passed"] is True
    for label, directory in (
        ("row", output),
        ("compact", compact_output),
    ):
        storage_path = tmp_path / f"storage-{label}.json"
        storage_result = subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[1]
                    / "scripts/analyze_e1_sqlite_storage.py"
                ),
                "--build-dir", str(directory),
                "--out", str(storage_path),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            cwd=Path(__file__).resolve().parents[1],
        )
        assert storage_result.returncode == 0, (
            storage_result.stderr + storage_result.stdout
        )
        assert json.loads(
            storage_path.read_text(encoding="utf-8")
        )["passed"] is True

    formalized_source = json.loads(
        (source / "source-manifest.json").read_text(encoding="utf-8")
    )
    formalized_source["formal_eligible"] = True
    formalized_source["selection"]["selection_rate"] = 0.5
    (source / "source-manifest.json").write_text(
        json.dumps(formalized_source), encoding="utf-8"
    )
    formalized_build = json.loads(
        (compact_output / "build-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    formalized_build["source_and_build_gates_pass"] = True
    (compact_output / "build-manifest.json").write_text(
        json.dumps(formalized_build), encoding="utf-8"
    )
    projection_path = tmp_path / "resource-projection.json"
    projection_result = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parents[1]
                / "scripts/assess_e1_resource_projection.py"
            ),
            "--source-dir", str(source),
            "--candidate-build", str(compact_output),
            "--available-disk-bytes", str(10**12),
            "--total-memory-bytes", str(10**11),
            "--min-ingest-checkpoints", "0",
            "--out", str(projection_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert projection_result.returncode == 0, (
        projection_result.stderr + projection_result.stdout
    )
    assert json.loads(
        projection_path.read_text(encoding="utf-8")
    )["formal_gate_passed"] is True


def test_manual_audit_queue_is_deterministic_and_stratified(tmp_path):
    db_path = tmp_path / "world-index.sqlite"
    writer, logical_build_id, _ = _build(db_path, _records())
    writer.close()
    (tmp_path / "build-manifest.json").write_text(
        json.dumps({
            "logical_build_id": logical_build_id,
            "source_manifest_id": "source-test",
        }),
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[1]
    outputs = [tmp_path / "audit-a.json", tmp_path / "audit-b.json"]
    for output in outputs:
        result = subprocess.run(
            [
                sys.executable,
                str(root / "scripts/create_e1_manual_audit_queue.py"),
                "--build-dir", str(tmp_path),
                "--per-stratum", "1",
                "--out", str(output),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            cwd=root,
        )
        assert result.returncode == 0, result.stderr + result.stdout

    first = json.loads(outputs[0].read_text(encoding="utf-8"))
    second = json.loads(outputs[1].read_text(encoding="utf-8"))
    first.pop("created_at")
    second.pop("created_at")
    assert first == second
    assert first["sampling"]["anchor_kind"] == "source_manifest_id"
    assert first["sampling"]["anchor_id"] == "source-test"
    assert first["sampling"]["method"] == (
        "sha256(anchor_id,NUL,stratum,NUL,page_id)"
    )
    assert len(first["queue_definition_id"]) == 64
    assert first["summary"] == {
        "failed": 0,
        "formal_gate_passed": False,
        "passed": 0,
        "pending": 2,
        "total": 2,
    }
    assert {item["stratum"] for item in first["items"]} == {
        "commerce_product_with_review",
        "community_thread_with_replies",
    }

    changed_manifest = json.loads(
        (tmp_path / "build-manifest.json").read_text(encoding="utf-8")
    )
    changed_manifest["logical_build_id"] = "compiler-rebuild-test"
    (tmp_path / "build-manifest.json").write_text(
        json.dumps(changed_manifest), encoding="utf-8"
    )
    third_path = tmp_path / "audit-c.json"
    third_result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/create_e1_manual_audit_queue.py"),
            "--build-dir", str(tmp_path),
            "--per-stratum", "1",
            "--out", str(third_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=root,
    )
    assert third_result.returncode == 0, (
        third_result.stderr + third_result.stdout
    )
    third = json.loads(third_path.read_text(encoding="utf-8"))
    identity = lambda queue: [
        (
            item["audit_item_id"], item["stratum"],
            item["document"]["page_snapshot_id"],
        )
        for item in queue["items"]
    ]
    assert identity(first) == identity(third)
    assert first["logical_build_id"] != third["logical_build_id"]
    assert first["queue_definition_id"] != third["queue_definition_id"]
    prior = json.loads(json.dumps(first))
    prior["items"][0]["review"] = {
        "status": "passed",
        "reviewer_id": "human-a",
        "reviewer_kind": "human",
        "reviewed_at": "2026-07-20T00:00:00Z",
        "check_results": {
            check: True
            for check in prior["items"][0]["required_checks"]
        },
        "systematic_loss_category": "表格行列错位",
        "notes": "prior observation",
    }
    prior_wrapper_path = tmp_path / "prior-wrapper.json"
    prior_wrapper_path.write_text(
        json.dumps({
            "queue": prior,
            "reviewer_id": "human-a",
            "saved_at": "2026-07-20T00:01:00Z",
        }),
        encoding="utf-8",
    )
    history_path = tmp_path / "audit-with-history.json"
    history_result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/carry_e1_review_history.py"),
            "--from-queue", str(prior_wrapper_path),
            "--to-queue", str(third_path),
            "--out", str(history_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=root,
    )
    assert history_result.returncode == 0, (
        history_result.stderr + history_result.stdout
    )
    with_history = json.loads(history_path.read_text(encoding="utf-8"))
    assert with_history["review_history_summary"]["carried_items"] == 1
    assert with_history["review_history_summary"][
        "formal_credit_granted"
    ] is False
    assert with_history["items"][0]["review"]["status"] == "pending"
    assert with_history["items"][0]["review_history"][0][
        "review"
    ]["notes"] == "prior observation"
    assert queue_definition_id(with_history) == third[
        "queue_definition_id"
    ]
    changed_manifest["logical_build_id"] = logical_build_id
    (tmp_path / "build-manifest.json").write_text(
        json.dumps(changed_manifest), encoding="utf-8"
    )
    checks = {
        item["stratum"]: set(item["required_checks"])
        for item in first["items"]
    }
    assert "structured_field_value_and_provenance" in checks[
        "commerce_product_with_review"
    ]
    assert "interaction_parent_child_tree" in checks[
        "community_thread_with_replies"
    ]

    machine_preaudit = tmp_path / "machine-preaudit.json"
    machine_preaudit.write_text(
        json.dumps({
            "schema": "dra_e1_manual_audit_machine_precheck_v1",
            "auditor_sha256": "a" * 64,
            "queue_definition_id": first["queue_definition_id"],
            "logical_build_id": logical_build_id,
            "source_manifest_id": "source-test",
            "summary": {
                "total": len(first["items"]),
                "passed": len(first["items"]),
                "failed": 0,
            },
            "items": [
                {
                    "audit_item_id": item["audit_item_id"],
                    "page_snapshot_id": item["document"][
                        "page_snapshot_id"
                    ],
                    "machine_precheck_passed": True,
                    "machine_precheck_failures": [],
                }
                for item in first["items"]
            ],
        }),
        encoding="utf-8",
    )
    pending_report = tmp_path / "pending-report.json"
    pending_result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/finalize_e1_manual_audit.py"),
            "--queue", str(outputs[0]),
            "--build-dir", str(tmp_path),
            "--machine-preaudit", str(machine_preaudit),
            "--min-per-stratum", "1",
            "--out", str(pending_report),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=root,
    )
    assert pending_result.returncode == 2
    assert json.loads(
        pending_report.read_text(encoding="utf-8")
    )["formal_gate_passed"] is False

    completed = json.loads(outputs[0].read_text(encoding="utf-8"))
    for item in completed["items"]:
        item["review"] = {
            "status": "passed",
            "reviewer_id": "fixture-reviewer",
            "reviewer_kind": "human",
            "reviewed_at": "2026-07-19T00:00:00Z",
            "check_results": {
                check: True for check in item["required_checks"]
            },
            "systematic_loss_category": None,
            "notes": None,
        }
    reviewed_queue = tmp_path / "reviewed-audit.json"
    reviewed_queue.write_text(
        json.dumps(completed), encoding="utf-8"
    )
    completed_report = tmp_path / "completed-report.json"
    completed_result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/finalize_e1_manual_audit.py"),
            "--queue", str(reviewed_queue),
            "--build-dir", str(tmp_path),
            "--machine-preaudit", str(machine_preaudit),
            "--min-per-stratum", "1",
            "--out", str(completed_report),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=root,
    )
    assert completed_result.returncode == 0, (
        completed_result.stderr + completed_result.stdout
    )
    assert json.loads(
        completed_report.read_text(encoding="utf-8")
    )["formal_gate_passed"] is True


def test_http_renderer_and_auditor_roundtrip(tmp_path):
    writer, _, _ = _build(
        tmp_path / "http.sqlite", _records()
    )
    writer.close()
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
    except PermissionError:
        pytest.skip("local TCP sockets are disabled in this test sandbox")
    root = Path(__file__).resolve().parents[1]
    server = subprocess.Popen(
        [
            sys.executable,
            str(root / "scripts/serve_e1_world_shard.py"),
            "--db", str(tmp_path / "http.sqlite"),
            "--port", str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=root,
    )
    try:
        for _ in range(50):
            try:
                with urlopen(
                    f"http://127.0.0.1:{port}/health",
                    timeout=0.2,
                ):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("renderer did not start")
        audit = subprocess.run(
            [
                sys.executable,
                str(root / "scripts/audit_e1_http_surface.py"),
                "--db", str(tmp_path / "http.sqlite"),
                "--base-url", f"http://127.0.0.1:{port}",
                "--per-pack", "1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            cwd=root,
        )
        assert audit.returncode == 0, audit.stderr + audit.stdout
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


def test_e1_stage_certificate_requires_bound_external_gates(tmp_path):
    source = tmp_path / "source"
    build_a = tmp_path / "build-a"
    build_b = tmp_path / "build-b"
    source.mkdir()
    build_a.mkdir()
    build_b.mkdir()
    source_id = "source-1"
    logical_id = "logical-1"
    (source / "source-manifest.json").write_text(json.dumps({
        "source_manifest_id": source_id,
        "formal_eligible": True,
        "task_conditioned": False,
        "task_or_witness_inputs": [],
    }), encoding="utf-8")
    build_manifest = {
        "source_manifest_id": source_id,
        "logical_build_id": logical_id,
        "sqlite_sha256": "a" * 64,
        "census": {"documents": 198699},
        "world_index_schema": "dra_world_index_compact_v1",
        "storage_profile": "compact-document-artifact-v1",
        "source_and_build_gates_pass": True,
        "task_conditioned": False,
        "task_or_witness_inputs": [],
        "compiler_sha256": "b" * 64,
        "world_index_module_sha256": "c" * 64,
        "structural_parser_module_sha256": "d" * 64,
    }
    for directory in (build_a, build_b):
        (directory / "build-manifest.json").write_text(
            json.dumps(build_manifest), encoding="utf-8"
        )
    reports = {
        "repro.json": {
            "passed": True,
            "auditor_sha256": "1" * 64,
            "checks": {"all": True},
            "first": str(build_a.resolve()),
            "second": str(build_b.resolve()),
            "first_logical_build_id": logical_id,
            "second_logical_build_id": logical_id,
            "source_manifest_id": source_id,
        },
        "http.json": {
            "passed": True,
            "auditor_sha256": "2" * 64,
            "logical_build_id": logical_id,
            "sqlite_sha256": "a" * 64,
            "db": str((build_a / "world-index.sqlite").resolve()),
            "sampled": 300,
            "document_hash_rate": 1.0,
            "min_search_top20_rate": 0.9,
            "search_top20_rate": 0.98,
        },
        "canonical.json": {
            "passed": True,
            "auditor_sha256": "6" * 64,
            "logical_build_id": logical_id,
            "source_manifest_id": source_id,
            "sqlite_sha256": "a" * 64,
            "build_dir": str(build_a.resolve()),
            "database": str(
                (build_a / "world-index.sqlite").resolve()
            ),
            "totals": {"documents": 198699},
            "failure_counts": {},
        },
        "manual.json": {
            "formal_gate_passed": True,
            "auditor_sha256": "3" * 64,
            "logical_build_id": logical_id,
            "source_manifest_id": source_id,
            "build_dir": str(build_a.resolve()),
            "min_per_stratum": 20,
            "queue_definition_id": "e" * 64,
            "machine_preaudit_sha256": "f" * 64,
        },
        "resource.json": {
            "formal_gate_passed": True,
            "auditor_sha256": "4" * 64,
            "logical_build_id": logical_id,
            "source_manifest_id": source_id,
            "candidate_build": str(build_a.resolve()),
            "selection": {"selection_rate": 0.01},
            "observed": {"ingest_checkpoints": 20},
            "host_budget": {
                "disk_usable_fraction": 0.8,
                "memory_usable_fraction": 0.8,
                "max_runtime_hours": 168.0,
            },
            "projection": {
                "disk_uncertainty_factor": 1.25,
                "runtime_uncertainty_factor": 1.5,
                "memory_uncertainty_factor": 2.0,
            },
        },
        "fidelity.json": {
            "passed": True,
            "auditor_sha256": "5" * 64,
            "compact_build": str(build_a.resolve()),
            "compact_logical_build_id": logical_id,
            "source_manifest_id": source_id,
        },
    }
    for filename, payload in reports.items():
        (tmp_path / filename).write_text(
            json.dumps(payload), encoding="utf-8"
        )
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        str(root / "scripts/finalize_e1_stage.py"),
        "--source-dir", str(source),
        "--build-a", str(build_a),
        "--build-b", str(build_b),
        "--reproducibility", str(tmp_path / "repro.json"),
        "--http-audit", str(tmp_path / "http.json"),
        "--canonical-structure-audit",
        str(tmp_path / "canonical.json"),
        "--manual-audit", str(tmp_path / "manual.json"),
        "--resource-projection", str(tmp_path / "resource.json"),
        "--storage-fidelity", str(tmp_path / "fidelity.json"),
        "--out", str(tmp_path / "certificate.json"),
    ]
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=root,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(
        (tmp_path / "certificate.json").read_text(encoding="utf-8")
    )["status"] == "PASS"

    reports["manual.json"]["logical_build_id"] = "wrong-build"
    (tmp_path / "manual.json").write_text(
        json.dumps(reports["manual.json"]), encoding="utf-8"
    )
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=root,
    )
    assert result.returncode == 2
    assert json.loads(
        (tmp_path / "certificate.json").read_text(encoding="utf-8")
    )["status"] == "FAIL"
