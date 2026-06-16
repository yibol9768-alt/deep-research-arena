"""Closed-world grounding metric (CLOSED_WORLD_REDESIGN.md section 7).

This is the decidable, anti-fabrication-first grounding score that replaces the
``0.5 * curated_must_cite_recall + 0.5 * quote_match`` gate. It is the synthesis
of four published ideas, adapted to our frozen sandbox where reachability is an
HTTP/DB fact rather than an inference:

  * ALCE (2305.14627): a citation counts toward precision only if it is
    load-bearing (it supports the claim on its own, or removing it drops the
    joint support). Non-load-bearing citations are dead weight -> anti-stuffing.
  * SAFE / F1@K (2403.18802): recall saturates at K* supported claims, so a thin
    or abstaining report caps its recall -> anti-brevity.
  * DR Tulu (2511.19399): a claim that needs a citation but has none scores 0 for
    that claim (NeedCite), and the fraction of citations that resolve (R_fmt /
    ReachRate) is a first-class reachability term -> anti-missing-citation.
  * DeepResearch Bench FACT (2506.11763) BUG FIX: FACT's released code drops dead
    / unreachable URLs from BOTH numerator and denominator, so a 404 citation is
    cost-free. Here an unreachable citation is a FAILURE, not an exclusion: it
    lowers recall (its claim loses support) and it drags down the multiplicative
    ReachRate gate.

The headline is multiplicative:

    GROUNDING = ReachRate ** gamma  *  GroundF1@K*

so a fluent report built on unreachable or fabricated sources is crushed
regardless of how well its few reachable claims are supported. This is the same
intuition as truth-gated Elo; gamma > 1 makes fabrication super-linearly costly.

This module is PURE: it takes already-resolved per-claim evidence (the
orchestrator in ``src/verifiers/grounding_verifier.py`` does the fetching and
support judging) and returns the score dict. That keeps it deterministic and
unit-testable offline, with no sandbox dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CiteFlags:
    """One citation attached to a claim, after the orchestrator resolved it.

    Attributes
    ----------
    url : str
        The cited URL (canonical or raw; only used for reporting here).
    reachable : bool
        Whether the URL resolved to non-empty sandbox content. Decidable in a
        closed world. An unreachable citation is a failed citation, never an
        excluded one (this is the FACT bug fix).
    load_bearing : bool
        ALCE necessity test: the citation supports the claim on its own, OR
        removing it would drop the claim's joint support. Only reachable
        citations can be load-bearing. A reachable-but-irrelevant citation is
        not load-bearing and lowers precision.
    """

    url: str = ""
    reachable: bool = False
    load_bearing: bool = False


@dataclass
class ClaimEvidence:
    """A single atomic factual claim from the report and its resolved support.

    Attributes
    ----------
    needs_citation : bool
        NeedCite: True for non-trivial factual claims that must be backed by a
        source. Common knowledge / framing sentences are False and are ignored
        by grounding (they go to the rubric layer instead).
    supp : float
        Support level of the claim by the UNION of its reachable cited sources,
        as judged by the orchestrator: 1.0 full, 0.5 partial, 0.0 none. The
        orchestrator must already have set this to 0.0 when the claim has no
        reachable citation (NeedCite enforcement).
    cites : list[CiteFlags]
        Every citation the claim carries (reachable or not). Used for
        per-claim precision and for the report-wide ReachRate.
    """

    needs_citation: bool = True
    supp: float = 0.0
    cites: list[CiteFlags] = field(default_factory=list)


def _claim_precision(claim: ClaimEvidence) -> float:
    """ALCE-style per-claim citation precision: load-bearing / total cites.

    A claim that requires a citation but carries none scores 0 precision (it is
    an unsupported assertion). Non-load-bearing or unreachable citations are
    dead weight and pull this down, so citation-stuffing cannot help.
    """
    if not claim.cites:
        return 0.0
    valid = sum(1 for c in claim.cites if c.reachable and c.load_bearing)
    return valid / len(claim.cites)


def closed_world_grounding(
    claims: list[ClaimEvidence],
    *,
    k_star: int,
    gamma: float = 1.0,
) -> dict:
    """Compute the closed-world grounding score.

    Parameters
    ----------
    claims
        Every atomic claim extracted from the report, with resolved evidence.
        Only claims with ``needs_citation=True`` count toward grounding; the
        rest are framing/common-knowledge and belong to the rubric layer.
    k_star
        Recall saturation target: the number of supported factual claims a good
        report on this task is expected to make. Suggested default per task is
        the size of the golden's vital fact-nugget subset. Must be >= 1.
    gamma
        Exponent on the ReachRate gate. gamma=1 is linear; gamma>1 makes
        unreachable / fabricated citations super-linearly costly.

    Returns
    -------
    dict with keys:
        grounding        the headline ReachRate**gamma * GroundF1
        ground_f1        F1(GroundPrec, GroundRecall)
        ground_precision support-weighted, stuffing-proof precision
        ground_recall    min(G / k_star, 1), anti-brevity
        reach_rate       reachable citations / total citations (the gate base)
        supported_mass   G = sum of per-claim support over required claims
        n_required       number of claims that needed a citation
        n_citations      total citations in the report
        n_reachable      reachable citations
        flags            diagnostics (e.g. "no_required_claims")
    """
    k_star = max(1, int(k_star))
    flags: list[str] = []

    # Report-wide ReachRate over ALL citations (the gate base). A report with no
    # citations grounds nothing -> ReachRate 0 -> the gate crushes it.
    all_cites = [c for cl in claims for c in cl.cites]
    n_citations = len(all_cites)
    n_reachable = sum(1 for c in all_cites if c.reachable)
    reach_rate = (n_reachable / n_citations) if n_citations else 0.0

    required = [cl for cl in claims if cl.needs_citation]
    n_required = len(required)
    if n_required == 0:
        # A report that makes no citable factual claims is not grounded; it is a
        # fluent essay. It must not pass a grounding gate. Return 0 with a flag
        # so the caller can route it to the rubric layer instead.
        flags.append("no_required_claims")
        return {
            "grounding": 0.0,
            "ground_f1": 0.0,
            "ground_precision": 0.0,
            "ground_recall": 0.0,
            "reach_rate": round(reach_rate, 4),
            "supported_mass": 0.0,
            "n_required": 0,
            "n_citations": n_citations,
            "n_reachable": n_reachable,
            "flags": flags,
        }

    # G = supported mass over required claims. supp is already 0 when the claim
    # has no reachable citation (NeedCite enforced upstream).
    supported_mass = sum(cl.supp for cl in required)

    # SAFE F1@K recall: saturates at k_star supported claims -> anti-brevity.
    ground_recall = min(supported_mass / k_star, 1.0)

    # Support-weighted, stuffing-proof precision: a claim contributes only to the
    # extent it is both supported AND cited without padding (ALCE per-claim prec).
    ground_precision = (
        sum(cl.supp * _claim_precision(cl) for cl in required) / n_required
    )

    if ground_precision > 0.0 and ground_recall > 0.0:
        ground_f1 = 2 * ground_precision * ground_recall / (ground_precision + ground_recall)
    else:
        ground_f1 = 0.0

    grounding = (reach_rate ** float(gamma)) * ground_f1

    return {
        "grounding": round(grounding, 4),
        "ground_f1": round(ground_f1, 4),
        "ground_precision": round(ground_precision, 4),
        "ground_recall": round(ground_recall, 4),
        "reach_rate": round(reach_rate, 4),
        "supported_mass": round(supported_mass, 4),
        "n_required": n_required,
        "n_citations": n_citations,
        "n_reachable": n_reachable,
        "flags": flags,
    }


def claim_evidence_from_dicts(rows: list[dict]) -> list[ClaimEvidence]:
    """Build ClaimEvidence list from plain dicts (for score_json round-trips).

    Each row: ``{"needs_citation": bool, "supp": float,
    "cites": [{"url": str, "reachable": bool, "load_bearing": bool}, ...]}``.
    """
    out: list[ClaimEvidence] = []
    for r in rows or []:
        cites = [
            CiteFlags(
                url=str(c.get("url", "")),
                reachable=bool(c.get("reachable", False)),
                load_bearing=bool(c.get("load_bearing", False)),
            )
            for c in (r.get("cites") or [])
        ]
        out.append(ClaimEvidence(
            needs_citation=bool(r.get("needs_citation", True)),
            supp=float(r.get("supp", 0.0) or 0.0),
            cites=cites,
        ))
    return out
