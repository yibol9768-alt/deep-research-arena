#!/usr/bin/env python3
"""Persistently gate W1M, then build and audit Wfull in sequence.

The supervisor never edits a completed view and never promotes on a failed
gate.  It is intended to run in a detached session while the independently
started W1M compiler is active.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence
from urllib.request import urlopen


SCHEMA = "dra_e2_ladder_supervisor_v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    payload = json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Supervisor:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.state_path = args.state_dir / "ladder-state.json"
        self.events: list[dict[str, Any]] = []
        self.state: dict[str, Any] = {
            "schema": SCHEMA,
            "started_at": utc_now(),
            "updated_at": utc_now(),
            "status": "running",
            "phase": "initializing",
            "events": self.events,
            "inputs": {
                "code_root": str(args.code_root),
                "auditor_root": str(args.auditor_root),
                "zim": str(args.zim),
                "snapshot_id": args.snapshot_id,
                "w1m_dir": str(args.w1m_dir),
                "wfull_dir": str(args.wfull_dir),
            },
        }
        self.save()

    def save(self) -> None:
        self.state["updated_at"] = utc_now()
        atomic_write_json(self.state_path, self.state)

    def mark(self, phase: str, **detail: Any) -> None:
        event = {"at": utc_now(), "phase": phase, **detail}
        self.events.append(event)
        self.state["phase"] = phase
        self.save()
        print(json.dumps(event, ensure_ascii=False), flush=True)

    def run(
        self,
        name: str,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
    ) -> None:
        log_path = self.args.state_dir / f"{name}.log"
        self.mark(
            f"running:{name}",
            command=list(command),
            log=str(log_path),
        )
        with log_path.open("ab") as log:
            log.write(
                (f"\n[{utc_now()}] command=" + json.dumps(list(command))
                 + "\n").encode("utf-8")
            )
            log.flush()
            result = subprocess.run(
                list(command),
                cwd=cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        self.mark(f"finished:{name}", exit_code=result.returncode)
        if result.returncode != 0:
            raise RuntimeError(
                f"{name} failed with exit code {result.returncode}; "
                f"see {log_path}"
            )

    def wait_for_existing_build(self, build_dir: Path) -> None:
        self.mark("waiting_for_w1m")
        while True:
            manifest = build_dir / "build-manifest.json"
            failure = build_dir / "failure.json"
            if manifest.is_file():
                self.mark("w1m_manifest_observed")
                return
            if failure.is_file():
                raise RuntimeError(
                    f"W1M compiler produced failure artifact: {failure}"
                )
            time.sleep(self.args.poll_seconds)

    def compiler_command(
        self,
        *,
        view: str,
        out: Path,
        resume: bool,
    ) -> list[str]:
        command = [
            sys.executable,
            str(self.args.code_root / "scripts/compile_e2_wikimedia_backbone.py"),
            "--zim", str(self.args.zim),
            "--out", str(out),
            "--snapshot-id", self.args.snapshot_id,
            "--view", view,
            "--checkpoint-every-scanned", "250000",
            "--checkpoint-every-compiled", "10000",
            "--progress-every", "500000",
            "--curve-every-checkpoints", "5",
            "--roundtrip-sample", "100",
        ]
        if resume:
            command.append("--resume")
        return command

    def validate_completed_view(self, view: str, out: Path) -> None:
        self.run(
            f"{view}-compiler-resume-validation",
            self.compiler_command(view=view, out=out, resume=True),
            cwd=self.args.code_root,
        )

    def ensure_view_built(self, view: str, out: Path) -> None:
        manifest = out / "build-manifest.json"
        checkpoint = out / "checkpoint.json"
        database = out / "world-index.sqlite"
        if manifest.is_file():
            self.validate_completed_view(view, out)
            return
        if checkpoint.is_file() and database.is_file():
            resume = True
        elif out.exists() and any(out.iterdir()):
            raise RuntimeError(
                f"refusing ambiguous non-empty build directory: {out}"
            )
        else:
            resume = False
        self.run(
            f"{view}-compiler",
            self.compiler_command(view=view, out=out, resume=resume),
            cwd=self.args.code_root,
        )

    def ensure_identity_audit(self, view: str, path: Path) -> None:
        if path.is_file():
            report = load_json(path)
            if (
                report.get("passed") is True
                and report.get("view", {}).get("view_id") == view
            ):
                self.mark(f"reused:{view}-url-identity", path=str(path))
                return
        self.run(
            f"{view}-url-identity",
            [
                sys.executable,
                str(self.args.code_root / "scripts/audit_e2_url_identity.py"),
                "--zim", str(self.args.zim),
                "--view", view,
                "--snapshot-id", self.args.snapshot_id,
                "--max-examples", "20",
                "--progress-every", "1000000",
                "--out", str(path),
            ],
            cwd=self.args.code_root,
        )

    def run_http_audit(self, view: str, build_dir: Path) -> Path:
        server_log_path = self.args.state_dir / f"{view}-http-server.log"
        server_log = server_log_path.open("ab")
        server = subprocess.Popen(
            [
                sys.executable,
                str(self.args.code_root / "scripts/serve_e1_world_shard.py"),
                "--db", str(build_dir / "world-index.sqlite"),
                "--host", "127.0.0.1",
                "--port", str(self.args.http_port),
            ],
            cwd=self.args.code_root,
            stdout=server_log,
            stderr=subprocess.STDOUT,
        )
        try:
            health = f"http://127.0.0.1:{self.args.http_port}/health"
            deadline = time.monotonic() + 60
            while True:
                if server.poll() is not None:
                    raise RuntimeError(
                        f"HTTP audit server exited; see {server_log_path}"
                    )
                try:
                    with urlopen(health, timeout=3) as response:
                        if int(response.status) == 200:
                            break
                except Exception:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError("HTTP audit server readiness timeout")
                time.sleep(1)
            output = build_dir / "http-audit.json"
            self.run(
                f"{view}-http-audit",
                [
                    sys.executable,
                    str(self.args.code_root / "scripts/audit_e1_http_surface.py"),
                    "--db", str(build_dir / "world-index.sqlite"),
                    "--base-url", f"http://127.0.0.1:{self.args.http_port}",
                    "--per-pack", "100",
                    "--min-search-top20-rate", "0.90",
                    "--out", str(output),
                ],
                cwd=self.args.code_root,
            )
            return output
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=15)
            server_log.close()

    def audit_view(self, view: str, build_dir: Path) -> dict[str, Path]:
        canonical = build_dir / "canonical-structure-audit.json"
        self.run(
            f"{view}-canonical-audit",
            [
                sys.executable,
                str(self.args.code_root / "scripts/audit_e1_canonical_structures.py"),
                "--build-dir", str(build_dir),
                "--out", str(canonical),
                "--progress-every", (
                    "100000" if view == "w1m" else "1000000"
                ),
            ],
            cwd=self.args.code_root,
        )
        native = build_dir / "native-route-audit.json"
        self.run(
            f"{view}-native-route-audit",
            [
                sys.executable,
                str(self.args.auditor_root / "audit_e2_native_routes.py"),
                "--db", str(build_dir / "world-index.sqlite"),
                "--base-url", self.args.kiwix_base_url,
                "--per-type", "100",
                "--edge-identity-limit", "1000",
                "--out", str(native),
            ],
        )
        http = self.run_http_audit(view, build_dir)
        return {"canonical": canonical, "native": native, "http": http}

    def promote_w1m(
        self,
        audits: Mapping[str, Path],
    ) -> Path:
        disk = shutil.disk_usage(self.args.w1m_dir).free
        memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        output = self.args.w1m_dir / "promotion-to-wfull.json"
        self.run(
            "w1m-promotion-to-wfull",
            [
                sys.executable,
                str(self.args.auditor_root / "assess_e2_promotion.py"),
                "--build-dir", str(self.args.w1m_dir),
                "--canonical-audit", str(audits["canonical"]),
                "--http-audit", str(audits["http"]),
                "--native-audit", str(audits["native"]),
                "--identity-audit", str(self.args.w1m_identity_audit),
                "--next-view", "wfull",
                "--available-disk-bytes", str(disk),
                "--total-memory-bytes", str(memory),
                "--max-runtime-hours", str(self.args.max_full_hours),
                "--out", str(output),
            ],
        )
        if load_json(output).get("promote_next_view") is not True:
            raise RuntimeError("W1M promotion report did not approve Wfull")
        return output

    def write_wfull_candidate_certificate(
        self,
        audits: Mapping[str, Path],
    ) -> Path:
        build_dir = self.args.wfull_dir
        manifest = load_json(build_dir / "build-manifest.json")
        quality = load_json(build_dir / "quality-report.json")
        identity = load_json(self.args.wfull_identity_audit)
        canonical = load_json(audits["canonical"])
        native = load_json(audits["native"])
        http = load_json(audits["http"])
        db_path = build_dir / "world-index.sqlite"
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            integrity = str(
                connection.execute("PRAGMA integrity_check").fetchone()[0]
            )
            documents = int(connection.execute(
                "SELECT COUNT(*) FROM documents"
            ).fetchone()[0])
            fts_rows = int(connection.execute(
                "SELECT COUNT(*) FROM search_fts"
            ).fetchone()[0])
        finally:
            connection.close()
        actual_hash = file_sha256(db_path)
        checks = {
            "compiler_quality_pass": (
                manifest.get("source_and_build_gates_pass") is True
                and quality.get("passed") is True
            ),
            "full_source_scan": manifest.get("full_source_scan") is True,
            "full_backbone_candidate": (
                manifest.get("full_backbone_candidate") is True
            ),
            "canonical_audit_pass": canonical.get("passed") is True,
            "native_route_audit_pass": native.get("passed") is True,
            "http_audit_pass": http.get("passed") is True,
            "url_identity_audit_pass": (
                identity.get("passed") is True
                and int(identity.get("selected") or -1) == documents
            ),
            "sqlite_hash_valid": actual_hash == manifest.get("sqlite_sha256"),
            "sqlite_integrity_ok": integrity == "ok",
            "database_census_consistent": (
                documents == int(manifest["census"]["documents"])
                and fts_rows == documents
            ),
            "task_blind": (
                manifest.get("task_conditioned") is False
                and manifest.get("task_or_witness_inputs") == []
            ),
            "no_failure_artifact": not (build_dir / "failure.json").exists(),
            "component_remains_formally_ineligible": (
                manifest.get("formal_eligible") is False
            ),
        }
        report = {
            "schema": "dra_e2_wfull_candidate_certificate_v1",
            "created_at": utc_now(),
            "logical_build_id": manifest.get("logical_build_id"),
            "pipeline_contract_id": manifest.get("pipeline_contract_id"),
            "sqlite_sha256": actual_hash,
            "documents": documents,
            "checks": checks,
            "structural_backbone_candidate_passed": all(checks.values()),
            "formal_eligible": False,
            "formal_eligibility_note": (
                "Wikidata alignment/statistics and the external E2 stage "
                "certificate remain separate required work."
            ),
        }
        output = build_dir / "wfull-candidate-certificate.json"
        atomic_write_json(output, report)
        if report["structural_backbone_candidate_passed"] is not True:
            raise RuntimeError("Wfull candidate certificate failed")
        return output

    def execute(self) -> None:
        self.wait_for_existing_build(self.args.w1m_dir)
        self.validate_completed_view("w1m", self.args.w1m_dir)
        self.ensure_identity_audit("w1m", self.args.w1m_identity_audit)
        w1m_audits = self.audit_view("w1m", self.args.w1m_dir)
        promotion = self.promote_w1m(w1m_audits)
        self.state["w1m_promotion"] = str(promotion)
        self.save()

        self.ensure_identity_audit("wfull", self.args.wfull_identity_audit)
        self.ensure_view_built("wfull", self.args.wfull_dir)
        self.validate_completed_view("wfull", self.args.wfull_dir)
        wfull_audits = self.audit_view("wfull", self.args.wfull_dir)
        certificate = self.write_wfull_candidate_certificate(wfull_audits)
        self.state.update({
            "status": "complete",
            "phase": "complete",
            "completed_at": utc_now(),
            "wfull_candidate_certificate": str(certificate),
        })
        self.save()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--code-root", type=Path, required=True)
    parser.add_argument("--auditor-root", type=Path, required=True)
    parser.add_argument("--zim", type=Path, required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--w1m-dir", type=Path, required=True)
    parser.add_argument("--w1m-identity-audit", type=Path, required=True)
    parser.add_argument("--wfull-dir", type=Path, required=True)
    parser.add_argument("--wfull-identity-audit", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument(
        "--kiwix-base-url", default="http://127.0.0.1:8090"
    )
    parser.add_argument("--http-port", type=int, default=18094)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--max-full-hours", type=float, default=336.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for name in (
        "code_root", "auditor_root", "zim", "w1m_dir",
        "w1m_identity_audit",
    ):
        if not Path(getattr(args, name)).exists():
            raise SystemExit(f"missing --{name.replace('_', '-')}")
    if args.poll_seconds <= 0:
        raise SystemExit("--poll-seconds must be positive")
    if not 1 <= args.http_port <= 65535:
        raise SystemExit("--http-port must be in [1,65535]")
    if args.max_full_hours <= 0:
        raise SystemExit("--max-full-hours must be positive")
    args.state_dir.mkdir(parents=True, exist_ok=True)

    supervisor = Supervisor(args)
    try:
        supervisor.execute()
    except BaseException as exc:
        supervisor.state.update({
            "status": "failed",
            "phase": "failed",
            "failed_at": utc_now(),
            "error": repr(exc),
        })
        supervisor.save()
        print(repr(exc), file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
