from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_citation_space_closure.py"


def find_q1_v2_package() -> Path:
    override = os.environ.get("Q1_V2_PACKAGE")
    if override:
        return Path(override)
    candidates = [ROOT.parent / "biodiv_q1_scoring_system" / "fixtures" / "q1_v2_package"]
    candidates.extend(sorted(ROOT.parent.glob("biodiv_q1_scoring_system_*/fixtures/q1_v2_package")))
    for candidate in reversed(candidates):
        if candidate.is_dir():
            return candidate
    raise AssertionError("q1_v2_package fixture not found")


PACKAGE = find_q1_v2_package()


class CitationSpaceClosureTests(unittest.TestCase):
    def run_gate(self, *extra: str) -> tuple[int, dict]:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "closure.json"
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--package-dir", str(PACKAGE), "--output", str(output), *extra],
                text=True,
                capture_output=True,
            )
            payload = json.loads(output.read_text()) if output.exists() else {}
            return completed.returncode, payload

    def test_whole_snapshot_query_with_registry_only_citations_fails_closed(self):
        code, payload = self.run_gate()
        self.assertEqual(2, code)
        self.assertEqual("FAIL", payload["status"])
        self.assertIn(
            "whole_snapshot_query_with_registry_only_citations",
            {row["code"] for row in payload["violations"]},
        )

    def test_context_claim_mode_is_explicitly_shadow_only(self):
        code, payload = self.run_gate("--allow-context-claims")
        self.assertEqual(0, code)
        self.assertEqual("PASS", payload["status"])
        self.assertFalse(payload["formal_eligible"])
        self.assertEqual("SHADOW_EXPERIMENTAL_ONLY", payload["release_mode"])

    def test_verifier_capacity_cannot_be_below_report_budget(self):
        code, payload = self.run_gate(
            "--allow-context-claims", "--max-urls", "10", "--verifier-max-urls", "9"
        )
        self.assertEqual(2, code)
        self.assertIn(
            "verifier_capacity_below_report_budget",
            {row["code"] for row in payload["violations"]},
        )


if __name__ == "__main__":
    unittest.main()
