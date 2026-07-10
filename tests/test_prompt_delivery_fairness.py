"""Regression tests for full, unexpanded task delivery in STORM lanes."""

from __future__ import annotations

import asyncio
import sys
import types

if "dspy" not in sys.modules:
    dspy = types.ModuleType("dspy")

    class Retrieve:
        def __init__(self, *_args, **_kwargs):
            pass

    dspy.Retrieve = Retrieve
    sys.modules["dspy"] = dspy

from scripts.runners import costorm_runner, storm_runner  # noqa: E402


LONG_INTENT = "opening constraint " + ("context " * 60) + "FINAL REQUIRED CONSTRAINT"


def test_storm_native_worker_receives_complete_intent(monkeypatch, tmp_path):
    captured = {}

    class FakeRunner:
        def run(self, **kwargs):
            captured.update(kwargs)

        def post_run(self):
            pass

    class Queue:
        item = None

        def put(self, item):
            self.item = item

    monkeypatch.setattr(storm_runner, "_build_storm_runner", lambda **_kw: FakeRunner())
    monkeypatch.setattr(storm_runner, "_install_offline_information_table_patch", lambda: None)
    monkeypatch.setattr(storm_runner, "_install_article_generation_guard", lambda: None)
    monkeypatch.setattr(storm_runner, "_extract_article", lambda *_a: "native article")

    queue = Queue()
    storm_runner._storm_native_worker(
        LONG_INTENT,
        "model",
        "http://localhost:8081",
        "http://localhost:8100/v1",
        False,
        str(tmp_path),
        "anything",
        queue,
    )

    assert queue.item == {"ok": True, "report": "native article"}
    assert captured["topic"] == LONG_INTENT
    assert captured["topic"].endswith("FINAL REQUIRED CONSTRAINT")


def test_costorm_uses_full_intent_without_harness_authored_turns(monkeypatch):
    captured = {}

    class Args:
        total_conv_turn = 5
        topic = LONG_INTENT

    class FakeRunner:
        runner_argument = Args()
        conversation_history = []

        def warm_start(self):
            pass

        def step(self, *args, **kwargs):
            captured.setdefault("steps", []).append((args, kwargs))

        def generate_report(self):
            return "# Native report\n\n" + ("framework output " * 10)

    def build(**kwargs):
        captured["build"] = kwargs
        return FakeRunner()

    monkeypatch.setattr(costorm_runner, "_build_costorm_runner", build)

    report = asyncio.run(
        costorm_runner.run(
            LONG_INTENT,
            "model",
            "http://localhost:8081",
            "http://localhost:8100/v1",
        )
    )

    assert report.startswith("# Native report")
    assert captured["build"]["topic"] == LONG_INTENT
    assert captured["build"]["topic"].endswith("FINAL REQUIRED CONSTRAINT")
    assert captured["steps"] == [((), {})] * 5
