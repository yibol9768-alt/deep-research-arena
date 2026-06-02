"""Policy protocol and deterministic offline mock policy."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence

from .env import Action, Finalize, Open, Read, Search


@dataclass
class Generation:
    actions: list[Action]
    report_md: str
    token_ids: list[int] | None = None
    logprobs: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Policy(Protocol):
    def act(self, observation: dict[str, Any]) -> Action:
        """Choose one environment action."""

    def generate(self, task_prompt: str, *, n: int) -> list[Generation]:
        """Generate training candidates for a task prompt."""

    def update(self, batch: dict[str, Any]) -> dict[str, float]:
        """Apply one policy update and return training metrics."""


class MockPolicy:
    """Deterministic policy for offline tests.

    ``quality_level`` may be a scalar level, a string level, ``"mixed"``, or
    a sequence of levels. Mixed and sequence levels cycle by episode so GRPO
    tests can create known reward variance without a model.
    """

    def __init__(
        self,
        scripted_actions: Sequence[Action] | Sequence[Sequence[Action]] | None = None,
        quality_level: str | float | Sequence[str | float] = "medium",
    ) -> None:
        self.scripted_actions = scripted_actions
        self.quality_level = quality_level
        self.update_calls = 0
        self.last_update_batch: dict[str, Any] | None = None
        self.saved_state: dict[str, Any] = {}
        self._episode_index = -1
        self._episode_actions: list[Action] = []
        self._cursor = 0
        self._phase = 0
        self._current_quality = "medium"

    def start_episode(self, task_config: dict[str, Any] | None = None) -> None:
        self._episode_index += 1
        self._cursor = 0
        self._phase = 0
        self._current_quality = self._quality_for_episode(self._episode_index)
        self._episode_actions = self._script_for_episode(self._episode_index)

    def act(self, observation: dict[str, Any]) -> Action:
        if self._episode_index < 0:
            self.start_episode(observation.get("task_config") or {})

        if self._episode_actions:
            if self._cursor < len(self._episode_actions):
                action = self._episode_actions[self._cursor]
                self._cursor += 1
                return action
            return Finalize(str(observation.get("report_md") or ""))

        quality = self._current_quality
        if quality in {"low", "bad", "poor"}:
            return self._act_low(observation)
        if quality in {"high", "good", "strong"}:
            return self._act_high(observation, target_reads=2)
        return self._act_high(observation, target_reads=1)

    def generate(self, task_prompt: str, *, n: int) -> list[Generation]:
        generations: list[Generation] = []
        for i in range(n):
            quality = self._quality_for_episode(i)
            if quality in {"high", "good", "strong"}:
                report = _report_from_sources(
                    task_prompt,
                    {"http://localhost:7770/mock-high.html": "alpha battery comfort sound evidence"},
                )
                actions: list[Action] = [
                    Search(task_prompt),
                    Open("http://localhost:7770/mock-high.html"),
                    Read(),
                    Finalize(report),
                ]
            else:
                report = _low_report(task_prompt)
                actions = [Search(task_prompt), Finalize(report)]
            generations.append(
                Generation(
                    actions=actions,
                    report_md=report,
                    token_ids=[i, len(actions)],
                    logprobs=[-0.1 for _ in actions],
                    metadata={"quality_level": quality},
                )
            )
        return generations

    def update(self, batch: dict[str, Any]) -> dict[str, float]:
        self.update_calls += 1
        self.last_update_batch = batch
        advantages = [float(v) for v in batch.get("advantages", [])]
        mean_abs_adv = (
            sum(abs(v) for v in advantages) / len(advantages)
            if advantages else 0.0
        )
        return {
            "loss": round(-mean_abs_adv, 6),
            "mock_updates": float(self.update_calls),
        }

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        payload = {
            "update_calls": self.update_calls,
            "episode_index": self._episode_index,
            "quality_level": _jsonable_quality(self.quality_level),
        }
        (target / "mock_policy.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def load(self, path: str | Path) -> None:
        payload_path = Path(path) / "mock_policy.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        self.update_calls = int(payload.get("update_calls", 0))
        self._episode_index = int(payload.get("episode_index", -1))
        self.saved_state = payload

    def _script_for_episode(self, index: int) -> list[Action]:
        scripted = self.scripted_actions
        if scripted is None:
            return []
        rows = list(scripted)
        if not rows:
            return []
        first = rows[0]
        if isinstance(first, (list, tuple)):
            choices = [list(row) for row in rows]  # type: ignore[arg-type]
            return list(choices[index % len(choices)])
        return list(rows)  # type: ignore[list-item]

    def _quality_for_episode(self, index: int) -> str:
        level = self.quality_level
        if isinstance(level, (list, tuple)):
            if not level:
                return "medium"
            return _quality_label(level[index % len(level)])
        if isinstance(level, str) and level.lower() == "mixed":
            return ["high", "low", "medium", "low"][index % 4]
        return _quality_label(level)

    def _act_low(self, observation: dict[str, Any]) -> Action:
        if self._phase == 0:
            self._phase += 1
            return Search(_prompt(observation))
        self._phase += 1
        return Finalize(_low_report(_prompt(observation)))

    def _act_high(self, observation: dict[str, Any], *, target_reads: int) -> Action:
        fetched = list(observation.get("fetched_urls") or [])
        results = list(observation.get("search_results") or [])
        current_url = observation.get("current_url")
        current_page = observation.get("current_page_text")

        if self._phase == 0:
            self._phase += 1
            return Search(_prompt(observation))

        if len(fetched) < target_reads:
            next_url = _next_unfetched_url(results, fetched)
            if current_url and not current_page and current_url not in fetched:
                self._phase += 1
                return Read()
            if next_url:
                self._phase += 1
                return Open(next_url)
            if current_url and current_url not in fetched:
                self._phase += 1
                return Read()

        self._phase += 1
        snippets = observation.get("retrieved_snippets") or {}
        if not snippets and current_url and current_page:
            snippets = {str(current_url): str(current_page)}
        return Finalize(_report_from_sources(_prompt(observation), snippets))


def _prompt(observation: dict[str, Any]) -> str:
    return str(observation.get("prompt") or "Research the task.")


def _quality_label(level: str | float) -> str:
    if isinstance(level, (int, float)):
        value = float(level)
        if value >= 0.75:
            return "high"
        if value <= 0.35:
            return "low"
        return "medium"
    lowered = str(level).lower().strip()
    aliases = {
        "good": "high",
        "strong": "high",
        "bad": "low",
        "poor": "low",
    }
    return aliases.get(lowered, lowered or "medium")


def _next_unfetched_url(results: list[Any], fetched: list[str]) -> str | None:
    fetched_set = set(fetched)
    for hit in results:
        if isinstance(hit, dict):
            url = str(hit.get("url") or "")
        else:
            url = str(hit)
        if url and url not in fetched_set:
            return url
    return None


def _report_from_sources(task_prompt: str, snippets: dict[str, str]) -> str:
    rows = [(str(url), str(text)) for url, text in snippets.items() if str(text).strip()]
    if not rows:
        rows = [("http://localhost:7770/mock-empty.html", "missing evidence")]

    paragraphs = ["# Research Report"]
    for idx, (url, text) in enumerate(rows[:3], start=1):
        claim = _short_claim(text)
        paragraphs.append(f"{claim} [source {idx}]({url}).")

    paragraphs.append(
        "The sources are used together to compare evidence, limits, and practical "
        "implications for the task. This grounded synthesis favors claims that "
        "are directly supported by the retrieved pages."
    )
    paragraphs.append(
        f"Task focus: {task_prompt}. The answer cites only pages opened during "
        "the rollout and avoids unsupported extra links."
    )
    return "\n\n".join(paragraphs)


def _short_claim(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    selected = words[:6] or ["retrieved", "page", "contains", "supporting", "evidence"]
    return " ".join(selected)


def _low_report(task_prompt: str) -> str:
    return (
        "# Brief Answer\n\n"
        f"{task_prompt} appears to have a simple answer, but this draft does "
        "not collect enough evidence or provide grounded citations."
    )


def _jsonable_quality(level: Any) -> Any:
    if isinstance(level, tuple):
        return list(level)
    return level


__all__ = ["Generation", "MockPolicy", "Policy"]
