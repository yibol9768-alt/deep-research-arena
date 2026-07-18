"""Schema and compiler for DRA Route A query-derived rubrics.

Route A keeps the natural v2 research query, but replaces the old weighted
``fact + proof_of_fetch + completeness`` score with a frozen set of necessary
but not sufficient rubric atoms.  The same atom is used for report coverage
and grounded coverage, so the denominator has a clear interpretation.

This module deliberately performs no LLM or network calls.  An LLM may propose
atom drafts, but a reviewed/frozen artifact must pass these deterministic
checks before it can be scored.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.verifiers.citation_format import canonicalize_url


SCHEMA_VERSION = "query_rubric_v1"
SCORING_SEMANTICS = "grounded_requirements_v1"
RUBRIC_STATUSES = frozenset({"draft", "reviewed", "frozen"})
ATOM_TYPES = frozenset({"entity", "option", "dimension", "source_role", "synthesis"})
SOURCE_ROLES = frozenset({"shopping", "forums", "wiki"})
OBSERVATION_MODES = frozenset({"body", "snippet_or_body"})


class RubricValidationError(ValueError):
    """Raised when a Route A rubric is ambiguous or not scoreable."""


def query_sha256(query: str) -> str:
    return hashlib.sha256(query.strip().encode("utf-8")).hexdigest()


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _strings(value: Any, field_name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise RubricValidationError(f"{field_name} must be a list")
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text and not allow_empty:
            raise RubricValidationError(f"{field_name} contains an empty string")
        if text:
            out.append(text)
    return tuple(out)


def _term_groups(value: Any, field_name: str) -> tuple[tuple[str, ...], ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise RubricValidationError(f"{field_name} must be a list of alternative-term lists")
    groups: list[tuple[str, ...]] = []
    for index, group in enumerate(value):
        terms = _strings(group, f"{field_name}[{index}]")
        if not terms:
            raise RubricValidationError(f"{field_name}[{index}] must not be empty")
        groups.append(terms)
    return tuple(groups)


@dataclass(frozen=True)
class TextMatcher:
    """Deterministic text contract.

    Every ``all_term_groups`` group must contribute at least one alternative.
    When phrases or regexes are present, at least one of those patterns must
    also match.  This supports both broad discussion atoms and narrower claims.
    """

    all_term_groups: tuple[tuple[str, ...], ...] = ()
    accepted_phrases: tuple[str, ...] = ()
    accepted_regex: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None, field_name: str) -> "TextMatcher":
        if not isinstance(raw, Mapping):
            raise RubricValidationError(f"{field_name} must be an object")
        matcher = cls(
            all_term_groups=_term_groups(raw.get("all_term_groups"), f"{field_name}.all_term_groups"),
            accepted_phrases=_strings(raw.get("accepted_phrases"), f"{field_name}.accepted_phrases"),
            accepted_regex=_strings(raw.get("accepted_regex"), f"{field_name}.accepted_regex"),
        )
        if not matcher.has_contract:
            raise RubricValidationError(f"{field_name} has no matching contract")
        for pattern in matcher.accepted_regex:
            try:
                re.compile(pattern, re.IGNORECASE | re.DOTALL)
            except re.error as exc:
                raise RubricValidationError(f"invalid regex in {field_name}: {exc}") from exc
        return matcher

    @property
    def has_contract(self) -> bool:
        return bool(self.all_term_groups or self.accepted_phrases or self.accepted_regex)

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_term_groups": [list(group) for group in self.all_term_groups],
            "accepted_phrases": list(self.accepted_phrases),
            "accepted_regex": list(self.accepted_regex),
        }


@dataclass(frozen=True)
class SupportWitness:
    """One authoring-time proof that an atom is answerable in the corpus.

    Witnesses gate freezing only.  They are not an exhaustive URL whitelist
    and the runtime scorer accepts equivalent observed support.
    """

    evidence_id: str
    source_url: str
    source_role: str
    support_span_sha256: str
    approved: bool = False

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], field_name: str) -> "SupportWitness":
        if not isinstance(raw, Mapping):
            raise RubricValidationError(f"{field_name} must be an object")
        evidence_id = str(raw.get("evidence_id") or "").strip()
        source_url = str(raw.get("source_url") or "").strip()
        source_role = str(raw.get("source_role") or "").strip()
        span_hash = str(raw.get("support_span_sha256") or "").strip().lower()
        approved = raw.get("approved", False)
        if not evidence_id:
            raise RubricValidationError(f"{field_name}.evidence_id is required")
        if not re.match(r"^https?://", source_url, re.IGNORECASE):
            raise RubricValidationError(f"{field_name}.source_url must be HTTP(S)")
        if source_role not in SOURCE_ROLES:
            raise RubricValidationError(f"{field_name}.source_role is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", span_hash):
            raise RubricValidationError(f"{field_name}.support_span_sha256 must be SHA-256")
        if type(approved) is not bool:
            raise RubricValidationError(f"{field_name}.approved must be boolean")
        return cls(evidence_id, source_url, source_role, span_hash, approved)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_url": self.source_url,
            "source_role": self.source_role,
            "support_span_sha256": self.support_span_sha256,
            "approved": self.approved,
        }


@dataclass(frozen=True)
class EvidenceContract:
    acceptable_source_roles: tuple[str, ...]
    required_source_roles: tuple[str, ...]
    relevance_contract: TextMatcher
    minimum_distinct_sources: int = 1
    observation_mode: str = "body"
    track_discovery: bool = True
    citation_binding_window_chars: int = 500
    evidence_window_chars: int = 1500
    acceptable_source_urls: tuple[str, ...] = ()
    known_support: tuple[SupportWitness, ...] = ()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None, field_name: str) -> "EvidenceContract":
        if not isinstance(raw, Mapping):
            raise RubricValidationError(f"{field_name} must be an object")
        roles = _strings(raw.get("acceptable_source_roles"), f"{field_name}.acceptable_source_roles")
        unknown = sorted(set(roles) - SOURCE_ROLES)
        if unknown:
            raise RubricValidationError(f"{field_name} has unknown source roles: {unknown}")
        required_roles = _strings(
            raw.get("required_source_roles"), f"{field_name}.required_source_roles"
        )
        invalid_required = sorted(set(required_roles) - set(roles))
        if invalid_required:
            raise RubricValidationError(
                f"{field_name}.required_source_roles must be acceptable: {invalid_required}"
            )
        urls = _strings(raw.get("acceptable_source_urls"), f"{field_name}.acceptable_source_urls")
        if not roles and not urls:
            raise RubricValidationError(
                f"{field_name} needs acceptable_source_roles or acceptable_source_urls"
            )
        minimum = raw.get("minimum_distinct_sources", 1)
        if type(minimum) is not int or minimum < 1:
            raise RubricValidationError(f"{field_name}.minimum_distinct_sources must be >= 1")
        if "support" in raw or "support_mode" in raw or "support_window_chars" in raw:
            raise RubricValidationError(
                f"{field_name}: support terminology is retired; use relevance_contract, observation_mode and evidence_window_chars"
            )
        mode = str(raw.get("observation_mode") or "body")
        if mode not in OBSERVATION_MODES:
            raise RubricValidationError(
                f"{field_name}.observation_mode must be one of {sorted(OBSERVATION_MODES)}"
            )
        if "require_discovery" in raw:
            raise RubricValidationError(
                f"{field_name}.require_discovery is retired; use track_discovery as a diagnostic"
            )
        track_discovery = raw.get("track_discovery", True)
        if type(track_discovery) is not bool:
            raise RubricValidationError(f"{field_name}.track_discovery must be boolean")
        binding_window = raw.get("citation_binding_window_chars", 500)
        if type(binding_window) is not int or not 100 <= binding_window <= 2000:
            raise RubricValidationError(
                f"{field_name}.citation_binding_window_chars must be in [100, 2000]"
            )
        evidence_window = raw.get("evidence_window_chars", 1500)
        if type(evidence_window) is not int or not 200 <= evidence_window <= 5000:
            raise RubricValidationError(
                f"{field_name}.evidence_window_chars must be in [200, 5000]"
            )
        witnesses_raw = raw.get("known_support") or []
        if not isinstance(witnesses_raw, list):
            raise RubricValidationError(f"{field_name}.known_support must be a list")
        witnesses = tuple(
            SupportWitness.from_dict(value, f"{field_name}.known_support[{index}]")
            for index, value in enumerate(witnesses_raw)
        )
        for witness in witnesses:
            if roles and witness.source_role not in roles:
                raise RubricValidationError(
                    f"{field_name}: witness role {witness.source_role!r} is not acceptable"
                )
        return cls(
            acceptable_source_roles=roles,
            required_source_roles=required_roles,
            acceptable_source_urls=urls,
            relevance_contract=TextMatcher.from_dict(
                raw.get("relevance_contract"), f"{field_name}.relevance_contract"
            ),
            minimum_distinct_sources=minimum,
            observation_mode=mode,
            track_discovery=track_discovery,
            citation_binding_window_chars=binding_window,
            evidence_window_chars=evidence_window,
            known_support=witnesses,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "acceptable_source_roles": list(self.acceptable_source_roles),
            "required_source_roles": list(self.required_source_roles),
            "acceptable_source_urls": list(self.acceptable_source_urls),
            "minimum_distinct_sources": self.minimum_distinct_sources,
            "observation_mode": self.observation_mode,
            "track_discovery": self.track_discovery,
            "citation_binding_window_chars": self.citation_binding_window_chars,
            "evidence_window_chars": self.evidence_window_chars,
            "relevance_contract": self.relevance_contract.to_dict(),
            "known_support": [witness.to_dict() for witness in self.known_support],
        }


@dataclass(frozen=True)
class RubricAtom:
    atom_id: str
    atom_type: str
    description: str
    mention: TextMatcher
    response_contract: TextMatcher
    evidence: EvidenceContract
    approved: bool = False
    review_note: str = ""

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], index: int) -> "RubricAtom":
        if not isinstance(raw, Mapping):
            raise RubricValidationError(f"atoms[{index}] must be an object")
        atom_id = str(raw.get("atom_id") or "").strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{1,63}", atom_id):
            raise RubricValidationError(f"atoms[{index}].atom_id is invalid: {atom_id!r}")
        atom_type = str(raw.get("atom_type") or "").strip()
        if atom_type not in ATOM_TYPES:
            raise RubricValidationError(f"{atom_id}.atom_type must be one of {sorted(ATOM_TYPES)}")
        description = str(raw.get("description") or "").strip()
        if not description:
            raise RubricValidationError(f"{atom_id}.description is required")
        if raw.get("required", True) is not True:
            raise RubricValidationError(
                f"{atom_id}: score-bearing Route A atoms are all required; move optional diagnostics outside atoms"
            )
        if "weight" in raw:
            raise RubricValidationError(f"{atom_id}: atom weights are forbidden in grounded_requirements_v1")
        approved = raw.get("approved", False)
        if type(approved) is not bool:
            raise RubricValidationError(f"{atom_id}.approved must be boolean")
        return cls(
            atom_id=atom_id,
            atom_type=atom_type,
            description=description,
            mention=TextMatcher.from_dict(raw.get("mention"), f"{atom_id}.mention"),
            response_contract=TextMatcher.from_dict(
                raw.get("response_contract"), f"{atom_id}.response_contract"
            ),
            evidence=EvidenceContract.from_dict(raw.get("evidence"), f"{atom_id}.evidence"),
            approved=approved,
            review_note=str(raw.get("review_note") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "atom_type": self.atom_type,
            "description": self.description,
            "required": True,
            "mention": self.mention.to_dict(),
            "response_contract": self.response_contract.to_dict(),
            "evidence": self.evidence.to_dict(),
            "approved": self.approved,
            "review_note": self.review_note,
        }


@dataclass(frozen=True)
class QueryRubric:
    task_id: str
    task_version: Any
    query: str
    query_hash: str
    cluster: str
    archetype: str
    status: str
    atoms: tuple[RubricAtom, ...]
    authoring: dict[str, Any] = field(default_factory=dict)
    evidence_graph_stamp: str | None = None
    corpus_registry_hash: str | None = None
    schema_version: str = SCHEMA_VERSION
    scoring_semantics: str = SCORING_SEMANTICS

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "QueryRubric":
        if not isinstance(raw, Mapping):
            raise RubricValidationError("query rubric must be an object")
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise RubricValidationError(f"schema_version must be {SCHEMA_VERSION!r}")
        if raw.get("scoring_semantics") != SCORING_SEMANTICS:
            raise RubricValidationError(f"scoring_semantics must be {SCORING_SEMANTICS!r}")
        task_id = str(raw.get("task_id") or "").strip()
        query = str(raw.get("query") or "").strip()
        if not task_id or not query:
            raise RubricValidationError("task_id and query are required")
        declared_hash = str(raw.get("query_sha256") or "").strip()
        actual_hash = query_sha256(query)
        if declared_hash != actual_hash:
            raise RubricValidationError("query_sha256 does not match the frozen query")
        status = str(raw.get("status") or "").strip()
        if status not in RUBRIC_STATUSES:
            raise RubricValidationError(f"status must be one of {sorted(RUBRIC_STATUSES)}")
        atoms_raw = raw.get("atoms")
        if not isinstance(atoms_raw, list) or not atoms_raw:
            raise RubricValidationError("atoms must be a non-empty list")
        atoms = tuple(RubricAtom.from_dict(atom, i) for i, atom in enumerate(atoms_raw))
        ids = [atom.atom_id for atom in atoms]
        if len(ids) != len(set(ids)):
            raise RubricValidationError("atom_id values must be unique")
        if status in {"reviewed", "frozen"} and not all(atom.approved for atom in atoms):
            raise RubricValidationError(f"all atoms must be approved when status={status!r}")
        authoring = raw.get("authoring") or {}
        if not isinstance(authoring, Mapping):
            raise RubricValidationError("authoring must be an object")
        reviewers = authoring.get("reviewers") or []
        if status == "frozen":
            if not isinstance(reviewers, list) or not reviewers:
                raise RubricValidationError("a frozen rubric requires at least one named reviewer")
            if not raw.get("evidence_graph_stamp") or not raw.get("corpus_registry_hash"):
                raise RubricValidationError(
                    "a frozen rubric requires evidence_graph_stamp and corpus_registry_hash"
                )
            for atom in atoms:
                witnesses = atom.evidence.known_support
                approved_urls = {
                    witness.source_url for witness in witnesses if witness.approved
                }
                if len(approved_urls) < atom.evidence.minimum_distinct_sources:
                    raise RubricValidationError(
                        f"{atom.atom_id}: frozen atom lacks enough approved known_support witnesses"
                    )
                witnessed_roles = {
                    witness.source_role for witness in witnesses if witness.approved
                }
                missing_roles = set(atom.evidence.required_source_roles) - witnessed_roles
                if missing_roles:
                    raise RubricValidationError(
                        f"{atom.atom_id}: frozen atom lacks witnesses for required roles {sorted(missing_roles)}"
                    )
        artifact = cls(
            task_id=task_id,
            task_version=raw.get("task_version"),
            query=query,
            query_hash=actual_hash,
            cluster=str(raw.get("cluster") or "").strip(),
            archetype=str(raw.get("archetype") or "").strip(),
            status=status,
            atoms=atoms,
            authoring=dict(authoring),
            evidence_graph_stamp=(str(raw["evidence_graph_stamp"]) if raw.get("evidence_graph_stamp") else None),
            corpus_registry_hash=(str(raw["corpus_registry_hash"]) if raw.get("corpus_registry_hash") else None),
        )
        declared_artifact_hash = raw.get("rubric_sha256")
        if declared_artifact_hash and declared_artifact_hash != artifact.content_sha256:
            raise RubricValidationError("rubric_sha256 does not match rubric content")
        return artifact

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "scoring_semantics": self.scoring_semantics,
            "task_id": self.task_id,
            "task_version": self.task_version,
            "query": self.query,
            "query_sha256": self.query_hash,
            "cluster": self.cluster,
            "archetype": self.archetype,
            "status": self.status,
            "atoms": [atom.to_dict() for atom in self.atoms],
            "authoring": dict(self.authoring),
        }
        if self.evidence_graph_stamp:
            out["evidence_graph_stamp"] = self.evidence_graph_stamp
        if self.corpus_registry_hash:
            out["corpus_registry_hash"] = self.corpus_registry_hash
        if include_hash:
            out["rubric_sha256"] = canonical_json_sha256(out)
        return out


def _task_query(task: Mapping[str, Any]) -> str:
    for key in ("intent", "query", "prompt"):
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise RubricValidationError("task has no intent/query/prompt string")


def compile_query_rubric(
    task: Mapping[str, Any],
    atom_drafts: Iterable[Mapping[str, Any]],
    *,
    status: str = "draft",
    reviewers: Iterable[str] = (),
    generator: str = "manual_or_llm_proposal_then_deterministic_review",
    evidence_graph_stamp: str | None = None,
    corpus_registry_hash: str | None = None,
) -> QueryRubric:
    """Compile atom drafts against the exact public v2 task.

    Stale ``synthesis_requirements`` are intentionally ignored.  Atoms must be
    supplied from a query plus evidence-graph review, then frozen explicitly.
    """

    query = _task_query(task)
    tri_source = task.get("tri_source") if isinstance(task.get("tri_source"), Mapping) else {}
    raw = {
        "schema_version": SCHEMA_VERSION,
        "scoring_semantics": SCORING_SEMANTICS,
        "task_id": task.get("task_id") or task.get("id"),
        "task_version": task.get("task_version"),
        "query": query,
        "query_sha256": query_sha256(query),
        "cluster": tri_source.get("cluster") or task.get("cluster") or "",
        "archetype": tri_source.get("archetype") or task.get("archetype") or "",
        "status": status,
        "atoms": list(atom_drafts),
        "authoring": {
            "source": "query_plus_evidence_graph",
            "generator": generator,
            "reviewers": [str(value).strip() for value in reviewers if str(value).strip()],
            "notes": "Necessary but not sufficient breadth obligations; no unique route or URL is required.",
        },
    }
    if evidence_graph_stamp:
        raw["evidence_graph_stamp"] = evidence_graph_stamp
    if corpus_registry_hash:
        raw["corpus_registry_hash"] = corpus_registry_hash
    return QueryRubric.from_dict(raw)


def load_query_rubric(path_or_mapping: str | Path | Mapping[str, Any]) -> QueryRubric:
    if isinstance(path_or_mapping, Mapping):
        return QueryRubric.from_dict(path_or_mapping)
    with Path(path_or_mapping).open(encoding="utf-8") as handle:
        return QueryRubric.from_dict(json.load(handle))


def _json_or_jsonl(path: Path) -> list[Mapping[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(value, Mapping):
        unpacked = False
        for key in ("nodes", "support_spans", "entries"):
            if isinstance(value.get(key), list):
                value = value[key]
                unpacked = True
                break
        if not unpacked:
            value = [value]
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        raise RubricValidationError(f"{path} is not a JSON/JSONL object collection")
    return list(value)


def audit_known_support_directory(
    rubric: QueryRubric,
    evidence_graph_dir: str | Path,
) -> dict[str, Any]:
    """Replay authoring witnesses against graph nodes, spans and registry.

    This is a freeze gate, not a runtime URL whitelist.
    """

    root = Path(evidence_graph_dir)
    required = {
        "nodes": root / "nodes.jsonl",
        "spans": root / "support_spans.jsonl",
        "registry": root / "corpus_registry.json",
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        return {
            "status": "failed",
            "reason_codes": ["known_support_audit_files_missing"],
            "missing_files": missing,
            "checked_witnesses": 0,
            "errors": [],
        }
    nodes = _json_or_jsonl(required["nodes"])
    spans = _json_or_jsonl(required["spans"])
    registry = _json_or_jsonl(required["registry"])
    nodes_by_id = {
        str(row.get("evidence_id")): row
        for row in nodes if row.get("evidence_id")
    }
    spans_by_evidence: dict[str, list[Mapping[str, Any]]] = {}
    for row in spans:
        spans_by_evidence.setdefault(str(row.get("evidence_id") or ""), []).append(row)
    corpus_urls = {
        canonicalize_url(str(row.get("source_url")))
        for row in registry
        if row.get("source_url") and row.get("in_corpus") is True
    }
    role_for_type = {
        "magento": "shopping",
        "shopping": "shopping",
        "shopping_product": "shopping",
        "postmill": "forums",
        "forum": "forums",
        "forums": "forums",
        "wikipedia": "wiki",
        "wiki": "wiki",
    }
    errors: list[dict[str, str]] = []
    checked = 0
    for atom in rubric.atoms:
        for witness in atom.evidence.known_support:
            checked += 1
            node = nodes_by_id.get(witness.evidence_id)
            prefix = {"atom_id": atom.atom_id, "evidence_id": witness.evidence_id}
            if node is None:
                errors.append({**prefix, "code": "witness_evidence_missing"})
                continue
            witness_url = canonicalize_url(witness.source_url)
            if canonicalize_url(str(node.get("source_url") or "")) != witness_url:
                errors.append({**prefix, "code": "witness_source_url_mismatch"})
            actual_role = role_for_type.get(str(node.get("source_type") or "").lower())
            if actual_role != witness.source_role:
                errors.append({**prefix, "code": "witness_source_role_mismatch"})
            if witness_url not in corpus_urls:
                errors.append({**prefix, "code": "witness_url_not_in_corpus_registry"})
            evidence_spans = spans_by_evidence.get(witness.evidence_id, [])
            if not any(
                str(span.get("sha256") or "").lower() == witness.support_span_sha256
                and canonicalize_url(str(span.get("source_url") or "")) == witness_url
                for span in evidence_spans
            ):
                errors.append({**prefix, "code": "witness_support_span_mismatch"})
    return {
        "status": "passed" if not errors and checked else "failed",
        "reason_codes": sorted({row["code"] for row in errors}),
        "checked_witnesses": checked,
        "errors": errors,
        "evidence_graph_dir": str(root),
    }
