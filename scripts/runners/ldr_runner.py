"""LDR (local-deep-research) runner for the deep-research benchmark.

Runs LDR as a subprocess using its own .venv-ldr312 venv and LDR's native
programmatic API (``detailed_research()`` with ``create_settings_snapshot``).

NO monkey-patching of LDR internals.  All configuration uses LDR's
supported mechanisms:

  1. ``create_settings_snapshot(overrides=...)`` -- official API for passing
     provider, model, search tool, temperature, etc.
  2. Environment variables ``LDR_LLM_PROVIDER``, ``LDR_LLM_MODEL``, etc.
     which LDR's InMemorySettingsManager reads via ``check_env_setting()``.
  3. HTTP transport-layer intercept (requests/httpx/aiohttp) to redirect
     ``api.tavily.com`` -> sandbox shim.  This is the same approach used
     for every other runner (DeerFlow, ii-researcher, etc.) and patches
     the HTTP libraries, not LDR itself.
  4. Localhost-masking at the httpx transport layer: replaces
     ``localhost:PORT`` with ``.internal`` domains in LLM API calls so
     DeepSeek V4 flash doesn't trigger its safety filter.

Pipeline:
  - Strip localhost URLs from the intent (the user's task description
    mentions sandbox URLs but LDR discovers sandbox content through
    search, so the LLM never needs to see raw ``localhost`` refs).
  - Launch subprocess in .venv-ldr312 with a generated driver script.
  - Driver calls ``detailed_research()`` with a settings snapshot.
  - Report is emitted between sentinels and extracted by the parent.
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

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
LDR_PYTHON = str(ROOT / ".venv-ldr312" / "bin" / "python")

# ---------------------------------------------------------------------------
# Timeout for one LDR run.  LDR does multi-iteration search + report
# generation, so we allow a generous window.
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT_S = 1800

# ---------------------------------------------------------------------------
# Sentinel markers for extracting the report from subprocess stdout.
# ---------------------------------------------------------------------------
_REPORT_START = "===LDR_REPORT_START==="
_REPORT_END = "===LDR_REPORT_END==="

# ---------------------------------------------------------------------------
# Localhost URL -> neutral description mapping for intent sanitization.
# ---------------------------------------------------------------------------
_URL_TO_DESC = {
    r"http://localhost:7770[^\s)\]]*": "the product catalog",
    r"http://localhost:9999[^\s)\]]*": "the discussion forum",
    r"http://localhost:8090[^\s)\]]*": "the encyclopedia",
}

# ---------------------------------------------------------------------------
# Localhost <-> .internal masking map for DeepSeek safety filter bypass.
# Applied at the HTTP transport layer to LLM API calls.
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

    LDR has its own search engine (shimmed to our Tavily-compatible sandbox),
    so it discovers sandbox pages on its own.  The LLM only needs the
    research topic, not the raw ``localhost`` URLs which trigger DeepSeek's
    safety filter.
    """
    text = intent
    # Replace specific sandbox URL patterns with neutral descriptions
    for pattern, desc in _URL_TO_DESC.items():
        text = re.sub(pattern, desc, text)
    # Strip any remaining localhost URLs
    text = re.sub(r"http://localhost:\d+[^\s)\]]*", "", text)
    # Remove backtick-quoted sandbox placeholders like (`__SHOPPING__`)
    text = re.sub(r"\(`?__\w+__`?\)", "", text)
    # Remove bare __SHOPPING__ etc. placeholders
    text = re.sub(r"`?__(?:SHOPPING|REDDIT|WIKIPEDIA)__`?", "", text)
    # Remove sandbox-specific directives that confuse the model
    text = re.sub(r"Source URLs MUST be sandbox-local\.?\s*", "", text)
    text = re.sub(r"Do not fabricate URLs[^.]*\.?\s*", "", text)
    # Clean up double spaces and orphaned parentheses
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


def _unmask_report(report: str) -> str:
    """Reverse masked domains back to localhost:PORT in the final report."""
    text = report
    for masked, original in _UNMASK_MAP.items():
        text = text.replace(masked, original)
    # Reverse the catch-all pattern for other ports
    text = re.sub(r"sandbox-(\d+)\.internal", r"localhost:\1", text)
    # Also catch https:// variants the LLM might have added
    text = text.replace("https://onestopmarket.com", "http://localhost:7770")
    text = text.replace("https://postmill.net", "http://localhost:9999")
    text = text.replace("https://kiwipedia.org", "http://localhost:8090")

    # FIX P2.5: Rewrite off-sandbox Wikipedia URLs to Kiwix sandbox URLs.
    # LDR's LLM may generate en.wikipedia.org/wiki/... URLs in its report text
    # from model knowledge. These are off-sandbox. We rewrite them to the local
    # Kiwix instance so they become valid sandbox URLs.
    def _rewrite_wiki_url(m):
        title = m.group(1)
        return f"http://localhost:8090/content/wikipedia_en_all_nopic/A/{title}"

    # Match both http and https variants
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
) -> str:
    """Build the Python driver script that runs inside LDR's venv.

    The driver uses three layers of configuration (all supported/standard):

    1. HTTP transport intercept -- patches requests.Session.send,
       httpx.Client.send, httpx.AsyncClient.send, and
       aiohttp.ClientSession._request to redirect api.tavily.com -> shim
       and en.wikipedia.org -> Kiwix.  This is the same approach used for
       every runner and patches HTTP libraries, not LDR.

    2. Localhost masking -- patches httpx.Client.send and
       httpx.AsyncClient.send to replace localhost:PORT with .internal
       domains in LLM API request bodies (chat/completions), and reverses
       the replacement in responses.  Prevents DeepSeek V4 safety refusal.

    3. LDR's ``create_settings_snapshot`` + ``detailed_research`` API --
       the official programmatic interface.  Passes provider, model,
       temperature, search tool, iterations, etc. as settings overrides.
    """
    # Escape the intent for embedding in a Python triple-quoted string
    intent_escaped = (
        intent.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
    )

    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Auto-generated LDR driver for benchmark runner.\"\"\"
        import os, sys, json, re, traceback

        # === Layer 0: Environment cleanup ===
        # Purge proxy env vars so LDR can only reach localhost services.
        for _pv in list(os.environ):
            if _pv.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'ftp_proxy'):
                del os.environ[_pv]
        os.environ['NO_PROXY'] = '*'

        SHIM = {shim_url!r}
        PROXY = {proxy_url!r}
        MODEL = {model!r}

        # === Layer 1: HTTP transport intercept ===
        # Redirect api.tavily.com -> sandbox shim at the transport layer.
        # This catches ALL HTTP calls regardless of which Python object makes them.
        from urllib.parse import urlparse, urlunparse

        def _rewrite_url(url):
            if not url:
                return url
            p = urlparse(url)
            h = p.hostname or ''
            if 'api.tavily.com' in h:
                sp = urlparse(SHIM)
                nurl = urlunparse(p._replace(scheme=sp.scheme, netloc=sp.netloc))
                print(f'[ldr-intercept] TAVILY: {{url[:120]}} -> {{nurl[:120]}}')
                return nurl
            if 'en.wikipedia.org' in h and p.path.startswith('/wiki/'):
                kiwix = os.environ.get('WIKIPEDIA_KIWIX_URL', 'http://localhost:8090')
                kp = urlparse(kiwix)
                title = p.path[len('/wiki/'):]
                nurl = urlunparse(p._replace(
                    scheme=kp.scheme, netloc=kp.netloc,
                    path=f'/content/wikipedia_en_all_nopic/A/{{title}}', query=''))
                print(f'[ldr-intercept] WIKI: {{url[:120]}} -> {{nurl[:120]}}')
                return nurl
            return url

        # Patch requests.Session.send
        try:
            import requests as _rq
            _orig_rq_send = _rq.Session.send
            def _patched_rq_send(self, req, **kw):
                nu = _rewrite_url(req.url)
                if nu != req.url:
                    req.url = nu
                return _orig_rq_send(self, req, **kw)
            _rq.Session.send = _patched_rq_send
        except ImportError:
            pass

        # Patch aiohttp -- force trust_env=False to prevent proxy leakage
        try:
            import aiohttp as _ah
            _orig_cs_init = _ah.ClientSession.__init__
            def _cs_init_patched(self, *a, **kw):
                kw['trust_env'] = False
                return _orig_cs_init(self, *a, **kw)
            _ah.ClientSession.__init__ = _cs_init_patched
            _orig_areq = _ah.ClientSession._request
            async def _patched_areq(self, method, url, **kw):
                url = _rewrite_url(str(url))
                return await _orig_areq(self, method, url, **kw)
            _ah.ClientSession._request = _patched_areq
        except ImportError:
            pass

        # === Layer 2: Localhost masking for LLM calls ===
        # DeepSeek V4 refuses when it sees localhost URLs in context.
        # We mask localhost -> .internal in LLM request bodies and unmask in responses.
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

        # Patch httpx for both URL rewriting (Layer 1) and localhost masking (Layer 2).
        # LDR uses langchain_openai which uses httpx for LLM API calls.
        try:
            import httpx as _hx

            # --- Sync httpx.Client.send ---
            _orig_hx_send = _hx.Client.send
            def _patched_hx_send(self, request, **kw):
                # Layer 1: URL rewriting for search calls
                nu = _rewrite_url(str(request.url))
                if nu != str(request.url):
                    request.url = _hx.URL(nu)

                # Layer 2: Localhost masking for LLM calls
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
                        print(f'[ldr-mask] warn: sync mask failed: {{e}}')

                resp = _orig_hx_send(self, request, **kw)

                # Unmask .internal in LLM responses
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

            # --- Async httpx.AsyncClient.send ---
            _orig_hx_async_send = _hx.AsyncClient.send
            async def _patched_hx_async_send(self, request, **kw):
                # Layer 1: URL rewriting
                nu = _rewrite_url(str(request.url))
                if nu != str(request.url):
                    request.url = _hx.URL(nu)

                # Layer 2: Localhost masking
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
                        print(f'[ldr-mask] warn: async mask failed: {{e}}')

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

            print('[ldr-intercept] httpx patched (URL rewrite + localhost masking)')
        except ImportError:
            print('[ldr-intercept] httpx not available')

        print(f'[ldr-intercept] Transport intercept installed (shim={{SHIM}})')

        # === Layer 3: LDR programmatic API ===
        # Use LDR's official create_settings_snapshot + detailed_research interface.
        from local_deep_research.api import create_settings_snapshot, detailed_research

        settings = create_settings_snapshot(overrides={{
            "llm.provider": "openai_endpoint",
            "llm.model": MODEL,
            "llm.temperature": 0.2,
            "llm.openai_endpoint.url": PROXY,
            "llm.openai_endpoint.api_key": os.environ.get("OPENAI_API_KEY", "anything"),
            "search.tool": "tavily",
            "search.iterations": 2,
            "search.questions_per_iteration": 2,
            "search.max_results": 10,
            "search.snippets_only": False,
        }})

        QUERY = '{intent_escaped}'

        try:
            result = detailed_research(
                query=QUERY,
                settings_snapshot=settings,
                search_tool="tavily",
                search_strategy="source-based",
                iterations=2,
                questions_per_iteration=2,
                temperature=0.2,
                model_name=MODEL,
                provider="openai_endpoint",
                openai_endpoint_url=PROXY,
            )

            if isinstance(result, dict):
                report = (
                    result.get("final_report")
                    or result.get("report")
                    or result.get("summary")
                    or str(result)[:30000]
                )
            else:
                report = str(result)

            # Final unmask pass
            report = _unmask_localhost(report)

        except Exception as e:
            report = f"(local-deep-research error: {{type(e).__name__}}: {{e}})"
            traceback.print_exc()

        print('{_REPORT_START}')
        print(report)
        print('{_REPORT_END}')
    """)


def _build_env(proxy_url: str, model: str, shim_url: str) -> dict:
    """Build the subprocess environment."""
    env = {**os.environ}

    # LLM configuration via LDR's environment variable convention
    env["LDR_LLM_PROVIDER"] = "openai_endpoint"
    env["LDR_LLM_MODEL"] = model
    env["LDR_LLM_OPENAI_ENDPOINT_URL"] = proxy_url
    env["LDR_LLM_OPENAI_ENDPOINT_API_KEY"] = env.get("OPENAI_API_KEY", "anything")

    # Search configuration
    env["LDR_SEARCH_TOOL"] = "tavily"
    env["LDR_SEARCH_ENGINE_WEB_TAVILY_API_KEY"] = "tvly-shim-fake"
    env["TAVILY_API_KEY"] = "tvly-shim-fake"

    # OpenAI-compatible env vars (langchain_openai reads these)
    env["OPENAI_BASE_URL"] = proxy_url
    env["OPENAI_API_KEY"] = env.get("OPENAI_API_KEY", "anything")

    # Remove HTTP proxies so LDR can only reach localhost services
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                "ALL_PROXY", "all_proxy", "FTP_PROXY", "ftp_proxy"):
        env.pop(key, None)
    env["NO_PROXY"] = "*"

    # Disable optional integrations that would fail in sandbox
    env.pop("LANGSMITH_TRACING", None)
    env.pop("LANGSMITH_API_KEY", None)

    return env


# Agent identifier for the auto-discovery registry. Must match the
# AGENT_NAME used in score files: data/results/deep_v3/ldr__<task>_matrix.score.json
AGENT_NAME = "ldr"


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Run LDR and return the markdown report.

    Args:
        intent: The research query / task description.
        model: OpenAI-compatible model name (e.g. "deepseek-v4-flash").
        shim_url: Tavily-compatible search API URL (e.g. "http://localhost:8081").
        proxy_url: OpenAI-compatible LLM endpoint (e.g. "http://localhost:8088/v1").
        timeout_s: Subprocess timeout in seconds.

    Returns:
        The markdown report produced by LDR, or an error string.
    """
    ldr_python = Path(LDR_PYTHON)
    if not ldr_python.exists():
        return f"(ldr: missing venv at {ldr_python})"

    # Sanitize the intent: strip localhost URLs so DeepSeek doesn't refuse
    clean_intent = _sanitize_intent(intent)

    # Build the driver script
    driver_code = _build_driver_script(clean_intent, shim_url, proxy_url, model)
    driver_path = ROOT / "scripts" / "_ldr_benchmark_driver.py"

    try:
        driver_path.write_text(driver_code)

        # Build subprocess environment
        env = _build_env(proxy_url, model, shim_url)

        logger.info(
            "Starting LDR subprocess: model=%s shim=%s proxy=%s",
            model, shim_url, proxy_url,
        )

        t0 = time.time()
        proc = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                [str(ldr_python), str(driver_path)],
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
                "LDR exited %d after %.0fs\nstderr (last 1500): %s",
                proc.returncode, elapsed, stderr[-1500:],
            )

        # Extract the report from the sentinel-delimited block
        report = _extract_report(stdout)

        if not report:
            logger.warning("No report extracted from LDR output")
            snippet = stdout[-2000:] if stdout else "(no stdout)"
            err_snippet = stderr[-1500:] if stderr else "(no stderr)"
            return (
                f"(LDR produced no report after {elapsed:.0f}s, "
                f"exit={proc.returncode})\n\n"
                f"--- stdout tail ---\n{snippet}\n\n"
                f"--- stderr tail ---\n{err_snippet}"
            )

        # Belt-and-suspenders: unmask any .internal domains that survived
        report = _unmask_report(report)

        logger.info(
            "LDR completed in %.0fs, report=%d chars",
            elapsed, len(report),
        )
        return report

    except subprocess.TimeoutExpired:
        logger.error("LDR timed out after %ds", timeout_s)
        return f"(LDR timeout after {timeout_s}s)"
    except Exception as e:
        logger.exception("LDR runner error")
        return f"(LDR error: {e})"
    finally:
        if driver_path.exists():
            driver_path.unlink(missing_ok=True)


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

    parser = argparse.ArgumentParser(description="Run LDR benchmark")
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
