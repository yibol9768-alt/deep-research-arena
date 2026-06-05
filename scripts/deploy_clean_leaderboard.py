#!/usr/bin/env python3
"""Assemble the deployable V3 leaderboard from the cleaned-benchmark re-base.

The clean re-base runs in two parts to keep the judge phase cheap:
  - a full dry-run (no judge) gives GROUNDING for every agent (the truth-gate),
  - a restricted build judges QUALITY only among the well-covered passers.

This merges them into frontend/data/results/deep_v3/leaderboard_deep_v3.json
(the shape frontend/lib/data/load-leaderboard.ts reads): the well-covered
passers are ranked in ``elo_v3_ci``; EVERY other agent appears in
``excluded_agents`` with an honest reason (below the grounding floor, or grounded
but with too few tasks to rank). Nothing synthetic is emitted.

Run (after pulling both JSONs from the box):
  python3 scripts/deploy_clean_leaderboard.py \
    --quality data/results/real/leaderboard_real_clean.json \
    --grounding data/results/real/leaderboard_real_full_grounding.json \
    --floor 0.30 --min-tasks 10
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "results" / "deep_v3" / "leaderboard_deep_v3.json"
KNOWN_NO_DATA = {"opencode": "no real reports on disk (was a synthetic placeholder)"}


def _wld(battle_log: list[dict]) -> dict[str, dict[str, int]]:
    rec: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0, "draws": 0})
    for b in battle_log:
        a, c, w = b.get("agent_a"), b.get("agent_b"), b.get("winner")
        if not a or not c:
            continue
        if w in (None, "tie", "TIE"):
            rec[a]["draws"] += 1
            rec[c]["draws"] += 1
        elif w == a:
            rec[a]["wins"] += 1
            rec[c]["losses"] += 1
        elif w == c:
            rec[c]["wins"] += 1
            rec[a]["losses"] += 1
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quality", required=True, help="restricted-agents build (judged)")
    ap.add_argument("--grounding", required=True, help="full dry-run (all-agent grounding)")
    ap.add_argument("--floor", type=float, default=0.30)
    ap.add_argument("--min-tasks", type=int, default=10,
                    help="min valid tasks to be rankable (else grounded-but-thin)")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    q = json.loads(Path(args.quality).read_text(encoding="utf-8"))
    g = json.loads(Path(args.grounding).read_text(encoding="utf-8"))

    qagents = q.get("agents", {})
    battle_log = q.get("battle_log", [])
    wld = _wld(battle_log)
    # All-agent grounding from the dry-run summary.
    grounding_all = g.get("grounding_mean", {})
    # n_tasks per agent (prefer the judged build's count; fall back to grounding run).
    ranked_set = {a for a, r in qagents.items()
                  if not r.get("gated") and (r.get("quality_elo_ranked") is not None
                                             or r.get("quality_elo") is not None)}

    elo_v3_ci: dict[str, dict] = {}
    per_agent_profile: dict[str, dict] = {}
    excluded: list[dict] = []

    # Union of all agents seen anywhere.
    all_agents = set(grounding_all) | set(qagents)
    for name in sorted(all_agents):
        gr = float(grounding_all.get(name, qagents.get(name, {}).get("grounding") or 0.0))
        per_agent_profile[name] = {
            "coverage_pct": round(gr * 100, 1),
            "reachability_pct": None,
            "synthetic_placeholder": False,
            "grounding": round(gr, 4),
        }
        if name in ranked_set:
            row = qagents[name]
            elo = float(row.get("quality_elo_ranked") or row.get("quality_elo") or 0.0)
            ci = row.get("quality_ci_ranked") or row.get("quality_ci") or {}
            w = wld.get(name, {"wins": 0, "losses": 0, "draws": 0})
            elo_v3_ci[name] = {
                "elo": round(elo, 1),
                "elo_lo": round(float(ci.get("lo", elo)), 1),
                "elo_hi": round(float(ci.get("hi", elo)), 1),
                "elo_half_width": round(float(ci.get("half_width", 0.0)), 1),
                "n_battles": int(row.get("n_battles", 0)),
                "wins": w["wins"], "losses": w["losses"], "draws": w["draws"],
                "grounding": round(gr, 4),
            }
        elif gr >= args.floor:
            # Grounded but not ranked: insufficient task coverage.
            excluded.append({
                "agent": name,
                "reason": (f"grounded (g={gr:.3f}) but too few scorable tasks to rank "
                           f"(min {args.min_tasks})"),
                "grounding": round(gr, 4),
            })
        else:
            excluded.append({
                "agent": name,
                "reason": f"grounding {gr:.3f} below truth-gate floor {args.floor}",
                "grounding": round(gr, 4),
            })

    for name, reason in KNOWN_NO_DATA.items():
        if name not in all_agents:
            excluded.append({"agent": name, "reason": reason, "grounding": None})

    out = {
        "_schema_version": "v3-clean-benchmark-grounding-gated-2026-06-04",
        "_dry_run": False,
        "synthetic_placeholder": False,
        "source": "real",
        "weights_v3": {"grounding_gate_floor": args.floor},
        "composite_formula": (
            "Two orthogonal numbers on the cleaned 75-task benchmark "
            "(off-topic keyword-collision cites removed; per-task source "
            "allow-list; 25 mostly-off-topic tasks quarantined). GROUNDING = "
            "0.5*curated_must_cite_recall + 0.5*quote_match. QUALITY = "
            "length-controlled pairwise Bradley-Terry Elo, cross-family "
            "DeepSeek-v4-flash judge, position-swap, multi-sample. GATE: a report "
            "must clear the grounding floor AND have enough scorable tasks to be "
            "ranked; fabricated-citation and fluent-but-ungrounded reports are "
            "excluded, not ranked."
        ),
        "elo_v3_ci": elo_v3_ci,
        "per_agent_profile": per_agent_profile,
        "excluded_agents": excluded,
        "human_alignment": {
            "note": (
                "Cleaned-benchmark re-base (2026-06-04): goldens re-audited for "
                "topic relevance, per-task source allow-list applied. Quality "
                "ranking is judge-invariant across DeepSeek/Qwen/GLM. Full "
                "human-kappa validation pending a labeled preference set "
                "(collection live at /annotate)."
            ),
        },
        "n_runs": len(battle_log),
        "source_file": Path(args.quality).name,
    }
    outp = Path(args.out)
    if outp.exists():
        bak = outp.with_suffix(".json.pre-clean-rebase")
        if not bak.exists():
            bak.write_text(outp.read_text(encoding="utf-8"), encoding="utf-8")
    outp.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {outp}")
    print(f"ranked ({len(elo_v3_ci)}): {list(elo_v3_ci.keys())}")
    print(f"excluded ({len(excluded)}): {[e['agent'] for e in excluded]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
