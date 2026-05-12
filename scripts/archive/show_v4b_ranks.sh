#!/usr/bin/env bash
set -e
cd /opt/deep_reserch
.venv-camel/bin/python -c '
import json
data = json.load(open("data/results/deep_v4/leaderboard_deep_v4b.json"))
ranked = sorted(data["elo"].items(), key=lambda kv: -kv[1]["elo"])
print("v4b leaderboard:")
print("rank  agent                       elo    ci_lo    ci_hi    half  battles")
for i, (a, v) in enumerate(ranked, 1):
    print("{:<5} {:<22} {:>8.1f} {:>7.1f} {:>7.1f} {:>7.1f} {:>8}".format(
        i, a, v["elo"], v["elo_lo"], v["elo_hi"], v["elo_half_width"], v["n_battles"]))
print()
print("Adjacent gaps:")
for i in range(len(ranked) - 1):
    g = ranked[i][1]["elo"] - ranked[i + 1][1]["elo"]
    print("  {:<22} -> {:<22} = {:>6.1f} Elo".format(
        ranked[i][0], ranked[i + 1][0], g))
gaps = [ranked[i][1]["elo"] - ranked[i + 1][1]["elo"] for i in range(len(ranked) - 1)]
print()
print("min adj gap = {:.1f}, mean adj gap = {:.1f}".format(min(gaps), sum(gaps) / len(gaps)))
'
