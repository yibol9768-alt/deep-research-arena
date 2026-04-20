"""Classify existing agent answers into error categories.

Four exclusive primary classes:
  - tool_misuse:     ran 0–1 tools or repeated the same query 5+ times
  - hallucination_url: cited URLs not in allowed sandbox domains, or
                        referenced "placeholder" / fake-looking slugs
  - format_error:    answer is empty, <200 words, or raw JSON wrapping
                      didn't unwrap
  - timeout_or_empty: the run didn't produce an answer.md or it's literally
                      "[empty — agent failed to finish]"

Plus zero-or-more secondary flags per run:
  - no_inline_cites, zero_wiki_cites, only_one_source_host,
    answer_wrapped_in_json, very_short_report, very_long_report

Pure heuristic — no LLM calls. Produces a per-agent distribution table so
we can see "why" certain agents fail beyond their raw score.

Paper value: error taxonomy lets us say "DeepSeek-based agents don't fail
because they can't reason — they fail because they hallucinate URLs in
56% of runs." That's a diagnosis, not just a ranking.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results"

ALLOWED_HOSTS = {
    "localhost:7770",    # magento / One Stop Market
    "localhost:9999",    # postmill / reddit-like
    "localhost:8090",    # kiwix / Wikipedia
    "localhost:8023",    # gitlab (not live)
    "localhost:7780",    # shopping_admin (not live)
}

# Signatures that indicate a hallucinated URL (independent of host).
FAKE_SLUG_SIGNALS = [
    r"\(placeholder\)",
    r"example\.com",
    r"wikipedia\.org",   # real wikipedia URL = hallucinated (our sandbox uses kiwix)
    r"\.tavily\.",       # tavily self-reference = leaked from prompt
    r"onestopmarket\.com",  # fake brand we've seen DeepSeek invent
]


def _host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1).lower() if m else ""


def classify(answer: str, agent: str, task_id: str) -> dict:
    """Return {primary, secondary[], stats{}} for one run."""
    stats = {
        "words": len(answer.split()),
        "cites": 0,
        "hosts": Counter(),
        "fake_signals": [],
        "wrapped_json": False,
    }

    # 1. Detect JSON wrapping
    trimmed = answer.strip()
    if trimmed.startswith('{"markdown_report"'):
        stats["wrapped_json"] = True

    # 2. Inline citations + hosts
    for m in re.finditer(r'\[[^\]]+\]\((https?://[^)\s]+)\)', answer):
        stats["cites"] += 1
        h = _host_of(m.group(1))
        if h:
            stats["hosts"][h] += 1

    # 3. Detect fake-signal URLs anywhere in text
    for pat in FAKE_SLUG_SIGNALS:
        if re.search(pat, answer, re.IGNORECASE):
            stats["fake_signals"].append(pat)

    # 4. Off-sandbox citations
    off_sandbox = sum(
        v for h, v in stats["hosts"].items()
        if not any(ah in h for ah in ALLOWED_HOSTS)
    )
    stats["off_sandbox_cites"] = off_sandbox

    # --- Primary classification ---
    primary = None
    if stats["words"] < 50 or "failed to finish" in answer.lower():
        primary = "timeout_or_empty"
    elif stats["wrapped_json"] and stats["words"] < 400:
        primary = "format_error"
    elif stats["fake_signals"] or off_sandbox >= 2:
        primary = "hallucination_url"
    elif stats["cites"] == 0 and stats["words"] >= 200:
        # Wrote a full-length report with no grounding
        primary = "hallucination_url"
    else:
        primary = "ok"

    # --- Secondary flags ---
    secondary = []
    if stats["cites"] == 0:
        secondary.append("no_inline_cites")
    if not any("8090" in h for h in stats["hosts"]):
        secondary.append("zero_wiki_cites")
    if len(stats["hosts"]) == 1:
        secondary.append("only_one_source_host")
    if stats["wrapped_json"]:
        secondary.append("answer_wrapped_in_json")
    if stats["words"] < 500:
        secondary.append("very_short_report")
    if stats["words"] > 3500:
        secondary.append("very_long_report")

    return {
        "agent": agent,
        "task_id": task_id,
        "primary": primary,
        "secondary": secondary,
        "stats": {
            "words": stats["words"],
            "cites": stats["cites"],
            "hosts": dict(stats["hosts"]),
            "fake_signals": stats["fake_signals"],
            "off_sandbox_cites": off_sandbox,
            "wrapped_json": stats["wrapped_json"],
        },
    }


def scan_all() -> list[dict]:
    rows = []
    for p in sorted(RESULTS.glob("*.answer.md")):
        # Parse filename: final_<agent>_<task>.answer.md or <agent>_<task>.answer.md
        stem = p.name.replace(".answer.md", "")
        if stem.startswith("final_"):
            stem = stem[len("final_"):]
        # task_id is always dr_*... starting from some point
        m = re.search(r"(dr_\S+)$", stem)
        if not m:
            continue
        task_id = m.group(1)
        agent = stem[: stem.rfind("_" + task_id)] if ("_" + task_id) in stem else stem.replace("_" + task_id, "")
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rows.append(classify(text, agent, task_id))
    return rows


def summarize(rows: list[dict]) -> dict:
    by_agent: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        by_agent[r["agent"]][r["primary"]] += 1

    # Secondary flag rate per agent
    by_agent_sec: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        for f in r["secondary"]:
            by_agent_sec[r["agent"]][f] += 1

    total_by_primary = Counter(r["primary"] for r in rows)
    return {
        "total_runs": len(rows),
        "total_by_primary": dict(total_by_primary),
        "by_agent_primary": {a: dict(c) for a, c in by_agent.items()},
        "by_agent_secondary": {a: dict(c) for a, c in by_agent_sec.items()},
    }


def render(rows: list[dict], summary: dict) -> str:
    lines = [
        "# Error Taxonomy — Per-Agent Failure Distribution",
        "",
        f"**{summary['total_runs']}** runs scanned (heuristic, no LLM calls).",
        "",
        "## Totals by primary class",
        "",
    ]
    for k, v in sorted(summary["total_by_primary"].items(), key=lambda x: -x[1]):
        lines.append(f"- **{k}**: {v} runs")

    lines += [
        "",
        "## Per-agent primary class distribution",
        "",
        "| Agent | ok | tool_misuse | hallucination_url | format_error | timeout_or_empty | total |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    agents = sorted(summary["by_agent_primary"].keys())
    for a in agents:
        d = summary["by_agent_primary"][a]
        total = sum(d.values())
        lines.append(
            f"| {a} | {d.get('ok',0)} | {d.get('tool_misuse',0)} | "
            f"{d.get('hallucination_url',0)} | {d.get('format_error',0)} | "
            f"{d.get('timeout_or_empty',0)} | {total} |"
        )

    lines += [
        "",
        "## Top secondary flags per agent",
        "",
    ]
    for a in agents:
        d = summary["by_agent_secondary"].get(a, {})
        if not d:
            continue
        flags_sorted = sorted(d.items(), key=lambda x: -x[1])[:5]
        flags_str = ", ".join(f"{f}({c})" for f, c in flags_sorted)
        lines.append(f"- **{a}**: {flags_str}")

    lines += [
        "",
        "## What this tells us",
        "",
        "- `hallucination_url` rate ≥ 50% on an agent → that agent is NOT graded fairly by our citation pillar (it's gaming URLs).",
        "- `format_error` rate > 20% → runner issue (e.g. JSON wrap unwrapping failed — check the runner code, not the agent).",
        "- `tool_misuse` rate high → prompting issue — try a more explicit ReAct template.",
        "- `zero_wiki_cites` dominant across agents → shim indexing bug or agents don't know to query wikipedia. Good signal post-#52.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    rows = scan_all()
    if not rows:
        print("no answer.md files found")
        return 1
    summary = summarize(rows)
    out_json = RESULTS / "error_taxonomy.json"
    out_md = RESULTS / "ERROR_TAXONOMY.md"
    out_json.write_text(json.dumps({"rows": rows, "summary": summary}, indent=2, ensure_ascii=False))
    out_md.write_text(render(rows, summary))
    print(f"Wrote {out_md}")
    print(f"\nTotals: {summary['total_by_primary']}")
    print(f"\nBy agent primary classes (top 5):")
    for a in sorted(summary["by_agent_primary"].keys()):
        d = summary["by_agent_primary"][a]
        print(f"  {a:<24} ok={d.get('ok',0)} halluc={d.get('hallucination_url',0)} format={d.get('format_error',0)} fail={d.get('timeout_or_empty',0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
