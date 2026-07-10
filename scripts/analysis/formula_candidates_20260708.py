#!/usr/bin/env python3
"""Recompute truth-board rankings under candidate scoring formulas (K0-K5).

Decision-memo support ONLY. Does NOT touch the production scorer.
Real scoring pipeline replicated: per-report quality = sum_k w_k * floor(axis_k),
truth = reach**gamma * quality, macro-average per agent, rank.

Data: scratchpad/boards/truth_board_{qwen3-8b,deepseek-v4-flash}.json
      per_task[agent][task]['axes'] = raw (pre-floor) five axes.

Caveat baked in: PoF axis is known false-negative (E-3/E-4). Any candidate that
removes the floor or drops spec is confounded by PoF false-negatives; numbers here
are on CURRENT (buggy-PoF) data and are a pessimistic bound for grounding-via-
non-markdown-citation reports. Flagged in output.
"""
import json, itertools, sys

GAMMA = 1.5
EPS = 0.05
BOARDS = {
    "qwen3-8b": "/tmp/claude-0/-root-Desktop/93ed2111-a32d-447e-aba8-7da9bb527cc9/scratchpad/boards/truth_board_qwen3-8b.json",
    "deepseek-v4-flash": "/tmp/claude-0/-root-Desktop/93ed2111-a32d-447e-aba8-7da9bb527cc9/scratchpad/boards/truth_board_deepseek-v4-flash.json",
}
AX = ["correctness_fact_support", "grounding_proof_of_fetch", "completeness", "spec"]
SHORT = {"correctness_fact_support": "fact", "grounding_proof_of_fetch": "pof",
         "completeness": "comp", "spec": "spec"}


def floor_std(v, active_only=False):
    """Standard floor: max(v,eps). floor-if-active: eps only when raw v>0."""
    if active_only:
        return max(v, EPS) if v > 0 else 0.0
    return max(v, EPS)


CANDIDATES = {
    # name: (weights over 4 axes fact/pof/comp/spec, floor_mode)
    # floor_mode: 'std' floor all quality axes; 'none' no floor; 'active' floor-if-active
    "K0_current":        (dict(fact=.35, pof=.25, comp=.30, spec=.10), "std"),
    "K1_nospec_renorm_floor": (dict(fact=.35/.90, pof=.25/.90, comp=.30/.90, spec=0.0), "std"),
    "K2_nospec_nofloor_declared": (dict(fact=.35, pof=.25, comp=.30, spec=0.0), "none"),
    "K3_nospec_nofloor_equal": (dict(fact=1/3, pof=1/3, comp=1/3, spec=0.0), "none"),
    "K4_spec_kept_floor_if_active": (dict(fact=.35, pof=.25, comp=.30, spec=.10), "active"),
    # K5 (my addition): keep 4 axes + declared weights + floor-if-active, but
    # spec de-weighted to .05 and mass moved to comp (form is weakest evidence).
    "K5_flooractive_specdown": (dict(fact=.35, pof=.25, comp=.35, spec=.05), "active"),
    # K6 (criteria-optimal candidate): spec OUT of truth + declared-3 renorm +
    # floor-if-active. Aim: C2 passes (all-zero shell -> 0) AND partial-substance
    # reports keep a gentle floor (unlike pure no-floor K2).
    "K6_nospec_renorm_flooractive": (dict(fact=.35/.90, pof=.25/.90, comp=.30/.90, spec=0.0), "active"),
    # K7: spec OUT + equal-3 + floor-if-active.
    "K7_nospec_equal_flooractive": (dict(fact=1/3, pof=1/3, comp=1/3, spec=0.0), "active"),
}


def quality(axes, weights, floor_mode):
    active = (floor_mode == "active")
    q = 0.0
    for a in AX:
        w = weights[SHORT[a]]
        if w == 0.0:
            continue
        raw = float(axes.get(a, 0.0))
        if floor_mode == "none":
            v = raw
        else:
            v = floor_std(raw, active_only=active)
        q += w * v
    return q


def report_truth(axes, weights, floor_mode):
    reach = max(0.0, float(axes.get("grounding_reach", 0.0)))
    return (reach ** GAMMA) * quality(axes, weights, floor_mode)


def kendall_tau(order_a, order_b):
    common = [x for x in order_a if x in order_b]
    ra = {a: i for i, a in enumerate(order_a)}
    rb = {a: i for i, a in enumerate(order_b)}
    n = len(common)
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            x, y = common[i], common[j]
            sa = ra[x] - ra[y]
            sb = rb[x] - rb[y]
            if sa * sb > 0:
                conc += 1
            elif sa * sb < 0:
                disc += 1
    tot = conc + disc
    return (conc - disc) / tot if tot else 1.0


def shell_axes(spec=1.0, reach=1.0):
    """Empty shell: zero substance, one real reachable citation, format-compliant."""
    return {"correctness_fact_support": 0.0, "grounding_proof_of_fetch": 0.0,
            "completeness": 0.0, "spec": spec, "grounding_reach": reach}


def has_substance(axes):
    return float(axes.get("correctness_fact_support", 0)) > 0 or \
           float(axes.get("completeness", 0)) > 0


def run_board(name, path):
    board = json.load(open(path))
    per_task = board["per_task"]
    agents = list(per_task.keys())
    out = {"backbone": name, "candidates": {}}
    # reference K0 ordering
    orderings = {}
    for cand, (w, fm) in CANDIDATES.items():
        macro = {}
        report_truths = []  # (agent, task, truth, has_subst)
        for ag in agents:
            ts = []
            for task, rec in per_task[ag].items():
                axes = rec["axes"]
                t = report_truth(axes, w, fm)
                ts.append(t)
                report_truths.append((ag, task, t, has_substance(axes)))
            macro[ag] = sum(ts) / len(ts) if ts else 0.0
        order = sorted(agents, key=lambda a: -macro[a])
        orderings[cand] = order
        # shell scores at two spec levels
        shell_hi = report_truth(shell_axes(spec=1.0), w, fm)
        shell_mid = report_truth(shell_axes(spec=0.6), w, fm)
        # C2: honest-with-substance reports strictly below the strong shell
        below = [(a, tk, round(t, 4)) for (a, tk, t, sub) in report_truths
                 if sub and t < shell_hi]
        out["candidates"][cand] = {
            "macro": {a: round(macro[a], 4) for a in order},
            "order": order,
            "ldr_rank": order.index("ldr") + 1 if "ldr" in order else None,
            "opencode_rank": order.index("opencode") + 1 if "opencode" in order else None,
            "top3": order[:3],
            "shell_spec1.0": round(shell_hi, 4),
            "shell_spec0.6": round(shell_mid, 4),
            "n_honest_substance_below_shell": len(below),
            "honest_below_shell_examples": below[:8],
        }
    # tau + top3 overlap vs K0
    k0 = orderings["K0_current"]
    for cand in CANDIDATES:
        out["candidates"][cand]["tau_vs_K0"] = round(kendall_tau(k0, orderings[cand]), 4)
        out["candidates"][cand]["top3_same_as_K0"] = \
            set(orderings[cand][:3]) == set(k0[:3])
    return out


def main():
    results = {}
    for name, path in BOARDS.items():
        results[name] = run_board(name, path)
    json.dump(results, open("/tmp/claude-0/-root-Desktop/93ed2111-a32d-447e-aba8-7da9bb527cc9/scratchpad/formula_candidates.json", "w"), indent=2)
    # console summary
    for name in BOARDS:
        print("=" * 70)
        print("BACKBONE:", name)
        r = results[name]["candidates"]
        print(f"{'cand':<32}{'ldr':>4}{'opn':>4}{'tau':>7}{'shellHi':>9}{'shellMid':>9}{'#hon<shell':>11}")
        for cand in CANDIDATES:
            c = r[cand]
            print(f"{cand:<32}{str(c['ldr_rank']):>4}{str(c['opencode_rank']):>4}"
                  f"{c['tau_vs_K0']:>7}{c['shell_spec1.0']:>9}{c['shell_spec0.6']:>9}"
                  f"{c['n_honest_substance_below_shell']:>11}")
        print("  K0 top3:", r["K0_current"]["top3"])
        for cand in CANDIDATES:
            if not r[cand]["top3_same_as_K0"]:
                print(f"  {cand} top3 CHANGED -> {r[cand]['top3']}")
    print("\nWrote scratchpad/formula_candidates.json")


if __name__ == "__main__":
    main()
