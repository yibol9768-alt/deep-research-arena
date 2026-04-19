"""Pairwise LLM-judge battle (Chatbot Arena style).

Given two agent answers to the same task, ask an LLM judge: which is
better overall? Returns winner ∈ {"A", "B", "tie"}, with brief rationale.

This is the gold standard for open-ended generation evaluation
(Zheng et al. MT-Bench 2023, lmsys Arena). It's noisy but unbiased
between architectures (treats prose vs JSON the same way a human would
— "did the report answer my question well?").

Mitigations against known judge biases:
  - Position bias  : run twice swapping (A,B) ↔ (B,A); average outcome
  - Length bias    : explicit instruction to discount verbosity
  - Self-preference: when comparing same-family models, recommend dual
                     judges (GLM + Claude) and report agreement κ
"""

from __future__ import annotations

import json
import os
import re
import textwrap
from typing import Any


JUDGE_MODEL = os.environ.get("PAIRWISE_JUDGE_MODEL", "glm-5.1")

_SYSTEM = textwrap.dedent("""\
    You are an expert reviewer judging two deep-research agent reports
    on the SAME research task. Decide which one better answers the
    research question.

    Consider, in this priority order:
      1. Did the report directly answer the question? (instruction following)
      2. Are the facts correct and grounded? (URLs / numbers verifiable on
         the source pages, no hallucinated products / prices / ratings)
      3. How comprehensive is the analysis? (covers all requested facets)
      4. Is the reasoning insightful, not just enumeration?
      5. Is it readable and well-structured?

    Explicitly DISCOUNT verbosity — a tight, correct answer beats a long
    rambling one. Markdown vs. JSON formatting is fine; only penalize if
    the task explicitly required a specific format AND the report
    ignored it.

    Output Chain-of-Thought reasoning (≤ 6 short bullet points), then a
    final verdict line that MUST match exactly one of:
        VERDICT: A
        VERDICT: B
        VERDICT: TIE

    Use TIE only if the two are genuinely indistinguishable in quality.
""")


def _extract_verdict(text: str) -> str:
    m = re.search(r"VERDICT:\s*(A|B|TIE)", text or "", re.I)
    if not m:
        return "tie"
    v = m.group(1).upper()
    return v if v in ("A", "B", "TIE") else "tie"


from src.verifiers.judge_client import call_judge  # pluggable backend


def _judge_once(model_unused: str, task_intent: str, ans_a: str, ans_b: str) -> tuple[str, str]:
    user = (
        f"Research task:\n{task_intent}\n\n"
        f"--- Report A ---\n{(ans_a or '')[:5000]}\n\n"
        f"--- Report B ---\n{(ans_b or '')[:5000]}\n\n"
        "Reason briefly, then emit `VERDICT: A | B | TIE`."
    )
    text, err = call_judge(_SYSTEM, user, max_tokens=1500)
    if text is None:
        return "tie", f"(judge error: {err})"
    return _extract_verdict(text), text[:600]


def battle(
    *,
    task_intent: str,
    agent_a: str,
    answer_a: str,
    agent_b: str,
    answer_b: str,
    model: str | None = None,
    swap_for_position_bias: bool = True,
) -> dict[str, Any]:
    """Run a pairwise LLM-judge battle. Returns:

    {
      "winner": "A" | "B" | "tie",
      "agent_winner": <agent name or "tie">,
      "verdicts_raw": [first_verdict, swap_verdict],
      "reasonings": [...],
    }

    `winner` corresponds to the FIRST presentation order.
    `agent_winner` resolves the "A"/"B" labels back to the agent names,
    accounting for the swap.
    """
    m = model or JUDGE_MODEL
    try:
        v1, r1 = _judge_once(m, task_intent, answer_a, answer_b)
        if not swap_for_position_bias:
            return _resolve(v1, [v1], [r1], agent_a, agent_b)
        v2_swapped, r2 = _judge_once(m, task_intent, answer_b, answer_a)
        # Un-swap verdict 2: if judge said A under swap (= original B),
        # then the real winner is B
        v2 = {"A": "B", "B": "A", "TIE": "TIE"}[v2_swapped]
        # Combine both verdicts
        if v1 == v2:
            final = v1
        elif "TIE" in (v1, v2):
            final = v1 if v2 == "TIE" else v2
        else:
            final = "TIE"  # A and B disagree → tie
        return _resolve(final, [v1, v2], [r1, r2], agent_a, agent_b)
    except Exception as e:
        return {"winner": "tie", "agent_winner": "tie", "error": f"{type(e).__name__}: {e}"}


def _resolve(verdict: str, all_v: list[str], all_r: list[str], agent_a: str, agent_b: str) -> dict[str, Any]:
    if verdict == "A":
        agent_winner = agent_a
    elif verdict == "B":
        agent_winner = agent_b
    else:
        agent_winner = "tie"
    return {
        "winner": verdict.lower() if verdict != "TIE" else "tie",
        "agent_winner": agent_winner,
        "verdicts_raw": all_v,
        "reasonings": all_r,
        "judge_model": JUDGE_MODEL,
    }
