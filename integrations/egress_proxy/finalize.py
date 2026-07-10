"""Privileged finalization for recording-proxy evidence.

The framework worker is deliberately unable to read or write either recorder's
evidence directory.  Finalization therefore runs in the root-owned egress
process: it validates the proxy bracket, copies content-addressed bodies, and
appends only fetch/block records to the still-open shim bracket.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def merge_egress_evidence(
    run_id: str,
    *,
    egress_dir: Path,
    unified_dir: Path,
) -> dict[str, object]:
    """Merge one closed egress stream into one open canonical shim stream.

    Start/end marks stay recorder-local.  This preserves the canonical
    evidence invariant of exactly one start and one end while making the page
    bytes observed by the egress door available to the scorer.
    """
    if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
        raise RuntimeError("unsafe or empty run_id for egress finalization")

    source = egress_dir / f"{run_id}.jsonl"
    target = unified_dir / f"{run_id}.jsonl"
    if not source.is_file():
        raise RuntimeError(f"egress evidence log missing: {source}")
    if not target.is_file():
        raise RuntimeError(f"shim evidence log missing before merge: {target}")

    records: list[dict] = []
    starts = ends = 0
    for lineno, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"malformed egress evidence {source}:{lineno}: {exc}"
            ) from exc
        if not isinstance(rec, dict) or rec.get("run_id") != run_id:
            raise RuntimeError(
                f"egress evidence owner mismatch at {source}:{lineno}"
            )
        if rec.get("kind") == "mark":
            starts += int(rec.get("phase") == "start")
            ends += int(rec.get("phase") == "end")
            continue
        if rec.get("kind") not in {"fetch", "block"}:
            raise RuntimeError(
                f"unexpected egress record kind {rec.get('kind')!r}"
            )
        rec["recorder"] = "egress"
        records.append(rec)
    if starts != 1 or ends != 1:
        raise RuntimeError(
            f"egress evidence bracket invalid: starts={starts} ends={ends}"
        )

    target_records: list[dict] = []
    for lineno, raw in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"malformed shim evidence {target}:{lineno}: {exc}"
            ) from exc
        if not isinstance(rec, dict) or rec.get("run_id") != run_id:
            raise RuntimeError(f"shim evidence owner mismatch at {target}:{lineno}")
        target_records.append(rec)
    if any(
        rec.get("kind") == "mark" and rec.get("phase") == "end"
        for rec in target_records
    ):
        raise RuntimeError("shim evidence closed before egress merge")

    existing = [rec for rec in target_records if rec.get("recorder") == "egress"]
    if existing:
        if existing != records:
            raise RuntimeError("canonical stream contains a conflicting egress merge")
        return {
            "records": len(records),
            "blobs_copied": 0,
            "already_merged": True,
        }

    copied = 0
    source_blobs = egress_dir / "blobs"
    target_blobs = unified_dir / "blobs"
    for rec in records:
        digest = rec.get("body_sha256") if rec.get("kind") == "fetch" else None
        if not digest:
            continue
        src = source_blobs / str(digest)
        dst = target_blobs / str(digest)
        if not src.is_file():
            raise RuntimeError(f"egress blob missing: {src}")
        body = src.read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise RuntimeError(f"egress blob digest mismatch: {src}")
        target_blobs.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            tmp = dst.with_suffix(f".part.{os.getpid()}")
            tmp.write_bytes(body)
            tmp.replace(dst)
            copied += 1

    if records:
        payload = "".join(
            json.dumps(rec, ensure_ascii=False) + "\n" for rec in records
        ).encode("utf-8")
        fd = os.open(target, os.O_WRONLY | os.O_APPEND)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise RuntimeError("short append while merging egress evidence")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
    return {
        "records": len(records),
        "blobs_copied": copied,
        "already_merged": False,
    }
