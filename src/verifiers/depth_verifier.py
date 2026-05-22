"""DepthVerifier -- LLM-judge 5-point analytical depth rubric for v3 scoring.

Part of the Workstream A v3 composite. Where the existing
`analysis_depth_verifier` mixes Tier A (deterministic) with Tier B (judge)
and produces a binary-rubric score, this verifier asks the judge for a
single 1-5 integer using anchored language. Self-consistency: three
calls at temperature 0.3, median of the integer levels.

Rubric anchors (deliberately concrete so judges land on the same level):

  1 = pure enumeration. The report lists facts/items from sources with no
      synthesis. Equivalent to a bulleted dump.
  2 = enumeration with surface grouping. Items are bucketed (e.g. by
      category or brand) but no analytical claim is made about the buckets.
  3 = claims with single-evidence links. The report makes assertions and
      points to one source per assertion, but does not reconcile multiple
      sources on the same claim.
  4 = multi-evidence claims. Several claims are backed by two or more
      sources, and the report compares them, but contradictions between
      sources are not explicitly addressed.
  5 = multi-step synthesis. The report identifies contradictions between
      sources, reconciles them (or declares them irreducible), and uses
      that reconciliation to drive at least one downstream claim.

The verifier returns:
  - score:  rescaled to [0, 1] via (level - 1) / 4
  - level:  integer 1..5 (median of self-consistency samples)
  - evidence: one-sentence judge quotation justifying the level
  - raw_judge_output: concatenated outputs from the three samples

Chain-of-thought is EXPLICITLY DISABLED in the prompt. We do not want the
judge to think aloud (the score we want is the level integer, not the
narrative). For DeepSeek-V4 the underlying call_judge helper already
emits `thinking: disabled`.

Cross-family routing follows `checklist_verifier` -- everything goes
through `judge_client.call_judge`, which is configured via env vars by
the run harness. There is no per-agent override in this verifier; the
caller is expected to set JUDGE_PROVIDER / JUDGE_MODEL such that the
judge is different-family from the agent under test. If no clear pattern
exists (e.g. the run harness has not been updated for GLM-agent runs),
the default DeepSeek path is used.

TODO(workstream-A-followup): when the AgentRL runner gains explicit
"agent_family" metadata in task_config, switch the judge identity here
based on that field (DeepSeek when agent is GLM, GLM when agent is
DeepSeek) instead of relying on global env vars.
"""

from __future__ import annotations

import os
import re
import statistics
from typing import Any

from .base import VerifierResult
from .judge_client import call_judge, judge_identity


# Number of self-consistency samples (median of integer levels).
_N_SAMPLES = int(os.environ.get("V3_JUDGE_N_SAMPLES", "3"))
_TEMP = float(os.environ.get("V3_JUDGE_TEMP", "0.3"))


_SYSTEM = (
    "You are a strict analytical-depth judge for deep-research reports.\n\n"
    "Score the report on a 1-5 integer scale using these anchors:\n"
    "  1 = enumeration only (lists facts, no synthesis).\n"
    "  2 = enumeration with surface grouping (buckets, no claims about buckets).\n"
    "  3 = claims with single-evidence links (one source per claim).\n"
    "  4 = multi-evidence claims (>=2 sources per claim, comparisons made,\n"
    "      contradictions not explicitly addressed).\n"
    "  5 = multi-step synthesis (contradictions surfaced and reconciled, and\n"
    "      that reconciliation drives at least one downstream claim).\n\n"
    "Do NOT write any reasoning, chain-of-thought, or explanation outside\n"
    "the required output format. Output exactly two lines:\n"
    "  LEVEL: <integer 1-5>\n"
    "  EVIDENCE: <one short sentence quoting or paraphrasing report text\n"
    "            that justifies the level, <= 30 words>\n"
    "Any prose beyond those two lines will be discarded."
)


def _build_user_prompt(intent: str, answer: str) -> str:
    truncated = (answer or "")[:6000]
    return (
        f"Research task:\n{intent}\n\n"
        f"Agent report (truncated to 6000 chars):\n---\n{truncated}\n---\n\n"
        "Score and output exactly:\n"
        "LEVEL: <1|2|3|4|5>\n"
        "EVIDENCE: <one short sentence>"
    )


_LEVEL_RE = re.compile(r"^\s*LEVEL\s*[:\-]\s*([1-5])\b", re.IGNORECASE | re.MULTILINE)
_EVIDENCE_RE = re.compile(r"^\s*EVIDENCE\s*[:\-]\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
# Fallback: a lone integer 1-5 anywhere in the first 200 chars.
_LONE_INT_RE = re.compile(r"\b([1-5])\b")


def _parse_one(text: str) -> tuple[int | None, str]:
    """Extract (level, evidence) from a single judge output. Returns
    (None, "") if no level could be parsed."""
    if not text:
        return None, ""
    m = _LEVEL_RE.search(text)
    level: int | None = int(m.group(1)) if m else None
    if level is None:
        # Some judges drop the "LEVEL:" preamble despite instructions.
        m2 = _LONE_INT_RE.search(text[:200])
        if m2:
            level = int(m2.group(1))
    em = _EVIDENCE_RE.search(text)
    evidence = (em.group(1).strip() if em else "")[:240]
    return level, evidence


def _level_to_score(level: int) -> float:
    """Map a 1-5 integer level into [0, 1]. Level 1 -> 0.0, level 5 -> 1.0."""
    level = max(1, min(5, int(level)))
    return (level - 1) / 4.0


class DepthVerifier:
    """5-point LLM-judge rubric for analytical depth, with self-consistency."""

    kind = "depth"

    def __init__(self, n_samples: int | None = None, temperature: float | None = None) -> None:
        self.n_samples = int(n_samples if n_samples is not None else _N_SAMPLES)
        self.temperature = float(temperature if temperature is not None else _TEMP)

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any = None) -> VerifierResult:
        from .base import is_degenerate_answer
        degen, why = is_degenerate_answer(answer, min_words=50, require_citations=False)
        if degen:
            return VerifierResult(
                score=0.0,
                passed=False,
                details={
                    "level": 1,
                    "evidence": f"degenerate_answer:{why}",
                    "raw_judge_output": "",
                    "n_samples": 0,
                    "judge_model": judge_identity()["model"],
                    "judge_provider": judge_identity()["provider"],
                },
            )

        intent = task_config.get("intent", "")
        user_prompt = _build_user_prompt(intent, answer)

        levels: list[int] = []
        evidences: list[str] = []
        raw_chunks: list[str] = []
        judge_errors: list[str] = []

        for i in range(self.n_samples):
            try:
                text, err = call_judge(
                    _SYSTEM,
                    user_prompt,
                    max_tokens=200,
                    temperature=self.temperature,
                )
            except Exception as e:
                # Defensive: if the judge backend itself raises (e.g. the DS
                # proxy is unreachable, the SDK is missing), do not crash the
                # whole eval pipeline. Mark this sample as unavailable and
                # continue; if every sample fails we fall back to neutral 0.5.
                text, err = None, f"{type(e).__name__}: {e}"
            if text is None:
                judge_errors.append(err or "unknown")
                continue
            raw_chunks.append(text)
            level, evidence = _parse_one(text)
            if level is not None:
                levels.append(level)
                if evidence:
                    evidences.append(evidence)

        if not levels:
            # All judge calls failed or returned unparseable output. Per the
            # spec: code defensively and return a neutral score with a
            # judge_unavailable marker rather than crashing the eval.
            return VerifierResult(
                score=0.5,
                passed=False,
                details={
                    "level": 3,
                    "evidence": "judge_unavailable",
                    "raw_judge_output": " ||| ".join(raw_chunks)[:1000],
                    "n_samples": 0,
                    "judge_errors": judge_errors[:3],
                    "judge_model": judge_identity()["model"],
                    "judge_provider": judge_identity()["provider"],
                },
            )

        # Median is the robust aggregate for an odd-count integer sample.
        # For even-count samples median can return a half-integer; round
        # down (toward stricter) to keep the level an integer.
        med = statistics.median(levels)
        level_final = int(med) if float(med).is_integer() else int(med)
        score = _level_to_score(level_final)

        return VerifierResult(
            score=round(score, 3),
            passed=score >= 0.5,
            details={
                "level": level_final,
                "evidence": evidences[0] if evidences else "",
                "samples": levels,
                "raw_judge_output": " ||| ".join(raw_chunks)[:1500],
                "n_samples": len(levels),
                "judge_errors": judge_errors[:3] if judge_errors else [],
                "judge_model": judge_identity()["model"],
                "judge_provider": judge_identity()["provider"],
                "temperature": self.temperature,
                "cot_disabled": True,
            },
        )
