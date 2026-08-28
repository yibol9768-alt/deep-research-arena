from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from auto_score_biodiv_q1 import PackageAssets, read_ledger, reconstruct_observations
from prepare_matrix_cell import ProjectionError, project


ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "fixtures" / "q1_package"


class PrepareMatrixCellTests(unittest.TestCase):
    def make_attempt(
        self,
        root: Path,
        *,
        corrupt_sha: bool = False,
        include_frozen_quote: bool = True,
        include_result: bool = True,
        matrix_reason: str = "evidence_observability_incomplete",
        report_text: str = "A supported fact [source](http://localhost:8090/content/wikipedia_en_all_nopic_2026-06/Biodiversity).",
    ) -> Path:
        attempt = root / "attempt-1"
        evidence = attempt / "search_evidence"
        blobs = evidence / "blobs"
        blobs.mkdir(parents=True)
        attempt.joinpath("report.md").write_text(report_text)
        attempt.joinpath("meta.json").write_text(json.dumps({"status": "pass"}))
        attempt.joinpath("exit_status.json").write_text(json.dumps({
            "cell_id": "cell-a", "exit_code": 0, "status": "failed",
            "reason": matrix_reason,
        }))
        mapping = json.loads((PACKAGE / "evidence_mapping.json").read_text())
        row = next(value for value in mapping["evidence_rows"] if value["canonical_url"].endswith("/Biodiversity"))
        results = [{
                "url": row["canonical_url"].replace("http://localhost:8090/", "http://localhost:8090/content/"),
                "raw_content": (
                    "prefix " + row["quote"] + " suffix"
                    if include_frozen_quote
                    else "captured content without a frozen exact quote"
                ),
            }] if include_result else []
        response = {"results": results}
        body = json.dumps(response).encode()
        digest = hashlib.sha256(body).hexdigest()
        blobs.joinpath(digest).write_bytes(body)
        recorded = "0" * 64 if corrupt_sha else digest
        evidence.joinpath("run.jsonl").write_text(json.dumps({
            "kind": "search", "status": 200,
            "response_blob_ref": f"blobs/{digest}",
            "response_sha256": recorded,
        }) + "\n")
        return attempt

    def test_projects_captured_raw_content_and_attests_normal_agent_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            attempt = self.make_attempt(root)
            output = root / "projection"
            receipt = project(
                attempt_dir=attempt, package_dir=PACKAGE,
                output_dir=output, run_id="score-cell-a",
            )
            self.assertEqual(1, receipt["search_event_count"])
            self.assertEqual(1, receipt["projected_content_count"])
            self.assertGreaterEqual(receipt["frozen_exact_quote_verified_count"], 1)
            self.assertTrue(receipt["normal_agent_return"])
            self.assertTrue(receipt["projection_recovers_observability_only"])
            ledger = [json.loads(line) for line in (output / "strict-evidence.jsonl").read_text().splitlines()]
            self.assertEqual(["search", "fetch"], [row["kind"] for row in ledger])
            self.assertTrue(ledger[1]["frozen_identity_verified_by_exact_quote"])
            manifest = json.loads((output / "run-manifest.json").read_text())
            self.assertTrue(manifest["completed"])
            self.assertEqual("success", manifest["execution"]["outcome"])
            diagnostics = json.loads((output / "citation-diagnostics.json").read_text())
            self.assertEqual(1, diagnostics["citation_count"])
            self.assertEqual(
                {"in_registry_and_fetched": 1}, diagnostics["status_counts"]
            )
            self.assertEqual(
                "in_registry_and_fetched", diagnostics["citations"][0]["status"]
            )
            self.assertTrue(diagnostics["citations"][0]["alias_rewritten"])
            self.assertTrue(diagnostics["citations"][0]["matched_evidence_ids"])

    def test_snapshot_page_outside_registry_is_coverage_diagnostic_not_fabrication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            attempt = self.make_attempt(
                root,
                report_text=(
                    "A relevant claim [source]("
                    "http://localhost:8090/content/wikipedia_en_all_nopic_2026-06/Biodiversity_loss)."
                ),
            )
            output = root / "projection"
            receipt = project(
                attempt_dir=attempt, package_dir=PACKAGE,
                output_dir=output, run_id="score-cell-a",
            )
            diagnostics = json.loads((output / "citation-diagnostics.json").read_text())
            self.assertEqual(
                {"in_snapshot_but_out_of_package_registry": 1},
                diagnostics["status_counts"],
            )
            row = diagnostics["citations"][0]
            self.assertEqual("in_snapshot_but_out_of_package_registry", row["status"])
            self.assertFalse(row["registry_hit"])
            self.assertEqual("registry_miss", row["failure_gate"])
            self.assertEqual(
                {"in_snapshot_but_out_of_package_registry": 1},
                receipt["citation_status_counts"],
            )

    def test_rejects_captured_blob_sha_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            attempt = self.make_attempt(root, corrupt_sha=True)
            with self.assertRaisesRegex(ProjectionError, "SHA mismatch"):
                project(
                    attempt_dir=attempt, package_dir=PACKAGE,
                    output_dir=root / "projection", run_id="score-cell-a",
                )

    def test_registered_url_without_frozen_exact_quote_is_not_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            attempt = self.make_attempt(root, include_frozen_quote=False)
            output = root / "projection"
            receipt = project(
                attempt_dir=attempt, package_dir=PACKAGE,
                output_dir=output, run_id="score-cell-a",
            )
            self.assertEqual(0, receipt["frozen_exact_quote_verified_count"])
            ledger = read_ledger(output / "strict-evidence.jsonl")
            fetch = next(row for row in ledger if row["kind"] == "fetch")
            self.assertFalse(fetch["frozen_identity_verified_by_exact_quote"])
            self.assertIsNone(fetch["page_content_sha256"])
            observations = reconstruct_observations(
                ledger, output / "strict-evidence.jsonl", PackageAssets.load(PACKAGE)
            )
            self.assertEqual({}, observations)

    def test_report_citation_is_never_used_when_search_blob_has_no_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            attempt = self.make_attempt(root, include_result=False)
            output = root / "projection"
            receipt = project(
                attempt_dir=attempt, package_dir=PACKAGE,
                output_dir=output, run_id="score-cell-a",
            )
            self.assertEqual(0, receipt["projected_content_count"])
            ledger = read_ledger(output / "strict-evidence.jsonl")
            self.assertEqual(["search"], [row["kind"] for row in ledger])

    def test_unrelated_matrix_failure_is_not_promoted_to_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            attempt = self.make_attempt(root, matrix_reason="identity_cross_check_failed")
            output = root / "projection"
            receipt = project(
                attempt_dir=attempt, package_dir=PACKAGE,
                output_dir=output, run_id="score-cell-a",
            )
            self.assertFalse(receipt["normal_agent_return"])
            self.assertFalse(receipt["projection_recovers_observability_only"])
            manifest = json.loads((output / "run-manifest.json").read_text())
            self.assertFalse(manifest["completed"])
            self.assertEqual("failed", manifest["execution"]["outcome"])


if __name__ == "__main__":
    unittest.main()
