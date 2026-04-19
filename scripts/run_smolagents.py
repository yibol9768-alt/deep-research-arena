"""Run huggingface/smolagents CodeAgent on 4 cross-site tasks via the shim.

smolagents' `examples/open_deep_research` is a code-as-action agent: the
LLM writes Python snippets that call tools like `web_search` and
`visit_webpage`. We reuse that pattern but route search through our
shim's Tavily endpoint.

Env:
    SMOL_SHIM_URL=http://localhost:8081
    OPENAI_API_KEY=<Coding Plan key>
    OPENAI_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
    TAVILY_API_KEY=tvly-anything

Outputs:
    data/results/smolagents_dr_cross_v3_<TASK>.md
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SHIM = os.environ.get("SMOL_SHIM_URL", "http://localhost:8081")
os.environ.setdefault("TAVILY_API_KEY", "tvly-shim-fake")

# Patch Tavily client → shim
try:
    import tavily
    _orig = tavily.TavilyClient.__init__

    def _patched(self, api_key=None, *a, **kw):
        kw.pop("api_base_url", None)
        _orig(self, api_key, *a, **kw)
        self.base_url = SHIM

    tavily.TavilyClient.__init__ = _patched
except Exception as e:
    print(f"warn: tavily patch: {e}")


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


def _build_agent():
    from smolagents import CodeAgent, OpenAIServerModel, ApiWebSearchTool
    from smolagents.default_tools import VisitWebpageTool

    # GLM / DeepSeek both habitually emit `</code>` instead of the
    # smolagents sentinel `<end_code>`, which breaks the CodeAgent parser
    # and leaves the agent in zero-tool-call hallucination mode. Patch
    # the model output on the way out.
    class SentinelRewriteModel(OpenAIServerModel):
        def generate(self, *a, **kw):  # type: ignore[override]
            out = super().generate(*a, **kw)
            # smolagents ≥1.20 returns a ChatMessage with .content
            if hasattr(out, "content") and isinstance(out.content, str):
                out.content = out.content.replace("</code>", "<end_code>")
            return out

    model = SentinelRewriteModel(
        model_id="deepseek-chat",
        api_base=os.environ.get("OPENAI_BASE_URL"),
        api_key=os.environ.get("OPENAI_API_KEY"),
    )
    # Point smolagents' ApiWebSearchTool at our shim's /search endpoint.
    # The shim accepts any Bearer token and returns Tavily-schema results.
    search_tool = ApiWebSearchTool(
        endpoint=f"{SHIM}/search",
        api_key=os.environ.get("TAVILY_API_KEY", "tvly-shim-fake"),
        headers={"Content-Type": "application/json"},
    )
    tools = [search_tool, VisitWebpageTool()]
    return CodeAgent(tools=tools, model=model, max_steps=12,
                     additional_authorized_imports=["requests", "json", "bs4"])


def _run_one(task_id: str) -> None:
    intent = _load_intent(task_id)
    print(f"\n{'='*60}\nsmolagents: {task_id}\n{'='*60}")
    t0 = time.time()
    try:
        agent = _build_agent()
        report = agent.run(intent)
        report = report if isinstance(report, str) else str(report)
    except Exception as e:
        report = f"(smolagents error: {type(e).__name__}: {e})"
    elapsed = time.time() - t0
    out_path = OUT_DIR / f"smolagents_{task_id}.md"
    out_path.write_text(report or "(empty)")
    print(f"Finished in {elapsed:.0f}s, {len(report)} chars → {out_path}")


def main() -> None:
    only = os.environ.get("SMOL_ONLY_TASK")
    tasks = [only] if only else TASKS
    for t in tasks:
        try:
            _run_one(t)
        except Exception as e:
            print(f"Task {t} failed: {e}")


if __name__ == "__main__":
    main()
