"""Extract decidable output-shape requirements (SpecRequirement) from a task's
legacy over-specified intent and its structured spec fields
(METHODOLOGY_REDESIGN_2026-07-03.md section 3b/4).

This is the deterministic half of de-specification: quotas that were baked into
the question ("cite >= 60 URLs", "final list of exactly 10", "<= 8 bullets",
"3500-8000 words", a verdict set) are lifted OUT of the prompt and turned into
axis-4 SPEC checks. The natural-language rewrite of the question itself needs a
model (stage 2); this module handles everything a parser can.

Sources, in priority order:
  1. the task json's structured fields (citation_policy, synthesis_requirements,
     markdown_spec) — already machine-readable;
  2. regex over the legacy intent text for quotas the fields missed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.eval.answer_key import SpecRequirement

VERDICT_SET_RE = re.compile(r"\{([A-Z_]{3,}(?:\s*[,/]\s*[A-Z_]{3,})+)\}")
BULLET_RE = re.compile(r"<=\s*(\d+)\s*bullet", re.I)
WORD_RANGE_RE = re.compile(r"(\d{3,5})\s*(?:-|to|and)\s*(\d{3,5})\s*words", re.I)
LIST_SIZE_RE = re.compile(r"(?:exactly|final)\s+(\d+)[- ]?(?:item|product)", re.I)


def _intent_text(task: dict) -> str:
    it = task.get("intent_v1_legacy") or task.get("intent")
    if isinstance(it, dict):
        it = it.get("prompt", "")
    return it or ""


def extract(task: dict) -> list:
    reqs: list[SpecRequirement] = []
    intent = _intent_text(task)

    # verdict schema (debunking tasks): the allowed verdict values
    m = VERDICT_SET_RE.search(intent)
    if m:
        vals = [v.strip() for v in re.split(r"[,/]", m.group(1))]
        reqs.append(SpecRequirement(
            id="verdict_table", kind="table_present",
            description="A verdict table is present",
            params={"min_pipes": 6}))
        reqs.append(SpecRequirement(
            id="verdict_values", kind="verdict_values",
            description=f"Verdicts use the allowed set {vals}",
            params={"allowed": vals, "min_distinct": 1}))

    # word range -> min_words only (we do NOT enforce an upper bound: penalizing
    # brevity is the answer key's job via coverage, not a quota)
    m = WORD_RANGE_RE.search(intent)
    if m:
        reqs.append(SpecRequirement(
            id="min_words", kind="min_words",
            description=f"Report is at least {m.group(1)} words",
            params={"min": int(m.group(1))}))

    # bounded cheat-sheet / bullet cap
    m = BULLET_RE.search(intent)
    if m:
        reqs.append(SpecRequirement(
            id="bullet_cap", kind="max_bullets",
            description=f"Any capped list stays within {m.group(1)} bullets",
            params={"max": int(m.group(1)), "global": False}))

    # synthesis sections named in the structured spec
    syn = task.get("synthesis_requirements") or {}
    if syn.get("contradiction_findings_min") and not syn.get(
            "contradiction_findings_min_deprecated"):
        reqs.append(SpecRequirement(
            id="sec_contradictions", kind="section_present",
            description="A contradictions / claim-vs-reality section is present",
            params={"keywords": ["contradict", "mismatch", "vs reality", "debunk"]}))
    if syn.get("final_buy_list_size") or LIST_SIZE_RE.search(intent):
        reqs.append(SpecRequirement(
            id="sec_shortlist", kind="section_present",
            description="An actionable shortlist / buy list is present",
            params={"keywords": ["shortlist", "buy list", "top ", "recommend", "pick"]}))

    return reqs


def natural_output_contract(task: dict) -> str:
    """A short, human output contract to show the agent (§5a) derived from the
    spec — the soft form a real user would state, not a quota list."""
    parts = []
    intent = _intent_text(task)
    if VERDICT_SET_RE.search(intent):
        parts.append("Start with a verdict table, one row per claim, each with a "
                     "clear verdict.")
    syn = task.get("synthesis_requirements") or {}
    if syn.get("final_buy_list_size") or LIST_SIZE_RE.search(intent):
        parts.append("End with a shortlist you would actually act on.")
    if BULLET_RE.search(intent):
        parts.append("Keep any summary checklist short.")
    return " ".join(parts) or "Answer in whatever form best serves the request."


if __name__ == "__main__":
    import sys
    tid = sys.argv[1] if len(sys.argv) > 1 else "dr_cross_deep_0001"
    p = Path("data/tasks/deep_research/cross_site_deep") / f"{tid}.json"
    task = json.loads(p.read_text())
    reqs = extract(task)
    print(f"{tid}: {len(reqs)} spec requirements")
    for r in reqs:
        print(f"  [{r.kind:16s}] {r.description}")
    print("contract:", natural_output_contract(task))
