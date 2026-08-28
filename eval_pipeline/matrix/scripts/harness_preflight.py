#!/usr/bin/env python3
"""Zero-model preflight for all 17 Q1-v2 Harnesses on authorized any2.

This script imports and inspects runtime code, local CLI pins, isolated STORM
dependencies, strict-sandbox call signatures, fallback settings and the frozen
matrix/package bindings.  It never sends a model, search or judge request.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import inspect
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZED_HOSTNAME = "VM-209-61-tencentos"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def run_text(command: list[str], env: dict[str, str]) -> str:
    completed = subprocess.run(
        command,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    return (completed.stdout or completed.stderr).strip()


def load_runtime_module(runner_path: Path):
    root = runner_path.resolve().parents[1]
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("q1_v2_runtime", runner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load unified runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "generated/matrix.manifest.json",
    )
    args = parser.parse_args()

    runtime = read_json(ROOT / "config/runtime.contract.json")
    manifest = read_json(args.manifest)
    routes = read_json(ROOT / "config/model_routes.json")
    failures: list[str] = []
    hostname = socket.gethostname()
    if hostname != AUTHORIZED_HOSTNAME:
        failures.append(f"unauthorized_hostname:{hostname}")

    env = dict(os.environ)
    prefix = str(runtime.get("path_prefix") or "")
    env["PATH"] = prefix + os.pathsep + env.get("PATH", "")
    env.update(
        {
            str(key): str(value)
            for key, value in (
                runtime.get("local_only_harness_environment") or {}
            ).items()
        }
    )

    runner_path = Path(runtime["runner_path"])
    if not runner_path.is_file() or sha256(runner_path) != runtime["runner_sha256"]:
        failures.append("unified_runner_seal_mismatch")
        runners: dict[str, Any] = {}
    else:
        module = load_runtime_module(runner_path)
        runners = dict(module.RUNNERS)

    expected_harnesses = [row["harness_id"] for row in manifest["harnesses"]]
    if set(runners) != set(expected_harnesses) or len(runners) != 17:
        failures.append("runner_registry_not_exactly_17")

    harness_receipts = []
    for harness_id in expected_harnesses:
        fn = runners.get(harness_id)
        signature = inspect.signature(fn) if fn is not None else None
        strict_parameter = (
            signature is not None and "strict_sandbox" in signature.parameters
        )
        if not strict_parameter:
            failures.append(f"strict_sandbox_missing:{harness_id}")
        harness_receipts.append(
            {
                "harness_id": harness_id,
                "registered": fn is not None,
                "strict_sandbox_parameter": strict_parameter,
                "runtime_module": getattr(fn, "__module__", None),
            }
        )

    binary_versions = {}
    commands = {
        "node": ["node", "--version"],
        "@anthropic-ai/claude-code": ["claude", "--version"],
        "opencode-ai": ["opencode", "--version"],
        "@openai/codex": ["codex", "--version"],
    }
    for package, command in commands.items():
        try:
            binary_versions[package] = run_text(command, env)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"local_cli_failed:{package}:{type(exc).__name__}")

    npm_prefix = Path(prefix.split(os.pathsep)[1]).parents[1]
    try:
        npm_doc = json.loads(
            run_text(
                ["npm", "ls", "--prefix", str(npm_prefix), "--depth=0", "--json"],
                env,
            )
        )
        npm_versions = {
            name: str((npm_doc.get("dependencies") or {}).get(name, {}).get("version") or "")
            for name in runtime["pinned_local_runtime"]
            if name != "node"
        }
    except Exception as exc:  # noqa: BLE001
        npm_versions = {}
        failures.append(f"npm_pin_read_failed:{type(exc).__name__}")
    for name, expected in runtime["pinned_local_runtime"].items():
        actual = binary_versions.get(name) if name == "node" else npm_versions.get(name)
        if name == "node":
            actual = binary_versions.get("node")
        if actual != expected and not (
            name == "@anthropic-ai/claude-code" and str(actual).startswith(expected)
        ) and not (
            name == "@openai/codex" and str(actual).endswith(expected)
        ):
            failures.append(f"runtime_pin_mismatch:{name}:{actual}")

    storm_python = Path("/data1/deep-research-arena/.venv-storm/bin/python")
    storm_dependency_status = "FAIL"
    storm_truth1000_subprocess_bridge = False
    try:
        storm_output = run_text(
            [
                str(storm_python),
                "-c",
                "import dspy,knowledge_storm; print(knowledge_storm.__version__)",
            ],
            env,
        )
        storm_dependency_status = f"PASS:{storm_output}"
    except Exception as exc:  # noqa: BLE001
        failures.append(f"storm_isolated_dependency_failed:{type(exc).__name__}")
    storm_fn = runners.get("storm")
    if storm_fn is not None:
        storm_source = inspect.getsource(storm_fn)
        storm_truth1000_subprocess_bridge = (
            "truth1000_storm_runner" in storm_source
            and "truth1000_adapter is not None" in storm_source
        )
    if not storm_truth1000_subprocess_bridge:
        failures.append("storm_truth1000_subprocess_bridge_missing")

    fallback_env = runtime.get("local_only_harness_environment") or {}
    for key in ("CLAUDE_CODE_SSH_HOST", "OPENCODE_SSH_HOST", "CODEX_SSH_HOST"):
        if fallback_env.get(key) != "":
            failures.append(f"ssh_fallback_enabled:{key}")
    if fallback_env.get("EVIDENCE_FALLBACK_ENABLE") != "0":
        failures.append("evidence_fallback_enabled")

    codex_module = importlib.import_module("scripts.runners.codex_runner")
    codex_source = inspect.getsource(codex_module._run_local_codex)
    codex_workspace_sandbox = (
        '"--sandbox", "workspace-write"' in codex_source
        and "--dangerously-bypass-approvals-and-sandbox" not in codex_source
    )
    if not codex_workspace_sandbox:
        failures.append("codex_local_workspace_sandbox_missing")

    route_rows = routes.get("models", [])
    route_ids = {row["model_id"] for row in route_rows}
    if route_ids != {row["model_id"] for row in manifest["models"]}:
        failures.append("six_model_route_set_mismatch")
    for row in route_rows:
        model_id = str(row.get("model_id") or "")
        request_name = str(row.get("request_name") or "")
        expected_identity = str(row.get("expected_actual_identity") or "")
        if not request_name:
            failures.append(f"route_request_name_missing:{model_id}")
        if not expected_identity:
            failures.append(f"route_expected_identity_missing:{model_id}")
        if not str(row.get("upstream_url") or "").endswith("/v1"):
            failures.append(f"route_upstream_url_invalid:{model_id}")
    first = manifest["cells"][0]
    if (first["harness_id"], first["model_id"]) != ("deerflow", "gpt-5-6-sol"):
        failures.append("first_cell_binding_mismatch")
    if manifest.get("design") == "CROSS5_FIXED_HARNESS_FIXED_MODEL":
        expected_cross5 = (
            "biodiversity-q1-v2--deerflow--gpt-5-6-sol",
            "biodiversity-q1-v2--deerflow--gemini-3-1-pro-preview",
            "biodiversity-q1-v2--deerflow--claude-opus-5",
            "biodiversity-q1-v2--opencode--gpt-5-6-sol",
            "biodiversity-q1-v2--claude-code--gpt-5-6-sol",
        )
        if tuple(row.get("cell_id") for row in manifest["cells"]) != expected_cross5:
            failures.append("cross5_cell_selection_mismatch")

    receipt = {
        "schema_version": "q1_v2_harness_preflight_v1",
        "status": "PASS_NO_MODEL" if not failures else "BLOCKED",
        "model_requests": 0,
        "hostname": hostname,
        "authorized_hostname": AUTHORIZED_HOSTNAME,
        "runner_path": str(runner_path),
        "runner_sha256": sha256(runner_path) if runner_path.is_file() else None,
        "harness_count": len(runners),
        "harnesses": harness_receipts,
        "binary_versions": binary_versions,
        "npm_versions": npm_versions,
        "storm_dependency_status": storm_dependency_status,
        "storm_truth1000_subprocess_bridge": storm_truth1000_subprocess_bridge,
        "codex_workspace_sandbox": codex_workspace_sandbox,
        "ssh_fallbacks_disabled": True,
        "evidence_fallback_disabled": True,
        "first_cell_id": first["cell_id"],
        "matrix_manifest_path": str(args.manifest.resolve()),
        "matrix_manifest_sha256": sha256(args.manifest),
        "matrix_cell_count": len(manifest["cells"]),
        "matrix_design": manifest.get("design"),
        "failures": failures,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise FileExistsError(args.output)
        args.output.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
