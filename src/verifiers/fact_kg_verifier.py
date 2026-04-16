"""FactKGVerifier — v3 main fact-checking verifier.

Given:
  - a task's golden triples (data/golden/<task_id>.json)
  - the agent's markdown answer
computes recall / precision / F1 of factual claims:

  * recall    = fraction of golden triples mentioned in the answer
  * precision = fraction of agent-extracted triples supported by either
                the DB or the golden set
  * f1        = harmonic mean of the two

Recall does NOT require a DB round-trip — we do substring co-occurrence
matching of subject+object within the answer text. This keeps recall cheap
and 100% deterministic (no LLM variance).

Precision DOES require the LLM triple extractor + DB lookup. If the
extractor or DB is unavailable, precision falls back to 1.0 (we don't
penalize the agent for our infra being down).

The verifier returns `score = f1` for wiring into CompositeScorer v3.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .base import VerifierResult
from ..golden.db_schema_map import PREDICATES, site_of
from ..golden.db_verifier import get_store
from ..golden.triple_extractor import extract_triples


GOLDEN_DIR = Path(os.environ.get(
    "FACT_KG_GOLDEN_DIR",
    str(Path(__file__).resolve().parents[2] / "data" / "golden"),
))


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _number_in(obj: str, hay: str) -> bool:
    """Does the numeric value in `obj` appear in `hay`? Tolerant to $, commas."""
    m = re.search(r"-?\d+(?:\.\d+)?", obj or "")
    if not m:
        return False
    num = m.group(0)
    h = hay.replace(",", "").replace("$", "").replace("¥", "")
    # Require a word-boundary match so "4.3" doesn't match "140.35".
    return re.search(rf"(?<![\d.]){re.escape(num)}(?![\d])", h) is not None


_GROUP_PREFIXES = ("theme:", "tea-type:", "forum:", "author:", "category:")


def _strip_group_prefix(subject: str) -> str:
    """Oracle group-subjects use 'theme:Foo' / 'tea-type:green'. Strip the label
    so matching runs against the human-readable tail ('foo', 'green')."""
    s = subject.strip()
    # Support compound keys like 'author:X/forum:Y' — strip each segment.
    parts = s.split("/")
    cleaned = []
    for part in parts:
        for pfx in _GROUP_PREFIXES:
            if part.lower().startswith(pfx):
                part = part[len(pfx):]
                break
        cleaned.append(part)
    return " ".join(p for p in cleaned if p)


def _subject_in(subject: str, hay: str) -> bool:
    """Does the subject appear (as a fuzzy prefix) anywhere in `hay`?"""
    core = _strip_group_prefix(subject)
    s = _normalize(core)
    if not s:
        return False
    for n in (60, 40, 24, 12):
        if len(s) >= n and s[:n] in hay:
            return True
    return s in hay


def _mention_score(triples: list[dict], answer: str) -> tuple[int, list[dict]]:
    """Return (matched_count, per_triple_result)."""
    hay_raw = answer or ""
    hay_norm = _normalize(hay_raw)
    details = []
    matched = 0
    for t in triples:
        subj = t.get("subject", "") or ""
        obj = str(t.get("object", ""))
        pred = t.get("predicate", "")
        subj_ok = _subject_in(subj, hay_norm) if subj else True  # empty subj → skip gate
        # Object matching: numeric predicates use number regex, strings use fuzzy substring.
        if _looks_numeric(obj):
            obj_ok = _number_in(obj, hay_raw)
        else:
            obj_ok = _normalize(obj) in hay_norm
        ok = subj_ok and obj_ok
        if ok:
            matched += 1
        details.append({
            "subject": subj[:60], "predicate": pred, "object": obj[:40],
            "subject_hit": subj_ok, "object_hit": obj_ok, "matched": ok,
        })
    return matched, details


def _looks_numeric(s: str) -> bool:
    return bool(re.match(r"^-?\d+(\.\d+)?$", (s or "").strip()))


def _load_golden(task_id: str) -> list[dict]:
    path = GOLDEN_DIR / f"{task_id}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return [t for t in data if isinstance(t, dict)]
    except Exception:
        return []


class FactKGVerifier:
    """Compute recall, precision, F1 of factual claims against a KG golden.

    Recall: substring-based co-occurrence of (subject, object) in answer.
    Precision: LLM-extracted triples, verified by DB or golden overlap.
    """

    kind = "fact_kg"

    def __init__(self, *, do_precision: bool = True, max_precision_triples: int = 30) -> None:
        self.do_precision = do_precision
        self.max_precision_triples = max_precision_triples

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any = None) -> VerifierResult:
        task_id = task_config.get("task_id") or ""
        sites = task_config.get("sites") or []
        site = sites[0] if sites else None

        golden = _load_golden(task_id)
        if not golden:
            return VerifierResult(
                score=0.0, passed=False,
                details={"reason": f"no golden triples for {task_id}"},
            )

        # --- RECALL ---
        matched, per_triple = _mention_score(golden, answer)
        total = len(golden)
        recall = matched / total if total else 0.0

        # --- PRECISION (optional) ---
        precision = 1.0
        extracted: list[dict] = []
        raw_extract = ""
        verified = unverifiable = wrong = 0
        if self.do_precision and site:
            extracted, raw_extract = extract_triples(answer or "", site=site)
            extracted = extracted[: self.max_precision_triples]
            if extracted:
                # For each extracted triple: DB lookup → True/False/None.
                # Fallback: if DB unverifiable, check if the triple is in golden.
                try:
                    store = get_store(site)
                except Exception:
                    store = None
                golden_keys = {
                    (_normalize(t["subject"]), t["predicate"], _normalize(str(t["object"])))
                    for t in golden
                }
                for et in extracted:
                    out = None
                    if store:
                        try:
                            out = store.verify(et["subject"], et["predicate"], str(et["object"])).outcome
                        except Exception:
                            out = None
                    if out is True:
                        verified += 1
                    elif out is False:
                        wrong += 1
                    else:
                        key = (_normalize(et["subject"]), et["predicate"], _normalize(str(et["object"])))
                        if key in golden_keys:
                            verified += 1
                        else:
                            unverifiable += 1
                decidable = verified + wrong
                precision = (verified / decidable) if decidable > 0 else 1.0

        # --- F1 ---
        if precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = 0.0

        details = {
            "task_id": task_id,
            "site": site,
            "golden_total": total,
            "recall": round(recall, 4),
            "recall_matched": matched,
            "precision": round(precision, 4),
            "extracted": len(extracted),
            "precision_verified": verified,
            "precision_wrong": wrong,
            "precision_unverifiable": unverifiable,
            "f1": round(f1, 4),
            # Expose a compact sample so debug is possible without huge noise.
            "misses_sample": [d for d in per_triple if not d["matched"]][:6],
        }
        return VerifierResult(score=f1, passed=f1 > 0.0, details=details)
