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
import hashlib
import json
import os
import signal
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The my5090 composite runtime installs open_deep_research editable.  Its
# generated PEP-660 finder records the checkout path that existed at install
# time (normally /opt/deep_reserch).  Formal smokes run from an immutable clean
# worktree mounted at /opt/deep_reserch-smoke, while the worker chroot exposes
# only that attested repository.  Put the attested source tree on sys.path so
# the native ODR graph never depends on an inaccessible/stale editable path.
ODR_SOURCE_ROOT = ROOT / "third_party" / "langchain-open-deep-research" / "src"

DEEP_TASK_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
OUT_DIR = ROOT / "data" / "results" / "deep"


def _run_output_dir() -> Path:
    """Per-run output root, isolated by run-set/backbone when requested."""
    raw = os.environ.get("DEEP_RUN_OUT_DIR", "").strip()
    if not raw:
        return OUT_DIR
    p = Path(raw).expanduser()
    return p if p.is_absolute() else ROOT / p

from scripts.runners import _budget, _egress  # noqa: E402  (needs ROOT on sys.path)

# Distinct exit codes so the shell driver can tell the four run outcomes apart.
# The old world collapsed "framework diverged" and "box wedged" into one
# `timeout`; these keep them separate (see _StallWatchdog and lane_protocol.yaml
# `budget`). Anything the driver classifies as `stalled` is infrastructure and
# is rerunnable, NOT a framework failure.
EXIT_OK = 0
EXIT_FRAMEWORK_ERROR = 1
EXIT_STALLED = 3        # no LLM/shim progress for stall_timeout_s -> infra fault
EXIT_WALL_TIMEOUT = 4   # optional uniform wall clock exceeded (default: never)


def _native_timeout_s(env_name: str) -> Optional[float]:
    """Per-lane native (self-abort) wall clock, with the shared default.

    Thin wrapper over _budget.resolve_native_timeout so every inline lane in
    this file resolves the SAME default (DRA_WALL_CLOCK_S, None = unlimited).
    The default must be identical across lanes because a per-lane time budget
    punishes a framework for its backbone's token rate, not its own behaviour;
    the no-progress watchdog is what actually terminates a wedged run. See
    scripts/runners/_budget.py for the measured 1206s stall that motivated this.
    """
    return _budget.resolve_native_timeout(env_name)


def _wait_for_timeout(native_timeout: Optional[float], floor: float = 60.0):
    """asyncio.wait_for timeout arg for a native path: None (no cap) passes
    through as None; a real value is floored so a tiny override can't abort a
    run before it starts."""
    if native_timeout is None:
        return None
    return max(floor, native_timeout)


class _StallWatchdog(threading.Thread):
    """Uniform no-progress watchdog. Same policy for every lane.

    WHAT "PROGRESS" MEANS HERE

    A run is making progress iff it is still talking to the sandbox or the LLM.
    We approximate that with two cross-process signals, polled over HTTP/stat so
    the watchdog never has to share memory with the runner:

      * shim call count -- GET {SHIM_URL}/_evidence/status .counters (the shim's
        per-process tally of search+fetch chokepoint hits).
      * egress call count -- GET {DRA_EGRESS_CONTROL_URL}/healthz .counters
        (direct page reads made outside the shim).
      * ds_proxy health counters -- GET {DS_PROXY_URL origin}/healthz
        .smoke_budget plus .usage_log_bytes (accepted requests, completed-token
        growth, and admission/retry heartbeats while shared slots are busy).
      * ds_proxy usage-log growth -- os.path.getsize(DSPROXY_USAGE_LOG); one
        appended line per upstream LLM call.

    If NEITHER advances for `stall_timeout_s`, the run is wedged (typically the
    local vLLM taking >1000s on a single step). We record `stalled` (an
    infrastructure fault, rerunnable, NOT a framework failure) and kill the
    process. If an optional uniform `wall_clock_s` is set (default None), we
    record `timeout` when it is exceeded regardless of progress.

    HONEST LIMITATIONS (do not paper over these)

      * The signals are per-recorder-process and per-usage-file, NOT per-run. This
        is only accurate when each concurrent worker has its OWN shim + usage
        log (which the protocol already requires: evidence.mark_start refuses to
        interleave two runs on one shim). With a SHARED shim, a sibling worker's
        traffic resets this run's stall clock, so stalls are under-detected. The
        exact per-run signal is the size of evidence_dir/<run_id>.jsonl. The
        current per-worker recorder isolation makes these counters equivalent
        while a queue runs one entry at a time.
      * On a stall we os._exit() to guarantee THIS process dies even while a
        blocked C extension or joined subprocess holds the GIL/thread. Direct
        child processes are SIGTERM'd first (best-effort, /proc-based). Deeper
        descendants of a subprocess lane may briefly orphan; the box reaper and
        the rerun handle them.
    """

    def __init__(
        self,
        *,
        stall_timeout_s: float,
        wall_clock_s: Optional[float],
        shim_url: str,
        egress_url: Optional[str],
        dsproxy_url: Optional[str],
        usage_log: Optional[str],
        meta_writer,
        t0: float,
        poll_interval: Optional[float] = None,
        on_kill=None,
    ) -> None:
        super().__init__(name="dra-stall-watchdog", daemon=True)
        self._stall = float(stall_timeout_s)
        self._wall = wall_clock_s
        self._shim_url = shim_url.rstrip("/")
        self._egress_url = (egress_url or "").rstrip("/") or None
        self._dsproxy_url = (dsproxy_url or "").rstrip("/") or None
        self._usage_log = usage_log or None
        self._meta_writer = meta_writer
        self._on_kill = on_kill
        self._t0 = t0
        self._stop = threading.Event()
        # Poll often enough to notice a stall promptly, but never busier than
        # every 5s. For the 900s default this lands at 30s.
        self._poll = poll_interval or min(30.0, max(5.0, self._stall / 20.0))

    def stop(self) -> None:
        self._stop.set()

    def _progress(self) -> tuple:
        shim_calls = 0
        try:
            import requests  # local import: watchdog must not add a hard dep

            r = requests.get(f"{self._shim_url}/_evidence/status", timeout=5)
            counters = (r.json() or {}).get("counters") or {}
            shim_calls = sum(int(v) for v in counters.values()
                             if isinstance(v, (int, float)))
        except Exception:
            # A shim that is briefly unreachable is not progress and not a stall
            # by itself; the usage log or the next poll settles it.
            pass
        usage_bytes = 0
        if self._usage_log:
            try:
                usage_bytes = os.path.getsize(self._usage_log)
            except OSError:
                usage_bytes = 0
        egress_calls = 0
        if self._egress_url:
            try:
                import requests

                session = requests.Session()
                session.trust_env = False
                r = session.get(f"{self._egress_url}/healthz", timeout=5)
                counters = (r.json() or {}).get("counters") or {}
                egress_calls = sum(
                    int(v) for v in counters.values()
                    if isinstance(v, (int, float))
                )
            except Exception:
                pass
        dsproxy_calls = 0
        dsproxy_tokens = 0
        dsproxy_usage_bytes = 0
        if self._dsproxy_url:
            try:
                from urllib.parse import urlsplit, urlunsplit

                parsed = urlsplit(self._dsproxy_url)
                path = parsed.path.rstrip("/")
                if path.endswith("/v1"):
                    path = path[:-3]
                health_url = urlunsplit((
                    parsed.scheme,
                    parsed.netloc,
                    path + "/healthz",
                    "",
                    "",
                ))
                import requests

                session = requests.Session()
                session.trust_env = False
                health = session.get(health_url, timeout=5).json() or {}
                smoke = health.get("smoke_budget") or {}
                dsproxy_calls = int(smoke.get("accepted_calls") or 0)
                dsproxy_tokens = int(smoke.get("observed_total_tokens") or 0)
                dsproxy_usage_bytes = int(health.get("usage_log_bytes") or 0)
            except Exception:
                pass
        return (
            shim_calls,
            egress_calls,
            usage_bytes,
            dsproxy_calls,
            dsproxy_tokens,
            dsproxy_usage_bytes,
        )

    def run(self) -> None:
        last = self._progress()
        last_change = time.time()
        while not self._stop.wait(self._poll):
            now = time.time()
            if self._wall is not None and (now - self._t0) > self._wall:
                self._fire("timeout", EXIT_WALL_TIMEOUT,
                           f"uniform wall clock {self._wall:.0f}s exceeded")
                return
            cur = self._progress()
            if cur != last:
                last = cur
                last_change = now
            elif (now - last_change) > self._stall:
                self._fire(
                    "stalled", EXIT_STALLED,
                    f"no shim/LLM progress for {self._stall:.0f}s "
                    "(infrastructure stall, not a framework failure)",
                )
                return

    def _fire(self, status: str, exit_code: int, reason: str) -> None:
        # Record the outcome BEFORE killing the process so a scored run is never
        # lost. We deliberately do NOT write the report .md: a stalled run left
        # no report, and leaving the .md absent keeps the task rerunnable and
        # keeps a genuine (empty) framework output distinguishable from an infra
        # kill. See main() and the residual-risk note on missing-as-zero.
        try:
            self._meta_writer(status, reason)
        except Exception:
            pass
        # Close the evidence bracket BEFORE os._exit. os._exit runs no finally and
        # no atexit, so without this the run's /_mark end is never posted and the
        # shim's _ACTIVE stays open. It would 409 the next run until the orphan TTL
        # elapses; posting end here lets the queue advance immediately. Best-effort:
        # a failed close still self-heals via the shim's bracket_ttl reclaim.
        if self._on_kill is not None:
            try:
                self._on_kill()
            except Exception:
                pass
        print(f"[deep_run] watchdog: {status} -- {reason}", file=sys.stderr)
        _terminate_children()
        # os._exit, not sys.exit: a blocked native call or joined subprocess can
        # swallow a normal interpreter shutdown. This guarantees the exit code.
        os._exit(exit_code)


def _terminate_children() -> None:
    """SIGTERM this process's direct children so a subprocess lane does not
    orphan when the watchdog kills us. Best-effort and Linux-first."""
    try:
        import psutil  # type: ignore

        me = psutil.Process()
        for child in me.children(recursive=True):
            try:
                child.terminate()
            except Exception:
                pass
        return
    except Exception:
        pass
    # psutil absent: fall back to a /proc scan for direct children only.
    try:
        my_pid = os.getpid()
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/stat") as fh:
                    ppid = int(fh.read().split(")")[-1].split()[1])
            except Exception:
                continue
            if ppid == my_pid:
                try:
                    os.kill(int(entry), signal.SIGTERM)
                except Exception:
                    pass
    except Exception:
        pass


def _load_task(task_id: str) -> dict:
    return json.loads((DEEP_TASK_DIR / f"{task_id}.json").read_text())


# The ONE instruction any lane may append to the shared intent.
#
# Prompt parity is defined on capability, not on the literal string. A native
# lane receives the sandbox as a tool (`ShimSearchTool`); a CLI lane has no
# search tool at all and must be told how to reach the shim with curl. Those
# deliveries differ by necessity. What must not differ is the task: no lane may
# be told to hit a citation count, a word count, a search count, or a citation
# format, because each of those steers directly at a scored axis.
#
# CLI lanes emit a conversational turn rather than a document by default, and
# several native lanes otherwise discard exact source URLs at their final write
# stage. The neutral report/citation contract below is therefore given to every
# lane identically. It specifies neither a count nor a citation syntax. Anything
# beyond it belongs in `config/lane_protocol.yaml` as a declared deviation.
SHARED_REPORT_FORMAT = (
    "\n\nBase factual claims on sources retrieved during this run. "
    "Include the exact retrieved URL for every source used in the final report. "
    "Deliver your answer as a single self-contained markdown report. "
    "Return the report only, with no planning notes or tool transcripts."
)


def _resolve_intent(task_cfg: dict) -> str:
    sandbox_subs = {
        # 7770 is what url_registry, the release compose, and MAGENTO_BASE_URL
        # all say. 17770 are the teardown ports of the verify compose, and
        # registry.classify calls that host `host_not_in_sandbox`, i.e. the
        # scorer counts a citation of it as FABRICATED. Pointing the agent at a
        # store and then punishing it for citing that store is not a benchmark.
        "__SHOPPING__":  os.environ.get("SHOPPING",  "http://localhost:7770"),
        "__REDDIT__":    os.environ.get("REDDIT",    "http://localhost:9999"),
        "__WIKIPEDIA__": os.environ.get("WIKIPEDIA", "http://localhost:8090"),
    }
    intent = task_cfg.get("intent", "")
    for k, v in sandbox_subs.items():
        intent = intent.replace(k, v)
    # Append the one shared output instruction exactly once at the single
    # dispatch boundary. Previously only smolagents/camel/qx/CLI paths received
    # it while most native runners saw the raw task, despite lane_protocol.yaml
    # claiming it was shared.
    return intent.rstrip() + SHARED_REPORT_FORMAT


def _setup_ds_backbone(model: str) -> None:
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
    os.environ["OPENAI_BASE_URL"] = proxy
    os.environ["OPENAI_API_BASE"] = proxy
    os.environ["OPENAI_API_KEY"] = "anything-proxy-uses-server-key"

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
        ("TAVILY_API_KEY", "tvly-shim-fake"),
    ]:
        # Never inherit a stale model/retriever from the login shell.  The
        # command-line backbone is the system under test.
        os.environ[var] = val


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
    - In a standalone developer run, aiohttp must not inherit a host/Mihomo
      proxy. In a harness run, ``DRA_EGRESS_PROXY`` is the recording door and
      aiohttp must do the opposite: force ``trust_env=True``.
    - DeerFlow's Jina crawler POSTs to https://r.jina.ai/ which is external.
      We intercept and fetch the target URL directly instead.
    - Process-level env cleanup remains the fail-closed standalone default, but
      is disabled when the harness deliberately configured the recording door.
    """
    return (
        "# --- HTTP-level intercept (auto-generated) ---\n"
        "import os as _os, sys as _sys\n"
        "_DRA_EGRESS_ON = bool(_os.environ.get('DRA_EGRESS_PROXY', '').strip())\n"
        "# Standalone runs scrub host proxies. Harness runs preserve the exact\n"
        "# proxy_env installed by run_deep_task so the child cannot bypass it.\n"
        "if not _DRA_EGRESS_ON:\n"
        "    for _pv in list(_os.environ):\n"
        "        if _pv.lower() in ('http_proxy','https_proxy','all_proxy','no_proxy','ftp_proxy'):\n"
        "            del _os.environ[_pv]\n"
        "    _os.environ['NO_PROXY'] = '*'\n"
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
        "# Patch aiohttp: trust only the harness door, never an ambient host proxy,\n"
        "# and intercept _request for URL rewriting.\n"
        "try:\n"
        "    import aiohttp as _ah\n"
        "    _orig_cs_init = _ah.ClientSession.__init__\n"
        "    def _cs_init_patched(self, *a, **kw):\n"
        "        kw['trust_env'] = _DRA_EGRESS_ON\n"
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
    os.environ["TAVILY_API_KEY"] = "tvly-shim-fake"
    os.environ["TAVILY_API_URL"] = shim
    os.environ["GPTR_SHIM_URL"] = shim
    # FIX #9: Install HTTP-level intercept for ALL in-process runners.
    # This catches requests/httpx/aiohttp calls to api.tavily.com and
    # en.wikipedia.org regardless of which Python object made them.
    try:
        import src.shim_intercept  # noqa: F401: auto-patches on import
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

    # This block used to seed the answer twice over: a literal example URL
    # (`[Active noise control](http://localhost:8090/...)`) that the model was
    # observed copying verbatim into its report as its ONLY sandbox citation,
    # and the exact per-domain citation counts the scorer checks for. The
    # 2026-07-06 lane audit ordered it neutralised (item 3) and it was
    # neutralised in `scripts/runners/gpt_researcher_runner.py` only. This copy
    # survived, still reachable through the V2 wrapper
    # (`integrations/agents/gpt_researcher/agent.py` imports this function).
    # Removed 2026-07-08.
    r = GPTResearcher(query=intent,
                      report_type="research_report", tone="objective")
    await r.conduct_research()
    return await r.write_report()


# Outcome of the pre-run source liveness check, stamped into the run meta.
#
# `DEEP_RUN_SKIP_SOURCE_CHECK=1` exists for tests and for bringing a box up, and
# an escape hatch that leaves no trace is the same failure this whole check was
# built to end: a run scored against a corpus nobody confirmed it could see,
# indistinguishable afterwards from a run that was checked. So the skip is
# recorded, and a board can filter on it.
_SOURCE_CHECK: dict[str, object] = {"state": "not_run"}


def _uncorpus_sample(urls: list[str]) -> list[str]:
    """Which of these URLs would the scorer call fabricated?

    Returns [] when the registry cannot be loaded: a missing registry is the
    scorer's problem to refuse, not grounds to block a run here on a guess.
    """
    if not urls:
        return []
    try:
        from src.eval.closed_world_eval import load_registry
        reg = load_registry()
    except Exception:  # noqa: BLE001
        return []
    if reg is None:
        return []
    out = []
    for u in urls:
        try:
            if not reg.classify(u).get("in_corpus"):
                out.append(u)
        except Exception:  # noqa: BLE001
            continue
    return out


# ---------------------------------------------------------------------------
# Workstream C: in-process HTTP gate
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


# The four sandbox SITE origins (Magento, its mirror, Kiwix, Postmill). Distinct
# from `_INPROC_SANDBOX_HOSTS`, which ALSO contains the shim's own origin
# (8081/18081). The gate must rewrite a page read to a site into a recorded shim
# /fetch, but must leave a request that is ALREADY going to the shim untouched,
# or the ShimSearchTool's POST {shim}/search would be rewritten into a self-loop.
_INPROC_SITE_HOSTS = frozenset({
    "localhost:7770", "localhost:17770", "localhost:8090", "localhost:9999",
    "127.0.0.1:7770", "127.0.0.1:17770", "127.0.0.1:8090", "127.0.0.1:9999",
})


def _install_inproc_sandbox_gate() -> None:
    """Install a `requests.Session.send` interceptor. Idempotent.

    Two jobs, both on `requests.Session.send` (so it covers every library built
    on `requests`, including smolagents' VisitWebpageTool and langchain's
    requests loaders):

      1. A GET to a sandbox SITE origin is REWRITTEN to a recorded
         `GET {shim}/fetch?url=<original>`. Before 2026-07-08 this path was a
         plain pass-through: the page read hit the site directly and the shim
         never saw it, so `pof` had nothing to measure. Rewriting makes the read
         land in `logs/fetch/<run_id>.jsonl` via the shim's record_fetch.
      2. Any other non-sandbox URL is rejected with a synthetic 403 (unchanged).

    Requests already going to the shim itself (8081/18081) pass straight through
    to avoid a rewrite self-loop.

    It does NOT catch `aiohttp`, `httpx`, `urllib.request`, or anything running
    in a child process (a subprocess has its own interpreter and never sees this
    patch). Lanes on those transports stay fetch_observable=false in
    config/lane_protocol.yaml. See FETCH_PATH_AUDIT_2026-07-08.md.

    The interceptor is reset when the parent process exits: these in-
    process runners always run one task per parent process anyway.
    """
    if getattr(_install_inproc_sandbox_gate, "_done", False):
        return
    from urllib.parse import quote as _quote
    from urllib.parse import urlparse as _up

    def _hostport(url: str) -> Optional[str]:
        try:
            p = _up(url)
            host = (p.hostname or "").lower()
            port = p.port
        except Exception:
            return None
        if not host or port is None:
            return None
        return f"{host}:{port}"

    def _ok(url: str) -> bool:
        hp = _hostport(url)
        return hp is not None and hp in _INPROC_SANDBOX_HOSTS

    try:
        import requests  # type: ignore
    except ImportError:
        return
    _orig = requests.Session.send

    def _gated(self, request, **kw):
        hp = _hostport(request.url)
        method = (getattr(request, "method", "") or "").upper()
        # A page read to a SITE origin: reroute through the recorded shim /fetch.
        # Setting request.url is sufficient for requests -- HTTPAdapter.send
        # re-derives the connection and path_url from it. Only GET is a page
        # read; other verbs to a site pass through unchanged.
        if hp in _INPROC_SITE_HOSTS and method == "GET":
            shim = os.environ.get("SHIM_URL", "http://127.0.0.1:8081").rstrip("/")
            request.url = f"{shim}/fetch?url={_quote(request.url, safe='')}"
            return _orig(self, request, **kw)
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

    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    # Unified native timeout: default identical to every other lane
    # (DRA_WALL_CLOCK_S, None = unlimited). SMOLAGENTS_NATIVE_TIMEOUT_S still
    # overrides for single-run debugging. The old hard 420s default aborted
    # slow-backbone runs that were still making progress; the no-progress
    # watchdog now handles genuine stalls. See scripts/runners/_budget.py.
    native_timeout = _native_timeout_s("SMOLAGENTS_NATIVE_TIMEOUT_S")

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
    # copy exact URLs returned by the search tool: dramatically improving URL accuracy.
    from smolagents import Tool, ToolCallingAgent, OpenAIServerModel
    from smolagents.default_tools import VisitWebpageTool

    class ShimSearchTool(Tool):
        name = "web_search"
        description = (
            "Search the benchmark index and return titles, URLs, and text."
        )
        inputs = {
            "query": {
                "type": "string",
                "description": "Search query.",
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
        max_steps=int(os.environ.get("SMOLAGENTS_MAX_STEPS", "20") or "20"),
    )
    # Prompt parity (fairness audit 2026-07-08, B3). This lane used to append a
    # rubric aimed straight at the scored axes: ">= 5 exact http://localhost
    # URLs or the report is invalid" (reach's numerator), ">= 4500 characters
    # and >= 10 paragraphs" (completeness), "make 6 to 10 focused searches".
    # No other lane received it. Every framework now gets the shared intent and
    # the report-format line that every lane gets, nothing else.
    smol_prompt = intent
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(agent.run, smol_prompt),
            timeout=_wait_for_timeout(native_timeout),
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
    # The repair loop that used to live here re-prompted the agent whenever
    # `_sandbox_url_count(result) < 5` or the report was short, i.e. it gave
    # this lane a second attempt keyed on the very quantity the scorer measures.
    # No other framework got a retry. Removed 2026-07-08 (fairness audit, B3).
    # A weak report is now saved verbatim, exactly as for every other lane.
    min_chars = int(os.environ.get("SMOLAGENTS_MIN_REPORT_CHARS", "3500") or "3500")

    if is_weak_report(result, min_chars=min_chars):
        reason = f"native output under threshold ({len(result or '')} chars)"
        # Weak-but-real output is the framework's own report: save it verbatim
        # (the scorer judges quality); stub only genuinely empty/stub output.
        return keep_or_stub("smolagents", "write", reason, result)
    return result


def _sanitize_camel_report(text: str) -> str:
    """Strip BALANCED framework XML markers from a camel-ai report before it is
    saved. Declared in lane_protocol.yaml as camel-ai's `report_postprocess`
    deviation so the board discloses this harness rewrite.

    Fairness audit 2026-07-06: camel saved the model's raw output including
    literal ``<think>...</think>`` reasoning and ``<tool_call>`` XML scaffolding
    (archived reports 0013/0024/0037). We remove ONLY BALANCED
    ``<tag>...</tag>`` pairs; all prose and citations are preserved
    byte-for-byte otherwise, and this changes the saved artifact only, not
    camel's behavior, prompts, or termination.

    An UNCLOSED opener is left in place, verbatim. The former version deleted
    from any dangling ``<think>``/``<tool_call>``/``<tool_response>`` to the end
    of the text (a ``.*`` with DOTALL): a single unclosed reasoning tag emitted
    mid-report therefore erased the entire body below it -- turning a real,
    scored camel report into a truncated stub. Preserving unclosed tags keeps
    the report body intact and lets the scorer judge what camel actually wrote.
    """
    import re as _re
    s = str(text or "")
    # Complete (BALANCED) <think>...</think> reasoning blocks (multiline).
    s = _re.sub(r"<think\b[^>]*>.*?</think\s*>", "", s, flags=_re.DOTALL | _re.IGNORECASE)
    # Complete (BALANCED) tool-call / tool-response scaffolding blocks.
    s = _re.sub(r"<tool_call\b[^>]*>.*?</tool_call\s*>", "", s, flags=_re.DOTALL | _re.IGNORECASE)
    s = _re.sub(r"<tool_response\b[^>]*>.*?</tool_response\s*>", "", s, flags=_re.DOTALL | _re.IGNORECASE)
    # No dangling-opener or orphan-closer removal: an UNCLOSED tag is left as-is
    # rather than deleting the report body to EOF (the disaster this fix kills).
    return s.strip()


async def _run_camel(intent: str, model: str, *, strict_sandbox: bool = False) -> str:
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
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
        # Same gate as smolagents: camel-ai's SearchToolkit may add new
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
    # 2026-07-08: the residual "every factual claim must be a markdown link" is
    # also gone. It prescribes a citation style and a citation density, both of
    # which are scored, to a lane whose peers were never told. What remains is
    # the role and the shared output-format line.
    system = "You are a deep-research agent."
    agent = ChatAgent(system_message=system, model=m, tools=tools)
    # Unified native timeout: default identical to every other lane
    # (DRA_WALL_CLOCK_S, None = unlimited). camel-ai was the ONLY lane running
    # unbounded (CAMEL_NATIVE_TIMEOUT_S=0); every lane is now unbounded by
    # default and terminated by the shared no-progress watchdog instead.
    native_timeout = _native_timeout_s("CAMEL_NATIVE_TIMEOUT_S")
    try:
        if native_timeout:
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

    # Fairness audit 2026-07-06: sanitize the SAVED report only: strip
    # <think>...</think> reasoning and dangling tool-call XML scaffolding that
    # qwen emits as literal text. Prose and citations are untouched.
    content = _sanitize_camel_report(content)

    if is_weak_report(content, min_chars=3000, min_urls=3):
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
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await storm_run(
        intent=intent, model=model, shim_url=shim, proxy_url=proxy,
        strict_sandbox=strict_sandbox,
    )


async def _run_langchain_odr_graph(intent: str, model: str) -> str:
    """Run open_deep_research's native LangGraph end to end.

    The previous adapter manually called one researcher, executed only the
    first tool call, replaced every additional call with a harness message,
    and bypassed the supervisor graph. That was a custom agent wearing ODR's
    name. Keep only endpoint/model compatibility here; planning, retrieval,
    compression, supervision, and final writing remain framework-owned.
    """
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    os.environ["OPENAI_BASE_URL"] = proxy
    os.environ.setdefault("OPENAI_API_KEY", "anything")
    os.environ["TAVILY_API_KEY"] = "tvly-shim-fake"

    # Route the framework's native Tavily clients to the benchmark shim without
    # replacing its search tool, result processing, or query policy.
    try:
        import httpx as _odr_httpx
        import tavily

        _orig_sync = tavily.TavilyClient.__init__

        def _patched_sync(self, api_key=None, *args, **kwargs):
            kwargs.pop("api_base_url", None)
            _orig_sync(self, api_key, *args, **kwargs)
            self.base_url = shim

        tavily.TavilyClient.__init__ = _patched_sync

        if hasattr(tavily, "AsyncTavilyClient"):
            _orig_async = tavily.AsyncTavilyClient.__init__

            def _patched_async(self, *args, **kwargs):
                kwargs.pop("api_base_url", None)
                _orig_async(self, *args, **kwargs)
                creator = getattr(self, "_client_creator", None)
                if callable(creator):
                    def _shim_client_creator(_creator=creator):
                        client = _creator()
                        client.base_url = _odr_httpx.URL(shim)
                        return client

                    self._client_creator = _shim_client_creator
                if hasattr(self, "_api_base_url"):
                    self._api_base_url = shim
                if getattr(self, "_client", None) is not None:
                    self._client.base_url = shim

            tavily.AsyncTavilyClient.__init__ = _patched_async
    except Exception as exc:  # noqa: BLE001
        print(f"  warn: langchain-odr Tavily routing patch failed: {exc}")

    odr_model = f"openai:{model}"
    for name in (
        "RESEARCH_MODEL", "SUMMARIZATION_MODEL", "COMPRESSION_MODEL",
        "FINAL_REPORT_MODEL",
    ):
        os.environ[name] = odr_model
    os.environ["DEFAULT_MODEL"] = model
    os.environ["OPENAI_MODEL_NAME"] = model

    if not (ODR_SOURCE_ROOT / "open_deep_research").is_dir():
        raise RuntimeError(
            f"open_deep_research source tree missing: {ODR_SOURCE_ROOT}"
        )
    odr_source = str(ODR_SOURCE_ROOT)
    if odr_source not in sys.path:
        sys.path.insert(0, odr_source)
    import open_deep_research.deep_researcher as odr

    # Compatibility only: some local backbones return the requested brief under
    # `description`. Accept that alias without inventing or rewriting a brief.
    from pydantic import BaseModel, ConfigDict, Field, model_validator

    class _ResearchQuestionCompat(BaseModel):
        model_config = ConfigDict(populate_by_name=True)
        research_brief: str = Field(
            description="A research question that will be used to guide the research."
        )

        @model_validator(mode="before")
        @classmethod
        def _description_alias(cls, data):
            if isinstance(data, dict) and not data.get("research_brief"):
                value = data.get("description")
                if isinstance(value, str) and value.strip():
                    data = {**data, "research_brief": value}
            return data

    odr.ResearchQuestion = _ResearchQuestionCompat

    cfg = {
        "configurable": {
            "research_model": odr_model,
            "compression_model": odr_model,
            "final_report_model": odr_model,
            "summarization_model": odr_model,
            "search_api": "tavily",
            "allow_clarification": False,
            # Preserve ODR's native breadth and iteration ceilings. Reducing
            # these values turns the framework into a narrower custom agent.
            "max_concurrent_research_units": 5,
            "max_researcher_iterations": 6,
            "max_react_tool_calls": 10,
            "research_model_max_tokens": 8192,
            "compression_model_max_tokens": 8192,
            "summarization_model_max_tokens": 8192,
            "final_report_model_max_tokens": 8192,
        }
    }
    graph = odr.deep_researcher_builder.compile()
    result = await graph.ainvoke(
        {"messages": [odr.HumanMessage(content=intent)]},
        config=cfg,
    )
    if isinstance(result, dict):
        final = result.get("final_report") or ""
        if not final and result.get("messages"):
            final = getattr(result["messages"][-1], "content", "")
    else:
        final = getattr(result, "final_report", "") or str(result or "")
    return str(final or "(empty langchain-odr result)")


async def _run_langchain_odr_graph_legacy(intent: str, model: str) -> str:
    """LangChain open_deep_research uses a langgraph supervisor → researcher → writer."""
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
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
            "search_api":             "tavily",
            "allow_clarification":    False,
            # Preserve ODR's native breadth and iteration ceilings. The legacy
            # compatibility path must not silently narrow the framework.
            "max_concurrent_research_units": 5,
            "max_researcher_iterations": 6,
            "max_react_tool_calls":   10,
            "research_model_max_tokens": 8192,
            "compression_model_max_tokens": 8192,
            "summarization_model_max_tokens": 8192,
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
    #   - The hand-rolled writer is DELETED (2026-07-08, fairness audit). It ran
    #     the searches itself and pasted 18 retrieved pages into the prompt, so
    #     the lane was scored on the harness's retrieval rather than
    #     open_deep_research's. An env flag guarding a path that manufactures
    #     grounding is an escape hatch, not a safeguard.
    # Unified native timeout: default identical to every other lane
    # (DRA_WALL_CLOCK_S, None = unlimited). LANGCHAIN_ODR_GRAPH_TIMEOUT_S still
    # overrides. The old 1500s default was a comparative wall clock; the shared
    # no-progress watchdog now governs termination.
    timeout_s = _native_timeout_s("LANGCHAIN_ODR_GRAPH_TIMEOUT_S")
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
        proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")

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
        text = await asyncio.wait_for(_run_langchain_odr_graph(intent, model),
                                      timeout=_wait_for_timeout(timeout_s))
        if allow_benchmark_fallback and _is_weak_report(text, min_chars=3000, min_urls=3):
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
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    # Unified native timeout: default identical to every other lane
    # (DRA_WALL_CLOCK_S, None = unlimited). DEERFLOW_NATIVE_TIMEOUT_S still
    # overrides. None flows through to subprocess.run(timeout=None) inside the
    # runner; the shared no-progress watchdog terminates a wedged subprocess.
    timeout_s = _native_timeout_s("DEERFLOW_NATIVE_TIMEOUT_S")
    text = await deerflow_run(
        intent=intent, model=model, shim_url=shim, proxy_url=proxy,
        strict_sandbox=strict_sandbox, timeout_s=timeout_s,
    )
    # None = unlimited: render it as "unbounded" in messages rather than "Nones".
    _tdesc = "unbounded" if timeout_s is None else f"{timeout_s:.0f}s"
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
        if lowered.startswith("(deerflow"):
            # Already deerflow's own honest stub; pass it through unchanged.
            return text
        if "timeout after" in lowered:
            # A timeout marker is a genuine failure, not a weak report.
            return error_stub("deerflow", "native", f"native path weak/timeout ({_tdesc} budget)")
        # Weak-but-real output is deerflow's own report: save it verbatim (the
        # scorer judges quality); stub only genuinely empty/stub output.
        return keep_or_stub("deerflow", "native", "native report weak/under-threshold", text)
    return text


async def _run_ldr(intent: str, model: str) -> str:
    """LDR via clean runner module:intent sanitization + LDR official API."""
    from scripts.runners.ldr_runner import run as ldr_run
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await ldr_run(intent=intent, model=model, shim_url=shim, proxy_url=proxy)


async def _run_ii_researcher(intent: str, model: str) -> str:
    """Intelligent-Internet/ii-researcher via subprocess in .venv-ii."""
    from scripts.runners.evidence_fallback import (
        error_stub,
        fallback_enabled,
        is_weak_report,
        keep_or_stub,
        synthesize_report,
    )

    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
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
    env["II_BENCHMARK_ROOT"] = str(ROOT)
    # FIX #10: Force SEARCH_PROVIDER=tavily so ii-researcher uses TavilyClient
    # (which goes through our shim) instead of the default "serpapi" (which hits
    # serpapi.com and is NOT intercepted by our monkey-patch).
    env["SEARCH_PROVIDER"] = "tavily"
    # Use BeautifulSoup scraper for page_visit so it goes through requests.Session
    # (intercepted for Wikipedia URL rewriting) instead of firecrawl/jina.
    env["SCRAPER_PROVIDER"] = "bs"
    # Standalone runs scrub ambient proxies. Formal runs preserve and normalize
    # the recording door in the FINAL environment passed to subprocess.run.
    _egress.scrub_or_apply(env)

    # FIX #6+#9+#10: Robust driver with HTTP-level intercept + TavilyClient patch.
    # The intercept preamble patches requests/aiohttp/httpx at transport layer so
    # ii-researcher's search calls to api.tavily.com are caught regardless of
    # whether it uses TavilyClient, AsyncTavilyClient, or raw HTTP.
    # Additionally, we directly patch TavilyClient.__init__ to set base_url to
    # shim as belt-and-suspenders.
    # Per-run path: formal workers may execute the same lane concurrently with
    # different shim URLs. A fixed `_ii_driver.py` let one worker overwrite the
    # other's driver and route search/evidence into the wrong bracket.
    driver = _egress.scratch_path("ii-researcher-driver")
    driver.write_text(_build_intercept_preamble(shim) +
        "import os, sys, asyncio, traceback, re, json\n"
        "sys.path.insert(0, '.')\n"
        "sys.path.insert(0, os.environ['II_BENCHMARK_ROOT'])\n"
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
        "    from scripts.runners.ii_tool_compat import MAX_NATIVE_ACTIONS, api_tool_schemas, tool_call_to_native_action\n"
        "    agent = ReasoningAgent(question=os.environ['II_QUERY'], report_type=ReportType.BASIC)\n"
        "    # II 0.1.5 exposes tools only through a textual fenced-Python\n"
        "    # convention. Advertise those same native tools through the API's\n"
        "    # function-tool channel and translate a selected call back into\n"
        "    # II's existing action syntax. auto keeps tool use model-chosen.\n"
        "    _api_tool_calls = []\n"
        "    _action_budget_exhausted = False\n"
        "    _ii_client = agent.client\n"
        "    def _generate_with_api_tools(trace, instructions=None):\n"
        "        global _action_budget_exhausted\n"
        "        if len(_api_tool_calls) >= MAX_NATIVE_ACTIONS:\n"
        "            _action_budget_exhausted = True\n"
        "            print('[ii-tool-compat] native_action_budget_exhausted=' + str(MAX_NATIVE_ACTIONS), flush=True)\n"
        "            # Native control transition: an action-free turn makes\n"
        "            # ReasoningAgent invoke its own ReportBuilder over the\n"
        "            # accumulated trace/tool history. No report text is added.\n"
        "            return '</think>'\n"
        "        _cfg = _ii_client.config.llm\n"
        "        _response = _ii_client.client.chat.completions.create(\n"
        "            model=_cfg.model,\n"
        "            messages=_ii_client._get_messages(trace, instructions),\n"
        "            temperature=_cfg.temperature,\n"
        "            top_p=_cfg.top_p,\n"
        "            presence_penalty=_cfg.presence_penalty,\n"
        "            stop=_cfg.stop_sequence,\n"
        "            tools=api_tool_schemas(),\n"
        "            tool_choice='auto',\n"
        "            parallel_tool_calls=False,\n"
        "        )\n"
        "        _message = _response.choices[0].message\n"
        "        _calls = list(getattr(_message, 'tool_calls', None) or [])\n"
        "        if _calls:\n"
        "            _function = _calls[0].function\n"
        "            _api_tool_calls.append(str(_function.name))\n"
        "            print('[ii-tool-compat] api_tool_call=' + str(_function.name), flush=True)\n"
        "            return tool_call_to_native_action(_function.name, _function.arguments)\n"
        "        return str(getattr(_message, 'content', '') or '')\n"
        "    _ii_client.generate_completion = _generate_with_api_tools\n"
        "    result = asyncio.run(agent.run(is_stream=False))\n"
        "    # Compatibility diagnostics only: record whether ii parsed native\n"
        "    # actions without retaining model prose or hidden reasoning. This\n"
        "    # distinguishes an unwired provider from a model-format mismatch.\n"
        "    _turns = list(getattr(getattr(agent, 'trace', None), 'turns', []) or [])\n"
        "    _actions = []\n"
        "    _first_raw = ''\n"
        "    for _i, _turn in enumerate(_turns):\n"
        "        _output = getattr(_turn, 'output', None)\n"
        "        _action = getattr(_output, 'action', None)\n"
        "        _name = getattr(_action, 'name', None)\n"
        "        if _name:\n"
        "            _actions.append(str(_name))\n"
        "        if _i == 0:\n"
        "            _first_raw = str(getattr(_output, 'raw', '') or '')\n"
        "    _history = getattr(agent, 'tool_history', None)\n"
        "    _searched = list(_history.get_searched_queries()) if _history and hasattr(_history, 'get_searched_queries') else []\n"
        "    _visited = list(_history.get_visited_urls()) if _history and hasattr(_history, 'get_visited_urls') else []\n"
        "    _diag = {\n"
        "        'turns': len(_turns),\n"
        "        'actions': _actions,\n"
        "        'api_tool_calls': _api_tool_calls,\n"
        "        'action_budget_exhausted': _action_budget_exhausted,\n"
        "        'searched_queries': len(_searched),\n"
        "        'visited_urls': len(_visited),\n"
        "        'collected_urls': len(_collected_urls),\n"
        "        'first_has_code_fence': '```' in _first_raw,\n"
        "        'first_has_web_search': 'web_search' in _first_raw,\n"
        "        'first_has_page_visit': 'page_visit' in _first_raw,\n"
        "        'first_has_end_code': '<end_code>' in _first_raw,\n"
        "    }\n"
        "    print('[ii-diag] ' + json.dumps(_diag, sort_keys=True), flush=True)\n"
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
    # Unified native timeout: default identical to every other lane
    # (DRA_WALL_CLOCK_S, None = unlimited). II_RESEARCHER_NATIVE_TIMEOUT_S still
    # overrides. None -> subprocess.run(timeout=None); watchdog governs.
    timeout_s = _native_timeout_s("II_RESEARCHER_NATIVE_TIMEOUT_S")

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
    finally:
        driver.unlink(missing_ok=True)
    if proc.returncode != 0:
        print(
            f"ii-researcher exited {proc.returncode}; stderr tail:\n"
            f"{(proc.stderr or '')[-4000:]}"
        )
    for line in (proc.stdout or "").splitlines():
        if (
            line.startswith("[ii-diag]")
            or line.startswith("[ii-fix]")
            or line.startswith("[ii-tool-compat]")
        ):
            print(line)
    if "===REPORT===" in proc.stdout:
        report = proc.stdout.split("===REPORT===", 1)[1].strip()
        if not is_weak_report(report, min_chars=3000, min_urls=3):
            return report
        print("ii-researcher native report weak")
        print(f"ii-researcher weak report preview: {report[:1500]!r}")
        if proc.stderr:
            print(f"ii-researcher stderr tail:\n{proc.stderr[-4000:]}")
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
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
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
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")

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

    # Unified native timeout: default identical to every other lane
    # (DRA_WALL_CLOCK_S, None = unlimited). FLOWSEARCHER_NATIVE_TIMEOUT_S still
    # overrides. The old 900s default was a comparative wall clock; the shared
    # no-progress watchdog now governs termination.
    native_timeout = _native_timeout_s("FLOWSEARCHER_NATIVE_TIMEOUT_S")

    try:
        report = await asyncio.wait_for(
            run_flowsearcher(intent, model, task_id=task_id,
                             shim_url=shim, proxy_url=proxy),
            timeout=_wait_for_timeout(native_timeout),
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
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await tongyi_run(intent=intent, model=model, shim_url=shim, proxy_url=proxy)


async def _run_costorm(intent: str, model: str) -> str:
    """Co-STORM (Stanford) via clean runner module:collaborative multi-perspective research."""
    from scripts.runners.costorm_runner import run as costorm_run
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await costorm_run(intent=intent, model=model, shim_url=shim, proxy_url=proxy)


async def _run_deepagents(intent: str, model: str) -> str:
    """LangChain DeepAgents via clean runner module:LangGraph super-agent."""
    from scripts.runners.deepagents_runner import run as deepagents_run
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await deepagents_run(intent=intent, model=model, shim_url=shim, proxy_url=proxy)


async def _run_local_deep_researcher(intent: str, model: str) -> str:
    """LangChain local-deep-researcher via clean runner module."""
    from scripts.runners.local_deep_researcher_runner import run as lcdr_run
    proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
    shim = os.environ.get("SHIM_URL", "http://localhost:8081")
    return await lcdr_run(intent=intent, model=model, shim_url=shim, proxy_url=proxy)


# Manually-wired agents: these need bespoke env-var setup beyond the standard
# (intent, model, shim_url, proxy_url) contract (e.g. gpt-researcher's
# FAST_LLM/SMART_LLM split, camel-ai's tool registration). Don't touch unless
# you know what you're doing.
_MANUAL_RUNNERS = {
    # gpt-researcher: removed: subprocess runner at
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
    # dzhng remains available through scripts/run_dzhng_deep_research.py, but is
    # not a comparative runner: this adapter sends no model identifier to the
    # external :3051 service, so the requested backbone is ignored and cannot be
    # identity-probed. Re-enable only after the service accepts and attests the
    # exact requested model.
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
        proxy = os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1")
        kwargs = {"intent": intent, "model": model, "shim_url": shim, "proxy_url": proxy}
        if _supports_strict:
            kwargs["strict_sandbox"] = strict_sandbox
        if _supports_timeout:
            # Native timeout resolution for auto-discovered runners. A per-lane
            # or global *_NATIVE_TIMEOUT_S env overrides; otherwise the default
            # is the SAME for every lane (DRA_WALL_CLOCK_S). When that default
            # is None (the protocol's "no comparative wall clock") we do not
            # pass timeout_s at all, leaving the runner's own uniform outer
            # subprocess cap in force -- some runners (e.g. browser_dr) cannot
            # accept timeout_s=None. The shared no-progress watchdog terminates
            # a wedged run regardless.
            raw_timeout = (
                os.environ.get(f"{_env_prefix}_NATIVE_TIMEOUT_S")
                or os.environ.get("REGISTRY_RUNNER_NATIVE_TIMEOUT_S")
            )
            if raw_timeout:
                resolved = _budget._coerce_none(raw_timeout)
            else:
                resolved = _budget.native_timeout_default()
            # Pass None explicitly.  Omitting the kwarg resurrects each runner's
            # historical 240/420/1800s default and defeats the protocol's
            # production contract of no comparative outer wall clock.
            kwargs["timeout_s"] = None if resolved is None else int(resolved)
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

    Manual entries always win on conflict: the registry shouldn't accidentally
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


def runner_choices() -> tuple[str, ...]:
    """Return the exact current RUNNERS keys used by argparse.

    Compute this when the parser is built rather than caching a second registry:
    tests and diagnostic callers may temporarily inject a runner, and a stale
    snapshot would make the CLI disagree with the runtime map.
    """
    return tuple(sorted(RUNNERS))


# ---------------------------------------------------------------------------
# Strict-sandbox plumbing: Workstream C
# ---------------------------------------------------------------------------
#
# `--strict-sandbox` flips the arena into an audited closed-book mode where
# every cited URL must resolve to one of the four local origins
# (Magento :7770, Postmill :9999, Kiwix :8090, search shim :8081).
#
# The flag is enforced at three independent layers:
#   1. Per-adapter tool allowlist: passed as `strict_sandbox=True` to each
#      runner; runners that honour it whitelist Read/Write/Bash(curl localhost*)
#      and reject everything else. Runners that cannot honour it raise
#      `NotImplementedError` here BEFORE the run starts.
#   2. Shim-level URL gate: set SHIM_MODE=strict in the subprocess env so
#      `integrations/search_shim/app.py` returns 403 for any non-sandbox
#      target. (Not all runners use the shim, but those that do get gated.)
#   3. Post-run domain audit: `src/verifiers/sandbox_compliance_verifier`
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
# "Bash/raw HTTP can leak past the patched search" gap: see
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
    except Exception as e:  # pragma: no cover: defensive
        return {"audit_error": f"{type(e).__name__}: {e}"}


def _lane_fetch_observable(agent: str, *, egress_bracketed: bool = False) -> bool:
    """Whether `agent`'s page reads are observable for this concrete run.

    The single source of truth is config/lane_protocol.yaml. Default is False:
    an agent not declared there (or a file that will not parse) is treated as
    NOT observable, because claiming observability we cannot back up is the one
    error that leads to a false fabrication charge. This is where the protocol's
    "when unsure, do not claim observable" actually takes effect.

    The recording egress door may upgrade a protocol-false lane, but only after
    its out-of-process ``/_mark`` bracket returned success AND the launcher
    attested that the box-level direct-bypass check passed. Merely exporting
    proxy variables is not enforcement: a client can connect to a sandbox
    origin directly unless the lane uid/netns is blocked from doing so.
    """
    if egress_bracketed and _egress.enforced():
        # SSH children live in a different network namespace/machine. They are
        # observable only when an explicit reverse-tunnel/remote enforcement
        # attestation points them at this same bracketed door. Claude/opencode
        # otherwise stay local (their runners disable uninstrumented fallback).
        if agent == "codex":
            return _egress.remote_enforced()
        if agent == "claude-code" and os.environ.get(
            "CLAUDE_CODE_USE_WINDOWS", ""
        ) == "1":
            return _egress.remote_enforced()
        if agent == "opencode" and os.environ.get(
            "OPENCODE_USE_WINDOWS", ""
        ) == "1":
            return _egress.remote_enforced()
        return True
    try:
        import yaml  # local import: keep yaml off the hot import path
        cfg = yaml.safe_load((ROOT / "config" / "lane_protocol.yaml").read_text())
        lane = (cfg.get("lanes") or {}).get(agent) or {}
        return bool(lane.get("fetch_observable", False))
    except Exception as e:  # noqa: BLE001
        print(f"[deep_run] WARN: could not read fetch_observable for {agent!r}: {e}; "
              "defaulting to False (not observable)")
        return False


def _seal_report(text: str) -> dict:
    """Byte-level seal of the report the runner returned (#61).

    The scorer reads the raw report bytes. Sealing the sha256 and length at the
    moment the runner returns means any later edit to the saved report -- a
    harness that grafts a "### Sources" block, a post-hoc URL rewrite -- makes
    the sidecar sha disagree with the file, which is detectable without relying
    on check_parity's text rules to catch the specific injection. Any legitimate
    post-processing must be written to a DIFFERENT field, never folded into the
    sealed bytes.
    """
    b = (text or "").encode("utf-8")
    return {
        "sha256": hashlib.sha256(b).hexdigest(),
        "n_bytes": len(b),
        "sealed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _merge_egress_evidence(
    run_id: str,
    *,
    egress_dir: Path,
    unified_dir: Path,
) -> dict[str, object]:
    """Merge one closed egress stream into the shim-owned run stream.

    The two recorders cannot append their own start/end marks to one file:
    ``load_run_evidence`` correctly rejects multiple brackets. The egress
    process therefore writes to a per-worker sibling directory. After its end
    acknowledgement, this function validates that stream, copies its
    content-addressed blobs, and appends only fetch/block records to the still
    open shim stream. The shim then writes the single canonical end mark.
    """
    source = egress_dir / f"{run_id}.jsonl"
    target = unified_dir / f"{run_id}.jsonl"
    if not source.is_file():
        raise RuntimeError(f"egress evidence log missing: {source}")
    if not target.is_file():
        raise RuntimeError(f"shim evidence log missing before merge: {target}")

    records: list[dict] = []
    starts = ends = 0
    for lineno, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"malformed egress evidence {source}:{lineno}: {exc}"
            ) from exc
        if not isinstance(rec, dict) or rec.get("run_id") != run_id:
            raise RuntimeError(
                f"egress evidence owner mismatch at {source}:{lineno}"
            )
        if rec.get("kind") == "mark":
            starts += int(rec.get("phase") == "start")
            ends += int(rec.get("phase") == "end")
            continue
        if rec.get("kind") not in {"fetch", "block"}:
            # Service calls are intentionally not recorded by the proxy. Future
            # diagnostic record kinds must be reviewed before entering scoring.
            raise RuntimeError(
                f"unexpected egress record kind {rec.get('kind')!r}"
            )
        rec["recorder"] = "egress"
        records.append(rec)
    if starts != 1 or ends != 1:
        raise RuntimeError(
            f"egress evidence bracket invalid: starts={starts} ends={ends}"
        )

    target_records = []
    for raw in target.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            target_records.append(json.loads(raw))
    if any(
        rec.get("kind") == "mark" and rec.get("phase") == "end"
        for rec in target_records if isinstance(rec, dict)
    ):
        raise RuntimeError("shim evidence closed before egress merge")

    copied = 0
    source_blobs = egress_dir / "blobs"
    target_blobs = unified_dir / "blobs"
    for rec in records:
        digest = rec.get("body_sha256") if rec.get("kind") == "fetch" else None
        if not digest:
            continue
        src = source_blobs / str(digest)
        dst = target_blobs / str(digest)
        if not src.is_file():
            raise RuntimeError(f"egress blob missing: {src}")
        body = src.read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise RuntimeError(f"egress blob digest mismatch: {src}")
        target_blobs.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            tmp = dst.with_suffix(f".part.{os.getpid()}")
            tmp.write_bytes(body)
            tmp.replace(dst)
            copied += 1

    if records:
        with target.open("a", encoding="utf-8") as handle:
            for rec in records:
                handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return {"records": len(records), "blobs_copied": copied}


def _model_probe_endpoint(agent: str) -> tuple[str, str]:
    """The OpenAI-compatible door this lane actually uses."""
    if agent == "claude-code":
        # A user-supplied CCR URL can route to an arbitrary model and the runner
        # has no config file to attest. Probing the canonical gateway while the
        # lane uses that override would certify the wrong door.
        override = (
            os.environ.get("CLAUDE_CODE_LOCAL_CCR_URL")
            or os.environ.get("CLAUDE_CODE_CCR_URL")
            or ""
        ).strip()
        if override:
            raise RuntimeError(
                "claude-code endpoint override is not identity-attestable for "
                f"a comparative run: {override}"
            )
        raw = (
            os.environ.get("CLAUDE_CODE_GATEWAY_URL")
            or os.environ.get("DS_PROXY_URL")
            or "http://127.0.0.1:8100/v1/chat/completions"
        ).rstrip("/")
        if raw.endswith("/chat/completions"):
            raw = raw[: -len("/chat/completions")]
        return raw, "claude-code-gateway"
    if agent == "opencode":
        return (
            os.environ.get("OPENCODE_LLM_BASE_URL")
            or os.environ.get("OPENCODE_DS_PROXY")
            or os.environ.get("DS_PROXY_URL")
            or "http://localhost:8100/v1",
            "opencode-gateway",
        )
    if agent == "codex":
        # codex executes on CODEX_SSH_HOST and its driver resolves
        # CODEX_DS_PROXY against the REMOTE loopback. Probing a loopback URL
        # from THIS host would attest a different machine's proxy than the one
        # the lane's traffic uses (lane_protocol codex `routing_ssh` deviation:
        # "must be identity-probed on that remote endpoint"). Same fail-closed
        # discipline as the claude-code override above: refuse to certify the
        # wrong door. A launcher-and-remote-reachable (non-loopback) endpoint
        # is attestable and proceeds.
        endpoint = (
            os.environ.get("CODEX_DS_PROXY")
            or os.environ.get("DS_PROXY_URL")
            or "http://localhost:8100/v1"
        )
        from urllib.parse import urlparse as _urlparse
        host = (_urlparse(endpoint).hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "::1"):
            raise RuntimeError(
                "codex model identity is not attestable from this host: "
                f"CODEX_DS_PROXY={endpoint!r} is a loopback URL, but the lane "
                "runs on CODEX_SSH_HOST where that address is a DIFFERENT "
                "machine. Point CODEX_DS_PROXY at an endpoint reachable from "
                "both hosts (and identical on both), or probe on the remote."
            )
        return endpoint, "codex-gateway"
    if agent == "flowsearcher-ds":
        return (
            os.environ.get("FLOWSEARCHER_LLM_BASE_URL")
            or os.environ.get("DS_PROXY_URL")
            or "http://localhost:8100/v1",
            "flowsearcher-gateway",
        )
    return (
        os.environ.get("DS_PROXY_URL", "http://localhost:8100/v1").rstrip("/"),
        "ds-proxy",
    )


def _probe_lane_model(agent: str, declared: str) -> dict:
    from scripts.run_manifest import probe_model_identity

    endpoint, role = _model_probe_endpoint(agent)
    result = probe_model_identity(endpoint, "anything", declared)
    result["endpoint_role"] = role
    return result


def _archive_previous_outputs(out_md: Path, out_meta: Path) -> tuple[int, str | None]:
    """Move stale artifacts aside before an attempt can be mistaken for them."""
    prior_attempts = 0
    try:
        prior_attempts = int(json.loads(out_meta.read_text()).get("attempts", 0))
    except Exception:
        pass
    candidates = [
        out_md,
        out_meta,
        out_md.with_suffix(".provenance.json"),
        out_md.with_suffix(".storm-url-to-info.json"),
    ]
    existing = [p for p in candidates if p.exists()]
    if not existing:
        return prior_attempts, None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    archive = out_md.parent / "_archive" / stamp
    archive.mkdir(parents=True, exist_ok=False)
    for path in existing:
        path.replace(archive / path.name)
    return prior_attempts, str(archive)


def _timeout_contract() -> dict:
    budget = _budget.load_budget()
    override_names = sorted(
        k for k, v in os.environ.items()
        if v and (k in {"DRA_WALL_CLOCK_S", "DRA_STALL_TIMEOUT_S",
                        "REGISTRY_RUNNER_NATIVE_TIMEOUT_S"}
                  or k.endswith("_NATIVE_TIMEOUT_S"))
    )
    return {
        "wall_clock_s": budget["wall_clock_s"],
        "stall_timeout_s": budget["stall_timeout_s"],
        "operator_overrides": override_names,
        "production_comparable": not override_names and budget["wall_clock_s"] is None,
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=runner_choices())
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

    # Run identity + evidence bracketing. The uuid suffix keeps a rerun of the
    # same (agent, task, backbone) from appending onto a previous run's evidence
    # log. Exported as DRA_RUN_ID so subprocess/CLI lanes started downstream can
    # read the same id if they need it (attribution itself does not require it:
    # the shim /_mark bracket sets a process-global active run, so every /search
    # /fetch to that shim is attributed regardless of who made the call).
    run_id = f"{args.agent}__{args.task}__{args.backbone}__{uuid.uuid4().hex[:8]}"
    os.environ["DRA_RUN_ID"] = run_id
    fetch_observable = _lane_fetch_observable(args.agent)
    egress_proxy_url = os.environ.get("DRA_EGRESS_PROXY", "").strip()
    egress_control_url = os.environ.get(
        "DRA_EGRESS_CONTROL_URL", egress_proxy_url,
    ).strip().rstrip("/")
    unified_evidence_dir = Path(
        os.environ.get("SHIM_EVIDENCE_DIR", "").strip()
        or (ROOT / "logs" / "fetch")
    )
    egress_evidence_raw = os.environ.get("DRA_EGRESS_EVIDENCE_DIR", "").strip()
    egress_evidence_dir = Path(egress_evidence_raw) if egress_evidence_raw else None
    recorder_server_merge = (
        os.environ.get("DRA_EGRESS_SERVER_MERGE", "").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    enforcement_claimed = (
        os.environ.get("DRA_EGRESS_ENFORCED", "").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    if enforcement_claimed and not egress_proxy_url:
        raise RuntimeError(
            "DRA_EGRESS_ENFORCED is set but DRA_EGRESS_PROXY is empty. "
            "Refusing a run that would claim network enforcement without a door."
        )
    if egress_proxy_url and not egress_control_url:
        raise RuntimeError(
            "DRA_EGRESS_PROXY is set but DRA_EGRESS_CONTROL_URL is empty. "
            "The harness cannot bracket the out-of-process evidence owner."
        )
    if egress_proxy_url and egress_evidence_dir is None:
        raise RuntimeError(
            "DRA_EGRESS_PROXY requires DRA_EGRESS_EVIDENCE_DIR. The door must "
            "write a separate bracket stream that the harness can validate and "
            "merge before the shim closes."
        )
    if (
        egress_evidence_dir is not None
        and egress_evidence_dir.resolve() == unified_evidence_dir.resolve()
    ):
        raise RuntimeError(
            "DRA_EGRESS_EVIDENCE_DIR must differ from SHIM_EVIDENCE_DIR; two "
            "recorders in one file create duplicate start/end marks."
        )
    print(
        f"[deep_run] run_id={run_id} fetch_observable={fetch_observable} "
        f"egress={'configured' if egress_proxy_url else 'off'} "
        f"enforced={_egress.enforced()}"
    )

    suffix = f"_{args.out_suffix}" if args.out_suffix else ""
    out_dir = _run_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_md = out_dir / f"{args.agent}__{args.task}{suffix}.md"
    out_meta = out_dir / f"{args.agent}__{args.task}{suffix}.meta.json"
    prior_attempts, prior_archive = _archive_previous_outputs(out_md, out_meta)
    # Adapters that record routing provenance (e.g. claude-code writes a
    # <report>.provenance.json sidecar) need to know where the final report
    # will land; export it before the runner is invoked.
    os.environ["DEEP_RUN_REPORT_PATH"] = str(out_md)
    runner = RUNNERS[args.agent]
    t0 = time.time()
    err = None
    report = ""
    model_identity: dict[str, object] = {"state": "not_run"}
    timeout_contract = _timeout_contract()
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
                f"agent={args.agent} is marked STRICT_SANDBOX_ELIGIBLE=False: "
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

    # meta.json now carries an explicit `status`. The old world had no status
    # column and the shell driver could only ever say "timeout" (its `timeout`
    # wrapper's exit code), collapsing "framework diverged" and "box wedged"
    # into one cell. The four run outcomes are now distinct:
    #   pass    -> a report was produced
    #   fail    -> the framework raised or refused (a genuine framework failure)
    #   stalled -> no shim/LLM progress for stall_timeout_s (INFRA, rerunnable)
    #   timeout -> optional uniform wall clock exceeded (default: never)
    # `stalled`/`timeout` are written by the watchdog thread just before it
    # kills the process, so they never reach this normal-completion path.
    def _prior_attempts() -> int:
        """Attempts already recorded for this (agent, task), from the meta on disk."""
        return prior_attempts

    def _write_meta(status: str, error, elapsed_seconds: float, report_text: str,
                    *, termination: dict | None = None) -> dict:
        audit = _post_audit_sandbox(report_text or "")
        native_artifacts: dict[str, dict[str, object]] = {}
        storm_map = out_md.with_suffix(".storm-url-to-info.json")
        if storm_map.is_file():
            artifact_bytes = storm_map.read_bytes()
            native_artifacts["storm_url_to_info"] = {
                "file": storm_map.name,
                "bytes": len(artifact_bytes),
                "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
            }
        out_meta.write_text(json.dumps({
            "agent": args.agent, "task": args.task, "backbone": args.backbone,
            "run_id": run_id,
            "elapsed_seconds": round(elapsed_seconds, 1),
            "report_chars": len(report_text or ""),
            "status": status,
            "error": error,
            # How many times this (agent, task) has been attempted. `stalled` is
            # an infrastructure fault and must be rerun, so `build_truth_board`
            # refuses to score a stalled task until its reruns are spent. It read
            # `attempts` from here and nothing ever wrote it, so the default of 1
            # made the board refuse forever: the very case the rerun policy
            # exists to handle. Counted from the meta already on disk.
            "attempts": _prior_attempts() + 1,
            "strict_sandbox": bool(args.strict_sandbox),
            "fetch_observable": fetch_observable,
            "egress_evidence": {
                "configured": bool(egress_proxy_url),
                "control_url": egress_control_url or None,
                "evidence_dir": (
                    str(egress_evidence_dir) if egress_evidence_dir else None
                ),
                "bracketed": bool(egress_bracketed),
                "enforced": bool(_egress.enforced()),
                "merge": dict(egress_merge),
                "merge_error": egress_merge_error,
            },
            "network_isolation": _egress.isolation_details(),
            "worker": os.environ.get("DRA_WORKER_ID") or None,
            "run_set_id": os.environ.get("DRA_RUN_SET_ID") or None,
            # Byte-level seal of the EXACT bytes written to out_md (#61). The
            # scorer reads those bytes; if anyone later injects into the saved
            # report, this sha stops matching (verify_report_seal in
            # score_deep_answer). Must seal `report or "(empty)"` because that is
            # what out_md.write_text receives: sealing the bare report made an
            # empty run's seal (sha of "") disagree with the file's "(empty)" and
            # false-fail the verifier. Post-processing belongs in its own field,
            # never folded into the sealed bytes.
            "report_seal": _seal_report(report_text or "(empty)"),
            # Native companion artifacts retained by an adapter. STORM's
            # index-to-URL table belongs here rather than being grafted into
            # the sealed report. The scorer may verify this manifest hash and
            # resolve only the numeric indices STORM actually emitted inline;
            # unused retrievals never receive citation credit.
            "native_artifacts": native_artifacts,
            # Did we confirm, before this run started, that the agent could reach
            # every sandbox source? "skipped_by_env" means nobody checked.
            "source_check": dict(_SOURCE_CHECK),
            "model_identity": dict(model_identity),
            "timeout_contract": timeout_contract,
            "prior_output_archive": prior_archive,
            "termination": termination,
            "sandbox_audit": audit,
        }, indent=2, ensure_ascii=False))
        return audit

    def _watchdog_meta(status: str, reason: str) -> None:
        # Runs on the watchdog thread. Record the infra outcome, but do NOT
        # write out_md: a stalled run produced no report, and leaving the .md
        # absent keeps the task rerunnable and keeps a genuine (empty) framework
        # output distinguishable from an infrastructure kill.
        _write_meta(status, reason, time.time() - t0, "")

    # Evidence-bracket endpoints. The shim records its own search/fetch traffic,
    # ds_proxy owns token accounting, and the recording egress door observes page
    # reads made by requests/httpx/aiohttp/curl. The latter is a separate process,
    # so it needs its own owner bracket before proxy_env reaches the runner.
    shim_base = os.environ.get("SHIM_URL", "http://127.0.0.1:8081").rstrip("/")
    _dsp = (os.environ.get("DS_PROXY_URL") or os.environ.get("OPENAI_BASE_URL")
            or "http://localhost:8100/v1").rstrip("/")
    if _dsp.endswith("/v1"):
        _dsp = _dsp[: -len("/v1")]
    dsproxy_base = _dsp.rstrip("/")

    def _mark_payload(
        phase: str, *, observable_override: bool | None = None,
    ) -> dict:
        return {
            "run_id": run_id, "phase": phase,
            "lane": args.agent, "agent": args.agent,
            "task": args.task, "task_id": args.task,
            "backbone": args.backbone, "model": args.backbone,
            "worker": os.environ.get("DRA_WORKER_ID") or None,
            "fetch_observable": (
                fetch_observable
                if observable_override is None
                else bool(observable_override)
            ),
        }

    def _post_mark(
        base: str,
        phase: str,
        *,
        fatal: bool,
        role: str,
        direct: bool = False,
        observable_override: bool | None = None,
    ) -> dict | None:
        """POST one /_mark and return its acknowledged JSON object.

        `fatal=True` (shim start only) raises on any failure: a dark shim means
        no instrument, and running the agent anyway would drop every fetch into
        _unattributed and let the scorer fall back to the retired text_v1 pof --
        exactly the silent-regression this whole change exists to end.

        `fatal=False` (ds_proxy, and every `end`) only warns. The ds_proxy
        bracket may already be owned by scripts/glm_lane_driver.sh, in which case
        our `start` 409s; that is benign, we simply do not close a bracket we did
        not open. A ds_proxy no-op (DSPROXY_USAGE_LOG unset) still returns 200,
        so it is not a failure. A failed `end` must never mask the run's outcome.
        """
        import requests  # local: keep requests off the module import path
        session = requests.Session()
        if direct:
            # Never send the proxy's own control request through itself. This
            # remains direct even after proxy_env has made NO_PROXY empty.
            session.trust_env = False
        try:
            r = session.post(
                f"{base}/_mark",
                json=_mark_payload(
                    phase, observable_override=observable_override,
                ),
                timeout=10,
            )
        except Exception as e:  # noqa: BLE001
            if fatal:
                raise RuntimeError(
                    f"{role} /_mark {phase} -> {base} unreachable: {e}. "
                    "Refusing to run with an unbracketed evidence process."
                ) from e
            print(
                f"[deep_run] WARN: {role} /_mark {phase} -> {base} "
                f"unreachable: {e}"
            )
            return None
        if r.status_code // 100 == 2:
            try:
                body = r.json()
            except Exception:
                body = {"ok": True}
            return body if isinstance(body, dict) else {"ok": True}
        detail = (
            f"{role} /_mark {phase} -> {base} returned "
            f"{r.status_code}: {r.text[:200]}"
        )
        if fatal:
            raise RuntimeError(f"{detail}. Refusing to run.")
        print(f"[deep_run] WARN: {detail}")
        return None

    def _assert_sources_alive(base: str) -> None:
        """Refuse to start when a sandbox source cannot answer a canned query.

        The store answered nothing for the life of the project: the gateway
        dialled it by a Host it does not recognise, took the 302 into a closed
        port, and returned `[]`. An unreachable source and a source with no match
        produce identical data, so `fact` read zero on 99% of reports and that
        was read as a property of the reports.

        A run scored against a corpus it could not see is not a measurement.
        """
        import requests  # local: keep requests off the module import path
        if os.environ.get("DEEP_RUN_SKIP_SOURCE_CHECK") == "1":
            print("[deep_run] WARN: source liveness check disabled by env")
            _SOURCE_CHECK.clear()
            _SOURCE_CHECK["state"] = "skipped_by_env"
            return
        try:
            r = requests.get(f"{base}/_sources/health?fresh=true", timeout=30)
            r.raise_for_status()
            h = r.json()
        except Exception as e:  # noqa: BLE001
            _SOURCE_CHECK.clear()
            _SOURCE_CHECK["state"] = "unreachable"
            raise RuntimeError(
                f"shim /_sources/health -> {base} unreachable: {e}. Refusing to "
                "run: cannot confirm the agent can reach the corpus."
            ) from e
        _SOURCE_CHECK.clear()
        _SOURCE_CHECK["state"] = "ok" if h.get("ok") else "down"
        _SOURCE_CHECK["hits"] = {s: d.get("n_results")
                                 for s, d in (h.get("sources") or {}).items()}
        expected_backend_sha256 = os.environ.get(
            "DRA_EXPECTED_SEARCH_BACKEND_SHA256", ""
        ).strip()
        actual_backend_sha256 = str(h.get("backend_sha256") or "")
        _SOURCE_CHECK["backend_sha256"] = actual_backend_sha256 or None
        if (
            expected_backend_sha256
            and actual_backend_sha256 != expected_backend_sha256
        ):
            _SOURCE_CHECK["state"] = "code_mismatch"
            raise RuntimeError(
                "search shim code mismatch: expected backend "
                f"{expected_backend_sha256}, got "
                f"{actual_backend_sha256 or '(missing)'}. Refusing to mix "
                "search implementations in one evaluation."
            )
        if h.get("degraded"):
            # Answered, but part of its fan-out failed. Not grounds to refuse the
            # run; grounds to know afterwards which runs saw a thinner corpus.
            _SOURCE_CHECK["degraded"] = h["degraded"]
            for s, err in h["degraded"].items():
                print(f"[deep_run] WARN: source {s} degraded: {err}")
        if not h.get("ok"):
            down = h.get("down") or {}
            never = h.get("not_queried") or []
            raise RuntimeError(
                f"sandbox source(s) down for query {h.get('query')!r}: "
                f"{down or never}. Refusing to run: the agent cannot see the "
                "corpus it will be scored against."
            )

        # Liveness is not enough. A source can answer and still hand the agent
        # URLs at an origin `url_registry` does not list -- the store publishes
        # links at its `base_url`, and if that disagrees with the registry then
        # `classify` returns `host_not_in_sandbox`, which the scorer reads as
        # FABRICATED. The agent would be punished for citing exactly what the
        # search tool showed it. The shim has no registry; we do.
        hidden_gold = os.environ.get("DRA_HIDDEN_GOLD_MASKED") == "1"
        supervisor_attested = os.environ.get("DRA_SUPERVISOR_SOURCE_CHECK") == "1"
        if hidden_gold and not supervisor_attested:
            raise RuntimeError(
                "hidden-gold worker has no trusted supervisor registry preflight"
            )
        _SOURCE_CHECK["registry_attested_by_supervisor"] = supervisor_attested
        bad = [] if hidden_gold else _uncorpus_sample(h.get("sample_urls") or [])
        _SOURCE_CHECK["sample_in_corpus"] = not bad
        if bad:
            raise RuntimeError(
                "the search tool returns URLs the scorer would count as "
                f"FABRICATED: {bad[:3]}. Refusing to run. Align the site's "
                "base_url with url_registry.hosts (see "
                "internal/docs/STORE_NEVER_SEARCHED_2026-07-09.md)."
            )

    dsproxy_owned = False
    shim_marked = False
    egress_owned = False
    egress_bracketed = False
    egress_merge: dict[str, object] = {}
    egress_merge_error: str | None = None

    def _close_brackets_best_effort() -> None:
        """Post /_mark end for whatever brackets THIS run opened. Called from the
        finally (normal/exception exit), the watchdog's os._exit path, and a
        SIGTERM handler (the `timeout` wrapper in run_full_leaderboard.sh sends
        SIGTERM, on which Python runs no finally). Idempotent: mark_end on an
        already-closed run is a safe no-op, so double-calling is harmless.
        SIGKILL remains uncatchable and is covered by the shim's orphan TTL."""
        nonlocal shim_marked, dsproxy_owned, egress_owned
        nonlocal egress_merge, egress_merge_error, fetch_observable
        # The egress stream must close and merge while the canonical shim stream
        # is still open, otherwise appending page records after the shim end mark
        # correctly makes the evidence unavailable.
        if egress_owned:
            try:
                closed = _post_mark(
                    egress_control_url, "end", fatal=False, role="egress",
                    direct=True,
                )
                if not closed:
                    raise RuntimeError("egress end marker was not acknowledged")
                if recorder_server_merge:
                    merged = closed.get("merge")
                    if not isinstance(merged, dict) or merged.get("mode") != "recorder":
                        raise RuntimeError(
                            "egress recorder did not acknowledge privileged merge"
                        )
                    egress_merge = dict(merged)
                else:
                    assert egress_evidence_dir is not None
                    egress_merge = _merge_egress_evidence(
                        run_id,
                        egress_dir=egress_evidence_dir,
                        unified_dir=unified_evidence_dir,
                    )
                    egress_merge["mode"] = "worker"
            except Exception as exc:  # noqa: BLE001
                egress_merge_error = f"{type(exc).__name__}: {exc}"
                fetch_observable = _lane_fetch_observable(args.agent)
                print(
                    f"[deep_run] WARN: {egress_merge_error}; transport "
                    "observability downgraded",
                    file=sys.stderr,
                )
            egress_owned = False
        if dsproxy_owned:
            try:
                _post_mark(
                    dsproxy_base, "end", fatal=False, role="ds_proxy",
                    direct=True,
                )
            except Exception:  # noqa: BLE001
                pass
            dsproxy_owned = False
        if shim_marked:
            try:
                _post_mark(
                    shim_base, "end", fatal=False, role="shim", direct=True,
                )
            except Exception:  # noqa: BLE001
                pass
            shim_marked = False

    def _sigterm_close(signum, frame):  # noqa: ARG001
        # `timeout` (SIGTERM) would otherwise skip the finally and orphan the
        # bracket. Close it, then exit non-zero so the shell records a failed run.
        print("[deep_run] SIGTERM: closing evidence bracket before exit", file=sys.stderr)
        try:
            _write_meta(
                "timeout",
                "received SIGTERM from an external/operator wall-clock wrapper",
                time.time() - t0,
                "",
                termination={"kind": "signal", "signal": "SIGTERM", "number": signum},
            )
        except Exception:  # noqa: BLE001
            pass
        _close_brackets_best_effort()
        os._exit(EXIT_WALL_TIMEOUT)

    try:
        signal.signal(signal.SIGTERM, _sigterm_close)
    except Exception:  # noqa: BLE001
        # Not the main thread, or platform without SIGTERM: fall back to the TTL.
        pass

    watchdog = None
    if not err:
        budget = _budget.load_budget()
        watchdog = _StallWatchdog(
            stall_timeout_s=budget["stall_timeout_s"],
            wall_clock_s=budget["wall_clock_s"],
            shim_url=os.environ.get("SHIM_URL", "http://localhost:8081"),
            egress_url=egress_control_url or None,
            dsproxy_url=os.environ.get("DS_PROXY_URL") or None,
            usage_log=os.environ.get("DSPROXY_USAGE_LOG") or None,
            meta_writer=_watchdog_meta,
            t0=t0,
            on_kill=_close_brackets_best_effort,
        )
        watchdog.start()
    if not err:
        # Open the evidence brackets BEFORE the runner so its /search and /fetch
        # land inside the bracket. Shim first and LOUD: on failure stop the
        # watchdog and re-raise rather than run a dark, unattributed agent. This
        # raise is deliberately OUTSIDE the runner try/except below, which would
        # otherwise swallow a dark instrument into a normal "fail" meta.
        try:
            # Before the bracket: a live instrument pointed at a dead corpus
            # records a clean, attributable, meaningless run.
            _assert_sources_alive(shim_base)
            model_identity.clear()
            model_identity.update(_probe_lane_model(args.agent, args.backbone))
            if not model_identity.get("ok"):
                raise RuntimeError(
                    "per-run model identity probe failed: "
                    f"{model_identity.get('error') or model_identity}"
                )
            # The door is bracketed with a direct, trust_env=False control
            # session BEFORE its proxy variables enter the runner environment.
            # A configured-but-dark door is always fatal: otherwise page reads
            # would land in _unattributed.jsonl while the run looked instrumented.
            if egress_proxy_url:
                egress_owned = _post_mark(
                    egress_control_url,
                    "start",
                    fatal=True,
                    role="egress",
                    direct=True,
                    # This is an attestation candidate. It becomes the concrete
                    # run claim only after this call returns 2xx below.
                    observable_override=_lane_fetch_observable(
                        args.agent, egress_bracketed=True,
                    ),
                )
                egress_bracketed = bool(egress_owned)
                fetch_observable = _lane_fetch_observable(
                    args.agent, egress_bracketed=egress_owned,
                )
            _post_mark(
                shim_base, "start", fatal=True, role="shim", direct=True,
            )
            shim_marked = True
        except Exception as e:  # noqa: BLE001
            if watchdog is not None:
                watchdog.stop()
            _close_brackets_best_effort()
            # Leave a sidecar. Without one, an abort BEFORE the agent ran -- a
            # store returning 503, a dark shim -- looks to the board exactly like
            # a framework that produced no report, and the lane is scored 0 for a
            # fault that was ours. `infra_abort` is rerunnable, like `stalled`.
            try:
                _write_meta("infra_abort", str(e), time.time() - t0, "")
            except Exception:  # noqa: BLE001 -- never mask the original failure
                pass
            raise
        dsproxy_owned = _post_mark(
            dsproxy_base, "start", fatal=False, role="ds_proxy", direct=True,
        )
        if egress_proxy_url:
            # This is the last mutation before runner dispatch. Every in-process
            # client and every subprocess env copy now sees the canonical eight
            # proxy variables (including empty NO_PROXY).
            _egress.apply_proxy_env(os.environ)
            _egress.install_aiohttp_trust_env()

    if not err:
        try:
            # A short report used to trigger one automatic retry
            # (DEEP_RUN_SHORT_RETRY_MIN_CHARS, default 3000 chars). Report length
            # is a proxy for `completeness`, which is scored, and
            # `config/lane_protocol.yaml` forbids "retrying or repairing a report
            # based on any scored quantity". It is the same construct as the
            # smolagents repair loop deleted on 2026-07-08, differing only in
            # that it was applied to every lane rather than one. Uniform unfairness
            # is still a scored-quantity retry: it hands every framework a second
            # attempt precisely when the first would have scored badly, and the
            # board cannot say which attempt it is looking at.
            #
            # Errors are still retried by the runners themselves. Silence is not.
            report = await _invoke_runner_once()
        except NotImplementedError as e:
            err = f"strict_sandbox unsupported: {e}"
            report = f"(runner refused strict-sandbox: {e})"
        except Exception as e:
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            report = f"(runner error: {type(e).__name__}: {e})"
        finally:
            # Disarm the watchdog before we touch the output files: the run has
            # returned (progress will now cease legitimately) and a late stall
            # verdict would be wrong.
            if watchdog is not None:
                watchdog.stop()
            # Close the brackets. Both best-effort: mark_end is idempotent (an
            # already-closed / never-opened run is a safe no-op) and a failed
            # close must not mask the run's real status. We only close ds_proxy
            # if OUR start opened it, so a 409 (glm_lane_driver already owns it)
            # does not make us clear another owner's bracket. Same helper the
            # SIGTERM/watchdog paths use, so every exit closes identically.
            _close_brackets_best_effort()
    if egress_merge_error and not err:
        err = (
            "egress evidence finalization failed: " + egress_merge_error
        )
    if not err:
        # Runners deliberately catch their own framework exceptions so they can
        # return an honest, recognizable stub. Treating that return as
        # meta.status=pass made failure rates and queue completion lie even
        # though the scorer later recognized the text as degenerate.
        try:
            from src.eval.report_stubs import classify_report

            report_class = classify_report(report)
        except Exception as exc:  # noqa: BLE001
            err = f"could not classify returned report: {type(exc).__name__}: {exc}"
        else:
            if report_class != "ok":
                first_line = str(report or "(empty)").strip().splitlines()[0][:200]
                err = f"runner returned {report_class}: {first_line}"
    elapsed = time.time() - t0

    status = "fail" if err else "pass"
    sandbox_audit = _write_meta(status, err, elapsed, report)
    out_md.write_text(report or "(empty)")

    print(f"[deep_run] done in {elapsed:.0f}s, {len(report)} chars → {out_md.name} [{status}]")
    if sandbox_audit.get("policy_violation"):
        print(
            f"[deep_run] sandbox audit: {len(sandbox_audit.get('non_sandbox_urls') or [])}"
            f" non-sandbox URL(s) cited"
        )
    if err:
        print(f"[deep_run] ERR: {err.splitlines()[0]}")
        return EXIT_FRAMEWORK_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
