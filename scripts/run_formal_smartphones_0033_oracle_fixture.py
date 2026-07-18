#!/usr/bin/env python3
"""Build Q33's replayable synthetic suite and pending-human handoff.

The three positive runs are synthetic scorer fixtures.  In particular, the
human-shaped row is not a human review and cannot satisfy the formal human
gate.  A real reviewer instead receives frozen search and target snapshots,
blank submission templates, and fail-closed finalization commands.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

import run_formal_smartphones_0030_oracle_fixture as base


ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "dra_v3_formal_smartphones_0033"
SNAPSHOT = "dra-v3-formal-smartphones-0033-long-life-2031-20260716-r1"
CAPTURE_RUN = "v3-corpus-formal-smartphones-0033-long-life-2031-20260716-r1"
RUN_PREFIX = "phone-case-0033"
DEFAULT_OUTPUT = (
    ROOT / "data/pilot_v3/formal_candidates" / TASK_ID / "oracle_suite"
)


def _configure_base() -> None:
    base.TASK_ID = TASK_ID
    base.CASE_PATH = (
        ROOT / "data/golden/cases_v3/formal_candidates" / f"{TASK_ID}.json"
    )
    base.PUBLIC_TASK_PATH = (
        ROOT / "data/tasks/deep_research/v3/formal_candidates" / f"{TASK_ID}.json"
    )
    base.GRAPH_DIR = ROOT / "data/evidence_graph/formal_candidates" / SNAPSHOT
    base.CAPTURE_BLOBS = (
        ROOT / "data/evidence_graph/captures" / CAPTURE_RUN / "blobs"
    )
    base.PROTOCOL_PATH = (
        ROOT
        / "data/pilot_v3/formal_candidates"
        / TASK_ID
        / "protocol_manifests/protocol.json"
    )
    base.QUERY_PATH = (
        ROOT
        / "data/pilot_v3/formal_candidates"
        / TASK_ID
        / "query_candidates/attempt1.txt"
    )
    base.INVENTORY_PATH = (
        ROOT
        / "data/pilot_v3/formal_candidates"
        / TASK_ID
        / "graph_inputs/inventory.json"
    )
    base.REVIEW_PACKET_MANIFEST_PATH = (
        ROOT
        / "data/pilot_v3/formal_candidates"
        / TASK_ID
        / "review_packet/manifest.json"
    )
    base.FABRICATED_URL = "http://localhost:7770/not-in-frozen-q33-corpus"


def _copy_inputs(output_dir: Path) -> None:
    for source, name in (
        (base.CASE_PATH, "case.json"),
        (base.PUBLIC_TASK_PATH, "public_task.json"),
        (base.PROTOCOL_PATH, "protocol.json"),
        (base.QUERY_PATH, "query.txt"),
        (base.GRAPH_DIR / "corpus_registry.json", "corpus_registry.json"),
        (base.GRAPH_DIR / "manifest.json", "graph_manifest.json"),
    ):
        if not source.is_file():
            raise RuntimeError(f"required input is missing: {source}")
        shutil.copyfile(source, output_dir / name)

    graph = {
        "corpus_snapshot": SNAPSHOT,
        "nodes": {
            row["evidence_id"]: row
            for row in base._load_jsonl(base.GRAPH_DIR / "nodes.jsonl")
        },
        "edges": base._load_jsonl(base.GRAPH_DIR / "edges.jsonl"),
        "support_spans": base._load_jsonl(
            base.GRAPH_DIR / "support_spans.jsonl"
        ),
    }
    base._write_json(output_dir / "evidence_graph.json", graph)

    blob_link = output_dir / "ledgers" / "blobs"
    blob_link.parent.mkdir(parents=True, exist_ok=True)
    target = os.path.relpath(base.CAPTURE_BLOBS, blob_link.parent)
    if blob_link.is_symlink():
        if os.readlink(blob_link) != target:
            raise RuntimeError(f"existing blob link points elsewhere: {blob_link}")
    elif blob_link.exists():
        raise RuntimeError(f"refusing to replace existing blob path: {blob_link}")
    else:
        blob_link.symlink_to(target, target_is_directory=True)


def _human_submission_templates(output_dir: Path) -> dict[str, dict[str, str]]:
    root = output_dir / "human_submission_templates"
    answer = root / "answer.template.txt"
    report = root / "report.template.md"
    ledger = root / "ledger.template.json"
    manual = root / "manual_record.template.json"
    base._write_text(answer, "")
    base._write_text(report, "")
    base._write_json(
        ledger,
        {
            "observation_semantics": "observation_ledger_v1",
            "run_id": f"{RUN_PREFIX}-human-formal-v1",
            "capture_complete": False,
            "events": [],
        },
    )
    base._write_json(
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
        "answer": base._artifact(answer, output_dir),
        "report": base._artifact(report, output_dir),
        "ledger": base._artifact(ledger, output_dir),
        "manual_record": base._artifact(manual, output_dir),
    }


def _replace_q30_markers(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("0030", "0033").replace("Q28", "Q33")
    if isinstance(value, list):
        return [_replace_q30_markers(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace_q30_markers(item) for key, item in value.items()}
    return value


def _build_human_inputs(
    output_dir: Path, case: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = base._build_human_inputs(output_dir, case)
    index = output_dir / "human_inputs/index.html"
    rendered = index.read_text(encoding="utf-8").replace("Q28", "Q33")
    base._write_text(index, rendered)
    return rows


def _build_human_packet(
    output_dir: Path,
    case: dict[str, Any],
    search_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    original_template_builder = base._build_human_submission_templates
    base._build_human_submission_templates = _human_submission_templates
    try:
        packet = base._build_human_oracle_packet(
            output_dir, case, search_rows, source_rows
        )
    finally:
        base._build_human_submission_templates = original_template_builder
    packet = _replace_q30_markers(packet)
    base._write_json(output_dir / "human_oracle_packet.json", packet)
    return packet


def _contradictory_decision(case: dict[str, Any]) -> str:
    claim = next(
        row
        for row in case["decidable_claims"]
        if row.get("contradicts_slot_id") == "D1"
    )
    return claim["rejected_matcher"]["accepted_phrases"][0]


def build(output_dir: Path) -> dict[str, Any]:
    _configure_base()
    output_dir.mkdir(parents=True, exist_ok=True)
    _copy_inputs(output_dir)
    case = json.loads((output_dir / "case.json").read_text(encoding="utf-8"))
    parts = base._report_parts(case)
    sources = parts["sources"]
    positive = parts["positive"]
    answer = parts["answer"]

    oracles: list[dict[str, Any]] = []
    for kind in ("machine", "human", "minimal"):
        run_id = f"{RUN_PREFIX}-synthetic-{kind}-v1"
        report, ledger = base._write_run(
            output_dir, run_id, positive, base._ledger(run_id, sources)
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
        base._citation_paragraph(
            source, sources[(index + 1) % len(sources)]["source_url"]
        )
        for index, source in enumerate(sources)
    )
    url_dump = " ".join(
        f"[source]({source['source_url']})" for source in sources
    )

    adversarial: list[dict[str, Any]] = []
    for category in base.ADVERSARIAL_CATEGORIES:
        run_id = f"{RUN_PREFIX}-negative-{category}-v1"
        ledger_mode = "full"
        declared_answer: str | None = None
        if category == "url_dump":
            report_text = url_dump
        elif category == "correct_plus_fabricated":
            report_text = f"{positive}\n\n[fabricated]({base.FABRICATED_URL})"
        elif category == "fetch_all_no_answer":
            report_text = "I opened every relevant frozen page but provide no answer."
        elif category == "unsupported_answer":
            report_text = f"{positive}\n\n{answer.replace('_', ' ')}"
            ledger_mode = "empty"
            declared_answer = answer
        elif category == "fact_dump":
            report_text = evidence
        elif category == "single_source":
            report_text = "\n\n".join([parts["evidence"][0], bridges, decision])
        elif category == "guessed_then_fetched":
            report_text = positive
            ledger_mode = "guessed_first"
        elif category == "wrong_binding":
            report_text = "\n\n".join([wrong_binding, bridges, decision])
        elif category == "contradictory_decision":
            report_text = "\n\n".join(
                [evidence, bridges, _contradictory_decision(case)]
            )
        elif category == "silence":
            report_text = ""
            ledger_mode = "empty"
        else:
            raise AssertionError(category)
        report, ledger = base._write_run(
            output_dir,
            run_id,
            report_text,
            base._ledger(run_id, sources, mode=ledger_mode),
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
        "suite_id": "dra-v3-smartphones-0033-synthetic-long-life-v1",
        "validation_scope": "synthetic_test",
        "scoring_semantics": "proof_steps_v1",
        "case": base._artifact(output_dir / "case.json", output_dir),
        "public_task": base._artifact(output_dir / "public_task.json", output_dir),
        "evidence_graph": base._artifact(
            output_dir / "evidence_graph.json", output_dir
        ),
        "protocols": base._artifact(output_dir / "protocol.json", output_dir),
        "oracles": oracles,
        "adversarial": adversarial,
    }
    base._write_json(output_dir / "suite.json", suite)
    search_rows, source_rows = _build_human_inputs(output_dir, case)
    _build_human_packet(output_dir, case, search_rows, source_rows)
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
                "human_status": "pending_human",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
