"""ArenaEvaluator -- the v3 reward-function entry point for AgentRL and friends.

Given a task_id and a report markdown, returns a single composite score in
[0, 1] plus a per-dim breakdown. Used by:

  * AgentRL (treats `evaluate(report).composite` as the per-episode reward).
  * The periodic leaderboard rebuild (`build_deep_leaderboard_v3.py`).
  * Workstream D's weight-fitting (consumes per-dim scores for regression).

Two modes:

  * `fast` -- deterministic-only. Skips the four LLM-judge dims
    (depth / rigor / style / checklist) and DROPS them from the weighted
    composite, renormalizing the remaining weights over the deterministic
    dims (coverage / spec) — it does NOT flatline them to 0.5, which would
    freeze ~70% of the weight mass to a constant and crush the reward's
    dynamic range (fatal for GRPO advantages). Sub-1 second on a real
    report. This is the mode AgentRL runs every rollout, so it MUST be
    cheap, non-flaky, AND carry real signal variance.

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
import re
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
    signal_health: str = "ok"
    reward_terms: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "composite": round(float(self.composite), 6),
            "breakdown": self.breakdown,
            "per_dim": {k: round(float(v), 6) for k, v in self.per_dim.items()},
            "policy": self.policy,
            "mode": self.mode,
            "judge_errors": list(self.judge_errors),
        }
        if self.signal_health != "ok":
            out["signal_health"] = self.signal_health
        if self.reward_terms:
            out["reward_terms"] = self.reward_terms
        return out


# Default neutral score for LLM-judge dims in fast mode and on verifier
# failure. Matches the soft-floor philosophy: never zero, never max, just
# uninformative — so the downstream reward signal degrades gracefully
# rather than spiking on judge unavailability.
_NEUTRAL = 0.5

# The 4 dims that go through LLM-judge verifiers (skipped in fast mode).
_JUDGE_DIMS = ("depth", "rigor", "style", "checklist")

# Public V3 leaderboard dims. Keep evaluate() and evaluate_async() on this
# shape; the rollout reward expands _ALL_DIMS below.
_LEADERBOARD_DIMS = ("coverage", "depth", "rigor", "style", "checklist", "spec")

# All rollout quality dims plus policy dims that feed the soft-floor.
_ALL_DIMS = (
    "coverage",
    "depth",
    "rigor",
    "style",
    "checklist",
    "spec",
    "source_diversity",
    "perspective_balance",
    "longform_quality",
    "bilingual",
)


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


def _safe_verify(
    verifier: Any,
    task_config: dict,
    answer: str,
    **verify_kwargs: Any,
) -> tuple[float, dict]:
    """Run a verifier defensively. Returns (score in [0,1], details).

    Any exception or missing field falls back to a neutral 0.5 with the
    error captured in details. We never let a verifier crash bubble up
    into the AgentRL reward path.
    """
    try:
        vr = verifier.verify(task_config=task_config, answer=answer, **verify_kwargs)
        s = float(getattr(vr, "score", 0.0) or 0.0)
        # Clip into [0, 1] — some legacy verifiers can return slightly out-of-range.
        s = max(0.0, min(1.0, s))
        details = dict(getattr(vr, "details", {}) or {})
        return s, details
    except Exception as e:
        logger.warning("verifier %s failed: %s", type(verifier).__name__, e)
        return _NEUTRAL, {"error": f"{type(e).__name__}: {e}"}


def _dim_not_measurable(details: dict) -> bool:
    """True when a deterministic dim should be dropped and renormalized."""
    if not isinstance(details, dict):
        return False
    if details.get("error"):
        return True
    if details.get("applicable") is False:
        return True
    # A verifier that no-ops because the task lacks its spec marks the dim with
    # a `skipped` note (e.g. MarkdownReportVerifier on a task with no
    # markdown_spec). That dim carries no signal and must be dropped, not
    # folded into the weighted quality at its placeholder score.
    if details.get("skipped"):
        return True
    reason = str(details.get("reason") or "").lower()
    if not reason:
        return False
    markers = (
        "degenerate",
        "empty_answer",
        "word_count_too_low",
        "answer_starts_with",
        "no sandbox citations",
        # URLCoverageVerifier.fail() reasons for tasks with no golden pool /
        # url_coverage spec. These return score=0.0 with a `reason` (and no
        # `error` key), so without these markers a non-applicable coverage dim
        # would freeze ~18% of WEIGHTS_RL mass at a constant 0.0.
        "no url_coverage spec",
        "golden_pool_path missing",
        "golden pool not found",
        "empty must_cite_urls",
    )
    return any(marker in reason for marker in markers)


def _execution_goal(task_config: dict[str, Any]) -> dict[str, Any] | None:
    goal = task_config.get("execution_goal") or task_config.get("state_diff") or {}
    if not isinstance(goal, dict):
        return None
    expected = goal.get("expected_state")
    return goal if isinstance(expected, dict) else None


def _execution_blend_weight(goal: dict[str, Any]) -> float:
    raw = goal.get("state_weight", goal.get("alpha", 0.5))
    try:
        weight = float(raw)
    except (TypeError, ValueError):
        weight = 0.5
    return max(0.0, min(1.0, weight))


_SUPPORT_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "of", "to", "in", "on", "for", "with", "and", "or", "but", "as", "at",
    "by", "from", "this", "that", "these", "those", "it", "its", "their",
    "his", "her", "our", "your", "we", "you", "they", "has", "have", "had",
    "do", "does", "did", "will", "would", "can", "could", "should", "may",
    "might", "shall", "must", "into", "near", "about", "than", "then",
}

_GENERIC_SUPPORT_TOKENS = {
    "article", "audio", "battery", "comfort", "content", "detail", "details",
    "document", "documents", "explains", "forum", "headphone", "headphones",
    "information", "listener", "listeners", "ordinary", "page", "pages",
    "practical", "product", "report", "source", "sources", "sound", "thread",
    "users", "value", "wikipedia",
}


def _support_tokens(text: str) -> list[str]:
    return [
        t for t in re.findall(r"[a-z0-9]{3,}", (text or "").lower())
        if t not in _SUPPORT_STOP
    ]


def _unique_ordered(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _longest_common_contiguous(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for tok_a in a:
        cur = [0] * (len(b) + 1)
        for j, tok_b in enumerate(b, start=1):
            if tok_a == tok_b:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _best_window_support(claim_terms: list[str], page_terms: list[str]) -> dict[str, Any]:
    claim_unique = _unique_ordered(claim_terms)
    claim_set = set(claim_unique)
    if not claim_set or not page_terms:
        return {
            "support": 0.0,
            "overlap": 0.0,
            "specific_recall": 0.0,
            "jaccard": 0.0,
        }

    specific = {
        t for t in claim_set
        if t not in _GENERIC_SUPPORT_TOKENS and not t.isdigit()
    }
    window_len = min(len(page_terms), max(12, len(claim_unique) * 2))
    starts = range(0, max(1, len(page_terms) - window_len + 1))
    best = {
        "support": 0.0,
        "overlap": 0.0,
        "specific_recall": 0.0,
        "jaccard": 0.0,
    }

    for start in starts:
        window_set = set(page_terms[start:start + window_len])
        if not window_set:
            continue
        overlap_set = claim_set & window_set
        overlap = len(overlap_set) / len(claim_set)
        union = claim_set | window_set
        jaccard = len(overlap_set) / len(union) if union else 0.0
        if specific:
            specific_recall = len(specific & window_set) / len(specific)
        else:
            specific_recall = 0.0
        support = 0.45 * overlap + 0.45 * specific_recall + 0.10 * jaccard
        if specific_recall < 0.30:
            support = min(support, 0.49)
        if support > best["support"]:
            best = {
                "support": support,
                "overlap": overlap,
                "specific_recall": specific_recall,
                "jaccard": jaccard,
            }
    return best


def _claim_page_support(claim: str, page_text: str) -> dict[str, Any]:
    claim_terms = _support_tokens(claim)
    page_terms = _support_tokens(page_text)
    scores = _best_window_support(claim_terms, page_terms)
    longest = _longest_common_contiguous(claim_terms, page_terms)
    verbatim_ratio = longest / len(claim_terms) if claim_terms else 0.0
    verbatim = bool(len(claim_terms) >= 8 and longest >= 8 and verbatim_ratio >= 0.80)
    support = float(scores["support"])
    if verbatim:
        support = min(support, 0.50)
    if support >= 0.62:
        leaf = 1.0
    elif support >= 0.35:
        leaf = 0.5
    else:
        leaf = 0.0
    return {
        "leaf": leaf,
        "support": support,
        "overlap": float(scores["overlap"]),
        "specific_recall": float(scores["specific_recall"]),
        "jaccard": float(scores["jaccard"]),
        "verbatim": verbatim,
        "verbatim_ratio": verbatim_ratio,
    }


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

    def evaluate_rollout(
        self,
        rollout: Any,
        *,
        process: Optional[dict] = None,
        penalties: Optional[dict] = None,
        rubric_snapshot: Optional[dict] = None,
    ) -> EvalResult:
        """Synchronous RL reward entry point for grounded rollouts."""
        try:
            return asyncio.run(self._evaluate_rollout_async(
                rollout,
                process=process,
                penalties=penalties,
                rubric_snapshot=rubric_snapshot,
            ))
        except RuntimeError as e:
            if "asyncio.run() cannot be called from a running event loop" in str(e):
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(self._evaluate_rollout_async(
                        rollout,
                        process=process,
                        penalties=penalties,
                        rubric_snapshot=rubric_snapshot,
                    ))
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

        if self.mode == "fast":
            composite, breakdown = self._fast_mode_composite(
                det_per_dim,
                weights,
                quote_match,
            )
        elif weights is WEIGHTS_V3 or weights == WEIGHTS_V3:
            composite = composite_v3_softfloor(score_dict)
            breakdown = composite_v3_breakdown(score_dict)
        else:
            # Custom weights, full mode — compute by hand so we honour the override.
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
            per_dim={k: det_per_dim[k] for k in _LEADERBOARD_DIMS},
            policy=policy,
            mode=self.mode,
            judge_errors=judge_errors,
        )

    def _fast_mode_composite(
        self,
        det_per_dim: dict[str, float],
        weights: dict[str, float],
        quote_match: float,
    ) -> tuple[float, dict[str, Any]]:
        present = [d for d in _LEADERBOARD_DIMS if d not in _JUDGE_DIMS]
        w_present = {d: float(weights.get(d, 0.0)) for d in present}
        w_total = sum(w_present.values()) or 1.0
        w_eff = {d: w / w_total for d, w in w_present.items()}
        rs = max(0.5, min(1.0, 0.5 + 0.5 * float(quote_match)))
        per_dim_contrib = {d: w_eff[d] * det_per_dim[d] for d in present}
        q_value = sum(per_dim_contrib.values())
        composite = rs * q_value
        return composite, {
            "reach_soft": round(rs, 6),
            "q_value": round(q_value, 6),
            "per_dim_contribution": {k: round(v, 6) for k, v in per_dim_contrib.items()},
            "composite": round(composite, 6),
            "weights_effective": {k: round(v, 6) for k, v in w_eff.items()},
            "dims_dropped": list(_JUDGE_DIMS),
            "mode": "fast",
        }

    async def _evaluate_rollout_async(
        self,
        rollout: Any,
        *,
        process: Optional[dict] = None,
        penalties: Optional[dict] = None,
        rubric_snapshot: Optional[dict] = None,
    ) -> EvalResult:
        """Grounded RL variant. Existing evaluate_async remains the leaderboard path."""
        from src.eval.reward_terms import compute_penalties, compute_process
        from src.scoring.leaderboard_composites import (
            WEIGHTS_RL,
            composite_v3_rl,
            composite_v3_rl_breakdown,
        )

        task_config = dict(self._task_config)
        if getattr(rollout, "pages_browsed", 0):
            task_config["pages_browsed"] = int(rollout.pages_browsed)
        report_md = getattr(rollout, "report_md", "") or ""

        det_per_dim: dict[str, float] = {}
        det_details: dict[str, dict] = {}
        degraded_dims: list[str] = []

        try:
            from src.verifiers.url_coverage_verifier import URLCoverageVerifier
            cov_score, cov_details = _safe_verify(URLCoverageVerifier(), task_config, report_md)
        except Exception as e:
            logger.warning("url_coverage import failed: %s", e)
            cov_score, cov_details = _NEUTRAL, {"error": str(e)}
        if _dim_not_measurable(cov_details):
            degraded_dims.append("coverage")
        det_per_dim["coverage"] = cov_score
        det_details["coverage"] = cov_details

        try:
            from src.verifiers.markdown_report_verifier import MarkdownReportVerifier
            spec_score, spec_details = _safe_verify(MarkdownReportVerifier(), task_config, report_md)
        except Exception as e:
            logger.warning("markdown_report import failed: %s", e)
            spec_score, spec_details = _NEUTRAL, {"error": str(e)}
        if _dim_not_measurable(spec_details):
            degraded_dims.append("spec")
        det_per_dim["spec"] = spec_score
        det_details["spec"] = spec_details

        try:
            from src.verifiers.source_diversity_verifier import SourceDiversityVerifier
            sd_score, sd_details = _safe_verify(SourceDiversityVerifier(), task_config, report_md)
        except Exception as e:
            logger.warning("source_diversity import failed: %s", e)
            sd_score, sd_details = _NEUTRAL, {"error": str(e)}
        if _dim_not_measurable(sd_details):
            degraded_dims.append("source_diversity")
        det_per_dim["source_diversity"] = sd_score
        det_details["source_diversity"] = sd_details

        try:
            from src.verifiers.perspective_balance_verifier import PerspectiveBalanceVerifier
            pb_score, pb_details = _safe_verify(
                PerspectiveBalanceVerifier(),
                task_config,
                report_md,
                deterministic_only=True,
            )
        except Exception as e:
            logger.warning("perspective_balance import failed: %s", e)
            pb_score, pb_details = _NEUTRAL, {"error": str(e)}
        if _dim_not_measurable(pb_details):
            degraded_dims.append("perspective_balance")
        det_per_dim["perspective_balance"] = pb_score
        det_details["perspective_balance"] = pb_details

        try:
            from src.verifiers.longform_quality_verifier import LongformQualityVerifier
            lf_score, lf_details = _safe_verify(LongformQualityVerifier(), task_config, report_md)
        except Exception as e:
            logger.warning("longform_quality import failed: %s", e)
            lf_score, lf_details = _NEUTRAL, {"error": str(e)}
        if _dim_not_measurable(lf_details):
            degraded_dims.append("longform_quality")
        det_per_dim["longform_quality"] = lf_score
        det_details["longform_quality"] = lf_details

        try:
            from src.verifiers.bilingual_quality_verifier import BilingualQualityVerifier
            bilingual_score, bilingual_details = _safe_verify(
                BilingualQualityVerifier(),
                task_config,
                report_md,
                deterministic_only=True,
            )
        except Exception as e:
            logger.warning("bilingual import failed: %s", e)
            bilingual_score, bilingual_details = _NEUTRAL, {"error": str(e)}
        if _dim_not_measurable(bilingual_details):
            degraded_dims.append("bilingual")
        det_per_dim["bilingual"] = bilingual_score
        det_details["bilingual"] = bilingual_details

        judge_errors: list[str] = []
        if self.mode == "fast":
            for d in _JUDGE_DIMS:
                det_per_dim[d] = _NEUTRAL
                det_details[d] = {"skipped": True, "reason": "fast_mode"}
        else:
            from src.verifiers.citation_format import canonicalize_url

            raw_evidence = getattr(rollout, "retrieved_snippets", None) or {}
            evidence = {
                canonicalize_url(str(url)): str(snippet or "")[:500]
                for url, snippet in list(raw_evidence.items())[:16]
                if str(url).strip() and str(snippet or "").strip()
            }
            judge_results = await self._run_judge_dims_rollout_async(
                task_config,
                report_md,
                rubric_snapshot=rubric_snapshot,
                evidence=evidence,
            )
            for d, (s, details, err) in judge_results.items():
                det_per_dim[d] = s
                det_details[d] = details
                if err:
                    judge_errors.append(f"{d}:{err}")
                    degraded_dims.append(d)

        s_ground, reach, ground_details = await self._compute_ground_signals(task_config, rollout)
        if ground_details.get("source") != "proof_of_fetch":
            degraded_dims.append("quote_match")

        execution_goal = _execution_goal(task_config)
        execution_score: float | None = None
        execution_terms: dict[str, Any] | None = None
        execution_mode = "none"
        if execution_goal is not None:
            execution_mode = str(execution_goal.get("reward_mode") or "state_diff_only")
            if execution_mode not in {"state_diff_only", "blend"}:
                execution_mode = "state_diff_only"
            try:
                from src.verifiers.state_diff_verifier import StateDiffVerifier

                vr = StateDiffVerifier().verify(task_config=task_config, rollout=rollout)
                execution_score = max(0.0, min(1.0, float(vr.score)))
                execution_terms = {
                    "score": round(float(execution_score), 6),
                    "passed": bool(vr.passed),
                    "mode": execution_mode,
                    "details": dict(vr.details or {}),
                }
            except Exception as exc:
                execution_score = 0.0
                execution_terms = {
                    "score": 0.0,
                    "passed": False,
                    "mode": execution_mode,
                    "details": {"error": f"{type(exc).__name__}: {exc}"},
                }
                degraded_dims.append("execution")

        process_terms = process if process is not None else compute_process(rollout, task_config)
        if process_terms.get("signal_health") == "degraded":
            degraded_dims.append("process")
        proof_grounded = ground_details.get("source") == "proof_of_fetch"
        rl_strict = bool(getattr(self, "_rl_strict", False))
        # In strict RL mode we always count citations against the fetch trace so
        # that citing URLs the policy never fetched is scored as fabrication
        # (n_resolved < n_cited) regardless of which grounding branch ran.
        count_cites = proof_grounded or rl_strict
        penalty_terms = penalties if penalties is not None else compute_penalties(
            rollout,
            task_config,
            s_ground=s_ground,
            n_cited=int(ground_details.get("n_cited", 0) or 0) if count_cites else 0,
            n_resolved=int(ground_details.get("n_resolved", 0) or 0) if count_cites else 0,
        )
        if penalty_terms.get("nullify") and not proof_grounded and not rl_strict:
            penalty_terms = dict(penalty_terms)
            penalty_terms["nullify"] = False
            penalty_terms["nullify_suppressed_reason"] = "not_proof_of_fetch"

        score_dict: dict[str, Any] = {
            "coverage": det_per_dim["coverage"],
            "depth": det_per_dim["depth"],
            "rigor": det_per_dim["rigor"],
            "style": det_per_dim["style"],
            "checklist": det_per_dim["checklist"],
            "spec": det_per_dim["spec"],
            "source_diversity": det_per_dim["source_diversity"],
            "perspective_balance": det_per_dim["perspective_balance"],
            "longform_quality": det_per_dim["longform_quality"],
            "bilingual": det_per_dim["bilingual"],
            "quote_match": {"score": s_ground},
            "reachability": reach,
        }

        weights = self.weights or WEIGHTS_RL
        dropped: list[str] = []
        if self.mode == "fast":
            dropped.extend(_JUDGE_DIMS)
        dropped.extend(d for d in degraded_dims if d in _ALL_DIMS)
        dropped = list(dict.fromkeys(dropped))

        composite = composite_v3_rl(
            score_dict,
            process=process_terms,
            penalties=penalty_terms,
            rubric_snapshot=rubric_snapshot,
            weights=weights,
            fast_dropped_dims=dropped or None,
        )
        breakdown = composite_v3_rl_breakdown(
            score_dict,
            process=process_terms,
            penalties=penalty_terms,
            rubric_snapshot=rubric_snapshot,
            weights=weights,
            fast_dropped_dims=dropped or None,
            mode="rl_fast" if self.mode == "fast" else "rl_full",
        )
        nullified = bool(penalty_terms.get("nullify")) and (proof_grounded or rl_strict)
        if nullified:
            composite = 0.0
            breakdown["composite"] = 0.0
            breakdown["nullified"] = True

        if execution_score is not None and execution_terms is not None:
            original_composite = float(composite)
            # The anti-fabrication gate (nullified) must survive the execution
            # override. Citing URLs the policy never fetched is fabrication and
            # forces composite=0.0; an agent must not be able to recover the
            # full state-diff reward by also doing the cart/order action. So we
            # zero the state-diff contribution here when nullified, keeping the
            # gate authoritative over the override.
            effective_state_diff = 0.0 if nullified else float(execution_score)
            if execution_mode == "blend":
                state_weight = _execution_blend_weight(execution_goal or {})
                composite = ((1.0 - state_weight) * original_composite) + (state_weight * effective_state_diff)
                breakdown["execution_blend"] = {
                    "state_weight": round(state_weight, 6),
                    "original_composite": round(original_composite, 6),
                    "state_diff": round(float(execution_score), 6),
                    "state_diff_effective": round(effective_state_diff, 6),
                    "nullified": nullified,
                }
            else:
                composite = effective_state_diff
                breakdown["execution_override"] = {
                    "mode": "state_diff_only",
                    "original_composite": round(original_composite, 6),
                    "state_diff": round(float(execution_score), 6),
                    "state_diff_effective": round(effective_state_diff, 6),
                    "nullified": nullified,
                }
            breakdown["composite"] = round(float(composite), 6)

        degraded_unique = list(dict.fromkeys(degraded_dims))
        signal_health = "degraded" if degraded_unique else "ok"
        reward_terms = {
            "grounding": ground_details,
            "process": process_terms,
            "penalties": penalty_terms,
            "degraded_dims": degraded_unique,
            "signal_health": signal_health,
        }
        if execution_terms is not None:
            reward_terms["execution"] = execution_terms

        policy = {
            "sandbox_violations": int(spec_details.get("sandbox_violations", 0) or 0),
            "reachability": float(reach),
            "quote_match": float(s_ground),
        }
        if execution_score is not None:
            policy["state_diff"] = float(execution_score)

        return EvalResult(
            composite=float(composite),
            breakdown=breakdown,
            per_dim={k: det_per_dim[k] for k in _ALL_DIMS},
            policy=policy,
            mode=self.mode,
            judge_errors=judge_errors,
            signal_health=signal_health,
            reward_terms=reward_terms,
        )

    # --------------------------------------------------- helpers (LLM dims)
    async def _run_judge_dims_rollout_async(
        self,
        task_config: dict,
        report_md: str,
        *,
        rubric_snapshot: Optional[dict] = None,
        evidence: Optional[dict] = None,
    ) -> dict[str, tuple[float, dict, Optional[str]]]:
        async def _run(name: str, verifier_factory: Any) -> tuple[str, tuple[float, dict, Optional[str]]]:
            try:
                verifier = verifier_factory()
            except Exception as e:
                return name, (_NEUTRAL, {"error": f"factory_failed: {e}"}, str(e))
            try:
                loop = asyncio.get_event_loop()
                if name == "checklist":
                    def _verify_checklist() -> tuple[float, dict]:
                        vr = verifier.verify(
                            task_config=task_config,
                            answer=report_md,
                            rubric_snapshot=rubric_snapshot,
                        )
                        s = max(0.0, min(1.0, float(getattr(vr, "score", 0.0) or 0.0)))
                        return s, dict(getattr(vr, "details", {}) or {})

                    s, d = await loop.run_in_executor(None, _verify_checklist)
                elif name in {"depth", "rigor", "style"}:
                    def _verify_with_evidence() -> tuple[float, dict]:
                        vr = verifier.verify(
                            task_config=task_config,
                            answer=report_md,
                            evidence=evidence,
                        )
                        s = max(0.0, min(1.0, float(getattr(vr, "score", 0.0) or 0.0)))
                        return s, dict(getattr(vr, "details", {}) or {})

                    s, d = await loop.run_in_executor(None, _verify_with_evidence)
                else:
                    s, d = await loop.run_in_executor(None, _safe_verify, verifier, task_config, report_md)
                err = d.get("error") if isinstance(d, dict) else None
                return name, (s, d, err)
            except Exception as e:
                return name, (_NEUTRAL, {"error": f"{type(e).__name__}: {e}"}, str(e))

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

        results = await asyncio.gather(
            _run("depth", _depth),
            _run("rigor", _rigor),
            _run("style", _style),
            _run("checklist", _checklist),
        )
        return dict(results)

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
    async def _compute_ground_signals(
        self,
        task_config: dict,
        rollout: Any,
    ) -> tuple[float, float, dict]:
        """Return (s_ground, reachability, details) for the rollout RL path."""
        from src.eval.reward_terms import CITATION_CAP, _ordered_cited_urls, _sandbox_hosts
        from src.verifiers.citation_format import (
            canonicalize_url,
            extract_cited_pairs,
        )

        report_md = getattr(rollout, "report_md", "") or ""
        sandbox_hosts = _sandbox_hosts(task_config)
        cited_capped = _ordered_cited_urls(rollout, task_config)
        n_cited = len(cited_capped)

        raw_store = getattr(rollout, "retrieved_snippets", None) or {}
        store = {
            canonicalize_url(str(url)): str(text or "")
            for url, text in raw_store.items()
            if str(url).strip() and str(text or "")
        }
        if not store:
            # RL rollouts are trace-capable by construction: an empty retrieval
            # store means the policy fetched no pages, so there is nothing to
            # ground against. The text-only proxy below is meant for external
            # arena agents that never expose a trace; using it here would reward
            # not reading (F1_claim≈1.0 for a report that read nothing), which
            # inverts the training signal. Under _rl_strict, treat no-fetch as
            # zero grounding instead.
            if getattr(self, "_rl_strict", False):
                return 0.0, 0.0, {
                    "source": "no_fetch",
                    "signal_health": "degraded",
                    "n_cited": n_cited,
                    "n_resolved": 0,
                    "R_resolve": 0.0,
                    "F1_claim": 0.0,
                    "citation_cap": CITATION_CAP,
                }
            trace = getattr(rollout, "trace", None)
            qm_trace = self._try_quote_match(trace) if trace is not None else None
            reach_trace = self._try_reachability(trace) if trace is not None else None
            if qm_trace is not None or reach_trace is not None:
                proxy, reach_proxy = await self._compute_policy_signals(task_config, report_md, None)
                qm_val = proxy if qm_trace is None else max(0.0, min(1.0, float(qm_trace)))
                reach_val = (
                    reach_proxy
                    if reach_trace is None
                    else max(0.0, min(1.0, float(reach_trace)))
                )
                s_ground = min(float(proxy), float(qm_val), 0.5)
                reach_degraded = min(float(reach_proxy), float(reach_val))
                return s_ground, reach_degraded, {
                    "source": "bench_trace",
                    "signal_health": "degraded",
                    "n_cited": n_cited,
                    "n_resolved": 0,
                    "R_resolve": 0.0,
                    "F1_claim": round(s_ground, 6),
                    "citation_cap": CITATION_CAP,
                    "trace_quote_match": None if qm_trace is None else round(float(qm_trace), 6),
                    "trace_reachability": None if reach_trace is None else round(float(reach_trace), 6),
                    "corroborated": False,
                }

            proxy, reach_proxy = await self._compute_policy_signals(task_config, report_md, None)
            return float(proxy), float(reach_proxy), {
                "source": "proxy",
                "signal_health": "degraded",
                "n_cited": n_cited,
                "n_resolved": 0,
                "R_resolve": 0.0,
                "F1_claim": round(float(proxy), 6),
                "citation_cap": CITATION_CAP,
            }

        resolved = [u for u in cited_capped if u in store]
        r_resolve = len(resolved) / n_cited if n_cited else 0.0

        claims_by_url: dict[str, list[str]] = {}
        for raw_url, claim, _offset in extract_cited_pairs(report_md, sandbox_hosts):
            canon = canonicalize_url(raw_url)
            if canon in cited_capped:
                claims_by_url.setdefault(canon, []).append(claim)

        leaves: list[float] = []
        per_claim: list[dict[str, Any]] = []
        for url in cited_capped:
            if url not in store:
                leaves.append(0.0)
                per_claim.append({"url": url[:120], "leaf": 0.0, "reason": "not_fetched"})
                continue
            supports = [
                _claim_page_support(claim, store[url])
                for claim in claims_by_url.get(url, [])
            ]
            best = max(supports, key=lambda x: x["support"]) if supports else None
            leaf = float(best["leaf"]) if best else 0.0
            leaves.append(leaf)
            sample = {
                "url": url[:120],
                "leaf": leaf,
            }
            if best:
                sample.update({
                    "support": round(float(best["support"]), 3),
                    "overlap": round(float(best["overlap"]), 3),
                    "specific_recall": round(float(best["specific_recall"]), 3),
                    "jaccard": round(float(best["jaccard"]), 3),
                    "verbatim": bool(best["verbatim"]),
                    "verbatim_ratio": round(float(best["verbatim_ratio"]), 3),
                })
            else:
                sample["reason"] = "no_claim"
            per_claim.append(sample)

        f1_claim = sum(leaves) / n_cited if n_cited else 0.0
        s_ground = 0.6 * f1_claim + 0.4 * r_resolve
        details = {
            "source": "proof_of_fetch",
            "n_cited": n_cited,
            "n_resolved": len(resolved),
            "R_resolve": round(r_resolve, 6),
            "F1_claim": round(f1_claim, 6),
            "citation_cap": CITATION_CAP,
            "resolved_urls_sample": resolved[:6],
            "samples": per_claim[:6],
        }
        trace = getattr(rollout, "trace", None)
        if trace is not None:
            qm_trace = self._try_quote_match(trace)
            reach_trace = self._try_reachability(trace)
            if qm_trace is not None or reach_trace is not None:
                details["trace_quote_match"] = None if qm_trace is None else round(float(qm_trace), 6)
                details["trace_reachability"] = None if reach_trace is None else round(float(reach_trace), 6)
                details["corroborated"] = True
        return float(s_ground), float(r_resolve), details

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
