from __future__ import annotations

from scripts.test_search_quality import _grade


def test_required_title_groups_are_alternatives():
    case = {
        "required_any_title_all": [
            ["large language model"],
            ["technological unemployment"],
        ],
    }
    rows = [{"title": "Large language model", "url": "http://localhost:8090/x"}]
    assert _grade(case, rows) == []


def test_forbidden_title_phrase_fails_the_gate():
    case = {"forbidden_title_contains": ["hair rollers"]}
    rows = [{"title": "Foam Sponge Hair Rollers", "url": "http://localhost:7770/x"}]
    assert _grade(case, rows)
