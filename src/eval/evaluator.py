"""ArenaEvaluator -- the v3 reward-function entry point for AgentRL and friends.

Given a task_id and a report markdown, returns a single composite score in
[0, 1] plus a per-dim breakdown. Used by:

  * AgentRL (treats `evaluate(report).composite` as the per-episode reward).
  * The periodic leaderboard rebuild (`build_deep_leaderboard_v3.py`).
  * Workstream D's weight-fitting (consumes per-dim scores for regression).

Two modes:

  * `fast` -- deterministic-only. Skips the four LLM-judge dims
    (depth / rigor / style / checklist) and sets them to a neutral 0.5.
    Sub-1 second on a real report. This is the mode AgentRL runs every
    rollout, so it MUST be cheap and non-flaky.

  * `full` -- runs every verifier, including the LLM-judge dims via
    `asyncio.gather`. Roughly 30s per report (judge latency dominates).
    Suitable for periodic eval or for the leaderboard rebuild script.

The async path keeps the LLM-judge dims concurrent so end-to-end latency
is ~max(depth, rigor, style, checklist) rather than the sum. The
synchronous `evaluate()` is a thin wrapper that drives `asyncio.run` so
callers without an event loop don't need to know about it.

Design choices worth flagging:
  * The four LLM-judge verifiers are duck-typed (any class with `verify`
    that returns a `VerifierResult`). This lets Workstream D swap in a
    fitted-weight judge or a calibration probe without touching this file.
  * If a verifier raises, we log it and substitute a `score=0.5,
    evidence='verifier_unavailable'` placeholder. The eval pipeline must
    never crash AgentRL mid-rollout — that would corrupt the replay
    buffer with NaN rewards.
  * The task spec is loaded from
    `data/tasks/deep_research/cross_site_deep/<task_id>.json`. If the
    file is missing (e.g. for a synthetic AgentRL task), we still run the
    deterministic dims that don't need task config (depth/rigor/style)
    and substitute neutral scores for the dims that do (coverage / checklist).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional


# Repo root = parents[2] from this file (src/eval/evaluator.py → repo).
_REPO_ROOT = Path(__file__).resolve().parents[2]

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    composite: float
    breakdown: dict
    per_dim: dict     # {dim: score in [0,1]}
    policy: dict      # {sandbox_violations: int, reachability: float, quote_match: float}
    mode: str = "full"
    judge_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "composite": round(float(self.composite), 6),
            "breakdown": self.breakdown,
            "per_dim": {k: round(float(v), 6) for k, v in self.per_dim.items()},
            "policy": self.policy,
            "mode": self.mode,
            "judge_errors": list(self.judge_errors),
        }


# Default neutral score for LLM-judge dims in fast mode and on verifier
# failure. Matches the soft-floor philosophy: never zero, never max, just
# uninformative — so the downstream reward signal degrades gracefully
# rather than spiking on judge unavailability.
_NEUTRAL = 0.5

# The 4 dims that go through LLM-judge verifiers (skipped in fast mode).
_JUDGE_DIMS = ("depth", "rigor", "style", "checklist")

# All 6 quality dims plus the 2 policy dims that feed the soft-floor.
_ALL_DIMS = ("coverage", "depth", "rigor", "style", "checklist", "spec")


def _task_spec_path(task_id: str) -> Path:
    """Where the task JSON lives. cross_site_deep is the v3 task tier."""
    return _REPO_ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / f"{task_id}.json"


def _load_task_config(task_id: str) -> dict[str, Any]:
    p = _task_spec_path(task_id)
    if not p.exists():
        logger.warning("task spec %s missing — using empty config", p)
        return {"task_id": task_id, "intent": ""}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("failed to load task spec %s: %s", p, e)
        return {"task_id": task_id, "intent": ""}


def _safe_verify(verifier: Any, task_config: dict, answer: str) -> tuple[float, dict]:
    """Run a verifier defensively. Returns (score in [0,1], details).

    Any exception or missing field falls back to a neutral 0.5 with the
    error captured in details. We never let a verifier crash bubble up
    into the AgentRL reward path.
    """
    try:
        vr = verifier.verify(task_config=task_config, answer=answer)
        s = float(getattr(vr, "score", 0.0) or 0.0)
        # Clip into [0, 1] — some legacy verifiers can return slightly out-of-range.
        s = max(0.0, min(1.0, s))
        details = dict(getattr(vr, "details", {}) or {})
        return s, details
    except Exception as e:
        logger.warning("verifier %s failed: %s", type(verifier).__name__, e)
        return _NEUTRAL, {"error": f"{type(e).__name__}: {e}"}


class ArenaEvaluator:
    """v3 reward-function evaluator. Drop-in callable for AgentRL.

    Parameters
    ----------
    task_id : str
        Identifies the task spec on disk (looked up under
        `data/tasks/deep_research/cross_site_deep/`).
    mode : "fast" | "full"
        - fast: skip LLM-judge dims (depth/rigor/style/checklist) — sub-1s,
          deterministic. AgentRL uses this every rollout.
        - full: run all 6 verifiers via asyncio.gather, ~30s. Periodic
          leaderboard rebuild uses this.
    weights : dict | None
        Override WEIGHTS_V3. Workstream D will pass fitted weights here
        once the human-pref data is collected.
    """

    def __init__(
        self,
        task_id: str,
        mode: Literal["fast", "full"] = "full",
        weights: Optional[dict[str, float]] = None,
    ) -> None:
        self.task_id = task_id
        if mode not in ("fast", "full"):
            raise ValueError(f"mode must be 'fast' or 'full', got {mode!r}")
        self.mode = mode
        self.weights = dict(weights) if weights else None
        self._task_config = _load_task_config(task_id)

    # ------------------------------------------------------------------ sync
    def evaluate(self, report_md: str, trace: Optional[dict] = None) -> EvalResult:
        """Synchronous entry point. Runs `evaluate_async` under a fresh loop.

        Use this from non-async callers (AgentRL reward function, the
        leaderboard build script, ad-hoc REPL eval). If you already have
        an event loop, prefer `evaluate_async`.
        """
        try:
            return asyncio.run(self.evaluate_async(report_md, trace=trace))
        except RuntimeError as e:
            # `asyncio.run` raises if a loop is already running (e.g. in
            # a Jupyter cell). Fall back to a nested loop via
            # asyncio.new_event_loop. We do not attempt to use the
            # existing loop because that would block the caller's coroutines.
            if "asyncio.run() cannot be called from a running event loop" in str(e):
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(self.evaluate_async(report_md, trace=trace))
                finally:
                    loop.close()
            raise

    # ----------------------------------------------------------------- async
    async def evaluate_async(self, report_md: str, trace: Optional[dict] = None) -> EvalResult:
        """Run all configured verifiers, fold into composite_v3_softfloor.

        In fast mode the four LLM-judge dims are short-circuited to a
        neutral 0.5 — no judge calls, no async overhead.
        """
        # Lazy import to avoid a hard dependency cycle when this module is
        # imported by harness code that hasn't loaded the verifier tree.
        from src.scoring.leaderboard_composites import (
            WEIGHTS_V3,
            composite_v3_softfloor,
            composite_v3_breakdown,
        )

        task_config = self._task_config
        report_md = report_md or ""

        # --- Deterministic dims (always run) ---
        # coverage: URLCoverageVerifier (deterministic, no LLM)
        # spec:     MarkdownReportVerifier (deterministic)
        det_per_dim: dict[str, float] = {}
        det_details: dict[str, dict] = {}

        try:
            from src.verifiers.url_coverage_verifier import URLCoverageVerifier
            cov_score, cov_details = _safe_verify(URLCoverageVerifier(), task_config, report_md)
        except Exception as e:
            logger.warning("url_coverage import failed: %s", e)
            cov_score, cov_details = _NEUTRAL, {"error": str(e)}
        det_per_dim["coverage"] = cov_score
        det_details["coverage"] = cov_details

        try:
            from src.verifiers.markdown_report_verifier import MarkdownReportVerifier
            spec_score, spec_details = _safe_verify(MarkdownReportVerifier(), task_config, report_md)
        except Exception as e:
            logger.warning("markdown_report import failed: %s", e)
            spec_score, spec_details = _NEUTRAL, {"error": str(e)}
        det_per_dim["spec"] = spec_score
        det_details["spec"] = spec_details

        # --- LLM-judge dims (fast: skipped, full: concurrent) ---
        judge_errors: list[str] = []
        if self.mode == "fast":
            for d in _JUDGE_DIMS:
                det_per_dim[d] = _NEUTRAL
                det_details[d] = {"skipped": True, "reason": "fast_mode"}
        else:
            judge_results = await self._run_judge_dims_async(task_config, report_md)
            for d, (s, details, err) in judge_results.items():
                det_per_dim[d] = s
                det_details[d] = details
                if err:
                    judge_errors.append(f"{d}:{err}")

        # --- Policy signals (reach / quote_match) for the soft floor ---
        # We need quote_match in [0,1] for the soft-floor formula. In fast
        # mode (and when no trace is provided), we approximate it from the
        # report's link density vs the citation requirement. The full mode
        # uses the real quote_match verifier if available; otherwise the
        # same approximation.
        quote_match, reach = await self._compute_policy_signals(task_config, report_md, trace)

        # --- Build the score dict in the shape composite_v3_softfloor expects ---
        score_dict: dict[str, Any] = {
            "coverage":   det_per_dim["coverage"],
            "depth":      det_per_dim["depth"],
            "rigor":      det_per_dim["rigor"],
            "style":      det_per_dim["style"],
            "checklist":  det_per_dim["checklist"],
            "spec":       det_per_dim["spec"],
            "quote_match": {"score": quote_match},
            "reachability": reach,
        }

        weights = self.weights or WEIGHTS_V3
        if weights is WEIGHTS_V3 or weights == WEIGHTS_V3:
            composite = composite_v3_softfloor(score_dict)
            breakdown = composite_v3_breakdown(score_dict)
        else:
            # Custom weights — compute by hand so we honour the override.
            rs = 0.5 + 0.5 * float(quote_match)
            rs = max(0.5, min(1.0, rs))
            per_dim_contrib = {d: w * det_per_dim[d] for d, w in weights.items()}
            q_value = sum(per_dim_contrib.values())
            composite = rs * q_value
            breakdown = {
                "reach_soft": round(rs, 6),
                "q_value": round(q_value, 6),
                "per_dim_contribution": {k: round(v, 6) for k, v in per_dim_contrib.items()},
                "composite": round(composite, 6),
                "weights": dict(weights),
            }

        policy = {
            "sandbox_violations": int(spec_details.get("sandbox_violations", 0) or 0),
            "reachability": float(reach),
            "quote_match": float(quote_match),
        }

        return EvalResult(
            composite=float(composite),
            breakdown=breakdown,
            per_dim={k: det_per_dim[k] for k in _ALL_DIMS},
            policy=policy,
            mode=self.mode,
            judge_errors=judge_errors,
        )

    # --------------------------------------------------- helpers (LLM dims)
    async def _run_judge_dims_async(
        self, task_config: dict, report_md: str
    ) -> dict[str, tuple[float, dict, Optional[str]]]:
        """Concurrently run the four LLM-judge dims. Each is wrapped in
        a thread executor because the underlying judge_client uses a
        sync HTTP SDK (not awaitable). Returns
        ``{dim: (score, details, error|None)}``."""

        async def _run(name: str, verifier_factory: Any) -> tuple[str, tuple[float, dict, Optional[str]]]:
            try:
                verifier = verifier_factory()
            except Exception as e:
                return name, (_NEUTRAL, {"error": f"factory_failed: {e}"}, str(e))
            try:
                loop = asyncio.get_event_loop()
                s, d = await loop.run_in_executor(None, _safe_verify, verifier, task_config, report_md)
                err = d.get("error") if isinstance(d, dict) else None
                return name, (s, d, err)
            except Exception as e:
                return name, (_NEUTRAL, {"error": f"{type(e).__name__}: {e}"}, str(e))

        # Lazy imports so missing/broken verifiers degrade gracefully.
        def _depth():
            from src.verifiers.depth_verifier import DepthVerifier
            return DepthVerifier()

        def _rigor():
            from src.verifiers.rigor_verifier import RigorVerifier
            return RigorVerifier()

        def _style():
            from src.verifiers.style_verifier import StyleVerifier
            return StyleVerifier()

        def _checklist():
            from src.verifiers.checklist_verifier import ChecklistVerifier
            return ChecklistVerifier()

        coros = [
            _run("depth", _depth),
            _run("rigor", _rigor),
            _run("style", _style),
            _run("checklist", _checklist),
        ]
        results = await asyncio.gather(*coros)
        return dict(results)

    # ------------------------------------------------- helpers (policy)
    async def _compute_policy_signals(
        self,
        task_config: dict,
        report_md: str,
        trace: Optional[dict],
    ) -> tuple[float, float]:
        """Return (quote_match, reachability), both in [0, 1].

        Preferred path: use the QuoteMatchVerifier and URLReachabilityVerifier
        if they're importable AND the trace provides what they need. If
        not (no trace, no quoted-spans field, fast-mode timing budget),
        fall back to a deterministic approximation:

          * quote_match ≈ min(1, n_markdown_links / min_citations_required)
            -- a citation-density proxy that scales the soft floor
            sensibly without needing the sandbox to be reachable.
          * reachability ≈ same proxy (we cannot probe URLs from the
            evaluator process; the proper signal lives in the score JSON
            written by `score_deep_answer.py` on the bench host).

        This conservative fallback keeps the evaluator usable in any
        environment, including AgentRL training where the sandbox isn't
        live and the only ground truth is the markdown the agent emitted.
        """
        # Try the real verifiers first.
        qm_real: Optional[float] = None
        reach_real: Optional[float] = None
        if trace is not None:
            qm_real = self._try_quote_match(trace)
            reach_real = self._try_reachability(trace)

        # Fallback proxy: count markdown links / required citations.
        if qm_real is None or reach_real is None:
            n_links = report_md.count("](")
            min_cites = int(
                ((task_config.get("markdown_spec") or {}).get("min_citations") or 30)
            )
            proxy = 0.0 if min_cites <= 0 else min(1.0, n_links / min_cites)
            if qm_real is None:
                qm_real = proxy
            if reach_real is None:
                reach_real = proxy

        return float(qm_real), float(reach_real)

    def _try_quote_match(self, trace: dict) -> Optional[float]:
        try:
            qm = trace.get("quote_match") if isinstance(trace, dict) else None
            if isinstance(qm, dict):
                v = qm.get("score")
                if v is not None:
                    return float(v)
            elif isinstance(qm, (int, float)):
                return float(qm)
        except Exception:
            return None
        return None

    def _try_reachability(self, trace: dict) -> Optional[float]:
        try:
            r = trace.get("url_reachability") if isinstance(trace, dict) else None
            if isinstance(r, dict):
                v = r.get("score")
                if v is not None:
                    return float(v)
            elif isinstance(r, (int, float)):
                return float(r)
        except Exception:
            return None
        return None
