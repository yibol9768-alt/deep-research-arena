from __future__ import annotations

import json

from src.scoring.audited_judge import AuditedJudge
from src.scoring.fact_evidence_resolver import (
    FrozenFactEvidenceResolver,
    SshPowerShellFrozenWorldGateway,
    claim_search_queries,
)
from src.scoring.four_axis_pipeline import (
    _claim_relevant_observation_excerpt,
    _evidence_response_schema,
    _json_char_batches,
    build_execution_audit,
    judge_citation_bindings,
    judge_facts,
    judge_rubric,
    reconstruct_native_observations,
    retrieve_fact_packet,
    value_blind_fact_query,
)
from src.scoring.report_claim_pipeline import segment_report
from src.scoring.task_manifest_compiler import compile_task_manifest
from src.scoring.url_registry import FrozenURLRegistry


def test_report_segmentation_preserves_exact_offsets_and_citations():
    report = '# H\n\nClaim 42. <cite id="a-0">source</cite>\n'
    segments = segment_report(report)
    assert [row["raw_text"] for row in segments] == [
        "# H",
        'Claim 42. <cite id="a-0">source</cite>',
    ]
    for row in segments:
        assert report[row["start"] : row["end"]] == row["raw_text"]
    assert segments[1]["citation_ids"] == ["a-0"]


def test_numbered_fact_line_is_not_suppressed_as_a_heading():
    segments = segment_report("1) Model X costs $49.\\n")
    assert segments[0]["material_signal"]
    assert not segments[0]["is_heading"]


def test_native_observation_projection_ignores_non_native_shared_ledger():
    trace = {
        "tool_calls": [
            {
                "call_id": "abc",
                "tool_name": "google_search",
                "called": True,
                "documents": [
                    {
                        "url": "http://localhost:7770/a.html",
                        "title": "A",
                        "snippet": "observed A",
                    }
                ],
            }
        ]
    }
    cmap = [
        {
            "evidence_id": "abc-0",
            "url": "http://localhost:7770/a.html",
        }
    ]
    projected = reconstruct_native_observations(trace, cmap)
    assert projected["citation_map_fully_attributable"] is True
    assert projected["documents"]["abc-0"]["observed_text"] == "observed A"
    assert projected["tool_call_count"] == 1
    audit = build_execution_audit(projected, cmap, '<cite id="abc-0">A</cite>')
    assert audit["snippet_observation_rate"] == 1.0
    assert audit["full_page_observation_rate"] == 0.0
    assert audit["shared_ledger_used"] is False


def test_explicit_search_snippet_tier_overrides_legacy_text_field():
    trace = {
        "tool_calls": [
            {
                "call_id": "search",
                "called": True,
                "documents": [
                    {
                        "url": "http://localhost:7770/a.html",
                        "text": "short search result",
                        "observation_tier": "search_snippet",
                    }
                ],
            }
        ]
    }
    projected = reconstruct_native_observations(
        trace,
        [{"evidence_id": "search-0", "url": "http://localhost:7770/a.html"}],
    )
    assert (
        projected["documents"]["search-0"]["observation_tier"]
        == "search_snippet"
    )


def test_frozen_url_registry_distinguishes_real_and_fabricated(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "hosts": {
                    "shopping": ["localhost:7770"],
                    "forums": ["localhost:9999"],
                    "wiki": ["localhost:8090"],
                },
                "products": ["real-product"],
                "submissions": {"7": "audio"},
                "wiki": ["IP_Code"],
            }
        ),
        encoding="utf-8",
    )
    registry = FrozenURLRegistry.load(path)
    assert registry.inspect(
        "http://localhost:7770/real-product.html"
    )["valid"]
    assert registry.inspect(
        "http://localhost:9999/f/audio/7/post"
    )["valid"]
    assert registry.inspect(
        "http://localhost:8090/content/wikipedia_en_all_nopic/IP_code"
    )["valid"]
    assert not registry.inspect(
        "http://localhost:7770/fabricated.html"
    )["valid"]


def test_fact_retrieval_query_is_value_blind():
    claim = {
        "normalized_claim": "Model X has a 5200 mAh battery",
        "subject": "Model X",
        "predicate": "battery capacity",
        "object": "5200 mAh",
        "qualifiers": {"model": "Model X", "listed_value": "5200 mAh"},
    }
    query = value_blind_fact_query(claim)
    assert "5200" not in query
    chunks = [
        {
            "span_id": "support",
            "url": "u1",
            "text": "Model X battery capacity is 5200 mAh.",
            "source_role": "retailer",
        },
        {
            "span_id": "refute",
            "url": "u2",
            "text": "Model X battery capacity is 6600 mAh.",
            "source_role": "manufacturer",
        },
    ]
    retrieved = retrieve_fact_packet(claim, chunks, top_k=2)
    assert {row["span_id"] for row in retrieved} == {"support", "refute"}


def test_json_char_batches_keep_complete_rows_under_budget():
    rows = [
        {"claim_id": "p1", "text": "a" * 30},
        {"claim_id": "p2", "text": "b" * 30},
        {"claim_id": "p3", "text": "c" * 30},
    ]

    batches = _json_char_batches(
        rows,
        char_budget=100,
        count_budget=4,
    )

    assert [row for batch in batches for row in batch] == rows
    assert [len(batch) for batch in batches] == [1, 1, 1]


def test_long_observation_projection_is_bounded_and_traceable():
    observed = (
        "irrelevant preface " * 800
        + "Soundcore Flare 2 battery capacity is 5200 mAh."
        + " irrelevant tail" * 800
    )

    projection = _claim_relevant_observation_excerpt(
        "Soundcore Flare 2 has a 5200 mAh battery.",
        "Battery comparison.",
        observed,
    )

    assert projection["excerpted"] is True
    assert "5200 mAh" in projection["text"]
    assert len(projection["text"]) < 6000
    assert projection["document_chars"] == len(observed)
    assert len(projection["windows"]) == 3


def test_evidence_response_schema_requires_one_bounded_verdict_per_binding():
    schema = _evidence_response_schema(2)
    verdicts = schema["properties"]["verdicts"]

    assert verdicts["minItems"] == 2
    assert verdicts["maxItems"] == 2
    assert verdicts["items"]["additionalProperties"] is False


def test_fact_query_preserves_product_model_digits():
    claim = {
        "normalized_claim": "Soundcore Flare2 has a 5200 mAh battery",
        "subject": "Soundcore Flare2",
        "predicate": "battery capacity",
        "object": "5200 mAh",
        "qualifiers": {"model": "Flare2", "listed_value": "5200 mAh"},
    }
    first_query = claim_search_queries(claim)[0]
    assert "Flare2" in first_query
    assert "5200" not in first_query


def test_ssh_fact_gateway_reuses_one_control_connection(monkeypatch):
    captured = {}

    class Completed:
        returncode = 0
        stdout = '{"ok":true}'
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr("subprocess.run", fake_run)
    gateway = SshPowerShellFrozenWorldGateway(
        ssh_host="frozen-host",
        control_path="/tmp/dra-test-%C",
    )
    assert gateway._run_json("test") == {"ok": True}
    command = captured["command"]
    assert "ControlMaster=auto" in command
    assert "ControlPersist=300" in command
    assert "ControlPath=/tmp/dra-test-%C" in command
    assert command.index("frozen-host") > command.index(
        "ControlPath=/tmp/dra-test-%C"
    )


def test_fact_resolver_checks_cited_page_then_global_sandbox(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "hosts": {"shopping": ["localhost:7770"]},
                "products": ["cited", "alternative"],
            }
        ),
        encoding="utf-8",
    )
    registry = FrozenURLRegistry.load(registry_path)

    class FakeGateway:
        def __init__(self):
            self.audit_rows = []
            self.fetched = []

        def search(self, query, *, max_results):
            return [
                {
                    "url": "http://localhost:7770/alternative.html",
                    "title": "Alternative",
                }
            ]

        def fetch(self, url):
            self.fetched.append(url)
            return {
                "ok": True,
                "text": (
                    "Official Model X product listing says its battery is 5200 mAh."
                    if url.endswith("/cited.html")
                    else "Another frozen page says the Model X battery is 6600 mAh."
                ),
                "content_sha256": url.rsplit("/", 1)[-1],
            }

        def product_lookup(self, url):
            return None

    gateway = FakeGateway()
    resolver = FrozenFactEvidenceResolver(
        seed_chunks=[],
        citation_map=[
            {
                "evidence_id": "c1",
                "url": "http://localhost:7770/cited.html",
            }
        ],
        observations={
            "documents": {
                "c1": {
                    "url": "http://localhost:7770/cited.html",
                    "observed_text": "snippet",
                    "observation_tier": "search_snippet",
                }
            }
        },
        registry=registry,
        gateway=gateway,
    )
    resolved = resolver.resolve(
        {
            "claim_id": "p1",
            "claim_kind": "external_atomic",
            "normalized_claim": "Model X battery is 5200 mAh.",
            "subject": "Model X",
            "predicate": "battery",
            "occurrences": [{"citation_ids": ["c1"]}],
        }
    )
    assert gateway.fetched[0].endswith("/cited.html")
    assert gateway.fetched[1].endswith("/alternative.html")
    modes = {row["retrieval_mode"] for row in resolved["chunks"]}
    assert "direct_cited_full_page" in modes
    assert "sandbox_search_full_page" in modes


def test_bounded_absence_requires_complete_scope_and_explicit_terms(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "hosts": {"shopping": ["localhost:7770"]},
                "products": ["a", "b"],
            }
        ),
        encoding="utf-8",
    )
    registry = FrozenURLRegistry.load(registry_path)

    class FakeGateway:
        audit_rows = []

        def search(self, query, *, max_results):
            return []

        def fetch(self, url):
            return {
                "ok": True,
                "text": "Bluetooth speaker with IPX7 waterproofing.",
                "content_sha256": url[-6:],
            }

        def product_lookup(self, url):
            return None

    urls = [
        "http://localhost:7770/a.html",
        "http://localhost:7770/b.html",
    ]
    resolver = FrozenFactEvidenceResolver(
        seed_chunks=[],
        citation_map=[
            {"evidence_id": f"c{i}", "url": url}
            for i, url in enumerate(urls, 1)
        ],
        observations={"documents": {}},
        registry=registry,
        gateway=FakeGateway(),
    )
    resolved = resolver.resolve(
        {
            "claim_id": "p1",
            "claim_kind": "bounded_absence",
            "normalized_claim": "Neither listing mentions Hi-Res.",
            "subject": "both listings",
            "predicate": "does not mention",
            "qualifiers": {"absence_terms": ["Hi-Res", "LDAC"]},
            "occurrences": [{"citation_ids": ["c1", "c2"]}],
        }
    )
    certificate = resolved["absence_certificate"]
    assert certificate["scope_urls"] == urls
    assert certificate["terms_absent"] is True


def test_full_page_observation_is_chunked_before_fact_retrieval(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "hosts": {"shopping": ["localhost:7770"]},
                "products": ["speaker"],
            }
        ),
        encoding="utf-8",
    )
    resolver = FrozenFactEvidenceResolver(
        seed_chunks=[],
        citation_map=[],
        observations={
            "documents": {
                "c1": {
                    "url": "http://localhost:7770/speaker.html",
                    "observed_text": "speaker specification " * 500,
                    "observation_tier": "full_page",
                    "delivery_sha256": "doc-hash",
                }
            }
        },
        registry=FrozenURLRegistry.load(registry_path),
    )

    chunks = resolver._observed_chunks("c1")

    assert len(chunks) > 1
    assert max(len(row["text"]) for row in chunks) <= 1400
    assert all(row["span_id"].startswith("observed:c1:") for row in chunks)
    assert all(row["complete_document_available"] for row in chunks)


def test_true_fact_requires_nonempty_support_span(tmp_path):
    def fake_call(system, user, model, max_tokens, temperature):
        payload = json.loads(user)
        claim_id = payload["claims"][0]["claim_id"]
        return (
            json.dumps(
                {
                    "verdicts": [
                        {
                            "claim_id": claim_id,
                            "verdict": "true",
                            "support_span_ids": [],
                            "contradiction_span_ids": [],
                        }
                    ]
                }
            ),
            None,
        )

    judge = AuditedJudge(tmp_path / "calls", judge_call=fake_call)
    claims = [
        {
            "claim_id": "p_0001",
            "claim_kind": "external_atomic",
            "normalized_claim": "Model X has a battery.",
            "subject": "Model X",
            "predicate": "battery",
            "materiality": 1,
            "report_span": {"raw_text": "Model X has a battery."},
        }
    ]
    chunks = [
        {
            "span_id": "world:1:0",
            "url": "u",
            "source_role": "manufacturer",
            "text": "Model X battery information.",
        }
    ]
    verdicts = judge_facts(claims, chunks, judge, tmp_path / "out")
    assert verdicts[0]["verdict"] == "instrument_ambiguous"


def test_search_snippet_cannot_prove_bounded_absence(tmp_path):
    def fake_call(system, user, model, max_tokens, temperature):
        binding_id = json.loads(user)["bindings"][0]["binding_id"]
        return (
            json.dumps(
                {
                    "verdicts": [
                        {
                            "binding_id": binding_id,
                            "bound": True,
                            "support_verdict": "support",
                            "role_ok": True,
                        }
                    ]
                }
            ),
            None,
        )

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "hosts": {"shopping": ["localhost:7770"]},
                "products": ["a"],
            }
        ),
        encoding="utf-8",
    )
    judge = AuditedJudge(tmp_path / "calls", judge_call=fake_call)
    bindings, required = judge_citation_bindings(
        [
            {
                "claim_id": "p1",
                "claim_kind": "bounded_absence",
                "normalized_claim": "The listing does not mention LDAC.",
                "evidence_policy": "citation_required",
                "report_span": {"raw_text": "No LDAC. <cite id=\"c1\">x</cite>"},
                "occurrences": [
                    {
                        "report_span": {
                            "raw_text": "No LDAC. <cite id=\"c1\">x</cite>"
                        },
                        "citation_ids": ["c1"],
                    }
                ],
            }
        ],
        [{"evidence_id": "c1", "url": "http://localhost:7770/a.html"}],
        {
            "documents": {
                "c1": {
                    "url": "http://localhost:7770/a.html",
                    "observed_text": "Speaker listing snippet",
                    "observation_tier": "search_snippet",
                    "observed": True,
                }
            }
        },
        FrozenURLRegistry.load(registry_path),
        judge,
        tmp_path / "out",
    )
    assert bindings[0]["supports"] is True
    assert bindings[0]["passed"] is False
    assert "incomplete_scope_observation" in bindings[0]["failure_reasons"]
    assert required[0]["grounded"] is False


def test_positive_rubric_requires_exact_report_quote(tmp_path):
    def fake_call(system, user, model, max_tokens, temperature):
        return (
            json.dumps(
                {
                    "verdicts": [
                        {
                            "rubric_id": "rubric:r1",
                            "verdict": "fulfilled",
                            "exact_quotes": ["text not present"],
                        }
                    ]
                }
            ),
            None,
        )

    judge = AuditedJudge(tmp_path / "calls", judge_call=fake_call)
    rows = judge_rubric(
        "Actual report text.",
        [
            {
                "rubric_id": "rubric:r1",
                "origin": "explicit",
                "requirement": "Give a recommendation.",
                "weight": 1,
            }
        ],
        judge,
    )
    assert rows[0]["verdict"] == "ambiguous"
    assert rows[0]["exact_quotes"] == []


def test_registry_without_hash_attestation_is_not_formally_attested(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "hosts": {"shopping": ["localhost:7770"]},
                "products": ["real-product"],
            }
        ),
        encoding="utf-8",
    )
    registry = FrozenURLRegistry.load(path)
    inspected = registry.inspect("http://localhost:7770/real-product.html")
    assert inspected["valid"]
    assert not inspected["snapshot_attested"]
    assert not registry.formal_snapshot_attestation_available


def test_rubric_and_completeness_requirements_are_disjoint(tmp_path):
    captured_payloads = []

    def fake_call(system, user, model, max_tokens, temperature):
        payload = json.loads(user)
        captured_payloads.append(payload)
        if "Audit proposed query-compliance rubrics" in system:
            return (
                json.dumps(
                    {
                        "items": [
                            {
                                "rubric_key": "Q1",
                                "verdict": "accept",
                                "reason_code": "entailed",
                            }
                        ]
                    }
                ),
                None,
            )
        if "query-compliance rubrics" in system:
            return (
                json.dumps(
                    {
                        "items": [
                            {
                                "rubric_key": "Q1",
                                "query_span": "recommend",
                                "requirement": "Give a recommendation.",
                                "requirement_type": "recommendation",
                            }
                        ]
                    }
                ),
                None,
            )
        if "candidate_requirements" in payload:
            return (
                json.dumps(
                    {
                        "items": [
                            {
                                "check_id": "K_USER",
                                "include": False,
                                "axis": "drop",
                                "needs_split": False,
                                "requirement": "Give a recommendation.",
                                "unit_type": "decision",
                            },
                            {
                                "check_id": "K_CONTENT",
                                "include": True,
                                "axis": "completeness",
                                "needs_split": False,
                                "requirement": "Compare battery evidence.",
                                "unit_type": "comparison",
                                "answer_leak": False,
                                "route_bound": False,
                            },
                        ]
                    }
                ),
                None,
            )
        return json.dumps({"items": []}), None

    judge = AuditedJudge(tmp_path / "calls", judge_call=fake_call)
    suite = {
        "facets": [
            {
                "facet_id": "F1",
                "units": [
                    {
                        "unit_id": "U1",
                        "checks": [
                            {
                                "check_id": "K_USER",
                                "content_contract": "Give a recommendation.",
                            },
                            {
                                "check_id": "K_CONTENT",
                                "content_contract": "Compare battery evidence.",
                            },
                        ],
                    }
                ],
            }
        ]
    }
    compiled = compile_task_manifest(
        {"task_id": "t", "prompt": "Compare and recommend."},
        {"task_id": "t", "assertions": []},
        suite,
        judge,
        tmp_path / "tec",
    )
    rubric_ids = {row["rubric_id"] for row in compiled["rubric_items"]}
    research_ids = {
        row["legacy_check_id"] for row in compiled["research_units"]
    }
    assert rubric_ids == {"rubric:query:001"}
    assert compiled["rubric_items"][0]["query_span"] == "recommend"
    assert research_ids == {"K_CONTENT"}
    assert compiled["manifest"]["axis_disjointness_certificate"]["passed"]
    proposal_payload = next(
        payload
        for payload in captured_payloads
        if set(payload) == {"query"}
    )
    assert "candidate_requirements" not in proposal_payload
