#!/usr/bin/env python3
"""Score every positive-Provenance lane in the fixed DRA 56-task matrix.

Tasks are the parallelization unit.  Within one task, reports are scored
sequentially so later reports can reuse the first report's report-blind TEC
compiler calls by exact request hash.  Failed evaluator attempts are retried
with all valid prior judge calls as caches; evaluator failure is never
converted into a task score of zero.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def score_payload(score_path: Path) -> dict[str, Any]:
    score = load_json(score_path)
    return {
        "score_path": str(score_path),
        "provenance": float(score["provenance"]["score"]),
        "fact": float(score["fact"]["score"]),
        "evidence": float(score["evidence"]["score"]),
        "completeness": float(score["completeness"]["score"]),
        "rubric": float(score["rubric"]["score"]),
        "quality": float(score["quality"]),
        "truth": float(score["truth_linear_diagnostic"]),
        "formal_eligible": bool(score.get("formal_eligible", False)),
    }


def cache_stage_dirs(attempt_dirs: list[Path]) -> list[Path]:
    roots: list[Path] = []
    for attempt in attempt_dirs:
        judge_root = attempt / "judge_calls"
        if not judge_root.is_dir():
            continue
        roots.extend(
            path
            for path in sorted(judge_root.iterdir())
            if path.is_dir()
        )
    return roots


def command_for_lane(
    lane: dict[str, Any],
    output_dir: Path,
    registry: Path,
    model: str,
    cache_dirs: list[Path],
    fact_search_base_url: str,
) -> list[str]:
    prepared = Path(str(lane["prepared_dir"])) / "scorer-inputs"
    assets = Path(str(lane["asset_dir"]))
    command = [
        sys.executable,
        str(ROOT / "scripts/run_four_axis_pipeline.py"),
        "--task",
        str(lane["task_path"]),
        "--report",
        str(prepared / "report.normalized.md"),
        "--trace",
        str(prepared / "trace.json"),
        "--citation-map",
        str(prepared / "citation-map.json"),
        "--task-world-model",
        str(assets / "task-world-model.json"),
        "--research-test-suite",
        str(assets / "research-test-suite.json"),
        "--graph-dir",
        str(assets / "graph"),
        "--url-registry",
        str(registry),
        "--output-dir",
        str(output_dir),
        "--model",
        model,
        "--claim-proposal-model",
        model,
        "--nli-model",
        model,
        "--structural-model",
        model,
        "--fact-model",
        model,
        "--evidence-model",
        model,
        "--fact-search-base-url",
        fact_search_base_url,
    ]
    for cache_dir in cache_dirs:
        command.extend(["--judge-cache-dir", str(cache_dir)])
    return command


def score_lane(
    lane: dict[str, Any],
    *,
    scores_root: Path,
    registry: Path,
    model: str,
    max_attempts: int,
    shared_cache_dirs: list[Path],
    fact_search_base_url: str,
) -> tuple[dict[str, Any], list[Path]]:
    lane_root = scores_root / lane["harness"] / lane["task_id"]
    prior_attempts = sorted(
        path
        for path in lane_root.glob("attempt-*")
        if path.is_dir()
    )
    for attempt in prior_attempts:
        score_path = attempt / "score.json"
        if score_path.exists():
            return {
                **lane,
                "scoring_status": "scored",
                **score_payload(score_path),
            }, prior_attempts

    errors: list[dict[str, Any]] = []
    for attempt_no in range(len(prior_attempts) + 1, max_attempts + 1):
        attempt_dir = lane_root / f"attempt-{attempt_no:03d}"
        attempt_dir.mkdir(parents=True, exist_ok=False)
        caches = [
            *shared_cache_dirs,
            *cache_stage_dirs(prior_attempts),
        ]
        command = command_for_lane(
            lane,
            attempt_dir,
            registry,
            model,
            caches,
            fact_search_base_url,
        )
        env = dict(os.environ)
        env.update(
            {
                "PYTHONPATH": str(ROOT),
                "JUDGE_PROVIDER": "openai",
                "JUDGE_MODEL": model,
                "JUDGE_MODEL_HEAVY": model,
                "JUDGE_THINKING": "0",
                "JUDGE_TIMEOUT_SECONDS": "300",
                "JUDGE_TIMEOUT_S": "300",
            }
        )
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        (attempt_dir / "driver.stdout.log").write_text(
            completed.stdout, encoding="utf-8"
        )
        (attempt_dir / "driver.stderr.log").write_text(
            completed.stderr, encoding="utf-8"
        )
        prior_attempts.append(attempt_dir)
        score_path = attempt_dir / "score.json"
        if completed.returncode == 0 and score_path.exists():
            return {
                **lane,
                "scoring_status": "scored",
                "attempt_count": attempt_no,
                **score_payload(score_path),
            }, prior_attempts
        errors.append(
            {
                "attempt": attempt_no,
                "returncode": completed.returncode,
                "stderr_tail": completed.stderr[-2000:],
            }
        )
    return {
        **lane,
        "scoring_status": "evaluator_failure",
        "attempt_count": len(prior_attempts),
        "errors": errors,
    }, prior_attempts


def score_task_group(
    rows: list[dict[str, Any]],
    *,
    scores_root: Path,
    registry: Path,
    model: str,
    max_attempts: int,
    fact_search_base_url: str,
) -> list[dict[str, Any]]:
    rows = sorted(
        rows,
        key=lambda row: (
            Path(str(row["report"])).stat().st_size,
            row["harness"],
        ),
    )
    completed: list[dict[str, Any]] = []
    compiler_caches: list[Path] = []
    for lane in rows:
        scored, attempts = score_lane(
            lane,
            scores_root=scores_root,
            registry=registry,
            model=model,
            max_attempts=max_attempts,
            shared_cache_dirs=compiler_caches,
            fact_search_base_url=fact_search_base_url,
        )
        completed.append(scored)
        if not compiler_caches:
            for attempt in attempts:
                compiler = attempt / "judge_calls" / "compiler"
                if compiler.is_dir():
                    compiler_caches = [compiler]
                    break
    return completed


def aggregate(
    all_lanes: list[dict[str, Any]],
    scored_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    scored_by_key = {
        (row["task_id"], row["harness"]): row for row in scored_rows
    }
    final_rows: list[dict[str, Any]] = []
    for lane in all_lanes:
        key = (lane["task_id"], lane["harness"])
        if key in scored_by_key:
            final_rows.append(scored_by_key[key])
            continue
        if lane["lane_status"] in {
            "report_generation_failure",
            "deterministic_zero",
        }:
            final_rows.append(
                {
                    **lane,
                    "scoring_status": "fixed_zero",
                    "truth": 0.0,
                }
            )
            continue
        final_rows.append({**lane, "scoring_status": "not_scored"})

    harnesses = sorted({row["harness"] for row in final_rows})
    leaderboard: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for harness in harnesses:
        rows = [row for row in final_rows if row["harness"] == harness]
        invalid = [
            row
            for row in rows
            if row["scoring_status"] not in {"fixed_zero", "scored"}
        ]
        if len(rows) != 56:
            invalid.append(
                {
                    "harness": harness,
                    "reason": f"expected 56 lanes, found {len(rows)}",
                }
            )
        if invalid:
            blockers.extend(invalid)
            truth = None
        else:
            truth = sum(float(row["truth"]) for row in rows) / 56.0
        leaderboard.append(
            {
                "harness": harness,
                "truth": truth,
                "scored_nonzero_candidate_lanes": sum(
                    row["scoring_status"] == "scored" for row in rows
                ),
                "fixed_zero_lanes": sum(
                    row["scoring_status"] == "fixed_zero" for row in rows
                ),
                "report_generation_failures": sum(
                    row["lane_status"] == "report_generation_failure"
                    for row in rows
                ),
                "evaluator_failures": len(invalid),
            }
        )
    leaderboard.sort(
        key=lambda row: (
            row["truth"] is not None,
            row["truth"] if row["truth"] is not None else -1.0,
        ),
        reverse=True,
    )
    for rank, row in enumerate(
        [row for row in leaderboard if row["truth"] is not None],
        1,
    ):
        row["rank"] = rank
    return {
        "schema": "dra_truth56_diagnostic_leaderboard_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "formula": "Truth=P*(Fact+Evidence+Completeness+Rubric)/4",
        "task_denominator": 56,
        "formal_eligible": False,
        "complete": not blockers,
        "leaderboard": leaderboard,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "lanes": final_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane-manifest", required=True, type=Path)
    parser.add_argument("--url-registry", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument(
        "--fact-search-base-url",
        default="http://localhost:8081",
    )
    args = parser.parse_args()

    lanes = load_jsonl(args.lane_manifest)
    ready = [
        row
        for row in lanes
        if row["lane_status"] == "ready_for_semantic_scoring"
    ]
    by_task: dict[str, list[dict[str, Any]]] = {}
    for row in ready:
        by_task.setdefault(str(row["task_id"]), []).append(row)

    scores_root = args.output_dir / "scores"
    scored: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                score_task_group,
                rows,
                scores_root=scores_root,
                registry=args.url_registry,
                model=args.model,
                max_attempts=args.max_attempts,
                fact_search_base_url=args.fact_search_base_url,
            ): task_id
            for task_id, rows in sorted(by_task.items())
        }
        for future in as_completed(futures):
            task_rows = future.result()
            scored.extend(task_rows)
            progress = {
                "completed_task_groups": len(
                    {row["task_id"] for row in scored}
                ),
                "total_task_groups": len(by_task),
                "completed_semantic_lanes": len(scored),
                "total_semantic_lanes": len(ready),
                "evaluator_failures": sum(
                    row["scoring_status"] == "evaluator_failure"
                    for row in scored
                ),
            }
            write_json(args.output_dir / "progress.json", progress)

    result = aggregate(lanes, scored)
    write_json(args.output_dir / "leaderboard.json", result)
    (args.output_dir / "lane-results.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in result["lanes"]
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "complete": result["complete"],
                "blocker_count": result["blocker_count"],
                "leaderboard": result["leaderboard"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
