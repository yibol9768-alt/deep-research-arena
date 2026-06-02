from __future__ import annotations

from src.rl.user_sim import LLMSimulatedUser, ScriptedUserSimulator


def test_scripted_user_simulator_returns_turns_then_default() -> None:
    sim = ScriptedUserSimulator(["hello", "confirm"], default="done")
    assert sim.respond({}) == "hello"
    assert sim.respond({}) == "confirm"
    assert sim.respond({}) == "done"
    sim.reset()
    assert sim.respond({}) == "hello"


def test_llm_user_simulator_uses_injected_complete_client() -> None:
    class Client:
        def complete(self, *, system: str, user: str) -> str:
            assert "simulated user" in system
            assert "Observation" in user
            return "Please cancel the order."

    sim = LLMSimulatedUser(Client())
    assert sim.respond({"order": "ord-1"}) == "Please cancel the order."
    assert sim.history[-1]["content"] == "Please cancel the order."


def test_llm_user_simulator_accepts_callable() -> None:
    sim = LLMSimulatedUser(lambda system, user: "callable user")
    assert sim.respond({}) == "callable user"
