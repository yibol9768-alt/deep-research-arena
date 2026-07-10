#!/usr/bin/env python3
"""Generate a governed full-run queue over the complete registered task set."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_run_set import (
    IntegrityError,
    assert_lane_registry_parity,
    is_entry_resumable,
)


def _declared_agents() -> list[str]:
    # Planning against only one side of the registry creates a false-green
    # queue: a protocol lane with no runner never executes, while an
    # auto-discovered runner with no protocol can be scheduled without an
    # auditable contract. Both directions must match before task selection.
    return assert_lane_registry_parity()


def _score_is_resumable(
    score: Path,
    meta: Path,
    backbone: str,
    *,
    report: Path | None = None,
    run_set_id: str | None = None,
    replicate: int | None = None,
    manifest: Path | None = None,
) -> bool:
    """A legacy score or a partially bound entry is never a cache hit."""
    if report is None or run_set_id is None or replicate is None or manifest is None:
        return False
    return is_entry_resumable(
        score,
        meta,
        report,
        manifest,
        run_set_id=run_set_id,
        backbone=backbone,
        replicate=replicate,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", nargs="+", default=None,
                    help="agents to schedule; default is every protocol-declared lane")
    ap.add_argument("--task-range", default="all",
                    help="inclusive N-M range, or 'all' (default: all 100 keys)")
    ap.add_argument("--run-dir", type=Path,
                    help="optional existing run-set/backbone directory to resume")
    ap.add_argument("--run-set-id",
                    help="required with --run-dir; must equal --run-dir's parent name")
    ap.add_argument("--manifest", type=Path,
                    help="manifest for resume; defaults to RUN_DIR/run_manifest.json")
    ap.add_argument("--backbone", required=True)
    ap.add_argument("--replicates", type=int, default=1)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.replicates < 1:
        ap.error("--replicates must be >= 1")
    try:
        declared_agents = _declared_agents()
    except IntegrityError as exc:
        ap.error(str(exc))
    agents = args.agents or declared_agents
    if not agents:
        ap.error("lane_protocol.yaml declares no agents")
    unknown_agents = sorted(set(agents) - set(declared_agents))
    if unknown_agents:
        ap.error(
            "requested agents are absent from the exact RUNNERS/lane_protocol set: "
            + ", ".join(unknown_agents)
        )

    manifest = args.manifest
    if args.run_dir:
        if not args.run_set_id:
            ap.error("--run-dir requires --run-set-id")
        if args.run_dir.name != args.backbone:
            ap.error("--run-dir basename must exactly equal --backbone")
        if args.run_dir.parent.name != args.run_set_id:
            ap.error("--run-dir parent must exactly equal --run-set-id")
        manifest = manifest or args.run_dir / "run_manifest.json"
        if not manifest.is_file():
            ap.error(f"resume manifest not found: {manifest}")
    elif args.run_set_id or manifest:
        ap.error("--run-set-id/--manifest are only valid with --run-dir")

    task_dir = ROOT / "data/tasks/deep_research/cross_site_deep"
    all_tasks = sorted(t.stem for t in task_dir.glob("dr_cross_deep_*.json"))
    if args.task_range == "all":
        selected = all_tasks
    else:
        lo, hi = (int(x) for x in args.task_range.split("-", 1))
        selected = [t for t in all_tasks if lo <= int(t.rsplit("_", 1)[1]) <= hi]
    if not selected:
        ap.error("task selection is empty")

    queue = []
    for agent in agents:
        pending = False
        for task in selected:
            for rep in range(1, args.replicates + 1):
                if args.run_dir:
                    suffix = f"rep{rep}"
                    score = args.run_dir / "scores" / f"{agent}__{task}_{suffix}.score.json"
                    meta = args.run_dir / "raw" / f"{agent}__{task}_{suffix}.meta.json"
                    report = args.run_dir / "raw" / f"{agent}__{task}_{suffix}.md"
                    if _score_is_resumable(
                        score,
                        meta,
                        args.backbone,
                        report=report,
                        run_set_id=args.run_set_id,
                        replicate=rep,
                        manifest=manifest,
                    ):
                        continue
                pending = True
                break
            if pending:
                queue.append((agent, task))
                pending = False

    out = sys.stdout if args.out is None else open(args.out, "w", encoding="utf-8")
    for agent, task in queue:
        print(f"{agent}\t{task}", file=out)
    if args.out:
        out.close()
        print(f"wrote {len(queue)} pairs to {args.out}", file=sys.stderr)
    else:
        print(f"# {len(queue)} pairs", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
