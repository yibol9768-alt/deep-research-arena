#!/usr/bin/env python3
"""Build the replayable synthetic oracle fixture for formal smartphone case 0030.

The fixture exercises the production proof-step scorer, including every
required adversarial category.  Its human-shaped run is explicitly synthetic
and cannot satisfy the formal human-attestation gate.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "dra_v3_formal_smartphones_0030"
CASE_PATH = (
    ROOT / "data/golden/cases_v3/formal_candidates" / f"{TASK_ID}.json"
)
PUBLIC_TASK_PATH = (
    ROOT / "data/tasks/deep_research/v3/formal_candidates" / f"{TASK_ID}.json"
)
GRAPH_DIR = (
    ROOT
    / "data/evidence_graph/formal_candidates"
    / "dra-v3-formal-smartphones-0030-20260716-r1"
)
CAPTURE_BLOBS = (
    ROOT
    / "data/evidence_graph/captures"
    / "v3-corpus-formal-smartphones-0030-20260716-r1"
    / "blobs"
)
PROTOCOL_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "protocol_manifests/protocol.json"
)
QUERY_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "query_candidates/attempt1.txt"
)
INVENTORY_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "graph_inputs/inventory.json"
)
REVIEW_PACKET_MANIFEST_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "review_packet/manifest.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "oracle_suite"
)
FABRICATED_URL = "http://localhost:7770/not-in-frozen-usbc-corpus"
ADVERSARIAL_CATEGORIES = (
    "url_dump",
    "correct_plus_fabricated",
    "fetch_all_no_answer",
    "unsupported_answer",
    "fact_dump",
    "single_source",
    "guessed_then_fetched",
    "wrong_binding",
    "contradictory_decision",
    "silence",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _copy_inputs(output_dir: Path) -> None:
    for source, name in (
        (CASE_PATH, "case.json"),
        (PUBLIC_TASK_PATH, "public_task.json"),
        (PROTOCOL_PATH, "protocol.json"),
        (QUERY_PATH, "query.txt"),
        (GRAPH_DIR / "corpus_registry.json", "corpus_registry.json"),
        (GRAPH_DIR / "manifest.json", "graph_manifest.json"),
    ):
        if not source.is_file():
            raise RuntimeError(f"required input is missing: {source}")
        shutil.copyfile(source, output_dir / name)

    graph = {
        "corpus_snapshot": "dra-v3-formal-smartphones-0030-20260716-r1",
        "nodes": {
            row["evidence_id"]: row
            for row in _load_jsonl(GRAPH_DIR / "nodes.jsonl")
        },
        "edges": _load_jsonl(GRAPH_DIR / "edges.jsonl"),
        "support_spans": _load_jsonl(GRAPH_DIR / "support_spans.jsonl"),
    }
    _write_json(output_dir / "evidence_graph.json", graph)

    blob_link = output_dir / "ledgers" / "blobs"
    blob_link.parent.mkdir(parents=True, exist_ok=True)
    target = os.path.relpath(CAPTURE_BLOBS, blob_link.parent)
    if blob_link.is_symlink():
        if os.readlink(blob_link) != target:
            raise RuntimeError(f"existing blob link points elsewhere: {blob_link}")
    elif blob_link.exists():
        raise RuntimeError(f"refusing to replace existing blob path: {blob_link}")
    else:
        blob_link.symlink_to(target, target_is_directory=True)


def _build_human_inputs(
    output_dir: Path,
    case: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    documents = inventory["documents"]
    search_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    human_root = output_dir / "human_inputs"

    for document in documents:
        if document["source_type"] != "search_result":
            continue
        source = ROOT / document["blob_path"]
        destination = human_root / "searches" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        search_rows.append(
            {
                "registry_id": document["registry_id"],
                "entry_url": document["source_url"],
                "content_sha256": document["content_sha256"],
                "snapshot_path": str(destination.relative_to(output_dir)),
                "snapshot_file_sha256": _sha256_file(destination),
            }
        )

    document_by_url = {row["source_url"]: row for row in documents}
    for source_spec in case["evidence_sources"]:
        document = document_by_url[source_spec["source_url"]]
        source = ROOT / document["blob_path"]
        destination = human_root / "sources" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        source_rows.append(
            {
                "evidence_id": source_spec["evidence_id"],
                "source_url": source_spec["source_url"],
                "source_type": source_spec["source_type"],
                "content_sha256": source_spec["content_sha256"],
                "snapshot_path": str(destination.relative_to(output_dir)),
                "snapshot_file_sha256": _sha256_file(destination),
                "access_policy": "allowed_only_after_discovery_in_a_search_snapshot",
            }
        )

    query = (output_dir / "query.txt").read_text(encoding="utf-8")
    links = "\n".join(
        "<li><a href=\"{path}\">{label}</a><br><code>{url}</code></li>".format(
            path=html.escape(
                str(Path(row["snapshot_path"]).relative_to("human_inputs")),
                quote=True,
            ),
            label=html.escape(row["registry_id"]),
            url=html.escape(row["entry_url"]),
        )
        for row in search_rows
    )
    source_links = "\n".join(
        "<li><a href=\"{path}\">{label}</a><br><code>{url}</code></li>".format(
            path=html.escape(
                str(Path(row["snapshot_path"]).relative_to("human_inputs")),
                quote=True,
            ),
            label=html.escape(row["evidence_id"]),
            url=html.escape(row["source_url"]),
        )
        for row in source_rows
    )
    page = (
        "<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\">"
        "<title>Q28 真人 oracle 冻结入口</title>"
        "<style>body{max-width:1050px;margin:32px auto;font:16px/1.6 sans-serif;}"
        "pre{white-space:pre-wrap;background:#f5f5f5;padding:16px;}"
        "li{margin:12px 0}code{word-break:break-all}</style>"
        "<h1>Q28 真人 oracle 冻结入口</h1>"
        "<p>先阅读公开问题，再从下面的冻结搜索快照开始。目标页只能在搜索快照中发现后打开。"
        "冻结字节是判定依据，实时网页只用于核对来源身份。</p>"
        f"<h2>公开问题</h2><pre>{html.escape(query)}</pre>"
        f"<h2>允许的起始入口</h2><ol>{links}</ol>"
        "<h2>发现后允许打开的冻结目标页</h2>"
        "<p>先在搜索快照中确认对应结果，再打开这里的冻结页面副本。</p>"
        f"<ol>{source_links}</ol>"
        "<h2>空白提交模板</h2><ul>"
        "<li><a href=\"../human_submission_templates/answer.template.txt\">"
        "answer.template.txt</a></li>"
        "<li><a href=\"../human_submission_templates/report.template.md\">"
        "report.template.md</a></li>"
        "<li><a href=\"../human_submission_templates/ledger.template.json\">"
        "ledger.template.json</a></li>"
        "<li><a href=\"../human_submission_templates/manual_record.template.json\">"
        "manual_record.template.json</a></li></ul></html>"
    )
    _write_text(human_root / "index.html", page)
    return search_rows, source_rows


def _build_human_oracle_packet(
    output_dir: Path,
    case: dict[str, Any],
    search_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    protocol = json.loads((output_dir / "protocol.json").read_text(encoding="utf-8"))
    graph_manifest = json.loads(
        (output_dir / "graph_manifest.json").read_text(encoding="utf-8")
    )
    query_text = (output_dir / "query.txt").read_text(encoding="utf-8")
    if query_text.endswith("\n"):
        query_text = query_text[:-1]
    review_manifest = (
        {
            "path": str(REVIEW_PACKET_MANIFEST_PATH.relative_to(ROOT)),
            "sha256": _sha256_file(REVIEW_PACKET_MANIFEST_PATH),
            "purpose": "graph_annotation_only_not_an_independent_oracle_input",
        }
        if REVIEW_PACKET_MANIFEST_PATH.is_file()
        else None
    )
    validation_path = output_dir / "validation.json"
    submission_templates = _build_human_submission_templates(output_dir)
    packet = {
        "schema": "dra_v3_human_oracle_handoff_v1",
        "task_id": TASK_ID,
        "status": "pending_human",
        "required_validation_scope": "formal",
        "scoring_semantics": "proof_steps_v1",
        "independence_policy": {
            "reviewer_must_solve_from_public_query_and_frozen_corpus": True,
            "frozen_bytes_are_authoritative": True,
            "live_pages_may_override_frozen_bytes": False,
            "synthetic_reports_or_private_case_may_be_viewed_before_submission": False,
            "review_packet_is_for_graph_annotation_not_oracle_solving": True,
        },
        "bindings": {
            "case": {
                **_artifact(output_dir / "case.json", output_dir),
                "reviewer_visible": False,
            },
            "public_task": {
                **_artifact(output_dir / "public_task.json", output_dir),
                "reviewer_visible": True,
            },
            "protocol": {
                **_artifact(output_dir / "protocol.json", output_dir),
                "manifest_sha256": protocol["manifest_sha256"],
                "reviewer_visible": False,
            },
            "query": {
                **_artifact(output_dir / "query.txt", output_dir),
                "query_text_sha256": _sha256_bytes(query_text.encode("utf-8")),
                "reviewer_visible": True,
            },
            "corpus_registry": {
                **_artifact(output_dir / "corpus_registry.json", output_dir),
                "corpus_registry_sha256": case["corpus_registry_hash"],
                "reviewer_visible": False,
            },
            "evidence_graph": {
                **_artifact(output_dir / "evidence_graph.json", output_dir),
                "evidence_graph_sha256": case["formal_bindings"][
                    "evidence_graph_sha256"
                ],
                "graph_manifest_file_sha256": _sha256_file(
                    output_dir / "graph_manifest.json"
                ),
                "graph_corpus_hash": graph_manifest["graph_corpus_hash"],
                "reviewer_visible": False,
            },
            "synthetic_base_suite": {
                **_artifact(output_dir / "suite.json", output_dir),
                "reviewer_visible": False,
            },
            "synthetic_validation": (
                {
                    **_artifact(validation_path, output_dir),
                    "reviewer_visible": False,
                }
                if validation_path.is_file()
                else None
            ),
            "graph_review_packet": review_manifest,
        },
        "reviewer_inputs": {
            "offline_index": _artifact(
                output_dir / "human_inputs/index.html", output_dir
            ),
            "public_query": "query.txt",
            "allowed_starting_search_snapshots": search_rows,
            "allowed_source_snapshots_after_discovery": source_rows,
            "allowed_live_local_urls_after_discovery": [
                row["source_url"] for row in source_rows
            ],
        },
        "prohibited_before_submission": [
            "case.json",
            "evidence_graph.json",
            "protocol.json",
            "suite.json",
            "validation.json",
            "reports/",
            "ledgers/phone-case-0030-synthetic-*.json",
        ],
        "submission_contract": {
            "directory": "human_submission",
            "run_id": "phone-case-0030-human-formal-v1",
            "files": {
                "answer": {
                    "path": "human_submission/answer.txt",
                    "type": "non_empty_natural_language_conclusion",
                    "must_appear_in_report": True,
                    "private_answer_identifier_required": False,
                    "prefilled": False,
                },
                "report": {
                    "path": "human_submission/report.md",
                    "type": "non_empty_utf8_text_with_locally_bound_citations",
                    "prefilled": False,
                },
                "ledger": {
                    "path": "human_submission/ledger.json",
                    "schema": "observation_ledger_v1",
                    "required_run_id": "phone-case-0030-human-formal-v1",
                    "capture_complete": True,
                    "prefilled": False,
                },
                "manual_record": {
                    "path": "human_submission/manual_record.json",
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
                    "access_path_must_equal_ledger_content_path": True,
                    "prefilled": False,
                },
            },
        },
        "submission_templates": submission_templates,
        "adjudication_commands": [
            {
                "cwd": str(ROOT),
                "argv": [
                    "python3",
                    "scripts/finalize_formal_smartphones_0030_human_oracle.py",
                    "--packet",
                    str((output_dir / "human_oracle_packet.json").relative_to(ROOT)),
                ],
            },
            {
                "cwd": str(ROOT),
                "argv": [
                    "python3",
                    "scripts/validate_oracle_suite_v3.py",
                    "--suite",
                    str((output_dir / "formal_suite.json").relative_to(ROOT)),
                    "--scoring-semantics",
                    "proof_steps_v1",
                    "--out",
                    str((output_dir / "formal_validation.json").relative_to(ROOT)),
                    "--pretty",
                ],
            },
        ],
        "completion_condition": {
            "validation_tier": "formal_human_attested",
            "formal_human_validation_passed": True,
            "formal_pilot_passed": True,
        },
    }
    _write_json(output_dir / "human_oracle_packet.json", packet)
    return packet


def _citation_paragraph(source: dict[str, Any], url: str | None = None) -> str:
    phrase = source["verifier"]["accepted_phrases"][0]
    return f"{phrase} [source]({url or source['source_url']})"


def _report_parts(case: dict[str, Any]) -> dict[str, Any]:
    sources = case["evidence_sources"]
    rules = case["rule_definitions"]
    evidence_paragraphs = [_citation_paragraph(source) for source in sources]
    bridge_paragraphs = [
        rules[step["rule"]]["accepted_phrases"][0]
        for step in case["evaluator_view"]["required_proof_steps"]
        if step["type"] == "bridge"
    ]

    decision_step = next(
        step
        for step in case["evaluator_view"]["required_proof_steps"]
        if step["type"] == "decision"
    )
    decision_rule = rules[decision_step["rule"]]
    conclusion = case["acceptable_conclusions"][0]
    answer = conclusion["answer"]
    admissible = next(
        row
        for row in decision_rule["admissible_conditions"]
        if row["answer"] == answer
    )
    decision_paragraphs = [
        decision_rule["decision_matcher"]["accepted_phrases"][0],
        admissible["condition_matcher"]["accepted_phrases"][0],
        *[
            admissible["tradeoff_matchers"][tradeoff]["accepted_phrases"][0]
            for tradeoff in conclusion["required_tradeoffs"]
        ],
        decision_rule["conclusion_matchers"][answer]["accepted_phrases"][0],
    ]
    return {
        "sources": sources,
        "answer": answer,
        "evidence": evidence_paragraphs,
        "bridges": bridge_paragraphs,
        "decision": decision_paragraphs,
        "positive": "\n\n".join(
            [*evidence_paragraphs, *bridge_paragraphs, *decision_paragraphs]
        ),
    }


def _event(
    run_id: str,
    event_id: int,
    event_type: str,
    url: str,
    *,
    content_sha256: str,
    content: Any,
    parent_event_id: int | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "event_id": event_id,
        "timestamp": float(event_id),
        "event_type": event_type,
        "request_url": url,
        "canonical_url": url,
        "parent_event_id": parent_event_id,
        "content_sha256": content_sha256,
        "content_text_or_blob_ref": content,
        "http_status": 200 if event_type == "fetch_body" else None,
        "observable": True,
    }


def _ledger(
    run_id: str,
    sources: list[dict[str, Any]],
    *,
    mode: str = "full",
) -> dict[str, Any]:
    if mode == "empty":
        events: list[dict[str, Any]] = []
    else:
        events = []
        next_id = 1
        for index, source in enumerate(sources):
            url = source["source_url"]
            digest = source["content_sha256"]
            blob = CAPTURE_BLOBS / digest
            if not blob.is_file() or _sha256_file(blob) != digest:
                raise RuntimeError(f"missing or drifted source blob: {digest}")

            search_id: int | None = None
            if not (mode == "guessed_first" and index == 0):
                snippet = f"search result for {source['evidence_id']}"
                search_id = next_id
                events.append(
                    _event(
                        run_id,
                        next_id,
                        "search_result",
                        url,
                        content_sha256=_sha256_bytes(snippet.encode("utf-8")),
                        content=snippet,
                    )
                )
                next_id += 1
            events.append(
                _event(
                    run_id,
                    next_id,
                    "fetch_body",
                    url,
                    content_sha256=digest,
                    content={"blob_ref": digest},
                    parent_event_id=search_id,
                )
            )
            next_id += 1
    return {
        "observation_semantics": "observation_ledger_v1",
        "run_id": run_id,
        "capture_complete": True,
        "events": events,
    }


def _artifact(path: Path, root: Path) -> dict[str, str]:
    return {
        "path": str(path.relative_to(root)),
        "sha256": _sha256_file(path),
    }


def _build_human_submission_templates(output_dir: Path) -> dict[str, dict[str, str]]:
    template_root = output_dir / "human_submission_templates"
    answer = template_root / "answer.template.txt"
    report = template_root / "report.template.md"
    ledger = template_root / "ledger.template.json"
    manual = template_root / "manual_record.template.json"
    _write_text(answer, "")
    _write_text(report, "")
    _write_json(
        ledger,
        {
            "observation_semantics": "observation_ledger_v1",
            "run_id": "phone-case-0030-human-formal-v1",
            "capture_complete": False,
            "events": [],
        },
    )
    _write_json(
        manual,
        {
            "origin": "",
            "reviewer": "",
            "solve_minutes": None,
            "access_path": [],
            "attested": False,
            "synthetic": False,
        },
    )
    return {
        "answer": _artifact(answer, output_dir),
        "report": _artifact(report, output_dir),
        "ledger": _artifact(ledger, output_dir),
        "manual_record": _artifact(manual, output_dir),
    }


def _write_run(
    output_dir: Path,
    run_id: str,
    report: str,
    ledger: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    report_path = output_dir / "reports" / f"{run_id}.txt"
    ledger_path = output_dir / "ledgers" / f"{run_id}.json"
    _write_text(report_path, report)
    _write_json(ledger_path, ledger)
    return _artifact(report_path, output_dir), _artifact(ledger_path, output_dir)


def build(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    _copy_inputs(output_dir)
    case = json.loads((output_dir / "case.json").read_text(encoding="utf-8"))
    parts = _report_parts(case)
    sources = parts["sources"]
    positive = parts["positive"]
    answer = parts["answer"]

    oracles: list[dict[str, Any]] = []
    for kind in ("machine", "human", "minimal"):
        run_id = f"phone-case-0030-synthetic-{kind}-v1"
        report, ledger = _write_run(
            output_dir,
            run_id,
            positive,
            _ledger(run_id, sources),
        )
        entry: dict[str, Any] = {
            "run_id": run_id,
            "kind": kind,
            "answer": answer,
            "report": report,
            "ledger": ledger,
        }
        if kind == "minimal":
            entry["minimal_evidence_ids"] = [
                source["evidence_id"] for source in sources
            ]
        if kind == "human":
            entry["manual_record"] = {
                "origin": "manual",
                "reviewer": "synthetic-fixture-not-a-human-review",
                "solve_minutes": 0.1,
                "access_path": [source["source_url"] for source in sources],
                "attested": True,
                "synthetic": True,
            }
        oracles.append(entry)

    evidence = "\n\n".join(parts["evidence"])
    bridges = "\n\n".join(parts["bridges"])
    decision = "\n\n".join(parts["decision"])
    wrong_binding = "\n\n".join(
        _citation_paragraph(source, sources[(index + 1) % len(sources)]["source_url"])
        for index, source in enumerate(sources)
    )
    url_dump = " ".join(
        f"[source]({source['source_url']})" for source in sources
    )

    adversarial: list[dict[str, Any]] = []
    for category in ADVERSARIAL_CATEGORIES:
        run_id = f"phone-case-0030-negative-{category}-v1"
        ledger_mode = "full"
        declared_answer: str | None = None
        if category == "url_dump":
            report_text = url_dump
        elif category == "correct_plus_fabricated":
            report_text = f"{positive}\n\n[fabricated]({FABRICATED_URL})"
        elif category == "fetch_all_no_answer":
            report_text = "I opened every relevant frozen page but provide no answer."
        elif category == "unsupported_answer":
            report_text = f"{positive}\n\n{answer.replace('_', ' ')}"
            ledger_mode = "empty"
            declared_answer = answer
        elif category == "fact_dump":
            report_text = evidence
        elif category == "single_source":
            report_text = "\n\n".join(
                [parts["evidence"][0], bridges, decision]
            )
        elif category == "guessed_then_fetched":
            report_text = positive
            ledger_mode = "guessed_first"
        elif category == "wrong_binding":
            report_text = "\n\n".join([wrong_binding, bridges, decision])
        elif category == "contradictory_decision":
            report_text = "\n\n".join(
                [
                    evidence,
                    bridges,
                    "The seller pages prove that one listed charger and cable pair is universally fastest and reliable for every family phone.",
                ]
            )
        elif category == "silence":
            report_text = ""
            ledger_mode = "empty"
        else:
            raise AssertionError(category)
        report, ledger = _write_run(
            output_dir,
            run_id,
            report_text,
            _ledger(run_id, sources, mode=ledger_mode),
        )
        entry = {
            "run_id": run_id,
            "category": category,
            "report": report,
            "ledger": ledger,
        }
        if declared_answer is not None:
            entry["answer"] = declared_answer
        adversarial.append(entry)

    suite = {
        "schema": "dra_v3_oracle_suite_v1",
        "suite_id": "dra-v3-usbc-0030-synthetic-mechanism-v1",
        "validation_scope": "synthetic_test",
        "scoring_semantics": "proof_steps_v1",
        "case": _artifact(output_dir / "case.json", output_dir),
        "public_task": _artifact(output_dir / "public_task.json", output_dir),
        "evidence_graph": _artifact(
            output_dir / "evidence_graph.json", output_dir
        ),
        "protocols": _artifact(output_dir / "protocol.json", output_dir),
        "oracles": oracles,
        "adversarial": adversarial,
    }
    _write_json(output_dir / "suite.json", suite)
    search_rows, source_rows = _build_human_inputs(output_dir, case)
    _build_human_oracle_packet(output_dir, case, search_rows, source_rows)
    return suite


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    suite = build(args.output_dir.resolve())
    print(
        json.dumps(
            {
                "status": "written",
                "suite": str(args.output_dir.resolve() / "suite.json"),
                "oracles": len(suite["oracles"]),
                "adversarial": len(suite["adversarial"]),
                "validation_scope": suite["validation_scope"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

