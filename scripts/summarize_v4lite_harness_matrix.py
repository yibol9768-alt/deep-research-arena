#!/usr/bin/env python3
"""Summarize one same-task v4lite harness matrix without semantic inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


HARNESSES = (
    "camel-ai",
    "claude-code",
    "deerflow",
    "gpt-researcher",
    "ii-researcher",
    "langchain-odr",
    "ldr",
    "miroflow",
    "opencode",
    "qx-agents",
    "smolagents",
    "storm",
)


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _fmt(value: object) -> str:
    return "N/A" if not isinstance(value, (int, float)) else f"{value:.3f}"


def _row(root: Path, harness: str) -> dict[str, Any]:
    prepared = root / "prepared" / harness
    score_dir = root / "scores" / harness
    projection = _load(prepared / "projection-manifest.json")
    adapter = _load(prepared / "scorer-inputs/adapter-manifest.json")
    score = _load(score_dir / "score.json")
    result: dict[str, Any] = {
        "harness": harness,
        "status": "not_run",
        "run_id": None,
        "completed": None,
        "run_failure": None,
        "execution_outcome": None,
        "report_bytes": None,
        "observed_documents": None,
        "full_pages": None,
        "snippets": None,
        "citations": None,
        "observed_citations": None,
        "unobserved_citations": None,
        "truth": None,
        "provenance": None,
        "fact": None,
        "resolution_rate": None,
        "evidence": None,
        "evidence_precision": None,
        "evidence_recall": None,
        "completeness": None,
        "rubric": None,
        "formal_eligible": None,
    }
    if projection is not None:
        files = projection.get("report_bundle", {}).get("files", [])
        observation = projection.get("observation_projection", {})
        result.update(
            {
                "status": "scored" if score is not None else "report_ready",
                "run_id": projection.get("run_id"),
                "completed": projection.get("completed"),
                "run_failure": projection.get("run_failure"),
                "execution_outcome": projection.get("execution_outcome"),
                "report_bytes": sum(
                    int(item.get("bytes") or 0)
                    for item in files
                    if isinstance(item, dict)
                ),
                "observed_documents": observation.get("document_count"),
                "full_pages": observation.get("full_page_document_count"),
                "snippets": observation.get("snippet_document_count"),
            }
        )
    if adapter is not None:
        result.update(
            {
                "citations": adapter.get("normalized_citation_id_count"),
                "observed_citations": adapter.get(
                    "observed_citation_id_count"
                ),
                "unobserved_citations": adapter.get(
                    "unobserved_citation_id_count"
                ),
            }
        )
    if (
        projection is not None
        and projection.get("non_delivery") is True
        and not projection.get("completed")
    ):
        result.update(
            {
                "status": "attributable_non_delivery",
                "truth": 0.0,
                "provenance": 0.0,
                "fact": 0.0,
                "evidence": 0.0,
                "evidence_precision": 0.0,
                "evidence_recall": 0.0,
                "completeness": 0.0,
                "rubric": 0.0,
                "formal_eligible": False,
            }
        )
    if score is not None:
        fact = score.get("fact", {})
        evidence = score.get("evidence", {})
        result.update(
            {
                "truth": score.get("truth"),
                "provenance": score.get("provenance", {}).get("score"),
                "fact": fact.get("score"),
                "resolution_rate": fact.get("resolution_rate"),
                "evidence": evidence.get("score"),
                "evidence_precision": evidence.get("precision"),
                "evidence_recall": evidence.get("recall"),
                "completeness": score.get("completeness", {}).get("score"),
                "rubric": score.get("rubric", {}).get("score"),
                "formal_eligible": score.get("formal_eligible"),
            }
        )
    return result


def _markdown(rows: list[dict[str, Any]]) -> str:
    ranked = sorted(
        rows,
        key=lambda row: (
            row["truth"] is not None,
            row["truth"] if row["truth"] is not None else -1,
        ),
        reverse=True,
    )
    lines = [
        "# Same-task v4lite harness matrix",
        "",
        "All semantic decisions were made by `deepseek-v4-flash`; "
        "manual claim decisions: 0. Scores are diagnostic, not formal "
        "leaderboard results.",
        "",
        "| Harness | Run | Truth | P | Fact (resolution) | Evidence (P/R) | "
        "Completeness | Rubric | Full/snippet pages | Citations observed/total |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in ranked:
        run = (
            "clean"
            if row["completed"] is True and not row["run_failure"]
            else "non-delivery"
            if row["status"] == "attributable_non_delivery"
            else "audit-warning"
            if row["run_id"]
            else row["status"]
        )
        lines.append(
            "| {harness} | {run} | {truth} | {p} | {fact} ({resolution}) | "
            "{evidence} ({ep}/{er}) | {complete} | {rubric} | {full}/{snippet} | "
            "{observed}/{citations} |".format(
                harness=row["harness"],
                run=run,
                truth=_fmt(row["truth"]),
                p=_fmt(row["provenance"]),
                fact=_fmt(row["fact"]),
                resolution=_fmt(row["resolution_rate"]),
                evidence=_fmt(row["evidence"]),
                ep=_fmt(row["evidence_precision"]),
                er=_fmt(row["evidence_recall"]),
                complete=_fmt(row["completeness"]),
                rubric=_fmt(row["rubric"]),
                full=row["full_pages"] if row["full_pages"] is not None else "N/A",
                snippet=row["snippets"] if row["snippets"] is not None else "N/A",
                observed=(
                    row["observed_citations"]
                    if row["observed_citations"] is not None
                    else "N/A"
                ),
                citations=row["citations"] if row["citations"] is not None else "N/A",
            )
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-root", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    rows = [_row(args.matrix_root, harness) for harness in HARNESSES]
    payload = {
        "schema": "dra_v4lite_same_task_matrix_v1",
        "semantic_judge_model": "deepseek-v4-flash",
        "manual_claim_decisions": 0,
        "formal_eligible": False,
        "rows": rows,
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(_markdown(rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
