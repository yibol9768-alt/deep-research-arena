"""LLM-as-judge verifier (RACE-style 4 dimensions, G-Eval-style CoT).

Scores a deep-research agent answer on four dimensions, each integer 1–5:

  - comprehensiveness       did it cover every facet the intent asks for?
  - insight_depth           does the analysis go beyond enumeration?
  - instruction_following   did it obey output schema / constraints?
  - readability             is structure / language / formatting clear?

Weighted aggregate (RACE default weights): 0.35 / 0.25 / 0.25 / 0.15.
Returns verifier.score = weighted_total / 5.0 ∈ [0.2, 1.0].

Defaults to GLM-5.1 via Anthropic-compat endpoint (same as our agents).
Set `JUDGE_MODEL` env var to override.

Notes:
  - Uses Chain-of-Thought: judge is asked to *explain* each score before
    emitting the numeric value. Zheng et al. (MT-Bench, 2023) show this
    markedly reduces LLM-judge variance.
  - Returns a structured `details` dict with per-dim scores + judge's
    reasoning. The caller can inspect reasoning to debug disagreements.
  - The judge never sees the report schema verbatim; we pass the
    *intent* so it grades what a user would care about.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .base import VerifierResult


JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "glm-5.1")

DIMENSIONS = [
    ("comprehensiveness",    0.35),
    ("insight_depth",        0.25),
    ("instruction_following", 0.25),
    ("readability",          0.15),
]

_SYSTEM = (
    "You are an expert reviewer grading a deep-research agent's report. "
    "You will score the report on FOUR dimensions, each integer 1..5:\n"
    "  - comprehensiveness:      1=misses key facets the question asks for; 5=covers every requested facet\n"
    "  - insight_depth:          1=surface enumeration only; 5=non-obvious analysis / tradeoffs / caveats\n"
    "  - instruction_following:  1=ignores output format / constraints; 5=strict adherence to the spec given\n"
    "  - readability:            1=disorganized / unclear; 5=clear structure, well-formatted, no ambiguity\n\n"
    "Be calibrated:\n"
    "  - a correct but minimal answer is a 3, not a 5\n"
    "  - a 5 requires the report to be genuinely hard to improve\n"
    "  - a 1 requires the dimension to be essentially absent\n\n"
    "You MUST use Chain-of-Thought: first reason briefly per dimension, "
    "then emit the scores as STRICT JSON. The JSON MUST be the LAST "
    "content in your reply, wrapped in ```json fences, matching this shape:\n"
    '{"comprehensiveness":N,"insight_depth":N,"instruction_following":N,'
    '"readability":N,"reason":"one sentence overall"}\n'
    "No prose after the closing fence."
)


def _extract_json(text: str) -> dict | None:
    # Prefer the last fenced block, fall back to any {...}
    fenced = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    for candidate in reversed(fenced):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _build_judge_client():
    """Lazy import anthropic + configure Zhipu endpoint."""
    try:
        import anthropic  # type: ignore
    except Exception:
        return None, "anthropic SDK not installed"
    os.environ.setdefault("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
    if not (os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")):
        return None, "set ANTHROPIC_AUTH_TOKEN (Zhipu coding-plan token); see README"
    return anthropic.Anthropic(), None


class LLMJudgeVerifier:
    """4-dimension LLM-as-judge scorer. Dimension scores in [1,5], total in [1,5]."""

    kind = "llm_judge"

    def __init__(self, model: str | None = None, max_tokens: int = 2000) -> None:
        self.model = model or JUDGE_MODEL
        self.max_tokens = max_tokens

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any = None) -> VerifierResult:
        intent = task_config.get("intent", "(intent missing)")
        schema = task_config.get("report_schema")
        schema_hint = ""
        if schema:
            try:
                schema_hint = (
                    "\n\nAgent was asked to return JSON matching this schema:\n"
                    + json.dumps(schema, ensure_ascii=False)[:1500]
                )
            except Exception:
                pass

        user_msg = (
            f"Research intent:\n{intent}\n"
            f"{schema_hint}\n\n"
            f"Agent report (truncated at 6k chars):\n---\n{(answer or '')[:6000]}\n---\n\n"
            "Grade the report now. Think step-by-step, then emit the JSON."
        )

        client, err = _build_judge_client()
        if client is None:
            return VerifierResult.fail(f"judge client unavailable: {err}")

        try:
            resp = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            text = ""
            for block in resp.content:
                if getattr(block, "type", None) == "text":
                    text += block.text
        except Exception as e:
            return VerifierResult.fail(f"judge call failed: {type(e).__name__}: {e}")

        parsed = _extract_json(text)
        if not parsed:
            return VerifierResult(
                score=0.0, passed=False,
                details={"reason": "judge produced unparseable output", "raw": text[:800]},
            )

        dim_scores: dict[str, int] = {}
        for name, _w in DIMENSIONS:
            v = parsed.get(name)
            try:
                iv = int(v)
            except Exception:
                iv = 1
            dim_scores[name] = max(1, min(5, iv))

        weighted_5 = sum(w * dim_scores[name] for name, w in DIMENSIONS)
        score01 = weighted_5 / 5.0  # normalize to 0-1 for composite

        passed = weighted_5 >= 3.5  # Rubric: "solid research" bar ≈ 3.5/5

        return VerifierResult(
            score=round(score01, 3),
            passed=passed,
            details={
                **dim_scores,
                "weighted_1_5": round(weighted_5, 3),
                "judge_model": self.model,
                "reason": parsed.get("reason", ""),
                "weights": {n: w for n, w in DIMENSIONS},
            },
        )
