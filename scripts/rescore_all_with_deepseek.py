"""Re-score every agent's 4-task output using the DeepSeek V3.2 judge.

This gives us a fresh, self-preference-free leaderboard where the
judge is a different-family model (deepseek-chat) from every agent
under test. Satisfies peer-review audit P0-1.

For each agent this script locates its markdown output(s), runs the
full 7-pillar composite scorer with run_judge=True, and writes
``data/results/final_<AGENT>_<TASK>.json`` (+ .answer.md).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from scripts.bench_v3 import score_from_file

RESULTS = ROOT / "data" / "results"
TASKS = ["dr_cross_v3_0001", "dr_cross_v3_0005", "dr_cross_v3_0006", "dr_cross_v3_0007"]

# Agent name → glob pattern(s) pointing at its markdown output
AGENTS: dict[str, list[str]] = {
    # GLM-4.7 agents × DeepSeek judge (first run, 2026-04-18)
    "camel-ai":                  ["camel-ai_{tid}.md"],
    "gpt-researcher":            ["gpt-researcher_{tid}.md",
                                   "final_gpt-researcher_{tid}.answer.md"],
    "react-qwen35plus":          ["final_react-qwen35plus_{tid}.answer.md"],
    "react-glm5":                ["final_react-glm5_{tid}.answer.md"],
    "deerflow-glm46":            ["final_deerflow-glm46_{tid}.answer.md"],
    "deerflow-glm46-new":        ["final_deerflow-glm46-new_{tid}.answer.md"],
    "deerflow-glm46-shim":       ["final_deerflow-glm46-shim_{tid}.answer.md"],
    "smolagents":                ["smolagents_{tid}.md"],
    # Role-swap: DeepSeek agent × GLM judge (second run, 2026-04-19)
    "camel-ai-ds":               ["camel-ai-ds_{tid}.md"],
    "gpt-researcher-ds":         ["gpt-researcher-ds_{tid}.md"],
    "smolagents-ds":             ["smolagents-ds_{tid}.md"],
    "deerflow-ds":               ["deerflow-ds_{tid}.md"],
    "dzhng-ds":                  ["dzhng-deep-research-ds_{tid}.md"],
    "odr-ds":                    ["open-deep-research-ds_{tid}.md"],
    "react-ds":                  ["react-ds_{tid}.md"],
    # GPT-5-chat-latest agent (Phase 10b)
    "gpt5chat":                  ["gpt5chat_{tid}.answer.md", "gpt5chat_{tid}.md"],
}


def find_source(agent: str, task_id: str) -> Path | None:
    for pat in AGENTS[agent]:
        candidate = RESULTS / pat.format(tid=task_id)
        if candidate.exists() and candidate.stat().st_size > 500:
            return candidate
    return None


def _resolve_tasks() -> list[str]:
    raw = os.environ.get("RESCORE_ONLY_TASKS")
    if not raw:
        return list(TASKS)
    ids: list[str] = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        ids.append(tok if tok.startswith("dr_cross") else f"dr_cross_v3_{tok}")
    return ids or list(TASKS)


def main() -> None:
    only_agent = os.environ.get("RESCORE_ONLY_AGENT")
    agents = [only_agent] if only_agent else list(AGENTS)
    tasks = _resolve_tasks()

    print(f"Judge: {os.environ.get('JUDGE_PROVIDER')} / "
          f"{os.environ.get('JUDGE_MODEL')} @ {os.environ.get('JUDGE_BASE_URL')}")
    print(f"Agents: {agents}")
    print(f"Tasks: {tasks}")
    print()

    rows: list[dict] = []
    for agent in agents:
        for tid in tasks:
            src = find_source(agent, tid)
            if src is None:
                print(f"  [skip] {agent}/{tid}: no markdown found")
                continue
            try:
                t0 = time.time()
                r = score_from_file(tid, agent, src, run_judge=True)
                elapsed = time.time() - t0
                out_json = RESULTS / f"final_{agent}_{tid}.json"
                out_answer = RESULTS / f"final_{agent}_{tid}.answer.md"
                out_json.write_text(json.dumps(r.to_dict(), indent=2, ensure_ascii=False))
                out_answer.write_text(src.read_text())
                p = r.pillars
                print(
                    f"  {agent}/{tid}  [{elapsed:>4.0f}s]  "
                    f"comp={r.composite:.3f}  "
                    f"md={p['markdown_structure'].score:.2f}  "
                    f"cite={p['citation'].score:.2f}  "
                    f"fkg={p['fact_kg'].score:.2f}  "
                    f"jdg={p['llm_judge'].score:.2f}  "
                    f"chk={p['checklist'].score:.2f}"
                )
                rows.append({
                    "agent": agent, "task": tid,
                    "composite": r.composite,
                    "elapsed": round(elapsed, 1),
                })
            except Exception as e:
                print(f"  [err ] {agent}/{tid}: {type(e).__name__}: {e}")

    # Write a summary
    out = RESULTS / "deepseek_judge_rescore_summary.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"\nSummary → {out}")


if __name__ == "__main__":
    main()
