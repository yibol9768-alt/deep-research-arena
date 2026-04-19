"""Run Stanford STORM (knowledge-storm) on 4 cross-site tasks via the shim.

STORM generates Wikipedia-style long reports through multi-perspective
question asking + co-STORM conversation. We feed it our shim as the
retriever backend.

Env:
    STORM_SHIM_URL=http://localhost:8081
    OPENAI_API_KEY=<Coding Plan key>
    OPENAI_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4

Outputs:
    data/results/storm_dr_cross_v3_<TASK>.md
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SHIM = os.environ.get("STORM_SHIM_URL", "http://localhost:8081")
os.environ.setdefault("TAVILY_API_KEY", "tvly-shim-fake")

# Patch Tavily base URL
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


def _build_runner():
    from knowledge_storm.storm_wiki.engine import (
        STORMWikiRunner,
        STORMWikiRunnerArguments,
        STORMWikiLMConfigs,
    )
    from knowledge_storm.lm import LitellmModel
    from knowledge_storm.rm import TavilySearchRM

    # Everything uses deepseek-chat via Coding Plan (litellm OpenAI-compat)
    llm_kw = dict(
        model="openai/deepseek-chat",
        api_key=os.environ.get("OPENAI_API_KEY"),
        api_base=os.environ.get("OPENAI_BASE_URL"),
        max_tokens=2000,
        temperature=0.7,
    )
    lm_config = STORMWikiLMConfigs()
    for setter in (
        lm_config.set_conv_simulator_lm,
        lm_config.set_question_asker_lm,
        lm_config.set_outline_gen_lm,
        lm_config.set_article_gen_lm,
        lm_config.set_article_polish_lm,
    ):
        setter(LitellmModel(**llm_kw))

    args = STORMWikiRunnerArguments(
        output_dir=str(OUT_DIR / "_storm_scratch"),
        max_conv_turn=3,
        max_perspective=3,
        search_top_k=5,
        max_thread_num=2,
    )
    rm = TavilySearchRM(
        tavily_search_api_key=os.environ.get("TAVILY_API_KEY"),
        k=5,
        include_raw_content=True,
    )
    return STORMWikiRunner(args, lm_config, rm)


def _run_one(task_id: str) -> None:
    intent = _load_intent(task_id)
    print(f"\n{'='*60}\nSTORM: {task_id}\n{'='*60}")
    t0 = time.time()
    try:
        runner = _build_runner()
        topic = intent[:200]
        runner.run(topic=topic, do_research=True, do_generate_outline=True,
                   do_generate_article=True, do_polish_article=True)
        runner.post_run()
        # STORM writes the polished article to output_dir/<topic>/storm_gen_article_polished.txt
        from knowledge_storm.utils import makeStringRed  # noqa (import check)
        import glob
        files = sorted(glob.glob(str(OUT_DIR / "_storm_scratch" / "**" / "storm_gen_article*.txt"),
                                 recursive=True), key=os.path.getmtime)
        report = Path(files[-1]).read_text() if files else "(no article produced)"
    except Exception as e:
        report = f"(STORM error: {type(e).__name__}: {e})"
    elapsed = time.time() - t0
    out_path = OUT_DIR / f"storm_{task_id}.md"
    out_path.write_text(report or "(empty)")
    print(f"Finished in {elapsed:.0f}s, {len(report)} chars → {out_path}")


def main() -> None:
    only = os.environ.get("STORM_ONLY_TASK")
    tasks = [only] if only else TASKS
    for t in tasks:
        try:
            _run_one(t)
        except Exception as e:
            print(f"Task {t} failed: {e}")


if __name__ == "__main__":
    main()
