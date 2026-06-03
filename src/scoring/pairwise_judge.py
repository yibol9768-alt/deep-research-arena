"""Pairwise LLM-judge battle (Chatbot Arena style).

Given two agent answers to the same task, ask an LLM judge: which is
better overall? Returns winner ∈ {"A", "B", "tie"}, with brief rationale.

This is the gold standard for open-ended generation evaluation
(Zheng et al. MT-Bench 2023, lmsys Arena). It's noisy but unbiased
between architectures (treats prose vs JSON the same way a human would
like "did the report answer my question well?").

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


def _default_judge_model() -> str:
    """Resolve the pairwise judge model at call time.

    Honors PAIRWISE_JUDGE_MODEL first, then the shared JUDGE_MODEL /
    CHECKLIST_JUDGE_MODEL used by the verifiers, so a single judge.env
    drives every judge. Falls back to a DeepSeek model (project default).
    """
    return (
        os.environ.get("PAIRWISE_JUDGE_MODEL")
        or os.environ.get("JUDGE_MODEL")
        or os.environ.get("CHECKLIST_JUDGE_MODEL")
        or "deepseek-v4-flash"
    )

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

    Explicitly DISCOUNT verbosity. A tight, correct answer beats a long
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
from src.verifiers.judge_client import format_evidence_block
from src.verifiers.judge_client import smart_truncate


def _report_cap() -> int:
    """Per-report char cap visible to the judge (env-configurable).

    Raised from the old hard 5000 head-only clip to a larger default so a
    long report's conclusion (where synthesis/depth lives) stays visible.
    """
    try:
        cap = int(os.environ.get("PAIRWISE_REPORT_CAP", "12000"))
    except (TypeError, ValueError):
        cap = 12000
    return cap if cap > 0 else 12000


# Per-dimension framing. When `dimension` is passed to `battle`, the judge is
# asked "which report is stronger on <dimension>, and why?" instead of overall
# quality. Humans labeled by picking a pair winner and citing a dimension, so
# dimension-aware comparative judging is the closer match to the human signal.
_DIMENSION_FOCUS = {
    "depth": (
        "analytical DEPTH: how much genuine multi-source synthesis happens "
        "(reconciling contradictions and driving downstream claims) versus "
        "mere enumeration of facts."
    ),
    "rigor": (
        "logical RIGOR: internal consistency and appropriate hedging. Penalize "
        "internal contradictions and over-claiming; reward flagging weak or "
        "disputed evidence."
    ),
    "style": (
        "STYLE: structure, signposting, and citation integration. Reward clear "
        "sectioning with inline markdown citations; penalize raw dumps and bare "
        "trailing URLs."
    ),
    "checklist": (
        "COVERAGE: which report more completely and verifiably satisfies the "
        "task's coverage criteria, with explicit evidence rather than vague "
        "assertions."
    ),
}


def _system_for_dimension(dimension: str | None) -> str:
    if not dimension:
        return _SYSTEM
    focus = _DIMENSION_FOCUS.get(
        dimension.lower(), f"the {dimension} quality of the report."
    )
    return textwrap.dedent(
        """\
        You are an expert reviewer judging two deep-research agent reports
        on the SAME research task. Decide which report is stronger on ONE
        specific dimension only, and explain why.

        The dimension to judge is {focus}

        Judge ONLY this dimension. Explicitly DISCOUNT verbosity. Markdown
        vs. JSON formatting is fine unless the task required a specific format.

        Output a brief reason (a few short bullets), then a final verdict line
        that MUST match exactly one of:
            VERDICT: A
            VERDICT: B
            VERDICT: TIE

        Use TIE only if the two are genuinely indistinguishable on this
        dimension.
        """
    ).format(focus=focus)


def _judge_once(
    model: str,
    task_intent: str,
    ans_a: str,
    ans_b: str,
    *,
    dimension: str | None = None,
    evidence_a: dict | None = None,
    evidence_b: dict | None = None,
) -> tuple[str, str]:
    ev_a = format_evidence_block(evidence_a)
    ev_b = format_evidence_block(evidence_b)
    cap = _report_cap()
    # Smart truncation keeps BOTH head and conclusion of long reports, so the
    # judge sees intro AND synthesis instead of only the first `cap` chars.
    # Short reports (< cap) pass through verbatim.
    user_parts = [
        f"Research task:\n{task_intent}",
        f"--- Report A ---\n{smart_truncate(ans_a or '', cap=cap)}",
    ]
    if ev_a:
        user_parts.append(f"[Evidence available to Report A]\n{ev_a}")
    user_parts.append(f"--- Report B ---\n{smart_truncate(ans_b or '', cap=cap)}")
    if ev_b:
        user_parts.append(f"[Evidence available to Report B]\n{ev_b}")
    if dimension:
        user_parts.append(
            f"Reason briefly about {dimension} only, then emit "
            "`VERDICT: A | B | TIE`."
        )
    else:
        user_parts.append("Reason briefly, then emit `VERDICT: A | B | TIE`.")
    user = "\n\n".join(user_parts)
    # Thread the resolved judge model through to call_judge so the chosen model
    # is actually honored. Without an explicit model, call_judge silently
    # re-reads JUDGE_MODEL from the environment, which can differ from the
    # model `battle` resolved (and stamped) -> the stamped judge_model lies.
    text, err = call_judge(
        _system_for_dimension(dimension), user, model=model, max_tokens=1500
    )
    if text is None:
        return "tie", f"(judge error: {err})"
    return _extract_verdict(text), text[:600]


def _combine(v1: str, v2: str) -> str:
    """Combine an original-order verdict with an un-swapped verdict."""
    if v1 == v2:
        return v1
    if "TIE" in (v1, v2):
        return v1 if v2 == "TIE" else v2
    return "TIE"  # A and B disagree, so call it a tie


def battle(
    *,
    task_intent: str,
    agent_a: str,
    answer_a: str,
    agent_b: str,
    answer_b: str,
    model: str | None = None,
    swap_for_position_bias: bool = True,
    dimension: str | None = None,
    evidence_a: dict | None = None,
    evidence_b: dict | None = None,
    n_samples: int = 3,
) -> dict[str, Any]:
    """Run a pairwise LLM-judge battle. Returns:

    {
      "winner": "A" | "B" | "tie",
      "agent_winner": <agent name or "tie">,
      "verdicts_raw": [...],
      "reasonings": [...],
    }

    `winner` corresponds to the FIRST presentation order.
    `agent_winner` resolves the "A"/"B" labels back to the agent names,
    accounting for the swap.

    When `dimension` is one of {"depth","rigor","style","checklist"}, the
    judge is asked which report is stronger on THAT dimension specifically
    (closer to how humans labeled pairs). `n_samples` controls how many
    debiased rounds are run; the per-round verdicts are aggregated by
    majority. Position-swap debiasing is kept within each round when
    `swap_for_position_bias` is True. `evidence_a` / `evidence_b` (url ->
    snippet) ground each report against the sources it had access to.
    """
    m = model or _default_judge_model()
    n = max(1, int(n_samples))
    try:
        round_finals: list[str] = []
        all_v: list[str] = []
        all_r: list[str] = []
        for _ in range(n):
            v1, r1 = _judge_once(
                m, task_intent, answer_a, answer_b,
                dimension=dimension, evidence_a=evidence_a, evidence_b=evidence_b,
            )
            all_v.append(v1)
            all_r.append(r1)
            if not swap_for_position_bias:
                round_finals.append(v1)
                continue
            v2_swapped, r2 = _judge_once(
                m, task_intent, answer_b, answer_a,
                dimension=dimension, evidence_a=evidence_b, evidence_b=evidence_a,
            )
            all_v.append(v2_swapped)
            all_r.append(r2)
            # Un-swap verdict 2: if judge said A under swap (= original B),
            # then the real winner is B.
            v2 = {"A": "B", "B": "A", "TIE": "TIE"}[v2_swapped]
            round_finals.append(_combine(v1, v2))

        # Majority across rounds. Ties in the vote count fall back to TIE.
        counts = {"A": 0, "B": 0, "TIE": 0}
        for f in round_finals:
            counts[f] = counts.get(f, 0) + 1
        if counts["A"] > counts["B"] and counts["A"] >= counts["TIE"]:
            final = "A"
        elif counts["B"] > counts["A"] and counts["B"] >= counts["TIE"]:
            final = "B"
        else:
            final = "TIE"
        res = _resolve(final, all_v, all_r, agent_a, agent_b, model=m)
        # Stamp the ACTUAL model that was threaded into every call_judge call,
        # not the env-driven default, so the recorded judge_model never lies.
        res["judge_model"] = m
        if dimension:
            res["dimension"] = dimension
        return res
    except Exception as e:
        return {"winner": "tie", "agent_winner": "tie", "error": f"{type(e).__name__}: {e}"}


def _resolve(
    verdict: str,
    all_v: list[str],
    all_r: list[str],
    agent_a: str,
    agent_b: str,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    if verdict == "A":
        agent_winner = agent_a
    elif verdict == "B":
        agent_winner = agent_b
    else:
        agent_winner = "tie"
    # Stamp the actual model used when provided; only fall back to the
    # env-driven default for back-compat when a caller does not pass one.
    return {
        "winner": verdict.lower() if verdict != "TIE" else "tie",
        "agent_winner": agent_winner,
        "verdicts_raw": all_v,
        "reasonings": all_r,
        "judge_model": model or _default_judge_model(),
    }
