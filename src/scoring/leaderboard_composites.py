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
# v4 — 11-dimension reach-gated composite with three new pillars added
# ---------------------------------------------------------------------------

def _pillar_score(score: dict[str, Any], key: str) -> float:
    """Read a pillar score with consistent dict-or-missing handling.

    Returns 0.0 when the key is absent or its `.score` is unset; this
    matches how composite_v3 has always treated absent verifiers, so
    composite_v4 can run side-by-side on score JSONs that pre-date the
    v4 verifiers without raising.
    """
    blob = score.get(key)
    if not isinstance(blob, dict):
        return 0.0
    return float(blob.get("score") or 0)


def composite_v4(score: dict[str, Any], floor: float = 0.0) -> float:
    """11-dimension reach-gated composite (v4 design — see docs/defense_walkthrough.html §15.5).

    composite_v4 = url_reachability  ·  (
          0.10 · url_coverage
        + 0.05 · spec
        + 0.10 · checklist
        + 0.10 · citation_alignment
        + 0.05 · quote_match
        + 0.13 · factual_exactness        ← v4 NEW
        + 0.13 · internal_consistency     ← v4 NEW
        + 0.08 · perspective_balance      ← v4 NEW
        + 0.06 · source_diversity         ← v4 NEW (zero-LLM)
        + 0.10 · analysis_depth
        + 0.10 · presentation
    )
    Weights sum to 1.00 (verified at bottom).

    Reach is the multiplicative gate (same semantics as v2 — the head-line
    methodology choice that drove the truthfulness-gate finding stays
    intact). Set ``floor`` > 0 to switch to the v3-style soft gate
    (``max(floor, reach)``) for ablation work.

    When a v4 pillar (factual_exactness / internal_consistency /
    perspective_balance / source_diversity) is absent from `score`
    (e.g. when re-scoring an older JSON that pre-dates the v4 verifiers),
    its contribution is 0.0 — the composite stays comparable across
    score files written before and after v4 verifiers were added, but
    naturally returns a lower number when the new dimensions weren't run.
    """
    reach = (score.get("url_reachability") or {}).get("score") or 0
    url   = _pillar_score(score, "url_coverage")
    qm    = _pillar_score(score, "quote_match")
    chk   = checklist_pass_rate(score.get("checklist") or {})
    spc   = spec_pass_fraction(score.get("markdown_spec") or {})
    cit   = _pillar_score(score, "citation_alignment")
    ad    = _pillar_score(score, "analysis_depth")
    pres  = _pillar_score(score, "presentation")
    fe    = _pillar_score(score, "factual_exactness")
    ic    = _pillar_score(score, "internal_consistency")
    pb    = _pillar_score(score, "perspective_balance")
    sd    = _pillar_score(score, "source_diversity")

    raw = (
        0.10 * url + 0.05 * spc + 0.10 * chk + 0.10 * cit + 0.05 * qm
        + 0.13 * fe + 0.13 * ic + 0.08 * pb + 0.06 * sd
        + 0.10 * ad + 0.10 * pres
    )
    if floor and float(reach) < float(floor):
        gate = float(floor)
    else:
        gate = float(reach)
    return gate * raw


def composite_v4_weights() -> dict[str, float]:
    """Return the v4 weight vector. Useful for callers that want to
    inspect / display / audit the formula without re-reading source."""
    return {
        "url_coverage":          0.10,
        "spec":                  0.05,
        "checklist":             0.10,
        "citation_alignment":    0.10,
        "quote_match":           0.05,
        "factual_exactness":     0.13,  # NEW v4
        "internal_consistency":  0.13,  # NEW v4
        "perspective_balance":   0.08,  # NEW v4
        "source_diversity":      0.06,  # NEW v4
        "analysis_depth":        0.10,
        "presentation":          0.10,
    }


# Sanity check at import: weights MUST sum to 1.00. If a future edit
# drifts the weights, callers see the assertion immediately rather than
# a quietly wrong leaderboard number.
assert abs(sum(composite_v4_weights().values()) - 1.0) < 1e-9, (
    "composite_v4 weights must sum to 1.0; got "
    f"{sum(composite_v4_weights().values()):.6f}"
)


# ---------------------------------------------------------------------------
# v4b — sharpened-and-rebalanced variant of v4 (improves discriminability)
# ---------------------------------------------------------------------------
#
# The v4 25-row pilot exposed a real problem: 4 middle agents
# (smolagents / deerflow / storm / ii-researcher) cluster within ~50 Elo of
# each other, with adjacent-rank p-values >> 0.05. Two root causes:
#
#   1. `internal_consistency` saturates near 1.0 for almost every agent
#      (the entity-cluster NLI rarely flags real contradictions). With
#      13% weight, this pillar contributes ~0.13 of constant signal — it
#      shifts everyone's score upward equally without ranking anyone.
#
#   2. `source_diversity` has the highest variance across agents (range
#      0.28 - 0.93, σ ≈ 0.21) but only 6% weight, so its discriminative
#      power is underused.
#
# v4b addresses both via two changes:
#
#   (A) Pillar threshold sharpening — `internal_consistency` is rescaled
#       so the [0.85, 1.0] saturated range maps to [0.0, 1.0] linearly.
#       Below 0.85 = 0 (real contradictions); above 0.95 = full credit.
#       This recovers signal from the saturated pillar without changing
#       its semantics.
#
#   (B) Variance-aware reweighting — `internal_consistency` weight drops
#       from 0.13 to 0.07, `source_diversity` rises from 0.06 to 0.12,
#       weights still sum to 1.0. This rewards the pillar with actual
#       discriminative information.
#
# Result on the same 25-row sample (computed empirically — see the
# `scripts/recompute_v4b.py` driver):
#   - Adjacent-gap mean increases from ~30 Elo to ~50 Elo (+67%)
#   - Worst adjacent gap rises from 4 Elo (basically tied) to 18 Elo
#   - Top / tail unchanged; middle 4 agents fan out as expected.
# v4b is *not* a different methodology — same multiplicative reach gate,
# same 11 pillars — only the weight vector and the IC scaling change.


def _rescale_ic(ic: float, lo: float = 0.85, hi: float = 0.95) -> float:
    """Linear rescale of internal_consistency so the saturated band
    (most agents land in 0.95-1.00) uses the full [0, 1] range.

    ic <= lo → 0 (genuine contradiction observed)
    lo < ic < hi → linear interpolation
    ic >= hi → 1 (no contradictions detectable at this sample size)

    Reasoning: every agent we measured has IC ∈ [0.87, 1.00], so the raw
    13% weight on IC was effectively a constant additive shift of ~0.12
    on every report's composite. The clamped range recovers the 0.05
    spread that does exist in this band and ignores the 0.85 floor
    (which no real agent hits — IC ≤ 0.85 means severe contradiction,
    rare in our sample).
    """
    if ic <= lo:
        return 0.0
    if ic >= hi:
        return 1.0
    return (ic - lo) / (hi - lo)


def composite_v4b(score: dict[str, Any], floor: float = 0.0) -> float:
    """v4b — sharpened-and-rebalanced 11-dim composite.

    Same shape as composite_v4 (reach gate × 11-pillar quality term),
    but with two methodological refinements:

      * `internal_consistency` rescaled via `_rescale_ic` so the
        saturated [0.85, 1.0] band uses the full [0, 1] range.
      * Pillar weights rebalanced — IC down from 0.13 to 0.07, SD up
        from 0.06 to 0.12. Net: high-discriminative pillars get more
        weight, low-discriminative pillars get less. Sum still = 1.00.

    This is *strictly v4 with better numerics* — same verifiers, same
    reach gate, same head/tail. Improves adjacent-rank gap for the
    middle 4 agents that v4 left clumped.
    """
    reach = (score.get("url_reachability") or {}).get("score") or 0
    url   = _pillar_score(score, "url_coverage")
    qm    = _pillar_score(score, "quote_match")
    chk   = checklist_pass_rate(score.get("checklist") or {})
    spc   = spec_pass_fraction(score.get("markdown_spec") or {})
    cit   = _pillar_score(score, "citation_alignment")
    ad    = _pillar_score(score, "analysis_depth")
    pres  = _pillar_score(score, "presentation")
    fe    = _pillar_score(score, "factual_exactness")
    ic    = _rescale_ic(_pillar_score(score, "internal_consistency"))
    pb    = _pillar_score(score, "perspective_balance")
    sd    = _pillar_score(score, "source_diversity")

    raw = (
        0.10 * url + 0.05 * spc + 0.10 * chk + 0.10 * cit + 0.05 * qm
        + 0.13 * fe         # unchanged
        + 0.07 * ic         # ← down from 0.13 (was saturated)
        + 0.08 * pb         # unchanged
        + 0.12 * sd         # ← up from 0.06 (high variance, was underweighted)
        + 0.10 * ad + 0.10 * pres
    )
    if floor and float(reach) < float(floor):
        gate = float(floor)
    else:
        gate = float(reach)
    return gate * raw


def composite_v4b_weights() -> dict[str, float]:
    """Return the v4b weight vector. Note `internal_consistency_effective`
    documents the sharpening: actual raw IC is rescaled before
    multiplication, so the listed 0.07 weight applies to the rescaled
    value, not the raw verifier output.
    """
    return {
        "url_coverage":          0.10,
        "spec":                  0.05,
        "checklist":             0.10,
        "citation_alignment":    0.10,
        "quote_match":           0.05,
        "factual_exactness":     0.13,
        "internal_consistency":  0.07,  # ← halved (was saturated)
        "perspective_balance":   0.08,
        "source_diversity":      0.12,  # ← doubled (high variance)
        "analysis_depth":        0.10,
        "presentation":          0.10,
    }


assert abs(sum(composite_v4b_weights().values()) - 1.0) < 1e-9, (
    "composite_v4b weights must sum to 1.0; got "
    f"{sum(composite_v4b_weights().values()):.6f}"
)


# ---------------------------------------------------------------------------
# v4c — variance-budgeted composite via z-score normalisation
# ---------------------------------------------------------------------------
#
# v4b already attacked the saturation problem by hand-rescaling
# `internal_consistency` and reweighting toward source_diversity. That helped
# (min adjacent gap 0.9 → 9.2 Elo at 44 rows), but the fix is brittle: it only
# treats the one pillar we noticed was saturated, and the weight bump on SD
# was a manual guess at how much variance budget to redirect.
#
# v4c does the same thing in a principled way:
#
#   - For each pillar i, observe its population mean μ_i and std σ_i across
#     the entire scored sample.
#   - Standardise every measurement: z_i = (p_i − μ_i) / σ_i.
#   - Squash back into [0, 1] via sigmoid with a mild sharpening factor
#     (default 1.2) so the contribution stays composable with weight sums.
#   - Multiply by the same v4b weights (no manual retune).
#
# What this gives us, automatically:
#   - Saturated pillars (low σ) collapse toward 0.5 for everyone — they
#     contribute roughly nothing to the ranking, regardless of weight.
#   - Wide-spread pillars (high σ) span [near-0, near-1] freely — they get
#     full discriminative power.
#   - No manual per-pillar rescaling like `_rescale_ic`; if a future pillar
#     also saturates, v4c handles it without code change.
#
# This is the standard "z-score then aggregate" pattern used in financial
# composite indices and multi-criteria decision making. The price: v4c is no
# longer a pure function of a single report — it needs the population stats.
# When this leaderboard is recomputed, all pillar means/stds must come from
# the same sample. That is documented and snapshotted in
# `leaderboard_deep_v4c.json` so reviewers can reproduce.
#
# v4c keeps v4b's reach gate and weight vector. The *only* difference is the
# variance normalisation step. Anything v4c separates that v4b didn't is
# attributable purely to the z-score step.


def composite_v4c_raw(score: dict[str, Any], pillar_stats: dict[str, dict],
                      sharpness: float = 1.2) -> float:
    """v4c — reach × Σ w_i · sigmoid((p_i − μ_i) / σ_i · sharpness).

    `pillar_stats` must be the dict produced by `scripts/recompute_v4c.py`
    (population μ and σ per pillar across the sample). When the sample
    changes, the stats change, so call with a fresh stats dict.

    Same weights as v4b. The composite degrades gracefully when σ_i is 0
    (an entirely saturated pillar across the whole sample): that pillar
    contributes a flat 0.5 × w_i — i.e. zero information, neutral weight.
    """
    import math

    def _sig(x: float) -> float:
        z = max(-6.0, min(6.0, x * sharpness))
        return 1.0 / (1.0 + math.exp(-z))

    weights = composite_v4b_weights()  # v4c reuses v4b weight vector

    pillars = {
        "url_coverage":         _pillar_score(score, "url_coverage"),
        "spec":                 spec_pass_fraction(score.get("markdown_spec") or {}),
        "checklist":            checklist_pass_rate(score.get("checklist") or {}),
        "citation_alignment":   _pillar_score(score, "citation_alignment"),
        "quote_match":          _pillar_score(score, "quote_match"),
        "factual_exactness":    _pillar_score(score, "factual_exactness"),
        "internal_consistency": _pillar_score(score, "internal_consistency"),
        "perspective_balance":  _pillar_score(score, "perspective_balance"),
        "source_diversity":     _pillar_score(score, "source_diversity"),
        "analysis_depth":       _pillar_score(score, "analysis_depth"),
        "presentation":         _pillar_score(score, "presentation"),
    }

    raw = 0.0
    for k, w in weights.items():
        s = pillar_stats.get(k) or {}
        sd = float(s.get("sd") or 0.0)
        if sd < 1e-6:
            normed = 0.5
        else:
            z = (pillars[k] - float(s.get("mu") or 0.0)) / sd
            normed = _sig(z)
        raw += w * normed

    reach = (score.get("url_reachability") or {}).get("score") or 0
    return float(reach) * raw


def composite_v4c_weights() -> dict[str, float]:
    """v4c uses the same weight vector as v4b. The difference is that each
    pillar value is z-score-normalised before being multiplied by its
    weight — so saturated pillars contribute ~constantly to everyone and
    the high-variance pillars get to discriminate."""
    return composite_v4b_weights()
