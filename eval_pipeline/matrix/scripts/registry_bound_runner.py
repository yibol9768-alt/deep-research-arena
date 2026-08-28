#!/usr/bin/env python3
"""Run the existing unified runner against a SHA-bound package task JSON.

The source document stays unchanged. The adapter maps its canonical `question`
field to the legacy runner's in-memory `intent` field at the single dispatch
boundary; no registry file in the shared checkout is created or overwritten.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path


RUNNER_OVERLAY_MODULES = (
    "deerflow_runner",
    "opencode_runner",
    "claudecode_runner",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install_runner_overlays(patch_dir: Path, *, repo_root: Path) -> list[dict]:
    """Load the three versioned runner fixes without editing the shared checkout.

    The unified runner imports these modules by their canonical
    ``scripts.runners.*`` names.  Installing the overlays under those exact
    names before ``run_deep_task.py`` is imported makes the replacement
    explicit and process-local.  A configured patch directory is fail-closed:
    all three files must exist and import successfully.
    """
    patch_dir = patch_dir.resolve(strict=True)
    if not patch_dir.is_dir():
        raise NotADirectoryError(f"runner patch path is not a directory: {patch_dir}")
    repo_root = repo_root.resolve(strict=True)
    os.environ["DRA_REPO_ROOT"] = str(repo_root)
    package = importlib.import_module("scripts.runners")
    paths = {stem: patch_dir / f"{stem}.py" for stem in RUNNER_OVERLAY_MODULES}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "missing required runner overlay: " + ", ".join(missing)
        )
    installed: list[dict] = []
    for stem in RUNNER_OVERLAY_MODULES:
        path = paths[stem]
        module_name = f"scripts.runners.{stem}"
        previous = sys.modules.get(module_name)
        previous_attribute = getattr(package, stem, None)
        had_previous_attribute = hasattr(package, stem)
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot build import spec for runner overlay: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            setattr(package, stem, module)
        except BaseException:
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous
            if had_previous_attribute:
                setattr(package, stem, previous_attribute)
            else:
                try:
                    delattr(package, stem)
                except AttributeError:
                    pass
            raise
        installed.append(
            {
                "module": module_name,
                "path": str(path),
                "sha256": sha256(path),
            }
        )
    return installed


def load_bound_task(path: Path, *, expected_file_sha: str, task_id: str, question_sha: str) -> tuple[dict, dict]:
    if sha256(path) != expected_file_sha:
        raise ValueError("task_json SHA-256 mismatch")
    source = json.loads(path.read_text())
    if source.get("task_id") != task_id:
        raise ValueError("task_json task_id mismatch")
    question = source.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("task_json.question is missing")
    if hashlib.sha256(question.encode()).hexdigest() != question_sha:
        raise ValueError("task_json.question SHA-256 mismatch")
    if source.get("intent") not in {None, question}:
        raise ValueError("task_json has a conflicting legacy intent")
    runtime = dict(source)
    runtime["intent"] = question
    receipt = {
        "schema_version": "1.0.0", "task_id": task_id, "source_path": str(path),
        "source_sha256": expected_file_sha, "source_field": "question",
        "question_sha256": question_sha, "legacy_runtime_field": "intent",
        "source_mutated": False,
    }
    return runtime, receipt


def model_probe_payload(declared: str, body: dict) -> dict:
    """Apply the route-specific, identity-only GPT probe contract.

    Service 27797 rejects the legacy ``max_tokens`` + ``temperature`` probe.
    It accepts the current OpenAI field while still returning the exact model
    identity.  Other model routes retain the shared runner's frozen payload.
    """
    payload = dict(body)
    if declared == "gpt-5.6-sol-2026-07-09":
        payload.pop("max_tokens", None)
        payload.pop("temperature", None)
        payload["max_completion_tokens"] = 16
    return payload


def install_matrix_model_probe(module) -> None:
    original = module._probe_lane_model

    def matrix_probe(agent: str, declared: str) -> dict:
        if declared != "gpt-5.6-sol-2026-07-09":
            return original(agent, declared)
        from scripts.run_manifest import probe_model_identity
        import requests

        endpoint, role = module._model_probe_endpoint(agent)
        timeout_s = float(os.environ.get("DRA_MODEL_PROBE_TIMEOUT_S", "20"))

        def transport(url: str, headers: dict, body: dict) -> dict:
            session = requests.Session()
            session.trust_env = False
            response = session.post(
                url,
                headers=headers,
                json=model_probe_payload(declared, body),
                timeout=timeout_s,
            )
            response.raise_for_status()
            return response.json()

        result = probe_model_identity(
            endpoint,
            "anything",
            declared,
            transport=transport,
            model_for_request=declared,
            timeout_s=timeout_s,
        )
        result["endpoint_role"] = role
        result["probe_contract"] = "max_completion_tokens_16_no_temperature"
        return result

    module._probe_lane_model = matrix_probe


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=Path, required=True)
    ap.add_argument("--task-json", type=Path, required=True)
    ap.add_argument("--task-json-sha256", required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--question-sha256", required=True)
    ap.add_argument("--binding-receipt", type=Path, required=True)
    ap.add_argument("runner_args", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    runner_args = args.runner_args[1:] if args.runner_args[:1] == ["--"] else args.runner_args
    task, receipt = load_bound_task(args.task_json, expected_file_sha=args.task_json_sha256, task_id=args.task_id, question_sha=args.question_sha256)
    repo_root = args.runner.resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    patch_dir = os.environ.get("DRA_RUNNER_PATCH_DIR", "").strip()
    if patch_dir:
        receipt["runner_overlays"] = install_runner_overlays(
            Path(patch_dir), repo_root=repo_root
        )
    else:
        receipt["runner_overlays"] = []
    args.binding_receipt.parent.mkdir(parents=True, exist_ok=True)
    args.binding_receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    spec = importlib.util.spec_from_file_location("matrix_bound_run_deep_task", args.runner)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module._load_task = lambda requested: task if requested == args.task_id else (_ for _ in ()).throw(ValueError("unbound task id"))
    install_matrix_model_probe(module)
    sys.argv = [str(args.runner), *runner_args]
    return int(asyncio.run(module.main()))


if __name__ == "__main__":
    raise SystemExit(main())
