from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/summarize_cross5_pilot.py"
spec = importlib.util.spec_from_file_location("cross5_summary", SCRIPT)
summary = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(summary)


class Cross5PilotSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pricing = summary.Pricing(summary.DEFAULT_PRICING)
        cls.inputs = ROOT / "inputs"
        cls.runs = [cls.inputs / f"BQ1-CROSS5-PILOT-20260825-{letter}" for letter in "ABC"]

    def test_gpt_single_request_long_context_threshold_is_strict(self):
        short = self.pricing.price("gpt-5.6-sol", {**summary.zero_tokens(), "input": 272000, "output": 10}, "standard")
        long = self.pricing.price("gpt-5.6-sol", {**summary.zero_tokens(), "input": 272001, "output": 10}, "standard")
        self.assertEqual("standard-prompt-0-272000", short["rate_card_id"])
        self.assertEqual("standard-prompt-272001-plus", long["rate_card_id"])
        self.assertAlmostEqual(1.0882, short["usd"])
        self.assertAlmostEqual(2.176308, long["usd"])

    def test_gemini_single_request_threshold_is_strict(self):
        short = self.pricing.price("gemini-3.1-pro-preview", {**summary.zero_tokens(), "input": 200000, "output": 10}, "standard")
        long = self.pricing.price("gemini-3.1-pro-preview", {**summary.zero_tokens(), "input": 200001, "output": 10}, "standard")
        self.assertEqual("paid-standard-prompt-0-200000", short["rate_card_id"])
        self.assertEqual("paid-standard-prompt-200001-plus", long["rate_card_id"])
        self.assertAlmostEqual(0.40012, short["usd"])
        self.assertAlmostEqual(0.800184, long["usd"])

    def test_claude_cost_and_unpriced_models_are_not_guessed(self):
        tokens = {**summary.zero_tokens(), "input": 154864, "output": 7322}
        claude = self.pricing.price("claude-opus-5", tokens, "standard")
        self.assertAlmostEqual(0.95737, claude["usd"])
        unknown = self.pricing.price("glm_5d2_fp8_adams", tokens, "standard")
        self.assertEqual("N/A_UNPRICED_EXACT_MODEL", unknown["status"])
        self.assertIsNone(unknown["usd"])

    def test_nested_cached_and_reasoning_token_details_are_preserved(self):
        tokens = summary.normalized_tokens({
            "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
            "prompt_tokens_details": {"cached_tokens": 40},
            "completion_tokens_details": {"reasoning_tokens": 7},
        })
        self.assertEqual(40, tokens["cached_input"])
        self.assertEqual(7, tokens["reasoning"])

    def test_real_run_abc_preserves_attempts_failures_usage_and_missing_scores(self):
        result = summary.build_summary(self.runs, self.pricing, {})
        self.assertEqual(3, result["totals"]["run_count"])
        self.assertEqual(5, result["totals"]["unique_cell_count"])
        self.assertEqual(20, result["totals"]["attempt_count"])
        self.assertEqual(30, result["totals"]["request_count"])
        self.assertEqual(1, result["totals"]["report_count"])
        self.assertEqual(0, result["totals"]["scored_cell_count"])
        self.assertEqual("available", result["totals"]["cny_status"])
        by_id = {cell["cell_id"]: cell for cell in result["cells"]}
        claude = by_id["biodiversity-q1--deerflow--claude-opus-5"]
        self.assertEqual(154864, claude["agent_tokens"]["input"])
        self.assertEqual(7322, claude["agent_tokens"]["output"])
        self.assertAlmostEqual(0.95737, claude["agent_cost"]["usd"])
        self.assertAlmostEqual(0.95737 * 6.722736625514403, claude["agent_cost"]["cny"])
        self.assertEqual("not_available", claude["score_status"])
        self.assertEqual("withheld_observability", claude["evaluation_status"])
        self.assertIsNone(claude["latest_metrics"]["grr"]["score"])
        gpt = by_id["biodiversity-q1--deerflow--gpt-5-6-sol"]
        self.assertEqual({"429": 1, "502": 4}, gpt["http_status_counts"])
        self.assertEqual([0, 0, 1, 0, 1], [attempt["retry_index"] for attempt in gpt["attempts"]])
        self.assertTrue(any(item["path"].endswith("failure_receipt.json") for attempt in gpt["attempts"] for item in attempt["failure_evidence"]))

    def test_explicit_score_map_attaches_metrics_and_separates_judge_cost(self):
        run_id = "BQ1-CROSS5-PILOT-20260825-B"
        cell_id = "biodiversity-q1--deerflow--claude-opus-5"
        with tempfile.TemporaryDirectory() as tmp:
            score_dir = Path(tmp) / "score"
            call = score_dir / "judge-calls/0001-test-attempt-0"
            call.mkdir(parents=True)
            (score_dir / "shadow-score.json").write_text(json.dumps({"metrics": {
                "citation_binding": {"score": 0.5, "status": "scored", "passed_required_claim_count": 1, "required_claim_count": 2},
                "gcp": {"score": 0.25, "status": "scored", "grounded_claim_count": 1, "eligible_claim_count": 4},
                "grr": {"score": 1 / 34, "status": "scored", "grounded_unit_count": 1, "necessary_unit_count": 34},
            }}))
            (call / "metadata.json").write_text(json.dumps({
                "stage": "test", "retry_index": 0, "request_model": "claude-opus-5",
                "expected_response_model": "claude-opus-5", "actual_response_model": "claude-opus-5",
                "identity_match": True, "http_status": 200, "latency_ms": 50,
                "usage": {"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100},
            }))
            scores = summary.score_map([f"{run_id}:{cell_id}:1={score_dir}"], [], self.pricing)
            result = summary.build_summary([self.runs[1]], self.pricing, scores)
            cell = next(row for row in result["cells"] if row["cell_id"] == cell_id)
            self.assertEqual("available", cell["score_status"])
            self.assertEqual("scored", cell["evaluation_status"])
            self.assertAlmostEqual(1 / 34, cell["latest_metrics"]["grr"]["score"])
            self.assertEqual(1000, cell["judge_tokens"]["input"])
            self.assertAlmostEqual(0.0075, cell["judge_cost"]["usd"])
            self.assertAlmostEqual(0.95737, cell["agent_cost"]["usd"])

    def test_diagnostic_probe_cost_is_separate_from_matrix_agent_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "probe.json"
            receipt.write_text(json.dumps({
                "schema_version": "gpt_route_payload_probe_v1",
                "requested_model": "gpt-5.6-sol",
                "rows": [{
                    "variant": "compatible", "actual_model_identity": "gpt-5.6-sol-2026-07-09",
                    "identity_match": True, "http_status": 200, "latency_ms": 10,
                    "usage": {"input": 7, "output": 5, "total": 12},
                }],
            }))
            diagnostics = summary.diagnostic_records([receipt], self.pricing)
            result = summary.build_summary([self.runs[1]], self.pricing, {}, diagnostics=diagnostics)
            self.assertEqual(12, result["totals"]["diagnostic_tokens"]["total"])
            self.assertAlmostEqual(0.000128, result["totals"]["diagnostic_cost"]["usd"])
            self.assertAlmostEqual(0.957372, result["totals"]["agent_cost"]["usd"])

    def test_outputs_include_four_csv_views_json_and_hash_seal(self):
        result = summary.build_summary([self.runs[1]], self.pricing, {})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            summary.write_outputs(result, out)
            expected = {"pilot_summary.json", "pilot_cells.csv", "pilot_attempts.csv", "pilot_requests.csv", "pilot_scores.csv", "pilot_diagnostics.csv", "SHA256SUMS.json"}
            self.assertEqual(expected, {path.name for path in out.iterdir()})
            seal = json.loads((out / "SHA256SUMS.json").read_text())
            self.assertEqual(expected - {"SHA256SUMS.json"}, {row["path"] for row in seal["files"]})


if __name__ == "__main__":
    unittest.main()
