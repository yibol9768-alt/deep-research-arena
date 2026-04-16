"""Tests for Elo computation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.scoring import compute_elo


def test_elo_deterministic_winner():
    """Agent A wins every battle → A > B > C in Elo."""
    recs = [
        {"task_id": "t1", "agent": "A", "composite": 0.9},
        {"task_id": "t1", "agent": "B", "composite": 0.5},
        {"task_id": "t1", "agent": "C", "composite": 0.1},
        {"task_id": "t2", "agent": "A", "composite": 0.8},
        {"task_id": "t2", "agent": "B", "composite": 0.6},
        {"task_id": "t2", "agent": "C", "composite": 0.3},
    ]
    elos = compute_elo(recs)
    assert elos["A"]["elo"] > elos["B"]["elo"] > elos["C"]["elo"]
    assert elos["A"]["wins"] == 4  # beats B twice, C twice
    assert elos["C"]["losses"] == 4
    assert elos["B"]["wins"] == 2 and elos["B"]["losses"] == 2


def test_elo_ties_within_eps():
    """Close composites → tie, not a win."""
    recs = [
        {"task_id": "t1", "agent": "A", "composite": 0.500},
        {"task_id": "t1", "agent": "B", "composite": 0.510},
    ]
    elos = compute_elo(recs, tie_eps=0.02)
    assert elos["A"]["draws"] == 1
    assert elos["B"]["draws"] == 1
    assert elos["A"]["wins"] == 0
    # Ratings stay near START_RATING on a single tie
    assert abs(elos["A"]["elo"] - 1000.0) < 5
    assert abs(elos["B"]["elo"] - 1000.0) < 5


def test_elo_no_records():
    assert compute_elo([]) == {}
