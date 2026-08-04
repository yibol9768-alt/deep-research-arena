"""Pure aggregation for the DRA report-level four-axis truth score.

All semantic decisions are made upstream and frozen in a judgment packet.
This module deliberately performs no retrieval, claim extraction, or LLM
judging.  It validates the finite verdict vocabulary and applies the frozen
four-axis transition formula. Provenance remains the report-level multiplier.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


FACT_VERDICTS = {
    "true",
    "false",
    "conflicted",
    "unresolved",
    "out_of_world",
    "census_gap",
    "retrieval_failure",
    "world_scope_gap",
    "exempt",
    "instrument_ambiguous",
}
RUBRIC_VALUES = {
    "fulfilled": 1.0,
    "partially_fulfilled": 0.5,
    "not_fulfilled": 0.0,
}


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _harmonic_mean(precision: float, recall: float) -> float:
    if precision + recall <= 0.0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def _fact_score(claims: list[dict[str, Any]]) -> dict[str, Any]:
    invalid = sorted(
        {
            str(row.get("verdict"))
            for row in claims
            if row.get("verdict") not in FACT_VERDICTS
        }
    )
    if invalid:
        raise ValueError(f"unknown Fact verdicts: {invalid}")

    true_mass = sum(
        float(row.get("materiality", 1.0))
        for row in claims
        if row["verdict"] == "true"
    )
    false_mass = sum(
        float(row.get("materiality", 1.0))
        for row in claims
        if row["verdict"] == "false"
    )
    conflicted_mass = sum(
        float(row.get("materiality", 1.0))
        for row in claims
        if row["verdict"] == "conflicted"
    )
    in_world_material_mass = sum(
        float(row.get("materiality", 1.0))
        for row in claims
        if row["verdict"] not in {"out_of_world", "exempt"}
    )
    verdict_counts = {
        verdict: sum(row["verdict"] == verdict for row in claims)
        for verdict in sorted(FACT_VERDICTS)
    }
    # Fact is conditional factual accuracy over claims that the frozen
    # instrument successfully adjudicated.  A categorical claim facing a
    # same-scope conflict receives no truth credit, but remains in the
    # denominator so conflict cannot be used to shrink the denominator.
    denominator = true_mass + false_mass + conflicted_mass
    return {
        "score": _ratio(true_mass, denominator),
        "true_mass": true_mass,
        "false_mass": false_mass,
        "conflicted_mass": conflicted_mass,
        "decidable_mass": denominator,
        "in_world_material_mass": in_world_material_mass,
        "claim_count": len(claims),
        "verdict_counts": verdict_counts,
        "adjudication_coverage": _ratio(
            denominator,
            in_world_material_mass,
        ),
        "resolution_rate": _ratio(
            verdict_counts["true"]
            + verdict_counts["false"]
            + verdict_counts["conflicted"],
            len(claims),
        ),
    }


def _evidence_score(
    bindings: list[dict[str, Any]],
    required_units: list[dict[str, Any]],
) -> dict[str, Any]:
    # Defensive de-duplication prevents an adapter from multiplying one local
    # binding by repeating it in the packet. Distinct claims and distinct
    # occurrences remain distinct: saying more still creates more audit work.
    unique_bindings: list[dict[str, Any]] = []
    seen_binding_keys: set[tuple[Any, ...]] = set()
    for index, row in enumerate(bindings):
        if {
            "claim_id",
            "occurrence_index",
            "citation_id",
        }.issubset(row):
            key: tuple[Any, ...] = (
                row.get("claim_id"),
                row.get("occurrence_index"),
                row.get("citation_id"),
            )
        else:
            key = ("packet_row", row.get("binding_id"), index)
        if key in seen_binding_keys:
            continue
        seen_binding_keys.add(key)
        unique_bindings.append(row)
    unique_required: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(required_units):
        key = str(row.get("claim_id") or row.get("unit_id") or index)
        unique_required.setdefault(key, row)
    required_units = list(unique_required.values())
    bindings = unique_bindings

    passing = sum(bool(row.get("passed")) for row in bindings)
    grounded = sum(bool(row.get("grounded")) for row in required_units)
    precision = _ratio(passing, len(bindings))
    recall = _ratio(grounded, len(required_units))
    failure_counts: dict[str, int] = defaultdict(int)
    for row in bindings:
        if row.get("passed"):
            continue
        for reason in row.get("failure_reasons", []):
            failure_counts[str(reason)] += 1
    return {
        "score": _harmonic_mean(precision, recall),
        "precision": precision,
        "recall": recall,
        "passing_bindings": passing,
        "binding_count": len(bindings),
        "grounded_units": grounded,
        "citation_required_unit_count": len(required_units),
        "failure_counts": dict(sorted(failure_counts.items())),
    }


def _completeness_score(units: list[dict[str, Any]]) -> dict[str, Any]:
    core = [
        row
        for row in units
        if row.get("importance", "core") == "core"
        and bool(row.get("applicable", True))
    ]
    missing_content_field = [
        str(row.get("unit_id") or "<unknown>")
        for row in core
        if "content_covered" not in row
    ]
    if missing_content_field:
        raise ValueError(
            "Completeness v2 requires content_covered for every core unit: "
            + ", ".join(missing_content_field[:10])
        )
    grouped: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for row in core:
        grouped[(str(row["facet_id"]), str(row["unit_type"]))].append(
            bool(row["content_covered"])
        )
    group_scores = {
        f"{facet}::{unit_type}": _ratio(sum(values), len(values))
        for (facet, unit_type), values in sorted(grouped.items())
    }
    return {
        "score": _ratio(sum(group_scores.values()), len(group_scores)),
        "group_scores": group_scores,
        "covered_units": sum(
            bool(row["content_covered"]) for row in core
        ),
        "core_unit_count": len(core),
        "macro_group_count": len(group_scores),
        "grounded_covered_units": sum(
            bool(row.get("grounded_covered")) for row in core
        ),
    }


def _rubric_score(items: list[dict[str, Any]]) -> dict[str, Any]:
    scorable = [
        row
        for row in items
        if row.get("verdict") not in {"not_applicable"}
    ]
    invalid = sorted(
        {
            str(row.get("verdict"))
            for row in scorable
            if row.get("verdict") not in RUBRIC_VALUES
            and row.get("verdict") != "ambiguous"
        }
    )
    if invalid:
        raise ValueError(f"unknown Rubric verdicts: {invalid}")

    # A diagnostic run must still produce a score.  Ambiguous judgments are
    # conservatively worth zero and make the run ineligible for the formal
    # board.  Formal packets should resolve every ambiguous item by review.
    numerator = 0.0
    denominator = 0.0
    verdict_counts: dict[str, int] = defaultdict(int)
    for row in scorable:
        verdict = str(row["verdict"])
        weight = float(row.get("weight", 1.0))
        denominator += weight
        numerator += weight * RUBRIC_VALUES.get(verdict, 0.0)
        verdict_counts[verdict] += 1
    return {
        "score": _ratio(numerator, denominator),
        "weighted_credit": numerator,
        "weight_total": denominator,
        "item_count": len(scorable),
        "ambiguous_count": verdict_counts.get("ambiguous", 0),
        "verdict_counts": dict(sorted(verdict_counts.items())),
    }


def _provenance_score(urls: list[dict[str, Any]]) -> dict[str, Any]:
    valid = sum(bool(row.get("valid")) for row in urls)
    failure_counts: dict[str, int] = defaultdict(int)
    for row in urls:
        if row.get("valid"):
            continue
        for leg in ("canonicalized", "in_registry", "snapshot_available"):
            if not row.get(leg):
                failure_counts[leg] += 1
    return {
        "score": _ratio(valid, len(urls)),
        "valid_urls": valid,
        "cited_url_count": len(urls),
        "fabricated_or_unregistered_urls": sum(
            not bool(row.get("in_registry")) for row in urls
        ),
        "failure_counts": dict(sorted(failure_counts.items())),
    }


def score_four_axis(packet: dict[str, Any]) -> dict[str, Any]:
    """Aggregate one frozen report judgment packet.

    The returned numeric ``truth`` is always present so a diagnostic run can
    distinguish better and worse reports.  ``formal_eligible`` is an
    independent publication flag and never erases the diagnostic score.
    """

    fact = _fact_score(packet.get("material_claims", []))
    evidence = _evidence_score(
        packet.get("citation_bindings", []),
        packet.get("citation_required_units", []),
    )
    completeness = _completeness_score(packet.get("completeness_units", []))
    rubric = _rubric_score(packet.get("rubric_items", []))
    provenance = _provenance_score(packet.get("cited_urls", []))

    quality = (
        fact["score"]
        + evidence["score"]
        + completeness["score"]
        + rubric["score"]
    ) / 4.0
    truth = provenance["score"] * quality
    legacy_weight_ablation = provenance["score"] * (
        0.39 * fact["score"]
        + 0.28 * evidence["score"]
        + 0.33 * completeness["score"]
    )
    geometric_candidate = (
        fact["score"]
        * evidence["score"]
        * completeness["score"]
        * rubric["score"]
    ) ** 0.25

    return {
        "fact": fact,
        "evidence": evidence,
        "completeness": completeness,
        "rubric": rubric,
        "provenance": provenance,
        "quality": quality,
        "truth": truth,
        "truth_linear_diagnostic": truth,
        "truth_geometric_candidate": provenance["score"] * geometric_candidate,
        "legacy_weight_ablation": legacy_weight_ablation,
        "minimum_axis": min(
            fact["score"],
            evidence["score"],
            completeness["score"],
            rubric["score"],
        ),
        "geometric_quality_ablation": geometric_candidate,
    }


__all__ = ["FACT_VERDICTS", "RUBRIC_VALUES", "score_four_axis"]
