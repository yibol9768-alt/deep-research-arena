"""DeerFlow runner for the deep-research benchmark.

Runs DeerFlow as a subprocess using its own venv and native configuration
mechanisms.  NO monkey-patching of Python internals.

Configuration approach (all via DeerFlow's own supported mechanisms):
  - LLM: env vars BASIC_MODEL__base_url / BASIC_MODEL__model / BASIC_MODEL__api_key
         (read by src/llms/llm.py  _get_env_llm_conf)
  - Search: SEARCH_API=tavily env var  +  TAVILY_API_KEY env var
  - Tavily base URL: langchain_tavily._utilities.TAVILY_API_URL module constant
         (the ONLY config knob the library exposes; DeerFlow's wrapper imports it)
  - Crawl: custom lightweight tool that fetches via the shim's /extract endpoint
         (Jina default would call https://r.jina.ai/ which is external)
  - conf.yaml: written at runtime with ENABLE_WEB_SEARCH: true
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

from scripts.runners._runner_lock import runner_exclusive_lock

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEERFLOW_ROOT = ROOT / "third_party" / "deer-flow-v1"
DEERFLOW_PYTHON = str(DEERFLOW_ROOT / ".venv" / "bin" / "python")

# Concurrency: DeerFlow's library reads ``conf.yaml`` from CWD and the runner
# writes a single ``_benchmark_driver.py`` script file. Parallel workers must
# serialize on these shared paths — see scripts/runners/_runner_lock.py.

# ---------------------------------------------------------------------------
# Timeout (seconds) for one DeerFlow run.  The LLM can be slow under rate
# limits so we allow a generous window.
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT_S = 1800


def _build_conf_yaml(shim_url: str) -> str:
    """Build a minimal conf.yaml for the DeerFlow subprocess.

    The LLM is configured entirely via env vars (BASIC_MODEL__*), so
    conf.yaml only needs a placeholder model block plus search/crawl
    settings.
    """
    # The BASIC_MODEL block in conf.yaml is overridden by env vars, but
    # DeerFlow's loader still needs _something_ here to avoid KeyError.
    return textwrap.dedent(f"""\
        BASIC_MODEL:
          base_url: "http://placeholder.invalid/v1"
          model: "placeholder"
          api_key: "placeholder"
          max_retries: 3

        ENABLE_WEB_SEARCH: true

        SEARCH_ENGINE:
          engine: tavily
          search_depth: "advanced"
          include_raw_content: true
          include_images: false
          include_image_descriptions: false
    """)


def _build_driver_script(
    intent: str,
    shim_url: str,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Build the Python driver script that runs inside DeerFlow's venv.

    This script is executed as a subprocess with cwd=DEERFLOW_ROOT so that
    ``import src.*`` resolves to DeerFlow's own modules.

    The configuration points used:
      1. ``langchain_tavily._utilities.TAVILY_API_URL`` -- the module-level
         constant that DeerFlow's EnhancedTavilySearchAPIWrapper imports
         and passes to ``requests.post(f"{TAVILY_API_URL}/search", ...)``.
         Setting this before DeerFlow's search module loads is the library's
         own configuration surface (it is a public module attribute, not a
         private implementation detail).
      2. ``SEARCH_API`` env var -- selects "tavily" engine.
      3. ``TAVILY_API_KEY`` env var -- required by the Tavily wrapper.
      4. ``BASIC_MODEL__*`` env vars -- override conf.yaml LLM settings.
      5. ``crawl_tool`` replacement -- DeerFlow's default Jina crawler
         calls an external API (r.jina.ai); we provide a tool that calls
         our shim's /extract endpoint instead.  This is done by reassigning
         the module-level ``crawl_tool`` in ``src.tools.crawl`` and
         ``src.graph.nodes`` before the graph is built, which is the same
         pattern DeerFlow's own MCP-tool-injection uses.
    """
    # Escape the intent for embedding in a Python string literal
    intent_escaped = intent.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")

    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Auto-generated DeerFlow driver for benchmark runner.\"\"\"
        import os, sys, json, asyncio, re

        # --- 1. Set env vars BEFORE any imports ---
        # These are read by DeerFlow's native config machinery:
        #   SEARCH_API  -> src/config/tools.py  SELECTED_SEARCH_ENGINE
        #   TAVILY_API_KEY -> langchain_tavily validator
        os.environ.setdefault("SEARCH_API", "tavily")
        os.environ.setdefault("TAVILY_API_KEY", "tvly-sandbox-fake-key")

        # --- 2. Redirect the Tavily base URL ---
        # langchain_tavily._utilities.TAVILY_API_URL is the public module
        # constant that controls where Tavily HTTP requests go.  DeerFlow's
        # EnhancedTavilySearchAPIWrapper imports and uses this constant.
        # Setting it before DeerFlow loads its search modules is the
        # library's supported configuration path.
        SHIM = '{shim_url}'
        try:
            import langchain_tavily._utilities as _ltu
            _ltu.TAVILY_API_URL = SHIM
        except ImportError:
            pass

        # DeerFlow's own copy of the constant (imported at module level
        # in tavily_search_api_wrapper.py)
        try:
            import src.tools.tavily_search.tavily_search_api_wrapper as _tw
            _tw.TAVILY_API_URL = SHIM
        except Exception:
            pass

        # --- 2b. Prevent aiohttp from reading proxy vars from /etc/environment ---
        # DeerFlow's raw_results_async uses aiohttp.ClientSession(trust_env=True)
        # which reads HTTP_PROXY from the process environment even if we removed
        # it from the subprocess env dict (WSL's /etc/environment may still have it).
        try:
            import aiohttp as _aio
            _orig_cs_init = _aio.ClientSession.__init__
            def _no_trust_init(self, *a, **kw):
                kw['trust_env'] = False
                _orig_cs_init(self, *a, **kw)
            _aio.ClientSession.__init__ = _no_trust_init
        except ImportError:
            pass

        # --- 3. Replace the crawl tool ---
        # DeerFlow's Jina crawler calls https://r.jina.ai/ (external).
        # We provide a tool that directly fetches sandbox URLs and extracts text.
        import requests as _req
        from langchain_core.tools import tool as _tool_dec

        @_tool_dec
        def _sandbox_crawl(url: str) -> str:
            \"\"\"Crawl a URL and return readable content.\"\"\"
            try:
                r = _req.get(url, timeout=15)
                if r.status_code >= 400:
                    return json.dumps({{"error": f"HTTP {{r.status_code}}", "url": url}})
                text = r.text
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\\s+', ' ', text).strip()[:2000]
                return json.dumps({{"url": url, "crawled_content": text}}, ensure_ascii=False)
            except Exception as e:
                return json.dumps({{"error": str(e), "url": url}})

        _sandbox_crawl.name = "crawl_tool"

        # Inject the sandbox crawl tool into DeerFlow's tool registry
        # BEFORE the graph is built.  This is the same injection point
        # that DeerFlow's MCP tool system uses.
        import src.tools as _tools_pkg
        import src.tools.crawl as _crawl_mod
        _tools_pkg.crawl_tool = _sandbox_crawl
        _crawl_mod.crawl_tool = _sandbox_crawl

        # Also patch in src.graph.nodes which imports crawl_tool at module
        # level from src.tools.
        import src.graph.nodes as _nodes_mod
        _nodes_mod.crawl_tool = _sandbox_crawl

        # --- 4. Build and run the graph ---
        from src.graph.builder import build_graph
        from src.config.configuration import get_recursion_limit

        graph = build_graph()

        QUERY = '{intent_escaped}'

        init_state = {{
            "messages": [{{"role": "user", "content": QUERY}}],
            "auto_accepted_plan": True,
            "enable_background_investigation": True,
            "enable_clarification": False,
            "research_topic": QUERY,
            "clarified_research_topic": QUERY,
        }}
        config = {{
            "configurable": {{
                "thread_id": "benchmark-run",
                "max_plan_iterations": 1,
                "max_step_num": 6,
                "mcp_settings": {{"servers": {{}}}},
            }},
            "recursion_limit": get_recursion_limit(default=80),
        }}

        async def _run():
            final_state = None
            async for s in graph.astream(
                input=init_state, config=config, stream_mode="values"
            ):
                final_state = s
                msgs = s.get("messages") or []
                if msgs:
                    last = msgs[-1]
                    role = getattr(last, "type", "") or getattr(last, "role", "")
                    name = getattr(last, "name", "") or ""
                    content = getattr(last, "content", "")
                    preview = content if isinstance(content, str) else str(content)
                    print(f"[{{role}}/{{name}}] {{preview[:300]}}", flush=True)
            return final_state

        final = asyncio.run(_run())
        report = ""
        if final:
            report = final.get("final_report") or ""
            if not isinstance(report, str):
                report = str(report)

        # Emit the report on a sentinel-delimited block so the parent
        # process can reliably extract it from mixed stdout.
        print("===DEERFLOW_REPORT_START===", flush=True)
        print(report, flush=True)
        print("===DEERFLOW_REPORT_END===", flush=True)
    """)


# Agent identifier for the auto-discovery registry. Must match the
# AGENT_NAME used in score files: data/results/deep_v3/deerflow__<task>_matrix.score.json
AGENT_NAME = "deerflow"


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Run DeerFlow and return the markdown report.

    Args:
        intent: The research query / task description.
        model: OpenAI-compatible model name (e.g. "deepseek-v4-flash").
        shim_url: Tavily-compatible search API URL (e.g. "http://localhost:8081").
        proxy_url: OpenAI-compatible LLM endpoint (e.g. "http://localhost:8088/v1").
        timeout_s: Subprocess timeout in seconds.

    Returns:
        The markdown report produced by DeerFlow, or an error string.
    """
    if not DEERFLOW_ROOT.exists():
        return f"(error: DeerFlow not found at {DEERFLOW_ROOT})"
    if not Path(DEERFLOW_PYTHON).exists():
        return f"(error: DeerFlow venv not found at {DEERFLOW_PYTHON})"

    # Acquire exclusive lock — multiple parallel workers cannot share the
    # ``conf.yaml`` and ``_benchmark_driver.py`` paths without trampling each
    # other. See _runner_lock.py for rationale.
    _lock_cm = runner_exclusive_lock("deerflow")
    _lock_cm.__enter__()

    # Write a temporary conf.yaml in DeerFlow's root
    conf_yaml_path = DEERFLOW_ROOT / "conf.yaml"
    conf_yaml_backup = None
    if conf_yaml_path.exists():
        conf_yaml_backup = conf_yaml_path.read_text()

    try:
        conf_yaml_path.write_text(_build_conf_yaml(shim_url))

        # Write the driver script to a temp file
        driver_code = _build_driver_script(intent, shim_url, timeout_s)
        driver_path = DEERFLOW_ROOT / "_benchmark_driver.py"
        driver_path.write_text(driver_code)

        # Build the subprocess environment
        env = {**os.environ}
        # Remove ALL proxy env vars — prevents aiohttp(trust_env=True)
        # from routing search through Mihomo to the real Tavily API.
        for key in list(env.keys()):
            if key.upper() in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                                'FTP_PROXY', 'NO_PROXY',
                                'http_proxy', 'https_proxy', 'all_proxy',
                                'ftp_proxy', 'no_proxy'):
                del env[key]
        # LLM configuration via DeerFlow's native env-var mechanism
        # (src/llms/llm.py  _get_env_llm_conf reads BASIC_MODEL__* vars)
        env["BASIC_MODEL__base_url"] = proxy_url
        env["BASIC_MODEL__model"] = model
        env["BASIC_MODEL__api_key"] = env.get("OPENAI_API_KEY", "sk-placeholder")
        # Search
        env["SEARCH_API"] = "tavily"
        env["TAVILY_API_KEY"] = "tvly-sandbox-fake-key"
        # Disable optional integrations that would fail in sandbox
        env.pop("JINA_API_KEY", None)
        env.pop("LANGSMITH_TRACING", None)
        env.pop("LANGSMITH_API_KEY", None)
        # Keep DEBUG for verbose logs
        env["DEBUG"] = "True"

        logger.info(
            "Starting DeerFlow subprocess: model=%s shim=%s proxy=%s",
            model, shim_url, proxy_url,
        )

        t0 = time.time()
        proc = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                [DEERFLOW_PYTHON, str(driver_path)],
                cwd=str(DEERFLOW_ROOT),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=env,
            ),
        )
        elapsed = time.time() - t0

        # Extract the report from stdout
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        if proc.returncode != 0:
            logger.error(
                "DeerFlow exited %d after %.0fs\nstderr (last 1000): %s",
                proc.returncode, elapsed, stderr[-1000:],
            )

        # Parse the report from the sentinel-delimited block
        report = _extract_report(stdout)

        if not report:
            # Fallback: return the raw stdout tail + error info
            logger.warning("No report extracted from DeerFlow output")
            snippet = stdout[-2000:] if stdout else "(no stdout)"
            err_snippet = stderr[-1000:] if stderr else "(no stderr)"
            return (
                f"(DeerFlow produced no report after {elapsed:.0f}s, "
                f"exit={proc.returncode})\n\n"
                f"--- stdout tail ---\n{snippet}\n\n"
                f"--- stderr tail ---\n{err_snippet}"
            )

        logger.info(
            "DeerFlow completed in %.0fs, report=%d chars",
            elapsed, len(report),
        )
        return report

    except subprocess.TimeoutExpired:
        logger.error("DeerFlow timed out after %ds", timeout_s)
        return f"(DeerFlow timeout after {timeout_s}s)"
    except Exception as e:
        logger.exception("DeerFlow runner error")
        return f"(DeerFlow error: {e})"
    finally:
        # Restore original conf.yaml
        if conf_yaml_backup is not None:
            conf_yaml_path.write_text(conf_yaml_backup)
        elif conf_yaml_path.exists():
            # We created it; leave it (don't delete, DeerFlow may need it)
            pass
        # Clean up driver script
        driver_path = DEERFLOW_ROOT / "_benchmark_driver.py"
        if driver_path.exists():
            driver_path.unlink(missing_ok=True)
        # Release the cross-process lock now that conf/driver files are restored.
        try:
            _lock_cm.__exit__(None, None, None)
        except Exception:
            logger.exception("deerflow lock release failed")


def _extract_report(stdout: str) -> str:
    """Extract the report from the sentinel-delimited block in stdout."""
    start_marker = "===DEERFLOW_REPORT_START==="
    end_marker = "===DEERFLOW_REPORT_END==="

    start_idx = stdout.find(start_marker)
    end_idx = stdout.find(end_marker)

    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return ""

    report = stdout[start_idx + len(start_marker):end_idx].strip()
    return report


# ---------------------------------------------------------------------------
# CLI entry point for standalone testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run DeerFlow benchmark")
    parser.add_argument("intent", help="Research query")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--shim-url", default="http://localhost:8081")
    parser.add_argument("--proxy-url", default="http://localhost:8088/v1")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--output", "-o", help="Write report to file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    report = asyncio.run(
        run(
            intent=args.intent,
            model=args.model,
            shim_url=args.shim_url,
            proxy_url=args.proxy_url,
            timeout_s=args.timeout,
        )
    )

    if args.output:
        Path(args.output).write_text(report)
        print(f"Report written to {args.output} ({len(report)} chars)")
    else:
        print(report)
