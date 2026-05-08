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
