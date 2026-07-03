"""Closed-world answer key: the DB-computed ground truth a report is scored
against (METHODOLOGY_REDESIGN_2026-07-03.md section 3b).

The answer key is the hidden layer of a task. The user-facing question stays
natural and quota-free; every "must cover N things" requirement lives here,
computed from the database rather than written into the prompt. Because the
sandbox is a frozen, queryable world, each field below is a decidable fact,
not an estimate:

  relevant_set      the on-topic entities (products / threads / articles) with
                    their DB-true facts. The completeness denominator (axis 3).
  vital_nuggets     the atomic facts a good report SHOULD convey, marked vital.
  useful_nuggets    secondary facts (softer coverage credit).
  gold_contradictions   real product-claim vs encyclopedia conflicts, precomputed.
  decidable_verdicts    for debunking tasks, the verdict the DB/wiki supports;
                        UNDETERMINED where the closed world cannot decide.
  spec_requirements     decidable output-shape checks (verdict table present,
                        verdict values in range, section present, <=N bullets).
                        This is where format quotas go, kept OUT of quality.

This module defines the schema and migrates the existing keyword-enumerated
db golden (data/golden/db/*.json) into it. The relevance gate that trims the
over-inclusive keyword net is applied separately (relevance_gate.py); the raw
migration preserves everything and records provenance so the trim is auditable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Entity:
    """One on-topic sandbox entity with its DB-true facts."""
    url: str
    name: str
    category: str  # shopping_product | reddit_thread | wiki_article
    facts: dict = field(default_factory=dict)  # predicate -> value (DB truth)
    weight: float = 0.5  # importance, not relevance
    relevant: bool = True  # set False by the relevance gate, never dropped
    relevance_reason: str = ""


@dataclass
class Nugget:
    """An atomic, self-contained fact the report should convey."""
    text: str
    subject: str
    predicate: str
    object: str
    source_url: str
    importance: str = "useful"  # vital | useful
    relevant: bool = True


@dataclass
class SpecRequirement:
    """A decidable output-shape check (axis 4). Quotas live here, not in the
    question. `kind` selects the parser; `params` carries its arguments."""
    id: str
    kind: str  # table_present | verdict_values | section_present | max_bullets | min_sections
    description: str
    params: dict = field(default_factory=dict)


@dataclass
class AnswerKey:
    task_id: str
    relevant_set: list = field(default_factory=list)      # list[Entity]
    vital_nuggets: list = field(default_factory=list)      # list[Nugget]
    useful_nuggets: list = field(default_factory=list)     # list[Nugget]
    gold_contradictions: list = field(default_factory=list)
    decidable_verdicts: dict = field(default_factory=dict)  # claim_id -> verdict
    spec_requirements: list = field(default_factory=list)  # list[SpecRequirement]
    metadata: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "task_id": self.task_id,
            "relevant_set": [asdict(e) for e in self.relevant_set],
            "vital_nuggets": [asdict(n) for n in self.vital_nuggets],
            "useful_nuggets": [asdict(n) for n in self.useful_nuggets],
            "gold_contradictions": self.gold_contradictions,
            "decidable_verdicts": self.decidable_verdicts,
            "spec_requirements": [asdict(s) for s in self.spec_requirements],
            "metadata": self.metadata,
        }

    @classmethod
    def load(cls, path) -> "AnswerKey":
        d = json.loads(Path(path).read_text())
        return cls(
            task_id=d["task_id"],
            relevant_set=[Entity(**e) for e in d.get("relevant_set", [])],
            vital_nuggets=[Nugget(**n) for n in d.get("vital_nuggets", [])],
            useful_nuggets=[Nugget(**n) for n in d.get("useful_nuggets", [])],
            gold_contradictions=d.get("gold_contradictions", []),
            decidable_verdicts=d.get("decidable_verdicts", {}),
            spec_requirements=[SpecRequirement(**s) for s in d.get("spec_requirements", [])],
            metadata=d.get("metadata", {}),
        )

    def save(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_json(), indent=2, ensure_ascii=False))


def migrate_db_golden(db_golden_path, task_id: str | None = None) -> AnswerKey:
    """Lift an existing keyword-enumerated db golden into the answer-key schema.

    Preserves every entity and nugget verbatim (the relevance gate trims later,
    non-destructively). vital/useful split follows the golden's `importance`.
    """
    d = json.loads(Path(db_golden_path).read_text())
    tid = task_id or d.get("task_id", "unknown")

    ents = []
    for e in d.get("relevant_set", []):
        ents.append(Entity(
            url=e["url"], name=e.get("name", ""),
            category=e.get("category", "unknown"),
            facts=e.get("facts", {}), weight=float(e.get("weight", 0.5)),
        ))

    vital, useful = [], []
    for n in d.get("fact_nuggets", []):
        nug = Nugget(
            text=n.get("text", ""), subject=n.get("subject", ""),
            predicate=n.get("predicate", ""), object=str(n.get("object", "")),
            source_url=n.get("source_url", ""),
            importance=n.get("importance", "useful"),
        )
        (vital if nug.importance == "vital" else useful).append(nug)

    return AnswerKey(
        task_id=tid, relevant_set=ents,
        vital_nuggets=vital, useful_nuggets=useful,
        metadata={
            "source": "migrated_from_db_golden",
            "n_relevant_raw": len(ents),
            "n_vital_raw": len(vital),
            "n_useful_raw": len(useful),
            "relevance_gate_applied": False,
        },
    )


if __name__ == "__main__":  # smoke: migrate task 0001 and print stats
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "data/golden/db/dr_cross_deep_0001.json"
    ak = migrate_db_golden(src)
    print(f"{ak.task_id}: {len(ak.relevant_set)} entities, "
          f"{len(ak.vital_nuggets)} vital + {len(ak.useful_nuggets)} useful nuggets")
