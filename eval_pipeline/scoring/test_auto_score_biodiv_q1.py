from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from auto_score_biodiv_q1 import (
    ADJUDICATION_SCHEMA,
    CLAIM_BATCH_MAX_CHARS,
    CLAIM_BATCH_SCHEMA,
    CLAIM_SCHEMA,
    AdamsOpenAIJudge,
    BudgetedJudge,
    JudgeBudgetError,
    JudgeError,
    JudgeIdentityError,
    JudgeSchemaError,
    JudgeTruncationError,
    PackageAssets,
    _claim_batches,
    adjudicate_batched,
    build_binding_candidates,
    compile_packet,
    canonicalize_citation_urls,
    execute,
    extract_claims_batched,
    extract_citations,
    normalize_claims,
    paragraph_bounds,
    parse_json_object,
    partition_report,
    repair_invalid_claim_quotes,
    read_json,
    reconstruct_observations,
    run_semantic_pipeline,
    sha256_file,
    judge_usage_summary,
    validate_schema,
)


HERE = Path(__file__).resolve().parent
PACKAGE = HERE / "fixtures/q1_package"
URL = "http://localhost:8090/wikipedia_en_all_nopic_2026-06/Environmental_mitigation"
CLAIM_A = (
    "Humans drive global biodiversity loss through changes in land use, "
    "exploitation of organisms, climate change, pollution, and invasive species"
)
CLAIM_B = "Environmental mitigation generally includes avoid, reduce, restore, and offset"
REPORT = f"{CLAIM_A} [source]({URL}).\n\n{CLAIM_B} [source]({URL}).\n"
REAL_ANCHORED_REPORT = Path(
    os.environ.get(
        "Q1_REAL_ANCHORED_REPORT",
        str(
            HERE.parent
            / "biodiversity_q1_17x6_experimental_matrix"
            / "inputs/BQ1-CROSS5-PILOT-20260825-D/cells"
            / "biodiversity-q1--deerflow--gpt-5-6-sol/attempt-1/report.md"
        ),
    )
)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canary_files(
    root: Path, *, include_search: bool = True, run_id: str = "AB-OFFLINE-CANARY"
) -> tuple[Path, Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    report = root / "report.md"
    report.write_text(REPORT, encoding="utf-8")
    mapping = json.loads((PACKAGE / "evidence_mapping.json").read_text())
    quotes = [
        row["quote"]
        for row in mapping["evidence_rows"]
        if row["evidence_id"] in {"IU002:E001", "IU012:E001"}
    ]
    body = root / "environmental-mitigation-window.json"
    write_json(
        body,
        {
            "canonical_url": URL,
            "page_content_sha256": "84cff0cdb9e732fe2b42948ee328248c6dab1b1e3c0e25cc2171b89e25227e9e",
            "content": "\n\n".join(quotes),
            "truncated": True,
            "evidence_level": "fetched_content",
        },
    )
    rows = []
    if include_search:
        rows.append({"kind": "search", "urls_returned": [URL]})
    rows.append(
        {
            "kind": "fetch",
            "url": URL,
            "http_status": 200,
            "body_path": str(body),
            "body_sha256": sha256_file(body),
        }
    )
    ledger = root / "ledger.jsonl"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    run_manifest = root / "run-manifest.json"
    write_json(
        run_manifest,
        {
            "run_id": run_id,
            "completed": True,
            "failure": None,
            "execution": {"outcome": "pass"},
            "report_sha256": sha256_file(report),
        },
    )
    return report, ledger, run_manifest


def adjudication_rows() -> dict:
    units = json.loads((PACKAGE / "required_units.json").read_text())["required_units"]
    coverage = []
    for row in units:
        unit_id = row["information_unit_id"]
        if unit_id == "IU002":
            coverage.append(
                {
                    "unit_id": unit_id,
                    "content_covered": True,
                    "matched_claim_ids": ["C001"],
                    "exact_report_quotes": [CLAIM_A],
                    "reason_code": "complete_match",
                    "explanation": "The report states all five drivers.",
                }
            )
        elif unit_id == "IU012":
            coverage.append(
                {
                    "unit_id": unit_id,
                    "content_covered": True,
                    "matched_claim_ids": ["C002"],
                    "exact_report_quotes": [CLAIM_B],
                    "reason_code": "complete_match",
                    "explanation": "The report states all four steps.",
                }
            )
        else:
            coverage.append(
                {
                    "unit_id": unit_id,
                    "content_covered": False,
                    "matched_claim_ids": [],
                    "exact_report_quotes": [],
                    "reason_code": "not_present",
                    "explanation": "The report does not cover this unit.",
                }
            )
    return {
        "claim_judgments": [
            {
                "claim_id": "C001",
                "verdict": "true",
                "support_evidence_ids": ["IU002:E001"],
                "contradiction_evidence_ids": [],
                "reason_code": "direct_support",
                "explanation": "The frozen quote states the five drivers.",
            },
            {
                "claim_id": "C002",
                "verdict": "true",
                "support_evidence_ids": ["IU012:E001"],
                "contradiction_evidence_ids": [],
                "reason_code": "direct_support",
                "explanation": "The frozen quote states the mitigation steps.",
            },
        ],
        "binding_judgments": [
            {
                "binding_id": "B0001",
                "bound": True,
                "support_verdict": "support",
                "role_ok": True,
                "reason_code": "local_support",
                "explanation": "The adjacent citation supports the claim.",
            },
            {
                "binding_id": "B0002",
                "bound": True,
                "support_verdict": "support",
                "role_ok": True,
                "reason_code": "local_support",
                "explanation": "The adjacent citation supports the claim.",
            },
        ],
        "completeness_judgments": coverage,
    }


class FakeJudge:
    model = "fixed-test-judge"

    def __init__(self, *, bad_quote: bool = False, missing_unit: bool = False):
        self.bad_quote = bad_quote
        self.missing_unit = missing_unit
        self.calls = []

    def call_json(self, stage, _system, payload, schema):
        self.calls.append((stage, payload))
        if stage.startswith("claim-extractor"):
            report = payload.get("report", REPORT)
            claims = []
            if CLAIM_A in report:
                claims.append(
                    {
                        "exact_report_quote": "not in report" if self.bad_quote else f"  {CLAIM_A}  ",
                        "normalized_claim": CLAIM_A,
                        "claim_kind": "external_atomic",
                        "evidence_policy": "citation_required",
                        "citation_refs": ["CITE001"],
                    }
                )
            if CLAIM_B in report:
                claims.append(
                    {
                        "exact_report_quote": CLAIM_B,
                        "normalized_claim": CLAIM_B,
                        "claim_kind": "external_atomic",
                        "evidence_policy": "citation_required",
                        "citation_refs": ["CITE002"],
                    }
                )
            value = {"claims": claims}
        elif stage.startswith("claim-quote-repair"):
            value = {"repairs": [{"claim_index": 0, "exact_report_quote": CLAIM_A}]}
        elif stage.startswith("claim-binding-adjudicator"):
            full = adjudication_rows()
            claim_ids = {row["claim_id"] for row in payload["claims_to_judge"]}
            binding_ids = {
                row["binding_id"] for row in payload["citation_candidates_to_judge"]
            }
            value = {
                "claim_judgments": [
                    row for row in full["claim_judgments"] if row["claim_id"] in claim_ids
                ],
                "binding_judgments": [
                    row for row in full["binding_judgments"] if row["binding_id"] in binding_ids
                ],
            }
        elif stage.startswith("completeness-adjudicator"):
            full = adjudication_rows()
            unit_ids = {
                row["unit_id"] for row in payload["required_information_units_to_judge"]
            }
            rows = [
                row for row in full["completeness_judgments"] if row["unit_id"] in unit_ids
            ]
            if self.missing_unit and rows:
                rows.pop()
            value = {"completeness_judgments": rows}
        else:
            value = adjudication_rows()
            if self.missing_unit:
                value["completeness_judgments"].pop()
        validate_schema(value, schema, stage)
        return value


SCORER = '''
def binding_gate(row):
    passed = all(bool(row.get(k)) for k in ("valid", "observed", "legally_discovered", "bound", "supports", "role_ok", "complete_scope_observed")) and row.get("observation_tier") in {"full_page", "fetched_content"}
    return {"passed": passed}
def score_gate_truth(packet):
    if str((packet.get("failure_status") or {}).get("status_code", "")).startswith("withheld"):
        return {"gcp":{"score":None}, "grr":{"score":None}, "formal_eligible":False, "formal_score":None}
    grounded = {r["claim_id"] for r in packet["citation_bindings"] if binding_gate(r)["passed"]}
    eligible = [r for r in packet["material_claims"] if r.get("eligible", True)]
    gc = [r for r in eligible if r.get("verdict") == "true" and r["claim_id"] in grounded]
    units = [r for r in packet["completeness_units"] if r.get("necessary") and r.get("applicable")]
    gu = [r for r in units if r.get("gate_truth_grounded_covered")]
    return {"gcp":{"score":len(gc)/len(eligible) if eligible else None}, "grr":{"score":len(gu)/len(units) if units else None}, "formal_eligible":False, "formal_score":None}
'''


def local_aggregator_fixture(root: Path) -> tuple[Path, Path, Path]:
    package = root / "package"
    shutil.copytree(PACKAGE, package)
    scorer_root = root / "scorer"
    implementation = scorer_root / "src/scoring/gate_truth_score.py"
    implementation.parent.mkdir(parents=True)
    implementation.write_text(SCORER, encoding="utf-8")
    scoring_path = package / "eco_scoring_manifest.json"
    scoring = json.loads(scoring_path.read_text())
    scoring["scorer_runtime"]["components"]["implementation"] = {
        "path": str(implementation),
        "sha256": sha256_file(implementation),
        "bytes": implementation.stat().st_size,
    }
    write_json(scoring_path, scoring)
    manifest_path = package / "evaluation_package_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"]["eco_scoring_manifest"] = {
        "path": str(scoring_path),
        "sha256": sha256_file(scoring_path),
        "bytes": scoring_path.stat().st_size,
    }
    write_json(manifest_path, manifest)
    local_copy = HERE / "score_gate_truth_packet.py"
    aggregator = (
        local_copy
        if local_copy.is_file()
        else HERE.parent / "biodiv_q1_scoring_audit/score_gate_truth_packet.py"
    )
    return package, scorer_root, aggregator


class AutomaticScorerTests(unittest.TestCase):
    def test_claim_schema_capacity_covers_long_research_reports(self):
        self.assertEqual(512, read_json(CLAIM_SCHEMA)["properties"]["claims"]["maxItems"])
        self.assertEqual(64, read_json(CLAIM_BATCH_SCHEMA)["properties"]["claims"]["maxItems"])

    def test_paragraph_partition_is_gapless_and_citations_have_one_owner(self):
        report = (
            f"first [source]({URL}).\n\n"
            f"second [source]({URL}).\n\n"
            "third paragraph"
        )
        citations = extract_citations(report)
        batches = partition_report(report, citations, max_chars=250)
        self.assertEqual(report, "".join(batch.text for batch in batches))
        self.assertEqual(list(range(1, len(batches) + 1)), [batch.batch_index for batch in batches])
        self.assertEqual(
            {row["citation_ref"] for row in citations},
            {row["citation_ref"] for batch in batches for row in batch.citations},
        )
        self.assertEqual(len(citations), sum(len(batch.citations) for batch in batches))

    def test_inline_reference_anchor_resolves_at_body_occurrence(self):
        report = (
            f"{CLAIM_A} [[12]](#ref-12).\n\n"
            "## References\n\n"
            '<a id="ref-12"></a>\n\n'
            f"- [[12]](#citation-target-12) **[Source]({URL})**\n"
        )
        citations = extract_citations(report)
        inline = [
            row
            for row in citations
            if row["occurrence_kind"] == "inline_reference_anchor"
        ]
        self.assertEqual(1, len(inline))
        self.assertEqual("resolved", inline[0]["resolution_status"])
        self.assertEqual(URL, inline[0]["url"])
        self.assertEqual(report.index("[[12]](#ref-12)"), inline[0]["start"])

        response = {
            "claims": [
                {
                    "exact_report_quote": CLAIM_A,
                    "normalized_claim": CLAIM_A,
                    "claim_kind": "external_atomic",
                    "evidence_policy": "citation_required",
                    "citation_refs": [inline[0]["citation_ref"]],
                }
            ]
        }
        claims = normalize_claims(response, report, citations)
        candidates = build_binding_candidates(
            claims,
            citations,
            {URL: {"observed": True, "legally_discovered": True}},
            PackageAssets.load(PACKAGE),
        )
        self.assertTrue(candidates[0]["same_paragraph"])
        self.assertTrue(candidates[0]["valid"])

    def test_unresolved_or_conflicting_inline_reference_is_invalid_not_withheld(self):
        missing_report = f"{CLAIM_A} [[7]](#ref-7)."
        missing = extract_citations(missing_report)
        self.assertEqual(1, len(missing))
        self.assertEqual("missing_definition", missing[0]["resolution_status"])
        self.assertEqual("", missing[0]["url"])

        conflicting_report = (
            f"{CLAIM_A} [[7]](#ref-7).\n\n"
            '<a id="ref-7"></a>\n\n'
            f"- [First]({URL})\n\n"
            '<a id="ref-7"></a>\n\n'
            "- [Second](https://example.invalid/conflict)\n"
        )
        conflicting = extract_citations(conflicting_report)
        inline = [
            row
            for row in conflicting
            if row["occurrence_kind"] == "inline_reference_anchor"
        ][0]
        self.assertEqual("conflicting_definition", inline["resolution_status"])
        self.assertEqual("", inline["url"])
        response = {
            "claims": [
                {
                    "exact_report_quote": CLAIM_A,
                    "normalized_claim": CLAIM_A,
                    "claim_kind": "external_atomic",
                    "evidence_policy": "citation_required",
                    "citation_refs": [inline["citation_ref"]],
                }
            ]
        }
        claims = normalize_claims(response, conflicting_report, conflicting)
        candidates = build_binding_candidates(
            claims, conflicting, {}, PackageAssets.load(PACKAGE)
        )
        self.assertTrue(candidates[0]["same_paragraph"])
        self.assertFalse(candidates[0]["valid"])

    def test_real_23k_anchored_report_partitions_without_gaps_or_duplicate_spans(self):
        if not REAL_ANCHORED_REPORT.is_file():
            self.skipTest(f"real anchored report fixture is not present: {REAL_ANCHORED_REPORT}")
        report = REAL_ANCHORED_REPORT.read_text(encoding="utf-8")
        self.assertGreater(len(report), 20_000)
        citations = extract_citations(report)
        inline = [
            row
            for row in citations
            if row["occurrence_kind"] == "inline_reference_anchor"
        ]
        self.assertGreater(len(inline), 1)
        self.assertTrue(all(row["resolution_status"] == "resolved" for row in inline))
        batches = partition_report(report, citations, max_chars=CLAIM_BATCH_MAX_CHARS)
        self.assertEqual(report, "".join(batch.text for batch in batches))
        self.assertEqual(0, batches[0].start)
        self.assertEqual(len(report), batches[-1].end)
        self.assertTrue(
            all(left.end == right.start for left, right in zip(batches, batches[1:]))
        )
        self.assertEqual(
            len(citations),
            sum(len(batch.citations) for batch in batches),
        )

        ref12 = next(row for row in inline if row["reference_id"] == "ref-12")
        p_start, _ = paragraph_bounds(report, ref12["start"])
        quote = report[p_start:ref12["start"]].strip()
        self.assertTrue(quote)
        response = {
            "claims": [
                {
                    "exact_report_quote": quote,
                    "normalized_claim": quote,
                    "claim_kind": "external_atomic",
                    "evidence_policy": "citation_required",
                    "citation_refs": [ref12["citation_ref"]],
                }
            ]
        }
        claims = normalize_claims(response, report, citations)
        candidates = build_binding_candidates(
            claims, citations, {}, PackageAssets.load(PACKAGE)
        )
        self.assertTrue(candidates[0]["same_paragraph"])

    def test_oversized_single_paragraph_fails_closed_instead_of_being_cut(self):
        with self.assertRaisesRegex(JudgeSchemaError, "without a safe boundary"):
            partition_report("x" * 101, [], max_chars=100)

    def test_multiline_long_paragraph_splits_only_at_safe_boundaries(self):
        report = ("a" * 70) + "\n" + ("b" * 70)
        batches = partition_report(report, [], max_chars=80)
        self.assertEqual(report, "".join(batch.text for batch in batches))
        self.assertEqual([71, 70], [len(batch.text) for batch in batches])

    def test_claim_extraction_batches_preserve_global_order_and_local_citations(self):
        report = (
            f"{CLAIM_A} [source]({URL}).\n\n"
            + ("context " * 50)
            + "\n\n"
            + f"{CLAIM_B} [source]({URL}).\n"
        )
        citations = canonicalize_citation_urls(
            extract_citations(report), PackageAssets.load(PACKAGE)
        )
        judge = FakeJudge()
        response, diagnostics = extract_claims_batched(
            PackageAssets.load(PACKAGE), report, citations, judge, max_chars=450
        )
        self.assertGreaterEqual(diagnostics["batch_count"], 2)
        self.assertEqual([CLAIM_A, CLAIM_B], [row["normalized_claim"] for row in response["claims"]])
        extraction_calls = [
            (stage, payload) for stage, payload in judge.calls
            if stage.startswith("claim-extractor-batch-")
        ]
        self.assertEqual(diagnostics["batch_count"], len(extraction_calls))
        for _, payload in extraction_calls:
            allowed = {row["citation_ref"] for row in payload["citation_catalog"]}
            for row in response["claims"]:
                if row["exact_report_quote"] in payload["report"]:
                    self.assertTrue(set(row["citation_refs"]).issubset(allowed))

    def test_claim_citation_cannot_escape_its_report_batch(self):
        class EscapingJudge(FakeJudge):
            def call_json(self, stage, system, payload, schema):
                value = super().call_json(stage, system, payload, schema)
                if stage.startswith("claim-extractor") and value["claims"]:
                    value["claims"][0]["citation_refs"] = ["CITE999"]
                    validate_schema(value, schema, stage)
                return value

        citations = canonicalize_citation_urls(
            extract_citations(REPORT), PackageAssets.load(PACKAGE)
        )
        with self.assertRaisesRegex(JudgeSchemaError, "citation escapes report batch"):
            extract_claims_batched(
                PackageAssets.load(PACKAGE), REPORT, citations, EscapingJudge()
            )

    def test_claim_adjudication_batches_obey_claim_and_binding_limits(self):
        claims = [{"claim_id": f"C{index:03d}"} for index in range(1, 34)]
        candidates = [
            {"claim_id": claim["claim_id"], "binding_id": f"B{offset:04d}"}
            for offset, claim in enumerate(
                [claim for claim in claims for _ in range(2)], 1
            )
        ]
        batches = _claim_batches(claims, candidates, 16, 48)
        self.assertEqual([16, 16, 1], [len(batch) for batch in batches])
        for batch in batches:
            ids = {row["claim_id"] for row in batch}
            self.assertLessEqual(
                sum(row["claim_id"] in ids for row in candidates), 48
            )

    def test_truncated_claim_batch_stops_before_any_adjudication(self):
        class TruncatingJudge(FakeJudge):
            def call_json(self, stage, system, payload, schema):
                if stage == "claim-extractor-batch-002":
                    self.calls.append((stage, payload))
                    raise JudgeTruncationError("simulated batch truncation")
                return super().call_json(stage, system, payload, schema)

        report = (
            f"{CLAIM_A} [source]({URL}).\n\n"
            + ("context. " * 100)
            + "\n\n"
            + ("context. " * 100)
            + "\n\n"
            + f"{CLAIM_B} [source]({URL}).\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, ledger, _ = canary_files(root)
            judge = TruncatingJudge()
            with self.assertRaises(JudgeTruncationError):
                run_semantic_pipeline(PackageAssets.load(PACKAGE), report, ledger, judge)
            self.assertFalse(
                any("adjudicator" in stage for stage, _ in judge.calls)
            )

    def test_truncation_is_withheld_and_never_converted_to_zero_score(self):
        class ImmediateTruncatingJudge:
            model = "fixed-test-judge"

            def call_json(self, stage, system, payload, schema):
                raise JudgeTruncationError(f"truncated at {stage}")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report, ledger, run_manifest = canary_files(root / "input")
            package, scorer_root, aggregator = local_aggregator_fixture(root / "agg")
            result = execute(
                package_dir=package,
                report_path=report,
                ledger_path=ledger,
                run_manifest_path=run_manifest,
                output_dir=root / "score",
                judge=ImmediateTruncatingJudge(),
                run_id="AB-OFFLINE-CANARY",
                judge_config={"request_model": "fixed-test-judge", "max_calls": 64},
                aggregator_path=aggregator,
                scorer_root=scorer_root,
            )
            self.assertEqual("WITHHELD", result["receipt"]["status"])
            self.assertEqual(
                "withheld_judge_truncated",
                result["packet"]["failure_status"]["status_code"],
            )
            self.assertIsNone(result["score"]["metrics"]["gcp"]["score"])
            self.assertIsNone(result["score"]["metrics"]["grr"]["score"])

    def test_ab_end_to_end_produces_two_of_34_grr(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report, ledger, run_manifest = canary_files(root)
            package, scorer_root, aggregator = local_aggregator_fixture(root / "agg")
            result = execute(
                package_dir=package,
                report_path=report,
                ledger_path=ledger,
                run_manifest_path=run_manifest,
                output_dir=root / "run",
                judge=FakeJudge(),
                run_id="AB-OFFLINE-CANARY",
                judge_config={"request_model": "fixed-test-judge", "max_calls": 64},
                aggregator_path=aggregator,
                scorer_root=scorer_root,
            )
            self.assertEqual(result["receipt"]["status"], "SCORED")
            self.assertEqual(result["score"]["metrics"]["citation_binding"]["score"], 1.0)
            self.assertEqual(result["score"]["metrics"]["gcp"]["score"], 1.0)
            self.assertAlmostEqual(result["score"]["metrics"]["grr"]["score"], 2 / 34)
            self.assertEqual(len(result["packet"]["completeness_units"]), 34)

    def test_adjudication_is_batched_and_preserves_full_34_unit_closure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, ledger, _ = canary_files(root)
            judge = FakeJudge()
            packet, diagnostics = run_semantic_pipeline(
                PackageAssets.load(PACKAGE), REPORT, ledger, judge
            )
            stages = [stage for stage, _ in judge.calls]
            self.assertEqual(1, sum(stage.startswith("claim-binding-adjudicator") for stage in stages))
            self.assertEqual(17, sum(stage.startswith("completeness-adjudicator") for stage in stages))
            self.assertEqual(34, len(packet["completeness_units"]))
            self.assertEqual(
                17,
                len(diagnostics["adjudication_batching"]["completeness_batches"]),
            )

    def test_exact_frozen_quote_scores_without_judge_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report, ledger, run_manifest = canary_files(root / "input", run_id="EXACT-ZERO-JUDGE")
            mapping = json.loads((PACKAGE / "evidence_mapping.json").read_text())
            quotes = [
                row["quote"]
                for row in mapping["evidence_rows"]
                if row["evidence_id"] in {"IU002:E001", "IU012:E001"}
            ]
            report.write_text(
                "".join(f"{quote} [source]({URL}).\n\n" for quote in quotes),
                encoding="utf-8",
            )
            manifest = json.loads(run_manifest.read_text())
            manifest["report_sha256"] = sha256_file(report)
            write_json(run_manifest, manifest)
            package, scorer_root, aggregator = local_aggregator_fixture(root / "agg")
            judge = FakeJudge()
            result = execute(
                package_dir=package,
                report_path=report,
                ledger_path=ledger,
                run_manifest_path=run_manifest,
                output_dir=root / "score",
                judge=judge,
                run_id="EXACT-ZERO-JUDGE",
                judge_config={"request_model": "fixed-test-judge", "max_calls": 0},
                aggregator_path=aggregator,
                scorer_root=scorer_root,
            )
            self.assertEqual("SCORED", result["receipt"]["status"])
            self.assertEqual([], judge.calls)
            self.assertEqual(1.0, result["score"]["metrics"]["citation_binding"]["score"])
            self.assertEqual(1.0, result["score"]["metrics"]["gcp"]["score"])
            self.assertAlmostEqual(2 / 34, result["score"]["metrics"]["grr"]["score"])

    def test_budgeted_judge_reserves_calls_before_spending(self):
        judge = BudgetedJudge(FakeJudge(), {"request_model": "fixed-test-judge", "max_calls": 1})
        judge.call_json("claim-extractor", "", {}, read_json(CLAIM_SCHEMA))
        with self.assertRaisesRegex(JudgeBudgetError, "judge call budget exceeded"):
            judge.ensure_available(1)
        self.assertEqual(1, judge.calls_made)

    def test_no_registered_citation_short_circuits_before_judge(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report, ledger, run_manifest = canary_files(root / "input")
            outside = (
                "A snapshot-looking claim [source]("
                "http://localhost:8090/content/wikipedia_en_all_nopic_2026-06/Biodiversity_loss).\n"
            )
            report.write_text(outside, encoding="utf-8")
            manifest = json.loads(run_manifest.read_text())
            manifest["report_sha256"] = sha256_file(report)
            write_json(run_manifest, manifest)
            judge = FakeJudge()
            result = execute(
                package_dir=PACKAGE,
                report_path=report,
                ledger_path=ledger,
                run_manifest_path=run_manifest,
                output_dir=root / "score",
                judge=judge,
                run_id="AB-OFFLINE-CANARY",
                judge_config={"request_model": "fixed-test-judge", "max_calls": 0},
            )
            self.assertEqual("SCORED", result["receipt"]["status"])
            self.assertEqual([], judge.calls)
            self.assertTrue(
                result["packet"]["failure_status"]["status_code"].startswith("scored_zero")
            )

    def test_claim_quote_is_trimmed_then_exactly_checked(self):
        claims = normalize_claims(
            FakeJudge().call_json("claim-extractor", "", {}, read_json(CLAIM_SCHEMA)),
            REPORT,
            extract_citations(REPORT),
        )
        self.assertEqual(claims[0]["exact_report_quote"], CLAIM_A)

    def test_parse_json_object_strips_leading_think_block(self):
        parsed = parse_json_object(
            "<think>reasoning</think>\n{\"answer\":\"supports\",\"reason\":\"same four steps\"}"
        )
        self.assertEqual("supports", parsed["answer"])

    def test_batched_quote_start_preserves_a_repeated_later_occurrence(self):
        repeated = f"{CLAIM_A} [first]({URL}).\n\n{CLAIM_A} [second]({URL}).\n"
        citations = extract_citations(repeated)
        second_start = repeated.rfind(CLAIM_A)
        response = {
            "claims": [
                {
                    "exact_report_quote": CLAIM_A,
                    "normalized_claim": CLAIM_A,
                    "claim_kind": "external_atomic",
                    "evidence_policy": "citation_required",
                    "citation_refs": [citations[-1]["citation_ref"]],
                    "_quote_start": second_start,
                }
            ]
        }
        claims = normalize_claims(response, repeated, citations)
        self.assertEqual(second_start, claims[0]["quote_start"])
        self.assertLessEqual(claims[0]["paragraph_start"], citations[-1]["start"])
        self.assertGreaterEqual(claims[0]["paragraph_end"], citations[-1]["start"])

    def test_non_substring_claim_quote_is_rejected(self):
        response = FakeJudge(bad_quote=True).call_json(
            "claim-extractor", "", {}, read_json(CLAIM_SCHEMA)
        )
        with self.assertRaisesRegex(JudgeSchemaError, "exact report substring"):
            normalize_claims(response, REPORT, extract_citations(REPORT))

    def test_invalid_claim_quote_is_repaired_without_changing_claim(self):
        judge = FakeJudge(bad_quote=True)
        response = judge.call_json(
            "claim-extractor", "", {}, read_json(CLAIM_SCHEMA)
        )
        repaired, count = repair_invalid_claim_quotes(response, REPORT, judge)
        self.assertEqual(1, count)
        self.assertEqual(CLAIM_A, repaired["claims"][0]["exact_report_quote"])
        self.assertEqual(
            response["claims"][0]["normalized_claim"],
            repaired["claims"][0]["normalized_claim"],
        )
        self.assertEqual(len(response["claims"]), len(repaired["claims"]))

    def test_missing_one_of_34_units_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report, ledger, _ = canary_files(root)
            with self.assertRaisesRegex(JudgeSchemaError, "completeness batch .* IDs differ"):
                run_semantic_pipeline(
                    PackageAssets.load(PACKAGE), REPORT, ledger, FakeJudge(missing_unit=True)
                )

    def test_fetch_without_prior_search_is_not_legally_discovered(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, ledger, _ = canary_files(root, include_search=False)
            observations = reconstruct_observations(
                [json.loads(line) for line in ledger.read_text().splitlines()],
                ledger,
                PackageAssets.load(PACKAGE),
            )
            self.assertTrue(observations[URL]["observed"])
            self.assertFalse(observations[URL]["legally_discovered"])

    def test_kiwix_content_route_is_canonicalized_only_when_registered(self):
        assets = PackageAssets.load(PACKAGE)
        live_url = URL.replace(
            "http://localhost:8090/", "http://localhost:8090/content/"
        )
        citations = extract_citations(f"fact [source]({live_url})")
        normalized = canonicalize_citation_urls(citations, assets)
        self.assertEqual(URL, normalized[0]["url"])
        self.assertEqual(live_url, normalized[0]["reported_url"])
        self.assertTrue(normalized[0]["url_alias_applied"])

        outside = extract_citations(
            "fact [source](http://localhost:8090/content/wiki/not-registered)"
        )
        unchanged = canonicalize_citation_urls(outside, assets)
        self.assertFalse(unchanged[0]["url_alias_applied"])

        backticked = extract_citations(f"fact {URL}`")
        normalized_backticked = canonicalize_citation_urls(backticked, assets)
        self.assertEqual(URL, normalized_backticked[0]["url"])

    def test_empty_report_is_withheld_unless_explicitly_normal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / "empty.md"
            report.write_text("", encoding="utf-8")
            _, ledger, _ = canary_files(root / "evidence")
            withheld_manifest = root / "withheld-run-manifest.json"
            write_json(
                withheld_manifest,
                {
                    "run_id": "EMPTY-WITHHELD",
                    "completed": False,
                    "failure": {"category": "harness"},
                    "execution": {"outcome": "fail"},
                    "report_sha256": sha256_file(report),
                },
            )
            zero_manifest = root / "zero-run-manifest.json"
            write_json(
                zero_manifest,
                {
                    "run_id": "EMPTY-ZERO",
                    "completed": True,
                    "failure": None,
                    "execution": {"outcome": "pass"},
                    "report_sha256": sha256_file(report),
                },
            )
            first = execute(
                package_dir=PACKAGE,
                report_path=report,
                ledger_path=ledger,
                run_manifest_path=withheld_manifest,
                output_dir=root / "withheld",
                judge=FakeJudge(),
                run_id="EMPTY-WITHHELD",
                judge_config={"request_model": "fixed-test-judge", "max_calls": 64},
            )
            second = execute(
                package_dir=PACKAGE,
                report_path=report,
                ledger_path=ledger,
                run_manifest_path=zero_manifest,
                output_dir=root / "zero",
                judge=FakeJudge(),
                run_id="EMPTY-ZERO",
                judge_config={"request_model": "fixed-test-judge", "max_calls": 64},
            )
            self.assertEqual(first["receipt"]["status"], "WITHHELD")
            self.assertEqual(second["receipt"]["status"], "SCORED")
            self.assertTrue(second["packet"]["failure_status"]["status_code"].startswith("scored_zero"))


class Response:
    def __init__(self, status_code: int, value: dict):
        self.status_code = status_code
        self._value = value
        self.text = json.dumps(value)

    def json(self):
        return self._value


class JudgeTransportTests(unittest.TestCase):
    def config(self, *, retries=0):
        return {
            "base_url": "http://judge.invalid/v1",
            "credential_env": "TEST_JUDGE_TOKEN",
            "request_model": "fixed-model",
            "expected_response_model": "fixed-model",
            "temperature": 0,
            "max_tokens": 100,
            "timeout_seconds": 1,
            "transient_retries": retries,
            "retry_http_statuses": [429, 500, 502, 503, 504],
            "usage_required": True,
        }

    def good_envelope(self, model="fixed-model", finish_reason="stop"):
        content = {"claims": []}
        return {
            "model": model,
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            "choices": [{
                "finish_reason": finish_reason,
                "message": {"content": json.dumps(content), "reasoning_content": "reason"},
            }],
        }

    @mock.patch.dict(os.environ, {"TEST_JUDGE_TOKEN": "secret"})
    @mock.patch("auto_score_biodiv_q1.httpx.post")
    def test_identity_mismatch_fails_closed(self, post):
        post.return_value = Response(200, self.good_envelope(model="fallback-model"))
        with tempfile.TemporaryDirectory() as temp:
            judge = AdamsOpenAIJudge(Path(temp), self.config(), "IDENTITY")
            with self.assertRaises(JudgeIdentityError):
                judge.call_json("claims", "prompt", {}, read_json(CLAIM_SCHEMA))

    @mock.patch.dict(os.environ, {"TEST_JUDGE_TOKEN": "secret"})
    @mock.patch("auto_score_biodiv_q1.httpx.post")
    def test_http_429_retries_once_then_succeeds(self, post):
        post.side_effect = [
            Response(429, {"error": "overloaded"}),
            Response(200, self.good_envelope()),
        ]
        with tempfile.TemporaryDirectory() as temp:
            judge = AdamsOpenAIJudge(Path(temp), self.config(retries=1), "RETRY")
            value = judge.call_json("claims", "prompt", {}, read_json(CLAIM_SCHEMA))
            self.assertEqual(value, {"claims": []})
            self.assertEqual(post.call_count, 2)

    @mock.patch.dict(os.environ, {"TEST_JUDGE_TOKEN": "secret"})
    @mock.patch("auto_score_biodiv_q1.httpx.post")
    def test_finish_reason_length_is_explicit_truncation_and_metadata_is_complete(self, post):
        envelope = self.good_envelope(finish_reason="length")
        envelope["choices"][0]["message"]["content"] = ""
        envelope["choices"][0]["message"]["reasoning_content"] = "unfinished reasoning"
        post.return_value = Response(200, envelope)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            judge = AdamsOpenAIJudge(root, self.config(), "TRUNCATED")
            with self.assertRaises(JudgeTruncationError):
                judge.call_json("claims", "prompt", {}, read_json(CLAIM_SCHEMA))
            metadata = json.loads(next(root.glob("*/metadata.json")).read_text())
            self.assertEqual("length", metadata["finish_reason"])
            self.assertEqual(0, metadata["content_chars"])
            self.assertEqual(len("unfinished reasoning"), metadata["reasoning_content_chars"])

    @mock.patch.dict(os.environ, {"TEST_JUDGE_TOKEN": "secret"})
    @mock.patch("auto_score_biodiv_q1.httpx.post")
    def test_adams_headers_are_sent_without_persisting_credential(self, post):
        post.return_value = Response(200, self.good_envelope())
        config = {
            **self.config(),
            "provider": "adams_openai_compatible",
            "adams_platform_user": "sivenfuuliu",
            "adams_business": "3939",
            "thinking": {"type": "disabled"},
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            judge = AdamsOpenAIJudge(root, config, "HEADERS")
            judge.call_json("claims", "prompt", {}, read_json(CLAIM_SCHEMA))
            sent = post.call_args.kwargs["headers"]
            self.assertEqual(sent["Adams-Platform-User"], "sivenfuuliu")
            self.assertEqual(sent["Adams-Business"], "3939")
            self.assertEqual(sent["Authorization"], "Bearer secret")
            self.assertEqual(
                post.call_args.kwargs["json"]["thinking"],
                {"type": "disabled"},
            )
            self.assertNotIn("enable_thinking", post.call_args.kwargs["json"])
            persisted = "".join(
                path.read_text(encoding="utf-8")
                for path in root.rglob("*")
                if path.is_file()
            )
            self.assertNotIn("Bearer secret", persisted)

    def test_judge_usage_summary_preserves_cost_relevant_token_classes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "0001-call"
            write_json(
                root / "metadata.json",
                {
                    "http_status": 200,
                    "actual_response_model": "fixed-model",
                    "identity_match": True,
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "total_tokens": 120,
                        "input_tokens_details": {
                            "cached_tokens": 30,
                            "cache_write_tokens": 10,
                        },
                        "output_tokens_details": {"reasoning_tokens": 7},
                    },
                },
            )
            summary = judge_usage_summary(root.parent)
            self.assertEqual(
                summary["tokens"],
                {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "cached_tokens": 30,
                    "cache_write_tokens": 10,
                    "reasoning_tokens": 7,
                },
            )

    @mock.patch.dict(os.environ, {"TEST_JUDGE_TOKEN": "secret"})
    @mock.patch("auto_score_biodiv_q1.httpx.post")
    def test_gpt_payload_uses_completion_budget_and_no_temperature(self, post):
        post.return_value = Response(200, self.good_envelope(model="gpt-5.6-sol-2026-07-09"))
        config = {
            **self.config(),
            "request_model": "gpt-5.6-sol",
            "expected_response_model": "gpt-5.6-sol-2026-07-09",
            "temperature": None,
            "max_completion_tokens": 16384,
            "reasoning_effort": "none",
        }
        config.pop("max_tokens", None)
        with tempfile.TemporaryDirectory() as temp:
            judge = AdamsOpenAIJudge(Path(temp), config, "GPT-PAYLOAD")
            judge.call_json("claims", "prompt", {}, read_json(CLAIM_SCHEMA))
            sent = post.call_args.kwargs["json"]
            self.assertEqual(sent["max_completion_tokens"], 16384)
            self.assertEqual(sent["reasoning_effort"], "none")
            self.assertNotIn("max_tokens", sent)
            self.assertNotIn("temperature", sent)

    @mock.patch.dict(os.environ, {"TEST_JUDGE_TOKEN": "secret"})
    @mock.patch("auto_score_biodiv_q1.httpx.post")
    def test_repeated_http_429_is_not_converted_to_score(self, post):
        post.return_value = Response(429, {"error": "overloaded"})
        with tempfile.TemporaryDirectory() as temp:
            judge = AdamsOpenAIJudge(Path(temp), self.config(retries=1), "RETRY-FAIL")
            with self.assertRaises(JudgeError):
                judge.call_json("claims", "prompt", {}, read_json(CLAIM_SCHEMA))
            self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
