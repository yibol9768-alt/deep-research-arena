from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "q1_v2_summary_test", ROOT / "scripts/summarize_q1_v2_matrix.py"
)
summary = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(summary)


class Q1V2SummaryTests(unittest.TestCase):
    def test_score_version_path_is_strict_and_isolated(self):
        root = Path("/scores")
        score_v1 = summary.cell_evaluation_path(root, "run", "cell", 1, "score-v1")
        score_v2 = summary.cell_evaluation_path(root, "run", "cell", 1, "score-v2")
        self.assertEqual(Path("/scores/run/cell/attempt-1/score-v1/cell-evaluation.json"), score_v1)
        self.assertEqual(Path("/scores/run/cell/attempt-1/score-v2/cell-evaluation.json"), score_v2)
        self.assertNotEqual(score_v1, score_v2)
        for invalid in ("score-v0", "score-v2/../score-v1", "score-v2-x"):
            with self.assertRaises(Exception):
                summary.cell_evaluation_path(root, "run", "cell", 1, invalid)

    def test_gateway_reconciliation_requires_exact_unique_ids(self):
        rows = [{"event_id": "e1"}, {"event_id": "e2"}]
        receipt = summary.reconcile_gateway_events(rows, list(reversed(rows)))
        self.assertEqual("PASS_EXACT_EVENT_ID_RECONCILIATION", receipt["status"])
        with self.assertRaises(ValueError):
            summary.reconcile_gateway_events(rows, [{"event_id": "e1"}])
        with self.assertRaises(ValueError):
            summary.reconcile_gateway_events(rows, [{"event_id": "e1"}, {"event_id": "e1"}])

    def test_group_summary_preserves_unpriced_cost_as_na(self):
        cells = [{
            "model_id": "qwen3-4b",
            "evaluation_status": "scored",
            "agent_request_count": 1,
            "agent_tokens": {key: (5 if key == "input" else 0) for key in summary.TOKEN_KEYS},
            "agent_request_costs": [{"status": "N/A_UNPRICED_EXACT_MODEL", "usd": None, "cny": None}],
            "metrics": {name: {"score": 0.25} for name in summary.METRICS},
        }]
        row = summary.group_summary(cells, "model_id")[0]
        self.assertEqual("PARTIAL_NA_UNPRICED", row["agent_cost"]["status"])
        self.assertIsNone(row["agent_cost"]["usd"])
        self.assertEqual(0.25, row["mean_grr"])


if __name__ == "__main__":
    unittest.main()
