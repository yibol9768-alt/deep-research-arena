"""Run LearningCircuit/local-deep-research on 4 cross-site tasks via the shim.

Zero code changes — monkey-patch Tavily base URL to shim. The framework
also supports SearXNG; we'd wire that next if needed.

Env:
    LDR_SHIM_URL=http://localhost:8081
    OPENAI_API_KEY=<Coding Plan key>
    OPENAI_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
    TAVILY_API_KEY=tvly-anything

Outputs:
    data/results/local-deep-research_dr_cross_v3_<TASK>.md
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SHIM = os.environ.get("LDR_SHIM_URL", "http://localhost:8081")
os.environ.setdefault("TAVILY_API_KEY", "tvly-shim-fake")
# LDR 1.5.x env pattern: settings key "a.b.c" → LDR_A_B_C (single underscores)
os.environ.setdefault("LDR_LLM_PROVIDER", "openai_endpoint")
os.environ.setdefault("LDR_LLM_MODEL", "deepseek-chat")
os.environ.setdefault("LDR_LLM_OPENAI_ENDPOINT_URL",
                      os.environ.get("OPENAI_BASE_URL",
                                     "https://open.bigmodel.cn/api/coding/paas/v4"))
# Prefer user-supplied OPENAI_API_KEY; fall back to empty so LDR uses placeholder.
os.environ.setdefault("LDR_LLM_OPENAI_ENDPOINT_API_KEY",
                      os.environ.get("OPENAI_API_KEY", ""))
os.environ.setdefault("LDR_SEARCH_TOOL", "tavily")
os.environ.setdefault("LDR_SEARCH_ENGINE_WEB_TAVILY_API_KEY",
                      os.environ.get("TAVILY_API_KEY", "tvly-shim-fake"))
os.environ.setdefault("LDR_SEARCH_SEARXNG_INSTANCE_URL",
                      os.environ.get("LDR_SHIM_URL", "http://localhost:8081"))

# Patch both (a) the tavily-python client and (b) LDR's internal
# TavilySearchEngine, which uses its OWN base_url independently.
try:
    import tavily
    _orig = tavily.TavilyClient.__init__

    def _patched(self, api_key=None, *a, **kw):
        kw.pop("api_base_url", None)
        _orig(self, api_key, *a, **kw)
        self.base_url = SHIM

    tavily.TavilyClient.__init__ = _patched
    if hasattr(tavily, "AsyncTavilyClient"):
        _a = tavily.AsyncTavilyClient.__init__

        def _pa(self, api_key=None, *a, **kw):
            kw.pop("api_base_url", None)
            _a(self, api_key, *a, **kw)
            self.base_url = SHIM

        tavily.AsyncTavilyClient.__init__ = _pa
except Exception as e:
    print(f"warn: tavily patch failed: {e}")

try:
    from local_deep_research.web_search_engines.engines import search_engine_tavily as _ldrt
    _orig_init_ldr = _ldrt.TavilySearchEngine.__init__

    def _patched_ldr(self, *a, **kw):
        _orig_init_ldr(self, *a, **kw)
        self.base_url = SHIM

    _ldrt.TavilySearchEngine.__init__ = _patched_ldr
    print(f"patched LDR TavilySearchEngine.base_url → {SHIM}")
except Exception as e:
    print(f"warn: LDR tavily patch failed: {e}")


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


def _run_one(task_id: str) -> None:
    intent = _load_intent(task_id)
    print(f"\n{'='*60}\nlocal-deep-research: {task_id}\n{'='*60}")
    t0 = time.time()
    try:
        from local_deep_research.api import quick_summary
        result = quick_summary(
            query=intent,
            model_name=os.environ.get("LDR_MODEL", "deepseek-chat"),
            provider="openai_endpoint",
            openai_endpoint_url=os.environ.get(
                "OPENAI_BASE_URL",
                "https://open.bigmodel.cn/api/coding/paas/v4",
            ),
            search_tool=os.environ.get("LDR_SEARCH_TOOL", "tavily"),
            search_strategy=os.environ.get("LDR_STRATEGY", "source-based"),
            iterations=int(os.environ.get("LDR_ITERATIONS", "2")),
            questions_per_iteration=int(os.environ.get("LDR_QPI", "2")),
            temperature=0.3,
        )
        report = (result or {}).get("summary") or json.dumps(result)[:2000]
    except Exception as e:
        report = f"(local-deep-research error: {type(e).__name__}: {e})"
    elapsed = time.time() - t0
    out_path = OUT_DIR / f"local-deep-research_{task_id}.md"
    out_path.write_text(report or "(empty)")
    print(f"Finished in {elapsed:.0f}s, {len(report)} chars → {out_path}")


def main() -> None:
    only = os.environ.get("LDR_ONLY_TASK")
    tasks = [only] if only else TASKS
    for t in tasks:
        try:
            _run_one(t)
        except Exception as e:
            print(f"Task {t} failed: {e}")


if __name__ == "__main__":
    main()
