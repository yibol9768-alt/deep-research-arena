#!/usr/bin/env python3
"""Capture a fail-closed, content-addressed source set for one v3 candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CAPTURE_PLAN_SCHEMA = "dra_v3_candidate_capture_plan_v1"
CAPTURE_MANIFEST_SCHEMA = "dra_v3_candidate_source_capture_v1"
CAPTURE_FILES_SCHEMA = "dra_v3_corpus_capture_files_v1"

_PLAN_KEYS = {
    "schema_version",
    "candidate_id",
    "corpus_snapshot",
    "run_id",
    "searches",
    "extracts",
    "source_identity",
    "metadata",
}
_SEARCH_KEYS = {
    "search_id",
    "query",
    "max_results",
    "include_domains",
    "required_urls",
}
_EXTRACT_KEYS = {
    "registry_id",
    "source_type",
    "url",
    "extract_depth",
}
_SOURCE_TYPES = {"magento", "postmill", "wikipedia"}
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")


class CandidateCaptureError(ValueError):
    """A capture plan or observed response violates the frozen-source contract."""


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidateCaptureError(f"{path}: expected an object")
    return dict(value)


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        raise CandidateCaptureError(
            f"{path}: schema mismatch; missing={missing}, unknown={unknown}"
        )


def _non_empty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CandidateCaptureError(f"{path}: expected a non-empty string")
    return value.strip()


def _safe_id(value: object, path: str) -> str:
    text = _non_empty_string(value, path)
    if not _SAFE_ID_RE.fullmatch(text):
        raise CandidateCaptureError(f"{path}: expected a safe lowercase identifier")
    return text


def _url(value: object, path: str) -> str:
    text = _non_empty_string(value, path)
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CandidateCaptureError(f"{path}: expected an absolute HTTP(S) URL")
    return text


def _string_list(value: object, path: str, *, urls: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise CandidateCaptureError(f"{path}: expected an array")
    items = [
        _url(item, f"{path}[{index}]")
        if urls
        else _non_empty_string(item, f"{path}[{index}]")
        for index, item in enumerate(value)
    ]
    if len(items) != len(set(items)):
        raise CandidateCaptureError(f"{path}: duplicate values are not allowed")
    return items


def validate_capture_plan(value: object) -> dict[str, Any]:
    """Validate and normalize an exact candidate capture plan."""
    plan = _object(value, "plan")
    _exact_keys(plan, _PLAN_KEYS, "plan")
    if plan["schema_version"] != CAPTURE_PLAN_SCHEMA:
        raise CandidateCaptureError(
            f"plan.schema_version: expected {CAPTURE_PLAN_SCHEMA!r}"
        )
    candidate_id = _safe_id(plan["candidate_id"], "plan.candidate_id")
    corpus_snapshot = _safe_id(plan["corpus_snapshot"], "plan.corpus_snapshot")
    run_id = _safe_id(plan["run_id"], "plan.run_id")

    raw_searches = plan["searches"]
    if not isinstance(raw_searches, list) or not raw_searches:
        raise CandidateCaptureError("plan.searches: expected a non-empty array")
    searches: list[dict[str, Any]] = []
    search_ids: set[str] = set()
    for index, raw_search in enumerate(raw_searches):
        path = f"plan.searches[{index}]"
        search = _object(raw_search, path)
        _exact_keys(search, _SEARCH_KEYS, path)
        search_id = _safe_id(search["search_id"], f"{path}.search_id")
        if search_id in search_ids:
            raise CandidateCaptureError(f"{path}.search_id: duplicate {search_id!r}")
        search_ids.add(search_id)
        max_results = search["max_results"]
        if type(max_results) is not int or not 1 <= max_results <= 100:
            raise CandidateCaptureError(f"{path}.max_results: expected 1..100")
        searches.append(
            {
                "search_id": search_id,
                "query": _non_empty_string(search["query"], f"{path}.query"),
                "max_results": max_results,
                "include_domains": _string_list(
                    search["include_domains"], f"{path}.include_domains"
                ),
                "required_urls": _string_list(
                    search["required_urls"], f"{path}.required_urls", urls=True
                ),
            }
        )

    raw_extracts = plan["extracts"]
    if not isinstance(raw_extracts, list) or not raw_extracts:
        raise CandidateCaptureError("plan.extracts: expected a non-empty array")
    extracts: list[dict[str, Any]] = []
    registry_ids: set[str] = set()
    extract_urls: set[str] = set()
    for index, raw_extract in enumerate(raw_extracts):
        path = f"plan.extracts[{index}]"
        extract = _object(raw_extract, path)
        _exact_keys(extract, _EXTRACT_KEYS, path)
        registry_id = _safe_id(extract["registry_id"], f"{path}.registry_id")
        source_type = _non_empty_string(extract["source_type"], f"{path}.source_type")
        source_url = _url(extract["url"], f"{path}.url")
        depth = extract["extract_depth"]
        if registry_id in registry_ids:
            raise CandidateCaptureError(f"{path}.registry_id: duplicate {registry_id!r}")
        if source_url in extract_urls:
            raise CandidateCaptureError(f"{path}.url: duplicate {source_url!r}")
        if source_type not in _SOURCE_TYPES:
            raise CandidateCaptureError(
                f"{path}.source_type: expected one of {sorted(_SOURCE_TYPES)}"
            )
        if depth not in {"basic", "advanced"}:
            raise CandidateCaptureError(
                f"{path}.extract_depth: expected 'basic' or 'advanced'"
            )
        registry_ids.add(registry_id)
        extract_urls.add(source_url)
        extracts.append(
            {
                "registry_id": registry_id,
                "source_type": source_type,
                "url": source_url,
                "extract_depth": depth,
            }
        )

    source_identity = _object(plan["source_identity"], "plan.source_identity")
    if not source_identity:
        raise CandidateCaptureError("plan.source_identity: must not be empty")
    for key, identity_value in source_identity.items():
        _non_empty_string(key, "plan.source_identity key")
        _non_empty_string(identity_value, f"plan.source_identity.{key}")
    metadata = _object(plan["metadata"], "plan.metadata")
    return {
        "schema_version": CAPTURE_PLAN_SCHEMA,
        "candidate_id": candidate_id,
        "corpus_snapshot": corpus_snapshot,
        "run_id": run_id,
        "searches": searches,
        "extracts": extracts,
        "source_identity": source_identity,
        "metadata": metadata,
    }


def load_capture_plan(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateCaptureError(f"cannot load capture plan: {exc}") from exc
    return validate_capture_plan(value)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json_bytes(value))


def _response_json(response: Any, path: str) -> dict[str, Any]:
    try:
        value = response.json()
    except Exception as exc:  # noqa: BLE001 - response diagnostics are wrapped
        raise CandidateCaptureError(f"{path}: response is not JSON") from exc
    if response.status_code != 200:
        raise CandidateCaptureError(
            f"{path}: HTTP {response.status_code}: {value!r}"
        )
    return _object(value, f"{path} response")


def _code_identity() -> dict[str, str]:
    files = {
        "app_py_sha256": ROOT / "integrations/search_shim/app.py",
        "backend_py_sha256": ROOT / "integrations/search_shim/backend.py",
    }
    return {key: _sha256(path.read_bytes()) for key, path in files.items()}


def _capture_with_client(
    plan: Mapping[str, Any],
    capture_dir: Path,
    client: TestClient,
) -> dict[str, Any]:
    run_id = str(plan["run_id"])
    mark_payload = {
        "run_id": run_id,
        "phase": "start",
        "lane": "corpus-inventory-v3",
        "task": plan["candidate_id"],
        "backbone": "deterministic-candidate-capture-v1",
        "fetch_observable": True,
    }
    mark_start = _response_json(client.post("/_mark", json=mark_payload), "/_mark start")
    _write_json(capture_dir / "mark_start.json", mark_start)
    started = True
    completed = False
    documents: list[dict[str, Any]] = []
    search_records: list[dict[str, Any]] = []
    discovery_failures: list[dict[str, Any]] = []
    try:
        for index, search in enumerate(plan["searches"], start=1):
            response = _response_json(
                client.post(
                    "/search",
                    json={
                        "query": search["query"],
                        "max_results": search["max_results"],
                        "include_domains": search["include_domains"],
                        "include_raw_content": False,
                    },
                ),
                f"/search {search['search_id']}",
            )
            result_urls = [
                str(item.get("url") or "")
                for item in response.get("results", [])
                if isinstance(item, Mapping)
            ]
            missing = sorted(set(search["required_urls"]) - set(result_urls))
            if missing:
                discovery_failures.append(
                    {
                        "search_id": search["search_id"],
                        "query": search["query"],
                        "missing_required_urls": missing,
                    }
                )
            relative_path = f"searches/{index:03d}-{search['search_id']}.json"
            _write_json(capture_dir / relative_path, response)
            search_records.append(
                {
                    "search_id": search["search_id"],
                    "query": search["query"],
                    "result_count": len(result_urls),
                    "response_path": relative_path,
                    "response_sha256": _sha256(_canonical_json_bytes(response)),
                    "required_urls": search["required_urls"],
                }
            )

        if discovery_failures:
            raise CandidateCaptureError(
                "capture discovery preflight failed; required URLs missing: "
                + json.dumps(
                    discovery_failures,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )

        for index, extract_spec in enumerate(plan["extracts"], start=1):
            response = _response_json(
                client.post(
                    "/extract",
                    json={
                        "urls": [extract_spec["url"]],
                        "extract_depth": extract_spec["extract_depth"],
                        "format": "text",
                        "include_images": False,
                    },
                ),
                f"/extract {extract_spec['registry_id']}",
            )
            failed = response.get("failed_results") or []
            results = response.get("results") or []
            if failed or not isinstance(results, list) or len(results) != 1:
                raise CandidateCaptureError(
                    f"extract {extract_spec['registry_id']!r}: expected one success, "
                    f"got results={len(results) if isinstance(results, list) else 'invalid'} "
                    f"failed={failed!r}"
                )
            result = _object(results[0], f"extract {extract_spec['registry_id']} result")
            if result.get("url") != extract_spec["url"]:
                raise CandidateCaptureError(
                    f"extract {extract_spec['registry_id']!r}: response URL mismatch"
                )
            raw_content = result.get("raw_content")
            if not isinstance(raw_content, str) or not raw_content.strip():
                raise CandidateCaptureError(
                    f"extract {extract_spec['registry_id']!r}: empty raw_content"
                )
            body = raw_content.encode("utf-8")
            body_sha256 = _sha256(body)
            blob = capture_dir / "blobs" / body_sha256
            if not blob.is_file() or blob.read_bytes() != body:
                raise CandidateCaptureError(
                    f"extract {extract_spec['registry_id']!r}: evidence blob missing or mismatched"
                )
            relative_path = f"extracts/{index:03d}-{extract_spec['registry_id']}.json"
            _write_json(capture_dir / relative_path, response)
            documents.append(
                {
                    "registry_id": extract_spec["registry_id"],
                    "source_type": extract_spec["source_type"],
                    "source_url": extract_spec["url"],
                    "extract_depth": extract_spec["extract_depth"],
                    "content_sha256": body_sha256,
                    "bytes": len(body),
                    "blob_path": f"blobs/{body_sha256}",
                    "response_path": relative_path,
                }
            )
        completed = True
    finally:
        if started:
            end_payload = {"run_id": run_id, "phase": "end"}
            try:
                mark_end = _response_json(
                    client.post("/_mark", json=end_payload), "/_mark end"
                )
                _write_json(capture_dir / "mark_end.json", mark_end)
            except Exception:
                if completed:
                    raise

    log_path = capture_dir / f"{run_id}.jsonl"
    if not log_path.is_file():
        raise CandidateCaptureError("capture evidence log was not written")
    observation_path = capture_dir / "observations_legacy.jsonl"
    log_path.replace(observation_path)
    observations = [
        json.loads(line)
        for line in observation_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    kinds = [str(record.get("kind") or "") for record in observations]
    phases = [
        record.get("phase")
        for record in observations
        if record.get("kind") == "mark"
    ]
    if phases != ["start", "end"]:
        raise CandidateCaptureError(f"capture bracket is incomplete: phases={phases!r}")
    if kinds.count("search") != len(plan["searches"]):
        raise CandidateCaptureError("observation search count does not match plan")
    if kinds.count("fetch") != len(plan["extracts"]):
        raise CandidateCaptureError("observation fetch count does not match plan")

    _write_json(capture_dir / "capture_plan.json", plan)
    _write_json(capture_dir / "documents.json", {"documents": documents})
    _write_json(capture_dir / "source_identity.json", plan["source_identity"])
    manifest = {
        "schema_version": CAPTURE_MANIFEST_SCHEMA,
        "status": "complete",
        "candidate_id": plan["candidate_id"],
        "corpus_snapshot": plan["corpus_snapshot"],
        "run_id": run_id,
        "captured_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "capture_plan_sha256": _sha256(_canonical_json_bytes(plan)),
        "extractor_identity": _code_identity(),
        "source_identity": plan["source_identity"],
        "metadata": plan["metadata"],
        "counts": {
            "searches": len(search_records),
            "documents": len(documents),
            "observation_records": len(observations),
            "fetches": kinds.count("fetch"),
        },
        "searches": search_records,
        "documents": documents,
        "observation_log_sha256": _sha256(observation_path.read_bytes()),
    }
    _write_json(capture_dir / "capture_manifest.json", manifest)
    return manifest


def _file_manifest(capture_dir: Path) -> dict[str, Any]:
    rows = []
    for path in sorted(capture_dir.rglob("*")):
        if not path.is_file() or path.name == "capture_files.json":
            continue
        data = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(capture_dir).as_posix(),
                "bytes": len(data),
                "sha256": _sha256(data),
            }
        )
    return {"schema": CAPTURE_FILES_SCHEMA, "files": rows}


def run_capture(
    plan_value: object,
    output_dir: str | Path,
    *,
    app_override: Any | None = None,
) -> dict[str, Any]:
    """Run one atomic capture. Existing output is never overwritten."""
    plan = validate_capture_plan(plan_value)
    output = Path(output_dir)
    if output.exists():
        raise CandidateCaptureError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.tmp.", dir=str(output.parent))
    )
    previous_env = {
        key: os.environ.get(key)
        for key in ("SHIM_EVIDENCE", "SHIM_EVIDENCE_DIR", "SHIM_MODE")
    }
    os.environ["SHIM_EVIDENCE"] = "1"
    os.environ["SHIM_EVIDENCE_DIR"] = str(staging)
    os.environ["SHIM_MODE"] = "strict"
    from integrations.search_shim import evidence
    from integrations.search_shim.app import app as default_app

    evidence.reset_for_tests()
    try:
        with TestClient(app_override or default_app) as client:
            manifest = _capture_with_client(plan, staging, client)
        _write_json(staging / "capture_files.json", _file_manifest(staging))
        staging.replace(output)
        return manifest
    finally:
        evidence.reset_for_tests()
        for key, old_value in previous_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value
        if staging.exists():
            shutil.rmtree(staging)


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateCaptureError(f"{label}: cannot read {path}: {exc}") from exc
    return _object(value, label)


def verify_capture(capture_dir: str | Path) -> dict[str, Any]:
    """Replay hashes, plan identity, document blobs, and the run bracket."""
    root = Path(capture_dir)
    if not root.is_dir():
        raise CandidateCaptureError(f"capture directory does not exist: {root}")
    files_path = root / "capture_files.json"
    files_doc = _load_json_object(files_path, "capture_files")
    _exact_keys(files_doc, {"schema", "files"}, "capture_files")
    if files_doc["schema"] != CAPTURE_FILES_SCHEMA:
        raise CandidateCaptureError("capture_files.schema: wrong schema")
    rows = files_doc["files"]
    if not isinstance(rows, list):
        raise CandidateCaptureError("capture_files.files: expected an array")
    declared_paths: set[str] = set()
    for index, raw_row in enumerate(rows):
        path = f"capture_files.files[{index}]"
        row = _object(raw_row, path)
        _exact_keys(row, {"path", "bytes", "sha256"}, path)
        relative_text = _non_empty_string(row["path"], f"{path}.path")
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise CandidateCaptureError(f"{path}.path: must stay within the capture")
        normalized = relative.as_posix()
        if normalized == "capture_files.json" or normalized in declared_paths:
            raise CandidateCaptureError(f"{path}.path: duplicate or self-reference")
        declared_paths.add(normalized)
        expected_bytes = row["bytes"]
        expected_sha = row["sha256"]
        if type(expected_bytes) is not int or expected_bytes < 0:
            raise CandidateCaptureError(f"{path}.bytes: expected a non-negative integer")
        if not isinstance(expected_sha, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_sha
        ):
            raise CandidateCaptureError(f"{path}.sha256: expected lowercase SHA-256")
        target = root / relative
        try:
            data = target.read_bytes()
        except OSError as exc:
            raise CandidateCaptureError(f"{path}.path: cannot read {target}") from exc
        if len(data) != expected_bytes or _sha256(data) != expected_sha:
            raise CandidateCaptureError(f"{path}: byte count or SHA-256 mismatch")
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "capture_files.json"
    }
    if actual_paths != declared_paths:
        raise CandidateCaptureError(
            "capture file set mismatch; "
            f"missing={sorted(declared_paths - actual_paths)}, "
            f"unknown={sorted(actual_paths - declared_paths)}"
        )

    plan = validate_capture_plan(
        _load_json_object(root / "capture_plan.json", "capture_plan")
    )
    manifest = _load_json_object(root / "capture_manifest.json", "capture_manifest")
    if manifest.get("schema_version") != CAPTURE_MANIFEST_SCHEMA:
        raise CandidateCaptureError("capture_manifest.schema_version: wrong schema")
    if manifest.get("status") != "complete":
        raise CandidateCaptureError("capture_manifest.status: capture is not complete")
    for field in ("candidate_id", "corpus_snapshot", "run_id", "source_identity"):
        if manifest.get(field) != plan[field]:
            raise CandidateCaptureError(
                f"capture_manifest.{field}: does not match capture_plan"
            )
    if manifest.get("capture_plan_sha256") != _sha256(_canonical_json_bytes(plan)):
        raise CandidateCaptureError("capture_manifest.capture_plan_sha256: mismatch")

    documents_doc = _load_json_object(root / "documents.json", "documents")
    _exact_keys(documents_doc, {"documents"}, "documents")
    documents = documents_doc["documents"]
    if not isinstance(documents, list) or documents != manifest.get("documents"):
        raise CandidateCaptureError("documents: does not match capture_manifest")
    if len(documents) != len(plan["extracts"]):
        raise CandidateCaptureError("documents: count does not match capture_plan")
    for index, (document, extract_spec) in enumerate(
        zip(documents, plan["extracts"])
    ):
        row = _object(document, f"documents[{index}]")
        for document_key, extract_key in (
            ("registry_id", "registry_id"),
            ("source_type", "source_type"),
            ("source_url", "url"),
            ("extract_depth", "extract_depth"),
        ):
            if row.get(document_key) != extract_spec[extract_key]:
                raise CandidateCaptureError(
                    f"documents[{index}].{document_key}: plan mismatch"
                )
        blob_path = root / str(row.get("blob_path") or "")
        body = blob_path.read_bytes()
        if row.get("bytes") != len(body) or row.get("content_sha256") != _sha256(body):
            raise CandidateCaptureError(f"documents[{index}]: blob mismatch")
        response_path = root / str(row.get("response_path") or "")
        response = _load_json_object(response_path, f"documents[{index}] response")
        results = response.get("results")
        if not isinstance(results, list) or len(results) != 1:
            raise CandidateCaptureError(f"documents[{index}] response: invalid results")
        result = _object(results[0], f"documents[{index}] response.results[0]")
        served = result.get("raw_content")
        if not isinstance(served, str) or served.encode("utf-8") != body:
            raise CandidateCaptureError(
                f"documents[{index}] response: served body does not match blob"
            )

    searches = manifest.get("searches")
    if not isinstance(searches, list) or len(searches) != len(plan["searches"]):
        raise CandidateCaptureError("capture_manifest.searches: count mismatch")
    for index, search in enumerate(searches):
        row = _object(search, f"capture_manifest.searches[{index}]")
        response_path = root / str(row.get("response_path") or "")
        if row.get("response_sha256") != _sha256(response_path.read_bytes()):
            raise CandidateCaptureError(
                f"capture_manifest.searches[{index}]: response hash mismatch"
            )

    observation_path = root / "observations_legacy.jsonl"
    observation_bytes = observation_path.read_bytes()
    if manifest.get("observation_log_sha256") != _sha256(observation_bytes):
        raise CandidateCaptureError("capture_manifest.observation_log_sha256: mismatch")
    try:
        observations = [
            json.loads(line)
            for line in observation_bytes.decode("utf-8").splitlines()
            if line.strip()
        ]
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateCaptureError("observations_legacy.jsonl: invalid JSONL") from exc
    if any(record.get("run_id") != plan["run_id"] for record in observations):
        raise CandidateCaptureError("observations: mixed or wrong run_id")
    phases = [
        record.get("phase")
        for record in observations
        if record.get("kind") == "mark"
    ]
    if phases != ["start", "end"]:
        raise CandidateCaptureError(f"observations: incomplete bracket {phases!r}")
    counts = manifest.get("counts") or {}
    if counts.get("searches") != sum(
        record.get("kind") == "search" for record in observations
    ):
        raise CandidateCaptureError("observations: search count mismatch")
    if counts.get("fetches") != sum(
        record.get("kind") == "fetch" for record in observations
    ):
        raise CandidateCaptureError("observations: fetch count mismatch")
    if counts.get("observation_records") != len(observations):
        raise CandidateCaptureError("observations: record count mismatch")

    return {
        "status": "verified",
        "candidate_id": plan["candidate_id"],
        "corpus_snapshot": plan["corpus_snapshot"],
        "run_id": plan["run_id"],
        "documents": len(documents),
        "searches": len(searches),
        "observation_records": len(observations),
        "capture_files_sha256": _sha256(files_path.read_bytes()),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--plan", type=Path)
    action.add_argument("--verify", type=Path)
    parser.add_argument("--out", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.verify is not None:
            if args.out is not None:
                raise CandidateCaptureError("--out is not used with --verify")
            result = verify_capture(args.verify)
        else:
            if args.out is None:
                raise CandidateCaptureError("--out is required with --plan")
            plan = load_capture_plan(args.plan)
            result = run_capture(plan, args.out)
    except (OSError, UnicodeError, CandidateCaptureError) as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
