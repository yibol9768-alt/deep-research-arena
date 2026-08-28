from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/plot_cross5_cost_scores.py"
spec = importlib.util.spec_from_file_location("cost_score_plots", SCRIPT)
plots = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(plots)


class CostScorePlotTests(unittest.TestCase):
    def test_missing_and_withheld_scores_are_not_plotted_as_zero(self):
        summary = {
            "cells": [
                {
                    "cell_id": "scored",
                    "harness_id": "deerflow",
                    "model_id": "gpt-5-6-sol",
                    "requested_model": "gpt-5.6-sol",
                    "evaluation_status": "scored",
                    "agent_cost": {"cny": 1.5},
                    "latest_metrics": {"gcp": {"score": 0.25}},
                },
                {
                    "cell_id": "withheld",
                    "harness_id": "deerflow",
                    "model_id": "gemini-3-1-pro-preview",
                    "requested_model": "gemini-3.1-pro-preview",
                    "evaluation_status": "withheld_observability",
                    "agent_cost": {"cny": 1.0},
                    "latest_metrics": {"gcp": {"score": None}},
                },
            ]
        }
        self.assertEqual(["scored"], [row["cell_id"] for row in plots.load_points(summary, "gcp")])

    def test_pareto_frontier_prefers_lower_cost_at_equal_score(self):
        points = [
            {"cell_id": "a", "cost_cny": 2.0, "score": 0.5},
            {"cell_id": "b", "cost_cny": 1.0, "score": 0.5},
            {"cell_id": "c", "cost_cny": 3.0, "score": 0.8},
            {"cell_id": "d", "cost_cny": 4.0, "score": 0.7},
        ]
        self.assertEqual(
            ["b", "c"],
            [row["cell_id"] for row in plots.pareto_frontier(points)],
        )


if __name__ == "__main__":
    unittest.main()
