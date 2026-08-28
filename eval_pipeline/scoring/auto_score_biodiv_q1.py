#!/usr/bin/env python3
"""Package-aware automatic scorer for the frozen Biodiversity Q1 package.

The program is deliberately split into deterministic gates and two model
stages.  The model extracts and adjudicates semantics; code owns package
hashes, report-span containment, citation/ledger provenance, the frozen
34-unit denominator, response identity/usage, and final aggregation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Protocol

import httpx
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent
CLAIM_PROMPT = ROOT / "prompts/claim_extractor.v1.txt"
CLAIM_REPAIR_PROMPT = ROOT / "prompts/claim_quote_repair.v1.txt"
CLAIM_BINDING_PROMPT = ROOT / "prompts/claim_binding_adjudicator.v1.txt"
COMPLETENESS_PROMPT = ROOT / "prompts/completeness_adjudicator.v1.txt"
CLAIM_SCHEMA = ROOT / "schemas/claim_extractor_output.v1.schema.json"
CLAIM_BATCH_SCHEMA = ROOT / "schemas/claim_extractor_batch_output.v1.schema.json"
CLAIM_REPAIR_SCHEMA = ROOT / "schemas/claim_quote_repair_output.v1.schema.json"
ADJUDICATION_SCHEMA = ROOT / "schemas/evidence_iu_adjudication_output.v1.schema.json"
CLAIM_BINDING_SCHEMA = ROOT / "schemas/claim_binding_adjudication_output.v1.schema.json"
COMPLETENESS_SCHEMA = ROOT / "schemas/completeness_adjudication_output.v1.schema.json"
CLAIM_BATCH_MAX_CHARS = 1200
ADJUDICATION_CLAIM_BATCH_SIZE = 4
ADJUDICATION_BINDING_BATCH_SIZE = 12
ADJUDICATION_UNIT_BATCH_SIZE = 2
REQUIRED_PACKET_FIELDS = (
    "material_claims",
    "citation_bindings",
    "citation_required_units",
    "completeness_units",
    "rubric_items",
    "failure_status",
)
GROUNDING_TIERS = {
    "full_page",
    "full_fetch",
    "fetched_content",
    "browser_observation",
    "structured_lookup",
}
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
BARE_URL_RE = re.compile(r"https?://[^\s<>\])}\"'`]+")
INLINE_REFERENCE_RE = re.compile(
    r"\[\[(?P<label>[0-9]+)\]\]\(#(?P<reference_id>ref-[A-Za-z0-9_.:-]+)\)"
)
REFERENCE_DEFINITION_RE = re.compile(
    r"<a\s+[^>]*\bid=[\"'](?P<reference_id>ref-[A-Za-z0-9_.:-]+)[\"'][^>]*>\s*</a>",
    re.IGNORECASE,
)
MARKDOWN_HEADING_RE = re.compile(r"(?m)^#{1,6}[ \t]+")


class ScoringError(RuntimeError):
    category = "scorer"
    status_code = "withheld_scorer_failure"


class TaskAssetError(ScoringError):
    category = "task_asset"
    status_code = "withheld_task_asset"


class ObservabilityError(ScoringError):
    category = "adapter"
    status_code = "withheld_observability"


class JudgeError(ScoringError):
    category = "judge_transport"
    status_code = "withheld_judge_failure"


class JudgeIdentityError(JudgeError):
    status_code = "withheld_judge_identity_mismatch"


class JudgeUsageError(JudgeError):
    status_code = "withheld_judge_usage_missing"


class JudgeSchemaError(JudgeError):
    status_code = "withheld_judge_malformed_json"


class JudgeTruncationError(JudgeError):
    status_code = "withheld_judge_truncated"


class JudgeBudgetError(JudgeError):
    status_code = "withheld_scorer_budget"


@dataclass(frozen=True)
class ReportBatch:
    batch_index: int
    start: int
    end: int
    text: str
    citations: list[dict[str, Any]]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskAssetError(f"cannot read JSON object: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TaskAssetError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    # Some small judges (for example Qwen3-4B via the current Adams route)
    # prepend a <think>...</think> block even when asked for raw JSON.  Strip
    # only a leading complete think block; never repair or invent JSON content.
    if stripped.startswith("<think>"):
        end = stripped.find("</think>")
        if end != -1:
            stripped = stripped[end + len("</think>") :].strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, count=1)
        stripped = re.sub(r"\s*```$", "", stripped, count=1)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise JudgeSchemaError("judge response is not one complete JSON object") from exc
    if not isinstance(value, dict):
        raise JudgeSchemaError("judge response top level is not an object")
    return value


def validate_schema(value: Any, schema: dict[str, Any], label: str) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise JudgeSchemaError(f"{label} schema error at {location}: {first.message}")


@dataclass(frozen=True)
class PackageAssets:
    package_dir: Path
    manifest_path: Path
    manifest: dict[str, Any]
    task: dict[str, Any]
    required_units: list[dict[str, Any]]
    evidence_rows: list[dict[str, Any]]
    registry_by_url: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, package_dir: Path) -> "PackageAssets":
        package_dir = package_dir.resolve()
        manifest_path = package_dir / "evaluation_package_manifest.json"
        manifest = read_json(manifest_path)
        if manifest.get("decision") != "STRUCTURAL_READY_UNCALIBRATED":
            raise TaskAssetError("unexpected package decision")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict):
            raise TaskAssetError("package has no artifact table")
        required_roles = {
            "task_json",
            "required_units",
            "evidence_mapping",
            "url_registry",
            "gate_truth_input_contract",
            "eco_scoring_manifest",
        }
        if not required_roles.issubset(artifacts):
            raise TaskAssetError("package lacks required automatic-scorer artifacts")

        resolved: dict[str, Path] = {}
        for role, ref in artifacts.items():
            if not isinstance(ref, dict):
                continue
            recorded = Path(str(ref.get("path") or ""))
            candidates = [recorded, package_dir / recorded.name]
            path = next((item for item in candidates if item.is_file()), None)
            if path is None:
                raise TaskAssetError(f"missing package artifact: {role}")
            if sha256_file(path) != ref.get("sha256"):
                raise TaskAssetError(f"package artifact SHA mismatch: {role}")
            if path.stat().st_size != ref.get("bytes"):
                raise TaskAssetError(f"package artifact byte mismatch: {role}")
            resolved[role] = path

        contract = read_json(resolved["gate_truth_input_contract"])
        if contract.get("required_packet_fields") != list(REQUIRED_PACKET_FIELDS):
            raise TaskAssetError("judgment-packet contract drift")

        required_doc = read_json(resolved["required_units"])
        units = required_doc.get("required_units")
        if not isinstance(units, list) or required_doc.get("unit_count") != len(units):
            raise TaskAssetError("required-unit count is inconsistent")
        unit_ids = [str(row.get("information_unit_id") or "") for row in units]
        if not unit_ids or "" in unit_ids or len(unit_ids) != len(set(unit_ids)):
            raise TaskAssetError("required-unit IDs are empty or duplicated")
        if not all(row.get("necessary") is True and row.get("applicable") is True for row in units):
            raise TaskAssetError("package contains a non-required GRR unit")

        evidence_doc = read_json(resolved["evidence_mapping"])
        evidence = evidence_doc.get("evidence_rows")
        if not isinstance(evidence, list) or evidence_doc.get("evidence_count") != len(evidence):
            raise TaskAssetError("evidence-row count is inconsistent")
        evidence_ids = [str(row.get("evidence_id") or "") for row in evidence]
        if "" in evidence_ids or len(evidence_ids) != len(set(evidence_ids)):
            raise TaskAssetError("evidence IDs are empty or duplicated")
        for row in evidence:
            if row.get("information_unit_id") not in set(unit_ids):
                raise TaskAssetError("evidence references an unknown required unit")
            quote = str(row.get("quote") or "")
            if not quote or sha256_text(quote) != row.get("quote_sha256"):
                raise TaskAssetError(f"evidence quote SHA mismatch: {row.get('evidence_id')}")

        registry_doc = read_json(resolved["url_registry"])
        urls = registry_doc.get("urls")
        if not isinstance(urls, list) or registry_doc.get("url_count") != len(urls):
            raise TaskAssetError("URL registry count is inconsistent")
        registry = {str(row.get("canonical_url") or ""): row for row in urls}
        if "" in registry or len(registry) != len(urls):
            raise TaskAssetError("URL registry contains empty or duplicate URLs")
        for row in evidence:
            url = str(row.get("canonical_url") or "")
            if url not in registry:
                raise TaskAssetError("evidence URL is outside the frozen registry")
            if row.get("page_content_sha256") != registry[url].get("page_content_sha256"):
                raise TaskAssetError("evidence page identity differs from URL registry")

        return cls(
            package_dir=package_dir,
            manifest_path=manifest_path,
            manifest=manifest,
            task=read_json(resolved["task_json"]),
            required_units=units,
            evidence_rows=evidence,
            registry_by_url=registry,
        )


def paragraph_bounds(text: str, offset: int) -> tuple[int, int]:
    start = text.rfind("\n\n", 0, offset)
    end = text.find("\n\n", offset)
    return (0 if start < 0 else start + 2, len(text) if end < 0 else end)


def _direct_url_occurrences(report: str) -> list[tuple[int, int, str, str]]:
    matches: list[tuple[int, int, str, str]] = []
    occupied: list[tuple[int, int]] = []
    for match in MARKDOWN_LINK_RE.finditer(report):
        matches.append((match.start(), match.end(), match.group(2), match.group(0)))
        occupied.append((match.start(), match.end()))
    for match in BARE_URL_RE.finditer(report):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        matches.append((match.start(), match.end(), match.group(0), match.group(0)))
    return sorted(matches)


def _reference_definitions(report: str) -> dict[str, dict[str, Any]]:
    """Resolve HTML ``ref-*`` anchors to the URL in their definition block.

    A malformed or conflicting report citation is a model-output quality issue,
    not scorer infrastructure failure.  Such definitions are recorded with an
    empty URL so their inline occurrences become invalid binding candidates.
    """
    anchors = list(REFERENCE_DEFINITION_RE.finditer(report))
    collected: dict[str, list[dict[str, Any]]] = {}
    for index, anchor in enumerate(anchors):
        block_end = anchors[index + 1].start() if index + 1 < len(anchors) else len(report)
        heading = MARKDOWN_HEADING_RE.search(report, anchor.end(), block_end)
        if heading is not None:
            block_end = heading.start()
        block = report[anchor.end():block_end]
        urls = sorted(
            {
                url.rstrip(".,;:")
                for _, _, url, _ in _direct_url_occurrences(block)
                if url.rstrip(".,;:`")
            }
        )
        reference_id = anchor.group("reference_id").lower()
        collected.setdefault(reference_id, []).append(
            {
                "definition_start": anchor.start(),
                "definition_end": block_end,
                "urls": urls,
            }
        )

    resolved: dict[str, dict[str, Any]] = {}
    for reference_id, definitions in collected.items():
        urls = sorted({url for definition in definitions for url in definition["urls"]})
        if len(urls) == 1:
            status = "resolved"
            url = urls[0]
        elif urls:
            status = "conflicting_definition"
            url = ""
        else:
            status = "missing_definition_url"
            url = ""
        resolved[reference_id] = {
            "url": url,
            "resolution_status": status,
            "definition_count": len(definitions),
            "definition_urls": urls,
            "definition_spans": [
                {
                    "start": definition["definition_start"],
                    "end": definition["definition_end"],
                }
                for definition in definitions
            ],
        }
    return resolved


def extract_citations(report: str) -> list[dict[str, Any]]:
    definitions = _reference_definitions(report)
    occurrences: list[dict[str, Any]] = []
    for start, end, url, raw in _direct_url_occurrences(report):
        occurrences.append(
            {
                "url": url.rstrip(".,;:`"),
                "raw_markup": raw,
                "start": start,
                "end": end,
                "occurrence_kind": "direct_url",
                "resolution_status": "direct_url",
                "reference_id": None,
            }
        )

    for match in INLINE_REFERENCE_RE.finditer(report):
        reference_id = match.group("reference_id").lower()
        definition = definitions.get(reference_id)
        label = match.group("label")
        expected_label = reference_id.removeprefix("ref-")
        if label != expected_label:
            status = "label_target_mismatch"
            url = ""
        elif definition is None:
            status = "missing_definition"
            url = ""
        else:
            status = str(definition["resolution_status"])
            url = str(definition["url"])
        occurrences.append(
            {
                "url": url,
                "raw_markup": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "occurrence_kind": "inline_reference_anchor",
                "resolution_status": status,
                "reference_id": reference_id,
                "reference_label": label,
                "definition_count": int(definition["definition_count"]) if definition else 0,
                "definition_urls": list(definition["definition_urls"]) if definition else [],
            }
        )

    citations = []
    for index, occurrence in enumerate(
        sorted(occurrences, key=lambda row: (int(row["start"]), int(row["end"]))), 1
    ):
        start = int(occurrence["start"])
        p_start, p_end = paragraph_bounds(report, start)
        row = dict(occurrence)
        row["citation_ref"] = f"CITE{index:03d}"
        row["local_context"] = report[p_start:p_end]
        citations.append(row)
    return citations


def canonicalize_citation_urls(
    citations: list[dict[str, Any]], assets: PackageAssets
) -> list[dict[str, Any]]:
    """Map the live Kiwix ``/content/`` route to the frozen canonical URL.

    The visible report URL is retained verbatim.  No fuzzy URL matching or
    title lookup is allowed; the single deterministic alias must land on an
    exact URL already present in the package registry.
    """
    normalized = []
    prefix = "http://localhost:8090/content/"
    canonical_prefix = "http://localhost:8090/"
    for citation in citations:
        row = dict(citation)
        reported = str(row.get("url") or "")
        row["reported_url"] = reported
        candidate = (
            canonical_prefix + reported[len(prefix):]
            if reported.startswith(prefix)
            else reported
        )
        if candidate in assets.registry_by_url:
            row["url"] = candidate
            row["url_alias_applied"] = candidate != reported
        else:
            row["url_alias_applied"] = False
        normalized.append(row)
    return normalized


def partition_report(
    report: str,
    citations: list[dict[str, Any]],
    max_chars: int = CLAIM_BATCH_MAX_CHARS,
) -> list[ReportBatch]:
    """Split a report deterministically without cutting paragraph content."""
    if max_chars <= 0:
        raise JudgeSchemaError("claim batch max_chars must be positive")
    if not report:
        return []
    paragraph_pieces: list[tuple[int, int]] = []
    cursor = 0
    for match in re.finditer(r"\n[ \t]*\n+", report):
        paragraph_pieces.append((cursor, match.end()))
        cursor = match.end()
    if cursor < len(report):
        paragraph_pieces.append((cursor, len(report)))
    if not paragraph_pieces:
        paragraph_pieces = [(0, len(report))]

    # Long Markdown paragraphs are commonly tables or multi-sentence list
    # items. Split only at explicit line/sentence boundaries and never cut a
    # URL or an inline ``[[n]](#ref-n)`` marker. A boundary-free overlong span
    # remains fail-closed.
    pieces: list[tuple[int, int]] = []
    for piece_start, piece_end in paragraph_pieces:
        segment = report[piece_start:piece_end]
        if len(segment) <= max_chars:
            pieces.append((piece_start, piece_end))
            continue
        boundaries = {match.end() for match in re.finditer(r"\n", segment)}
        for match in re.finditer(r"(?<=[.!?;])[^\S\r\n]+", segment):
            if not segment[match.end():].startswith("[["):
                boundaries.add(match.end())
        local_start = 0
        while len(segment) - local_start > max_chars:
            candidates = [
                boundary
                for boundary in boundaries
                if local_start < boundary <= local_start + max_chars
            ]
            if not candidates:
                raise JudgeSchemaError(
                    "one report paragraph exceeds claim batch max_chars without a safe boundary"
                )
            local_end = max(candidates)
            pieces.append((piece_start + local_start, piece_start + local_end))
            local_start = local_end
        if local_start < len(segment):
            pieces.append((piece_start + local_start, piece_end))

    spans: list[tuple[int, int]] = []
    batch_start = pieces[0][0]
    batch_end = batch_start
    for start, end in pieces:
        if batch_end > batch_start and end - batch_start > max_chars:
            spans.append((batch_start, batch_end))
            batch_start = start
        batch_end = end
    spans.append((batch_start, batch_end))
    if "".join(report[start:end] for start, end in spans) != report:
        raise JudgeSchemaError("claim batch partition does not reconstruct report")

    citation_groups: list[list[dict[str, Any]]] = [[] for _ in spans]
    for citation in citations:
        start = int(citation["start"])
        end = int(citation["end"])
        owners = [
            index
            for index, (span_start, span_end) in enumerate(spans)
            if span_start <= start and end <= span_end
        ]
        if len(owners) != 1:
            raise JudgeSchemaError("citation crosses or escapes a claim batch boundary")
        citation_groups[owners[0]].append(citation)
    return [
        ReportBatch(
            batch_index=index + 1,
            start=start,
            end=end,
            text=report[start:end],
            citations=citation_groups[index],
        )
        for index, (start, end) in enumerate(spans)
    ]


def read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ObservabilityError(f"evidence ledger is missing: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ObservabilityError("evidence ledger is empty")
    try:
        value = json.loads(text)
        if isinstance(value, list):
            rows = value
        elif isinstance(value, dict) and isinstance(value.get("events"), list):
            rows = value["events"]
        else:
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ObservabilityError("evidence ledger contains no event objects")
    return rows


def _urls_from_search(row: dict[str, Any]) -> list[str]:
    values = row.get("urls_returned") or row.get("result_urls") or []
    if not values and isinstance(row.get("results"), list):
        values = [item.get("url") for item in row["results"] if isinstance(item, dict)]
    return [str(value) for value in values if value]


def _status_ok(row: dict[str, Any]) -> bool:
    raw = row.get("http_status", row.get("status"))
    try:
        return 200 <= int(raw) < 300
    except (TypeError, ValueError):
        return bool(row.get("ok"))


def reconstruct_observations(
    rows: list[dict[str, Any]], ledger_path: Path, assets: PackageAssets
) -> dict[str, dict[str, Any]]:
    discovered: set[str] = set()
    observations: dict[str, dict[str, Any]] = {}
    for event_index, row in enumerate(rows):
        kind = str(row.get("kind") or row.get("operation") or row.get("type") or "").lower()
        if kind == "search":
            discovered.update(_urls_from_search(row))
            continue
        if kind != "fetch":
            continue
        url = str(row.get("canonical_url") or row.get("url") or "")
        if not url or not _status_ok(row):
            continue
        body_path_raw = row.get("body_path") or row.get("blob_path")
        if not body_path_raw:
            continue
        body_path = Path(str(body_path_raw))
        if not body_path.is_absolute():
            body_path = (ledger_path.parent / body_path).resolve()
        if not body_path.is_file():
            continue
        body_sha = sha256_file(body_path)
        recorded_body_sha = row.get("body_sha256") or row.get("blob_sha256")
        if recorded_body_sha and recorded_body_sha != body_sha:
            continue
        try:
            body_doc = json.loads(body_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(body_doc, dict):
            continue
        body_url = str(body_doc.get("canonical_url") or url)
        if body_url != url:
            continue
        registry = assets.registry_by_url.get(url)
        page_sha = str(body_doc.get("page_content_sha256") or row.get("page_content_sha256") or "")
        valid_identity = bool(registry) and page_sha == registry.get("page_content_sha256")
        content = str(body_doc.get("content") or body_doc.get("raw_content") or "")
        if not content or not valid_identity:
            continue
        truncated = body_doc.get("truncated")
        total_chars = body_doc.get("total_chars")
        span = body_doc.get("char_span") if isinstance(body_doc.get("char_span"), dict) else {}
        full_page = truncated is False and (
            total_chars is None
            or int(total_chars) <= len(content)
            or int(span.get("char_end") or 0) >= int(total_chars)
        )
        tier = "full_page" if full_page else str(
            row.get("observation_tier") or body_doc.get("evidence_level") or "fetched_content"
        )
        evidence_ids = [
            evidence["evidence_id"]
            for evidence in assets.evidence_rows
            if evidence.get("canonical_url") == url
            and str(evidence.get("quote") or "") in content
        ]
        candidate = {
            "url": url,
            "observed": True,
            "legally_discovered": url in discovered,
            "observation_tier": tier,
            "page_content_sha256": page_sha,
            "body_sha256": body_sha,
            "body_path": str(body_path),
            "event_index": event_index,
            "observed_evidence_ids": evidence_ids,
        }
        prior = observations.get(url)
        rank = 2 if tier == "full_page" else 1
        prior_rank = 2 if prior and prior.get("observation_tier") == "full_page" else 1 if prior else 0
        if rank >= prior_rank:
            observations[url] = candidate
    return observations


class JsonJudge(Protocol):
    model: str

    def call_json(
        self,
        stage: str,
        system: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> dict[str, Any]: ...


class BudgetedJudge:
    """Fail-closed judge wrapper with a hard call budget.

    The wrapper reserves deterministic batch slots before each model stage so a
    long report cannot discover halfway through adjudication that it needs an
    unbounded number of judge calls. Persistent cross-run caching is still a
    separate deployment concern; this wrapper guarantees the hard stop.
    """

    def __init__(self, delegate: JsonJudge, config: dict[str, Any]):
        self.delegate = delegate
        self.model = getattr(delegate, "model", str(config.get("request_model") or ""))
        self.max_calls = int(config.get("max_calls", 8) or 8)
        self.calls_made = 0

    def ensure_available(self, needed: int) -> None:
        if needed < 0:
            raise JudgeBudgetError("negative judge reservation is invalid")
        if self.calls_made + needed > self.max_calls:
            raise JudgeBudgetError(
                "judge call budget exceeded: "
                f"needed={needed} calls_made={self.calls_made} max_calls={self.max_calls}"
            )

    def call_json(
        self,
        stage: str,
        system: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.ensure_available(1)
        self.calls_made += 1
        return self.delegate.call_json(stage, system, payload, schema)


@dataclass
class AdamsOpenAIJudge:
    output_dir: Path
    config: dict[str, Any]
    run_id: str

    def __post_init__(self) -> None:
        self.model = str(self.config["request_model"])
        self.expected_model = str(self.config["expected_response_model"])
        if self.config.get("provider") == "adams_openai_compatible":
            if not str(self.config.get("adams_platform_user") or "").strip():
                raise JudgeError("Adams judge config lacks adams_platform_user")
            if not str(self.config.get("adams_business") or "").strip():
                raise JudgeError("Adams judge config lacks adams_business")
        self._counter = 0

    def call_json(
        self,
        stage: str,
        system: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        credential_name = str(self.config["credential_env"])
        credential = os.environ.get(credential_name, "").strip()
        if not credential:
            raise JudgeError(f"missing controlled credential environment: {credential_name}")
        request_doc = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "input": payload,
                            "required_output_json_schema": schema,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            "stream": False,
        }
        if self.config.get("temperature") is not None:
            request_doc["temperature"] = float(self.config["temperature"])
        if self.config.get("max_completion_tokens") is not None:
            request_doc["max_completion_tokens"] = int(self.config["max_completion_tokens"])
        else:
            request_doc["max_tokens"] = int(self.config.get("max_tokens", 16384))
        if isinstance(self.config.get("reasoning_effort"), str):
            request_doc["reasoning_effort"] = self.config["reasoning_effort"]
        if isinstance(self.config.get("enable_thinking"), bool):
            request_doc["enable_thinking"] = self.config["enable_thinking"]
        thinking = self.config.get("thinking")
        if isinstance(thinking, dict):
            request_doc["thinking"] = json.loads(json.dumps(thinking))
        request_sha = sha256_bytes(canonical_json_bytes(request_doc))
        statuses = {int(value) for value in self.config.get("retry_http_statuses", [])}
        retries = int(self.config.get("transient_retries", 0))
        last_error: Exception | None = None
        for retry_index in range(retries + 1):
            self._counter += 1
            call_dir = self.output_dir / f"{self._counter:04d}-{stage}-attempt-{retry_index}"
            call_dir.mkdir(parents=True, exist_ok=False)
            write_json(call_dir / "request.json", request_doc)
            started = time.monotonic()
            status: int | None = None
            response_doc: dict[str, Any] | None = None
            transport_error: str | None = None
            try:
                headers = {"Authorization": f"Bearer {credential}"}
                platform_user = str(self.config.get("adams_platform_user") or "").strip()
                business = str(self.config.get("adams_business") or "").strip()
                if platform_user:
                    headers["Adams-Platform-User"] = platform_user
                if business:
                    headers["Adams-Business"] = business
                response = httpx.post(
                    str(self.config["base_url"]).rstrip("/") + "/chat/completions",
                    headers=headers,
                    json=request_doc,
                    timeout=float(self.config.get("timeout_seconds", 900)),
                )
                status = response.status_code
                raw = response.text
                (call_dir / "raw-response.txt").write_text(raw, encoding="utf-8")
                if status == 200:
                    value = response.json()
                    response_doc = value if isinstance(value, dict) else None
                else:
                    last_error = JudgeError(f"judge HTTP {status} at {stage}")
            except Exception as exc:  # noqa: BLE001
                raw = ""
                transport_error = type(exc).__name__
                last_error = JudgeError(f"judge transport failure at {stage}: {type(exc).__name__}")
                (call_dir / "raw-response.txt").write_text("", encoding="utf-8")
            latency_ms = round((time.monotonic() - started) * 1000, 3)
            actual_model = response_doc.get("model") if response_doc else None
            usage = response_doc.get("usage") if response_doc and isinstance(response_doc.get("usage"), dict) else {}
            choices = response_doc.get("choices") if response_doc else None
            first_choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            message = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
            content = message.get("content")
            if isinstance(content, list):
                content = "".join(
                    str(item.get("text") or "") for item in content if isinstance(item, dict)
                )
            reasoning_content = message.get("reasoning_content")
            finish_reason = first_choice.get("finish_reason")
            metadata = {
                "schema": "truth1000_biodiv_judge_call_v1",
                "run_id": self.run_id,
                "stage": stage,
                "retry_index": retry_index,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "request_model": self.model,
                "expected_response_model": self.expected_model,
                "actual_response_model": actual_model,
                "identity_match": actual_model == self.expected_model if actual_model else False,
                "request_sha256": request_sha,
                "raw_response_sha256": sha256_text(raw),
                "http_status": status,
                "transport_error": transport_error,
                "latency_ms": latency_ms,
                "finish_reason": finish_reason,
                "content_chars": len(content) if isinstance(content, str) else 0,
                "reasoning_content_chars": (
                    len(reasoning_content) if isinstance(reasoning_content, str) else 0
                ),
                "usage": usage,
            }
            write_json(call_dir / "metadata.json", metadata)
            if response_doc is not None:
                write_json(call_dir / "response-envelope.json", response_doc)
                if actual_model != self.expected_model:
                    raise JudgeIdentityError(
                        f"expected judge {self.expected_model!r}, received {actual_model!r}"
                    )
                if self.config.get("usage_required", True) and not usage:
                    raise JudgeUsageError(f"judge usage missing at {stage}")
                if not isinstance(choices, list) or not choices:
                    raise JudgeSchemaError(f"judge response has no choices at {stage}")
                if finish_reason == "length":
                    raise JudgeTruncationError(
                        f"judge output truncated at {stage}: finish_reason=length"
                    )
                parsed = parse_json_object(str(content or ""))
                validate_schema(parsed, schema, stage)
                write_json(call_dir / "parsed-response.json", parsed)
                return parsed
            if retry_index < retries and (status in statuses or transport_error):
                continue
            break
        raise last_error or JudgeError(f"judge failed at {stage}")


def normalize_claims(
    response: dict[str, Any], report: str, citations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    allowed_citations = {row["citation_ref"] for row in citations}
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for index, row in enumerate(response["claims"], 1):
        quote = str(row["exact_report_quote"]).strip()
        claim = str(row["normalized_claim"]).strip()
        refs = [str(value) for value in row["citation_refs"]]
        if not quote or quote not in report:
            raise JudgeSchemaError("claim exact_report_quote is not an exact report substring")
        if not claim:
            raise JudgeSchemaError("normalized claim is empty")
        if not set(refs).issubset(allowed_citations):
            raise JudgeSchemaError("claim references an unknown citation")
        key = (quote, claim.casefold(), tuple(refs))
        if key in seen:
            raise JudgeSchemaError("claim extractor returned a duplicate claim row")
        seen.add(key)
        recorded_start = row.get("_quote_start")
        start = (
            int(recorded_start)
            if isinstance(recorded_start, int)
            and report[recorded_start:recorded_start + len(quote)] == quote
            else report.find(quote)
        )
        p_start, p_end = paragraph_bounds(report, start)
        normalized.append(
            {
                "claim_id": f"C{index:03d}",
                "exact_report_quote": quote,
                "quote_start": start,
                "quote_end": start + len(quote),
                "paragraph_start": p_start,
                "paragraph_end": p_end,
                "normalized_claim": claim,
                "claim_kind": row["claim_kind"],
                "evidence_policy": row["evidence_policy"],
                "citation_refs": refs,
            }
        )
    return normalized


def repair_invalid_claim_quotes(
    response: dict[str, Any],
    report: str,
    judge: JsonJudge,
    *,
    stage: str = "claim-quote-repair",
) -> tuple[dict[str, Any], int]:
    invalid = []
    for index, row in enumerate(response["claims"]):
        quote = str(row["exact_report_quote"]).strip()
        if not quote or quote not in report:
            invalid.append(
                {
                    "claim_index": index,
                    "normalized_claim": row["normalized_claim"],
                    "invalid_exact_report_quote": row["exact_report_quote"],
                }
            )
    if not invalid:
        return response, 0
    repair = judge.call_json(
        stage,
        CLAIM_REPAIR_PROMPT.read_text(encoding="utf-8"),
        {"report": report, "invalid_claims": invalid},
        read_json(CLAIM_REPAIR_SCHEMA),
    )
    rows = repair["repairs"]
    expected = {row["claim_index"] for row in invalid}
    actual = [row["claim_index"] for row in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise JudgeSchemaError("claim quote repair indices differ from invalid claims")
    repaired = json.loads(json.dumps(response))
    for row in rows:
        quote = str(row["exact_report_quote"]).strip()
        if not quote or quote not in report:
            raise JudgeSchemaError(
                "repaired claim quote is not an exact report substring"
            )
        repaired["claims"][row["claim_index"]]["exact_report_quote"] = quote
    return repaired, len(invalid)


def extract_claims_batched(
    assets: PackageAssets,
    report: str,
    citations: list[dict[str, Any]],
    judge: JsonJudge,
    *,
    max_chars: int = CLAIM_BATCH_MAX_CHARS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    batch_schema = read_json(CLAIM_BATCH_SCHEMA)
    merged_schema = read_json(CLAIM_SCHEMA)
    batches = partition_report(report, citations, max_chars)
    gathered: list[tuple[int, int, int, dict[str, Any]]] = []
    repaired_count = 0
    batch_receipts = []
    for batch in batches:
        stage = f"claim-extractor-batch-{batch.batch_index:03d}"
        response = judge.call_json(
            stage,
            CLAIM_PROMPT.read_text(encoding="utf-8"),
            {
                "task_question": assets.task["question"],
                "report": batch.text,
                "report_span": {"start": batch.start, "end": batch.end},
                "citation_catalog": batch.citations,
            },
            batch_schema,
        )
        response, count = repair_invalid_claim_quotes(
            response,
            batch.text,
            judge,
            stage=f"claim-quote-repair-batch-{batch.batch_index:03d}",
        )
        repaired_count += count
        allowed_refs = {row["citation_ref"] for row in batch.citations}
        for row_index, source in enumerate(response["claims"]):
            row = json.loads(json.dumps(source))
            quote = str(row["exact_report_quote"]).strip()
            normalized = str(row["normalized_claim"]).strip()
            refs = [str(value) for value in row["citation_refs"]]
            if not quote or quote not in batch.text:
                raise JudgeSchemaError(
                    f"claim quote escapes report batch {batch.batch_index:03d}"
                )
            if not normalized:
                raise JudgeSchemaError("batched normalized claim is empty")
            if not set(refs).issubset(allowed_refs):
                raise JudgeSchemaError(
                    f"claim citation escapes report batch {batch.batch_index:03d}"
                )
            row["exact_report_quote"] = quote
            row["normalized_claim"] = normalized
            row["citation_refs"] = refs
            gathered.append(
                (
                    batch.start + batch.text.find(quote),
                    batch.batch_index,
                    row_index,
                    row,
                )
            )

        batch_receipts.append(
            {
                "batch_index": batch.batch_index,
                "start": batch.start,
                "end": batch.end,
                "chars": len(batch.text),
                "citation_count": len(batch.citations),
                "claim_count": len(response["claims"]),
                "report_segment_sha256": sha256_text(batch.text),
            }
        )

    gathered.sort(key=lambda value: (value[0], value[1], value[2]))
    claims: list[dict[str, Any]] = []
    claim_starts: list[int] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    duplicate_count = 0
    for global_start, _, _, row in gathered:
        key = (
            row["exact_report_quote"],
            row["normalized_claim"].casefold(),
            tuple(row["citation_refs"]),
        )
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        claims.append(row)
        claim_starts.append(global_start)
    merged = {"claims": claims}
    validate_schema(merged, merged_schema, "claim-extractor-merged")
    # This private deterministic field is attached only after JSON-Schema
    # validation.  It prevents a repeated verbatim sentence in a later batch
    # from being rebound to its first occurrence in the full report.
    if len(merged["claims"]) != len(claim_starts):
        raise JudgeSchemaError("claim positions differ from merged claims")
    for row, global_start in zip(merged["claims"], claim_starts):
        row["_quote_start"] = global_start
    return merged, {
        "batch_count": len(batches),
        "max_batch_chars": max_chars,
        "batches": batch_receipts,
        "repaired_claim_quote_count": repaired_count,
        "deduplicated_claim_count": duplicate_count,
    }


def _chunks(values: list[Any], size: int) -> list[list[Any]]:
    if size <= 0:
        raise JudgeSchemaError("adjudication batch size must be positive")
    return [values[index:index + size] for index in range(0, len(values), size)]


def _claim_batches(
    claims: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    claim_limit: int,
    binding_limit: int,
) -> list[list[dict[str, Any]]]:
    if claim_limit <= 0 or binding_limit <= 0:
        raise JudgeSchemaError("claim adjudication limits must be positive")
    counts: dict[str, int] = {}
    for candidate in candidates:
        claim_id = str(candidate["claim_id"])
        counts[claim_id] = counts.get(claim_id, 0) + 1
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_bindings = 0
    for claim in claims:
        binding_count = counts.get(str(claim["claim_id"]), 0)
        if binding_count > binding_limit:
            raise JudgeSchemaError("one claim exceeds the binding batch limit")
        if current and (
            len(current) >= claim_limit
            or current_bindings + binding_count > binding_limit
        ):
            batches.append(current)
            current = []
            current_bindings = 0
        current.append(claim)
        current_bindings += binding_count
    if current:
        batches.append(current)
    return batches


def adjudicate_batched(
    report: str,
    claims: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    assets: PackageAssets,
    judge: JsonJudge,
    *,
    claim_batch_size: int = ADJUDICATION_CLAIM_BATCH_SIZE,
    binding_batch_size: int = ADJUDICATION_BINDING_BATCH_SIZE,
    unit_batch_size: int = ADJUDICATION_UNIT_BATCH_SIZE,
) -> tuple[dict[str, Any], dict[str, Any]]:
    claim_schema = read_json(CLAIM_BINDING_SCHEMA)
    completeness_schema = read_json(COMPLETENESS_SCHEMA)
    claim_judgments: list[dict[str, Any]] = []
    binding_judgments: list[dict[str, Any]] = []
    claim_batches = _claim_batches(
        claims, candidates, claim_batch_size, binding_batch_size
    )
    claim_batch_receipts = []
    for batch_index, claim_batch in enumerate(claim_batches, 1):
        claim_ids = [row["claim_id"] for row in claim_batch]
        claim_id_set = set(claim_ids)
        candidate_batch = [
            row for row in candidates if row["claim_id"] in claim_id_set
        ]
        contexts = []
        seen_contexts: set[tuple[int, int]] = set()
        for claim in claim_batch:
            bounds = (int(claim["paragraph_start"]), int(claim["paragraph_end"]))
            if bounds in seen_contexts:
                continue
            seen_contexts.add(bounds)
            contexts.append(
                {"start": bounds[0], "end": bounds[1], "text": report[bounds[0]:bounds[1]]}
            )
        response = judge.call_json(
            f"claim-binding-adjudicator-batch-{batch_index:03d}",
            CLAIM_BINDING_PROMPT.read_text(encoding="utf-8"),
            {
                "report_contexts": contexts,
                "claims_to_judge": claim_batch,
                "citation_candidates_to_judge": candidate_batch,
                "frozen_evidence": assets.evidence_rows,
            },
            claim_schema,
        )
        _require_exact_ids(
            response["claim_judgments"], "claim_id", claim_ids,
            f"claim batch {batch_index} judgments",
        )
        _require_exact_ids(
            response["binding_judgments"], "binding_id",
            [row["binding_id"] for row in candidate_batch],
            f"claim batch {batch_index} binding judgments",
        )
        claim_judgments.extend(response["claim_judgments"])
        binding_judgments.extend(response["binding_judgments"])
        claim_batch_receipts.append(
            {
                "batch_index": batch_index,
                "claim_count": len(claim_batch),
                "binding_count": len(candidate_batch),
                "claim_ids": claim_ids,
            }
        )

    unit_batches = _chunks(assets.required_units, unit_batch_size)
    completeness_judgments: list[dict[str, Any]] = []
    unit_batch_receipts = []
    compact_claims = [
        {
            "claim_id": row["claim_id"],
            "exact_report_quote": row["exact_report_quote"],
            "normalized_claim": row["normalized_claim"],
        }
        for row in claims
    ]
    for batch_index, unit_batch in enumerate(unit_batches, 1):
        unit_context = [
            {
                "unit_id": row["information_unit_id"],
                "public_description": row["public_description"],
            }
            for row in unit_batch
        ]
        response = judge.call_json(
            f"completeness-adjudicator-batch-{batch_index:03d}",
            COMPLETENESS_PROMPT.read_text(encoding="utf-8"),
            {
                "report": report,
                "claims_for_coverage": compact_claims,
                "required_information_units_to_judge": unit_context,
            },
            completeness_schema,
        )
        expected_ids = [row["unit_id"] for row in unit_context]
        _require_exact_ids(
            response["completeness_judgments"], "unit_id", expected_ids,
            f"completeness batch {batch_index} judgments",
        )
        completeness_judgments.extend(response["completeness_judgments"])
        unit_batch_receipts.append(
            {
                "batch_index": batch_index,
                "unit_count": len(unit_context),
                "unit_ids": expected_ids,
            }
        )

    merged = {
        "claim_judgments": claim_judgments,
        "binding_judgments": binding_judgments,
        "completeness_judgments": completeness_judgments,
    }
    validate_schema(merged, read_json(ADJUDICATION_SCHEMA), "adjudication-merged")
    return merged, {
        "claim_batch_size": claim_batch_size,
        "binding_batch_size": binding_batch_size,
        "unit_batch_size": unit_batch_size,
        "claim_binding_batches": claim_batch_receipts,
        "completeness_batches": unit_batch_receipts,
    }


def build_binding_candidates(
    claims: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    observations: dict[str, dict[str, Any]],
    assets: PackageAssets,
) -> list[dict[str, Any]]:
    citation_map = {row["citation_ref"]: row for row in citations}
    evidence_by_id = {row["evidence_id"]: row for row in assets.evidence_rows}
    candidates = []
    for claim in claims:
        for ref in claim["citation_refs"]:
            citation = citation_map[ref]
            url = citation["url"]
            observation = observations.get(url, {})
            same_paragraph = (
                claim["paragraph_start"] <= citation["start"] <= claim["paragraph_end"]
            )
            observed_ids = list(observation.get("observed_evidence_ids") or [])
            candidates.append(
                {
                    "binding_id": f"B{len(candidates) + 1:04d}",
                    "claim_id": claim["claim_id"],
                    "citation_ref": ref,
                    "url": url,
                    "same_paragraph": same_paragraph,
                    "valid": url in assets.registry_by_url,
                    "observed": bool(observation.get("observed")),
                    "legally_discovered": bool(observation.get("legally_discovered")),
                    "observation_tier": observation.get("observation_tier"),
                    "page_content_sha256": observation.get("page_content_sha256"),
                    "observed_evidence_ids": observed_ids,
                    "observed_evidence": [evidence_by_id[value] for value in observed_ids],
                }
            )
    return candidates


def _require_exact_ids(rows: list[dict[str, Any]], field: str, expected: list[str], label: str) -> None:
    actual = [str(row.get(field) or "") for row in rows]
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise JudgeSchemaError(f"{label} IDs differ; expected={expected}, actual={actual}")


def compile_packet(
    report: str,
    claims: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    adjudication: dict[str, Any],
    assets: PackageAssets,
) -> dict[str, Any]:
    claim_rows = adjudication["claim_judgments"]
    binding_rows = adjudication["binding_judgments"]
    coverage_rows = adjudication["completeness_judgments"]
    claim_ids = [row["claim_id"] for row in claims]
    binding_ids = [row["binding_id"] for row in candidates]
    unit_ids = [row["information_unit_id"] for row in assets.required_units]
    _require_exact_ids(claim_rows, "claim_id", claim_ids, "claim judgments")
    _require_exact_ids(binding_rows, "binding_id", binding_ids, "binding judgments")
    _require_exact_ids(coverage_rows, "unit_id", unit_ids, "completeness judgments")
    evidence_ids = {row["evidence_id"] for row in assets.evidence_rows}
    claim_judgment = {row["claim_id"]: row for row in claim_rows}
    material_claims = []
    for claim in claims:
        judgment = claim_judgment[claim["claim_id"]]
        supports = list(judgment["support_evidence_ids"])
        contradictions = list(judgment["contradiction_evidence_ids"])
        if not set(supports + contradictions).issubset(evidence_ids):
            raise JudgeSchemaError("claim judgment references unknown frozen evidence")
        if judgment["verdict"] == "true" and not supports:
            raise JudgeSchemaError("true claim has no frozen support evidence")
        if judgment["verdict"] == "false" and not contradictions:
            raise JudgeSchemaError("false claim has no direct contradiction evidence")
        material_claims.append(
            {
                **claim,
                "verdict": judgment["verdict"],
                "support_evidence_ids": supports,
                "contradiction_evidence_ids": contradictions,
                "materiality": "eligible",
                "eligible": True,
                "semantic_verdict": judgment,
            }
        )

    candidate_map = {row["binding_id"]: row for row in candidates}
    binding_judgment = {row["binding_id"]: row for row in binding_rows}
    bindings = []
    for binding_id in binding_ids:
        candidate = candidate_map[binding_id]
        semantic = binding_judgment[binding_id]
        bound = bool(semantic["bound"]) and bool(candidate["same_paragraph"])
        supports = semantic["support_verdict"] == "support" and bool(
            candidate["observed_evidence_ids"]
        )
        bindings.append(
            {
                **{key: value for key, value in candidate.items() if key != "observed_evidence"},
                "occurrence_index": 0,
                "citation_id": candidate["citation_ref"],
                "bound": bound,
                "supports": supports,
                "support_verdict": semantic["support_verdict"],
                "role_ok": bool(semantic["role_ok"]),
                "complete_scope_observed": (
                    candidate["observation_tier"] == "full_page"
                    if next(row for row in claims if row["claim_id"] == candidate["claim_id"])["claim_kind"] == "bounded_absence"
                    else True
                ),
                "semantic_verdict": semantic,
            }
        )

    def binding_passes(row: dict[str, Any]) -> bool:
        return all(
            bool(row.get(field))
            for field in (
                "valid",
                "observed",
                "legally_discovered",
                "bound",
                "supports",
                "role_ok",
                "complete_scope_observed",
            )
        ) and row.get("observation_tier") in GROUNDING_TIERS

    passing_binding_claims = {row["claim_id"] for row in bindings if binding_passes(row)}
    grounded_claims = {
        row["claim_id"]
        for row in material_claims
        if row["verdict"] == "true"
        and (
            row["claim_id"] in passing_binding_claims
            if row["evidence_policy"] == "citation_required"
            else bool(row.get("proof_chain_grounded"))
        )
    }
    unit_source = {row["information_unit_id"]: row for row in assets.required_units}
    coverage_map = {row["unit_id"]: row for row in coverage_rows}
    completeness = []
    for unit_id in unit_ids:
        semantic = coverage_map[unit_id]
        matched = list(semantic["matched_claim_ids"])
        quotes = [str(value).strip() for value in semantic["exact_report_quotes"]]
        if not set(matched).issubset(set(claim_ids)):
            raise JudgeSchemaError("completeness judgment references an unknown claim")
        if any(not quote or quote not in report for quote in quotes):
            raise JudgeSchemaError("coverage exact quote is not an exact report substring")
        content = bool(semantic["content_covered"]) and bool(matched) and bool(quotes)
        if not semantic["content_covered"] and (matched or quotes):
            raise JudgeSchemaError("uncovered unit carries positive witnesses")
        grounded = content and all(claim_id in grounded_claims for claim_id in matched)
        source = unit_source[unit_id]
        completeness.append(
            {
                "unit_id": unit_id,
                "necessary": True,
                "applicable": True,
                "citation_required": bool(source.get("citation_required", True)),
                "public_description": source["public_description"],
                "content_covered": content,
                "matched_claim_ids": matched,
                "exact_quotes": quotes,
                "gate_truth_grounded_covered": grounded,
                "semantic_verdict": semantic,
            }
        )

    return {
        "schema": "truth1000_biodiv_judgment_packet_v1",
        "material_claims": material_claims,
        "citation_bindings": bindings,
        "citation_required_units": [
            {"claim_id": row["claim_id"]}
            for row in material_claims
            if row["evidence_policy"] == "citation_required"
        ],
        "completeness_units": completeness,
        "rubric_items": [],
        "failure_status": {"category": "none", "status_code": "scored", "retry_count": 0},
    }


def _find_whitespace_tolerant(report: str, quote: str) -> tuple[int, int] | None:
    """Find quote in report after whitespace normalization, returning raw span."""
    normalized_chars: list[str] = []
    raw_index: list[int] = []
    pending_space = False
    for index, char in enumerate(report):
        if char.isspace():
            pending_space = bool(normalized_chars)
            continue
        if pending_space:
            normalized_chars.append(" ")
            raw_index.append(index)
            pending_space = False
        normalized_chars.append(char)
        raw_index.append(index)
    normalized = "".join(normalized_chars)
    needle = " ".join(quote.split())
    found = normalized.find(needle)
    if found == -1:
        return None
    start_char = raw_index[found]
    end_norm = found + len(needle) - 1
    end_char = raw_index[end_norm] + 1
    return start_char, end_char


def exact_quote_packet(
    assets: PackageAssets,
    report: str,
    citations: list[dict[str, Any]],
    observations: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Build a judgment packet without any model call when frozen exact quotes hit.

    This is the deterministic floor of scoring: if the report contains a frozen
    evidence quote in the same paragraph as a legally observed citation to that
    page, code can prove the binding without asking a judge to re-read prose.
    Paraphrase-only content intentionally falls through to the narrow judge path.
    """
    claims: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    citations_by_url: dict[str, list[dict[str, Any]]] = {}
    for citation in citations:
        citations_by_url.setdefault(str(citation.get("url") or ""), []).append(citation)

    for evidence in assets.evidence_rows:
        evidence_id = str(evidence.get("evidence_id") or "")
        quote = str(evidence.get("quote") or "")
        url = str(evidence.get("canonical_url") or "")
        if not evidence_id or not quote or url not in assets.registry_by_url:
            continue
        quote_span = _find_whitespace_tolerant(report, quote)
        if quote_span is None:
            continue
        observation = observations.get(url) or {}
        if not (
            observation.get("observed")
            and observation.get("legally_discovered")
            and observation.get("observation_tier") in GROUNDING_TIERS
        ):
            continue
        quote_start, quote_end = quote_span
        report_quote = report[quote_start:quote_end]
        p_start, p_end = paragraph_bounds(report, quote_start)
        paragraph_citations = [
            row
            for row in citations_by_url.get(url, [])
            if p_start <= int(row["start"]) <= p_end
        ]
        if not paragraph_citations:
            continue
        claim_id = f"C{len(claims) + 1:03d}"
        citation_refs = [str(row["citation_ref"]) for row in paragraph_citations]
        claim = {
            "claim_id": claim_id,
            "exact_report_quote": report_quote,
            "normalized_claim": " ".join(quote.split()),
            "claim_kind": "external_atomic",
            "evidence_policy": "citation_required",
            "citation_refs": citation_refs,
            "quote_start": quote_start,
            "quote_end": quote_end,
            "paragraph_start": p_start,
            "paragraph_end": p_end,
            "verdict": "true",
            "support_evidence_ids": [evidence_id],
            "contradiction_evidence_ids": [],
            "materiality": "eligible",
            "eligible": True,
            "semantic_verdict": {
                "verdict": "true",
                "support_evidence_ids": [evidence_id],
                "reason_code": "exact_frozen_quote",
                "explanation": "Exact frozen evidence quote appears in the report paragraph.",
            },
        }
        claims.append(claim)
        for citation in paragraph_citations:
            binding_id = f"B{len(bindings) + 1:04d}"
            bindings.append(
                {
                    "binding_id": binding_id,
                    "claim_id": claim_id,
                    "citation_ref": citation["citation_ref"],
                    "url": url,
                    "same_paragraph": True,
                    "valid": True,
                    "observed": True,
                    "legally_discovered": True,
                    "observation_tier": observation.get("observation_tier"),
                    "page_content_sha256": observation.get("page_content_sha256"),
                    "observed_evidence_ids": [evidence_id],
                    "occurrence_index": 0,
                    "citation_id": citation["citation_ref"],
                    "bound": True,
                    "supports": True,
                    "support_verdict": "support",
                    "role_ok": True,
                    "complete_scope_observed": True,
                    "semantic_verdict": {
                        "bound": True,
                        "support_verdict": "support",
                        "role_ok": True,
                        "reason_code": "exact_frozen_quote",
                        "explanation": "Citation in the same paragraph points to the fetched frozen evidence page.",
                    },
                }
            )

    if not claims:
        return None

    grounded_claims = {row["claim_id"] for row in claims}
    unit_matches: dict[str, list[dict[str, Any]]] = {}
    for claim, evidence_id in zip(claims, [row["support_evidence_ids"][0] for row in claims]):
        unit_id = evidence_id.split(":", 1)[0]
        unit_matches.setdefault(unit_id, []).append(claim)
    completeness = []
    for source in assets.required_units:
        unit_id = str(source["information_unit_id"])
        matched = unit_matches.get(unit_id, [])
        quotes = [row["exact_report_quote"] for row in matched]
        content = bool(matched)
        completeness.append(
            {
                "unit_id": unit_id,
                "necessary": True,
                "applicable": True,
                "citation_required": bool(source.get("citation_required", True)),
                "public_description": source["public_description"],
                "content_covered": content,
                "matched_claim_ids": [row["claim_id"] for row in matched],
                "exact_quotes": quotes,
                "gate_truth_grounded_covered": content and all(
                    row["claim_id"] in grounded_claims for row in matched
                ),
                "semantic_verdict": {
                    "unit_id": unit_id,
                    "content_covered": content,
                    "matched_claim_ids": [row["claim_id"] for row in matched],
                    "exact_report_quotes": quotes,
                    "reason_code": "exact_frozen_quote" if content else "not_present",
                    "explanation": (
                        "Exact frozen evidence quote grounded this unit."
                        if content
                        else "No exact frozen evidence quote with a legal citation was found."
                    ),
                },
            }
        )

    return {
        "schema": "truth1000_biodiv_judgment_packet_v1",
        "material_claims": claims,
        "citation_bindings": bindings,
        "citation_required_units": [{"claim_id": row["claim_id"]} for row in claims],
        "completeness_units": completeness,
        "rubric_items": [],
        "failure_status": {"category": "none", "status_code": "scored", "retry_count": 0},
    }


def withheld_packet(error: ScoringError) -> dict[str, Any]:
    return {
        "schema": "truth1000_biodiv_judgment_packet_v1",
        "material_claims": [],
        "citation_bindings": [],
        "citation_required_units": [],
        "completeness_units": [],
        "rubric_items": [],
        "failure_status": {
            "category": error.category,
            "status_code": error.status_code,
            "retry_count": 0,
            "detail": str(error)[:1000],
        },
    }


def scored_zero_packet(assets: PackageAssets) -> dict[str, Any]:
    """Represent a normally completed empty answer with the frozen denominator.

    An empty model answer is a capability result, not an infrastructure
    failure.  Keeping all 34 completeness rows makes the GRR denominator
    explicit and auditable even though every numerator is zero.
    """
    return {
        "schema": "truth1000_biodiv_judgment_packet_v1",
        "material_claims": [],
        "citation_bindings": [],
        "citation_required_units": [],
        "completeness_units": [
            {
                "unit_id": row["information_unit_id"],
                "necessary": True,
                "applicable": True,
                "citation_required": bool(row.get("citation_required", True)),
                "public_description": row["public_description"],
                "content_covered": False,
                "matched_claim_ids": [],
                "exact_quotes": [],
                "gate_truth_grounded_covered": False,
                "semantic_verdict": {
                    "unit_id": row["information_unit_id"],
                    "content_covered": False,
                    "matched_claim_ids": [],
                    "exact_report_quotes": [],
                    "explanation": "The normally completed report was empty.",
                },
            }
            for row in assets.required_units
        ],
        "rubric_items": [],
        "failure_status": {
            "category": "report",
            "status_code": "scored_zero_normal_empty_report",
            "retry_count": 0,
        },
    }


def verify_run_manifest(path: Path, report_path: Path, run_id: str) -> dict[str, Any]:
    if not path.is_file():
        raise ObservabilityError(f"run manifest is missing: {path}")
    manifest = read_json(path)
    recorded_run_id = str(manifest.get("run_id") or "")
    if recorded_run_id and recorded_run_id != run_id:
        raise ObservabilityError("run manifest ID differs from scoring run ID")
    execution = manifest.get("execution") if isinstance(manifest.get("execution"), dict) else {}
    outcome = str(execution.get("outcome") or manifest.get("outcome") or "").lower()
    completed = manifest.get("completed") is True or str(manifest.get("status") or "").lower() == "completed"
    failure = manifest.get("failure")
    normal = completed and outcome in {"pass", "success", "completed"} and not failure
    recorded_sha = manifest.get("report_sha256")
    if recorded_sha and report_path.is_file() and recorded_sha != sha256_file(report_path):
        raise ObservabilityError("run manifest report SHA differs from delivered report")
    return {
        "manifest_sha256": sha256_file(path),
        "completed": completed,
        "outcome": outcome,
        "failure": failure,
        "normal_completion_attested": normal,
    }


def run_semantic_pipeline(
    assets: PackageAssets,
    report: str,
    ledger_path: Path,
    judge: JsonJudge,
) -> tuple[dict[str, Any], dict[str, Any]]:
    citations = canonicalize_citation_urls(extract_citations(report), assets)
    ledger_rows = read_ledger(ledger_path)
    observations = reconstruct_observations(ledger_rows, ledger_path, assets)
    registry_citation_count = sum(
        1 for citation in citations if citation.get("url") in assets.registry_by_url
    )
    deterministic_preflight = {
        "citation_count": len(citations),
        "registry_citation_count": registry_citation_count,
        "observed_url_count": len(observations),
        "required_unit_count": len(assets.required_units),
    }
    exact_packet = exact_quote_packet(assets, report, citations, observations)
    if exact_packet is not None:
        return exact_packet, {
            **deterministic_preflight,
            "claim_count": len(exact_packet["material_claims"]),
            "binding_candidate_count": len(exact_packet["citation_bindings"]),
            "short_circuit": "exact_frozen_quote",
        }
    if not citations:
        packet = scored_zero_packet(assets)
        return packet, {
            **deterministic_preflight,
            "claim_count": 0,
            "binding_candidate_count": 0,
            "short_circuit": "no_citations",
        }
    if registry_citation_count == 0:
        packet = scored_zero_packet(assets)
        return packet, {
            **deterministic_preflight,
            "claim_count": 0,
            "binding_candidate_count": 0,
            "short_circuit": "no_registered_citation",
        }
    if hasattr(judge, "ensure_available"):
        judge.ensure_available(len(partition_report(report, citations)))
    claim_response, claim_batch_diagnostics = extract_claims_batched(
        assets, report, citations, judge
    )
    claims = normalize_claims(claim_response, report, citations)
    candidates = build_binding_candidates(claims, citations, observations, assets)
    if hasattr(judge, "ensure_available"):
        claim_batches = (
            (len(claims) + ADJUDICATION_CLAIM_BATCH_SIZE - 1) // ADJUDICATION_CLAIM_BATCH_SIZE
            if claims
            else 0
        )
        unit_batches = (
            len(assets.required_units) + ADJUDICATION_UNIT_BATCH_SIZE - 1
        ) // ADJUDICATION_UNIT_BATCH_SIZE
        judge.ensure_available(claim_batches + unit_batches)
    adjudication, adjudication_batch_diagnostics = adjudicate_batched(
        report, claims, candidates, assets, judge
    )
    packet = compile_packet(report, claims, candidates, adjudication, assets)
    diagnostics = {
        **deterministic_preflight,
        "citation_count": len(citations),
        "claim_count": len(claims),
        "repaired_claim_quote_count": claim_batch_diagnostics["repaired_claim_quote_count"],
        "binding_candidate_count": len(candidates),
        "observed_url_count": len(observations),
        "required_unit_count": len(assets.required_units),
        "claim_extraction_batching": claim_batch_diagnostics,
        "adjudication_batching": adjudication_batch_diagnostics,
    }
    return packet, diagnostics


def load_aggregator(path: Path):
    spec = importlib.util.spec_from_file_location("biodiv_packet_aggregator", path)
    if spec is None or spec.loader is None:
        raise ScoringError("cannot load deterministic packet aggregator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "aggregate", None)):
        raise ScoringError("packet aggregator lacks aggregate()")
    return module.aggregate


def seal_tree(output_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.json":
            continue
        rows.append(
            {
                "path": str(path.relative_to(output_dir)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    write_json(output_dir / "SHA256SUMS.json", {"schema": "sha256_inventory_v1", "files": rows})
    return rows


def judge_usage_summary(judge_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if judge_root.is_dir():
        for path in sorted(judge_root.glob("*/metadata.json")):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(row, dict):
                rows.append(row)
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
    }
    for row in rows:
        usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
        details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
        input_details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
        completion_details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
        output_details = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}
        prompt_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
        completion_tokens = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
        totals["prompt_tokens"] += prompt_tokens
        totals["completion_tokens"] += completion_tokens
        totals["total_tokens"] += int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0)
        totals["cached_tokens"] += int(
            details.get("cached_tokens", input_details.get("cached_tokens", usage.get("cached_tokens", 0))) or 0
        )
        totals["cache_write_tokens"] += int(
            details.get(
                "cache_write_tokens",
                details.get(
                    "cache_creation_input_tokens",
                    input_details.get(
                        "cache_write_tokens",
                        usage.get("cache_write_tokens", usage.get("cache_creation_input_tokens", 0)),
                    ),
                ),
            )
            or 0
        )
        totals["reasoning_tokens"] += int(
            completion_details.get(
                "reasoning_tokens",
                output_details.get("reasoning_tokens", usage.get("reasoning_tokens", 0)),
            )
            or 0
        )
    successful = [row for row in rows if row.get("http_status") == 200]
    return {
        "attempt_count": len(rows),
        "successful_http_200_count": len(successful),
        "actual_response_models": sorted(
            {
                str(row["actual_response_model"])
                for row in rows
                if row.get("actual_response_model")
            }
        ),
        "identity_all_match": bool(successful) and all(
            bool(row.get("identity_match")) for row in successful
        ),
        "tokens": totals,
    }


def execute(
    *,
    package_dir: Path,
    report_path: Path,
    ledger_path: Path,
    run_manifest_path: Path,
    output_dir: Path,
    judge: JsonJudge,
    run_id: str,
    judge_config: dict[str, Any],
    aggregator_path: Path | None = None,
    scorer_root: Path | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    assets = PackageAssets.load(package_dir)
    budgeted_judge = BudgetedJudge(judge, judge_config)
    run_integrity = verify_run_manifest(run_manifest_path, report_path, run_id)
    if not report_path.is_file():
        error: ScoringError = ObservabilityError("agent report is missing")
        packet = withheld_packet(error)
        diagnostics: dict[str, Any] = {}
    else:
        report = report_path.read_text(encoding="utf-8")
        if not run_integrity["normal_completion_attested"]:
            error = ObservabilityError("run manifest does not attest a normal completed agent return")
            packet = withheld_packet(error)
            diagnostics = {}
        elif not report.strip():
            if run_integrity["normal_completion_attested"]:
                packet = scored_zero_packet(assets)
                diagnostics = {"claim_count": 0, "required_unit_count": len(assets.required_units)}
        else:
            try:
                packet, diagnostics = run_semantic_pipeline(assets, report, ledger_path, budgeted_judge)
            except ScoringError as exc:
                packet = withheld_packet(exc)
                diagnostics = {}
    judge_audit = judge_usage_summary(output_dir / "judge-calls")
    packet["report_integrity"] = {
        **run_integrity,
        "report_present": report_path.is_file(),
        "report_nonempty": report_path.is_file() and bool(report_path.read_text(encoding="utf-8").strip()),
        "report_sha256": sha256_file(report_path) if report_path.is_file() else None,
        "report_bytes": report_path.stat().st_size if report_path.is_file() else 0,
    }
    packet["asset_freeze"] = {
        "package_manifest_sha256": sha256_file(assets.manifest_path),
        "required_unit_count": len(assets.required_units),
        "evidence_row_count": len(assets.evidence_rows),
        "url_count": len(assets.registry_by_url),
    }
    packet["judge_audit"] = judge_audit
    packet_path = output_dir / "judgment-packet.json"
    write_json(packet_path, packet)
    protocol = {
        "schema": "truth1000_biodiv_automatic_scoring_protocol_v1",
        "run_id": run_id,
        "started_utc": started,
        "package_manifest_sha256": sha256_file(assets.manifest_path),
        "report_sha256": sha256_file(report_path) if report_path.is_file() else None,
        "ledger_sha256": sha256_file(ledger_path) if ledger_path.is_file() else None,
        "implementation_sha256": sha256_file(Path(__file__)),
        "prompt_sha256": {
            "claim_extractor": sha256_file(CLAIM_PROMPT),
            "claim_quote_repair": sha256_file(CLAIM_REPAIR_PROMPT),
            "claim_binding_adjudicator": sha256_file(CLAIM_BINDING_PROMPT),
            "completeness_adjudicator": sha256_file(COMPLETENESS_PROMPT),
        },
        "schema_sha256": {
            "claim_extractor": sha256_file(CLAIM_SCHEMA),
            "claim_extractor_batch": sha256_file(CLAIM_BATCH_SCHEMA),
            "claim_quote_repair": sha256_file(CLAIM_REPAIR_SCHEMA),
            "claim_binding_adjudicator": sha256_file(CLAIM_BINDING_SCHEMA),
            "completeness_adjudicator": sha256_file(COMPLETENESS_SCHEMA),
            "adjudication_merged": sha256_file(ADJUDICATION_SCHEMA),
        },
        "judge": {
            key: value
            for key, value in judge_config.items()
            if key != "credential"
        },
        "judge_usage": judge_audit,
        "diagnostics": diagnostics,
        "manual_claim_or_unit_judgments": 0,
        "formal_eligible": False,
        "release_mode": "shadow",
    }
    write_json(output_dir / "protocol-manifest.json", protocol)
    score = None
    if aggregator_path is not None and scorer_root is not None:
        aggregate = load_aggregator(aggregator_path)
        score = aggregate(package_dir, scorer_root, packet_path)
        write_json(output_dir / "shadow-score.json", score)
    receipt = {
        "schema": "truth1000_biodiv_automatic_scoring_receipt_v1",
        "run_id": run_id,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "status": "WITHHELD" if str(packet["failure_status"]["status_code"]).startswith("withheld") else "SCORED",
        "failure_status": packet["failure_status"],
        "judgment_packet_sha256": sha256_file(packet_path),
        "shadow_score_sha256": sha256_file(output_dir / "shadow-score.json") if score is not None else None,
        "formal_eligible": False,
        "manual_judgments": 0,
        "judge_usage": protocol["judge_usage"],
    }
    write_json(output_dir / "run-receipt.json", receipt)
    seal_tree(output_dir)
    return {"packet": packet, "score": score, "receipt": receipt}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--run-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--judge-config", required=True, type=Path)
    parser.add_argument("--aggregator", type=Path)
    parser.add_argument("--scorer-root", type=Path)
    args = parser.parse_args()
    config = read_json(args.judge_config)
    judge = AdamsOpenAIJudge(args.output_dir / "judge-calls", config, args.run_id)
    result = execute(
        package_dir=args.package_dir,
        report_path=args.report,
        ledger_path=args.ledger,
        run_manifest_path=args.run_manifest,
        output_dir=args.output_dir,
        judge=judge,
        run_id=args.run_id,
        judge_config=config,
        aggregator_path=args.aggregator,
        scorer_root=args.scorer_root,
    )
    print(json.dumps(result["receipt"], ensure_ascii=False, indent=2))
    return 0 if result["receipt"]["status"] == "SCORED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
