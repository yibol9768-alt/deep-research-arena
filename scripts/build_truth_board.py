#!/usr/bin/env python3
"""Five-axis truth board builder (EXECUTION_PLAN P5; #16 code side).

Consumes the v2 decidable stack end to end:
  reports dir (<agent>/<task_id>.md) x answer keys x URL registry x page cache
  -> per-report five-axis scores -> per-agent aggregate -> board JSON.

Ranking = macro-mean truth (decidable axes only). Presentation (the LLM
panel, when a results file is supplied) is a SEPARATE column: it may only
order agents whose truth scores tie within --tie-eps, and never enters the
truth number (M-C1). Per M-M1 the board carries macro, micro and
min_report_truth for every agent.

Usage:
  python3 scripts/build_truth_board.py --reports-dir <dir> \
      [--keys-dir data/golden/answer_keys] [--cache sandbox_cache.json] \
      [--panel panel_results.json] [--gamma 1.5] [--out board.json]

The live v1 leaderboard pipeline (build_real_leaderboard.py) stays untouched
until the re-judge lands; this builder is the v2 replacement, validated on
the sample tasks first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.answer_key import AnswerKey                     # noqa: E402
from src.eval import decidable_scorer as ds                   # noqa: E402
from src.eval.closed_world_eval import evaluate, load_registry  # noqa: E402

AXES = ("grounding_reach", "grounding_proof_of_fetch",
        "correctness_fact_support", "completeness", "spec")


def _load_lane_info(manifest_path: Path) -> dict[str, dict]:
    """Derive per-agent lane-failure accounting from an extraction manifest.

    A lane fails when the runs that never produced a real report (stub reports
    plus runs missing versus the fullest lane) exceed half of that lane's total
    runs. ``n_runs_total`` is the agent's own attempted-run count; ``n_missing``
    counts tasks it never even recorded, measured against the most complete
    lane in the manifest. Neither number touches the truth score: it only tells
    the board that a 0.0 (or an absent agent) is a broken pipe, not a real zero.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    agents = manifest.get("agents", {})
    expected = max((a.get("n_records", 0) for a in agents.values()), default=0)
    info: dict[str, dict] = {}
    for agent, a in agents.items():
        n_records = a.get("n_records", 0)
        n_stub = sum(a.get("n_stubs_by_class", {}).values())
        n_missing = max(0, expected - n_records)
        lane_failed = (n_stub + n_missing) > (n_records / 2) if n_records else True
        info[agent] = {
            "n_runs_total": n_records,
            "n_stub_reports": n_stub,
            "n_missing_runs": n_missing,
            "lane_failed": lane_failed,
        }
    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports-dir", required=True,
                    help="layout <agent>/<task_id>.md")
    ap.add_argument("--keys-dir", default="data/golden/answer_keys")
    ap.add_argument("--cache", default=None, help="sandbox page cache json")
    ap.add_argument("--panel", default=None,
                    help="presentation panel results json: {agent: score}")
    ap.add_argument("--manifest", default=None,
                    help="extraction_manifest.json from extract_unified_reports.py; "
                         "surfaces lane failures instead of letting a broken "
                         "lane silently vanish or read as a real 0.0")
    ap.add_argument("--gamma", type=float, default=ds.GAMMA_DEFAULT)
    ap.add_argument("--tie-eps", type=float, default=0.005)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    keys_dir = ROOT / args.keys_dir
    keys = {p.stem: AnswerKey.load(p) for p in sorted(keys_dir.glob("*.json"))}
    if not keys:
        print(f"no answer keys under {keys_dir}")
        return 2
    cache = json.loads(Path(args.cache).read_text()) if args.cache else {}
    panel = json.loads(Path(args.panel).read_text()) if args.panel else {}
    registry = load_registry()
    # build_page_stats(cache) is a document-frequency pass over the WHOLE
    # cache; it is the same for every report in this run, so compute it once
    # here rather than paying its cost inside score_report() per report.
    page_stats = ds.build_page_stats(cache)

    rows = []
    rdir = Path(args.reports_dir)
    for agent_dir in sorted(p for p in rdir.iterdir() if p.is_dir()):
        per_task = {}
        for tid, ak in keys.items():
            rp = agent_dir / f"{tid}.md"
            if not rp.exists():
                continue
            md = rp.read_text(errors="replace")
            per_task[tid] = evaluate(md, ak, cache, registry=registry,
                                     gamma=args.gamma, page_stats=page_stats)
        if not per_task:
            continue
        truths = [d["truth"] for d in per_task.values()]
        n = len(truths)
        macro = sum(truths) / n
        # micro: pool numerators/denominators where meaningful (reach), else
        # report the mean over tasks weighted by citation volume
        dens = [d["reach_detail"].get("den", 0) for d in per_task.values()]
        micro = (sum(t * w for t, w in zip(truths, dens)) / sum(dens)
                 if sum(dens) else macro)
        axes_mean = {a: round(sum(d["axes"][a] for d in per_task.values()) / n, 4)
                     for a in AXES}
        rows.append({
            "agent": agent_dir.name,
            "n_tasks": n,
            "truth_macro": round(macro, 4),
            "truth_micro": round(micro, 4),
            "min_report_truth": round(min(truths), 4),
            "axes_mean": axes_mean,
            # spec is OUT of truth (FORMULA_LOCK K6): surfaced as a separate
            # compliance column, never multiplied in. Kept in axes_mean too.
            "compliance": axes_mean.get("spec", 0.0),
            "presentation": panel.get(agent_dir.name),
            "per_task": {t: {"truth": d["truth"], "axes": d["axes"]}
                         for t, d in per_task.items()},
        })

    # rank: truth first; presentation may only break ties within tie_eps
    rows.sort(key=lambda r: -r["truth_macro"])
    i = 0
    while i < len(rows):
        j = i
        while (j + 1 < len(rows) and
               rows[i]["truth_macro"] - rows[j + 1]["truth_macro"] <= args.tie_eps):
            j += 1
        if j > i:
            rows[i:j + 1] = sorted(
                rows[i:j + 1],
                key=lambda r: -(r["presentation"] if isinstance(
                    r.get("presentation"), (int, float)) else float("-inf")))
        i = j + 1
    for k, r in enumerate(rows, 1):
        r["rank"] = k

    lane_info = _load_lane_info(Path(args.manifest)) if args.manifest else {}
    if lane_info:
        scored_agents = {r["agent"] for r in rows}
        for r in rows:
            li = lane_info.get(r["agent"])
            if li:
                r.update(li)
        # A lane whose every run was a stub (or missing) produces no report file
        # for the board to score, so it would silently disappear. Keep it in,
        # flagged, so the failure is visible rather than absent. Placeholders are
        # ranked after every scored agent and carry no truth signal.
        next_rank = len(rows) + 1
        for agent in sorted(lane_info):
            li = lane_info[agent]
            if agent in scored_agents or not li["lane_failed"]:
                continue
            placeholder = {
                "agent": agent,
                "n_tasks": 0,
                "truth_macro": 0.0,
                "truth_micro": 0.0,
                "min_report_truth": 0.0,
                "axes_mean": {a: 0.0 for a in AXES},
                "presentation": panel.get(agent),
                "per_task": {},
                "rank": next_rank,
            }
            placeholder.update(li)
            rows.append(placeholder)
            next_rank += 1

    board = {
        "board": "truth_v2",
        "composition": ("truth = reach^gamma * (0.39 fact + 0.28 pof + "
                        "0.33 completeness), floor-if-active eps=0.05 "
                        "(FORMULA_LOCK K6); spec/compliance and presentation "
                        "are separate columns, tie-break only, never in truth"),
        "gamma": args.gamma,
        "n_answer_keys": len(keys),
        "rows": [{k: v for k, v in r.items() if k != "per_task"} for r in rows],
        "per_task": {r["agent"]: r["per_task"] for r in rows},
    }
    out = json.dumps(board, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(out + "\n")
        print(f"wrote {args.out}")
    for r in rows:
        pres = r["presentation"]
        suffix = ""
        if r.get("lane_failed"):
            suffix = (f"  [LANE FAILED {r.get('n_stub_reports', 0)}/"
                      f"{r.get('n_runs_total', 0)} runs]")
        print(f"#{r['rank']} {r['agent']:20s} truth={r['truth_macro']:.4f} "
              f"min={r['min_report_truth']:.4f} n={r['n_tasks']} "
              f"pres={pres if pres is not None else '-'}{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
