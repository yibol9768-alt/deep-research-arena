"""Efficiency metrics for deep-research agent runs.

Captures the "sixth pillar" of our scoring framework (see
SCORING_FRAMEWORK.md §二): wall-time, token counts, tool-call count,
and a dollar-denominated cost estimate.

Prices are configurable; defaults below are rough list prices for GLM /
DeepSeek coding-plan models at the time of writing (2026-Q2) — used only
to keep cross-agent comparisons on the same scale, not as ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# USD per 1M tokens. Update as provider prices shift.
PRICING: dict[str, dict[str, float]] = {
    "glm-5.1":        {"in": 1.0, "out": 3.0},
    "glm-4.6":        {"in": 0.6, "out": 2.2},
    "glm-4.5":        {"in": 0.4, "out": 1.8},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "claude-opus-4-6":   {"in": 15.0, "out": 75.0},
    "deepseek-v3.2":  {"in": 0.28, "out": 1.12},
    "doubao-seed-2.0-code": {"in": 1.0, "out": 3.0},
}
_DEFAULT_PRICE = {"in": 1.0, "out": 3.0}


@dataclass
class EfficiencyMetrics:
    wall_time_s: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0
    model: str = ""
    # Per-call breakdown kept small, for debugging
    per_call: list[dict[str, Any]] = field(default_factory=list)

    def add_llm_call(self, *, tokens_in: int, tokens_out: int, model: str | None = None) -> None:
        self.llm_calls += 1
        self.tokens_in += int(tokens_in or 0)
        self.tokens_out += int(tokens_out or 0)
        if model and not self.model:
            self.model = model
        price = PRICING.get(model or self.model, _DEFAULT_PRICE)
        self.cost_usd += (tokens_in / 1e6) * price["in"] + (tokens_out / 1e6) * price["out"]
        self.per_call.append({"in": int(tokens_in or 0), "out": int(tokens_out or 0), "model": model or self.model})

    def add_tool_call(self, name: str = "") -> None:
        self.tool_calls += 1

    def merge(self, other: "EfficiencyMetrics") -> None:
        self.wall_time_s += other.wall_time_s
        self.tokens_in += other.tokens_in
        self.tokens_out += other.tokens_out
        self.llm_calls += other.llm_calls
        self.tool_calls += other.tool_calls
        self.cost_usd += other.cost_usd
        self.per_call.extend(other.per_call)
        if not self.model:
            self.model = other.model

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cost_usd"] = round(d["cost_usd"], 5)
        d["wall_time_s"] = round(d["wall_time_s"], 2)
        d["per_call"] = d["per_call"][:20]  # cap
        return d

    def score01(self, *, budget_cost_usd: float = 0.10, budget_time_s: float = 300.0) -> float:
        """Normalize to [0,1]: 1.0 at-or-below budget, linearly decays to 0 at 3× budget.

        Composite combines cost (70%) and time (30%) — cost dominates.
        """
        def _decay(actual: float, budget: float) -> float:
            if actual <= budget:
                return 1.0
            if actual >= 3 * budget:
                return 0.0
            return 1.0 - (actual - budget) / (2 * budget)

        return round(0.7 * _decay(self.cost_usd, budget_cost_usd) + 0.3 * _decay(self.wall_time_s, budget_time_s), 3)


def from_anthropic_response(resp: Any, model: str | None = None) -> tuple[int, int]:
    """Extract (input, output) tokens from an anthropic.Message response."""
    u = getattr(resp, "usage", None)
    if u is None:
        return 0, 0
    return int(getattr(u, "input_tokens", 0) or 0), int(getattr(u, "output_tokens", 0) or 0)


def from_langchain_usage(usage_metadata: dict | None) -> tuple[int, int]:
    """Extract (input, output) tokens from a LangChain AIMessage.usage_metadata."""
    if not usage_metadata:
        return 0, 0
    return int(usage_metadata.get("input_tokens", 0) or 0), int(usage_metadata.get("output_tokens", 0) or 0)
