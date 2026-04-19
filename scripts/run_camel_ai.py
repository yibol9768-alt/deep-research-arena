"""Run CAMEL-AI ChatAgent+SearchToolkit on the 4 cross-site tasks via the shim.

CAMEL doesn't ship a one-shot DeepResearch agent, so we compose
`ChatAgent(SearchToolkit.search_tavily + tavily_extract)` with a
deep-research system prompt. Tavily base URL is monkey-patched to our
sandbox shim.

Env (set before invoking):
    CAMEL_SHIM_URL=http://localhost:8081
    TAVILY_API_KEY=tvly-anything
    OPENAI_COMPATIBLE_API_KEY=<GLM Coding Plan key>
    OPENAI_COMPATIBLE_API_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4

Outputs:
    data/results/camel-ai_dr_cross_v3_<TASK>.md
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SHIM = os.environ.get("CAMEL_SHIM_URL", "http://localhost:8081")
os.environ.setdefault("TAVILY_API_KEY", "tvly-shim-fake")

# Monkey-patch Tavily client BEFORE camel imports it
import tavily  # noqa: E402
_orig_init = tavily.TavilyClient.__init__


def _patched_init(self, api_key=None, *a, **kw):
    kw.pop("api_base_url", None)
    _orig_init(self, api_key, *a, **kw)
    # Overwrite the per-instance attribute that TavilyClient uses.
    self.base_url = SHIM
    if hasattr(self, "_client_creator"):
        # some SDK versions have an internal client_creator — kick it if present
        pass


tavily.TavilyClient.__init__ = _patched_init
if hasattr(tavily, "AsyncTavilyClient"):
    _orig_async = tavily.AsyncTavilyClient.__init__

    def _patched_async(self, api_key=None, *a, **kw):
        kw.pop("api_base_url", None)
        _orig_async(self, api_key, *a, **kw)
        self.base_url = SHIM

    tavily.AsyncTavilyClient.__init__ = _patched_async


# OpenAI-compat LLM config
OPENAI_KEY = os.environ.get("OPENAI_COMPATIBLE_API_KEY") or os.environ.get("OPENAI_API_KEY")
OPENAI_BASE = os.environ.get("OPENAI_COMPATIBLE_API_BASE_URL") or os.environ.get(
    "OPENAI_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4"
)

from camel.agents import ChatAgent  # noqa: E402
from camel.models import ModelFactory  # noqa: E402
from camel.toolkits import SearchToolkit, FunctionTool  # noqa: E402
from camel.types import ModelPlatformType  # noqa: E402


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


_SYSTEM = (
    "You are a deep-research agent. Answer the user's question by calling "
    "the search tool multiple times on focused sub-queries, then write a "
    "comprehensive markdown report. Every factual claim MUST be backed by "
    "a markdown link `[descriptive text](url)` to a specific page you "
    "cited. Aim for 1500-2500 words with clear section headings. Prefer "
    "crawling individual product/article/post pages over relying only on "
    "search snippets."
)


def _build_agent():
    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type="deepseek-chat",
        url=OPENAI_BASE,
        api_key=OPENAI_KEY,
        model_config_dict={"temperature": 0.2, "max_tokens": 4096},
    )
    tk = SearchToolkit()
    tools = [
        FunctionTool(tk.search_tavily),
    ]
    # tavily_extract only available in recent camel — try to add it
    for attr in ("tavily_extract", "search_tavily_extract"):
        if hasattr(tk, attr):
            tools.append(FunctionTool(getattr(tk, attr)))
            break
    return ChatAgent(system_message=_SYSTEM, model=model, tools=tools)


def _run_one(task_id: str) -> None:
    intent = _load_intent(task_id)
    print(f"\n{'='*60}\ncamel-ai: {task_id}\n{'='*60}")
    t0 = time.time()
    try:
        agent = _build_agent()
        resp = agent.step(intent)
        report = resp.msg.content if resp.msg else "(empty)"
    except Exception as e:
        report = f"(camel-ai error: {type(e).__name__}: {e})"
    elapsed = time.time() - t0
    out_path = OUT_DIR / f"camel-ai_{task_id}.md"
    out_path.write_text(report or "(empty)")
    print(f"Finished in {elapsed:.0f}s, {len(report)} chars → {out_path}")


def main() -> None:
    only = os.environ.get("CAMEL_ONLY_TASK")
    tasks = [only] if only else TASKS
    for t in tasks:
        try:
            _run_one(t)
        except Exception as e:
            print(f"Task {t} failed: {e}")


if __name__ == "__main__":
    main()
