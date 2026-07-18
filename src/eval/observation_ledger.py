"""Normalized, replayable observations for DRA v3.

The verified-slot scorer is deliberately forbidden from fetching a cited page
after a run.  This module is therefore the boundary between a harness trace and
the scorer: it records *exactly* the snippets/bodies/links which were visible to
the agent, checks that their attribution and ordering are sound, and fails
closed when that cannot be established.

``ObservationLedger`` accepts the v1 schema described in
``DRA_V3_EVIDENCE_GRAPH_REDESIGN_PLAN_2026-07-15.md``.  A small adapter for the
legacy ``RunEvidence`` JSONL format is included to make pilot migration
possible.  Legacy search records license discovery but, because they did not
store snippets, can never support a claim from snippet text.

No function in this module performs network I/O.
"""

from __future__ import annotations

import hashlib
import html.parser
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional
from urllib.parse import urljoin

from src.verifiers.citation_format import canonicalize_url


OBSERVATION_SEMANTICS = "observation_ledger_v1"
EVENT_TYPES = frozenset(
    {"search_result", "fetch_body", "extracted_body", "page_link"}
)
CONTENT_EVENT_TYPES = frozenset(
    {"search_result", "fetch_body", "extracted_body"}
)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _canonical(url: Any) -> str:
    raw = str(url or "").strip()
    return canonicalize_url(raw) if raw else ""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def _timestamp_key(value: Any) -> Optional[float]:
    """Return a comparable timestamp, accepting unix numbers and ISO-8601."""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            number = float(text)
            return number if math.isfinite(number) else None
        except ValueError:
            pass
        try:
            # ``fromisoformat`` does not accept a trailing Z before Python 3.11.
            parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
            return parsed.timestamp()
        except (ValueError, OverflowError):
            return None
    return None


def _coerce_content(raw: Any) -> tuple[Optional[str], Optional[str]]:
    """Split the schema's text-or-blob field into unambiguous components."""

    if raw is None:
        return None, None
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace"), None
    if isinstance(raw, Mapping):
        text = raw.get("text")
        if text is None:
            text = raw.get("content_text")
        blob = raw.get("blob_ref") or raw.get("content_blob_ref")
        return (None if text is None else str(text), None if blob is None else str(blob))
    # A plain string is inline text.  Blob references should use ``blob_ref`` or
    # the object form above; guessing based on a string prefix is not auditable.
    return str(raw), None


@dataclass(frozen=True)
class LedgerIssue:
    """One stable reason the ledger is incomplete or malformed."""

    code: str
    message: str
    event_id: Optional[int] = None
    fatal: bool = True

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "fatal": self.fatal,
        }
        if self.event_id is not None:
            out["event_id"] = self.event_id
        return out


@dataclass
class ObservationEvent:
    """One normalized observation delivered to the agent."""

    run_id: str
    event_id: int
    timestamp: Any
    event_type: str
    request_url: str = ""
    canonical_url: str = ""
    parent_event_id: Optional[int] = None
    content_sha256: str = ""
    content_text: Optional[str] = None
    blob_ref: Optional[str] = None
    http_status: Optional[int] = None
    observable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.run_id = str(self.run_id or "").strip()
        self.event_type = str(self.event_type or "").strip()
        self.request_url = str(self.request_url or "").strip()
        self.canonical_url = _canonical(self.canonical_url or self.request_url)
        # Do not coerce schema values here.  ``bool`` is an ``int`` subclass,
        # ``int(1.5)`` silently truncates, and ``bool("false")`` is True.  A
        # formal evidence ledger must make malformed values visible instead of
        # laundering them into plausible ones.
        self.content_sha256 = str(self.content_sha256 or "").strip().lower()
        if self.content_text is not None:
            self.content_text = str(self.content_text)
        if self.blob_ref is not None:
            self.blob_ref = str(self.blob_ref)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, default_event_id: int = 0) -> "ObservationEvent":
        combined = raw.get("content_text_or_blob_ref")
        text, blob = _coerce_content(combined)
        if raw.get("content_text") is not None:
            text = str(raw.get("content_text"))
        elif raw.get("snippet") is not None and raw.get("event_type") == "search_result":
            text = str(raw.get("snippet"))
        elif raw.get("body") is not None:
            body = raw.get("body")
            text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
        blob = raw.get("blob_ref") or raw.get("content_blob_ref") or blob
        known = {
            "run_id", "event_id", "timestamp", "ts", "event_type",
            "request_url", "canonical_url", "url", "parent_event_id",
            "content_sha256", "body_sha256", "content_text_or_blob_ref",
            "content_text", "content_blob_ref", "blob_ref", "body", "snippet",
            "http_status", "status", "observable", "metadata",
        }
        metadata = {str(k): v for k, v in raw.items() if k not in known}
        declared_metadata = raw.get("metadata")
        if isinstance(declared_metadata, Mapping):
            metadata.update({str(k): v for k, v in declared_metadata.items()})
        return cls(
            run_id=str(raw.get("run_id") or ""),
            event_id=raw.get("event_id", default_event_id),
            timestamp=raw.get("timestamp", raw.get("ts")),
            event_type=str(raw.get("event_type") or ""),
            request_url=str(raw.get("request_url") or raw.get("url") or ""),
            canonical_url=str(raw.get("canonical_url") or raw.get("url") or ""),
            parent_event_id=raw.get("parent_event_id"),
            content_sha256=str(raw.get("content_sha256") or raw.get("body_sha256") or ""),
            content_text=text,
            blob_ref=None if blob is None else str(blob),
            http_status=raw.get("http_status", raw.get("status")),
            observable=raw.get("observable", True),
            metadata=metadata,
        )

    def content_bytes(self, blob_loader: Any = None) -> Optional[bytes]:
        if self.content_text is not None:
            return self.content_text.encode("utf-8")
        if not self.blob_ref or blob_loader is None:
            return None
        try:
            if callable(blob_loader):
                value = blob_loader(self.blob_ref)
            elif isinstance(blob_loader, Mapping):
                value = blob_loader.get(self.blob_ref)
            else:
                value = (Path(blob_loader) / self.blob_ref).read_bytes()
        except (OSError, TypeError, ValueError):
            return None
        if value is None:
            return None
        return value if isinstance(value, bytes) else str(value).encode("utf-8")

    def visible_text(self, blob_loader: Any = None) -> Optional[str]:
        if self.content_text is not None:
            return self.content_text
        value = self.content_bytes(blob_loader)
        return None if value is None else value.decode("utf-8", "replace")

    def to_dict(self) -> dict[str, Any]:
        content: Any
        if self.content_text is not None and self.blob_ref is not None:
            content = {"text": self.content_text, "blob_ref": self.blob_ref}
        elif self.content_text is not None:
            content = self.content_text
        else:
            content = {"blob_ref": self.blob_ref} if self.blob_ref else None
        out = {
            "run_id": self.run_id,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "request_url": self.request_url,
            "canonical_url": self.canonical_url,
            "parent_event_id": self.parent_event_id,
            "content_sha256": self.content_sha256,
            "content_text_or_blob_ref": content,
            "http_status": self.http_status,
            "observable": self.observable,
        }
        if self.metadata:
            out["metadata"] = dict(self.metadata)
        return out


@dataclass
class ObservationLedger:
    """Validated chronological observation trace for one and only one run."""

    run_id: Optional[str]
    events: list[ObservationEvent] = field(default_factory=list)
    issues: list[LedgerIssue] = field(default_factory=list)
    # An empty trace is not necessarily missing: a silent agent can complete a
    # run without making one search/fetch.  The envelope must explicitly attest
    # capture completeness to distinguish that observed zero from blindness.
    capture_complete: bool = False
    observation_semantics: str = OBSERVATION_SEMANTICS
    blob_loader: Any = field(default=None, repr=False, compare=False)

    @property
    def complete(self) -> bool:
        return self.capture_complete and not any(issue.fatal for issue in self.issues)

    @property
    def available(self) -> bool:
        return self.complete

    @property
    def withhold_reason_codes(self) -> list[str]:
        return [issue.code for issue in self.issues if issue.fatal]

    def by_id(self) -> dict[int, ObservationEvent]:
        return {event.event_id: event for event in self.events}

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_semantics": self.observation_semantics,
            "run_id": self.run_id,
            "capture_complete": self.capture_complete,
            "complete": self.complete,
            "issues": [issue.to_dict() for issue in self.issues],
            "events": [event.to_dict() for event in self.events],
        }

    @classmethod
    def from_records(
        cls,
        records: Iterable[Mapping[str, Any] | ObservationEvent],
        *,
        expected_run_id: Optional[str] = None,
        blob_loader: Any = None,
        extra_issues: Optional[Iterable[LedgerIssue]] = None,
        capture_complete: bool = False,
    ) -> "ObservationLedger":
        events: list[ObservationEvent] = []
        issues = list(extra_issues or [])
        for index, raw in enumerate(records, 1):
            if isinstance(raw, ObservationEvent):
                events.append(raw)
            elif isinstance(raw, Mapping):
                events.append(ObservationEvent.from_dict(raw, default_event_id=index))
            else:
                issues.append(LedgerIssue(
                    "invalid_observation_record",
                    f"record {index} is not an object",
                ))

        run_ids = {event.run_id for event in events if event.run_id}
        run_id = next(iter(run_ids)) if len(run_ids) == 1 else expected_run_id
        ledger = cls(
            run_id=run_id,
            events=events,
            issues=issues,
            capture_complete=(capture_complete is True),
            blob_loader=blob_loader,
        )
        ledger._validate(expected_run_id=expected_run_id)
        return ledger

    @classmethod
    def unavailable(cls, code: str, message: str, *, run_id: Optional[str] = None) -> "ObservationLedger":
        return cls(
            run_id=run_id,
            issues=[LedgerIssue(code, message)],
            capture_complete=False,
        )

    def _add(self, code: str, message: str, event_id: Optional[int] = None) -> None:
        key = (code, event_id)
        if not any((issue.code, issue.event_id) == key for issue in self.issues):
            self.issues.append(LedgerIssue(code, message, event_id))

    def _validate(self, *, expected_run_id: Optional[str] = None) -> None:
        if not self.capture_complete:
            self._add(
                "observation_capture_incomplete",
                "ledger envelope does not attest capture_complete=true",
            )
        if not self.events:
            if not (self.run_id or expected_run_id):
                self._add(
                    "observation_missing_run_id",
                    "an empty complete trace still requires an attributable run_id",
                )
            elif expected_run_id is not None and self.run_id not in (None, str(expected_run_id)):
                self._add(
                    "observation_run_id_mismatch",
                    f"ledger run_id {self.run_id!r} does not match expected {expected_run_id!r}",
                )
            # A complete empty trace is a valid observation of agent silence.
            return

        run_ids = {event.run_id for event in self.events if event.run_id}
        if any(not event.run_id for event in self.events):
            self._add("observation_missing_run_id", "one or more events have no run_id")
        if len(run_ids) > 1:
            self._add("observation_multiple_run_ids", "events are attributed to multiple run_id values")
        elif run_ids:
            actual = next(iter(run_ids))
            self.run_id = actual
            if expected_run_id is not None and actual != str(expected_run_id):
                self._add(
                    "observation_run_id_mismatch",
                    f"ledger run_id {actual!r} does not match expected {expected_run_id!r}",
                )

        seen: dict[int, ObservationEvent] = {}
        previous_id: Optional[int] = None
        previous_timestamp: Optional[float] = None
        for event in self.events:
            eid = event.event_id
            if event.event_type not in EVENT_TYPES:
                self._add("observation_invalid_event_type", f"unsupported event type {event.event_type!r}", eid)
            valid_eid = type(eid) is int and eid >= 0
            if not valid_eid:
                self._add("observation_invalid_event_id", "event_id must be a non-negative JSON integer")
                # A synthetic key keeps validation running without treating a
                # malformed ID as a real parent target.
                eid_key = -(len(seen) + 1)
            else:
                eid_key = eid
            if eid_key in seen:
                self._add("observation_duplicate_event_id", f"event_id {eid} occurs more than once", eid)
            if valid_eid and previous_id is not None and eid <= previous_id:
                self._add("observation_non_monotonic_event_order", "event_id values must strictly increase in log order", eid)
            seen[eid_key] = event
            if valid_eid:
                previous_id = eid

            stamp = _timestamp_key(event.timestamp)
            if stamp is None:
                self._add("observation_invalid_timestamp", "event has no valid timestamp", eid)
            elif previous_timestamp is not None and stamp < previous_timestamp:
                self._add("observation_non_monotonic_timestamp", "timestamps must be non-decreasing", eid)
            if stamp is not None:
                previous_timestamp = stamp

            if not event.canonical_url:
                self._add("observation_missing_url", "event has no canonical URL", eid)
            if type(event.observable) is not bool:
                self._add("observation_invalid_observable", "observable must be a JSON boolean", eid if valid_eid else None)
            elif not event.observable:
                self._add("observation_not_observable", "event was not observable to the agent", eid)
            if event.event_type in {"fetch_body", "extracted_body"}:
                if type(event.http_status) is not int:
                    self._add("observation_missing_http_status", "body event http_status must be a JSON integer", eid if valid_eid else None)
                elif event.http_status != 200:
                    # A failed request is useful diagnostics but is not visible
                    # support.  It does not make a correctly captured ledger
                    # blind, so this issue is intentionally non-fatal.
                    self.issues.append(LedgerIssue(
                        "observation_fetch_non_200",
                        f"body event returned HTTP {event.http_status}",
                        eid,
                        fatal=False,
                    ))

            if event.event_type in CONTENT_EVENT_TYPES:
                if event.blob_ref and (
                    event.blob_ref in {".", ".."}
                    or ".." in Path(event.blob_ref).parts
                    or Path(event.blob_ref).is_absolute()
                    or "/" in event.blob_ref
                    or "\\" in event.blob_ref
                ):
                    self._add("observation_invalid_blob_ref", "blob_ref must be a safe content-addressed filename", eid if valid_eid else None)
                    content = None
                else:
                    content = event.content_bytes(self.blob_loader)
                # Empty legacy search snippets are allowed: those events still
                # license URL discovery, just not claim observation.
                legacy_no_snippet = (
                    event.event_type == "search_result"
                    and event.metadata.get("legacy_snippet_unavailable")
                )
                if content is None and not legacy_no_snippet:
                    self._add("observation_content_unavailable", "observable content bytes cannot be loaded", eid)
                elif content is not None:
                    if not event.content_sha256:
                        self._add("observation_missing_content_hash", "content-bearing event has no sha256", eid)
                    elif sha256_bytes(content) != event.content_sha256:
                        self._add("observation_content_hash_mismatch", "content bytes do not match content_sha256", eid)

        for event in self.events:
            parent_id = event.parent_event_id
            if parent_id is None:
                continue
            if type(parent_id) is not int or parent_id < 0:
                self._add("observation_invalid_parent_id", "parent_event_id must be a non-negative JSON integer", event.event_id if type(event.event_id) is int else None)
                continue
            parent = seen.get(parent_id)
            if parent is None:
                self._add("observation_parent_missing", f"parent_event_id {parent_id} does not exist", event.event_id)
                continue
            if (
                type(parent.event_id) is int
                and type(event.event_id) is int
                and parent.event_id >= event.event_id
            ):
                self._add("observation_parent_not_prior", "parent event must precede its child", event.event_id)
            if event.event_type == "page_link" and parent.event_type not in {"fetch_body", "extracted_body"}:
                self._add("observation_invalid_link_parent", "page_link parent must be fetched/extracted body", event.event_id)
            elif event.event_type == "page_link":
                parent_text = parent.visible_text(self.blob_loader)
                recorded_links = parent.metadata.get("links") or []
                visible_links = {_canonical(url) for url in recorded_links if url}
                if parent_text is not None:
                    visible_links.update(_links_in_body(parent_text, parent.canonical_url))
                if event.canonical_url not in visible_links:
                    self._add(
                        "observation_link_not_in_parent",
                        "page_link target is not present in its parent observation",
                        event.event_id,
                    )
            if event.event_type == "extracted_body" and parent.event_type not in {"fetch_body", "search_result", "page_link"}:
                self._add("observation_invalid_extract_parent", "extracted_body parent has an invalid type", event.event_id)


def _default_blob_loader(log_path: Path) -> Callable[[str], Optional[bytes]]:
    blob_dir = log_path.parent / "blobs"

    def load(ref: str) -> Optional[bytes]:
        if (
            ref in {".", ".."}
            or ".." in Path(ref).parts
            or Path(ref).is_absolute()
            or "/" in ref
            or "\\" in ref
        ):
            return None
        try:
            return (blob_dir / ref).read_bytes()
        except OSError:
            return None

    return load


class _HrefParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def _links_in_body(text: str, base_url: str) -> set[str]:
    parser = _HrefParser()
    try:
        parser.feed(text)
    except Exception:
        pass
    return {_canonical(urljoin(base_url, href)) for href in parser.hrefs if href}


def _legacy_search_snippets(record: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in ("results", "search_results", "organic", "hits"):
        rows = record.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            url = row.get("url") or row.get("link")
            snippet = row.get("snippet") or row.get("content") or row.get("text")
            if url and snippet is not None:
                out[_canonical(url)] = str(snippet)
    return out


def adapt_legacy_records(
    records: Iterable[Mapping[str, Any]],
    *,
    expected_run_id: Optional[str] = None,
    blob_loader: Any = None,
) -> ObservationLedger:
    """Convert legacy shim ``mark/search/fetch`` records to ledger v1.

    Start/end bracket checks are retained.  Generated ``page_link`` events are
    children of the exact successful body event which exposed the link.
    """

    raw = [dict(record) for record in records]
    issues: list[LedgerIssue] = []
    legacy_run_ids = {str(record.get("run_id")) for record in raw if record.get("run_id")}
    if len(legacy_run_ids) > 1:
        issues.append(LedgerIssue(
            "observation_multiple_run_ids",
            "legacy evidence log is attributed to multiple run_id values",
        ))
    effective_run_id = (
        str(expected_run_id) if expected_run_id is not None
        else (next(iter(legacy_run_ids)) if len(legacy_run_ids) == 1 else None)
    )
    starts = [r for r in raw if r.get("kind") == "mark" and r.get("phase") == "start"]
    ends = [r for r in raw if r.get("kind") == "mark" and r.get("phase") == "end"]
    if len(starts) != 1:
        issues.append(LedgerIssue(
            "legacy_missing_start_mark" if not starts else "legacy_multiple_start_marks",
            "legacy evidence log must contain exactly one start mark",
        ))
    if len(ends) != 1:
        issues.append(LedgerIssue(
            "legacy_missing_end_mark" if not ends else "legacy_multiple_end_marks",
            "legacy evidence log must contain exactly one end mark",
        ))
    if ends and ends[0].get("orphaned"):
        issues.append(LedgerIssue("legacy_orphaned_bracket", "legacy run bracket was orphaned"))

    normalized: list[ObservationEvent] = []
    next_id = 1
    ended = False
    for record in raw:
        kind = record.get("kind")
        if kind == "mark":
            if record.get("phase") == "end":
                ended = True
            continue
        if kind not in {"search", "fetch", "block"}:
            continue
        if ended:
            issues.append(LedgerIssue("legacy_traffic_after_end", "legacy evidence has traffic after end mark"))
        if kind == "block":
            continue
        run_id = str(record.get("run_id") or effective_run_id or "")
        ts = record.get("ts")
        if kind == "search":
            snippets = _legacy_search_snippets(record)
            urls = list(record.get("urls_returned") or [])
            for url in urls:
                snippet = snippets.get(_canonical(url))
                normalized.append(ObservationEvent(
                    run_id=run_id,
                    event_id=next_id,
                    timestamp=ts,
                    event_type="search_result",
                    request_url=str(record.get("endpoint") or ""),
                    canonical_url=str(url),
                    content_text=snippet,
                    content_sha256=sha256_text(snippet) if snippet is not None else "",
                    observable=True,
                    metadata={
                        "legacy_kind": "search",
                        "query": record.get("query"),
                        "legacy_snippet_unavailable": snippet is None,
                    },
                ))
                next_id += 1
        elif kind == "fetch":
            endpoint = str(record.get("endpoint") or "")
            event_type = "extracted_body" if "extract" in endpoint.lower() else "fetch_body"
            digest = str(record.get("body_sha256") or "")
            body_event = ObservationEvent(
                run_id=run_id,
                event_id=next_id,
                timestamp=ts,
                event_type=event_type,
                request_url=str(record.get("url") or ""),
                canonical_url=str(record.get("url") or ""),
                content_sha256=digest,
                blob_ref=digest or None,
                http_status=record.get("status"),
                observable=bool(record.get("fetch_observable", True)),
                metadata={"legacy_kind": "fetch", "endpoint": endpoint},
            )
            body_event.metadata["links"] = list(record.get("links") or [])
            normalized.append(body_event)
            body_id = next_id
            next_id += 1
            for link in record.get("links") or []:
                normalized.append(ObservationEvent(
                    run_id=run_id,
                    event_id=next_id,
                    timestamp=ts,
                    event_type="page_link",
                    request_url=body_event.canonical_url,
                    canonical_url=str(link),
                    parent_event_id=body_id,
                    content_text=str(link),
                    content_sha256=sha256_text(str(link)),
                    observable=body_event.observable,
                    metadata={"legacy_kind": "fetch_link"},
                ))
                next_id += 1

    return ObservationLedger.from_records(
        normalized,
        expected_run_id=effective_run_id,
        blob_loader=blob_loader,
        extra_issues=issues,
        capture_complete=True,
    )


def adapt_run_evidence(
    evidence: Any,
    *,
    expected_run_id: Optional[str] = None,
    blob_loader: Any = None,
) -> ObservationLedger:
    """Best-effort adapter for an in-memory legacy ``RunEvidence`` object."""

    if evidence is None or not bool(_field(evidence, "available", False)):
        reason = str(_field(evidence, "unavailable_reason", "no evidence log") or "no evidence log")
        return ObservationLedger.unavailable("no_observation_ledger", reason, run_id=expected_run_id)
    records: list[dict[str, Any]] = []
    rid = str(_field(evidence, "run_id", None) or expected_run_id or "")
    # Synthetic marks let the common adapter enforce all remaining invariants.
    t_start = _field(evidence, "t_start", None)
    t_end = _field(evidence, "t_end", None)
    if t_start is None or t_end is None:
        return ObservationLedger.unavailable(
            "legacy_order_unavailable",
            "RunEvidence lacks start/end timestamps, so event order cannot be replayed",
            run_id=rid or None,
        )
    records.append({"kind": "mark", "phase": "start", "run_id": rid, "ts": t_start})
    records.extend(dict(row) for row in (_field(evidence, "searches", []) or []))
    records.extend(dict(row) for row in (_field(evidence, "fetched", {}) or {}).values())
    middle = [row for row in records[1:] if _timestamp_key(row.get("ts")) is not None]
    if len(middle) != len(records) - 1:
        return ObservationLedger.unavailable(
            "legacy_order_unavailable",
            "RunEvidence records lack timestamps, so event order cannot be replayed",
            run_id=rid or None,
        )
    middle.sort(key=lambda row: float(_timestamp_key(row.get("ts")) or 0.0))
    records = records[:1] + middle
    records.append({"kind": "mark", "phase": "end", "run_id": rid, "ts": t_end})
    return adapt_legacy_records(
        records,
        expected_run_id=expected_run_id,
        blob_loader=blob_loader,
    )


def load_observation_ledger(
    path: str | Path,
    *,
    expected_run_id: Optional[str] = None,
    blob_loader: Any = None,
    allow_legacy: bool = True,
) -> ObservationLedger:
    """Load a JSON/JSONL ledger, validating attribution, hashes and parents."""

    source = Path(path)
    if not source.exists():
        return ObservationLedger.unavailable(
            "no_observation_ledger",
            f"observation ledger does not exist: {source}",
            run_id=expected_run_id,
        )
    if blob_loader is None:
        blob_loader = _default_blob_loader(source)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        return ObservationLedger.unavailable(
            "observation_ledger_unreadable", str(exc), run_id=expected_run_id
        )
    if not text.strip():
        return ObservationLedger.unavailable(
            "empty_observation_ledger", "observation ledger is empty", run_id=expected_run_id
        )

    records: list[Any]
    capture_complete = False
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        records = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                return ObservationLedger.unavailable(
                    "observation_ledger_damaged",
                    f"invalid JSON on line {line_number}: {exc}",
                    run_id=expected_run_id,
                )
    else:
        if isinstance(parsed, Mapping):
            if "events" not in parsed or not isinstance(parsed.get("events"), list):
                return ObservationLedger.unavailable(
                    "observation_events_missing",
                    "native ledger envelope requires an explicit events array",
                    run_id=expected_run_id,
                )
            records = list(parsed.get("events") or [])
            declared = parsed.get("observation_semantics")
            if declared != OBSERVATION_SEMANTICS:
                return ObservationLedger.unavailable(
                    "observation_semantics_mismatch",
                    f"native ledger requires observation_semantics={OBSERVATION_SEMANTICS!r}; got {declared!r}",
                    run_id=expected_run_id,
                )
            declared_run_id = parsed.get("run_id")
            if not isinstance(declared_run_id, str) or not declared_run_id.strip():
                return ObservationLedger.unavailable(
                    "observation_missing_run_id",
                    "native ledger envelope requires a non-empty run_id",
                    run_id=expected_run_id,
                )
            if (
                expected_run_id is not None
                and declared_run_id != str(expected_run_id)
            ):
                return ObservationLedger.unavailable(
                    "observation_run_id_mismatch",
                    f"ledger run_id {declared_run_id!r} does not match expected "
                    f"{expected_run_id!r}",
                    run_id=declared_run_id,
                )
            if "capture_complete" not in parsed or type(parsed.get("capture_complete")) is not bool:
                return ObservationLedger.unavailable(
                    "observation_capture_marker_missing",
                    "native ledger envelope requires a boolean capture_complete marker",
                    run_id=expected_run_id or declared_run_id,
                )
            expected_run_id = expected_run_id or declared_run_id
            capture_complete = parsed.get("capture_complete") is True
        elif isinstance(parsed, list):
            records = parsed
        else:
            return ObservationLedger.unavailable(
                "observation_ledger_damaged", "ledger root must be an object or array", run_id=expected_run_id
            )

    if not all(isinstance(row, Mapping) for row in records):
        return ObservationLedger.unavailable(
            "observation_ledger_damaged", "every observation must be an object", run_id=expected_run_id
        )
    if records and all("event_type" not in row and "kind" in row for row in records):
        if not allow_legacy:
            return ObservationLedger.unavailable(
                "legacy_observation_not_allowed", "legacy RunEvidence JSONL is disabled", run_id=expected_run_id
            )
        return adapt_legacy_records(
            records,
            expected_run_id=expected_run_id,
            blob_loader=blob_loader,
        )
    return ObservationLedger.from_records(
        records,
        expected_run_id=expected_run_id,
        blob_loader=blob_loader,
        capture_complete=capture_complete,
    )


# Concise aliases for callers and pilot scripts.
load_ledger = load_observation_ledger
normalize_observations = ObservationLedger.from_records


__all__ = [
    "OBSERVATION_SEMANTICS",
    "EVENT_TYPES",
    "LedgerIssue",
    "ObservationEvent",
    "ObservationLedger",
    "adapt_legacy_records",
    "adapt_run_evidence",
    "load_observation_ledger",
    "load_ledger",
    "normalize_observations",
    "sha256_bytes",
    "sha256_text",
]
