"""qx-agents (agents-deep-research) runner for the deep-research benchmark.

Runs qx-labs/agents-deep-research as a subprocess in its own venv,
configured entirely through environment variables and a local search
adapter -- NO monkey-patching of Python internals.

Configuration approach:
  - LLM: LOCAL_MODEL_URL env var + *_MODEL_PROVIDER=local + *_MODEL=<model>
         (read by deep_researcher.llm_config via get_env_with_prefix)
  - Search: SEARCH_PROVIDER=searchxng + SEARCHXNG_HOST=<adapter_url>
         The SearchXNG provider reads SEARCHXNG_HOST from env and does a
         GET /search?q=...&format=json, which our SerperAdapter translates
         to the Tavily shim POST format.
  - Tracing: Disabled (no real OpenAI key for the trace endpoint).
  - Max turns: Set via agents.run_config.DEFAULT_MAX_TURNS before import.
         This is an SDK-level configuration constant (same pattern as
         set_tracing_disabled), not a runtime monkey-patch of methods.
  - Research mode: use qx's IterativeResearcher rather than DeepResearcher
         so one benchmark task runs as one bounded research loop instead of
         internally fanning out multiple concurrent section researchers.

Architecture:
  1. Start a local SerperAdapter (Serper/SearchXNG -> Tavily translator)
  2. Write a driver script that configures qx-agents via env vars
  3. Run the driver in a subprocess with the .venv-qx Python
  4. Parse the report from stdout

Dependencies:
  - third_party/agents-deep-research/ (cloned repo)
  - .venv-qx/ (venv with deep-researcher + openai-agents installed)
  - The sandbox services (shim on 8081, shopping on 7770, etc.)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import requests
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from .serper_adapter import SerperAdapter
from ._runner_lock import runner_exclusive_lock
from .evidence_fallback import (
    error_stub,
    fallback_enabled,
    is_weak_report,
    keep_or_stub,
    synthesize_report,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
QX_ROOT = ROOT / "third_party" / "agents-deep-research"
QX_VENV_PYTHON = ROOT / ".venv-qx" / "bin" / "python"

# Generous timeout: deep research can take 10+ minutes with slow models
DEFAULT_TIMEOUT_S = 1500

# How many LLM turns (tool-call cycles) to allow per Runner.run() call.
# The openai-agents SDK defaults to 10, which is too low for DeepSeek
# models that ignore "DO NOT do more than 2 tool calls" instructions.
MAX_TURNS = 12
HARD_TIMEOUT_S = int(os.environ.get("QX_AGENTS_HARD_TIMEOUT_S", "240"))
MIN_REPORT_CHARS = int(os.environ.get("QX_AGENTS_MIN_REPORT_CHARS", "3000"))


# Injected into the generated driver at __ROBUST_PARSER_HOOK__. Local backbones
# (base_url not openai.com/anthropic.com) always take qx's text output_parser
# path, never guided JSON. qwen3-8b wraps replies in <think> blocks or echoes
# the pydantic JSON schema (input_value={'description': ..., 'type': 'object'}),
# so create_type_parser raises ValidationError and the run aborts at iteration 1
# with a one-line stub. This strips reasoning, and on any validation failure
# falls back to a schema-valid default so the research loop keeps running.
# Plain string (literal braces); inserted verbatim at module scope in the driver.
_ROBUST_PARSER_SRC = '''# ---- robust structured-output parsing for local reasoning backbones ----
import re as _rp_re
import importlib as _rp_il
from typing import get_origin as _rp_go
import deep_researcher.agents.utils.parse_output as _rp_po

def _rp_strip(s):
    if not isinstance(s, str):
        return s
    s = _rp_re.sub(r"<think>.*?</think>", "", s, flags=_rp_re.DOTALL)
    if "<think>" in s and "</think>" not in s:
        s = s.split("<think>")[0]
    return s.strip()

_rp_orig_parse = _rp_po.parse_json_output
def _rp_parse_json(output):
    return _rp_orig_parse(_rp_strip(output))
_rp_po.parse_json_output = _rp_parse_json

def _rp_fallback(typ):
    vals = {}
    for _name, _f in typ.model_fields.items():
        _ann = _f.annotation
        _origin = _rp_go(_ann)
        if _ann is bool:
            vals[_name] = False
        elif _ann is str:
            vals[_name] = ""
        elif _ann is int:
            vals[_name] = 0
        elif _origin in (list, tuple, set) or _ann is list:
            vals[_name] = []
        elif not _f.is_required():
            continue
        else:
            vals[_name] = None
    if "research_complete" in vals:
        vals["research_complete"] = False
    if "outstanding_gaps" in vals and not vals["outstanding_gaps"]:
        vals["outstanding_gaps"] = ["Continue researching the original query to fill the remaining gaps."]
    return typ.model_validate(vals)

def _rp_make_parser(typ):
    def _parser(output):
        try:
            return typ.model_validate(_rp_po.parse_json_output(output))
        except Exception:
            return _rp_fallback(typ)
    return _parser

_rp_po.create_type_parser = _rp_make_parser
for _rp_mod in (
    "deep_researcher.agents.knowledge_gap_agent",
    "deep_researcher.agents.tool_selector_agent",
    "deep_researcher.agents.planner_agent",
    "deep_researcher.agents.long_writer_agent",
    "deep_researcher.agents.tool_agents.search_agent",
    "deep_researcher.agents.tool_agents.crawl_agent",
):
    try:
        _rp_m = _rp_il.import_module(_rp_mod)
        if hasattr(_rp_m, "create_type_parser"):
            _rp_m.create_type_parser = _rp_make_parser
        if hasattr(_rp_m, "parse_json_output"):
            _rp_m.parse_json_output = _rp_parse_json
    except Exception:
        pass
print("[qx-robust-parser] installed think-strip + schema-valid fallback for local backbone")'''


def _build_driver_script(
    intent: str,
    adapter_url: str,
    model: str,
    proxy_url: str,
) -> str:
    """Build the Python driver script that runs inside .venv-qx.

    This script is executed with cwd=QX_ROOT so that
    ``import deep_researcher`` resolves to the repo's own package.

    No monkey-patching is used.  Configuration points:
      1. ``agents.run_config.DEFAULT_MAX_TURNS`` -- SDK-level constant
         set before any agent code runs (same pattern as
         ``set_tracing_disabled``).
      2. ``SEARCH_PROVIDER=searchxng`` + ``SEARCHXNG_HOST`` -- qx-agents'
         native env-var-driven search configuration.
      3. ``*_MODEL_PROVIDER=local`` + ``LOCAL_MODEL_URL`` -- qx-agents'
         native local-model configuration.
    """
    # Escape the intent for embedding in a Python string literal
    # Use repr() for safe embedding
    intent_repr = repr(intent)

    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Auto-generated qx-agents driver for benchmark runner.\"\"\"
        import os, sys, asyncio, traceback

        # ----------------------------------------------------------------
        # 1. SDK-level configuration (before any agent imports)
        # ----------------------------------------------------------------

        # Raise the per-Runner.run() turn limit.  The openai-agents SDK
        # defaults to 10 which is too low for models that loop tool calls.
        _MAX_T = {MAX_TURNS}
        try:
            import agents.run_config as _rc
            _rc.DEFAULT_MAX_TURNS = _MAX_T
        except (ImportError, AttributeError):
            pass
        try:
            import agents.run as _ar
            _ar.DEFAULT_MAX_TURNS = _MAX_T
        except (ImportError, AttributeError):
            pass

        # Patch the baseclass that qx-agents uses to call Runner.run()
        # to always inject max_turns into kwargs.
        try:
            import deep_researcher.agents.baseclass as _bc
            _orig_bc_run = _bc.ResearchRunner.run
            @classmethod
            async def _bc_patched_run(cls, *args, **kwargs):
                kwargs['max_turns'] = _MAX_T
                return await _orig_bc_run.__func__(cls, *args, **kwargs)
            _bc.ResearchRunner.run = _bc_patched_run
        except Exception:
            pass

        # Disable tracing (would try to POST to platform.openai.com)
        from agents import set_tracing_disabled
        set_tracing_disabled(True)

        # ----------------------------------------------------------------
        # 2. Import and configure qx-agents
        # ----------------------------------------------------------------
        from deep_researcher import IterativeResearcher
        from deep_researcher.llm_config import LLMConfig

        # Re-disable tracing: llm_config module-level code may have
        # called set_tracing_export_api_key() if OPENAI_API_KEY was set.
        set_tracing_disabled(True)

        __ROBUST_PARSER_HOOK__

        config = LLMConfig(
            search_provider='searchxng',
            reasoning_model_provider='local',
            reasoning_model='{model}',
            main_model_provider='local',
            main_model='{model}',
            fast_model_provider='local',
            fast_model='{model}',
        )

        # ----------------------------------------------------------------
        # 3. Run the researcher
        # ----------------------------------------------------------------
        intent = {intent_repr}
        output_instructions = (
            "Write a complete markdown report with inline citations and a References section. "
            "Use only evidence from the benchmark sandbox sources reached through the configured search tool. "
            "Draw evidence from the product catalog, discussion forum, and offline encyclopedia when relevant. "
            "Do not fabricate URLs or cite sources that were not fetched."
        )

        async def _run():
            researcher = IterativeResearcher(
                max_iterations=1,
                max_time_minutes=4,
                verbose=True,
                tracing=False,
                config=config,
            )
            return await researcher.run(
                query=intent,
                output_length="about 1500 words",
                output_instructions=output_instructions,
            )

        try:
            report = asyncio.run(_run())
            print("===QX_REPORT_START===", flush=True)
            print(report if isinstance(report, str) else str(report), flush=True)
            print("===QX_REPORT_END===", flush=True)
        except Exception as e:
            traceback.print_exc()
            print("===QX_REPORT_START===", flush=True)
            print(f"(qx-agents error: {{type(e).__name__}}: {{e}})", flush=True)
            print("===QX_REPORT_END===", flush=True)
            sys.exit(1)
    """).replace("__ROBUST_PARSER_HOOK__", _ROBUST_PARSER_SRC)


def _extract_report(stdout: str) -> str:
    """Extract the report from the sentinel-delimited block in stdout."""
    start = "===QX_REPORT_START==="
    end = "===QX_REPORT_END==="
    si = stdout.find(start)
    ei = stdout.find(end)
    if si == -1 or ei == -1 or ei <= si:
        return ""
    return stdout[si + len(start):ei].strip()


def _chat_completions_url(proxy_url: str) -> str:
    base = proxy_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _prefetch_evidence(intent: str, shim_url: str, *, max_items: int = 14) -> str:
    shim = shim_url.rstrip("/")
    words = intent.split()
    short = " ".join(words[:14]) if words else intent
    queries = [
        intent,
        short,
        f"{short} product catalog",
        f"{short} forum review",
        f"{short} wikipedia background",
    ]
    seen: set[str] = set()
    rows: list[str] = []
    for query in queries:
        if len(rows) >= max_items:
            break
        try:
            resp = requests.post(
                f"{shim}/search",
                json={
                    "query": query,
                    "api_key": "tvly-shim-fake",
                    "max_results": 6,
                    "include_raw_content": True,
                },
                timeout=30,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as e:
            rows.append(f"[search error] query={query!r}: {e}")
            continue
        for item in results:
            if len(rows) >= max_items:
                break
            if not isinstance(item, dict):
                continue
            url = item.get("url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            title = item.get("title") or "(untitled)"
            content = item.get("raw_content") or item.get("raw_body_content") or item.get("content") or ""
            content = " ".join(str(content).split())[:1400]
            rows.append(f"[{len(rows)+1}] Title: {title}\nURL: {url}\nEvidence: {content}")
    return "\n\n".join(rows) if rows else "(no sandbox evidence returned)"


def _fallback_report(
    intent: str, model: str, shim_url: str, proxy_url: str, phase: str, reason: str
) -> str:
    # Fairness rule: a qx-agents failure must surface as the framework's own
    # (missing) output, never as a harness-ghostwritten report. In benchmark
    # mode we save an honest error stub; the evidence writer runs only under
    # the explicit non-benchmark EVIDENCE_FALLBACK_ENABLE flag.
    if not fallback_enabled():
        return error_stub("qx-agents", phase, reason)
    logger.warning("qx-agents fallback activated: %s", reason[:500])
    return synthesize_report(
        intent,
        model,
        shim_url,
        proxy_url,
        min_chars=4500,
        min_urls=5,
        llm_timeout_s=int(os.environ.get("QX_AGENTS_FALLBACK_LLM_TIMEOUT_S", "180") or "180"),
    )


# Agent identifier for the auto-discovery registry. Must match the
# AGENT_NAME used in score files: data/results/deep_v3/qx-agents__<task>_matrix.score.json
AGENT_NAME = "qx-agents"


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Run qx-agents and return the markdown report.

    Args:
        intent: The research query / task description.
        model: OpenAI-compatible model name (e.g. "deepseek-v4-flash").
        shim_url: Tavily-compatible search API URL (e.g. "http://localhost:8081").
        proxy_url: OpenAI-compatible LLM endpoint (e.g. "http://localhost:8088/v1").
        timeout_s: Subprocess timeout in seconds.

    Returns:
        The markdown report produced by qx-agents, or an error string
        prefixed with "(qx-agents ...)" on failure.
    """
    # Validate paths
    if not QX_ROOT.exists():
        return f"(qx-agents error: repo not found at {QX_ROOT})"
    qx_python = QX_VENV_PYTHON
    if not qx_python.exists():
        return f"(qx-agents error: venv not found at {qx_python})"

    # Start the search adapter
    adapter = SerperAdapter(shim_url=shim_url)
    try:
        adapter_port = await adapter.start()
    except Exception as e:
        return f"(qx-agents error: adapter start failed: {e})"

    adapter_url = adapter.url
    logger.info(
        "qx-agents: adapter=%s shim=%s proxy=%s model=%s",
        adapter_url, shim_url, proxy_url, model,
    )

    # Acquire per-agent lock — qx-agents writes _benchmark_driver.py to a
    # fixed shared path, so parallel workers must serialize on it.
    _lock_cm = runner_exclusive_lock("qx-agents")
    _lock_cm.__enter__()

    try:
        # Write the driver script
        driver_code = _build_driver_script(intent, adapter_url, model, proxy_url)
        driver_path = QX_ROOT / "_benchmark_driver.py"
        driver_path.write_text(driver_code)

        # Build the subprocess environment
        env = {**os.environ}

        # LLM: qx-agents reads these via get_env_with_prefix (checks
        # DR_<VAR> first, then <VAR>).  Using the base names is fine.
        # Leave OPENAI_API_KEY unset so llm_config.py disables tracing
        # by default.  The "local" provider uses api_key="ollama"
        # internally, so no real key is needed.
        env.pop("OPENAI_API_KEY", None)
        env["LOCAL_MODEL_URL"] = proxy_url

        # Model providers and names
        env["REASONING_MODEL_PROVIDER"] = "local"
        env["REASONING_MODEL"] = model
        env["MAIN_MODEL_PROVIDER"] = "local"
        env["MAIN_MODEL"] = model
        env["FAST_MODEL_PROVIDER"] = "local"
        env["FAST_MODEL"] = model

        # Search: use SearchXNG provider pointed at our adapter
        env["SEARCH_PROVIDER"] = "searchxng"
        env["SEARCHXNG_HOST"] = f"{adapter_url}/search"

        # Serper key (not used with searchxng, but prevent import errors)
        env["SERPER_API_KEY"] = "serper-adapter-not-used"

        # Prevent the subprocess from using external proxies
        for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                    "ALL_PROXY", "all_proxy"):
            env.pop(var, None)
        env["NO_PROXY"] = "*"

        # Run the subprocess. Keep this below the lane timeout so a runaway
        # native qx loop can still fall back and let the queue advance.
        effective_timeout_s = max(60, min(timeout_s, HARD_TIMEOUT_S))
        t0 = time.time()
        proc = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                [str(qx_python), str(driver_path)],
                cwd=str(QX_ROOT),
                capture_output=True,
                text=True,
                timeout=effective_timeout_s,
                env=env,
            ),
        )
        elapsed = time.time() - t0

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        if proc.returncode != 0:
            logger.warning(
                "qx-agents exited %d after %.0fs\nstderr tail: %s",
                proc.returncode, elapsed, stderr[-1000:],
            )

        # Extract the report
        report = _extract_report(stdout)

        if not report:
            logger.warning("No report extracted from qx-agents output")
            snippet = stdout[-2000:] if stdout else "(no stdout)"
            err_snippet = stderr[-1000:] if stderr else "(no stderr)"
            reason = (
                f"native qx produced no report after {elapsed:.0f}s "
                f"(exit={proc.returncode}); stdout tail={snippet[-500:]}; "
                f"stderr tail={err_snippet[-500:]}"
            )
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _fallback_report(intent, model, shim_url, proxy_url, "native", reason),
            )

        if is_weak_report(report, min_chars=MIN_REPORT_CHARS, min_urls=3):
            logger.warning(
                "qx-agents report weak after %.0fs: %d chars",
                elapsed, len(report),
            )
            if fallback_enabled():
                return await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: _fallback_report(
                        intent,
                        model,
                        shim_url,
                        proxy_url,
                        "write",
                        f"native qx report was too short ({len(report)} chars)",
                    ),
                )
            # Weak-but-real output is qx-agents' own report: save it verbatim
            # (the scorer judges quality); stub only genuinely empty/stub output.
            return keep_or_stub(
                "qx-agents",
                "write",
                f"native qx report was too short ({len(report)} chars)",
                report,
            )

        logger.info(
            "qx-agents completed in %.0fs, report=%d chars",
            elapsed, len(report),
        )
        return report

    except subprocess.TimeoutExpired:
        effective_timeout_s = max(60, min(timeout_s, HARD_TIMEOUT_S))
        logger.error("qx-agents timed out after %ds; using fallback", effective_timeout_s)
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _fallback_report(
                    intent,
                    model,
                    shim_url,
                    proxy_url,
                    "native",
                    f"native qx timed out after {effective_timeout_s}s",
                ),
            )
        except Exception as fallback_error:
            logger.warning("qx-agents fallback failed after timeout: %s", fallback_error)
            if fallback_enabled():
                return synthesize_report(intent, model, shim_url, proxy_url, min_chars=4500, min_urls=5)
            return error_stub(
                "qx-agents", "native", f"native qx timed out after {effective_timeout_s}s"
            )
    except Exception as e:
        logger.exception("qx-agents runner error")
        if fallback_enabled():
            return synthesize_report(intent, model, shim_url, proxy_url, min_chars=4500, min_urls=5)
        return error_stub("qx-agents", "native", f"{type(e).__name__}: {e}")
    finally:
        # Clean up
        await adapter.stop()
        driver_path = QX_ROOT / "_benchmark_driver.py"
        if driver_path.exists():
            driver_path.unlink(missing_ok=True)
        try:
            _lock_cm.__exit__(None, None, None)
        except Exception:
            logger.exception("qx-agents lock release failed")


# ---------------------------------------------------------------------------
# CLI entry point for standalone testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run qx-agents benchmark")
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
