#!/usr/bin/env python3
"""Roll up human URL-audit worksheets into per-(agent,task) pass rates.

Reads `data/results/audit/<agent>__<task>.audit.md`, parses the table rows
emitted by sample_urls_for_human_audit.py, counts:

  - reachable_pass = rows with `[x]` in the reachable column
                     (or live probe code in {200, 30x})
  - supports_pass  = rows with `[x]` in the supports_claim column
  - uncertain      = rows with `[?]`
  - n_sampled      = total rows

and writes:
  - data/results/human_url_audit_summary.json — flat list per (agent, task)
  - data/results/HUMAN_URL_AUDIT.md           — human-readable leaderboard
                                                 with reachability% and
                                                 supports_claim%

Usage: python3 scripts/aggregate_human_url_audit.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data" / "results" / "audit"
OUT_JSON = ROOT / "data" / "results" / "human_url_audit_summary.json"
OUT_MD = ROOT / "data" / "results" / "HUMAN_URL_AUDIT.md"

ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(\w+)\s*\|\s*`([^`]+)`\s*\|.*?\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$",
    re.MULTILINE,
)

PASS_TOKENS = {"[x]", "[X]"}
UNCERTAIN_TOKENS = {"[?]"}


def parse_worksheet(path: Path) -> dict:
    text = path.read_text(errors="ignore")
    stem = path.stem.replace(".audit", "")
    if "__" not in stem:
        return {}
    agent, task = stem.split("__", 1)

    n = 0
    reach_pass = 0
    supports_pass = 0
    uncertain = 0
    by_domain: dict[str, dict] = {}

    for m in ROW_RE.finditer(text):
        idx, domain, url, reach_cell, supports_cell, _notes = m.groups()
        n += 1
        d = by_domain.setdefault(domain, {"n": 0, "reach": 0, "supports": 0})
        d["n"] += 1

        reach_token = reach_cell.strip()
        # accept literal "[x]" or "`200`" / "`301`" etc as reachable
        if reach_token in PASS_TOKENS or reach_token.strip("`").startswith(("2", "30")):
            reach_pass += 1
            d["reach"] += 1

        s_token = supports_cell.strip()
        if s_token in PASS_TOKENS:
            supports_pass += 1
            d["supports"] += 1
        elif s_token in UNCERTAIN_TOKENS:
            uncertain += 1

    return {
        "agent": agent,
        "task_id": task,
        "n_sampled": n,
        "reachable_pass": reach_pass,
        "supports_pass": supports_pass,
        "uncertain": uncertain,
        "reachable_rate": round(reach_pass / n, 3) if n else 0.0,
        "supports_rate": round(supports_pass / n, 3) if n else 0.0,
        "by_domain": by_domain,
        "source_file": str(path.relative_to(ROOT)),
    }


def render_md(records: list[dict]) -> str:
    if not records:
        return "_no audit worksheets found_\n"

    by_agent: dict[str, list[dict]] = {}
    for r in records:
        by_agent.setdefault(r["agent"], []).append(r)

    lines = [
        "# Human URL Audit — Aggregated Leaderboard",
        "",
        "*Aggregated from `data/results/audit/*.audit.md`. `reach%` = fraction of sampled cited URLs that resolve on the sandbox; `support%` = fraction whose content actually backs the claim around them. `support%` is the truthfulness ground-truth for paper Section 5.*",
        "",
        "## Per-agent summary (mean across audited tasks)",
        "",
        "| Agent | Tasks audited | Total sampled | Mean reach% | Mean support% | Mean uncertain% |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for agent in sorted(by_agent):
        rs = by_agent[agent]
        n_total = sum(r["n_sampled"] for r in rs)
        if n_total == 0:
            continue
        mean_reach = sum(r["reachable_pass"] for r in rs) / n_total
        mean_supp = sum(r["supports_pass"] for r in rs) / n_total
        mean_unc = sum(r["uncertain"] for r in rs) / n_total
        lines.append(
            f"| {agent} | {len(rs)} | {n_total} | "
            f"{mean_reach * 100:.1f}% | **{mean_supp * 100:.1f}%** | {mean_unc * 100:.1f}% |"
        )

    lines += [
        "",
        "## Per-(agent, task) breakdown",
        "",
        "| Agent | Task | n | reach% | support% | uncertain% |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in sorted(records, key=lambda x: (-x["supports_rate"], x["agent"], x["task_id"])):
        lines.append(
            f"| {r['agent']} | {r['task_id']} | {r['n_sampled']} | "
            f"{r['reachable_rate'] * 100:.0f}% | **{r['supports_rate'] * 100:.0f}%** | "
            f"{(r['uncertain'] / r['n_sampled'] * 100) if r['n_sampled'] else 0:.0f}% |"
        )
    return "\n".join(lines) + "\n"


def main():
    if not AUDIT.exists():
        print(f"No audit dir: {AUDIT}", file=sys.stderr)
        sys.exit(1)

    records = []
    for p in sorted(AUDIT.glob("*.audit.md")):
        rec = parse_worksheet(p)
        if rec:
            records.append(rec)
            print(f"  parsed {p.name}: n={rec['n_sampled']}, reach={rec['reachable_rate']:.0%}, supports={rec['supports_rate']:.0%}")

    OUT_JSON.write_text(json.dumps(records, indent=2))
    OUT_MD.write_text(render_md(records))
    print(f"\nWROTE {OUT_JSON.relative_to(ROOT)}  ({len(records)} records)")
    print(f"WROTE {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
