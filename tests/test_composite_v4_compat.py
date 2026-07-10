from src.scoring.leaderboard_composites import composite_v4, composite_v4_weights


def test_legacy_v4_imports_and_computes():
    score = {
        "url_reachability": {"score": 1.0},
        "url_coverage": {"score": 1.0},
        "quote_match": {"score": 1.0},
        "citation_alignment": {"score": 1.0},
        "analysis_depth": {"score": 1.0},
        "presentation": {"score": 1.0},
        "source_diversity": {"score": 1.0},
        "perspective_balance": {"score": 1.0},
        "factual_exactness": {"score": 1.0},
        "internal_consistency": {"score": 1.0},
        "markdown_spec": {
            "words_ok": True, "citations_ok": True, "paragraphs_ok": True,
        },
        "checklist": {"pass_rate": 1.0},
    }
    assert sum(composite_v4_weights().values()) == 1.0
    assert composite_v4(score) == 1.0
