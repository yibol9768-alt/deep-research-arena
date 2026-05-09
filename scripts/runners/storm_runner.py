"""STORM runner for the deep-research benchmark.

Integrates Stanford STORM (knowledge_storm) against our sandbox WITHOUT
monkey-patching. Instead of patching TavilyClient to redirect its base URL,
we implement a custom dspy.Retrieve subclass (SandboxSearchRM) that talks
directly to our Tavily-compatible shim. STORM's RM architecture is designed
for exactly this: every RM (YouRM, BingSearch, BraveRM, TavilySearchRM, etc.)
is a dspy.Retrieve subclass whose forward() returns List[Dict] with keys
'description', 'snippets', 'title', 'url'. We provide our own.

Sentence-transformers / HuggingFace models: the STORM Wiki pipeline does NOT
use sentence-transformers. The Encoder class (encoder.py) uses LiteLLM
embeddings and is only used in collaborative_storm and QdrantVectorStoreManager,
neither of which STORMWikiRunner references. So this is a non-issue.

Usage (on westd, with shim+sandbox+ds_proxy running):
    export SHIM_URL=http://localhost:8081
    export DS_PROXY_URL=http://localhost:8088/v1
    export OPENAI_API_KEY=anything
    python3 -c "
    import asyncio
    from scripts.runners.storm_runner import run
    print(asyncio.run(run(
        intent='Compare headphone prices across stores...',
        model='deepseek-v4-flash',
        shim_url='http://localhost:8081',
        proxy_url='http://localhost:8088/v1',
    )))
    "
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from pathlib import Path
from typing import Callable, List, Union

# Prevent HuggingFace from trying to download models at import time.
# The model must be pre-cached: run `SentenceTransformer('paraphrase-MiniLM-L6-v2')`
# once with HTTP_PROXY set before using this runner.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import dspy
import requests

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Custom retrieval model: talks directly to our Tavily-compatible shim.
# No monkey-patching needed -- this is the same pattern STORM uses for all
# its built-in retrievers (YouRM, BingSearch, BraveRM, SerperRM, etc.).
# ---------------------------------------------------------------------------

class SandboxSearchRM(dspy.Retrieve):
    """Retrieve search results from the benchmark sandbox shim.

    The shim exposes a Tavily-compatible POST /search endpoint.
    This RM calls it directly and returns results in the format STORM expects:
    List[Dict] with keys 'description', 'snippets' (list of str), 'title', 'url'.
    """

    def __init__(
        self,
        shim_url: str = "http://localhost:8081",
        k: int = 5,
        include_raw_content: bool = True,
        is_valid_source: Callable = None,
        api_key: str = "tvly-shim-fake",
    ):
        super().__init__(k=k)
        self.shim_url = shim_url.rstrip("/")
        self.k = k
        self.include_raw_content = include_raw_content
        self.api_key = api_key
        self.usage = 0
        self.is_valid_source = is_valid_source or (lambda x: True)

    def get_usage_and_reset(self):
        usage = self.usage
        self.usage = 0
        return {"SandboxSearchRM": usage}

    def forward(
        self,
        query_or_queries: Union[str, List[str]],
        exclude_urls: List[str] = [],
    ) -> List[dict]:
        """Search the sandbox shim for top-k results per query.

        Returns:
            List of dicts with keys: 'description', 'snippets', 'title', 'url'
        """
        queries = (
            [query_or_queries]
            if isinstance(query_or_queries, str)
            else query_or_queries
        )
        self.usage += len(queries)
        collected_results = []

        for query in queries:
            try:
                resp = requests.post(
                    f"{self.shim_url}/search",
                    json={
                        "query": query,
                        "api_key": self.api_key,
                        "max_results": self.k,
                        "include_raw_content": self.include_raw_content,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])

                for d in results:
                    if not isinstance(d, dict):
                        continue
                    url = d.get("url", "")
                    if not url:
                        continue
                    if not self.is_valid_source(url):
                        continue
                    if url in exclude_urls:
                        continue

                    title = d.get("title", "")
                    description = d.get("content", "")
                    # Build snippets: prefer raw_content if available,
                    # fall back to content field.
                    snippets = []
                    raw = d.get("raw_content") or d.get("raw_body_content")
                    if raw:
                        snippets.append(raw)
                    elif description:
                        snippets.append(description)

                    if not all([url, title, snippets]):
                        continue

                    collected_results.append({
                        "url": url,
                        "title": title,
                        "description": description,
                        "snippets": snippets,
                    })

            except Exception as e:
                logger.error(f"Error searching shim for query '{query[:80]}': {e}")

        return collected_results


# ---------------------------------------------------------------------------
# Build the STORM runner with our custom RM + LiteLLM model.
# ---------------------------------------------------------------------------

def _build_storm_runner(
    shim_url: str,
    proxy_url: str,
    model: str,
    output_dir: str,
    api_key: str = "anything",
):
    """Construct a STORMWikiRunner using our SandboxSearchRM.

    Uses STORM's official constructor args and LM config setters.
    No monkey-patching.
    """
    from knowledge_storm.storm_wiki.engine import (
        STORMWikiRunner,
        STORMWikiRunnerArguments,
        STORMWikiLMConfigs,
    )
    from knowledge_storm.lm import LitellmModel

    # -- Language model config --
    # All STORM pipeline stages use the same backbone via LiteLLM's
    # OpenAI-compatible routing. The "openai/" prefix tells LiteLLM
    # to use the OpenAI provider, and api_base redirects it to our proxy.
    llm_kwargs = dict(
        model=f"openai/{model}",
        api_key=api_key,
        api_base=proxy_url,
        max_tokens=8192,
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
        setter(LitellmModel(**llm_kwargs))

    # -- Runner arguments --
    args = STORMWikiRunnerArguments(
        output_dir=output_dir,
        max_conv_turn=3,
        max_perspective=3,
        search_top_k=5,
        max_thread_num=2,
    )

    # -- Retrieval model: our custom subclass, no patching needed --
    rm = SandboxSearchRM(
        shim_url=shim_url,
        k=5,
        include_raw_content=True,
    )

    return STORMWikiRunner(args, lm_config, rm)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Agent identifier for the auto-discovery registry. Must match the
# AGENT_NAME used in score files: data/results/deep_v3/storm__<task>_matrix.score.json
AGENT_NAME = "storm"


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
) -> str:
    """Run STORM and return the markdown report.

    Args:
        intent: The research topic / query.
        model: LLM model name (e.g. 'deepseek-v4-flash').
        shim_url: Tavily-compatible search shim (e.g. 'http://localhost:8081').
        proxy_url: OpenAI-compatible LLM proxy (e.g. 'http://localhost:8088/v1').

    Returns:
        The polished article as a markdown string.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "anything")

    # Use a unique scratch dir per run to avoid collisions.
    topic_hash = hashlib.md5(intent[:300].encode()).hexdigest()[:12]
    scratch_dir = os.path.join(
        str(ROOT / "data" / "results" / "deep"),
        f"_storm_scratch_{topic_hash}",
    )
    os.makedirs(scratch_dir, exist_ok=True)

    runner = _build_storm_runner(
        shim_url=shim_url,
        proxy_url=proxy_url,
        model=model,
        output_dir=scratch_dir,
        api_key=api_key,
    )

    # STORM's run() is synchronous (uses threading internally).
    # Truncate topic to 300 chars to avoid filesystem path issues.
    topic = intent[:300]
    runner.run(
        topic=topic,
        do_research=True,
        do_generate_outline=True,
        do_generate_article=True,
        do_polish_article=True,
    )
    runner.post_run()

    # Collect the output article.
    # STORM creates a subdirectory named after the topic (sanitized).
    # Look for the polished article first, then fall back to other outputs.
    scratch_path = Path(scratch_dir)
    candidates = list(scratch_path.rglob("storm_gen_article_polished.txt"))
    if not candidates:
        candidates = list(scratch_path.rglob("storm_gen_article*.txt"))
    if not candidates:
        candidates = list(scratch_path.rglob("*.txt"))

    if candidates:
        # Pick the largest file (most likely the polished article).
        candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
        result = candidates[0].read_text()
        logger.info(f"STORM output: {candidates[0]} ({len(result)} chars)")
        return result

    # Debug: list what STORM actually wrote.
    all_files = list(scratch_path.rglob("*"))
    logger.warning(
        f"No article found in {scratch_dir}. "
        f"Files: {[str(f) for f in all_files[:20]]}"
    )
    return "(empty storm output)"
