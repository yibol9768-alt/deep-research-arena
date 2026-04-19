"""Run LangChain's `open_deep_research` on the 4 cross-site tasks via the shim.

Zero code changes to open_deep_research — we only monkey-patch
`tavily.async_tavily.AsyncTavilyClient.__init__` so its base URL hits
our sandbox shim instead of api.tavily.com.

Env (set before invoking):
    ODR_SHIM_URL=http://localhost:8081           # default
    OPENAI_API_KEY=<Coding Plan key>
    OPENAI_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
    TAVILY_API_KEY=tvly-anything

Outputs:
    data/results/open-deep-research_dr_cross_v3_<TASK>.md
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

SHIM = os.environ.get("ODR_SHIM_URL", "http://localhost:8081")
os.environ.setdefault("TAVILY_API_KEY", "tvly-shim-fake")
os.environ.setdefault("SEARCH_API", "tavily")

# Monkey-patch Tavily async client BEFORE open_deep_research imports it.
import tavily.async_tavily as _at  # noqa: E402
_orig_init = _at.AsyncTavilyClient.__init__

def _patched_init(self, api_key=None, *a, **kw):
    kw.setdefault("api_base_url", SHIM)
    _orig_init(self, api_key=api_key, *a, **kw)

_at.AsyncTavilyClient.__init__ = _patched_init

# Same for the sync Tavily client — some paths inside ODR/langchain-tavily use it.
try:
    import tavily as _tav  # noqa: E402
    if hasattr(_tav, "TavilyClient"):
        _orig_sync = _tav.TavilyClient.__init__

        def _patched_sync(self, api_key=None, *a, **kw):
            kw.setdefault("api_base_url", SHIM)
            _orig_sync(self, api_key=api_key, *a, **kw)

        _tav.TavilyClient.__init__ = _patched_sync
except Exception:
    pass

from langchain_core.messages import HumanMessage  # noqa: E402

# Patch ChatOpenAI.with_structured_output to use method="json_mode" — DeepSeek
# only supports response_format={"type":"json_object"}, not json_schema.
try:
    from langchain_openai.chat_models.base import BaseChatOpenAI as _BCO  # noqa
    _orig_wso = _BCO.with_structured_output

    def _patched_wso(self, schema, *, method=None, **kw):
        # DeepSeek supports function_calling but NOT json_schema (strict) and
        # requires prompt to contain "json" for json_mode. function_calling
        # is cleanest.
        return _orig_wso(self, schema, method="function_calling", **kw)

    _BCO.with_structured_output = _patched_wso
    print("patched ChatOpenAI.with_structured_output → method=json_mode")
except Exception as e:
    print(f"warn: ChatOpenAI patch failed: {e}")

from open_deep_research.deep_researcher import deep_researcher  # noqa: E402

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
    print(f"\n{'='*60}\nopen-deep-research: {task_id}\n{'='*60}")
    cfg = {
        "configurable": {
            "research_model": "openai:deepseek-chat",
            "summarization_model": "openai:deepseek-chat",
            "compression_model": "openai:deepseek-chat",
            "final_report_model": "openai:deepseek-chat",
            "search_api": "tavily",
            "allow_clarification": False,
            "max_researcher_iterations": 3,
            "max_react_tool_calls": 6,
            "max_concurrent_research_units": 2,
        }
    }
    t0 = time.time()
    try:
        out = await deep_researcher.ainvoke(
            {"messages": [HumanMessage(content=intent)]}, cfg
        )
        report = out.get("final_report") or "(no final_report key)"
    except Exception as e:
        report = f"(open_deep_research error: {type(e).__name__}: {e})"
    elapsed = time.time() - t0

    out_path = OUT_DIR / f"open-deep-research_{task_id}.md"
    out_path.write_text(report or "(empty)")
    print(f"Finished in {elapsed:.0f}s, {len(report)} chars → {out_path}")


async def main() -> None:
    only = os.environ.get("ODR_ONLY_TASK")
    tasks = [only] if only else TASKS
    for t in tasks:
        try:
            await _run_one(t)
        except Exception as e:
            print(f"Task {t} failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
