"""Rubric buffer pruning utilities."""

from __future__ import annotations

import statistics

from .store import RubricItem


def manage_buffer(
    items: list[RubricItem],
    per_item_scores: dict[str, list[float]],
    *,
    kmax: int = 5,
) -> list[RubricItem]:
    """Drop non-discriminative rubrics and keep the highest-variance items."""

    if kmax <= 0:
        return []

    ranked: list[tuple[float, int, RubricItem]] = []
    for index, item in enumerate(items):
        raw_scores = per_item_scores.get(item.id, [])
        scores = [float(score) for score in raw_scores]
        if len(scores) < 2:
            continue
        stdev = statistics.pstdev(scores)
        if stdev <= 1e-12:
            continue
        ranked.append((stdev, index, item))

    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [item for _, _, item in ranked[:kmax]]
