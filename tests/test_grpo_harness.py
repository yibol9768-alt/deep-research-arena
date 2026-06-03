from __future__ import annotations

import json
import math
from pathlib import Path

from src.eval.evaluator import ArenaEvaluator
from src.rl.env import (
    Cite,
    Finalize,
    MockSandboxBackend,
    Open,
    Read,
    ReadMemory,
    ResearchEnv,
    Search,
    WriteMemory,
)
from src.rl.grpo import GRPOConfig, GRPOTrainer
from src.rl.policy import MockPolicy
from src.rl.runner import collect_group, run_episode
from src.rubrics.store import RubricItem, RubricStore
from src.verifiers.citation_format import canonicalize_url


TASK_ID = "rl_harness_synth"
PROMPT = "Compare Alpha headphones with forum evidence."
URL_A = "http://localhost:7770/product-a.html"
URL_B = "http://localhost:7770/forum-thread.html"

PAGES = {
    URL_A: (
        "Alpha headphones balanced sound battery comfort travel value evidence "
        "comes from a product test with practical limitations."
    ),
    URL_B: (
        "Forum owners report long term comfort value fit durability evidence "
        "for Alpha headphones in everyday use."
    ),
}


def _write_golden(tmp_path: Path) -> Path:
    path = tmp_path / "golden.json"
    rows = [{"url": URL_A, "weight": 1.0}, {"url": URL_B, "weight": 1.0}]
    path.write_text(
        json.dumps({
            "must_cite_urls": rows,
            "expected_pool_urls": rows,
        }),
        encoding="utf-8",
    )
    return path


def _task_config(tmp_path: Path) -> dict:
    return {
        "task_id": TASK_ID,
        "intent": PROMPT,
        "sandbox_hosts": ["localhost:7770"],
        "markdown_spec": {
            "min_words": 20,
            "max_words": 220,
            "min_paragraphs": 2,
            "min_citations": 1,
            "min_pages_browsed": 0,
        },
        "citation_policy": {"must_be_in_domain": []},
        "perspective_balance": {
            "evaluated_entities": ["Alpha headphones"],
            "min_score": 0.5,
        },
        "url_coverage": {
            "golden_pool_path": str(_write_golden(tmp_path)),
            "min_unique_urls_cited": 1,
            "min_must_cite_recall": 0.0,
            "min_expected_pool_coverage": 0.0,
            "min_domain_balance": 0.0,
        },
        "search": {"target_distinct_queries": 1},
    }


def _backend() -> MockSandboxBackend:
    return MockSandboxBackend(PAGES, {PROMPT: [URL_A, URL_B]})


def _evaluator_factory(task_config: dict):
    def factory(task_id: str) -> ArenaEvaluator:
        evaluator = ArenaEvaluator(task_id, mode="fast")
        evaluator._task_config = task_config
        return evaluator

    return factory


def _rubric_item(item_id: str, criterion: str, *, tier: str = "active") -> RubricItem:
    return RubricItem(
        id=item_id,
        criterion=criterion,
        weight=1.0,
        is_deterministic=(tier == "persist"),
        polarity="positive",
        tier=tier,
        origin="test",
    )


def test_env_scripted_sequence_produces_rollout_and_enforces_cap(tmp_path: Path):
    config = _task_config(tmp_path)
    report = f"# Report\n\nAlpha headphones balanced sound [a]({URL_A})."
    policy = MockPolicy(
        scripted_actions=[
            Search(PROMPT),
            Open(URL_A),
            Read(),
            WriteMemory("alpha note"),
            ReadMemory(),
            Cite(URL_A),
            Finalize(report),
        ]
    )
    rollout = run_episode(config, ResearchEnv(config, _backend()), policy)

    assert [call["endpoint"] for call in rollout.tool_calls] == [
        "/search",
        "/open",
        "/fetch",
        "/memory/write",
        "/memory/read",
        "/cite",
    ]
    assert rollout.fetched_urls == [URL_A]
    assert rollout.retrieved_snippets[canonicalize_url(URL_A)] == PAGES[URL_A]
    assert rollout.report_md == report
    assert rollout.trace["memory"] == ["alpha note"]
    assert rollout.step_count == 7

    capped = ResearchEnv(config, _backend(), max_tool_calls=1)
    capped.reset()
    _obs, done, info = capped.step(Search(PROMPT))
    assert done is False
    _obs, done, info = capped.step(Open(URL_A))
    assert done is True
    assert info["error"] == "tool_call_cap_exceeded"
    assert len(capped.to_rollout().tool_calls) == 1


def test_runner_episode_and_collect_group(tmp_path: Path):
    config = _task_config(tmp_path)
    rollout = run_episode(
        config,
        ResearchEnv(config, _backend()),
        MockPolicy(quality_level="high"),
    )
    assert rollout.report_md
    assert rollout.fetched_urls

    group = collect_group(
        config,
        _backend,
        MockPolicy(quality_level=["high", "low"]),
        g=4,
    )
    assert len(group) == 4
    assert all(row.task_id == TASK_ID for row in group)
    assert any(row.fetched_urls for row in group)
    assert any(not row.fetched_urls for row in group)


def test_grpo_step_varied_rewards_and_degenerate_advantages(tmp_path: Path):
    config = _task_config(tmp_path)
    varied_policy = MockPolicy(quality_level=["high", "low"])
    trainer = GRPOTrainer(
        varied_policy,
        _evaluator_factory(config),
        {TASK_ID: RubricStore(TASK_ID)},
        GRPOConfig(g=4, refresh_every_n=99),
    )

    stats = trainer.step(config, _backend)
    assert len(set(round(r, 6) for r in stats.rewards)) > 1
    assert abs(stats.advantage_mean) < 1e-6
    assert math.isclose(stats.advantage_std, 1.0, rel_tol=1e-6, abs_tol=1e-6)
    assert varied_policy.update_calls == 1
    assert varied_policy.last_update_batch is not None
    assert varied_policy.last_update_batch["advantages"] == stats.advantages
    assert varied_policy.last_update_batch["mask_tool_tokens"] is True
    assert varied_policy.last_update_batch["tool_token_masks"]

    equal_policy = MockPolicy(quality_level="high")
    equal_trainer = GRPOTrainer(
        equal_policy,
        _evaluator_factory(config),
        {TASK_ID: RubricStore(TASK_ID)},
        GRPOConfig(g=3, refresh_every_n=99),
    )
    equal_stats = equal_trainer.step(config, _backend)
    assert len(set(round(r, 6) for r in equal_stats.rewards)) == 1
    assert equal_stats.advantages == [0.0, 0.0, 0.0]


def test_rubric_refresh_fires_on_interval_and_next_snapshot_is_used(
    monkeypatch,
    tmp_path: Path,
):
    config = _task_config(tmp_path)
    store = RubricStore(TASK_ID)
    calls: list[list[float]] = []

    def fake_generate(task_config: dict, rollouts: list[dict], *, k: int = 5, model=None):
        calls.append([float(row["reward"]) for row in rollouts])
        return [_rubric_item("active-new", "Uses both Alpha evidence sources")]

    monkeypatch.setattr(
        "src.rubrics.generator.generate_active_rubrics",
        fake_generate,
    )

    policy = MockPolicy(quality_level=["high", "low"])
    trainer = GRPOTrainer(
        policy,
        _evaluator_factory(config),
        {TASK_ID: store},
        GRPOConfig(g=4, refresh_every_n=2, kmax=5),
    )

    first = trainer.step(config, _backend)
    assert first.refreshed is False
    assert policy.last_update_batch["rubric_snapshot"]["version"] == 0

    second = trainer.step(config, _backend)
    assert second.refreshed is True
    assert len(calls) == 1
    assert store.version == 1

    third = trainer.step(config, _backend)
    assert third.rubric_version == 1
    assert policy.last_update_batch["rubric_snapshot"]["version"] == 1


def test_evaluator_is_rl_strict_by_default(tmp_path: Path):
    # The live RL training loop must run with strict grounding so a rollout
    # that cites sandbox URLs but fetched no pages scores 0 instead of taking
    # the text-only proxy branch. _evaluator must force _rl_strict=True even
    # when the default factory or a factory that forgets the flag is used.
    config = _task_config(tmp_path)

    # Default factory (no custom factory passed): must still be strict.
    default_trainer = GRPOTrainer(
        MockPolicy(quality_level="high"),
        None,
        {TASK_ID: RubricStore(TASK_ID)},
        GRPOConfig(g=2, refresh_every_n=99),
    )
    default_eval = default_trainer._evaluator(TASK_ID, config)
    assert default_eval._rl_strict is True
    assert default_eval._task_config == config

    # Custom factory that omits the flag: _evaluator must still force it on.
    def forgetful_factory(task_id: str) -> ArenaEvaluator:
        return ArenaEvaluator(task_id, mode="fast")

    forgetful_trainer = GRPOTrainer(
        MockPolicy(quality_level="high"),
        forgetful_factory,
        {TASK_ID: RubricStore(TASK_ID)},
        GRPOConfig(g=2, refresh_every_n=99),
    )
    forgetful_eval = forgetful_trainer._evaluator(TASK_ID, config)
    assert forgetful_eval._rl_strict is True


def test_checkpoint_roundtrip_restores_trainer_and_rubric_state(tmp_path: Path):
    config = _task_config(tmp_path)
    store = RubricStore(TASK_ID)
    store.set_persist([_rubric_item("persist-1", "Mentions Alpha", tier="persist")])
    store.replace_active([_rubric_item("active-1", "Uses forum evidence")])
    policy = MockPolicy(quality_level="high")
    trainer = GRPOTrainer(
        policy,
        _evaluator_factory(config),
        {TASK_ID: store},
        GRPOConfig(g=2, refresh_every_n=99),
    )
    trainer.step(config, _backend)

    ckpt = tmp_path / "ckpt"
    trainer.save_checkpoint(ckpt)

    loaded_policy = MockPolicy(quality_level="low")
    loaded = GRPOTrainer(
        loaded_policy,
        _evaluator_factory(config),
        {},
        GRPOConfig(g=8, refresh_every_n=16),
    )
    loaded.load_checkpoint(ckpt)

    assert loaded.step_count == trainer.step_count
    assert loaded.task_steps == trainer.task_steps
    assert loaded.scheduler.last_refresh == trainer.scheduler.last_refresh
    assert loaded.config.g == 2
    assert loaded.rubric_stores[TASK_ID].version == store.version
    assert [item.id for item in loaded.rubric_stores[TASK_ID].persist] == ["persist-1"]
    assert [item.id for item in loaded.rubric_stores[TASK_ID].active] == ["active-1"]
    assert loaded_policy.update_calls == policy.update_calls
