#!/usr/bin/env python3
"""Build an explicitly selected DRA v3 score board."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.board_v3 import (  # noqa: E402
    aggregate_proof_step_scores,
    aggregate_scores,
)
from src.eval.protocol_manifest_v3 import load_v3_protocol_manifest  # noqa: E402
from src.eval.protocol_v3 import (  # noqa: E402
    LEGACY_SCORING_SEMANTICS,
    SCORING_SEMANTICS,
)


def _read(path: Path) -> list[dict]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("scores"), list):
        return value["scores"]
    if isinstance(value, dict):
        return [value]
    raise ValueError(f"unsupported score document in {path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scores", nargs="+", type=Path,
                    help="per-run JSON/JSONL score files")
    ap.add_argument(
        "--scoring-semantics",
        choices=(LEGACY_SCORING_SEMANTICS, SCORING_SEMANTICS),
        default=LEGACY_SCORING_SEMANTICS,
        help=(
            "board protocol; default preserves verified_slots_v1, new formal "
            "boards must explicitly select proof_steps_v1"
        ),
    )
    ap.add_argument("--protocol-manifest", type=Path,
                    help="sealed full v3 protocol manifest; required for a formal board")
    ap.add_argument("--expected-agent", action="append", default=[],
                    help="formal agent id (repeat; required unless diagnostic)")
    ap.add_argument("--expected-task", action="append", default=[],
                    help="optional task id assertion; must equal manifest task_ids")
    ap.add_argument("--expected-replicate", action="append", default=[], type=int,
                    help="formal positive replicate id (repeat; required unless diagnostic)")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="diagnostic only: report missing/withheld cells instead of refusing")
    ap.add_argument("--bootstrap-samples", type=int, default=2000)
    ap.add_argument("--bootstrap-seed", type=int, default=1729)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    formal = not args.allow_incomplete
    if formal and args.protocol_manifest is None:
        ap.error("formal board requires --protocol-manifest")
    if formal and not args.expected_agent:
        ap.error("formal board requires at least one --expected-agent")
    if formal and not args.expected_replicate:
        ap.error("formal board requires at least one --expected-replicate")
    protocol_manifest = (
        load_v3_protocol_manifest(args.protocol_manifest)
        if args.protocol_manifest is not None
        else None
    )
    records = [row for path in args.scores for row in _read(path)]
    aggregator = (
        aggregate_proof_step_scores
        if args.scoring_semantics == SCORING_SEMANTICS
        else aggregate_scores
    )
    board = aggregator(
        records,
        protocol_manifest=protocol_manifest,
        expected_agents=args.expected_agent or None,
        expected_tasks=args.expected_task or None,
        expected_replicates=args.expected_replicate or None,
        require_complete=formal,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
