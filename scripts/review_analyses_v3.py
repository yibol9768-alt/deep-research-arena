"""
Reviewer-driven analyses on V3 score files (post-rescore, all 9 dims present).

Inputs from data/results/deep_v3/*.score.json (synced from westd 2026-05-06).
Filters to *_matrix.score.json only (excludes _smoke), and dr_cross_deep_NNNN tasks only.

Outputs:
1) Coverage matrix (9 agents × N tasks)
2) Per-intent stratified V3 leaderboard (R1.4 / EIC Q4)
3) V3 floor sensitivity sweep over {0.0, 0.05, 0.1, 0.2, 0.5} (R1.7)
4) HTTP-failure breakdown by agent (R2.3)
5) URL-stuffing null-agent attack with V3 (citation_alignment as new defense) (R1.10)
6) Symmetric n leaderboard (R0.2)
7) V1 (no gate) vs V3 ranking comparison (refresh F6 with real V3 data)
8) Multi-judge (citation_alignment / checklist) cross-agent variance
"""
import json
import glob
import os
import collections
import math

ROOT = "/Users/liuyibo/Desktop/lyb/deep_reserch"
SCORE_DIR = os.path.join(ROOT, "data/results/deep_v3")
TASK_DIR = os.path.join(ROOT, "data/tasks/deep_research/cross_site_deep")


def load_scores():
    rows = []
    for path in sorted(glob.glob(os.path.join(SCORE_DIR, "*_matrix.score.json"))):
        name = os.path.basename(path)
        agent = name.split("__")[0]
        task = name.split("__")[1].split("_matrix")[0]
        if not task.startswith("dr_cross_deep_"):
            continue
        try:
            d = json.load(open(path))
        except Exception:
            continue
        comp = d.get("composite", {})
        rd = d.get("url_reachability", {}).get("details", {})
        rows.append(dict(
            agent=agent, task=task,
            url_cov=d.get("url_coverage", {}).get("score", 0.0),
            reach=d.get("url_reachability", {}).get("score", 0.0),
            quote=d.get("quote_match", {}).get("score", 0.0),
            spec=comp.get("spec_pass_fraction", 0.0),
            judge=d.get("checklist", {}).get("pass_rate", 0.0),
            citation_alignment=comp.get("citation_alignment", 0.0),
            analysis_depth=comp.get("analysis_depth", 0.0),
            presentation=comp.get("presentation", 0.0),
            composite_v3=comp.get("composite_v3", 0.0),
            composite_v2=comp.get("composite_v2", 0.0),
            composite_v1=comp.get("composite_v1", 0.0),
            cited_total=rd.get("cited_total", 0),
            http_200=rd.get("http_200", 0),
            http_4xx=rd.get("http_4xx", 0),
            http_5xx=rd.get("http_5xx", 0),
            net_fail=rd.get("net_fail", 0),
        ))
    return rows


def load_task_meta():
    meta = {}
    for path in sorted(glob.glob(os.path.join(TASK_DIR, "*.json"))):
        bn = os.path.basename(path).replace(".json", "")
        if not bn.startswith("dr_cross_deep_"):
            continue
        try:
            d = json.load(open(path))
        except Exception:
            continue
        meta[bn] = dict(
            domain=d.get("domain", "?"),
            intent_type=d.get("intent_type", d.get("intent", "?")),
        )
    return meta


def composite_v3(row, floor=0.1):
    """Recompute V3 from components.
    composite_v3 = max(floor, reach) × (0.20·url_cov + 0.20·quote + 0.20·judge + 0.15·cite_align + 0.10·depth + 0.10·spec + 0.05·pres)
    """
    quality = (0.20 * row["url_cov"] + 0.20 * row["quote"] + 0.20 * row["judge"]
               + 0.15 * row["citation_alignment"] + 0.10 * row["analysis_depth"]
               + 0.10 * row["spec"] + 0.05 * row["presentation"])
    return max(floor, row["reach"]) * quality


def composite_v1_recomp(row):
    """V1 (no gate, only quality)."""
    return (0.20 * row["url_cov"] + 0.20 * row["quote"] + 0.20 * row["judge"]
            + 0.15 * row["citation_alignment"] + 0.10 * row["analysis_depth"]
            + 0.10 * row["spec"] + 0.05 * row["presentation"])


def composite_v3_no_cite_gate(row, floor=0.1):
    """C13 fix: V1' baseline that includes citation_alignment, no reachability gate."""
    return composite_v1_recomp(row)


def kendall_tau(rank_a, rank_b):
    pos_a = {x: i for i, x in enumerate(rank_a)}
    pos_b = {x: i for i, x in enumerate(rank_b)}
    items = list(rank_a)
    n = len(items)
    if n < 2:
        return 1.0
    c = d = 0
    for i in range(n):
        for j in range(i + 1, n):
            v = (pos_a[items[i]] - pos_a[items[j]]) * (pos_b[items[i]] - pos_b[items[j]])
            if v > 0:
                c += 1
            elif v < 0:
                d += 1
    return (c - d) / (c + d) if (c + d) > 0 else 1.0


def bt_elo(rows, scoring_fn):
    by_task = collections.defaultdict(dict)
    for r in rows:
        by_task[r["task"]][r["agent"]] = r
    agents = sorted({r["agent"] for r in rows})
    wins = collections.defaultdict(lambda: collections.defaultdict(int))
    for task, ag2row in by_task.items():
        present = list(ag2row.keys())
        for i, a in enumerate(present):
            for b in present[i+1:]:
                sa, sb = scoring_fn(ag2row[a]), scoring_fn(ag2row[b])
                if sa > sb:
                    wins[a][b] += 1
                elif sb > sa:
                    wins[b][a] += 1
    theta = {a: 1.0 for a in agents}
    for _ in range(500):
        new = {}
        for a in agents:
            num = 0.5 + sum(wins[a][b] for b in agents if b != a)
            den = 0.5
            for b in agents:
                if b == a:
                    continue
                wab = wins[a][b] + wins[b][a]
                if wab > 0:
                    den += wab / (theta[a] + theta[b])
            new[a] = num / den if den > 0 else theta[a]
        s = sum(new.values()) / len(new)
        new = {k: v / s for k, v in new.items()}
        if max(abs(new[a] - theta[a]) for a in agents) < 1e-6:
            theta = new
            break
        theta = new
    ln = {a: math.log(theta[a]) for a in agents}
    m = sum(ln.values()) / len(ln)
    elo = {a: 1000 + 400 * (ln[a] - m) / math.log(10) for a in agents}
    wl = {a: (sum(wins[a][b] for b in agents if b != a),
              sum(wins[b][a] for b in agents if b != a)) for a in agents}
    return elo, wl


# ============================================================
print("=" * 70)
print("Loading V3 score files (post-rescore)...")
rows = load_scores()
meta = load_task_meta()
agents = sorted({r["agent"] for r in rows})
agent_tasks = collections.defaultdict(set)
for r in rows:
    agent_tasks[r["agent"]].add(r["task"])
all_tasks = sorted({r["task"] for r in rows})
print(f"agents: {len(agents)} = {agents}")
print(f"tasks (unique seen): {len(all_tasks)}")
print(f"per-agent task coverage:")
for a in agents:
    print(f"  {a:<20} {len(agent_tasks[a])}")
common = set.intersection(*agent_tasks.values()) if agent_tasks else set()
print(f"common tasks across all agents: {len(common)}")
common_rows = [r for r in rows if r["task"] in common]

# ============================================================
# Analysis 1: Per-intent leaderboard (V3)
# ============================================================
print()
print("=" * 70)
print("ANALYSIS 1: Per-intent V3 composite mean (common subset)")
print("=" * 70)
intent_of = {t: meta.get(t, {}).get("intent_type", "?") for t in common}
intent_counts = collections.Counter(intent_of.values())
print(f"Intent dist on common ({len(common)} tasks):")
for it, n in sorted(intent_counts.items(), key=lambda x: -x[1]):
    print(f"  {it:<25} {n}")

print()
intents_sorted = sorted(intent_counts.keys())
header = ["Agent"] + intents_sorted + ["All"]
fmt_h = "{:<20}" + " {:>14}" * len(intents_sorted) + " {:>10}"
fmt_r = "{:<20}" + " {:>14}" * len(intents_sorted) + " {:>10}"
print(fmt_h.format(*header))
agent_intent_v3 = collections.defaultdict(dict)
for a in agents:
    for it in intents_sorted:
        comps = [r["composite_v3"] for r in common_rows if r["agent"] == a and intent_of.get(r["task"]) == it]
        agent_intent_v3[a][it] = (sum(comps) / len(comps)) if comps else float("nan")
    overall = [r["composite_v3"] for r in common_rows if r["agent"] == a]
    agent_intent_v3[a]["All"] = sum(overall) / len(overall) if overall else 0.0
for a in agents:
    cells = [a]
    for it in intents_sorted:
        v = agent_intent_v3[a][it]
        cells.append(f"{v:.3f} (n={sum(1 for r in common_rows if r['agent']==a and intent_of.get(r['task'])==it)})")
    cells.append(f"{agent_intent_v3[a]['All']:.3f}")
    print(fmt_r.format(*cells))

# Per-intent winner
print()
print("Per-intent winner (highest V3 mean):")
for it in intents_sorted:
    best = max(agents, key=lambda a: agent_intent_v3[a][it] if not math.isnan(agent_intent_v3[a][it]) else -1)
    print(f"  {it:<25} → {best} ({agent_intent_v3[best][it]:.3f})")

# ============================================================
# Analysis 2: V3 floor sensitivity sweep
# ============================================================
print()
print("=" * 70)
print("ANALYSIS 2: V3 reachability-gate floor sensitivity")
print("=" * 70)
floors = [0.0, 0.05, 0.1, 0.2, 0.5]
ranks = {}
elos = {}
for f in floors:
    e, _ = bt_elo(common_rows, lambda r: composite_v3(r, floor=f))
    ranks[f] = sorted(agents, key=lambda a: -e[a])
    elos[f] = e
ref = ranks[0.1]
print(f"{'Floor':>6} {'Ranking':<70} {'τ vs 0.1':>10}")
for f in floors:
    print(f"{f:>6.2f} {' > '.join(ranks[f]):<70} {kendall_tau(ref, ranks[f]):>10.3f}")
print()
print(f"{'Agent':<20}" + "".join(f" floor={f:<5}" for f in floors))
for a in agents:
    print(f"{a:<20}" + "".join(f" {elos[f][a]:>10.0f}" for f in floors))

# V1' = no-gate but with citation_alignment (DA C13 critique fix)
elo_v1p, _ = bt_elo(common_rows, composite_v1_recomp)
ranks_v1p = sorted(agents, key=lambda a: -elo_v1p[a])
tau_v3_v1p = kendall_tau(ref, ranks_v1p)
print()
print("V1' (no gate, includes citation_alignment) — fair no-gate baseline:")
for a in ranks_v1p:
    print(f"  {a:<20} {elo_v1p[a]:>6.0f}")
print(f"τ(V3 floor=0.1, V1') = {tau_v3_v1p:.3f}")

# ============================================================
# Analysis 3: HTTP failure breakdown
# ============================================================
print()
print("=" * 70)
print("ANALYSIS 3: HTTP failure breakdown (common subset)")
print("=" * 70)
print(f"{'Agent':<20} {'cited':>8} {'200':>8} {'4xx':>8} {'5xx':>8} {'netfail':>8} {'fab%':>8}")
for a in agents:
    ar = [r for r in common_rows if r["agent"] == a]
    t = sum(r["cited_total"] for r in ar)
    h2 = sum(r["http_200"] for r in ar)
    h4 = sum(r["http_4xx"] for r in ar)
    h5 = sum(r["http_5xx"] for r in ar)
    nf = sum(r["net_fail"] for r in ar)
    fab = (1 - h2 / t) * 100 if t > 0 else 0
    print(f"{a:<20} {t:>8} {h2:>8} {h4:>8} {h5:>8} {nf:>8} {fab:>7.1f}%")

# ============================================================
# Analysis 4: URL-stuffing attack with V3 + citation_alignment defense
# ============================================================
print()
print("=" * 70)
print("ANALYSIS 4: URL-stuffing attack — does citation_alignment defend?")
print("=" * 70)
# Two adversaries:
# (a) URL-stuffer: dumps all sandbox URLs verbatim (high reach, high url_cov, near-zero alignment)
# (b) Quote-stuffer: copies first 200 chars of each cited page (high quote_match, but low judge / depth / pres)
stuffer = dict(url_cov=0.95, reach=0.99, quote=0.10, judge=0.05, spec=1.0,
               citation_alignment=0.05, analysis_depth=0.0, presentation=0.20)
stuffer_v3 = composite_v3(stuffer, floor=0.1)
stuffer_v1 = composite_v1_recomp(stuffer)
print(f"URL-stuffer (real URLs, no real prose):")
print(f"  components: url_cov=.95 reach=.99 quote=.10 judge=.05 cite_align=.05")
print(f"  V3 (floor=0.1): {stuffer_v3:.3f}")
print(f"  V1' (no gate): {stuffer_v1:.3f}")

# Compare to real top-3
real_means = {a: sum(r["composite_v3"] for r in common_rows if r["agent"] == a) / len(common) for a in agents}
print(f"\nTop-3 real V3 means on common subset:")
for a in sorted(agents, key=lambda x: -real_means[x])[:3]:
    print(f"  {a}: V3={real_means[a]:.3f}")
print()
print(f"**Verdict**: URL-stuffer V3 = {stuffer_v3:.3f}.")
real_ranked = sorted(agents, key=lambda x: -real_means[x])
n_better = sum(1 for a in agents if real_means[a] > stuffer_v3)
print(f"It would rank #{n_better+1} of {len(agents)+1} agents (beating {len(agents)-n_better} real frameworks).")

# ============================================================
# Analysis 5: Symmetric leaderboard (V3) on common
# ============================================================
print()
print("=" * 70)
print(f"ANALYSIS 5: Symmetric n={len(common)} V3 leaderboard")
print("=" * 70)
elo_main, wl_main = bt_elo(common_rows, lambda r: composite_v3(r, floor=0.1))
print(f"{'Rank':>4} {'Agent':<20} {'Elo':>6} {'W':>4} {'L':>4} {'V3 mean':>9}")
for i, a in enumerate(sorted(agents, key=lambda x: -elo_main[x]), 1):
    w, l = wl_main[a]
    print(f"{i:>4} {a:<20} {elo_main[a]:>6.0f} {w:>4} {l:>4} {real_means[a]:>9.3f}")

# ============================================================
# Output JSON for paper revision
# ============================================================
out = dict(
    n_score_files=len(rows),
    n_common_tasks=len(common),
    common_tasks=sorted(common),
    agents=agents,
    agent_task_counts={a: len(agent_tasks[a]) for a in agents},
    intent_distribution=dict(intent_counts),
    per_intent_v3={a: dict(agent_intent_v3[a]) for a in agents},
    floor_sensitivity={f: dict(elos[f]) for f in floors},
    floor_sensitivity_tau={f: kendall_tau(ref, ranks[f]) for f in floors},
    v1_prime_elo=elo_v1p,
    tau_v3_vs_v1prime=tau_v3_v1p,
    http_breakdown={a: dict(
        cited=sum(r["cited_total"] for r in common_rows if r["agent"] == a),
        h200=sum(r["http_200"] for r in common_rows if r["agent"] == a),
        h4xx=sum(r["http_4xx"] for r in common_rows if r["agent"] == a),
        h5xx=sum(r["http_5xx"] for r in common_rows if r["agent"] == a),
        netfail=sum(r["net_fail"] for r in common_rows if r["agent"] == a),
    ) for a in agents},
    stuffer_simulation=dict(
        components=stuffer,
        v3_floor_0p1=stuffer_v3,
        v1_prime=stuffer_v1,
        rank_among_real=n_better + 1,
    ),
    symmetric_leaderboard={a: dict(elo=elo_main[a], w=wl_main[a][0], l=wl_main[a][1],
                                    v3_mean=real_means[a]) for a in agents},
)
out_path = os.path.join(ROOT, "REVIEW_ANALYSES_V3_RESULTS.json")
json.dump(out, open(out_path, "w"), indent=2, default=str)
print()
print(f"Results written to {out_path}")
