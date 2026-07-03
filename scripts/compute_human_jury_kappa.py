#!/usr/bin/env python3
"""Human-vs-jury agreement (Cohen's kappa) at the battle level.

This is the paper-grade replacement for scripts/compute_judge_human_kappa.py
(the May dim-score proxy: it compared human dimension-cited winners against
per-dim score deltas, which is an approximation and is NOT usable in the
paper). Here both sides label the SAME object, one battle, with the same
three categories, which is what Cohen's kappa assumes:

  - human labels: JSONL exported from /annotate or /survey
    (fields: task_id, agent_a, agent_b, winner in {a,b,tie}; /survey rows
    also carry trust in {a,b,unsure} and source="survey")
  - jury verdicts: the committed battle log, majority verdict per battle,
    deduplicated to the last record per (task, unordered pair)
  - matching: (task_id, unordered agent pair); both UIs save canonical
    a/b (presentation order is mapped back before saving)

Reports:
  - Cohen's kappa (3 categories a/b/tie) human vs jury majority, with a
    label-bootstrap 95% CI
  - collapsed 2-category kappa (ties dropped) as a robustness view
  - trust-vs-grounding: among /survey rows with trust in {a,b}, how often
    the trusted side is the better-grounded agent (per-agent aggregate
    grounding from the board JSON)

Usage:
  python3 scripts/compute_human_jury_kappa.py labels1.jsonl [labels2.jsonl ...]
"""

import argparse
import collections
import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BATTLES = REPO / "data/results/real/leaderboard_jury_elo.json.battles.jsonl"
BOARD = REPO / "data/results/deep_v3/leaderboard_deep_v3.json"


def load_jury():
    last = {}
    for line in open(BATTLES):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = (r["_task"], tuple(sorted((r["_a"], r["_b"]))))
        w = r["res"]["winner"]  # a/b relative to _a/_b ordering
        if w == "a":
            verdict = r["_a"]
        elif w == "b":
            verdict = r["_b"]
        else:
            verdict = "tie"
        last[key] = verdict  # winning agent name, or 'tie'
    return last


def load_grounding():
    d = json.loads(BOARD.read_text())
    return {a: (p["reachability_pct"] + p["url_veracity_pct"]) / 2
            for a, p in d["per_agent_profile"].items()}


def cohen_kappa(pairs):
    """pairs: list of (human_cat, jury_cat) with categories from {a,b,tie}."""
    n = len(pairs)
    if n == 0:
        return None
    cats = sorted({c for p in pairs for c in p})
    agree = sum(1 for h, j in pairs if h == j) / n
    ph = collections.Counter(h for h, _ in pairs)
    pj = collections.Counter(j for _, j in pairs)
    pe = sum((ph[c] / n) * (pj[c] / n) for c in cats)
    if pe == 1:
        return 1.0
    return (agree - pe) / (1 - pe)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+", help="human-label JSONL files")
    ap.add_argument("--bootstrap", type=int, default=2000)
    args = ap.parse_args()

    jury = load_jury()
    grounding = load_grounding()

    rows = []
    for f in args.labels:
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    print(f"human labels: {len(rows)} from {len(args.labels)} file(s)")

    matched = []       # (human_cat, jury_cat), canonical
    trust_rows = []    # (trusted_agent, other_agent)
    unmatched = 0
    for r in rows:
        key = (r["task_id"], tuple(sorted((r["agent_a"], r["agent_b"]))))
        jv = jury.get(key)
        if jv is None:
            unmatched += 1
            continue
        jury_cat = "tie" if jv == "tie" else ("a" if jv == r["agent_a"] else "b")
        matched.append((r["winner"], jury_cat))
        t = r.get("trust")
        if t in ("a", "b"):
            trusted = r["agent_a"] if t == "a" else r["agent_b"]
            other = r["agent_b"] if t == "a" else r["agent_a"]
            trust_rows.append((trusted, other))
    print(f"matched to jury battles: {len(matched)} (unmatched {unmatched})")

    if matched:
        k3 = cohen_kappa(matched)
        two = [(h, j) for h, j in matched if h != "tie" and j != "tie"]
        k2 = cohen_kappa(two)
        rng = random.Random(42)
        ks = []
        for _ in range(args.bootstrap):
            sample = [matched[rng.randrange(len(matched))] for _ in matched]
            kk = cohen_kappa(sample)
            if kk is not None:
                ks.append(kk)
        ks.sort()
        lo, hi = ks[int(0.025 * len(ks))], ks[int(0.975 * len(ks))]
        agree = sum(1 for h, j in matched if h == j) / len(matched)
        print(f"\nCohen kappa (3-cat a/b/tie): {k3:.3f}  95% CI [{lo:.3f}, {hi:.3f}]")
        print(f"raw agreement: {agree:.1%}  | n = {len(matched)}")
        if k2 is not None:
            print(f"Cohen kappa (2-cat, ties dropped): {k2:.3f}  (n = {len(two)})")
        else:
            print(f"Cohen kappa (2-cat): n/a (n = {len(two)})")

    if trust_rows:
        ok = miss = 0
        for trusted, other in trust_rows:
            gt, go = grounding.get(trusted), grounding.get(other)
            if gt is None or go is None:
                miss += 1
                continue
            ok += gt > go
        n = len(trust_rows) - miss
        if n:
            print(f"\ntrust-vs-grounding: trusted side better grounded in "
                  f"{ok}/{n} = {ok / n:.1%} of survey rows (skipped {miss})")


if __name__ == "__main__":
    main()
