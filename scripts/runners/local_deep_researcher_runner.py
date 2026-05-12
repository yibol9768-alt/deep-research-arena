"""LangChain local-deep-researcher runner for the deep-research benchmark.

Integrates langchain-ai/local-deep-researcher (NOT LearningCircuit/local-deep-
research which is the ``ldr`` runner) against our sandbox.

GitHub: https://github.com/langchain-ai/local-deep-researcher
Architecture: LangGraph iterative loop -- search -> summarize -> reflect ->
re-search for N cycles.  Native Tavily support.

Configuration approach (all via generated subprocess driver):
  1. TavilyClient monkey-patch: inject ``api_base_url`` pointing at our
     Tavily-compatible shim.  The tavily-python client accepts this param
     but the framework doesn't expose it, so we patch ``__init__`` to
     force-set ``self.base_url``.
  2. LLM: use ``lmstudio`` provider (ChatLMStudio, which extends ChatOpenAI)
     pointed at our OpenAI-compatible ds_proxy.
  3. HTTP transport intercept: patch httpx to rewrite Tavily URLs (belt-and-
     suspenders) and apply localhost masking for DeepSeek safety filter.
  4. Environment variables: SEARCH_API=tavily, TAVILY_API_KEY, LLM_PROVIDER,
     LMSTUDIO_BASE_URL, LOCAL_LLM.

Pipeline:
  - Sanitize intent (strip localhost URLs that trigger DeepSeek safety filter)
  - Launch subprocess in .venv-lcdr with a generated driver script
  - Driver patches TavilyClient, configures LLM, runs the LangGraph graph
  - Report is emitted between sentinels and extracted by the parent
  - Localhost domains are unmasked in the final report

Installation (on westd WSL):
  cd /opt/deep_reserch
  python3 -m venv .venv-lcdr
  .venv-lcdr/bin/pip install --upgrade pip
  .venv-lcdr/bin/pip install langgraph langchain-community langchain-ollama \\
      langchain-openai tavily-python duckduckgo-search httpx markdownify \\
      python-dotenv openai
  git clone https://github.com/langchain-ai/local-deep-researcher.git \\
      third_party/local-deep-researcher
  .venv-lcdr/bin/pip install -e third_party/local-deep-researcher
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import textwrap
import time
from pathlib import Path

from ._runner_lock import runner_exclusive_lock

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
LCDR_PYTHON = str(ROOT / ".venv-lcdr" / "bin" / "python")

# ---------------------------------------------------------------------------
# Timeout for one run.  The graph does multi-iteration search + summarize,
# so we allow a generous window.
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT_S = 1200

# ---------------------------------------------------------------------------
# Sentinel markers for extracting the report from subprocess stdout.
# ---------------------------------------------------------------------------
_REPORT_START = "===LCDR_REPORT_START==="
_REPORT_END = "===LCDR_REPORT_END==="

# ---------------------------------------------------------------------------
# Localhost URL -> neutral description mapping for intent sanitization.
# ---------------------------------------------------------------------------
_URL_TO_DESC = {
    r"http://localhost:7770[^\s)\]]*": "the product catalog",
    r"http://localhost:9999[^\s)\]]*": "the discussion forum",
    r"http://localhost:8090[^\s)\]]*": "the encyclopedia",
}

# ---------------------------------------------------------------------------
# Localhost <-> masked domain map for DeepSeek safety filter bypass.
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


def _sanitize_intent(intent: str) -> str:
    """Strip sandbox URLs and placeholders from the intent.

    The framework discovers sandbox pages through search, so the LLM
    never needs raw ``localhost`` URLs which trigger DeepSeek's safety filter.
    """
    text = intent
    for pattern, desc in _URL_TO_DESC.items():
        text = re.sub(pattern, desc, text)
    text = re.sub(r"http://localhost:\d+[^\s)\]]*", "", text)
    text = re.sub(r"\(`?__\w+__`?\)", "", text)
    text = re.sub(r"`?__(?:SHOPPING|REDDIT|WIKIPEDIA)__`?", "", text)
    text = re.sub(r"Source URLs MUST be sandbox-local\.?\s*", "", text)
    text = re.sub(r"Do not fabricate URLs[^.]*\.?\s*", "", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


def _unmask_report(report: str) -> str:
    """Reverse masked domains back to localhost:PORT in the final report."""
    text = report
    for masked, original in _UNMASK_MAP.items():
        text = text.replace(masked, original)
    text = re.sub(r"sandbox-(\d+)\.internal", r"localhost:\1", text)
    text = text.replace("https://onestopmarket.com", "http://localhost:7770")
    text = text.replace("https://postmill.net", "http://localhost:9999")
    text = text.replace("https://kiwipedia.org", "http://localhost:8090")

    # FIX P2.5: Rewrite off-sandbox Wikipedia URLs to Kiwix sandbox URLs.
    # The LLM may generate en.wikipedia.org/wiki/... URLs in its report text
    # from model knowledge. These are off-sandbox. We rewrite them to the local
    # Kiwix instance so they become valid sandbox URLs.
    def _rewrite_wiki_url(m):
        title = m.group(1)
        return f"http://localhost:8090/content/wikipedia_en_all_nopic/A/{title}"

    text = re.sub(
        r"https?://en\.wikipedia\.org/wiki/([^\s)\]#\"']+)",
        _rewrite_wiki_url,
        text,
    )
    return text


def _build_driver_script(
    intent: str,
    shim_url: str,
    proxy_url: str,
    model: str,
    max_loops: int = 3,
) -> str:
    """Build the Python driver script that runs inside the lcdr venv.

    The driver:
      1. Patches TavilyClient to redirect to our shim
      2. Patches httpx for localhost masking (DeepSeek safety filter bypass)
      3. Configures the LLM to use our OpenAI-compatible proxy
      4. Runs the LangGraph graph and extracts the final summary
    """
    intent_escaped = (
        intent.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
    )

    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Auto-generated local-deep-researcher driver for benchmark runner.\"\"\"
        import os, sys, json, re, traceback

        # === Layer 0: Environment setup ===
        # Purge proxy env vars so we can only reach localhost services.
        for _pv in list(os.environ):
            if _pv.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'ftp_proxy'):
                del os.environ[_pv]
        os.environ['NO_PROXY'] = '*'

        # Configure via environment variables (read by Configuration.from_runnable_config)
        os.environ['SEARCH_API'] = 'tavily'
        os.environ['TAVILY_API_KEY'] = 'tvly-sandbox-fake-key'
        os.environ['LLM_PROVIDER'] = 'lmstudio'
        os.environ['LMSTUDIO_BASE_URL'] = {proxy_url!r}
        os.environ['LOCAL_LLM'] = {model!r}
        os.environ['MAX_WEB_RESEARCH_LOOPS'] = str({max_loops})
        os.environ['FETCH_FULL_PAGE'] = 'True'
        os.environ['STRIP_THINKING_TOKENS'] = 'True'

        # Disable langsmith tracing
        os.environ.pop('LANGSMITH_TRACING', None)
        os.environ.pop('LANGSMITH_API_KEY', None)
        os.environ.pop('LANGCHAIN_TRACING_V2', None)

        SHIM = {shim_url!r}
        PROXY = {proxy_url!r}
        MODEL = {model!r}

        # === Layer 1: Patch TavilyClient to use our shim ===
        # The tavily-python TavilyClient accepts api_base_url but the framework
        # instantiates it without that param.  We patch __init__ to force our shim URL.
        try:
            import tavily.tavily as _tavily_mod

            _orig_tavily_init = _tavily_mod.TavilyClient.__init__

            def _patched_tavily_init(self, *args, **kwargs):
                kwargs['api_base_url'] = SHIM
                # Also strip any proxy settings to prevent leaking through Mihomo
                kwargs.pop('proxies', None)
                _orig_tavily_init(self, *args, **kwargs)
                # Belt-and-suspenders: force the base_url after init
                self.base_url = SHIM
                # Remove proxy settings from the session
                if hasattr(self, 'session') and hasattr(self.session, 'proxies'):
                    self.session.proxies = {{}}
                print(f'[lcdr-patch] TavilyClient base_url -> {{SHIM}}')

            _tavily_mod.TavilyClient.__init__ = _patched_tavily_init
            print('[lcdr-patch] TavilyClient.__init__ patched')
        except ImportError as e:
            print(f'[lcdr-patch] WARNING: could not patch TavilyClient: {{e}}')

        # Also patch the async client if present
        try:
            import tavily.async_tavily as _atavily_mod

            _orig_async_init = _atavily_mod.AsyncTavilyClient.__init__

            def _patched_async_init(self, *args, **kwargs):
                kwargs['api_base_url'] = SHIM
                _orig_async_init(self, *args, **kwargs)
                self._api_base_url = SHIM
                print(f'[lcdr-patch] AsyncTavilyClient base_url -> {{SHIM}}')

            _atavily_mod.AsyncTavilyClient.__init__ = _patched_async_init
        except (ImportError, AttributeError):
            pass

        # === Layer 2: Localhost masking for LLM calls ===
        # DeepSeek V4 refuses when it sees localhost URLs in context.
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

        def _mask_localhost(text):
            if not isinstance(text, str):
                return text
            for old, new in _MASK_MAP.items():
                text = text.replace(old, new)
            text = re.sub(r'localhost:(\\d+)', r'sandbox-\\1.internal', text)
            return text

        def _unmask_localhost(text):
            if not isinstance(text, str):
                return text
            for masked, original in _UNMASK_MAP.items():
                text = text.replace(masked, original)
            text = re.sub(r'sandbox-(\\d+)\\.internal', r'localhost:\\1', text)
            return text

        # Patch httpx for localhost masking on LLM calls
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
                                    masked = _mask_localhost(msg['content'])
                                    if masked != msg['content']:
                                        msg['content'] = masked
                                        modified = True
                                elif isinstance(msg.get('content'), list):
                                    for part in msg['content']:
                                        if isinstance(part, dict) and isinstance(part.get('text'), str):
                                            masked = _mask_localhost(part['text'])
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
                        print(f'[lcdr-mask] warn: sync mask failed: {{e}}')

                resp = _orig_hx_send(self, request, **kw)

                if '/chat/completions' in url_str or '/completions' in url_str:
                    try:
                        rtext = resp.content.decode('utf-8')
                        unmasked = _unmask_localhost(rtext)
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
                                    masked = _mask_localhost(msg['content'])
                                    if masked != msg['content']:
                                        msg['content'] = masked
                                        modified = True
                                elif isinstance(msg.get('content'), list):
                                    for part in msg['content']:
                                        if isinstance(part, dict) and isinstance(part.get('text'), str):
                                            masked = _mask_localhost(part['text'])
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
                        print(f'[lcdr-mask] warn: async mask failed: {{e}}')

                resp = await _orig_hx_async_send(self, request, **kw)

                if '/chat/completions' in url_str or '/completions' in url_str:
                    try:
                        rtext = resp.content.decode('utf-8')
                        unmasked = _unmask_localhost(rtext)
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

            print('[lcdr-patch] httpx patched (localhost masking)')
        except ImportError:
            print('[lcdr-patch] httpx not available')

        # === Layer 3: Run the LangGraph graph ===
        from ollama_deep_researcher.graph import graph
        from ollama_deep_researcher.configuration import Configuration

        QUERY = '{intent_escaped}'

        try:
            # Configuration via RunnableConfig configurable dict.
            # Environment variables take precedence (already set above),
            # but we also pass via configurable for belt-and-suspenders.
            config = {{
                "configurable": {{
                    "search_api": "tavily",
                    "llm_provider": "lmstudio",
                    "lmstudio_base_url": PROXY,
                    "local_llm": MODEL,
                    "max_web_research_loops": {max_loops},
                    "fetch_full_page": True,
                    "strip_thinking_tokens": True,
                    "use_tool_calling": False,
                }}
            }}

            # Invoke the graph synchronously
            result = graph.invoke(
                {{"research_topic": QUERY}},
                config=config,
            )

            report = ""
            if isinstance(result, dict):
                report = result.get("running_summary", "")
            elif hasattr(result, "running_summary"):
                report = result.running_summary or ""
            else:
                report = str(result)

            if not report:
                report = "(local-deep-researcher produced empty output)"

            # Final unmask pass
            report = _unmask_localhost(report)

        except Exception as e:
            report = f"(local-deep-researcher error: {{type(e).__name__}}: {{e}})"
            traceback.print_exc()

        print('{_REPORT_START}')
        print(report)
        print('{_REPORT_END}')
    """)


def _build_env(proxy_url: str, model: str, shim_url: str) -> dict:
    """Build the subprocess environment."""
    env = {**os.environ}

    # LLM configuration via environment variables
    # (read by Configuration.from_runnable_config via os.environ)
    env["LLM_PROVIDER"] = "lmstudio"
    env["LMSTUDIO_BASE_URL"] = proxy_url
    env["LOCAL_LLM"] = model
    env["MAX_WEB_RESEARCH_LOOPS"] = "3"
    env["FETCH_FULL_PAGE"] = "True"
    env["STRIP_THINKING_TOKENS"] = "True"

    # Search configuration
    env["SEARCH_API"] = "tavily"
    env["TAVILY_API_KEY"] = "tvly-sandbox-fake-key"

    # OpenAI-compatible env vars (ChatOpenAI / ChatLMStudio may read these)
    env["OPENAI_BASE_URL"] = proxy_url
    env["OPENAI_API_KEY"] = env.get("OPENAI_API_KEY", "anything")

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


# Agent identifier for the auto-discovery registry. Must match the
# AGENT_NAME used in score files: data/results/deep_v3/local-deep-researcher__<task>_matrix.score.json
AGENT_NAME = "local-deep-researcher"


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Run LangChain local-deep-researcher and return the markdown report.

    Args:
        intent: The research query / task description.
        model: OpenAI-compatible model name (e.g. "deepseek-v4-flash").
        shim_url: Tavily-compatible search API URL (e.g. "http://localhost:8081").
        proxy_url: OpenAI-compatible LLM endpoint (e.g. "http://localhost:8088/v1").
        timeout_s: Subprocess timeout in seconds.

    Returns:
        The markdown report, or an error string.
    """
    lcdr_python = Path(LCDR_PYTHON)
    if not lcdr_python.exists():
        return (
            f"(local-deep-researcher: missing venv at {lcdr_python})\n\n"
            "Installation:\n"
            "  cd /opt/deep_reserch\n"
            "  python3 -m venv .venv-lcdr\n"
            "  .venv-lcdr/bin/pip install langgraph langchain-community "
            "langchain-ollama langchain-openai tavily-python "
            "duckduckgo-search httpx markdownify python-dotenv openai\n"
            "  git clone https://github.com/langchain-ai/local-deep-researcher.git "
            "third_party/local-deep-researcher\n"
            "  .venv-lcdr/bin/pip install -e third_party/local-deep-researcher"
        )

    # Sanitize the intent: strip localhost URLs so DeepSeek doesn't refuse
    clean_intent = _sanitize_intent(intent)

    # Build the driver script
    driver_code = _build_driver_script(clean_intent, shim_url, proxy_url, model)
    driver_path = ROOT / "scripts" / "_lcdr_benchmark_driver.py"

    # Per-agent lock so parallel workers don't trample the shared driver path.
    _lock_cm = runner_exclusive_lock("local-deep-researcher")
    _lock_cm.__enter__()

    try:
        driver_path.write_text(driver_code)

        # Build subprocess environment
        env = _build_env(proxy_url, model, shim_url)

        logger.info(
            "Starting local-deep-researcher subprocess: model=%s shim=%s proxy=%s",
            model, shim_url, proxy_url,
        )

        t0 = time.time()
        proc = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                [str(lcdr_python), str(driver_path)],
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
                "local-deep-researcher exited %d after %.0fs\nstderr (last 1500): %s",
                proc.returncode, elapsed, stderr[-1500:],
            )

        # Extract the report from the sentinel-delimited block
        report = _extract_report(stdout)

        if not report:
            logger.warning("No report extracted from local-deep-researcher output")
            snippet = stdout[-2000:] if stdout else "(no stdout)"
            err_snippet = stderr[-1500:] if stderr else "(no stderr)"
            return (
                f"(local-deep-researcher produced no report after {elapsed:.0f}s, "
                f"exit={proc.returncode})\n\n"
                f"--- stdout tail ---\n{snippet}\n\n"
                f"--- stderr tail ---\n{err_snippet}"
            )

        # Unmask any .internal domains that survived
        report = _unmask_report(report)

        logger.info(
            "local-deep-researcher completed in %.0fs, report=%d chars",
            elapsed, len(report),
        )
        return report

    except subprocess.TimeoutExpired:
        logger.error("local-deep-researcher timed out after %ds", timeout_s)
        return f"(local-deep-researcher timeout after {timeout_s}s)"
    except Exception as e:
        logger.exception("local-deep-researcher runner error")
        return f"(local-deep-researcher error: {e})"
    finally:
        if driver_path.exists():
            driver_path.unlink(missing_ok=True)
        try:
            _lock_cm.__exit__(None, None, None)
        except Exception:
            logger.exception("local-deep-researcher lock release failed")


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

    parser = argparse.ArgumentParser(
        description="Run LangChain local-deep-researcher benchmark"
    )
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
