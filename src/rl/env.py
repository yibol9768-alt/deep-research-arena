"""Research environment for the C1 action space.

The environment is deliberately small and deterministic. GPU inference and
live browsing are outside this module; real web access is represented by the
``SandboxBackend`` protocol and the local tests use ``MockSandboxBackend``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from src.eval.rollout import Rollout
from src.verifiers.citation_format import canonicalize_url


Hit = dict[str, Any]


class SandboxBackend(Protocol):
    def search(self, query: str) -> list[Hit]:
        """Return deterministic search hits for ``query``."""

    def fetch(self, url: str) -> str:
        """Return full page text for ``url``."""


class HttpSandboxBackend:
    """HTTP adapter for the training-box search shim.

    The shim (``integrations/search_shim/app.py``) speaks a Tavily-compatible
    surface: ``POST /search`` for retrieval and ``POST /extract`` for full-page
    fetches. ``requests`` is imported lazily so this package stays importable on
    machines without the live sandbox. Response handling is tolerant of the few
    shapes small shims emit, but the defaults target the Tavily contract.

    ``max_results`` controls search breadth (the reward's search-breadth signal
    saturates around 8 distinct results, so the default is generous). The
    rollout's own in-memory trace (``fetched_urls`` / ``retrieved_snippets``,
    recorded by ``ResearchEnv._do_read``) is what proof-of-fetch verifies, so no
    X-Run-Id log correlation is required for native env rollouts.
    """

    def __init__(
        self,
        shim_url: str,
        *,
        max_results: int = 10,
        bearer_token: str = "sandbox",
        timeout: float = 60.0,
    ) -> None:
        self.shim_url = shim_url.rstrip("/")
        self.max_results = int(max_results)
        self.bearer_token = bearer_token
        self.timeout = float(timeout)

    def _post_json(self, path: str, payload: dict[str, Any]) -> Any:
        try:
            import requests
        except Exception as exc:  # pragma: no cover - exercised on training box
            raise RuntimeError(
                "HTTP sandbox backend requires requests and the training sandbox"
            ) from exc

        headers = {}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        response = requests.post(
            f"{self.shim_url}/{path.lstrip('/')}",
            json=payload,
            headers=headers,
            timeout=self.timeout,
            # The shim is a localhost service; never route it through an HTTP
            # proxy (training boxes often set http_proxy for HuggingFace, which
            # would send localhost calls to a proxy that cannot reach WSL).
            proxies={"http": None, "https": None},
        )
        response.raise_for_status()
        return response.json()

    def search(self, query: str) -> list[Hit]:
        data = self._post_json(
            "search",
            {"query": query, "max_results": self.max_results},
        )
        if isinstance(data, list):
            raw_hits = data
        elif isinstance(data, dict):
            raw_hits = data.get("results") or data.get("hits") or []
        else:
            raw_hits = []
        return [_normalize_hit(hit) for hit in raw_hits if _normalize_hit(hit).get("url")]

    def fetch(self, url: str) -> str:
        # Tavily /extract takes a list of URLs and returns raw_content per URL.
        data = self._post_json(
            "extract",
            {"urls": [url], "extract_depth": "advanced", "format": "markdown"},
        )
        if isinstance(data, dict):
            results = data.get("results")
            if isinstance(results, list) and results:
                first = results[0]
                if isinstance(first, dict):
                    return str(
                        first.get("raw_content")
                        or first.get("content")
                        or first.get("text")
                        or ""
                    )
            # tolerate a flat single-page shape from non-Tavily shims
            return str(data.get("text") or data.get("content") or data.get("raw_content") or "")
        return str(data or "")


class MockSandboxBackend:
    """Deterministic offline sandbox for unit tests."""

    def __init__(
        self,
        pages: dict[str, str],
        index: dict[str, list[str | Hit]],
    ) -> None:
        self.pages = {str(url): str(text) for url, text in pages.items()}
        self.index = {
            _norm_query(query): list(urls)
            for query, urls in index.items()
        }

    def search(self, query: str) -> list[Hit]:
        key = _norm_query(query)
        raw_hits = self.index.get(key)
        if raw_hits is None:
            raw_hits = self._substring_hits(key)
        return [self._hit(row) for row in (raw_hits or [])]

    def fetch(self, url: str) -> str:
        return self.pages.get(str(url), "")

    def _substring_hits(self, key: str) -> list[str | Hit]:
        if not key:
            return []
        for indexed_query, hits in self.index.items():
            if key in indexed_query or indexed_query in key:
                return hits
        return []

    def _hit(self, row: str | Hit) -> Hit:
        if isinstance(row, dict):
            hit = _normalize_hit(row)
            if "snippet" not in hit:
                hit["snippet"] = self.pages.get(str(hit.get("url", "")), "")[:240]
            return hit
        url = str(row)
        return {
            "url": url,
            "title": url.rsplit("/", 1)[-1] or url,
            "snippet": self.pages.get(url, "")[:240],
        }


@dataclass(slots=True)
class Search:
    query: str


@dataclass(slots=True)
class Open:
    url: str


@dataclass(slots=True)
class Read:
    pass


@dataclass(slots=True)
class WriteMemory:
    note: str


@dataclass(slots=True)
class ReadMemory:
    pass


@dataclass(slots=True)
class Cite:
    url: str


@dataclass(slots=True)
class CallTool:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Finalize:
    report_md: str


Action = Search | Open | Read | WriteMemory | ReadMemory | Cite | CallTool | Finalize


@dataclass
class _EnvState:
    search_results: list[Hit] = field(default_factory=list)
    current_url: str | None = None
    current_page_text: str = ""
    memory: list[str] = field(default_factory=list)
    cited_urls: list[str] = field(default_factory=list)
    fetched_urls: list[str] = field(default_factory=list)
    retrieved_snippets: dict[str, str] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_state_deltas: list[dict[str, Any]] = field(default_factory=list)
    sessions: list[dict[str, Any]] = field(default_factory=list)
    report_md: str = ""
    step_count: int = 0
    done: bool = False
    last_observation: dict[str, Any] = field(default_factory=dict)


class ResearchEnv:
    """Step-able research environment that accumulates a ``Rollout``."""

    def __init__(
        self,
        task_config: dict[str, Any],
        backend: SandboxBackend,
        *,
        max_tool_calls: int = 40,
        max_tokens: int | None = None,
    ) -> None:
        self.task_config = dict(task_config)
        self.backend = backend
        self.max_tool_calls = int(max_tool_calls)
        if self.max_tool_calls <= 0:
            raise ValueError("max_tool_calls must be positive")
        self.max_tokens = max_tokens
        self._state = _EnvState()
        # Built lazily on first use so ``import src.rl.env`` never imports the
        # tool module (which is authored separately and may pull lazy deps).
        self._registry: Any = None
        self._registry_built = False

    def reset(self) -> dict[str, Any]:
        self._state = _EnvState()
        # Force a fresh registry for the new episode (the ToolContext binds the
        # live backend / task config, both stable across resets, but rebuilding
        # keeps the seam clean and matches the design's reset() lifecycle).
        self._registry = None
        self._registry_built = False
        return self._observe(last_action="reset")

    def _tool_ctx(self) -> Any:
        """Build a ToolContext bound to this env's backend + plumbing.

        Imported lazily (like ``backend_from_task_config``) so the tool module
        is only loaded when a CallTool is actually dispatched.
        """
        from .tools import ToolContext  # lazy: avoids import cycle / lazy deps

        return ToolContext(
            backend=self.backend,
            task_config=self.task_config,
            fetch=lambda url: self._truncate_text(self.backend.fetch(url)),
            canonicalize=canonicalize_url,
            extras={
                "run_id": self.task_config.get("run_id"),
                "shim_url": (self.task_config.get("acquisition") or {}).get("shim_url"),
            },
        )

    def _get_registry(self) -> Any:
        """Return the per-task tool registry, building it lazily on first use."""
        if self._registry_built:
            return self._registry
        self._registry_built = True
        try:
            from .tools import build_tool_registry  # lazy
            self._registry = build_tool_registry(self.task_config, self._tool_ctx())
        except Exception:
            # The tool module may be absent or fail to import in minimal envs;
            # a missing registry degrades CallTool to a graceful no-op, never a
            # crash, and leaves the default Search/Open/Read path untouched.
            self._registry = None
        return self._registry

    def step(self, action: Action) -> tuple[dict[str, Any], bool, dict[str, Any]]:
        if self._state.done:
            obs = self._observe(last_action=_action_name(action))
            return obs, True, {"ok": False, "error": "episode_done"}

        info: dict[str, Any] = {"ok": True}
        self._state.step_count += 1
        self._state.sessions.append({
            "step": self._state.step_count,
            "action": _action_payload(action),
        })

        if isinstance(action, Finalize):
            self._state.report_md = self._truncate_text(str(action.report_md))
            self._state.done = True
            obs = self._observe(last_action="finalize")
            return obs, True, info

        if not self._can_use_tool():
            self._state.done = True
            info.update({"ok": False, "error": "tool_call_cap_exceeded"})
            obs = self._observe(last_action=_action_name(action))
            return obs, True, info

        if isinstance(action, Search):
            self._do_search(action, info)
        elif isinstance(action, Open):
            self._do_open(action, info)
        elif isinstance(action, Read):
            self._do_read(info)
        elif isinstance(action, WriteMemory):
            self._do_write_memory(action, info)
        elif isinstance(action, ReadMemory):
            self._do_read_memory(info)
        elif isinstance(action, Cite):
            self._do_cite(action, info)
        elif isinstance(action, CallTool):
            self._do_call_tool(action, info)
        else:  # pragma: no cover - type checkers should prevent this
            info.update({"ok": False, "error": f"unknown_action:{type(action).__name__}"})

        obs = self._observe(last_action=_action_name(action))
        return obs, self._state.done, info

    def to_rollout(self) -> Rollout:
        task_id = str(
            self.task_config.get("task_id")
            or self.task_config.get("id")
            or "unknown_task"
        )
        return Rollout(
            task_id=task_id,
            report_md=self._state.report_md,
            retrieved_snippets=dict(self._state.retrieved_snippets),
            fetched_urls=list(self._state.fetched_urls),
            tool_calls=[dict(call) for call in self._state.tool_calls],
            step_count=int(self._state.step_count),
            sessions=[dict(row) for row in self._state.sessions],
            trace=self._build_trace(),
        )

    def _build_trace(self) -> dict[str, Any]:
        # Additive: the P3 write-action key is only present when a CallTool
        # actually recorded a state_delta, so the default-path trace stays
        # byte-identical to {"memory": [...], "cited_urls": [...]}.
        trace: dict[str, Any] = {
            "memory": list(self._state.memory),
            "cited_urls": list(self._state.cited_urls),
        }
        if self._state.tool_state_deltas:
            trace["tool_state_deltas"] = [dict(row) for row in self._state.tool_state_deltas]
        return trace

    @property
    def done(self) -> bool:
        return self._state.done

    @property
    def tool_calls_used(self) -> int:
        return len(self._state.tool_calls)

    def _can_use_tool(self) -> bool:
        return len(self._state.tool_calls) < self.max_tool_calls

    def _record_tool(
        self,
        endpoint: str,
        query: str | None,
        n_results: int,
        ok: bool,
        **extra: Any,
    ) -> None:
        call = {
            "endpoint": endpoint,
            "query": query,
            "n_results": int(n_results),
            "ok": bool(ok),
        }
        call.update(extra)
        self._state.tool_calls.append(call)

    def _do_search(self, action: Search, info: dict[str, Any]) -> None:
        query = str(action.query).strip()
        try:
            hits = [_normalize_hit(hit) for hit in self.backend.search(query)]
            hits = [hit for hit in hits if str(hit.get("url") or "").strip()]
            self._state.search_results = hits
            self._record_tool("/search", query, len(hits), True)
            info["n_results"] = len(hits)
        except Exception as exc:
            self._state.search_results = []
            self._record_tool("/search", query, 0, False, error=str(exc))
            info.update({"ok": False, "error": str(exc)})

    def _do_open(self, action: Open, info: dict[str, Any]) -> None:
        url = str(action.url).strip()
        self._state.current_url = url
        self._state.current_page_text = ""
        ok = bool(url)
        self._record_tool("/open", url, 1 if ok else 0, ok)
        if not ok:
            info.update({"ok": False, "error": "empty_url"})

    def _do_read(self, info: dict[str, Any]) -> None:
        url = self._state.current_url
        if not url:
            self._record_tool("/fetch", None, 0, False, error="no_open_url")
            info.update({"ok": False, "error": "no_open_url"})
            return
        try:
            text = self._truncate_text(self.backend.fetch(url))
            self._state.current_page_text = text
            ok = bool(text)
            if ok:
                self._state.fetched_urls.append(url)
                self._state.retrieved_snippets[canonicalize_url(url)] = text
            self._record_tool("/fetch", url, 1 if ok else 0, ok)
            info["url"] = url
        except Exception as exc:
            self._record_tool("/fetch", url, 0, False, error=str(exc))
            info.update({"ok": False, "error": str(exc)})

    def _do_write_memory(self, action: WriteMemory, info: dict[str, Any]) -> None:
        note = self._truncate_text(str(action.note).strip())
        if note:
            self._state.memory.append(note)
        self._record_tool("/memory/write", note, 1 if note else 0, bool(note))
        if not note:
            info.update({"ok": False, "error": "empty_note"})

    def _do_read_memory(self, info: dict[str, Any]) -> None:
        self._record_tool("/memory/read", None, len(self._state.memory), True)
        info["memory"] = list(self._state.memory)

    def _do_cite(self, action: Cite, info: dict[str, Any]) -> None:
        url = str(action.url).strip()
        if url:
            self._state.cited_urls.append(url)
        self._record_tool("/cite", url, 1 if url else 0, bool(url))
        if not url:
            info.update({"ok": False, "error": "empty_url"})

    def _do_call_tool(self, action: CallTool, info: dict[str, Any]) -> None:
        name = str(action.name or "").strip()
        registry = self._get_registry()
        tool = registry.get(name) if registry else None
        if tool is None:
            # disallowed/unknown name: graceful no-op, NOT a crash. The episode
            # continues; only the tool-call budget slot is consumed by the
            # surrounding step() bookkeeping (this records a failed call).
            self._record_tool(f"/tool/{name or 'unknown'}", name, 0, False, error="tool_not_allowed")
            info.update({"ok": False, "error": "tool_not_allowed", "tool": name})
            return
        try:
            result = tool.run(self._tool_ctx(), dict(action.args or {}))
        except Exception as exc:
            self._record_tool(f"/tool/{name}", name, 0, False, error=str(exc))
            info.update({"ok": False, "error": str(exc), "tool": name})
            return
        # Fold ToolResult into the SAME grounding store (reward unchanged by
        # construction): retrieved_snippets / fetched_urls are the exact slots
        # _do_read writes, so tool-acquired (url, text) is credited identically.
        for url, text in (result.snippets or {}).items():
            u = str(url).strip()
            if not u or not str(text or ""):
                continue
            self._state.retrieved_snippets[canonicalize_url(u)] = self._truncate_text(str(text))
        for url in (result.fetched_urls or []):
            u = str(url).strip()
            if u:
                self._state.fetched_urls.append(u)
        if result.hits:
            normalized = [_normalize_hit(h) for h in result.hits]
            self._state.search_results = [h for h in normalized if h.get("url")]
        if result.state_delta is not None:
            self._state.tool_state_deltas.append({"tool": name, "delta": result.state_delta})
        if result.display:
            self._state.current_page_text = result.display
        n = int(result.n_results) or len(result.snippets or {}) or len(result.hits or [])
        self._record_tool(f"/tool/{name}", name, n, bool(result.ok), tool=name)
        info.update({"ok": bool(result.ok), "tool": name})
        if result.error:
            info["error"] = result.error

    def _truncate_text(self, text: str) -> str:
        if self.max_tokens is None:
            return text
        words = text.split()
        if len(words) <= self.max_tokens:
            return text
        return " ".join(words[: self.max_tokens])

    def _observe(self, *, last_action: str) -> dict[str, Any]:
        prompt = (
            self.task_config.get("prompt")
            or self.task_config.get("intent")
            or self.task_config.get("question")
            or ""
        )
        obs = {
            "task_id": str(self.task_config.get("task_id") or self.task_config.get("id") or ""),
            "task_config": dict(self.task_config),
            "prompt": str(prompt),
            "last_action": last_action,
            "search_results": [dict(hit) for hit in self._state.search_results],
            "current_url": self._state.current_url,
            "current_page_text": self._state.current_page_text,
            "memory": list(self._state.memory),
            "cited_urls": list(self._state.cited_urls),
            "fetched_urls": list(self._state.fetched_urls),
            "retrieved_snippets": dict(self._state.retrieved_snippets),
            "tool_calls_used": len(self._state.tool_calls),
            "tool_calls_remaining": max(0, self.max_tool_calls - len(self._state.tool_calls)),
            "step_count": self._state.step_count,
            "done": self._state.done,
            "report_md": self._state.report_md,
        }
        self._state.last_observation = obs
        return obs


def backend_from_task_config(
    task_config: dict[str, Any],
    *,
    shim_url: str | None = None,
    mock: SandboxBackend | None = None,
    **kw: Any,
) -> SandboxBackend:
    """Build the acquisition backend a task asks for (default ``search_shim``).

    Reads the optional top-level ``acquisition`` block from ``task_config``
    (``{"backend"/"modalities", "shim_url", "max_results"}``); when the block is
    absent the modality defaults to ``shim`` so every existing task reproduces
    today's :class:`HttpSandboxBackend` byte-for-byte. ``mock`` is a
    dependency-injection override returned verbatim for offline tests.

    The factory lives in :mod:`src.rl.backends`; it is imported lazily here so
    ``import src.rl.env`` never pulls in the (lazily playwright-backed) browser
    module unless a caller actually selects it.
    """
    from .backends import make_backend_from_task  # lazy: avoids import cycle

    return make_backend_from_task(task_config, shim_url=shim_url, mock=mock, **kw)


def _norm_query(query: str) -> str:
    return " ".join(str(query).lower().split())


def _normalize_hit(hit: Any) -> Hit:
    if isinstance(hit, dict):
        url = str(hit.get("url") or hit.get("link") or "").strip()
        return {
            "url": url,
            "title": str(hit.get("title") or url),
            "snippet": str(hit.get("snippet") or hit.get("content") or ""),
        }
    url = str(hit).strip()
    return {"url": url, "title": url, "snippet": ""}


def _action_name(action: Action) -> str:
    name = type(action).__name__
    return name[:1].lower() + name[1:]


def _action_payload(action: Action) -> dict[str, Any]:
    if isinstance(action, Search):
        return {"type": "search", "query": action.query}
    if isinstance(action, Open):
        return {"type": "open", "url": action.url}
    if isinstance(action, Read):
        return {"type": "read"}
    if isinstance(action, WriteMemory):
        return {"type": "write_memory", "note": action.note}
    if isinstance(action, ReadMemory):
        return {"type": "read_memory"}
    if isinstance(action, Cite):
        return {"type": "cite", "url": action.url}
    if isinstance(action, CallTool):
        return {"type": "call_tool", "name": action.name, "args": dict(action.args or {})}
    if isinstance(action, Finalize):
        return {"type": "finalize", "report_chars": len(action.report_md)}
    return {"type": type(action).__name__}


__all__ = [
    "Action",
    "CallTool",
    "Cite",
    "Finalize",
    "Hit",
    "HttpSandboxBackend",
    "MockSandboxBackend",
    "Open",
    "Read",
    "ReadMemory",
    "ResearchEnv",
    "SandboxBackend",
    "Search",
    "WriteMemory",
    "backend_from_task_config",
]
