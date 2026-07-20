#!/usr/bin/env python3
"""Export deterministic E1 records from frozen Magento, Postmill, and Kiwix.

Run this on the source host. Selection is based only on frozen top-level
identities. Benchmark queries, answer keys, evidence graphs, and witness URLs
are never read.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Iterator, Mapping, Sequence
from urllib.parse import quote, urljoin


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.world_index.e1 import (
    E1_SCHEMA_VERSION,
    SHARD_ALGORITHM,
    canonical_json,
    document_title,
    stable_bucket,
    stable_id,
)


DEFAULT_SNAPSHOT = "dra-world-v0-2026-07-19"
DEFAULT_ZIM = Path("/mnt/d/dr-eval-release-20260611/wiki/wikipedia_en_all_nopic.zim")
WIKI_BOOK = "wikipedia_en_all_nopic"
PACK_COMMERCE = "commerce-magento-v0"
PACK_COMMUNITY = "community-postmill-v0"
PACK_WIKIMEDIA = "wikimedia-zim-v0"
REQUIRED_PACK_NAMES = ("commerce", "community", "wikimedia")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def digest_text(value: str) -> str:
    return digest_bytes(value.encode("utf-8"))


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def text_from_html(value: Any) -> str:
    text = str(value or "")
    if "<" not in text or ">" not in text:
        return normalize_text(text)
    from bs4 import BeautifulSoup
    return normalize_text(BeautifulSoup(text, "lxml").get_text(" ", strip=True))


def quote_blocks(value: Any) -> list[str]:
    text = str(value or "")
    if not text or "<blockquote" not in text.casefold():
        return []
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, "lxml")
    return [
        normalize_text(tag.get_text(" ", strip=True))
        for tag in soup.find_all("blockquote")
    ]


def author_key(snapshot_id: str, public_handle: Any) -> str:
    return stable_id(
        "author", snapshot_id, normalize_text(public_handle), length=18
    )


def run_checked(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command[:5])}\n"
            f"stderr: {result.stderr[-4000:]}"
        )
    return result


def iter_json_process(command: Sequence[str]) -> Iterator[dict[str, Any]]:
    process = subprocess.Popen(
        list(command),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    assert process.stdout is not None
    for line_no, line in enumerate(process.stdout, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            process.kill()
            raise RuntimeError(
                f"invalid JSON at line {line_no}: {line[:500]!r}"
            ) from exc
        if not isinstance(value, dict):
            process.kill()
            raise RuntimeError("database exporter returned a non-object row")
        yield value
    stderr = process.stderr.read() if process.stderr else ""
    returncode = process.wait()
    if returncode:
        raise RuntimeError(
            f"command failed ({returncode}): {' '.join(command[:5])}\n"
            f"stderr: {stderr[-4000:]}"
        )


def mysql_json(args: argparse.Namespace, sql: str) -> Iterator[dict[str, Any]]:
    command = [
        "docker", "exec", args.magento_container,
        "mysql", "--batch", "--raw", "--skip-column-names",
        f"--user={args.magento_user}",
        f"--password={args.magento_password}",
        args.magento_database, "--execute", sql,
    ]
    yield from iter_json_process(command)


def postgres_json(args: argparse.Namespace, sql: str) -> Iterator[dict[str, Any]]:
    wrapped = f"SELECT row_to_json(dra_row) FROM ({sql}) AS dra_row"
    command = [
        "docker", "exec", args.postmill_container,
        "psql", "--username", args.postmill_user,
        "--no-align", "--tuples-only", "--quiet", "--command", wrapped,
    ]
    yield from iter_json_process(command)


def batches(values: list[int], size: int = 400) -> Iterator[list[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def is_selected(
    args: argparse.Namespace, pack_id: str, source_id: Any
) -> bool:
    return (
        stable_bucket(
            args.snapshot_id, pack_id, str(source_id), modulus=args.modulus
        )
        == args.bucket
    )


def writer(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = path.open("wb")
    compressed = gzip.GzipFile(
        filename="",
        mode="wb",
        compresslevel=6,
        fileobj=raw,
        mtime=0,
    )
    return io.TextIOWrapper(
        compressed, encoding="utf-8", newline="\n"
    )


def write_record(handle, record: Mapping[str, Any]) -> None:
    handle.write(canonical_json(record))
    handle.write("\n")


def source_image_id(container: str) -> str:
    result = run_checked(
        ["docker", "inspect", "--format={{.Image}}", container]
    )
    return result.stdout.strip().strip("'")


def tool_version(command: Sequence[str]) -> str:
    """Capture version output regardless of whether a CLI uses stdout/stderr."""

    result = run_checked(command)
    return normalize_text(result.stdout or result.stderr)


def wiki_served_path(path: str) -> str:
    """Map a libzim entry path to the path exposed by kiwix-serve.

    Older ZIMs expose a namespace prefix such as ``A/`` in ``Entry.path``;
    newer bindings may return an article path without that prefix.  Preserve
    explicit namespaces and add the article namespace only when absent.
    """

    clean = str(path or "").lstrip("/")
    if re.match(r"^(?:[A-Za-z]|-)/", clean):
        return clean
    return f"A/{clean}"


def html_soft_redirect(html: str) -> str | None:
    """Return a meta-refresh target used as a soft redirect, if present."""

    # ZIM soft redirects put the meta tag in ``head``.  Avoid constructing a
    # BeautifulSoup tree for every normal article in the 1% full-corpus pass.
    # The bounded prefix also avoids a second full-size lowercase allocation.
    head_probe = (html or "")[:16_384].casefold()
    if "http-equiv" not in head_probe or "refresh" not in head_probe:
        return None

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
    for meta in soup.find_all("meta"):
        if normalize_text(meta.get("http-equiv")).casefold() != "refresh":
            continue
        content = str(meta.get("content") or "")
        match = re.search(
            r"(?:^|;)\s*url\s*=\s*(['\"]?)(.*?)\1\s*$",
            content,
            flags=re.IGNORECASE,
        )
        if match and normalize_text(match.group(2)):
            return normalize_text(match.group(2))
    return None


def export_commerce(
    args: argparse.Namespace, out: Path
) -> dict[str, Any]:
    started = time.perf_counter()
    population_sql = """
      SELECT JSON_OBJECT(
        'entity_id',p.entity_id,'sku',p.sku,'type_id',p.type_id,
        'attribute_set_id',p.attribute_set_id,
        'created_at',CAST(p.created_at AS CHAR),
        'updated_at',CAST(p.updated_at AS CHAR),
        'url_key',url_key.value,'name',product_name.value
      )
      FROM catalog_product_entity p
      LEFT JOIN catalog_product_entity_varchar url_key
        ON url_key.entity_id=p.entity_id
       AND url_key.attribute_id=121 AND url_key.store_id=0
      LEFT JOIN catalog_product_entity_varchar product_name
        ON product_name.entity_id=p.entity_id
       AND product_name.attribute_id=73 AND product_name.store_id=0
      ORDER BY p.entity_id
    """
    population = list(mysql_json(args, population_sql))
    selected_rows = [
        row for row in population
        if is_selected(args, PACK_COMMERCE, row["entity_id"])
    ]
    selected_ids = [int(row["entity_id"]) for row in selected_rows]
    selected_set = set(selected_ids)
    url_by_id = {
        int(row["entity_id"]): normalize_text(row.get("url_key"))
        for row in population if row.get("url_key")
    }
    data: dict[int, dict[str, Any]] = {
        int(row["entity_id"]): {
            "base": row, "eav": [], "categories": [], "stock": [],
            "relations": [], "reviews": {},
        }
        for row in selected_rows
    }

    for group in batches(selected_ids):
        ids = ",".join(str(value) for value in group)
        for backend in ("varchar", "text", "decimal", "int", "datetime"):
            sql = f"""
              SELECT JSON_OBJECT(
                'entity_id',v.entity_id,'attribute_code',a.attribute_code,
                'backend_type','{backend}','store_id',v.store_id,
                'value',CAST(v.value AS CHAR)
              )
              FROM catalog_product_entity_{backend} v
              JOIN eav_attribute a ON a.attribute_id=v.attribute_id
              WHERE v.entity_id IN ({ids})
              ORDER BY v.entity_id,a.attribute_code,v.store_id
            """
            for row in mysql_json(args, sql):
                data[int(row["entity_id"])]["eav"].append(row)

        sql = f"""
          SELECT JSON_OBJECT(
            'entity_id',cp.product_id,'category_id',cp.category_id,
            'position',cp.position,'category_name',cn.value
          )
          FROM catalog_category_product cp
          LEFT JOIN catalog_category_entity_varchar cn
            ON cn.entity_id=cp.category_id
           AND cn.attribute_id=(
             SELECT attribute_id FROM eav_attribute
              WHERE entity_type_id=3 AND attribute_code='name' LIMIT 1
           ) AND cn.store_id=0
          WHERE cp.product_id IN ({ids})
          ORDER BY cp.product_id,cp.category_id
        """
        for row in mysql_json(args, sql):
            data[int(row["entity_id"])]["categories"].append(row)

        sql = f"""
          SELECT JSON_OBJECT(
            'entity_id',product_id,'stock_id',stock_id,
            'qty',CAST(qty AS CHAR),'is_in_stock',is_in_stock,
            'manage_stock',manage_stock
          )
          FROM cataloginventory_stock_item
          WHERE product_id IN ({ids})
          ORDER BY product_id,stock_id
        """
        for row in mysql_json(args, sql):
            data[int(row["entity_id"])]["stock"].append(row)

        sql = f"""
          SELECT JSON_OBJECT(
            'entity_id',r.entity_pk_value,'review_id',r.review_id,
            'created_at',CAST(r.created_at AS CHAR),'status_id',r.status_id,
            'title',d.title,'detail',d.detail,'nickname',d.nickname
          )
          FROM review r LEFT JOIN review_detail d ON d.review_id=r.review_id
          WHERE r.entity_pk_value IN ({ids})
          ORDER BY r.entity_pk_value,r.review_id,d.detail_id
        """
        for row in mysql_json(args, sql):
            product_id = int(row["entity_id"])
            data[product_id]["reviews"].setdefault(
                int(row["review_id"]), {**row, "votes": []}
            )

        sql = f"""
          SELECT JSON_OBJECT(
            'entity_id',r.entity_pk_value,'review_id',v.review_id,
            'rating_id',v.rating_id,'value',v.value,'percent',v.percent
          )
          FROM rating_option_vote v JOIN review r ON r.review_id=v.review_id
          WHERE r.entity_pk_value IN ({ids})
          ORDER BY r.entity_pk_value,v.review_id,v.rating_id
        """
        for row in mysql_json(args, sql):
            product_id = int(row["entity_id"])
            review = data[product_id]["reviews"].get(int(row["review_id"]))
            if review is not None:
                review["votes"].append(row)

        sql = f"""
          SELECT JSON_OBJECT(
            'relation_type','catalog_product_relation',
            'parent_id',parent_id,'child_id',child_id
          )
          FROM catalog_product_relation
          WHERE parent_id IN ({ids}) OR child_id IN ({ids})
          UNION ALL
          SELECT JSON_OBJECT(
            'relation_type','catalog_product_super_link',
            'parent_id',parent_id,'child_id',product_id
          )
          FROM catalog_product_super_link
          WHERE parent_id IN ({ids}) OR product_id IN ({ids})
        """
        for row in mysql_json(args, sql):
            for endpoint in (int(row["parent_id"]), int(row["child_id"])):
                if endpoint in selected_set:
                    data[endpoint]["relations"].append(row)

    output = out / "records" / "commerce.jsonl.gz"
    with writer(output) as handle:
        for product_id in sorted(data):
            item = data[product_id]
            base = item["base"]
            preferred: dict[str, dict[str, Any]] = {}
            for field in item["eav"]:
                code = str(field["attribute_code"])
                prior = preferred.get(code)
                if prior is None or int(field.get("store_id") or 0) < int(
                    prior.get("store_id") or 0
                ):
                    preferred[code] = field

            url_key = normalize_text(base.get("url_key"))
            served_key = url_key or f"catalog-product-{product_id}"
            canonical_url = (
                f"http://localhost:7770/"
                f"{quote(served_key, safe='-._~')}.html"
            )
            title = (
                normalize_text(base.get("name"))
                or normalize_text(base.get("sku"))
                or str(product_id)
            )
            blocks = [{
                "block_type": "heading", "section_path": [title],
                "dom_path": "db:catalog_product_entity/name", "text": title,
                "structural": {"attribute_code": "name"},
            }]
            for code, section in (
                ("short_description", "Overview"),
                ("description", "Description"),
            ):
                field = preferred.get(code)
                value = text_from_html(field.get("value")) if field else ""
                if value:
                    blocks.append({
                        "block_type": "paragraph",
                        "section_path": [section],
                        "dom_path": f"db:catalog_product_entity_text/{code}",
                        "text": value,
                        "structural": {
                            "attribute_code": code,
                            "store_id": field.get("store_id"),
                        },
                    })

            fields = [
                {"name": "entity_id", "value": product_id,
                 "field_type": "identifier"},
                {"name": "sku", "value": base.get("sku"),
                 "field_type": "identifier"},
                {"name": "type_id", "value": base.get("type_id"),
                 "field_type": "product_type"},
            ]
            for code, field in sorted(preferred.items()):
                if code in {"description", "short_description", "name", "url_key"}:
                    continue
                fields.append({
                    "name": code, "value": field.get("value"),
                    "field_type": field.get("backend_type"),
                    "provenance_locator": (
                        f"db:catalog_product_entity_"
                        f"{field.get('backend_type')}/{code}/"
                        f"store/{field.get('store_id')}"
                    ),
                })
            for stock in item["stock"]:
                fields.extend([
                    {"name": "stock_qty", "value": stock.get("qty"),
                     "field_type": "inventory"},
                    {"name": "is_in_stock", "value": stock.get("is_in_stock"),
                     "field_type": "inventory"},
                ])
            for category in item["categories"]:
                fields.append({
                    "name": "category",
                    "value": (
                        category.get("category_name")
                        or category.get("category_id")
                    ),
                    "field_type": "category",
                    "metadata": {
                        "category_id": category.get("category_id"),
                        "position": category.get("position"),
                    },
                })

            interactions = []
            reviews = sorted(
                item["reviews"].values(),
                key=lambda row: int(row["review_id"]),
            )
            for review in reviews:
                votes = review.get("votes") or []
                score = None
                if votes:
                    score = sum(
                        float(vote.get("percent") or 0) for vote in votes
                    ) / len(votes)
                interactions.append({
                    "interaction_id": f"review:{review['review_id']}",
                    "parent_interaction_id": None,
                    "kind": "review",
                    "author_key": author_key(
                        args.snapshot_id, review.get("nickname")
                    ),
                    "timestamp": review.get("created_at"),
                    "score": score,
                    "text": normalize_text(
                        f"{review.get('title') or ''} "
                        f"{review.get('detail') or ''}"
                    ),
                    "metadata": {
                        "status_id": review.get("status_id"),
                        "rating_votes": votes,
                        "display_name_hash": digest_text(
                            normalize_text(review.get("nickname"))
                        )[:16],
                    },
                })

            links = []
            for relation in sorted(item["relations"], key=canonical_json):
                other_id = int(
                    relation["child_id"]
                    if int(relation["parent_id"]) == product_id
                    else relation["parent_id"]
                )
                other_key = url_by_id.get(other_id)
                if other_key:
                    target = (
                        f"http://localhost:7770/"
                        f"{quote(other_key, safe='-._~')}.html"
                    )
                    links.append({
                        "href": target, "canonical_target": target,
                        "anchor_text": f"related product {other_id}",
                        "dom_path": f"db:{relation['relation_type']}",
                    })

            raw = {
                "base": base, "eav": item["eav"],
                "categories": item["categories"], "stock": item["stock"],
                "relations": item["relations"], "reviews": reviews,
            }
            write_record(handle, {
                "pack_id": PACK_COMMERCE,
                "source_id": str(product_id),
                "canonical_url": canonical_url,
                "source_family": "shop",
                "page_type": "product",
                "title": title,
                "mime_type": "text/html",
                "language": "en",
                "http_status": 200,
                "raw_content_hash": digest_text(canonical_json(raw)),
                "capture_or_archive_locator": (
                    f"mysql:{args.magento_database}/"
                    f"catalog_product_entity/{product_id}"
                ),
                "rights_class": "benchmark-local-restricted",
                "blocks": blocks,
                "structured_fields": fields,
                "interactions": interactions,
                "links": links,
                "aliases": [title, base.get("sku"), url_key],
                "metadata": {
                    "attribute_set_id": base.get("attribute_set_id"),
                    "created_at": base.get("created_at"),
                    "updated_at": base.get("updated_at"),
                    "raw_child_counts": {
                        "eav": len(item["eav"]),
                        "categories": len(item["categories"]),
                        "stock": len(item["stock"]),
                        "relations": len(item["relations"]),
                        "reviews": len(reviews),
                    },
                },
            })

    return {
        "pack_id": PACK_COMMERCE,
        "population": len(population),
        "selected": len(selected_ids),
        "missing_url_key": sum(
            1 for row in population if not row.get("url_key")
        ),
        "records_path": str(output.relative_to(out)),
        "records_sha256": digest_bytes(output.read_bytes()),
        "source_image_id": source_image_id(args.magento_container),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def export_community(
    args: argparse.Namespace, out: Path
) -> dict[str, Any]:
    started = time.perf_counter()
    population = list(postgres_json(args, """
      SELECT s.id, f.name AS forum_name
        FROM submissions s JOIN forums f ON f.id=s.forum_id
       ORDER BY s.id
    """))
    selected_ids = [
        int(row["id"])
        for row in population
        if is_selected(args, PACK_COMMUNITY, row["id"])
    ]
    submissions: dict[int, dict[str, Any]] = {}
    comments: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for group in batches(selected_ids):
        ids = ",".join(str(value) for value in group)
        for row in postgres_json(args, f"""
          SELECT s.id,s.forum_id,f.name AS forum_name,s.title,s.timestamp,
                 s.url,s.body,s.sticky,s.ranking,s.edited_at,s.moderated,
                 s.locked,s.last_active,s.comment_count,s.net_score,
                 s.visibility,s.media_type,u.username
            FROM submissions s
            JOIN forums f ON f.id=s.forum_id
            LEFT JOIN users u ON u.id=s.user_id
           WHERE s.id IN ({ids})
           ORDER BY s.id
        """):
            submissions[int(row["id"])] = row
        for row in postgres_json(args, f"""
          SELECT c.id,c.submission_id,c.parent_id,c.body,c.timestamp,
                 c.visibility,c.edited_at,c.moderated,c.net_score,u.username
            FROM comments c LEFT JOIN users u ON u.id=c.user_id
           WHERE c.submission_id IN ({ids})
           ORDER BY c.submission_id,c.timestamp,c.id
        """):
            comments[int(row["submission_id"])].append(row)

    output = out / "records" / "community.jsonl.gz"
    with writer(output) as handle:
        for submission_id in sorted(selected_ids):
            row = submissions[submission_id]
            forum = str(row["forum_name"])
            canonical_url = (
                f"http://localhost:9999/f/"
                f"{quote(forum, safe='-._~')}/{submission_id}"
            )
            title = normalize_text(row.get("title"))
            body = text_from_html(row.get("body"))
            root_id = f"post:{submission_id}"
            interactions = [{
                "interaction_id": root_id,
                "parent_interaction_id": None,
                "kind": "post",
                "author_key": author_key(
                    args.snapshot_id, row.get("username")
                ),
                "timestamp": row.get("timestamp"),
                "score": row.get("net_score"),
                "text": body or title,
                "metadata": {
                    "visibility": row.get("visibility"),
                    "edited_at": row.get("edited_at"),
                    "display_name_hash": digest_text(
                        normalize_text(row.get("username"))
                    )[:16],
                    "quotes": quote_blocks(row.get("body")),
                },
            }]
            for comment in comments.get(submission_id, []):
                parent = comment.get("parent_id")
                interactions.append({
                    "interaction_id": f"comment:{comment['id']}",
                    "parent_interaction_id": (
                        f"comment:{parent}" if parent is not None else root_id
                    ),
                    "kind": "reply",
                    "author_key": author_key(
                        args.snapshot_id, comment.get("username")
                    ),
                    "timestamp": comment.get("timestamp"),
                    "score": comment.get("net_score"),
                    "text": text_from_html(comment.get("body")),
                    "metadata": {
                        "visibility": comment.get("visibility"),
                        "edited_at": comment.get("edited_at"),
                        "display_name_hash": digest_text(
                            normalize_text(comment.get("username"))
                        )[:16],
                        "quotes": quote_blocks(comment.get("body")),
                    },
                })

            blocks = [{
                "block_type": "heading",
                "section_path": [title],
                "dom_path": "db:submissions/title",
                "text": title,
                "structural": {},
            }]
            if body:
                blocks.append({
                    "block_type": "post",
                    "section_path": [title, "Post"],
                    "dom_path": "db:submissions/body",
                    "text": body,
                    "structural": {"interaction_id": root_id},
                })

            raw = {
                "submission": row,
                "comments": comments.get(submission_id, []),
            }
            write_record(handle, {
                "pack_id": PACK_COMMUNITY,
                "source_id": str(submission_id),
                "canonical_url": canonical_url,
                "source_family": "community",
                "page_type": "forum_thread",
                "title": title,
                "mime_type": "text/html",
                "language": "en",
                "http_status": 200,
                "raw_content_hash": digest_text(canonical_json(raw)),
                "capture_or_archive_locator": (
                    f"postgres:postmill/submissions/{submission_id}"
                ),
                "rights_class": "benchmark-local-restricted",
                "blocks": blocks,
                "structured_fields": [
                    {"name": "forum", "value": forum,
                     "field_type": "forum"},
                    {"name": "timestamp", "value": row.get("timestamp"),
                     "field_type": "time"},
                    {"name": "net_score", "value": row.get("net_score"),
                     "field_type": "score"},
                    {"name": "comment_count",
                     "value": row.get("comment_count"),
                     "field_type": "count"},
                    {"name": "visibility",
                     "value": row.get("visibility"),
                     "field_type": "state"},
                    {"name": "locked", "value": row.get("locked"),
                     "field_type": "state"},
                ],
                "interactions": interactions,
                "links": ([{
                    "href": row["url"],
                    "canonical_target": row["url"],
                    "anchor_text": "external submission link",
                }] if row.get("url") else []),
                "aliases": [title, forum],
                "metadata": {
                    "forum_id": row.get("forum_id"),
                    "media_type": row.get("media_type"),
                    "sticky": row.get("sticky"),
                    "moderated": row.get("moderated"),
                    "raw_child_counts": {
                        "comments": len(comments.get(submission_id, []))
                    },
                },
            })

    return {
        "pack_id": PACK_COMMUNITY,
        "population": len(population),
        "selected": len(selected_ids),
        "selected_comments": sum(
            len(comments.get(value, [])) for value in selected_ids
        ),
        "records_path": str(output.relative_to(out)),
        "records_sha256": digest_bytes(output.read_bytes()),
        "source_image_id": source_image_id(args.postmill_container),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


@dataclass(frozen=True)
class WikimediaRecord:
    """One canonical source record plus streaming accounting metadata."""

    record: dict[str, Any]
    page_type: str
    content_bytes_read: int


def build_wikimedia_record(
    archive: Any,
    *,
    index: int,
    entry: Any,
) -> WikimediaRecord:
    """Build the shared E1/E2 record for one selected ZIM entry.

    Keeping this transformation in one function prevents the full E2 stream
    from drifting away from the parser contract validated on the E1 shard.
    """

    path = str(entry.path)
    served_path = wiki_served_path(path)
    canonical_url = (
        f"http://localhost:8090/content/{WIKI_BOOK}/"
        f"{quote(served_path, safe='/-._~()')}"
    )
    base = {
        "pack_id": PACK_WIKIMEDIA,
        "source_id": path,
        "canonical_url": canonical_url,
        "archive_entry_path": path,
        "source_family": "encyclopedia",
        "title": entry.title,
        "language": "en",
        "http_status": 200,
        "capture_or_archive_locator": (
            f"zim:{archive.uuid}/{index}/{path}"
        ),
        "rights_class": "CC-BY-SA/GFDL",
        "aliases": [entry.title, path.replace("_", " ")],
        "metadata": {
            "zim_entry_index": index,
            "zim_uuid": str(archive.uuid),
        },
    }
    if entry.is_redirect:
        target = entry.get_redirect_entry()
        target_served_path = wiki_served_path(target.path)
        redirect_url = (
            f"http://localhost:8090/content/{WIKI_BOOK}/"
            f"{quote(target_served_path, safe='/-._~()')}"
        )
        raw = canonical_json({
            "path": path,
            "title": entry.title,
            "redirect_target": target.path,
        })
        record = {
            **base,
            "page_type": "wiki_redirect",
            "mime_type": "text/html",
            "redirect_target": redirect_url,
            "raw_content_hash": digest_text(raw),
            "blocks": [],
            "links": [{
                "href": redirect_url,
                "canonical_target": redirect_url,
                "anchor_text": target.title,
            }],
            "structured_fields": [{
                "name": "redirect_target",
                "value": target.path,
                "field_type": "redirect",
            }],
        }
        return WikimediaRecord(record, "wiki_redirect", 0)

    item = entry.get_item()
    content = bytes(item.content)
    mime = item.mimetype
    raw_hash = digest_bytes(content)
    if mime == "text/html" or mime.startswith("application/xhtml"):
        decoded = content.decode("utf-8", "replace")
        soft_target = html_soft_redirect(decoded)
        if soft_target:
            redirect_url = urljoin(canonical_url, soft_target)
            record = {
                **base,
                "page_type": "wiki_redirect",
                "mime_type": mime,
                "redirect_target": redirect_url,
                "raw_content_hash": raw_hash,
                "blocks": [],
                "links": [{
                    "href": soft_target,
                    "canonical_target": redirect_url,
                    "anchor_text": entry.title,
                }],
                "structured_fields": [{
                    "name": "redirect_target",
                    "value": soft_target,
                    "field_type": "soft_redirect",
                }],
                "metadata": {
                    **base["metadata"],
                    "redirect_kind": "html_meta_refresh",
                },
            }
            return WikimediaRecord(
                record, "wiki_redirect", len(content)
            )
        record = {
            **base,
            "page_type": "wiki_article",
            "mime_type": mime,
            "raw_content_hash": raw_hash,
            "html_content": decoded,
            "structured_fields": [],
            "interactions": [],
        }
        return WikimediaRecord(record, "wiki_article", len(content))

    resource_title = document_title(
        entry.title,
        source_id=path,
        page_type="wiki_resource",
        archive_entry_path=path,
    )
    record = {
        **base,
        "title": resource_title,
        "page_type": "wiki_resource",
        "mime_type": mime,
        "raw_content_hash": raw_hash,
        "blocks": [],
        "links": [],
        "aliases": [
            resource_title,
            path,
            path.replace("_", " "),
        ],
        "structured_fields": [{
            "name": "item_size",
            "value": item.size,
            "unit": "bytes",
            "field_type": "size",
        }],
        "metadata": {
            **base["metadata"],
            "resource_content_omitted": True,
        },
    }
    return WikimediaRecord(record, "wiki_resource", len(content))


def export_wikimedia(
    args: argparse.Namespace, out: Path
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from libzim.reader import Archive
    except ImportError as exc:
        raise RuntimeError(
            "python3-libzim is required on the frozen source host"
        ) from exc

    archive = Archive(args.zim)
    output = out / "records" / "wikimedia.jsonl.gz"
    selected_count = 0
    selected_redirects = 0
    selected_html = 0
    selected_resources = 0
    read_bytes = 0
    errors: list[dict[str, Any]] = []
    next_progress = args.progress_every
    scan_count = archive.entry_count
    if args.wiki_scan_limit is not None:
        scan_count = min(scan_count, args.wiki_scan_limit)

    with writer(output) as handle:
        for index in range(scan_count):
            try:
                entry = archive._get_entry_by_id(index)
                path = entry.path
            except Exception as exc:
                errors.append({
                    "index": index, "stage": "entry", "error": repr(exc)
                })
                continue

            if not is_selected(args, PACK_WIKIMEDIA, path):
                if index + 1 >= next_progress:
                    print(
                        f"[wiki] scanned={index + 1}/{scan_count} "
                        f"selected={selected_count}",
                        file=sys.stderr,
                        flush=True,
                    )
                    next_progress += args.progress_every
                continue

            selected_count += 1
            try:
                built = build_wikimedia_record(
                    archive, index=index, entry=entry
                )
                read_bytes += built.content_bytes_read
                if built.page_type == "wiki_redirect":
                    selected_redirects += 1
                elif built.page_type == "wiki_article":
                    selected_html += 1
                elif built.page_type == "wiki_resource":
                    selected_resources += 1
                write_record(handle, built.record)
            except Exception as exc:
                errors.append({
                    "index": index, "path": path,
                    "stage": "content", "error": repr(exc),
                })

            if index + 1 >= next_progress:
                print(
                    f"[wiki] scanned={index + 1}/{scan_count} "
                    f"selected={selected_count}",
                    file=sys.stderr,
                    flush=True,
                )
                next_progress += args.progress_every

    errors_path = out / "errors" / "wikimedia-errors.json"
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    errors_path.write_text(
        canonical_json(errors) + "\n", encoding="utf-8"
    )
    return {
        "pack_id": PACK_WIKIMEDIA,
        "population": archive.entry_count,
        "all_entry_count": archive.all_entry_count,
        "article_count": archive.article_count,
        "scanned": scan_count,
        "scan_complete": scan_count == archive.entry_count,
        "selected": selected_count,
        "selected_html": selected_html,
        "selected_redirects": selected_redirects,
        "selected_resources": selected_resources,
        "selected_read_bytes": read_bytes,
        "errors": len(errors),
        "records_path": str(output.relative_to(out)),
        "records_sha256": digest_bytes(output.read_bytes()),
        "errors_path": str(errors_path.relative_to(out)),
        "zim_path": str(args.zim),
        "zim_size": archive.filesize,
        "zim_uuid": str(archive.uuid),
        "zim_checksum": archive.checksum,
        "zim_has_fulltext_index": archive.has_fulltext_index,
        "zim_has_title_index": archive.has_title_index,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0]
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--snapshot-id", default=DEFAULT_SNAPSHOT)
    parser.add_argument("--modulus", type=int, default=100)
    parser.add_argument("--bucket", type=int, default=0)
    parser.add_argument(
        "--packs",
        nargs="+",
        choices=("commerce", "community", "wikimedia"),
        default=("commerce", "community", "wikimedia"),
    )
    parser.add_argument(
        "--magento-container", default="dr_sandbox_shopping"
    )
    parser.add_argument("--magento-user", default="magentouser")
    parser.add_argument(
        "--magento-password",
        default=os.environ.get("DRA_MAGENTO_PASSWORD", "MyPassword"),
    )
    parser.add_argument("--magento-database", default="magentodb")
    parser.add_argument(
        "--postmill-container", default="dr_sandbox_reddit"
    )
    parser.add_argument("--postmill-user", default="postmill")
    parser.add_argument("--zim", type=Path, default=DEFAULT_ZIM)
    parser.add_argument("--progress-every", type=int, default=500_000)
    parser.add_argument(
        "--wiki-scan-limit",
        type=int,
        help=(
            "engineering smoke only: stop ZIM enumeration after N entries; "
            "any manifest produced with this option is formal-ineligible"
        ),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.modulus <= 0 or not (0 <= args.bucket < args.modulus):
        raise SystemExit("invalid shard modulus/bucket")
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()) and not args.overwrite:
        raise SystemExit(
            f"refusing non-empty output directory without --overwrite: {out}"
        )
    out.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    packs = []
    if "commerce" in args.packs:
        print("[e1] exporting commerce", file=sys.stderr, flush=True)
        packs.append(export_commerce(args, out))
    if "community" in args.packs:
        print("[e1] exporting community", file=sys.stderr, flush=True)
        packs.append(export_community(args, out))
    if "wikimedia" in args.packs:
        print("[e1] exporting wikimedia", file=sys.stderr, flush=True)
        packs.append(export_wikimedia(args, out))

    manifest = {
        "schema": "dra_e1_source_manifest_v1",
        "created_at": utc_now(),
        "snapshot_id": args.snapshot_id,
        "selection": {
            "algorithm": SHARD_ALGORITHM,
            "modulus": args.modulus,
            "bucket": args.bucket,
            "selection_rate": 1 / args.modulus,
            "top_level_only": True,
            "child_closure": {
                PACK_COMMERCE: [
                    "EAV fields", "categories", "stock",
                    "relations", "reviews", "rating votes",
                ],
                PACK_COMMUNITY: [
                    "root post", "complete reply tree",
                    "timestamps", "scores",
                ],
                PACK_WIKIMEDIA: [
                    "selected entry content", "redirect target",
                    "page links parsed downstream",
                ],
            },
        },
        "task_conditioned": False,
        "task_or_witness_inputs": [],
        "formal_eligible": (
            args.wiki_scan_limit is None
            and tuple(args.packs) == REQUIRED_PACK_NAMES
            and all(int(pack.get("errors") or 0) == 0 for pack in packs)
        ),
        "engineering_smoke": args.wiki_scan_limit is not None,
        "wiki_scan_limit": args.wiki_scan_limit,
        "packs": packs,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "tool_versions": {
            "python": sys.version.split()[0],
            "zim_tools": tool_version(["zimdump", "--version"]),
            "exporter_sha256": digest_bytes(
                Path(__file__).resolve().read_bytes()
            ),
            "world_index_module_sha256": digest_bytes(
                (ROOT / "src/world_index/e1.py").read_bytes()
            ),
            "world_index_schema": E1_SCHEMA_VERSION,
        },
    }
    stable_packs = [
        {
            key: value for key, value in pack.items()
            if key != "elapsed_seconds"
        }
        for pack in packs
    ]
    manifest_identity = {
        "schema": manifest["schema"],
        "snapshot_id": manifest["snapshot_id"],
        "selection": manifest["selection"],
        "task_conditioned": manifest["task_conditioned"],
        "task_or_witness_inputs": manifest["task_or_witness_inputs"],
        "formal_eligible": manifest["formal_eligible"],
        "engineering_smoke": manifest["engineering_smoke"],
        "wiki_scan_limit": manifest["wiki_scan_limit"],
        "packs": stable_packs,
        "tool_versions": manifest["tool_versions"],
    }
    manifest["source_manifest_id"] = digest_text(
        canonical_json(manifest_identity)
    )
    manifest["identity_excludes"] = [
        "created_at",
        "elapsed_seconds",
        "packs[].elapsed_seconds",
    ]
    manifest_path = out / "source-manifest.json"
    manifest_path.write_text(
        json.dumps(
            manifest, ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n",
        encoding="utf-8",
    )
    print(f"[e1] wrote {manifest_path}", file=sys.stderr)
    print(json.dumps({
        "source_manifest_id": manifest["source_manifest_id"],
        "packs": packs,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
