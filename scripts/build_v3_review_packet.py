#!/usr/bin/env python3
"""Build a self-contained human-review packet from frozen DRA v3 evidence.

The packet is a review surface, not an automatic labeler. It renders the exact
validated bytes and support-span context used by the evidence graph, then
provides a blank decision template and an in-browser JSON export. Live pages
are linked only for source-identity inspection and must not override frozen
content during review.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
import tempfile
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from string import Template
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_evidence_graph import compile_inventory, load_inventory  # noqa: E402
from src.eval.evidence_graph import (  # noqa: E402
    EdgeRelation,
    EvidenceGraphFormatError,
    canonical_json_bytes,
    load_json,
    save_json,
    sha256_bytes,
)


REVIEW_QUEUE_SCHEMA = "dra_v3_human_review_queue_v1"
REVIEW_DECISIONS_SCHEMA = "dra_v3_human_review_decisions_v1"
REVIEW_PACKET_MANIFEST_SCHEMA = "dra_v3_human_review_packet_manifest_v1"
REVIEW_TRANSLATIONS_SCHEMA = "dra_v3_review_translations_v1"


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _strict_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceGraphFormatError(f"{path}: expected an object")
    return dict(value)


def _review_kind(node_type: str) -> str:
    if node_type in {"assertion", "experience_claim", "claim", "mechanism"}:
        return "semantic"
    if node_type in {"entity", "attribute"}:
        return "structured"
    return "support"


def _context(
    content: bytes,
    *,
    start: int,
    end: int,
    context_bytes: int,
) -> dict[str, object]:
    exact = content[start:end]
    prefix_start = max(0, start - context_bytes)
    suffix_end = min(len(content), end + context_bytes)
    return {
        "prefix_start": prefix_start,
        "suffix_end": suffix_end,
        "prefix": content[prefix_start:start].decode("utf-8", "replace"),
        "exact_text": exact.decode("utf-8", "replace"),
        "suffix": content[end:suffix_end].decode("utf-8", "replace"),
    }


def _build_queue(
    inventory_path: Path,
    *,
    snapshot_root: Path,
    context_bytes: int,
) -> tuple[dict[str, object], dict[str, bytes], dict[str, object]]:
    inventory = load_inventory(inventory_path)
    inventory_meta = _strict_object(inventory.get("metadata", {}), "metadata")
    graph, registry, blobs = compile_inventory(inventory, blob_root=snapshot_root)
    node_by_id = graph.node_by_id

    propositions_by_assertion: dict[str, list[dict[str, object]]] = defaultdict(list)
    for edge in graph.edges:
        if edge.relation is not EdgeRelation.ASSERTS:
            continue
        proposition = node_by_id[edge.target_id]
        propositions_by_assertion[edge.source_id].append(
            {
                "edge_id": edge.edge_id,
                "evidence_id": proposition.evidence_id,
                "subject": proposition.subject,
                "predicate": proposition.predicate,
                "object": proposition.object,
                "metadata": dict(proposition.metadata),
            }
        )

    spans_by_node: dict[str, list[Any]] = defaultdict(list)
    for span in graph.support_spans:
        spans_by_node[span.evidence_id].append(span)

    items: list[dict[str, object]] = []
    for evidence_id in sorted(spans_by_node):
        node = node_by_id[evidence_id]
        content = blobs[node.source_url]
        rendered_spans: list[dict[str, object]] = []
        for span in sorted(
            spans_by_node[evidence_id], key=lambda item: item.support_span_id
        ):
            rendered_spans.append(
                {
                    "support_span_id": span.support_span_id,
                    "support_type": span.support_type.value,
                    "start": span.start,
                    "end": span.end,
                    "sha256": span.sha256,
                    "metadata": dict(span.metadata),
                    **_context(
                        content,
                        start=span.start,
                        end=span.end,
                        context_bytes=context_bytes,
                    ),
                }
            )
        items.append(
            {
                "review_item_id": evidence_id,
                "review_kind": _review_kind(node.node_type.value),
                "evidence_id": evidence_id,
                "node_type": node.node_type.value,
                "subject": node.subject,
                "predicate": node.predicate,
                "object": node.object,
                "source_url": node.source_url,
                "source_type": node.source_type.value,
                "content_sha256": node.content_sha256,
                "body_support": node.body_support,
                "search_snippet_support": node.search_snippet_support,
                "verifier": dict(node.verifier),
                "metadata": dict(node.metadata),
                "proposed_propositions": sorted(
                    propositions_by_assertion.get(evidence_id, []),
                    key=lambda item: str(item["evidence_id"]),
                ),
                "support_spans": rendered_spans,
            }
        )

    source_files: dict[str, bytes] = {}
    sources: list[dict[str, object]] = []
    for entry in sorted(registry.entries, key=lambda item: item.registry_id):
        content = blobs[entry.source_url]
        relative = f"sources/{entry.content_sha256}"
        previous = source_files.get(relative)
        if previous is not None and previous != content:
            raise EvidenceGraphFormatError(
                f"{relative}: one content hash resolved to conflicting bytes"
            )
        source_files[relative] = content
        sources.append(
            {
                "registry_id": entry.registry_id,
                "source_url": entry.source_url,
                "source_type": entry.source_type.value,
                "content_sha256": entry.content_sha256,
                "raw_snapshot_path": relative,
                "bytes": len(content),
                "metadata": dict(entry.metadata),
            }
        )

    gaps = inventory_meta.get("evidence_gaps", [])
    if not isinstance(gaps, list) or not all(isinstance(gap, str) for gap in gaps):
        raise EvidenceGraphFormatError("metadata.evidence_gaps: expected a string array")
    candidate_id = inventory_meta.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        candidate_id = "unassigned_candidate"

    queue: dict[str, object] = {
        "schema_version": REVIEW_QUEUE_SCHEMA,
        "corpus_snapshot": graph.corpus_snapshot,
        "evidence_graph_hash": graph.graph_sha256,
        "corpus_registry_hash": registry.corpus_sha256,
        "inventory_sha256": sha256_bytes(inventory_path.read_bytes()),
        "candidate_id": candidate_id,
        "status": inventory_meta.get("status", "pending_human_review"),
        "eligible_for_case_generation": inventory_meta.get(
            "eligible_for_case_generation", False
        ),
        "review_policy": {
            "frozen_bytes_are_authoritative": True,
            "live_page_may_override_snapshot": False,
            "review_does_not_auto_promote": True,
            "semantic_claims_require_scope_review": True,
            "structured_claims_require_span_review": True,
        },
        "evidence_gaps": list(gaps),
        "items": items,
        "sources": sources,
    }
    counts = {
        "review_items": len(items),
        "semantic_items": sum(item["review_kind"] == "semantic" for item in items),
        "structured_items": sum(
            item["review_kind"] == "structured" for item in items
        ),
        "support_items": sum(item["review_kind"] == "support" for item in items),
        "support_spans": sum(len(item["support_spans"]) for item in items),
        "sources": len(sources),
        "evidence_gaps": len(gaps),
    }
    return queue, source_files, counts


def _decision_template(queue: Mapping[str, object]) -> dict[str, object]:
    items = queue.get("items", [])
    gaps = queue.get("evidence_gaps", [])
    if not isinstance(items, list) or not isinstance(gaps, list):
        raise EvidenceGraphFormatError("review queue items/gaps must be arrays")
    return {
        "schema_version": REVIEW_DECISIONS_SCHEMA,
        "corpus_snapshot": queue["corpus_snapshot"],
        "evidence_graph_hash": queue["evidence_graph_hash"],
        "candidate_id": queue["candidate_id"],
        "reviewer_id": "",
        "reviewed_at_utc": "",
        "independent_review": True,
        "candidate_verdict": "pending",
        "items": [
            {
                "review_item_id": item["review_item_id"],
                "decision": "pending",
                "support_span_correct": None,
                "proposition_supported": None,
                "source_scope_correct": None,
                "context_sufficient": None,
                "reviewer_note": "",
            }
            for item in items
            if isinstance(item, Mapping)
        ],
        "evidence_gaps": [
            {
                "gap_id": f"gap_{index:03d}",
                "description": gap,
                "resolution": "unresolved",
                "reviewer_note": "",
            }
            for index, gap in enumerate(gaps, 1)
        ],
    }


def _apply_translations(
    queue: dict[str, object],
    translations_path: Path,
) -> bytes:
    """Validate and attach a non-authoritative human-language overlay."""

    raw_bytes = translations_path.read_bytes()
    raw = load_json(translations_path)
    translations = _strict_object(raw, "translations")
    expected_keys = {
        "schema_version",
        "language",
        "corpus_snapshot",
        "evidence_graph_hash",
        "candidate_id",
        "authority",
        "evidence_gaps_zh",
        "items",
    }
    if set(translations) != expected_keys:
        raise EvidenceGraphFormatError(
            f"translations: keys must be exactly {sorted(expected_keys)!r}"
        )
    if translations["schema_version"] != REVIEW_TRANSLATIONS_SCHEMA:
        raise EvidenceGraphFormatError(
            f"translations.schema_version: expected {REVIEW_TRANSLATIONS_SCHEMA!r}"
        )
    for key in ("corpus_snapshot", "evidence_graph_hash", "candidate_id"):
        if translations[key] != queue[key]:
            raise EvidenceGraphFormatError(
                f"translations.{key}: does not match the frozen review queue"
            )
    if translations["language"] != "zh-CN":
        raise EvidenceGraphFormatError("translations.language: expected 'zh-CN'")
    if translations["authority"] != "translation_aid_only":
        raise EvidenceGraphFormatError(
            "translations.authority: must be 'translation_aid_only'"
        )

    original_gaps = queue.get("evidence_gaps", [])
    translated_gaps = translations["evidence_gaps_zh"]
    if not isinstance(translated_gaps, list) or len(translated_gaps) != len(original_gaps):
        raise EvidenceGraphFormatError(
            "translations.evidence_gaps_zh: must translate every evidence gap"
        )
    if not all(isinstance(value, str) and value.strip() for value in translated_gaps):
        raise EvidenceGraphFormatError(
            "translations.evidence_gaps_zh: translations must be non-empty strings"
        )

    queue_items = queue.get("items", [])
    translated_items = translations["items"]
    if not isinstance(queue_items, list) or not isinstance(translated_items, list):
        raise EvidenceGraphFormatError("translations.items: expected an array")
    by_id: dict[str, dict[str, Any]] = {}
    for index, raw_item in enumerate(translated_items):
        item = _strict_object(raw_item, f"translations.items[{index}]")
        required = {
            "review_item_id",
            "claim_zh",
            "propositions_zh",
            "support_spans_zh",
            "scope_note_zh",
        }
        if set(item) != required:
            raise EvidenceGraphFormatError(
                f"translations.items[{index}]: keys must be exactly {sorted(required)!r}"
            )
        review_item_id = item["review_item_id"]
        if not isinstance(review_item_id, str) or review_item_id in by_id:
            raise EvidenceGraphFormatError(
                f"translations.items[{index}].review_item_id: invalid or duplicate"
            )
        claim = item["claim_zh"]
        if not isinstance(claim, dict) or set(claim) != {"subject", "predicate", "object"}:
            raise EvidenceGraphFormatError(
                f"translations.items[{index}].claim_zh: expected subject/predicate/object"
            )
        if not isinstance(item["scope_note_zh"], str) or not item["scope_note_zh"].strip():
            raise EvidenceGraphFormatError(
                f"translations.items[{index}].scope_note_zh: must be non-empty"
            )
        by_id[review_item_id] = item

    expected_ids = {
        str(_strict_object(item, "queue.items[]")["review_item_id"])
        for item in queue_items
    }
    if set(by_id) != expected_ids:
        missing = sorted(expected_ids - set(by_id))
        unknown = sorted(set(by_id) - expected_ids)
        raise EvidenceGraphFormatError(
            f"translations.items: incomplete overlay; missing={missing}, unknown={unknown}"
        )

    for raw_item in queue_items:
        item = _strict_object(raw_item, "queue.items[]")
        translated = by_id[str(item["review_item_id"])]
        proposition_ids = {
            str(_strict_object(value, "proposed_propositions[]")["evidence_id"])
            for value in item.get("proposed_propositions", [])
        }
        propositions_zh = translated["propositions_zh"]
        if not isinstance(propositions_zh, list):
            raise EvidenceGraphFormatError("translations.propositions_zh: expected an array")
        translated_proposition_ids = {
            str(_strict_object(value, "propositions_zh[]").get("evidence_id"))
            for value in propositions_zh
        }
        if translated_proposition_ids != proposition_ids:
            raise EvidenceGraphFormatError(
                f"translations[{item['review_item_id']}].propositions_zh: IDs do not match"
            )
        span_ids = {
            str(_strict_object(value, "support_spans[]")["support_span_id"])
            for value in item.get("support_spans", [])
        }
        spans_zh = translated["support_spans_zh"]
        if not isinstance(spans_zh, list):
            raise EvidenceGraphFormatError("translations.support_spans_zh: expected an array")
        translated_span_ids: set[str] = set()
        for raw_span in spans_zh:
            span = _strict_object(raw_span, "support_spans_zh[]")
            if set(span) != {"support_span_id", "exact_text_zh", "context_note_zh"}:
                raise EvidenceGraphFormatError(
                    "translations.support_spans_zh: expected support_span_id/exact_text_zh/context_note_zh"
                )
            if not isinstance(span["exact_text_zh"], str) or not span["exact_text_zh"].strip():
                raise EvidenceGraphFormatError(
                    "translations.support_spans_zh.exact_text_zh: must be non-empty"
                )
            if not isinstance(span["context_note_zh"], str) or not span["context_note_zh"].strip():
                raise EvidenceGraphFormatError(
                    "translations.support_spans_zh.context_note_zh: must be non-empty"
                )
            translated_span_ids.add(str(span["support_span_id"]))
        if translated_span_ids != span_ids:
            raise EvidenceGraphFormatError(
                f"translations[{item['review_item_id']}].support_spans_zh: IDs do not match"
            )
        if not isinstance(raw_item, dict):
            raise EvidenceGraphFormatError("queue.items[]: expected a mutable object")
        raw_item["translation_zh"] = translated

    queue["translation"] = {
        "language": translations["language"],
        "authority": translations["authority"],
        "sha256": sha256_bytes(raw_bytes),
        "evidence_gaps_zh": translated_gaps,
    }
    return raw_bytes


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _pretty(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _select(name: str, options: tuple[str, ...]) -> str:
    labels = {
        "pending": "待定（pending）",
        "approve": "通过（approve）",
        "reject": "拒绝（reject）",
        "needs_more_context": "需要更多上下文",
        "unknown": "不确定",
        "yes": "是",
        "no": "否",
        "not_applicable": "不适用",
        "unresolved": "未解决",
        "resolved_by_new_evidence": "由新冻结证据解决",
        "resolved_by_scope_change": "通过缩小题目范围解决",
        "reject_candidate": "淘汰候选题",
    }
    rendered = []
    for option in options:
        selected = " selected" if option in {"pending", "unknown", "unresolved"} else ""
        rendered.append(
            f'<option value="{_escape(option)}"{selected}>{_escape(labels.get(option, option))}</option>'
        )
    return f'<select name="{_escape(name)}">{"".join(rendered)}</select>'


def _render_html(queue: Mapping[str, object], counts: Mapping[str, object]) -> bytes:
    items = queue.get("items", [])
    sources = queue.get("sources", [])
    gaps = queue.get("evidence_gaps", [])
    if not isinstance(items, list) or not isinstance(sources, list) or not isinstance(gaps, list):
        raise EvidenceGraphFormatError("review queue arrays are malformed")

    translation_meta = queue.get("translation", {})
    if not isinstance(translation_meta, Mapping):
        raise EvidenceGraphFormatError("review queue translation must be an object")
    translated_gaps = translation_meta.get("evidence_gaps_zh", [])
    if translated_gaps and (
        not isinstance(translated_gaps, list) or len(translated_gaps) != len(gaps)
    ):
        raise EvidenceGraphFormatError("translated evidence gaps do not match originals")

    gap_html = []
    for index, gap in enumerate(gaps, 1):
        translated_gap = (
            translated_gaps[index - 1]
            if isinstance(translated_gaps, list) and translated_gaps
            else gap
        )
        gap_html.append(
            '<li class="gap" data-gap-id="gap_{index:03d}" data-gap-description="{gap_attr}">'
            '<div><strong>gap_{index:03d}</strong>: {translated_gap}'
            '<div class="original-text">英文冻结描述：{gap}</div></div>'
            '<label>处理结果 {select}</label>'
            '<label>备注 <input name="gap_note" type="text"></label>'
            "</li>".format(
                index=index,
                gap=_escape(gap),
                gap_attr=_escape(gap),
                translated_gap=_escape(translated_gap),
                select=_select(
                    "gap_resolution",
                    ("unresolved", "resolved_by_new_evidence", "resolved_by_scope_change", "reject_candidate"),
                ),
            )
        )

    cards: list[str] = []
    for raw_item in items:
        item = _strict_object(raw_item, "items[]")
        propositions = item.get("proposed_propositions", [])
        spans = item.get("support_spans", [])
        if not isinstance(propositions, list) or not isinstance(spans, list):
            raise EvidenceGraphFormatError("review item propositions/spans must be arrays")
        translation = item.get("translation_zh")
        translation_html = ""
        if translation is not None:
            translated = _strict_object(translation, "translation_zh")
            translated_props = translated.get("propositions_zh", [])
            translated_spans = translated.get("support_spans_zh", [])
            if not isinstance(translated_props, list) or not isinstance(translated_spans, list):
                raise EvidenceGraphFormatError(
                    "translation_zh propositions/support spans must be arrays"
                )
            translated_span_html = "".join(
                '<div class="translated-span"><strong>高亮原文译文：</strong>{exact}'
                '<p><strong>上下文提示：</strong>{context}</p></div>'.format(
                    exact=_escape(_strict_object(span, "support_spans_zh[]").get("exact_text_zh")),
                    context=_escape(_strict_object(span, "support_spans_zh[]").get("context_note_zh")),
                )
                for span in translated_spans
            )
            translated_prop_html = (
                '<p class="muted">结构化项没有 ASSERTS proposition。</p>'
                if not translated_props
                else "".join(
                    '<div class="proposition"><code>{id}</code><pre>{payload}</pre></div>'.format(
                        id=_escape(_strict_object(prop, "propositions_zh[]").get("evidence_id")),
                        payload=_escape(
                            _pretty(
                                {
                                    key: _strict_object(prop, "propositions_zh[]").get(key)
                                    for key in ("subject", "predicate", "object")
                                }
                            )
                        ),
                    )
                    for prop in translated_props
                )
            )
            translation_html = (
                '<section class="translation"><h4>中文标注辅助（非证据）</h4>'
                '<strong>拟议节点中文：</strong><pre>{claim}</pre>'
                '<strong>拟议 proposition 中文：</strong>{propositions}'
                '{spans}<p><strong>范围提示：</strong>{scope}</p></section>'
            ).format(
                claim=_escape(_pretty(translated.get("claim_zh"))),
                propositions=translated_prop_html,
                spans=translated_span_html,
                scope=_escape(translated.get("scope_note_zh")),
            )
        proposition_html = (
            "<p class=muted>该节点没有 ASSERTS proposition，仅审核结构化字段与 span。</p>"
            if not propositions
            else "".join(
                '<div class="proposition"><code>{id}</code><pre>{payload}</pre></div>'.format(
                    id=_escape(_strict_object(prop, "proposition").get("evidence_id")),
                    payload=_escape(
                        _pretty(
                            {
                                key: _strict_object(prop, "proposition").get(key)
                                for key in ("subject", "predicate", "object", "metadata")
                            }
                        )
                    ),
                )
                for prop in propositions
            )
        )
        span_html = []
        for raw_span in spans:
            span = _strict_object(raw_span, "support_span")
            span_html.append(
                '<section class="span">'
                '<div class="span-meta"><code>{span_id}</code> | bytes [{start}, {end}) | '
                '<code>{digest}</code></div>'
                '<pre class="context"><span>{prefix}</span><mark>{exact}</mark><span>{suffix}</span></pre>'
                "</section>".format(
                    span_id=_escape(span.get("support_span_id")),
                    start=_escape(span.get("start")),
                    end=_escape(span.get("end")),
                    digest=_escape(span.get("sha256")),
                    prefix=_escape(span.get("prefix", "")),
                    exact=_escape(span.get("exact_text", "")),
                    suffix=_escape(span.get("suffix", "")),
                )
            )
        item_id = str(item["review_item_id"])
        source_path = f"sources/{item['content_sha256']}"
        cards.append(
            '<article class="review-card" data-kind="{kind}" data-item-id="{item_id}">'
            '<header><h3>{item_id}</h3><span class="badge">{kind}</span>'
            '<span class="badge">{node_type}</span><span class="badge">{source_type}</span></header>'
            '{translation}'
            '<div class="claim"><strong>英文拟议节点（协议原文）</strong><pre>{claim}</pre></div>'
            '<details open><summary>英文拟议 proposition（协议原文）</summary>{propositions}</details>'
            '<details open><summary>英文冻结原文与上下文（权威证据）</summary>{spans}</details>'
            '<details><summary>来源身份与元数据</summary>'
            '<p>URL: <a href="{url}" target="_blank" rel="noreferrer">{url}</a></p>'
            '<p>冻结文件: <a href="{source_path}" target="_blank">{source_path}</a></p>'
            '<p>内容 SHA-256: <code>{content_hash}</code></p>'
            '<pre>{metadata}</pre></details>'
            '<fieldset><legend>人工决定</legend>'
            '<label>结论 {decision}</label>'
            '<label>span 正确 {span_correct}</label>'
            '<label>proposition 被原文支持 {prop_supported}</label>'
            '<label>来源范围表达正确 {scope_correct}</label>'
            '<label>上下文充分 {context_sufficient}</label>'
            '<label class="note">审核备注<textarea name="reviewer_note"></textarea></label>'
            "</fieldset></article>".format(
                kind=_escape(item.get("review_kind")),
                item_id=_escape(item_id),
                node_type=_escape(item.get("node_type")),
                source_type=_escape(item.get("source_type")),
                translation=translation_html,
                claim=_escape(
                    _pretty(
                        {
                            "subject": item.get("subject"),
                            "predicate": item.get("predicate"),
                            "object": item.get("object"),
                        }
                    )
                ),
                propositions=proposition_html,
                spans="".join(span_html),
                url=_escape(item.get("source_url")),
                source_path=_escape(source_path),
                content_hash=_escape(item.get("content_sha256")),
                metadata=_escape(
                    _pretty(
                        {
                            "verifier": item.get("verifier"),
                            "metadata": item.get("metadata"),
                            "body_support": item.get("body_support"),
                            "search_snippet_support": item.get("search_snippet_support"),
                        }
                    )
                ),
                decision=_select(
                    "decision", ("pending", "approve", "reject", "needs_more_context")
                ),
                span_correct=_select("support_span_correct", ("unknown", "yes", "no")),
                prop_supported=_select(
                    "proposition_supported", ("unknown", "yes", "no", "not_applicable")
                ),
                scope_correct=_select(
                    "source_scope_correct", ("unknown", "yes", "no", "not_applicable")
                ),
                context_sufficient=_select(
                    "context_sufficient", ("unknown", "yes", "no")
                ),
            )
        )

    source_rows = []
    for raw_source in sources:
        source = _strict_object(raw_source, "sources[]")
        source_rows.append(
            "<tr><td>{registry}</td><td>{type}</td><td><a href=\"{path}\">{hash}</a></td>"
            "<td><a href=\"{url}\" target=\"_blank\" rel=\"noreferrer\">来源 URL</a></td>"
            "<td>{bytes}</td></tr>".format(
                registry=_escape(source.get("registry_id")),
                type=_escape(source.get("source_type")),
                path=_escape(source.get("raw_snapshot_path")),
                hash=_escape(source.get("content_sha256")),
                url=_escape(source.get("source_url")),
                bytes=_escape(source.get("bytes")),
            )
        )

    candidate_json = json.dumps(str(queue["candidate_id"]), ensure_ascii=False)
    snapshot_json = json.dumps(str(queue["corpus_snapshot"]), ensure_ascii=False)
    graph_hash_json = json.dumps(str(queue["evidence_graph_hash"]), ensure_ascii=False)
    page = Template(r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DRA v3 冻结证据人工审核</title>
<style>
:root { color-scheme: light; font-family: Inter, "Noto Sans SC", sans-serif; }
body { margin: 0; background: #f4f6f8; color: #17212b; }
main { max-width: 1180px; margin: 0 auto; padding: 28px; }
h1, h2, h3 { margin-top: 0; }
.warning { background: #fff3cd; border: 1px solid #e0b84f; padding: 16px; border-radius: 8px; }
.translation { background: #edf7ff; border: 1px solid #8ec5ee; border-radius: 8px; padding: 14px; margin: 14px 0; }
.translation h4 { margin: 0 0 10px; }
.translated-span { background: white; border-left: 4px solid #3182ce; padding: 10px 12px; margin: 10px 0; }
.original-text { color: #657587; font-size: 12px; margin-top: 5px; }
.summary, .toolbar, .review-card, .sources { background: white; border: 1px solid #d9e0e7; border-radius: 10px; padding: 18px; margin: 16px 0; }
.toolbar { position: sticky; top: 0; z-index: 10; box-shadow: 0 3px 12px #0002; }
.toolbar-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; align-items: end; }
label { display: flex; flex-direction: column; gap: 5px; font-size: 14px; }
input, select, textarea, button { font: inherit; padding: 8px; }
button { cursor: pointer; background: #155eef; color: white; border: 0; border-radius: 6px; }
.review-card header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.review-card h3 { margin: 0 auto 0 0; }
.badge { border: 1px solid #aab7c4; border-radius: 999px; padding: 3px 8px; font-size: 12px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f7f9fb; border: 1px solid #e1e7ed; padding: 12px; border-radius: 6px; }
.context { line-height: 1.6; }
mark { background: #ffe08a; padding: 2px; }
details { margin: 12px 0; }
summary { cursor: pointer; font-weight: 650; }
fieldset { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; border: 1px solid #cbd5df; border-radius: 8px; }
.note { grid-column: 1 / -1; }
textarea { min-height: 70px; }
.gap { margin-bottom: 14px; }
.gap label { margin-top: 6px; }
.muted, .span-meta { color: #536273; font-size: 13px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid #e1e7ed; padding: 8px; text-align: left; overflow-wrap: anywhere; }
.hidden { display: none; }
</style>
</head>
<body><main>
<h1>DRA v3 冻结证据人工审核</h1>
<section class="warning"><strong>审核规则：</strong>以本页展示的英文冻结 bytes 为准。中文是理解辅助，不是独立证据。实时网页只能核对来源身份，不能覆盖冻结快照。JSON 用于记录决定，不应代替阅读原文和上下文。本页不会自动把候选题晋级。</section>
<section class="summary">
<h2>审核对象</h2>
<p>候选题: <code>$candidate</code></p>
<p>语料快照: <code>$snapshot</code></p>
<p>证据图哈希: <code>$graph_hash</code></p>
<p>待审项 $review_items 个，其中语义项 $semantic_items 个、结构化项 $structured_items 个；冻结来源 $sources_count 个；已知证据缺口 $gap_count 个。</p>
<h3>已知证据缺口</h3><ol>$gaps</ol>
</section>
<section class="toolbar">
<div class="toolbar-grid">
<label>标注者 ID<input id="reviewer_id" placeholder="你的名字或标注者 ID"></label>
<label>候选题结论<select id="candidate_verdict"><option value="pending">待定（pending）</option><option value="eligible">可晋级（eligible）</option><option value="reject">淘汰（reject）</option><option value="revise_scope">缩小题目范围（revise_scope）</option></select></label>
<label>筛选<select id="kind_filter"><option value="all">全部</option><option value="semantic">语义项</option><option value="structured">结构化项</option><option value="pending">尚未决定</option></select></label>
<button id="export_button" type="button">导出审核 JSON</button>
</div></section>
<section id="review_items">$cards</section>
<section class="sources"><h2>冻结来源文件</h2><table><thead><tr><th>注册项</th><th>类型</th><th>SHA-256 / 快照</th><th>URL</th><th>字节数</th></tr></thead><tbody>$source_rows</tbody></table></section>
</main>
<script>
const candidateId = $candidate_json;
const corpusSnapshot = $snapshot_json;
const graphHash = $graph_hash_json;
const filter = document.getElementById('kind_filter');
filter.addEventListener('change', () => {
  document.querySelectorAll('.review-card').forEach(card => {
    const decision = card.querySelector('[name="decision"]').value;
    const visible = filter.value === 'all' || card.dataset.kind === filter.value || (filter.value === 'pending' && decision === 'pending');
    card.classList.toggle('hidden', !visible);
  });
});
document.getElementById('export_button').addEventListener('click', () => {
  const items = Array.from(document.querySelectorAll('.review-card')).map(card => ({
    review_item_id: card.dataset.itemId,
    decision: card.querySelector('[name="decision"]').value,
    support_span_correct: card.querySelector('[name="support_span_correct"]').value,
    proposition_supported: card.querySelector('[name="proposition_supported"]').value,
    source_scope_correct: card.querySelector('[name="source_scope_correct"]').value,
    context_sufficient: card.querySelector('[name="context_sufficient"]').value,
    reviewer_note: card.querySelector('[name="reviewer_note"]').value
  }));
  const evidence_gaps = Array.from(document.querySelectorAll('.gap')).map(gap => ({
    gap_id: gap.dataset.gapId,
    description: gap.dataset.gapDescription,
    resolution: gap.querySelector('[name="gap_resolution"]').value,
    reviewer_note: gap.querySelector('[name="gap_note"]').value
  }));
  const output = {
    schema_version: 'dra_v3_human_review_decisions_v1',
    corpus_snapshot: corpusSnapshot,
    evidence_graph_hash: graphHash,
    candidate_id: candidateId,
    reviewer_id: document.getElementById('reviewer_id').value,
    reviewed_at_utc: new Date().toISOString(),
    independent_review: true,
    candidate_verdict: document.getElementById('candidate_verdict').value,
    items,
    evidence_gaps
  };
  const blob = new Blob([JSON.stringify(output, null, 2) + '\n'], {type: 'application/json'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = candidateId + '.review-decisions.json';
  link.click();
  URL.revokeObjectURL(link.href);
});
</script></body></html>
""").substitute(
        candidate=_escape(queue["candidate_id"]),
        snapshot=_escape(queue["corpus_snapshot"]),
        graph_hash=_escape(queue["evidence_graph_hash"]),
        review_items=_escape(counts["review_items"]),
        semantic_items=_escape(counts["semantic_items"]),
        structured_items=_escape(counts["structured_items"]),
        sources_count=_escape(counts["sources"]),
        gap_count=_escape(counts["evidence_gaps"]),
        gaps="".join(gap_html),
        cards="".join(cards),
        source_rows="".join(source_rows),
        candidate_json=candidate_json,
        snapshot_json=snapshot_json,
        graph_hash_json=graph_hash_json,
    )
    return page.encode("utf-8")


def _file_record(path: Path, root: Path) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def build_review_packet(
    inventory_path: str | Path,
    output_dir: str | Path,
    *,
    snapshot_root: str | Path | None = None,
    translations_path: str | Path | None = None,
    context_bytes: int = 360,
) -> dict[str, object]:
    """Validate frozen evidence and write a deterministic offline review UI."""

    inventory = Path(inventory_path)
    out = Path(output_dir)
    root = Path(snapshot_root) if snapshot_root is not None else inventory.parent
    if type(context_bytes) is not int or context_bytes < 0:
        raise EvidenceGraphFormatError("context_bytes must be a non-negative integer")
    queue, source_files, counts = _build_queue(
        inventory,
        snapshot_root=root,
        context_bytes=context_bytes,
    )
    translation_bytes: bytes | None = None
    if translations_path is not None:
        translation_bytes = _apply_translations(queue, Path(translations_path))
    decisions = _decision_template(queue)
    html_bytes = _render_html(queue, counts)

    out.mkdir(parents=True, exist_ok=True)
    sources_dir = out / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    expected_source_names = {Path(relative).name for relative in source_files}
    for existing in sources_dir.iterdir():
        if existing.is_file() and existing.name not in expected_source_names:
            existing.unlink()
    for relative, content in sorted(source_files.items()):
        _atomic_write(out / relative, content)
    if translation_bytes is not None:
        _atomic_write(out / "translations.zh-CN.json", translation_bytes)
    else:
        try:
            (out / "translations.zh-CN.json").unlink()
        except FileNotFoundError:
            pass
    save_json(out / "review_queue.json", queue)
    save_json(out / "review_decisions.template.json", decisions)
    _atomic_write(out / "index.html", html_bytes)

    generated = [
        out / "index.html",
        out / "review_queue.json",
        out / "review_decisions.template.json",
        *([out / "translations.zh-CN.json"] if translation_bytes is not None else []),
        *(out / relative for relative in sorted(source_files)),
    ]
    manifest = {
        "schema_version": REVIEW_PACKET_MANIFEST_SCHEMA,
        "corpus_snapshot": queue["corpus_snapshot"],
        "evidence_graph_hash": queue["evidence_graph_hash"],
        "corpus_registry_hash": queue["corpus_registry_hash"],
        "candidate_id": queue["candidate_id"],
        "translation_sha256": (
            queue.get("translation", {}).get("sha256")
            if isinstance(queue.get("translation"), Mapping)
            else None
        ),
        "counts": counts,
        "files": [_file_record(path, out) for path in generated],
    }
    save_json(out / "manifest.json", manifest)
    verified = verify_review_packet(out)
    return {
        "ok": True,
        "candidate_id": queue["candidate_id"],
        "corpus_snapshot": queue["corpus_snapshot"],
        "evidence_graph_hash": queue["evidence_graph_hash"],
        "counts": counts,
        "manifest_sha256": sha256_bytes((out / "manifest.json").read_bytes()),
        "verified_files": verified["verified_files"],
        "output_dir": str(out),
    }


def verify_review_packet(output_dir: str | Path) -> dict[str, object]:
    """Verify every file declared by a generated review-packet manifest."""

    root = Path(output_dir)
    raw = load_json(root / "manifest.json")
    manifest = _strict_object(raw, "manifest")
    expected_keys = {
        "schema_version",
        "corpus_snapshot",
        "evidence_graph_hash",
        "corpus_registry_hash",
        "candidate_id",
        "translation_sha256",
        "counts",
        "files",
    }
    if set(manifest) != expected_keys:
        raise EvidenceGraphFormatError(
            f"manifest: keys must be exactly {sorted(expected_keys)!r}"
        )
    if manifest["schema_version"] != REVIEW_PACKET_MANIFEST_SCHEMA:
        raise EvidenceGraphFormatError(
            f"manifest.schema_version: expected {REVIEW_PACKET_MANIFEST_SCHEMA!r}"
        )
    files = manifest["files"]
    if not isinstance(files, list) or not files:
        raise EvidenceGraphFormatError("manifest.files: expected a non-empty array")
    seen: set[str] = set()
    for index, raw_record in enumerate(files):
        record = _strict_object(raw_record, f"manifest.files[{index}]")
        if set(record) != {"path", "bytes", "sha256"}:
            raise EvidenceGraphFormatError(
                f"manifest.files[{index}]: expected path/bytes/sha256"
            )
        relative = record["path"]
        if not isinstance(relative, str) or not relative or relative in seen:
            raise EvidenceGraphFormatError(
                f"manifest.files[{index}].path: invalid or duplicate path"
            )
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise EvidenceGraphFormatError(
                f"manifest.files[{index}].path: must remain inside the packet"
            )
        seen.add(relative)
        path = root / relative_path
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise EvidenceGraphFormatError(f"{path}: cannot read: {exc}") from exc
        if len(content) != record["bytes"]:
            raise EvidenceGraphFormatError(f"{path}: byte length mismatch")
        if sha256_bytes(content) != record["sha256"]:
            raise EvidenceGraphFormatError(f"{path}: SHA-256 mismatch")
    return {
        "ok": True,
        "candidate_id": manifest["candidate_id"],
        "corpus_snapshot": manifest["corpus_snapshot"],
        "evidence_graph_hash": manifest["evidence_graph_hash"],
        "verified_files": len(seen),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=None,
        help="base directory for inventory blob_path values",
    )
    parser.add_argument(
        "--context-bytes",
        type=int,
        default=360,
        help="frozen bytes shown before and after each exact support span",
    )
    parser.add_argument(
        "--translations",
        type=Path,
        default=None,
        help="optional validated zh-CN translation overlay for human review",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify an existing --out-dir without rebuilding it",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.verify_only:
            result = verify_review_packet(args.out_dir)
        else:
            result = build_review_packet(
                args.inventory,
                args.out_dir,
                snapshot_root=args.snapshot_root,
                translations_path=args.translations,
                context_bytes=args.context_bytes,
            )
    except (EvidenceGraphFormatError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
