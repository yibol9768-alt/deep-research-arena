"""Deterministic migration of legacy harness artifacts into scorer inputs.

The four-axis scorer consumes an inline ``<cite id="...">`` report plus a
native trace and citation map.  Older harness runs used Markdown links or
numbered references and stored observations in an observation ledger.  This
module translates only those explicit structures.  It deliberately does not
infer missing citations, match prose descriptions to pages, or add evidence
that the report did not cite.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


MARKDOWN_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
NUMBERED_REFERENCE_RE = re.compile(r"\[(\d+)\]")
SOURCE_DEFINITION_RE = re.compile(
    r"^\s*\[(\d+)\]\s+.*?(https?://\S+)\s*$",
    re.MULTILINE,
)
MULTI_SOURCE_HEADER_RE = re.compile(
    r"^\s*\[([0-9]+(?:\s*,\s*[0-9]+)*)\]\s+.*$"
)
SOURCE_URL_LINE_RE = re.compile(r"^\s*URL:\s*(https?://\S+)\s*$")
SOURCES_HEADING_RE = re.compile(r"^#{1,6}\s+Sources\s*$", re.IGNORECASE)
BARE_URL_RE = re.compile(r"https?://[^\s<>\])}\"'`]+")
CITE_ELEMENT_RE = re.compile(r"(<cite\s+id=\"[^\"]+\">.*?</cite>)")
TRAILING_URL_PUNCTUATION = ".,;:"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_url(url: str) -> str:
    return url.rstrip(TRAILING_URL_PUNCTUATION)


def _blob_text(run_dir: Path, event: dict[str, Any]) -> str:
    direct = event.get("content_text_or_blob_ref")
    if isinstance(direct, str) and not direct.startswith(("http://", "https://")):
        return direct
    blob_ref = event.get("blob_ref")
    if not blob_ref and isinstance(direct, dict):
        blob_ref = direct.get("blob_ref")
    if not blob_ref:
        blob_ref = event.get("content_sha256")
    if not blob_ref:
        return ""
    path = run_dir / "blobs" / str(blob_ref)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def documents_from_sources(path: Path) -> list[dict[str, Any]]:
    """Load documents explicitly retained by a legacy harness."""

    payload = _read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"expected a JSON array in {path}")
    documents: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict) or not row.get("url"):
            continue
        raw_content = str(row.get("raw_content") or "")
        text = raw_content or str(
            row.get("snippet") or row.get("text") or ""
        )
        documents.append(
            {
                "url": str(row["url"]),
                "title": str(row.get("title") or ""),
                "text": text,
                "raw_content": raw_content,
                "observation_tier": (
                    str(row.get("observation_tier"))
                    if row.get("observation_tier")
                    in {"full_page", "search_snippet"}
                    else "full_page"
                    if raw_content
                    else "search_snippet"
                ),
            }
        )
    return documents


def documents_from_observation_ledger(path: Path) -> list[dict[str, Any]]:
    """Project successful, observable fetches without inventing observations."""

    payload = _read_json(path)
    run_dir = path.parent
    documents: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for event in payload.get("events", []):
        if (
            event.get("event_type") != "fetch_body"
            or event.get("http_status") != 200
            or not event.get("observable", False)
        ):
            continue
        url = str(event.get("canonical_url") or event.get("request_url") or "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        text = _blob_text(run_dir, event)
        endpoint = str((event.get("metadata") or {}).get("endpoint") or "")
        observation_tier = (
            "search_snippet"
            if endpoint == "/search"
            else "full_page"
        )
        documents.append(
            {
                "url": url,
                "title": text.splitlines()[0].strip() if text else "",
                "text": text,
                "raw_content": text if observation_tier == "full_page" else "",
                "observation_tier": observation_tier,
                "legacy_endpoint": endpoint,
            }
        )
    return documents


def adapt_legacy_run(
    *,
    report_path: Path,
    output_dir: Path,
    observation_ledger_path: Path | None = None,
    sources_path: Path | None = None,
    numbered_source_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create scorer-compatible artifacts using explicit legacy citations only."""

    if (observation_ledger_path is None) == (sources_path is None):
        raise ValueError("provide exactly one of observation_ledger_path or sources_path")

    report = report_path.read_text(encoding="utf-8")
    if sources_path is not None:
        documents = documents_from_sources(sources_path)
        observation_source = sources_path
        observation_kind = "retained_sources"
    else:
        assert observation_ledger_path is not None
        documents = documents_from_observation_ledger(observation_ledger_path)
        observation_source = observation_ledger_path
        observation_kind = "observation_ledger_fetches"

    call_id = "legacyobs"
    observed_by_url = {
        str(row["url"]): f"{call_id}-{index}"
        for index, row in enumerate(documents)
    }
    map_by_id: dict[str, dict[str, Any]] = {}

    def citation_id_for(url: str) -> str:
        cleaned = _clean_url(url)
        observed_id = observed_by_url.get(cleaned)
        if observed_id:
            evidence_id = observed_id
        else:
            evidence_id = f"legacy-unobserved-{_sha256_text(cleaned)[:16]}"
        map_by_id.setdefault(
            evidence_id,
            {
                "evidence_id": evidence_id,
                "url": cleaned,
                "title": "",
                "adapter_status": "observed"
                if observed_id
                else "explicit_but_unobserved",
            },
        )
        return evidence_id

    # Markdown links are explicit bindings. Replacing the link syntax preserves
    # its display text and does not attach it to any other report sentence.
    def replace_markdown_link(match: re.Match[str]) -> str:
        display, url = match.groups()
        evidence_id = citation_id_for(url)
        return f'<cite id="{evidence_id}">{display}</cite>'

    normalized = MARKDOWN_LINK_RE.sub(replace_markdown_link, report)

    # Numbered references are translated only when the report itself contains a
    # matching source-definition line with an explicit URL.
    numbered_sources = {
        number: _clean_url(url)
        for number, url in SOURCE_DEFINITION_RE.findall(report)
    }
    lines = report.splitlines(keepends=True)
    for index, line in enumerate(lines[:-1]):
        header = MULTI_SOURCE_HEADER_RE.match(line.rstrip("\r\n"))
        if not header:
            continue
        for next_index in range(index + 1, min(index + 4, len(lines))):
            url_line = SOURCE_URL_LINE_RE.match(
                lines[next_index].rstrip("\r\n")
            )
            if not url_line:
                continue
            url = _clean_url(url_line.group(1))
            for number in re.findall(r"\d+", header.group(1)):
                numbered_sources[number] = url
            break
    explicit_native_numbered_source_count = 0
    for number, url in (numbered_source_map or {}).items():
        number = str(number)
        url = str(url)
        if not number.isdigit() or not url.startswith(("http://", "https://")):
            raise ValueError("native numbered source map contains an invalid entry")
        numbered_sources[number] = _clean_url(url)
        explicit_native_numbered_source_count += 1

    normalized_lines: list[str] = []
    in_sources_section = False
    for line in normalized.splitlines(keepends=True):
        if SOURCES_HEADING_RE.match(line.rstrip("\r\n")):
            in_sources_section = True
            normalized_lines.append(line)
            continue
        if in_sources_section:
            normalized_lines.append(line)
            continue
        if SOURCE_DEFINITION_RE.match(line.rstrip("\r\n")):
            normalized_lines.append(line)
            continue

        def replace_numbered(match: re.Match[str]) -> str:
            number = match.group(1)
            url = numbered_sources.get(number)
            if not url:
                return match.group(0)
            evidence_id = citation_id_for(url)
            return f'<cite id="{evidence_id}">[{number}]</cite>'

        numbered = NUMBERED_REFERENCE_RE.sub(replace_numbered, line)

        def replace_bare_url(match: re.Match[str]) -> str:
            url = _clean_url(match.group(0))
            evidence_id = citation_id_for(url)
            return f'<cite id="{evidence_id}">{url}</cite>'

        pieces = CITE_ELEMENT_RE.split(numbered)
        normalized_lines.append(
            "".join(
                piece
                if CITE_ELEMENT_RE.fullmatch(piece)
                else BARE_URL_RE.sub(replace_bare_url, piece)
                for piece in pieces
            )
        )
    normalized = "".join(normalized_lines)

    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_report_path = output_dir / "report.normalized.md"
    trace_path = output_dir / "trace.json"
    citation_map_path = output_dir / "citation-map.json"
    manifest_path = output_dir / "adapter-manifest.json"

    normalized_report_path.write_text(normalized, encoding="utf-8")
    trace = {
        "schema": "dra_legacy_trace_projection_v1",
        "tool_call_count": 1 if documents else 0,
        "tool_calls": [
            {
                "call_id": call_id,
                "tool_name": "legacy_observation_projection",
                "called": True,
                "error": "",
                "documents": documents,
                "raw_output": {"query": None},
            }
        ]
        if documents
        else [],
    }
    trace_path.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    citation_map = sorted(map_by_id.values(), key=lambda row: row["evidence_id"])
    citation_map_path.write_text(
        json.dumps(citation_map, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": "dra_legacy_report_adapter_manifest_v1",
        "semantic_inference_used": False,
        "missing_citations_inferred": False,
        "observation_kind": observation_kind,
        "source_report": {
            "path": str(report_path.resolve()),
            "sha256": _sha256_text(report),
        },
        "observation_source": {
            "path": str(observation_source.resolve()),
            "sha256": hashlib.sha256(observation_source.read_bytes()).hexdigest(),
        },
        "normalized_report": {
            "path": str(normalized_report_path.resolve()),
            "sha256": _sha256_text(normalized),
        },
        "observed_document_count": len(documents),
        "explicit_numbered_source_count": len(numbered_sources),
        "explicit_native_numbered_source_count": (
            explicit_native_numbered_source_count
        ),
        "normalized_citation_id_count": len(map_by_id),
        "observed_citation_id_count": sum(
            row["adapter_status"] == "observed" for row in citation_map
        ),
        "unobserved_citation_id_count": sum(
            row["adapter_status"] == "explicit_but_unobserved"
            for row in citation_map
        ),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "report": normalized_report_path,
        "trace": trace_path,
        "citation_map": citation_map_path,
        "manifest": manifest_path,
        "summary": manifest,
    }
