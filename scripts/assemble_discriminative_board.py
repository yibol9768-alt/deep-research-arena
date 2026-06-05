#!/usr/bin/env python3
"""Assemble the differentiating leaderboard from a re-scored signal matrix.

Pipeline (the user's directive: the board must actually separate agents, with
real signal, not manufactured spread):
  1. coverage filter: only rank agents scored on >= --min-tasks comparable tasks;
  2. GATE (unchanged): eligible iff mean(0.5*curated_recall + 0.5*quote_match)
     >= --floor; gated agents are shown as excluded, not ranked;
  3. QUALITY composite (deterministic, judge-independent, validated by the
     discrimination workflow): default REACH-PRES =
     0.75*reachability + 0.25*presentation_lenadj, where presentation is
     length-residualized (OLS vs word_count over all scored rows) so verbosity
     cannot raise the score. Weights/signals overridable once the discrimination
     re-run on the fresh richer signal set picks them.
  4. bootstrap CIs on the per-agent composite (task-resample) for separability.
  5. emit data/results/deep_v3/leaderboard_deep_v3.json (the frontend shape).

Run: python3 scripts/assemble_discriminative_board.py \
       --matrix data/results/real/signal_matrix_fresh.json \
       --manifest data/golden/deep_clean/_manifest.json
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "results" / "deep_v3" / "leaderboard_deep_v3.json"

# Deterministic task-resample bootstrap without Random (Date/random are fine in
# a plain script, but keep it reproducible): use a fixed LCG seeded per agent.
def _boot_ci(per_task_vals: list[float], n_boot: int = 2000, seed: int = 12345):
    if not per_task_vals:
        return (0.0, 0.0, 0.0)
    k = len(per_task_vals)
    s = seed & 0xFFFFFFFF
    means = []
    for _ in range(n_boot):
        acc = 0.0
        for _ in range(k):
            s = (1103515245 * s + 12345) & 0x7FFFFFFF
            acc += per_task_vals[s % k]
        means.append(acc / k)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot)]
    mid = sum(per_task_vals) / k
    return (mid, lo, hi)


def _ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    if n < 2:
        return (sum(ys) / n if n else 0.0, 0.0)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx > 0 else 0.0
    a = my - b * mx
    return (a, b)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matrix", required=True, help="fresh signal matrix json {rows:[...]}")
    ap.add_argument("--manifest", default=str(ROOT / "data/golden/deep_clean/_manifest.json"))
    ap.add_argument("--floor", type=float, default=0.30)
    ap.add_argument("--min-tasks", type=int, default=15)
    ap.add_argument("--w-reach", type=float, default=0.75)
    ap.add_argument("--w-pres", type=float, default=0.25)
    ap.add_argument("--tasks", default=None,
                    help="restrict scoring basis to these task ids (comma-sep or @file); "
                         "use the comparable common-task set for a paired, fair board")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    rows = json.loads(Path(args.matrix).read_text())["rows"]
    manifest = (json.loads(Path(args.manifest).read_text()).get("tasks") or {})

    task_filter: set[str] | None = None
    if args.tasks:
        if args.tasks.startswith("@"):
            task_filter = {t.strip() for t in Path(args.tasks[1:]).read_text().split() if t.strip()}
        else:
            task_filter = {t.strip() for t in args.tasks.split(",") if t.strip()}

    # keep non-quarantine, "scored" rows (a real score JSON, not a missing-file zero)
    def scored(r):
        return any((r.get(k) or 0) > 0 for k in
                   ("quote_match", "reachability", "citation_alignment", "presentation"))
    rows = [r for r in rows
            if (manifest.get(r["task"]) or {}).get("verdict") != "quarantine" and scored(r)
            and (task_filter is None or r["task"] in task_filter)]

    # global length residualization for presentation (so verbosity can't lift it)
    wc = [float(r.get("word_count") or 0) for r in rows]
    pres = [float(r.get("presentation") or 0) for r in rows]
    a, b = _ols(wc, pres)
    pres_mean = sum(pres) / len(pres) if pres else 0.0
    for r in rows:
        resid = float(r.get("presentation") or 0) - (a + b * float(r.get("word_count") or 0))
        r["_pres_lenadj"] = pres_mean + resid
        r["_gate"] = 0.5 * float(r.get("curated_recall") or 0) + 0.5 * float(r.get("quote_match") or 0)
        r["_quality"] = args.w_reach * float(r.get("reachability") or 0) + args.w_pres * r["_pres_lenadj"]

    by_agent: dict[str, list] = defaultdict(list)
    for r in rows:
        by_agent[r["agent"]].append(r)

    elo_v3_ci: dict[str, dict] = {}
    per_agent_profile: dict[str, dict] = {}
    excluded: list[dict] = []

    for agent, rs in by_agent.items():
        n = len(rs)
        gate = sum(x["_gate"] for x in rs) / n
        reach = sum(float(x.get("reachability") or 0) for x in rs) / n
        prof = {
            "coverage_pct": round(gate * 100, 1),
            "grounding": round(gate, 4),
            "reachability_pct": round(reach * 100, 1),
            "n_tasks": n,
            "synthetic_placeholder": False,
        }
        per_agent_profile[agent] = prof
        if n < args.min_tasks:
            excluded.append({"agent": agent, "reason": f"insufficient coverage (scored {n} < {args.min_tasks} tasks)", "grounding": round(gate, 4)})
            continue
        if gate < args.floor:
            excluded.append({"agent": agent, "reason": f"grounding {gate:.3f} below truth-gate floor {args.floor}", "grounding": round(gate, 4)})
            continue
        q_vals = [x["_quality"] for x in rs]
        mid, lo, hi = _boot_ci(q_vals, seed=abs(hash(agent)) % 2_000_000_000 + 1)
        score = round(mid * 100, 1)  # scale to a readable 0-100 board number
        elo_v3_ci[agent] = {
            "elo": score,
            "elo_lo": round(lo * 100, 1),
            "elo_hi": round(hi * 100, 1),
            "elo_half_width": round((hi - lo) * 50, 1),
            "n_battles": n,  # n comparable tasks backing the number
            "wins": 0, "losses": 0, "draws": 0,
            "grounding": round(gate, 4),
        }

    out = {
        "_schema_version": "v3-discriminative-composite-2026-06-04",
        "_dry_run": False,
        "synthetic_placeholder": False,
        "source": "real",
        "weights_v3": {"grounding_gate_floor": args.floor, "w_reachability": args.w_reach, "w_presentation_lenadj": args.w_pres},
        "composite_formula": (
            "QUALITY (deterministic, judge-independent) = "
            f"{args.w_reach}*reachability + {args.w_pres}*presentation_lenadj, where "
            "presentation is length-residualized against word_count so verbosity "
            "cannot raise it. Validated by a discrimination workflow (reachability "
            "is the strongest length-independent agent discriminator). GATE "
            "(unchanged): rank only agents that clear mean(0.5*curated_recall + "
            "0.5*quote_match) >= floor AND have enough comparable scored tasks; "
            "fabricated/ungrounded reports are excluded, not ranked."
        ),
        "elo_v3_ci": elo_v3_ci,
        "per_agent_profile": per_agent_profile,
        "excluded_agents": excluded,
        "n_runs": sum(len(rs) for rs in by_agent.values()),
        "source_file": Path(args.matrix).name,
    }
    outp = Path(args.out)
    if outp.exists():
        bak = outp.with_suffix(".json.pre-discriminative")
        if not bak.exists():
            bak.write_text(outp.read_text(encoding="utf-8"), encoding="utf-8")
    outp.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {outp}")
    ranked = sorted(elo_v3_ci.items(), key=lambda kv: -kv[1]["elo"])
    print("ranked:", [(a, e["elo"], f"[{e['elo_lo']},{e['elo_hi']}]") for a, e in ranked])
    print("excluded:", [(e["agent"], round(e["grounding"] or 0, 3)) for e in excluded])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
