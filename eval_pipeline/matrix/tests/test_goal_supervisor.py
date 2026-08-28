from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


score_cell = load("score_matrix_cell_test", ROOT / "scripts/score_matrix_cell.py")
supervisor = load("goal_supervisor_test", ROOT / "scripts/goal_supervisor.py")


def find_test_scorer_dir() -> Path:
    override = os.environ.get("Q1_TEST_SCORER_DIR")
    if override:
        return Path(override)
    candidates = [ROOT.parent / "biodiv_q1_scoring_system"]
    candidates.extend(sorted(ROOT.parent.glob("biodiv_q1_scoring_system_*")))
    for candidate in reversed(candidates):
        if (candidate / "fixtures/q1_package").is_dir():
            return candidate
    raise AssertionError("test scorer dir not found")


class GoalSupervisorTests(unittest.TestCase):
    def test_score_cell_rejects_unsafe_score_version(self):
        self.assertEqual("score-v2", score_cell.validated_score_version("score-v2"))
        for invalid in ("score-v0", "score-v2/../score-v1", "v2", "score-v2-x"):
            with self.assertRaises(argparse.ArgumentTypeError):
                score_cell.validated_score_version(invalid)

    def test_score_version_is_strict_and_routes_commands_and_paths(self):
        args = Namespace(
            run_id="run-a",
            runs_root=Path("/runs"),
            scores_root=Path("/scores"),
            scorer_dir=Path("/scorer"),
            package_dir=Path("/package"),
            audit_script=Path("/audit.py"),
            scorer_root=Path("/root"),
            pricing=Path("/pricing.json"),
            score_version="score-v2",
        )
        command = supervisor.score_command(args, "cell-a", 1)
        self.assertEqual("score-v2", command[command.index("--score-version") + 1])
        self.assertEqual(
            "/scorer/config/judge.glm5d2.v1.json",
            command[command.index("--judge-config") + 1],
        )
        self.assertEqual(
            Path("/scores/run-a/cell-a/attempt-1/score-v2/cell-evaluation.json"),
            supervisor.evaluation_path(args, "cell-a", 1),
        )
        for invalid in ("score-v0", "score-v01", "score-v2/../score-v1", "v2", "score-v2-x"):
            with self.assertRaises(Exception):
                supervisor.validated_score_version(invalid)

    def test_explicit_judge_config_is_forwarded_unchanged(self):
        args = Namespace(
            run_id="run-a",
            runs_root=Path("/runs"),
            scores_root=Path("/scores"),
            scorer_dir=Path("/scorer"),
            judge_config=Path("/frozen/judge.gpt.json"),
            package_dir=Path("/package"),
            audit_script=Path("/audit.py"),
            scorer_root=Path("/root"),
            pricing=Path("/pricing.json"),
            score_version="score-v4",
        )
        command = supervisor.score_command(args, "cell-a", 1)
        self.assertEqual(
            "/frozen/judge.gpt.json",
            command[command.index("--judge-config") + 1],
        )

    def test_numeric_metrics_accepts_real_zero_and_fixed_grr_denominator(self):
        metrics = score_cell.numeric_metrics(
            {
                "metrics": {
                    "citation_binding": {
                        "status": "scored_zero_normal_empty_report", "score": 0.0,
                        "passed_required_claim_count": 0, "required_claim_count": 0,
                    },
                    "gcp": {
                        "status": "scored_zero_no_material_claim", "score": 0.0,
                        "grounded_claim_count": 0, "eligible_claim_count": 0,
                    },
                    "grr": {
                        "status": "scored_zero_no_grounded_required_unit", "score": 0.0,
                        "grounded_unit_count": 0, "necessary_unit_count": 34,
                    },
                }
            }
        )
        self.assertEqual(0.0, metrics["citation_binding"]["score"])
        self.assertEqual(34, metrics["grr"]["denominator"])

    def test_numeric_metrics_rejects_withheld_or_wrong_denominator(self):
        base = {
            "metrics": {
                "citation_binding": {"status": "scored", "score": 0.5},
                "gcp": {"status": "scored", "score": 0.5},
                "grr": {"status": "scored", "score": 0.5, "necessary_unit_count": 33},
            }
        }
        with self.assertRaises(ValueError):
            score_cell.numeric_metrics(base)
        base["metrics"]["grr"].update(status="withheld", necessary_unit_count=34)
        with self.assertRaises(ValueError):
            score_cell.numeric_metrics(base)

    def test_valid_evaluation_requires_all_numeric_and_grr_34(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evaluation.json"
            path.write_text(json.dumps({
                "status": "SCORED",
                "metrics": {
                    "citation_binding": {"score": 0.0},
                    "gcp": {"score": 0.25},
                    "grr": {"score": 1 / 34, "denominator": 34},
                },
            }))
            self.assertTrue(supervisor.valid_evaluation(path))
            document = json.loads(path.read_text())
            document["metrics"]["gcp"]["score"] = None
            path.write_text(json.dumps(document))
            self.assertFalse(supervisor.valid_evaluation(path))

    def test_empty_but_real_attempt_scores_zero_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            cell_id = "biodiversity-q1-v2--deerflow--gpt-5-6-sol"
            attempt = run_dir / "cells" / cell_id / "attempt-1"
            evidence = attempt / "search_evidence"
            evidence.mkdir(parents=True)
            (run_dir / "run.json").write_text(json.dumps({"run_id": "offline-score-zero"}))
            documents = {
                "exit_status.json": {
                    "cell_id": cell_id, "status": "success", "exit_code": 0,
                    "reason": None,
                },
                "identity.json": {"identity_consistent": True},
                "observability.json": {
                    "schema_version": "2.0.0", "recorder_initialized": True,
                    "capture_bracket_valid": True, "capture_healthy": True,
                    "search_call_count": 0, "fetch_call_count": 0,
                    "zero_tool_calls_attested": True,
                },
                "report_provenance.json": {"model_output_attested": True},
                "meta.json": {"status": "pass"},
            }
            for name, document in documents.items():
                (attempt / name).write_text(json.dumps(document))
            (attempt / "report.md").write_text("")
            usage = {
                "cell_id": cell_id,
                "matrix_attribution": {"cell_id": cell_id},
                "requested_model": "gpt-5.6-sol",
                "expected_actual_identity": "gpt-5.6-sol-2026-07-09",
                "actual_model_identity": "gpt-5.6-sol-2026-07-09",
                "identity_match": True,
                "http_status": 200,
                "usage_observed": True,
                "tokens": {"input": 5, "output": 1, "total": 6},
            }
            (attempt / "gateway_usage.jsonl").write_text(json.dumps(usage) + "\n")
            fake_aggregator = root / "fake_aggregator.py"
            fake_aggregator.write_text(
                "def aggregate(package_dir, scorer_root, packet_path):\n"
                " return {'metrics': {"
                "'citation_binding': {'status':'scored','score':0.0,'passed_required_claim_count':0,'required_claim_count':0},"
                "'gcp': {'status':'scored','score':0.0,'grounded_claim_count':0,'eligible_claim_count':0},"
                "'grr': {'status':'scored','score':0.0,'grounded_unit_count':0,'necessary_unit_count':34}" 
                "}, 'failure_status': {'category':'report','status_code':'scored_zero_normal_empty_report'}}\n"
            )
            scorer_dir = find_test_scorer_dir()
            result = score_cell.score_cell(Namespace(
                matrix_run_dir=run_dir,
                cell_id=cell_id,
                attempt_index=1,
                score_version="score-v1",
                output_root=root / "scores",
                scorer_dir=scorer_dir,
                package_dir=scorer_dir / "fixtures/q1_package",
                audit_script=fake_aggregator,
                scorer_root=root,
                pricing=ROOT / "config/pricing.cross5.20260825.json",
            ))
            self.assertEqual("SCORED", result["status"])
            self.assertEqual(0.0, result["metrics"]["citation_binding"]["score"])
            self.assertEqual(0.0, result["metrics"]["gcp"]["score"])
            self.assertEqual(0.0, result["metrics"]["grr"]["score"])
            self.assertEqual(34, result["metrics"]["grr"]["denominator"])
            seal = root / "scores" / cell_id / "attempt-1/score-v1/cell-evaluation-seal.json"
            self.assertTrue(seal.is_file())

    def test_resume_score_v2_ignores_score_v1_and_does_not_rerun_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "cross5-resume"
            run_dir = root / "runs" / run_id
            scores_root = root / "scores"
            run_dir.mkdir(parents=True)
            manifest = {
                "design": "CROSS5_FIXED_HARNESS_FIXED_MODEL",
                "concurrency": {"global_cells": 3, "judge_requests": 2},
                "cells": [
                    {"cell_id": cell_id, "ordinal": index + 1}
                    for index, cell_id in enumerate(supervisor.EXPECTED_CROSS5_CELL_IDS)
                ],
            }
            manifest_path = root / "matrix.cross5.manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            harness_receipt = root / "harness.json"
            harness_receipt.write_text(json.dumps({
                "status": "PASS_NO_MODEL",
                "matrix_manifest_sha256": supervisor.sha256_file(manifest_path),
                "matrix_cell_count": 5,
            }))
            route_receipt = root / "routes.json"
            route_receipt.write_text(json.dumps({"status": "PASS"}))
            (run_dir / "run.json").write_text(json.dumps({"run_id": run_id}))
            first_cell = supervisor.EXPECTED_CROSS5_CELL_IDS[0]
            for index, cell_id in enumerate(supervisor.EXPECTED_CROSS5_CELL_IDS):
                cell_dir = run_dir / "cells" / cell_id
                cell_dir.mkdir(parents=True)
                state = {
                    "cell_id": cell_id,
                    "status": "success" if index == 0 else "pending",
                    "attempt_count": 1 if index == 0 else 0,
                }
                (cell_dir / "state.json").write_text(json.dumps(state))
            first_state_path = run_dir / "cells" / first_cell / "state.json"
            first_state_before = first_state_path.read_bytes()
            legacy = scores_root / run_id / first_cell / "attempt-1/score-v1"
            legacy.mkdir(parents=True)
            legacy_evaluation = legacy / "cell-evaluation.json"
            legacy_evaluation.write_text(json.dumps({
                "status": "SCORED",
                "metrics": {
                    "citation_binding": {"score": 0.1},
                    "gcp": {"score": 0.1},
                    "grr": {"score": 1 / 34, "denominator": 34},
                },
            }))
            legacy_before = legacy_evaluation.read_bytes()
            commands = []

            def write_evaluation(cell_id: str, attempt_index: int) -> None:
                path = (
                    scores_root / run_id / cell_id / f"attempt-{attempt_index}"
                    / "score-v2/cell-evaluation.json"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({
                    "status": "SCORED",
                    "metrics": {
                        "citation_binding": {"score": 0.2},
                        "gcp": {"score": 0.3},
                        "grr": {"score": 2 / 34, "denominator": 34},
                    },
                    "agent": {},
                    "judge": {},
                }))

            def fake_run_logged(command, _log_dir, label):
                commands.append((list(command), label))
                if "score_matrix_cell.py" in " ".join(command):
                    self.assertIn("score-v2", command)
                    write_evaluation(first_cell, 1)
                elif "matrix_executor.py" in " ".join(command):
                    self.assertIn("--resume", command)
                    self.assertNotIn("--cell-id", command)
                    for cell_id in supervisor.EXPECTED_CROSS5_CELL_IDS[1:]:
                        path = run_dir / "cells" / cell_id / "state.json"
                        state = json.loads(path.read_text())
                        state.update(status="success", attempt_count=1)
                        path.write_text(json.dumps(state))
                return 0

            async def fake_score_all(_args, cells, _concurrency, _log_dir):
                for cell_id, attempt_index in cells:
                    write_evaluation(cell_id, attempt_index)
                return {cell_id: 0 for cell_id, _ in cells}

            argv = [
                "goal_supervisor.py",
                "--run-id", run_id,
                "--manifest", str(manifest_path),
                "--runs-root", str(root / "runs"),
                "--scores-root", str(scores_root),
                "--scorer-dir", str(root / "scorer"),
                "--package-dir", str(root / "package"),
                "--audit-script", str(root / "audit.py"),
                "--scorer-root", str(root),
                "--pricing", str(root / "pricing.json"),
                "--harness-preflight-receipt", str(harness_receipt),
                "--route-probe-receipt", str(route_receipt),
                "--score-version", "score-v2",
                "--resume",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                supervisor, "run_logged", side_effect=fake_run_logged
            ), mock.patch.object(supervisor, "score_all", side_effect=fake_score_all):
                self.assertEqual(0, supervisor.main())
            self.assertEqual(first_state_before, first_state_path.read_bytes())
            self.assertEqual(legacy_before, legacy_evaluation.read_bytes())
            self.assertTrue((scores_root / run_id / first_cell / "attempt-1/score-v2/cell-evaluation.json").is_file())
            harness_commands = [command for command, _ in commands if "matrix_executor.py" in " ".join(command)]
            self.assertEqual(1, len(harness_commands))
            self.assertNotIn(first_cell, harness_commands[0])


if __name__ == "__main__":
    unittest.main()
