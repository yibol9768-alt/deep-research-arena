"""DRACO-style coverage checklist verifier.

Loads a per-task list of binary coverage criteria from
`data/tasks/deep_research/<site>/checklists.json` and asks an LLM judge
to mark each as pass / fail against the agent's report. The score is
the fraction of items passed.

Why this beats a single LLM score:
  - DRACO showed that binary rubric judgments have lower variance than
    Likert scales (per their 2026 paper)
  - Each item is independently evaluable → easier to argue / debug
  - Specific items can be added per task without retraining the judge

Usage:
    v = ChecklistVerifier(checklist_path=...)  # path is auto-resolved if omitted
    r = v.verify(task_config=cfg, answer=ans)
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .base import VerifierResult
from .judge_client import call_judge, judge_identity


JUDGE_MODEL = os.environ.get("CHECKLIST_JUDGE_MODEL", "glm-5.1")
_CHECKLIST_ROOT = Path(__file__).resolve().parents[2] / "data" / "tasks" / "deep_research"
# v3 (new) checklists are loaded FIRST so they win on duplicate task_id keys.
# v2 files stay so old tasks continue to score (until Phase 6 cleanup).
_CHECKLIST_PATHS = [
    _CHECKLIST_ROOT / "shopping"   / "checklists_v3.json",
    _CHECKLIST_ROOT / "reddit"     / "checklists_v3.json",
    _CHECKLIST_ROOT / "cross_site" / "checklists_v3.json",
    _CHECKLIST_ROOT / "shopping"   / "checklists.json",
    _CHECKLIST_ROOT / "reddit"     / "checklists.json",
]
DEFAULT_CHECKLIST_PATH = _CHECKLIST_PATHS[0]  # legacy — aggregated loader below


_SYSTEM = (
    "You evaluate whether a deep-research agent's report satisfies "
    "specific binary coverage criteria.\n\n"
    "For each criterion you will output PASS or FAIL on a single line, "
    "with no other text on that line. Be strict: if the report does "
    "not clearly demonstrate the criterion, mark FAIL. Do not give the "
    "benefit of the doubt — DRACO-style rubrics require explicit evidence.\n\n"
    "After the per-criterion lines, you may add ONE final line starting "
    "with 'NOTES:' if you want to flag anything ambiguous. No other prose."
)


def _build_user_prompt(intent: str, items: list[str], answer: str) -> str:
    numbered = "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))
    return (
        f"Research task:\n{intent}\n\n"
        f"Coverage criteria (judge each independently):\n{numbered}\n\n"
        f"Agent report (truncated to 6000 chars):\n---\n{(answer or '')[:6000]}\n---\n\n"
        f"For each numbered criterion, emit one line:\n"
        f"  1. PASS|FAIL  (reason ≤ 12 words)\n"
        f"  2. PASS|FAIL  (reason ≤ 12 words)\n"
        f"  ...\n"
        "Then optional NOTES line."
    )


def _parse(text: str, n_items: int) -> list[dict[str, Any]]:
    """Extract per-item PASS/FAIL verdicts.

    Supports several formats judges emit in practice:
      - ``1. PASS - reason``  (numbered, with reason)  ← strictest
      - ``1) PASS``           (numbered, no reason)
      - ``PASS`` per line     (unnumbered, one verdict per line)  ← DeepSeek default
      - mixed lines
    """
    text = text or ""
    out: list[dict[str, Any]] = []

    # Pass 1: strict numbered parse
    for i in range(n_items):
        pat = rf"(?:^|\n)\s*{i+1}[\.\)]\s*(PASS|FAIL)\b\s*[:.\-—)]?\s*(.*?)(?=\n\s*\d+[\.\)]|\nNOTES:|\Z)"
        m = re.search(pat, text, re.S | re.I)
        if m:
            out.append({
                "index": i + 1,
                "passed": m.group(1).upper() == "PASS",
                "reason": m.group(2).strip().split("\n")[0][:120],
            })
        else:
            out.append(None)  # placeholder, filled below

    # Pass 2: unnumbered one-verdict-per-line fallback. Triggers on ANY
    # missing slot — old `> n_items // 2` threshold meant a mixed-format
    # output (some numbered, some not) left the unnumbered half FAILing.
    missing_idx = [i for i, v in enumerate(out) if v is None]
    if missing_idx:
        # Strip NOTES tail
        body = re.split(r"\n\s*NOTES:", text, maxsplit=1, flags=re.I)[0]
        # Collect all standalone PASS/FAIL tokens in order
        tokens = re.findall(r"(?:^|\n)\s*(PASS|FAIL)\b", body, re.I)
        if len(tokens) >= n_items:
            for i in range(n_items):
                out[i] = {
                    "index": i + 1,
                    "passed": tokens[i].upper() == "PASS",
                    "reason": "",
                }

    # Fill any still-missing slots with "judge did not emit" fail
    for i, v in enumerate(out):
        if v is None:
            out[i] = {"index": i + 1, "passed": False, "reason": "judge did not emit a verdict"}
    return out


def _client():
    try:
        import anthropic  # type: ignore
    except Exception:
        return None
    os.environ.setdefault("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
    if not (os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")):
        return None
    return anthropic.Anthropic()


class ChecklistVerifier:
    """Per-task DRACO-style binary rubric judge."""

    kind = "coverage_checklist"

    def __init__(self, checklist_path: Path | str | None = None, model: str | None = None) -> None:
        self.checklist_path = Path(checklist_path) if checklist_path else DEFAULT_CHECKLIST_PATH
        self.model = model or JUDGE_MODEL
        self._cache: dict | None = None

    def _load(self) -> dict:
        if self._cache is None:
            merged: dict = {}
            # Merge all known checklist files so tasks across sandboxes
            # can live in one verifier.
            for p in _CHECKLIST_PATHS:
                try:
                    merged.update(json.loads(p.read_text()))
                except Exception:
                    continue
            # Also allow an explicit override via __init__(checklist_path=...)
            if self.checklist_path and self.checklist_path != DEFAULT_CHECKLIST_PATH:
                try:
                    merged.update(json.loads(self.checklist_path.read_text()))
                except Exception:
                    pass
            self._cache = merged
        return self._cache

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any = None) -> VerifierResult:
        all_lists = self._load()
        task_id = task_config.get("task_id", "")
        items = all_lists.get(task_id) or []
        if not items:
            return VerifierResult(
                score=0.0, passed=False,
                details={"reason": f"no checklist for {task_id}", "checklist_path": str(self.checklist_path)},
            )

        # Route through the pluggable judge backend (DeepSeek / Claude / etc.)
        # — different family from the agent LLM removes the self-preference
        # confound flagged by the methodology audit.
        text, err = call_judge(
            _SYSTEM,
            _build_user_prompt(task_config.get("intent", ""), items, answer),
            max_tokens=1500,
        )
        if text is None:
            return VerifierResult.fail(f"judge call failed: {err}")

        per_item = _parse(text, len(items))
        passed_count = sum(1 for x in per_item if x["passed"])
        score = passed_count / len(items)

        # Attach the original criterion text alongside the verdict
        for i, x in enumerate(per_item):
            if i < len(items):
                x["criterion"] = items[i]

        return VerifierResult(
            score=round(score, 3),
            passed=score >= 0.7,  # 70% bar — DRACO uses similar thresholds
            details={
                "passed_count": passed_count,
                "total": len(items),
                "per_item": per_item,
                "judge_model": judge_identity()["model"],
                "judge_provider": judge_identity()["provider"],
                "raw_judge_output": text[:800],
            },
        )
