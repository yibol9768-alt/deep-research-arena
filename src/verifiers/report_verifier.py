"""Verifier for deep-research `report_match` eval type.

Checks:
  1. Answer parses as JSON.
  2. Matches `report_schema` (JSON Schema draft-7, via `jsonschema`).
  3. Every `FieldConstraint` in `report_expected` matches at least one item
     in the corresponding list field.

Deterministic, no LLM involved.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .base import VerifierResult


def _as_dict(answer: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(answer or "")
    except Exception:
        # Tolerate wrapped markdown fences
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", answer or "", re.S)
        if not m:
            return None
        try:
            obj = json.loads(m.group(1))
        except Exception:
            return None
    return obj if isinstance(obj, dict) else None


def _match_constraint(item: dict[str, Any], c: dict[str, Any]) -> tuple[bool, str]:
    """Return (ok, reason_if_not)."""
    if "name_contains" in c and c["name_contains"]:
        name = str(item.get("name", ""))
        for needle in c["name_contains"]:
            if needle.lower() not in name.lower():
                return False, f"name missing '{needle}'"
    if "name_regex" in c and c["name_regex"]:
        if not re.search(c["name_regex"], str(item.get("name", "")), re.I):
            return False, f"name_regex miss"
    if "price_range" in c and c["price_range"]:
        lo, hi = c["price_range"]
        try:
            p = float(item.get("price"))
        except Exception:
            return False, "price not numeric"
        if not (lo <= p <= hi):
            return False, f"price {p} outside [{lo}, {hi}]"
    if "rating_min" in c and c["rating_min"] is not None:
        try:
            r = float(item.get("rating"))
        except Exception:
            return False, "rating not numeric"
        if r < c["rating_min"]:
            return False, f"rating {r} < {c['rating_min']}"
    if "url_regex" in c and c["url_regex"]:
        url = str(item.get("product_url") or item.get("url") or "")
        if not re.search(c["url_regex"], url):
            return False, "url_regex miss"
    return True, ""


def _validate_schema(obj: dict, schema: dict) -> tuple[bool, str]:
    try:
        import jsonschema  # type: ignore
    except Exception:
        return True, "jsonschema unavailable - skipped"
    try:
        jsonschema.validate(obj, schema)
        return True, ""
    except Exception as e:
        return False, f"schema: {e}"


class ReportVerifier:
    kind = "report_match"

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any = None) -> VerifierResult:
        report = _as_dict(answer)
        if report is None:
            return VerifierResult.fail("answer is not valid JSON object")

        schema = task_config.get("report_schema") or {}
        if schema:
            ok, why = _validate_schema(report, schema)
            if not ok:
                return VerifierResult.fail(why, report=report)

        expected = (task_config.get("eval") or {}).get("report_expected") or {}
        misses: list[dict[str, Any]] = []

        # For each list field in expected, each constraint must match at
        # least one actual item (multiset semantics, order-insensitive).
        for field, constraints in expected.items():
            if field in ("facts", "numeric", "extra"):
                continue
            if not constraints:
                continue  # explicit null/empty = no constraint on this field
            actual = report.get(field)
            if not isinstance(actual, list):
                misses.append({"field": field, "reason": "missing or not a list"})
                continue
            for ci, c in enumerate(constraints or []):
                c = dict(c)
                c.pop("extra", None)
                if not any(_match_constraint(it, c) == (True, "") for it in actual):
                    reasons = [_match_constraint(it, c)[1] for it in actual]
                    misses.append({"field": field, "constraint_idx": ci, "no_match_reasons": reasons[:3]})

        # facts: every string must appear somewhere in the JSON-serialized report
        for fact in expected.get("facts", []) or []:
            blob = json.dumps(report, ensure_ascii=False).lower()
            if fact.lower() not in blob:
                misses.append({"fact": fact, "reason": "not present"})

        # numeric: field path -> (lo, hi) range
        for path, rng in (expected.get("numeric") or {}).items():
            val = report
            for part in path.split("."):
                if isinstance(val, dict):
                    val = val.get(part)
                else:
                    val = None
                    break
            try:
                fval = float(val)
            except Exception:
                misses.append({"numeric": path, "reason": f"not numeric: {val!r}"})
                continue
            lo, hi = rng
            if not (lo <= fval <= hi):
                misses.append({"numeric": path, "value": fval, "range": [lo, hi]})

        if misses:
            return VerifierResult(score=0.0, passed=False, details={"misses": misses})
        return VerifierResult.ok(report_keys=list(report.keys()))
