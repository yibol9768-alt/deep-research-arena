from __future__ import annotations

from pathlib import Path

from src.rubrics import (
    RefreshScheduler,
    RubricItem,
    RubricStore,
    generate_active_rubrics,
    manage_buffer,
    synthesize_negative_rubrics,
)
from src.verifiers.checklist_verifier import ChecklistVerifier


def _item(item_id: str, criterion: str, *, tier: str = "active") -> RubricItem:
    origin = "seed" if tier == "persist" else "generated"
    polarity = "negative" if tier == "negative" else "positive"
    return RubricItem(
        id=item_id,
        criterion=criterion,
        weight=1.0,
        is_deterministic=(tier == "persist"),
        polarity=polarity,
        tier=tier,
        origin=origin,
        version=0,
    )


def test_store_snapshot_verifier_and_json_roundtrip(monkeypatch, tmp_path: Path):
    store = RubricStore("rubric_task")
    store.set_persist([_item("p1", "Mentions the source date", tier="persist")])
    assert store.version == 0

    store.replace_active([_item("a1", "Compares the strong and weak evidence")])
    assert store.version == 1

    store.add_negative([_item("n1", "Uses citation stuffing", tier="negative")])
    assert store.version == 2

    snapshot = store.snapshot()
    assert set(snapshot) == {"version", "items", "negative_items"}
    assert [item["id"] for item in snapshot["items"]] == ["p1", "a1"]
    assert snapshot["negative_items"][0]["polarity"] == "negative"

    def fake_call_judge(system: str, user: str, **kwargs):
        assert "Mentions the source date" in user
        assert "Compares the strong and weak evidence" in user
        return "1. FULL - present\n2. PARTIAL - thin\n", None

    monkeypatch.setattr(
        "src.verifiers.checklist_verifier.call_judge",
        fake_call_judge,
    )
    result = ChecklistVerifier().verify(
        task_config={
            "task_id": "rubric_task",
            "intent": "Write a sourced comparison.",
        },
        answer="The answer mentions the source date and compares evidence.",
        rubric_snapshot=snapshot,
    )
    assert result.details["version"] == "2"
    assert result.details["total"] == 2
    assert result.details["weighted_score"] == 0.75

    store.to_json(base_dir=tmp_path)
    loaded = RubricStore.from_json("rubric_task", base_dir=tmp_path)
    assert loaded.version == store.version
    assert [item.to_dict() for item in loaded.persist] == [
        item.to_dict() for item in store.persist
    ]
    assert [item.to_dict() for item in loaded.active] == [
        item.to_dict() for item in store.active
    ]
    assert [item.to_dict() for item in loaded.negative] == [
        item.to_dict() for item in store.negative
    ]


def test_manage_buffer_drops_zero_variance_and_keeps_top_stdev():
    items = [
        _item("zero", "Already solved"),
        _item("wide", "Separates strongly"),
        _item("medium", "Separates moderately"),
        _item("small", "Separates weakly"),
    ]
    scores = {
        "zero": [1.0, 1.0, 1.0],
        "wide": [0.0, 1.0],
        "medium": [0.0, 0.5, 1.0],
        "small": [0.4, 0.6],
    }

    kept = manage_buffer(items, scores, kmax=2)
    assert [item.id for item in kept] == ["wide", "medium"]

    kept_all = manage_buffer(items, scores, kmax=5)
    assert [item.id for item in kept_all] == ["wide", "medium", "small"]


def test_refresh_scheduler_first_sight_interval_and_task_independence():
    scheduler = RefreshScheduler(n=3)

    assert scheduler.should_refresh("task-a", 0) is True
    assert scheduler.should_refresh("task-a", 1) is False
    assert scheduler.should_refresh("task-a", 2) is False
    assert scheduler.should_refresh("task-a", 3) is True

    assert scheduler.should_refresh("task-b", 1) is True
    assert scheduler.should_refresh("task-b", 3) is False
    assert scheduler.should_refresh("task-b", 4) is True

    assert scheduler.should_refresh("task-a", 5) is False
    assert scheduler.should_refresh("task-a", 6) is True


def test_generate_active_rubrics_parses_canned_output_and_uses_contrast(monkeypatch):
    captured: dict[str, str] = {}

    def fake_heavy(system: str, user: str, **kwargs):
        captured["system"] = system
        captured["user"] = user
        return (
            '[{"criterion": "Uses the warranty date from the product page", '
            '"weight": 0.8}, '
            '{"criterion": "Contrasts forum comfort evidence with spec-sheet claims", '
            '"weight": 1.2}]',
            None,
        )

    monkeypatch.setattr("src.rubrics.generator.call_judge_heavy", fake_heavy)
    rollouts = [
        {
            "report_md": "LOW REPORT ignores the warranty and cites vague claims.",
            "evidence": {"http://bad.example": "weak snippet"},
            "reward": 0.1,
        },
        {
            "report_md": "HIGH REPORT names the warranty date and forum comfort limits.",
            "evidence": {"http://good.example": "warranty date and comfort snippet"},
            "reward": 0.9,
        },
    ]

    items = generate_active_rubrics(
        {"task_id": "rubric_task", "intent": "Compare product evidence."},
        rollouts,
        k=5,
    )

    assert "HIGH REPORT names the warranty date" in captured["user"]
    assert "LOW REPORT ignores the warranty" in captured["user"]
    assert [item.tier for item in items] == ["active", "active"]
    assert [item.origin for item in items] == ["generated", "generated"]
    assert [item.polarity for item in items] == ["positive", "positive"]
    assert items[0].weight == 0.8


def test_synthesize_negative_rubrics_parses_negative_items(monkeypatch):
    def fake_heavy(system: str, user: str, **kwargs):
        assert "anomalously high reward" in user
        return (
            "- Rewards citation stuffing with unrelated links (weight=1.0)\n"
            "- Uses self-congratulatory boilerplate as evidence (weight=0.7)\n",
            None,
        )

    monkeypatch.setattr("src.rubrics.negative_synthesis.call_judge_heavy", fake_heavy)
    items = synthesize_negative_rubrics(
        [
            {
                "report_md": "This answer lists many links but no support.",
                "evidence": {"http://x.example": "unrelated snippet"},
                "reward": 0.95,
            }
        ]
    )

    assert len(items) == 2
    assert all(item.tier == "negative" for item in items)
    assert all(item.polarity == "negative" for item in items)
    assert all(item.origin == "rubicon" for item in items)
