#!/usr/bin/env python3
"""Convert a real build_real_leaderboard.py output into the frontend V3 file.

The site (frontend/lib/data/load-leaderboard.ts) reads
data/results/deep_v3/leaderboard_deep_v3.json with shape:
  { _dry_run, weights_v3, composite_formula, elo_v3_ci{agent: {elo, elo_lo,
    elo_hi, elo_half_width, n_battles, wins, losses, draws}}, per_agent_profile,
    excluded_agents, human_alignment }

Truth-gate policy: only agents that clear the grounding floor get a rank in
elo_v3_ci. Agents below the floor, or with no real reports, go to
excluded_agents with a reason. Nothing synthetic is emitted.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "results" / "deep_v3" / "leaderboard_deep_v3.json"
# Agents that exist only as synthetic placeholders (no real reports on disk).
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
    ap.add_argument("--in", dest="inp", required=True, help="leaderboard_real*.json")
    ap.add_argument("--floor", type=float, default=0.30, help="grounding gate floor")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    d = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    agents = d.get("agents", {})
    battle_log = d.get("battle_log", [])
    wld = _wld(battle_log)

    elo_v3_ci: dict[str, dict] = {}
    per_agent_profile: dict[str, dict] = {}
    excluded: list[dict] = []

    for name, a in agents.items():
        grounding = float(a.get("grounding") or 0.0)
        gated = bool(a.get("gated")) or grounding < args.floor
        w = wld.get(name, {"wins": 0, "losses": 0, "draws": 0})
        per_agent_profile[name] = {
            "coverage_pct": round(grounding * 100, 1),
            "reachability_pct": None,
            "synthetic_placeholder": False,
            "grounding": round(grounding, 4),
        }
        if gated:
            excluded.append({
                "agent": name,
                "reason": f"grounding {grounding:.3f} below truth-gate floor {args.floor}",
                "grounding": round(grounding, 4),
            })
            continue
        ci = a.get("quality_ci", {})
        elo = float(a.get("quality_elo") or 0.0)
        elo_v3_ci[name] = {
            "elo": round(elo, 1),
            "elo_lo": round(float(ci.get("lo", elo)), 1),
            "elo_hi": round(float(ci.get("hi", elo)), 1),
            "elo_half_width": round(float(ci.get("half_width", 0.0)), 1),
            "n_battles": int(a.get("n_battles", 0)),
            "wins": w["wins"], "losses": w["losses"], "draws": w["draws"],
            "grounding": round(grounding, 4),
        }

    for name, reason in KNOWN_NO_DATA.items():
        if name not in agents:
            excluded.append({"agent": name, "reason": reason, "grounding": None})

    out = {
        "_schema_version": "v3-real-grounding-gated-2026-06-02",
        "_dry_run": False,
        "synthetic_placeholder": False,
        "source": "real",
        "weights_v3": {"grounding_gate_floor": args.floor},
        "composite_formula": (
            "Two orthogonal numbers: GROUNDING = F1(citation precision with "
            "proof-of-fetch, must-cite recall); QUALITY = length-controlled "
            "pairwise win-rate vs peers, Bradley-Terry Elo with cross-family "
            "DeepSeek judge and position-swap. GATE: a report must clear the "
            "grounding floor to be ranked; fluent-but-ungrounded and "
            "fabricated-citation reports are excluded, not ranked."
        ),
        "elo_v3_ci": elo_v3_ci,
        "per_agent_profile": per_agent_profile,
        "excluded_agents": excluded,
        "human_alignment": {
            "note": (
                "Scoring redesigned (2026-06-02) to match the field consensus "
                "(DeepResearch Bench RACE+FACT, Arena-Hard, ALCE): separate "
                "grounding from quality, never reward citation volume, "
                "length-controlled pairwise judging. Full human-kappa validation "
                "pending a labeled preference set."
            ),
        },
        "n_runs": len(battle_log),
        "source_file": Path(args.inp).name,
    }
    outp = Path(args.out)
    if outp.exists():
        bak = outp.with_suffix(".json.synthetic-backup")
        if not bak.exists():
            bak.write_text(outp.read_text(encoding="utf-8"), encoding="utf-8")
    outp.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {outp}")
    print(f"ranked (ungated): {list(elo_v3_ci.keys())}")
    print(f"excluded: {[e['agent'] for e in excluded]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
