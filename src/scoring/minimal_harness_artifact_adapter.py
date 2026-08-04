"""Deterministically project minimal-harness artifacts into scorer inputs.

The projection uses only explicitly delivered report files and the sealed
strict-evidence ledger.  It never asks a model to infer citations, repair a
report, or decide whether an observed page supports a claim.
"""

from __future__ import annotations

from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from src.scoring.legacy_report_adapter import adapt_legacy_run


def _read_json(path: Path) -> Any:
    raw = path.read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _result_manifest(run_dir: Path) -> tuple[Path, dict[str, Any]]:
    candidates = [run_dir / "control/run-manifest.json"]
    candidates.extend(sorted((run_dir / "control").glob("*result.json")))
    for path in candidates:
        if not path.is_file():
            continue
        payload = _read_json(path)
        if (
            isinstance(payload, dict)
            and payload.get("run_id")
            and "completed" in payload
        ):
            return path, payload
    raise FileNotFoundError(f"no run result manifest found under {run_dir}")


def _localize_manifest_path(run_dir: Path, value: str) -> Path | None:
    direct = Path(value)
    if direct.is_file():
        return direct
    parts = direct.parts
    if run_dir.name in parts:
        suffix = parts[parts.index(run_dir.name) + 1 :]
        candidate = run_dir.joinpath(*suffix)
        if candidate.is_file():
            return candidate
    return None


def _manifest_report_paths(
    run_dir: Path, manifest: dict[str, Any]
) -> list[Path]:
    values: list[str] = []
    report = manifest.get("report")
    if isinstance(report, str):
        values.append(report)
    native_outputs = manifest.get("native_outputs")
    if isinstance(native_outputs, dict):
        reports = native_outputs.get("report")
        if isinstance(reports, list):
            values.extend(value for value in reports if isinstance(value, str))
    paths: list[Path] = []
    for value in values:
        path = _localize_manifest_path(run_dir, value)
        if path is not None and path not in paths:
            paths.append(path)
    return paths


def delivered_report_paths(
    run_dir: Path, manifest: dict[str, Any]
) -> list[Path]:
    """Return only primary reports and explicit report-output attachments."""

    paths = _manifest_report_paths(run_dir, manifest)
    primary = run_dir / "worker/native/report.md"
    if primary.is_file() and primary not in paths:
        paths.insert(0, primary)

    # DeerFlow and similar research systems can return a short final message
    # while placing the requested report in a native directory literally
    # named ``outputs``.  Those files are user-facing deliverables, not hidden
    # chain-of-thought or scratch state.
    native_root = run_dir / "worker/native"
    if native_root.is_dir():
        for path in sorted(native_root.rglob("*")):
            relative_parts = path.relative_to(native_root).parts
            if (
                path.is_file()
                and "outputs" in path.parts
                # Tool runtimes commonly place failed write calls and other
                # internal transcripts below outputs/.tool-results.  They are
                # not user-facing report attachments and can contain an
                # escaped duplicate of the entire report in one giant line.
                and not any(part.startswith(".") for part in relative_parts)
                and path.suffix.casefold() in {".md", ".markdown", ".txt"}
                and path not in paths
            ):
                paths.append(path)

    if not paths and native_root.is_dir():
        storm_reports = sorted(
            native_root.rglob("storm_gen_article_polished.txt")
        )
        paths.extend(storm_reports)
    if not paths:
        raise FileNotFoundError(f"no delivered report found under {run_dir}")
    return paths


def write_report_bundle(
    paths: Iterable[Path], output_path: Path
) -> dict[str, Any]:
    selected = list(paths)
    bodies: list[str] = []
    entries: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for path in selected:
        digest = _sha256(path)
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        body = path.read_text(encoding="utf-8", errors="replace").strip()
        if not body:
            continue
        entries.append(
            {
                "path": str(path.resolve()),
                "sha256": digest,
                "bytes": path.stat().st_size,
            }
        )
        bodies.append(
            f"<!-- DRA delivered artifact: {path.name} -->\n\n{body}"
        )
    if not bodies:
        raise ValueError("all delivered report files were empty")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n---\n\n".join(bodies) + "\n", encoding="utf-8")
    return {
        "schema": "dra_delivered_report_bundle_v1",
        "semantic_inference_used": False,
        "files": entries,
        "bundle_sha256": _sha256(output_path),
    }


def _strict_events(run_dir: Path) -> list[dict[str, Any]]:
    root = run_dir / "control/audit/strict-evidence"
    paths = sorted(
        path
        for path in root.glob("*.jsonl")
        if path.name != "_unattributed.jsonl"
    )
    events: list[dict[str, Any]] = []
    for path in paths:
        events.extend(_read_jsonl(path))
    return events


def _response_blob(run_dir: Path, row: dict[str, Any]) -> Path | None:
    digest = str(row.get("response_blob_sha256") or "")
    candidates: list[Path] = []
    value = row.get("response_blob_path")
    if isinstance(value, str):
        localized = _localize_manifest_path(run_dir, value)
        if localized is not None:
            candidates.append(localized)
    if digest:
        candidates.extend(
            [
                run_dir / "control/audit/response-blobs" / digest,
                run_dir
                / "control/audit/protocol-sidecar/response-blobs"
                / digest,
            ]
        )
    return next((path for path in candidates if path.is_file()), None)


def _walk_search_documents(value: Any) -> Iterable[dict[str, str]]:
    if isinstance(value, dict):
        url = value.get("url") or value.get("link") or value.get("href")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            raw_content = value.get("raw_content")
            snippet = (
                raw_content
                or value.get("content")
                or value.get("snippet")
                or value.get("text")
                or value.get("description")
                or ""
            )
            yield {
                "url": url,
                "title": str(value.get("title") or ""),
                "snippet": str(snippet or ""),
                "raw_content": str(raw_content or ""),
            }
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _walk_search_documents(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_search_documents(child)


def _search_response_documents(
    run_dir: Path,
) -> dict[str, list[dict[str, str]]]:
    documents: dict[str, list[dict[str, str]]] = defaultdict(list)
    egress_paths = [run_dir / "control/audit/egress.jsonl"]
    egress_paths.extend(
        sorted((run_dir / "control/audit").glob("*/egress.jsonl"))
    )
    for path in egress_paths:
        if not path.is_file():
            continue
        for row in _read_jsonl(path):
            if int(row.get("status") or 0) != 200:
                continue
            endpoint = str(row.get("path") or "").casefold()
            if not any(
                marker in endpoint
                for marker in ("search", "serper", "tavily")
            ):
                continue
            blob = _response_blob(run_dir, row)
            if blob is None:
                continue
            try:
                payload = _read_json(blob)
            except (OSError, json.JSONDecodeError):
                continue
            for document in _walk_search_documents(payload):
                documents[document["url"]].append(document)
    return documents


def _documents_from_payload(
    payload: Any,
    *,
    artifact_path: Path,
) -> Iterable[dict[str, str]]:
    for document in _walk_search_documents(payload):
        yield {
            **document,
            "native_artifact_path": str(artifact_path.resolve()),
        }


def _json_from_text(value: Any) -> Any | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _gpt_researcher_native_documents(
    native_root: Path,
) -> Iterable[dict[str, str]]:
    path = native_root / "sources.json"
    if not path.is_file():
        return
    try:
        payload = _read_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, gzip.BadGzipFile):
        return
    yield from _documents_from_payload(payload, artifact_path=path)


def _opencode_native_documents(
    native_root: Path,
) -> Iterable[dict[str, str]]:
    path = native_root / "native-events.jsonl"
    if not path.is_file():
        return
    for row in _read_jsonl(path):
        if row.get("type") != "tool_use":
            continue
        part = row.get("part")
        if not isinstance(part, dict):
            continue
        tool = str(part.get("tool") or "").casefold()
        state = part.get("state")
        if "search" not in tool or not isinstance(state, dict):
            continue
        if state.get("status") != "completed":
            continue
        payload = _json_from_text(state.get("output"))
        if payload is None:
            continue
        yield from _documents_from_payload(payload, artifact_path=path)


def _miroflow_native_documents(
    native_root: Path,
) -> Iterable[dict[str, str]]:
    paths = sorted(native_root.rglob("task-trace.json"))
    for path in paths:
        try:
            payload = _read_json(path)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            gzip.BadGzipFile,
        ):
            continue
        if not isinstance(payload, dict):
            continue
        sessions = payload.get("sub_agent_message_history_sessions")
        if not isinstance(sessions, dict):
            continue
        for session in sessions.values():
            if not isinstance(session, dict):
                continue
            history = session.get("message_history")
            if not isinstance(history, list):
                continue
            tool_names: dict[str, str] = {}
            for message in history:
                if not isinstance(message, dict):
                    continue
                for call in message.get("tool_calls", []) or []:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function")
                    if not isinstance(function, dict):
                        continue
                    call_id = str(call.get("id") or "")
                    name = str(function.get("name") or "").casefold()
                    if call_id:
                        tool_names[call_id] = name
                if message.get("role") != "tool":
                    continue
                call_id = str(message.get("tool_call_id") or "")
                if "search" not in tool_names.get(call_id, ""):
                    continue
                result = _json_from_text(message.get("content"))
                if result is None:
                    continue
                yield from _documents_from_payload(result, artifact_path=path)


def _storm_native_documents(
    native_root: Path,
) -> Iterable[dict[str, str]]:
    for path in sorted(native_root.rglob("url_to_info.json")):
        try:
            payload = _read_json(path)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            gzip.BadGzipFile,
        ):
            continue
        yield from _documents_from_payload(payload, artifact_path=path)


def _native_observation_documents(
    run_dir: Path,
    *,
    harness: str,
    allowed_urls: set[str],
) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    """Recover exact official tool outputs, never model-inferred evidence.

    Native source/trace files are useful only when a URL is independently
    present in the strict search/fetch ledger.  This intersection prevents a
    report, scratchpad, or model-authored URL from becoming observation proof.
    """

    native_root = run_dir / "worker/native"
    extractors = {
        "gpt-researcher": _gpt_researcher_native_documents,
        "miroflow": _miroflow_native_documents,
        "opencode": _opencode_native_documents,
        "storm": _storm_native_documents,
    }
    extractor = extractors.get(harness)
    documents: dict[str, list[dict[str, str]]] = defaultdict(list)
    rejected_urls: set[str] = set()
    artifact_paths: set[str] = set()
    if extractor is not None and native_root.is_dir():
        for document in extractor(native_root):
            url = document["url"]
            if url not in allowed_urls:
                rejected_urls.add(url)
                continue
            documents[url].append(document)
            path = document.get("native_artifact_path")
            if path:
                artifact_paths.add(path)
    return documents, {
        "native_artifact_candidate_count": sum(
            len(rows) for rows in documents.values()
        ),
        "native_artifact_url_count": len(documents),
        "native_artifact_paths": sorted(artifact_paths),
        "native_artifacts": [
            {
                "path": path,
                "sha256": _sha256(Path(path)),
            }
            for path in sorted(artifact_paths)
            if Path(path).is_file()
        ],
        "native_artifact_rejected_url_count": len(rejected_urls),
    }


def observed_documents(
    run_dir: Path,
    *,
    harness: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events = _strict_events(run_dir)
    snippets = _search_response_documents(run_dir)
    searched_urls: set[str] = set()
    fetches: dict[str, dict[str, Any]] = {}
    searches = 0
    successful_fetches = 0

    for event in events:
        kind = event.get("kind")
        if kind == "search":
            searches += 1
            searched_urls.update(
                str(url)
                for url in event.get("urls_returned", [])
                if isinstance(url, str)
            )
            continue
        if kind != "fetch":
            continue
        status = int(event.get("status") or 0)
        url = str(event.get("url") or "")
        if not url or not 200 <= status < 300:
            continue
        successful_fetches += 1
        digest = str(event.get("body_sha256") or "")
        blob = (
            run_dir / "control/audit/strict-evidence/blobs" / digest
            if digest
            else None
        )
        text = (
            blob.read_text(encoding="utf-8", errors="replace")
            if blob is not None and blob.is_file()
            else ""
        )
        prior = fetches.get(url)
        if prior is None or len(text) > len(str(prior.get("raw_content") or "")):
            fetches[url] = {
                "url": url,
                "title": "",
                "text": text,
                "raw_content": text,
                "observation_tier": "full_page",
                "strict_body_sha256": digest or None,
                "strict_endpoint": event.get("endpoint"),
            }

    native_snippets, native_summary = _native_observation_documents(
        run_dir,
        harness=harness,
        allowed_urls=searched_urls | set(fetches),
    )
    for url, rows in native_snippets.items():
        snippets[url].extend(rows)

    documents: list[dict[str, Any]] = []
    for url in sorted(searched_urls | set(fetches)):
        if url in fetches:
            document = dict(fetches[url])
            candidates = snippets.get(url, [])
            if candidates:
                document["title"] = candidates[0]["title"]
            documents.append(document)
            continue
        candidates = snippets.get(url, [])
        best = max(
            candidates,
            key=lambda row: len(row["raw_content"] or row["snippet"]),
            default={
                "url": url,
                "title": "",
                "snippet": "",
                "raw_content": "",
            },
        )
        observed_text = best["raw_content"] or best["snippet"]
        document = {
            "url": url,
            "title": best["title"],
            "text": observed_text,
            "raw_content": best["raw_content"],
            "observation_tier": "search_snippet",
        }
        native_path = best.get("native_artifact_path")
        if native_path:
            document["native_artifact_path"] = native_path
        documents.append(document)

    summary = {
        "schema": "dra_minimal_harness_observation_projection_v1",
        "semantic_inference_used": False,
        "strict_event_count": len(events),
        "search_event_count": searches,
        "successful_fetch_event_count": successful_fetches,
        "unique_search_url_count": len(searched_urls),
        "unique_full_page_url_count": len(fetches),
        "document_count": len(documents),
        "snippet_document_count": sum(
            row["observation_tier"] == "search_snippet" for row in documents
        ),
        "full_page_document_count": sum(
            row["observation_tier"] == "full_page" for row in documents
        ),
        "nonempty_search_observation_count": sum(
            row["observation_tier"] == "search_snippet"
            and bool(str(row.get("text") or "").strip())
            for row in documents
        ),
        **native_summary,
    }
    return documents, summary


def _native_numbered_source_map(run_dir: Path) -> dict[str, str]:
    """Read an explicit framework citation index without semantic matching."""

    native_root = run_dir / "worker/native"
    mappings: dict[str, str] = {}
    if not native_root.is_dir():
        return mappings
    for path in sorted(native_root.rglob("url_to_info.json")):
        try:
            payload = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        index = payload.get("url_to_unified_index")
        if not isinstance(index, dict):
            continue
        for url, number in index.items():
            if (
                isinstance(url, str)
                and url.startswith(("http://", "https://"))
                and isinstance(number, int)
                and number > 0
            ):
                mappings[str(number)] = url
    return mappings


def adapt_minimal_harness_run(
    *, run_dir: Path, output_dir: Path
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path, result = _result_manifest(run_dir)
    reports = delivered_report_paths(run_dir, result)
    bundle_path = output_dir / "report.bundle.md"
    bundle = write_report_bundle(reports, bundle_path)
    documents, observation_summary = observed_documents(
        run_dir,
        harness=str(result.get("harness") or ""),
    )
    sources_path = output_dir / "observed-sources.json"
    sources_path.write_text(
        json.dumps(documents, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    native_numbered_sources = _native_numbered_source_map(run_dir)
    adapted = adapt_legacy_run(
        report_path=bundle_path,
        sources_path=sources_path,
        output_dir=output_dir / "scorer-inputs",
        numbered_source_map=native_numbered_sources,
    )
    execution = result.get("execution")
    execution_outcome = (
        execution.get("outcome") if isinstance(execution, dict) else None
    )
    projection = {
        "schema": "dra_minimal_harness_projection_manifest_v1",
        "run_id": result.get("run_id"),
        "harness": result.get("harness"),
        "completed": result.get("completed"),
        "run_failure": result.get("failure") or result.get("failure_type"),
        "execution_outcome": execution_outcome,
        "result_manifest": {
            "path": str(result_path),
            "sha256": _sha256(result_path),
        },
        "report_bundle": bundle,
        "observation_projection": observation_summary,
        "native_numbered_source_count": len(native_numbered_sources),
        "legacy_adapter_manifest": str(adapted["manifest"]),
    }
    projection_path = output_dir / "projection-manifest.json"
    projection_path.write_text(
        json.dumps(projection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        **adapted,
        "projection_manifest": projection_path,
        "sources": sources_path,
        "summary": projection,
    }


def project_minimal_harness_non_delivery(
    *,
    run_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Record an attributable run failure without inventing a report.

    This projection deliberately creates no scorer inputs.  A matrix-level
    policy may assign the end-to-end non-delivery score, while every semantic
    report axis remains absent rather than model- or human-filled.
    """

    run_dir = run_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path, result = _result_manifest(run_dir)
    if result.get("completed") is True:
        raise ValueError("completed run cannot be projected as non-delivery")
    try:
        reports = delivered_report_paths(run_dir, result)
    except FileNotFoundError:
        reports = []
    if reports:
        raise ValueError("run delivered a report; use the normal projection")
    documents, observation_summary = observed_documents(
        run_dir,
        harness=str(result.get("harness") or ""),
    )
    sources_path = output_dir / "observed-sources.json"
    sources_path.write_text(
        json.dumps(documents, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    execution = result.get("execution")
    execution_outcome = (
        execution.get("outcome") if isinstance(execution, dict) else None
    )
    projection = {
        "schema": "dra_minimal_harness_projection_manifest_v1",
        "run_id": result.get("run_id"),
        "harness": result.get("harness"),
        "completed": False,
        "scoreable": False,
        "non_delivery": True,
        "run_failure": result.get("failure") or result.get("failure_type"),
        "execution_outcome": execution_outcome,
        "result_manifest": {
            "path": str(result_path),
            "sha256": _sha256(result_path),
        },
        "report_bundle": {
            "schema": "dra_delivered_report_bundle_v1",
            "semantic_inference_used": False,
            "files": [],
            "bundle_sha256": None,
            "non_delivery": True,
        },
        "observation_projection": observation_summary,
        "native_numbered_source_count": 0,
        "legacy_adapter_manifest": None,
    }
    projection_path = output_dir / "projection-manifest.json"
    projection_path.write_text(
        json.dumps(projection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "projection_manifest": projection_path,
        "sources": sources_path,
        "summary": projection,
    }


__all__ = [
    "adapt_minimal_harness_run",
    "delivered_report_paths",
    "observed_documents",
    "project_minimal_harness_non_delivery",
    "write_report_bundle",
]
