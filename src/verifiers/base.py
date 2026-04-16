from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class VerifierResult:
    score: float
    passed: bool
    details: dict[str, Any]

    @classmethod
    def fail(cls, reason: str, **extra: Any) -> "VerifierResult":
        return cls(score=0.0, passed=False, details={"reason": reason, **extra})

    @classmethod
    def ok(cls, score: float = 1.0, **extra: Any) -> "VerifierResult":
        return cls(score=float(score), passed=score > 0, details=extra)


class Verifier(Protocol):
    """Stateless predicate that scores an execution against a task's success criteria.

    Implementations receive the task spec, the agent's final answer, and a Playwright
    `Page` for live DOM / URL inspection. Must return a score in [0, 1].
    """

    kind: str

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any) -> VerifierResult:
        ...
