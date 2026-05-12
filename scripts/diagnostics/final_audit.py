"""Final per-framework forensic audit:
  For each of the 14 framework names (13 in leaderboard + qx-agents filtered),
  classify EVERY clean pair into one of:
    AGENT-FAULT  (refused, errored, empty, fabricated URLs, wrong URL format)
    OUR-FAULT    (our scoring or config issue penalized a real research output)
    OK           (genuinely productive run)
  Then summarize per agent: "score gap reflects agent quality" vs "we may
  have under-penalized agent".
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/opt/deep_reserch")
DIR = ROOT / "data/results/deep_v3"
sys.path.insert(0, str(ROOT))
from src.verifiers.url_coverage_verifier import _canonical, _extract_cited_urls

NAME_RE = re.compile(r"^([A-Za-z0-9_\-]+?)__dr_cross_deep_(\d{4})_matrix\.score\.json$")
RUNNER_FAIL_RE = re.compile(
    r"^\(\s*[A-Za-z][\w\- ]*\s+produced no report\s+after\s+\d+\s*s", re.IGNORECASE,
)
RUNNER_EXC_RE = re.compile(r"^\(\s*[A-Za-z][\w\- ]*\s+(error|stderr)\s*:", re.IGNORECASE)
REFUSAL_HEADS = (
    "please confirm", "i cannot", "based on the analysis", "given the scope",
    "i will need", "(empty ",
)
SANDBOX_HOSTS = ("localhost:7770", "localhost:9999", "localhost:8090")


def _gp(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def classify(d) -> str:
    """Return AGENT-FAULT-{kind} / OUR-FAULT-{kind} / OK-{quality}."""
    chars = d.get("answer_chars", 0) or 0
    if chars < 100:
        return "AGENT-FAULT-empty"

    ans_path = d.get("answer_path")
    text = ""
    if ans_path:
        a = Path(ans_path) if Path(ans_path).is_absolute() else ROOT / ans_path
        if a.exists():
            text = a.read_text(encoding="utf-8", errors="replace")
    if not text:
        return "AGENT-FAULT-no-md"

    head = text[:300].lstrip()
    if RUNNER_FAIL_RE.match(head):
        return "AGENT-FAULT-runner-crash"
    if RUNNER_EXC_RE.match(head):
        return "AGENT-FAULT-runner-exception"
    if any(head.lower().startswith(p) for p in REFUSAL_HEADS):
        return "AGENT-FAULT-refusal"

    if chars < 1000:
        return "AGENT-FAULT-tiny"

    cited_canon, _ = _extract_cited_urls(text)
    if not cited_canon:
        return "AGENT-FAULT-no-urls"

    sandbox = [u for u in cited_canon if any(h in u for h in SANDBOX_HOSTS)]
    external = [u for u in cited_canon if u not in sandbox]
    ext_ratio = len(external) / max(1, len(cited_canon))

    reach = _gp(d, "url_reachability", "score", default=0.0) or 0.0
    cited_total = _gp(d, "url_reachability", "details", "cited_total", default=0)
    http_200 = _gp(d, "url_reachability", "details", "http_200", default=0)
    http_4xx = _gp(d, "url_reachability", "details", "http_4xx", default=0)
    must_hit = _gp(d, "url_coverage", "details", "must_cite_hit", default=0)
    c2 = _gp(d, "composite", "composite_v2", default=0.0) or 0.0

    if ext_ratio > 0.5:
        return "AGENT-FAULT-external-urls"
    # All sandbox URLs, but all 4xx → agent emitted wrong path format
    if reach == 0 and len(sandbox) > 5 and http_4xx > 0:
        return "AGENT-FAULT-wrong-url-format"
    # 0 reach but reasonable cited count and ALSO must_hit > 0 — canonical
    # form matched golden but raw probe failed. Could be our normalizer being
    # too generous (Kiwix lowercase, etc.) OR agent's URL form just wrong.
    if reach == 0 and must_hit > 0:
        return "OUR-FAULT-canonical-vs-raw"
    if c2 > 0.15:
        return "OK-strong"
    if c2 > 0.05:
        return "OK-mid"
    if c2 > 0:
        return "OK-weak"
    if reach > 0 and c2 == 0:
        # reach worked but composite still 0 — usually checklist gave 0 or
        # truth factor=0 from quote_match/nli=0. Still agent fault (no
        # ground truth claims).
        return "AGENT-FAULT-no-grounded-claims"
    return "AGENT-FAULT-other-zero"


def main():
    by_agent: dict[str, list[dict]] = defaultdict(list)
    for fp in sorted(DIR.glob("*_matrix.score.json")):
        m = NAME_RE.match(fp.name)
        if not m:
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        d["_agent"] = m.group(1)
        d["_task"] = m.group(2)
        by_agent[m.group(1)].append(d)

    print(f"{'agent':<25} {'n':>3}  {'agent-fault':>12} {'our-fault':>10} {'ok':>6}  verdict")
    print("-" * 100)
    for agent in sorted(by_agent.keys()):
        rows = by_agent[agent]
        labels = Counter(classify(d) for d in rows)
        agent_fault = sum(c for k, c in labels.items() if k.startswith("AGENT-FAULT"))
        our_fault = sum(c for k, c in labels.items() if k.startswith("OUR-FAULT"))
        ok = sum(c for k, c in labels.items() if k.startswith("OK"))

        # Verdict
        n = len(rows)
        if our_fault == 0:
            verdict = "✓ all gaps are agent quality"
        elif our_fault / max(1, n) > 0.2:
            verdict = f"⚠ {our_fault}/{n} pairs may be under-scored by us"
        else:
            verdict = f"~ {our_fault}/{n} pairs OUR-FAULT (edge case)"
        print(f"  {agent:<23} {n:>3}  {agent_fault:>12} {our_fault:>10} {ok:>6}  {verdict}")

        # Show detailed breakdown for any agent with >0 OUR-FAULT
        if our_fault > 0:
            for k, c in sorted(labels.items()):
                if k.startswith("OUR-FAULT"):
                    print(f"      {k}: {c}")


if __name__ == "__main__":
    main()
