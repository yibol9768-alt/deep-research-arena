"""Typed, content-addressed evidence graphs for DRA v3.

This module is deliberately independent from the v2 answer-key and scoring
code.  It models the frozen evidence layer only:

* semantic evidence nodes;
* typed dependency and discoverability edges;
* byte-addressed support spans; and
* an independent frozen-corpus membership registry.

Validation is fail-closed.  A source is accepted only when both of the
following are supplied and pass:

1. a corpus registry/allowlist says that the exact URL belongs to the frozen
   corpus; and
2. a blob loader returns bytes whose SHA-256 matches the node, including the
   SHA-256 of every declared support span.

Consequently, merely placing a blob at a guessed URL can never establish
corpus membership (the v3 ``R_i`` condition).  Support span offsets are byte
offsets into the exact frozen bytes, with ``start`` inclusive and ``end``
exclusive.

The JSON and JSONL helpers reject duplicate object keys, non-finite numbers,
unknown record fields, malformed identifiers and malformed hashes.  Graph
serialization sorts records by identifier and uses canonical JSON, making
reruns byte deterministic.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping, Set as AbstractSet
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeAlias, Union
from urllib.parse import urlsplit


EVIDENCE_GRAPH_VERSION = "evidence_graph_v1"
CORPUS_REGISTRY_VERSION = "frozen_corpus_registry_v1"

NODES_FILENAME = "nodes.jsonl"
EDGES_FILENAME = "edges.jsonl"
SUPPORT_SPANS_FILENAME = "support_spans.jsonl"
CORPUS_REGISTRY_FILENAME = "corpus_registry.json"
MANIFEST_FILENAME = "manifest.json"
EVIDENCE_GRAPH_MANIFEST_VERSION = "evidence_graph_manifest_v1"

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_PREDICATE_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_CONTROL_OR_SPACE_RE = re.compile(r"[\x00-\x20\x7f]")

JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
BlobLoader: TypeAlias = Mapping[str, bytes] | Callable[[str], bytes]
MembershipHook: TypeAlias = Union[
    "FrozenCorpusRegistry",
    AbstractSet[str],
    Mapping[str, object],
    Callable[["EvidenceNode"], object],
]


class EvidenceGraphError(ValueError):
    """Base class for evidence-graph format and validation failures."""


class EvidenceGraphFormatError(EvidenceGraphError):
    """Raised when JSON or a typed record is malformed."""


class EvidenceGraphValidationError(EvidenceGraphError):
    """Raised when a graph is structurally or cryptographically invalid."""


# Short alias for callers that do not need to distinguish format/validation.
ValidationError = EvidenceGraphValidationError


class NodeType(StrEnum):
    """Node types allowed by ``evidence_graph_v1``.

    The first eight are the minimum types from the v3 design.  The remaining
    types make source pages/search snippets and generic proof nodes explicit,
    which lets ``SUPPORTED_BY`` and discoverability edges have real endpoints.
    """

    ENTITY = "entity"
    ATTRIBUTE = "attribute"
    MECHANISM = "mechanism"
    ASSERTION = "assertion"
    PROPOSITION = "proposition"
    EXPERIENCE_CLAIM = "experience_claim"
    CONSTRAINT = "constraint"
    CONTRADICTION = "contradiction"
    BRIDGE = "bridge"
    DECISION = "decision"
    CATEGORY = "category"
    CLAIM = "claim"
    INFERENCE = "inference"
    DOCUMENT = "document"
    SEARCH_RESULT = "search_result"
    SNIPPET = "snippet"


class SourceType(StrEnum):
    """Closed set of source roles/implementations accepted by v1."""

    # Role-level names used by the redesign document.
    SHOPPING = "shopping"
    FORUM = "forum"
    CONCEPT = "concept"
    STRUCTURED_DB = "structured_db"
    CASE_SPEC = "case_spec"
    CURATED = "curated"
    SEARCH_RESULT = "search_result"

    # Concrete sandbox implementations.  These are kept explicit rather than
    # silently rewriting them to roles, so source identity remains auditable.
    MAGENTO = "magento"
    POSTMILL = "postmill"
    WIKIPEDIA = "wikipedia"


class EdgeRelation(StrEnum):
    HAS_ATTRIBUTE = "HAS_ATTRIBUTE"
    INSTANCE_OF = "INSTANCE_OF"
    ASSERTS = "ASSERTS"
    SUPPORTED_BY = "SUPPORTED_BY"
    REFUTES = "REFUTES"
    CONTRADICTS = "CONTRADICTS"
    APPLIES_UNDER = "APPLIES_UNDER"
    REQUIRES = "REQUIRES"
    DERIVES_FROM = "DERIVES_FROM"
    DISCOVERABLE_FROM = "DISCOVERABLE_FROM"
    SATISFIES = "SATISFIES"
    VIOLATES = "VIOLATES"


class DiscoveryMethod(StrEnum):
    """Static counterpart of the S/F/L observation vocabulary.

    ``S`` and ``L`` may license discovery.  ``SEED`` denotes a task-declared
    start URL.  ``F`` is represented so callers cannot accidentally conflate
    fetch with discovery; a ``DISCOVERABLE_FROM`` edge using ``F`` is rejected.
    """

    SEARCH_RESULT = "S"
    FETCH_BODY = "F"
    PAGE_LINK = "L"
    TASK_SEED = "SEED"


class SupportType(StrEnum):
    BODY = "body"
    SEARCH_SNIPPET = "search_snippet"


def sha256_bytes(content: bytes) -> str:
    """Return the lowercase SHA-256 hex digest for exact bytes."""

    if not isinstance(content, bytes):
        raise TypeError("sha256_bytes requires bytes")
    return hashlib.sha256(content).hexdigest()


def _format_error(path: str, message: str) -> EvidenceGraphFormatError:
    return EvidenceGraphFormatError(f"{path}: {message}")


def _validation_error(path: str, message: str) -> EvidenceGraphValidationError:
    return EvidenceGraphValidationError(f"{path}: {message}")


def _validate_id(value: object, path: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise _format_error(
            path,
            "must match ^[A-Za-z][A-Za-z0-9_.:-]{0,127}$",
        )
    return value


def _validate_predicate(value: object, path: str) -> str:
    if not isinstance(value, str) or not _PREDICATE_RE.fullmatch(value):
        raise _format_error(path, "must be a lowercase snake_case predicate")
    return value


def _validate_nonempty_text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _format_error(path, "must be a non-empty string")
    if _CONTROL_OR_SPACE_RE.search(value.strip()) and any(
        ord(ch) < 32 and ch not in "\t\n\r" for ch in value
    ):
        raise _format_error(path, "contains a control character")
    return value


def _validate_sha256(value: object, path: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise _format_error(path, "must be exactly 64 lowercase hex characters")
    return value


def _validate_source_url(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise _format_error(path, "must be a non-empty absolute URL")
    if _CONTROL_OR_SPACE_RE.search(value):
        raise _format_error(path, "must not contain whitespace/control characters")
    if _BAD_PERCENT_RE.search(value):
        raise _format_error(path, "contains an invalid percent escape")
    try:
        parsed = urlsplit(value)
        # Accessing .port is itself validation for malformed/non-numeric ports.
        _ = parsed.port
    except ValueError as exc:
        raise _format_error(path, f"malformed URL: {exc}") from exc
    if parsed.scheme not in {"http", "https"}:
        raise _format_error(path, "scheme must be http or https")
    if not parsed.hostname:
        raise _format_error(path, "must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise _format_error(path, "userinfo is forbidden")
    if parsed.fragment:
        raise _format_error(path, "fragments are forbidden in frozen source identity")
    path_segments = parsed.path.split("/")
    if any(segment in {".", ".."} for segment in path_segments):
        raise _format_error(path, "dot path segments are forbidden")
    return value


def _coerce_enum(enum_type: type[StrEnum], value: object, path: str) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        raise _format_error(path, f"must be one of {[item.value for item in enum_type]}")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise _format_error(
            path, f"unknown value {value!r}; expected one of {[item.value for item in enum_type]}"
        ) from exc


def _normalize_json(value: object, path: str = "value") -> JSONValue:
    """Deep-copy and validate a value as strict JSON (no NaN/Infinity)."""

    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _format_error(path, "non-finite numbers are forbidden")
        return value
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        out: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _format_error(path, "JSON object keys must be strings")
            out[key] = _normalize_json(item, f"{path}.{key}")
        return out
    raise _format_error(path, f"unsupported JSON value type {type(value).__name__}")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceGraphFormatError(f"duplicate JSON object key {key!r}")
        out[key] = value
    return out


def canonical_json_bytes(value: object) -> bytes:
    """Encode strict canonical UTF-8 JSON (without a trailing newline)."""

    normalized = _normalize_json(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def load_json(path: str | Path) -> JSONValue:
    """Load strict UTF-8 JSON while rejecting duplicate object keys."""

    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8")
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, EvidenceGraphFormatError) as exc:
        if isinstance(exc, EvidenceGraphFormatError):
            raise EvidenceGraphFormatError(f"{source}: {exc}") from exc
        raise EvidenceGraphFormatError(f"{source}: invalid JSON: {exc}") from exc
    return _normalize_json(value, str(source))


def load_jsonl(path: str | Path) -> list[dict[str, JSONValue]]:
    """Load strict JSONL.  Blank lines are ignored; every record is an object."""

    source = Path(path)
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise EvidenceGraphFormatError(f"{source}: unable to read JSONL: {exc}") from exc
    records: list[dict[str, JSONValue]] = []
    for line_number, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        except (json.JSONDecodeError, EvidenceGraphFormatError) as exc:
            raise EvidenceGraphFormatError(
                f"{source}:{line_number}: invalid JSON object: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise EvidenceGraphFormatError(
                f"{source}:{line_number}: each JSONL record must be an object"
            )
        records.append(_normalize_json(value, f"{source}:{line_number}"))
    return records


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def save_json(path: str | Path, value: object) -> None:
    """Atomically write canonical JSON with exactly one trailing newline."""

    _atomic_write(Path(path), canonical_json_bytes(value) + b"\n")


def _canonical_jsonl_bytes(records: Iterable[Mapping[str, object]]) -> bytes:
    encoded = [canonical_json_bytes(dict(record)) for record in records]
    encoded.sort()
    return b"" if not encoded else b"\n".join(encoded) + b"\n"


def save_jsonl(path: str | Path, records: Iterable[Mapping[str, object]]) -> None:
    """Atomically write records in canonical byte-sorted order."""

    _atomic_write(Path(path), _canonical_jsonl_bytes(records))


def _check_record_keys(
    raw: Mapping[str, object],
    *,
    required: AbstractSet[str],
    optional: AbstractSet[str],
    path: str,
) -> None:
    keys = set(raw)
    missing = sorted(required - keys)
    unknown = sorted(keys - required - optional)
    if missing:
        raise _format_error(path, f"missing required fields: {', '.join(missing)}")
    if unknown:
        raise _format_error(path, f"unknown fields: {', '.join(unknown)}")


def _with_alias(
    raw: Mapping[str, object], canonical: str, aliases: tuple[str, ...], path: str
) -> dict[str, object]:
    out = dict(raw)
    present = [name for name in (canonical, *aliases) if name in out]
    if len(present) > 1:
        raise _format_error(path, f"fields {present} are aliases; provide exactly one")
    if present and present[0] != canonical:
        out[canonical] = out.pop(present[0])
    return out


@dataclass(frozen=True, slots=True)
class EvidenceNode:
    evidence_id: str
    node_type: NodeType
    subject: str
    predicate: str
    object: JSONValue
    source_url: str
    source_type: SourceType
    content_sha256: str
    corpus_snapshot: str
    search_snippet_support: bool = False
    body_support: bool = True
    verifier: Mapping[str, JSONValue] = field(
        default_factory=lambda: {"kind": "typed_claim", "tolerance": None}
    )
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _validate_id(self.evidence_id, "evidence_id"))
        object.__setattr__(
            self, "node_type", _coerce_enum(NodeType, self.node_type, "node_type")
        )
        object.__setattr__(self, "subject", _validate_nonempty_text(self.subject, "subject"))
        object.__setattr__(self, "predicate", _validate_predicate(self.predicate, "predicate"))
        object.__setattr__(self, "object", _normalize_json(self.object, "object"))
        object.__setattr__(
            self, "source_url", _validate_source_url(self.source_url, "source_url")
        )
        object.__setattr__(
            self, "source_type", _coerce_enum(SourceType, self.source_type, "source_type")
        )
        object.__setattr__(
            self,
            "content_sha256",
            _validate_sha256(self.content_sha256, "content_sha256"),
        )
        object.__setattr__(
            self, "corpus_snapshot", _validate_id(self.corpus_snapshot, "corpus_snapshot")
        )
        if type(self.search_snippet_support) is not bool:
            raise _format_error("search_snippet_support", "must be boolean")
        if type(self.body_support) is not bool:
            raise _format_error("body_support", "must be boolean")
        if not self.search_snippet_support and not self.body_support:
            raise _format_error(
                "EvidenceNode", "at least one of body_support/search_snippet_support must be true"
            )
        verifier = _normalize_json(self.verifier, "verifier")
        if not isinstance(verifier, dict):
            raise _format_error("verifier", "must be an object")
        _validate_id(verifier.get("kind"), "verifier.kind")
        object.__setattr__(self, "verifier", verifier)
        metadata = _normalize_json(self.metadata, "metadata")
        if not isinstance(metadata, dict):
            raise _format_error("metadata", "must be an object")
        object.__setattr__(self, "metadata", metadata)

    @property
    def node_id(self) -> str:
        """Compatibility/readability alias for ``evidence_id``."""

        return self.evidence_id

    @property
    def source_identity(self) -> str:
        payload = {
            "corpus_snapshot": self.corpus_snapshot,
            "source_url": self.source_url,
            "source_type": self.source_type.value,
            "content_sha256": self.content_sha256,
        }
        return f"source:sha256:{sha256_bytes(canonical_json_bytes(payload))}"

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "evidence_id": self.evidence_id,
            "node_type": self.node_type.value,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "source_url": self.source_url,
            "source_type": self.source_type.value,
            "content_sha256": self.content_sha256,
            "corpus_snapshot": self.corpus_snapshot,
            "search_snippet_support": self.search_snippet_support,
            "body_support": self.body_support,
            "verifier": dict(self.verifier),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "EvidenceNode":
        path = "EvidenceNode"
        raw = _with_alias(raw, "evidence_id", ("node_id",), path)
        required = {
            "evidence_id",
            "node_type",
            "subject",
            "predicate",
            "object",
            "source_url",
            "source_type",
            "content_sha256",
            "corpus_snapshot",
        }
        optional = {
            "search_snippet_support",
            "body_support",
            "verifier",
            "metadata",
        }
        _check_record_keys(raw, required=required, optional=optional, path=path)
        return cls(
            evidence_id=raw["evidence_id"],  # type: ignore[arg-type]
            node_type=raw["node_type"],  # type: ignore[arg-type]
            subject=raw["subject"],  # type: ignore[arg-type]
            predicate=raw["predicate"],  # type: ignore[arg-type]
            object=raw["object"],  # type: ignore[arg-type]
            source_url=raw["source_url"],  # type: ignore[arg-type]
            source_type=raw["source_type"],  # type: ignore[arg-type]
            content_sha256=raw["content_sha256"],  # type: ignore[arg-type]
            corpus_snapshot=raw["corpus_snapshot"],  # type: ignore[arg-type]
            search_snippet_support=raw.get("search_snippet_support", False),  # type: ignore[arg-type]
            body_support=raw.get("body_support", True),  # type: ignore[arg-type]
            verifier=raw.get(
                "verifier", {"kind": "typed_claim", "tolerance": None}
            ),  # type: ignore[arg-type]
            metadata=raw.get("metadata", {}),  # type: ignore[arg-type]
        )


def _coerce_discovery_method(value: object, path: str) -> DiscoveryMethod:
    aliases = {
        "search": "S",
        "search_result": "S",
        "fetch": "F",
        "fetch_body": "F",
        "link": "L",
        "page_link": "L",
        "seed": "SEED",
        "task_seed": "SEED",
    }
    if isinstance(value, str):
        value = aliases.get(value, value)
    return _coerce_enum(DiscoveryMethod, value, path)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class EvidenceEdge:
    """A typed graph edge.

    For ``DISCOVERABLE_FROM`` the direction is intentionally literal rather
    than conventional link direction::

        source_id DISCOVERABLE_FROM target_id

    Therefore reachability traversal moves ``target_id -> source_id``.  With
    method ``S``, target is a search-result node and source is the returned
    page.  With ``L``, target is the already reachable/fetched page and source
    is the linked page.  With ``SEED``, source itself is a task-declared root
    and target records the case/start-page declaration that licensed it.
    """

    edge_id: str
    relation: EdgeRelation
    source_id: str
    target_id: str
    discovery_method: DiscoveryMethod | None = None
    discovery_order: int | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "edge_id", _validate_id(self.edge_id, "edge_id"))
        object.__setattr__(
            self, "relation", _coerce_enum(EdgeRelation, self.relation, "relation")
        )
        object.__setattr__(self, "source_id", _validate_id(self.source_id, "source_id"))
        object.__setattr__(self, "target_id", _validate_id(self.target_id, "target_id"))
        if self.source_id == self.target_id:
            raise _format_error("EvidenceEdge", "self-edges are forbidden")
        method = self.discovery_method
        if method is not None:
            method = _coerce_discovery_method(method, "discovery_method")
            object.__setattr__(self, "discovery_method", method)
        if self.relation is EdgeRelation.DISCOVERABLE_FROM:
            if method is None:
                raise _format_error(
                    "discovery_method",
                    "DISCOVERABLE_FROM must say whether discovery came from S, L, or SEED",
                )
            if method is DiscoveryMethod.FETCH_BODY:
                raise _format_error(
                    "discovery_method",
                    "F (fetch) observes a body but never licenses URL discovery",
                )
        elif method is not None or self.discovery_order is not None:
            raise _format_error(
                "EvidenceEdge",
                "discovery_method/order are only valid for DISCOVERABLE_FROM",
            )
        if self.discovery_order is not None:
            if type(self.discovery_order) is not int or self.discovery_order < 0:
                raise _format_error("discovery_order", "must be a non-negative integer")
        metadata = _normalize_json(self.metadata, "metadata")
        if not isinstance(metadata, dict):
            raise _format_error("metadata", "must be an object")
        object.__setattr__(self, "metadata", metadata)

    @property
    def grants_discovery_license(self) -> bool:
        return self.relation is EdgeRelation.DISCOVERABLE_FROM and self.discovery_method in {
            DiscoveryMethod.SEARCH_RESULT,
            DiscoveryMethod.PAGE_LINK,
            DiscoveryMethod.TASK_SEED,
        }

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "edge_id": self.edge_id,
            "relation": self.relation.value,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "discovery_method": (
                self.discovery_method.value if self.discovery_method is not None else None
            ),
            "discovery_order": self.discovery_order,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "EvidenceEdge":
        path = "EvidenceEdge"
        raw = _with_alias(raw, "source_id", ("source", "from_id"), path)
        raw = _with_alias(raw, "target_id", ("target", "to_id"), path)
        required = {"edge_id", "relation", "source_id", "target_id"}
        optional = {"discovery_method", "discovery_order", "metadata"}
        _check_record_keys(raw, required=required, optional=optional, path=path)
        return cls(
            edge_id=raw["edge_id"],  # type: ignore[arg-type]
            relation=raw["relation"],  # type: ignore[arg-type]
            source_id=raw["source_id"],  # type: ignore[arg-type]
            target_id=raw["target_id"],  # type: ignore[arg-type]
            discovery_method=raw.get("discovery_method"),  # type: ignore[arg-type]
            discovery_order=raw.get("discovery_order"),  # type: ignore[arg-type]
            metadata=raw.get("metadata", {}),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class SupportSpan:
    support_span_id: str
    evidence_id: str
    source_url: str
    start: int
    end: int
    sha256: str
    support_type: SupportType = SupportType.BODY
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "support_span_id",
            _validate_id(self.support_span_id, "support_span_id"),
        )
        object.__setattr__(self, "evidence_id", _validate_id(self.evidence_id, "evidence_id"))
        object.__setattr__(
            self, "source_url", _validate_source_url(self.source_url, "source_url")
        )
        if type(self.start) is not int or self.start < 0:
            raise _format_error("start", "must be a non-negative integer byte offset")
        if type(self.end) is not int or self.end <= self.start:
            raise _format_error("end", "must be an integer greater than start")
        object.__setattr__(self, "sha256", _validate_sha256(self.sha256, "sha256"))
        object.__setattr__(
            self,
            "support_type",
            _coerce_enum(SupportType, self.support_type, "support_type"),
        )
        metadata = _normalize_json(self.metadata, "metadata")
        if not isinstance(metadata, dict):
            raise _format_error("metadata", "must be an object")
        object.__setattr__(self, "metadata", metadata)

    @property
    def span_id(self) -> str:
        return self.support_span_id

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "support_span_id": self.support_span_id,
            "evidence_id": self.evidence_id,
            "source_url": self.source_url,
            "start": self.start,
            "end": self.end,
            "sha256": self.sha256,
            "support_type": self.support_type.value,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "SupportSpan":
        path = "SupportSpan"
        raw = _with_alias(raw, "support_span_id", ("span_id",), path)
        raw = _with_alias(raw, "evidence_id", ("node_id",), path)
        required = {
            "support_span_id",
            "evidence_id",
            "source_url",
            "start",
            "end",
            "sha256",
        }
        optional = {"support_type", "metadata"}
        _check_record_keys(raw, required=required, optional=optional, path=path)
        return cls(
            support_span_id=raw["support_span_id"],  # type: ignore[arg-type]
            evidence_id=raw["evidence_id"],  # type: ignore[arg-type]
            source_url=raw["source_url"],  # type: ignore[arg-type]
            start=raw["start"],  # type: ignore[arg-type]
            end=raw["end"],  # type: ignore[arg-type]
            sha256=raw["sha256"],  # type: ignore[arg-type]
            support_type=raw.get("support_type", SupportType.BODY),  # type: ignore[arg-type]
            metadata=raw.get("metadata", {}),  # type: ignore[arg-type]
        )


def _validate_semantic_assertion_layer(
    nodes: Mapping[str, EvidenceNode],
    edges: Iterable[EvidenceEdge],
    support_spans: Iterable[SupportSpan],
) -> None:
    """Fail closed for the v3 ``Assertion -> Proposition`` semantic layer.

    Legacy v3 graph nodes remain valid, but opting into the explicit
    ``assertion``/``proposition`` vocabulary carries stronger invariants:

    * an assertion is a page statement, so it must be byte-addressed by at
      least one frozen support span;
    * ``ASSERTS`` always points from a source-backed assertion-like node to a
      normalized proposition; and
    * every proposition must be grounded by an assertion/support/refutation
      edge instead of silently becoming an untraceable global truth.

    ``REFUTES`` is accepted in either serialized orientation because the plan
    describes both ``Page refutes Proposition`` and
    ``REFUTES(proposition, page_or_snippet)``.  Exactly one endpoint must be a
    proposition, which keeps the meaning unambiguous without imposing a
    storage convention on inventories.
    """

    span_backed_ids = {span.evidence_id for span in support_spans}
    semantic_edges = tuple(edges)

    for node in nodes.values():
        if node.node_type is NodeType.ASSERTION and node.evidence_id not in span_backed_ids:
            raise _validation_error(
                f"node[{node.evidence_id}]",
                "assertion nodes require at least one frozen support span",
            )

    proposition_ids = {
        node.evidence_id
        for node in nodes.values()
        if node.node_type is NodeType.PROPOSITION
    }
    grounded_propositions: set[str] = set()
    assertion_like_types = {
        NodeType.ASSERTION,
        NodeType.CLAIM,
        NodeType.EXPERIENCE_CLAIM,
        NodeType.DOCUMENT,
        NodeType.SNIPPET,
    }

    for edge in semantic_edges:
        source = nodes[edge.source_id]
        target = nodes[edge.target_id]
        if edge.relation is EdgeRelation.ASSERTS:
            if target.node_type is not NodeType.PROPOSITION:
                raise _validation_error(
                    f"edge[{edge.edge_id}]",
                    "ASSERTS must target a proposition node",
                )
            if source.node_type not in assertion_like_types:
                raise _validation_error(
                    f"edge[{edge.edge_id}]",
                    "ASSERTS must originate at an assertion/document/claim node",
                )
            if source.evidence_id not in span_backed_ids:
                raise _validation_error(
                    f"edge[{edge.edge_id}]",
                    "ASSERTS source must be backed by a frozen support span",
                )
            grounded_propositions.add(target.evidence_id)
        elif edge.relation is EdgeRelation.REFUTES:
            proposition_endpoints = {
                node.evidence_id
                for node in (source, target)
                if node.node_type is NodeType.PROPOSITION
            }
            if len(proposition_endpoints) != 1:
                raise _validation_error(
                    f"edge[{edge.edge_id}]",
                    "REFUTES must connect exactly one proposition to one source-backed node",
                )
            evidence_endpoint = target if source.node_type is NodeType.PROPOSITION else source
            if evidence_endpoint.evidence_id not in span_backed_ids:
                raise _validation_error(
                    f"edge[{edge.edge_id}]",
                    "REFUTES evidence endpoint must be backed by a frozen support span",
                )
            grounded_propositions.update(proposition_endpoints)
        elif edge.relation is EdgeRelation.SUPPORTED_BY:
            if source.node_type is NodeType.PROPOSITION:
                if target.evidence_id not in span_backed_ids:
                    raise _validation_error(
                        f"edge[{edge.edge_id}]",
                        "SUPPORTED_BY evidence endpoint must have a frozen support span",
                    )
                grounded_propositions.add(source.evidence_id)
            elif target.node_type is NodeType.PROPOSITION:
                if source.evidence_id not in span_backed_ids:
                    raise _validation_error(
                        f"edge[{edge.edge_id}]",
                        "SUPPORTED_BY evidence endpoint must have a frozen support span",
                    )
                grounded_propositions.add(target.evidence_id)

    ungrounded = sorted(proposition_ids - grounded_propositions)
    if ungrounded:
        raise _validation_error(
            "propositions",
            "normalized propositions lack a source-backed ASSERTS/REFUTES/"
            f"SUPPORTED_BY path: {', '.join(ungrounded)}",
        )


@dataclass(frozen=True, slots=True)
class FrozenCorpusEntry:
    """One independently enumerated member of a frozen corpus registry."""

    registry_id: str
    source_url: str
    source_type: SourceType
    content_sha256: str
    corpus_snapshot: str
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "registry_id", _validate_id(self.registry_id, "registry_id"))
        object.__setattr__(
            self, "source_url", _validate_source_url(self.source_url, "source_url")
        )
        object.__setattr__(
            self, "source_type", _coerce_enum(SourceType, self.source_type, "source_type")
        )
        object.__setattr__(
            self,
            "content_sha256",
            _validate_sha256(self.content_sha256, "content_sha256"),
        )
        object.__setattr__(
            self, "corpus_snapshot", _validate_id(self.corpus_snapshot, "corpus_snapshot")
        )
        metadata = _normalize_json(self.metadata, "metadata")
        if not isinstance(metadata, dict):
            raise _format_error("metadata", "must be an object")
        object.__setattr__(self, "metadata", metadata)

    @property
    def source_identity(self) -> str:
        payload = {
            "corpus_snapshot": self.corpus_snapshot,
            "source_url": self.source_url,
            "source_type": self.source_type.value,
            "content_sha256": self.content_sha256,
        }
        return f"source:sha256:{sha256_bytes(canonical_json_bytes(payload))}"

    def matches(self, node: EvidenceNode) -> bool:
        return (
            self.source_url == node.source_url
            and self.source_type is node.source_type
            and self.content_sha256 == node.content_sha256
            and self.corpus_snapshot == node.corpus_snapshot
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "registry_id": self.registry_id,
            "source_url": self.source_url,
            "source_type": self.source_type.value,
            "content_sha256": self.content_sha256,
            "corpus_snapshot": self.corpus_snapshot,
            "in_corpus": True,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "FrozenCorpusEntry":
        path = "FrozenCorpusEntry"
        required = {
            "registry_id",
            "source_url",
            "source_type",
            "content_sha256",
            "corpus_snapshot",
            "in_corpus",
        }
        optional = {"metadata"}
        _check_record_keys(raw, required=required, optional=optional, path=path)
        if raw["in_corpus"] is not True:
            raise _format_error("in_corpus", "must be explicitly true for a registry member")
        return cls(
            registry_id=raw["registry_id"],  # type: ignore[arg-type]
            source_url=raw["source_url"],  # type: ignore[arg-type]
            source_type=raw["source_type"],  # type: ignore[arg-type]
            content_sha256=raw["content_sha256"],  # type: ignore[arg-type]
            corpus_snapshot=raw["corpus_snapshot"],  # type: ignore[arg-type]
            metadata=raw.get("metadata", {}),  # type: ignore[arg-type]
        )


def _coerce_registry_entry(value: object, index: int) -> FrozenCorpusEntry:
    if not isinstance(value, Mapping):
        raise _format_error(f"entries[{index}]", "must be an object")
    return FrozenCorpusEntry.from_dict(value)


@dataclass(frozen=True, slots=True)
class FrozenCorpusRegistry:
    """Exact URL/type/hash membership registry for one corpus snapshot."""

    corpus_snapshot: str
    entries: tuple[FrozenCorpusEntry, ...]
    version: str = CORPUS_REGISTRY_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "corpus_snapshot", _validate_id(self.corpus_snapshot, "corpus_snapshot")
        )
        if self.version != CORPUS_REGISTRY_VERSION:
            raise _format_error(
                "version", f"must be exactly {CORPUS_REGISTRY_VERSION!r}"
            )
        entries = tuple(
            entry if isinstance(entry, FrozenCorpusEntry) else FrozenCorpusEntry.from_dict(entry)
            for entry in self.entries
        )
        if not entries:
            raise _format_error("entries", "frozen corpus registry must not be empty")
        object.__setattr__(self, "entries", entries)
        by_id: set[str] = set()
        by_url: dict[str, FrozenCorpusEntry] = {}
        for entry in entries:
            if entry.corpus_snapshot != self.corpus_snapshot:
                raise _format_error(
                    f"registry[{entry.registry_id}]",
                    "corpus_snapshot does not match registry snapshot",
                )
            if entry.registry_id in by_id:
                raise _format_error("entries", f"duplicate registry_id {entry.registry_id!r}")
            by_id.add(entry.registry_id)
            previous = by_url.get(entry.source_url)
            if previous is not None:
                raise _format_error(
                    "entries",
                    f"duplicate source_url {entry.source_url!r} in registry",
                )
            by_url[entry.source_url] = entry

    @property
    def _stamp_payload(self) -> dict[str, JSONValue]:
        return {
            "version": self.version,
            "corpus_snapshot": self.corpus_snapshot,
            "entries": [
                entry.to_dict()
                for entry in sorted(self.entries, key=lambda item: item.registry_id)
            ],
        }

    @property
    def corpus_sha256(self) -> str:
        """Raw 64-hex digest used in protocol/manifest hash fields."""

        return sha256_bytes(canonical_json_bytes(self._stamp_payload))

    @property
    def corpus_stamp(self) -> str:
        return f"corpus-registry-v1:sha256:{self.corpus_sha256}"

    @property
    def stamp(self) -> str:
        return self.corpus_stamp

    def entry_for_url(self, source_url: str) -> FrozenCorpusEntry | None:
        # Keep the dataclass immutable and the implementation simple.  Corpus
        # inventories are constructed once; validation caches source blobs.
        return next((entry for entry in self.entries if entry.source_url == source_url), None)

    def contains(self, node: EvidenceNode) -> bool:
        entry = self.entry_for_url(node.source_url)
        return entry is not None and entry.matches(node)

    def save(self, path_or_directory: str | Path) -> None:
        save_corpus_registry(self, path_or_directory)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return the deterministic typed registry object used by case tools."""

        return self._stamp_payload

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "FrozenCorpusRegistry":
        path = "FrozenCorpusRegistry"
        _check_record_keys(
            raw,
            required={"version", "corpus_snapshot", "entries"},
            optional=set(),
            path=path,
        )
        entries = raw["entries"]
        if not isinstance(entries, list):
            raise _format_error("entries", "must be an array")
        return cls(
            corpus_snapshot=raw["corpus_snapshot"],  # type: ignore[arg-type]
            entries=tuple(
                _coerce_registry_entry(entry, index)
                for index, entry in enumerate(entries)
            ),
            version=raw["version"],  # type: ignore[arg-type]
        )

    @classmethod
    def load(cls, path_or_directory: str | Path) -> "FrozenCorpusRegistry":
        return load_corpus_registry(path_or_directory)


CorpusRegistry = FrozenCorpusRegistry


def _membership_result_is_exact(result: object, node: EvidenceNode) -> bool:
    if result is True:
        return True
    if not isinstance(result, Mapping):
        return False
    if result.get("in_corpus") is not True:
        return False
    checks = {
        "source_url": node.source_url,
        "source_type": node.source_type.value,
        "content_sha256": node.content_sha256,
        "corpus_snapshot": node.corpus_snapshot,
    }
    for key, expected in checks.items():
        if key in result and result[key] != expected:
            return False
    return True


def source_is_frozen_member(node: EvidenceNode, membership: MembershipHook) -> bool:
    """Evaluate independent corpus membership, treating unknown as false.

    Preferred input is :class:`FrozenCorpusRegistry`, which checks URL, source
    type, content hash and snapshot.  A URL set is an explicit allowlist.  A
    mapping may be keyed by source identity or URL and return either literal
    ``True`` or a mapping containing ``in_corpus: true``.  A callable receives
    the full node and follows the same result contract.
    """

    if isinstance(membership, FrozenCorpusRegistry):
        return membership.contains(node)
    if isinstance(membership, AbstractSet) and not isinstance(membership, (str, bytes)):
        return node.source_url in membership
    if isinstance(membership, Mapping):
        sentinel = object()
        result = membership.get(node.source_identity, sentinel)
        if result is sentinel:
            result = membership.get(node.source_url, sentinel)
        return result is not sentinel and _membership_result_is_exact(result, node)
    if callable(membership):
        try:
            result = membership(node)
        except Exception as exc:
            raise _validation_error(
                f"node[{node.evidence_id}].membership",
                f"membership hook failed: {exc}",
            ) from exc
        return _membership_result_is_exact(result, node)
    raise _validation_error(
        "corpus_membership",
        "must be FrozenCorpusRegistry, an explicit URL allowlist/mapping, or a node hook",
    )


def _load_blob(blob_loader: BlobLoader, node: EvidenceNode) -> bytes:
    try:
        if isinstance(blob_loader, Mapping):
            if node.source_url not in blob_loader:
                raise KeyError(node.source_url)
            content = blob_loader[node.source_url]
        elif callable(blob_loader):
            content = blob_loader(node.source_url)
        else:
            raise TypeError("blob loader must be a URL->bytes mapping or callable")
    except Exception as exc:
        raise _validation_error(
            f"node[{node.evidence_id}].source_url",
            f"frozen blob is unavailable for {node.source_url!r}: {exc}",
        ) from exc
    if isinstance(content, (bytearray, memoryview)):
        content = bytes(content)
    if not isinstance(content, bytes):
        raise _validation_error(
            f"node[{node.evidence_id}].source_url",
            "blob loader must return bytes, never decoded text",
        )
    return content


@dataclass(frozen=True, slots=True)
class EvidenceGraph:
    corpus_snapshot: str
    nodes: tuple[EvidenceNode, ...]
    edges: tuple[EvidenceEdge, ...]
    support_spans: tuple[SupportSpan, ...]
    version: str = EVIDENCE_GRAPH_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "corpus_snapshot", _validate_id(self.corpus_snapshot, "corpus_snapshot")
        )
        if self.version != EVIDENCE_GRAPH_VERSION:
            raise _format_error("version", f"must be exactly {EVIDENCE_GRAPH_VERSION!r}")
        object.__setattr__(
            self,
            "nodes",
            tuple(
                node if isinstance(node, EvidenceNode) else EvidenceNode.from_dict(node)
                for node in self.nodes
            ),
        )
        object.__setattr__(
            self,
            "edges",
            tuple(
                edge if isinstance(edge, EvidenceEdge) else EvidenceEdge.from_dict(edge)
                for edge in self.edges
            ),
        )
        object.__setattr__(
            self,
            "support_spans",
            tuple(
                span if isinstance(span, SupportSpan) else SupportSpan.from_dict(span)
                for span in self.support_spans
            ),
        )

    @property
    def node_by_id(self) -> dict[str, EvidenceNode]:
        return {node.evidence_id: node for node in self.nodes}

    @property
    def corpus_stamp(self) -> str:
        """Stable stamp of the exact source identities used by this graph."""

        sources = {
            (
                node.source_url,
                node.source_type.value,
                node.content_sha256,
                node.corpus_snapshot,
            )
            for node in self.nodes
        }
        payload = {
            "version": "graph_corpus_identity_v1",
            "corpus_snapshot": self.corpus_snapshot,
            "sources": [
                {
                    "source_url": source_url,
                    "source_type": source_type,
                    "content_sha256": content_sha256,
                    "corpus_snapshot": corpus_snapshot,
                }
                for source_url, source_type, content_sha256, corpus_snapshot in sorted(sources)
            ],
        }
        return f"graph-corpus-v1:sha256:{sha256_bytes(canonical_json_bytes(payload))}"

    @property
    def corpus_sha256(self) -> str:
        """Raw digest component of :attr:`corpus_stamp`."""

        return self.corpus_stamp.rsplit(":", 1)[-1]

    @property
    def _graph_stamp_payload(self) -> dict[str, JSONValue]:
        return {
            "version": self.version,
            "corpus_stamp": self.corpus_stamp,
            "nodes": [
                node.to_dict() for node in sorted(self.nodes, key=lambda item: item.evidence_id)
            ],
            "edges": [
                edge.to_dict() for edge in sorted(self.edges, key=lambda item: item.edge_id)
            ],
            "support_spans": [
                span.to_dict()
                for span in sorted(
                    self.support_spans, key=lambda item: item.support_span_id
                )
            ],
        }

    @property
    def graph_sha256(self) -> str:
        """Raw 64-hex evidence graph digest for ``evidence_graph_hash``."""

        return sha256_bytes(canonical_json_bytes(self._graph_stamp_payload))

    @property
    def graph_hash(self) -> str:
        """Alias used by protocol manifests."""

        return self.graph_sha256

    @property
    def graph_stamp(self) -> str:
        return f"evidence-graph-v1:sha256:{self.graph_sha256}"

    @property
    def stamp(self) -> str:
        return self.graph_stamp

    @property
    def discoverability_edges(self) -> tuple[EvidenceEdge, ...]:
        return tuple(
            edge
            for edge in self.edges
            if edge.relation is EdgeRelation.DISCOVERABLE_FROM
        )

    def discoverable_node_ids(
        self,
        root_node_ids: Iterable[str] = (),
        *,
        include_seed_roots: bool = True,
        include_search_result_roots: bool = True,
    ) -> tuple[str, ...]:
        """Return the deterministic S/L/SEED discoverability closure.

        Explicit roots are node IDs supplied by a task/start-page policy.
        ``SEED`` edges contribute their ``source_id`` as declared roots, while
        search-result nodes may be treated as roots (the default) because their
        snippets/returned URLs are agent-visible.  Traversal then follows only
        licensed ``DISCOVERABLE_FROM`` edges in the documented
        ``target_id -> source_id`` direction.  Proof edges such as ``REQUIRES``
        never grant discovery.

        Reachability is a URL property.  Once one node is reachable, all nodes
        bound to the same exact frozen ``source_url`` are included in the
        closure.  This avoids requiring redundant edges from a page node to
        every claim extracted from that page.

        This operation is structural and deterministic; formal callers should
        first call :meth:`validate` so corpus membership and bytes are proven.
        """

        node_index: dict[str, EvidenceNode] = {}
        nodes_by_url: dict[str, list[str]] = {}
        for node in self.nodes:
            if node.evidence_id in node_index:
                raise _validation_error(
                    "nodes", f"duplicate evidence_id {node.evidence_id!r}"
                )
            node_index[node.evidence_id] = node
            nodes_by_url.setdefault(node.source_url, []).append(node.evidence_id)

        roots: set[str] = set()
        for root in root_node_ids:
            root_id = _validate_id(root, "root_node_ids")
            if root_id not in node_index:
                raise _validation_error(
                    "root_node_ids", f"unknown discoverability root {root_id!r}"
                )
            roots.add(root_id)
        if include_search_result_roots:
            roots.update(
                node.evidence_id
                for node in self.nodes
                if node.node_type is NodeType.SEARCH_RESULT
            )

        adjacency: dict[str, list[str]] = {}
        for edge in self.discoverability_edges:
            if edge.source_id not in node_index:
                raise _validation_error(
                    f"edge[{edge.edge_id}].source_id",
                    f"dangling endpoint {edge.source_id!r}",
                )
            if edge.target_id not in node_index:
                raise _validation_error(
                    f"edge[{edge.edge_id}].target_id",
                    f"dangling endpoint {edge.target_id!r}",
                )
            if not edge.grants_discovery_license:
                continue
            if edge.discovery_method is DiscoveryMethod.TASK_SEED:
                if include_seed_roots:
                    roots.add(edge.source_id)
                continue
            adjacency.setdefault(edge.target_id, []).append(edge.source_id)

        reached: set[str] = set()
        pending = sorted(roots, reverse=True)
        while pending:
            current = pending.pop()
            if current in reached:
                continue
            reached.add(current)
            node = node_index[current]
            same_url = nodes_by_url[node.source_url]
            next_ids = [*same_url, *adjacency.get(current, ())]
            for next_id in sorted(next_ids, reverse=True):
                if next_id not in reached:
                    pending.append(next_id)
        return tuple(sorted(reached))

    def reachable_node_ids(
        self,
        root_node_ids: Iterable[str] = (),
        *,
        include_seed_roots: bool = True,
        include_search_result_roots: bool = True,
    ) -> tuple[str, ...]:
        """Alias for :meth:`discoverable_node_ids`."""

        return self.discoverable_node_ids(
            root_node_ids,
            include_seed_roots=include_seed_roots,
            include_search_result_roots=include_search_result_roots,
        )

    def discoverable_source_urls(
        self,
        root_node_ids: Iterable[str] = (),
        *,
        include_seed_roots: bool = True,
        include_search_result_roots: bool = True,
    ) -> tuple[str, ...]:
        reached = self.discoverable_node_ids(
            root_node_ids,
            include_seed_roots=include_seed_roots,
            include_search_result_roots=include_search_result_roots,
        )
        node_index = self.node_by_id
        return tuple(sorted({node_index[node_id].source_url for node_id in reached}))

    def require_discoverable(
        self,
        required_node_ids: Iterable[str],
        root_node_ids: Iterable[str] = (),
        *,
        include_seed_roots: bool = True,
        include_search_result_roots: bool = True,
    ) -> tuple[str, ...]:
        """Return the closure or reject any unreachable required evidence."""

        required: set[str] = set()
        node_index = self.node_by_id
        for node_id in required_node_ids:
            checked = _validate_id(node_id, "required_node_ids")
            if checked not in node_index:
                raise _validation_error(
                    "required_node_ids", f"unknown required node {checked!r}"
                )
            required.add(checked)
        reached = self.discoverable_node_ids(
            root_node_ids,
            include_seed_roots=include_seed_roots,
            include_search_result_roots=include_search_result_roots,
        )
        unreachable = sorted(required - set(reached))
        if unreachable:
            raise _validation_error(
                "discoverability",
                f"required evidence is unreachable: {', '.join(unreachable)}",
            )
        return reached

    def validate(
        self,
        *,
        blob_loader: BlobLoader | None,
        corpus_membership: MembershipHook | None,
    ) -> "EvidenceGraph":
        """Strictly validate structure, membership, whole blobs and spans.

        Both keyword arguments are mandatory in semantics even though their
        type admits ``None``: ``None`` produces a validation error rather than
        silently downgrading to structural-only validation.

        Graph validation intentionally verifies declared spans but does not
        require every node to have one: bridge/decision/inference nodes may be
        proof-derived.  The case compiler is responsible for requiring spans
        on every *critical evidence* node.
        """

        if not self.nodes:
            raise _validation_error("nodes", "graph must contain at least one node")
        if blob_loader is None:
            raise _validation_error(
                "blob_loader", "required; content hashes cannot be trusted without frozen bytes"
            )
        if corpus_membership is None:
            raise _validation_error(
                "corpus_membership",
                "required independently of blob availability (v3 R_i)",
            )

        nodes: dict[str, EvidenceNode] = {}
        source_identities: dict[str, tuple[SourceType, str, str]] = {}
        for node in self.nodes:
            if node.evidence_id in nodes:
                raise _validation_error("nodes", f"duplicate evidence_id {node.evidence_id!r}")
            nodes[node.evidence_id] = node
            if node.corpus_snapshot != self.corpus_snapshot:
                raise _validation_error(
                    f"node[{node.evidence_id}].corpus_snapshot",
                    f"expected {self.corpus_snapshot!r}, got {node.corpus_snapshot!r}",
                )
            identity = (node.source_type, node.content_sha256, node.corpus_snapshot)
            previous = source_identities.get(node.source_url)
            if previous is not None and previous != identity:
                raise _validation_error(
                    f"node[{node.evidence_id}].source_url",
                    "one frozen URL is bound to conflicting type/hash/snapshot identities",
                )
            source_identities[node.source_url] = identity
            if not source_is_frozen_member(node, corpus_membership):
                raise _validation_error(
                    f"node[{node.evidence_id}].source_url",
                    "URL/type/hash/snapshot is not an explicit frozen-corpus member",
                )

        edge_ids: set[str] = set()
        edge_triples: set[tuple[str, EdgeRelation, str]] = set()
        for edge in self.edges:
            if edge.edge_id in edge_ids:
                raise _validation_error("edges", f"duplicate edge_id {edge.edge_id!r}")
            edge_ids.add(edge.edge_id)
            if edge.source_id not in nodes:
                raise _validation_error(
                    f"edge[{edge.edge_id}].source_id",
                    f"dangling endpoint {edge.source_id!r}",
                )
            if edge.target_id not in nodes:
                raise _validation_error(
                    f"edge[{edge.edge_id}].target_id",
                    f"dangling endpoint {edge.target_id!r}",
                )
            triple = (edge.source_id, edge.relation, edge.target_id)
            if triple in edge_triples:
                raise _validation_error(
                    f"edge[{edge.edge_id}]", "duplicate source/relation/target edge"
                )
            edge_triples.add(triple)

        span_ids: set[str] = set()
        for span in self.support_spans:
            if span.support_span_id in span_ids:
                raise _validation_error(
                    "support_spans",
                    f"duplicate support_span_id {span.support_span_id!r}",
                )
            span_ids.add(span.support_span_id)
            node = nodes.get(span.evidence_id)
            if node is None:
                raise _validation_error(
                    f"span[{span.support_span_id}].evidence_id",
                    f"unknown evidence node {span.evidence_id!r}",
                )
            if span.source_url != node.source_url:
                raise _validation_error(
                    f"span[{span.support_span_id}].source_url",
                    "must exactly match the evidence node source_url",
                )
            if span.support_type is SupportType.BODY and not node.body_support:
                raise _validation_error(
                    f"span[{span.support_span_id}].support_type",
                    "body span conflicts with node body_support=false",
                )
            if (
                span.support_type is SupportType.SEARCH_SNIPPET
                and not node.search_snippet_support
            ):
                raise _validation_error(
                    f"span[{span.support_span_id}].support_type",
                    "snippet span conflicts with node search_snippet_support=false",
                )

        _validate_semantic_assertion_layer(nodes, self.edges, self.support_spans)

        blob_cache: dict[str, bytes] = {}
        for node in self.nodes:
            content = blob_cache.get(node.source_url)
            if content is None:
                content = _load_blob(blob_loader, node)
                blob_cache[node.source_url] = content
            actual_hash = sha256_bytes(content)
            if actual_hash != node.content_sha256:
                raise _validation_error(
                    f"node[{node.evidence_id}].content_sha256",
                    f"expected {node.content_sha256}, frozen bytes hash to {actual_hash}",
                )

        for span in self.support_spans:
            content = blob_cache[span.source_url]
            if span.end > len(content):
                raise _validation_error(
                    f"span[{span.support_span_id}]",
                    f"byte range [{span.start}, {span.end}) exceeds blob length {len(content)}",
                )
            actual_hash = sha256_bytes(content[span.start : span.end])
            if actual_hash != span.sha256:
                raise _validation_error(
                    f"span[{span.support_span_id}].sha256",
                    f"expected {span.sha256}, selected frozen bytes hash to {actual_hash}",
                )
        return self

    def save(
        self,
        directory: str | Path,
        *,
        blob_loader: BlobLoader | None,
        corpus_membership: MembershipHook | None,
    ) -> None:
        save_graph(
            self,
            directory,
            blob_loader=blob_loader,
            corpus_membership=corpus_membership,
        )

    @classmethod
    def load(
        cls,
        directory: str | Path,
        *,
        blob_loader: BlobLoader | None,
        corpus_membership: MembershipHook | None = None,
    ) -> "EvidenceGraph":
        return load_graph(
            directory,
            blob_loader=blob_loader,
            corpus_membership=corpus_membership,
        )


def _corpus_registry_path(path_or_directory: str | Path) -> Path:
    path = Path(path_or_directory)
    if path.name == CORPUS_REGISTRY_FILENAME or path.suffix.lower() == ".json":
        return path
    return path / CORPUS_REGISTRY_FILENAME


def save_corpus_registry(
    registry: FrozenCorpusRegistry, path_or_directory: str | Path
) -> None:
    """Persist the complete typed registry, including unused corpus pages."""

    if not isinstance(registry, FrozenCorpusRegistry):
        raise TypeError("save_corpus_registry requires FrozenCorpusRegistry")
    save_json(_corpus_registry_path(path_or_directory), registry.to_dict())


def load_corpus_registry(path_or_directory: str | Path) -> FrozenCorpusRegistry:
    """Load a deterministic ``frozen_corpus_registry_v1`` JSON object."""

    path = _corpus_registry_path(path_or_directory)
    raw = load_json(path)
    if not isinstance(raw, dict):
        raise EvidenceGraphFormatError(f"{path}: corpus registry must be an object")
    return FrozenCorpusRegistry.from_dict(raw)


def build_evidence_graph_manifest(
    graph: EvidenceGraph, registry: FrozenCorpusRegistry
) -> dict[str, JSONValue]:
    """Build the path/time-independent commit manifest for graph artifacts."""

    if graph.corpus_snapshot != registry.corpus_snapshot:
        raise _validation_error(
            "manifest.corpus_snapshot", "graph and registry snapshots do not match"
        )
    return {
        "version": EVIDENCE_GRAPH_MANIFEST_VERSION,
        "evidence_graph": graph.version,
        "corpus_registry": registry.version,
        "corpus_snapshot": graph.corpus_snapshot,
        "evidence_graph_hash": graph.graph_sha256,
        "corpus_registry_hash": registry.corpus_sha256,
        "graph_corpus_hash": graph.corpus_sha256,
        "graph_stamp": graph.graph_stamp,
        "registry_stamp": registry.corpus_stamp,
        "graph_corpus_stamp": graph.corpus_stamp,
        "counts": {
            "registry_entries": len(registry.entries),
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "support_spans": len(graph.support_spans),
        },
        "files": {
            "nodes": NODES_FILENAME,
            "edges": EDGES_FILENAME,
            "support_spans": SUPPORT_SPANS_FILENAME,
            "corpus_registry": CORPUS_REGISTRY_FILENAME,
        },
    }


def save_evidence_graph_manifest(
    graph: EvidenceGraph,
    registry: FrozenCorpusRegistry,
    path_or_directory: str | Path,
) -> None:
    path = Path(path_or_directory)
    if path.name != MANIFEST_FILENAME and path.suffix.lower() != ".json":
        path = path / MANIFEST_FILENAME
    save_json(path, build_evidence_graph_manifest(graph, registry))


def load_evidence_graph_manifest(path_or_directory: str | Path) -> dict[str, JSONValue]:
    """Load and strictly validate a persisted graph commit manifest."""

    path = Path(path_or_directory)
    if path.name != MANIFEST_FILENAME and path.suffix.lower() != ".json":
        path = path / MANIFEST_FILENAME
    raw = load_json(path)
    if not isinstance(raw, dict):
        raise EvidenceGraphFormatError(f"{path}: manifest must be an object")
    required = {
        "version",
        "evidence_graph",
        "corpus_registry",
        "corpus_snapshot",
        "evidence_graph_hash",
        "corpus_registry_hash",
        "graph_corpus_hash",
        "graph_stamp",
        "registry_stamp",
        "graph_corpus_stamp",
        "counts",
        "files",
    }
    _check_record_keys(raw, required=required, optional=set(), path=str(path))
    if raw["version"] != EVIDENCE_GRAPH_MANIFEST_VERSION:
        raise _format_error(
            "manifest.version", f"must be {EVIDENCE_GRAPH_MANIFEST_VERSION!r}"
        )
    if raw["evidence_graph"] != EVIDENCE_GRAPH_VERSION:
        raise _format_error(
            "manifest.evidence_graph", f"must be {EVIDENCE_GRAPH_VERSION!r}"
        )
    if raw["corpus_registry"] != CORPUS_REGISTRY_VERSION:
        raise _format_error(
            "manifest.corpus_registry", f"must be {CORPUS_REGISTRY_VERSION!r}"
        )
    _validate_id(raw["corpus_snapshot"], "manifest.corpus_snapshot")
    for field_name in (
        "evidence_graph_hash",
        "corpus_registry_hash",
        "graph_corpus_hash",
    ):
        _validate_sha256(raw[field_name], f"manifest.{field_name}")
    counts = raw["counts"]
    files = raw["files"]
    if not isinstance(counts, dict) or not isinstance(files, dict):
        raise _format_error("manifest", "counts and files must be objects")
    expected_count_keys = {"registry_entries", "nodes", "edges", "support_spans"}
    if set(counts) != expected_count_keys:
        raise _format_error(
            "manifest.counts", f"keys must be exactly {sorted(expected_count_keys)!r}"
        )
    for key, value in counts.items():
        if type(value) is not int or value < 0:
            raise _format_error(f"manifest.counts.{key}", "must be a non-negative integer")
    expected_files = {
        "nodes": NODES_FILENAME,
        "edges": EDGES_FILENAME,
        "support_spans": SUPPORT_SPANS_FILENAME,
        "corpus_registry": CORPUS_REGISTRY_FILENAME,
    }
    if files != expected_files:
        raise _format_error(
            "manifest.files", f"must be exactly {expected_files!r}"
        )
    if raw["graph_stamp"] != f"evidence-graph-v1:sha256:{raw['evidence_graph_hash']}":
        raise _format_error("manifest.graph_stamp", "does not match evidence_graph_hash")
    if raw["registry_stamp"] != (
        f"corpus-registry-v1:sha256:{raw['corpus_registry_hash']}"
    ):
        raise _format_error("manifest.registry_stamp", "does not match corpus_registry_hash")
    if raw["graph_corpus_stamp"] != (
        f"graph-corpus-v1:sha256:{raw['graph_corpus_hash']}"
    ):
        raise _format_error("manifest.graph_corpus_stamp", "does not match graph_corpus_hash")
    return raw


def _load_graph_records_without_blobs(directory: Path) -> EvidenceGraph:
    nodes = tuple(
        EvidenceNode.from_dict(record)
        for record in load_jsonl(directory / NODES_FILENAME)
    )
    edges = tuple(
        EvidenceEdge.from_dict(record)
        for record in load_jsonl(directory / EDGES_FILENAME)
    )
    spans = tuple(
        SupportSpan.from_dict(record)
        for record in load_jsonl(directory / SUPPORT_SPANS_FILENAME)
    )
    snapshots = {node.corpus_snapshot for node in nodes}
    if len(snapshots) != 1:
        raise _validation_error(
            "nodes.corpus_snapshot",
            f"expected exactly one snapshot, found {sorted(snapshots)!r}",
        )
    return EvidenceGraph(next(iter(snapshots)), nodes, edges, spans)


def _verify_structure_without_blobs(
    graph: EvidenceGraph, registry: FrozenCorpusRegistry
) -> None:
    """Verify graph topology/registry identity without claiming byte support."""

    if graph.corpus_snapshot != registry.corpus_snapshot:
        raise _validation_error(
            "corpus_snapshot", "graph and registry snapshots do not match"
        )
    nodes: dict[str, EvidenceNode] = {}
    source_identities: dict[str, tuple[SourceType, str, str]] = {}
    for node in graph.nodes:
        if node.evidence_id in nodes:
            raise _validation_error("nodes", f"duplicate evidence_id {node.evidence_id!r}")
        nodes[node.evidence_id] = node
        if not registry.contains(node):
            raise _validation_error(
                f"node[{node.evidence_id}].source_url",
                "node identity is not present in the persisted full registry",
            )
        identity = (node.source_type, node.content_sha256, node.corpus_snapshot)
        previous = source_identities.get(node.source_url)
        if previous is not None and previous != identity:
            raise _validation_error(
                f"node[{node.evidence_id}].source_url", "conflicting frozen source identity"
            )
        source_identities[node.source_url] = identity

    edge_ids: set[str] = set()
    edge_triples: set[tuple[str, EdgeRelation, str]] = set()
    for edge in graph.edges:
        if edge.edge_id in edge_ids:
            raise _validation_error("edges", f"duplicate edge_id {edge.edge_id!r}")
        edge_ids.add(edge.edge_id)
        if edge.source_id not in nodes or edge.target_id not in nodes:
            raise _validation_error(
                f"edge[{edge.edge_id}]", "contains a dangling endpoint"
            )
        triple = (edge.source_id, edge.relation, edge.target_id)
        if triple in edge_triples:
            raise _validation_error(f"edge[{edge.edge_id}]", "duplicate typed edge")
        edge_triples.add(triple)

    span_ids: set[str] = set()
    for span in graph.support_spans:
        if span.support_span_id in span_ids:
            raise _validation_error(
                "support_spans", f"duplicate support_span_id {span.support_span_id!r}"
            )
        span_ids.add(span.support_span_id)
        node = nodes.get(span.evidence_id)
        if node is None:
            raise _validation_error(
                f"span[{span.support_span_id}]", "references an unknown evidence node"
            )
        if span.source_url != node.source_url:
            raise _validation_error(
                f"span[{span.support_span_id}].source_url",
                "does not match evidence node source_url",
            )
        if span.support_type is SupportType.BODY and not node.body_support:
            raise _validation_error(
                f"span[{span.support_span_id}]", "body support is disabled on node"
            )
        if (
            span.support_type is SupportType.SEARCH_SNIPPET
            and not node.search_snippet_support
        ):
            raise _validation_error(
                f"span[{span.support_span_id}]", "snippet support is disabled on node"
            )

    _validate_semantic_assertion_layer(nodes, graph.edges, graph.support_spans)


def _require_canonical_artifact(path: Path, expected: bytes) -> None:
    try:
        actual = path.read_bytes()
    except OSError as exc:
        raise EvidenceGraphValidationError(f"{path}: cannot read artifact: {exc}") from exc
    if actual != expected:
        raise _validation_error(
            str(path), "artifact bytes are non-canonical or have drifted"
        )


def verify_evidence_graph_manifest(
    directory: str | Path,
) -> dict[str, JSONValue]:
    """Recompute and verify a graph artifact set without loading source blobs.

    This verifies canonical artifact bytes, graph/registry structure, exact
    node membership, counts, fixed filenames, raw hashes and readable stamps.
    It deliberately does *not* claim that source bytes/support spans are valid;
    that stronger check remains :meth:`EvidenceGraph.validate` with a blob
    loader.  The function is suitable for protocol builders that need to pin a
    prevalidated artifact set without fetching the corpus again.
    """

    source = Path(directory)
    graph = _load_graph_records_without_blobs(source)
    registry = load_corpus_registry(source)
    manifest = load_evidence_graph_manifest(source)
    _verify_structure_without_blobs(graph, registry)

    _require_canonical_artifact(
        source / NODES_FILENAME,
        _canonical_jsonl_bytes(node.to_dict() for node in graph.nodes),
    )
    _require_canonical_artifact(
        source / EDGES_FILENAME,
        _canonical_jsonl_bytes(edge.to_dict() for edge in graph.edges),
    )
    _require_canonical_artifact(
        source / SUPPORT_SPANS_FILENAME,
        _canonical_jsonl_bytes(span.to_dict() for span in graph.support_spans),
    )
    _require_canonical_artifact(
        source / CORPUS_REGISTRY_FILENAME,
        canonical_json_bytes(registry.to_dict()) + b"\n",
    )
    _require_canonical_artifact(
        source / MANIFEST_FILENAME,
        canonical_json_bytes(manifest) + b"\n",
    )

    expected = build_evidence_graph_manifest(graph, registry)
    if manifest != expected:
        differing = sorted(
            key for key in set(manifest) | set(expected) if manifest.get(key) != expected.get(key)
        )
        raise _validation_error(
            "manifest", f"does not match graph/registry artifacts: {', '.join(differing)}"
        )
    return manifest


def save_graph(
    graph: EvidenceGraph,
    directory: str | Path,
    *,
    blob_loader: BlobLoader | None,
    corpus_membership: MembershipHook | None,
) -> None:
    """Validate and save canonical graph files plus a typed full registry.

    When ``corpus_membership`` is a :class:`FrozenCorpusRegistry`, the complete
    registry (including valid pages unused by graph nodes) is persisted as
    ``corpus_registry.json``.  Custom membership hooks remain supported for
    unit/integration uses, but cannot be serialized by this function.
    """

    graph.validate(blob_loader=blob_loader, corpus_membership=corpus_membership)
    destination = Path(directory)
    save_jsonl(
        destination / NODES_FILENAME,
        (
            node.to_dict()
            for node in sorted(graph.nodes, key=lambda item: item.evidence_id)
        ),
    )
    save_jsonl(
        destination / EDGES_FILENAME,
        (edge.to_dict() for edge in sorted(graph.edges, key=lambda item: item.edge_id)),
    )
    save_jsonl(
        destination / SUPPORT_SPANS_FILENAME,
        (
            span.to_dict()
            for span in sorted(graph.support_spans, key=lambda item: item.support_span_id)
        ),
    )
    if isinstance(corpus_membership, FrozenCorpusRegistry):
        save_corpus_registry(corpus_membership, destination)
        # Written last: consumers can treat a valid manifest as the commit
        # marker for the graph/registry artifact set.
        save_evidence_graph_manifest(graph, corpus_membership, destination)


def load_graph(
    directory: str | Path,
    *,
    blob_loader: BlobLoader | None,
    corpus_membership: MembershipHook | None = None,
) -> EvidenceGraph:
    """Load and strictly validate the three canonical graph JSONL files."""

    source = Path(directory)
    nodes = tuple(
        EvidenceNode.from_dict(record) for record in load_jsonl(source / NODES_FILENAME)
    )
    edges = tuple(
        EvidenceEdge.from_dict(record) for record in load_jsonl(source / EDGES_FILENAME)
    )
    support_spans = tuple(
        SupportSpan.from_dict(record)
        for record in load_jsonl(source / SUPPORT_SPANS_FILENAME)
    )
    snapshots = {node.corpus_snapshot for node in nodes}
    if len(snapshots) != 1:
        raise _validation_error(
            "nodes.corpus_snapshot",
            f"expected exactly one snapshot, found {sorted(snapshots)!r}",
        )
    graph = EvidenceGraph(
        corpus_snapshot=next(iter(snapshots)),
        nodes=nodes,
        edges=edges,
        support_spans=support_spans,
    )
    if corpus_membership is None:
        # This remains fail-closed: absence/invalidity of the independent
        # persisted registry raises rather than treating the source blobs as
        # proof of membership.
        corpus_membership = load_corpus_registry(source)
    return graph.validate(
        blob_loader=blob_loader,
        corpus_membership=corpus_membership,
    )


def load_graph_structure(directory: str | Path) -> EvidenceGraph:
    """Load a canonical, manifest-pinned graph without re-reading corpus blobs.

    This is intended for deterministic downstream compilation after the graph
    was built with :func:`save_graph`.  It verifies the complete artifact set,
    registry membership, topology and semantic assertion layer.  It does not
    replace :func:`load_graph` at corpus-ingestion time because it cannot
    independently replay support-span bytes.
    """

    source = Path(directory)
    verify_evidence_graph_manifest(source)
    return _load_graph_records_without_blobs(source)


# Explicit aliases make downstream code self-documenting without creating a
# second schema vocabulary.
EvidenceNodeType = NodeType
RelationType = EdgeRelation


__all__ = [
    "BlobLoader",
    "CORPUS_REGISTRY_FILENAME",
    "CORPUS_REGISTRY_VERSION",
    "CorpusRegistry",
    "DiscoveryMethod",
    "EDGES_FILENAME",
    "EVIDENCE_GRAPH_VERSION",
    "EVIDENCE_GRAPH_MANIFEST_VERSION",
    "EdgeRelation",
    "EvidenceEdge",
    "EvidenceGraph",
    "EvidenceGraphError",
    "EvidenceGraphFormatError",
    "EvidenceGraphValidationError",
    "EvidenceNode",
    "EvidenceNodeType",
    "FrozenCorpusEntry",
    "FrozenCorpusRegistry",
    "MembershipHook",
    "MANIFEST_FILENAME",
    "NODES_FILENAME",
    "NodeType",
    "RelationType",
    "SUPPORT_SPANS_FILENAME",
    "SourceType",
    "SupportSpan",
    "SupportType",
    "ValidationError",
    "canonical_json_bytes",
    "build_evidence_graph_manifest",
    "load_graph",
    "load_graph_structure",
    "load_corpus_registry",
    "load_evidence_graph_manifest",
    "load_json",
    "load_jsonl",
    "save_graph",
    "save_corpus_registry",
    "save_evidence_graph_manifest",
    "save_json",
    "save_jsonl",
    "sha256_bytes",
    "source_is_frozen_member",
    "verify_evidence_graph_manifest",
]
