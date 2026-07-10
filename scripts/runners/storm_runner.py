"""STORM runner for the deep-research benchmark.

Integrates Stanford STORM (knowledge_storm) against our sandbox WITHOUT
monkey-patching. Instead of patching TavilyClient to redirect its base URL,
we implement a custom dspy.Retrieve subclass (SandboxSearchRM) that talks
directly to our Tavily-compatible shim. STORM's RM architecture is designed
for exactly this: every RM (YouRM, BingSearch, BraveRM, TavilySearchRM, etc.)
is a dspy.Retrieve subclass whose forward() returns List[Dict] with keys
'description', 'snippets', 'title', 'url'. We provide our own.

Sentence-transformers / HuggingFace models: STORM's article generation calls
StormInformationTable.prepare_table_for_retrieval(), which instantiates
SentenceTransformer("paraphrase-MiniLM-L6-v2") (storm_dataclass.py:110). With
HuggingFace offline that raises and no article file is written, so the run
returns rc=0 with an empty report. _install_offline_information_table_patch()
below neutralizes this by replacing the embedding retriever with a
deterministic lexical scorer, so no external model cache is required. The
scorer preserves STORM's original contract of always returning up to
`search_top_k` snippets per query (lexical matches ranked first, deterministic
richness tiebreak), so no section is ever left ungrounded.

Article-generation skip filter: STORM's generate_article skips first-level
sections named introduction/conclusion/summary. Our outlines are always a
single `#` title with the real sections nested as `##`, so the outline tree has
exactly one first-level section (the title). If that lone title matches the
skip filter the whole article is skipped and nothing is written.
_install_article_generation_guard() below reimplements generate_article so the
skip filter can never empty the outline.

Usage (on westd, with shim+sandbox+ds_proxy running):
    export SHIM_URL=http://localhost:8081
    export DS_PROXY_URL=http://localhost:8100/v1
    export OPENAI_API_KEY=anything
    python3 -c "
    import asyncio
    from scripts.runners.storm_runner import run
    print(asyncio.run(run(
        intent='Compare headphone prices across stores...',
        model='deepseek-v4-flash',
        shim_url='http://localhost:8081',
        proxy_url='http://localhost:8100/v1',
    )))
    "
"""

from __future__ import annotations

import json
import logging
import multiprocessing as mp
import os
import copy
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, List, Union

# Prevent HuggingFace from trying to download models at import time.
# The model must be pre-cached: run `SentenceTransformer('paraphrase-MiniLM-L6-v2')`
# once with HTTP_PROXY set before using this runner.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import dspy
import requests

from . import _budget
from .evidence_fallback import (
    error_stub,
    fallback_enabled,
    is_weak_report,
    keep_or_stub,
    synthesize_report,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Unified default, identical for every lane (see scripts/runners/_budget.py):
# None = no native self-abort, the no-progress watchdog terminates a stall.
DEFAULT_NATIVE_TIMEOUT_S = _budget.native_timeout_default()


def _native_timeout():
    # Unified native timeout. Default identical to every lane (DRA_WALL_CLOCK_S);
    # STORM_NATIVE_TIMEOUT_S still overrides. None (unlimited) means proc.join
    # blocks until the worker finishes and the shared no-progress watchdog is
    # what kills a wedged run. The old hard 420s default was a per-lane wall
    # clock that aborted slow-backbone runs still making progress.
    configured = _budget.resolve_native_timeout("STORM_NATIVE_TIMEOUT_S")
    return None if configured is None else max(60, int(configured))


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
        k: int = 3,
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


def _install_offline_information_table_patch() -> None:
    """Avoid STORM's hard dependency on a HuggingFace sentence-transformer.

    STORM's article generation calls StormInformationTable.prepare_table_for_retrieval(),
    which normally instantiates SentenceTransformer("paraphrase-MiniLM-L6-v2").
    That makes full runs depend on an external model cache. For this benchmark
    we only need deterministic local snippet selection, so replace the embedding
    retriever with a small lexical scorer.
    """
    if getattr(_install_offline_information_table_patch, "_done", False):
        return

    from knowledge_storm.storm_wiki.modules import storm_dataclass

    table_cls = storm_dataclass.StormInformationTable

    def _tokenize(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9][a-z0-9._-]+", (text or "").lower()))

    def _prepare_table_for_retrieval(self):
        self.encoder = None
        self.collected_urls = []
        self.collected_snippets = []
        self._snippet_tokens = []
        for url, information in self.url_to_info.items():
            for snippet in getattr(information, "snippets", []) or []:
                if not snippet:
                    continue
                self.collected_urls.append(url)
                self.collected_snippets.append(snippet)
                self._snippet_tokens.append(_tokenize(snippet))
        self.encoded_snippets = []

    def _retrieve_information(self, queries, search_top_k):
        if isinstance(queries, str):
            queries = [queries]
        if not getattr(self, "collected_snippets", None):
            return []

        selected = []
        for query in queries:
            query_tokens = _tokenize(query)
            scored = []
            for idx, snippet_tokens in enumerate(self._snippet_tokens):
                overlap = len(query_tokens & snippet_tokens)
                # IMPORTANT: do NOT drop zero-overlap snippets. STORM's original
                # embedding retriever always returned up to `search_top_k`
                # snippets per query (argsort top-k, regardless of similarity
                # magnitude), so every section was guaranteed some citable
                # source. An earlier version of this scorer `continue`d past
                # overlap==0, which left sections with no snippets whenever a
                # section's title tokens did not lexically overlap the corpus.
                # That produced articles with zero inline citations and an empty
                # url_to_unified_index (the "0 localhost citations" failure).
                # We keep every snippet, rank lexical matches first, and let the
                # deterministic richness tiebreak fill the remaining top-k slots.
                richness = min(len(snippet_tokens), 200) / 10000.0  # in [0, 0.02)
                score = overlap + richness
                scored.append((score, idx))
            # Rank by score DESC, then snippet index ASC (stable, deterministic).
            scored.sort(key=lambda t: (-t[0], t[1]))
            selected.extend(idx for _, idx in scored[:search_top_k])

        url_to_snippets = {}
        for idx in selected:
            url = self.collected_urls[idx]
            url_to_snippets.setdefault(url, set()).add(self.collected_snippets[idx])

        selected_url_to_info = {}
        for url, snippets in url_to_snippets.items():
            selected_url_to_info[url] = copy.deepcopy(self.url_to_info[url])
            selected_url_to_info[url].snippets = list(snippets)
        return list(selected_url_to_info.values())

    table_cls.prepare_table_for_retrieval = _prepare_table_for_retrieval
    table_cls.retrieve_information = _retrieve_information
    _install_offline_information_table_patch._done = True  # type: ignore[attr-defined]


def _install_article_generation_guard() -> None:
    """Stop STORM's section-skip filter from producing an empty article.

    STORM's ``StormArticleGenerationModule.generate_article`` iterates the
    first-level sections of the outline and *skips* any section whose title is
    ``introduction`` or starts with ``conclusion`` / ``summary`` (it does not
    want to write standalone intro/conclusion sections in a multi-section
    Wikipedia article). That heuristic is safe when the outline has many
    first-level sections.

    For this benchmark it is not. The outline LM always emits a single ``#``
    title heading with the real sections nested one level down as ``##``, so
    ``StormArticle.from_outline_str`` builds a tree whose root has exactly ONE
    child: the title node. ``get_first_level_section_names()`` therefore returns
    a single entry (the title). When that lone title happens to start with
    ``summary``/``conclusion`` or equals ``introduction`` (e.g. a report titled
    "Summary of ...", "Conclusions and Recommendations"), the skip filter drops
    the *only* section, so generate_article writes nothing: no LLM call, an empty
    draft, and after polishing a "summary-only" file. This is the dead
    article-generation module observed in the smoke (run_article_generation_module
    returning in ~0.0007s having never called the LLM).

    Fix: reimplement generate_article (faithful to knowledge-storm 1.1.1) with a
    single guard: if applying the skip filter would leave zero sections to write,
    write every section instead. Multi-section outlines (and single-title
    outlines whose title is not a skip word) are unaffected.
    """
    if getattr(_install_article_generation_guard, "_done", False):
        return

    import concurrent.futures
    from concurrent.futures import as_completed

    from knowledge_storm.storm_wiki.modules import article_generation
    from knowledge_storm.storm_wiki.modules.storm_dataclass import StormArticle

    gen_cls = article_generation.StormArticleGenerationModule

    def _is_skippable(section_title: str) -> bool:
        name = section_title.lower().strip()
        return (
            name == "introduction"
            or name.startswith("conclusion")
            or name.startswith("summary")
        )

    def _generate_article(
        self,
        topic,
        information_table,
        article_with_outline,
        callback_handler=None,
    ):
        information_table.prepare_table_for_retrieval()

        if article_with_outline is None:
            article_with_outline = StormArticle(topic_name=topic)

        sections_to_write = article_with_outline.get_first_level_section_names()

        # ADAPTER GUARD: never let the intro/conclusion/summary filter empty the
        # outline. If every first-level section is skippable (the single-title
        # outline case) fall back to writing all of them.
        writable = [s for s in sections_to_write if not _is_skippable(s)]
        if not writable:
            if sections_to_write:
                logger.warning(
                    "storm: all %d first-level section(s) matched STORM's "
                    "intro/conclusion/summary skip filter (%r); writing them "
                    "anyway to avoid a dead article-generation module.",
                    len(sections_to_write),
                    sections_to_write,
                )
            writable = list(sections_to_write)

        section_output_dict_collection = []
        if len(sections_to_write) == 0:
            logger.error(
                "No outline for %s. Will directly search with the topic.", topic
            )
            section_output_dict = self.generate_section(
                topic=topic,
                section_name=topic,
                information_table=information_table,
                section_outline="",
                section_query=[topic],
            )
            section_output_dict_collection = [section_output_dict]
        else:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_thread_num
            ) as executor:
                future_to_sec_title = {}
                for section_title in writable:
                    section_query = article_with_outline.get_outline_as_list(
                        root_section_name=section_title, add_hashtags=False
                    )
                    queries_with_hashtags = article_with_outline.get_outline_as_list(
                        root_section_name=section_title, add_hashtags=True
                    )
                    section_outline = "\n".join(queries_with_hashtags)
                    future_to_sec_title[
                        executor.submit(
                            self.generate_section,
                            topic,
                            section_title,
                            information_table,
                            section_outline,
                            section_query,
                        )
                    ] = section_title

                for future in as_completed(future_to_sec_title):
                    section_output_dict_collection.append(future.result())

        article = copy.deepcopy(article_with_outline)
        for section_output_dict in section_output_dict_collection:
            article.update_section(
                parent_section_name=topic,
                current_section_content=section_output_dict["section_content"],
                current_section_info_list=section_output_dict["collected_info"],
            )
        article.post_processing()
        return article

    gen_cls.generate_article = _generate_article
    _install_article_generation_guard._done = True  # type: ignore[attr-defined]


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
        temperature=0.2,
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
    # Preserve STORMWikiRunnerArguments' native research budgets. The adapter
    # previously raised search_top_k from 3 to 5 and cut max_thread_num from
    # 10 to 2 without declaring either change in the lane protocol.
    args = STORMWikiRunnerArguments(
        output_dir=output_dir,
        max_conv_turn=3,
        max_perspective=3,
        search_top_k=3,
        max_thread_num=10,
    )

    # -- Retrieval model: our custom subclass, no patching needed --
    rm = SandboxSearchRM(
        shim_url=shim_url,
        k=3,
        include_raw_content=True,
    )

    return STORMWikiRunner(args, lm_config, rm)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Agent identifier for the auto-discovery registry. Must match the
# AGENT_NAME used in score files: data/results/deep_v3/storm__<task>_matrix.score.json
AGENT_NAME = "storm"

# Workstream C — strict-sandbox eligibility.
# DECISION: storm is strict_sandbox_eligible.
#
# Rationale (vs. the alternative — patching en.wikipedia.org -> :8090):
# storm's retrieval already goes through SandboxSearchRM (this file) which
# only talks to the shim. The remaining attack surface is STORM's internal
# WebPageHelper that fetches result URLs to re-rank — but those URLs only
# come from the shim, which we gate in strict mode. The narrow alternative
# (patching requests.Session.send to rewrite en.wikipedia.org -> :8090) is
# larger code than installing the sandbox-only HTTP gate below; both
# converge on the same outcome (no traffic ever leaves the box) so we go
# with the smaller patch.
STRICT_SANDBOX_ELIGIBLE = True


def _storm_native_worker(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    strict_sandbox: bool,
    scratch_dir: str,
    api_key: str,
    out_q,
) -> None:
    try:
        if strict_sandbox:
            os.environ["SHIM_MODE"] = "strict"
            _install_strict_http_gate()
        _install_offline_information_table_patch()
        _install_article_generation_guard()

        runner = _build_storm_runner(
            shim_url=shim_url,
            proxy_url=proxy_url,
            model=model,
            output_dir=scratch_dir,
            api_key=api_key,
        )
        run_start_mtime = time.time() - 1.0
        runner.run(
            # The task is the benchmark input.  Truncating it here silently
            # removed constraints that every other lane received.  Scratch
            # paths are UUID-based, so the old filesystem-safety rationale no
            # longer applies.
            topic=intent,
            do_research=True,
            do_generate_outline=True,
            do_generate_article=True,
            do_polish_article=True,
        )
        runner.post_run()
        report = _extract_article(Path(scratch_dir), run_start_mtime)
        out_q.put({"ok": True, "report": report})
    except BaseException as e:  # noqa: BLE001
        out_q.put({"ok": False, "error": f"{type(e).__name__}: {e}"})


def _install_strict_http_gate() -> None:
    """Install a `requests.Session.send` interceptor that refuses any
    non-sandbox URL. Idempotent — repeat calls are no-ops.

    Called only when run() is invoked with strict_sandbox=True. STORM's
    WebPageHelper fetches result URLs via requests; without this gate a
    malicious shim response (or a STORM bug that supplies a URL not
    derived from the shim) could reach the real internet.
    """
    if getattr(_install_strict_http_gate, "_done", False):
        return
    from urllib.parse import urlparse as _up

    _SBX = {
        "localhost:7770", "localhost:17770", "localhost:8090", "localhost:9999", "localhost:8081",
        "127.0.0.1:7770", "127.0.0.1:17770", "127.0.0.1:8090", "127.0.0.1:9999", "127.0.0.1:8081",
        "localhost:18081", "127.0.0.1:18081",
    }

    def _sandbox_only(url: str) -> bool:
        try:
            p = _up(url)
            host = (p.hostname or "").lower()
            port = p.port
        except Exception:
            return False
        if not host or port is None:
            return False
        return f"{host}:{port}" in _SBX

    _orig = requests.Session.send

    def _gated(self, request, **kw):
        if not _sandbox_only(request.url):
            logger.warning("storm strict: BLOCK non-sandbox %s", request.url[:120])
            from requests.models import Response
            r = Response()
            r.status_code = 403
            r._content = b'{"error":"non_sandbox_url_blocked"}'
            return r
        return _orig(self, request, **kw)

    requests.Session.send = _gated
    _install_strict_http_gate._done = True  # type: ignore[attr-defined]


def _extract_article(scratch_path: Path, run_start_mtime: float) -> str:
    """Recover the STORM article from a scratch tree.

    Only files whose mtime is >= run_start_mtime are considered, so a stale
    article left behind by a prior run (or a concurrent run sharing the tree)
    can never be picked up as this run's output. Within the fresh candidates we
    prefer the polished article, then any storm_gen_article*.txt, then any .txt,
    and finally pick the largest (most likely the full polished article).

    Args:
        scratch_path: root of the per-run scratch directory.
        run_start_mtime: epoch seconds captured just before STORM ran; files
            older than this are treated as stale and ignored.

    Returns:
        The article markdown (with an appended References section when STORM's
        url_to_info.json is available), or "(empty storm output)" if no fresh
        article was produced.
    """

    def _fresh(paths: List[Path]) -> List[Path]:
        fresh = []
        for p in paths:
            try:
                if p.stat().st_mtime >= run_start_mtime:
                    fresh.append(p)
            except OSError:
                continue
        return fresh

    candidates = _fresh(list(scratch_path.rglob("storm_gen_article_polished.txt")))
    if not candidates:
        candidates = _fresh(list(scratch_path.rglob("storm_gen_article*.txt")))
    if not candidates:
        candidates = _fresh(list(scratch_path.rglob("*.txt")))

    if candidates:
        # Pick the largest file (most likely the polished article).
        candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
        result = candidates[0].read_text()
        logger.info(f"STORM output: {candidates[0]} ({len(result)} chars)")
        # The harness used to append a "## References" section here, built from
        # the bibliography STORM keeps in url_to_info.json, "so the URL
        # extractor can recover" it. That is the same construct as ldr's
        # `_attach_sources` and ii-researcher's deleted B1 graft: the harness
        # writes the lane's URLs into the scored artifact. Counterfactual
        # rescore with the block removed: storm macro reach 0.9609 -> 0.0000.
        #
        # Whether STORM "really" retrieved those URLs is beside the point. Every
        # other framework must put its citations in its own report to be
        # credited for them, and none of them get the harness to do it. Removed
        # 2026-07-08 (fairness audit). The bibliography is logged, not appended.
        try:
            url_info_paths = list(candidates[0].parent.glob("url_to_info.json"))
            if not url_info_paths:
                url_info_paths = list(scratch_path.rglob("url_to_info.json"))
            if url_info_paths:
                url_to_idx = json.loads(url_info_paths[0].read_text()).get("url_to_unified_index", {})
                logger.info("storm retrieved %d sources (diagnostic only, not appended)",
                            len(url_to_idx))
        except Exception as e:
            logger.warning(f"Failed to read storm bibliography: {e}")
        return result

    # Debug: list what STORM actually wrote.
    all_files = list(scratch_path.rglob("*"))
    logger.warning(
        f"No article found in {scratch_path}. "
        f"Files: {[str(f) for f in all_files[:20]]}"
    )
    return "(empty storm output)"


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    strict_sandbox: bool = False,
) -> str:
    """Run STORM and return the markdown report.

    Args:
        intent: The research topic / query.
        model: LLM model name (e.g. 'deepseek-v4-flash').
        shim_url: Tavily-compatible search shim (e.g. 'http://localhost:8081').
        proxy_url: OpenAI-compatible LLM proxy (e.g. 'http://localhost:8100/v1').
        strict_sandbox: when True, installs an HTTP-layer gate that refuses
            any non-sandbox URL (belt-and-suspenders behind SandboxSearchRM
            which already only talks to the shim). Also forwards
            SHIM_MODE=strict via the process env.

    Returns:
        The polished article as a markdown string.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "anything")

    # Use a unique per-invocation scratch dir. Keying on a content hash of the
    # intent (the old behaviour) made two runs of the same task share a tree
    # that was never cleaned, so a failing run could silently read back a stale
    # or cross-run article as its own output. A uuid4 token guarantees no
    # collision across runs (sequential or concurrent), and the finally block
    # below deletes the tree so nothing leaks into a later run.
    scratch_dir = os.path.join(
        str(ROOT / "data" / "results" / "deep"),
        f"_storm_scratch_{uuid.uuid4().hex}",
    )
    os.makedirs(scratch_dir, exist_ok=True)
    scratch_path = Path(scratch_dir)

    def _degrade(phase: str, reason: str) -> str:
        # Fairness rule: a STORM failure or weak native article must surface as
        # STORM's own output (an honest error stub), never a harness-ghostwritten
        # report. The source-grounded evidence writer runs only under the explicit
        # non-benchmark EVIDENCE_FALLBACK_ENABLE flag.
        if fallback_enabled():
            return synthesize_report(
                intent,
                model,
                shim_url,
                proxy_url,
                min_chars=4500,
                min_urls=5,
            )
        return error_stub("storm", phase, reason)

    try:
        ctx = mp.get_context("fork")
        out_q = ctx.Queue(maxsize=1)
        proc = ctx.Process(
            target=_storm_native_worker,
            args=(intent, model, shim_url, proxy_url, strict_sandbox, scratch_dir, api_key, out_q),
            daemon=True,
        )
        proc.start()
        proc.join(_native_timeout())
        if proc.is_alive():
            logger.warning("storm native path exceeded %ss; recording honest failure", _native_timeout())
            proc.terminate()
            proc.join(5)
            if proc.is_alive():
                proc.kill()
                proc.join(5)
            return _degrade("native", f"native path exceeded {_native_timeout()}s timeout")

        payload = None
        try:
            payload = out_q.get_nowait()
        except Exception:
            pass
        if not payload:
            logger.warning("storm native path exited without payload; recording honest failure")
            return _degrade("native", "native path exited without payload")
        if not payload.get("ok"):
            logger.warning("storm native path failed: %s", payload.get("error"))
            return _degrade("native", str(payload.get("error") or "native path failed"))
        report = str(payload.get("report") or "").strip()
        if is_weak_report(report, min_chars=3000, min_urls=3):
            if fallback_enabled():
                logger.warning("storm native report weak/empty; using source-grounded writer")
                return _degrade("write", "native article under length/URL threshold")
            # Weak-but-real output is STORM's own article: save it verbatim
            # (the scorer judges quality); stub only genuinely empty/stub output.
            return keep_or_stub(
                "storm", "write", "native article under length/URL threshold", report
            )
        return report
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
