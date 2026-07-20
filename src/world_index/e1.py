"""Deterministic compiler for the Phase E1 structural World Index shard.

This module is intentionally task-blind.  It accepts source records from the
frozen Domain Packs and writes a common SQLite representation containing:

* page identity, source lineage, hashes, redirects, and archive locators;
* stable blocks for paragraphs, lists, tables, product fields, posts, reviews;
* page/span links and deterministic structured fields;
* interaction trees for forum replies and product reviews;
* exact aliases and a SQLite FTS5/BM25 retrieval index.

No LLM is called and no assertion-level semantics are inferred here.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import unquote, urljoin


E1_SCHEMA_VERSION = "dra_world_index_e1_v1"
SHARD_ALGORITHM = "sha256(snapshot_id\\0pack_id\\0source_id)-mod-v1"
PARSER_VERSION = "dra-structural-html-v3"
LOCATOR_VERSION = "dra-block-locator-v1"
RENDERER_VERSION = "dra-e1-renderer-v2"
SEARCH_VERSION = "sqlite-fts5-bm25-v1"


_WS = re.compile(r"\s+")


def canonical_json(value: Any) -> str:
    """Stable JSON encoding used for hashes and JSON columns."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def normalize_text(value: Any) -> str:
    return _WS.sub(" ", str(value or "")).strip()


def document_title(
    value: Any,
    *,
    parsed_title: Any = "",
    source_id: Any = "",
    page_type: Any = "",
    archive_entry_path: Any = "",
) -> str:
    """Resolve a usable title without mistaking ZIM null metadata for one.

    Some non-HTML ZIM entries expose the literal string ``"null"`` as their
    title.  That is source metadata, not the name a reviewer should see.  The
    special case is deliberately limited to resource records so a legitimate
    encyclopedia article named "Null" remains untouched.
    """

    candidate = normalize_text(value)
    if (
        normalize_text(page_type) == "wiki_resource"
        and candidate.casefold() in {"null", "none", "undefined"}
    ):
        candidate = ""
    if candidate:
        return candidate
    parsed = normalize_text(parsed_title)
    if parsed:
        return parsed
    locator = normalize_text(archive_entry_path) or normalize_text(source_id)
    if normalize_text(page_type) == "wiki_resource" and locator:
        leaf = unquote(locator).rstrip("/").rsplit("/", 1)[-1]
        if leaf:
            return leaf
    return normalize_text(source_id) or "Untitled"


def stable_rank64(
    snapshot_id: str,
    pack_id: str,
    source_id: str,
) -> int:
    """Return a reproducible unsigned 64-bit rank for a source object."""

    material = f"{snapshot_id}\0{pack_id}\0{source_id}".encode("utf-8")
    return int.from_bytes(sha256(material).digest()[:8], "big")


def stable_bucket(
    snapshot_id: str,
    pack_id: str,
    source_id: str,
    *,
    modulus: int = 100,
) -> int:
    """Return the reproducible shard bucket for a top-level source object."""

    if modulus <= 0:
        raise ValueError("modulus must be positive")
    return stable_rank64(snapshot_id, pack_id, source_id) % modulus


def stable_id(prefix: str, *parts: Any, length: int = 24) -> str:
    material = "\0".join(str(p) for p in parts)
    return f"{prefix}_{sha256_text(material)[:length]}"


def _dom_path(tag: Any) -> str:
    """Create a deterministic, compact DOM locator for a BeautifulSoup tag."""

    pieces: list[str] = []
    cur = tag
    while getattr(cur, "name", None) and len(pieces) < 12:
        name = str(cur.name).lower()
        index = 1
        sibling = getattr(cur, "previous_sibling", None)
        while sibling is not None:
            if getattr(sibling, "name", None) == cur.name:
                index += 1
            sibling = getattr(sibling, "previous_sibling", None)
        pieces.append(f"{name}[{index}]")
        cur = getattr(cur, "parent", None)
    return "/" + "/".join(reversed(pieces))


def _precompute_dom_paths(soup: Any) -> dict[int, str]:
    """Compute sibling-indexed DOM paths in one tree traversal."""

    paths: dict[int, str] = {}
    stack: list[tuple[Any, str]] = [(soup, "")]
    while stack:
        parent, parent_path = stack.pop()
        counts: dict[str, int] = {}
        descendants: list[tuple[Any, str]] = []
        for child in getattr(parent, "children", ()):
            if not getattr(child, "name", None):
                continue
            name = str(child.name).lower()
            counts[name] = counts.get(name, 0) + 1
            path = f"{parent_path}/{name}[{counts[name]}]"
            paths[id(child)] = path
            descendants.append((child, path))
        stack.extend(reversed(descendants))
    return paths


def _table_span_attributes(tag: Any) -> dict[str, Any]:
    structural: dict[str, Any] = {}
    for attribute in ("rowspan", "colspan"):
        raw_value = tag.get(attribute)
        raw_text = str(raw_value).strip() if raw_value is not None else "1"
        if re.fullmatch(r"[0-9]+", raw_text):
            structural[attribute] = int(raw_text)
        else:
            structural[attribute] = 1
            structural[f"{attribute}_raw_invalid"] = raw_text
    return structural


def _precompute_table_coordinates(soup: Any) -> dict[int, dict[str, Any]]:
    """Index table cells on the logical grid in one table traversal.

    ``cell_index`` preserves physical sibling order.  ``column_index`` and
    ``grid_column_index`` identify the logical column after accounting for
    rowspans from earlier rows.  Keeping both avoids silently treating a DOM
    sibling position as a table-grid coordinate.
    """

    tables = list(soup.find_all("table"))
    table_index = {id(table): index for index, table in enumerate(tables)}
    rows_by_table: dict[int, list[Any]] = {}
    for row in soup.find_all("tr"):
        table = row.find_parent("table")
        if table is not None:
            rows_by_table.setdefault(id(table), []).append(row)

    coordinates: dict[int, dict[str, Any]] = {}
    for table in tables:
        current_table_index = table_index[id(table)]
        for caption in table.find_all("caption", recursive=False):
            coordinates[id(caption)] = {
                "table_index": current_table_index,
            }
        rows = rows_by_table.get(id(table), [])
        occupied_until: dict[int, int] = {}
        for row_index, row in enumerate(rows):
            cells = row.find_all(["th", "td"], recursive=False)
            for cell_index, cell in enumerate(cells):
                span = _table_span_attributes(cell)
                colspan = max(1, int(span.get("colspan") or 1))
                raw_rowspan = int(span.get("rowspan") or 0)
                effective_rowspan = (
                    max(1, len(rows) - row_index)
                    if raw_rowspan == 0
                    else max(1, raw_rowspan)
                )
                column_index = 0
                while any(
                    occupied_until.get(column, 0) > row_index
                    for column in range(
                        column_index, column_index + colspan
                    )
                ):
                    column_index += 1
                coordinates[id(cell)] = {
                    "table_index": current_table_index,
                    "row_index": row_index,
                    "cell_index": cell_index,
                    "column_index": column_index,
                    "grid_column_index": column_index,
                    "is_header": getattr(cell, "name", "") == "th",
                    **span,
                }
                if raw_rowspan == 0:
                    coordinates[id(cell)][
                        "effective_rowspan"
                    ] = effective_rowspan
                if int(span.get("colspan") or 0) == 0:
                    coordinates[id(cell)]["effective_colspan"] = colspan
                for column in range(
                    column_index, column_index + colspan
                ):
                    occupied_until[column] = max(
                        occupied_until.get(column, 0),
                        row_index + effective_rowspan,
                    )
    return coordinates


def _table_coordinates(tag: Any) -> dict[str, Any]:
    row = tag.find_parent("tr")
    table = tag.find_parent("table")
    row_index = None
    column_index = None
    if table is not None and row is not None:
        rows = table.find_all("tr")
        try:
            row_index = rows.index(row)
        except ValueError:
            pass
        cells = row.find_all(["th", "td"], recursive=False)
        try:
            column_index = cells.index(tag)
        except ValueError:
            pass
    structural = {
        "table_index": None if table is None else len(table.find_all_previous("table")),
        "row_index": row_index,
        "column_index": column_index,
        "is_header": getattr(tag, "name", "") == "th",
    }
    return {**structural, **_table_span_attributes(tag)}


def parse_html_document(html: str, *, base_url: str) -> dict[str, Any]:
    """Parse stable text blocks, table cells, and links from HTML.

    Generated E1 renderer pages carry ``data-dra-block-type`` locators.  Those
    take precedence during round-trip parsing so interaction and table context
    is not flattened on the served side.
    """

    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover: deployment preflight checks it
        raise RuntimeError("beautifulsoup4 is required for E1 HTML parsing") from exc

    soup = BeautifulSoup(html or "", "lxml")
    for noisy in soup.find_all(["script", "style", "noscript", "template"]):
        noisy.decompose()

    dom_paths = _precompute_dom_paths(soup)
    table_coordinates = _precompute_table_coordinates(soup)

    title = ""
    if soup.title is not None:
        title = normalize_text(soup.title.get_text(" ", strip=True))
    if not title:
        heading = soup.find(["h1", "h2"])
        if heading is not None:
            title = normalize_text(heading.get_text(" ", strip=True))

    blocks: list[dict[str, Any]] = []
    section_stack: list[str] = []

    explicit = soup.select("[data-dra-block-type]")
    if explicit:
        candidates = explicit
    else:
        root = soup.find("main") or soup.find("article") or soup.body or soup
        candidates = root.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "caption", "figcaption", "th", "td"]
        )

    for tag in candidates:
        text = normalize_text(tag.get_text(" ", strip=True))
        name = str(getattr(tag, "name", "") or "").lower()
        explicit_type = tag.get("data-dra-block-type")
        if not text and not (
            name in {"th", "td"} or explicit_type == "table_cell"
        ):
            continue
        if explicit_type:
            block_type = str(explicit_type)
            raw_section = tag.get("data-dra-section-path")
            try:
                section_path = json.loads(raw_section) if raw_section else []
            except (TypeError, json.JSONDecodeError):
                section_path = []
            structural = {}
            raw_structural = tag.get("data-dra-structural")
            if raw_structural:
                try:
                    structural = json.loads(raw_structural)
                except json.JSONDecodeError:
                    structural = {}
        else:
            structural: dict[str, Any] = {}
            if name.startswith("h") and len(name) == 2 and name[1].isdigit():
                level = max(1, min(6, int(name[1])))
                section_stack = section_stack[: level - 1]
                section_stack.append(text)
                block_type = "heading"
            elif name == "li":
                block_type = "list_item"
            elif name in {"th", "td"}:
                block_type = "table_cell"
                precomputed = table_coordinates.get(id(tag))
                structural = (
                    dict(precomputed)
                    if precomputed is not None
                    else _table_coordinates(tag)
                )
            elif name == "caption":
                block_type = "table_caption"
                structural = dict(table_coordinates.get(id(tag)) or {})
            elif name == "figcaption":
                block_type = "figure_caption"
            else:
                block_type = "paragraph"
            section_path = list(section_stack)

        blocks.append(
            {
                "ordinal": len(blocks),
                "block_type": block_type,
                "section_path": section_path,
                "dom_path": (
                    tag.get("data-dra-dom-path")
                    or dom_paths.get(id(tag))
                    or _dom_path(tag)
                ),
                "text": text,
                "structural": structural,
            }
        )

    links: list[dict[str, Any]] = []
    for ordinal, anchor in enumerate(soup.find_all("a", href=True)):
        raw_href = str(anchor.get("href") or "").strip()
        if not raw_href or raw_href.startswith(("javascript:", "mailto:", "data:")):
            continue
        links.append(
            {
                "ordinal": len(links),
                "href": raw_href,
                "canonical_target": urljoin(base_url, raw_href),
                "anchor_text": normalize_text(anchor.get_text(" ", strip=True)),
                "dom_path": (
                    dom_paths.get(id(anchor)) or _dom_path(anchor)
                ),
            }
        )

    _assign_offsets(blocks)
    body_text = "\n".join(block["text"] for block in blocks)
    return {"title": title, "body_text": body_text, "blocks": blocks, "links": links}


def _assign_offsets(blocks: Sequence[dict[str, Any]]) -> None:
    cursor = 0
    for block in blocks:
        text = normalize_text(block.get("text"))
        block["text"] = text
        block["char_start"] = cursor
        block["char_end"] = cursor + len(text)
        cursor += len(text) + 1


def _json_attr(value: Any) -> str:
    return escape(canonical_json(value), quote=True)


def _display_number(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format(float(value), ".12g")
    return str(value)


def render_document_html(record: Mapping[str, Any]) -> str:
    """Render a deterministic canonical audit projection.

    This projection is for compiler round-trip checks and human E1 auditing.
    It is not a replacement for the source-native page shown to a harness.
    """

    title = document_title(
        record.get("title"),
        source_id=record.get("source_id"),
        page_type=record.get("page_type"),
        archive_entry_path=record.get("archive_entry_path"),
    )
    canonical_url = str(record.get("canonical_url") or "")
    page_type = str(record.get("page_type") or "document")
    blocks = list(record.get("blocks") or [])
    fields = list(record.get("structured_fields") or [])
    interactions = list(record.get("interactions") or [])
    links = list(record.get("links") or [])
    metadata = dict(record.get("metadata") or {})

    identity_fields = [
        ("source_id", record.get("source_id")),
        ("canonical_url", canonical_url),
        ("archive_entry_path", record.get("archive_entry_path")),
        ("mime_type", record.get("mime_type")),
        ("raw_content_hash", record.get("raw_content_hash")),
        (
            "capture_or_archive_locator",
            record.get("capture_or_archive_locator"),
        ),
    ]
    if "resource_content_omitted" in metadata:
        identity_fields.append((
            "resource_content_omitted",
            str(bool(metadata["resource_content_omitted"])).lower(),
        ))

    out = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{escape(title)}</title>",
        f'<meta name="dra-canonical-url" content="{escape(canonical_url, quote=True)}">',
        f'<meta name="dra-page-type" content="{escape(page_type, quote=True)}">',
        """<style>
        :root{color-scheme:light;font-family:system-ui,sans-serif}
        body{margin:0;background:#f6f7f9;color:#172033}
        main{max-width:1100px;margin:0 auto;padding:24px}
        section,nav,details{background:white;border:1px solid #d9dee8;
          border-radius:10px;margin:16px 0;padding:16px}
        .audit-banner{background:#fff5d6;border:1px solid #e3bd4d;
          border-radius:8px;padding:12px}
        dl{display:grid;grid-template-columns:minmax(170px,260px) 1fr;
          gap:6px 14px}dt{font-weight:650}dd{margin:0;overflow-wrap:anywhere}
        table{border-collapse:collapse;width:100%;margin:12px 0}
        th,td{border:1px solid #9da7b5;padding:7px;text-align:left;
          vertical-align:top}.audit-empty{background:#f1f3f6;min-width:1.5rem}
        article[data-dra-interaction-id]{border-left:3px solid #7e8da8;
          margin:10px 0 10px min(calc(var(--dra-depth) * 1.4rem),24rem);
          padding:10px 12px;background:#fafbfc}
        article header{font-size:.88rem;color:#4e5d73;margin-bottom:5px}
        .reply-relation{display:block;color:#6b4f00;font-weight:600}
        .canonical-block{padding:4px 0;border-bottom:1px dotted #dfe3e9}
        code{overflow-wrap:anywhere}
        </style>""",
        "</head><body>",
        f"<main><h1>{escape(title)}</h1>",
        '<p class="audit-banner"><strong>Canonical structural audit projection.</strong> '
        "This is not the source-site UI and is not served to benchmark harnesses.</p>",
    ]

    visible_identity = [
        (name, value) for name, value in identity_fields
        if value is not None and normalize_text(value)
    ]
    if visible_identity:
        omitted = str(bool(metadata.get("resource_content_omitted"))).lower()
        out.append(
            '<section id="document-identity" '
            f'data-dra-resource-omitted="{omitted}">'
            "<h2>Document identity and provenance</h2><dl>"
        )
        for name, value in visible_identity:
            out.append(
                f'<dt>{escape(name)}</dt><dd data-dra-identity-field="{escape(name, quote=True)}">'
                f"{escape(normalize_text(value))}</dd>"
            )
        out.append("</dl></section>")

    if fields:
        out.append('<section id="structured-fields"><h2>Structured fields</h2><dl>')
        for ordinal, field in enumerate(fields):
            name = normalize_text(field.get("name"))
            value = normalize_text(field.get("value"))
            unit = normalize_text(field.get("unit"))
            field_type = normalize_text(field.get("field_type"))
            provenance_locator = normalize_text(
                field.get("provenance_locator")
            )
            out.append(
                f"<dt>{escape(name)}</dt>"
                f'<dd data-dra-field-ordinal="{ordinal}" '
                f'data-dra-field-name="{escape(name, quote=True)}" '
                f'data-dra-field-value="{escape(value, quote=True)}" '
                f'data-dra-field-unit="{escape(unit, quote=True)}" '
                f'data-dra-field-type="{escape(field_type, quote=True)}" '
                f'data-dra-field-provenance="{escape(provenance_locator, quote=True)}">'
                f"{escape(value)}{(' ' + escape(unit)) if unit else ''}</dd>"
            )
        out.append("</dl></section>")

    if blocks:
        table_cells: dict[int, list[dict[str, Any]]] = {}
        table_captions: dict[int, str] = {}
        for block in blocks:
            structural = dict(block.get("structural") or {})
            table_index = structural.get("table_index")
            if not isinstance(table_index, int):
                continue
            if block.get("block_type") == "table_cell":
                table_cells.setdefault(table_index, []).append(block)
            elif block.get("block_type") == "table_caption":
                table_captions.setdefault(
                    table_index, normalize_text(block.get("text"))
                )
        if table_cells:
            out.append(
                '<section id="audit-table-projections">'
                "<h2>Reconstructed tables</h2>"
                "<p>Rendered from canonical row, logical-column, rowspan, "
                "and colspan coordinates.</p>"
            )
            for table_index in sorted(table_cells):
                cells = table_cells[table_index]
                row_indexes = [
                    int((cell.get("structural") or {}).get("row_index") or 0)
                    for cell in cells
                ]
                out.append(
                    f'<table data-dra-audit-table-index="{table_index}">'
                )
                caption = table_captions.get(table_index)
                if caption:
                    out.append(f"<caption>{escape(caption)}</caption>")
                out.append("<tbody>")
                for row_index in range(max(row_indexes, default=-1) + 1):
                    row_cells = [
                        cell for cell in cells
                        if int((cell.get("structural") or {}).get(
                            "row_index"
                        ) or 0) == row_index
                    ]
                    row_cells.sort(key=lambda cell: (
                        int((cell.get("structural") or {}).get(
                            "column_index"
                        ) or 0),
                        int((cell.get("structural") or {}).get(
                            "cell_index"
                        ) or 0),
                    ))
                    out.append(
                        f'<tr data-dra-audit-row-index="{row_index}">'
                    )
                    for cell in row_cells:
                        structural = dict(cell.get("structural") or {})
                        tag = "th" if structural.get("is_header") else "td"
                        column_index = int(
                            structural.get("column_index") or 0
                        )
                        rowspan = int(
                            structural.get("effective_rowspan")
                            or structural.get("rowspan")
                            or 1
                        )
                        colspan = int(
                            structural.get("effective_colspan")
                            or structural.get("colspan")
                            or 1
                        )
                        span_attrs = ""
                        if rowspan > 1:
                            span_attrs += f' rowspan="{rowspan}"'
                        if colspan > 1:
                            span_attrs += f' colspan="{colspan}"'
                        text = normalize_text(cell.get("text"))
                        empty_class = ' class="audit-empty"' if not text else ""
                        content = escape(text) if text else "&nbsp;"
                        out.append(
                            f'<{tag}{empty_class}{span_attrs} '
                            f'data-dra-audit-table-index="{table_index}" '
                            f'data-dra-audit-row-index="{row_index}" '
                            f'data-dra-audit-column-index="{column_index}">'
                            f"{content}</{tag}>"
                        )
                    out.append("</tr>")
                out.append("</tbody></table>")
            out.append("</section>")

        out.append(
            '<details id="document-blocks"><summary><strong>Canonical '
            "block stream</strong></summary>"
        )
        for ordinal, block in enumerate(blocks):
            attrs = (
                f'data-dra-canonical-block-ordinal="{ordinal}" '
                f'data-dra-block-type="{escape(str(block.get("block_type") or "paragraph"), quote=True)}" '
                f'data-dra-section-path="{_json_attr(block.get("section_path") or [])}" '
                f'data-dra-structural="{_json_attr(block.get("structural") or {})}" '
                f'data-dra-dom-path="{escape(str(block.get("dom_path") or ""), quote=True)}"'
            )
            out.append(
                f'<div class="canonical-block" {attrs}>'
                f"{escape(normalize_text(block.get('text')))}</div>"
            )
        out.append("</details>")

    if interactions:
        out.append('<section id="interactions"><h2>Interactions</h2>')
        interactions_by_id = {
            str(item.get("interaction_id") or ""): item
            for item in interactions
        }
        depth_cache: dict[str, int] = {}

        def interaction_depth(interaction_id: str, trail: set[str]) -> int:
            if interaction_id in depth_cache:
                return depth_cache[interaction_id]
            if interaction_id in trail:
                return 0
            current = interactions_by_id.get(interaction_id)
            parent_id = str(
                (current or {}).get("parent_interaction_id") or ""
            )
            if not parent_id or parent_id not in interactions_by_id:
                depth = 0
            else:
                depth = 1 + interaction_depth(
                    parent_id, trail | {interaction_id}
                )
            depth_cache[interaction_id] = depth
            return depth

        for ordinal, interaction in enumerate(interactions):
            interaction_id = str(interaction.get("interaction_id") or "")
            parent_id = str(
                interaction.get("parent_interaction_id") or ""
            )
            depth = interaction_depth(interaction_id, set())
            attrs = (
                f'data-dra-interaction-ordinal="{ordinal}" '
                f'data-dra-interaction-id="{escape(interaction_id, quote=True)}" '
                f'data-dra-parent-id="{escape(parent_id, quote=True)}" '
                f'data-dra-audit-depth="{depth}" '
                f'style="--dra-depth:{depth}" '
                f'data-dra-kind="{escape(str(interaction.get("kind") or "interaction"), quote=True)}" '
                f'data-dra-author-key="{escape(normalize_text(interaction.get("author_key")), quote=True)}" '
                f'data-dra-timestamp="{escape(normalize_text(interaction.get("timestamp")), quote=True)}" '
                f'data-dra-score="{escape(_display_number(interaction.get("score")) if interaction.get("score") is not None else "", quote=True)}" '
                f'data-dra-interaction-metadata="{_json_attr(interaction.get("metadata") or {})}"'
            )
            author = normalize_text(interaction.get("author_key"))
            timestamp = normalize_text(interaction.get("timestamp"))
            score = interaction.get("score")
            out.append(f"<article {attrs}>")
            out.append(
                f"<header>{escape(author)} | {escape(timestamp)}"
                f"{(' | score ' + escape(_display_number(score))) if score is not None else ''}</header>"
            )
            if parent_id:
                parent = interactions_by_id.get(parent_id) or {}
                parent_label = normalize_text(parent.get("author_key"))
                if not parent_label:
                    parent_label = parent_id
                out.append(
                    '<span class="reply-relation">'
                    f"Reply depth {depth}; parent: {escape(parent_label)}"
                    "</span>"
                )
            out.append(
                '<div data-dra-block-type="interaction" '
                f'data-dra-section-path="{_json_attr(["Interactions", str(interaction.get("kind") or "interaction")])}" '
                f'data-dra-structural="{_json_attr({"interaction_id": interaction.get("interaction_id"), "parent_interaction_id": interaction.get("parent_interaction_id")})}">'
                f"{escape(normalize_text(interaction.get('text')))}</div>"
            )
            out.append("</article>")
        out.append("</section>")

    if links:
        out.append('<nav id="outgoing-links"><h2>Links</h2><ul>')
        for ordinal, link in enumerate(links):
            href = str(link.get("canonical_target") or link.get("href") or "")
            original_href = str(link.get("href") or "")
            dom_path = str(link.get("dom_path") or "")
            label = normalize_text(link.get("anchor_text")) or href
            out.append(
                f'<li><a data-dra-link-ordinal="{ordinal}" '
                f'data-dra-original-href="{escape(original_href, quote=True)}" '
                f'data-dra-dom-path="{escape(dom_path, quote=True)}" '
                f'href="{escape(href, quote=True)}">{escape(label)}</a></li>'
            )
        out.append("</ul></nav>")

    out.append("</main></body></html>\n")
    return "".join(out)


def projection_roundtrip_failures(
    rendered: str,
    *,
    canonical_url: str,
    artifact: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return exact canonical-artifact mismatches in an audit projection.

    The legacy gate only asked whether every original text occurred somewhere
    in the reparsed page.  That allowed lost empty cells, changed coordinates,
    or wrong interaction parents to pass.  This gate compares every serialized
    block, field, interaction, and link in order.
    """

    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "beautifulsoup4 is required for E1 projection audit"
        ) from exc

    failures: list[dict[str, Any]] = []
    soup = BeautifulSoup(rendered, "lxml")
    expected_blocks = list(artifact.get("blocks") or [])
    container = soup.select_one("#document-blocks")
    if expected_blocks and container is None:
        failures.append({"reason": "canonical_block_stream_missing"})
    else:
        actual_blocks = (
            parse_html_document(
                str(container), base_url=canonical_url
            )["blocks"]
            if container is not None else []
        )

        def block_signature(block: Mapping[str, Any]) -> tuple[Any, ...]:
            return (
                str(block.get("block_type") or "paragraph"),
                tuple(block.get("section_path") or []),
                str(block.get("dom_path") or ""),
                normalize_text(block.get("text")),
                canonical_json(block.get("structural") or {}),
            )

        expected_signatures = [
            block_signature(block) for block in expected_blocks
        ]
        actual_signatures = [
            block_signature(block) for block in actual_blocks
        ]
        if expected_signatures != actual_signatures:
            mismatch = next((
                index for index, (expected, actual) in enumerate(
                    zip(expected_signatures, actual_signatures)
                ) if expected != actual
            ), min(len(expected_signatures), len(actual_signatures)))
            failures.append({
                "reason": "canonical_block_stream_mismatch",
                "expected_count": len(expected_signatures),
                "actual_count": len(actual_signatures),
                "first_mismatch_ordinal": mismatch,
            })

    expected_fields = []
    for ordinal, field in enumerate(artifact.get("structured_fields") or []):
        expected_fields.append((
            ordinal,
            normalize_text(field.get("name")),
            normalize_text(field.get("value")),
            normalize_text(field.get("unit")),
            normalize_text(field.get("field_type")),
            normalize_text(field.get("provenance_locator")),
        ))
    actual_fields = [(
        int(node.get("data-dra-field-ordinal") or 0),
        str(node.get("data-dra-field-name") or ""),
        str(node.get("data-dra-field-value") or ""),
        str(node.get("data-dra-field-unit") or ""),
        str(node.get("data-dra-field-type") or ""),
        str(node.get("data-dra-field-provenance") or ""),
    ) for node in soup.select("[data-dra-field-ordinal]")]
    if expected_fields != actual_fields:
        failures.append({
            "reason": "structured_field_stream_mismatch",
            "expected_count": len(expected_fields),
            "actual_count": len(actual_fields),
        })

    expected_interactions = []
    for ordinal, interaction in enumerate(artifact.get("interactions") or []):
        expected_interactions.append((
            ordinal,
            str(interaction.get("interaction_id") or ""),
            str(interaction.get("parent_interaction_id") or ""),
            str(interaction.get("kind") or "interaction"),
            normalize_text(interaction.get("author_key")),
            normalize_text(interaction.get("timestamp")),
            (
                _display_number(interaction.get("score"))
                if interaction.get("score") is not None else ""
            ),
            normalize_text(interaction.get("text")),
            canonical_json(interaction.get("metadata") or {}),
        ))
    actual_interactions = []
    for node in soup.select("article[data-dra-interaction-ordinal]"):
        text_node = node.select_one('[data-dra-block-type="interaction"]')
        actual_interactions.append((
            int(node.get("data-dra-interaction-ordinal") or 0),
            str(node.get("data-dra-interaction-id") or ""),
            str(node.get("data-dra-parent-id") or ""),
            str(node.get("data-dra-kind") or "interaction"),
            str(node.get("data-dra-author-key") or ""),
            str(node.get("data-dra-timestamp") or ""),
            str(node.get("data-dra-score") or ""),
            normalize_text(
                text_node.get_text(" ", strip=True) if text_node else ""
            ),
            str(node.get("data-dra-interaction-metadata") or "{}"),
        ))
    if expected_interactions != actual_interactions:
        failures.append({
            "reason": "interaction_stream_mismatch",
            "expected_count": len(expected_interactions),
            "actual_count": len(actual_interactions),
        })

    expected_links = []
    for ordinal, link in enumerate(artifact.get("links") or []):
        expected_links.append((
            ordinal,
            str(link.get("href") or link.get("canonical_target") or ""),
            str(
                link.get("canonical_target")
                or urljoin(canonical_url, str(link.get("href") or ""))
            ),
            normalize_text(link.get("anchor_text"))
            or str(link.get("canonical_target") or link.get("href") or ""),
            str(link.get("dom_path") or ""),
        ))
    actual_links = [(
        int(node.get("data-dra-link-ordinal") or 0),
        str(node.get("data-dra-original-href") or ""),
        urljoin(canonical_url, str(node.get("href") or "")),
        normalize_text(node.get_text(" ", strip=True)),
        str(node.get("data-dra-dom-path") or ""),
    ) for node in soup.select("#outgoing-links [data-dra-link-ordinal]")]
    if expected_links != actual_links:
        failures.append({
            "reason": "link_stream_mismatch",
            "expected_count": len(expected_links),
            "actual_count": len(actual_links),
        })
    return failures


SCHEMA_SQL = """
PRAGMA foreign_keys=ON;
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
CREATE TABLE documents (
    page_snapshot_id TEXT PRIMARY KEY,
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
    body_text TEXT NOT NULL,
    raw_content_hash TEXT NOT NULL,
    parsed_content_hash TEXT NOT NULL,
    rendered_content_hash TEXT NOT NULL,
    capture_or_archive_locator TEXT NOT NULL,
    rights_class TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    renderer_version TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    UNIQUE(pack_id, source_id)
);
CREATE TABLE blocks (
    span_id TEXT PRIMARY KEY,
    page_snapshot_id TEXT NOT NULL REFERENCES documents(page_snapshot_id),
    ordinal INTEGER NOT NULL,
    section_path_json TEXT NOT NULL,
    block_type TEXT NOT NULL,
    dom_path TEXT,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    structural_json TEXT NOT NULL,
    locator_version TEXT NOT NULL,
    UNIQUE(page_snapshot_id, ordinal)
);
CREATE TABLE links (
    link_id TEXT PRIMARY KEY,
    page_snapshot_id TEXT NOT NULL REFERENCES documents(page_snapshot_id),
    span_id TEXT REFERENCES blocks(span_id),
    ordinal INTEGER NOT NULL,
    href TEXT NOT NULL,
    canonical_target TEXT NOT NULL,
    anchor_text TEXT,
    dom_path TEXT,
    target_page_snapshot_id TEXT,
    UNIQUE(page_snapshot_id, ordinal)
);
CREATE TABLE structured_fields (
    field_id TEXT PRIMARY KEY,
    page_snapshot_id TEXT NOT NULL REFERENCES documents(page_snapshot_id),
    ordinal INTEGER NOT NULL,
    name TEXT NOT NULL,
    value TEXT,
    unit TEXT,
    field_type TEXT,
    provenance_locator TEXT,
    metadata_json TEXT NOT NULL,
    UNIQUE(page_snapshot_id, ordinal)
);
CREATE TABLE interactions (
    interaction_id TEXT PRIMARY KEY,
    page_snapshot_id TEXT NOT NULL REFERENCES documents(page_snapshot_id),
    parent_interaction_id TEXT,
    kind TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    author_key TEXT,
    timestamp TEXT,
    score REAL,
    text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    UNIQUE(page_snapshot_id, ordinal)
);
CREATE TABLE aliases (
    alias TEXT NOT NULL,
    page_snapshot_id TEXT NOT NULL REFERENCES documents(page_snapshot_id),
    alias_type TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    PRIMARY KEY(normalized_alias, page_snapshot_id, alias_type)
);
CREATE TABLE duplicate_clusters (
    content_hash TEXT NOT NULL,
    page_snapshot_id TEXT NOT NULL REFERENCES documents(page_snapshot_id),
    cluster_size INTEGER NOT NULL,
    PRIMARY KEY(content_hash, page_snapshot_id)
);
CREATE VIRTUAL TABLE search_fts USING fts5(
    page_snapshot_id UNINDEXED,
    title,
    aliases,
    body_text,
    tokenize='unicode61 remove_diacritics 2'
);
CREATE INDEX idx_documents_pack_type ON documents(pack_id, page_type);
CREATE INDEX idx_blocks_page_type ON blocks(page_snapshot_id, block_type);
CREATE INDEX idx_links_target ON links(canonical_target);
CREATE INDEX idx_interactions_page_parent ON interactions(page_snapshot_id, parent_interaction_id);
CREATE INDEX idx_aliases_page ON aliases(page_snapshot_id, normalized_alias, alias_type);
"""


@dataclass
class AddResult:
    page_snapshot_id: str
    canonical_url: str
    block_count: int
    link_count: int
    structured_field_count: int
    interaction_count: int


class WorldIndexWriter:
    """Write and validate one deterministic E1 SQLite World Index."""

    def __init__(self, path: str | Path, *, snapshot_id: str, overwrite: bool = False):
        self.path = Path(path)
        if self.path.exists():
            if not overwrite:
                raise FileExistsError(self.path)
            self.path.unlink()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_id = snapshot_id
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_SQL)
        self.set_metadata("schema_version", E1_SCHEMA_VERSION)
        self.set_metadata("snapshot_id", snapshot_id)
        self.set_metadata("parser_version", PARSER_VERSION)
        self.set_metadata("renderer_version", RENDERER_VERSION)
        self.set_metadata("search_version", SEARCH_VERSION)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.commit()
            self.conn.close()
            self.conn = None  # type: ignore[assignment]

    def __enter__(self) -> "WorldIndexWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc is None:
            self.finalize()
        self.close()

    def set_metadata(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO metadata(key,value_json) VALUES (?,?)",
            (key, canonical_json(value)),
        )

    def add_record_atomic(
        self, raw_record: Mapping[str, Any]
    ) -> AddResult:
        """Add one record under a savepoint and remove all partial rows on error."""

        # A SAVEPOINT opened without an outer transaction becomes the outermost
        # transaction, so RELEASE would fsync every record after a caller's
        # periodic commit.  Keep a batch transaction open; callers retain full
        # control over checkpoint commits while each record remains rollback-
        # isolated by the nested savepoint.
        if not self.conn.in_transaction:
            self.conn.execute("BEGIN")
        self.conn.execute("SAVEPOINT dra_add_record")
        try:
            result = self.add_record(raw_record)
        except Exception:
            self.conn.execute("ROLLBACK TO SAVEPOINT dra_add_record")
            self.conn.execute("RELEASE SAVEPOINT dra_add_record")
            raise
        self.conn.execute("RELEASE SAVEPOINT dra_add_record")
        return result

    def add_record(self, raw_record: Mapping[str, Any]) -> AddResult:
        record = dict(raw_record)
        pack_id = str(record["pack_id"])
        source_id = str(record["source_id"])
        canonical_url = str(record["canonical_url"])
        page_snapshot_id = str(
            record.get("page_snapshot_id")
            or stable_id("ps", self.snapshot_id, pack_id, source_id)
        )

        blocks = [dict(block) for block in (record.get("blocks") or [])]
        links = [dict(link) for link in (record.get("links") or [])]
        html_content = record.get("html_content")
        parsed_title = ""
        if html_content:
            parsed = parse_html_document(str(html_content), base_url=canonical_url)
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
        interactions = [dict(item) for item in (record.get("interactions") or [])]
        fields = [dict(item) for item in (record.get("structured_fields") or [])]

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
            source_interaction_id = interaction.pop(
                "_source_interaction_id"
            )
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
            metadata.setdefault(
                "source_interaction_id", source_interaction_id
            )
            if source_parent_id is not None:
                metadata.setdefault(
                    "source_parent_interaction_id",
                    str(source_parent_id),
                )
            interaction["metadata"] = metadata
            interaction.setdefault("ordinal", ordinal)

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
        raw_hash = str(record.get("raw_content_hash") or sha256_text(canonical_json(record.get("raw") or record)))
        parsed_hash = sha256_text(body_text)
        rendered_hash = sha256_text(rendered_html)
        metadata = dict(record.get("metadata") or {})

        self.conn.execute(
            """
            INSERT INTO documents(
              page_snapshot_id,pack_id,source_id,canonical_url,archive_entry_path,
              redirect_target,http_status,source_family,page_type,snapshot_id,
              mime_type,language,title,body_text,raw_content_hash,
              parsed_content_hash,rendered_content_hash,capture_or_archive_locator,
              rights_class,parser_version,renderer_version,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                page_snapshot_id,
                pack_id,
                source_id,
                canonical_url,
                record.get("archive_entry_path"),
                record.get("redirect_target"),
                record.get("http_status"),
                str(record.get("source_family") or pack_id),
                str(record.get("page_type") or "document"),
                self.snapshot_id,
                record.get("mime_type"),
                record.get("language"),
                title,
                body_text,
                raw_hash,
                parsed_hash,
                rendered_hash,
                str(record.get("capture_or_archive_locator") or f"{pack_id}:{source_id}"),
                str(record.get("rights_class") or "frozen-benchmark-use"),
                PARSER_VERSION,
                RENDERER_VERSION,
                canonical_json(metadata),
            ),
        )

        for ordinal, block in enumerate(blocks):
            span_id = str(block.get("span_id") or stable_id("span", page_snapshot_id, ordinal))
            text = normalize_text(block.get("text"))
            self.conn.execute(
                """
                INSERT INTO blocks(
                  span_id,page_snapshot_id,ordinal,section_path_json,block_type,
                  dom_path,char_start,char_end,text,text_hash,structural_json,
                  locator_version
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    span_id,
                    page_snapshot_id,
                    ordinal,
                    canonical_json(block.get("section_path") or []),
                    str(block.get("block_type") or "paragraph"),
                    block.get("dom_path"),
                    int(block.get("char_start") or 0),
                    int(block.get("char_end") or 0),
                    text,
                    sha256_text(text),
                    canonical_json(block.get("structural") or {}),
                    LOCATOR_VERSION,
                ),
            )

        for ordinal, link in enumerate(links):
            self.conn.execute(
                """
                INSERT INTO links(
                  link_id,page_snapshot_id,span_id,ordinal,href,canonical_target,
                  anchor_text,dom_path,target_page_snapshot_id
                ) VALUES (?,?,?,?,?,?,?,?,NULL)
                """,
                (
                    stable_id("link", page_snapshot_id, ordinal),
                    page_snapshot_id,
                    link.get("span_id"),
                    ordinal,
                    str(link.get("href") or link.get("canonical_target") or ""),
                    str(link.get("canonical_target") or urljoin(canonical_url, str(link.get("href") or ""))),
                    normalize_text(link.get("anchor_text")),
                    link.get("dom_path"),
                ),
            )

        for ordinal, field in enumerate(fields):
            self.conn.execute(
                """
                INSERT INTO structured_fields(
                  field_id,page_snapshot_id,ordinal,name,value,unit,field_type,
                  provenance_locator,metadata_json
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    stable_id("field", page_snapshot_id, ordinal),
                    page_snapshot_id,
                    ordinal,
                    normalize_text(field.get("name")),
                    normalize_text(field.get("value")),
                    normalize_text(field.get("unit")),
                    field.get("field_type"),
                    field.get("provenance_locator"),
                    canonical_json(field.get("metadata") or {}),
                ),
            )

        for ordinal, interaction in enumerate(interactions):
            text = normalize_text(interaction.get("text"))
            self.conn.execute(
                """
                INSERT INTO interactions(
                  interaction_id,page_snapshot_id,parent_interaction_id,kind,
                  ordinal,author_key,timestamp,score,text,text_hash,metadata_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(interaction["interaction_id"]),
                    page_snapshot_id,
                    interaction.get("parent_interaction_id"),
                    str(interaction.get("kind") or "interaction"),
                    ordinal,
                    normalize_text(interaction.get("author_key")),
                    interaction.get("timestamp"),
                    interaction.get("score"),
                    text,
                    sha256_text(text),
                    canonical_json(interaction.get("metadata") or {}),
                ),
            )

        aliases = {(title, "title"), (source_id, "source_id")}
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
            aliases.add((alias_text, alias_type))
        for alias, alias_type in sorted(aliases):
            if not alias:
                continue
            self.conn.execute(
                "INSERT OR IGNORE INTO aliases(alias,page_snapshot_id,alias_type,normalized_alias) VALUES (?,?,?,?)",
                (alias, page_snapshot_id, alias_type, alias.casefold()),
            )

        return AddResult(
            page_snapshot_id=page_snapshot_id,
            canonical_url=canonical_url,
            block_count=len(blocks),
            link_count=len(links),
            structured_field_count=len(fields),
            interaction_count=len(interactions),
        )

    def finalize(self) -> None:
        self.conn.execute(
            """
            UPDATE links
               SET target_page_snapshot_id = (
                   SELECT d.page_snapshot_id FROM documents d
                    WHERE d.canonical_url = links.canonical_target
               )
             WHERE target_page_snapshot_id IS NULL
            """
        )
        self.conn.execute("DELETE FROM duplicate_clusters")
        self.conn.execute(
            """
            INSERT INTO duplicate_clusters(content_hash,page_snapshot_id,cluster_size)
            WITH duplicate_hashes AS (
              SELECT parsed_content_hash,COUNT(*) AS cluster_size
                FROM documents
               WHERE trim(body_text) != ''
               GROUP BY parsed_content_hash
              HAVING COUNT(*) > 1
            )
            SELECT d.parsed_content_hash,d.page_snapshot_id,h.cluster_size
              FROM documents d
              JOIN duplicate_hashes h
                ON h.parsed_content_hash=d.parsed_content_hash
            """
        )
        self.conn.execute("DELETE FROM search_fts")
        self.conn.execute(
            """
            INSERT INTO search_fts(page_snapshot_id,title,aliases,body_text)
            SELECT d.page_snapshot_id,d.title,
                   COALESCE((
                     SELECT group_concat(alias, ' ')
                       FROM (
                         SELECT a.alias
                           FROM aliases a
                          WHERE a.page_snapshot_id=d.page_snapshot_id
                          ORDER BY a.normalized_alias,a.alias_type
                       )
                   ),''),
                   trim(
                     d.body_text || ' ' ||
                     COALESCE((
                       SELECT group_concat(field_text, ' ')
                         FROM (
                           SELECT sf.name || ' ' || COALESCE(sf.value,'')
                                  || ' ' || COALESCE(sf.unit,'')
                                    AS field_text
                             FROM structured_fields sf
                            WHERE sf.page_snapshot_id=d.page_snapshot_id
                            ORDER BY sf.ordinal
                         )
                     ),'')
                   )
              FROM documents d
             ORDER BY d.page_snapshot_id
            """
        )
        self.conn.commit()

    def logical_digest(self) -> str:
        """Hash ordered logical rows, avoiding SQLite file-header variance."""

        table_order = {
            "metadata": "key",
            "documents": "page_snapshot_id",
            "blocks": "page_snapshot_id,ordinal",
            "links": "page_snapshot_id,ordinal",
            "structured_fields": "page_snapshot_id,ordinal",
            "interactions": "page_snapshot_id,ordinal",
            "aliases": "normalized_alias,page_snapshot_id,alias_type",
            "duplicate_clusters": "content_hash,page_snapshot_id",
            # finalize() inserts FTS rows in page_snapshot_id order.  rowid is
            # therefore the stable compact traversal key; ordering by every
            # long text column caused a multi-terabyte logical scan on 1%.
            "search_fts": "rowid",
        }
        digest = sha256()
        for table, order in table_order.items():
            columns = [row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")]
            if not columns:
                raise RuntimeError(f"missing schema table: {table}")
            projection = ",".join(f'"{column}"' for column in columns)
            for row in self.conn.execute(
                f'SELECT {projection} FROM "{table}" ORDER BY {order}'
            ):
                digest.update(table.encode("utf-8"))
                digest.update(b"\0")
                digest.update(canonical_json(list(row)).encode("utf-8"))
                digest.update(b"\n")
        return digest.hexdigest()

    def census(self) -> dict[str, Any]:
        scalar = lambda sql: self.conn.execute(sql).fetchone()[0]
        by_pack = {
            row[0]: row[1]
            for row in self.conn.execute(
                "SELECT pack_id,COUNT(*) FROM documents GROUP BY pack_id ORDER BY pack_id"
            )
        }
        by_type = {
            f"{row[0]}:{row[1]}": row[2]
            for row in self.conn.execute(
                "SELECT pack_id,page_type,COUNT(*) FROM documents GROUP BY pack_id,page_type ORDER BY pack_id,page_type"
            )
        }
        return {
            "documents": scalar("SELECT COUNT(*) FROM documents"),
            "blocks": scalar("SELECT COUNT(*) FROM blocks"),
            "links": scalar("SELECT COUNT(*) FROM links"),
            "structured_fields": scalar("SELECT COUNT(*) FROM structured_fields"),
            "interactions": scalar("SELECT COUNT(*) FROM interactions"),
            "aliases": scalar("SELECT COUNT(*) FROM aliases"),
            "duplicate_clusters": scalar("SELECT COUNT(DISTINCT content_hash) FROM duplicate_clusters"),
            "documents_by_pack": by_pack,
            "documents_by_pack_and_type": by_type,
        }

    def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT f.page_snapshot_id,d.canonical_url,d.title,bm25(search_fts) AS score
              FROM search_fts f JOIN documents d USING(page_snapshot_id)
             WHERE search_fts MATCH ?
             ORDER BY score,d.page_snapshot_id
             LIMIT ?
            """,
            (query, limit),
        )
        return [dict(row) for row in rows]

    def document_artifact(
        self, page_snapshot_id: str
    ) -> dict[str, list[dict[str, Any]]]:
        blocks = [dict(row) for row in self.conn.execute(
            "SELECT block_type,section_path_json,dom_path,text,structural_json FROM blocks WHERE page_snapshot_id=? ORDER BY ordinal",
            (page_snapshot_id,),
        )]
        for block in blocks:
            block["section_path"] = json.loads(block.pop("section_path_json"))
            block["structural"] = json.loads(block.pop("structural_json"))
        fields = [dict(row) for row in self.conn.execute(
            "SELECT name,value,unit,field_type,provenance_locator,metadata_json FROM structured_fields WHERE page_snapshot_id=? ORDER BY ordinal",
            (page_snapshot_id,),
        )]
        for field in fields:
            field["metadata"] = json.loads(field.pop("metadata_json"))
        interactions = [dict(row) for row in self.conn.execute(
            "SELECT interaction_id,parent_interaction_id,kind,author_key,timestamp,score,text,metadata_json FROM interactions WHERE page_snapshot_id=? ORDER BY ordinal",
            (page_snapshot_id,),
        )]
        for interaction in interactions:
            interaction["metadata"] = json.loads(
                interaction.pop("metadata_json")
            )
        links = [dict(row) for row in self.conn.execute(
            "SELECT href,canonical_target,anchor_text,dom_path FROM links WHERE page_snapshot_id=? ORDER BY ordinal",
            (page_snapshot_id,),
        )]
        return {
            "blocks": blocks,
            "structured_fields": fields,
            "interactions": interactions,
            "links": links,
        }

    def render_by_id(self, page_snapshot_id: str) -> str:
        doc = self.conn.execute(
            "SELECT * FROM documents WHERE page_snapshot_id=?", (page_snapshot_id,)
        ).fetchone()
        if doc is None:
            raise KeyError(page_snapshot_id)
        artifact = self.document_artifact(page_snapshot_id)
        return render_document_html(
            {
                "source_id": doc["source_id"],
                "canonical_url": doc["canonical_url"],
                "page_type": doc["page_type"],
                "title": doc["title"],
                "archive_entry_path": doc["archive_entry_path"],
                "mime_type": doc["mime_type"],
                "raw_content_hash": doc["raw_content_hash"],
                "capture_or_archive_locator": doc[
                    "capture_or_archive_locator"
                ],
                "metadata": json.loads(doc["metadata_json"]),
                **artifact,
            }
        )

    def roundtrip_audit(self, page_ids: Iterable[str] | None = None) -> dict[str, Any]:
        if page_ids is None:
            page_ids = [row[0] for row in self.conn.execute(
                "SELECT page_snapshot_id FROM documents ORDER BY page_snapshot_id"
            )]
        checked = 0
        failures: list[dict[str, Any]] = []
        for page_id in page_ids:
            doc = self.conn.execute(
                "SELECT canonical_url,rendered_content_hash FROM documents WHERE page_snapshot_id=?",
                (page_id,),
            ).fetchone()
            if doc is None:
                failures.append({"page_snapshot_id": page_id, "reason": "missing_document"})
                continue
            rendered = self.render_by_id(page_id)
            checked += 1
            if sha256_text(rendered) != doc["rendered_content_hash"]:
                failures.append({"page_snapshot_id": page_id, "reason": "rendered_hash_mismatch"})
                continue
            artifact = self.document_artifact(page_id)
            projection_failures = projection_roundtrip_failures(
                rendered,
                canonical_url=doc["canonical_url"],
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


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    import gzip

    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no}: expected object")
            yield value


def write_jsonl(path: str | Path, records: Iterable[Mapping[str, Any]]) -> int:
    """Write canonical JSONL, with a reproducible gzip header when compressed."""

    import gzip
    import io

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    if path.suffix == ".gz":
        raw = path.open("wb")
        compressed = gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=6,
            fileobj=raw,
            mtime=0,
        )
        handle = io.TextIOWrapper(
            compressed, encoding="utf-8", newline="\n"
        )
    else:
        handle = path.open("wt", encoding="utf-8", newline="\n")
    with handle:
        for record in records:
            handle.write(canonical_json(record))
            handle.write("\n")
            count += 1
    return count
