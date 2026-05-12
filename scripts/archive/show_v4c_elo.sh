#!/usr/bin/env bash
set -e
cd /opt/deep_reserch
.venv-camel/bin/python - <<'PY'
import json
d = json.load(open("data/results/deep_v4/leaderboard_deep_v4c.json"))
print("=== v4c Elo (mean aggregation, row-level battles) ===")
elo = d["elo_mean"]
ranked = sorted(elo.items(), key=lambda kv: -kv[1]["elo"])
print(f"{'rank':<5}{'agent':<25}{'elo':>8}{'ci_lo':>8}{'ci_hi':>8}{'half':>8}{'battles':>10}")
for i, (a, v) in enumerate(ranked, 1):
    print(f"{i:<5}{a:<22}{v['elo']:>8.1f}{v['elo_lo']:>8.1f}{v['elo_hi']:>8.1f}{v['elo_half_width']:>8.1f}{v['n_battles']:>10}")
print()
gaps = [ranked[i][1]["elo"]-ranked[i+1][1]["elo"] for i in range(len(ranked)-1)]
print("Adjacent gaps:")
for i in range(len(ranked)-1):
    print(f"  {ranked[i][0]:<22} -> {ranked[i+1][0]:<22} = {gaps[i]:>6.1f} Elo")
print()
print(f"min adj gap = {min(gaps):.1f} | mean adj gap = {sum(gaps)/len(gaps):.1f}")
print()
print("=== significance ===")
for p in d["rank_significance"].get("adjacent_pairs", []):
    star = "*" if p.get("significant") else " "
    print(f"  {star} {p['higher']:<22} - {p['lower']:<22}  gap={p['gap']:>5.1f}  p={p['p_value']:.3f}")
PY
