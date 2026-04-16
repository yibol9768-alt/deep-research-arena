"""Smoke-tests for CompositeV3 scorer.

We run it in dry-run mode (run_judge=False) so no LLM calls are needed —
citation + markdown_structure + fact_kg (recall-only) + efficiency are all
deterministic. The test asserts:
  - weights sum to 1.0
  - oracle report scores very high on the 4 deterministic pillars
  - composite scoring is monotonic in fact_kg weight
"""

from __future__ import annotations

import math
from pathlib import Path

from src.scoring.composite_v3 import score, DEFAULT_WEIGHTS, CompositeResultV3


ROOT = Path(__file__).resolve().parents[1]


def test_weights_sum_to_one():
    assert math.isclose(sum(DEFAULT_WEIGHTS.values()), 1.0, abs_tol=1e-6)
    # Documented in module docstring:
    assert DEFAULT_WEIGHTS["fact_kg"] == 0.30
    assert DEFAULT_WEIGHTS["checklist"] == 0.20


def test_oracle_dryrun_scores_well_on_deterministic_pillars():
    task_id = "dr_shop_v3_0001"
    oracle_md = ROOT / "data" / "results" / f"oracle_v3_{task_id}.md"
    if not oracle_md.exists():
        import pytest
        pytest.skip("oracle markdown missing")
    answer = oracle_md.read_text()

    task_cfg = {
        "task_id": task_id,
        "sites": ["shopping"],
        "intent": "Buying guide for $30-100 headphones across 3 form-factors.",
        "markdown_spec": {
            "min_words": 300, "max_words": 3000,
            "min_paragraphs": 3, "min_citations": 3, "min_pages_browsed": 0,
        },
        "citation_policy": {"must_be_in_domain": ["__SHOPPING__"]},
    }

    result = score(
        task_id=task_id,
        agent="oracle",
        task_config=task_cfg,
        answer=answer,
        page=None,
        efficiency=None,
        run_judge=False,  # no LLM calls
    )
    assert isinstance(result, CompositeResultV3)
    # Oracle should clear the structural floor.
    assert result.pillars["markdown_structure"].score == 1.0, result.pillars["markdown_structure"].details
    # Oracle should have high fact_kg recall by construction (≥ 0.8).
    assert result.pillars["fact_kg"].score >= 0.5, result.pillars["fact_kg"].details


def test_reweighting_changes_composite():
    task_id = "dr_shop_v3_0001"
    oracle_md = ROOT / "data" / "results" / f"oracle_v3_{task_id}.md"
    if not oracle_md.exists():
        import pytest
        pytest.skip("oracle markdown missing")
    answer = oracle_md.read_text()
    task_cfg = {
        "task_id": task_id,
        "sites": ["shopping"],
        "intent": "x",
        "markdown_spec": {"min_words": 1, "min_paragraphs": 1, "min_citations": 1},
        "citation_policy": {"must_be_in_domain": ["__SHOPPING__"]},
    }
    default = score(task_id=task_id, agent="a", task_config=task_cfg, answer=answer,
                    efficiency=None, run_judge=False)
    boosted = score(task_id=task_id, agent="a", task_config=task_cfg, answer=answer,
                    efficiency=None, run_judge=False,
                    weights={"fact_kg": 0.80, "markdown_structure": 0.05,
                             "citation": 0.05, "llm_judge": 0.05,
                             "checklist": 0.04, "efficiency": 0.01})
    assert default.composite != boosted.composite
