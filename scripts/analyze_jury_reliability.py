#!/usr/bin/env python3
"""Jury reliability analysis: inter-judge agreement, position bias, and
degenerate-round detection.

Reads the jury battle sidecar (judge_votes per battle, both-ordering raw
verdicts per judge) and reports, per battle subset:

  - Fleiss' kappa over verdict categories {a, b, tie} across the 3 jurors
  - unanimity / 2-majority / 3-way-split rates
  - per-judge tie marginals
  - per-judge position consistency: among battles where a judge gave two
    non-TIE raw verdicts (one per ordering), the share that picked the
    SAME report in both orderings ((A,B) or (B,A)); 50% = pure position
    preference, 100% = fully order-invariant

Subsets: all battles / clean rounds / rounds involving the agents named in
--suspect (default claude-code,opencode), where the 2026-06 API-credit
outage left two jurors returning errors that were recorded as ties
(C-1 in survey/F_our_results_inventory.md).

Usage:
  python3 scripts/analyze_jury_reliability.py \
      [--battles data/results/real/leaderboard_jury_elo.json.battles.jsonl] \
      [--json out.json]

Dedup rule: the sidecar is append-only across re-judge rounds; the LAST
occurrence of a (task, unordered pair) wins, matching the board builder.
"""

import argparse
import collections
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_BATTLES = REPO / "data/results/real/leaderboard_jury_elo.json.battles.jsonl"


def load_battles(path):
    last = {}
    for line in open(path):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        last[(r["_task"], tuple(sorted((r["_a"], r["_b"]))))] = r
    return list(last.values())


def vote_cat(r, judge):
    jv = r["res"]["judge_votes"].get(judge, {})
    w = jv.get("winner")
    if w == "tie":
        return "tie"
    if w == r["_a"]:
        return "a"
    if w == r["_b"]:
        return "b"
    return None


def fleiss_stats(subset, judges):
    """Fleiss' kappa + agreement pattern rates over categories {a,b,tie}."""
    n_valid = unanimous = majority2 = 0
    pi_sum = 0.0
    marg = collections.Counter()
    for r in subset:
        votes = [vote_cat(r, j) for j in judges]
        if any(v is None for v in votes):
            continue
        n_valid += 1
        cnt = collections.Counter(votes)
        marg.update(cnt)
        pi_sum += (sum(m * m for m in cnt.values()) - 3) / 6  # n_raters=3
        top = max(cnt.values())
        unanimous += top == 3
        majority2 += top == 2
    if not n_valid:
        return None
    p_bar = pi_sum / n_valid
    tot = sum(marg.values())
    p_e = sum((v / tot) ** 2 for v in marg.values())
    return {
        "n": n_valid,
        "fleiss_kappa": round((p_bar - p_e) / (1 - p_e), 4),
        "unanimous": round(unanimous / n_valid, 4),
        "majority2": round(majority2 / n_valid, 4),
        "split3": round(1 - (unanimous + majority2) / n_valid, 4),
        "marginals": {c: round(marg[c] / tot, 4) for c in ("a", "b", "tie")},
    }


def position_consistency(subset, judges):
    """Per-judge order-invariance among double non-TIE raw verdicts."""
    out = {}
    for j in judges:
        same = total = tie_any = 0
        for r in subset:
            vr = r["res"]["judge_votes"].get(j, {}).get("verdicts_raw", [])
            if len(vr) != 2:
                continue
            if "TIE" in vr:
                tie_any += 1
                continue
            total += 1
            same += (tuple(vr) in {("A", "B"), ("B", "A")})
        out[j] = {
            "consistent": round(same / total, 4) if total else None,
            "n_double_verdicts": total,
            "n_with_tie": tie_any,
        }
    return out


def degenerate_tie_patterns(subset, judges):
    """Count judges whose raw verdicts are (TIE, TIE), i.e. produced no
    signal; the C-1 outage shows up as ~100% here for two jurors."""
    out = {}
    for j in judges:
        tt = n = 0
        for r in subset:
            vr = r["res"]["judge_votes"].get(j, {}).get("verdicts_raw", [])
            if len(vr) == 2:
                n += 1
                tt += vr == ["TIE", "TIE"]
        out[j] = {"tie_tie_share": round(tt / n, 4) if n else None, "n": n}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--battles", default=str(DEFAULT_BATTLES))
    ap.add_argument("--suspect", default="claude-code,opencode",
                    help="agents whose rounds are analyzed separately")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    rows = load_battles(args.battles)
    judges = sorted({j for r in rows for j in r["res"].get("judge_votes", {})})
    suspect = set(a for a in args.suspect.split(",") if a)
    sus = [r for r in rows if suspect & {r["_a"], r["_b"]}]
    clean = [r for r in rows if not (suspect & {r["_a"], r["_b"]})]

    report = {"judges": judges, "n_battles": len(rows)}
    for label, subset in (("all", rows), ("clean", clean), ("suspect_rounds", sus)):
        report[label] = {
            "agreement": fleiss_stats(subset, judges),
            "position_consistency": position_consistency(subset, judges),
            "degenerate_tie": degenerate_tie_patterns(subset, judges),
        }

    print(json.dumps(report, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
