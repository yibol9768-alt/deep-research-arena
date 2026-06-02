"""DRACO-style coverage checklist verifier.

Loads a per-task list of binary coverage criteria from
`data/tasks/deep_research/<site>/checklists.json` and asks an LLM judge
to mark each as pass / fail against the agent's report. The score is
the fraction of items passed.

Why this beats a single LLM score:
  - DRACO showed that binary rubric judgments have lower variance than
    Likert scales (per their 2026 paper)
  - Each item is independently evaluable, so it is easier to argue / debug
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
from .judge_client import (
    call_judge,
    format_evidence_block,
    format_exemplars_block,
    judge_identity,
    load_exemplars,
    smart_truncate,
)


JUDGE_MODEL = (
    os.environ.get("CHECKLIST_JUDGE_MODEL")
    or os.environ.get("JUDGE_MODEL")
    or "deepseek-v4-flash"
)

# Self-consistency: majority / median-of-N for the checklist judge, matching
# depth/rigor/style. N is env-configurable; default 3.
_N_SAMPLES = int(os.environ.get("CHECKLIST_JUDGE_N_SAMPLES", os.environ.get("V3_JUDGE_N_SAMPLES", "3")))

_DIMENSION = "checklist"

# Total report budget for the de-truncated prompt (was a hard 6000 slice).
_REPORT_CAP = int(os.environ.get("V3_JUDGE_REPORT_CAP", "9000"))
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
DEFAULT_CHECKLIST_PATH = _CHECKLIST_PATHS[0]  # legacy: aggregated loader below


_SYSTEM = (
    "You evaluate whether a deep-research agent's report satisfies "
    "specific binary coverage criteria.\n\n"
    "For each criterion you will output PASS or FAIL on a single line, "
    "with no other text on that line. Be strict: if the report does "
    "not clearly demonstrate the criterion, mark FAIL. Do not give the "
    "benefit of the doubt: DRACO-style rubrics require explicit evidence.\n\n"
    "After the per-criterion lines, you may add ONE final line starting "
    "with 'NOTES:' if you want to flag anything ambiguous. No other prose."
)


def _build_user_prompt(
    intent: str, items: list[str], answer: str, evidence: dict | None = None
) -> str:
    numbered = "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))
    # De-truncation: keep head AND conclusion instead of a hard 6000 slice.
    truncated = smart_truncate(answer or "", cap=_REPORT_CAP)
    exemplars_block = format_exemplars_block(load_exemplars(_DIMENSION))
    evidence_block = format_evidence_block(evidence)
    sections = [
        f"Research task:\n{intent}",
        f"Coverage criteria (judge each independently):\n{numbered}",
    ]
    if exemplars_block:
        sections.append(exemplars_block)
    sections.append(
        f"Agent report (head and conclusion preserved):\n---\n{truncated}\n---"
    )
    if evidence_block:
        sections.append(evidence_block)
    sections.append(
        "For each numbered criterion, emit one line:\n"
        "  1. PASS|FAIL  (reason <= 12 words)\n"
        "  2. PASS|FAIL  (reason <= 12 words)\n"
        "  ...\n"
        "Then optional NOTES line."
    )
    return "\n\n".join(sections)


def _parse(text: str, n_items: int) -> list[dict[str, Any]]:
    """Extract per-item PASS/FAIL verdicts.

    Supports several formats judges emit in practice:
      - ``1. PASS - reason``  (numbered, with reason); strictest
      - ``1) PASS``           (numbered, no reason)
      - ``PASS`` per line     (unnumbered, one verdict per line); DeepSeek default
      - mixed lines
    """
    text = text or ""
    out: list[dict[str, Any]] = []

    # Pass 1: strict numbered parse
    for i in range(n_items):
        pat = rf"(?:^|\n)\s*{i+1}[\.\)]\s*(PASS|FAIL)\b\s*[:.\-\u2014)]?\s*(.*?)(?=\n\s*\d+[\.\)]|\nNOTES:|\Z)"
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
    # missing slot: old `> n_items // 2` threshold meant a mixed-format
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

    def __init__(
        self,
        checklist_path: Path | str | None = None,
        model: str | None = None,
        n_samples: int | None = None,
    ) -> None:
        self.checklist_path = Path(checklist_path) if checklist_path else DEFAULT_CHECKLIST_PATH
        self.model = model or JUDGE_MODEL
        self.n_samples = int(n_samples if n_samples is not None else _N_SAMPLES)
        self._cache: dict | None = None

    def verify(
        self,
        *,
        task_config: dict[str, Any],
        answer: str,
        page: Any = None,
        evidence: dict | None = None,
        **kwargs: Any,
    ) -> VerifierResult:
        all_lists = self._load()
        task_id = task_config.get("task_id", "")
        items = all_lists.get(task_id) or []
        if not items:
            return VerifierResult(
                score=0.0, passed=False,
                details={"reason": f"no checklist for {task_id}", "checklist_path": str(self.checklist_path)},
            )

        prompt = _build_user_prompt(task_config.get("intent", ""), items, answer, evidence)

        # Self-consistency: majority / median-of-N. Route through the pluggable
        # judge backend (DeepSeek / Claude / etc.); a different family from the
        # agent LLM removes the self-preference confound flagged by the audit.
        # Per item, take the majority PASS/FAIL across the N samples so a single
        # noisy verdict cannot flip the score.
        raw_outputs: list[str] = []
        per_sample_verdicts: list[list[dict[str, Any]]] = []
        for _ in range(max(1, self.n_samples)):
            text, err = call_judge(_SYSTEM, prompt, max_tokens=1500)
            if text is None:
                continue
            raw_outputs.append(text)
            per_sample_verdicts.append(_parse(text, len(items)))

        if not per_sample_verdicts:
            return VerifierResult.fail("judge call failed: no usable samples")

        # Per-item majority vote across samples (ties break toward FAIL, the
        # stricter outcome, consistent with the DRACO no-benefit-of-the-doubt
        # policy).
        per_item: list[dict[str, Any]] = []
        for i in range(len(items)):
            votes = [s[i]["passed"] for s in per_sample_verdicts if i < len(s)]
            pass_votes = sum(1 for v in votes if v)
            passed = pass_votes > (len(votes) / 2.0)
            reason = ""
            for s in per_sample_verdicts:
                if i < len(s) and s[i]["passed"] == passed and s[i].get("reason"):
                    reason = s[i]["reason"]
                    break
            per_item.append({
                "index": i + 1,
                "passed": passed,
                "reason": reason,
                "criterion": items[i],
                "pass_votes": pass_votes,
                "n_votes": len(votes),
            })

        passed_count = sum(1 for x in per_item if x["passed"])
        score = passed_count / len(items)

        return VerifierResult(
            score=round(score, 3),
            passed=score >= 0.7,  # 70% bar: DRACO uses similar thresholds
            details={
                "passed_count": passed_count,
                "total": len(items),
                "per_item": per_item,
                "n_samples": len(per_sample_verdicts),
                "judge_model": judge_identity()["model"],
                "judge_provider": judge_identity()["provider"],
                "raw_judge_output": " ||| ".join(raw_outputs)[:1500],
            },
        )

    def verify_pairwise(
        self,
        task_config: dict[str, Any],
        answer_a: str,
        answer_b: str,
        evidence_a: dict | None = None,
        evidence_b: dict | None = None,
    ) -> dict[str, Any]:
        """Comparative mode: which report better satisfies the checklist?

        Delegates to the dimension-aware pairwise judge. Returns
        ``{"winner": "a"|"b"|"tie", "reason": str}`` and degrades to tie
        when the judge backend is unconfigured.
        """
        from src.scoring.pairwise_judge import battle

        res = battle(
            task_intent=task_config.get("intent", ""),
            agent_a="a",
            answer_a=answer_a,
            agent_b="b",
            answer_b=answer_b,
            dimension=_DIMENSION,
            evidence_a=evidence_a,
            evidence_b=evidence_b,
        )
        winner = (res.get("winner") or "tie").lower()
        if winner not in ("a", "b", "tie"):
            winner = "tie"
        reasonings = res.get("reasonings") or []
        reason = reasonings[0] if reasonings else res.get("error", "")
        return {"winner": winner, "reason": reason}
