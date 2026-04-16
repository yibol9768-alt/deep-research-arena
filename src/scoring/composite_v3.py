"""Composite scorer v3 — aligned with the markdown-long-form + KG-golden design.

v3 pillars (replaces the 6 pillars of v2):

  0.10  markdown_structure   MarkdownReportVerifier (words / paras / cites / pages)
  0.15  citation             CitationVerifier (ALCE F1, prose mode)
  0.30  fact_kg              FactKGVerifier   (** NEW primary signal **)
  0.20  llm_judge            LLMJudgeVerifier (RACE 4-dim)
  0.20  checklist            ChecklistVerifier (DRACO 15-item binary rubric)
  0.05  efficiency           EfficiencyMetrics (tokens / time / cost)

Design rationale (cf. DRACO 2026, LiveResearchBench 2025, ResearchRubrics 2025):

  - fact_kg carries the most weight (0.30) — our unique advantage vs open-web
    benchmarks is the sandbox ground truth. Deterministic, zero-variance recall.
  - checklist weight raised from 0.10 → 0.20 — DRACO shows 40-item rubrics
    outperform single-point scores; our 15 items are a calibrated middle path.
  - llm_judge kept but capped at 0.20 — judge length-bias (MEGA finding #3)
    means we cannot trust it standalone.
  - deterministic pillar retired — v3 answers are markdown, not JSON. Its
    role is split into `markdown_structure` (contract adherence) and
    `fact_kg` (content correctness).

v2 scorer remains at src/scoring/composite_v2.py for historical comparison.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.verifiers import (
    CitationVerifier,
    LLMJudgeVerifier,
    ChecklistVerifier,
    FactKGVerifier,
    MarkdownReportVerifier,
    VerifierResult,
)
from src.metrics import EfficiencyMetrics


DEFAULT_WEIGHTS: dict[str, float] = {
    "markdown_structure": 0.10,
    "citation":           0.15,
    "fact_kg":            0.30,
    "llm_judge":          0.20,
    "checklist":          0.20,
    "efficiency":         0.05,
}


@dataclass
class PillarScore:
    score: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompositeResultV3:
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
            f"{p['markdown_structure'].score:.2f} | "
            f"{p['citation'].score:.2f} | "
            f"{p['fact_kg'].score:.2f} | "
            f"{p['llm_judge'].score:.2f} | "
            f"{p['checklist'].score:.2f} | "
            f"{p['efficiency'].score:.2f} |"
        )

    @staticmethod
    def markdown_header() -> str:
        return (
            "| Agent | Task | Composite | Md | Cite | Fact-KG | Judge | Chk | Eff |\n"
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
) -> CompositeResultV3:
    """Run the v3 pillars and aggregate.

    `run_judge=False` skips llm_judge + checklist (they hit the LLM) and
    returns 0 for those pillars — useful for offline dry-runs.
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    pillars: dict[str, PillarScore] = {}

    # 1. markdown structure
    md = MarkdownReportVerifier().verify(task_config=task_config, answer=answer, page=page)
    pillars["markdown_structure"] = _vr_to_pillar(md)

    # 2. citation (ALCE F1, prose mode)
    cit = CitationVerifier().verify(task_config=task_config, answer=answer, page=page)
    pillars["citation"] = _vr_to_pillar(cit)

    # 3. fact_kg — primary v3 signal
    fk = FactKGVerifier(do_precision=run_judge).verify(task_config=task_config, answer=answer, page=page)
    pillars["fact_kg"] = _vr_to_pillar(fk)

    # 4. LLM judge
    if run_judge:
        jv = LLMJudgeVerifier().verify(task_config=task_config, answer=answer, page=page)
        pillars["llm_judge"] = _vr_to_pillar(jv)
    else:
        pillars["llm_judge"] = PillarScore(score=0.0, passed=False, details={"skipped": True})

    # 5. DRACO-style checklist
    if run_judge:
        chk = ChecklistVerifier().verify(task_config=task_config, answer=answer, page=page)
        pillars["checklist"] = _vr_to_pillar(chk)
    else:
        pillars["checklist"] = PillarScore(score=0.0, passed=False, details={"skipped": True})

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

    return CompositeResultV3(
        task_id=task_id,
        agent=agent,
        answer=answer,
        pillars=pillars,
        weights=w,
        composite=round(composite, 3),
    )
