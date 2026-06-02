"""Contrastive active-rubric generation from rollout batches."""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from src.verifiers.judge_client import call_judge_heavy

from .store import RubricItem


_SYSTEM = (
    "You generate task-specific grading rubrics for deep-research reports. "
    "Use the privileged rollout evidence to create discriminative, concrete, "
    "checkable criteria that separate strong answers from weak answers."
)


def _criterion_id(prefix: str, criterion: str) -> str:
    digest = hashlib.sha1(criterion.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def _clean_criterion(text: str) -> str:
    text = re.sub(r"```(?:json)?", "", text, flags=re.I).strip()
    text = re.sub(r"^\s*(?:[-*]|\d+[\.)])\s*", "", text).strip()
    text = re.sub(r"^(?:criterion|rubric|item)\s*[:=-]\s*", "", text, flags=re.I).strip()
    text = re.sub(r"\s*\(?\s*weight\s*[:=]\s*[-+]?\d*\.?\d+\s*\)?\s*", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -:\t")
    return text


def _parse_weight(data: Any, default: float = 1.0) -> float:
    if isinstance(data, dict):
        raw = data.get("weight", default)
    else:
        match = re.search(r"weight\s*[:=]\s*([-+]?\d*\.?\d+)", str(data), re.I)
        raw = match.group(1) if match else default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _json_candidates(text: str) -> list[Any]:
    stripped = re.sub(r"```(?:json)?|```", "", text or "", flags=re.I).strip()
    candidates = [stripped]
    start = stripped.find("[")
    end = stripped.rfind("]")
    if 0 <= start < end:
        candidates.append(stripped[start:end + 1])
    start = stripped.find("{")
    end = stripped.rfind("}")
    if 0 <= start < end:
        candidates.append(stripped[start:end + 1])

    parsed: list[Any] = []
    for candidate in candidates:
        try:
            parsed.append(json.loads(candidate))
        except Exception:
            continue
    return parsed


def _iter_json_items(parsed: Any) -> list[Any]:
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("criteria", "items", "rubrics", "negative_items"):
            value = parsed.get(key)
            if isinstance(value, list):
                return value
    return []


def _parse_rubric_output(
    text: str | None,
    *,
    k: int,
    tier: str,
    origin: str,
    polarity: str,
    id_prefix: str,
) -> list[RubricItem]:
    if not text or k <= 0:
        return []

    raw_items: list[Any] = []
    for parsed in _json_candidates(text):
        raw_items = _iter_json_items(parsed)
        if raw_items:
            break

    if not raw_items:
        lines = []
        for line in str(text).splitlines():
            line = line.strip()
            if not line or line.startswith("```"):
                continue
            if re.match(r"^(?:here are|criteria|rubrics?)\b", line, re.I):
                continue
            if re.match(r"^(?:[-*]|\d+[\.)])\s+", line):
                lines.append(line)
        raw_items = lines

    out: list[RubricItem] = []
    seen: set[str] = set()
    for raw in raw_items:
        if isinstance(raw, dict):
            criterion = str(
                raw.get("criterion")
                or raw.get("text")
                or raw.get("description")
                or ""
            )
            weight = _parse_weight(raw)
            is_deterministic = bool(raw.get("is_deterministic", False))
            item_id = str(raw.get("id") or "").strip()
        else:
            criterion = str(raw)
            weight = _parse_weight(raw)
            is_deterministic = False
            item_id = ""

        criterion = _clean_criterion(criterion)
        if not criterion:
            continue
        key = criterion.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            RubricItem(
                id=item_id or _criterion_id(id_prefix, criterion),
                criterion=criterion,
                weight=weight,
                is_deterministic=is_deterministic,
                polarity=polarity,
                tier=tier,
                origin=origin,
                version=0,
            )
        )
        if len(out) >= k:
            break
    return out


def _format_evidence(evidence: Any) -> str:
    if not evidence:
        return "(no retrieved evidence provided)"
    if isinstance(evidence, dict):
        rows = evidence.items()
    else:
        rows = enumerate(evidence)
    lines = []
    for url, snippet in list(rows)[:8]:
        lines.append(f"- {url}: {str(snippet)[:700]}")
    return "\n".join(lines) if lines else "(no retrieved evidence provided)"


def _format_rollout(label: str, rollout: dict[str, Any]) -> str:
    evidence = rollout.get("evidence") or rollout.get("retrieved_snippets") or {}
    return (
        f"{label} reward: {float(rollout.get('reward', 0.0)):.4f}\n"
        f"{label} report:\n{str(rollout.get('report_md') or '')[:4000]}\n\n"
        f"{label} privileged retrieved evidence:\n{_format_evidence(evidence)}"
    )


def _build_prompt(task_config: dict[str, Any], rollouts: list[dict[str, Any]], k: int) -> str:
    ordered = sorted(rollouts, key=lambda row: float(row.get("reward", 0.0)), reverse=True)
    high = ordered[0]
    low = ordered[-1]
    return (
        "Build DR-Tulu-style evolving rubrics from contrastive rollouts.\n\n"
        f"Task id: {task_config.get('task_id', '')}\n"
        f"Task intent: {task_config.get('intent') or task_config.get('prompt') or ''}\n\n"
        "Goal: propose concrete criteria that the high-reward rollout satisfies "
        "and the low-reward rollout misses. Criteria must be task-specific, "
        "checkable from the report, non-redundant, and not generic writing advice.\n\n"
        f"{_format_rollout('HIGH', high)}\n\n"
        f"{_format_rollout('LOW', low)}\n\n"
        f"Return JSON only: an array of at most {k} objects with keys "
        '"criterion", "weight", and optional "is_deterministic".'
    )


def _call_with_optional_model(
    system: str,
    user: str,
    *,
    model: str | None,
) -> tuple[str | None, str | None]:
    if not model:
        return call_judge_heavy(system, user, max_tokens=2500, temperature=0.1)

    old = os.environ.get("JUDGE_MODEL_HEAVY")
    os.environ["JUDGE_MODEL_HEAVY"] = model
    try:
        return call_judge_heavy(system, user, max_tokens=2500, temperature=0.1)
    finally:
        if old is None:
            os.environ.pop("JUDGE_MODEL_HEAVY", None)
        else:
            os.environ["JUDGE_MODEL_HEAVY"] = old


def generate_active_rubrics(
    task_config: dict[str, Any],
    rollouts: list[dict[str, Any]],
    *,
    k: int = 5,
    model: str | None = None,
) -> list[RubricItem]:
    if not rollouts or k <= 0:
        return []

    prompt = _build_prompt(task_config, rollouts, k)
    text, err = _call_with_optional_model(_SYSTEM, prompt, model=model)
    if text is None or err:
        return []
    return _parse_rubric_output(
        text,
        k=k,
        tier="active",
        origin="generated",
        polarity="positive",
        id_prefix="active",
    )
