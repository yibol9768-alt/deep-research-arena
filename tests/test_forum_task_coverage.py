"""The shared search tool must expose every forum promised by formal tasks."""

from __future__ import annotations

import json
from pathlib import Path

from integrations.search_shim import backend


ROOT = Path(__file__).resolve().parents[1]


def test_all_formal_task_forums_are_in_shared_search_inventory():
    declared = set()
    task_dir = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
    for path in task_dir.glob("dr_cross_deep_*.json"):
        task = json.loads(path.read_text())
        if task.get("task_version") != 2:
            continue
        declared.update((task.get("tri_source") or {}).get("forums") or [])

    configured = {f.strip().casefold() for f in backend._DEFAULT_REDDIT_FORUMS if f.strip()}
    missing = {f for f in declared if f.casefold() not in configured}
    assert not missing, f"formal task forums unreachable through search shim: {sorted(missing)}"


def test_generated_answer_keys_preserve_each_tasks_forum_requirement():
    task_dir = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
    key_dir = ROOT / "data" / "golden" / "answer_keys"
    for path in task_dir.glob("dr_cross_deep_*.json"):
        task = json.loads(path.read_text())
        if task.get("task_version") != 2:
            continue
        expected = (task.get("tri_source") or {}).get("forums") or []
        key = json.loads((key_dir / path.name).read_text())
        assert key.get("metadata", {}).get("forums") == expected, path.stem


def test_domain_hints_route_to_task_declared_forums():
    assert "MechanicalKeyboards" in backend._forums_hinted_by_query("quiet mechanical keyboard")
    assert "BuyItForLife" in backend._forums_hinted_by_query("durable carry-on luggage")
    assert "food" in backend._forums_hinted_by_query("coffee grinder for food prep")
    assert "pics" in backend._forums_hinted_by_query("camera photo quality")
