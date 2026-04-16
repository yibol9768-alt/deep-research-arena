"""Tests for v3 task schema."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import DeepResearchTaskV3, MarkdownReportSpec, GoldenSpec, CitationPolicy


def _minimal_v3(**overrides):
    base = dict(
        task_id="dr_shop_v3_0001",
        sites=["shopping"],
        intent="Compare three headphone form-factors and recommend one with reasoning.",
        start_url="__SHOPPING__/",
        markdown_spec=MarkdownReportSpec(),
        citation_policy=CitationPolicy(must_be_in_domain=["__SHOPPING__"], min_distinct_sources=3),
    )
    base.update(overrides)
    return DeepResearchTaskV3(**base)


def test_v3_minimal_loads():
    t = _minimal_v3()
    assert t.schema_version.startswith("3.")
    assert t.markdown_spec.min_words == 500
    assert t.markdown_spec.require_markdown_links is True
    assert t.golden.triples_path is None  # optional


def test_v3_task_id_pattern_v2_rejected():
    """A v2-style task_id (`dr_shop_0001`) must NOT validate as v3."""
    with pytest.raises(Exception):
        _minimal_v3(task_id="dr_shop_0001")


def test_v3_intent_too_short_rejected():
    with pytest.raises(Exception):
        _minimal_v3(intent="too short")


def test_v3_markdown_spec_bounds():
    spec = MarkdownReportSpec(min_words=800, max_words=3000, min_paragraphs=5,
                              min_citations=10, min_pages_browsed=6)
    assert spec.min_words == 800
    with pytest.raises(Exception):
        MarkdownReportSpec(min_words=10)  # < 50 floor


def test_v3_round_trips_json():
    t = _minimal_v3(
        golden=GoldenSpec(triples_path="data/golden/dr_shop_v3_0001.json",
                          expected_predicates=["price", "rating"]),
        coverage_checklist_path="data/tasks/.../checklists_v3.json",
        difficulty=3, expected_steps=12,
    )
    blob = t.model_dump_json()
    t2 = DeepResearchTaskV3.model_validate_json(blob)
    assert t2.golden.expected_predicates == ["price", "rating"]
    assert t2.difficulty == 3
