#!/usr/bin/env python3
"""Render a compact E1 human-audit queue with machine precheck context."""

from __future__ import annotations

import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.world_index.e1 import canonical_json, iter_jsonl, normalize_text
from src.world_index.e1_compact import (
    CompactWorldIndexWriter,
    _prepare_record,
)
from scripts.create_e1_manual_audit_queue import queue_definition_id


STRATUM_LABELS = {
    "commerce_product_with_review": "商品页（含评论）",
    "commerce_product": "商品页",
    "community_thread_with_replies": "论坛主题（含回复）",
    "community_thread": "论坛主题",
    "wiki_article_with_tables": "百科文章（含表格）",
    "wiki_article_with_links": "百科文章（含链接）",
    "wiki_article": "百科文章",
    "wiki_redirect": "百科重定向页",
    "wiki_resource": "百科资源页",
}

STRATUM_GUIDANCE = {
    "commerce_product_with_review": (
        "重点看商品标题、规格/价格等字段，以及评论正文、作者、时间和评分"
        "是否保留且没有串到别处。"
    ),
    "commerce_product": (
        "重点看商品标题、说明、规格、价格、库存等可见信息是否缺失或错位。"
    ),
    "community_thread_with_replies": (
        "重点看主题正文、作者/时间，以及回复内容和父子层级是否正确。"
    ),
    "community_thread": (
        "重点看主题标题、正文、作者、时间和帖子顺序是否正确。"
    ),
    "wiki_article_with_tables": (
        "重点看正文与章节顺序，并确认表格没有丢行、丢列或跨行错位。"
    ),
    "wiki_article_with_links": (
        "重点看正文与章节顺序，并抽看链接文字和跳转目标是否对应。"
    ),
    "wiki_article": "重点看标题、正文、章节顺序以及特殊字符是否正常。",
    "wiki_redirect": "确认生成页明确显示重定向，并且目标页面名称正确。",
    "wiki_resource": (
        "确认资源类型和大小说明正确；被有意省略的二进制内容必须有明确标记。"
    ),
}

CHECK_LABELS = {
    "raw_to_parsed_lineage": "原始材料与解析结果属于同一个页面",
    "parsed_to_served_content": "canonical 结构审计投影没有明显缺失、乱码或错误转义",
    "title_and_alias_identity": "标题、URL 与页面身份对应",
    "block_text_and_section_coordinates": "正文段落和章节顺序正确",
    "table_row_column_and_span_coordinates": "表格行列及跨行跨列关系正确",
    "outgoing_link_target_and_anchor": "链接文字和跳转目标对应",
    "structured_field_value_and_provenance": "规格等结构化字段的值与来源正确",
    "interaction_text_author_time_score_attribution": (
        "评论/帖子正文、作者、时间和评分没有串位"
    ),
    "interaction_parent_child_tree": "评论或回复的父子层级正确",
    "redirect_target_identity": "重定向目标正确",
    "resource_mime_size_and_omission_marker": (
        "资源类型、大小和省略标记正确"
    ),
}


def open_compact(path: Path) -> CompactWorldIndexWriter:
    writer = object.__new__(CompactWorldIndexWriter)
    writer.path = path
    writer.snapshot_id = ""
    writer.conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    writer.conn.row_factory = sqlite3.Row
    snapshot = writer.conn.execute(
        "SELECT value_json FROM metadata WHERE key='snapshot_id'"
    ).fetchone()
    writer.snapshot_id = json.loads(snapshot[0]) if snapshot else ""
    return writer


def load_source_records(
    source_dir: Path,
    wanted: set[tuple[str, str]],
) -> dict[tuple[str, str], dict[str, Any]]:
    manifest = json.loads(
        (source_dir / "source-manifest.json").read_text(encoding="utf-8")
    )
    found: dict[tuple[str, str], dict[str, Any]] = {}
    wanted_by_pack: dict[str, set[str]] = {}
    for pack_id, source_id in wanted:
        wanted_by_pack.setdefault(pack_id, set()).add(source_id)
    for pack in manifest["packs"]:
        pack_id = str(pack["pack_id"])
        pending = wanted_by_pack.get(pack_id)
        if not pending:
            continue
        for record in iter_jsonl(source_dir / pack["records_path"]):
            source_id = str(record["source_id"])
            if source_id in pending:
                found[(pack_id, source_id)] = record
                if len(found) == len(wanted):
                    return found
    return found


def excerpt(values: list[dict[str, Any]], limit: int = 5) -> str:
    if not values:
        return "<em>none</em>"
    selected = values[:limit]
    if len(values) > limit:
        selected.append({"omitted_items": len(values) - limit})
    return "<pre>" + escape(
        json.dumps(selected, ensure_ascii=False, indent=2)
    ) + "</pre>"


def _interaction_depths(
    interactions: list[dict[str, Any]],
) -> dict[str, int]:
    by_id = {
        str(item.get("interaction_id") or ""): item
        for item in interactions
    }
    cache: dict[str, int] = {}

    def depth(interaction_id: str, trail: set[str]) -> int:
        if interaction_id in cache:
            return cache[interaction_id]
        if interaction_id in trail:
            return 0
        parent_id = str(
            (by_id.get(interaction_id) or {}).get(
                "parent_interaction_id"
            ) or ""
        )
        if not parent_id or parent_id not in by_id:
            value = 0
        else:
            value = 1 + depth(parent_id, trail | {interaction_id})
        cache[interaction_id] = value
        return value

    return {interaction_id: depth(interaction_id, set()) for interaction_id in by_id}


def projection_structure_failures(
    rendered: str,
    source_record: dict[str, Any],
    artifact: dict[str, Any],
) -> list[str]:
    """Check that audit-only visualizations expose canonical structure."""

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(rendered, "lxml")
    failures: list[str] = []
    page_type = str(source_record.get("page_type") or "")

    if page_type == "wiki_resource":
        title = normalize_text(
            soup.title.get_text(" ", strip=True) if soup.title else ""
        )
        if not title or title.casefold() in {"null", "none", "undefined"}:
            failures.append("resource_projection_title_unusable")
        identity = {
            str(node.get("data-dra-identity-field") or ""): normalize_text(
                node.get_text(" ", strip=True)
            )
            for node in soup.select("[data-dra-identity-field]")
        }
        for field_name in (
            "source_id",
            "archive_entry_path",
            "mime_type",
            "raw_content_hash",
            "capture_or_archive_locator",
        ):
            expected = normalize_text(source_record.get(field_name))
            if expected and identity.get(field_name) != expected:
                failures.append(
                    f"resource_projection_{field_name}_mismatch"
                )
        omitted = bool(
            (source_record.get("metadata") or {}).get(
                "resource_content_omitted"
            )
        )
        identity_section = soup.select_one("#document-identity")
        if omitted and (
            identity.get("resource_content_omitted") != "true"
            or identity_section is None
            or identity_section.get("data-dra-resource-omitted") != "true"
        ):
            failures.append("resource_projection_omission_marker_missing")
        for field in artifact.get("structured_fields") or []:
            if normalize_text(field.get("name")) != "item_size":
                continue
            node = soup.select_one('[data-dra-field-name="item_size"]')
            expected = " ".join(filter(None, (
                normalize_text(field.get("value")),
                normalize_text(field.get("unit")),
            )))
            if node is None or normalize_text(
                node.get_text(" ", strip=True)
            ) != expected:
                failures.append("resource_projection_item_size_mismatch")

    expected_cells = [
        block for block in artifact.get("blocks") or []
        if block.get("block_type") == "table_cell"
        and isinstance((block.get("structural") or {}).get("table_index"), int)
    ]
    if expected_cells:
        expected_signatures = []
        for block in expected_cells:
            structural = dict(block.get("structural") or {})
            expected_signatures.append((
                int(structural["table_index"]),
                int(structural.get("row_index") or 0),
                int(structural.get("column_index") or 0),
                max(1, int(
                    structural.get("effective_rowspan")
                    or structural.get("rowspan")
                    or 1
                )),
                max(1, int(
                    structural.get("effective_colspan")
                    or structural.get("colspan")
                    or 1
                )),
                normalize_text(block.get("text")),
            ))
        actual_signatures = []
        for node in soup.select(
            "#audit-table-projections th[data-dra-audit-column-index],"
            "#audit-table-projections td[data-dra-audit-column-index]"
        ):
            actual_signatures.append((
                int(node.get("data-dra-audit-table-index") or 0),
                int(node.get("data-dra-audit-row-index") or 0),
                int(node.get("data-dra-audit-column-index") or 0),
                max(1, int(node.get("rowspan") or 1)),
                max(1, int(node.get("colspan") or 1)),
                normalize_text(node.get_text(" ", strip=True)),
            ))
        if sorted(expected_signatures) != sorted(actual_signatures):
            failures.append("table_audit_projection_coordinate_mismatch")

    interactions = list(artifact.get("interactions") or [])
    expected_depths = _interaction_depths(interactions)
    if expected_depths:
        articles = {
            str(node.get("data-dra-interaction-id") or ""): node
            for node in soup.select("article[data-dra-interaction-id]")
        }
        if set(articles) != set(expected_depths):
            failures.append("interaction_audit_projection_id_mismatch")
        else:
            for interaction_id, expected_depth in expected_depths.items():
                node = articles[interaction_id]
                if int(node.get("data-dra-audit-depth") or 0) != expected_depth:
                    failures.append(
                        "interaction_audit_projection_depth_mismatch"
                    )
                    break
                if expected_depth > 0 and node.select_one(
                    ".reply-relation"
                ) is None:
                    failures.append(
                        "interaction_audit_projection_parent_label_missing"
                    )
                    break
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    queue_path = args.queue.resolve()
    build_dir = args.build_dir.resolve()
    source_dir = args.source_dir.resolve()
    out_dir = args.out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()) and not args.overwrite:
        raise SystemExit(
            f"refusing non-empty output directory without --overwrite: {out_dir}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = out_dir / "served-pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    source_records_dir = out_dir / "source-records"
    source_records_dir.mkdir(parents=True, exist_ok=True)
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    actual_queue_definition_id = queue_definition_id(queue)
    if queue.get("queue_definition_id") != actual_queue_definition_id:
        raise SystemExit("manual audit queue definition hash mismatch")
    wanted = {
        (
            str(item["document"]["pack_id"]),
            str(item["document"]["source_id"]),
        )
        for item in queue["items"]
    }
    source_records = load_source_records(source_dir, wanted)
    writer = open_compact(build_dir / "world-index.sqlite")
    items_report: list[dict[str, Any]] = []
    cards: list[str] = []
    total_items = len(queue["items"])
    for position, item in enumerate(queue["items"], start=1):
        audit_id = str(item["audit_item_id"])
        document = item["document"]
        page_id = str(document["page_snapshot_id"])
        key = (str(document["pack_id"]), str(document["source_id"]))
        source_record = source_records.get(key)
        source_record_path: Path | None = None
        source_html_path: Path | None = None
        if source_record is not None:
            source_descriptor = dict(source_record)
            raw_html = source_descriptor.pop("html_content", None)
            if raw_html is not None:
                raw_html_bytes = str(raw_html).encode("utf-8")
                source_html_path = (
                    source_records_dir / f"{audit_id}.html.txt"
                )
                source_html_path.write_bytes(raw_html_bytes)
                source_descriptor["html_content"] = {
                    "externalized_path": str(source_html_path),
                    "utf8_bytes": len(raw_html_bytes),
                    "sha256": sha256(raw_html_bytes).hexdigest(),
                }
            source_record_path = source_records_dir / f"{audit_id}.json"
            source_record_path.write_text(
                json.dumps(
                    source_descriptor,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ) + "\n",
                encoding="utf-8",
            )
        row = writer.conn.execute(
            "SELECT * FROM documents WHERE page_snapshot_id=?",
            (page_id,),
        ).fetchone()
        failures: list[str] = []
        prepared = None
        stored_artifact: dict[str, Any] | None = None
        if source_record is None:
            failures.append("source_record_missing")
        if row is None:
            failures.append("compiled_document_missing")
        if source_record is not None and row is not None:
            try:
                prepared = _prepare_record(
                    source_record, snapshot_id=writer.snapshot_id
                )
                stored_artifact = writer._artifact_from_row(row)
                expected_artifact = json.loads(prepared.artifact_json)
                if canonical_json(stored_artifact) != canonical_json(
                    expected_artifact
                ):
                    failures.append("prepared_artifact_mismatch")
                for name, expected, actual in (
                    ("raw_hash", prepared.raw_hash, row["raw_content_hash"]),
                    (
                        "parsed_hash", prepared.parsed_hash,
                        row["parsed_content_hash"],
                    ),
                    (
                        "rendered_hash", prepared.rendered_hash,
                        row["rendered_content_hash"],
                    ),
                ):
                    if expected != actual:
                        failures.append(f"{name}_mismatch")
            except Exception as exc:
                failures.append(f"precheck_exception:{repr(exc)}")
        rendered = ""
        if row is not None:
            try:
                rendered = writer.render_by_id(page_id)
                if sha256(rendered.encode("utf-8")).hexdigest() != row[
                    "rendered_content_hash"
                ]:
                    failures.append("served_render_hash_mismatch")
            except Exception as exc:
                failures.append(f"render_exception:{repr(exc)}")
        if rendered and source_record is not None and stored_artifact is not None:
            try:
                failures.extend(projection_structure_failures(
                    rendered, source_record, stored_artifact
                ))
            except Exception as exc:
                failures.append(
                    f"projection_precheck_exception:{repr(exc)}"
                )
        page_path = pages_dir / f"{audit_id}.html"
        if rendered:
            page_path.write_text(rendered, encoding="utf-8")
        artifact = stored_artifact or {
            "blocks": [], "links": [], "structured_fields": [],
            "interactions": [],
        }
        report_item = {
            "audit_item_id": audit_id,
            "page_snapshot_id": page_id,
            "stratum": item["stratum"],
            "machine_precheck_passed": not failures,
            "machine_precheck_failures": failures,
            "served_page": str(page_path),
            "source_record": (
                str(source_record_path) if source_record_path else None
            ),
            "source_html_text": (
                str(source_html_path) if source_html_path else None
            ),
        }
        items_report.append(report_item)
        checkboxes = "".join(
            f'<li><label><input type="checkbox" class="audit-check" '
            f'data-check="{escape(check)}"> '
            f'{escape(CHECK_LABELS.get(check, check))}'
            f' <small class="code-label">{escape(check)}</small></label></li>'
            for check in item["required_checks"]
        )
        source_links = []
        if source_record_path is not None:
            source_links.append(
                f'<a class="open-link" target="_blank" '
                f'href="source-records/{escape(source_record_path.name)}">'
                "② 打开原始记录</a>"
            )
        if source_html_path is not None:
            source_links.append(
                f'<a class="open-link" target="_blank" '
                f'href="source-records/{escape(source_html_path.name)}">'
                "③ 打开原始 HTML 文本（需要时）</a>"
            )
        source_links_html = " &middot; ".join(source_links)
        prior_reviews = list(item.get("review_history") or [])
        prior_html = ""
        if prior_reviews:
            prior = prior_reviews[-1]
            prior_review = dict(prior.get("review") or {})
            prior_html = (
                '<aside class="prior-review"><strong>旧 build 审阅记录'
                '（仅供参考，不计入本次通过）：</strong> '
                f"状态 {escape(str(prior_review.get('status') or 'pending'))}；"
                f"类别 {escape(str(prior_review.get('systematic_loss_category') or '无'))}；"
                f"备注 {escape(str(prior_review.get('notes') or '无'))}"
                "</aside>"
            )
        cards.append(f"""
        <article data-audit-item-id="{escape(audit_id)}">
          <h2>第 {position}/{total_items} 项 ·
              {escape(STRATUM_LABELS.get(item['stratum'], item['stratum']))}</h2>
          <p class="guidance"><strong>这一项看什么：</strong>
             {escape(STRATUM_GUIDANCE.get(item['stratum'], '检查 canonical 结构审计投影是否与原始材料一致。'))}</p>
          <p><strong>机器预检：</strong>
             {'通过（仍需目视确认）' if not failures else '失败：' + escape(', '.join(failures))}</p>
          <p><strong>页面标题：</strong> {escape(str(document.get('title') or '（无标题）'))}<br>
             <strong>页面 URL：</strong> {escape(str(document.get('canonical_url') or ''))}<br>
             <span class="technical"><strong>原始定位：</strong>
             {escape(str(document.get('capture_or_archive_locator') or ''))}</span></p>
          <p class="open-row"><a class="open-link" target="_blank"
             href="served-pages/{escape(audit_id)}.html">① 打开 canonical 结构审计投影（非原站、非 harness 页面）</a>
             {' &middot; ' + source_links_html if source_links_html else ''}</p>
          {prior_html}
          <section class="review-box">
            <p><strong>看完以后选择：</strong></p>
            <button type="button" class="mark-pass primary">✓ 我已对照，结构与来源一致</button>
            <button type="button" class="mark-fail danger">✗ 我发现了问题</button>
            <label>当前结论
              <select class="review-status">
                <option value="pending">尚未检查</option>
                <option value="passed">通过</option>
                <option value="failed">失败</option>
              </select>
            </label>
            <label>问题类别（失败时填写）
              <input class="loss-category" type="text" list="loss-categories"
                     placeholder="例如：正文缺失、表格错位、回复层级错误">
            </label>
            <label>问题说明（失败时写一句即可）
              <textarea class="review-notes"></textarea></label>
          </section>
          <p><strong>逐项确认：</strong></p><ul class="check-list">{checkboxes}</ul>
          <details><summary>辅助：解析后的正文块（{len(artifact['blocks'])}）</summary>
            {excerpt(artifact['blocks'])}</details>
          <details><summary>辅助：解析后的表格单元格</summary>
            {excerpt([b for b in artifact['blocks'] if b.get('block_type') == 'table_cell'])}</details>
          <details><summary>辅助：结构化字段（{len(artifact['structured_fields'])}）</summary>
            {excerpt(artifact['structured_fields'])}</details>
          <details><summary>辅助：评论、帖子或回复（{len(artifact['interactions'])}）</summary>
            {excerpt(artifact['interactions'])}</details>
          <details><summary>辅助：页面链接（{len(artifact['links'])}）</summary>
            {excerpt(artifact['links'])}</details>
        </article>
        """)
    writer.close()
    machine_report = {
        "schema": "dra_e1_manual_audit_machine_precheck_v1",
        "auditor_sha256": sha256(
            Path(__file__).resolve().read_bytes()
        ).hexdigest(),
        "queue": str(queue_path),
        "queue_definition_id": actual_queue_definition_id,
        "logical_build_id": queue["logical_build_id"],
        "source_manifest_id": queue["source_manifest_id"],
        "items": items_report,
        "summary": {
            "total": len(items_report),
            "passed": sum(
                1 for item in items_report
                if item["machine_precheck_passed"]
            ),
            "failed": sum(
                1 for item in items_report
                if not item["machine_precheck_passed"]
            ),
        },
        "human_gate_satisfied": False,
        "note": (
            "Machine precheck is navigation and corruption triage only. It "
            "does not populate review fields or satisfy the human audit gate."
        ),
    }
    (out_dir / "machine-preaudit.json").write_text(
        json.dumps(
            machine_report, ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n",
        encoding="utf-8",
    )
    embedded_queue = json.dumps(
        queue, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).replace("<", "\\u003c")
    review_script = r"""
<script>
const queue = JSON.parse(document.getElementById('queue-data').textContent);
const byId = new Map(queue.items.map(item => [item.audit_item_id, item]));
const cards = [...document.querySelectorAll('article[data-audit-item-id]')];
const storageKey = `dra-e1-human-audit:${queue.queue_definition_id}`;
const draftStatus = document.getElementById('draft-status');

function validateImportedQueue(candidate) {
  if (!candidate || typeof candidate !== 'object') {
    throw new Error('导入的 JSON 不是有效对象');
  }
  for (const key of ['schema', 'logical_build_id', 'source_manifest_id',
                     'queue_definition_id']) {
    if (candidate[key] !== queue[key]) {
      throw new Error(`${key} 与当前审阅包不匹配`);
    }
  }
  if (!Array.isArray(candidate.items) ||
      candidate.items.length !== queue.items.length) {
    throw new Error('抽查项目数量不匹配');
  }
  const expected = new Set(queue.items.map(item => item.audit_item_id));
  const observed = new Set(candidate.items.map(item => item.audit_item_id));
  if (observed.size !== expected.size ||
      [...expected].some(itemId => !observed.has(itemId))) {
    throw new Error('抽查项目身份不匹配');
  }
}

function applyReviewState(candidate, savedReviewerId = null) {
  validateImportedQueue(candidate);
  const candidateById = new Map(
    candidate.items.map(item => [item.audit_item_id, item]));
  const reviewerIds = new Set(candidate.items
    .map(item => item.review && item.review.reviewer_id)
    .filter(Boolean));
  if (reviewerIds.size > 1 && !savedReviewerId) {
    throw new Error('该进度文件包含多个审阅人，当前页面无法安全合并');
  }
  document.getElementById('reviewer-id').value =
    savedReviewerId || [...reviewerIds][0] || '';
  for (const card of cards) {
    const item = byId.get(card.dataset.auditItemId);
    const imported = candidateById.get(item.audit_item_id);
    const review = imported.review || {};
    const status = ['pending', 'passed', 'failed'].includes(review.status)
      ? review.status : 'pending';
    card.querySelector('.review-status').value = status;
    card.querySelector('.loss-category').value =
      review.systematic_loss_category || '';
    card.querySelector('.review-notes').value = review.notes || '';
    const results = review.check_results || {};
    for (const check of card.querySelectorAll('.audit-check')) {
      check.checked = results[check.dataset.check] === true;
    }
    item.review = {
      status,
      reviewer_id: status === 'pending' ? null : (review.reviewer_id || null),
      reviewer_kind: status === 'pending' ? null : (review.reviewer_kind || null),
      reviewed_at: status === 'pending' ? null : (review.reviewed_at || null),
      check_results: status === 'pending' ? {} : results,
      systematic_loss_category: review.systematic_loss_category || null,
      notes: review.notes || null,
    };
  }
  updateProgress();
}

function updateProgress() {
  const decided = cards.filter(card =>
    card.querySelector('.review-status').value !== 'pending').length;
  document.getElementById('progress').textContent =
    `已完成 ${decided}/${cards.length}`;
  const pendingOnly = document.getElementById('pending-only').checked;
  for (const card of cards) {
    const isPending = card.querySelector('.review-status').value === 'pending';
    card.hidden = pendingOnly && !isPending;
  }
}

function collectReviewState() {
  const reviewerId = document.getElementById('reviewer-id').value.trim();
  const now = new Date().toISOString();
  const warnings = [];
  for (const card of cards) {
    const item = byId.get(card.dataset.auditItemId);
    const status = card.querySelector('.review-status').value;
    const checkResults = {};
    for (const check of card.querySelectorAll('.audit-check')) {
      checkResults[check.dataset.check] = check.checked;
    }
    if (status !== 'pending' && !reviewerId) {
      warnings.push(`${item.audit_item_id}：缺少审阅人姓名或代号`);
    }
    if (status === 'passed' && Object.values(checkResults).some(value => !value)) {
      warnings.push(`${item.audit_item_id}：结论为通过，但仍有检查项未勾选`);
    }
    item.review = {
      status,
      reviewer_id: status === 'pending' ? null : reviewerId,
      reviewer_kind: status === 'pending' ? null : 'human',
      reviewed_at: status === 'pending' ? null :
        (item.review.reviewed_at || now),
      check_results: status === 'pending' ? {} : checkResults,
      systematic_loss_category:
        card.querySelector('.loss-category').value.trim() || null,
      notes: card.querySelector('.review-notes').value.trim() || null,
    };
  }
  const statuses = queue.items.map(item => item.review.status);
  queue.summary = {
    total: queue.items.length,
    pending: statuses.filter(value => value === 'pending').length,
    passed: statuses.filter(value => value === 'passed').length,
    failed: statuses.filter(value => value === 'failed').length,
    formal_gate_passed: false,
  };
  return warnings;
}

function saveDraftLocally() {
  collectReviewState();
  try {
    const payload = {
      queue,
      reviewer_id: document.getElementById('reviewer-id').value.trim(),
      saved_at: new Date().toISOString(),
    };
    localStorage.setItem(storageKey, JSON.stringify(payload));
    draftStatus.textContent = `进度已保存：${payload.saved_at}`;
  } catch (error) {
    draftStatus.textContent = `本地保存不可用：${error.message}`;
  }
}

let saveTimer = null;
function scheduleDraftSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveDraftLocally, 300);
}

for (const card of cards) {
  card.querySelector('.mark-pass').addEventListener('click', () => {
    for (const check of card.querySelectorAll('.audit-check')) check.checked = true;
    card.querySelector('.review-status').value = 'passed';
    updateProgress();
    scheduleDraftSave();
  });
  card.querySelector('.mark-fail').addEventListener('click', () => {
    card.querySelector('.review-status').value = 'failed';
    card.querySelector('.review-notes').focus();
    updateProgress();
    scheduleDraftSave();
  });
  card.querySelector('.review-status').addEventListener('change', () => {
    updateProgress();
    scheduleDraftSave();
  });
  for (const check of card.querySelectorAll('.audit-check')) {
    check.addEventListener('change', scheduleDraftSave);
  }
  card.querySelector('.loss-category').addEventListener('input', scheduleDraftSave);
  card.querySelector('.review-notes').addEventListener('input', scheduleDraftSave);
}
document.getElementById('reviewer-id').addEventListener('input', scheduleDraftSave);
document.getElementById('save-draft').addEventListener('click', saveDraftLocally);
document.getElementById('pending-only').addEventListener('change', updateProgress);
document.getElementById('next-pending').addEventListener('click', () => {
  const next = cards.find(card =>
    card.querySelector('.review-status').value === 'pending');
  if (next) next.scrollIntoView({behavior: 'smooth', block: 'start'});
  else window.alert('全部 180 项都已经给出结论。');
});
document.getElementById('import-reviewed').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const payload = JSON.parse(await file.text());
    const candidate = payload.queue || payload;
    applyReviewState(candidate, payload.reviewer_id || null);
    saveDraftLocally();
    draftStatus.textContent = `已导入 ${file.name} 并保存进度`;
  } catch (error) {
    window.alert(`导入被拒绝：${error.message}`);
    event.target.value = '';
  }
});

document.getElementById('export-reviewed').addEventListener('click', () => {
  const warnings = collectReviewState();
  if (warnings.length && !window.confirm(
      `${warnings.slice(0, 10).join('\n')}\n\n当前记录尚不完整，仍然导出草稿吗？`)) {
    return;
  }
  saveDraftLocally();
  const blob = new Blob([JSON.stringify(queue, null, 2) + '\n'],
                        {type: 'application/json'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `manual-audit-queue-reviewed-${queue.logical_build_id.slice(0, 12)}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
});
updateProgress();
try {
  const saved = localStorage.getItem(storageKey);
  if (saved) {
    const payload = JSON.parse(saved);
    applyReviewState(payload.queue, payload.reviewer_id || null);
    draftStatus.textContent = `已恢复本地进度：${payload.saved_at}`;
  }
} catch (error) {
  draftStatus.textContent = `本地进度恢复失败：${error.message}`;
}
</script>
"""
    (out_dir / "index.html").write_text(
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
        "<title>DRA E1 canonical 结构审计抽查</title>"
        "<style>body{font:15px sans-serif;max-width:1100px;margin:auto;padding:1rem;"
        "color:#172033;background:#f7f8fa}"
        "article{border:1px solid #cbd3df;border-radius:10px;padding:1rem;"
        "margin:1rem 0;background:#fff;scroll-margin-top:7rem}"
        "pre{white-space:pre-wrap;max-height:30rem;overflow:auto}"
        ".intro{background:#eef5ff;border-left:5px solid #2f6feb;padding:1rem;"
        "border-radius:6px}.toolbar{position:sticky;top:0;background:#fff;"
        "border:1px solid #8794a8;border-radius:8px;padding:1rem;z-index:2;"
        "box-shadow:0 3px 12px #0002}.review-box{background:#f4f6f8;"
        "padding:.75rem;border-radius:8px}"
        ".review-box label{display:block;margin:.6rem 0}textarea{width:100%;min-height:4rem}"
        ".audit-check{transform:scale(1.15);margin-right:.4rem}.check-list li{margin:.45rem 0}"
        ".code-label,.technical{color:#687386;font-size:.82em}.guidance{font-size:1.05em}"
        ".prior-review{background:#fff7d6;border:1px solid #d9a600;"
        "padding:.75rem;margin:.75rem 0;border-radius:6px}"
        ".open-link,button{display:inline-block;margin:.25rem;padding:.5rem .75rem;"
        "border-radius:6px}.open-link{background:#eaf1ff;color:#174ea6;"
        "text-decoration:none}.primary{background:#18794e;color:#fff;border:0}"
        ".danger{background:#b42318;color:#fff;border:0}button{cursor:pointer}"
        "</style><h1>DRA E1：检查 canonical 结构审计投影</h1>"
        "<div class='intro'><strong>你只需要做下面四步：</strong><ol>"
        "<li>每一项先点开“canonical 结构审计投影”，再点开“原始记录”。该投影不要求复刻原站 CSS，也不会提供给 harness。</li>"
        "<li>按照该项的中文提示，看内容有没有明显缺失、乱码、错位或串绑。</li>"
        "<li>正常就点绿色按钮；有问题就点红色按钮并写一句原因。</li>"
        "<li>180 项完成后，点击“导出最终审阅 JSON”。</li></ol>"
        "<p><strong>不需要看代码，也不评价网页是否美观。</strong>只判断原始材料"
        "有没有被正确映射到结构审计投影。</p></div>"
        "<p><strong>注意：</strong>审阅材料含 benchmark-local 受限数据，rights/PII"
        " 审核前不要公开传播。</p>"
        "<datalist id='loss-categories'><option value='正文缺失'>"
        "<option value='乱码或错误转义'><option value='表格行列错位'>"
        "<option value='商品字段错误'><option value='评论或回复串绑'>"
        "<option value='回复层级错误'><option value='链接或重定向错误'>"
        "</datalist>"
        "<div class='toolbar'><label>审阅人姓名或代号 "
        "<input id='reviewer-id' type='text'></label> "
        "<strong id='progress'></strong> "
        "<button id='next-pending' type='button'>跳到下一条未检查</button> "
        "<label><input id='pending-only' type='checkbox'>只显示未检查项</label> "
        "<button id='save-draft' type='button'>保存当前进度</button> "
        "<label>导入之前的进度 JSON "
        "<input id='import-reviewed' type='file' accept='application/json'></label> "
        "<button id='export-reviewed' type='button'>导出最终审阅 JSON</button>"
        "<br><small id='draft-status'>尚未载入本地进度。</small><br>"
        "<small>页面会自动保存进度。未检查完或信息不一致的文件无法通过正式验收。</small>"
        "</div>"
        + "".join(cards)
        + f"<script type='application/json' id='queue-data'>{embedded_queue}</script>"
        + review_script,
        encoding="utf-8",
    )
    print(json.dumps({
        "index": str(out_dir / "index.html"),
        "machine_preaudit": str(out_dir / "machine-preaudit.json"),
        "summary": machine_report["summary"],
    }, ensure_ascii=False, indent=2))
    return 0 if machine_report["summary"]["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
