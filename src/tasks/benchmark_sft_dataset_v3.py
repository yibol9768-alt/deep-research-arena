"""Build an intentionally overlapping DRA v3 benchmark and SFT-QA pilot.

This module is a data exporter, not a trainer.  It reads replay-validated oracle
suites, verifies their artifact lineage, and emits two views of the same cases:

* a public benchmark view containing the query but no answer; and
* an SFT view containing the query and one validated oracle report.

Exact task overlap is rejected unless the caller explicitly opts in.  The
resulting manifest permanently labels the export as a same-task pipeline pilot,
not evidence of held-out generalization.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


DATASET_SCHEMA = "dra_v3_benchmark_sft_same_task_pilot_v1"
BENCHMARK_ITEM_SCHEMA = "dra_v3_benchmark_item_v1"
SFT_QA_SCHEMA = "dra_v3_sft_qa_v1"
PROVENANCE_SCHEMA = "dra_v3_sft_provenance_v1"

DEFAULT_SYSTEM_PROMPT = (
    "You are a careful deep-research assistant. Produce a complete, "
    "evidence-grounded report that answers the user's request. Preserve "
    "uncertainty and source scope, synthesize across sources, cite supporting "
    "URLs inline, and never fabricate evidence or citations."
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_URL_RE = re.compile(r"https?://[^\s)>\]}'\"]+")
_SUITE_GLOBS = (
    "*/oracle_suite/suite.json",
    "*/oracle_suites/synthetic/suite.json",
)


class DatasetBuildError(ValueError):
    """Raised when source artifacts cannot support a trustworthy export."""


@dataclass(frozen=True)
class BuildOptions:
    """Selection and safety options for one dataset export."""

    oracle_kind: str = "machine"
    allow_synthetic: bool = False
    allow_intentional_overlap: bool = False
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


def build_same_task_pilot(
    candidates_root: str | Path,
    output_dir: str | Path,
    *,
    options: BuildOptions | None = None,
) -> dict[str, Any]:
    """Verify source suites and write benchmark plus SFT views.

    Returns the written manifest.  All source records are collected and
    validated before any output file is changed.
    """

    opts = options or BuildOptions()
    if not opts.allow_intentional_overlap:
        raise DatasetBuildError(
            "exact benchmark/SFT task overlap requires "
            "allow_intentional_overlap=True"
        )
    if not opts.oracle_kind.strip():
        raise DatasetBuildError("oracle_kind must be non-empty")
    if not opts.system_prompt.strip():
        raise DatasetBuildError("system_prompt must be non-empty")

    source_root = Path(candidates_root).resolve()
    suite_paths = sorted(
        {
            path
            for pattern in _SUITE_GLOBS
            for path in source_root.glob(pattern)
        }
    )
    if not suite_paths:
        raise DatasetBuildError(f"no oracle suites found below {source_root}")

    benchmark_rows: list[dict[str, Any]] = []
    sft_rows: list[dict[str, Any]] = []
    message_rows: list[dict[str, Any]] = []
    provenance_rows: list[dict[str, Any]] = []
    skipped_synthetic: list[str] = []
    seen_task_ids: set[str] = set()

    for suite_path in suite_paths:
        collected = _collect_suite(
            suite_path,
            candidates_root=source_root,
            options=opts,
        )
        if collected is None:
            skipped_synthetic.append(suite_path.relative_to(source_root).parts[0])
            continue
        benchmark, sft, messages, provenance = collected
        task_id = str(benchmark["task_id"])
        if task_id in seen_task_ids:
            raise DatasetBuildError(f"duplicate task_id across suites: {task_id}")
        seen_task_ids.add(task_id)
        benchmark_rows.append(benchmark)
        sft_rows.append(sft)
        message_rows.append(messages)
        provenance_rows.append(provenance)

    if not benchmark_rows:
        suffix = (
            "; all discovered suites are synthetic, pass allow_synthetic=True "
            "for an explicitly labelled pipeline pilot"
            if skipped_synthetic
            else ""
        )
        raise DatasetBuildError(f"no eligible oracle suites{suffix}")

    benchmark_rows.sort(key=lambda row: str(row["task_id"]))
    sft_rows.sort(key=lambda row: str(row["example_id"]))
    provenance_rows.sort(key=lambda row: str(row["example_id"]))
    messages_by_id = {
        str(row["example_id"]): row for row in message_rows
    }
    message_rows = [
        messages_by_id[str(row["example_id"])] for row in sft_rows
    ]

    serialized = {
        "benchmark.jsonl": _jsonl_bytes(benchmark_rows),
        "sft_qa.jsonl": _jsonl_bytes(sft_rows),
        "sft_messages.jsonl": _jsonl_bytes(
            [{"messages": row["messages"]} for row in message_rows]
        ),
        "provenance.jsonl": _jsonl_bytes(provenance_rows),
    }
    artifact_meta = {
        name: {"bytes": len(payload), "sha256": _sha256(payload)}
        for name, payload in serialized.items()
    }
    fingerprint_basis = b"".join(
        name.encode("utf-8") + b"\0" + serialized[name]
        for name in sorted(serialized)
    )
    dataset_sha256 = _sha256(fingerprint_basis)
    task_ids = [str(row["task_id"]) for row in benchmark_rows]
    synthetic_count = sum(
        bool(row["source_validation"]["synthetic_only"])
        for row in provenance_rows
    )

    manifest: dict[str, Any] = {
        "schema": DATASET_SCHEMA,
        "dataset_id": f"dra-v3-same-task-pilot-{dataset_sha256[:16]}",
        "dataset_sha256": dataset_sha256,
        "purpose": "pipeline_sanity_check_and_memorization_upper_bound",
        "formal_benchmark_eligible": False,
        "generalization_claim_allowed": False,
        "overlap_policy": {
            "kind": "intentional_exact_task_overlap",
            "n_overlapping_tasks": len(task_ids),
            "task_ids": task_ids,
            "warning": (
                "Every benchmark query also appears in SFT training data. "
                "Results measure pipeline behavior or memorization, not held-out "
                "research generalization."
            ),
        },
        "source_selection": {
            "candidates_root": _portable_path(source_root),
            "suite_globs": list(_SUITE_GLOBS),
            "oracle_kind": opts.oracle_kind,
            "requires_validation_status": "validated",
            "requires_full_pass": 1,
            "requires_partial_completion": 1.0,
            "requires_fabricated_citations": 0,
            "synthetic_sources_allowed": bool(opts.allow_synthetic),
        },
        "counts": {
            "benchmark_items": len(benchmark_rows),
            "sft_examples": len(sft_rows),
            "unique_tasks": len(task_ids),
            "synthetic_examples": synthetic_count,
            "human_validated_examples": len(task_ids) - synthetic_count,
            "skipped_synthetic_suites": len(skipped_synthetic),
        },
        "artifacts": artifact_meta,
    }

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for name, payload in serialized.items():
        _atomic_write(destination / name, payload)
    _atomic_write(
        destination / "manifest.json",
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
    )
    return manifest


def _collect_suite(
    suite_path: Path,
    *,
    candidates_root: Path,
    options: BuildOptions,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    suite_dir = suite_path.parent
    suite_raw = suite_path.read_bytes()
    suite = _json_object(suite_raw, label=str(suite_path))
    suite_sha256 = _sha256(suite_raw)

    validation_path = suite_dir / "validation.json"
    if not validation_path.is_file():
        raise DatasetBuildError(f"missing validation.json for {suite_path}")
    validation_raw = validation_path.read_bytes()
    validation = _json_object(validation_raw, label=str(validation_path))
    if validation.get("status") != "validated":
        raise DatasetBuildError(
            f"suite is not replay-validated: {suite_path} "
            f"(status={validation.get('status')!r})"
        )
    expected_suite_sha = str(validation.get("suite_sha256") or "")
    if expected_suite_sha != suite_sha256:
        raise DatasetBuildError(
            f"validation/suite hash mismatch for {suite_path}: "
            f"expected {expected_suite_sha}, got {suite_sha256}"
        )

    synthetic_only = bool(validation.get("synthetic_only")) or str(
        validation.get("validation_scope") or suite.get("validation_scope") or ""
    ) == "synthetic_test"
    if synthetic_only and not options.allow_synthetic:
        return None

    case_path, case_raw = _artifact(
        suite_dir, suite.get("case"), label=f"{suite_path}:case"
    )
    graph_path, graph_raw = _artifact(
        suite_dir,
        suite.get("evidence_graph"),
        label=f"{suite_path}:evidence_graph",
    )
    public_path, public_raw = _artifact(
        suite_dir,
        suite.get("public_task"),
        label=f"{suite_path}:public_task",
    )
    protocol_path, protocol_raw = _artifact(
        suite_dir,
        suite.get("protocols"),
        label=f"{suite_path}:protocols",
    )
    public_task = _json_object(public_raw, label=str(public_path))

    raw_oracles = suite.get("oracles")
    if not isinstance(raw_oracles, list):
        raise DatasetBuildError(f"oracles must be a list in {suite_path}")
    oracle_matches = [
        row
        for row in raw_oracles
        if isinstance(row, Mapping) and row.get("kind") == options.oracle_kind
    ]
    if len(oracle_matches) != 1:
        raise DatasetBuildError(
            f"suite {suite_path} requires exactly one {options.oracle_kind!r} "
            f"oracle; found {len(oracle_matches)}"
        )
    oracle = dict(oracle_matches[0])
    report_path, report_raw = _artifact(
        suite_dir,
        oracle.get("report"),
        label=f"{suite_path}:oracle_report",
    )
    ledger_path, ledger_raw = _artifact(
        suite_dir,
        oracle.get("ledger"),
        label=f"{suite_path}:oracle_ledger",
    )
    report_sha256 = _sha256(report_raw)
    report = report_raw.decode("utf-8").strip()
    if not report:
        raise DatasetBuildError(f"empty oracle report: {report_path}")

    run_id = str(oracle.get("run_id") or "")
    validation_results = validation.get("oracle_results")
    if not isinstance(validation_results, list):
        raise DatasetBuildError(f"oracle_results must be a list in {validation_path}")
    result_matches = [
        row
        for row in validation_results
        if isinstance(row, Mapping)
        and row.get("kind") == options.oracle_kind
        and str(row.get("run_id") or "") == run_id
    ]
    if len(result_matches) != 1:
        raise DatasetBuildError(
            f"validation requires exactly one result for oracle run {run_id!r}; "
            f"found {len(result_matches)}"
        )
    result = dict(result_matches[0])
    result_report = result.get("report_artifact")
    if not isinstance(result_report, Mapping) or result_report.get("sha256") != report_sha256:
        raise DatasetBuildError(
            f"validation result report hash mismatch for oracle run {run_id}"
        )
    score = result.get("score")
    if not isinstance(score, Mapping):
        raise DatasetBuildError(f"missing score for oracle run {run_id}")
    _require_passing_score(score, run_id=run_id)

    task_id = str(public_task.get("task_id") or validation.get("task_id") or "").strip()
    if not task_id:
        raise DatasetBuildError(f"missing task_id in {public_path}")
    validation_task_id = str(validation.get("task_id") or task_id)
    if validation_task_id != task_id:
        raise DatasetBuildError(
            f"public/validation task_id mismatch: {task_id} != {validation_task_id}"
        )
    query = _query_from_public_task(public_task, public_path)
    query_sha256 = _sha256(query.encode("utf-8"))
    answer_sha256 = _sha256(report.encode("utf-8"))
    example_id = f"{task_id}::{options.oracle_kind}"
    cluster_id = str(public_task.get("cluster_id") or "")
    validation_scope = str(
        validation.get("validation_scope") or suite.get("validation_scope") or "unknown"
    )
    label_status = "synthetic_oracle" if synthetic_only else "human_validated_oracle"

    messages = [
        {"role": "system", "content": options.system_prompt.strip()},
        {"role": "user", "content": query},
        {"role": "assistant", "content": report},
    ]
    benchmark = {
        "schema": BENCHMARK_ITEM_SCHEMA,
        "task_id": task_id,
        "query": query,
        "split": "pilot_eval_same_task",
        "cluster_id": cluster_id,
        "motif": public_task.get("motif"),
        "corpus_snapshot": public_task.get("corpus_snapshot"),
        "query_sha256": query_sha256,
        "contamination_status": "intentional_exact_task_overlap_with_sft",
        "formal_benchmark_eligible": False,
    }
    sft = {
        "schema": SFT_QA_SCHEMA,
        "example_id": example_id,
        "task_id": task_id,
        "question": query,
        "answer": report,
        "messages": messages,
        "metadata": {
            "split": "pilot_train_same_task",
            "cluster_id": cluster_id,
            "motif": public_task.get("motif"),
            "oracle_kind": options.oracle_kind,
            "label_status": label_status,
            "validation_scope": validation_scope,
            "query_sha256": query_sha256,
            "answer_sha256": answer_sha256,
            "benchmark_overlap": "intentional_exact_task",
            "formal_generalization_claim_allowed": False,
        },
    }
    message_record = {"example_id": example_id, "messages": messages}

    citation_urls = _citation_urls(score, report)
    provenance = {
        "schema": PROVENANCE_SCHEMA,
        "example_id": example_id,
        "task_id": task_id,
        "source_validation": {
            "status": validation.get("status"),
            "validation_scope": validation_scope,
            "validation_tier": validation.get("validation_tier"),
            "synthetic_only": synthetic_only,
            "formal_human_validation_passed": bool(
                validation.get("formal_human_validation_passed")
            ),
            "requires_real_human_followup": bool(
                validation.get("requires_real_human_followup")
            ),
        },
        "source_artifacts": {
            "suite": _source_artifact(
                suite_path,
                suite_sha256,
                candidates_root=candidates_root,
            ),
            "validation": _source_artifact(
                validation_path,
                _sha256(validation_raw),
                candidates_root=candidates_root,
            ),
            "case": _suite_artifact(case_path, case_raw, suite_dir=suite_dir),
            "evidence_graph": _suite_artifact(
                graph_path, graph_raw, suite_dir=suite_dir
            ),
            "public_task": _suite_artifact(
                public_path, public_raw, suite_dir=suite_dir
            ),
            "protocol": _suite_artifact(
                protocol_path, protocol_raw, suite_dir=suite_dir
            ),
            "oracle_report": _suite_artifact(
                report_path, report_raw, suite_dir=suite_dir
            ),
            "oracle_ledger": _suite_artifact(
                ledger_path, ledger_raw, suite_dir=suite_dir
            ),
        },
        "oracle": {
            "kind": options.oracle_kind,
            "run_id": run_id,
            "answer_label": oracle.get("answer"),
            "query_sha256": query_sha256,
            "answer_sha256": answer_sha256,
            "citation_urls": citation_urls,
        },
        "score_summary": {
            "scoring_semantics": score.get("scoring_semantics"),
            "required_steps": score.get("required_steps"),
            "passed_steps": score.get("passed_steps"),
            "partial_completion": score.get("partial_completion"),
            "full_pass": score.get("full_pass"),
            "fabricated_citations": score.get("fabricated_citations"),
            "critical_contradictions": score.get("critical_contradictions"),
        },
    }
    return benchmark, sft, message_record, provenance


def _require_passing_score(score: Mapping[str, Any], *, run_id: str) -> None:
    checks = {
        "full_pass": score.get("full_pass") == 1,
        "partial_completion": score.get("partial_completion") == 1.0,
        "fabricated_citations": score.get("fabricated_citations") == 0,
        "critical_contradictions": score.get("critical_contradictions") == 0,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        detail = {name: score.get(name) for name in failed}
        raise DatasetBuildError(
            f"oracle run {run_id} is not a clean FullPass target: {detail}"
        )


def _artifact(
    suite_dir: Path,
    descriptor: Any,
    *,
    label: str,
) -> tuple[Path, bytes]:
    if not isinstance(descriptor, Mapping):
        raise DatasetBuildError(f"{label} must be a path/hash object")
    relative = str(descriptor.get("path") or "")
    expected_sha = str(descriptor.get("sha256") or "")
    if not relative or not _SHA256_RE.fullmatch(expected_sha):
        raise DatasetBuildError(f"{label} requires path and lowercase sha256")
    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise DatasetBuildError(f"{label} path must be relative: {relative}")
    path = (suite_dir / relative_path).resolve()
    if not path.is_relative_to(suite_dir.resolve()):
        raise DatasetBuildError(f"{label} escapes suite directory: {relative}")
    if not path.is_file():
        raise DatasetBuildError(f"{label} file is missing: {path}")
    raw = path.read_bytes()
    actual_sha = _sha256(raw)
    if actual_sha != expected_sha:
        raise DatasetBuildError(
            f"{label} hash mismatch: expected {expected_sha}, got {actual_sha}"
        )
    return path, raw


def _query_from_public_task(public_task: Mapping[str, Any], path: Path) -> str:
    for key in ("intent", "query", "prompt", "question"):
        value = public_task.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise DatasetBuildError(f"public task has no query text: {path}")


def _citation_urls(score: Mapping[str, Any], report: str) -> list[str]:
    used = score.get("used_citations")
    if isinstance(used, list):
        urls = [str(value).strip() for value in used if str(value).strip()]
        if urls:
            return sorted(set(urls))
    return sorted(set(_URL_RE.findall(report)))


def _json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatasetBuildError(f"invalid UTF-8 JSON in {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise DatasetBuildError(f"JSON root must be an object: {label}")
    return value


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(_jsonl_line(row) for row in rows).encode("utf-8")


def _jsonl_line(row: Mapping[str, Any]) -> str:
    line = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    for separator, escaped in (
        ("\u0085", "\\u0085"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        line = line.replace(separator, escaped)
    return line + "\n"


def _source_artifact(
    path: Path,
    sha256: str,
    *,
    candidates_root: Path,
) -> dict[str, Any]:
    return {
        "path": path.resolve().relative_to(candidates_root.resolve()).as_posix(),
        "sha256": sha256,
    }


def _suite_artifact(path: Path, raw: bytes, *, suite_dir: Path) -> dict[str, Any]:
    return {
        "path": path.resolve().relative_to(suite_dir.resolve()).as_posix(),
        "sha256": _sha256(raw),
    }


def _portable_path(path: Path) -> str:
    project_root = Path(__file__).resolve().parents[2]
    try:
        return path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
