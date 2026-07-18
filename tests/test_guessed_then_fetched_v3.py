from __future__ import annotations

from src.eval.observation_ledger import ObservationLedger, sha256_bytes, sha256_text
from src.eval.slot_scorer import score_case


U = "http://localhost:9999/product/alpha"
PARENT = "http://localhost:9999/category/audio"
BODY = "The product states battery life is 30 hours."
REGISTRY_HASH = sha256_text("guessed fixture full registry")


def _event(i, kind, url, text, status=None, parent=None):
    return {
        "run_id": "discovery-run",
        "event_id": i,
        "timestamp": i,
        "event_type": kind,
        "request_url": url,
        "canonical_url": url,
        "parent_event_id": parent,
        "content_sha256": sha256_text(text),
        "content_text_or_blob_ref": text,
        "http_status": status,
        "observable": True,
    }


def _case():
    return {
        "task_id": "discovery-test",
        "task_version": 3,
        "corpus_registry_urls": [U, PARENT],
        "corpus_registry_hash": REGISTRY_HASH,
        "research_subgoals": [
            {
                "subgoal_id": "G1",
                "critical": True,
                "requires": ["E1"],
                "local_conclusion_slot_id": "E1",
            }
        ],
        "slots": [
            {"slot_id": "E1", "type": "evidence", "critical": True, "claim_id": "ev1"}
        ],
        "acceptable_conclusions": ["Alpha"],
    }


def _graph(*, snippet=False, spans=None):
    return {
        "nodes": {
            "ev1": {
                "evidence_id": "ev1",
                "subject": "Alpha",
                "predicate": "battery_life",
                "object": "30 hours",
                "source_url": U,
                "content_sha256": sha256_text(BODY),
                "search_snippet_support": snippet,
                "body_support": True,
                "support_spans": spans or [{"text": "battery life is 30 hours"}],
                "verifier": {
                    "matcher": "normalized_text",
                    "accepted_phrases": ["Alpha lasts 30 hours"],
                },
            }
        }
    }


def _report():
    return f"Alpha lasts 30 hours [source]({U})."


def _score(events, *, case=None, graph=None):
    trace = ObservationLedger.from_records(
        events, expected_run_id="discovery-run", capture_complete=True
    )
    result = score_case(case or _case(), _report(), trace, graph or _graph())
    return result, result["slot_results"][0]


def test_fetch_only_is_observed_but_guessed_then_fetched_fails_L():
    result, slot = _score([_event(1, "fetch_body", U, BODY, 200)])
    assert result["status"] == "scored"
    assert slot["O"] is True
    assert slot["L"] is False
    assert slot["discovery_class"] == "guessed_then_fetched"
    assert slot["reason_codes"]["L"] == "guessed_then_fetched"
    assert slot["verified"] is False


def test_search_must_precede_supporting_fetch():
    valid_result, valid = _score([
        _event(1, "search_result", U, "Alpha result"),
        _event(2, "fetch_body", U, BODY, 200, 1),
    ])
    assert valid["L"] is True
    assert valid["discovery_class"] == "searched"
    assert valid["verified"] is True
    # A verified leaf is a prerequisite, not a complete local research
    # question: this synthetic subgoal has no bridge/decision synthesis.
    assert valid_result["verified_research_completion"] == 0.0
    assert valid_result["research_subgoal_results"][0]["reason_codes"][
        "RESEARCH_SYNTHESIS"
    ] == "evidence_leaf_only_not_completion"

    _, too_late = _score([
        _event(1, "fetch_body", U, BODY, 200),
        _event(2, "search_result", U, "Alpha result"),
    ])
    assert too_late["O"] is True
    assert too_late["L"] is False
    assert too_late["discovery_class"] == "guessed_then_fetched"


def test_page_link_licenses_discovery_only_when_before_target_fetch():
    parent_body = f'<a href="{U}">Alpha product</a>'
    before = [
        _event(1, "search_result", PARENT, "audio category"),
        _event(2, "fetch_body", PARENT, parent_body, 200, 1),
        _event(3, "page_link", U, U, parent=2),
        _event(4, "fetch_body", U, BODY, 200, 3),
    ]
    _, linked = _score(before)
    assert linked["L"] is True
    assert linked["O"] is True
    assert linked["discovery_class"] == "linked"

    after = [
        _event(1, "fetch_body", U, BODY, 200),
        _event(2, "search_result", PARENT, "audio category"),
        _event(3, "fetch_body", PARENT, parent_body, 200, 2),
        _event(4, "page_link", U, U, parent=3),
    ]
    _, late = _score(after)
    assert late["O"] is True
    assert late["L"] is False


def test_link_from_a_guessed_parent_does_not_create_a_licensed_chain():
    parent_body = f'<a href="{U}">Alpha product</a>'
    events = [
        _event(1, "fetch_body", PARENT, parent_body, 200),
        _event(2, "page_link", U, U, parent=1),
        _event(3, "fetch_body", U, BODY, 200, 2),
    ]
    _, slot = _score(events)
    assert slot["O"] is True
    assert slot["L"] is False
    assert slot["discovery_class"] == "guessed_then_fetched"


def test_compiled_discovery_root_allows_direct_fetch():
    seeded_case = _case()
    seeded_case["discovery_root_urls"] = [U]
    _, slot = _score(
        [_event(1, "fetch_body", U, BODY, 200)], case=seeded_case
    )
    assert slot["L"] is True
    assert slot["discovery_class"] == "task_seed"
    assert slot["verified"] is True


def test_snippet_span_hash_is_scanned_in_snippet_coordinate_space():
    gold = b"battery life is 30 hours"
    # Gold offsets refer to a long frozen page, not to the snippet.  The scorer
    # proves inclusion by span length+digest rather than applying offset 120.
    span = {
        "start": 120,
        "end": 120 + len(gold),
        "sha256": sha256_bytes(gold),
        "support_type": "search_snippet",
    }
    graph = _graph(snippet=True, spans=[span])
    graph["nodes"]["ev1"].pop("content_sha256")
    positive = [_event(1, "search_result", U, "Result: battery life is 30 hours for Alpha")]
    _, supported = _score(positive, graph=graph)
    assert supported["O"] is True
    assert supported["L"] is True

    negative = [_event(1, "search_result", U, "Result: battery life is 31 hours for Alpha")]
    _, unsupported = _score(negative, graph=graph)
    assert unsupported["O"] is False


def test_wrong_page_citation_audits_actual_page_not_expected_gold_page():
    wrong = PARENT
    trace = ObservationLedger.from_records(
        [
            _event(1, "search_result", U, "Alpha result"),
            _event(2, "fetch_body", U, BODY, 200, 1),
        ],
        expected_run_id="discovery-run",
        capture_complete=True,
    )
    report = f"Alpha lasts 30 hours [wrong page]({wrong})."
    result = score_case(_case(), report, trace, _graph())
    slot = result["slot_results"][0]
    assert slot["B"] is False
    assert slot["citation_url"] == wrong
    assert slot["L"] is False
    assert slot["O"] is False
