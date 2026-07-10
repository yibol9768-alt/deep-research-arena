from __future__ import annotations

import math

import pytest

from src.scoring.bradley_terry import fit_bradley_terry


def _rename_battles(battles, mapping):
    out = []
    for row in battles:
        r = dict(row)
        r["agent_a"] = mapping[r["agent_a"]]
        r["agent_b"] = mapping[r["agent_b"]]
        if r["winner"] != "tie":
            r["winner"] = mapping[r["winner"]]
        out.append(r)
    return out


def test_bt_is_invariant_to_agent_names():
    battles = [
        {"agent_a": "A", "agent_b": "B", "winner": "A"},
        {"agent_a": "A", "agent_b": "B", "winner": "A"},
        {"agent_a": "B", "agent_b": "C", "winner": "B"},
        {"agent_a": "B", "agent_b": "C", "winner": "tie"},
        {"agent_a": "C", "agent_b": "A", "winner": "C"},
    ]
    mapping = {"A": "Z", "B": "A", "C": "B"}
    base = fit_bradley_terry(battles)
    renamed = fit_bradley_terry(_rename_battles(battles, mapping))
    for old, new in mapping.items():
        assert math.isclose(base[old], renamed[new], abs_tol=1e-5)


def test_bt_refuses_disconnected_comparison_graph():
    battles = [
        {"agent_a": "A", "agent_b": "B", "winner": "A"},
        {"agent_a": "C", "agent_b": "D", "winner": "C"},
    ]
    with pytest.raises(ValueError, match="disconnected"):
        fit_bradley_terry(battles)


def test_bt_accepts_arena_battle_schema():
    battles = [
        {"a1": "A", "a2": "B", "agent_winner": "A"},
        {"a1": "B", "a2": "C", "agent_winner": "B"},
        {"a1": "C", "a2": "A", "agent_winner": "tie"},
    ]
    assert set(fit_bradley_terry(battles)) == {"A", "B", "C"}
