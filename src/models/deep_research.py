"""Pydantic models for deep-research task files.

Lightweight — mirrors the WebArena JSON shape with three new sections:
`report_schema`, `citation_policy`, and `eval.report_expected`. See
`DEEP_RESEARCH_TASK_SPEC.md` for the narrative spec.
"""

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class CitationPolicy(BaseModel):
    required_for: List[str] = Field(default_factory=list)
    must_be_in_domain: List[str] = Field(default_factory=list)
    min_distinct_sources: int = 1


class FieldConstraint(BaseModel):
    """One expected constraint on a single item inside a report list field."""

    name_contains: Optional[List[str]] = None
    name_regex: Optional[str] = None
    price_range: Optional[Tuple[float, float]] = None
    rating_min: Optional[float] = None
    url_regex: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ReportExpected(BaseModel):
    """Whitelist of required facts the report must contain."""

    products: Optional[List[FieldConstraint]] = None
    facts: Optional[List[str]] = None
    numeric: Optional[Dict[str, Tuple[float, float]]] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class DREval(BaseModel):
    eval_types: List[str]
    report_expected: Optional[ReportExpected] = None
    source_count_min: Optional[int] = None
    reference_answers: Optional[Dict[str, Any]] = None
    reference_url: Optional[str] = None
    program_html: Optional[List[Dict[str, Any]]] = None


class DeepResearchTask(BaseModel):
    task_id: str = Field(..., pattern=r"^dr_[a-z]+_[0-9]{4}$")
    sites: List[str]
    intent: str
    start_url: str
    storage_state: Optional[str] = None
    require_login: bool = False

    report_schema: Dict[str, Any]
    citation_policy: CitationPolicy
    eval: DREval

    difficulty: Optional[int] = Field(None, ge=1, le=5)
    expected_steps: Optional[int] = Field(None, ge=1, le=50)
    author_notes: Optional[str] = None

    @classmethod
    def load(cls, path: str) -> "DeepResearchTask":
        import json as _json
        from pathlib import Path as _Path

        return cls.model_validate(_json.loads(_Path(path).read_text()))
