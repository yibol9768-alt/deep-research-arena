#!/usr/bin/env python3
"""Read-only deployment preflight; performs no network or model request."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_census_is_kiwix_only(document: dict) -> bool:
    rows = document.get("sources")
    if not isinstance(rows, list) or len(rows) != 1:
        return False
    source = str(rows[0].get("source") or "").lower()
    return source in {"kiwix", "wiki", "wikipedia"} and int(rows[0].get("support_ref_count") or 0) > 0


def blockers(manifest: dict, runtime: dict, routes: dict, env: dict | None = None) -> list[str]:
    env = env or os.environ
    issues: list[str] = []
    if manifest.get("execution_mode") != "EXPERIMENTAL_ENABLED" or runtime.get("mode") != "EXPERIMENTAL_ENABLED":
        issues.append("experimental_mode_not_enabled")
    if manifest.get("formal_eligible") is not False or runtime.get("formal_eligible") is not False:
        issues.append("formal_state_would_be_upgraded")
    runner = Path(runtime["runner_path"])
    if not runner.is_file():
        issues.append("runner_missing")
    elif sha256(runner) != runtime["runner_sha256"]:
        issues.append("runner_sha256_mismatch")
    path_prefix = str(runtime.get("path_prefix") or "")
    required_local_bins = ("node", "claude", "opencode", "codex", "ccr")
    prefix_dirs = [Path(value) for value in path_prefix.split(os.pathsep) if value]
    for binary in required_local_bins:
        if not any((directory / binary).is_file() for directory in prefix_dirs):
            issues.append(f"local_runtime_missing:{binary}")
    local_env = runtime.get("local_only_harness_environment") or {}
    for key in ("CLAUDE_CODE_SSH_HOST", "OPENCODE_SSH_HOST", "CODEX_SSH_HOST"):
        if local_env.get(key) != "":
            issues.append(f"remote_fallback_not_disabled:{key}")
    package = manifest["source_package"]
    for name, ref in package.items():
        if not isinstance(ref, dict) or "path" not in ref:
            continue
        path = Path(ref["path"])
        if not path.is_file():
            issues.append(f"package_asset_missing:{name}")
        elif sha256(path) != ref["sha256"]:
            issues.append(f"package_asset_sha256_mismatch:{name}")
    task_ref = package["task_json"]
    task_path = Path(task_ref["path"])
    if task_path.is_file() and sha256(task_path) == task_ref["sha256"]:
        task = json.loads(task_path.read_text())
        if task.get("task_id") != manifest["task_id"]:
            issues.append("task_id_mismatch")
        question = task.get("question")
        if not isinstance(question, str) or hashlib.sha256(question.encode()).hexdigest() != task_ref["question_sha256"]:
            issues.append("question_sha256_mismatch")
        if task.get("report_generation_authorized") is not True or task.get("scoring_mode") != "SHADOW_EXPERIMENTAL_ONLY":
            issues.append("task_not_authorized_for_shadow_reports")
    census_ref = package["task_source_census"]
    census_path = Path(census_ref["path"])
    if census_path.is_file() and sha256(census_path) == census_ref["sha256"] and not source_census_is_kiwix_only(json.loads(census_path.read_text())):
        issues.append("task_source_census_not_kiwix_only")
    k2_manifest = Path(manifest["k2"]["index_dir"]) / "manifest.json"
    if not k2_manifest.is_file():
        issues.append("k2_manifest_missing")
    elif sha256(k2_manifest) != manifest["k2"]["manifest_sha256"]:
        issues.append("k2_manifest_sha256_mismatch")
    if not env.get(runtime["search_upstream_env"]):
        issues.append(f"missing_env:{runtime['search_upstream_env']}")
    credential_env = routes["credential_contract"]["env"]
    if not env.get(credential_env):
        issues.append(f"missing_env:{credential_env}")
    if not routes["credential_contract"].get("platform_user"):
        issues.append("missing_adams_platform_user")
    if not routes["credential_contract"].get("business"):
        issues.append("missing_adams_business")
    expected_models = {row["model_id"] for row in manifest["models"]}
    if {row.get("model_id") for row in routes.get("models", [])} != expected_models:
        issues.append("route_model_set_mismatch")
    return issues


def main() -> int:
    from build_matrix import build
    manifest = build(json.loads((ROOT / "config" / "matrix.source.json").read_text()))
    runtime = json.loads((ROOT / "config" / "runtime.contract.json").read_text())
    routes = json.loads((ROOT / "config" / "model_routes.json").read_text())
    issues = blockers(manifest, runtime, routes)
    print(json.dumps({"status": "PASS_NO_MODEL" if not issues else "BLOCKED", "model_requests": 0, "issues": issues}, sort_keys=True))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
