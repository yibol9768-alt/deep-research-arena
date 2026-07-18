#!/usr/bin/env python3
"""Import and minimally normalize the 14 Route A annotator-B YAML files.

Original attachment bytes are preserved verbatim.  The normalized copy only
quotes mapping scalar values so Chinese text following an embedded quoted
English phrase remains valid YAML.  No requirement is added, removed, merged,
or edited semantically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(
    "/root/.codex/attachments/2abc0b95-49ed-4375-93cd-13abb57b40f6"
)
DEFAULT_OUTPUT = ROOT / "data/calibration/route_a_dev14/annotations/B"
TASK_MANIFEST = ROOT / "data/calibration/route_a_dev14/task_manifest.json"
FILENAME_RE = re.compile(r"annotation_(dr_cross_deep_\d{4})_B\.yaml$")
MAPPING_RE = re.compile(
    r"^(?P<prefix>\s*(?:-\s+)?[A-Za-z_][A-Za-z0-9_]*:\s*)(?P<value>.*)$"
)
ALLOWED_ROLES = {"shopping", "forums", "wiki"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def normalize_yaml_text(text: str) -> tuple[str, int]:
    """Iteratively quote only the mapping value reported by the YAML parser."""

    lines = text.splitlines()
    repairs = 0
    repaired_lines: set[int] = set()
    while True:
        candidate = "\n".join(lines).rstrip() + "\n"
        try:
            yaml.safe_load(candidate)
            return candidate, repairs
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            if mark is None:
                raise
            target = mark.line
            match = MAPPING_RE.match(lines[target]) if target < len(lines) else None
            if match is None or not match.group("value").strip():
                # A parser may point at the continuation line.  Walk backward
                # only to the nearest mapping key; do not rewrite block bodies.
                match = None
                for index in range(target - 1, -1, -1):
                    possible = MAPPING_RE.match(lines[index])
                    if possible and possible.group("value").strip():
                        target = index
                        match = possible
                        break
            if match is None or target in repaired_lines:
                raise
            value = match.group("value").strip()
            if value in {"|", "|-", "|+", ">", ">-", ">+"}:
                raise
            lines[target] = match.group("prefix") + json.dumps(
                value, ensure_ascii=False
            )
            repaired_lines.add(target)
            repairs += 1


def _validate_annotation(
    data: Any,
    *,
    expected_task: str,
    expected_query_hash: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["document_not_mapping"]
    expected_scalars = {
        "packet_version": "route_a_interview_v1",
        "questionnaire_version": "route_a_qbank_v1",
        "annotation_mode": "human_interviewed",
        "annotator_id": "B",
        "task_id": expected_task,
        "query_sha256": expected_query_hash,
        "evidence_answerability": "not_assessed",
    }
    for key, expected in expected_scalars.items():
        if str(data.get(key)) != expected:
            errors.append(f"{key}_mismatch")
    if not isinstance(data.get("initial_response"), str) or not data["initial_response"].strip():
        errors.append("initial_response_missing")
    if not isinstance(data.get("initial_requirements"), list):
        errors.append("initial_requirements_not_list")
    requirements = data.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        errors.append("requirements_missing")
        return errors
    ids: list[str] = []
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            errors.append(f"requirements_{index}_not_mapping")
            continue
        for field in (
            "local_id",
            "requirement",
            "necessity_reason",
            "query_basis",
            "output_form",
            "intrinsic_source_roles",
            "source_role_reason",
        ):
            if field not in requirement:
                errors.append(f"requirements_{index}_{field}_missing")
        local_id = str(requirement.get("local_id") or "")
        ids.append(local_id)
        roles = requirement.get("intrinsic_source_roles")
        if not isinstance(roles, list):
            errors.append(f"{local_id}_source_roles_not_list")
        elif set(map(str, roles)) - ALLOWED_ROLES:
            errors.append(f"{local_id}_source_roles_invalid")
    if len(ids) != len(set(ids)):
        errors.append("duplicate_local_ids")
    if not isinstance(data.get("unresolved"), list):
        errors.append("unresolved_not_list")
    return sorted(set(errors))


def _review_flags(data: dict[str, Any]) -> list[dict[str, str]]:
    """Deterministic adjudication flags; these do not alter the annotation."""

    flags: list[dict[str, str]] = []
    for req in data.get("requirements") or []:
        text = " ".join(
            str(req.get(key) or "")
            for key in ("requirement", "necessity_reason", "query_basis")
        )
        local_id = str(req.get("local_id") or "?")
        if any(token in text.lower() for token in ("隐含", "implicit")):
            flags.append(
                {
                    "local_id": local_id,
                    "code": "implicit_obligation_needs_adjudication",
                    "detail": "Requirement relies on an implied rather than explicit query obligation.",
                }
            )
        if any(token in text.lower() for token in ("结构化格式", "table", "表格", "显要位置")):
            flags.append(
                {
                    "local_id": local_id,
                    "code": "presentation_format_may_be_nonessential",
                    "detail": "Presentation format may be desirable writing quality rather than a necessary query obligation.",
                }
            )
        if any(token in text.lower() for token in ("近期在售", "时效性", "最新", "current availability")):
            flags.append(
                {
                    "local_id": local_id,
                    "code": "timeliness_requirement_needs_query_basis",
                    "detail": "Timeliness must be explicitly grounded in the query before it can score.",
                }
            )
    return flags


def import_annotations(source_dir: Path, output_dir: Path) -> dict[str, Any]:
    manifest = json.loads(TASK_MANIFEST.read_text(encoding="utf-8"))
    expected = {
        row["task_id"]: row["query_sha256"] for row in manifest["tasks"]
    }
    paths = sorted(source_dir.glob("annotation_dr_cross_deep_*_B.yaml"))
    found_ids = {
        match.group(1)
        for path in paths
        if (match := FILENAME_RE.match(path.name))
    }
    if found_ids != set(expected):
        raise SystemExit(
            "attachment task set mismatch: "
            + json.dumps(
                {
                    "missing": sorted(set(expected) - found_ids),
                    "extra": sorted(found_ids - set(expected)),
                }
            )
        )

    original_dir = output_dir / "original"
    normalized_dir = output_dir / "normalized"
    original_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    all_flags: list[dict[str, str]] = []
    for source in paths:
        match = FILENAME_RE.match(source.name)
        assert match is not None
        task_id = match.group(1)
        original_bytes = source.read_bytes()
        original_target = original_dir / source.name
        original_target.write_bytes(original_bytes)
        original_valid = True
        original_error = None
        try:
            yaml.safe_load(original_bytes)
        except yaml.YAMLError as exc:
            original_valid = False
            mark = getattr(exc, "problem_mark", None)
            original_error = {
                "line": mark.line + 1 if mark else None,
                "column": mark.column + 1 if mark else None,
                "problem": getattr(exc, "problem", str(exc)),
            }

        normalized_text, repairs = normalize_yaml_text(
            original_bytes.decode("utf-8")
        )
        data = yaml.safe_load(normalized_text)
        errors = _validate_annotation(
            data,
            expected_task=task_id,
            expected_query_hash=expected[task_id],
        )
        normalized_target = normalized_dir / source.name
        normalized_target.write_text(normalized_text, encoding="utf-8")
        flags = _review_flags(data)
        all_flags.extend(
            {"task_id": task_id, **flag} for flag in flags
        )
        rows.append(
            {
                "task_id": task_id,
                "source_filename": source.name,
                "original_path": _display_path(original_target),
                "original_sha256": _sha256(original_bytes),
                "original_yaml_valid": original_valid,
                "original_yaml_error": original_error,
                "normalization_scalar_quotes_added": repairs,
                "normalized_path": _display_path(normalized_target),
                "normalized_sha256": _sha256(normalized_text.encode("utf-8")),
                "normalized_yaml_valid": True,
                "schema_errors": errors,
                "annotation_mode": data.get("annotation_mode"),
                "annotator_id": data.get("annotator_id"),
                "requirement_count": len(data.get("requirements") or []),
                "unresolved_count": len(data.get("unresolved") or []),
                "review_flags": flags,
            }
        )

    output = {
        "schema": "route_a_annotation_import_v1",
        "annotator_id": "B",
        "source": "user_provided_attachment",
        "task_count": len(rows),
        "requirement_count": sum(row["requirement_count"] for row in rows),
        "original_yaml_valid_count": sum(row["original_yaml_valid"] for row in rows),
        "normalized_yaml_valid_count": sum(row["normalized_yaml_valid"] for row in rows),
        "schema_valid_count": sum(not row["schema_errors"] for row in rows),
        "unresolved_total": sum(row["unresolved_count"] for row in rows),
        "independence_attestation": "not_provided",
        "adjudication_status": "not_started",
        "formal_calibration_eligible": False,
        "status": "imported_pending_independence_attestation_and_adjudication",
        "tasks": rows,
        "review_flags": all_flags,
    }
    (output_dir / "import_manifest.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = import_annotations(args.source_dir, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
