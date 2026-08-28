#!/usr/bin/env python3
"""Own the two per-cell doors and normalize one unified-runner attempt."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from cell_ds_proxy import start_proxy as start_ds_proxy, stop_proxy as stop_ds_proxy
from cell_search_shim import start_proxy as start_search_proxy, stop_proxy as stop_search_proxy


def _actual_identity(meta: dict) -> str | None:
    identity = meta.get("model_identity") if isinstance(meta.get("model_identity"), dict) else {}
    # ``backbone`` is the runner's declared identity, not an observation.  It
    # must never be accepted as proof of the model that actually answered.
    return (
        identity.get("actual_model_identity")
        or identity.get("actual")
        or identity.get("model")
    )


def _monitor(stop: threading.Event, heartbeat: Path, paths: list[Path]) -> None:
    prior = None
    while not stop.wait(0.2):
        current = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in paths)
        if current != prior:
            heartbeat.touch()
            prior = current


def normalized_failure_receipt(code: int, usage_rows: list[dict]) -> dict:
    last = usage_rows[-1] if usage_rows else {}
    status = last.get("http_status")
    if status is None and last.get("transport_error_type"):
        failure_class, exception_type = "transport", str(last["transport_error_type"])
    elif status in {500, 502, 503, 504}:
        failure_class, exception_type = "http", None
    elif status == 429:
        failure_class, exception_type = "rate_limited", None
    else:
        failure_class, exception_type = "task_failure", None
    return {
        "schema_version": "1.0.0", "source": "adapter_normalized_exception",
        "failure_class": failure_class, "http_status": status,
        "exception_type": exception_type, "gateway_event_id": last.get("event_id"),
        "runner_exit_code": code,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", required=True)
    ap.add_argument("--task-json", required=True)
    ap.add_argument("--task-json-sha256", required=True)
    ap.add_argument("--question-sha256", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--backbone", required=True)
    args = ap.parse_args()
    out = Path(os.environ["DEEP_RUN_OUT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw"
    raw.mkdir(exist_ok=False)
    search_evidence = out / "search_evidence"
    search_evidence.mkdir(exist_ok=False)
    usage = raw / "dsproxy_usage.jsonl"
    heartbeat = Path(os.environ["DRA_PROGRESS_HEARTBEAT"])
    heartbeat.touch()
    credential_env = os.environ["DRA_CREDENTIAL_ENV_NAME"]
    credential = os.environ.get(credential_env)
    if not credential:
        raise SystemExit(f"missing controlled credential env: {credential_env}")
    upstream_request_model = os.environ["DRA_UPSTREAM_REQUEST_MODEL"]
    declared_identity = os.environ["DRA_EXPECTED_MODEL_IDENTITY"]
    recorder_started_ns = time.time_ns()
    search = start_search_proxy(
        upstream=os.environ["DRA_SEARCH_UPSTREAM_URL"], cell_id=os.environ["DRA_CELL_ID"],
        evidence_dir=search_evidence, slot_dir=Path(os.environ["DRA_BM25_SEMAPHORE_DIR"]),
        slot_ledger=Path(os.environ["DRA_BM25_GATE_LEDGER"]),
        slot_count=int(os.environ.get("DRA_BM25_MAX_IN_FLIGHT", "4")),
        timeout=float(os.environ.get("DRA_SEARCH_TIMEOUT_S", "600")),
    )
    ds = start_ds_proxy(
        upstream_url=os.environ["DRA_LLM_UPSTREAM_URL"], credential=credential,
        credential_header=os.environ.get("DRA_CREDENTIAL_HEADER", "Authorization"),
        credential_scheme=os.environ.get("DRA_CREDENTIAL_SCHEME", "Bearer"),
        extra_headers={
            "Adams-Platform-User": os.environ["DRA_ADAMS_PLATFORM_USER"],
            "Adams-Business": os.environ["DRA_ADAMS_BUSINESS"],
        },
        cell_id=os.environ["DRA_CELL_ID"], harness_id=args.agent,
        run_id=os.environ["DRA_MATRIX_RUN_ID"],
        requested_model=upstream_request_model, expected_identity=declared_identity,
        usage_log=usage,
    )
    env = dict(os.environ)
    env.update({"DEEP_RUN_OUT_DIR": str(raw), "DSPROXY_USAGE_LOG": str(usage), "SHIM_URL": search[2], "SHIM_EVIDENCE_DIR": str(search_evidence), "DS_PROXY_URL": ds[2], "OPENAI_BASE_URL": ds[2], "OPENAI_API_BASE": ds[2], "OPENAI_API_KEY": "cell-proxy-managed"})
    binding_receipt = out / "task_binding.json"
    command = [
        sys.executable, str(Path(__file__).with_name("registry_bound_runner.py")),
        "--runner", args.runner, "--task-json", args.task_json,
        "--task-json-sha256", args.task_json_sha256, "--task-id", args.task,
        "--question-sha256", args.question_sha256, "--binding-receipt", str(binding_receipt), "--",
        "--agent", args.agent, "--task", args.task,
        "--backbone", declared_identity, "--strict-sandbox",
    ]
    watched = [usage, search_evidence, raw]
    stop = threading.Event()
    monitor = threading.Thread(target=_monitor, args=(stop, heartbeat, watched), daemon=True)
    monitor.start()
    try:
        completed = subprocess.run(command, env=env)
        code = completed.returncode
    finally:
        stop.set()
        monitor.join(timeout=1)
        stop_ds_proxy(ds[0], ds[1])
        stop_search_proxy(search[0], search[1])
        heartbeat.touch()
    recorder_ended_ns = time.time_ns()
    prefix = f"{args.agent}__{args.task}"
    reports = sorted(raw.glob(f"{prefix}*.md"))
    metas = sorted(raw.glob(f"{prefix}*.meta.json"))
    if reports:
        shutil.copy2(reports[-1], out / "report.md")
    if metas:
        shutil.copy2(metas[-1], out / "meta.json")
    if usage.exists():
        shutil.copy2(usage, out / "gateway_usage.jsonl")
    else:
        (out / "gateway_usage.jsonl").write_text("")
    meta = json.loads(metas[-1].read_text()) if metas else {}
    actual = _actual_identity(meta)
    usage_rows = [json.loads(line) for line in usage.read_text().splitlines() if line.strip()] if usage.exists() else []
    observed = {row.get("actual_model_identity") for row in usage_rows if row.get("actual_model_identity")}
    expected = declared_identity
    consistent = bool(observed) and observed == {expected} and actual in {None, expected}
    (out / "identity.json").write_text(json.dumps({
        "requested_model": args.backbone,
        "upstream_request_model": upstream_request_model,
        "runner_declared_identity": declared_identity,
        "expected_actual_identity": expected,
        "meta_actual_identity": actual, "raw_usage_actual_identities": sorted(observed),
        "identity_consistent": consistent,
    }, indent=2, sort_keys=True) + "\n")
    evidence_rows = []
    for path in search_evidence.glob("*.jsonl"):
        evidence_rows.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    kinds = {row.get("kind") for row in evidence_rows}
    search_count = sum(row.get("kind") == "search" for row in evidence_rows)
    fetch_count = sum(row.get("kind") == "fetch" for row in evidence_rows)
    capture_healthy = recorder_ended_ns >= recorder_started_ns
    (out / "observability.json").write_text(json.dumps({
        "schema_version": "2.0.0",
        "recorder_initialized": True,
        "capture_bracket_valid": capture_healthy,
        "capture_started_ns": recorder_started_ns,
        "capture_ended_ns": recorder_ended_ns,
        "capture_healthy": capture_healthy,
        "search_call_count": search_count,
        "fetch_call_count": fetch_count,
        "search": "observed" if search_count else "observed_zero_calls",
        "fetch": "observed" if fetch_count else "observed_zero_calls",
        "zero_tool_calls_attested": search_count == 0 and fetch_count == 0,
        "evidence_directory": "search_evidence",
    }, indent=2, sort_keys=True) + "\n")
    report_exists = (out / "report.md").is_file()
    meta_pass = meta.get("status") == "pass"
    (out / "report_provenance.json").write_text(json.dumps({
        "schema_version": "1.0.0",
        "model_output_attested": bool(
            code == 0 and report_exists and meta_pass and consistent and usage_rows
        ),
        "runner_exit_code": code,
        "runner_meta_status": meta.get("status"),
        "report_present": report_exists,
        "report_bytes": (out / "report.md").stat().st_size if report_exists else 0,
        "length_threshold_used": False,
        "url_count_threshold_used": False,
        "internal_error_stub": bool(meta.get("status") in {"fail", "infra_abort"}),
    }, indent=2, sort_keys=True) + "\n")
    if code:
        (out / "failure_receipt.json").write_text(json.dumps(
            normalized_failure_receipt(code, usage_rows), indent=2, sort_keys=True
        ) + "\n")
    return code if code else (0 if consistent else 7)


if __name__ == "__main__":
    raise SystemExit(main())
