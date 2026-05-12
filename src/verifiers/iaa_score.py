"""IAA helper — Cohen's κ and Krippendorff's α for must-cite annotation.

Two annotators independently produce a must-cite list (subset of all
sandbox URLs that they think the report should cite). We model this as
binary classification on the union of both lists: each URL is either
"include" or "exclude" per annotator.

Usage:
    python3 -m src.verifiers.iaa_score \\
        --annotator-a data/annotation/0001/alice_must_cite.json \\
        --annotator-b data/annotation/0001/bob_must_cite.json

Each input is a JSON list of URL strings.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _cohens_kappa(a: list[int], b: list[int]) -> float:
    """Both lists same length, values in {0,1}. Returns κ."""
    if len(a) != len(b):
        raise ValueError("a and b must have same length")
    n = len(a)
    if n == 0:
        return 0.0
    agree = sum(1 for x, y in zip(a, b) if x == y)
    p_o = agree / n
    p_a1 = sum(a) / n
    p_b1 = sum(b) / n
    p_e = p_a1 * p_b1 + (1 - p_a1) * (1 - p_b1)
    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1.0 - p_e)


def _krippendorff_alpha_binary(a: list[int], b: list[int]) -> float:
    """Krippendorff's α for nominal binary data with 2 coders.
    For binary nominal with no missing data this equals
    1 - n_disagree / n_expected_disagree.
    """
    if len(a) != len(b):
        raise ValueError("a and b must have same length")
    n = len(a)
    if n == 0:
        return 0.0
    n_disagree = sum(1 for x, y in zip(a, b) if x != y)
    p1 = (sum(a) + sum(b)) / (2 * n)
    p0 = 1.0 - p1
    expected = 2.0 * p1 * p0
    if expected == 0:
        return 1.0 if n_disagree == 0 else 0.0
    return 1.0 - (n_disagree / n) / expected


def cohen_kappa(set_a: set[str], set_b: set[str]) -> dict:
    union = sorted(set_a | set_b)
    a = [1 if u in set_a else 0 for u in union]
    b = [1 if u in set_b else 0 for u in union]
    k = _cohens_kappa(a, b)
    alpha = _krippendorff_alpha_binary(a, b)
    intersection = set_a & set_b
    return {
        "n_universe":    len(union),
        "n_a_only":      len(set_a - set_b),
        "n_b_only":      len(set_b - set_a),
        "n_both":        len(intersection),
        "cohens_kappa":  round(k, 4),
        "krippendorff_alpha": round(alpha, 4),
        "interpretation": _interpret(k),
    }


def _interpret(k: float) -> str:
    if k < 0:    return "worse than chance"
    if k < 0.21: return "slight (Landis-Koch)"
    if k < 0.41: return "fair"
    if k < 0.61: return "moderate"
    if k < 0.81: return "substantial — acceptable per Fleiss >0.75"
    return "almost perfect"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--annotator-a", required=True)
    ap.add_argument("--annotator-b", required=True)
    args = ap.parse_args()

    a_set = set(json.loads(Path(args.annotator_a).read_text()))
    b_set = set(json.loads(Path(args.annotator_b).read_text()))
    result = cohen_kappa(a_set, b_set)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
