"""Run a single agent through one deep-tier task.

Usage (on westd, with shim 8081 + ds_proxy 8088 + sandbox up):
    python3 scripts/run_deep_task.py \
        --agent gpt-researcher \
        --task dr_cross_deep_0001 \
        --backbone deepseek-v4-flash

Outputs:
    data/results/deep/<agent>__<task>.md         (final markdown report)
    data/results/deep/<agent>__<task>.meta.json  (timing, tokens, errors)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEEP_TASK_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
OUT_DIR = ROOT / "data" / "results" / "deep"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _load_task(task_id: str) -> dict:
    return json.loads((DEEP_TASK_DIR / f"{task_id}.json").read_text())


def _resolve_intent(task_cfg: dict) -> str:
    sandbox_subs = {
        "__SHOPPING__":  os.environ.get("SHOPPING",  "http://localhost:17770"),
        "__REDDIT__":    os.environ.get("REDDIT",    "http://localhost:9999"),
        "__WIKIPEDIA__": os.environ.get("WIKIPEDIA", "http://localhost:8090"),
    }
    intent = task_cfg.get("intent", "")
    for k, v in sandbox_subs.items():
        intent = intent.replace(k, v)
    return intent


def _setup_ds_backbone(model: str) -> None:
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    os.environ["OPENAI_BASE_URL"] = proxy
    os.environ["OPENAI_API_BASE"] = proxy
    os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "anything-proxy-uses-server-key")

    for var, val in [
        ("FAST_LLM",      f"openai:{model}"),
        ("SMART_LLM",     f"openai:{model}"),
        ("STRATEGIC_LLM", f"openai:{model}"),
        ("RETRIEVER",     "tavily"),
        # FIX #1: Use "custom" provider so gpt-researcher's OpenAIEmbeddings reads
        # OPENAI_BASE_URL (-> ds_proxy) with a model name ds_proxy actually maps to
        # DashScope text-embedding-v4.  "openai:embedding-3" failed because the
        # gpt-researcher "openai" path doesn't pass openai_api_base, so it tried
        # the real OpenAI endpoint.  "custom" path passes OPENAI_BASE_URL explicitly.
        ("EMBEDDING",     "custom:text-embedding-v4"),
    ]:
        os.environ.setdefault(var, val)


def _build_intercept_preamble(shim_url: str) -> str:
    """Generate inline Python code that patches requests/aiohttp/httpx at the
    transport layer to redirect api.tavily.com -> shim.

    This is embedded into subprocess driver scripts that run in their own venvs
    where `src.shim_intercept` is not importable.

    Key issues solved:
    - DeerFlow's EnhancedTavilySearchAPIWrapper does
      ``from langchain_tavily._utilities import TAVILY_API_URL`` which creates a
      stale local copy.  The requests.Session.send / aiohttp._request intercepts
      catch the actual HTTP call regardless of the Python variable.
    - aiohttp.ClientSession(trust_env=True) reads proxy settings from the process
      environment (/etc/environment on WSL has proxy vars).  We force trust_env=False.
    - DeerFlow's Jina crawler POSTs to https://r.jina.ai/ which is external.
      We intercept and fetch the target URL directly instead.
    - Process-level env cleanup to purge ALL proxy vars (belt-and-suspenders
      against /etc/environment being sourced by the subprocess shell).
    """
    return (
        "# --- HTTP-level intercept (auto-generated) ---\n"
        "import os as _os, sys as _sys\n"
        "# Purge ALL proxy env vars at process level (WSL /etc/environment leaks them)\n"
        "for _pv in list(_os.environ):\n"
        "    if _pv.lower() in ('http_proxy','https_proxy','all_proxy','no_proxy','ftp_proxy'):\n"
        "        del _os.environ[_pv]\n"
        "_os.environ['NO_PROXY'] = '*'\n"
        f"_SHIM_URL = {shim_url!r}\n"
        "def _rewrite_url(url):\n"
        "    if not url: return url\n"
        "    from urllib.parse import urlparse, urlunparse\n"
        "    p = urlparse(url)\n"
        "    h = p.hostname or ''\n"
        "    if 'api.tavily.com' in h:\n"
        "        sp = urlparse(_SHIM_URL)\n"
        "        nurl = urlunparse(p._replace(scheme=sp.scheme, netloc=sp.netloc))\n"
        "        print(f'[intercept] TAVILY: {url[:100]} -> {nurl[:100]}')\n"
        "        return nurl\n"
        "    if 'en.wikipedia.org' in h and p.path.startswith('/wiki/'):\n"
        "        kiwix = _os.environ.get('WIKIPEDIA_KIWIX_URL', 'http://localhost:8090')\n"
        "        kp = urlparse(kiwix)\n"
        "        title = p.path[len('/wiki/'):]\n"
        "        nurl = urlunparse(p._replace(scheme=kp.scheme, netloc=kp.netloc, path=f'/content/wikipedia_en_all_nopic/A/{title}', query=''))\n"
        "        print(f'[intercept] WIKI: {url[:100]} -> {nurl[:100]}')\n"
        "        return nurl\n"
        "    return url\n"
        "# Patch requests.Session.send - catches sync Tavily calls + Jina crawler\n"
        "try:\n"
        "    import requests as _rq\n"
        "    _orig_send = _rq.Session.send\n"
        "    def _ps(self, req, **kw):\n"
        "        from urllib.parse import urlparse as _up\n"
        "        _h = (_up(req.url).hostname or '')\n"
        "        # Intercept Jina crawler: POST to r.jina.ai -> fetch target URL directly\n"
        "        if 'r.jina.ai' in _h:\n"
        "            import json as _json\n"
        "            try:\n"
        "                _body = _json.loads(req.body) if isinstance(req.body, (str, bytes)) else {}\n"
        "                _target = _body.get('url', '')\n"
        "            except Exception:\n"
        "                _target = ''\n"
        "            if _target:\n"
        "                print(f'[intercept] JINA: r.jina.ai -> direct fetch {_target[:100]}')\n"
        "                _dreq = _rq.Request('GET', _target)\n"
        "                _prep = self.prepare_request(_dreq)\n"
        "                return _orig_send(self, _prep, **kw)\n"
        "        nu = _rewrite_url(req.url)\n"
        "        if nu != req.url: req.url = nu\n"
        "        return _orig_send(self, req, **kw)\n"
        "    _rq.Session.send = _ps\n"
        "except ImportError: pass\n"
        "# Patch aiohttp - force trust_env=False to prevent proxy leakage from\n"
        "# /etc/environment, and intercept _request for URL rewriting\n"
        "try:\n"
        "    import aiohttp as _ah\n"
        "    _orig_cs_init = _ah.ClientSession.__init__\n"
        "    def _cs_init_patched(self, *a, **kw):\n"
        "        kw['trust_env'] = False\n"
        "        return _orig_cs_init(self, *a, **kw)\n"
        "    _ah.ClientSession.__init__ = _cs_init_patched\n"
        "    _orig_areq = _ah.ClientSession._request\n"
        "    async def _par(self, method, url, **kw):\n"
        "        url = _rewrite_url(str(url))\n"
        "        return await _orig_areq(self, method, url, **kw)\n"
        "    _ah.ClientSession._request = _par\n"
        "except ImportError: pass\n"
        "# Patch httpx\n"
        "try:\n"
        "    import httpx as _hx\n"
        "    if hasattr(_hx, 'AsyncClient'):\n"
        "        _orig_hxa = _hx.AsyncClient.send\n"
        "        async def _pha(self, req, **kw):\n"
        "            nu = _rewrite_url(str(req.url))\n"
        "            if nu != str(req.url): req.url = _hx.URL(nu)\n"
        "            return await _orig_hxa(self, req, **kw)\n"
        "        _hx.AsyncClient.send = _pha\n"
        "    if hasattr(_hx, 'Client'):\n"
        "        _orig_hxs = _hx.Client.send\n"
        "        def _phs(self, req, **kw):\n"
        "            nu = _rewrite_url(str(req.url))\n"
        "            if nu != str(req.url): req.url = _hx.URL(nu)\n"
        "            return _orig_hxs(self, req, **kw)\n"
        "        _hx.Client.send = _phs\n"
        "except ImportError: pass\n"
        "print(f'[intercept] HTTP-level intercept installed (shim={_SHIM_URL})')\n"
        "# --- end intercept ---\n"
    )


def _setup_sandbox_shim() -> None:
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    os.environ.setdefault("TAVILY_API_KEY", "tvly-shim-fake")
    os.environ["GPTR_SHIM_URL"] = shim
    # FIX #9: Install HTTP-level intercept for ALL in-process runners.
    # This catches requests/httpx/aiohttp calls to api.tavily.com and
    # en.wikipedia.org regardless of which Python object made them.
    try:
        import src.shim_intercept  # noqa: F401 — auto-patches on import
    except Exception as e:
        print(f"  warn: shim_intercept install failed: {e}")


async def _run_gpt_researcher(intent: str) -> str:
    # gpt-researcher 0.12.3 still imports several langchain submodules that
    # were removed/relocated in langchain 1.x. Install runtime shims pointing
    # at the new homes so legacy imports resolve.
    import sys as _sys
    import types as _types

    def _shim_module(name: str, attrs: dict) -> None:
        if name in _sys.modules:
            return
        m = _types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        _sys.modules[name] = m

    try:
        from langchain_core.documents import Document as _LCDoc
        from langchain_core.vectorstores import VectorStore as _LCVS
        from langchain_text_splitters import (
            RecursiveCharacterTextSplitter as _LCSplit,
            CharacterTextSplitter as _LCCSplit,
        )
        _shim_module("langchain.docstore", {"document": None, "Document": _LCDoc})
        _shim_module("langchain.docstore.document", {"Document": _LCDoc})
        _sys.modules["langchain.docstore"].document = _sys.modules["langchain.docstore.document"]
        _shim_module("langchain.vectorstores", {"VectorStore": _LCVS})
        _shim_module("langchain.text_splitter", {
            "RecursiveCharacterTextSplitter": _LCSplit,
            "CharacterTextSplitter": _LCCSplit,
        })
        # Generic redirect: any future ``langchain.<x>`` import that fails
        # falls through to ``langchain_core.<x>`` / ``langchain_community.<x>``.
        # This catches the long tail of submodules gpt-researcher 0.12.3
        # references (callbacks, schema, prompts, chains, ...).
        import importlib.abc
        import importlib.machinery

        class _LangchainShimFinder(importlib.abc.MetaPathFinder):
            _checked = set()

            def find_spec(self, fullname, path, target=None):
                if not fullname.startswith("langchain."):
                    return None
                if fullname in self._checked:
                    return None
                self._checked.add(fullname)
                tail = fullname[len("langchain."):]
                for parent in ("langchain_core", "langchain_community"):
                    candidate = f"{parent}.{tail}"
                    try:
                        spec = importlib.util.find_spec(candidate)
                    except (ImportError, ValueError, ModuleNotFoundError):
                        continue
                    if spec is None:
                        continue
                    real = importlib.import_module(candidate)
                    _sys.modules[fullname] = real
                    return importlib.util.spec_from_loader(fullname, loader=None)
                return None

        if not any(isinstance(f, _LangchainShimFinder) for f in _sys.meta_path):
            _sys.meta_path.append(_LangchainShimFinder())
    except Exception:
        pass

    # FIX #1: Patch gpt-researcher's TavilySearch to use the sandbox shim for search,
    # and ensure the EMBEDDING env var is "custom:text-embedding-v4" so that the
    # OpenAIEmbeddings class reads OPENAI_BASE_URL (pointing at ds_proxy) instead of
    # hitting the real OpenAI endpoint.
    import gpt_researcher.retrievers.tavily.tavily_search as _tm
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    _orig = _tm.TavilySearch.__init__
    def _patched(self, *a, **kw):
        _orig(self, *a, **kw)
        self.base_url = f"{shim}/search"
    _tm.TavilySearch.__init__ = _patched

    from gpt_researcher import GPTResearcher

    # FIX P2.3: Enhance the query to explicitly request Wikipedia/encyclopedia citations.
    # gpt-researcher's search may find wiki content but the report writer drops wiki URLs
    # from citations because they don't look like typical web sources. We add explicit
    # instructions to the query to ensure wiki sources are cited.
    enhanced_intent = (
        intent + "\n\n"
        "CITATION REQUIREMENTS:\n"
        "- You MUST cite Wikipedia/encyclopedia articles as markdown links for technical definitions.\n"
        "- Include at least 15 Wikipedia article citations (e.g. [Active noise control](http://localhost:8090/...)).\n"
        "- Cite all three source types: shopping product pages, forum/reddit threads, AND Wikipedia articles.\n"
        "- Every factual claim needs a `[label](url)` markdown link."
    )
    r = GPTResearcher(query=enhanced_intent, report_type="research_report", tone="objective")
    await r.conduct_research()
    return await r.write_report()


# ---------------------------------------------------------------------------
# Workstream C — in-process HTTP gate
# ---------------------------------------------------------------------------
#
# Used by `_run_smolagents` and `_run_camel` (which both run in the parent
# process, not a subprocess venv). Reuses the helper inside the runner
# modules where available; falls back to its own implementation here so the
# strict-sandbox plumbing works regardless of which runner is invoked.

_INPROC_SANDBOX_HOSTS = frozenset({
    "localhost:7770", "localhost:17770", "localhost:8090", "localhost:9999", "localhost:8081", "localhost:18081",
    "127.0.0.1:7770", "127.0.0.1:17770", "127.0.0.1:8090", "127.0.0.1:9999", "127.0.0.1:8081", "127.0.0.1:18081",
})


def _install_inproc_sandbox_gate() -> None:
    """Install a `requests.Session.send` interceptor that rejects any
    non-sandbox URL with a synthetic 403 response. Idempotent.

    The interceptor is reset when the parent process exits — these in-
    process runners always run one task per parent process anyway.
    """
    if getattr(_install_inproc_sandbox_gate, "_done", False):
        return
    from urllib.parse import urlparse as _up

    def _ok(url: str) -> bool:
        try:
            p = _up(url)
            host = (p.hostname or "").lower()
            port = p.port
        except Exception:
            return False
        if not host or port is None:
            return False
        return f"{host}:{port}" in _INPROC_SANDBOX_HOSTS

    try:
        import requests  # type: ignore
    except ImportError:
        return
    _orig = requests.Session.send

    def _gated(self, request, **kw):
        if not _ok(request.url):
            print(f"[strict-sandbox] BLOCK non-sandbox: {request.url[:120]}")
            from requests.models import Response  # type: ignore
            r = Response()
            r.status_code = 403
            r._content = b'{"error":"non_sandbox_url_blocked"}'
            return r
        return _orig(self, request, **kw)

    requests.Session.send = _gated
    _install_inproc_sandbox_gate._done = True  # type: ignore[attr-defined]


async def _run_smolagents(intent: str, model: str, *, strict_sandbox: bool = False) -> str:
    from scripts.runners.evidence_fallback import (
        error_stub,
        fallback_enabled,
        is_weak_report,
        keep_or_stub,
        synthesize_report,
    )

    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    try:
        native_timeout = float(os.environ.get("SMOLAGENTS_NATIVE_TIMEOUT_S", "420") or "420")
    except ValueError:
        native_timeout = 420.0

    async def _fallback_report() -> str:
        return await asyncio.to_thread(
            synthesize_report, intent, model, shim, proxy, min_chars=4500, min_urls=5
        )

    async def _degrade(phase: str, reason: str) -> str:
        # Fairness rule: a smolagents failure must surface as the framework's
        # own (missing) output, never as a harness-ghostwritten report. In
        # benchmark mode we save an honest error stub; the evidence writer runs
        # only under the explicit non-benchmark EVIDENCE_FALLBACK_ENABLE flag.
        if fallback_enabled():
            return await _fallback_report()
        return error_stub("smolagents", phase, reason)

    # Default OFF: the native smolagents agent is the benchmark path. The old
    # default ("1") forced the evidence writer for every run, so this lane never
    # exercised smolagents at all and emitted the deterministic fallback report.
    force_fallback = os.environ.get("SMOLAGENTS_FORCE_FALLBACK", "0").strip().lower()
    if force_fallback not in {"0", "false", "no", "native"}:
        return await _degrade("forced", "SMOLAGENTS_FORCE_FALLBACK requested the evidence writer")

    if strict_sandbox:
        # Install the HTTP gate FIRST so any tool that bypasses the
        # patched TavilyClient (e.g. VisitWebpageTool fetching a URL the
        # model hallucinated) is refused at the requests layer instead of
        # leaking to the real internet.
        _install_inproc_sandbox_gate()
        os.environ["SHIM_MODE"] = "strict"
    try:
        import tavily
        _orig = tavily.TavilyClient.__init__
        def _patched(self, api_key=None, *a, **kw):
            kw.pop("api_base_url", None)
            _orig(self, api_key, *a, **kw)
            self.base_url = shim
        tavily.TavilyClient.__init__ = _patched
    except Exception as e:
        print(f"  warn: tavily patch: {e}")

    # FIX #2: Switch from CodeAgent to ToolCallingAgent.
    # CodeAgent generates Python code that *constructs* URLs from patterns, producing
    # 92% wrong URLs.  ToolCallingAgent uses tool calls (structured JSON), so it must
    # copy exact URLs returned by the search tool — dramatically improving URL accuracy.
    from smolagents import Tool, ToolCallingAgent, OpenAIServerModel
    from smolagents.default_tools import VisitWebpageTool

    class ShimSearchTool(Tool):
        name = "web_search"
        description = (
            "Search the local sandbox index. Returns exact sandbox URLs with snippets. "
            "Use only URLs returned by this tool for citations and webpage visits."
        )
        inputs = {
            "query": {
                "type": "string",
                "description": "Focused search query for products, forum discussions, or encyclopedia background.",
            }
        }
        output_type = "string"

        def forward(self, query: str) -> str:
            import requests

            max_results = int(os.environ.get("SMOLAGENTS_SEARCH_MAX_RESULTS", "6") or "6")
            snippet_chars = int(os.environ.get("SMOLAGENTS_SEARCH_SNIPPET_CHARS", "650") or "650")
            try:
                resp = requests.post(
                    f"{shim}/search",
                    json={
                        "query": query,
                        "api_key": os.environ.get("TAVILY_API_KEY", "tvly-shim-fake"),
                        "max_results": max_results,
                        "include_raw_content": True,
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception as e:  # noqa: BLE001
                return f"Search error for query {query!r}: {type(e).__name__}: {e}"

            results = payload.get("results") or []
            if not results:
                return f"No results found for query: {query}"
            lines = [f"Query: {query}", ""]
            for idx, item in enumerate(results[:max_results], 1):
                title = str(item.get("title") or "Untitled").strip()
                url = str(item.get("url") or "").strip()
                content = str(item.get("content") or item.get("raw_content") or "").strip()
                raw = str(item.get("raw_content") or "").strip()
                snippet = content or raw
                if len(snippet) > snippet_chars:
                    snippet = snippet[:snippet_chars] + "..."
                lines.append(f"{idx}. {title}")
                lines.append(f"   URL: {url}")
                if snippet:
                    lines.append(f"   Snippet: {snippet}")
                lines.append("")
            return "\n".join(lines).strip()

    llm = OpenAIServerModel(
        model_id=model,
        api_base=proxy,
        api_key=os.environ.get("OPENAI_API_KEY", "anything"),
    )
    agent = ToolCallingAgent(
        tools=[ShimSearchTool(), VisitWebpageTool()],
        model=llm,
        max_steps=int(os.environ.get("SMOLAGENTS_MAX_STEPS", "24") or "24"),
    )
    smol_prompt = (
        intent
        + "\n\nIMPORTANT: NEVER construct or guess URLs. Only use EXACT URLs "
        "returned by the search tool. Copy URLs verbatim from search results.\n\n"
        "FINAL REPORT REQUIREMENTS:\n"
        "- Return only the final markdown report, not planning notes.\n"
        "- Write at least 4500 characters and at least 10 substantive paragraphs.\n"
        "- Include a concise answer first, then evidence grouped by shopping, forum, "
        "and encyclopedia/wiki findings when those sources are relevant.\n"
        "- Cite exact sandbox URLs inline for factual claims whenever URLs are available.\n"
        "- The final report is invalid unless it contains at least 5 exact "
        "`http://localhost:...` sandbox URLs copied from search or visit results.\n"
        "- End with a References section listing the cited sandbox URLs.\n"
        "- Include tradeoffs, edge cases, and a final recommendation or verdict.\n"
        "- Make 6 to 10 focused searches, then stop searching and write the final report.\n"
        "- Do not stop after a brief summary; expand the reasoning enough for a fair "
        "deep-research comparison."
    )
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(agent.run, smol_prompt),
            timeout=max(60.0, native_timeout),
        )
    except Exception as e:
        return await _degrade("native", f"{type(e).__name__}: {e}")

    # FIX P2.2: smolagents may return a dict/JSON with {"answer": "..."} structure.
    # Extract the answer field if present.
    result = raw
    if isinstance(result, dict):
        result = result.get("answer", result.get("output", str(result)))
    elif isinstance(result, str):
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict) and "answer" in parsed:
                result = parsed["answer"]
            elif isinstance(parsed, dict) and "output" in parsed:
                result = parsed["output"]
        except (json.JSONDecodeError, TypeError):
            pass
    result = str(result)
    min_chars = int(os.environ.get("SMOLAGENTS_MIN_REPORT_CHARS", "3500") or "3500")
    min_urls = int(os.environ.get("SMOLAGENTS_MIN_SANDBOX_URLS", "5") or "5")

    def _sandbox_url_count(text: str) -> int:
        import re
        return len(set(re.findall(r"https?://localhost:[0-9]+[^\\s)\\]]+", text or "")))

    repair_reasons = []
    if len(result or "") < min_chars:
        repair_reasons.append(f"shorter than {min_chars} characters")
    if _sandbox_url_count(result) < min_urls:
        repair_reasons.append(f"fewer than {min_urls} sandbox URL citations")
    if repair_reasons:
        repair_prompt = (
            smol_prompt
            + "\n\nYour previous final report was invalid for this benchmark: "
            + "; ".join(repair_reasons)
            + ". Run new searches if needed, then rewrite it into a complete "
            f"markdown report of at least {min_chars} characters with at least "
            f"{min_urls} exact `http://localhost:...` markdown links. Preserve any "
            "concrete evidence already found. Add source-by-source analysis, "
            "tradeoffs, assumptions, and a clear verdict. Return only the expanded "
            "report, and include a References section.\n\n"
            "Previous short report:\n"
            f"{result}"
        )
        try:
            repaired = await asyncio.wait_for(
                asyncio.to_thread(agent.run, repair_prompt),
                timeout=max(60.0, native_timeout),
            )
        except Exception as e:
            return await _degrade("repair", f"{type(e).__name__}: {e}")
        if isinstance(repaired, dict):
            repaired = repaired.get("answer", repaired.get("output", str(repaired)))
        elif isinstance(repaired, str):
            try:
                parsed = json.loads(repaired)
                if isinstance(parsed, dict) and "answer" in parsed:
                    repaired = parsed["answer"]
                elif isinstance(parsed, dict) and "output" in parsed:
                    repaired = parsed["output"]
            except (json.JSONDecodeError, TypeError):
                pass
        result = str(repaired)

    if (
        is_weak_report(result, min_chars=min_chars, min_urls=3)
        or _sandbox_url_count(result) < min_urls
    ):
        reason = (
            f"native output under threshold ({len(result or '')} chars, "
            f"{_sandbox_url_count(result)} sandbox URLs)"
        )
        if fallback_enabled():
            return await _degrade("write", reason)
        # Weak-but-real output is the framework's own report: save it verbatim
        # (the scorer judges quality); stub only genuinely empty/stub output.
        return keep_or_stub("smolagents", "write", reason, result)
    return result


def _sanitize_camel_report(text: str) -> str:
    """Strip model scaffolding from a camel-ai report BEFORE it is saved.

    Fairness audit 2026-07-06: camel saved the model's raw output including
    literal ``<think>...</think>`` reasoning and ``<tool_call>`` XML scaffolding
    (archived reports 0013/0024/0037). We remove ONLY that scaffolding; all
    prose and citations are preserved byte-for-byte otherwise. This changes the
    saved artifact only, not camel's behavior, prompts, or termination. The
    audit's model-capability verdict on camel's low grounding still stands.
    """
    import re as _re
    s = str(text or "")
    # Complete <think>...</think> reasoning blocks (multiline).
    s = _re.sub(r"<think\b[^>]*>.*?</think\s*>", "", s, flags=_re.DOTALL | _re.IGNORECASE)
    # Complete tool-call / tool-response scaffolding blocks.
    s = _re.sub(r"<tool_call\b[^>]*>.*?</tool_call\s*>", "", s, flags=_re.DOTALL | _re.IGNORECASE)
    s = _re.sub(r"<tool_response\b[^>]*>.*?</tool_response\s*>", "", s, flags=_re.DOTALL | _re.IGNORECASE)
    # Dangling / unclosed openers run to the end of the text.
    s = _re.sub(r"<think\b[^>]*>.*", "", s, flags=_re.DOTALL | _re.IGNORECASE)
    s = _re.sub(r"<tool_call\b[^>]*>.*", "", s, flags=_re.DOTALL | _re.IGNORECASE)
    s = _re.sub(r"<tool_response\b[^>]*>.*", "", s, flags=_re.DOTALL | _re.IGNORECASE)
    # Orphan closing tags left behind by malformed emissions.
    s = _re.sub(r"</?(?:think|tool_call|tool_response)\s*>", "", s, flags=_re.IGNORECASE)
    return s.strip()


async def _run_camel(intent: str, model: str, *, strict_sandbox: bool = False) -> str:
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    from scripts.runners.evidence_fallback import (
        error_stub,
        fallback_enabled,
        is_weak_report,
        keep_or_stub,
        synthesize_report,
    )

    async def _fallback_report() -> str:
        return await asyncio.to_thread(
            synthesize_report, intent, model, shim, proxy, min_chars=4500, min_urls=5
        )

    async def _degrade(phase: str, reason: str) -> str:
        # Fairness rule: a camel-ai failure must surface as the framework's own
        # (missing) output, never as a harness-ghostwritten report. In benchmark
        # mode we save an honest error stub; the evidence writer runs only under
        # the explicit non-benchmark EVIDENCE_FALLBACK_ENABLE flag.
        if fallback_enabled():
            return await _fallback_report()
        return error_stub("camel-ai", phase, reason)

    if os.environ.get("CAMEL_FORCE_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}:
        return await _degrade("forced", "CAMEL_FORCE_FALLBACK requested the evidence writer")

    if strict_sandbox:
        # Same gate as smolagents — camel-ai's SearchToolkit may add new
        # tools at any release; the HTTP-layer gate catches anything that
        # doesn't go through the patched TavilyClient.
        _install_inproc_sandbox_gate()
        os.environ["SHIM_MODE"] = "strict"

    import tavily
    _orig = tavily.TavilyClient.__init__
    def _patched(self, api_key=None, *a, **kw):
        kw.pop("api_base_url", None)
        _orig(self, api_key, *a, **kw)
        self.base_url = shim
    tavily.TavilyClient.__init__ = _patched

    from camel.agents import ChatAgent
    from camel.models import ModelFactory
    from camel.toolkits import SearchToolkit, FunctionTool
    from camel.types import ModelPlatformType

    m = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=model,
        url=proxy,
        api_key=os.environ.get("OPENAI_API_KEY", "anything"),
        model_config_dict={"temperature": 0.2, "max_tokens": 8192},
    )
    tk = SearchToolkit()
    tools = [FunctionTool(tk.search_tavily)]
    for attr in ("tavily_extract", "search_tavily_extract"):
        if hasattr(tk, attr):
            tools.append(FunctionTool(getattr(tk, attr)))
            break

    # Fairness audit 2026-07-06: trimmed the bespoke rubric nudge. The prior
    # system prompt demanded >=60 citations, >=15 Wikipedia articles, >=20
    # search calls and a 3500+ word report, plus a per-domain keyword strategy
    # that mirrored the scorer thresholds. The audit flagged this as the
    # heaviest rubric-shaped asymmetry among the in-process lanes. Under the
    # binding user decision, per-lane prompt EXTRAS that hand one lane a rubric
    # advantage over the shared task prompt are removed. The system message is
    # now a neutral deep-research role plus the shared citation policy (cite
    # exact retrieved URLs, do not invent), which is what every lane already
    # receives via the task intent.
    system = (
        "You are a deep-research agent. Use the search tool to gather evidence, "
        "then write a comprehensive markdown report that answers the task. Every "
        "factual claim must be a markdown link `[label](url)` to a specific page "
        "you actually retrieved. Do not invent URLs."
    )
    agent = ChatAgent(system_message=system, model=m, tools=tools)
    native_timeout = int(os.environ.get("CAMEL_NATIVE_TIMEOUT_S", "0") or "0")
    try:
        if native_timeout > 0:
            resp = await asyncio.wait_for(
                asyncio.to_thread(agent.step, intent), timeout=native_timeout
            )
        else:
            resp = agent.step(intent)
    except asyncio.TimeoutError:
        print(f"camel-ai native path exceeded {native_timeout}s")
        return await _degrade("native", f"native path exceeded {native_timeout}s timeout")
    except Exception as e:  # noqa: BLE001
        print(f"  warn: camel-ai native path failed: {e}")
        return await _degrade("native", f"{type(e).__name__}: {e}")
    content = resp.msg.content if resp.msg else "(empty)"

    # Fairness audit 2026-07-06: sanitize the SAVED report only — strip
    # <think>...</think> reasoning and dangling tool-call XML scaffolding that
    # qwen emits as literal text. Prose and citations are untouched.
    content = _sanitize_camel_report(content)

    # FIX P2.1: Strip CoT leakage prefix (e.g. "I now have enough data to compile...")
    import re as _re
    # Remove common CoT prefixes that leak into the output
    _cot_patterns = [
        r'^(?:I now have enough|Now I have enough|I have gathered enough|Let me compile|'
        r'Based on (?:my|the) (?:research|search|findings)|I\'ll now (?:compile|write|create))'
        r'[^\n]*\n+',
    ]
    for pat in _cot_patterns:
        content = _re.sub(pat, '', content, count=1, flags=_re.IGNORECASE)
    # Also strip any leading text before the first markdown heading
    if '\n# ' in content:
        idx = content.index('\n# ')
        prefix = content[:idx].strip()
        # Only strip if the prefix is short CoT (< 500 chars) and doesn't contain citations
        if len(prefix) < 500 and '[' not in prefix:
            content = content[idx:].lstrip('\n')

    if is_weak_report(content, min_chars=3000, min_urls=3):
        if fallback_enabled():
            return await _degrade("write", "native report weak/under-threshold")
        # Weak-but-real output is camel's own report: save it verbatim (the
        # scorer judges quality); stub only genuinely empty/stub output.
        return keep_or_stub("camel-ai", "write", "native report weak/under-threshold", content)
    return content


async def _run_storm(intent: str, model: str, *, strict_sandbox: bool = False) -> str:
    """STORM via clean runner module:uses SandboxSearchRM (dspy.Retrieve subclass).

    Forwards `strict_sandbox` so storm_runner.run() installs its strict HTTP
    gate (_install_strict_http_gate). Without this the gate is never armed and
    a closed-book run would be silently downgraded to best-effort shim-only.
    """
    from scripts.runners.storm_runner import run as storm_run
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await storm_run(
        intent=intent, model=model, shim_url=shim, proxy_url=proxy,
        strict_sandbox=strict_sandbox,
    )


async def _run_storm_OLD(intent: str, model: str) -> str:
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    kiwix = os.environ.get("WIKIPEDIA_KIWIX_URL", "http://localhost:8090")

    # =====================================================================
    # FIX #12: Pre-download sentence-transformers model WITH proxy enabled.
    # STORM's ArticleTextProcessing / WebPageHelper loads
    # sentence-transformers/paraphrase-MiniLM-L6-v2 on first use. After we
    # strip the proxy env vars, huggingface.co is unreachable. So we trigger
    # the download now (while proxy may still be set), then proceed.
    #
    # Strategy:
    #   1. Try loading the model (works if already cached).
    #   2. If it fails with a connection error, temporarily restore the
    #      HTTP proxy, download, then remove proxy again.
    #   3. Set HF_HUB_OFFLINE=1 after successful download so STORM never
    #      attempts another network call to HF during the run.
    # =====================================================================
    _hf_model_name = "sentence-transformers/paraphrase-MiniLM-L6-v2"

    def _ensure_hf_model_cached():
        """Ensure the HF model is in local cache. Returns True if available."""
        try:
            from sentence_transformers import SentenceTransformer
            # This will load from cache if available, or download if not
            SentenceTransformer(_hf_model_name)
            print(f"[storm] HF model '{_hf_model_name}' loaded from cache.")
            return True
        except Exception as e:
            if "Max retries exceeded" in str(e) or "ConnectionError" in str(e) or "NewConnectionError" in str(e):
                return False
            # Other errors (e.g. import error) -- model might still be cached
            # at the file level even if sentence_transformers isn't importable
            # in this venv. Check huggingface_hub directly.
            try:
                from huggingface_hub import snapshot_download
                snapshot_download(_hf_model_name, local_files_only=True)
                print(f"[storm] HF model '{_hf_model_name}' found in hub cache.")
                return True
            except Exception:
                return False

    # First try without any proxy changes
    if not _ensure_hf_model_cached():
        # Model not cached -- temporarily restore proxy for download
        _http_proxy = os.environ.get("_SAVED_HTTP_PROXY", "") or os.environ.get("HTTP_PROXY", "")
        _https_proxy = os.environ.get("_SAVED_HTTPS_PROXY", "") or os.environ.get("HTTPS_PROXY", "")
        # Fallback: use Mihomo proxy on WSL default gateway
        if not _http_proxy:
            try:
                import subprocess as _sp
                gw = _sp.check_output(
                    ["ip", "route"], text=True, timeout=5
                )
                for line in gw.splitlines():
                    if line.startswith("default"):
                        gw_ip = line.split()[2]
                        _http_proxy = f"http://{gw_ip}:7890"
                        _https_proxy = _http_proxy
                        break
            except Exception:
                pass
        if _http_proxy:
            print(f"[storm] Model not cached. Downloading with proxy={_http_proxy}...")
            os.environ["HTTP_PROXY"] = _http_proxy
            os.environ["HTTPS_PROXY"] = _https_proxy or _http_proxy
            os.environ["http_proxy"] = _http_proxy
            os.environ["https_proxy"] = _https_proxy or _http_proxy
            try:
                _ensure_hf_model_cached()
            finally:
                # Strip proxy again immediately after download
                for _pv in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                    os.environ.pop(_pv, None)
        else:
            print(f"[storm] WARNING: Model not cached and no proxy available. STORM may fail.")

    # Tell HF libraries to work offline from now on
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    # FIX #10: Monkey-patch requests.Session.send BEFORE importing STORM.
    # STORM's WebPageHelper fetches URLs from search results (e.g.
    # https://en.wikipedia.org/wiki/Headphones) using requests.  Without a
    # proxy these fail with "Network is unreachable".  We intercept at the
    # transport layer and rewrite:
    #   - en.wikipedia.org/wiki/X  ->  localhost:8090/content/wikipedia_en_all_nopic/A/X
    #   - api.tavily.com           ->  localhost:8081 (the shim)
    #   - localhost:7770/9999/8090  ->  untouched
    import requests as _rq
    _storm_orig_send = _rq.Session.send

    def _storm_patched_send(self, request, **kw):
        url = request.url
        if 'en.wikipedia.org/wiki/' in url:
            title = url.split('/wiki/')[-1].split('?')[0].split('#')[0]
            request.url = f'{kiwix}/content/wikipedia_en_all_nopic/A/{title}'
            kw['verify'] = False
            # Strip proxy settings so localhost isn't routed through a dead proxy
            kw.pop('proxies', None)
            if 'Host' in request.headers:
                from urllib.parse import urlparse as _up
                request.headers['Host'] = _up(request.url).netloc
            print(f'[storm-intercept] WIKI: {url[:100]} -> {request.url[:100]}')
        elif 'en.wikipedia.org' in url:
            # Non-wiki paths (e.g. /w/api.php) - redirect to Kiwix search
            from urllib.parse import urlparse as _up, urlunparse as _uu
            p = _up(url)
            request.url = _uu(p._replace(
                scheme='http',
                netloc=_up(kiwix).netloc,
                path='/search',
            ))
            kw['verify'] = False
            kw.pop('proxies', None)
            print(f'[storm-intercept] WIKI-API: {url[:100]} -> {request.url[:100]}')
        elif 'api.tavily.com' in url:
            from urllib.parse import urlparse as _up, urlunparse as _uu
            p = _up(url)
            sp = _up(shim)
            request.url = _uu(p._replace(scheme=sp.scheme, netloc=sp.netloc))
            kw['verify'] = False
            kw.pop('proxies', None)
            print(f'[storm-intercept] TAVILY: {url[:100]} -> {request.url[:100]}')
        elif 'huggingface.co' in url or 'hf.co' in url:
            # Block any unexpected HF downloads -- model should already be cached
            print(f'[storm-intercept] BLOCKED HF download: {url[:120]}')
            from requests.models import Response
            resp = Response()
            resp.status_code = 503
            resp._content = b'HF downloads blocked in sandbox mode'
            return resp
        return _storm_orig_send(self, request, **kw)

    _rq.Session.send = _storm_patched_send

    # Also strip proxy env vars so requests doesn't try to route localhost
    # through a dead HTTP_PROXY (which causes "Network is unreachable").
    _saved_proxy_env = {}
    for _pv in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'):
        if _pv in os.environ:
            _saved_proxy_env[_pv] = os.environ.pop(_pv)
    os.environ['NO_PROXY'] = os.environ.get('NO_PROXY', '') + ',en.wikipedia.org,api.tavily.com'

    # FIX #7: Patch tavily.TavilyClient AND tavily.AsyncTavilyClient so STORM's
    # TavilySearchRM (which does `from tavily import TavilyClient; self.tavily_client
    # = TavilyClient(...)`) hits the sandbox shim, not api.tavily.com.
    import tavily
    _orig = tavily.TavilyClient.__init__
    def _patched(self, api_key=None, *a, **kw):
        kw.pop("api_base_url", None)
        _orig(self, api_key, *a, **kw)
        self.base_url = shim
    tavily.TavilyClient.__init__ = _patched

    # Also patch AsyncTavilyClient if present
    if hasattr(tavily, "AsyncTavilyClient"):
        _orig_async = tavily.AsyncTavilyClient.__init__
        def _patched_async(self, *a, **kw):
            kw.pop("api_base_url", None)
            kw["api_base_url"] = shim
            _orig_async(self, *a, **kw)
            self._api_base_url = shim
        tavily.AsyncTavilyClient.__init__ = _patched_async

    try:
        from knowledge_storm.storm_wiki.engine import (
            STORMWikiRunner, STORMWikiRunnerArguments, STORMWikiLMConfigs,
        )
        from knowledge_storm.lm import LitellmModel
        from knowledge_storm.rm import TavilySearchRM

        llm_kw = dict(
            model=f"openai/{model}",
            api_key=os.environ.get("OPENAI_API_KEY", "anything"),
            api_base=proxy,
            max_tokens=2000,
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
            setter(LitellmModel(**llm_kw))

        # Use a unique scratch dir per run to avoid collisions
        import hashlib
        scratch_name = hashlib.md5(intent[:300].encode()).hexdigest()[:12]
        scratch_dir = str(OUT_DIR / f"_storm_scratch_{scratch_name}")

        args = STORMWikiRunnerArguments(
            output_dir=scratch_dir,
            max_conv_turn=3,
            max_perspective=3,
            search_top_k=5,
            max_thread_num=2,
        )
        rm = TavilySearchRM(
            tavily_search_api_key=os.environ.get("TAVILY_API_KEY", "tvly-shim-fake"),
            k=5,
            include_raw_content=True,
        )
        # BUG B fix: TavilySearchRM with a fake key would otherwise query the
        # OPEN WEB (api.tavily.com) and get nothing, so STORM produced no
        # article. Point its retrieval at the sandbox shim the same way
        # scripts/runners/gpt_researcher_runner.py patches TavilySearch.base_url.
        # TavilySearchRM holds a `tavily.TavilyClient` (the .__init__ patch
        # above already redirects new clients), but we also override the
        # already-constructed client's base URL defensively so a future
        # knowledge_storm version that builds the client differently still
        # routes to the shim and not the open web. TavilyClient appends
        # "/search" to base_url itself, so we set the bare shim base here
        # (matching the TavilyClient.__init__ patch above), mirroring how
        # gpt_researcher_runner points TavilySearch.base_url at the shim.
        for _attr in ("tavily_client", "client", "_client"):
            _client = getattr(rm, _attr, None)
            if _client is not None and hasattr(_client, "base_url"):
                _client.base_url = shim
        runner = STORMWikiRunner(args, lm_config, rm)
        runner.run(
            topic=intent[:300],
            do_research=True,
            do_generate_outline=True,
            do_generate_article=True,
            do_polish_article=True,
        )
        runner.post_run()

        # FIX #7 (cont): STORM creates the article dir using a sanitized topic name.
        # The exact sanitization varies by version, so search all subdirs for output files.
        # Prefer polished articles, then generated articles, then any markdown/text.
        scratch_path = Path(scratch_dir)
        candidates = list(scratch_path.rglob("storm_gen_article_polished.txt"))
        if not candidates:
            candidates = list(scratch_path.rglob("storm_gen_article*.txt"))
        if not candidates:
            candidates = list(scratch_path.rglob("*.md"))
        if not candidates:
            candidates = list(scratch_path.rglob("*.txt"))
        if candidates:
            # Pick the largest file (most likely the polished article)
            candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
            result = candidates[0].read_text()
            print(f"[storm] output file: {candidates[0]} ({len(result)} chars)")
            return result
        # List what's actually in scratch_dir for debugging
        all_files = list(scratch_path.rglob("*"))
        print(f"[storm] no article found in {scratch_dir}. Files: {[str(f) for f in all_files[:20]]}")
        return "(empty storm output)"

    finally:
        # Restore proxy env vars so other runners aren't affected
        for _pv, _val in _saved_proxy_env.items():
            os.environ[_pv] = _val
        # Restore original requests.Session.send
        _rq.Session.send = _storm_orig_send
        # Remove offline flags so other runners can use HF if needed
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)


async def _run_langchain_odr_graph(intent: str, model: str) -> str:
    """LangChain open_deep_research uses a langgraph supervisor → researcher → writer."""
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    os.environ["OPENAI_BASE_URL"] = proxy
    os.environ.setdefault("OPENAI_API_KEY", "anything")
    os.environ.setdefault("TAVILY_API_KEY", "tvly-shim-fake")

    shim = os.environ.get("SHIM_URL", "http://localhost:8081")

    # FIX #4: LangChain ODR uses `tavily.AsyncTavilyClient`, NOT `tavily.TavilyClient`.
    # The old patch only patched TavilyClient.__init__, which AsyncTavilyClient doesn't
    # call.  We must patch both.
    #
    # FIX #5 (adapter audit 2026-07-07): the installed tavily 0.5.x
    # `AsyncTavilyClient.__init__(api_key, company_info_tags, proxies)` has NO
    # `api_base_url` parameter and no `_api_base_url` / `_client` attributes.  It
    # bakes `base_url="https://api.tavily.com"` into a `self._client_creator`
    # lambda.  The previous patch injected `kw["api_base_url"] = shim` into the
    # real __init__, which raised
    #   TypeError: AsyncTavilyClient.__init__() got an unexpected keyword argument 'api_base_url'
    # on EVERY construction.  ODR's `execute_tool_safely` swallowed that into an
    # "Error executing tool" observation, so every search silently returned no
    # sources and the writer produced ungrounded prose with zero localhost
    # citations on both backbones.  The correct patch does not pass api_base_url
    # to the real __init__; it repoints the httpx client factory at the shim
    # (and still sets the documented base-url attributes for other tavily builds).
    try:
        import tavily
        import httpx as _odr_httpx
        # Patch sync client (for any fallback paths)
        _orig_sync = tavily.TavilyClient.__init__
        def _patched_sync(self, api_key=None, *a, **kw):
            kw.pop("api_base_url", None)
            _orig_sync(self, api_key, *a, **kw)
            self.base_url = shim
        tavily.TavilyClient.__init__ = _patched_sync

        def _odr_repoint_client_creator(client_obj):
            """Wrap a tavily client's `_client_creator` so every httpx.AsyncClient
            it builds targets the sandbox shim instead of api.tavily.com."""
            creator = getattr(client_obj, "_client_creator", None)
            if callable(creator):
                def _shim_client_creator(_creator=creator):
                    client = _creator()
                    try:
                        client.base_url = _odr_httpx.URL(shim)
                    except Exception:
                        client.base_url = shim
                    return client
                client_obj._client_creator = _shim_client_creator

        # Patch async client (the one ODR actually uses)
        if hasattr(tavily, "AsyncTavilyClient"):
            _orig_async = tavily.AsyncTavilyClient.__init__
            def _patched_async(self, *a, **kw):
                # Do NOT forward api_base_url to the real __init__ (unsupported
                # in tavily 0.5.x and raises TypeError).
                kw.pop("api_base_url", None)
                _orig_async(self, *a, **kw)
                # tavily 0.5.x: repoint the per-request client factory at the shim.
                _odr_repoint_client_creator(self)
                # Belt-and-suspenders for tavily builds that expose these directly:
                if hasattr(self, "_api_base_url"):
                    self._api_base_url = shim
                if getattr(self, "_client", None) is not None:
                    self._client.base_url = shim
            tavily.AsyncTavilyClient.__init__ = _patched_async
    except Exception as e:
        print(f"  warn: tavily patch (langchain-odr): {e}")

    odr_model = f"openai:{model}"
    os.environ["DEFAULT_MODEL"] = model
    os.environ["OPENAI_MODEL_NAME"] = model
    # open_deep_research reads environment variables before runnable config.
    # Some internal summarization calls do not consistently receive the graph
    # config, so set the env fallback too.
    os.environ["RESEARCH_MODEL"] = odr_model
    os.environ["SUMMARIZATION_MODEL"] = odr_model
    os.environ["COMPRESSION_MODEL"] = odr_model
    os.environ["FINAL_REPORT_MODEL"] = odr_model
    # GLM sometimes returns {"description": "..."} for ODR's structured
    # ResearchQuestion despite the schema requiring {"research_brief": "..."}.
    # Accept that common shape so the graph can proceed instead of failing
    # before any research is performed.
    import open_deep_research.deep_researcher as _odr_deep_researcher
    from pydantic import BaseModel as _PydanticBaseModel
    from pydantic import ConfigDict as _PydanticConfigDict
    from pydantic import Field as _PydanticField
    from pydantic import model_validator as _pydantic_model_validator

    class _ResearchQuestionCompat(_PydanticBaseModel):
        model_config = _PydanticConfigDict(populate_by_name=True)

        research_brief: str = _PydanticField(
            description="A research question that will be used to guide the research.",
        )

        @_pydantic_model_validator(mode="before")
        @classmethod
        def _coerce_description(cls, data):
            if isinstance(data, dict) and not data.get("research_brief"):
                desc = data.get("description")
                if isinstance(desc, str):
                    data = dict(data)
                    data["research_brief"] = desc
                elif isinstance(desc, dict):
                    for key in ("research_brief", "brief", "query", "question", "description"):
                        val = desc.get(key)
                        if isinstance(val, str) and val.strip():
                            data = dict(data)
                            data["research_brief"] = val
                            break
                    else:
                        vals = [v for v in desc.values() if isinstance(v, str) and v.strip()]
                        if vals:
                            data = dict(data)
                            data["research_brief"] = max(vals, key=len)
            return data

    _odr_deep_researcher.ResearchQuestion = _ResearchQuestionCompat
    deep_researcher_builder = _odr_deep_researcher.deep_researcher_builder

    # ODR's Tavily tool normally runs an LLM summarizer over every raw search
    # result using asyncio.gather(). With GLM-4.7-Flash this creates many
    # concurrent proxy calls and 429 retry storms. Our shim already returns
    # sandbox text, so return truncated raw snippets directly.
    try:
        import open_deep_research.utils as _odr_utils
        from langchain_core.tools import tool as _lc_tool

        async def _summarize_webpage_noop(_model, webpage_content: str) -> str:
            return str(webpage_content or "").replace("\x00", "")[:3500]

        _odr_utils.summarize_webpage = _summarize_webpage_noop

        @_lc_tool("tavily_search", description=_odr_utils.TAVILY_SEARCH_DESCRIPTION)
        async def _tavily_search_no_summarize(
            queries: list[str],
            max_results: int = 5,
            topic: str = "general",
        ) -> str:
            if isinstance(queries, str):
                queries = [queries]
            search_results = []
            for query in queries[:2]:
                search_results.extend(await _odr_utils.tavily_search_async(
                    [query],
                    max_results=min(int(max_results or 5), 5),
                    topic=topic,
                    include_raw_content=True,
                    config=None,
                ))

            unique_results = {}
            for response in search_results:
                for result in response.get("results", []):
                    url = result.get("url")
                    if url and url not in unique_results:
                        unique_results[url] = {**result, "query": response.get("query", "")}

            if not unique_results:
                return "No valid search results found. Please try different search queries."

            formatted_output = "Search results:\n"
            for i, (url, result) in enumerate(unique_results.items(), start=1):
                content = (
                    result.get("raw_content")
                    or result.get("raw_body_content")
                    or result.get("content")
                    or ""
                )
                content = str(content).replace("\x00", "")[:3500]
                formatted_output += (
                    f"\n\n--- SOURCE {i}: {result.get('title', 'Untitled')} ---\n"
                    f"URL: {url}\n"
                    f"QUERY: {result.get('query', '')}\n\n"
                    f"CONTENT:\n{content}\n"
                    + "\n" + "-" * 80 + "\n"
                )
            return formatted_output

        _tavily_search_no_summarize.metadata = {
            **(_tavily_search_no_summarize.metadata or {}),
            "type": "search",
            "name": "web_search",
        }

        _odr_utils.tavily_search = _tavily_search_no_summarize
    except Exception as e:
        print(f"  warn: langchain-odr tavily no-summary patch failed: {e}", flush=True)

    # GLM can also respond to LangChain's structured-output request with the
    # JSON schema itself, which still fails validation even after accepting
    # {"description": ...}. The brief step is only a prompt-normalization pass,
    # so bypass it and feed the original task into ODR's supervisor directly.
    async def _write_research_brief_direct(state, config):
        configurable = _odr_deep_researcher.Configuration.from_runnable_config(config)
        supervisor_system_prompt = _odr_deep_researcher.lead_researcher_prompt.format(
            date=_odr_deep_researcher.get_today_str(),
            max_concurrent_research_units=configurable.max_concurrent_research_units,
            max_researcher_iterations=configurable.max_researcher_iterations,
        )
        research_brief = intent.strip() or _odr_deep_researcher.get_buffer_string(state.get("messages", []))
        return _odr_deep_researcher.Command(
            goto="research_supervisor",
            update={
                "research_brief": research_brief,
                "supervisor_messages": {
                    "type": "override",
                    "value": [
                        _odr_deep_researcher.SystemMessage(content=supervisor_system_prompt),
                        _odr_deep_researcher.HumanMessage(content=research_brief),
                    ],
                },
            },
        )

    try:
        from langgraph._internal._runnable import coerce_to_runnable as _lg_coerce_to_runnable
        from langgraph.graph._node import StateNodeSpec as _LGStateNodeSpec

        def _replace_graph_node(builder, node_name, func):
            spec = builder.nodes[node_name]
            builder.nodes[node_name] = _LGStateNodeSpec(
                runnable=_lg_coerce_to_runnable(func, name=node_name, trace=False),
                metadata=spec.metadata,
                input_schema=spec.input_schema,
                retry_policy=spec.retry_policy,
                cache_policy=spec.cache_policy,
                ends=spec.ends,
                defer=spec.defer,
            )

        async def _researcher_tools_single_lane(state, config):
            configurable = _odr_deep_researcher.Configuration.from_runnable_config(config)
            researcher_messages = state.get("researcher_messages", [])
            most_recent_message = researcher_messages[-1]
            has_tool_calls = bool(most_recent_message.tool_calls)
            has_native_search = (
                _odr_deep_researcher.openai_websearch_called(most_recent_message)
                or _odr_deep_researcher.anthropic_websearch_called(most_recent_message)
            )
            if not has_tool_calls and not has_native_search:
                return _odr_deep_researcher.Command(goto="compress_research")

            tools = await _odr_deep_researcher.get_all_tools(config)
            tools_by_name = {
                tool.name if hasattr(tool, "name") else tool.get("name", "web_search"): tool
                for tool in tools
            }

            tool_outputs = []
            for tool_call in most_recent_message.tool_calls[:1]:
                observation = await _odr_deep_researcher.execute_tool_safely(
                    tools_by_name[tool_call["name"]],
                    tool_call["args"],
                    config,
                )
                tool_outputs.append(_odr_deep_researcher.ToolMessage(
                    content=observation,
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                ))
            for tool_call in most_recent_message.tool_calls[1:]:
                tool_outputs.append(_odr_deep_researcher.ToolMessage(
                    content="Skipped in this benchmark adapter to keep GLM-4.7-Flash single-lane; continue with one focused tool call at a time.",
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                ))

            exceeded_iterations = state.get("tool_call_iterations", 0) >= configurable.max_react_tool_calls
            research_complete_called = any(
                tool_call["name"] == "ResearchComplete"
                for tool_call in most_recent_message.tool_calls
            )
            if exceeded_iterations or research_complete_called:
                return _odr_deep_researcher.Command(
                    goto="compress_research",
                    update={"researcher_messages": tool_outputs},
                )
            return _odr_deep_researcher.Command(
                goto="researcher",
                update={"researcher_messages": tool_outputs},
            )

        async def _supervisor_tools_single_lane(state, config):
            configurable = _odr_deep_researcher.Configuration.from_runnable_config(config)
            supervisor_messages = state.get("supervisor_messages", [])
            research_iterations = state.get("research_iterations", 0)
            most_recent_message = supervisor_messages[-1]

            exceeded_allowed_iterations = research_iterations > configurable.max_researcher_iterations
            no_tool_calls = not most_recent_message.tool_calls
            research_complete_tool_call = any(
                tool_call["name"] == "ResearchComplete"
                for tool_call in most_recent_message.tool_calls
            )
            if exceeded_allowed_iterations or no_tool_calls or research_complete_tool_call:
                return _odr_deep_researcher.Command(
                    goto=_odr_deep_researcher.END,
                    update={
                        "notes": _odr_deep_researcher.get_notes_from_tool_calls(supervisor_messages),
                        "research_brief": state.get("research_brief", ""),
                    },
                )

            all_tool_messages = []
            update_payload = {"supervisor_messages": []}

            for tool_call in [
                tc for tc in most_recent_message.tool_calls
                if tc["name"] == "think_tool"
            ]:
                all_tool_messages.append(_odr_deep_researcher.ToolMessage(
                    content=f"Reflection recorded: {tool_call['args']['reflection']}",
                    name="think_tool",
                    tool_call_id=tool_call["id"],
                ))

            conduct_research_calls = [
                tc for tc in most_recent_message.tool_calls
                if tc["name"] == "ConductResearch"
            ]
            if conduct_research_calls:
                try:
                    tool_results = []
                    for tool_call in conduct_research_calls[:1]:
                        observation = await _odr_deep_researcher.researcher_subgraph.ainvoke({
                            "researcher_messages": [
                                _odr_deep_researcher.HumanMessage(content=tool_call["args"]["research_topic"])
                            ],
                            "research_topic": tool_call["args"]["research_topic"],
                        }, config)
                        tool_results.append((observation, tool_call))

                    for observation, tool_call in tool_results:
                        all_tool_messages.append(_odr_deep_researcher.ToolMessage(
                            content=observation.get("compressed_research", "Error synthesizing research report: Maximum retries exceeded"),
                            name=tool_call["name"],
                            tool_call_id=tool_call["id"],
                        ))

                    for overflow_call in conduct_research_calls[1:]:
                        all_tool_messages.append(_odr_deep_researcher.ToolMessage(
                            content="Skipped in this benchmark adapter to keep GLM-4.7-Flash single-lane. Continue with the completed research or request one more focused research unit.",
                            name="ConductResearch",
                            tool_call_id=overflow_call["id"],
                        ))

                    raw_notes_concat = "\n".join(
                        "\n".join(observation.get("raw_notes", []))
                        for observation, _tool_call in tool_results
                    )
                    if raw_notes_concat:
                        update_payload["raw_notes"] = [raw_notes_concat]
                except Exception:
                    return _odr_deep_researcher.Command(
                        goto=_odr_deep_researcher.END,
                        update={
                            "notes": _odr_deep_researcher.get_notes_from_tool_calls(supervisor_messages),
                            "research_brief": state.get("research_brief", ""),
                        },
                    )

            update_payload["supervisor_messages"] = all_tool_messages
            return _odr_deep_researcher.Command(goto="supervisor", update=update_payload)

        _replace_graph_node(deep_researcher_builder, "write_research_brief", _write_research_brief_direct)
        _replace_graph_node(_odr_deep_researcher.researcher_builder, "researcher_tools", _researcher_tools_single_lane)
        _odr_deep_researcher.researcher_subgraph = _odr_deep_researcher.researcher_builder.compile()
        _replace_graph_node(_odr_deep_researcher.supervisor_builder, "supervisor_tools", _supervisor_tools_single_lane)
        _odr_deep_researcher.supervisor_subgraph = _odr_deep_researcher.supervisor_builder.compile()
        _replace_graph_node(deep_researcher_builder, "research_supervisor", _odr_deep_researcher.supervisor_subgraph)
    except Exception as e:
        print(f"  warn: langchain-odr single-lane graph patch failed: {e}")

    cfg = {
        "configurable": {
            "research_model":         odr_model,
            "compression_model":      odr_model,
            "final_report_model":     odr_model,
            "summarization_model":    odr_model,
            "writer_model":           odr_model,
            "planner_model":          odr_model,
            "search_api":             "tavily",
            "allow_clarification":    False,
            # GLM-4.7-Flash throttles hard under ODR's default parallel
            # researcher fan-out. Keep this runner single-lane like the outer
            # harness so repair/full queues remain comparable and stable.
            "max_concurrent_research_units": 1,
            "max_researcher_iterations": 3,
            "max_react_tool_calls":   5,
            "research_model_max_tokens": 4096,
            "compression_model_max_tokens": 4096,
            "summarization_model_max_tokens": 2048,
            "final_report_model_max_tokens": 8192,
        }
    }
    research_brief = intent.strip()

    def _apply_odr_update(state, update):
        for key, val in (update or {}).items():
            if isinstance(val, dict) and val.get("type") == "override":
                state[key] = val.get("value", [])
            elif key in {"researcher_messages", "supervisor_messages", "raw_notes", "notes", "messages"}:
                state.setdefault(key, [])
                state[key].extend(val if isinstance(val, list) else [val])
            else:
                state[key] = val

    # Single-lane ODR mode: use ODR's researcher/search/compression/final-writer
    # components directly, but skip the supervisor graph that fan-outs multiple
    # concurrent researchers under tool calling.
    researcher_state = {
        "researcher_messages": [_odr_deep_researcher.HumanMessage(content=research_brief)],
        "research_topic": research_brief,
        "tool_call_iterations": 0,
    }
    max_react = int(cfg["configurable"]["max_react_tool_calls"])
    for _ in range(max_react + 1):
        command = await _odr_deep_researcher.researcher(researcher_state, cfg)
        _apply_odr_update(researcher_state, getattr(command, "update", {}))
        tool_command = await _researcher_tools_single_lane(researcher_state, cfg)
        _apply_odr_update(researcher_state, getattr(tool_command, "update", {}))
        if getattr(tool_command, "goto", None) == "compress_research":
            break

    compressed = await _odr_deep_researcher.compress_research(researcher_state, cfg)
    notes = [compressed.get("compressed_research") or "\n".join(compressed.get("raw_notes", []))]
    result = await _odr_deep_researcher.final_report_generation({
        "messages": [_odr_deep_researcher.HumanMessage(content=intent)],
        "research_brief": research_brief,
        "notes": notes,
    }, cfg)
    final = result.get("final_report") or ""
    if not final and result.get("messages"):
        final = getattr(result["messages"][-1], "content", str(result["messages"][-1]))
    return final or "(empty langchain-odr result)"


async def _run_langchain_odr_fallback(intent: str, model: str) -> str:
    """Stable LangChain-based DR adapter for GLM runs when ODR graph stalls."""
    import re as _re
    import requests as _requests
    from scripts.runners.evidence_fallback import error_stub as _error_stub
    from scripts.runners.evidence_fallback import fallback_enabled as _fallback_enabled
    from scripts.runners.evidence_fallback import is_weak_report as _is_weak_report
    from scripts.runners.evidence_fallback import keep_or_stub as _keep_or_stub
    from scripts.runners.evidence_fallback import synthesize_report as _synthesize_report

    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    api_key = os.environ.get("OPENAI_API_KEY", "anything")
    llm_timeout = float(os.environ.get("LANGCHAIN_ODR_LLM_TIMEOUT_S", "180") or "180")

    def _degrade(phase: str, reason: str) -> str:
        # Fairness rule: even on this debug-only adapter path, a failure must
        # surface as an honest stub in benchmark mode; the evidence writer runs
        # only under the explicit non-benchmark EVIDENCE_FALLBACK_ENABLE flag.
        if _fallback_enabled():
            return _synthesize_report(intent, model, shim, proxy, min_chars=4500, min_urls=5)
        return _error_stub("langchain-odr", phase, reason)

    def _search(query: str, limit: int = 6) -> list[dict]:
        try:
            resp = _requests.post(
                f"{shim}/search",
                json={
                    "query": query,
                    "api_key": os.environ.get("TAVILY_API_KEY", "tvly-shim-fake"),
                    "max_results": limit,
                    "include_raw_content": True,
                },
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            return list((resp.json() or {}).get("results") or [])
        except Exception as e:  # noqa: BLE001
            print(f"  warn: langchain-odr fallback search failed for {query!r}: {e}")
            return []

    compact_intent = " ".join(intent.split())
    keyword_query = _re.sub(r"[^A-Za-z0-9 $%+./-]+", " ", compact_intent)[:220]
    # Fairness audit 2026-07-06: removed the per-domain query-suffix steering
    # ("product price comparison" / "reddit forum discussion" / "wikipedia
    # background" / "buying guide tradeoffs"). The audit flagged that steering
    # as ASYMMETRIC (no other lane receives domain-directed queries). The
    # fallback now issues only the task-derived query, like every other lane.
    queries = [keyword_query]

    unique: dict[str, dict] = {}
    for query in queries:
        for item in _search(query):
            url = str(item.get("url") or "").strip()
            if url and url not in unique:
                unique[url] = {**item, "query": query}
            if len(unique) >= 18:
                break
        if len(unique) >= 18:
            break

    evidence_blocks = []
    for idx, (url, item) in enumerate(unique.items(), 1):
        title = str(item.get("title") or "Untitled").strip()
        content = str(item.get("raw_content") or item.get("content") or "").replace("\x00", " ").strip()
        if len(content) > 1300:
            content = content[:1300] + "..."
        evidence_blocks.append(
            f"Source {idx}\nTitle: {title}\nURL: {url}\nQuery: {item.get('query', '')}\nContent: {content}"
        )
    evidence = "\n\n".join(evidence_blocks) or "No sandbox evidence was returned."

    prompt = f"""You are the LangChain open-deep-research adapter running in a sandbox.

User research brief:
{intent}

Sandbox evidence gathered through the local search shim:
{evidence}

Write the final markdown report directly. Requirements:
- Start with a clear answer to the user's decision/question.
- Use only the sandbox evidence above and clearly separate strong evidence from assumptions.
- Include inline markdown citations using exact URLs copied verbatim from the evidence. Do not invent URLs.
- Include tradeoffs, edge cases, and a concrete recommendation/verdict.
- End with a References section listing cited URLs.
- Do not discuss process details, tool behavior, or implementation details.
"""

    text = ""
    try:
        from langchain_core.messages import HumanMessage as _HumanMessage
        from langchain_openai import ChatOpenAI as _ChatOpenAI

        llm = _ChatOpenAI(
            model=model,
            base_url=proxy,
            api_key=api_key,
            temperature=0.2,
            max_tokens=8192,
            timeout=llm_timeout,
        )
        msg = await asyncio.wait_for(llm.ainvoke([_HumanMessage(content=prompt)]), timeout=llm_timeout + 30)
        text = getattr(msg, "content", str(msg))
    except Exception as e:  # noqa: BLE001
        print(f"  warn: langchain-odr fallback ChatOpenAI failed: {e}")
        try:
            from openai import AsyncOpenAI as _AsyncOpenAI

            client = _AsyncOpenAI(base_url=proxy, api_key=api_key, timeout=llm_timeout)
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=8192,
                ),
                timeout=llm_timeout + 30,
            )
            text = resp.choices[0].message.content or ""
        except Exception as e2:  # noqa: BLE001
            print(f"  warn: langchain-odr direct writer failed: {e2}")
            return _degrade("write", f"{type(e2).__name__}: {e2}")

    if len(text.strip()) < 3000:
        expand_prompt = (
            prompt
            + "\n\nThe previous report was too short. Expand it to at least 4500 characters "
            "while preserving citations and the References section.\n\nPrevious report:\n"
            + text
        )
        try:
            from langchain_core.messages import HumanMessage as _HumanMessage
            from langchain_openai import ChatOpenAI as _ChatOpenAI

            llm = _ChatOpenAI(
                model=model,
                base_url=proxy,
                api_key=api_key,
                temperature=0.2,
                max_tokens=8192,
                timeout=llm_timeout,
            )
            msg = await asyncio.wait_for(llm.ainvoke([_HumanMessage(content=expand_prompt)]), timeout=llm_timeout + 30)
            text = getattr(msg, "content", str(msg))
        except Exception:
            pass
    text = str(text).strip()
    if _is_weak_report(text, min_chars=3000, min_urls=3):
        if _fallback_enabled():
            return _degrade("write", "fallback writer report weak/under-threshold")
        # Weak-but-real writer output: save it verbatim (the scorer judges
        # quality); stub only genuinely empty/stub output.
        return _keep_or_stub(
            "langchain-odr", "write", "fallback writer report weak/under-threshold", text
        )
    return text


async def _run_langchain_odr(intent: str, model: str) -> str:
    # Fairness audit 2026-07-06 (binding user decision): langchain-odr must
    # benchmark the REAL open_deep_research langgraph, never a hand-rolled
    # writer. The former default inverted this: it ran `_run_langchain_odr_fallback`
    # (a bespoke evidence+writer) and only touched the framework under
    # LANGCHAIN_ODR_FORCE_GRAPH=1 behind a 240s timeout that silently masked
    # graph failures. We invert that:
    #   - The open_deep_research graph is the ONLY benchmark path.
    #   - Its timeout is raised to 1500s so a slow-but-real run is not masked.
    #   - On ANY graph failure we return an honest error stub instead of
    #     silently substituting the hand-rolled writer.
    #   - The hand-rolled writer stays reachable ONLY under an explicit
    #     LANGCHAIN_ODR_ALLOW_FALLBACK=1 for NON-BENCHMARK debugging use.
    if os.environ.get("LANGCHAIN_ODR_ALLOW_FALLBACK") == "1":
        # NON-BENCHMARK path: hand-rolled writer for local debugging only.
        # Never enable this for a scored/leaderboard run.
        timeout_s = int(os.environ.get("LANGCHAIN_ODR_FALLBACK_TIMEOUT_S", "600") or "600")
        try:
            return await asyncio.wait_for(_run_langchain_odr_fallback(intent, model), timeout=timeout_s)
        except Exception as e:  # noqa: BLE001
            return f"(langchain-odr error: fallback failed: {type(e).__name__}: {e})"
    timeout_s = int(os.environ.get("LANGCHAIN_ODR_GRAPH_TIMEOUT_S", "1500") or "1500")
    allow_benchmark_fallback = os.environ.get(
        "LANGCHAIN_ODR_BENCHMARK_FALLBACK", ""
    ).strip().lower() in {"1", "true", "yes", "on"}
    if allow_benchmark_fallback:
        from scripts.runners.evidence_fallback import error_stub as _error_stub
        from scripts.runners.evidence_fallback import fallback_enabled as _fallback_enabled
        from scripts.runners.evidence_fallback import is_weak_report as _is_weak_report
        from scripts.runners.evidence_fallback import keep_or_stub as _keep_or_stub
        from scripts.runners.evidence_fallback import synthesize_report as _synthesize_report

        shim = os.environ.get("SHIM_URL", "http://localhost:8081")
        proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")

        async def _benchmark_fallback(phase: str, reason: str) -> str:
            # Fairness rule: the evidence writer runs only under the explicit
            # non-benchmark EVIDENCE_FALLBACK_ENABLE flag; in benchmark mode a
            # failure surfaces as an honest per-lane error stub instead.
            if _fallback_enabled():
                return await asyncio.to_thread(
                    _synthesize_report, intent, model, shim, proxy, min_chars=4500, min_urls=5
                )
            return _error_stub("langchain-odr", phase, reason)

    try:
        text = await asyncio.wait_for(_run_langchain_odr_graph(intent, model), timeout=timeout_s)
        if allow_benchmark_fallback and _is_weak_report(text, min_chars=3000, min_urls=3):
            if _fallback_enabled():
                return await _benchmark_fallback("write", "graph report weak/under-threshold")
            # Weak-but-real graph output: save it verbatim (the scorer judges
            # quality); stub only genuinely empty/stub output.
            return _keep_or_stub(
                "langchain-odr", "write", "graph report weak/under-threshold", text
            )
        return text
    except asyncio.TimeoutError:
        if allow_benchmark_fallback:
            print(f"langchain-odr graph exceeded {timeout_s}s")
            return await _benchmark_fallback(
                "timeout", f"open_deep_research graph timeout after {timeout_s}s"
            )
        return f"(langchain-odr error: open_deep_research graph timeout after {timeout_s}s)"
    except Exception as e:  # noqa: BLE001
        if allow_benchmark_fallback:
            print(f"  warn: langchain-odr graph failed: {e}")
            return await _benchmark_fallback("native", f"{type(e).__name__}: {e}")
        return f"(langchain-odr error: {type(e).__name__}: {e})"


async def _run_deerflow(intent: str, model: str, *, strict_sandbox: bool = False) -> str:
    """DeerFlow via clean runner module:uses native env vars + conf.yaml.

    Forwards `strict_sandbox` so deerflow_runner.run() arms the in-driver HTTP
    gate (_STRICT block). Without this the gate is never armed and a closed-book
    run would be silently downgraded to best-effort shim-only.
    """
    from scripts.runners.deerflow_runner import run as deerflow_run
    from scripts.runners.evidence_fallback import (
        error_stub,
        fallback_enabled,
        is_weak_report,
        keep_or_stub,
        synthesize_report,
    )
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    timeout_s = int(os.environ.get("DEERFLOW_NATIVE_TIMEOUT_S", "1800") or "1800")
    text = await deerflow_run(
        intent=intent, model=model, shim_url=shim, proxy_url=proxy,
        strict_sandbox=strict_sandbox, timeout_s=timeout_s,
    )
    lowered = str(text or "").strip().lower()
    if (
        is_weak_report(text, min_chars=3000, min_urls=3)
        or lowered.startswith("(deerflow")
        or "timeout after" in lowered
    ):
        # Fairness rule: a deerflow failure must surface as the framework's own
        # (missing) output, never as a harness-ghostwritten report. The evidence
        # writer runs only under the explicit non-benchmark
        # EVIDENCE_FALLBACK_ENABLE flag.
        if fallback_enabled():
            print(f"deerflow native path weak/timeout after {timeout_s}s; using source-grounded writer")
            return await asyncio.to_thread(
                synthesize_report, intent, model, shim, proxy, min_chars=4500, min_urls=5
            )
        if lowered.startswith("(deerflow"):
            # Already deerflow's own honest stub; pass it through unchanged.
            return text
        if "timeout after" in lowered:
            # A timeout marker is a genuine failure, not a weak report.
            return error_stub("deerflow", "native", f"native path weak/timeout after {timeout_s}s")
        # Weak-but-real output is deerflow's own report: save it verbatim (the
        # scorer judges quality); stub only genuinely empty/stub output.
        return keep_or_stub("deerflow", "native", "native report weak/under-threshold", text)
    return text


async def _run_deerflow_OLD(intent: str, model: str) -> str:
    """DeerFlow runs in own venv at third_party/deer-flow-v1/.venv via subprocess.

    FIX #12 (URL hallucination): DeerFlow's search correctly returns sandbox
    URLs (HTTP intercept works -- 106 sandbox-format URLs found), but the
    reporter LLM fabricates similar-looking URLs instead of copying exact ones.
    Two-pronged fix:
      1. Stronger prompt: explicit URL-fidelity instructions injected via the
         driver script (in deerflow_patch.py).
      2. Post-processing: after graph.ainvoke(), collect all ground-truth URLs
         from search/crawl tool results, then scan the report for hallucinated
         URLs and replace them with the closest matching real URL.
    """
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    deerflow_root = ROOT / "third_party" / "deer-flow-v1"
    deerflow_python = deerflow_root / ".venv" / "bin" / "python"
    if not deerflow_python.exists():
        return f"(deerflow: missing venv at {deerflow_python})"
    sites_block = (
        "  - Shopping (Magento): http://localhost:7770\n"
        "  - Reddit (Postmill): http://localhost:9999\n"
        "  - Wikipedia (Kiwix): http://localhost:8090"
    )
    prompt = f"{intent}\n\n## Available sandbox sites:\n{sites_block}\n\nUse Tavily search and crawl_tool aggressively across all 3 sites. Cite >=60 distinct sandbox URLs as markdown links."
    env = os.environ.copy()
    env["TAVILY_API_KEY"] = "tvly-shim-fake"
    env["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "anything")
    env["OPENAI_BASE_URL"] = proxy
    env["BASIC_MODEL__BASE_URL"] = proxy
    env["BASIC_MODEL__MODEL"] = model
    env["BASIC_MODEL__API_KEY"] = env["OPENAI_API_KEY"]
    env["DEERFLOW_QUERY"] = prompt
    # FIX #3+#10: Remove ALL proxy env vars.  DeerFlow's
    # EnhancedTavilySearchAPIWrapper.raw_results_async() creates
    # aiohttp.ClientSession(trust_env=True) which reads proxy settings from the
    # process environment.  WSL's /etc/environment has proxy vars that cause
    # requests to route through Mihomo to the real Tavily API (rejecting our
    # fake key).  The intercept preamble also purges them at process level as
    # belt-and-suspenders, and forces trust_env=False on aiohttp sessions.
    for _pvar in list(env):
        if _pvar.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'ftp_proxy'):
            env.pop(_pvar, None)
    env["NO_PROXY"] = "*"
    # deerflow's researcher tool spawns `uvx` -- ensure it's on PATH
    env["PATH"] = f"{deerflow_root}/.venv/bin:/usr/local/bin:" + env.get("PATH", "")
    # FIX #3+#9+#10+#12: The driver installs HTTP-level intercept that catches
    # ALL outgoing requests at the transport layer, AND post-processes the
    # report to replace hallucinated URLs with real ones from search results.
    # See scripts/patches/deerflow_patch.py for the full driver logic.
    from scripts.patches.deerflow_patch import build_deerflow_driver
    driver = ROOT / "scripts" / "_deerflow_driver.py"
    driver.write_text(build_deerflow_driver(shim, _build_intercept_preamble(shim)))
    cmd = [str(deerflow_python), str(driver)]
    import subprocess
    try:
        proc = subprocess.run(cmd, cwd=str(deerflow_root), env=env, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return "(deerflow: timeout 600s)"
    out = proc.stdout
    if "===REPORT===" in out:
        return out.split("===REPORT===", 1)[1].strip()
    return f"(deerflow stderr: {proc.stderr[-500:]})"


async def _run_ldr(intent: str, model: str) -> str:
    """LDR via clean runner module:intent sanitization + LDR official API."""
    from scripts.runners.ldr_runner import run as ldr_run
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await ldr_run(intent=intent, model=model, shim_url=shim, proxy_url=proxy)


async def _run_ldr_OLD(intent: str, model: str) -> str:
    """LearningCircuit/local-deep-research via subprocess in .venv-ldr312."""
    import re as _re
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    ldr_python = ROOT / ".venv-ldr312" / "bin" / "python"
    if not ldr_python.exists():
        return f"(ldr: missing venv at {ldr_python})"

    # FIX #11: Strip ALL localhost URLs from the intent before passing to LDR.
    # DeepSeek V4 flash refuses to write reports that mention localhost URLs
    # (triggers safety filter: "I cannot complete this request...").
    # LDR has its own search engine (shimmed to Tavily->sandbox), so it will
    # discover sandbox URLs on its own. We only need the topic description.
    #
    # Strategy: remove `http://localhost:XXXX` and backtick-quoted references
    # like `__SHOPPING__`, replace with human-readable placeholders that don't
    # trigger the safety filter.
    ldr_intent = intent
    # Replace specific sandbox URL patterns with neutral descriptions
    _url_to_desc = {
        r"http://localhost:7770[^\s)\]]*": "the product catalog",
        r"http://localhost:9999[^\s)\]]*": "the discussion forum",
        r"http://localhost:8090[^\s)\]]*": "the encyclopedia",
    }
    for pattern, desc in _url_to_desc.items():
        ldr_intent = _re.sub(pattern, desc, ldr_intent)
    # Also strip any remaining localhost URLs (e.g. other ports)
    ldr_intent = _re.sub(r'http://localhost:\d+[^\s)\]]*', '', ldr_intent)
    # Remove backtick-quoted sandbox placeholders like (`__SHOPPING__`)
    ldr_intent = _re.sub(r'\(`?__\w+__`?\)', '', ldr_intent)
    # Remove bare __SHOPPING__ etc. placeholders
    ldr_intent = _re.sub(r'`?__(?:SHOPPING|REDDIT|WIKIPEDIA)__`?', '', ldr_intent)
    # Remove "Source URLs MUST be sandbox-local" and similar directives that
    # confuse the model about sandbox/localhost context
    ldr_intent = _re.sub(r'Source URLs MUST be sandbox-local\.?\s*', '', ldr_intent)
    ldr_intent = _re.sub(r'Do not fabricate URLs[^.]*\.?\s*', '', ldr_intent)
    # Clean up double spaces and orphaned parentheses
    ldr_intent = _re.sub(r'\(\s*\)', '', ldr_intent)
    ldr_intent = _re.sub(r'  +', ' ', ldr_intent)

    env = os.environ.copy()
    env["TAVILY_API_KEY"] = "tvly-shim-fake"
    env["LDR_LLM_PROVIDER"] = "openai_endpoint"
    env["LDR_LLM_MODEL"] = model
    env["LDR_LLM_OPENAI_ENDPOINT_URL"] = proxy
    env["LDR_LLM_OPENAI_ENDPOINT_API_KEY"] = os.environ.get("OPENAI_API_KEY", "anything")
    env["LDR_SEARCH_TOOL"] = "tavily"
    env["LDR_SEARCH_ENGINE_WEB_TAVILY_API_KEY"] = "tvly-shim-fake"
    env["OPENAI_BASE_URL"] = proxy
    env["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "anything")
    env["LDR_QUERY"] = ldr_intent
    env["LDR_SHIM"] = shim
    # Remove HTTP proxy so LDR can only reach localhost services
    env.pop("HTTP_PROXY", None)
    env.pop("HTTPS_PROXY", None)
    env.pop("http_proxy", None)
    env.pop("https_proxy", None)
    env["NO_PROXY"] = "*"

    # FIX #11 + #13: LDR driver with HTTP-level intercept AND localhost-masking.
    # The intercept catches any raw HTTP calls to api.tavily.com.
    # The localhost-masking replaces localhost:PORT with .internal domains in
    # all text that flows to the LLM, preventing DeepSeek's safety refusal.
    # After the final report is generated, we reverse the replacement.
    driver = ROOT / "scripts" / "_ldr_driver.py"
    driver.write_text(_build_intercept_preamble(shim) +
        "import os, sys, re\n"
        "shim = os.environ['LDR_SHIM']\n"
        "\n"
        "# ================================================================\n"
        "# FIX #13: Localhost-masking for DeepSeek V4 safety filter bypass.\n"
        "# DeepSeek refuses when it sees 'localhost' URLs in context.\n"
        "# We intercept the LLM call layer to mask localhost -> .internal\n"
        "# in prompts, then unmask in responses.\n"
        "# ================================================================\n"
        "_MASK_MAP = {\n"
        "    'http://localhost:7770': 'http://shop.internal',\n"
        "    'http://localhost:9999': 'http://forum.internal',\n"
        "    'http://localhost:8090': 'http://wiki.internal',\n"
        "    'http://localhost:8081': 'http://search.internal',\n"
        "    'localhost:7770': 'shop.internal',\n"
        "    'localhost:9999': 'forum.internal',\n"
        "    'localhost:8090': 'wiki.internal',\n"
        "    'localhost:8081': 'search.internal',\n"
        "}\n"
        "_UNMASK_MAP = {v: k for k, v in _MASK_MAP.items()}\n"
        "\n"
        "def _mask_localhost(text):\n"
        "    '''Replace localhost:PORT with .internal domains.'''\n"
        "    if not isinstance(text, str):\n"
        "        return text\n"
        "    for old, new in _MASK_MAP.items():\n"
        "        text = text.replace(old, new)\n"
        "    # Catch any remaining localhost references with other ports\n"
        "    text = re.sub(r'localhost:(\\d+)', r'sandbox-\\1.internal', text)\n"
        "    return text\n"
        "\n"
        "def _unmask_localhost(text):\n"
        "    '''Reverse .internal domains back to localhost:PORT.'''\n"
        "    if not isinstance(text, str):\n"
        "        return text\n"
        "    for masked, original in _UNMASK_MAP.items():\n"
        "        text = text.replace(masked, original)\n"
        "    # Reverse the catch-all pattern\n"
        "    text = re.sub(r'sandbox-(\\d+)\\.internal', r'localhost:\\1', text)\n"
        "    return text\n"
        "\n"
        "# Monkey-patch httpx to mask/unmask localhost in LLM API calls.\n"
        "try:\n"
        "    import httpx as _hx\n"
        "    import json as _json\n"
        "    _orig_hx_send = _hx.Client.send\n"
        "    def _masked_hx_send(self, request, **kw):\n"
        "        url_str = str(request.url)\n"
        "        if '/chat/completions' in url_str or '/completions' in url_str:\n"
        "            try:\n"
        "                body = _json.loads(request.content)\n"
        "                modified = False\n"
        "                if 'messages' in body:\n"
        "                    for msg in body['messages']:\n"
        "                        if isinstance(msg.get('content'), str):\n"
        "                            masked = _mask_localhost(msg['content'])\n"
        "                            if masked != msg['content']:\n"
        "                                msg['content'] = masked\n"
        "                                modified = True\n"
        "                        elif isinstance(msg.get('content'), list):\n"
        "                            for part in msg['content']:\n"
        "                                if isinstance(part, dict) and isinstance(part.get('text'), str):\n"
        "                                    masked = _mask_localhost(part['text'])\n"
        "                                    if masked != part['text']:\n"
        "                                        part['text'] = masked\n"
        "                                        modified = True\n"
        "                if modified:\n"
        "                    new_content = _json.dumps(body).encode('utf-8')\n"
        "                    request = _hx.Request(\n"
        "                        method=request.method,\n"
        "                        url=request.url,\n"
        "                        headers=dict(request.headers),\n"
        "                        content=new_content,\n"
        "                    )\n"
        "                    request.headers['content-length'] = str(len(new_content))\n"
        "                    print('[ldr-mask] Masked localhost refs in LLM request')\n"
        "            except Exception as e:\n"
        "                print(f'[ldr-mask] warn: mask failed: {e}')\n"
        "        resp = _orig_hx_send(self, request, **kw)\n"
        "        if '/chat/completions' in url_str or '/completions' in url_str:\n"
        "            try:\n"
        "                rdata = _json.loads(resp.content)\n"
        "                rtext = _json.dumps(rdata)\n"
        "                unmasked = _unmask_localhost(rtext)\n"
        "                if unmasked != rtext:\n"
        "                    new_resp = _hx.Response(\n"
        "                        status_code=resp.status_code,\n"
        "                        headers=dict(resp.headers),\n"
        "                        content=unmasked.encode('utf-8'),\n"
        "                        request=resp.request,\n"
        "                    )\n"
        "                    print('[ldr-mask] Unmasked .internal refs in LLM response')\n"
        "                    return new_resp\n"
        "            except Exception:\n"
        "                pass\n"
        "        return resp\n"
        "    _hx.Client.send = _masked_hx_send\n"
        "    print('[ldr-mask] httpx.Client.send patched for localhost masking')\n"
        "except ImportError:\n"
        "    print('[ldr-mask] httpx not available')\n"
        "\n"
        "# Also patch async httpx for async LLM calls\n"
        "try:\n"
        "    import httpx as _hx\n"
        "    import json as _json\n"
        "    _orig_hx_async_send = _hx.AsyncClient.send\n"
        "    async def _masked_hx_async_send(self, request, **kw):\n"
        "        url_str = str(request.url)\n"
        "        if '/chat/completions' in url_str or '/completions' in url_str:\n"
        "            try:\n"
        "                body = _json.loads(request.content)\n"
        "                modified = False\n"
        "                if 'messages' in body:\n"
        "                    for msg in body['messages']:\n"
        "                        if isinstance(msg.get('content'), str):\n"
        "                            masked = _mask_localhost(msg['content'])\n"
        "                            if masked != msg['content']:\n"
        "                                msg['content'] = masked\n"
        "                                modified = True\n"
        "                        elif isinstance(msg.get('content'), list):\n"
        "                            for part in msg['content']:\n"
        "                                if isinstance(part, dict) and isinstance(part.get('text'), str):\n"
        "                                    masked = _mask_localhost(part['text'])\n"
        "                                    if masked != part['text']:\n"
        "                                        part['text'] = masked\n"
        "                                        modified = True\n"
        "                if modified:\n"
        "                    new_content = _json.dumps(body).encode('utf-8')\n"
        "                    request = _hx.Request(\n"
        "                        method=request.method,\n"
        "                        url=request.url,\n"
        "                        headers=dict(request.headers),\n"
        "                        content=new_content,\n"
        "                    )\n"
        "                    request.headers['content-length'] = str(len(new_content))\n"
        "                    print('[ldr-mask] Masked localhost refs in async LLM request')\n"
        "            except Exception as e:\n"
        "                print(f'[ldr-mask] warn: async mask failed: {e}')\n"
        "        resp = await _orig_hx_async_send(self, request, **kw)\n"
        "        if '/chat/completions' in url_str or '/completions' in url_str:\n"
        "            try:\n"
        "                rdata = _json.loads(resp.content)\n"
        "                rtext = _json.dumps(rdata)\n"
        "                unmasked = _unmask_localhost(rtext)\n"
        "                if unmasked != rtext:\n"
        "                    new_resp = _hx.Response(\n"
        "                        status_code=resp.status_code,\n"
        "                        headers=dict(resp.headers),\n"
        "                        content=unmasked.encode('utf-8'),\n"
        "                        request=resp.request,\n"
        "                    )\n"
        "                    print('[ldr-mask] Unmasked .internal refs in async LLM response')\n"
        "                    return new_resp\n"
        "            except Exception:\n"
        "                pass\n"
        "        return resp\n"
        "    _hx.AsyncClient.send = _masked_hx_async_send\n"
        "    print('[ldr-mask] httpx.AsyncClient.send patched for localhost masking')\n"
        "except ImportError:\n"
        "    pass\n"
        "\n"
        "# Patch LDR's own TavilySearchEngine as belt-and-suspenders\n"
        "try:\n"
        "    from local_deep_research.web_search_engines.engines.search_engine_tavily import TavilySearchEngine as _LdrTavily\n"
        "    _orig_ldr = _LdrTavily.__init__\n"
        "    def _ldr_init(self, *a, **kw):\n"
        "        _orig_ldr(self, *a, **kw)\n"
        "        self.base_url = shim\n"
        "    _LdrTavily.__init__ = _ldr_init\n"
        "except Exception as e:\n"
        "    print('warn: LDR TavilySearchEngine patch:', e)\n"
        "from local_deep_research.api import detailed_research\n"
        "result = detailed_research(\n"
        "    query=os.environ['LDR_QUERY'],\n"
        "    provider='openai_endpoint',\n"
        "    api_key=os.environ.get('OPENAI_API_KEY', 'anything'),\n"
        "    temperature=0.2,\n"
        ")\n"
        "if isinstance(result, dict):\n"
        "    out = result.get('final_report') or result.get('report') or result.get('summary') or str(result)[:30000]\n"
        "else:\n"
        "    out = str(result)\n"
        "# Final unmask pass on the output\n"
        "out = _unmask_localhost(out)\n"
        "print('===REPORT===')\n"
        "print(out)\n"
    )
    cmd = [str(ldr_python), str(driver)]
    import subprocess
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=1500)
    except subprocess.TimeoutExpired:
        return "(ldr: timeout 1500s)"
    if "===REPORT===" in proc.stdout:
        report = proc.stdout.split("===REPORT===", 1)[1].strip()
        # Belt-and-suspenders: unmask any .internal domains that survived
        report = report.replace("http://shop.internal", "http://localhost:7770")
        report = report.replace("http://forum.internal", "http://localhost:9999")
        report = report.replace("http://wiki.internal", "http://localhost:8090")
        report = report.replace("http://search.internal", "http://localhost:8081")
        report = report.replace("shop.internal", "localhost:7770")
        report = report.replace("forum.internal", "localhost:9999")
        report = report.replace("wiki.internal", "localhost:8090")
        report = report.replace("search.internal", "localhost:8081")
        report = _re.sub(r'sandbox-(\d+)\.internal', r'localhost:\1', report)
        return report
    return f"(ldr: no report marker. stderr: {proc.stderr[-500:]})"


async def _run_ii_researcher(intent: str, model: str) -> str:
    """Intelligent-Internet/ii-researcher via subprocess in .venv-ii."""
    from scripts.runners.evidence_fallback import (
        error_stub,
        fallback_enabled,
        is_weak_report,
        keep_or_stub,
        synthesize_report,
    )

    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    ii_root = ROOT / "third_party" / "ii-researcher"
    ii_python = ROOT / ".venv-ii" / "bin" / "python"
    if not ii_python.exists():
        return f"(ii: missing venv at {ii_python})"
    if not ii_root.exists():
        return f"(ii: missing repo at {ii_root})"

    env = os.environ.copy()
    env["OPENAI_BASE_URL"] = proxy
    env["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "anything")
    env["TAVILY_API_KEY"] = "tvly-shim-fake"
    env["R_MODEL"] = model
    env["R_REPORT_MODEL"] = model
    env["REPORT_MODEL"] = model
    env["II_QUERY"] = intent
    env["II_SHIM"] = shim
    # FIX #10: Force SEARCH_PROVIDER=tavily so ii-researcher uses TavilyClient
    # (which goes through our shim) instead of the default "serpapi" (which hits
    # serpapi.com and is NOT intercepted by our monkey-patch).
    env["SEARCH_PROVIDER"] = "tavily"
    # Use BeautifulSoup scraper for page_visit so it goes through requests.Session
    # (intercepted for Wikipedia URL rewriting) instead of firecrawl/jina.
    env["SCRAPER_PROVIDER"] = "bs"
    # FIX #6: Remove external proxies so ii-researcher can only reach localhost.
    env.pop("HTTP_PROXY", None)
    env.pop("HTTPS_PROXY", None)
    env.pop("http_proxy", None)
    env.pop("https_proxy", None)
    env["NO_PROXY"] = "*"

    # FIX #6+#9+#10: Robust driver with HTTP-level intercept + TavilyClient patch.
    # The intercept preamble patches requests/aiohttp/httpx at transport layer so
    # ii-researcher's search calls to api.tavily.com are caught regardless of
    # whether it uses TavilyClient, AsyncTavilyClient, or raw HTTP.
    # Additionally, we directly patch TavilyClient.__init__ to set base_url to
    # shim as belt-and-suspenders.
    driver = ROOT / "scripts" / "_ii_driver.py"
    driver.write_text(_build_intercept_preamble(shim) +
        "import os, sys, asyncio, traceback, re, json\n"
        "sys.path.insert(0, '.')\n"
        "shim = os.environ['II_SHIM']\n"
        "# Search-result URLs collected for DIAGNOSTICS ONLY (never written into\n"
        "# the report; see fairness audit 2026-07-06 B1)\n"
        "_collected_urls = []\n"
        "# Patch TavilyClient to redirect base_url to shim AND collect result URLs\n"
        "try:\n"
        "    import tavily\n"
        "    _orig_tavily_init = tavily.TavilyClient.__init__\n"
        "    def _patched_tavily_init(self, api_key=None, *a, **kw):\n"
        "        kw.pop('api_base_url', None)\n"
        "        _orig_tavily_init(self, api_key, *a, **kw)\n"
        "        self.base_url = shim\n"
        "        print(f'[ii-fix] TavilyClient.base_url -> {shim}')\n"
        "    tavily.TavilyClient.__init__ = _patched_tavily_init\n"
        "    # Also patch search method to collect URLs\n"
        "    if hasattr(tavily.TavilyClient, 'search'):\n"
        "        _orig_search = tavily.TavilyClient.search\n"
        "        def _patched_search(self, *a, **kw):\n"
        "            result = _orig_search(self, *a, **kw)\n"
        "            if isinstance(result, dict) and 'results' in result:\n"
        "                for r in result['results']:\n"
        "                    if 'url' in r:\n"
        "                        _collected_urls.append({'url': r['url'], 'title': r.get('title',''), 'content': r.get('content','')[:200]})\n"
        "            return result\n"
        "        tavily.TavilyClient.search = _patched_search\n"
        "except Exception as e:\n"
        "    print(f'[ii-fix] warn: tavily patch failed: {e}')\n"
        "try:\n"
        "    from ii_researcher.reasoning.agent import ReasoningAgent\n"
        "    from ii_researcher.reasoning.builders.report import ReportType\n"
        "    agent = ReasoningAgent(question=os.environ['II_QUERY'], report_type=ReportType.BASIC)\n"
        "    result = asyncio.run(agent.run(is_stream=False))\n"
        "    if isinstance(result, dict):\n"
        "        out = result.get('final_report') or result.get('answer') or str(result)[:30000]\n"
        "    else:\n"
        "        out = str(result)\n"
        "    # Fairness audit 2026-07-06 (B1): the former post-processing step\n"
        "    # that grafted collected wiki URLs onto bare title mentions was\n"
        "    # removed. The saved report must be the framework's own output;\n"
        "    # harness-injected citations manufacture grounding the agent\n"
        "    # never performed.\n"
        "    print('===REPORT===')\n"
        "    print(out)\n"
        "except Exception as e:\n"
        "    print('===REPORT===')\n"
        "    print(f'(ii-researcher error: {type(e).__name__}: {e})')\n"
        "    traceback.print_exc()\n"
    )
    cmd = [str(ii_python), str(driver)]
    import subprocess
    timeout_s = int(os.environ.get("II_RESEARCHER_NATIVE_TIMEOUT_S", "1500") or "1500")

    async def _fallback_report() -> str:
        return await asyncio.to_thread(
            synthesize_report, intent, model, shim, proxy, min_chars=4500, min_urls=5
        )

    async def _degrade(phase: str, reason: str) -> str:
        # Fairness rule: an ii-researcher failure must surface as the
        # framework's own (missing) output, never as a harness-ghostwritten
        # report. In benchmark mode we save an honest error stub; the evidence
        # writer runs only under the explicit non-benchmark
        # EVIDENCE_FALLBACK_ENABLE flag.
        if fallback_enabled():
            return await _fallback_report()
        return error_stub("ii-researcher", phase, reason)

    try:
        proc = subprocess.run(cmd, cwd=str(ii_root), env=env, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        print(f"ii-researcher native path exceeded {timeout_s}s")
        return await _degrade("native", f"native path exceeded {timeout_s}s timeout")
    if "===REPORT===" in proc.stdout:
        report = proc.stdout.split("===REPORT===", 1)[1].strip()
        if not is_weak_report(report, min_chars=3000, min_urls=3):
            return report
        print("ii-researcher native report weak")
        if fallback_enabled():
            return await _degrade("write", "native report weak/under-threshold")
        # Weak-but-real output is ii-researcher's own report: save it verbatim
        # (the scorer judges quality); stub only genuinely empty/stub output.
        return keep_or_stub("ii-researcher", "write", "native report weak/under-threshold", report)
    print("ii-researcher native path produced no report marker")
    return await _degrade("native", "native path produced no report marker")


async def _run_qx_agents(intent: str, model: str) -> str:
    """qx-labs/agents-deep-research via the clean runner module.

    Delegates to scripts/runners/qx_runner which uses:
      - SearchXNG provider (native env-var config, no monkey-patching)
      - A local SerperAdapter that translates SearchXNG wire format
        to our Tavily shim
      - SDK-level DEFAULT_MAX_TURNS set before import (not runtime patch)
    """
    from scripts.runners.qx_runner import run as qx_run
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await qx_run(
        intent=intent,
        model=model,
        shim_url=shim,
        proxy_url=proxy,
    )


async def _run_flowsearcher_ds(intent: str, model: str) -> str:
    """FlowSearcher-DS: memory-guided deep research agent."""
    from scripts.runners.evidence_fallback import (
        error_stub,
        fallback_enabled,
        is_weak_report,
        keep_or_stub,
        synthesize_report,
    )

    task_id = os.environ.get("_FLOWSEARCHER_TASK_ID", "")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")

    async def _fallback_report() -> str:
        return await asyncio.to_thread(
            synthesize_report, intent, model, shim, proxy, min_chars=4500, min_urls=5
        )

    async def _degrade(phase: str, reason: str) -> str:
        # Fairness rule: a flowsearcher failure must surface as an honest stub,
        # never a harness-ghostwritten report. The evidence writer runs only
        # under the explicit non-benchmark EVIDENCE_FALLBACK_ENABLE flag.
        if fallback_enabled():
            return await _fallback_report()
        return error_stub("flowsearcher", phase, reason)

    # Default OFF: run the real flowsearcher adapter as the benchmark path.
    # When the operator explicitly sets FLOWSEARCHER_FORCE_FALLBACK, treat that
    # as opt-in authorization to use the shared evidence writer for completion
    # runs instead of returning a short error stub.
    force_fallback = os.environ.get("FLOWSEARCHER_FORCE_FALLBACK", "0").strip().lower()
    if force_fallback not in {"0", "false", "no", "native"}:
        return await _fallback_report()

    from scripts.run_flowsearcher import run_flowsearcher

    try:
        native_timeout = float(os.environ.get("FLOWSEARCHER_NATIVE_TIMEOUT_S", "900") or "900")
    except ValueError:
        native_timeout = 900.0

    try:
        report = await asyncio.wait_for(
            run_flowsearcher(intent, model, task_id=task_id,
                             shim_url=shim, proxy_url=proxy),
            timeout=max(60.0, native_timeout),
        )
    except asyncio.TimeoutError:
        return await _degrade("native", f"native path exceeded {native_timeout}s timeout")
    except Exception as e:
        return await _degrade("native", f"{type(e).__name__}: {e}")

    # run_flowsearcher already returns its own honest "(flowsearcher error: ...)"
    # stub on internal failure; pass those through unchanged rather than masking
    # them with the evidence writer.
    from src.eval.report_stubs import classify_report as _classify_report

    if _classify_report(report) != "ok":
        return report
    if (
        "LLM writer failed after retries" in report
        or is_weak_report(report, min_chars=3000, min_urls=3)
    ):
        if fallback_enabled():
            return await _degrade("write", "native report weak/under-threshold")
        # Weak-but-real output is flowsearcher's own report: save it verbatim
        # (the scorer judges quality); stub only genuinely empty/stub output.
        return keep_or_stub("flowsearcher", "write", "native report weak/under-threshold", report)
    return report


async def _run_dzhng(intent: str, model: str) -> str:
    """dzhng/deep-research via Node HTTP API on :3051 (Firecrawl-compat shim)."""
    import requests
    api_url = os.environ.get("DZHNG_API_URL", "http://localhost:3051/api/generate-report")
    try:
        r = requests.post(api_url, json={
            "query": intent,
            "breadth": int(os.environ.get("DZHNG_BREADTH", "2")),
            "depth": int(os.environ.get("DZHNG_DEPTH", "2")),
        }, timeout=1800)
        if r.status_code >= 400:
            return f"(dzhng HTTP {r.status_code}: {r.text[:500]})"
        data = r.json()
        if isinstance(data, dict):
            return data.get("report") or data.get("output") or str(data)[:30000]
        return str(data)
    except requests.exceptions.ConnectionError:
        return "(dzhng: API server :3051 not running. Start: cd third_party/deep-research && npm run api)"
    except Exception as e:
        return f"(dzhng error: {type(e).__name__}: {e})"


async def _run_tongyi_dr(intent: str, model: str) -> str:
    """Tongyi DeepResearch (Alibaba-NLP) via clean runner module.

    Reimplements the ReAct loop from react_agent.py with sandbox-compatible
    tools: search via shim, visit via direct fetch + LLM summarization,
    LLM via ds_proxy.  No local model needed.
    """
    from scripts.runners.tongyi_runner import run as tongyi_run
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await tongyi_run(intent=intent, model=model, shim_url=shim, proxy_url=proxy)


async def _run_costorm(intent: str, model: str) -> str:
    """Co-STORM (Stanford) via clean runner module:collaborative multi-perspective research."""
    from scripts.runners.costorm_runner import run as costorm_run
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await costorm_run(intent=intent, model=model, shim_url=shim, proxy_url=proxy)


async def _run_deepagents(intent: str, model: str) -> str:
    """LangChain DeepAgents via clean runner module:LangGraph super-agent."""
    from scripts.runners.deepagents_runner import run as deepagents_run
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await deepagents_run(intent=intent, model=model, shim_url=shim, proxy_url=proxy)


async def _run_local_deep_researcher(intent: str, model: str) -> str:
    """LangChain local-deep-researcher via clean runner module."""
    from scripts.runners.local_deep_researcher_runner import run as lcdr_run
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await lcdr_run(intent=intent, model=model, shim_url=shim, proxy_url=proxy)


# Manually-wired agents — these need bespoke env-var setup beyond the standard
# (intent, model, shim_url, proxy_url) contract (e.g. gpt-researcher's
# FAST_LLM/SMART_LLM split, camel-ai's tool registration). Don't touch unless
# you know what you're doing.
_MANUAL_RUNNERS = {
    # gpt-researcher: removed — subprocess runner at
    # scripts/runners/gpt_researcher_runner.py takes precedence via
    # auto-discovery.  Function body is kept for reference/fallback.
    "smolagents":            _run_smolagents,
    "camel-ai":              _run_camel,
    "storm":                 _run_storm,
    "langchain-odr":         _run_langchain_odr,
    "deerflow":              _run_deerflow,
    "ldr":                   _run_ldr,
    "ii-researcher":         _run_ii_researcher,
    "qx-agents":             _run_qx_agents,
    "dzhng":                 _run_dzhng,
    "flowsearcher-ds":       _run_flowsearcher_ds,
    "tongyi-dr":             _run_tongyi_dr,
    "co-storm":              _run_costorm,
    "deepagents":            _run_deepagents,
    "local-deep-researcher": _run_local_deep_researcher,
}


def _wrap_runner(run_fn):
    """Adapt a registry runner (intent, model, shim_url, proxy_url) to the
    (intent, model) signature this script invokes. Picks shim/proxy URLs from
    the same env vars `_setup_ds_backbone` and `_setup_sandbox_shim` already
    use, so a registry-discovered runner Just Works.

    Workstream C: also forwards `strict_sandbox` if the wrapped runner's
    signature accepts it. Otherwise it is silently dropped (the runner's
    module-level `STRICT_SANDBOX_ELIGIBLE` flag is what determines whether
    `main()` permits the run; the kwarg itself is purely informational).
    """
    import inspect as _inspect
    try:
        _sig = _inspect.signature(run_fn)
        _supports_strict = "strict_sandbox" in _sig.parameters
        _supports_timeout = "timeout_s" in _sig.parameters
    except (TypeError, ValueError):
        _sig = None
        _supports_strict = False
        _supports_timeout = False
    _agent_name = getattr(run_fn, "AGENT_NAME", None)
    if not _agent_name:
        try:
            _module = __import__(getattr(run_fn, "__module__", ""), fromlist=["AGENT_NAME"])
            _agent_name = getattr(_module, "AGENT_NAME", None)
        except Exception:
            _agent_name = None
    _agent_name = str(_agent_name or getattr(run_fn, "__module__", "runner")).split(".")[-1]
    _env_prefix = _agent_name.replace("_runner", "").replace("-", "_").upper()

    async def _adapter(intent: str, model: str, *, strict_sandbox: bool = False) -> str:
        shim = os.environ.get("SHIM_URL", "http://localhost:8081")
        proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
        kwargs = {"intent": intent, "model": model, "shim_url": shim, "proxy_url": proxy}
        if _supports_strict:
            kwargs["strict_sandbox"] = strict_sandbox
        if _supports_timeout:
            raw_timeout = (
                os.environ.get(f"{_env_prefix}_NATIVE_TIMEOUT_S")
                or os.environ.get("REGISTRY_RUNNER_NATIVE_TIMEOUT_S")
            )
            if raw_timeout:
                kwargs["timeout_s"] = int(raw_timeout)
        text = await run_fn(**kwargs)
        lowered = str(text or "").strip().lower()
        if lowered.startswith("(") and (
            "timeout" in lowered or "error" in lowered or "produced no report" in lowered
        ):
            from scripts.runners.evidence_fallback import fallback_enabled, synthesize_report

            # Fairness rule: a runner failure must surface as the framework's
            # own honest stub, never a harness-ghostwritten report. The
            # evidence writer runs only under the explicit non-benchmark
            # EVIDENCE_FALLBACK_ENABLE flag.
            if fallback_enabled():
                print(f"{_agent_name} native path failed/timeout; using source-grounded writer")
                return await asyncio.to_thread(
                    synthesize_report, intent, model, shim, proxy, min_chars=4500, min_urls=5
                )
            # Already the runner's own honest stub; pass it through unchanged.
            return text
        try:
            from scripts.runners.evidence_fallback import (
                fallback_enabled,
                is_weak_report,
                keep_or_stub,
                synthesize_report,
            )

            if is_weak_report(text, min_chars=3000, min_urls=3):
                if fallback_enabled():
                    print(f"{_agent_name} native report weak; using source-grounded writer")
                    return await asyncio.to_thread(
                        synthesize_report, intent, model, shim, proxy, min_chars=4500, min_urls=5
                    )
                # Weak-but-real output is the framework's own report: save it
                # verbatim (the scorer judges quality); stub only genuinely
                # empty/stub output.
                return keep_or_stub(
                    _agent_name, "write", "native report weak/under-threshold", text
                )
        except Exception as e:  # noqa: BLE001
            print(f"  warn: registry fallback check failed for {_agent_name}: {e}")
        return text
    _adapter.__name__ = f"_adapter_{getattr(run_fn, '__module__', 'runner')}"
    return _adapter


def _build_runners_map():
    """Merge manual entries with auto-discovered runner modules.

    Manual entries always win on conflict — the registry shouldn't accidentally
    replace a hand-tuned in-process runner with its bare module-level run().
    A new framework only needs to drop a `<name>_runner.py` with AGENT_NAME +
    async def run(...) into scripts/runners/ to appear here automatically.
    """
    merged = dict(_MANUAL_RUNNERS)
    try:
        from scripts.runners.registry import discover  # type: ignore
        discovered, errs = discover()
        for name, fn in discovered.items():
            if name not in merged:
                merged[name] = _wrap_runner(fn)
        if errs:
            for stem, why in errs.items():
                print(f"[deep_run] runner registry warn: {stem} skipped: {why}", file=sys.stderr)
    except Exception as e:
        print(f"[deep_run] runner registry unavailable: {e}", file=sys.stderr)
    return merged


RUNNERS = _build_runners_map()


# ---------------------------------------------------------------------------
# Strict-sandbox plumbing — Workstream C
# ---------------------------------------------------------------------------
#
# `--strict-sandbox` flips the arena into an audited closed-book mode where
# every cited URL must resolve to one of the four local origins
# (Magento :7770, Postmill :9999, Kiwix :8090, search shim :8081).
#
# The flag is enforced at three independent layers:
#   1. Per-adapter tool allowlist — passed as `strict_sandbox=True` to each
#      runner; runners that honour it whitelist Read/Write/Bash(curl localhost*)
#      and reject everything else. Runners that cannot honour it raise
#      `NotImplementedError` here BEFORE the run starts.
#   2. Shim-level URL gate — set SHIM_MODE=strict in the subprocess env so
#      `integrations/search_shim/app.py` returns 403 for any non-sandbox
#      target. (Not all runners use the shim, but those that do get gated.)
#   3. Post-run domain audit — `src/verifiers/sandbox_compliance_verifier`
#      scans the final report and writes ``policy_violation`` into the
#      .meta.json so leaderboard composites can disqualify offending runs.
#
# A runner declares itself strict-eligible by setting
# ``STRICT_SANDBOX_ELIGIBLE = True`` at module top level, or by exposing a
# ``strict_sandbox`` keyword on its `run()` signature. The dispatch below
# inspects both before deciding to forward the flag.
# ---------------------------------------------------------------------------

def _runner_supports_strict(runner) -> bool:
    """Return True if `runner` accepts `strict_sandbox=` or is an in-process
    helper declared strict-eligible. Used by `main()` to decide between
    forwarding the kwarg, refusing the run, or silently dropping it.
    """
    import inspect
    try:
        sig = inspect.signature(runner)
    except (TypeError, ValueError):
        return False
    return "strict_sandbox" in sig.parameters


# Manual in-process runners (defined above in this file) that ARE strict-
# sandbox eligible. Each entry was hand-reviewed for the closing of the
# "Bash/raw HTTP can leak past the patched search" gap — see
# docs/STRICT_SANDBOX_CONTRACT.md for the per-adapter table.
_INPROC_STRICT_ELIGIBLE: set[str] = {
    "smolagents",
    "camel-ai",
}

# Manual in-process runners that are NOT strict-sandbox eligible because
# their upstream framework does not expose a hook we can use to enforce
# the URL allowlist. Listed here so `main()` can refuse `--strict-sandbox`
# pre-flight rather than letting the runner silently leak.
_INPROC_STRICT_INELIGIBLE: set[str] = {
    # `langchain-odr`, `ldr`, `ii-researcher`, `dzhng`, `flowsearcher-ds`,
    # `tongyi-dr`, `co-storm`, `deepagents` were NOT audited for strict
    # mode in this Workstream. They run today as "best-effort, shim-gated
    # only". Leaving them out of the eligible set is more honest than
    # claiming compliance we haven't verified.
}


def _runner_module_strict_eligible(name: str) -> bool | None:
    """Resolve `name -> STRICT_SANDBOX_ELIGIBLE` across both runner sources.

    Lookup order:
      1. Inline manual entries (`_INPROC_STRICT_ELIGIBLE` /
         `_INPROC_STRICT_INELIGIBLE`) which cover the runners defined
         inside this script (smolagents, camel-ai, storm, etc.).
      2. The registry-discovered runner modules under
         `scripts/runners/<name>_runner.py`.

    Returns True/False if either source declares a verdict, None when both
    sources are silent (treated by `main()` as "best-effort eligible").
    """
    if name in _INPROC_STRICT_ELIGIBLE:
        return True
    if name in _INPROC_STRICT_INELIGIBLE:
        return False
    try:
        from scripts.runners import registry  # type: ignore
        runners, _ = registry.discover()
        if name not in runners:
            return None
        mod = runners[name].__globals__.get("__name__")
        if mod:
            import importlib
            m = importlib.import_module(mod)
            v = getattr(m, "STRICT_SANDBOX_ELIGIBLE", None)
            if isinstance(v, bool):
                return v
    except Exception:
        pass
    return None


def _post_audit_sandbox(report: str) -> dict:
    """Run the deterministic sandbox-compliance audit on the final report
    and return a dict suitable for embedding in `.meta.json`.

    Failure modes (import errors, malformed reports) degrade to
    ``{"audit_error": ...}`` so the run isn't blocked on a verifier bug.
    """
    try:
        from src.verifiers.sandbox_compliance_verifier import (  # noqa: E402
            verify_sandbox_compliance,
        )
        return verify_sandbox_compliance(report)
    except Exception as e:  # pragma: no cover — defensive
        return {"audit_error": f"{type(e).__name__}: {e}"}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=list(RUNNERS.keys()))
    ap.add_argument("--task", required=True)
    ap.add_argument("--backbone", default=os.environ.get("AGENT_LLM_MODEL", "deepseek-v4-flash"))
    ap.add_argument("--out-suffix", default="")
    ap.add_argument(
        "--strict-sandbox",
        action="store_true",
        default=False,
        help=(
            "Enforce the closed-book contract: per-adapter tool allowlist, "
            "shim-level URL gate (SHIM_MODE=strict), and post-run domain "
            "audit. Runners that cannot honour the allowlist are refused. "
            "See docs/STRICT_SANDBOX_CONTRACT.md."
        ),
    )
    args = ap.parse_args()

    _setup_ds_backbone(args.backbone)
    _setup_sandbox_shim()

    # Propagate strict mode to the shim and to any subprocess driver scripts
    # that read SHIM_MODE. Runners that wrap subprocess.run() with their own
    # env dict will see this var in os.environ and copy it through.
    if args.strict_sandbox:
        os.environ["SHIM_MODE"] = "strict"

    task_cfg = _load_task(args.task)
    intent = _resolve_intent(task_cfg)
    print(f"[deep_run] agent={args.agent} task={args.task} backbone={args.backbone}")
    print(f"[deep_run] intent length={len(intent)} chars")
    if args.strict_sandbox:
        print("[deep_run] strict-sandbox mode: per-adapter allowlist + shim gate + post-audit")

    os.environ["_FLOWSEARCHER_TASK_ID"] = args.task
    runner = RUNNERS[args.agent]
    t0 = time.time()
    err = None
    report = ""
    force_evidence_fallback = os.environ.get(
        "FORCE_EVIDENCE_FALLBACK_ALL", ""
    ).strip().lower() in {"1", "true", "yes", "on"}

    # Strict-mode dispatch. If the runner advertises `strict_sandbox` as a
    # kwarg we forward it. If the runner's MODULE declares itself
    # ineligible we refuse pre-flight rather than letting it silently make
    # non-sandbox HTTP calls. Otherwise we run as normal and rely solely on
    # the shim gate + post-audit (best-effort).
    runner_kwargs: dict[str, object] = {}
    if args.strict_sandbox:
        eligible = _runner_module_strict_eligible(args.agent)
        if eligible is False:
            err = (
                f"agent={args.agent} is marked STRICT_SANDBOX_ELIGIBLE=False — "
                "its upstream framework cannot honour the per-adapter "
                "allowlist. Rerun without --strict-sandbox or pick a "
                "different agent. See docs/STRICT_SANDBOX_CONTRACT.md."
            )
            report = f"(strict-sandbox refused: {err})"
        elif _runner_supports_strict(runner):
            runner_kwargs["strict_sandbox"] = True
        else:
            # The run was NOT refused (eligible is True or None) but the runner
            # callable does not expose a `strict_sandbox` kwarg, so the flag
            # would be silently dropped and the strict HTTP gate would never be
            # installed. Recording strict_sandbox=true here would falsely claim
            # an enforced closed-book run. Fail loud instead. See bug:
            # "--strict-sandbox silently NOT enforced".
            err = (
                f"agent={args.agent} advertises strict-sandbox eligibility "
                f"(STRICT_SANDBOX_ELIGIBLE={eligible!r}) but its runner does "
                "not accept a `strict_sandbox` kwarg, so the strict HTTP gate "
                "cannot be installed. Refusing the run rather than recording "
                "an unenforced run as strict_sandbox=true. See "
                "docs/STRICT_SANDBOX_CONTRACT.md."
            )
            report = f"(strict-sandbox refused: {err})"

    async def _invoke_runner_once() -> str:
        if force_evidence_fallback:
            from scripts.runners.evidence_fallback import synthesize_report

            shim = os.environ.get("SHIM_URL", "http://127.0.0.1:8081")
            proxy = (
                os.environ.get("DS_PROXY_URL")
                or os.environ.get("OPENAI_BASE_URL")
                or ""
            )
            print(
                "[deep_run] FORCE_EVIDENCE_FALLBACK_ALL=1; "
                "using source-grounded writer"
            )
            return await asyncio.to_thread(
                synthesize_report,
                intent,
                args.backbone,
                shim,
                proxy,
                min_chars=4500,
                min_urls=5,
            )
        out = runner(intent, args.backbone, **runner_kwargs)
        return await out if asyncio.iscoroutine(out) else out

    if not err:
        try:
            report = await _invoke_runner_once()
            min_chars = int(os.environ.get("DEEP_RUN_SHORT_RETRY_MIN_CHARS", "3000") or "3000")
            if len(report or "") < min_chars:
                print(
                    f"[deep_run] short report ({len(report or '')} chars < {min_chars}); retrying once",
                    file=sys.stderr,
                )
                report = await _invoke_runner_once()
        except NotImplementedError as e:
            err = f"strict_sandbox unsupported: {e}"
            report = f"(runner refused strict-sandbox: {e})"
        except Exception as e:
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            report = f"(runner error: {type(e).__name__}: {e})"
    elapsed = time.time() - t0

    # Run the deterministic sandbox-compliance audit on the final report.
    # We do this regardless of --strict-sandbox so the meta.json always
    # carries the URL-leak signal — strict mode just promotes it from
    # "informational" to "policy violation".
    sandbox_audit = _post_audit_sandbox(report or "")

    suffix = f"_{args.out_suffix}" if args.out_suffix else ""
    out_md = OUT_DIR / f"{args.agent}__{args.task}{suffix}.md"
    out_meta = OUT_DIR / f"{args.agent}__{args.task}{suffix}.meta.json"
    out_md.write_text(report or "(empty)")
    out_meta.write_text(json.dumps({
        "agent": args.agent, "task": args.task, "backbone": args.backbone,
        "elapsed_seconds": round(elapsed, 1),
        "report_chars": len(report or ""),
        "error": err,
        "strict_sandbox": bool(args.strict_sandbox),
        "sandbox_audit": sandbox_audit,
    }, indent=2, ensure_ascii=False))

    print(f"[deep_run] done in {elapsed:.0f}s, {len(report)} chars → {out_md.name}")
    if sandbox_audit.get("policy_violation"):
        print(
            f"[deep_run] sandbox audit: {len(sandbox_audit.get('non_sandbox_urls') or [])}"
            f" non-sandbox URL(s) cited"
        )
    if err:
        print(f"[deep_run] ERR: {err.splitlines()[0]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
