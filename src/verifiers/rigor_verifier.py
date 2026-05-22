"""RigorVerifier -- LLM-judge 5-point logical-coherence rubric for v3 scoring.

Part of the Workstream A v3 composite. Targets a different failure mode
than `depth_verifier`: where depth measures *how much* synthesis happens,
rigor measures whether what is written is *internally consistent and
appropriately hedged*. A report can be deep but rigorously wrong (e.g.
multi-step synthesis with internal contradictions) or shallow but
rigorous (a tight enumeration that does not over-claim).

Rubric anchors (1-5 integer scale):

  1 = multiple internal contradictions. The report contains claims that
      directly conflict with each other within the body.
  2 = visible over-claiming or partial contradiction. At least one claim
      is stated more strongly than the evidence supports, OR there is a
      minor contradiction between two sections.
  3 = mostly consistent. No internal contradictions, but the report
      treats uncertain claims as certain (no hedging where evidence is
      thin or sources disagree).
  4 = consistent with some hedging. The report acknowledges uncertainty
      in at least one place where it is warranted; no contradictions.
  5 = consistent with hedged uncertainty. The report flags where evidence
      is weak, where sources disagree, and where claims are speculative,
      throughout. No internal contradictions or unsupported over-claims.

Same shape as `DepthVerifier`: self-consistency (median of 3 samples at
temperature 0.3), chain-of-thought disabled, judge stamped via
`judge_identity()`.
"""

from __future__ import annotations

import os
import re
import statistics
from typing import Any

from .base import VerifierResult
from .judge_client import call_judge, judge_identity


_N_SAMPLES = int(os.environ.get("V3_JUDGE_N_SAMPLES", "3"))
_TEMP = float(os.environ.get("V3_JUDGE_TEMP", "0.3"))


_SYSTEM = (
    "You are a strict logical-rigor judge for deep-research reports.\n\n"
    "Score the report on a 1-5 integer scale using these anchors:\n"
    "  1 = multiple internal contradictions (claims conflict within the report).\n"
    "  2 = visible over-claiming or partial contradiction (one over-strong\n"
    "      claim OR one minor contradiction).\n"
    "  3 = mostly consistent but no hedging where uncertainty is warranted.\n"
    "  4 = consistent with some hedging on weak or disputed evidence.\n"
    "  5 = consistent with appropriate hedging throughout (flags weak\n"
    "      evidence, disagreeing sources, and speculative claims).\n\n"
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
_LONE_INT_RE = re.compile(r"\b([1-5])\b")


def _parse_one(text: str) -> tuple[int | None, str]:
    if not text:
        return None, ""
    m = _LEVEL_RE.search(text)
    level: int | None = int(m.group(1)) if m else None
    if level is None:
        m2 = _LONE_INT_RE.search(text[:200])
        if m2:
            level = int(m2.group(1))
    em = _EVIDENCE_RE.search(text)
    evidence = (em.group(1).strip() if em else "")[:240]
    return level, evidence


def _level_to_score(level: int) -> float:
    level = max(1, min(5, int(level)))
    return (level - 1) / 4.0


class RigorVerifier:
    """5-point LLM-judge rubric for logical rigor, with self-consistency."""

    kind = "rigor"

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

        for _ in range(self.n_samples):
            try:
                text, err = call_judge(
                    _SYSTEM,
                    user_prompt,
                    max_tokens=200,
                    temperature=self.temperature,
                )
            except Exception as e:
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
