"""Tests for scripts/contamination_probe.py.

All tests are offline: the model backend is mocked, so no network is touched.
We cover:
  - topic extraction + intent neutralization (no sandbox placeholders leak)
  - golden-fact loading
  - confidence parsing (decimals + percentages)
  - abstention detection
  - scoring of a HEALTHY closed-book answer (generic / abstaining -> CLEAN)
  - scoring of a CONTAMINATED answer (leaked sandbox URL + golden price)
  - end-to-end run_probe with an injected mock answer fn
  - aggregate verdict + report rendering
  - the --dry-run CLI path writes a report and returns 0
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import the probe module by path so the test does not depend on packaging.
_SPEC = importlib.util.spec_from_file_location(
    "contamination_probe", ROOT / "scripts" / "contamination_probe.py"
)
cp = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
# Register before exec so dataclass type resolution (which looks the module up
# in sys.modules by __module__) works for the @dataclass definitions.
sys.modules["contamination_probe"] = cp
_SPEC.loader.exec_module(cp)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


SAMPLE_INTENT = (
    "Produce a comprehensive market-intelligence report on Consumer-grade audio "
    "headphones, spanning THREE dimensions. Enumerate products on the One Stop "
    "Market (`__SHOPPING__`) ... start_url __SHOPPING__/catalogsearch ... "
    "Harvest Postmill threads (`__REDDIT__`) ... Wikipedia (`__WIKIPEDIA__`). "
    "See http://localhost:7770/some-product.html for an example."
)


@pytest.fixture
def sample_task() -> dict:
    return {"task_id": "dr_cross_deep_0001", "intent": SAMPLE_INTENT}


@pytest.fixture
def sample_facts() -> "cp.TaskFacts":
    return cp.TaskFacts(
        task_id="dr_cross_deep_0001",
        topic="Consumer-grade audio headphones",
        sandbox_urls=["http://localhost:7770/some-headphones.html"],
        golden_prices={"$16.99", "$29.99"},
    )


# --------------------------------------------------------------------------- #
# Topic + neutralization
# --------------------------------------------------------------------------- #


def test_extract_topic():
    assert cp.extract_topic(SAMPLE_INTENT) == "Consumer-grade audio headphones"


def test_neutralize_intent_strips_sandbox_identity():
    neutral = cp.neutralize_intent(SAMPLE_INTENT)
    # Placeholders must be gone.
    assert "__SHOPPING__" not in neutral
    assert "__REDDIT__" not in neutral
    assert "__WIKIPEDIA__" not in neutral
    # Sandbox hosts / explicit urls must be gone.
    assert "localhost:7770" not in neutral
    assert "http://localhost" not in neutral
    # Neutral synonyms present.
    assert "an online store" in neutral
    assert "a community forum" in neutral
    assert "an encyclopedia" in neutral


# --------------------------------------------------------------------------- #
# Golden loading
# --------------------------------------------------------------------------- #


def test_load_task_facts_real_golden_if_present(sample_task):
    facts = cp.load_task_facts(sample_task)
    assert facts.task_id == "dr_cross_deep_0001"
    assert facts.topic == "Consumer-grade audio headphones"
    golden = ROOT / "data" / "golden" / "deep" / "dr_cross_deep_0001.json"
    if golden.exists():
        # Should have harvested at least some sandbox urls.
        assert len(facts.sandbox_urls) > 0


def test_load_task_facts_missing_golden_is_graceful():
    facts = cp.load_task_facts({"task_id": "dr_cross_deep_999999",
                                "intent": SAMPLE_INTENT})
    assert facts.sandbox_urls == []
    assert facts.golden_prices == set()


# --------------------------------------------------------------------------- #
# Confidence parsing + abstention
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text,expected", [
    ("blah\nCONFIDENCE: 0.05", 0.05),
    ("CONFIDENCE: 0", 0.0),
    ("CONFIDENCE: 1.0", 1.0),
    ("confidence: 85", 0.85),          # percentage form (>2) scaled by 100
    ("CONFIDENCE: 1.5", 1.0),          # just-above-1 typo clamped to 1.0
    ("no marker here", None),
])
def test_parse_confidence(text, expected):
    assert cp.parse_confidence(text) == expected


def test_detect_abstention():
    assert cp.detect_abstention("I cannot provide specific URLs without browsing.")
    assert cp.detect_abstention("I do not have access to the catalog.")
    assert not cp.detect_abstention("The headphones cost exactly $199 and are great.")


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def test_score_healthy_answer_is_clean(sample_facts):
    answer = cp.make_dry_run_answer(sample_facts)
    res = cp.score_answer(answer, sample_facts)
    assert res.sandbox_url_hits == 0
    assert res.golden_price_matches == 0
    assert res.abstained is True
    assert res.can_answer is False
    assert res.closed_book_specificity < 0.3
    assert res.verdict == "CLEAN"
    assert res.self_reported_confidence is not None
    assert res.self_reported_confidence < 0.2


def test_score_contaminated_answer(sample_facts):
    leaked_url = sample_facts.sandbox_urls[0]
    answer = (
        f"The best pick is [Model X]({leaked_url}) priced at $16.99 with a "
        "4.5 rating and 1200 reviews. Another is $29.99. CONFIDENCE: 0.9"
    )
    res = cp.score_answer(answer, sample_facts)
    assert res.sandbox_url_hits == 1
    assert res.golden_price_matches == 2          # $16.99 and $29.99
    assert res.invented_price_count >= 2
    assert res.can_answer is True
    assert res.closed_book_specificity >= 0.5
    assert res.verdict == "CONTAMINATED"


def test_score_suspicious_answer(sample_facts):
    # Confident, non-abstaining, invents generic prices but no sandbox leak and
    # no golden-price match.
    answer = (
        "Top headphones typically run $59, $129, and $249 depending on tier. "
        "Brand A is best. CONFIDENCE: 0.8"
    )
    res = cp.score_answer(answer, sample_facts)
    assert res.sandbox_url_hits == 0
    assert res.golden_price_matches == 0
    assert res.can_answer is True
    assert res.verdict in ("SUSPICIOUS", "CONTAMINATED")
    assert res.verdict == "SUSPICIOUS"


# --------------------------------------------------------------------------- #
# Orchestration + aggregate
# --------------------------------------------------------------------------- #


def test_run_probe_with_mock_answer_fn(sample_task):
    # Mock model that always returns the healthy canned answer.
    def mock_answer_fn(facts, neutral):
        # Guard: the neutralized intent handed to the model must not leak the
        # sandbox identity.
        assert "__SHOPPING__" not in neutral
        assert "localhost" not in neutral
        return cp.make_dry_run_answer(facts)

    results = cp.run_probe([sample_task], "mock-model", mock_answer_fn)
    assert len(results) == 1
    assert results[0].verdict == "CLEAN"


def test_aggregate_verdict_pass(sample_task):
    def mock_answer_fn(facts, neutral):
        return cp.make_dry_run_answer(facts)

    results = cp.run_probe([sample_task, sample_task], "mock", mock_answer_fn)
    summary = cp.aggregate_verdict(results)
    assert summary["overall"] == "PASS_NO_MEMORIZATION"
    assert summary["n_contaminated"] == 0
    assert summary["total_sandbox_url_leaks"] == 0


def test_aggregate_verdict_fail(sample_task, sample_facts):
    leaked = sample_facts.sandbox_urls[0]

    def mock_answer_fn(facts, neutral):
        return f"Buy [X]({leaked}) for $16.99 and $29.99. CONFIDENCE: 0.95"

    # Need facts that match; rewrite the task to use the same golden urls.
    results = cp.run_probe([sample_task], "mock", mock_answer_fn)
    # If the real golden for 0001 contains the leaked url, it will be CONTAMINATED.
    # To make the test deterministic regardless of repo data, score directly.
    res = cp.score_answer(
        f"Buy [X]({leaked}) for $16.99 and $29.99. CONFIDENCE: 0.95",
        sample_facts,
    )
    summary = cp.aggregate_verdict([res])
    assert summary["overall"] == "FAIL_CONTAMINATION_DETECTED"
    assert summary["n_contaminated"] == 1


# --------------------------------------------------------------------------- #
# Report rendering + CLI dry-run
# --------------------------------------------------------------------------- #


def test_render_report_contains_verdict(sample_task):
    def mock_answer_fn(facts, neutral):
        return cp.make_dry_run_answer(facts)

    results = cp.run_probe([sample_task], "mock", mock_answer_fn)
    summary = cp.aggregate_verdict(results)
    md = cp.render_report(results, summary, model="mock", dry_run=True)
    assert "# Contamination Probe Report" in md
    assert "Overall verdict" in md
    assert summary["overall"] in md
    assert "dr_cross_deep_0001" in md


def test_cli_dry_run_writes_report(tmp_path):
    report = tmp_path / "report.md"
    jsonp = tmp_path / "out.json"
    rc = cp.main([
        "--dry-run", "--num-tasks", "2",
        "--report-path", str(report),
        "--json-out", str(jsonp),
    ])
    assert rc == 0
    assert report.exists()
    text = report.read_text()
    assert "Contamination Probe Report" in text
    payload = json.loads(jsonp.read_text())
    assert payload["summary"]["overall"] == "PASS_NO_MEMORIZATION"
    assert len(payload["results"]) == 2
