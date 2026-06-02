"""Real-browser deep-research arena adapter (slug ``browser-dr``).

This adapter brings the **real-browser acquisition modality** onto the Deep
Research leaderboard so the board is not search-shim-only. Every other adapter
(the 13 framework/baseline slugs) acquires evidence through the Tavily-compatible
search shim; ``browser-dr`` instead drives a live Playwright browser over the
sandbox sites (Magento ``__SHOPPING__`` / Postmill ``__REDDIT__`` / Kiwix
``__WIKIPEDIA__``) and emits a **deep-research MARKDOWN report** with inline
``[title](url)`` citations -- NOT the WebArena JSON answer that
``src/agents/glm_react_agent.py`` produces.

Why this is correct by construction
------------------------------------
The grounding reward (``src/eval/evaluator.py::_compute_ground_signals``) is
modality-agnostic: it reads only ``rollout.retrieved_snippets`` (``dict[url] ->
page_text``) plus the cited URLs (``s_ground = 0.6*f1_claim + 0.4*r_resolve``)
and never inspects *how* the bytes were fetched. So driving the SAME text-only
C1 action space (Search/Open/Read/WriteMemory/ReadMemory/Cite/Finalize) over a
``ResearchEnv`` whose backend is a :class:`BrowserSandboxBackend` lands the
browser's DOM ``innerText`` into the exact ``retrieved_snippets`` slot the shim
path uses, earning identical reward. Only the *backend* differs; the action
space, env, policy, and reward are unchanged.

Module-import contract (registry stays boot-safe)
-------------------------------------------------
The module top-level imports ONLY ``BaseAgent``/``AgentResult``/``AgentServices``
and stdlib, exactly like the 13 existing adapters. Playwright and the RL env /
backend are imported **lazily inside** :meth:`BrowserDRAgent.run` (and the
factory's lazy ``browser`` branch). Consequences:

* ``import integrations.agents`` and ``get_agent("browser-dr")`` succeed on a
  plain system ``python3`` with no playwright installed -- the slug stays
  registered and importable offline.
* If playwright is genuinely missing, the lazy import raises ``ImportError`` at
  ``run()`` time; :meth:`run` catches it and returns
  ``AgentResult(error="ImportError: ...")`` so the harness writes a
  ``.md.error`` and skips scoring, never crashing the boot path. This mirrors
  the ``get_agent`` docstring contract: framework deps surface as ImportError on
  instantiation/run, not at registry import.

The LLM seam (offline-safe default + real-model attach point)
------------------------------------------------------------
A *trained* report policy needs a GPU/LLM that cannot be called offline. The
adapter therefore takes an optional ``policy`` (dependency injection): when
omitted it falls back to the deterministic, GPU-free :class:`MockPolicy`
(``src/rl/policy.py``), which drives Search -> Open -> Read -> Finalize and emits
a grounded ``[label](url)`` markdown report from the pages it actually browsed.
That keeps the import/registration checks and an end-to-end offline run green.

To attach a REAL model post-pilot, pass ``policy=QwenPolicy(...)`` (from
``src/rl/qwen_policy.py``) -- it speaks the identical ``Policy`` protocol
(``act(observation) -> Action``), so the env loop, backend, and reward contract
are unchanged; swapping the policy changes only WHO chooses the actions, never
how reward is computed.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from integrations.agents.base import AgentResult, AgentServices, BaseAgent


# Sentinel substrings the policy may emit; resolved to localhost sandbox bases by
# BrowserSandboxBackend._resolve (ports 7770 / 9999 / 8090 per the grounded env
# facts). Kept here only so run()'s task_config can advertise the sites; the
# actual resolution lives in the backend.
_SANDBOX_SLUG_TO_SENTINEL = {
    "shopping": "__SHOPPING__",
    "reddit": "__REDDIT__",
    "wikipedia": "__WIKIPEDIA__",
    "wiki": "__WIKIPEDIA__",
}


class BrowserDRAgent(BaseAgent):
    """Deep-research arena agent that acquires evidence via a real browser.

    Drives the text-only C1 action space over a :class:`ResearchEnv` whose
    backend is a :class:`BrowserSandboxBackend` (real Playwright DOM), then
    returns ``env.to_rollout().report_md`` as the leaderboard markdown. Scored
    by the existing ``ArenaEvaluator`` path -- identical reward to the shim
    adapters for identical acquired ``(url, page_text)`` pairs.
    """

    name = "browser-dr"
    venv = None  # in-process; the browser runs inside this process via Playwright

    def __init__(
        self,
        *,
        policy: Any | None = None,
        backend: Any | None = None,
        max_tool_calls: int = 40,
    ) -> None:
        """Construct the adapter.

        Args:
            policy: Optional :class:`src.rl.policy.Policy` implementation
                (``act(observation) -> Action``). Defaults to the offline,
                GPU-free :class:`MockPolicy`. Pass a real ``QwenPolicy`` here
                post-pilot to attach a trained model -- the env/backend/reward
                are unchanged.
            backend: Optional :class:`src.rl.env.SandboxBackend` override
                (dependency injection). When given, it is used verbatim and the
                browser/playwright path is skipped entirely; this lets an
                offline test pass a ``MockSandboxBackend`` and assert that
                ``run()`` yields a non-empty grounded markdown report with no
                playwright, no network, and no GPU. When omitted, ``run()``
                lazily builds a real :class:`BrowserSandboxBackend`.
            max_tool_calls: Per-episode tool-call budget for the env (default
                40, matching the native rollout cap).
        """
        self._injected_policy = policy
        self._injected_backend = backend
        self._max_tool_calls = int(max_tool_calls)

    async def run(self, intent: str, services: AgentServices) -> AgentResult:
        t0 = time.time()
        try:
            # --- LAZY imports (heavy / env deps) keep registry boot-safe -------
            from src.rl.env import ResearchEnv
            from src.rl.runner import run_episode

            backend = self._injected_backend
            if backend is None:
                # Real-browser channel. Probe playwright eagerly here so a box
                # without it surfaces a clean ImportError AgentResult (the
                # documented graceful-degradation contract) instead of a hollow,
                # ungrounded report: BrowserSandboxBackend.fetch swallows its own
                # lazy-import failure (it returns "" on any fetch error), so
                # without this probe a missing playwright would silently yield a
                # zero-page report rather than a typed error the harness can skip.
                try:
                    import playwright  # noqa: F401  (lazy probe; not used directly)
                except Exception as exc:  # ImportError on a box without playwright
                    raise ImportError(
                        "playwright not installed; browser modality unavailable "
                        "(install playwright + chromium, or inject a backend for "
                        f"offline runs): {exc}"
                    ) from exc

                # make_backend's "browser" branch builds a BrowserSandboxBackend;
                # playwright is launched lazily on the first fetch/search.
                from src.rl.backends import make_backend

                backend = make_backend(
                    "browser",
                    site_map=self._site_map_from_services(services),
                    shim_url=services.search_url,  # delegate SERP breadth to the shim
                )

            policy = self._injected_policy
            if policy is None:
                # Offline-safe default: deterministic, GPU-free policy that
                # produces a grounded [label](url) report from browsed pages.
                # Replace with QwenPolicy(...) for a trained model (same protocol).
                from src.rl.policy import MockPolicy

                policy = MockPolicy(quality_level="high")

            task_config = self._build_task_config(intent)

            env = ResearchEnv(
                task_config,
                backend,
                max_tool_calls=self._max_tool_calls,
            )
            try:
                rollout = run_episode(task_config, env, policy)
            finally:
                # Tear down the browser/playwright handles if the backend owns
                # any (BrowserSandboxBackend / ComputerUseBackend expose close()).
                closer = getattr(backend, "close", None)
                if callable(closer) and self._injected_backend is None:
                    try:
                        closer()
                    except Exception:
                        pass

            report_md = rollout.report_md or ""
            if not report_md.strip():
                return AgentResult(
                    markdown="",
                    elapsed_s=time.time() - t0,
                    error="EmptyReport: browser rollout produced no report markdown",
                    metadata={
                        "modality": "browser",
                        "fetched_urls": list(rollout.fetched_urls),
                        "pages_browsed": len(rollout.fetched_urls),
                    },
                )

            return AgentResult(
                markdown=report_md,
                elapsed_s=time.time() - t0,
                metadata={
                    "modality": "browser",
                    "fetched_urls": list(rollout.fetched_urls),
                    "pages_browsed": len(rollout.fetched_urls),
                    "tool_calls": int(rollout.step_count),
                    "cited_urls": list((rollout.trace or {}).get("cited_urls") or []),
                },
            )
        except Exception as exc:  # noqa: BLE001 — must never raise out of run()
            # Per the BaseAgent contract the harness uses the typed result to
            # decide whether to score; a missing playwright surfaces here as a
            # clean ImportError-flavored AgentResult, not a crash.
            return AgentResult(
                markdown="",
                elapsed_s=time.time() - t0,
                error=f"{type(exc).__name__}: {exc}",
                metadata={"modality": "browser"},
            )

    # ------------------------------------------------------------------ helpers
    def _build_task_config(self, intent: str) -> dict[str, Any]:
        """Minimal task_config for the env.

        The env only reads ``task_id`` / ``prompt`` / ``intent`` (for the
        observation) and the optional ``acquisition`` block (read by the
        backend factory, irrelevant here since we pass the backend directly).
        We advertise ``acquisition.backend = "browser"`` for provenance and a
        small ``markdown_spec`` so the report shape is documented; neither is
        load-bearing for the reward, which only credits retrieved_snippets.
        """
        return {
            "task_id": self._derive_task_id(intent),
            "intent": intent,
            "prompt": intent,
            "acquisition": {"modalities": ["browser"], "backend": "browser"},
            "markdown_spec": {"min_citations": 1, "min_paragraphs": 1},
        }

    @staticmethod
    def _derive_task_id(intent: str) -> str:
        import hashlib

        digest = hashlib.sha1(intent.strip().encode("utf-8")).hexdigest()[:12]
        return f"browser_dr_{digest}"

    @staticmethod
    def _site_map_from_services(services: AgentServices) -> Optional[dict[str, str]]:
        """Translate ``services.sandbox_hosts`` into BrowserSandboxBackend's
        sentinel-keyed ``site_map`` (``{"SHOPPING": "http://host:port", ...}``).

        ``sandbox_hosts`` is ``{"shopping": "localhost:7770", "reddit":
        "localhost:9999", "wiki": "localhost:8090"}`` (bare host:port). We map
        slugs to the SHOPPING/REDDIT/WIKIPEDIA sentinel keys the backend's
        ``_resolve`` expects and prefix ``http://`` when no scheme is present.
        Returns ``None`` when no hosts are provided so the backend falls back to
        its grounded localhost defaults.
        """
        hosts = getattr(services, "sandbox_hosts", None) or {}
        if not hosts:
            return None
        slug_to_key = {
            "shopping": "SHOPPING",
            "reddit": "REDDIT",
            "wiki": "WIKIPEDIA",
            "wikipedia": "WIKIPEDIA",
        }
        site_map: dict[str, str] = {}
        for slug, host in hosts.items():
            key = slug_to_key.get(str(slug).strip().lower())
            if not key or not host:
                continue
            base = str(host).strip()
            if not base.startswith(("http://", "https://")):
                base = f"http://{base}"
            site_map[key] = base
        return site_map or None


__all__ = ["BrowserDRAgent"]
