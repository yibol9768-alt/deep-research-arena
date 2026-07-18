"""LDR (local-deep-research) runner for the deep-research benchmark.

Runs LDR as a subprocess using its own .venv-ldr312 venv and LDR's native
programmatic report API (``generate_report()`` with
``create_settings_snapshot``).

NO monkey-patching of LDR internals.  All configuration uses LDR's
supported mechanisms:

  1. ``create_settings_snapshot(overrides=...)`` -- official API for passing
     provider, model, search tool, temperature, etc.
  2. Environment variables ``LDR_LLM_PROVIDER``, ``LDR_LLM_MODEL``, etc.
     which LDR's InMemorySettingsManager reads via ``check_env_setting()``.
  3. LDR's documented ``retrievers={name: BaseRetriever}`` API to register a
     sandbox-search retriever.  This is required in the formal worker: LDR's
     built-in Tavily engine DNS-validates ``api.tavily.com`` before an HTTP
     transport rewrite can run, while the worker intentionally has no public
     DNS/default route.
  4. Localhost-masking at the httpx transport layer: replaces
     ``localhost:PORT`` with ``.internal`` domains in LLM API calls so
     DeepSeek V4 flash doesn't trigger its safety filter.

Pipeline:
  - Normalize the intent. For local backbones (the default) this is
    information-preserving: LDR receives the SAME sandbox host roots
    (``localhost:17770/9999/8090``) the shared task prompt gives every other
    lane. The localhost->neutral rewrite and the transport-layer mask are
    applied only for a DeepSeek backbone whose safety filter refuses localhost
    (keyed on the model / ``LDR_INTENT_MASK`` env), so the masking never acts
    as a silent reverse handicap under qwen/glm.
  - Launch subprocess in .venv-ldr312 with a generated driver script.
  - Driver calls ``generate_report()`` with a settings snapshot.  This matters:
    ``detailed_research()`` returns only the intermediate ``current_knowledge``
    summary while ``generate_report()`` performs the native report-writing stage
    and adds LDR's own ``## Sources`` URL mapping.
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

from . import _budget, _egress
from ._runner_lock import runner_exclusive_lock
from .evidence_fallback import error_stub, fallback_enabled, keep_or_stub, synthesize_report

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
LDR_PYTHON = str(ROOT / ".venv-ldr312" / "bin" / "python")

# ---------------------------------------------------------------------------
# Unified default, identical for every lane (see scripts/runners/_budget.py):
# None = no native self-abort, the no-progress watchdog terminates a stall.
# The former hardcoded DEFAULT_TIMEOUT_S = 1800 was an UNDECLARED per-lane hard
# wall (lane_protocol.yaml declares wall_clock_s: null): run_deep_task's manual
# dispatch passes no timeout_s, so that default governed formal runs.
# ---------------------------------------------------------------------------
DEFAULT_NATIVE_TIMEOUT_S = _budget.native_timeout_default()
DEFAULT_TIMEOUT_S = DEFAULT_NATIVE_TIMEOUT_S

# ---------------------------------------------------------------------------
# Sentinel markers for extracting the report from subprocess stdout.
# ---------------------------------------------------------------------------
_REPORT_START = "===LDR_REPORT_START==="
_REPORT_END = "===LDR_REPORT_END==="

# The driver emits URLs already present in LDR's native report as a diagnostic
# between these sentinels.  Nothing is appended to the scored report by the
# harness: ``generate_report()`` itself owns the ``## Sources`` section.
_SOURCES_START = "===LDR_SOURCES_START==="
_SOURCES_END = "===LDR_SOURCES_END==="
_DIAGNOSTICS_START = "===LDR_DIAGNOSTICS_START==="
_DIAGNOSTICS_END = "===LDR_DIAGNOSTICS_END==="

# ---------------------------------------------------------------------------
# Localhost URL -> neutral description mapping for intent sanitization.
# ---------------------------------------------------------------------------
_URL_TO_DESC = {
    r"http://localhost:7770[^\s)\]]*": "the product catalog",
    r"http://localhost:17770[^\s)\]]*": "the product catalog",
    r"http://localhost:9999[^\s)\]]*": "the discussion forum",
    r"http://localhost:8090[^\s)\]]*": "the encyclopedia",
}

# ---------------------------------------------------------------------------
# Localhost <-> .internal masking map for DeepSeek safety filter bypass.
# Applied at the HTTP transport layer to LLM API calls.
# ---------------------------------------------------------------------------
_MASK_MAP = {
    "http://localhost:7770": "http://onestopmarket.com",
    "http://localhost:17770": "http://onestopmarket.com",
    "http://localhost:9999": "http://postmill.net",
    "http://localhost:8090": "http://kiwipedia.org",
    "http://localhost:8081": "http://searchapi.internal",
    "localhost:7770": "onestopmarket.com",
    "localhost:17770": "onestopmarket.com",
    "localhost:9999": "postmill.net",
    "localhost:8090": "kiwipedia.org",
    "localhost:8081": "searchapi.internal",
}
_UNMASK_MAP = {v: k for k, v in _MASK_MAP.items()}


def _needs_intent_masking(model: str | None) -> bool:
    """Always False by default: the premise for masking was measured and is false.

    The localhost -> neutral-description rewrite existed for one stated reason:
    "DeepSeek V4 flash refuses to write reports that mention localhost URLs
    (triggers safety filter)". The 2026-07-08 fairness audit tested that claim
    against the live API. Four arms, N=10 each, same report-writing prompt with
    only the URL host varied:

        A  localhost      0/10 refusals, 114 localhost URLs written
        B  shop.internal  0/10 refusals, 130 .internal URLs written
        C  rtings.com     0/10 refusals,  87 public URLs written
        D  no URLs given  0/10 refusals,  61 public URLs invented

    DeepSeek does not refuse localhost. It writes it faithfully. The real subset
    corroborates: unpatched camel-ai and langchain-odr on deepseek wrote 10-33
    localhost URLs per report with zero refusals.

    Masking was therefore a lane-specific privilege resting on a false premise:
    it deleted the sandbox host roots the shared prompt gives every other lane,
    and (with the now-removed Wikipedia rewrite) converted off-sandbox drift
    into sandbox grounding. It is off. ``LDR_INTENT_MASK=1`` still forces it on
    for anyone investigating a provider that genuinely does refuse, but that
    must be declared in the lane protocol, not switched on by backbone name.
    """
    override = os.environ.get("LDR_INTENT_MASK", "").strip().lower()
    if override in ("1", "true", "yes", "on"):
        return True
    return False


def _sanitize_intent(intent: str, model: str | None = None) -> str:
    """Normalize the intent before handing it to LDR.

    For local backbones (the default) this is information-preserving: the intent
    keeps the same sandbox host roots (``http://localhost:17770/9999/8090``) and
    grounding constraints the shared task prompt gives every other lane. Only for
    a DeepSeek backbone (see ``_needs_intent_masking``) do we rewrite the raw
    ``localhost`` URLs to neutral descriptions, because DeepSeek V4 flash's safety
    filter refuses otherwise. That rewrite is a deliberate, backbone-keyed
    trade (fewer refusals at the cost of the host roots), NOT a blanket handicap.
    """
    if not _needs_intent_masking(model):
        # Preserve path: hand LDR the same sandbox host information every other
        # lane receives. Do not strip localhost URLs or placeholders here; the
        # transport-layer mask (bypassed for local backbones) and the shared
        # prompt already carry the intent and citation policy.
        return intent.strip()

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
    # Keep the grounding constraints, but phrase them without raw localhost
    # strings that can trigger safety refusals in some model routes.
    text = re.sub(
        r"Source URLs MUST be sandbox-local\.?\s*",
        "Use only source URLs returned by the benchmark sandbox search corpus. ",
        text,
    )
    text = re.sub(
        r"Do not fabricate URLs[^.]*\.?\s*",
        "Do not fabricate URLs; cite only fetched sandbox search results. ",
        text,
    )
    # Clean up double spaces and orphaned parentheses
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


def _augment_intent_for_sandbox_search(intent: str) -> str:
    """Prompt parity: LDR gets the shared task intent, nothing more.

    This used to append four LDR-only instructions ("cite evidence from all
    sandbox source types", "every comparison must be tied to fetched source
    URLs", "the final report must include a References section"). Each of them
    steers directly at a scored axis, and no other lane received them. Fairness
    audit 2026-07-08 (B3, prompt equivalence): per-lane rubric injection is
    removed everywhere. Whatever the task asks for is what every framework is
    asked for.
    """
    return intent.strip()


def _unmask_report(report: str, model: str | None = None) -> str:
    """Reverse the mask ROUND TRIP the harness itself applied, and nothing else.

    Only meaningful when masking was enabled inbound (``_needs_intent_masking``).
    With masking off (the default) nothing was ever masked, so reversing masked
    domains here would only LAUNDER a model that emitted onestopmarket.com /
    postmill.net / kiwipedia.org from parametric memory into valid sandbox
    grounding -- the exact off-sandbox drift the benchmark measures. The former
    unconditional tail did precisely that: a literal ``replace`` of the three
    public domains (``https://``/``http://`` variants) into localhost, plus a
    ``en.wikipedia.org/wiki/X`` -> Kiwix rewrite, all applied even when masking
    was OFF. That converted drift into perfect grounding, for this lane only.

    Removed 2026-07-09 (fairness audit), mirroring
    ``local_deep_researcher_runner._unmask_report``: the guard runs first, so
    with masking off the report is byte-identical, and only the round trip of
    masks this harness itself applied (the ``_UNMASK_MAP`` reversal) survives.
    """
    if not _needs_intent_masking(model):
        return report
    text = report
    for masked, original in _UNMASK_MAP.items():
        text = text.replace(masked, original)
    text = re.sub(r"sandbox-(\d+)\.internal", r"localhost:\1", text)
    return text


def _native_timeout(timeout_s):
    # Unified native timeout. Default identical to every lane (DRA_WALL_CLOCK_S);
    # LDR_NATIVE_TIMEOUT_S still overrides. The old hard 420s default was a
    # per-lane wall clock; None (unlimited) defers termination to the shared
    # no-progress watchdog and the outer subprocess cap.
    configured = _budget.resolve_native_timeout("LDR_NATIVE_TIMEOUT_S")
    if configured is None:
        return timeout_s
    if timeout_s is None:
        return max(60, int(configured))
    return max(60, min(int(timeout_s), int(configured)))


# Markers that mean LDR produced no usable report and the shared rescue writer
# is warranted. A substantive-but-URL-light report is NOT a failure: returning
# it as-is is the fair outcome (see run()).
_FAILURE_MARKERS = (
    "(local-deep-research error",
    "local-deep-research error:",
    "no report extracted",
    "runner error",
    "(ldr:",
)


def _is_failed_report(report: str) -> bool:
    """Return True only for a genuine runner failure that warrants a rescue.

    A failure is empty output, a driver error string, or a stub far below any
    plausible report length. This deliberately does NOT treat a low sandbox-URL
    count as failure: fabricating grounding to hit a URL quota would mask a real
    model/framework weakness and make the benchmark unfair.
    """
    text = (report or "").strip()
    if len(text) < 500:
        return True
    low = text.lower()
    return any(marker in low for marker in _FAILURE_MARKERS)


def _build_driver_script(
    intent: str,
    shim_url: str,
    proxy_url: str,
    model: str,
    mask_llm_localhost: bool | None = None,
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

    3. LDR's ``create_settings_snapshot`` + ``generate_report`` API --
       the official programmatic interface.  Passes provider, model,
       temperature, search tool, iterations, etc. as settings overrides.
    """
    # Layer-2 localhost masking of LLM request bodies is only meaningful for a
    # backbone whose safety filter refuses localhost (DeepSeek). For local
    # backbones it is a no-op round-trip that only risks leaking a half-unmasked
    # ``.internal`` domain to the model, so bypass it cleanly and let the model
    # see the same localhost roots every other lane inlines into its prompt.
    if mask_llm_localhost is None:
        mask_llm_localhost = _needs_intent_masking(model)

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

        # === Layer 0: Environment policy ===
        _DRA_EGRESS_ON = bool(os.environ.get('DRA_EGRESS_PROXY', '').strip())
        if not _DRA_EGRESS_ON:
            for _pv in list(os.environ):
                if _pv.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'ftp_proxy'):
                    del os.environ[_pv]
            os.environ['NO_PROXY'] = '*'

        SHIM = {shim_url!r}
        PROXY = {proxy_url!r}
        MODEL = {model!r}
        # When False (local backbones) the LLM sees raw localhost URLs, matching
        # every other lane; the mask exists only for the DeepSeek safety filter.
        _MASK_ENABLED = {mask_llm_localhost!r}

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
            # No en.wikipedia.org -> kiwix rewrite. This lane's own comment at
            # :211 explains why it was deleted, and the deletion did not reach
            # this driver string. Rescuing parametric-memory drift into a corpus
            # page manufactures grounding the lane did not earn.
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

        # Patch aiohttp: trust the harness recording door, never ambient proxies.
        try:
            import aiohttp as _ah
            _orig_cs_init = _ah.ClientSession.__init__
            def _cs_init_patched(self, *a, **kw):
                kw['trust_env'] = _DRA_EGRESS_ON
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
            'http://localhost:17770': 'http://onestopmarket.com',
            'http://localhost:9999': 'http://postmill.net',
            'http://localhost:8090': 'http://kiwipedia.org',
            'http://localhost:8081': 'http://searchapi.internal',
            'localhost:7770': 'onestopmarket.com',
            'localhost:17770': 'onestopmarket.com',
            'localhost:9999': 'postmill.net',
            'localhost:8090': 'kiwipedia.org',
            'localhost:8081': 'searchapi.internal',
        }}
        _UNMASK_MAP = {{v: k for k, v in _MASK_MAP.items()}}

        def _mask_localhost(text):
            if not _MASK_ENABLED or not isinstance(text, str):
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
        # Use LDR's official settings + custom-retriever + report interfaces.
        from local_deep_research.api import create_settings_snapshot, generate_report
        from langchain_core.documents import Document
        from langchain_core.retrievers import BaseRetriever
        from pydantic import PrivateAttr

        SEARCH_ITERATIONS = int(os.environ.get('LDR_SEARCH_ITERATIONS', '3') or '3')
        QUESTIONS_PER_ITERATION = int(os.environ.get('LDR_QUESTIONS_PER_ITERATION', '1') or '1')
        SEARCH_MAX_RESULTS = int(os.environ.get('LDR_SEARCH_MAX_RESULTS', '50') or '50')
        RETRIEVER_NAME = 'dra_sandbox'

        BASE_QUERY = '{intent_escaped}'

        class DraSandboxRetriever(BaseRetriever):
            \"\"\"LDR-supported retriever backed by the benchmark search shim.

            The retriever only translates LDR's own search query to the shim's
            Tavily-compatible /search response and returns LangChain Documents.
            It performs no pre-search, source injection, or report rewriting.
            \"\"\"

            shim_url: str
            max_results: int = 50
            _calls: int = PrivateAttr(default=0)
            _results: int = PrivateAttr(default=0)
            _errors: int = PrivateAttr(default=0)
            _last_error: str = PrivateAttr(default='')
            _rejected_results: int = PrivateAttr(default=0)
            _external_urls_omitted: int = PrivateAttr(default=0)

            @staticmethod
            def _is_sandbox_source_url(value):
                \"\"\"Accept only canonical corpus-page URLs returned by shim.

                A sandbox Reddit document can legitimately quote the original
                post's public outbound links in its body.  Those links are
                content, not retriever source identities, and LDR's section
                writer otherwise mistakes them for citations.  The canonical
                source remains the shim result's localhost URL.
                \"\"\"
                try:
                    parsed = urlparse(str(value))
                    return (
                        parsed.scheme in ('http', 'https')
                        and (parsed.hostname or '').lower()
                        in ('localhost', '127.0.0.1')
                        and parsed.port in (7770, 8090, 9999)
                    )
                except (TypeError, ValueError):
                    return False

            @classmethod
            def _sanitize_snippet(cls, value):
                \"\"\"Remove embedded public URL tokens, preserving all prose.

                This runs before the Document enters LDR.  It does not edit the
                generated report and it leaves canonical sandbox URLs intact.
                \"\"\"
                omitted = 0

                def _replace(match):
                    nonlocal omitted
                    candidate = match.group(0)
                    check = candidate.rstrip('.,;:!?')
                    if cls._is_sandbox_source_url(check):
                        return candidate
                    omitted += 1
                    return '[external URL omitted]'

                text = re.sub(
                    r'''https?://[^\s<>()\[\]"']+''',
                    _replace,
                    str(value or ''),
                )
                return text, omitted

            def _get_relevant_documents(self, query, *, run_manager=None):
                self._calls += 1
                try:
                    response = _rq.post(
                        self.shim_url.rstrip('/') + '/search',
                        json={{
                            'query': str(query)[:400],
                            'max_results': self.max_results,
                        }},
                        timeout=60,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    documents = []
                    for item in (payload.get('results') or [])[:self.max_results]:
                        if not isinstance(item, dict):
                            continue
                        url = str(item.get('url') or '').strip()
                        if not url:
                            continue
                        if not self._is_sandbox_source_url(url):
                            self._rejected_results += 1
                            continue
                        content = str(
                            item.get('raw_content')
                            or item.get('content')
                            or ''
                        )
                        content, omitted = self._sanitize_snippet(content)
                        self._external_urls_omitted += omitted
                        documents.append(Document(
                            page_content=content,
                            metadata={{
                                'title': str(item.get('title') or ''),
                                'source': url,
                                'url': url,
                                'score': item.get('score', 1.0),
                            }},
                        ))
                    self._results += len(documents)
                    return documents
                except Exception as exc:
                    self._errors += 1
                    self._last_error = f'{{type(exc).__name__}}: {{exc}}'[:500]
                    print(f'[ldr-retriever] ERROR {{self._last_error}}')
                    return []

        _retriever = DraSandboxRetriever(
            shim_url=SHIM,
            max_results=SEARCH_MAX_RESULTS,
        )
        _native_diag = {{
            'retriever': RETRIEVER_NAME,
            'health_ok': False,
            'calls': 0,
            'results': 0,
            'errors': 0,
            'last_error': '',
            'rejected_results': 0,
            'external_urls_omitted': 0,
        }}

        # Connectivity-only preflight: no task search and no source is retained.
        # This fails fast if the formal worker cannot reach its owned shim,
        # instead of spending a full report run on an empty search backend.
        try:
            _health = _rq.get(SHIM.rstrip('/') + '/healthz', timeout=15)
            _health.raise_for_status()
            _native_diag['health_ok'] = True
            print(f'[ldr-preflight] retriever={{RETRIEVER_NAME}} health=ok')
        except Exception as exc:
            raise RuntimeError(
                f'LDR sandbox retriever preflight failed: {{type(exc).__name__}}: {{exc}}'
            ) from exc

        settings = create_settings_snapshot(overrides={{
            "llm.provider": "openai_endpoint",
            "llm.model": MODEL,
            "llm.temperature": 0.2,
            "llm.openai_endpoint.url": PROXY,
            "llm.openai_endpoint.api_key": os.environ.get("OPENAI_API_KEY", "anything"),
            "search.tool": RETRIEVER_NAME,
            "search.iterations": SEARCH_ITERATIONS,
            "search.questions_per_iteration": QUESTIONS_PER_ITERATION,
            "search.max_results": SEARCH_MAX_RESULTS,
            "search.snippets_only": True,
            # SourceBasedSearchStrategy normally drops the original query when
            # it exceeds app.max_user_query_length (default: 300 chars).  The
            # shared benchmark task plus neutral report contract is longer than
            # that.  If the old question parser also rejects the model's format,
            # no search happens at all.  Keep the public API's
            # search_original_query=True contract by admitting exactly this
            # task's length; this supplies no source or scorer information.
            "app.max_user_query_length": max(300, len(BASE_QUERY)),
        }})

        # FAIRNESS: no lane-specific seed injection. Earlier revisions ran an
        # extra sandbox search here and pasted the top hits (source URLs plus
        # snippets) into the query, telling the model to copy those URLs. That
        # handed LDR golden sources the shared task prompt never gives other
        # lanes, and it trained the model to echo bracketed [N] labels instead
        # of real source URLs. LDR must discover sandbox sources through its own
        # shim-routed search.
        QUERY = BASE_QUERY

        try:
            result = generate_report(
                query=QUERY,
                retrievers={{RETRIEVER_NAME: _retriever}},
                settings_snapshot=settings,
                search_tool=RETRIEVER_NAME,
                search_strategy="source-based",
                iterations=SEARCH_ITERATIONS,
                questions_per_iteration=QUESTIONS_PER_ITERATION,
                temperature=0.2,
                model_name=MODEL,
                provider="openai_endpoint",
                openai_endpoint_url=PROXY,
            )

            _sources = []
            if isinstance(result, dict):
                report = (
                    result.get("content")
                    or result.get("final_report")
                    or result.get("report")
                    or result.get("summary")
                    or str(result)[:30000]
                )
                # `generate_report()` writes LDR's native URL table into the
                # report itself.  Mirror only URLs already present there into a
                # diagnostic payload; never graft them into the scored text.
                _seen_urls = set()
                for _url in re.findall(r'https?://[^\\s)>\\]]+', str(report)):
                    if _url not in _seen_urls:
                        _seen_urls.add(_url)
                        _sources.append({{"url": _url}})
            else:
                report = str(result)

            # Final unmask pass. Return LDR's real report as-is: the parent
            # runner rescues only genuine failures. Fabricating a longer or
            # re-grounded report here would hide a real model/framework weakness
            # and manufacture grounding the model never produced.
            report = _unmask_localhost(report)
            _native_diag.update({{
                'calls': _retriever._calls,
                'results': _retriever._results,
                'errors': _retriever._errors,
                'last_error': _retriever._last_error,
                'rejected_results': _retriever._rejected_results,
                'external_urls_omitted': _retriever._external_urls_omitted,
                'report_urls': len(_sources),
            }})

        except Exception as e:
            report = f"(local-deep-research error: {{type(e).__name__}}: {{e}})"
            _sources = []
            _native_diag.update({{
                'calls': _retriever._calls,
                'results': _retriever._results,
                'errors': _retriever._errors,
                'last_error': _retriever._last_error,
                'rejected_results': _retriever._rejected_results,
                'external_urls_omitted': _retriever._external_urls_omitted,
                'report_urls': 0,
            }})
            traceback.print_exc()

        print('{_REPORT_START}')
        print(report)
        print('{_REPORT_END}')
        try:
            _sources_json = json.dumps(_sources, default=str)
        except Exception:
            _sources_json = '[]'
        print('{_SOURCES_START}')
        print(_sources_json)
        print('{_SOURCES_END}')
        print('{_DIAGNOSTICS_START}')
        print(json.dumps(_native_diag, sort_keys=True, default=str))
        print('{_DIAGNOSTICS_END}')
    """)


def _build_env(proxy_url: str, model: str, shim_url: str) -> dict:
    """Build the subprocess environment."""
    env = {**os.environ}

    # LLM configuration via LDR's environment variable convention
    env["LDR_LLM_PROVIDER"] = "openai_endpoint"
    env["LDR_LLM_MODEL"] = model
    env["LDR_LLM_OPENAI_ENDPOINT_URL"] = proxy_url
    env["LDR_LLM_OPENAI_ENDPOINT_API_KEY"] = env.get("OPENAI_API_KEY", "anything")

    # Search configuration. The driver registers this name through LDR's
    # official custom-retriever API; no public-search credential is involved.
    env["LDR_SEARCH_TOOL"] = "dra_sandbox"

    # OpenAI-compatible env vars (langchain_openai reads these)
    env["OPENAI_BASE_URL"] = proxy_url
    env["OPENAI_API_KEY"] = env.get("OPENAI_API_KEY", "anything")

    _egress.scrub_or_apply(env)

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
    timeout_s: float | None = DEFAULT_TIMEOUT_S,
) -> str:
    """Run LDR and return the markdown report.

    Args:
        intent: The research query / task description.
        model: OpenAI-compatible model name (e.g. "deepseek-v4-flash").
        shim_url: Tavily-compatible search API URL (e.g. "http://localhost:8081").
        proxy_url: OpenAI-compatible LLM endpoint (e.g. "http://localhost:8100/v1").
        timeout_s: Subprocess timeout in seconds; None (the protocol default,
            wall_clock_s: null) means no wall clock and the shared no-progress
            watchdog owns termination.

    Returns:
        The markdown report produced by LDR, or an error string.
    """
    def _degrade(phase: str, reason: str) -> str:
        # Fairness rule: an LDR failure must surface as the framework's own
        # (missing) output, never as a harness-ghostwritten report. In benchmark
        # mode we save an honest error stub; the evidence writer runs only under
        # the explicit non-benchmark EVIDENCE_FALLBACK_ENABLE flag.
        if fallback_enabled():
            return synthesize_report(
                intent,
                model,
                shim_url,
                proxy_url,
                min_chars=4500,
                min_urls=5,
            )
        return error_stub("ldr", phase, reason)

    ldr_python = Path(LDR_PYTHON)
    if not ldr_python.exists():
        return f"(ldr: missing venv at {ldr_python})"

    # Normalize the intent. For local backbones this preserves the sandbox host
    # roots the shared task prompt gives every lane; only a DeepSeek backbone
    # gets the refusal-avoiding localhost rewrite (see _needs_intent_masking).
    clean_intent = _augment_intent_for_sandbox_search(_sanitize_intent(intent, model))

    # Build the driver script
    driver_code = _build_driver_script(clean_intent, shim_url, proxy_url, model)
    driver_path = _egress.scratch_path("ldr-benchmark-driver")

    # Per-agent lock so parallel workers don't trample _ldr_benchmark_driver.py
    _lock_cm = runner_exclusive_lock("ldr")
    _lock_cm.__enter__()

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
                timeout=_native_timeout(timeout_s),
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
            return _degrade("native", "no report extracted from LDR output")

        # URLs already present in LDR's native report are mirrored as a
        # diagnostic, NOT appended by the harness. See sources_diagnostic() for
        # the measurement that killed the old `_attach_sources` behaviour. The
        # saved report is exactly what LDR's generate_report() API wrote,
        # including the native API's own Sources section.
        _diag = sources_diagnostic(_extract_sources(stdout))
        _native_diag = _extract_diagnostics(stdout)
        print(
            "[ldr-diagnostic] "
            f"health_ok={_native_diag.get('health_ok')} "
            f"calls={_native_diag.get('calls')} "
            f"results={_native_diag.get('results')} "
            f"errors={_native_diag.get('errors')} "
            f"rejected_results={_native_diag.get('rejected_results')} "
            f"external_urls_omitted={_native_diag.get('external_urls_omitted')} "
            f"report_urls={_diag['n_sources_retrieved']}"
        )
        if _native_diag and (
            int(_native_diag.get("calls") or 0) < 1
            or int(_native_diag.get("results") or 0) < 1
        ):
            return _degrade(
                "search",
                "native sandbox retriever returned no search results "
                f"({_native_diag.get('last_error') or 'no native error'})",
            )

        # Round-trip only: undo the masks this harness applied before the call.
        # With masking off (the default) this is a no-op, so a model-emitted
        # public domain is left ALONE instead of being laundered into grounding.
        report = _unmask_report(report, model)
        # FAIRNESS: capture LDR's real report even when it is light on sandbox
        # URLs. Only rescue genuine failures (empty output / driver error
        # markers / a stub far below any plausible length). Substituting a
        # synthesized or templated report just because the URL count is low
        # would fabricate grounding the model never produced and hide a real
        # model/framework weakness -- the opposite of a fair benchmark.
        if _is_failed_report(report):
            logger.warning("LDR produced a failed/empty report")
            if fallback_enabled():
                return _degrade("native", "LDR produced a failed/empty report")
            # Weak-but-real output (e.g. merely short) is LDR's own report:
            # save it verbatim (the scorer judges quality); stub only genuinely
            # empty output or text already shaped like a failure stub.
            return keep_or_stub(
                "ldr", "native", "LDR produced a failed/empty report", report
            )

        logger.info(
            "LDR completed in %.0fs, report=%d chars",
            elapsed, len(report),
        )
        return report

    except subprocess.TimeoutExpired:
        logger.error("LDR native path exceeded %ds", _native_timeout(timeout_s))
        return _degrade(
            "native", f"native path exceeded {_native_timeout(timeout_s)}s timeout"
        )
    except Exception as e:
        logger.exception("LDR runner error")
        return _degrade("native", f"{type(e).__name__}: {e}")
    finally:
        if driver_path.exists():
            driver_path.unlink(missing_ok=True)
        try:
            _lock_cm.__exit__(None, None, None)
        except Exception:
            logger.exception("ldr lock release failed")


def _extract_report(stdout: str) -> str:
    """Extract the report from the sentinel-delimited block in stdout."""
    start_idx = stdout.find(_REPORT_START)
    end_idx = stdout.find(_REPORT_END)

    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return ""

    return stdout[start_idx + len(_REPORT_START):end_idx].strip()


def _extract_sources(stdout: str) -> list:
    """Extract URLs mirrored from LDR's native report from stdout.

    Returns the list of ``{"url": ...}`` diagnostics serialized between the
    sources sentinels, or ``[]`` if absent/unparseable. These do not modify the
    report and do not create scorer-visible citations.
    """
    import json as _json

    start_idx = stdout.find(_SOURCES_START)
    end_idx = stdout.find(_SOURCES_END)
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return []
    blob = stdout[start_idx + len(_SOURCES_START):end_idx].strip()
    if not blob:
        return []
    try:
        data = _json.loads(blob)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _extract_diagnostics(stdout: str) -> dict:
    """Extract bounded, non-reasoning native retriever counters."""
    import json as _json

    start_idx = stdout.find(_DIAGNOSTICS_START)
    end_idx = stdout.find(_DIAGNOSTICS_END)
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return {}
    blob = stdout[start_idx + len(_DIAGNOSTICS_START):end_idx].strip()
    if not blob:
        return {}
    try:
        data = _json.loads(blob)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def sources_diagnostic(sources: list) -> dict:
    """Summarise LDR's retrieved link table WITHOUT writing it into the report.

    `_attach_sources` used to append this table to the saved report as a
    "### Sources" block, on the theory that LDR's model cites by bracketed
    ``[N]`` index and the URL table lives in a sibling field, so re-attaching it
    was "faithful capture, not fabrication".

    The 2026-07-08 fairness audit measured what that block was worth. Deleting
    it from the saved reports and rescoring with the real scorer:

        qwen3-8b          macro reach 0.9519 -> 0.0000   (13/13 tasks)
        deepseek-v4-flash macro reach 0.9868 -> 0.0000

    with `before_block = 0`: LDR's own prose contained no sandbox URL at all, on
    any task, under either backbone. The entire grounding score of the lane that
    ranked #1 on both boards was written by this function.

    That is the same construct the audit of 2026-07-06 deleted from
    ii-researcher as publish blocker B1 ("harness-manufactured grounding, not
    agent grounding"). Keeping one and deleting the other cannot be defended, so
    this one is gone too. The link table is still captured, as a diagnostic
    beside the report, where it can inform analysis without being scored.
    """
    urls: list[str] = []
    seen: set[str] = set()
    for src in sources or []:
        if not isinstance(src, dict):
            continue
        url = src.get("url") or src.get("link")
        if not isinstance(url, str):
            continue
        url = url.strip()
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return {"n_sources_retrieved": len(urls), "urls_retrieved": urls}


# ---------------------------------------------------------------------------
# CLI entry point for standalone testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run LDR benchmark")
    parser.add_argument("intent", help="Research query")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--shim-url", default="http://localhost:8081")
    parser.add_argument("--proxy-url", default="http://localhost:8100/v1")
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
