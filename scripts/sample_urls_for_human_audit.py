#!/usr/bin/env python3
"""Sample cited URLs from each agent run for human URL-truthfulness audit.

User workflow (2026-04-27 decision): the only two manual loops are
  (1) read the leaderboard to pick the best DR framework, and
  (2) audit a sample of cited URLs for "is this URL real / does it support
      the claim around it".

This script implements (2). For each (agent, task) answer markdown file, it:

  - Extracts every markdown-linked URL `[label](url)` in the report
  - Filters to sandbox-local URLs (shopping/reddit/wiki host)
  - Stratifies a sample of N (default 20) URLs across the three sandbox
    domains, balanced by per-domain ratio
  - For each sampled URL it grabs ~120 chars of report context (the
    paragraph around the citation) so the auditor can judge whether the
    URL actually supports the claim
  - Writes a markdown worksheet `data/results/audit/<agent>__<task>.audit.md`
    with one row per URL: URL, snippet, two checkbox columns
        [ ] reachable (URL returns HTTP 200 on sandbox)
        [ ] supports_claim (URL content matches the surrounding claim)
  - Optionally probes reachability live (--probe) using requests through
    the shim; otherwise leaves the auditor to click through

After audit, run `scripts/aggregate_human_url_audit.py` to roll the
prefilled checkboxes into a per-agent `human_url_pass_rate` for the
leaderboard.

Usage:
    # default: sample 20 URLs from every final_*.answer.md
    python3 scripts/sample_urls_for_human_audit.py

    # only 3 agents, top-task only, with live reachability probe
    python3 scripts/sample_urls_for_human_audit.py \\
        --agents gpt-researcher,smolagents,react-glm5 \\
        --tasks dr_cross_deep_0001,dr_cross_deep_0006 \\
        --n 20 --probe
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results"
DEEP_RESULTS = RESULTS / "deep"
AUDIT_DIR = RESULTS / "audit"

LINK_RE = re.compile(r"\[([^\]\n]{1,200})\]\((https?://[^\s)]+)\)")

SANDBOX_HOSTS = {
    "localhost:7770": "shopping",
    "127.0.0.1:7770": "shopping",
    "localhost:9999": "reddit",
    "127.0.0.1:9999": "reddit",
    "localhost:8090": "wikipedia",
    "127.0.0.1:8090": "wikipedia",
}


def classify(url: str) -> str | None:
    try:
        p = urlparse(url)
    except ValueError:
        return None
    host = p.netloc
    return SANDBOX_HOSTS.get(host)


def extract_citations(md_text: str) -> list[dict]:
    """Return [{'url':..., 'label':..., 'snippet': ~150 chars context, 'domain':...}, ...]"""
    out = []
    for m in LINK_RE.finditer(md_text):
        label, url = m.group(1), m.group(2)
        domain = classify(url)
        if domain is None:
            continue
        # ~120 chars before + after the link occurrence
        start = max(0, m.start() - 120)
        end = min(len(md_text), m.end() + 120)
        snippet = md_text[start:end].replace("\n", " ").strip()
        out.append({"url": url, "label": label, "snippet": snippet, "domain": domain})
    return out


def stratified_sample(citations: list[dict], n: int, seed: int = 42) -> list[dict]:
    """Sample n citations, balanced across shopping/reddit/wikipedia."""
    rng = random.Random(seed)
    by_domain: dict[str, list] = {"shopping": [], "reddit": [], "wikipedia": []}
    for c in citations:
        by_domain[c["domain"]].append(c)
    # de-dup per domain so the auditor doesn't see same URL twice
    for d in by_domain:
        seen = set()
        uniq = []
        for c in by_domain[d]:
            if c["url"] in seen:
                continue
            seen.add(c["url"])
            uniq.append(c)
        rng.shuffle(uniq)
        by_domain[d] = uniq

    target = {
        "shopping":  max(1, int(round(n * 0.45))),
        "reddit":    max(1, int(round(n * 0.30))),
        "wikipedia": max(1, int(round(n * 0.25))),
    }
    while sum(target.values()) > n:
        # trim from largest pool
        d = max(target, key=target.get)
        target[d] -= 1
    while sum(target.values()) < n:
        d = max(by_domain, key=lambda k: len(by_domain[k]) - target[k])
        target[d] += 1

    sampled = []
    for d, k in target.items():
        sampled.extend(by_domain[d][:k])
    rng.shuffle(sampled)
    return sampled


def probe_reachability(url: str, timeout: float = 5.0) -> str:
    """HEAD/GET probe through the sandbox. Returns '200' / '404' / 'ERR'."""
    try:
        import requests
    except ImportError:
        return "SKIP"
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        return str(r.status_code)
    except Exception:
        return "ERR"


def render_worksheet(agent: str, task_id: str, sample: list[dict], probe: bool) -> str:
    head = (
        f"# Human URL Audit — agent={agent} task={task_id}\n\n"
        "For each row: tick `[x]` if the URL is reachable on the sandbox AND its content reasonably supports the surrounding claim. "
        "Tick `[?]` if uncertain (need to look longer). Leave blank if FAIL.\n\n"
        f"Sandbox URLs: shopping=`localhost:7770`, reddit=`localhost:9999`, wiki=`localhost:8090`.\n\n"
        "| # | domain | URL | snippet | reachable | supports_claim | notes |\n"
        "|---:|---|---|---|:---:|:---:|---|\n"
    )
    rows = []
    for i, c in enumerate(sample, 1):
        snip = c["snippet"]
        if len(snip) > 200:
            snip = snip[:200] + "…"
        snip = snip.replace("|", "\\|").replace("`", "'")
        reach_box = "[ ]"
        if probe:
            code = probe_reachability(c["url"])
            reach_box = f"`{code}`"
        rows.append(
            f"| {i} | {c['domain']} | `{c['url']}` | {snip} | {reach_box} | [ ] | |"
        )
    return head + "\n".join(rows) + "\n"


def discover_runs(agents: list[str] | None, tasks: list[str] | None) -> list[tuple[str, str, Path]]:
    """Find both shallow-tier (final_*.answer.md) and deep-tier (data/results/deep/*.md) runs."""
    out = []
    # shallow
    for p in RESULTS.glob("final_*.answer.md"):
        stem = p.name.replace("final_", "").replace(".answer.md", "")
        parts = stem.split("_", 1)
        if len(parts) != 2:
            continue
        a, t = parts
        if agents and a not in agents: continue
        if tasks and t not in tasks: continue
        out.append((a, t, p))
    # deep
    for p in DEEP_RESULTS.glob("*.md"):
        if p.name.endswith(".score.json"): continue
        stem = p.stem  # e.g. "gpt-researcher__dr_cross_deep_0001_smoke"
        if "__" not in stem: continue
        a, t = stem.split("__", 1)
        # strip trailing run-suffix tags ("_smoke", "_smoke3", "_matrix", "_diag", "_v1", ...)
        t = re.sub(r"_(smoke\d*|matrix|diag|v\d+)$", "", t)
        if agents and a not in agents: continue
        if tasks and t not in tasks: continue
        out.append((a, t, p))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default="", help="comma-separated agent ids; empty=all")
    ap.add_argument("--tasks", default="", help="comma-separated task ids; empty=all")
    ap.add_argument("--n", type=int, default=20, help="sample size per (agent,task)")
    ap.add_argument("--probe", action="store_true", help="live HTTP probe for reachability")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    agents = [a.strip() for a in args.agents.split(",") if a.strip()] or None
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()] or None

    runs = discover_runs(agents, tasks)
    if not runs:
        print(f"No runs found in {RESULTS} or {DEEP_RESULTS}.", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(runs)} agent×task runs to sample.")

    for a, t, p in runs:
        text = p.read_text(errors="ignore")
        citations = extract_citations(text)
        if not citations:
            print(f"  [skip] {a}__{t}: no sandbox-local citations in {p.name}")
            continue
        sample = stratified_sample(citations, args.n, seed=args.seed + hash(f"{a}{t}") % 1000)
        ws = render_worksheet(a, t, sample, args.probe)
        out_path = AUDIT_DIR / f"{a}__{t}.audit.md"
        out_path.write_text(ws)
        print(f"  WROTE {out_path.relative_to(ROOT)} (n={len(sample)} of {len(citations)} citations)")

    print(f"\nDone. {len(runs)} worksheets in {AUDIT_DIR.relative_to(ROOT)}.")
    print("Next: open each .audit.md, tick the boxes, save, then run aggregate_human_url_audit.py.")


if __name__ == "__main__":
    main()
