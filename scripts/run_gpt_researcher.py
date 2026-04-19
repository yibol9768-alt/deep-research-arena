"""Run GPT-Researcher on the 4 cross-site tasks via our sandbox search shim.

Zero code changes to gpt_researcher itself — we only monkey-patch the
Tavily retriever's `base_url` at import time so its /search calls hit our
shim instead of api.tavily.com.

Environment (set before invoking):
    GPTR_SHIM_URL=http://localhost:8081   # default
    OPENAI_API_KEY=<Coding Plan key>
    OPENAI_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
    FAST_LLM=openai:deepseek-chat
    SMART_LLM=openai:deepseek-chat
    STRATEGIC_LLM=openai:deepseek-chat

Outputs:
    data/results/gpt-researcher_dr_cross_v3_<TASK>.md
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SHIM = os.environ.get("GPTR_SHIM_URL", "http://localhost:8081")
os.environ.setdefault("TAVILY_API_KEY", "tvly-shim-fake")

# Monkey-patch tavily retriever base URL before any GPT-Researcher imports.
import gpt_researcher.retrievers.tavily.tavily_search as _tm  # noqa: E402
_orig_init = _tm.TavilySearch.__init__
def _patched_init(self, *a, **kw):
    _orig_init(self, *a, **kw)
    self.base_url = f"{SHIM}/search"
_tm.TavilySearch.__init__ = _patched_init

# Make GPT-Researcher use our LLM config. It honours the "<provider>:<model>"
# syntax in *_LLM env vars; "openai:deepseek-chat" means OpenAI-compat (shim goes
# to Coding Plan) with model name deepseek-chat.
for var, default in [
    ("FAST_LLM", "openai:deepseek-chat"),
    ("SMART_LLM", "openai:deepseek-chat"),
    ("STRATEGIC_LLM", "openai:deepseek-chat"),
    ("RETRIEVER", "tavily"),
    ("EMBEDDING", "openai:embedding-3"),
]:
    os.environ.setdefault(var, default)

from gpt_researcher import GPTResearcher  # noqa: E402


TASKS = [
    "dr_cross_v3_0001",
    "dr_cross_v3_0005",
    "dr_cross_v3_0006",
    "dr_cross_v3_0007",
]
TASKS_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site"
OUT_DIR = ROOT / "data" / "results"


def _load_intent(task_id: str) -> str:
    cfg = json.loads((TASKS_DIR / f"{task_id}.json").read_text())
    return cfg.get("intent") or cfg.get("description") or ""


async def _run_one(task_id: str) -> None:
    intent = _load_intent(task_id)
    print(f"\n{'='*60}\nGPT-Researcher: {task_id}\n{'='*60}")
    t0 = time.time()
    try:
        researcher = GPTResearcher(query=intent, report_type="research_report", tone="objective")
        await researcher.conduct_research()
        report = await researcher.write_report()
    except Exception as e:
        report = f"(GPT-Researcher error: {type(e).__name__}: {e})"
    elapsed = time.time() - t0

    out_path = OUT_DIR / f"gpt-researcher_{task_id}.md"
    out_path.write_text(report or "(empty)")
    print(f"Finished in {elapsed:.0f}s, {len(report)} chars → {out_path}")


async def main() -> None:
    only = os.environ.get("GPTR_ONLY_TASK")
    tasks = [only] if only else TASKS
    for t in tasks:
        try:
            await _run_one(t)
        except Exception as e:
            print(f"Task {t} failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
