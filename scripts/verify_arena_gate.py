#!/usr/bin/env python3
"""G-1: verify the Arena-Score grounding gate.

Arena Score is the presentation-leaderboard headline candidate

    arena(agent) = reach ** gamma  *  winrate_vs_avg_opponent

with reach taken from the decidable truth board (axes_mean.grounding_reach)
and winrate from the Bradley-Terry usefulness-jury snapshot. Unlike the truth
score, arena multiplies reach^gamma by a JUDGE quantity (winrate), not by a
decidable quality. The registry worry (finding #4) is that this composition
does NOT inherit the gate theorem: a low-reach fabricator that wins the
presentation battle can out-score an honest high-reach system.

This tool makes that worry falsifiable. It enumerates an adversary family

    reach in a low grid (default 0.05 .. 0.31)  x  winrate = 1.0

(the strongest possible jury outcome at each low reach) and asserts every
adversary corner scores at most as high as EVERY real board system whose reach
clears a floor (default 0.6, i.e. a genuinely well-grounded system). It reports
PASS/FAIL and the minimum safety margin

    min_safe_margin = min(arena over real reach>=floor systems)
                    - max(arena over adversary grid)

A non-negative margin means no modelled fabricator can top an honest system on
arena; a negative margin is a concrete counterexample (the binding real system
and the adversary corner that beats it are both printed).

Model-free and deterministic. Does NOT modify any production formula.

Usage:
  python3 scripts/verify_arena_gate.py \
      --board  truth_board_<bb>.json \
      --bt     bt_<bb>_<date>.json \
      [--gamma 1.5] [--reach-floor 0.6] \
      [--adv-reach-min 0.05] [--adv-reach-max 0.31] [--adv-reach-step 0.01] \
      [--adv-winrate 1.0]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def arena(reach: float, winrate: float, gamma: float) -> float:
    return (max(0.0, float(reach)) ** gamma) * float(winrate)


def _adv_grid(rmin: float, rmax: float, step: float) -> list[float]:
    """Inclusive grid rmin, rmin+step, ..., up to (and including, modulo float
    slack) rmax."""
    if step <= 0:
        raise ValueError("adv-reach-step must be positive")
    grid = []
    x = rmin
    # 1e-9 slack so the intended endpoint is not dropped by binary rounding
    while x <= rmax + 1e-9:
        grid.append(round(x, 10))
        x += step
    return grid


def reach_by_agent(board: dict) -> dict[str, float]:
    out = {}
    for r in board.get("rows", []):
        ax = r.get("axes_mean", {})
        if "grounding_reach" in ax:
            out[r["agent"]] = float(ax["grounding_reach"])
    return out


def winrate_by_agent(bt: dict) -> dict[str, float]:
    return {a: float(v["winrate_vs_avg_opponent"])
            for a, v in bt.get("agents", {}).items()
            if "winrate_vs_avg_opponent" in v}


def verify_arena_gate(reaches: dict[str, float],
                      winrates: dict[str, float],
                      gamma: float = 1.5,
                      reach_floor: float = 0.6,
                      adv_reach_min: float = 0.05,
                      adv_reach_max: float = 0.31,
                      adv_reach_step: float = 0.01,
                      adv_winrate: float = 1.0) -> dict:
    """Return the gate verdict. `reaches` and `winrates` are agent->value maps;
    only agents present in BOTH are real board systems (need both a reach and a
    winrate to have an arena score)."""
    real = []
    for a in sorted(set(reaches) & set(winrates)):
        if reaches[a] >= reach_floor:
            real.append({
                "agent": a,
                "reach": round(reaches[a], 4),
                "winrate": round(winrates[a], 4),
                "arena": arena(reaches[a], winrates[a], gamma),
            })
    grid = _adv_grid(adv_reach_min, adv_reach_max, adv_reach_step)
    adv = [{"reach": r, "winrate": adv_winrate,
            "arena": arena(r, adv_winrate, gamma)} for r in grid]

    result = {
        "gamma": gamma,
        "reach_floor": reach_floor,
        "adv_grid": {"min": adv_reach_min, "max": adv_reach_max,
                     "step": adv_reach_step, "winrate": adv_winrate,
                     "n_points": len(grid)},
        "n_real_systems": len(real),
        "real_systems": sorted(real, key=lambda d: d["arena"]),
    }
    if not real:
        result["status"] = "SKIP"
        result["reason"] = "no board system clears the reach floor"
        result["passed"] = None
        return result

    worst_real = min(real, key=lambda d: d["arena"])      # smallest honest arena
    worst_adv = max(adv, key=lambda d: d["arena"])        # strongest fabricator
    margin = worst_real["arena"] - worst_adv["arena"]
    passed = margin >= 0.0

    # largest adversary reach that still stays at/below the binding real system
    safe_ceiling = None
    for c in adv:
        if c["arena"] <= worst_real["arena"] + 1e-12:
            safe_ceiling = c["reach"]
    beaten = [r for r in real if r["arena"] < worst_adv["arena"]]

    result.update({
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "min_safe_margin": margin,
        "binding_real_system": worst_real,
        "strongest_adversary": worst_adv,
        "adversary_safe_reach_ceiling": safe_ceiling,
        "n_real_systems_beaten_by_adversary": len(beaten),
        "real_systems_beaten": sorted(beaten, key=lambda d: d["arena"]),
    })
    return result


def _fmt(res: dict) -> str:
    L = []
    L.append(f"Arena-gate verify  gamma={res['gamma']}  reach_floor={res['reach_floor']}")
    g = res["adv_grid"]
    L.append(f"  adversary grid: reach {g['min']}..{g['max']} step {g['step']} "
             f"({g['n_points']} pts) x winrate {g['winrate']}")
    L.append(f"  real systems (reach>=floor): {res['n_real_systems']}")
    for r in res["real_systems"]:
        L.append(f"    {r['agent']:<16} reach={r['reach']:.3f} "
                 f"winrate={r['winrate']:.3f} arena={r['arena']:.4f}")
    if res["status"] == "SKIP":
        L.append(f"  STATUS: SKIP ({res['reason']})")
        return "\n".join(L)
    br = res["binding_real_system"]
    sa = res["strongest_adversary"]
    L.append(f"  binding honest system: {br['agent']} arena={br['arena']:.4f}")
    L.append(f"  strongest adversary: reach={sa['reach']} winrate={sa['winrate']} "
             f"arena={sa['arena']:.4f}")
    L.append(f"  min_safe_margin = {res['min_safe_margin']:+.4f}")
    L.append(f"  adversary reach ceiling that stays safe: "
             f"{res['adversary_safe_reach_ceiling']}")
    L.append(f"  STATUS: {res['status']}")
    if res["status"] == "FAIL":
        L.append(f"  {res['n_real_systems_beaten_by_adversary']} honest system(s) "
                 f"beaten by the reach={sa['reach']} fabricator:")
        for r in res["real_systems_beaten"]:
            L.append(f"    {r['agent']:<16} arena={r['arena']:.4f}")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True)
    ap.add_argument("--bt", required=True)
    ap.add_argument("--gamma", type=float, default=1.5)
    ap.add_argument("--reach-floor", type=float, default=0.6)
    ap.add_argument("--adv-reach-min", type=float, default=0.05)
    ap.add_argument("--adv-reach-max", type=float, default=0.31)
    ap.add_argument("--adv-reach-step", type=float, default=0.01)
    ap.add_argument("--adv-winrate", type=float, default=1.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    board = json.loads(Path(args.board).read_text())
    bt = json.loads(Path(args.bt).read_text())
    res = verify_arena_gate(
        reach_by_agent(board), winrate_by_agent(bt),
        gamma=args.gamma, reach_floor=args.reach_floor,
        adv_reach_min=args.adv_reach_min, adv_reach_max=args.adv_reach_max,
        adv_reach_step=args.adv_reach_step, adv_winrate=args.adv_winrate)
    print(_fmt(res))
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=1))
        print("wrote", args.out)
    # exit non-zero on FAIL so CI can gate on it
    return 0 if res.get("passed") in (True, None) else 1


if __name__ == "__main__":
    raise SystemExit(main())
