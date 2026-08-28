#!/usr/bin/env python3
"""Non-overwriting experimental 17x6 executor with cell failure isolation."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
import importlib.util
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_manifest(path: Path | None = None) -> dict:
    if path is not None:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError("matrix manifest must be a JSON object")
        return value
    generated = ROOT / "generated" / "matrix.manifest.json"
    if generated.is_file():
        return json.loads(generated.read_text())
    spec = importlib.util.spec_from_file_location("experimental_build_matrix", ROOT / "scripts" / "build_matrix.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.build(json.loads((ROOT / "config" / "matrix.source.json").read_text()))


def _atomic(path: Path, value: object, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seal(path: Path) -> dict:
    return {"path": path.name, "bytes": path.stat().st_size, "sha256": _sha(path)}


def initialize(run_dir: Path, run_id: str, manifest: dict, runtime: dict) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", run_id):
        raise ValueError("unsafe run_id")
    if manifest["execution_mode"] != "EXPERIMENTAL_ENABLED" or runtime["mode"] != "EXPERIMENTAL_ENABLED":
        raise ValueError("experimental mode is not enabled")
    if manifest.get("formal_eligible") is not False or runtime.get("formal_eligible") is not False:
        raise ValueError("formal eligibility must remain false")
    header = {
        "schema_version": "1.0.0", "run_id": run_id, "matrix_id": manifest["matrix_id"],
        "task_id": manifest["task_id"], "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "EXPERIMENTAL_ENABLED", "package_decision": "STRUCTURAL_READY_UNCALIBRATED",
        "formal_eligible": False,
        "evaluation_phase_authorized": bool(manifest.get("evaluation_phase_authorized")),
        "report_generation_authorized": True, "scoring_mode": "SHADOW_EXPERIMENTAL_ONLY",
    }
    _atomic(run_dir / "run.json", header, exclusive=True)
    (run_dir / "usage").mkdir(parents=True)
    (run_dir / "ledger").mkdir(parents=True)
    (run_dir / "usage" / "gateway_events.jsonl").touch(exist_ok=False)
    (run_dir / "ledger" / "transitions.jsonl").touch(exist_ok=False)
    task = manifest["source_package"]["task_json"]
    for cell in manifest["cells"]:
        cell_dir = run_dir / "cells" / cell["cell_id"]
        state = {
            "cell_id": cell["cell_id"], "harness_id": cell["harness_id"], "model_id": cell["model_id"],
            "requested_model": cell["model_request_name"], "runnable": cell["runnable"],
            "status": cell["status"], "status_reason": cell["status_reason"], "attempt_count": 0,
        }
        request = {
            "cell_id": cell["cell_id"], "task_id": manifest["task_id"], "task_json": task,
            "package_run_id": manifest["source_package"]["run_id"],
            "execution_mode": "EXPERIMENTAL_ENABLED", "formal_eligible": False,
            "scoring_mode": "SHADOW_EXPERIMENTAL_ONLY",
        }
        _atomic(cell_dir / "state.json", state, exclusive=True)
        _atomic(cell_dir / "request.json", request, exclusive=True)


def retry_allowed(receipt: dict | None, retries: int) -> bool:
    if retries >= 1 or not isinstance(receipt, dict) or receipt.get("source") != "adapter_normalized_exception":
        return False
    if receipt.get("failure_class") == "transport":
        return receipt.get("http_status") is None
    return receipt.get("failure_class") == "http" and receipt.get("http_status") in {500, 502, 503, 504}


def infrastructure_retry_evidence(cell_dir: Path, state: dict) -> tuple[bool, str]:
    """Fail closed unless the latest attempt is an attested harness stub failure.

    A low-quality, empty, or uncited *model* answer is still a successful
    attempt and must never enter this path.  This predicate is deliberately
    narrower: the runner exited non-zero, emitted its normalized infrastructure
    receipt, and explicitly attested that the report is an internal error stub
    rather than model output.
    """
    if state.get("status") != "failed":
        return False, "cell_is_not_failed"
    attempt_index = int(state.get("attempt_count") or 0)
    if attempt_index < 1:
        return False, "missing_prior_attempt"
    attempt_dir = cell_dir / f"attempt-{attempt_index}"
    required = {
        "exit": attempt_dir / "exit_status.json",
        "receipt": attempt_dir / "failure_receipt.json",
        "provenance": attempt_dir / "report_provenance.json",
        "identity": attempt_dir / "identity.json",
        "seal": attempt_dir / "seal.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        return False, "missing_retry_evidence:" + ",".join(sorted(missing))
    exit_status = json.loads(required["exit"].read_text())
    receipt = json.loads(required["receipt"].read_text())
    provenance = json.loads(required["provenance"].read_text())
    identity = json.loads(required["identity"].read_text())
    if (
        exit_status.get("status") != "failed"
        or exit_status.get("attempt") != attempt_index
        or not isinstance(exit_status.get("exit_code"), int)
        or exit_status.get("exit_code") == 0
    ):
        return False, "latest_exit_is_not_infrastructure_failure"
    if not (
        receipt.get("source") == "adapter_normalized_exception"
        and receipt.get("failure_class") == "task_failure"
        and isinstance(receipt.get("runner_exit_code"), int)
        and receipt.get("runner_exit_code") != 0
    ):
        return False, "failure_receipt_is_not_task_infrastructure"
    if not (
        provenance.get("internal_error_stub") is True
        and provenance.get("model_output_attested") is False
    ):
        return False, "prior_attempt_is_not_an_internal_error_stub"
    if identity.get("identity_consistent") is not True:
        return False, "prior_model_identity_is_not_consistent"
    return True, "attested_harness_infrastructure_failure"


async def _watch(proc, heartbeat: Path, timeout: float) -> tuple[int, bool]:
    last, stamp = time.monotonic(), heartbeat.stat().st_mtime_ns
    while proc.returncode is None:
        await asyncio.sleep(0.1)
        current = heartbeat.stat().st_mtime_ns
        if current != stamp:
            stamp, last = current, time.monotonic()
        if time.monotonic() - last > timeout:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            return int(proc.returncode), True
    return int(proc.returncode), False


async def dispatch(
    manifest: dict,
    runtime: dict,
    routes: dict,
    run_dir: Path,
    *,
    cells: list[dict] | None = None,
    env_base: dict | None = None,
    adapter_command: list[str] | None = None,
    watchdog: float | None = None,
    parallel: bool = False,
    global_cells: int | None = None,
    retry_failed_infrastructure: bool = False,
) -> dict:
    env_base = dict(env_base or os.environ)
    route_by_id = {x["model_id"]: x for x in routes["models"]}
    credential_contract = routes["credential_contract"]
    lanes = {x["model_id"]: asyncio.Semaphore(1) for x in manifest["models"]}
    global_limit = int(
        global_cells
        if global_cells is not None
        else manifest["concurrency"]["global_cells"]
    )
    if global_limit <= 0:
        raise ValueError("global cell concurrency must be positive")
    global_gate = asyncio.Semaphore(global_limit)
    ledger_lock = asyncio.Lock()
    usage_lock = asyncio.Lock()
    active = defaultdict(int)
    max_active = defaultdict(int)
    active_cells = 0
    max_active_cells = 0
    results: list[dict] = []
    task = manifest["source_package"]["task_json"]
    search_env = runtime["search_upstream_env"]
    search_upstream = env_base.get(search_env)
    command_template = adapter_command or runtime["adapter_command"]
    timeout = float(watchdog if watchdog is not None else manifest["timeouts_seconds"]["no_progress"])
    bm25_dir = run_dir / "bm25_slots"

    async def transition(cell_dir: Path, expected: str, target: str, reason: str | None = None):
        state_path = cell_dir / "state.json"
        state = json.loads(state_path.read_text())
        if state["status"] != expected:
            raise ValueError(f"illegal transition {state['status']}->{target}")
        state.update(status=target, status_reason=reason)
        _atomic(state_path, state)
        async with ledger_lock:
            with (run_dir / "ledger" / "transitions.jsonl").open("a") as handle:
                handle.write(json.dumps({"at_ns": time.time_ns(), "cell_id": state["cell_id"], "from": expected, "to": target, "reason": reason}, sort_keys=True) + "\n")

    selected_cells = cells if cells is not None else manifest["cells"]
    if retry_failed_infrastructure:
        for cell in selected_cells:
            cell_dir = run_dir / "cells" / cell["cell_id"]
            state = json.loads((cell_dir / "state.json").read_text())
            eligible, reason = infrastructure_retry_evidence(cell_dir, state)
            if not eligible:
                raise ValueError(
                    f"unsafe infrastructure retry for {cell['cell_id']}: {reason}"
                )

    async def one(cell: dict) -> dict:
        nonlocal active_cells, max_active_cells
        cell_dir = run_dir / "cells" / cell["cell_id"]
        initial_state = json.loads((cell_dir / "state.json").read_text())
        if not cell["runnable"]:
            return {"cell_id": cell["cell_id"], "status": "blocked", "reason": cell["status_reason"], "usage_event_count": 0}
        if not search_upstream:
            if not retry_failed_infrastructure:
                await transition(cell_dir, "pending", "blocked", f"missing_env:{search_env}")
            return {"cell_id": cell["cell_id"], "status": "blocked", "reason": f"missing_env:{search_env}", "usage_event_count": 0}
        credential_env = credential_contract["env"]
        if not env_base.get(credential_env):
            if not retry_failed_infrastructure:
                await transition(cell_dir, "pending", "blocked", f"missing_env:{credential_env}")
            return {"cell_id": cell["cell_id"], "status": "blocked", "reason": f"missing_env:{credential_env}", "usage_event_count": 0}
        route = route_by_id[cell["model_id"]]
        if retry_failed_infrastructure:
            await transition(
                cell_dir,
                "failed",
                "retry_ready",
                "authorized_attested_harness_infrastructure_retry",
            )
            ready_status = "retry_ready"
        else:
            await transition(cell_dir, "pending", "ready")
            ready_status = "ready"
        async with lanes[cell["model_id"]], global_gate:
            await transition(cell_dir, ready_status, "running")
            active[cell["model_id"]] += 1
            max_active[cell["model_id"]] = max(max_active[cell["model_id"]], active[cell["model_id"]])
            active_cells += 1
            max_active_cells = max(max_active_cells, active_cells)
            try:
                retries = 0
                prior_attempt_count = int(initial_state.get("attempt_count") or 0)
                total_usage = int(initial_state.get("usage_event_count") or 0)
                cell_seal_path = cell_dir / "seal.json"
                prior_cell_seal = (
                    json.loads(cell_seal_path.read_text())
                    if cell_seal_path.is_file()
                    else {}
                )
                attempt_seals = list(prior_cell_seal.get("attempt_seals") or [])
                while True:
                    attempt_index = prior_attempt_count + retries + 1
                    attempt = cell_dir / f"attempt-{attempt_index}"
                    attempt.mkdir(exist_ok=False)
                    heartbeat = attempt / "heartbeat"
                    heartbeat.touch()
                    values = {
                        "task_json": task["path"], "task_json_sha256": task["sha256"], "question_sha256": task["question_sha256"],
                        "task_id": manifest["task_id"], "harness_id": cell["harness_id"], "request_name": cell["model_request_name"],
                    }
                    command = [part.format_map(values) for part in command_template]
                    env = dict(env_base)
                    path_prefix = str(runtime.get("path_prefix") or "").strip()
                    if path_prefix:
                        env["PATH"] = path_prefix + os.pathsep + env.get("PATH", "")
                    for key, value in (
                        runtime.get("local_only_harness_environment") or {}
                    ).items():
                        env[str(key)] = str(value)
                    env.update({
                        "DRA_CELL_ID": cell["cell_id"], "DRA_MATRIX_RUN_ID": json.loads((run_dir / "run.json").read_text())["run_id"],
                        "DRA_PROGRESS_HEARTBEAT": str(heartbeat), "DEEP_RUN_OUT_DIR": str(attempt),
                        "DRA_BM25_SEMAPHORE_DIR": str(bm25_dir), "DRA_BM25_GATE_LEDGER": str(run_dir / "ledger" / "bm25_gate.jsonl"),
                        "DRA_BM25_MAX_IN_FLIGHT": str(manifest["concurrency"]["bm25_requests"]), "DRA_SEARCH_TIMEOUT_S": str(manifest["timeouts_seconds"]["search"]),
                        "DRA_SEARCH_UPSTREAM_URL": search_upstream, "DRA_LLM_UPSTREAM_URL": route["upstream_url"],
                        "DRA_TASK_SOURCE_CENSUS_SHA256": manifest["source_package"]["task_source_census"]["sha256"],
                        "DRA_CREDENTIAL_ENV_NAME": credential_env, "DRA_CREDENTIAL_HEADER": credential_contract["header"],
                        "DRA_CREDENTIAL_SCHEME": credential_contract["scheme"],
                        "DRA_UPSTREAM_REQUEST_MODEL": route["request_name"],
                        "DRA_EXPECTED_MODEL_IDENTITY": route["expected_actual_identity"],
                        "DRA_ADAMS_PLATFORM_USER": credential_contract["platform_user"],
                        "DRA_ADAMS_BUSINESS": credential_contract["business"],
                    })
                    with (attempt / "stdout.log").open("wb") as stdout, (attempt / "stderr.log").open("wb") as stderr:
                        proc = await asyncio.create_subprocess_exec(*command, cwd=str(ROOT), env=env, stdout=stdout, stderr=stderr)
                        code, stalled = await _watch(proc, heartbeat, timeout)
                    status, reason = ("stalled", "heartbeat_watchdog") if stalled else (("failed", f"exit_{code}") if code else ("success", None))
                    identity_path, usage_path = attempt / "identity.json", attempt / "gateway_usage.jsonl"
                    identity = json.loads(identity_path.read_text()) if identity_path.exists() else {}
                    if status == "success" and not identity.get("identity_consistent"):
                        status, reason = "failed", "identity_cross_check_failed"
                    usage_rows = [json.loads(line) for line in usage_path.read_text().splitlines() if line.strip()] if usage_path.exists() else []
                    for row in usage_rows:
                        if row.get("cell_id") != cell["cell_id"] or (row.get("matrix_attribution") or {}).get("cell_id") != cell["cell_id"]:
                            status, reason = "failed", "usage_attribution_failed"
                    if status == "success":
                        required_nonempty = [
                            attempt / "meta.json", attempt / "gateway_usage.jsonl",
                            attempt / "identity.json", attempt / "observability.json",
                            attempt / "report_provenance.json", attempt / "task_binding.json",
                        ]
                        missing = [
                            path.name for path in required_nonempty
                            if not path.is_file() or path.stat().st_size == 0
                        ]
                        if not (attempt / "report.md").is_file():
                            missing.append("report.md")
                        if missing:
                            status, reason = "failed", "missing_or_empty_required_artifacts:" + ",".join(missing)
                    if status == "success" and not usage_rows:
                        status, reason = "failed", "missing_gateway_usage"
                    if status == "success":
                        observability = json.loads((attempt / "observability.json").read_text())
                        provenance = json.loads((attempt / "report_provenance.json").read_text())
                        evidence_dir = attempt / "search_evidence"
                        evidence_files = list(evidence_dir.glob("*.jsonl")) if evidence_dir.is_dir() else []
                        evidence_rows = []
                        for evidence_file in evidence_files:
                            evidence_rows.extend(json.loads(line) for line in evidence_file.read_text().splitlines() if line.strip())
                        search_count = sum(row.get("kind") == "search" for row in evidence_rows)
                        fetch_count = sum(row.get("kind") == "fetch" for row in evidence_rows)
                        if not (
                            observability.get("recorder_initialized") is True
                            and observability.get("capture_bracket_valid") is True
                            and observability.get("capture_healthy") is True
                            and observability.get("search_call_count") == search_count
                            and observability.get("fetch_call_count") == fetch_count
                        ):
                            status, reason = "failed", "evidence_recorder_health_failed"
                        elif not provenance.get("model_output_attested"):
                            status, reason = "failed", "report_provenance_failed"
                    receipt_path = attempt / "failure_receipt.json"
                    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
                    if status == "failed" and isinstance(receipt, dict) and receipt.get("failure_class") == "rate_limited" and receipt.get("http_status") == 429:
                        reason = "rate_limited_http_429"
                    total_usage += len(usage_rows)
                    if usage_rows:
                        async with usage_lock:
                            with (run_dir / "usage" / "gateway_events.jsonl").open("a") as handle:
                                handle.write("".join(json.dumps(row, sort_keys=True) + "\n" for row in usage_rows))
                    exit_doc = {"cell_id": cell["cell_id"], "attempt": attempt_index, "status": status, "reason": reason, "exit_code": code, "usage_event_count": len(usage_rows)}
                    _atomic(attempt / "exit_status.json", exit_doc)
                    _atomic(attempt / "seal.json", {"files": [_seal(path) for path in sorted(attempt.iterdir()) if path.is_file() and path.name != "seal.json"]})
                    attempt_seals.append(_seal(attempt / "seal.json"))
                    if status == "failed" and retry_allowed(receipt, retries):
                        retries += 1
                        continue
                    break
                _atomic(cell_dir / "seal.json", {"cell_id": cell["cell_id"], "attempt_seals": attempt_seals, "terminal": exit_doc})
                await transition(cell_dir, "running", status, reason)
                state_path = cell_dir / "state.json"
                state = json.loads(state_path.read_text())
                state.update(attempt_count=attempt_index, usage_event_count=total_usage)
                _atomic(state_path, state)
                exit_doc["usage_event_count"] = total_usage
                return exit_doc
            finally:
                active[cell["model_id"]] -= 1
                active_cells -= 1

    result_by_cell: dict[str, dict] = {}

    async def isolated(cell: dict) -> dict:
        try:
            return await one(cell)
        except Exception as item:
            cell_dir = run_dir / "cells" / cell["cell_id"]
            state_path = cell_dir / "state.json"
            state = json.loads(state_path.read_text())
            prior = state["status"]
            state.update(status="failed", status_reason=f"isolated_dispatch_exception:{type(item).__name__}")
            _atomic(state_path, state)
            result = {"cell_id": cell["cell_id"], "status": "failed", "reason": state["status_reason"], "usage_event_count": 0}
            async with ledger_lock:
                with (run_dir / "ledger" / "transitions.jsonl").open("a") as handle:
                    handle.write(json.dumps({"at_ns": time.time_ns(), "cell_id": cell["cell_id"], "from": prior, "to": "failed", "reason": state["status_reason"]}, sort_keys=True) + "\n")
            return result

    ordered_cells = sorted(selected_cells, key=lambda row: row["ordinal"])
    if parallel:
        completed = await asyncio.gather(*(isolated(cell) for cell in ordered_cells))
        result_by_cell.update({row["cell_id"]: row for row in completed})
    else:
        for cell in ordered_cells:
            result_by_cell[cell["cell_id"]] = await isolated(cell)
    results = []
    for cell in manifest["cells"]:
        state = json.loads((run_dir / "cells" / cell["cell_id"] / "state.json").read_text())
        results.append({
            "cell_id": cell["cell_id"],
            "status": state["status"],
            "reason": state.get("status_reason"),
            "usage_event_count": state.get("usage_event_count", 0),
            "attempt_count": state.get("attempt_count", 0),
        })
    summary = {
        "cell_count": len(results),
        "processed_this_invocation": len(selected_cells),
        **{key: sum(x["status"] == key for x in results) for key in ("pending", "ready", "running", "success", "failed", "stalled", "blocked")},
        "execution_policy": (
            "PARALLEL_MODEL_LANES_ONE_CELL_PER_MODEL"
            if parallel
            else "STRICT_MANIFEST_ORDINAL_SERIAL"
        ),
        "global_cell_limit": global_limit,
        "max_active_per_model": dict(max_active),
        "max_active_cells": max_active_cells,
        "usage_event_count": sum(x.get("usage_event_count", 0) for x in results),
        "results": results,
    }
    _atomic(run_dir / "dispatch_summary.json", summary)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Explicit frozen manifest; required by the Cross-5 supervisor.",
    )
    ap.add_argument("--runs-root", type=Path, default=ROOT / "runs")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Continue an existing SHA-bound run directory without reinitializing it.",
    )
    ap.add_argument(
        "--max-cells",
        type=int,
        default=None,
        help="Process at most this many pending runnable cells in manifest order.",
    )
    ap.add_argument(
        "--cell-id",
        action="append",
        default=[],
        help="Run only this exact manifest cell ID; repeat for multiple cells.",
    )
    ap.add_argument(
        "--parallel",
        action="store_true",
        help="Run selected cells concurrently while retaining one cell per model lane.",
    )
    ap.add_argument(
        "--global-cells",
        type=int,
        default=None,
        help="Maximum concurrently active cells for this invocation.",
    )
    ap.add_argument(
        "--retry-failed-infrastructure",
        action="store_true",
        help=(
            "Retry only explicitly named failed cells whose latest attempt is "
            "an attested internal harness error stub. Creates a new attempt and "
            "never retries a successful capability result."
        ),
    )
    args = ap.parse_args()
    manifest = _load_manifest(args.manifest)
    runtime = json.loads((ROOT / "config" / "runtime.contract.json").read_text())
    routes = json.loads((ROOT / "config" / "model_routes.json").read_text())
    if args.max_cells is not None and args.max_cells <= 0:
        ap.error("--max-cells must be positive")
    if args.global_cells is not None and args.global_cells <= 0:
        ap.error("--global-cells must be positive")
    if len(args.cell_id) != len(set(args.cell_id)):
        ap.error("--cell-id values must be unique")
    if args.retry_failed_infrastructure and (
        not args.resume or not args.execute or not args.cell_id
    ):
        ap.error(
            "--retry-failed-infrastructure requires --resume, --execute, and "
            "at least one explicit --cell-id"
        )
    manifest_cell_ids = {cell["cell_id"] for cell in manifest["cells"]}
    unknown_cell_ids = sorted(set(args.cell_id) - manifest_cell_ids)
    if unknown_cell_ids:
        ap.error("unknown --cell-id value(s): " + ",".join(unknown_cell_ids))
    if args.execute:
        from preflight import blockers
        issues = blockers(manifest, runtime, routes)
        if issues:
            raise SystemExit("BLOCKED_DEPLOYMENT_PREFLIGHT: " + ";".join(issues))
    run_dir = args.runs_root / args.run_id
    if args.resume:
        if not run_dir.is_dir() or not (run_dir / "run.json").is_file():
            raise SystemExit("BLOCKED_RESUME_RUN_NOT_FOUND")
        header = json.loads((run_dir / "run.json").read_text())
        if (
            header.get("run_id") != args.run_id
            or header.get("matrix_id") != manifest["matrix_id"]
            or header.get("task_id") != manifest["task_id"]
            or header.get("formal_eligible") is not False
        ):
            raise SystemExit("BLOCKED_RESUME_BINDING_MISMATCH")
    else:
        initialize(run_dir, args.run_id, manifest, runtime)
    if not args.execute:
        print(json.dumps({"run_dir": str(run_dir), "mode": "EXPERIMENTAL_ENABLED", "model_requests": 0, "blocked": 6}, sort_keys=True))
        return 0
    pending = []
    requested_cell_ids = set(args.cell_id)
    for cell in sorted(manifest["cells"], key=lambda row: row["ordinal"]):
        if requested_cell_ids and cell["cell_id"] not in requested_cell_ids:
            continue
        state = json.loads((run_dir / "cells" / cell["cell_id"] / "state.json").read_text())
        if args.retry_failed_infrastructure:
            if state["status"] != "failed":
                raise SystemExit(
                    "BLOCKED_INFRASTRUCTURE_RETRY_CELL_NOT_FAILED:"
                    + cell["cell_id"]
                )
            eligible, reason = infrastructure_retry_evidence(
                run_dir / "cells" / cell["cell_id"], state
            )
            if not eligible:
                raise SystemExit(
                    "BLOCKED_UNSAFE_INFRASTRUCTURE_RETRY:"
                    + cell["cell_id"]
                    + ":"
                    + reason
                )
            pending.append(cell)
        elif state["status"] == "pending":
            pending.append(cell)
    selected = pending[: args.max_cells] if args.max_cells is not None else pending
    invocation = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requested_cell_ids": args.cell_id,
        "selected_cell_ids": [cell["cell_id"] for cell in selected],
        "parallel": args.parallel,
        "retry_failed_infrastructure": args.retry_failed_infrastructure,
        "global_cells": (
            args.global_cells
            if args.global_cells is not None
            else manifest["concurrency"]["global_cells"]
        ),
    }
    invocation_dir = run_dir / "invocations"
    invocation_dir.mkdir(exist_ok=True)
    invocation_path = invocation_dir / f"{time.time_ns()}.json"
    _atomic(invocation_path, invocation, exclusive=True)
    summary = asyncio.run(
        dispatch(
            manifest,
            runtime,
            routes,
            run_dir,
            cells=selected,
            parallel=args.parallel,
            global_cells=args.global_cells,
            retry_failed_infrastructure=args.retry_failed_infrastructure,
        )
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
