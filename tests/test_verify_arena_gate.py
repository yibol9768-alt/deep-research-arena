"""G-1 unit tests for the Arena-Score grounding-gate verifier.

Deterministic and model-free: synthetic reach/winrate maps exercise the PASS
corner, the FAIL corner (a low-reach fabricator out-scoring an honest system),
and the grid/boundary arithmetic.
"""
from __future__ import annotations

from scripts.verify_arena_gate import (
    _adv_grid,
    arena,
    verify_arena_gate,
)


def test_pass_when_honest_systems_dominate():
    # Every real system clears floor 0.6 AND has a winrate high enough that its
    # arena beats the strongest adversary (reach=0.31, wr=1.0 -> 0.1726).
    reaches = {"honest_a": 0.95, "honest_b": 0.80, "lowreach": 0.20}
    winrates = {"honest_a": 0.70, "honest_b": 0.60, "lowreach": 0.99}
    res = verify_arena_gate(reaches, winrates, gamma=1.5, reach_floor=0.6)
    assert res["status"] == "PASS"
    assert res["passed"] is True
    assert res["min_safe_margin"] >= 0.0
    # only the two high-reach systems are counted as real
    assert res["n_real_systems"] == 2
    assert res["n_real_systems_beaten_by_adversary"] == 0
    # strongest adversary is exactly the top grid corner
    assert res["strongest_adversary"]["reach"] == 0.31
    assert abs(res["strongest_adversary"]["arena"] - arena(0.31, 1.0, 1.5)) < 1e-12


def test_fail_when_fabricator_outscores_honest_system():
    # honest_low has high reach but a weak jury winrate, so its arena
    # (0.9^1.5 * 0.12 = 0.1025) falls UNDER the strongest adversary
    # (0.31^1.5 * 1.0 = 0.1726). The gate must catch this.
    reaches = {"honest_low": 0.90}
    winrates = {"honest_low": 0.12}
    res = verify_arena_gate(reaches, winrates, gamma=1.5, reach_floor=0.6)
    assert res["status"] == "FAIL"
    assert res["passed"] is False
    assert res["min_safe_margin"] < 0.0
    assert res["binding_real_system"]["agent"] == "honest_low"
    assert res["n_real_systems_beaten_by_adversary"] == 1
    assert res["real_systems_beaten"][0]["agent"] == "honest_low"


def test_grid_endpoints_and_margin_arithmetic():
    # grid is inclusive of both endpoints at the given step
    grid = _adv_grid(0.05, 0.31, 0.01)
    assert grid[0] == 0.05
    assert grid[-1] == 0.31
    assert len(grid) == 27
    # margin is exactly (binding real arena) - (top-corner adversary arena)
    reaches = {"h": 0.80}
    winrates = {"h": 0.50}
    res = verify_arena_gate(reaches, winrates, gamma=1.5, reach_floor=0.6)
    expected_margin = arena(0.80, 0.50, 1.5) - arena(0.31, 1.0, 1.5)
    assert abs(res["min_safe_margin"] - expected_margin) < 1e-12


def test_skip_when_no_system_clears_floor():
    reaches = {"a": 0.30, "b": 0.10}
    winrates = {"a": 0.90, "b": 0.90}
    res = verify_arena_gate(reaches, winrates, reach_floor=0.6)
    assert res["status"] == "SKIP"
    assert res["passed"] is None
