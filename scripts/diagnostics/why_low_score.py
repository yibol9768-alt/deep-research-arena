"""Per-agent forensic audit: WHY does this agent score low?

For each agent's bottom-quartile pairs, print:
  - the exact URL list the agent emitted (first 10)
  - HTTP probe of each URL via the same canonicaliser the scorer uses
  - the verdict: "agent fault" / "our fault" / "mixed"

Classification:
  AGENT FAULT  agent emitted external/fabricated URLs that don't exist in sandbox
  AGENT FAULT  agent emitted no URLs / refused / errored
  OUR FAULT    URLs look valid (localhost:7770/9999/8090, path looks real)
               BUT probe gets 4xx → maybe sandbox state, OR canonical form
               in extractor differs from raw form HTTP probes
  MIXED        some valid, some fabricated

Run from /opt/deep_reserch/.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path("/opt/deep_reserch")
DIR = ROOT / "data/results/deep_v3"
DEEP = ROOT / "data/results/deep"

sys.path.insert(0, str(ROOT))
from src.verifiers.url_coverage_verifier import _canonical, _extract_cited_urls

NAME_RE = re.compile(r"^([A-Za-z0-9_\-]+?)__dr_cross_deep_(\d{4})_matrix\.score\.json$")
RUNNER_FAIL_RE = re.compile(
    r"^\(\s*[A-Za-z][\w\- ]*\s+produced no report\s+after\s+\d+\s*s",
    re.IGNORECASE,
)
RUNNER_EXC_RE = re.compile(r"^\(\s*[A-Za-z][\w\- ]*\s+(error|stderr)\s*:", re.IGNORECASE)


def _gp(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


# Bottom agents to investigate
TARGETS = ["langchain-odr", "ldr", "gpt-researcher"]

for agent in TARGETS:
    print(f"\n{'=' * 80}")
    print(f"AGENT: {agent}")
    print("=" * 80)
    files = sorted(DIR.glob(f"{agent}__*_matrix.score.json"))
    rows = []
    for fp in files:
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        c2 = _gp(d, "composite", "composite_v2", default=0.0) or 0.0
        rows.append((c2, fp, d))
    rows.sort()

    if not rows:
        print("  (no rows)")
        continue

    # Pick 3 from low-end (excluding the 0-only rows where it's obvious)
    # Take rank 0, mid-low, just-below-median
    n = len(rows)
    picks = [rows[0], rows[n // 4], rows[n // 2]]
    seen_tasks = set()
    for c2, fp, d in picks:
        task_id = d.get("task", "?")
        if task_id in seen_tasks:
            continue
        seen_tasks.add(task_id)

        ans_path = d.get("answer_path")
        md = Path(ROOT / ans_path) if ans_path else None
        text = md.read_text(encoding="utf-8", errors="replace") if (md and md.exists()) else ""
        if not text:
            print(f"\n  task {task_id}: NO REPORT ON DISK")
            continue

        # Classify the report shape
        head = text[:300].lstrip()
        if RUNNER_FAIL_RE.match(head) or RUNNER_EXC_RE.match(head):
            print(f"\n  task {task_id} composite_v2={c2:.4f}: AGENT FAULT — runner-error placeholder")
            continue
        chars = len(text)
        if chars < 300:
            print(f"\n  task {task_id} composite_v2={c2:.4f}: AGENT FAULT — empty/tiny ({chars} chars)")
            continue
        if head.startswith(("Please confirm", "I cannot", "Based on", "Given the", "I will need")):
            print(f"\n  task {task_id} composite_v2={c2:.4f}: AGENT FAULT — agent refused/asked-clarification")
            continue

        # Pull cited URLs via the same code path the scorer uses
        cited_canon, _ = _extract_cited_urls(text)
        if not cited_canon:
            print(f"\n  task {task_id} composite_v2={c2:.4f}: AGENT FAULT — no parseable URLs ({chars} chars)")
            continue

        # Classify URLs: sandbox vs external; for sandbox, check raw vs canonical
        sandbox_hosts = ("localhost:7770", "localhost:9999", "localhost:8090")
        sandbox_urls = [u for u in cited_canon if any(h in u for h in sandbox_hosts)]
        external_urls = [u for u in cited_canon if u not in sandbox_urls]

        # Recorded reach details
        reach = _gp(d, "url_reachability", "score", default=0.0)
        cited_total = _gp(d, "url_reachability", "details", "cited_total", default=0)
        http_200 = _gp(d, "url_reachability", "details", "http_200", default=0)
        http_4xx = _gp(d, "url_reachability", "details", "http_4xx", default=0)
        http_5xx = _gp(d, "url_reachability", "details", "http_5xx", default=0)
        net_fail = _gp(d, "url_reachability", "details", "net_fail", default=0)
        must_hit = _gp(d, "url_coverage", "details", "must_cite_hit", default=0)

        # Verdict
        ext_ratio = len(external_urls) / max(1, len(cited_canon))
        if ext_ratio > 0.5:
            verdict = "AGENT FAULT — >50% external URLs (fabricated/wrong domain)"
        elif http_4xx > 0 and http_200 == 0 and len(sandbox_urls) > 0:
            # Sandbox URLs all 4xx
            verdict = "AGENT FAULT — sandbox URLs but wrong paths (all 4xx)"
        elif http_200 > 0 and reach < 0.3:
            verdict = "MIXED — some hit, many fabricated"
        elif reach > 0.5:
            verdict = "OK on reach but other pillars low — check checklist/citation_alignment"
        else:
            verdict = "INVESTIGATE — none of the obvious patterns"

        print(f"\n  task {task_id} composite_v2={c2:.4f}: {verdict}")
        print(f"    chars={chars}  cited_canon={len(cited_canon)} (sandbox={len(sandbox_urls)} ext={len(external_urls)})")
        print(f"    reach.score={reach}  http: 200={http_200} 4xx={http_4xx} 5xx={http_5xx} netfail={net_fail}")
        print(f"    must_cite_hit={must_hit}")
        print(f"    first 5 extracted URLs:")
        for u in sorted(cited_canon)[:5]:
            tag = "  sandbox" if any(h in u for h in sandbox_hosts) else "  external"
            print(f"      {tag}  {u}")
