"""gpt-researcher runner for the deep-research benchmark.

Runs gpt-researcher 0.12.3 in its own venv (.venv-gptr) as a subprocess,
because gpt-researcher 0.12.3 imports langchain pre-1.0 submodules
(``langchain.docstore``, ``.vectorstores``, ``.text_splitter``, ``.callbacks``,
``.schema``, ...) that don't exist in langchain 1.x.  The main benchmark
venv (.venv-camel) runs langchain 1.x for langchain-odr, so gpt-researcher
needs its own isolated environment.

Configuration approach:
  - Patch ``gpt_researcher.retrievers.tavily.tavily_search.TavilySearch.__init__``
    inside the subprocess to set ``self.base_url = f"{shim_url}/search"``.
  - Set OPENAI_BASE_URL/OPENAI_API_KEY pointing at our ds_proxy.
  - Set FAST_LLM/SMART_LLM/STRATEGIC_LLM/RETRIEVER/EMBEDDING env vars so
    gpt-researcher reads our proxy instead of real OpenAI.
  - Use the "custom:text-embedding-v4" embedding alias so OpenAIEmbeddings
    reads OPENAI_BASE_URL (-> ds_proxy mapped to DashScope text-embedding-v4)
    instead of hitting the real OpenAI endpoint.

Pipeline:
  - Sanitize is NOT performed here: gpt-researcher's report writer is robust
    to localhost URLs in the intent (we did NOT add sanitization to the
    in-process runner originally).
  - Append CITATION REQUIREMENTS so the report cites all three sandbox
    sources (shopping / reddit / wikipedia).
  - Launch subprocess in .venv-gptr, run conduct_research + write_report.
  - Report is emitted between sentinels and extracted by the parent.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import textwrap
import time
from pathlib import Path

from ._runner_lock import runner_exclusive_lock

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
GPTR_PYTHON = str(ROOT / ".venv-gptr" / "bin" / "python")

# ---------------------------------------------------------------------------
# Timeout for one run.  conduct_research + write_report typically finishes
# within 10-15 minutes on this benchmark; allow a generous window.
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT_S = 1800

# ---------------------------------------------------------------------------
# Sentinel markers for extracting the report from subprocess stdout.
# ---------------------------------------------------------------------------
_REPORT_START = "===GPTR_REPORT_START==="
_REPORT_END = "===GPTR_REPORT_END==="

# Agent identifier for the auto-discovery registry.
AGENT_NAME = "gpt-researcher"


def _build_driver_script(
    intent: str,
    shim_url: str,
    proxy_url: str,
    model: str,
) -> str:
    """Build the Python driver script that runs inside .venv-gptr.

    Reproduces what scripts/run_deep_task.py::_run_gpt_researcher used to do
    in-process, minus the langchain 1.x compatibility shims (.venv-gptr has
    langchain 0.3.x already).
    """
    enhanced_intent = (
        intent + "\n\n"
        "CITATION REQUIREMENTS:\n"
        "- You MUST cite Wikipedia/encyclopedia articles as markdown links for technical definitions.\n"
        "- Include at least 15 Wikipedia article citations (e.g. [Active noise control](http://localhost:8090/...)).\n"
        "- Cite all three source types: shopping product pages, forum/reddit threads, AND Wikipedia articles.\n"
        "- Every factual claim needs a `[label](url)` markdown link."
    )

    # Use repr() to embed the intent as a single Python string literal —
    # safer than triple-quote delimiters because the intent may contain
    # quotes, backslashes, or anything else.  repr() escapes them all.
    intent_repr = repr(enhanced_intent)

    # Build the driver source at column 0 (NO leading indent) so we don't
    # have to rely on textwrap.dedent — dedent breaks when f-string
    # substitution introduces lines with different indentation.
    return f'''#!/usr/bin/env python3
"""Auto-generated gpt-researcher driver for benchmark runner."""
import os, sys, asyncio, traceback

# === Layer 0: Environment cleanup ===
# Purge any HTTP proxy env vars so the subprocess can only reach
# localhost services (the parent launcher does this too, but be safe).
for _pv in list(os.environ):
    if _pv.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'ftp_proxy'):
        del os.environ[_pv]
os.environ['NO_PROXY'] = '*'

SHIM = {shim_url!r}
PROXY = {proxy_url!r}
MODEL = {model!r}

# === Layer 1: gpt-researcher env vars ===
# ds_proxy is OpenAI-compatible.  gpt-researcher's "openai:<model>"
# provider path uses OPENAI_BASE_URL.
os.environ['OPENAI_BASE_URL'] = PROXY
os.environ['OPENAI_API_BASE'] = PROXY
os.environ.setdefault('OPENAI_API_KEY', 'anything')

os.environ.setdefault('FAST_LLM',      f'openai:{{MODEL}}')
os.environ.setdefault('SMART_LLM',     f'openai:{{MODEL}}')
os.environ.setdefault('STRATEGIC_LLM', f'openai:{{MODEL}}')
os.environ.setdefault('RETRIEVER',     'tavily')
# "custom" provider so OpenAIEmbeddings reads OPENAI_BASE_URL
# (-> ds_proxy mapped to DashScope text-embedding-v4).
os.environ.setdefault('EMBEDDING',     'custom:text-embedding-v4')
os.environ.setdefault('TAVILY_API_KEY', 'tvly-shim-fake')

# Disable optional integrations
os.environ.pop('LANGSMITH_TRACING', None)
os.environ.pop('LANGSMITH_API_KEY', None)
os.environ.pop('LANGCHAIN_TRACING_V2', None)

# === Layer 2: Patch TavilySearch to use our shim ===
try:
    import gpt_researcher.retrievers.tavily.tavily_search as _tm
    _orig = _tm.TavilySearch.__init__
    def _patched(self, *a, **kw):
        _orig(self, *a, **kw)
        self.base_url = f'{{SHIM}}/search'
    _tm.TavilySearch.__init__ = _patched
    print(f'[gptr-patch] TavilySearch.base_url -> {{SHIM}}/search')
except Exception as e:
    print(f'[gptr-patch] WARNING: could not patch TavilySearch: {{e}}')

# === Layer 3: Run gpt-researcher ===
from gpt_researcher import GPTResearcher

QUERY = {intent_repr}

async def _go():
    r = GPTResearcher(query=QUERY, report_type="research_report", tone="objective")
    await r.conduct_research()
    return await r.write_report()

try:
    report = asyncio.run(_go())
    if not report:
        report = "(gpt-researcher produced empty output)"
except Exception as e:
    report = f"(gpt-researcher error: {{type(e).__name__}}: {{e}})"
    traceback.print_exc()

print({_REPORT_START!r})
print(report)
print({_REPORT_END!r})
'''


def _build_env(proxy_url: str, model: str, shim_url: str) -> dict:
    """Build the subprocess environment."""
    env = {**os.environ}

    # OpenAI-compatible env vars (read by langchain_openai inside gpt-researcher)
    env["OPENAI_BASE_URL"] = proxy_url
    env["OPENAI_API_BASE"] = proxy_url
    env["OPENAI_API_KEY"] = env.get("OPENAI_API_KEY", "anything")

    # gpt-researcher LLM/retriever config
    env.setdefault("FAST_LLM",      f"openai:{model}")
    env.setdefault("SMART_LLM",     f"openai:{model}")
    env.setdefault("STRATEGIC_LLM", f"openai:{model}")
    env.setdefault("RETRIEVER",     "tavily")
    env.setdefault("EMBEDDING",     "custom:text-embedding-v4")
    env.setdefault("TAVILY_API_KEY", "tvly-shim-fake")
    env["GPTR_SHIM_URL"] = shim_url

    # Remove HTTP proxies so the subprocess can only reach localhost services
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                "ALL_PROXY", "all_proxy", "FTP_PROXY", "ftp_proxy"):
        env.pop(key, None)
    env["NO_PROXY"] = "*"

    # Disable optional integrations that would fail in sandbox
    env.pop("LANGSMITH_TRACING", None)
    env.pop("LANGSMITH_API_KEY", None)
    env.pop("LANGCHAIN_TRACING_V2", None)

    return env


def _extract_report(stdout: str) -> str:
    """Extract the report from the sentinel-delimited block in stdout."""
    start_idx = stdout.find(_REPORT_START)
    end_idx = stdout.find(_REPORT_END)

    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return ""

    return stdout[start_idx + len(_REPORT_START):end_idx].strip()


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Run gpt-researcher and return the markdown report.

    Args:
        intent: The research query / task description.
        model: OpenAI-compatible model name (e.g. "deepseek-v4-flash").
        shim_url: Tavily-compatible search API URL (e.g. "http://localhost:8081").
        proxy_url: OpenAI-compatible LLM endpoint (e.g. "http://localhost:8088/v1").
        timeout_s: Subprocess timeout in seconds.

    Returns:
        The markdown report, or an error string starting with
        "(gpt-researcher ...".
    """
    gptr_python = Path(GPTR_PYTHON)
    if not gptr_python.exists():
        return (
            f"(gpt-researcher: missing venv at {gptr_python})\n\n"
            "Installation:\n"
            "  cd /opt/deep_reserch\n"
            "  python3 -m venv .venv-gptr\n"
            "  .venv-gptr/bin/pip install gpt-researcher==0.12.3"
        )

    driver_code = _build_driver_script(intent, shim_url, proxy_url, model)
    driver_path = ROOT / "scripts" / "_gptr_benchmark_driver.py"

    # Per-agent lock so parallel workers don't trample the shared driver path.
    _lock_cm = runner_exclusive_lock("gpt-researcher")
    _lock_cm.__enter__()

    try:
        driver_path.write_text(driver_code)

        env = _build_env(proxy_url, model, shim_url)

        logger.info(
            "Starting gpt-researcher subprocess: model=%s shim=%s proxy=%s",
            model, shim_url, proxy_url,
        )

        t0 = time.time()
        proc = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                [str(gptr_python), str(driver_path)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=env,
            ),
        )
        elapsed = time.time() - t0

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        if proc.returncode != 0:
            logger.error(
                "gpt-researcher exited %d after %.0fs\nstderr (last 1500): %s",
                proc.returncode, elapsed, stderr[-1500:],
            )

        report = _extract_report(stdout)

        if not report:
            logger.warning("No report extracted from gpt-researcher output")
            snippet = stdout[-2000:] if stdout else "(no stdout)"
            err_snippet = stderr[-1500:] if stderr else "(no stderr)"
            return (
                f"(gpt-researcher produced no report after {elapsed:.0f}s, "
                f"exit={proc.returncode})\n\n"
                f"--- stdout tail ---\n{snippet}\n\n"
                f"--- stderr tail ---\n{err_snippet}"
            )

        logger.info(
            "gpt-researcher completed in %.0fs, report=%d chars",
            elapsed, len(report),
        )
        return report

    except subprocess.TimeoutExpired:
        logger.error("gpt-researcher timed out after %ds", timeout_s)
        return f"(gpt-researcher timeout after {timeout_s}s)"
    except Exception as e:
        logger.exception("gpt-researcher runner error")
        return f"(gpt-researcher error: {e})"
    finally:
        if driver_path.exists():
            driver_path.unlink(missing_ok=True)
        try:
            _lock_cm.__exit__(None, None, None)
        except Exception:
            logger.exception("gpt-researcher lock release failed")


# ---------------------------------------------------------------------------
# CLI entry point for standalone testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run gpt-researcher benchmark")
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
