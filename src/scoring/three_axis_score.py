"""Pure aggregation for the DRA report-level three-axis score.

Semantic extraction and evidence verification happen upstream.  This module
only validates and aggregates a frozen, machine-readable judgment packet.
Keeping aggregation pure makes the published score reproducible and lets the
semantic judges be calibrated independently.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _harmonic_mean(precision: float, recall: float) -> float:
    return (
        2.0 * precision * recall / (precision + recall)
        if precision + recall > 0.0
        else 0.0
    )


def score_three_axis(packet: dict[str, Any]) -> dict[str, Any]:
    """Aggregate one frozen task/report judgment packet.

    Required packet collections:
      material_claims: status is ``supported`` or ``wrong``;
      core_atomic_facts: boolean ``covered``;
      citation_bindings: boolean ``passed``;
      citation_required_units: boolean ``grounded``;
      research_units: ``facet``, ``unit_type``, boolean ``covered``;
      cited_urls: boolean ``legal_origin``.
    """

    claims = packet["material_claims"]
    invalid_claim_statuses = sorted(
        {
            str(item.get("status"))
            for item in claims
            if item.get("status") not in {"supported", "wrong"}
        }
    )
    if invalid_claim_statuses:
        raise ValueError(
            "material claims must be split to supported/wrong before scoring; "
            f"got {invalid_claim_statuses}"
        )

    supported_claims = sum(item["status"] == "supported" for item in claims)
    wrong_claims = sum(item["status"] == "wrong" for item in claims)
    fact_precision = _ratio(supported_claims, supported_claims + wrong_claims)

    core_facts = packet["core_atomic_facts"]
    covered_core_facts = sum(bool(item["covered"]) for item in core_facts)
    fact_recall = _ratio(covered_core_facts, len(core_facts))
    fact = _harmonic_mean(fact_precision, fact_recall)

    bindings = packet["citation_bindings"]
    passing_bindings = sum(bool(item["passed"]) for item in bindings)
    evidence_precision = _ratio(passing_bindings, len(bindings))

    evidence_units = packet["citation_required_units"]
    grounded_units = sum(bool(item["grounded"]) for item in evidence_units)
    evidence_recall = _ratio(grounded_units, len(evidence_units))
    evidence = _harmonic_mean(evidence_precision, evidence_recall)

    research_units = packet["research_units"]
    grouped: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for item in research_units:
        grouped[(str(item["facet"]), str(item["unit_type"]))].append(
            bool(item["covered"])
        )
    group_scores = {
        f"{facet}::{unit_type}": _ratio(sum(values), len(values))
        for (facet, unit_type), values in sorted(grouped.items())
    }
    completeness = _ratio(sum(group_scores.values()), len(group_scores))

    cited_urls = packet["cited_urls"]
    legal_urls = sum(bool(item["legal_origin"]) for item in cited_urls)
    provenance = _ratio(legal_urls, len(cited_urls))

    quality = (fact + evidence + completeness) / 3.0
    truth = provenance * quality
    legacy_weight_ablation = provenance * (
        0.39 * fact + 0.28 * evidence + 0.33 * completeness
    )

    return {
        "fact": {
            "precision": fact_precision,
            "recall": fact_recall,
            "score": fact,
            "supported_claims": supported_claims,
            "wrong_claims": wrong_claims,
            "covered_core_facts": covered_core_facts,
            "core_fact_count": len(core_facts),
        },
        "evidence": {
            "precision": evidence_precision,
            "recall": evidence_recall,
            "score": evidence,
            "passing_bindings": passing_bindings,
            "binding_count": len(bindings),
            "grounded_units": grounded_units,
            "citation_required_unit_count": len(evidence_units),
        },
        "completeness": {
            "score": completeness,
            "group_scores": group_scores,
            "covered_units": sum(bool(item["covered"]) for item in research_units),
            "research_unit_count": len(research_units),
            "macro_group_count": len(group_scores),
        },
        "provenance": {
            "score": provenance,
            "legal_origin_urls": legal_urls,
            "cited_url_count": len(cited_urls),
        },
        "quality": quality,
        "truth": truth,
        "legacy_weight_ablation": legacy_weight_ablation,
    }


__all__ = ["score_three_axis"]
