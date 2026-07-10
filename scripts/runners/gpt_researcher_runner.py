"""gpt-researcher runner for the deep-research benchmark.

Runs gpt-researcher 0.12.3 in its own venv (.venv-gptr) as a subprocess,
because gpt-researcher 0.12.3 imports langchain pre-1.0 submodules
(``langchain.docstore``, ``.vectorstores``, ``.text_splitter``, ``.callbacks``,
``.schema``, ...) that don't exist in langchain 1.x.  The main benchmark
venv (.venv-camel) runs langchain 1.x for langchain-odr, so gpt-researcher
needs its own isolated environment.

Configuration approach:
  - Sandbox search wiring (the reach-0 root fix). We do NOT monkey-patch the
    real ``TavilySearch.__init__`` any more. gpt-researcher resolves its
    retriever class lazily inside ``GPTResearcher.__init__`` via
    ``get_retrievers -> get_retriever("tavily")``, which runs a *late*
    ``from gpt_researcher.retrievers import TavilySearch`` at construction time.
    We therefore BIND a self-contained shim-backed retriever class onto that
    exact name (in both ``gpt_researcher.retrievers`` and the
    ``...tavily.tavily_search`` submodule) BEFORE ``GPTResearcher()`` is built,
    so every search gpt-researcher issues (the planning search and every
    sub-query search alike) goes through the sandbox shim. This removes all
    dependence on the real retriever's private ``self.base_url`` attribute and
    request payload, which is why the old ``__init__`` patch was fragile (see
    ``_build_shim_retriever_block``).
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

Why the old wiring missed (mechanism of the reach-0 bug):
  gpt-researcher 0.12.3's ``TavilySearch.search()`` wraps the whole request in
  ``try/except Exception`` and returns ``[]`` on ANY failure (see the vendored
  source: retrievers/tavily/tavily_search.py). The previous adapter only
  reassigned ``self.base_url`` after ``__init__``; that is an internal detail
  of one code path, and any mismatch (a version whose retriever uses the
  ``tavily`` SDK client instead of ``self.base_url``, a payload the shim
  rejects, a bind that lands after the class reference is captured) makes
  ``search()`` silently return zero sources. With zero retrieved sources the
  report writer falls back to the model's parametric prior and emits fluent but
  ungrounded public ``en.wikipedia.org`` citations (the archived 1294-public /
  1-localhost partial run). The fix replaces the whole retriever class so the
  request shape and endpoint are ours, and binds it at the name gpt-researcher
  actually imports, so the failure can no longer be silent.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import textwrap
import time
from pathlib import Path

from . import _budget, _egress
from ._runner_lock import runner_exclusive_lock

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
GPTR_PYTHON = str(ROOT / ".venv-gptr" / "bin" / "python")

# ---------------------------------------------------------------------------
# No runner-specific comparative wall clock.  A positive global/operator
# override is passed by run_deep_task; otherwise the shared no-progress watchdog
# owns termination and subprocess.run receives timeout=None.
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT_S = _budget.native_timeout_default()

# ---------------------------------------------------------------------------
# Sentinel markers for extracting the report from subprocess stdout.
# ---------------------------------------------------------------------------
_REPORT_START = "===GPTR_REPORT_START==="
_REPORT_END = "===GPTR_REPORT_END==="

# Grounding diagnostic marker. The driver prints one line with this prefix to
# stdout (OUTSIDE the report sentinels) reporting how many URLs the retriever
# actually returned and how many were localhost/sandbox origins. This is what
# makes the "reach 0" failure self-revealing on the next live run without
# guessing: retrieved=0 -> the bound _ShimTavilyRetriever fed the model no
# sources (shim down or every search errored — look for "[gptr-shim] ...
# FAILED" on stderr); retrieved>0 but localhost=0 -> real web leaked past the
# sandbox; localhost>0 -> the shim path works and sandbox URLs reached the
# writer.
_DIAG_MARK = "===GPTR_DIAG==="

# Agent identifier for the auto-discovery registry.
AGENT_NAME = "gpt-researcher"

# Workstream C — strict-sandbox eligibility.
# gpt-researcher resolves its retriever by the RETRIEVER name; we bind a
# shim-backed class onto that name (see _build_shim_retriever_block) so the
# retriever cannot reach the real web at all. Under strict_sandbox=True we keep
# RETRIEVER=tavily, and additionally fail-fast if a real TAVILY_API_KEY is
# leaking through the environment. Our retriever never reads that key, but the
# check is a defence-in-depth tripwire against a future code path that imports
# the real tavily client directly. The shim itself also runs in strict mode in
# this scenario, so any leaked request that still reached it is gated there.
STRICT_SANDBOX_ELIGIBLE = True

# Real Tavily keys start with `tvly-` followed by alphanumeric content;
# our fake sandbox key is `tvly-shim-fake`. Anything matching the prefix
# but NOT our sentinel is treated as a real key and refused under strict.
_FAKE_TAVILY_KEY = "tvly-shim-fake"


def _enhance_intent(intent: str) -> str:
    """Append grounding-neutral citation guidance to the shared task prompt.

    Fairness (open issue #19, seed-injection). Earlier revisions of this block
    seeded answers in two ways that a non-grounded model can exploit without
    ever retrieving anything:

      1. A literal example URL ``[Active noise control](http://localhost:8090/...)``
         which the model copied verbatim into its report as a fabricated
         citation (see archived dr_cross_deep_0023.md, the ONLY localhost URL
         across all 55 reports — it is this example, not a retrieved source).
      2. The exact per-domain citation counts the scorer checks for
         ("at least 15 Wikipedia ... shopping ... reddit"), i.e. teaching to
         the test and asymmetric vs the shared prompt other lanes receive.

    Neither helped grounding (url_reachability stayed 0). Both are adapter-
    injected, not part of the gpt-researcher framework, so removing them is the
    correct fairness direction. We keep only guidance that pushes toward
    grounding on *retrieved* sources and away from fabrication.
    """
    # 2026-07-08 (fairness audit, B3): the residual block is also removed.
    #
    # It was defended as "grounding-neutral", but it is not neutral relative to
    # the lanes that never received it. "Cite as markdown links `[label](url)`"
    # prescribes the one citation style the old PoF extractor could see; "cite
    # every factual claim" is an instruction to maximise citation density, which
    # is reach's numerator; "do not cite pages you did not retrieve" tells the
    # model the rule the scorer enforces. Telling one framework the grading
    # rubric and not the others is the thing this audit exists to stop, whether
    # or not the instruction is good advice.
    #
    # Parity is now enforced upstream: every lane receives the shared intent
    # plus `SHARED_REPORT_FORMAT`, and any deviation must be declared in
    # `config/lane_protocol.yaml`.
    return intent.strip()


def _build_shim_retriever_block(shim_url: str) -> str:
    """Return the driver code that defines and BINDS the sandbox retriever.

    This is the reach-0 root fix. Instead of monkey-patching the real
    ``TavilySearch.__init__`` (which only redirected ``self.base_url`` and
    silently no-ops if the retriever's request path ever changes), we:

      1. Define ``_ShimTavilyRetriever`` with the exact public contract
         gpt-researcher expects from a retriever class:
             __init__(query, headers=None, topic="general", query_domains=None)
             search(max_results=10) -> [{"href": url, "body": text}, ...]
         It POSTs every query to the sandbox shim's Tavily-compatible
         ``/search`` and returns ONLY the URLs the shim serves. There is no
         fallback to the real web.
      2. Bind that class onto ``gpt_researcher.retrievers.TavilySearch`` AND
         ``gpt_researcher.retrievers.tavily.tavily_search.TavilySearch`` BEFORE
         ``GPTResearcher()`` is constructed. gpt-researcher's
         ``get_retriever("tavily")`` runs a late
         ``from gpt_researcher.retrievers import TavilySearch`` at construction
         time, so replacing that name is exactly the framework's own resolution
         surface, not a fragile after-the-fact hook.

    Returned as plain (non f-string) source so its own ``{}`` / ``%`` stay
    literal when it is spliced into the outer f-string driver via a single
    ``{retriever_block}`` substitution (f-strings do not re-scan substituted
    values for braces).
    """
    search_endpoint = shim_url.rstrip("/") + "/search"
    endpoint_repr = repr(search_endpoint)
    return (
        "import os as _os, sys as _sys, requests as _rq\n"
        "\n"
        "_SHIM_SEARCH_URL = " + endpoint_repr + "\n"
        "\n"
        "class _ShimTavilyRetriever:\n"
        "    \"\"\"Sandbox retriever bound in place of gpt_researcher ... TavilySearch.\"\"\"\n"
        "    def __init__(self, query, headers=None, topic='general', query_domains=None):\n"
        "        self.query = query\n"
        "        self.headers = headers or {}\n"
        "        self.topic = topic\n"
        "        self.query_domains = query_domains or None\n"
        "\n"
        "    def search(self, max_results=10):\n"
        "        payload = {\n"
        "            'query': self.query,\n"
        "            'max_results': max_results,\n"
        "            'search_depth': 'basic',\n"
        "            'topic': self.topic,\n"
        "            'include_raw_content': True,\n"
        "            'include_domains': list(self.query_domains) if self.query_domains else None,\n"
        "        }\n"
        "        try:\n"
        "            resp = _rq.post(_SHIM_SEARCH_URL, json=payload, timeout=100)\n"
        "            resp.raise_for_status()\n"
        "            data = resp.json()\n"
        "        except Exception as e:\n"
        "            print('[gptr-shim] search FAILED q=%r err=%s' % (self.query, e), file=_sys.stderr)\n"
        "            return []\n"
        "        results = (data or {}).get('results', []) or []\n"
        "        out = []\n"
        "        for obj in results:\n"
        "            if not isinstance(obj, dict):\n"
        "                continue\n"
        "            url = obj.get('url') or obj.get('href')\n"
        "            if not url:\n"
        "                continue\n"
        "            body = obj.get('raw_content') or obj.get('content') or ''\n"
        "            out.append({'href': url, 'body': body})\n"
        "        print('[gptr-shim] search q=%r -> %d hits' % (self.query, len(out)), file=_sys.stderr)\n"
        "        return out\n"
        "\n"
        "# Bind at the name gpt-researcher's get_retriever('tavily') imports.\n"
        "import gpt_researcher.retrievers as _gr_pkg\n"
        "import gpt_researcher.retrievers.tavily.tavily_search as _gr_tav\n"
        "_gr_pkg.TavilySearch = _ShimTavilyRetriever\n"
        "_gr_tav.TavilySearch = _ShimTavilyRetriever\n"
        "print('[gptr-shim] bound _ShimTavilyRetriever -> ' + _SHIM_SEARCH_URL, file=_sys.stderr)\n"
    )


def _build_fetch_intercept_block(shim_url: str) -> str:
    """Return driver code that routes gpt-researcher's PAGE fetches through the
    shim's recorded ``GET /fetch?url=`` endpoint.

    Why this exists (FETCH_PATH_AUDIT_2026-07-08). Search was already bound to
    the shim (``_build_shim_retriever_block``), but gpt-researcher 0.12.3's
    default BeautifulSoup scraper reads each result page with a plain
    ``requests.get`` straight to the sandbox origin (localhost:7770/9999/8090).
    Those reads never touched the shim, so ``logs/fetch/<run_id>.jsonl`` recorded
    zero fetches and the scorer could not tell a page the agent actually opened
    from one it recited from parametric memory. We monkey-patch
    ``requests.Session.send`` (the single chokepoint under both ``requests.get``
    and ``Session().get``) so that a GET aimed at a sandbox SITE host is rewritten
    to ``{shim}/fetch?url=<original>``. The shim fetches the origin server-side,
    returns the bytes verbatim (same content-type), and records the read against
    the open run bracket. The scraper still receives the page HTML it expects, so
    this is transparent to the framework.

    Only GET-to-SITE is rewritten. Requests to the shim itself (the bound
    retriever POSTs to ``{shim}/search``) and to ds_proxy (LLM/embeddings) are
    left untouched, so there is no self-loop and no LLM interference. ``NO_PROXY``
    cannot defeat this: it is a monkey-patch, not an HTTP proxy.

    Returned as plain (non f-string) source so its ``{}`` stay literal when it is
    spliced into the outer f-string driver via one ``{fetch_block}`` slot.
    """
    fetch_endpoint = shim_url.rstrip("/") + "/fetch"
    endpoint_repr = repr(fetch_endpoint)
    return (
        "import requests as _fq, sys as _fsys\n"
        "from urllib.parse import urlparse as _fup, quote as _fquote\n"
        "_SHIM_FETCH_URL = " + endpoint_repr + "\n"
        "# Sandbox SITE origins only. The shim (8081) and ds_proxy (8088) are\n"
        "# deliberately absent so search POSTs and LLM calls are not rewritten.\n"
        "_FETCH_SITE_HOSTS = {\n"
        "    'localhost:7770','localhost:17770','localhost:8090','localhost:9999',\n"
        "    '127.0.0.1:7770','127.0.0.1:17770','127.0.0.1:8090','127.0.0.1:9999',\n"
        "}\n"
        "_fq_orig_send = _fq.Session.send\n"
        "def _fetch_via_shim_send(self, request, **kw):\n"
        "    try:\n"
        "        _p = _fup(request.url)\n"
        "        _hp = (_p.hostname or '').lower() + ':' + str(_p.port)\n"
        "    except Exception:\n"
        "        return _fq_orig_send(self, request, **kw)\n"
        "    if (request.method or '').upper() == 'GET' and _hp in _FETCH_SITE_HOSTS:\n"
        "        request.url = _SHIM_FETCH_URL + '?url=' + _fquote(request.url, safe='')\n"
        "        print('[gptr-fetch] site GET -> shim /fetch (%s)' % _hp, file=_fsys.stderr)\n"
        "    return _fq_orig_send(self, request, **kw)\n"
        "_fq.Session.send = _fetch_via_shim_send\n"
        "print('[gptr-fetch] requests.Session.send patched -> ' + _SHIM_FETCH_URL, file=_fsys.stderr)\n"
    )


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
    enhanced_intent = _enhance_intent(intent)

    # Sandbox retriever definition + registry bind (spliced verbatim below).
    retriever_block = _build_shim_retriever_block(shim_url)

    # Page-fetch interceptor: routes the scraper's requests.get to the shim's
    # recorded /fetch endpoint (spliced verbatim below).
    fetch_block = _build_fetch_intercept_block(shim_url)

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

# === Layer 0: Environment policy ===
# Preserve the recording door in harness mode; scrub ambient standalone
# proxies only. The parent already normalized every proxy spelling.
_DRA_EGRESS_ON = bool(os.environ.get('DRA_EGRESS_PROXY', '').strip())
if not _DRA_EGRESS_ON:
    for _pv in list(os.environ):
        if _pv.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'ftp_proxy'):
            del os.environ[_pv]
    os.environ['NO_PROXY'] = '*'

SHIM = {shim_url!r}
PROXY = {proxy_url!r}
MODEL = {model!r}

# === Layer 0b: Route page fetches through the shim's recorded /fetch ===
# The bound retriever (Layer 2) sends SEARCH through the shim, but the bs
# scraper reads each result page with a raw requests.get to the origin. This
# rewrites those site GETs to {{shim}}/fetch?url= so every page read is recorded
# and attributable. See FETCH_PATH_AUDIT_2026-07-08.md.
{fetch_block}

# === Layer 1: gpt-researcher env vars ===
# ds_proxy is OpenAI-compatible.  gpt-researcher's "openai:<model>"
# provider path uses OPENAI_BASE_URL.
os.environ['OPENAI_BASE_URL'] = PROXY
os.environ['OPENAI_API_BASE'] = PROXY
os.environ['OPENAI_API_KEY'] = 'anything'

# Assignment is deliberate.  setdefault let a login shell's stale Qwen/OpenAI
# values silently override the requested lane backbone and real-web retriever.
os.environ['FAST_LLM']      = f'openai:{{MODEL}}'
os.environ['SMART_LLM']     = f'openai:{{MODEL}}'
os.environ['STRATEGIC_LLM'] = f'openai:{{MODEL}}'
os.environ['RETRIEVER']     = 'tavily'
# "custom" provider so OpenAIEmbeddings reads OPENAI_BASE_URL
# (-> ds_proxy mapped to DashScope text-embedding-v4).
os.environ['EMBEDDING']      = 'custom:text-embedding-v4'
os.environ['TAVILY_API_KEY'] = 'tvly-shim-fake'
os.environ['TAVILY_API_URL'] = SHIM

# Disable optional integrations
os.environ.pop('LANGSMITH_TRACING', None)
os.environ.pop('LANGSMITH_API_KEY', None)
os.environ.pop('LANGCHAIN_TRACING_V2', None)

# === Layer 2: Bind the sandbox retriever (reach-0 root fix) ===
# Replaces the whole tavily retriever class with a shim-backed one and binds
# it at the exact name gpt-researcher's get_retriever('tavily') imports, BEFORE
# GPTResearcher() below builds self.retrievers. Every planning/sub-query search
# then goes through the sandbox shim; a wiring break can no longer silently
# swallow to zero sources (it prints [gptr-shim] ... FAILED to stderr).
{retriever_block}
# === Layer 3: Run gpt-researcher ===
from gpt_researcher import GPTResearcher

QUERY = {intent_repr}

async def _go():
    r = GPTResearcher(query=QUERY, report_type="research_report", tone="objective")
    await r.conduct_research()
    # Grounding diagnostic ONLY, no harness compensation. We proved (box
    # smoke8c, gpt-researcher 0.12.3) that the framework already threads every
    # scraped source URL into the writer's context as "Source: <url>"
    # (context/compression.py) and its report prompt MANDATES citing them
    # verbatim (prompts.py reference_prompt, report_source=web). So there is
    # nothing for the adapter to re-inject: a working retriever plus a capable
    # model is all it takes. An earlier revision here tried to append a curated
    # retrieved-URL block to the prompt and to mutate r.query after
    # construction; BOTH were dead code (the writer takes no prompt-override
    # keyword, and ReportGenerator snapshots r.query at __init__ so a later
    # mutation never reaches the prompt) AND, had they worked, they would have
    # written citations on the framework's behalf, i.e. a fairness violation. We
    # only READ the visited URLs to report how many sandbox origins the
    # framework surfaced; whether the model then cites them is the
    # framework-plus-model's job, not ours.
    _urls = []
    for _attr in ('visited_urls', 'research_sources', 'source_urls'):
        try:
            _v = getattr(r, _attr, None)
            if callable(_v):
                _v = _v()
            if _v:
                _urls = [u for u in (_v if not isinstance(_v, dict) else _v.keys()) if isinstance(u, str)]
                if _urls:
                    break
        except Exception:
            pass
    # Printed OUTSIDE the report sentinels so it never pollutes the captured
    # report. Surfaces whether the retriever actually fed the framework any
    # sandbox URLs; the parent parses this to log a warning when retrieved=0 or
    # localhost=0 (the "reach 0" failure mode). retrieved>0 & localhost>0 with a
    # report that still cites public URLs is a MODEL fabrication, documented and
    # attributed to the model, never patched over by the harness.
    _local = [u for u in _urls if ('localhost' in u) or ('127.0.0.1' in u)]
    print({_DIAG_MARK!r} + ' retrieved=%d localhost=%d' % (len(_urls), len(_local)))
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
    env["OPENAI_API_KEY"] = "anything"

    # gpt-researcher LLM/retriever config
    env["FAST_LLM"] = f"openai:{model}"
    env["SMART_LLM"] = f"openai:{model}"
    env["STRATEGIC_LLM"] = f"openai:{model}"
    env["RETRIEVER"] = "tavily"
    env["EMBEDDING"] = "custom:text-embedding-v4"
    env["TAVILY_API_KEY"] = _FAKE_TAVILY_KEY
    env["TAVILY_API_URL"] = shim_url.rstrip("/")
    env["GPTR_SHIM_URL"] = shim_url

    _egress.scrub_or_apply(env)

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


def _extract_diag(stdout: str) -> str:
    """Extract the grounding-diagnostic line (``_DIAG_MARK ...``) from stdout.

    Returns the marker line stripped of surrounding whitespace, or "" if the
    driver did not emit one (older driver, or a hard crash before research
    completed). Pure/string-only so it is unit-testable without the venv.
    """
    for line in stdout.splitlines():
        if line.startswith(_DIAG_MARK):
            return line.strip()
    return ""


def _summarize_shim_activity(stderr: str) -> tuple[int, int, int]:
    """Parse the bound retriever's ``[gptr-shim]`` breadcrumbs from stderr.

    Returns ``(n_search, n_hits, n_failed)``:
      - ``n_search``  number of search POSTs the bound ``_ShimTavilyRetriever``
        physically issued to the sandbox shim (one per ``[gptr-shim] search
        q=... -> N hits`` line),
      - ``n_hits``    total results the shim returned across those POSTs,
      - ``n_failed``  number of searches that raised (shim down / rejected —
        one per ``[gptr-shim] search FAILED`` line).

    This is the durable fix for the *silent* reach-0 failure: the runner used to
    log the subprocess stderr only on a non-zero exit, so a run that completed
    (exit 0) having issued zero shim POSTs — the exact deepseek symptom — left no
    trace in the lane log. Surfacing these counts on EVERY run makes "the
    framework never searched through the shim" self-revealing. Pure/string-only
    so it is unit-testable without the venv. Read-only: it parses breadcrumbs, it
    never adds or edits report content.
    """
    n_search = n_hits = n_failed = 0
    for line in stderr.splitlines():
        if "[gptr-shim]" not in line:
            continue
        if "search FAILED" in line:
            n_failed += 1
        elif "search q=" in line:
            n_search += 1
            # Tail shape: "... -> <N> hits"
            tail = line.rsplit("-> ", 1)
            if len(tail) == 2:
                num = tail[1].split(None, 1)[0]
                if num.isdigit():
                    n_hits += int(num)
    return n_search, n_hits, n_failed


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    timeout_s: float | None = DEFAULT_TIMEOUT_S,
    strict_sandbox: bool = False,
) -> str:
    """Run gpt-researcher and return the markdown report.

    Args:
        intent: The research query / task description.
        model: OpenAI-compatible model name (e.g. "deepseek-v4-flash").
        shim_url: Tavily-compatible search API URL (e.g. "http://localhost:8081").
        proxy_url: OpenAI-compatible LLM endpoint (e.g. "http://localhost:8100/v1").
        timeout_s: Explicit operator wall clock in seconds, or None (production
            default: no comparative outer wall clock).
        strict_sandbox: when True, pre-flight asserts no real Tavily key is
            present in the env (a future code path importing the real tavily
            client directly would otherwise reach api.tavily.com), keeps
            RETRIEVER=tavily (bound to the shim retriever), and writes
            SHIM_MODE=strict into the subprocess so any leaked request that
            still hits the shim is refused at the gate.

    Returns:
        The markdown report, or an error string starting with
        "(gpt-researcher ...".
    """
    # The subprocess environment overwrites any host Tavily configuration with
    # the sandbox sentinel and endpoint.  Refusing a run merely because a login
    # shell contains a real key is unnecessary once pollution cannot survive.
    if strict_sandbox:
        env_key = os.environ.get("TAVILY_API_KEY", "")
        if env_key and env_key != _FAKE_TAVILY_KEY:
            logger.warning(
                "gpt-researcher: replacing host TAVILY_API_KEY pollution with "
                "the sandbox sentinel"
            )
        logger.info("gpt-researcher: strict-sandbox active (RETRIEVER=tavily->shim, no real Tavily key)")

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
    driver_path = _egress.scratch_path("gptr-benchmark-driver")

    # Per-agent lock so parallel workers don't trample the shared driver path.
    _lock_cm = runner_exclusive_lock("gpt-researcher")
    _lock_cm.__enter__()

    try:
        driver_path.write_text(driver_code)

        env = _build_env(proxy_url, model, shim_url)

        # Strict-mode propagation: pin TAVILY_API_KEY to our sentinel and
        # forward SHIM_MODE=strict so the search shim's URL gate is the
        # second layer of defence behind the bound shim retriever.
        if strict_sandbox:
            env["TAVILY_API_KEY"] = _FAKE_TAVILY_KEY
            env["SHIM_MODE"] = "strict"
            env["GPTR_STRICT_SANDBOX"] = "1"

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

        # Surface the bound retriever's per-search shim breadcrumbs into the lane
        # log on EVERY run, not only failures. This is what closes the *silent*
        # reach-0 hole: a run could exit 0 having POSTed zero searches to the shim
        # (the deepseek symptom) and, because stderr was logged only on a non-zero
        # exit, leave no trace. These counts make "the framework never searched
        # through the shim" (n_search=0) vs "searched but the shim was down"
        # (n_failed>0) vs "searched and got sandbox hits" (n_hits>0) explicit.
        # Read-only: parsed from stderr breadcrumbs, no report content is touched.
        n_search, n_hits, n_failed = _summarize_shim_activity(stderr)
        if n_search or n_failed:
            log_at = logger.warning if (n_failed and not n_hits) else logger.info
            log_at(
                "gpt-researcher shim reach: %d search POST(s) -> %d hit(s), "
                "%d failed (shim=%s)", n_search, n_hits, n_failed, shim_url,
            )
        else:
            logger.warning(
                "gpt-researcher shim reach: the bound retriever issued NO search "
                "POSTs (no [gptr-shim] breadcrumbs on stderr) — the framework "
                "never called search() through the shim (shim=%s)", shim_url,
            )

        # Log the grounding diagnostic so the "reach 0" failure is visible in
        # the run log without inspecting the report. A warning here is the
        # cheapest signal that the Tavily->shim wiring needs a live check.
        diag = _extract_diag(stdout)
        if diag:
            if "retrieved=0" in diag or "localhost=0" in diag:
                logger.warning(
                    "gpt-researcher grounding: %s — NO sandbox URLs reached the "
                    "writer; check the [gptr-shim] stderr lines and the shim "
                    "/search endpoint on the box.", diag,
                )
            else:
                logger.info("gpt-researcher grounding: %s", diag)

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
        logger.error("gpt-researcher timed out after %ss", timeout_s)
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
    parser.add_argument("--proxy-url", default="http://localhost:8100/v1")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--output", "-o", help="Write report to file")
    parser.add_argument("--strict-sandbox", action="store_true", default=False)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    report = asyncio.run(
        run(
            intent=args.intent,
            model=args.model,
            shim_url=args.shim_url,
            proxy_url=args.proxy_url,
            timeout_s=args.timeout,
            strict_sandbox=args.strict_sandbox,
        )
    )

    if args.output:
        Path(args.output).write_text(report)
        print(f"Report written to {args.output} ({len(report)} chars)")
    else:
        print(report)
