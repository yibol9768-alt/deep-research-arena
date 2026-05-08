"""
Multi-judge robustness slice (R0.3 / C3 — same-family judge bias).

Re-runs the *checklist* dimension on 20 reports (5 tasks × 4 agents) using Kimi-K2.6
as a cross-family judge (vs. DeepSeek V4 flash used in the main scoring), then
recomputes V3 with the new judge value (other 7 dimensions unchanged) and reports
the Kendall τ between DeepSeek-judge V3 ordering and Kimi-judge V3 ordering.

This addresses the editorial decision's C3 issue (same-family agent backbone +
judge raises self-enhancement bias) by providing concrete cross-family Kendall τ.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
import collections

# Configure via env (used to be hardcoded — leaked the API key in source).
# Falls back to the JUDGE_* convention so it shares config with the rest
# of the verifier suite.
PROXY = (
    os.environ.get("MULTI_JUDGE_PROXY")
    or os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/") + "/v1/chat/completions"
    if os.environ.get("ANTHROPIC_BASE_URL")
    else "http://localhost:8088/v1/chat/completions"
)
KEY = os.environ.get("MULTI_JUDGE_KEY") or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("MULTI_JUDGE_MODEL", "kimi-k2.6")
if not KEY:
    raise RuntimeError(
        "multi_judge_slice: set MULTI_JUDGE_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY"
    )

ROOT = "/Users/liuyibo/Desktop/lyb/deep_reserch"
REPORT_DIR = os.path.join(ROOT, "data/results/deep_reports")
TASK_DIR = os.path.join(ROOT, "data/tasks_subset")
SCORE_DIR = os.path.join(ROOT, "data/results/deep_v3")

AGENTS = ["camel-ai", "flowsearcher-ds", "smolagents", "gpt-researcher"]
TASKS = [f"dr_cross_deep_{i:04d}" for i in range(1, 6)]


def llm_call(prompt, retries=3):
    """Single Kimi call. Returns text content."""
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 60,
    }).encode()
    req = urllib.request.Request(
        PROXY,
        data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                d = json.load(resp)
                return d["choices"][0]["message"]["content"]
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
            if attempt == retries - 1:
                return f"[ERR:{e}]"
            time.sleep(2 ** attempt)


JUDGE_PROMPT_TEMPLATE = """You are evaluating a deep-research report against a checklist item.

REPORT (excerpt, ~5000 chars):
{report}

CHECKLIST ITEM: {item}

Decide: PASS (clearly satisfies the item), FAIL (clearly does not), or UNCLEAR (partial / ambiguous).
Reply with only one word: PASS, FAIL, or UNCLEAR."""


def judge_report(report_text, checklist_items):
    """Judge each checklist item via Kimi. Returns list of (item, verdict)."""
    out = []
    excerpt = report_text[:5000]  # keep prompt short
    for item in checklist_items:
        prompt = JUDGE_PROMPT_TEMPLATE.format(report=excerpt, item=item)
        v = llm_call(prompt).strip().upper()
        # Normalize
        if "PASS" in v:
            verdict = "PASS"
        elif "UNCLEAR" in v:
            verdict = "UNCLEAR"
        elif "FAIL" in v:
            verdict = "FAIL"
        else:
            verdict = "UNCLEAR"
        out.append((item, verdict))
    return out


def pass_rate(verdicts):
    if not verdicts:
        return 0.0
    score = sum({"PASS": 1.0, "UNCLEAR": 0.5}.get(v[1], 0.0) for v in verdicts) / len(verdicts)
    return score


def composite_v3(reach, url_cov, quote, judge, cite_align, depth, spec, pres, floor=0.1):
    quality = (0.20 * url_cov + 0.20 * quote + 0.20 * judge
               + 0.15 * cite_align + 0.10 * depth + 0.10 * spec + 0.05 * pres)
    return max(floor, reach) * quality


# ============================================================
# Main
# ============================================================
print("=" * 70)
print("Multi-judge slice: Kimi-K2.6 vs DeepSeek-V4-flash judge on 20 reports")
print("=" * 70)

# Build list of (agent, task) pairs and load DS-side scores + reports + checklists
records = []
for agent in AGENTS:
    for task in TASKS:
        report_path = os.path.join(REPORT_DIR, f"{agent}__{task}_matrix.md")
        score_path = os.path.join(SCORE_DIR, f"{agent}__{task}_matrix.score.json")
        task_path = os.path.join(TASK_DIR, f"{task}.json")
        if not (os.path.exists(report_path) and os.path.exists(score_path) and os.path.exists(task_path)):
            print(f"  SKIP missing: {agent}/{task}")
            continue
        report = open(report_path).read()
        score = json.load(open(score_path))
        td = json.load(open(task_path))
        checklist_items = td.get("checklist") or td.get("checklist_items") or []
        if isinstance(checklist_items, list) and checklist_items and isinstance(checklist_items[0], dict):
            checklist_items = [c.get("question", str(c)) for c in checklist_items]
        records.append(dict(agent=agent, task=task, report=report, score=score,
                             checklist=checklist_items))

print(f"loaded {len(records)} records")

# Run Kimi judge on each
print()
print("Running Kimi judge...")
for r in records:
    print(f"  {r['agent']}/{r['task']} ({len(r['checklist'])} items)...", end=" ", flush=True)
    t0 = time.time()
    r["kimi_verdicts"] = judge_report(r["report"], r["checklist"])
    r["kimi_pass_rate"] = pass_rate(r["kimi_verdicts"])
    r["ds_pass_rate"] = r["score"].get("checklist", {}).get("pass_rate", 0.0)
    print(f"DS={r['ds_pass_rate']:.3f} Kimi={r['kimi_pass_rate']:.3f} ({time.time()-t0:.0f}s)")

# Recompute V3 with kimi judge
print()
print("Recomputing V3 with Kimi judge:")
print(f"{'Agent':<20} {'Task':<25} {'V3-DS':>8} {'V3-Kimi':>8} {'ΔJudge':>8}")
for r in records:
    s = r["score"]
    comp = s.get("composite", {})
    ds_v3 = comp.get("composite_v3", 0)
    kimi_v3 = composite_v3(
        reach=s.get("url_reachability", {}).get("score", 0),
        url_cov=s.get("url_coverage", {}).get("score", 0),
        quote=s.get("quote_match", {}).get("score", 0),
        judge=r["kimi_pass_rate"],
        cite_align=comp.get("citation_alignment", 0),
        depth=comp.get("analysis_depth", 0),
        spec=comp.get("spec_pass_fraction", 0),
        pres=comp.get("presentation", 0),
    )
    r["ds_v3"] = ds_v3
    r["kimi_v3"] = kimi_v3
    djudge = r["kimi_pass_rate"] - r["ds_pass_rate"]
    print(f"{r['agent']:<20} {r['task']:<25} {ds_v3:>8.3f} {kimi_v3:>8.3f} {djudge:>+8.3f}")

# Per-task pairwise agreement
print()
print("=" * 70)
print("Per-task pairwise V3 ordering agreement (DS-judge vs Kimi-judge)")
print("=" * 70)
task_to_records = collections.defaultdict(list)
for r in records:
    task_to_records[r["task"]].append(r)
total_pairs = 0
agree_pairs = 0
for task, recs in task_to_records.items():
    if len(recs) < 2:
        continue
    print(f"  {task} ({len(recs)} agents):")
    for i, ra in enumerate(recs):
        for rb in recs[i+1:]:
            ds_order = ">" if ra["ds_v3"] > rb["ds_v3"] else ("<" if ra["ds_v3"] < rb["ds_v3"] else "=")
            kimi_order = ">" if ra["kimi_v3"] > rb["kimi_v3"] else ("<" if ra["kimi_v3"] < rb["kimi_v3"] else "=")
            agree = (ds_order == kimi_order)
            total_pairs += 1
            agree_pairs += int(agree)
            print(f"    {ra['agent']:<18} vs {rb['agent']:<18} DS:{ds_order} Kimi:{kimi_order} {'OK' if agree else 'DISAGREE'}")
print()
print(f"TOTAL: {agree_pairs}/{total_pairs} pairs agree = {agree_pairs/total_pairs*100:.1f}% pairwise agreement")

# Kendall τ over pairwise comparisons (treating disagreements as discordant pairs)
import math
concordant = agree_pairs
discordant = total_pairs - agree_pairs
tau = (concordant - discordant) / total_pairs if total_pairs > 0 else 1.0
print(f"Pairwise Kendall-style τ = {tau:.3f}")

# Mean absolute V3 score drift
mean_drift = sum(abs(r["kimi_v3"] - r["ds_v3"]) for r in records) / len(records)
print(f"Mean |V3-DS - V3-Kimi| = {mean_drift:.3f}")

# Save
out = dict(
    n_reports=len(records),
    records=[dict(agent=r["agent"], task=r["task"],
                   ds_v3=r["ds_v3"], kimi_v3=r["kimi_v3"],
                   ds_judge=r["ds_pass_rate"], kimi_judge=r["kimi_pass_rate"]) for r in records],
    pairwise_agreement=f"{agree_pairs}/{total_pairs}",
    pairwise_tau=tau,
    mean_v3_drift=mean_drift,
)
out_path = os.path.join(ROOT, "MULTI_JUDGE_SLICE_RESULTS.json")
json.dump(out, open(out_path, "w"), indent=2)
print()
print(f"Saved to {out_path}")
