"""Composite scorer (v2) that aggregates the six pillars from
SCORING_FRAMEWORK.md:

  0.30  Deterministic        (ReportVerifier — schema + field constraints)
  0.15  CitationQuality      (CitationVerifier — F1 of recall/precision)
  0.25  Factuality           (stub — reuses CitationVerifier precision for now)
  0.15  LLMJudge             (LLMJudgeVerifier — 4 dim weighted 1-5)
  0.10  Comprehensiveness    (stub — reuses LLM-judge 'comprehensiveness' dim)
  0.05  Efficiency           (EfficiencyMetrics.score01)

Returns:
    CompositeResult with per-pillar scores + a single composite in [0,1]
    plus a markdown-rendering helper for leaderboard rows.

Design notes
------------
* Pillars that do not yet have a dedicated verifier are wired to the
  closest proxy, with the intent to replace them later (see TODO tags).
  This keeps the pipeline end-to-end today while leaving clean extension
  points.
* All six sub-scores are saved raw; composite is derived on demand so we
  can reweight without re-running the judges.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from src.verifiers import (
    ReportVerifier,
    CitationVerifier,
    LLMJudgeVerifier,
    ChecklistVerifier,
    VerifierResult,
)
from src.metrics import EfficiencyMetrics


DEFAULT_WEIGHTS: dict[str, float] = {
    "deterministic": 0.30,
    "citation":      0.15,
    "factuality":    0.25,
    "llm_judge":     0.15,
    "comprehensiveness": 0.10,
    "efficiency":    0.05,
}


@dataclass
class PillarScore:
    score: float            # 0..1
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompositeResult:
    task_id: str
    agent: str
    answer: str
    pillars: dict[str, PillarScore]
    weights: dict[str, float]
    composite: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent": self.agent,
            "composite": round(self.composite, 3),
            "pillars": {k: asdict(v) for k, v in self.pillars.items()},
            "weights": self.weights,
            "answer_preview": (self.answer or "")[:400],
        }

    def to_markdown_row(self) -> str:
        p = self.pillars
        return (
            f"| {self.agent} | {self.task_id} | **{self.composite:.2f}** | "
            f"{p['deterministic'].score:.2f} | "
            f"{p['citation'].score:.2f} | "
            f"{p['factuality'].score:.2f} | "
            f"{p['llm_judge'].score:.2f} | "
            f"{p['comprehensiveness'].score:.2f} | "
            f"{p['efficiency'].score:.2f} |"
        )

    @staticmethod
    def markdown_header() -> str:
        return (
            "| Agent | Task | Composite | Det. | Cite | Fact | Judge | Comp | Eff |\n"
            "|---|---|---:|---:|---:|---:|---:|---:|---:|"
        )


def _vr_to_pillar(vr: VerifierResult) -> PillarScore:
    return PillarScore(
        score=float(vr.score),
        passed=bool(vr.passed),
        details=dict(vr.details),
    )


def score(
    *,
    task_id: str,
    agent: str,
    task_config: dict,
    answer: str,
    page: Any = None,
    efficiency: EfficiencyMetrics | None = None,
    run_judge: bool = True,
    weights: dict[str, float] | None = None,
    budget_cost_usd: float = 0.10,
    budget_time_s: float = 300.0,
) -> CompositeResult:
    """Run all pillars and aggregate."""
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    pillars: dict[str, PillarScore] = {}

    # 1. Deterministic
    det = ReportVerifier().verify(task_config=task_config, answer=answer, page=page)
    pillars["deterministic"] = _vr_to_pillar(det)

    # 2. Citation (ALCE F1)
    cit = CitationVerifier().verify(task_config=task_config, answer=answer, page=page)
    pillars["citation"] = _vr_to_pillar(cit)

    # 3. Factuality — TODO: dedicated atomic-fact verifier. For now use
    # CitationVerifier's precision (supported citations / total) as a
    # conservative proxy: a fully-supported citation implies the claimed
    # value was found on the cited page.
    fact_score = float(cit.details.get("citation_precision", 0.0))
    pillars["factuality"] = PillarScore(
        score=fact_score,
        passed=fact_score >= 0.8,
        details={
            "proxy": "citation_precision",
            "verified": cit.details.get("supported_citations", 0),
            "total": cit.details.get("total_citations", 0),
            "TODO": "replace with atomic-fact extractor (FActScore-style)",
        },
    )

    # 4. LLM judge
    if run_judge:
        jv = LLMJudgeVerifier().verify(task_config=task_config, answer=answer, page=page)
        pillars["llm_judge"] = _vr_to_pillar(jv)
        comp_dim = int(jv.details.get("comprehensiveness") or 0)
    else:
        pillars["llm_judge"] = PillarScore(score=0.0, passed=False, details={"skipped": True})
        comp_dim = 0

    # 5. Comprehensiveness — DRACO-style coverage checklist
    if run_judge:
        chk = ChecklistVerifier().verify(task_config=task_config, answer=answer, page=page)
        if chk.score == 0.0 and "no checklist" in str(chk.details.get("reason", "")):
            # Fall back to LLM-judge comprehensiveness dim if no checklist defined
            fallback = max(0.0, (comp_dim - 0) / 5.0) if comp_dim else 0.0
            pillars["comprehensiveness"] = PillarScore(
                score=fallback,
                passed=fallback >= 0.7,
                details={"fallback": "llm_judge.comprehensiveness", "dim_1_5": comp_dim, **chk.details},
            )
        else:
            pillars["comprehensiveness"] = _vr_to_pillar(chk)
    else:
        pillars["comprehensiveness"] = PillarScore(score=0.0, passed=False, details={"skipped": True})

    # 6. Efficiency
    if efficiency is not None:
        eff_score = efficiency.score01(budget_cost_usd=budget_cost_usd, budget_time_s=budget_time_s)
        pillars["efficiency"] = PillarScore(
            score=eff_score,
            passed=eff_score >= 0.5,
            details=efficiency.to_dict(),
        )
    else:
        pillars["efficiency"] = PillarScore(score=0.0, passed=False, details={"reason": "metrics unavailable"})

    composite = sum(w[name] * pillars[name].score for name in w)

    return CompositeResult(
        task_id=task_id,
        agent=agent,
        answer=answer,
        pillars=pillars,
        weights=w,
        composite=round(composite, 3),
    )
