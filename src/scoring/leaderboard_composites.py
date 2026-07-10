"""Single source of truth for the deep-tier leaderboard composite formulas.

The headline ranking, every ablation, and every per-intent slice MUST agree
on what `composite_v2` means. Before this module existed, three scripts each
implemented their own variant:

  * build_deep_leaderboard.composite_v2_truthful: ``reach * quality``.
  * scoring_ablation.compute_v2: ``reach * (0.5 + 0.5*qm) * (0.5 + 0.5*nli)
    * quality`` (truthfulness-multiplicative).
  * review_analyses.composite_v2: ``max(0.1, reach) * quality``
    (V3-floor variant).

Use of three different "v2"s meant ablation and per-intent tables silently
disagreed with the headline leaderboard — paper rows for the same agent
were not on the same scale.

This module exports the canonical formulas plus helpers that every script
in `scripts/` should import. If you need a *new* variant for a new
analysis, add it here under its own clear name; do **not** redefine v1 / v2
inside another script.
"""

from __future__ import annotations

from typing import Any


def spec_pass_fraction(spec: dict | None) -> float:
    """3 boolean flags averaged → [0, 1]. ``markdown_spec`` does not have a
    top-level `score` field, so reading `.score` (the previous habit)
    silently zeroes the spec contribution to composite for everyone."""
    if not isinstance(spec, dict):
        return 0.0
    flags = [bool(spec.get(k, False)) for k in ("words_ok", "citations_ok", "paragraphs_ok")]
    return sum(flags) / 3.0


def checklist_pass_rate(ck: dict | None) -> float:
    """Checklist score lives under ``pass_rate``. Old code reading ``.score``
    silently got 0 because that key never existed."""
    if not isinstance(ck, dict):
        return 0.0
    val = ck.get("pass_rate")
    if val is None:
        val = ck.get("score")
    return float(val or 0)


def quality(score: dict[str, Any]) -> float:
    """Quality term used by composite v1 and v2_truthful.

    quality = 0.40·url_coverage + 0.40·checklist_pass_rate + 0.20·spec_pass.
    """
    url = (score.get("url_coverage") or {}).get("score") or 0
    chk = checklist_pass_rate(score.get("checklist") or {})
    spc = spec_pass_fraction(score.get("markdown_spec") or {})
    return 0.40 * float(url) + 0.40 * chk + 0.20 * spc


def composite_v1(score: dict[str, Any]) -> float:
    """Legacy additive composite — `reach` is treated as a *quality input*,
    not a multiplicative gate. This is what `composite_v2_truthful` reduces
    to when reachability is dropped, and what `score_deep_answer.py`
    legacy `composite_v1` reports as `legacy_composite`.
    """
    if "composite" in score and isinstance(score["composite"], (int, float)):
        return float(score["composite"])
    return quality(score)


def composite_v2_truthful(score: dict[str, Any]) -> float:
    """Headline ranking — multiplicative reach gate over quality.

    composite_v2 = reachability · quality

    Reachability gate kills any agent with fabricated URLs regardless of
    how fluent the prose is. This is the formula `build_deep_leaderboard`
    uses in `LEADERBOARD_DEEP.md`; **paper headline numbers come from here**.
    """
    reach = (score.get("url_reachability") or {}).get("score") or 0
    return float(reach) * quality(score)


def composite_v2_truthfulness_factored(score: dict[str, Any]) -> float:
    """Variant used by `scoring_ablation.compute_v2` historically — adds a
    quote-match × NLI truthfulness factor on top of the reach gate. Kept
    here under a clear name so callers explicitly opt in.
    """
    reach = (score.get("url_reachability") or {}).get("score") or 0
    qm = (score.get("quote_match") or {}).get("score") or 0
    nli = (score.get("claim_nli") or {}).get("score") or 0
    truth = float(reach) * (0.5 + 0.5 * float(qm)) * (0.5 + 0.5 * float(nli))
    return truth * quality(score)


def composite_v2_floored(score: dict[str, Any], floor: float = 0.1) -> float:
    """Variant used by `review_analyses.composite_v2` historically — replaces
    the multiplicative reach gate with `max(floor, reach)` so reach=0
    agents still receive `floor·quality` instead of zero. Aligns with
    composite_v3's grounding-gate semantics.
    """
    reach = (score.get("url_reachability") or {}).get("score") or 0
    gate = max(float(floor), float(reach))
    return gate * quality(score)


def composite_v3(score: dict[str, Any], floor: float = 0.1) -> float:
    """7-dimension grounding-gated composite.

    composite_v3 = max(floor, reach) · (0.20·url_coverage + 0.20·quote_match
        + 0.20·judge_pass + 0.10·spec + 0.15·citation_alignment
        + 0.10·analysis_depth + 0.05·presentation)
    """
    reach = (score.get("url_reachability") or {}).get("score") or 0
    url = (score.get("url_coverage") or {}).get("score") or 0
    qm = (score.get("quote_match") or {}).get("score") or 0
    chk = checklist_pass_rate(score.get("checklist") or {})
    spc = spec_pass_fraction(score.get("markdown_spec") or {})
    cit = ((score.get("citation_alignment") or {}).get("score") or 0) if isinstance(score.get("citation_alignment"), dict) else 0
    ad = ((score.get("analysis_depth") or {}).get("score") or 0) if isinstance(score.get("analysis_depth"), dict) else 0
    pres = ((score.get("presentation") or {}).get("score") or 0) if isinstance(score.get("presentation"), dict) else 0
    raw = (
        0.20 * float(url) + 0.20 * float(qm) + 0.20 * chk + 0.10 * spc
        + 0.15 * float(cit) + 0.10 * float(ad) + 0.05 * float(pres)
    )
    gate = max(float(floor), float(reach))
    return gate * raw


# ---------------------------------------------------------------------------
# v3-softfloor — Workstream A (2026-05-21) replacement for the v2 hard gate
# ---------------------------------------------------------------------------
#
# v2's multiplicative reach gate (`composite_v2_truthful = reach × quality`)
# zeroes any run with even one broken URL. F6 came from this — and it was
# correct as a finding ("URL truthfulness matters multiplicatively") — but
# the hard zero is a wrecking-ball for downstream uses:
#   * AgentRL needs a smooth, never-zero reward signal.
#   * Workstream D wants human-pref weight fitting on real-valued scores,
#     not on a binary "did the agent fabricate any URL" indicator.
#   * Workstream E's leaderboard becomes uninformative when half the agents
#     get composite_v2 ≈ 0 for one bad citation.
#
# v3 keeps the truthfulness signal but softens it:
#
#   composite_v3 = reach_soft × Q
#   reach_soft   = 0.5 + 0.5 × quote_match     # in [0.5, 1.0]
#   Q            = Σ_d w_d · score_d           # 6 quality dims
#
# Quote_match (not reach!) is the soft-floor input because it's the
# already-deterministic per-citation truthfulness signal: did the agent's
# quoted span actually appear on the cited URL. Reachability is an upstream
# health-check (does the URL resolve), already partially captured by url_coverage
# and by quote_match's denominator. Using quote_match as the soft-gate means
# v3 punishes hallucinated *quotes* (not just dead URLs), which is the
# stronger truthfulness signal.
#
# Initial WEIGHTS_V3 are placeholder uniform-ish weights; Workstream D fits
# these to human preference data via `scripts/fit_weights_v3.py`. The 6
# dims are intentionally NOT the same as v4's 11 pillars — v3 collapses
# down to the dimensions humans actually distinguish (coverage / depth /
# rigor / style / checklist / spec).

WEIGHTS_V3: dict[str, float] = {
    "coverage":  0.20,
    "depth":     0.20,
    "rigor":     0.20,
    "style":     0.10,
    "checklist": 0.20,
    "spec":      0.10,
}

assert abs(sum(WEIGHTS_V3.values()) - 1.0) < 1e-9, (
    "WEIGHTS_V3 must sum to 1.0; got "
    f"{sum(WEIGHTS_V3.values()):.6f}"
)

# RL reward weights (Phase Q6). Deterministic spine (0.57) + judge/rubric (0.43).
# These are a principled INITIAL allocation favoring discriminative, ungameable,
# fast-mode-available deterministic signals; the judge dims were F=2.30 noise before
# the Q1 evidence-aware rebuild, so they are retained but not dominant. Final
# numbers to be calibrated against real per-agent F-ratios on the training box.
WEIGHTS_RL: dict[str, float] = {
    # deterministic spine (scored in BOTH fast and full mode)
    "coverage":            0.18,
    "source_diversity":    0.10,
    "longform_quality":    0.10,
    "perspective_balance": 0.08,
    "spec":                0.06,
    "bilingual":           0.05,
    # judge / rubric (full mode only; dropped + renormalized in fast mode)
    "checklist":           0.16,
    "depth":               0.12,
    "rigor":               0.09,
    "style":               0.06,
}
assert abs(sum(WEIGHTS_RL.values()) - 1.0) < 1e-9


def _v3_dim_score(score: dict[str, Any], dim: str) -> float:
    """Read a v3 quality dim from a score dict, tolerating two shapes:

      1. A top-level scalar in [0, 1]:  score[dim] = 0.7
      2. A verifier dict:                score[dim] = {"score": 0.7, ...}

    Falls back to the legacy verifier locations used by v2 / v4:
      - "coverage"  → url_coverage.score
      - "checklist" → checklist.pass_rate (via checklist_pass_rate helper)
      - "spec"      → markdown_spec via spec_pass_fraction helper
    depth / rigor / style do not have legacy fallbacks (they are new in v3).
    Missing dims default to 0.0, matching how composite_v3 / v4 treat
    absent pillars.
    """
    if dim in score:
        v = score[dim]
        if isinstance(v, dict):
            inner = v.get("score")
            if inner is not None:
                return float(inner)
        elif isinstance(v, (int, float)):
            return float(v)
    if dim == "coverage":
        return float((score.get("url_coverage") or {}).get("score") or 0)
    if dim == "checklist":
        return checklist_pass_rate(score.get("checklist") or {})
    if dim == "spec":
        return spec_pass_fraction(score.get("markdown_spec") or {})
    return 0.0


def _reach_soft(score: dict[str, Any]) -> float:
    """0.5 + 0.5 * quote_match, clipped to [0.5, 1.0].

    quote_match is the per-quoted-span truthfulness signal — far stronger
    than mere reachability (a URL can resolve but the quote can be
    invented). Clipping below at 0.5 is what makes v3 a *soft* floor:
    even an agent with no quote matches still gets half-credit on Q,
    giving downstream learners (AgentRL) and rankers (Bradley-Terry over
    composite) a usable gradient.
    """
    qm = score.get("quote_match")
    if isinstance(qm, dict):
        qm_val = qm.get("score")
    else:
        qm_val = qm
    qm_val = float(qm_val or 0.0)
    raw = 0.5 + 0.5 * qm_val
    # Clip — quote_match is supposed to be in [0,1] but score dicts in the
    # wild sometimes contain stray values.
    if raw < 0.5:
        return 0.5
    if raw > 1.0:
        return 1.0
    return raw


def composite_v3_softfloor(score: dict[str, Any]) -> float:
    """v3 soft-floor composite — never-zero replacement for composite_v2.

    composite_v3 = reach_soft · Σ w_d · score_d
                   where reach_soft = 0.5 + 0.5 * quote_match
                         w_d        = WEIGHTS_V3
                         dims       = {coverage, depth, rigor, style, checklist, spec}

    Returns a float in [0.5 · 0, 1.0 · 1] = [0, 1]. In practice the
    soft-floor multiplies a non-negative Q by at least 0.5, so an agent
    that completely fails truthfulness (quote_match = 0) still gets
    0.5 · Q on the quality side. F6 stays observable as a *gap* between
    high-quote_match and low-quote_match agents, but no run is zeroed.

    The function name is suffixed `_softfloor` because the bare
    `composite_v3` symbol is taken by the legacy 7-dim variant above.
    Both stay callable side-by-side for parallel computation, per the
    Workstream A spec ("keep `composite_v2_truthful` callable").
    """
    rs = _reach_soft(score)
    q = sum(w * _v3_dim_score(score, d) for d, w in WEIGHTS_V3.items())
    return rs * q


def composite_v3_breakdown(score: dict[str, Any]) -> dict[str, Any]:
    """Return the per-dim contribution to composite_v3_softfloor.

    Shape:
      {
        "reach_soft": float in [0.5, 1.0],
        "q_value":    float in [0, 1],
        "per_dim_contribution": {dim: w_d * score_d},
        "composite":  float = reach_soft * q_value,
      }

    Useful for the frontend leaderboard (per-pillar breakdown) and for
    weight-fitting (Workstream D) which needs the raw dim scores.
    """
    rs = _reach_soft(score)
    per_dim: dict[str, float] = {}
    q_val = 0.0
    for d, w in WEIGHTS_V3.items():
        s_d = _v3_dim_score(score, d)
        contribution = w * s_d
        per_dim[d] = round(contribution, 6)
        q_val += contribution
    return {
        "reach_soft": round(rs, 6),
        "q_value": round(q_val, 6),
        "per_dim_contribution": per_dim,
        "composite": round(rs * q_val, 6),
    }


# ---------------------------------------------------------------------------
# Legacy v4 compatibility
# ---------------------------------------------------------------------------
# Several shipped score/build entry points still materialise the historical
# 11-pillar v4 record. The implementation was removed while those callers were
# left live, making single-report scoring fail at import time. Keep the formula
# here as an explicitly legacy compatibility surface. It is not the truth_v2
# headline used by build_truth_board.py.


def _pillar_score(score: dict[str, Any], key: str) -> float:
    blob = score.get(key)
    if not isinstance(blob, dict):
        return 0.0
    try:
        return float(blob.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def composite_v4_weights() -> dict[str, float]:
    return {
        "url_coverage": 0.10,
        "spec": 0.05,
        "checklist": 0.10,
        "citation_alignment": 0.10,
        "quote_match": 0.05,
        "factual_exactness": 0.13,
        "internal_consistency": 0.13,
        "perspective_balance": 0.08,
        "source_diversity": 0.06,
        "analysis_depth": 0.10,
        "presentation": 0.10,
    }


def composite_v4(score: dict[str, Any], floor: float = 0.0) -> float:
    """Historical 11-pillar reach-gated composite used by legacy tools."""
    values = {
        "url_coverage": _pillar_score(score, "url_coverage"),
        "spec": spec_pass_fraction(score.get("markdown_spec") or {}),
        "checklist": checklist_pass_rate(score.get("checklist") or {}),
        "citation_alignment": _pillar_score(score, "citation_alignment"),
        "quote_match": _pillar_score(score, "quote_match"),
        "factual_exactness": _pillar_score(score, "factual_exactness"),
        "internal_consistency": _pillar_score(score, "internal_consistency"),
        "perspective_balance": _pillar_score(score, "perspective_balance"),
        "source_diversity": _pillar_score(score, "source_diversity"),
        "analysis_depth": _pillar_score(score, "analysis_depth"),
        "presentation": _pillar_score(score, "presentation"),
    }
    weights = composite_v4_weights()
    raw = sum(weights[key] * value for key, value in values.items())
    reach = _pillar_score(score, "url_reachability")
    gate = max(float(floor), reach) if floor else reach
    return gate * raw


assert abs(sum(composite_v4_weights().values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# v3 RL reward variant. Additive-only: the public leaderboard path continues
# to call composite_v3_softfloor / composite_v3_breakdown unchanged.
# ---------------------------------------------------------------------------

LAMBDA_PROC = 0.15
PENALTY_CAP = 0.30


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _process_bonus(process: Any) -> float:
    if process is None:
        return 0.0
    try:
        if isinstance(process, dict):
            return _clip01(float(process.get("R_process") or 0.0))
        return _clip01(float(process))
    except (TypeError, ValueError):
        return 0.0


def _penalty_total(penalties: Any) -> float:
    if penalties is None:
        return 0.0
    try:
        if isinstance(penalties, dict):
            val = penalties.get("P_hack")
            if val is None:
                val = sum(
                    float(penalties.get(k) or 0.0)
                    for k in ("p_fabricate", "p_unused", "p_verbose")
                )
            return max(0.0, min(PENALTY_CAP, float(val)))
        return max(0.0, min(PENALTY_CAP, float(penalties)))
    except (TypeError, ValueError):
        return 0.0


def _rubric_match(rubric_snapshot: Any) -> float:
    if not isinstance(rubric_snapshot, dict):
        return 1.0
    for key in ("rubric_match", "match_score", "score"):
        if key in rubric_snapshot:
            try:
                return _clip01(float(rubric_snapshot[key]))
            except (TypeError, ValueError):
                return 1.0
    return 1.0


def _effective_rl_quality(
    score: dict[str, Any],
    weights: dict[str, float],
    fast_dropped_dims: Any,
) -> tuple[float, dict[str, float], list[str]]:
    dropped = set(fast_dropped_dims or [])
    present = [d for d in weights if d not in dropped]
    wtot = sum(float(weights[d]) for d in present) or 1.0
    weights_eff = {d: float(weights[d]) / wtot for d in present}
    q = sum(weights_eff[d] * _v3_dim_score(score, d) for d in present)
    return q, weights_eff, [d for d in weights if d in dropped]


def composite_v3_rl(
    score: dict[str, Any],
    process: Any = None,
    penalties: Any = None,
    rubric_snapshot: Any = None,
    *,
    weights: dict[str, float] | None = None,
    fast_dropped_dims: Any = None,
) -> float:
    rs = _reach_soft(score)
    w = weights or WEIGHTS_V3
    q, _, _ = _effective_rl_quality(score, w, fast_dropped_dims)
    r_process = _process_bonus(process)
    p_hack = _penalty_total(penalties)
    return _clip01(rs * q + LAMBDA_PROC * r_process - p_hack)


def composite_v3_rl_breakdown(
    score: dict[str, Any],
    process: Any = None,
    penalties: Any = None,
    rubric_snapshot: Any = None,
    *,
    weights: dict[str, float] | None = None,
    fast_dropped_dims: Any = None,
    mode: str | None = None,
) -> dict[str, Any]:
    rs = _reach_soft(score)
    w = weights or WEIGHTS_V3
    q_val, weights_eff, dropped = _effective_rl_quality(score, w, fast_dropped_dims)
    per_dim = {
        d: round(weights_eff[d] * _v3_dim_score(score, d), 6)
        for d in weights_eff
    }
    base = rs * q_val
    r_process = _process_bonus(process)
    p_hack = _penalty_total(penalties)
    composite = _clip01(base + LAMBDA_PROC * r_process - p_hack)
    if mode not in {"rl_fast", "rl_full"}:
        mode = "rl_fast" if set(dropped) >= {"depth", "rigor", "style", "checklist"} else "rl_full"
    return {
        "reach_soft": round(rs, 6),
        "q_value": round(q_val, 6),
        "per_dim_contribution": per_dim,
        "composite": round(composite, 6),
        "process_bonus": round(r_process, 6),
        "penalty_total": round(p_hack, 6),
        "rubric_match": round(_rubric_match(rubric_snapshot), 6),
        "lambda_proc": LAMBDA_PROC,
        "base": round(base, 6),
        "weights_effective": {k: round(v, 6) for k, v in weights_eff.items()},
        "dims_dropped": dropped,
        "mode": mode,
    }
