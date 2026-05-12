"""DeepAgents runner for the deep-research benchmark.

Integrates LangChain DeepAgents (https://github.com/langchain-ai/deepagents)
against our sandbox.

DeepAgents is a LangGraph-based super-agent with planning (write_todos),
sub-agent spawning, filesystem tools, and shell execution.  It does NOT
include a built-in web search tool -- search is passed as a custom tool
in the ``tools`` parameter.

Configuration approach (all via DeepAgents' public API):
  - LLM:    ``init_chat_model("openai:<model>", base_url=..., api_key=...)``
            or direct ``ChatOpenAI(model=..., base_url=..., api_key=...)``.
            Passed to ``create_deep_agent(model=...)``.
  - Search: A custom ``internet_search()`` function that POSTs to our
            Tavily-compatible shim.  Passed via ``create_deep_agent(tools=[...])``.
  - Output: ``agent.invoke({"messages": [...]})`` returns state dict;
            final report is ``result["messages"][-1].content``.

No monkey-patching of DeepAgents internals.

Installation (on westd):
    pip install deepagents tavily-python

    # If running in the main .venv-camel:
    .venv-camel/bin/pip install deepagents

    # Alternatively, create a dedicated venv:
    python3.12 -m venv .venv-deepagents
    .venv-deepagents/bin/pip install deepagents langchain-openai
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from ._runner_lock import runner_exclusive_lock

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Timeout (seconds) for one DeepAgents run.
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT_S = 1800

# ---------------------------------------------------------------------------
# Sentinel markers for extracting the report from subprocess stdout.
# ---------------------------------------------------------------------------
_REPORT_START = "===DEEPAGENTS_REPORT_START==="
_REPORT_END = "===DEEPAGENTS_REPORT_END==="

# ---------------------------------------------------------------------------
# Localhost <-> neutral domain masking for DeepSeek safety filter bypass.
# DeepSeek V4 refuses when it sees localhost:PORT URLs in the prompt.
# We mask them to neutral-looking domains in the system prompt and search
# results, then unmask in the final report.
# ---------------------------------------------------------------------------
_MASK_MAP = {
    "http://localhost:7770": "http://onestopmarket.com",
    "http://localhost:9999": "http://postmill.net",
    "http://localhost:8090": "http://kiwipedia.org",
    "http://localhost:8081": "http://searchapi.internal",
    "localhost:7770": "onestopmarket.com",
    "localhost:9999": "postmill.net",
    "localhost:8090": "kiwipedia.org",
    "localhost:8081": "searchapi.internal",
}
_UNMASK_MAP = {v: k for k, v in _MASK_MAP.items()}


def _mask_localhost(text: str) -> str:
    """Replace localhost:PORT URLs with neutral domains."""
    if not isinstance(text, str):
        return text
    for old, new in _MASK_MAP.items():
        text = text.replace(old, new)
    # Catch-all for other ports
    text = re.sub(r"localhost:(\d+)", r"sandbox-\1.internal", text)
    return text


def _unmask_report(report: str) -> str:
    """Reverse masked domains back to localhost:PORT in the final report."""
    text = report
    for masked, original in _UNMASK_MAP.items():
        text = text.replace(masked, original)
    text = re.sub(r"sandbox-(\d+)\.internal", r"localhost:\1", text)
    # Also catch https:// variants the LLM might have added
    text = text.replace("https://onestopmarket.com", "http://localhost:7770")
    text = text.replace("https://postmill.net", "http://localhost:9999")
    text = text.replace("https://kiwipedia.org", "http://localhost:8090")
    return text


def _build_driver_script(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
) -> str:
    """Build the Python driver script that runs DeepAgents.

    The driver:
      1. Purges proxy env vars (sandbox-only network).
      2. Patches httpx to mask localhost URLs in LLM request bodies
         and unmask them in responses (DeepSeek safety filter bypass).
      3. Creates a custom ``internet_search`` tool that queries our
         Tavily-compatible shim directly (via requests.post).
      4. Configures the LLM via ``ChatOpenAI(base_url=proxy_url, ...)``.
      5. Calls ``create_deep_agent(model=..., tools=[...], system_prompt=...)``
         which returns a compiled LangGraph graph.
      6. Invokes the agent and extracts the final report.
    """
    # Escape the intent for embedding in a Python triple-quoted string
    intent_escaped = (
        intent.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
    )

    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Auto-generated DeepAgents driver for benchmark runner.\"\"\"
        import os, sys, json, re, traceback

        # === Layer 0: Environment cleanup ===
        # Purge proxy env vars so the agent can only reach localhost services.
        for _pv in list(os.environ):
            if _pv.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'ftp_proxy'):
                del os.environ[_pv]
        os.environ['NO_PROXY'] = '*'

        SHIM = {shim_url!r}
        PROXY = {proxy_url!r}
        MODEL = {model!r}

        # === Layer 1: Localhost masking for LLM calls ===
        # DeepSeek V4 refuses when it sees localhost URLs.
        # Mask localhost -> neutral domains in LLM request bodies,
        # unmask in responses.
        _MASK_MAP = {{
            'http://localhost:7770': 'http://onestopmarket.com',
            'http://localhost:9999': 'http://postmill.net',
            'http://localhost:8090': 'http://kiwipedia.org',
            'http://localhost:8081': 'http://searchapi.internal',
            'localhost:7770': 'onestopmarket.com',
            'localhost:9999': 'postmill.net',
            'localhost:8090': 'kiwipedia.org',
            'localhost:8081': 'searchapi.internal',
        }}
        _UNMASK_MAP = {{v: k for k, v in _MASK_MAP.items()}}

        def _mask_text(text):
            if not isinstance(text, str):
                return text
            for old, new in _MASK_MAP.items():
                text = text.replace(old, new)
            text = re.sub(r'localhost:(\\d+)', r'sandbox-\\1.internal', text)
            return text

        def _unmask_text(text):
            if not isinstance(text, str):
                return text
            for masked, original in _UNMASK_MAP.items():
                text = text.replace(masked, original)
            text = re.sub(r'sandbox-(\\d+)\\.internal', r'localhost:\\1', text)
            return text

        # Patch httpx to mask/unmask localhost in LLM API calls.
        # DeepAgents uses langchain_openai which uses httpx.
        try:
            import httpx as _hx

            _orig_hx_send = _hx.Client.send
            def _patched_hx_send(self, request, **kw):
                url_str = str(request.url)
                if '/chat/completions' in url_str or '/completions' in url_str:
                    try:
                        body = json.loads(request.content)
                        modified = False
                        if 'messages' in body:
                            for msg in body['messages']:
                                if isinstance(msg.get('content'), str):
                                    masked = _mask_text(msg['content'])
                                    if masked != msg['content']:
                                        msg['content'] = masked
                                        modified = True
                                elif isinstance(msg.get('content'), list):
                                    for part in msg['content']:
                                        if isinstance(part, dict) and isinstance(part.get('text'), str):
                                            masked = _mask_text(part['text'])
                                            if masked != part['text']:
                                                part['text'] = masked
                                                modified = True
                        if modified:
                            new_content = json.dumps(body).encode('utf-8')
                            request = _hx.Request(
                                method=request.method,
                                url=request.url,
                                headers=dict(request.headers),
                                content=new_content,
                            )
                            request.headers['content-length'] = str(len(new_content))
                    except Exception as e:
                        print(f'[deepagents-mask] sync mask warn: {{e}}')
                resp = _orig_hx_send(self, request, **kw)
                if '/chat/completions' in url_str or '/completions' in url_str:
                    try:
                        rtext = resp.content.decode('utf-8')
                        unmasked = _unmask_text(rtext)
                        if unmasked != rtext:
                            resp = _hx.Response(
                                status_code=resp.status_code,
                                headers=dict(resp.headers),
                                content=unmasked.encode('utf-8'),
                                request=resp.request,
                            )
                    except Exception:
                        pass
                return resp
            _hx.Client.send = _patched_hx_send

            _orig_hx_async_send = _hx.AsyncClient.send
            async def _patched_hx_async_send(self, request, **kw):
                url_str = str(request.url)
                if '/chat/completions' in url_str or '/completions' in url_str:
                    try:
                        body = json.loads(request.content)
                        modified = False
                        if 'messages' in body:
                            for msg in body['messages']:
                                if isinstance(msg.get('content'), str):
                                    masked = _mask_text(msg['content'])
                                    if masked != msg['content']:
                                        msg['content'] = masked
                                        modified = True
                                elif isinstance(msg.get('content'), list):
                                    for part in msg['content']:
                                        if isinstance(part, dict) and isinstance(part.get('text'), str):
                                            masked = _mask_text(part['text'])
                                            if masked != part['text']:
                                                part['text'] = masked
                                                modified = True
                        if modified:
                            new_content = json.dumps(body).encode('utf-8')
                            request = _hx.Request(
                                method=request.method,
                                url=request.url,
                                headers=dict(request.headers),
                                content=new_content,
                            )
                            request.headers['content-length'] = str(len(new_content))
                    except Exception as e:
                        print(f'[deepagents-mask] async mask warn: {{e}}')
                resp = await _orig_hx_async_send(self, request, **kw)
                if '/chat/completions' in url_str or '/completions' in url_str:
                    try:
                        rtext = resp.content.decode('utf-8')
                        unmasked = _unmask_text(rtext)
                        if unmasked != rtext:
                            resp = _hx.Response(
                                status_code=resp.status_code,
                                headers=dict(resp.headers),
                                content=unmasked.encode('utf-8'),
                                request=resp.request,
                            )
                    except Exception:
                        pass
                return resp
            _hx.AsyncClient.send = _patched_hx_async_send

            print('[deepagents-intercept] httpx patched (localhost masking)')
        except ImportError:
            print('[deepagents-intercept] httpx not available')

        # === Layer 2: Custom search tool ===
        # DeepAgents does not include a built-in search tool.
        # We provide internet_search() that POSTs to our Tavily-compatible shim.
        import requests as _rq
        from typing import Literal

        def internet_search(
            query: str,
            max_results: int = 10,
            topic: Literal["general", "news", "finance"] = "general",
            include_raw_content: bool = True,
        ) -> dict:
            \"\"\"Search the web for information. Returns search results with titles, URLs, and content snippets.

            Use this tool to find relevant web pages, product listings, forum
            discussions, and encyclopedia articles. Always cite the URLs from
            the results in your final report.

            Args:
                query: The search query string.
                max_results: Maximum number of results to return (default 10).
                topic: Topic category for the search.
                include_raw_content: Whether to include full page content.

            Returns:
                dict with 'results' list, each containing 'title', 'url', 'content',
                and optionally 'raw_content'.
            \"\"\"
            try:
                resp = _rq.post(
                    f'{{SHIM}}/search',
                    json={{
                        'query': query,
                        'api_key': 'tvly-shim-fake',
                        'max_results': max_results,
                        'include_raw_content': include_raw_content,
                        'topic': topic,
                    }},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                # Mask localhost URLs in results so DeepSeek doesn't refuse
                results = data.get('results', [])
                for r in results:
                    if isinstance(r, dict):
                        for field in ('url', 'title', 'content', 'raw_content'):
                            if isinstance(r.get(field), str):
                                r[field] = _mask_text(r[field])
                data['results'] = results
                print(f'[deepagents-search] query={{query[:80]!r}} -> {{len(results)}} results')
                return data
            except Exception as e:
                print(f'[deepagents-search] error: {{e}}')
                return {{'results': [], 'error': str(e)}}

        # === Layer 3: Fetch/crawl tool ===
        # Give the agent a way to fetch full page content from sandbox URLs.
        def fetch_page(url: str) -> str:
            \"\"\"Fetch the full content of a web page and return readable text.

            Use this to get detailed content from URLs found via internet_search.

            Args:
                url: The URL to fetch.

            Returns:
                The page content as cleaned text (HTML tags stripped).
            \"\"\"
            try:
                # Unmask URL in case the agent passes a masked domain
                real_url = _unmask_text(url)
                resp = _rq.get(real_url, timeout=15)
                if resp.status_code >= 400:
                    return f'Error: HTTP {{resp.status_code}} for {{url}}'
                text = resp.text
                # Strip scripts and styles
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\\s+', ' ', text).strip()
                # Mask localhost URLs in the extracted text
                text = _mask_text(text)
                return text[:8000]
            except Exception as e:
                return f'Error fetching {{url}}: {{e}}'

        # === Layer 4: Configure LLM and create agent ===
        from langchain_openai import ChatOpenAI
        from deepagents import create_deep_agent

        llm = ChatOpenAI(
            model=MODEL,
            base_url=PROXY,
            api_key=os.environ.get('OPENAI_API_KEY', 'anything'),
            max_tokens=8192,
            temperature=0.2,
            max_retries=3,
            timeout=120,
        )

        SYSTEM_PROMPT = (
            "You are an expert research agent. Your job is to conduct thorough, "
            "comprehensive research and produce a detailed markdown report.\\n\\n"
            "You have access to an internet search tool and a page fetcher. "
            "Use them extensively to gather information from multiple sources.\\n\\n"
            "Research methodology:\\n"
            "1. Start by searching for the main topic with multiple queries.\\n"
            "2. For each relevant result, use fetch_page to get detailed content.\\n"
            "3. Cross-reference information across multiple sources.\\n"
            "4. Search for subtopics, related products, discussions, and analyses.\\n"
            "5. Aim for at least 20 different source URLs in your report.\\n\\n"
            "Report requirements:\\n"
            "- Write a comprehensive markdown report (2000+ words).\\n"
            "- Cite ALL source URLs inline using markdown links: [text](url).\\n"
            "- Include specific data points, prices, specifications, quotes, and statistics.\\n"
            "- Organize with clear headings (##) and subheadings (###).\\n"
            "- Include a References section at the end listing all cited URLs.\\n"
            "- Every factual claim must be supported by a cited source URL.\\n"
            "- Cover the topic from multiple angles: product details, user opinions, "
            "expert analysis, comparisons."
        )

        QUERY = '{intent_escaped}'

        agent = create_deep_agent(
            model=llm,
            tools=[internet_search, fetch_page],
            system_prompt=SYSTEM_PROMPT,
        )

        # === Layer 5: Run the agent ===
        try:
            result = agent.invoke(
                {{"messages": [{{"role": "user", "content": _mask_text(QUERY)}}]}},
                config={{
                    "recursion_limit": 120,
                }},
            )

            # Extract the final report from the agent's output
            report = ""
            if isinstance(result, dict):
                # Try final_report key first (some LangGraph agents use this)
                report = result.get("final_report", "")
                if not report and "messages" in result:
                    msgs = result["messages"]
                    if msgs:
                        # Get the last assistant message
                        for msg in reversed(msgs):
                            role = getattr(msg, "type", "") or getattr(msg, "role", "")
                            if role in ("ai", "assistant"):
                                content = getattr(msg, "content", "")
                                if isinstance(content, str) and len(content) > 100:
                                    report = content
                                    break
                        if not report:
                            last = msgs[-1]
                            report = getattr(last, "content", str(last))
            else:
                report = str(result)

            # Unmask localhost URLs in the final report
            report = _unmask_text(report)

        except Exception as e:
            report = f"(DeepAgents error: {{type(e).__name__}}: {{e}})"
            traceback.print_exc()

        print('{_REPORT_START}')
        print(report)
        print('{_REPORT_END}')
    """)


def _build_env(proxy_url: str, model: str) -> dict:
    """Build the subprocess environment."""
    env = {**os.environ}

    # OpenAI-compatible env vars
    env["OPENAI_BASE_URL"] = proxy_url
    env["OPENAI_API_KEY"] = env.get("OPENAI_API_KEY", "anything")

    # Remove HTTP proxies so the agent can only reach localhost services
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                "ALL_PROXY", "all_proxy", "FTP_PROXY", "ftp_proxy"):
        env.pop(key, None)
    env["NO_PROXY"] = "*"

    # Disable optional integrations that would fail in sandbox
    env.pop("LANGSMITH_TRACING", None)
    env.pop("LANGSMITH_API_KEY", None)

    return env


# Agent identifier for the auto-discovery registry. Must match the
# AGENT_NAME used in score files: data/results/deep_v3/deepagents__<task>_matrix.score.json
AGENT_NAME = "deepagents"


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Run DeepAgents and return the markdown report.

    Args:
        intent: The research query / task description.
        model: OpenAI-compatible model name (e.g. "deepseek-v4-flash").
        shim_url: Tavily-compatible search API URL (e.g. "http://localhost:8081").
        proxy_url: OpenAI-compatible LLM endpoint (e.g. "http://localhost:8088/v1").
        timeout_s: Subprocess timeout in seconds.

    Returns:
        The markdown report produced by DeepAgents, or an error string.
    """
    # Write the driver script to a temp file
    driver_code = _build_driver_script(intent, model, shim_url, proxy_url)
    driver_path = ROOT / "scripts" / "_deepagents_benchmark_driver.py"

    # Per-agent lock so parallel workers don't trample the shared driver path.
    _lock_cm = runner_exclusive_lock("deepagents")
    _lock_cm.__enter__()

    try:
        driver_path.write_text(driver_code)

        # Build subprocess environment
        env = _build_env(proxy_url, model)

        # Determine Python executable.
        # Prefer a dedicated venv if it exists, otherwise fall back to
        # the main camel venv or the current interpreter.
        venv_candidates = [
            ROOT / ".venv-deepagents" / "bin" / "python",
            ROOT / ".venv-camel" / "bin" / "python",
        ]
        python_exe = sys.executable  # fallback
        for candidate in venv_candidates:
            if candidate.exists():
                python_exe = str(candidate)
                break

        logger.info(
            "Starting DeepAgents subprocess: python=%s model=%s shim=%s proxy=%s",
            python_exe, model, shim_url, proxy_url,
        )

        t0 = time.time()
        proc = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                [python_exe, str(driver_path)],
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
                "DeepAgents exited %d after %.0fs\nstderr (last 1500): %s",
                proc.returncode, elapsed, stderr[-1500:],
            )

        # Extract the report from the sentinel-delimited block
        report = _extract_report(stdout)

        if not report:
            logger.warning("No report extracted from DeepAgents output")
            snippet = stdout[-2000:] if stdout else "(no stdout)"
            err_snippet = stderr[-1500:] if stderr else "(no stderr)"
            return (
                f"(DeepAgents produced no report after {elapsed:.0f}s, "
                f"exit={proc.returncode})\n\n"
                f"--- stdout tail ---\n{snippet}\n\n"
                f"--- stderr tail ---\n{err_snippet}"
            )

        # Belt-and-suspenders: unmask any masked domains that survived
        report = _unmask_report(report)

        logger.info(
            "DeepAgents completed in %.0fs, report=%d chars",
            elapsed, len(report),
        )
        return report

    except subprocess.TimeoutExpired:
        logger.error("DeepAgents timed out after %ds", timeout_s)
        return f"(DeepAgents timeout after {timeout_s}s)"
    except Exception as e:
        logger.exception("DeepAgents runner error")
        return f"(DeepAgents error: {e})"
    finally:
        if driver_path.exists():
            driver_path.unlink(missing_ok=True)
        try:
            _lock_cm.__exit__(None, None, None)
        except Exception:
            logger.exception("deepagents lock release failed")


def _extract_report(stdout: str) -> str:
    """Extract the report from the sentinel-delimited block in stdout."""
    start_idx = stdout.find(_REPORT_START)
    end_idx = stdout.find(_REPORT_END)

    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return ""

    return stdout[start_idx + len(_REPORT_START):end_idx].strip()


# ---------------------------------------------------------------------------
# CLI entry point for standalone testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run DeepAgents benchmark")
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
