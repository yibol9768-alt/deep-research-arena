"""CompletenessVerifier (CLOSED_WORLD_REDESIGN.md section 8).

The closed-world superpower: because the sandbox is a closed, queryable world, the
golden's ``relevant_set`` is the COMPLETE set of entities that satisfy the task's
relevance predicate (derived from the DB by ``scripts/build_db_golden.py``, not
scraped). So we can measure TRUE completeness:

    completeness = (relevant entities correctly surfaced) / |relevant_set|

This is impossible on the live web, where the relevant set is unknown and the
field must fall back to TREC pooling / bpref ESTIMATES. Here the denominator is
exact, so we report exact completeness rather than an incompleteness-robust guess.

"Correctly surfaced" composes with grounding: an entity counts only when the
report both references it (its sandbox URL is cited, or its name appears) AND
states at least one of its DB-TRUE facts. A hallucinated entity (absent from the
relevant_set) cannot inflate the score, and an entity mentioned with only invented
numbers is not credited.

Pure and deterministic: it matches the report text against the DB-derived golden.
No sandbox fetch and no LLM, so it is offline-testable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .base import VerifierResult
from .citation_format import canonicalize_url, extract_cited_urls


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _looks_numeric(s: str) -> bool:
    return bool(re.match(r"^-?\d+(?:\.\d+)?$", (s or "").strip()))


def _number_in(value: str, hay: str) -> bool:
    """Does the numeric value appear in ``hay`` as a whole number? Tolerant to
    $, commas, currency. Word-boundary guarded so 4.3 does not match 140.35."""
    m = re.search(r"-?\d+(?:\.\d+)?", value or "")
    if not m:
        return False
    num = m.group(0)
    h = (hay or "").replace(",", "").replace("$", "").replace("¥", "")
    return re.search(rf"(?<![\d.]){re.escape(num)}(?![\d])", h) is not None


def _value_present(value: str, hay_raw: str, hay_norm: str) -> bool:
    v = str(value)
    if _looks_numeric(v):
        return _number_in(v, hay_raw)
    return _normalize(v) in hay_norm


def _load_relevant_set(task_config: dict[str, Any]) -> list[dict]:
    """Load the relevant_set, either inline on the task or from a golden path."""
    cfg = task_config.get("completeness") or {}
    inline = cfg.get("relevant_set") or task_config.get("relevant_set")
    if inline:
        return [e for e in inline if isinstance(e, dict)]
    path = cfg.get("golden_path") or (task_config.get("golden") or {}).get("relevant_set_path")
    if not path:
        return []
    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[2] / p
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except Exception:
        return []
    rs = data.get("relevant_set") if isinstance(data, dict) else data
    return [e for e in (rs or []) if isinstance(e, dict)]


class CompletenessVerifier:
    """Exact closed-world completeness against the DB-derived relevant_set."""

    kind = "completeness"

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any = None) -> VerifierResult:
        relevant = _load_relevant_set(task_config)
        if not relevant:
            return VerifierResult.fail("no relevant_set for completeness")

        cited_canon, _ = extract_cited_urls(answer, sandbox_hosts=None, sandbox_only=False)
        hay_raw = answer or ""
        hay_norm = _normalize(hay_raw)

        # completeness@K: score against the top-K most important entities (by weight,
        # then review_count) so the denominator is a realistic coverage target, not
        # the entire on-topic catalog (which would put every report near 0, the
        # must-cite-recall failure mode). k=0 scores the full relevant_set.
        cfg = task_config.get("completeness") or {}
        k = int(cfg.get("k", 40))

        def _importance(e: dict) -> tuple:
            try:
                rc = int(float((e.get("facts") or {}).get("review_count", 0) or 0))
            except Exception:
                rc = 0
            return (float(e.get("weight", 0.5) or 0.5), rc)

        ranked = sorted(relevant, key=_importance, reverse=True)
        pool = ranked[:k] if k > 0 else ranked

        surfaced_w = 0.0
        total_w = 0.0
        n_surfaced = 0
        misses: list[dict] = []

        for e in pool:
            weight = float(e.get("weight", 1.0) or 0.0)
            total_w += weight

            url = e.get("url") or ""
            name = e.get("name") or e.get("title") or ""
            facts = e.get("facts") or {}

            # Referenced: its sandbox URL is cited, OR its name appears in prose.
            referenced = bool(url) and canonicalize_url(url) in cited_canon
            if not referenced and name:
                referenced = _normalize(name) in hay_norm

            # Grounded: at least one DB-true fact value appears (anti-hallucination).
            # If the entity carries no facts, referencing it is enough.
            if facts:
                fact_ok = any(_value_present(v, hay_raw, hay_norm) for v in facts.values())
            else:
                fact_ok = True

            if referenced and fact_ok:
                surfaced_w += weight
                n_surfaced += 1
            elif len(misses) < 8:
                misses.append({
                    "name": str(name)[:50] or str(url)[:50],
                    "referenced": referenced,
                    "fact_ok": fact_ok,
                })

        completeness = (surfaced_w / total_w) if total_w else 0.0
        pool_n = len(pool)
        min_pass = float(cfg.get("min_completeness", 0.0))

        return VerifierResult(
            score=round(completeness, 4),
            passed=completeness >= min_pass,
            details={
                "completeness": round(completeness, 4),
                "k": k,
                "pool_size": pool_n,
                "relevant_total": len(relevant),
                "surfaced_count": n_surfaced,
                "completeness_unweighted": round(n_surfaced / pool_n, 4) if pool_n else 0.0,
                "weighted_surfaced": round(surfaced_w, 4),
                "weighted_total": round(total_w, 4),
                "misses_sample": misses,
            },
        )
