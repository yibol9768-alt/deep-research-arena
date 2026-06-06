#!/usr/bin/env python3
"""Quality gates over the jury battle checkpoint (experiment protocol §6).

Reads <battles.jsonl> and reports:
  - jury-level tie rate (target < 20%)
  - decisiveness split: unanimous 3-0 / majority 2-1 / no-majority tie
  - per-judge decisive rate and position-locked rate (['A','A'] / ['B','B'])
  - per-agent draw share (fairness of signal compression)

Usage: python3 scripts/jury_quality_gates.py <battles.jsonl>
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict


def main(path: str) -> int:
    n = 0
    jury_tie = 0
    unanimous = 0
    majority = 0
    errors = 0
    per_judge = defaultdict(Counter)  # judge -> {decisive, locked, tie, n}
    per_agent = defaultdict(Counter)  # agent -> {battles, draws}

    # Dedup by (task, a, b) keeping the LAST record per key (re-judged clean
    # overwrites the old degraded line), so the gate sees exactly the finalized
    # board's battle set, not the append-only history.
    dedup: dict[tuple, dict] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            dedup[(rec.get("_task"), rec.get("_a"), rec.get("_b"))] = rec

    for rec in dedup.values():
            res = rec.get("res") or {}
            if res.get("error"):
                errors += 1
                continue
            n += 1
            a, b = rec.get("_a"), rec.get("_b")
            winner = (res.get("winner") or "").lower()
            votes = res.get("judge_votes") or {}

            # per-judge stats
            named_votes = []
            for judge, v in votes.items():
                per_judge[judge]["n"] += 1
                vr = v.get("verdicts_raw") or []
                w = v.get("winner")
                if w in (a, b):
                    per_judge[judge]["decisive"] += 1
                    named_votes.append(w)
                elif len(set(vr)) == 1 and len(vr) == 2:
                    per_judge[judge]["locked"] += 1  # ['A','A'] / ['B','B']
                else:
                    per_judge[judge]["tie"] += 1

            # jury level
            per_agent[a]["battles"] += 1
            per_agent[b]["battles"] += 1
            if winner in ("a", "b"):
                top = Counter(named_votes).most_common(1)
                if top and top[0][1] == 3:
                    unanimous += 1
                else:
                    majority += 1
            else:
                jury_tie += 1
                per_agent[a]["draws"] += 1
                per_agent[b]["draws"] += 1

    if not n:
        print("no valid battles")
        return 1

    tie_rate = jury_tie / n
    print(f"battles parsed: {n}  (judge-error rows skipped: {errors})")
    print(f"jury tie rate : {tie_rate:6.1%}  target <20%  -> {'PASS' if tie_rate < 0.20 else 'FAIL'}")
    print(f"unanimous 3-0 : {unanimous / n:6.1%}")
    print(f"majority  2-1 : {majority / n:6.1%}")
    print(f"decisive total: {(unanimous + majority) / n:6.1%}")
    print("\nper-judge:")
    for judge, c in sorted(per_judge.items()):
        tot = c["n"] or 1
        print(f"  {judge:18} decisive={c['decisive']/tot:6.1%}  "
              f"pos-locked={c['locked']/tot:6.1%}  tie={c['tie']/tot:6.1%}  n={c['n']}")
    print("\nper-agent draw share (fairness):")
    for agent, c in sorted(per_agent.items(), key=lambda kv: -kv[1]["draws"] / max(kv[1]["battles"], 1)):
        share = c["draws"] / max(c["battles"], 1)
        print(f"  {agent:18} draws={c['draws']:>4}/{c['battles']:>4}  ({share:5.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else
                          "data/results/real/leaderboard_jury_elo.json.battles.jsonl"))
