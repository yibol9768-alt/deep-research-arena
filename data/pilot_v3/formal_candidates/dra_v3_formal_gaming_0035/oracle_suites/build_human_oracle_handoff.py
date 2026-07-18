#!/usr/bin/env python3
"""Build the blank, independent pending-human oracle handoff for Q35.

This builder exposes only the public task/query and frozen search/source bytes.
It never copies the private case, synthetic reports, or graph annotations into
the reviewer-visible directory, and it never prefills a human answer.
"""

from __future__ import annotations

import hashlib
import html
import json
import shutil
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
TASK_ID = "dra_v3_formal_gaming_0035"
RUN_ID = "q35-human-formal-v1"
HUMAN_ROOT = HERE / "human_pending"

CASE_PATH = (
    ROOT / "data/golden/cases_v3/formal_candidates" / f"{TASK_ID}.json"
)
PUBLIC_TASK_PATH = (
    ROOT / "data/tasks/deep_research/v3/formal_candidates" / f"{TASK_ID}.json"
)
QUERY_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "query_candidates/attempt2.txt"
)
INVENTORY_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "graph_inputs/inventory.json"
)
GRAPH_DIR = (
    ROOT
    / "data/evidence_graph"
    / "dra-v3-formal-gaming-0035-console-generation-value-boundary-20260716-r1"
)
PROTOCOL_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "protocol_manifests/protocol.json"
)
REVIEW_MANIFEST_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "oracle_suites/human_pending/evidence_review_packet/manifest.json"
)
SUITE_PATH = HERE / "synthetic/suite.json"
VALIDATION_PATH = HERE / "synthetic/validation.json"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def copy_exact(source: Path, destination: Path, expected_sha256: str) -> None:
    if sha256_file(source) != expected_sha256:
        raise ValueError(f"frozen source hash mismatch: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if sha256_file(destination) != expected_sha256:
        raise ValueError(f"copied source hash mismatch: {destination}")


def binding(path: Path, *, relative_to: Path = HUMAN_ROOT) -> dict[str, str]:
    return {
        "path": path.relative_to(relative_to).as_posix(),
        "sha256": sha256_file(path),
    }


def build_snapshots(
    inventory: dict[str, Any], case: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    documents = inventory.get("documents")
    if not isinstance(documents, list):
        raise ValueError("inventory.documents must be an array")
    document_by_url = {
        str(document["source_url"]): document
        for document in documents
        if isinstance(document, dict)
    }

    search_rows: list[dict[str, Any]] = []
    for document in documents:
        if document.get("source_type") != "search_result":
            continue
        source = ROOT / str(document["blob_path"])
        destination = HUMAN_ROOT / "human_inputs/searches" / source.name
        digest = str(document["content_sha256"])
        copy_exact(source, destination, digest)
        search_rows.append(
            {
                "registry_id": str(document["registry_id"]),
                "entry_url": str(document["source_url"]),
                "content_sha256": digest,
                "snapshot_path": destination.relative_to(HUMAN_ROOT).as_posix(),
                "snapshot_file_sha256": sha256_file(destination),
            }
        )

    source_rows: list[dict[str, Any]] = []
    evidence_sources = case.get("evidence_sources")
    if not isinstance(evidence_sources, list):
        raise ValueError("case.evidence_sources must be an array")
    seen_source_urls: set[str] = set()
    for evidence in evidence_sources:
        url = str(evidence["source_url"])
        if url in seen_source_urls:
            continue
        seen_source_urls.add(url)
        document = document_by_url.get(url)
        if document is None or document.get("source_type") == "case_spec":
            raise ValueError(f"reviewer-visible frozen source is missing: {url}")
        source = ROOT / str(document["blob_path"])
        digest = str(document["content_sha256"])
        destination = HUMAN_ROOT / "human_inputs/sources" / digest
        copy_exact(source, destination, digest)
        source_rows.append(
            {
                "source_label": f"source_{len(source_rows) + 1:03d}",
                "source_url": url,
                "source_type": str(document["source_type"]),
                "content_sha256": digest,
                "snapshot_path": destination.relative_to(HUMAN_ROOT).as_posix(),
                "snapshot_file_sha256": sha256_file(destination),
                "access_policy": "allowed_only_after_discovery_in_a_search_snapshot",
            }
        )
    return search_rows, source_rows


def build_templates() -> dict[str, dict[str, str]]:
    templates = HUMAN_ROOT / "human_submission_templates"
    answer = templates / "answer.template.txt"
    report = templates / "report.template.md"
    ledger = templates / "ledger.template.json"
    manual = templates / "manual_record.template.json"

    write_text(answer, "")
    write_text(report, "")
    write_json(
        ledger,
        {
            "capture_complete": False,
            "events": [],
            "observation_semantics": "observation_ledger_v1",
            "run_id": RUN_ID,
        },
    )
    write_json(
        manual,
        {
            "access_path": [],
            "attested": False,
            "origin": "",
            "reviewer": "",
            "solve_minutes": None,
            "synthetic": False,
        },
    )
    return {
        "answer": binding(answer),
        "report": binding(report),
        "ledger": binding(ledger),
        "manual_record": binding(manual),
    }


def build_html(
    query: str,
    search_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
) -> Path:
    search_links = "\n".join(
        "<li><a href=\"{path}\">{label}</a><br><code>{url}</code></li>".format(
            path=html.escape(
                Path(row["snapshot_path"])
                .relative_to("human_inputs")
                .as_posix(),
                quote=True,
            ),
            label=html.escape(str(row["registry_id"])),
            url=html.escape(str(row["entry_url"])),
        )
        for row in search_rows
    )
    source_links = "\n".join(
        "<li><a href=\"{path}\">{label}</a><br><code>{url}</code></li>".format(
            path=html.escape(
                Path(row["snapshot_path"])
                .relative_to("human_inputs")
                .as_posix(),
                quote=True,
            ),
            label=html.escape(str(row["source_label"])),
            url=html.escape(str(row["source_url"])),
        )
        for row in source_rows
    )
    page = f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8">
<title>Q35 真人独立 oracle 冻结入口</title>
<style>
body{{max-width:1080px;margin:32px auto;padding:0 18px;font:16px/1.65 sans-serif;color:#202124}}
pre{{white-space:pre-wrap;background:#f6f8fa;padding:16px;border-radius:8px}}
li{{margin:12px 0}}code{{word-break:break-all}}.warning{{background:#fff4ce;padding:12px;border-left:4px solid #d97706}}
</style>
<h1>Q35 真人独立 oracle 冻结入口</h1>
<p class="warning">状态：pending_human。请独立解题。提交前不要查看 private case、证据图谱标注页、合成报告、合成日志或合成验证结果；它们不是人工证据。</p>
<p>冻结字节是唯一判定依据。先从搜索快照开始；只有在搜索快照中发现目标页后，才打开对应的冻结目标页。实时本地网页只可用于核对来源身份，不能覆盖冻结内容。</p>
<h2>公开问题</h2><pre>{html.escape(query)}</pre>
<p><a href="../public_task.json">公开任务 JSON</a></p>
<h2>允许的起始搜索快照</h2><ol>{search_links}</ol>
<h2>发现后允许打开的冻结目标页</h2><ol>{source_links}</ol>
<h2>空白提交模板</h2>
<ul>
<li><a href="../human_submission_templates/answer.template.txt">answer.template.txt</a></li>
<li><a href="../human_submission_templates/report.template.md">report.template.md</a></li>
<li><a href="../human_submission_templates/ledger.template.json">ledger.template.json</a></li>
<li><a href="../human_submission_templates/manual_record.template.json">manual_record.template.json</a></li>
</ul>
</html>
"""
    output = HUMAN_ROOT / "human_inputs/index.html"
    write_text(output, page)
    return output


def main() -> None:
    case = load_object(CASE_PATH, "formal case")
    public_task = load_object(PUBLIC_TASK_PATH, "public task")
    inventory = load_object(INVENTORY_PATH, "inventory")
    validation = load_object(VALIDATION_PATH, "synthetic validation")
    if validation.get("synthetic_only") is not True:
        raise ValueError("synthetic validation must remain synthetic_only")
    if validation.get("requires_real_human_followup") is not True:
        raise ValueError("synthetic validation must require real human followup")

    HUMAN_ROOT.mkdir(parents=True, exist_ok=True)
    public_copy = HUMAN_ROOT / "public_task.json"
    query_copy = HUMAN_ROOT / "query.txt"
    shutil.copyfile(PUBLIC_TASK_PATH, public_copy)
    shutil.copyfile(QUERY_PATH, query_copy)
    query = query_copy.read_text(encoding="utf-8").strip()

    search_rows, source_rows = build_snapshots(inventory, case)
    templates = build_templates()
    html_path = build_html(query, search_rows, source_rows)

    packet = {
        "schema": "dra_v3_human_oracle_handoff_v1",
        "task_id": TASK_ID,
        "status": "pending_human",
        "formal_oracle_gate_passed": False,
        "scoring_semantics": "proof_steps_v1",
        "synthetic_fixture_is_not_human_evidence": True,
        "bindings": {
            "public_task": {**binding(public_copy), "reviewer_visible": True},
            "query": {
                **binding(query_copy),
                "query_text_sha256": sha256_bytes(query.encode("utf-8")),
                "reviewer_visible": True,
            },
            "synthetic_base_suite": {
                "path": "../synthetic/suite.json",
                "sha256": sha256_file(SUITE_PATH),
                "reviewer_visible": False,
            },
            "synthetic_validation": {
                "path": "../synthetic/validation.json",
                "sha256": sha256_file(VALIDATION_PATH),
                "reviewer_visible": False,
            },
            "private_case": {
                "path": str(CASE_PATH.relative_to(ROOT)),
                "sha256": sha256_file(CASE_PATH),
                "reviewer_visible": False,
            },
            "evidence_graph_manifest": {
                "path": str((GRAPH_DIR / "manifest.json").relative_to(ROOT)),
                "sha256": sha256_file(GRAPH_DIR / "manifest.json"),
                "reviewer_visible": False,
            },
            "protocol": {
                "path": str(PROTOCOL_PATH.relative_to(ROOT)),
                "sha256": sha256_file(PROTOCOL_PATH),
                "reviewer_visible": False,
            },
            "graph_review_packet": {
                "path": str(REVIEW_MANIFEST_PATH.relative_to(ROOT)),
                "sha256": sha256_file(REVIEW_MANIFEST_PATH),
                "purpose": "graph_annotation_only_not_an_independent_oracle_input",
                "reviewer_visible": False,
            },
        },
        "reviewer_inputs": {
            "public_query": "query.txt",
            "public_task": "public_task.json",
            "offline_index": binding(html_path),
            "allowed_starting_search_snapshots": search_rows,
            "allowed_source_snapshots_after_discovery": source_rows,
            "allowed_live_local_urls_after_discovery": [
                row["source_url"] for row in source_rows
            ],
        },
        "independence_policy": {
            "reviewer_must_solve_from_public_query_and_frozen_corpus": True,
            "frozen_bytes_are_authoritative": True,
            "live_pages_may_override_frozen_bytes": False,
            "graph_annotation_packet_is_not_oracle_input": True,
            "synthetic_or_private_material_may_be_viewed_before_submission": False,
        },
        "prohibited_before_submission": [
            "evidence_review_packet/",
            "../synthetic/",
            "../build_synthetic_suite.py",
            "../../case_authoring/",
            "../../case_drafts/",
            "../../generator_views/",
            "../../graph_inputs/",
            "../../motif_compilations/",
            "../../protocol_manifests/",
            "../../query_review_packets/",
            "../../query_reviews/",
            "../../reachability/",
            "../../source_audits/",
        ],
        "submission_contract": {
            "directory": "human_submission",
            "run_id": RUN_ID,
            "files": {
                "answer": {
                    "path": "human_submission/answer.txt",
                    "prefilled": False,
                    "must_appear_in_report": True,
                    "type": "non_empty_natural_language_conclusion",
                },
                "report": {
                    "path": "human_submission/report.md",
                    "prefilled": False,
                    "type": "non_empty_utf8_text_with_locally_bound_citations",
                },
                "ledger": {
                    "path": "human_submission/ledger.json",
                    "prefilled": False,
                    "schema": "observation_ledger_v1",
                    "required_run_id": RUN_ID,
                    "capture_complete": True,
                },
                "manual_record": {
                    "path": "human_submission/manual_record.json",
                    "prefilled": False,
                    "required_fields": [
                        "origin",
                        "reviewer",
                        "solve_minutes",
                        "access_path",
                        "attested",
                        "synthetic",
                    ],
                    "required_constants": {
                        "origin": "manual",
                        "attested": True,
                        "synthetic": False,
                    },
                },
            },
        },
        "submission_templates": templates,
        "completion_condition": {
            "formal_human_validation_passed": True,
            "validation_tier": "formal_human_attested",
            "full_pass": 1,
            "partial_completion": 1,
            "critical_contradictions": 0,
            "fabricated_citations": 0,
        },
        "replay_command": [
            "python3",
            "scripts/score_case_v3.py",
            "--case",
            str(CASE_PATH.relative_to(ROOT)),
            "--scoring-semantics",
            "proof_steps_v1",
            "--report",
            str((HUMAN_ROOT / "human_submission/report.md").relative_to(ROOT)),
            "--ledger",
            str((HUMAN_ROOT / "human_submission/ledger.json").relative_to(ROOT)),
            "--evidence-graph",
            str(GRAPH_DIR.relative_to(ROOT)),
            "--corpus-registry",
            str((GRAPH_DIR / "corpus_registry.json").relative_to(ROOT)),
            "--protocol-manifest",
            str(PROTOCOL_PATH.relative_to(ROOT)),
            "--public-task",
            str(PUBLIC_TASK_PATH.relative_to(ROOT)),
            "--agent",
            "human-oracle-q35",
            "--replicate",
            "1",
            "--expected-run-id",
            RUN_ID,
            "--pretty",
            "--fail-on-withhold",
        ],
    }
    packet_path = HUMAN_ROOT / "human_oracle_packet.json"
    write_json(packet_path, packet)
    print(
        json.dumps(
            {
                "status": "pending_human",
                "formal_oracle_gate_passed": False,
                "packet": str(packet_path.relative_to(ROOT)),
                "packet_sha256": sha256_file(packet_path),
                "offline_index": str(html_path.relative_to(ROOT)),
                "search_snapshots": len(search_rows),
                "source_snapshots": len(source_rows),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
