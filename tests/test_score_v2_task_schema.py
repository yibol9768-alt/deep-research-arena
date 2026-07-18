import json
from pathlib import Path

from scripts.score_deep_answer import _judge_checklist, _load_checklist
from src.verifiers.url_coverage_verifier import URLCoverageVerifier


ROOT = Path(__file__).resolve().parents[1]


def test_checklist_loader_accepts_structured_v2_schema(tmp_path):
    path = tmp_path / "checklist.json"
    path.write_text(json.dumps({
        "task_id": "task-v2",
        "items": [
            {"id": "c1", "type": "SPEC", "params": {"kind": "min_words", "min": 10},
             "description": "Covers the seal trade-off"},
            {"id": "c2", "type": "SPEC", "params": {"kind": "section_present"},
             "description": "Provides a final pick"},
        ],
    }))
    assert _load_checklist(path, "task-v2") == [
        {"id": "c1", "type": "SPEC", "params": {"kind": "min_words", "min": 10},
         "description": "Covers the seal trade-off"},
        {"id": "c2", "type": "SPEC", "params": {"kind": "section_present"},
         "description": "Provides a final pick"},
    ]


def test_checklist_loader_keeps_legacy_task_map(tmp_path):
    path = tmp_path / "checklist.json"
    path.write_text(json.dumps({"legacy-task": ["One", "Two"]}))
    assert _load_checklist(path, "legacy-task") == ["One", "Two"]


def test_url_coverage_accepts_answer_key_v2_schema(tmp_path):
    url = "http://localhost:7770/headphones.html"
    answer_key = tmp_path / "answer-key.json"
    answer_key.write_text(json.dumps({
        "task_id": "task-v2",
        "vital_nuggets": [{
            "text": "Headphone evidence",
            "source_url": url,
            "predicate": "feature_claim",
        }],
        "relevant_set": [{
            "url": url,
            "category": "shopping_product",
            "weight": 1.0,
            "relevant": True,
        }],
    }))
    task = {
        "task_id": "task-v2",
        "task_version": 2,
        "url_coverage": {
            "golden_pool_path": str(answer_key),
            "curated_k": 12,
            "min_must_cite_recall": 1.0,
            "min_expected_pool_coverage": 1.0,
        },
    }
    result = URLCoverageVerifier().verify(
        task_config=task,
        answer=f"Supported claim [source]({url}).",
    )
    assert result.passed is True
    assert result.details["golden_schema"] == "answer_key_v2"
    assert result.details["must_cite_total"] == 1
    assert result.details["must_cite_hit"] == 1
    assert result.details["pool_total"] == 1
    assert result.details["pool_hit"] == 1


def test_task_0010_routes_v2_fields_to_headphones_answer_key():
    task = json.loads((
        ROOT / "data/tasks/deep_research/cross_site_deep/dr_cross_deep_0010.json"
    ).read_text())
    assert task["task_version"] == 2
    assert "mechanical" not in task["start_url"].lower()
    assert task["url_coverage"]["golden_pool_path"].endswith(
        "answer_keys/dr_cross_deep_0010.json"
    )
    assert task["synthesis_requirements"]["task_type"] == "use_case_fit"
    assert task["intent_type"] == "UseCaseFit"
    assert len(task["tri_source"]["vital_product_urls"]) == 10
    assert task["tri_source"]["contradictions_product_scope"] == "vital"


def test_task_0010_v2_gold_is_topical_and_has_no_cluster_wide_soundbar_requirements():
    answer_key = json.loads((
        ROOT / "data/golden/answer_keys/dr_cross_deep_0010.json"
    ).read_text())
    checklist = json.loads((
        ROOT / "data/golden/checklists/dr_cross_deep_0010.json"
    ).read_text())
    subjects = [str(n.get("subject") or "").lower()
                for n in answer_key["vital_nuggets"]]

    assert len(answer_key["vital_nuggets"]) == 13
    assert answer_key["gold_contradictions"] == []
    assert answer_key["metadata"]["contradiction_scorable"] is False
    assert answer_key["metadata"]["vital_product_override"] is True
    assert any("noise-cancelling headphones" in subject for subject in subjects)
    assert not any("soundbar" in subject or "cat ears" in subject for subject in subjects)
    assert not any(item["type"] == "CONTRADICTION" for item in checklist["items"])


def test_structured_checklist_is_deterministic_and_excludes_silent_facts():
    url = "http://localhost:7770/acme-flight-buds.html"
    checklist = [
        {
            "id": "cov0", "type": "COVERAGE", "decidable": True,
            "description": "Conveys the Acme sentiment",
            "params": {"subject": "Acme Flight Buds", "predicate": "buyer_sentiment",
                       "object": "80.0%/10rev", "source_url": url},
        },
        {
            "id": "fact0", "type": "FACT", "decidable": True,
            "description": "Acme sentiment is exact",
            "params": {"subject": "Acme Flight Buds", "predicate": "buyer_sentiment",
                       "object": "80.0%/10rev"},
        },
        {
            "id": "fact_silent", "type": "FACT", "decidable": True,
            "description": "Unmentioned product is exact",
            "params": {"subject": "Never Mentioned ZX9", "predicate": "buyer_sentiment",
                       "object": "55.0%/12rev"},
        },
        {"id": "reach", "type": "GROUNDING", "decidable": True,
         "description": "URLs resolve", "params": {"metric": "reachability"}},
        {"id": "quote", "type": "GROUNDING", "decidable": True,
         "description": "Quotes match", "params": {"metric": "proof_of_fetch"}},
        {"id": "words", "type": "SPEC", "decidable": True,
         "description": "Enough words", "params": {"kind": "min_words", "min": 8}},
        {"id": "pick", "type": "SPEC", "decidable": True,
         "description": "Has a pick", "params": {"kind": "section_present",
                                                    "keywords": ["final pick"]}},
    ]
    answer = (
        "## Final pick\n\n"
        f"Acme Flight Buds are rated 80% positive in the corpus. [source]({url})"
    )

    result = _judge_checklist(
        checklist, answer, "task-v2", reachability=1.0, quote_match=1.0,
    )

    assert result["scoring_mode"] == "structured_v2"
    assert result["pass_count"] == 6
    assert result["not_applicable_count"] == 1
    assert result["applicable_count"] == 6
    assert result["pass_rate"] == 1.0
    assert dict((row["id"], row["verdict"]) for row in result["item_results"])[
        "fact_silent"
    ] == "NOT_APPLICABLE"


def test_structured_coverage_cannot_pass_from_unrelated_prose_or_url_slug():
    url = "http://localhost:7770/acme-flight-buds-rated-80-percent.html"
    checklist = [{
        "id": "cov0", "type": "COVERAGE", "decidable": True,
        "description": "Conveys the Acme sentiment",
        "params": {"subject": "Acme Flight Buds", "predicate": "buyer_sentiment",
                   "object": "80.0%/10rev", "source_url": url},
    }]
    answer = f"Some earbuds are convenient. [source]({url})"

    result = _judge_checklist(
        checklist, answer, "task-v2", reachability=1.0, quote_match=1.0,
    )

    assert result["pass_count"] == 0
    assert result["fail_count"] == 1


def test_structured_fact_does_not_bind_a_different_model_from_same_brand():
    checklist = [{
        "id": "fact0", "type": "FACT", "decidable": True,
        "description": "Sony XM3 sentiment is exact",
        "params": {
            "subject": "SONY WH1000XM3 Noise Canceling Headphones",
            "predicate": "buyer_sentiment",
            "object": "87.0%/12rev",
        },
    }]
    answer = (
        "The Sony WH-1000XM5 case is rated 70 percent for packability, "
        "but that is a different model."
    )

    result = _judge_checklist(checklist, answer, "task-v2")

    assert result["not_applicable_count"] == 1
    assert result["fail_count"] == 0
