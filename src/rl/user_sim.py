"""User-simulation seams for transactional RL tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class UserSimClient(Protocol):
    """LLM client seam for simulated user turns."""

    def complete(self, *, system: str, user: str) -> str: ...


@dataclass
class ScriptedUserSimulator:
    """Deterministic fake user simulator for offline tests."""

    turns: list[str]
    default: str = ""
    index: int = 0

    def reset(self) -> None:
        self.index = 0

    def respond(self, observation: dict[str, Any] | None = None) -> str:
        del observation
        if self.index < len(self.turns):
            text = self.turns[self.index]
            self.index += 1
            return text
        return self.default


@dataclass
class LLMSimulatedUser:
    """Small adapter around an injected LLM-style client."""

    client: Any
    system_prompt: str = "You are a concise simulated user for a sandbox task."
    history: list[dict[str, str]] = field(default_factory=list)

    def respond(self, observation: dict[str, Any] | None = None) -> str:
        obs = observation or {}
        user = f"Observation:\n{obs}\n\nRespond as the user in one short turn."
        if callable(self.client):
            text = self.client(self.system_prompt, user)
        elif hasattr(self.client, "complete") and callable(self.client.complete):
            text = self.client.complete(system=self.system_prompt, user=user)
        elif hasattr(self.client, "respond") and callable(self.client.respond):
            text = self.client.respond({"system": self.system_prompt, "user": user, "history": self.history})
        else:
            raise TypeError("user_sim_client must be callable or expose complete/respond")
        out = str(text or "")
        self.history.append({"role": "user", "content": out})
        return out


__all__ = ["ScriptedUserSimulator", "LLMSimulatedUser", "UserSimClient"]
