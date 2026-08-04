"""Immutable, hash-verified Task Evaluation Contracts for DRA scoring.

The transition compiler is intentionally report-blind, but calling it once per
report still changes the evaluation instrument across harnesses.  This module
turns one compiler output into a reusable task-level contract and verifies
every byte before a scoring run consumes it.

Two semantics are represented explicitly:

``transition_legacy_exact``
    Preserve the current diagnostic denominator byte-for-byte.  TWM atomic
    assertions remain scored Completeness units.

``research_obligations_v1``
    Treat TWM atomic assertions as answerability/retrieval witnesses only.
    Completeness is defined by the report-blind research obligations.  An
    atomic assertion enters Completeness only when it was explicitly marked
    ``scored_in_completeness`` during task construction.

The first mode makes historical comparisons possible.  The second is the
target semantics, and prevents a world-model census from silently becoming a
list of public-query obligations.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


CONTRACT_SCHEMA = "dra_task_evaluation_contract_v1"
CONTRACT_SEMANTICS = {
    "transition_legacy_exact",
    "research_obligations_v1",
}

_ARTIFACT_FILES = {
    "facets": ("facets.json", "json"),
    "rubric_items": ("rubric_items.jsonl", "jsonl"),
    "atomic_completeness_units": (
        "atomic_completeness_units.jsonl",
        "jsonl",
    ),
    "research_units": ("research_units.jsonl", "jsonl"),
    "answerability_facts": ("answerability_facts.jsonl", "jsonl"),
}


class ContractValidationError(ValueError):
    """Raised when a frozen task contract is incomplete or has drifted."""


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ContractValidationError(
                    f"{path}:{line_no} must contain a JSON object"
                )
            rows.append(value)
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            )


def _unique_ids(
    rows: list[dict[str, Any]],
    field: str,
    artifact_name: str,
) -> set[str]:
    identifiers: list[str] = []
    for index, row in enumerate(rows, 1):
        identifier = str(row.get(field) or "")
        if not identifier:
            raise ContractValidationError(
                f"{artifact_name} row {index} has no {field}"
            )
        identifiers.append(identifier)
    duplicates = sorted(
        identifier
        for identifier in set(identifiers)
        if identifiers.count(identifier) > 1
    )
    if duplicates:
        raise ContractValidationError(
            f"{artifact_name} contains duplicate {field}: {duplicates}"
        )
    return set(identifiers)


def _artifact_entry(path: Path, value: Any, file_format: str) -> dict[str, Any]:
    count = len(value) if isinstance(value, list) else 1
    return {
        "file": path.name,
        "format": file_format,
        "sha256": file_sha256(path),
        "row_count": count,
    }


def _contract_identity(
    *,
    task_id: str,
    query_sha256: str,
    contract_semantics: str,
    source_hashes: dict[str, str],
    compiler_manifest_sha256: str,
    artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": CONTRACT_SCHEMA,
        "task_id": task_id,
        "query_sha256": query_sha256,
        "contract_semantics": contract_semantics,
        "source_hashes": source_hashes,
        "compiler_manifest_sha256": compiler_manifest_sha256,
        "artifacts": artifacts,
    }


def seal_compiled_task_contract(
    *,
    compiled_dir: Path,
    output_dir: Path,
    task: dict[str, Any],
    task_world_model: dict[str, Any],
    research_test_suite: dict[str, Any],
    contract_semantics: str,
    frozen_before_report_input: bool,
) -> dict[str, Any]:
    """Seal one report-blind compiler output as an immutable task contract."""

    if contract_semantics not in CONTRACT_SEMANTICS:
        raise ValueError(
            "contract_semantics must be one of "
            f"{sorted(CONTRACT_SEMANTICS)}"
        )
    compiled_dir = Path(compiled_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    compiler_manifest_path = compiled_dir / "tec-manifest.json"
    compiler_manifest = _read_json(compiler_manifest_path)
    task_id = str(
        task.get("task_id")
        or task_world_model.get("task_id")
        or compiler_manifest.get("task_id")
        or ""
    )
    if not task_id:
        raise ContractValidationError("task contract has no task_id")
    query = str(
        task.get("prompt")
        or task.get("intent")
        or task.get("query")
        or compiler_manifest.get("query")
        or ""
    )
    source_hashes = {
        "task": canonical_json_sha256(task),
        "task_world_model": canonical_json_sha256(task_world_model),
        "research_test_suite": canonical_json_sha256(research_test_suite),
    }
    compiler_source_hashes = compiler_manifest.get("source_hashes") or {}
    if compiler_source_hashes and compiler_source_hashes != source_hashes:
        raise ContractValidationError(
            "compiler source hashes do not match the supplied frozen task assets"
        )

    facets = _read_json(compiled_dir / "facets.json")
    rubric_items = _read_jsonl(compiled_dir / "rubric_items.jsonl")
    atomic_facts = _read_jsonl(compiled_dir / "atomic_facts.jsonl")
    research_units = _read_jsonl(compiled_dir / "research_units.jsonl")
    if contract_semantics == "transition_legacy_exact":
        atomic_completeness_units = list(atomic_facts)
    else:
        atomic_completeness_units = [
            row
            for row in atomic_facts
            if bool(row.get("scored_in_completeness", False))
        ]
    scored_atomic_ids = {
        str(row.get("unit_id") or "") for row in atomic_completeness_units
    }
    answerability_facts = [
        {
            **row,
            "scored_in_completeness": str(row.get("unit_id") or "")
            in scored_atomic_ids,
        }
        for row in atomic_facts
    ]

    values = {
        "facets": facets,
        "rubric_items": rubric_items,
        "atomic_completeness_units": atomic_completeness_units,
        "research_units": research_units,
        "answerability_facts": answerability_facts,
    }
    artifacts: dict[str, dict[str, Any]] = {}
    for logical_name, (filename, file_format) in _ARTIFACT_FILES.items():
        path = output_dir / filename
        value = values[logical_name]
        if file_format == "jsonl":
            _write_jsonl(path, value)
        else:
            _write_json(path, value)
        artifacts[logical_name] = _artifact_entry(path, value, file_format)

    identity = _contract_identity(
        task_id=task_id,
        query_sha256=hashlib.sha256(query.encode("utf-8")).hexdigest(),
        contract_semantics=contract_semantics,
        source_hashes=source_hashes,
        compiler_manifest_sha256=file_sha256(compiler_manifest_path),
        artifacts=artifacts,
    )
    notes = list(compiler_manifest.get("formal_eligibility_notes") or [])
    if not frozen_before_report_input:
        notes.append(
            "contract was sealed after report inputs existed; diagnostic reuse only"
        )
    if contract_semantics == "transition_legacy_exact":
        notes.append(
            "legacy transition semantics score all TWM assertions in Completeness"
        )
    notes = list(dict.fromkeys(notes))
    manifest = {
        **identity,
        "contract_sha256": canonical_json_sha256(identity),
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "compiled_without_report": bool(
            compiler_manifest.get("compiled_without_report")
        ),
        "frozen_before_report_input": bool(frozen_before_report_input),
        "compiler": {
            "schema": compiler_manifest.get("schema"),
            "model": compiler_manifest.get("compiler_model"),
            "manual_semantic_decisions": compiler_manifest.get(
                "manual_semantic_decisions"
            ),
        },
        "counts": {
            logical_name: entry["row_count"]
            for logical_name, entry in artifacts.items()
        },
        "formal_eligible": bool(
            compiler_manifest.get("formal_eligible")
            and frozen_before_report_input
            and contract_semantics == "research_obligations_v1"
        ),
        "formal_eligibility_notes": notes,
    }
    _write_json(output_dir / "contract-manifest.json", manifest)
    return load_task_evaluation_contract(
        output_dir,
        expected_task=task,
        expected_task_world_model=task_world_model,
        expected_research_test_suite=research_test_suite,
    )


def load_task_evaluation_contract(
    contract_dir: Path,
    *,
    expected_task: dict[str, Any] | None = None,
    expected_task_world_model: dict[str, Any] | None = None,
    expected_research_test_suite: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load a task contract only after hash and referential validation."""

    contract_dir = Path(contract_dir)
    manifest_path = contract_dir / "contract-manifest.json"
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != CONTRACT_SCHEMA:
        raise ContractValidationError(
            f"unsupported contract schema: {manifest.get('schema')!r}"
        )
    semantics = str(manifest.get("contract_semantics") or "")
    if semantics not in CONTRACT_SEMANTICS:
        raise ContractValidationError(
            f"unsupported contract semantics: {semantics!r}"
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ContractValidationError("contract has no artifact table")

    values: dict[str, Any] = {}
    for logical_name, (expected_filename, expected_format) in _ARTIFACT_FILES.items():
        entry = artifacts.get(logical_name)
        if not isinstance(entry, dict):
            raise ContractValidationError(
                f"contract is missing artifact {logical_name}"
            )
        if entry.get("file") != expected_filename:
            raise ContractValidationError(
                f"{logical_name} must use {expected_filename}"
            )
        if entry.get("format") != expected_format:
            raise ContractValidationError(
                f"{logical_name} has an invalid format"
            )
        path = contract_dir / expected_filename
        if not path.is_file():
            raise ContractValidationError(f"missing contract artifact: {path}")
        actual_sha256 = file_sha256(path)
        if actual_sha256 != entry.get("sha256"):
            raise ContractValidationError(
                f"contract artifact hash mismatch: {logical_name}"
            )
        value = _read_jsonl(path) if expected_format == "jsonl" else _read_json(path)
        actual_count = len(value) if isinstance(value, list) else 1
        if actual_count != entry.get("row_count"):
            raise ContractValidationError(
                f"contract artifact count mismatch: {logical_name}"
            )
        values[logical_name] = value

    identity = _contract_identity(
        task_id=str(manifest.get("task_id") or ""),
        query_sha256=str(manifest.get("query_sha256") or ""),
        contract_semantics=semantics,
        source_hashes=dict(manifest.get("source_hashes") or {}),
        compiler_manifest_sha256=str(
            manifest.get("compiler_manifest_sha256") or ""
        ),
        artifacts=artifacts,
    )
    if canonical_json_sha256(identity) != manifest.get("contract_sha256"):
        raise ContractValidationError("contract identity hash mismatch")

    expected_sources: dict[str, str] = {}
    if expected_task is not None:
        expected_sources["task"] = canonical_json_sha256(expected_task)
        expected_task_id = str(expected_task.get("task_id") or "")
        if expected_task_id and expected_task_id != manifest.get("task_id"):
            raise ContractValidationError(
                "task_id does not match the frozen task contract"
            )
        expected_query = str(
            expected_task.get("prompt")
            or expected_task.get("intent")
            or expected_task.get("query")
            or ""
        )
        expected_query_sha256 = hashlib.sha256(
            expected_query.encode("utf-8")
        ).hexdigest()
        if expected_query_sha256 != manifest.get("query_sha256"):
            raise ContractValidationError(
                "query does not match the frozen task contract"
            )
    if expected_task_world_model is not None:
        expected_sources["task_world_model"] = canonical_json_sha256(
            expected_task_world_model
        )
    if expected_research_test_suite is not None:
        expected_sources["research_test_suite"] = canonical_json_sha256(
            expected_research_test_suite
        )
    for name, expected_hash in expected_sources.items():
        if (manifest.get("source_hashes") or {}).get(name) != expected_hash:
            raise ContractValidationError(
                f"{name} does not match the frozen task contract"
            )

    facets = values["facets"]
    if not isinstance(facets, list):
        raise ContractValidationError("facets must be a JSON array")
    facet_ids = _unique_ids(facets, "facet_id", "facets")
    atomic_units = values["atomic_completeness_units"]
    research_units = values["research_units"]
    rubric_items = values["rubric_items"]
    answerability_facts = values["answerability_facts"]
    _unique_ids(atomic_units, "unit_id", "atomic_completeness_units")
    _unique_ids(research_units, "unit_id", "research_units")
    _unique_ids(rubric_items, "rubric_id", "rubric_items")
    _unique_ids(answerability_facts, "unit_id", "answerability_facts")
    for artifact_name, rows in (
        ("atomic_completeness_units", atomic_units),
        ("research_units", research_units),
        ("answerability_facts", answerability_facts),
    ):
        unknown = sorted(
            {
                str(row.get("facet_id") or "")
                for row in rows
                if row.get("facet_id") not in facet_ids
            }
        )
        if unknown:
            raise ContractValidationError(
                f"{artifact_name} references unknown facets: {unknown}"
            )

    return {
        "manifest": manifest,
        "facets": facets,
        "atomic_units": atomic_units,
        "research_units": research_units,
        "rubric_items": rubric_items,
        "answerability_facts": answerability_facts,
        "contract_dir": contract_dir,
        "manifest_path": manifest_path,
    }


__all__ = [
    "CONTRACT_SCHEMA",
    "CONTRACT_SEMANTICS",
    "ContractValidationError",
    "canonical_json_sha256",
    "file_sha256",
    "load_task_evaluation_contract",
    "seal_compiled_task_contract",
]
