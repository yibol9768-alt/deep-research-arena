"""Unified token budget guard for fair agent comparison.

Every agent runner wraps its LLM client in TokenBudgetGuard. When cumulative
input_tokens or output_tokens crosses the per-run cap, the next call raises
BudgetExceeded so the runner can gracefully finalize (emit partial report,
mark the run as budget_capped).

Defaults match v3.3 fairness config:
  - 200k input tokens per run
  - 20k output tokens per run
  - soft margin: last-call warning at 90%

Without this, DeerFlow / ODR burn 500k+ input while smolagents caps at ~80k
just because of their internal architecture. The resulting Elo is "who's
most willing to spend tokens" rather than "who uses tokens best."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


DEFAULT_INPUT_CAP = 200_000
DEFAULT_OUTPUT_CAP = 20_000
WARN_THRESHOLD = 0.9


class BudgetExceeded(Exception):
    """Raised when the next LLM call would exceed the configured cap."""

    def __init__(self, kind: str, used: int, cap: int) -> None:
        super().__init__(f"{kind} budget exceeded: {used} > {cap}")
        self.kind = kind
        self.used = used
        self.cap = cap


@dataclass
class TokenBudgetGuard:
    input_cap: int = DEFAULT_INPUT_CAP
    output_cap: int = DEFAULT_OUTPUT_CAP
    input_used: int = 0
    output_used: int = 0
    warned: bool = False
    on_warn: Callable[[str, int, int], None] | None = None

    def check_before_call(self, est_input: int = 0) -> None:
        """Call before sending a request. Raises if budget already exhausted
        or projected input would exceed the cap."""
        if self.input_used >= self.input_cap:
            raise BudgetExceeded("input", self.input_used, self.input_cap)
        if self.output_used >= self.output_cap:
            raise BudgetExceeded("output", self.output_used, self.output_cap)
        if est_input and self.input_used + est_input > self.input_cap:
            raise BudgetExceeded("input", self.input_used + est_input, self.input_cap)

    def record(self, *, input_tokens: int, output_tokens: int) -> None:
        self.input_used += max(0, int(input_tokens))
        self.output_used += max(0, int(output_tokens))
        if not self.warned:
            in_frac = self.input_used / max(1, self.input_cap)
            out_frac = self.output_used / max(1, self.output_cap)
            if max(in_frac, out_frac) >= WARN_THRESHOLD:
                self.warned = True
                if self.on_warn:
                    self.on_warn(
                        "warn", self.input_used, self.output_used
                    )

    def record_usage_obj(self, usage: Any) -> None:
        """Read token counts out of an OpenAI / Anthropic usage object or dict.
        Accepts any of:
          - {'prompt_tokens': N, 'completion_tokens': M}
          - {'input_tokens': N, 'output_tokens': M}
          - object with .prompt_tokens / .completion_tokens or .input_tokens
        """
        if usage is None:
            return
        if isinstance(usage, dict):
            pt = usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
            ct = usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
        else:
            pt = (
                getattr(usage, "prompt_tokens", None)
                or getattr(usage, "input_tokens", None)
                or 0
            )
            ct = (
                getattr(usage, "completion_tokens", None)
                or getattr(usage, "output_tokens", None)
                or 0
            )
        self.record(input_tokens=pt, output_tokens=ct)

    def snapshot(self) -> dict[str, int]:
        return {
            "input_used": self.input_used,
            "input_cap": self.input_cap,
            "output_used": self.output_used,
            "output_cap": self.output_cap,
            "input_frac": round(self.input_used / max(1, self.input_cap), 3),
            "output_frac": round(self.output_used / max(1, self.output_cap), 3),
        }

    def is_exhausted(self) -> bool:
        return (
            self.input_used >= self.input_cap
            or self.output_used >= self.output_cap
        )
