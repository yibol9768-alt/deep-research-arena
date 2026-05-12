#!/usr/bin/env bash
set -e
cd /opt/deep_reserch
.venv-camel/bin/python -c '
import json, math, glob, statistics
from collections import defaultdict

V4_DIR = "data/results/deep_v4"
V3_DIR = "data/results/deep_v3"

PILLARS = [
    "url_coverage", "checklist", "citation_alignment", "quote_match",
    "factual_exactness", "internal_consistency", "perspective_balance",
    "source_diversity", "analysis_depth", "presentation", "spec",
]

WEIGHTS_V4B = {
    "url_coverage": 0.10, "spec": 0.05, "checklist": 0.10,
    "citation_alignment": 0.10, "quote_match": 0.05,
    "factual_exactness": 0.13, "internal_consistency": 0.07,
    "perspective_balance": 0.08, "source_diversity": 0.12,
    "analysis_depth": 0.10, "presentation": 0.10,
}

def spec_pass(spec):
    if not isinstance(spec, dict): return 0.0
    flags = [bool(spec.get(k, False)) for k in ("words_ok","citations_ok","paragraphs_ok")]
    return sum(flags) / 3.0

def chk_pass(c):
    if not isinstance(c, dict): return 0.0
    v = c.get("pass_rate")
    if v is None: v = c.get("score")
    return float(v or 0)

def pscore(blob, key):
    b = blob.get(key)
    if isinstance(b, dict):
        if key == "checklist": return chk_pass(b)
        if key == "markdown_spec": return spec_pass(b)
        return float(b.get("score") or 0)
    return 0.0

# 1) Load all 44 rows, harvest every pillar value
rows = []
for fp in sorted(glob.glob(V4_DIR + "/*.v4.json")):
    v4 = json.load(open(fp))
    v3 = json.load(open(v4["score_path"]))
    pillars = {
        "url_coverage": pscore(v3, "url_coverage"),
        "spec": spec_pass(v3.get("markdown_spec")),
        "checklist": chk_pass(v3.get("checklist")),
        "citation_alignment": pscore(v3, "citation_alignment"),
        "quote_match": pscore(v3, "quote_match"),
        "factual_exactness": pscore(v4, "factual_exactness"),
        "internal_consistency": pscore(v4, "internal_consistency"),
        "perspective_balance": pscore(v4, "perspective_balance"),
        "source_diversity": pscore(v4, "source_diversity"),
        "analysis_depth": pscore(v3, "analysis_depth"),
        "presentation": pscore(v3, "presentation"),
    }
    reach = pscore(v3, "url_reachability")
    rows.append({"agent": v4["agent"], "task": v4["task"],
                 "pillars": pillars, "reach": reach})

print(f"loaded {len(rows)} rows")
print()

# 2) Compute population stats per pillar
stats = {}
for k in WEIGHTS_V4B:
    vals = [r["pillars"][k] for r in rows]
    mu = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    rng = max(vals) - min(vals)
    stats[k] = {"mu": mu, "sd": sd, "min": min(vals), "max": max(vals), "rng": rng}
    print(f"{k:24} mu={mu:.3f}  sd={sd:.3f}  range=[{min(vals):.2f}, {max(vals):.2f}]  span={rng:.2f}")
print()

# 3) Z-score + sigmoid for each row
def sig(x):
    if x > 8: return 1.0
    if x < -8: return 0.0
    return 1.0 / (1.0 + math.exp(-x))

def v4c_score(row):
    raw = 0.0
    for k, w in WEIGHTS_V4B.items():
        s = stats[k]
        if s["sd"] < 1e-6:
            z = 0.0
        else:
            z = (row["pillars"][k] - s["mu"]) / s["sd"]
            z = max(-3.0, min(3.0, z))
        normed = sig(z * 1.2)  # 1.2 sharpening
        raw += w * normed
    return row["reach"] * raw

# 4) Aggregate per agent
per_agent = defaultdict(list)
for r in rows:
    per_agent[r["agent"]].append(v4c_score(r))

print("=== Per-agent v4c (mean / median / P25 / min) ===")
print(f"{'agent':<22} {'mean':>8} {'med':>8} {'P25':>8} {'min':>8} {'n':>4}")
ranked = []
for a, scores in per_agent.items():
    scores_sorted = sorted(scores)
    mean = sum(scores) / len(scores)
    median = statistics.median(scores)
    p25 = scores_sorted[max(0, len(scores)//4 - 0)] if len(scores) >= 4 else scores_sorted[0]
    mn = min(scores)
    ranked.append((a, mean, median, p25, mn, len(scores)))

ranked.sort(key=lambda x: -x[1])
for a, m, med, p25, mn, n in ranked:
    print(f"{a:<22} {m:>8.4f} {med:>8.4f} {p25:>8.4f} {mn:>8.4f} {n:>4}")
'
