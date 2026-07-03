"""Checklist generator: answer key -> typed, decidable unit tests
(METHODOLOGY_REDESIGN_2026-07-03.md section 4).

Replaces the hand-written template checklists (which had 6 all-"PASS" dead
files and ~11% length/count quotas that fight our own anti-verbosity finding)
with unit tests DERIVED from the DB answer key. Each item carries a type that
routes it to an axis, so the checklist IS the score, not a decorative side
list a task-blind judge never sees.

Item types (mirrors decidable_scorer axes):
  FACT          structured claim vs DB nugget      -> axis 2 (decidable)
  COVERAGE      did the report surface vital fact   -> axis 3 (decidable)
  CONTRADICTION did it find a gold contradiction    -> axis 3 (decidable/semi)
  GROUNDING     cited URL reachable + quote in page -> axis 1 (decidable)
  SPEC          output-shape requirement            -> axis 4 (decidable)
  VERDICT       report verdict vs DB-supported one  -> axis 2 (decidable)
  FACT_PROSE    prose claim vs cited page (CNV)      -> axis 2 (LLM, stage 2)

Quotas (word counts, "cite >= N URLs") are emitted ONLY as SPEC items, never
as content requirements, and never injected into the user-facing question.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class ChecklistItem:
    id: str
    type: str       # FACT | COVERAGE | CONTRADICTION | GROUNDING | SPEC | VERDICT | FACT_PROSE
    axis: int       # 1..4
    decidable: bool  # True = no LLM needed
    description: str
    params: dict = field(default_factory=dict)


AXIS_OF = {"FACT": 2, "COVERAGE": 3, "CONTRADICTION": 3, "GROUNDING": 1,
           "SPEC": 4, "VERDICT": 2, "FACT_PROSE": 2}
LLM_TYPES = {"FACT_PROSE", "CONTRADICTION"}  # CONTRADICTION semi-decidable


def generate(answer_key, max_coverage: int = 60, max_fact: int = 40) -> list:
    """Build a typed checklist from an answer key. COVERAGE/FACT items are
    capped and drawn from the highest-weight relevant vital nuggets so the
    checklist is bounded and focuses on what matters."""
    items: list[ChecklistItem] = []

    vital = [n for n in answer_key.vital_nuggets if getattr(n, "relevant", True)]
    vital.sort(key=lambda n: (n.predicate != "rating", n.subject))  # rating facts first

    # COVERAGE: report should surface these vital facts (axis 3 recall)
    for i, n in enumerate(vital[:max_coverage]):
        items.append(ChecklistItem(
            id=f"cov{i:03d}", type="COVERAGE", axis=3, decidable=True,
            description=f"Does the report convey: {n.text}",
            params={"subject": n.subject, "predicate": n.predicate, "object": n.object,
                    "source_url": n.source_url}))

    # FACT: any of these the report states must match the DB (axis 2 correctness)
    for i, n in enumerate(vital[:max_fact]):
        items.append(ChecklistItem(
            id=f"fact{i:03d}", type="FACT", axis=2, decidable=True,
            description=f"If the report states {n.subject[:50]}'s {n.predicate}, "
                        f"it must equal the DB value {n.object}",
            params={"subject": n.subject, "predicate": n.predicate, "object": n.object}))

    # CONTRADICTION: real product-vs-wiki conflicts the report should find
    for i, c in enumerate(answer_key.gold_contradictions):
        items.append(ChecklistItem(
            id=f"contra{i:03d}", type="CONTRADICTION", axis=3, decidable=False,
            description=f"Does the report surface the contradiction: {c.get('summary', '')}",
            params=c))

    # VERDICT: for debunking tasks, report verdict must match DB-supported one
    for cid, v in (answer_key.decidable_verdicts or {}).items():
        items.append(ChecklistItem(
            id=f"verdict_{cid}", type="VERDICT", axis=2, decidable=True,
            description=f"Report's verdict on claim '{cid}' should be {v} "
                        f"(or justified UNDETERMINED)",
            params={"claim_id": cid, "gold_verdict": v}))

    # GROUNDING: global grounding checks (axis 1)
    items.append(ChecklistItem(
        id="ground_reach", type="GROUNDING", axis=1, decidable=True,
        description="Cited sandbox URLs resolve in the frozen corpus (no fabrication)",
        params={"metric": "reachability"}))
    items.append(ChecklistItem(
        id="ground_quote", type="GROUNDING", axis=1, decidable=True,
        description="Quoted context appears on the cited page (proof of fetch)",
        params={"metric": "proof_of_fetch"}))

    # SPEC: the task's decidable output-shape requirements (quotas live here)
    for s in answer_key.spec_requirements:
        items.append(ChecklistItem(
            id=f"spec_{s.id}", type="SPEC", axis=4, decidable=True,
            description=s.description, params={"kind": s.kind, **(s.params or {})}))

    return items


def summary(items: list) -> dict:
    import collections
    by_type = collections.Counter(i.type for i in items)
    return {
        "n_items": len(items),
        "by_type": dict(by_type),
        "decidable": sum(1 for i in items if i.decidable),
        "llm_needed": sum(1 for i in items if not i.decidable),
    }


def save(items: list, path):
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps([asdict(i) for i in items], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    from src.eval.answer_key import migrate_db_golden
    from src.eval.relevance_gate import apply_gate
    ak = migrate_db_golden("data/golden/db/dr_cross_deep_0001.json")
    apply_gate(ak, ["headphone", "earbud", "earphone", "headset", "airpod"])
    items = generate(ak)
    print(json.dumps(summary(items), indent=2))
    for it in items[:3] + items[-3:]:
        print(f"  [{it.type:13s} axis{it.axis} {'D' if it.decidable else 'L'}] {it.description[:80]}")
