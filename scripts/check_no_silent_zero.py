#!/usr/bin/env python3
"""G6 gate: end-to-end no silent zero.

The frozen-sandbox scorer publishes one number per (lane, axis). A `0` there is
only trustworthy if it means "the instrument observed the report and it was
genuinely that bad" -- never "the instrument saw nothing and defaulted to 0".
This checker enforces that invariant over a directory of scoring RESULTS (not by
re-scoring; it reads what the pipeline already wrote):

  for every (lane, axis) unit,
    * the value is not NaN, and
    * if the value is 0 and the axis was not WITHHELD, it carries a
      machine-readable `reason` code.

A WITHHELD axis (the instrument could not observe it: no fetch log, fetch not
observable, damaged/incomplete evidence, ...) is the CORRECT alternative to a
false 0 and is never a violation here -- G4 owns the withhold enum; this gate
only insists that a *scored* 0 explains itself.

Input formats (auto-detected, probed against the real shapes under
data/results/):

  1. decidable per-report json  -- src.eval.closed_world_eval.evaluate() output:
     {"axes": {<axis>: score, ...}, "axis_reasons": {<axis>: code}, "detail": {...}}
     (this is the go-forward format the #39 smoke emits)
  2. board json                 -- scripts/build_truth_board.py output:
     {"rows": [{"agent": ..., "per_task_summary": {tid: {"replicates": {...}}}}]}
  3. legacy per-report score json (data/results/deep*/*.score.json):
     {"task": ..., "<axis>": {"score": float, "details": {...}}, ...}
  4. v4 per-report json         (data/results/deep_v4/*.v4.json):
     {"agent":..., "task":..., "v2_pillars": {<axis>: float}, "<block>": {"score":...}}
  5. results tsv (long form)     -- header with columns
     lane\ttask\taxis\tvalue\treason[\twithheld]  (one axis per row); or a wide
     form lane\ttask\t<axis...> with optional <axis>_reason companion columns.

Anything a format probe does not recognise is skipped (many json files under
data/results/ are not score results at all), so the checker never fabricates a
finding from an unrelated file.

Usage:
    python3 scripts/check_no_silent_zero.py <results_dir_or_file> [--out report.txt]
                                            [--quiet] [--strict-withheld-reason]

Exit code: 0 = clean, 1 = at least one violation, 2 = usage / no parseable input.
Deterministic: files and violations are emitted in sorted order.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional


# --- the axis-detail sub-key that carries a per-axis reason, per published axis
# key. Mirrors src.eval.closed_world_eval.evaluate()'s detail layout so the
# checker can recover a reason even from an older per-report json written before
# axis_reasons existed at top level. Kept in sync with decidable_scorer.
_AXIS_DETAIL_KEY = {
    "grounding_reach": "reach",
    "grounding_proof_of_fetch": "proof_of_fetch",
    "grounding_quote_support": "proof_of_fetch",
    "correctness_fact_support": "fact",
    "completeness": "completeness",
    "spec": "spec",
    "compliance": "compliance",
}

_WITHHELD_PREFIX = "withheld_"

# Canonical withhold codes: the G4 lane's WithholdReason enum
# (src/eval/decidable_scorer.py, branch gates-L3-withhold, commit 8985c07e) is
# the ONE authoritative set. After the lanes merge the enum lives in this
# repo's decidable_scorer and is imported below; until then the 18 values are
# replicated verbatim (以 gates-L3-withhold 的 WithholdReason 为准, 合并时
# 替换为 import).
_WITHHOLD_CODES_FALLBACK = frozenset({
    # transport / proof-of-fetch (src/eval/fetch_log.py) -- the evidence log
    "no_evidence_log",
    "empty_evidence_log",
    "evidence_log_multiple_run_ids",
    "evidence_missing_start_mark",
    "evidence_multiple_start_marks",
    "evidence_missing_end_mark",
    "evidence_multiple_end_marks",
    "evidence_traffic_after_end",
    "evidence_orphaned_bracket",
    "evidence_invalid_timestamp",
    "evidence_end_before_start",
    "evidence_log_damaged",
    "evidence_incomplete_unattributed",
    "evidence_isolation_ambiguous",
    "evidence_worker_disagreement",
    # lane fetches off-shim (declared fetch_mode, 8/12 lanes)
    "fetch_not_observable",
    # completeness concept axis: evaluator holds no cached copy of the page
    "concept_page_not_cached",
    # classifier fallback (G4 tests lock every live path to a non-UNKNOWN code)
    "unknown_withhold",
})


def _load_withhold_codes() -> frozenset:
    try:  # post-merge: the enum is importable from the live scorer
        from src.eval.decidable_scorer import WithholdReason  # type: ignore
        return frozenset(w.value for w in WithholdReason)
    except Exception:
        return _WITHHOLD_CODES_FALLBACK


WITHHOLD_CODES = _load_withhold_codes()


def _is_withhold_reason(reason) -> bool:
    """A reason naming an 'instrument was blind' outcome: one of the canonical
    WithholdReason codes, or the legacy withheld_* spelling."""
    return isinstance(reason, str) and (
        reason in WITHHOLD_CODES or reason.startswith(_WITHHELD_PREFIX))


# The two mutually-exclusive names the grounding-fidelity axis can carry. A
# transport_v2 report earns "grounding_proof_of_fetch" (a fetch was witnessed);
# a text_v1 report carries "grounding_quote_support" (none was). They mean
# different things and MUST NOT co-occur within one lane -- the board's rc=3
# gate refuses such a board, and SPEC_ISSUES (G6) records that a lane mixing them
# used to crash the board builder with a bare KeyError before that gate could
# fire. This checker catches the same defect from the OUTPUT, wherever it lands.
_POF_AXIS_NAMES = ("grounding_proof_of_fetch", "grounding_quote_support")


@dataclass(frozen=True)
class AxisUnit:
    """One (lane, axis) measurement extracted from a results file."""
    source: str
    lane: str
    task: str
    axis: str
    value: Optional[float]      # None => the axis is absent / withheld
    reason: Optional[str]
    withheld: bool

    def sort_key(self):
        return (self.source, self.lane, self.task, self.axis)


@dataclass(frozen=True)
class Violation:
    unit: AxisUnit
    kind: str          # "nan" | "silent_zero" | "withheld_without_reason"
    message: str


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _is_nan(x) -> bool:
    return _is_number(x) and math.isnan(float(x))


# ---------------------------------------------------------------------------
# Format probes / extractors. Each yields AxisUnit; each returns nothing (an
# empty iterator) if the object is not of its shape, so the dispatcher can try
# them in order and skip unrecognised files.
# ---------------------------------------------------------------------------

def _lane_task_from_name(path: Path) -> tuple[str, str]:
    """Best-effort (lane, task) from a `<lane>__<task>...` or `<lane>_<task>...`
    filename when the payload carries neither."""
    stem = path.name
    for suffix in (".score.json", ".v4.json", ".meta.json", ".json", ".tsv"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    if "__" in stem:
        lane, task = stem.split("__", 1)
        return lane, task
    return stem, "?"


def _withheld_and_reason(axis: str, value, axis_reasons: dict,
                         detail: dict) -> tuple[bool, Optional[str]]:
    """Decide whether `axis` is withheld and recover its reason from any of the
    places the pipeline may record one:

      - axis_reasons[axis] (the G6 map);
      - the axis's detail sub-block: `reason_code` (G4 stamps the canonical
        WithholdReason code beside the frozen prose) then `reason`;
      - `available: False` on the sub-block (transport-style withhold);
      - the G4 concept-withhold shape on completeness:
        `concept_axis_withheld: true` + `concept_axis_withheld_reason`;
      - a null axis value;
      - a reason that IS a canonical withhold code (or legacy withheld_*).
    """
    reason = axis_reasons.get(axis)
    dkey = _AXIS_DETAIL_KEY.get(axis)
    sub = detail.get(dkey) if (dkey and isinstance(detail, dict)) else None
    if reason is None and isinstance(sub, dict):
        reason = sub.get("reason_code") or sub.get("reason")
    withheld = False
    if value is None:
        withheld = True
    if isinstance(sub, dict):
        if sub.get("available") is False:
            withheld = True
        if sub.get("concept_axis_withheld"):
            # G4: concept slots whose source page the evaluator never cached.
            # Score/denominator are unchanged, so the axis value may be a real
            # number; the withheld flag says part of the pool was unobservable,
            # which is a legal, explained state, never a silent zero.
            withheld = True
            if reason is None:
                reason = (sub.get("concept_axis_withheld_reason")
                          or "concept_page_not_cached")
    if _is_withhold_reason(reason):
        withheld = True
    return withheld, (str(reason) if reason is not None else None)


def _from_axes_dict(path: Path, obj: dict) -> Iterator[AxisUnit]:
    """Format 1: a per-report evaluate() payload ({"axes": {...}, ...})."""
    axes = obj.get("axes")
    if not isinstance(axes, dict):
        return
    lane = str(obj.get("agent") or obj.get("lane") or _lane_task_from_name(path)[0])
    task = str(obj.get("task") or obj.get("task_id") or _lane_task_from_name(path)[1])
    axis_reasons = obj.get("axis_reasons")
    if not isinstance(axis_reasons, dict):
        axis_reasons = (obj.get("detail") or {}).get("axis_reasons", {})
    if not isinstance(axis_reasons, dict):
        axis_reasons = {}
    detail = obj.get("detail") if isinstance(obj.get("detail"), dict) else {}
    withheld_axes = obj.get("withheld_axes") or []
    for axis, raw in axes.items():
        value = float(raw) if _is_number(raw) else None
        withheld, reason = _withheld_and_reason(axis, value, axis_reasons, detail)
        if axis in withheld_axes:
            withheld = True
        yield AxisUnit(str(path), lane, task, str(axis), value, reason, withheld)


def _from_board(path: Path, obj: dict) -> Iterator[AxisUnit]:
    """Format 2: a build_truth_board board json. Descends into every replicate's
    axes + axis_reasons so a 0 that survived aggregation is still checked."""
    rows = obj.get("rows")
    if not isinstance(rows, list) or not any(
        isinstance(r, dict) and "per_task_summary" in r for r in rows
    ):
        return
    for r in rows:
        if not isinstance(r, dict):
            continue
        lane = str(r.get("agent") or r.get("lane") or "?")
        pts = r.get("per_task_summary") or {}
        if not isinstance(pts, dict):
            continue
        for tid, summ in pts.items():
            reps = (summ or {}).get("replicates") or {}
            if not isinstance(reps, dict):
                continue
            for rep, cell in reps.items():
                if not isinstance(cell, dict):
                    continue
                axes = cell.get("axes") or {}
                axis_reasons = cell.get("axis_reasons") or {}
                if not isinstance(axes, dict):
                    continue
                task = f"{tid}#rep{rep}"
                for axis, raw in axes.items():
                    value = float(raw) if _is_number(raw) else None
                    withheld, reason = _withheld_and_reason(
                        str(axis), value, axis_reasons, {})
                    yield AxisUnit(str(path), lane, task, str(axis),
                                   value, reason, withheld)


def _from_legacy_score(path: Path, obj: dict) -> Iterator[AxisUnit]:
    """Formats 3 & 4: legacy per-report score json / v4 json. Axis blocks are
    top-level keys whose value is a dict carrying a numeric "score" (plus, for
    v4, the flat "v2_pillars" map)."""
    if "axes" in obj or "rows" in obj:
        return  # handled by a more specific probe
    lane = str(obj.get("agent") or _lane_task_from_name(path)[0])
    task = str(obj.get("task") or obj.get("task_id") or _lane_task_from_name(path)[1])
    emitted = False
    pillars = obj.get("v2_pillars")
    if isinstance(pillars, dict):
        for axis, raw in pillars.items():
            value = float(raw) if _is_number(raw) else None
            if value is None:
                continue
            emitted = True
            yield AxisUnit(str(path), lane, task, f"v2:{axis}", value, None, False)
    for key, block in obj.items():
        if not isinstance(block, dict) or "score" not in block:
            continue
        raw = block.get("score")
        value = float(raw) if _is_number(raw) else None
        if value is None and not _is_nan(raw):
            continue
        reason = (block.get("details") or {}).get("reason") \
            if isinstance(block.get("details"), dict) else None
        emitted = True
        yield AxisUnit(str(path), lane, task, str(key),
                       float(raw) if _is_number(raw) else None,
                       str(reason) if reason else None, False)
    if not emitted:
        return


def _from_tsv(path: Path) -> Iterator[AxisUnit]:
    """Format 5: results tsv. Long form (lane/task/axis/value/reason[/withheld])
    is preferred; a wide form (lane, task, then one column per axis, with
    optional `<axis>_reason` companion columns) is also accepted."""
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter="\t")
        rows = [r for r in reader if r and any(c.strip() for c in r)]
    if not rows:
        return
    header = [c.strip() for c in rows[0]]
    lower = [c.lower() for c in header]
    idx = {name: lower.index(name) for name in
           ("lane", "agent", "task", "axis", "value", "score", "reason", "withheld")
           if name in lower}
    lane_col = idx.get("lane", idx.get("agent"))
    val_col = idx.get("value", idx.get("score"))

    def _num(cell: str):
        c = (cell or "").strip()
        if c == "" or c.lower() in ("na", "null", "none", "-"):
            return None, True  # blank cell => withheld/absent
        low = c.lower()
        if low in ("nan",):
            return float("nan"), False
        try:
            return float(c), False
        except ValueError:
            return None, True

    # long form
    if "axis" in lower and val_col is not None:
        for r in rows[1:]:
            if lane_col is None or lane_col >= len(r):
                continue
            lane = r[lane_col].strip()
            task = r[idx["task"]].strip() if "task" in idx and idx["task"] < len(r) else "?"
            axis = r[idx["axis"]].strip() if idx["axis"] < len(r) else "?"
            value, blank = _num(r[val_col]) if val_col < len(r) else (None, True)
            reason = (r[idx["reason"]].strip() if "reason" in idx
                      and idx["reason"] < len(r) else "") or None
            withheld = blank
            if "withheld" in idx and idx["withheld"] < len(r):
                withheld = withheld or r[idx["withheld"]].strip().lower() in ("1", "true", "yes")
            if _is_withhold_reason(reason):
                withheld = True
            yield AxisUnit(str(path), lane, task, axis, value, reason, withheld)
        return
    # wide form
    if lane_col is None:
        return
    axis_cols = [i for i, name in enumerate(lower)
                 if i != lane_col and name not in ("task", "agent")
                 and not name.endswith("_reason")]
    reason_col = {name[: -len("_reason")]: i for i, name in enumerate(lower)
                  if name.endswith("_reason")}
    for r in rows[1:]:
        if lane_col >= len(r):
            continue
        lane = r[lane_col].strip()
        task = r[idx["task"]].strip() if "task" in idx and idx["task"] < len(r) else "?"
        for i in axis_cols:
            if i >= len(r):
                continue
            axis = header[i]
            value, blank = _num(r[i])
            rc = reason_col.get(lower[i])
            reason = (r[rc].strip() if rc is not None and rc < len(r) else "") or None
            withheld = blank or _is_withhold_reason(reason)
            yield AxisUnit(str(path), lane, task, axis, value, reason, withheld)


def parse_file(path: Path) -> list[AxisUnit]:
    """Extract every (lane, axis) unit from one results file, or [] if the file
    is not a recognised score-results shape."""
    if path.suffix == ".tsv":
        try:
            return list(_from_tsv(path))
        except (OSError, UnicodeDecodeError, csv.Error):
            return []
    if path.suffix != ".json":
        return []
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return []
    if not isinstance(obj, dict):
        return []
    for probe in (_from_axes_dict, _from_board, _from_legacy_score):
        units = list(probe(path, obj))
        if units:
            return units
    return []


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------

def find_violations(units: Iterable[AxisUnit],
                    strict_withheld_reason: bool = False) -> list[Violation]:
    """Apply the G6 invariant to every unit. NaN and unexplained scored-0 are
    always violations; a withheld axis is fine unless --strict-withheld-reason
    is set, which additionally requires a withheld axis to name its reason."""
    out: list[Violation] = []
    for u in units:
        if u.value is not None and _is_nan(u.value):
            out.append(Violation(u, "nan",
                                 f"{u.lane}/{u.axis}: value is NaN"))
            continue
        if u.withheld:
            if strict_withheld_reason and not u.reason:
                out.append(Violation(
                    u, "withheld_without_reason",
                    f"{u.lane}/{u.axis}: axis withheld with no reason code"))
            continue
        if u.value == 0.0 and not u.reason:
            out.append(Violation(
                u, "silent_zero",
                f"{u.lane}/{u.axis}: score is 0 with no machine-readable reason"))
    return sorted(out, key=lambda v: v.unit.sort_key() + (v.kind,))


def find_semantics_violations(units: Iterable[AxisUnit]) -> list[Violation]:
    """Flag any lane whose reports mix the two grounding-axis names (transport_v2
    proof-of-fetch and text_v1 quote-support). The two are not comparable and a
    board or run set that contains both for one lane is the exact defect the
    board's rc=3 gate refuses; catching it here means an already-written result
    directory cannot smuggle the mix past review (SPEC_ISSUES G6)."""
    by_lane: dict[str, set[str]] = {}
    rep: dict[str, AxisUnit] = {}
    for u in units:
        if u.axis in _POF_AXIS_NAMES:
            by_lane.setdefault(u.lane, set()).add(u.axis)
            rep.setdefault(u.lane, u)
    out: list[Violation] = []
    for lane, names in by_lane.items():
        if len(names) > 1:
            out.append(Violation(
                rep[lane], "mixed_pof_semantics",
                f"{lane}: lane mixes grounding-axis semantics "
                f"{sorted(names)} (transport_v2 and text_v1 are not comparable)"))
    return sorted(out, key=lambda v: v.unit.sort_key() + (v.kind,))


def iter_result_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in (".json", ".tsv"):
            files.append(p)
    return sorted(files)


def check(root: Path, strict_withheld_reason: bool = False):
    """Returns (units, violations, n_files_parsed, n_files_seen)."""
    seen = iter_result_files(root)
    units: list[AxisUnit] = []
    parsed = 0
    for p in seen:
        file_units = parse_file(p)
        if file_units:
            parsed += 1
            units.extend(file_units)
    violations = find_violations(units, strict_withheld_reason=strict_withheld_reason)
    violations = sorted(violations + find_semantics_violations(units),
                        key=lambda v: v.unit.sort_key() + (v.kind,))
    return units, violations, parsed, len(seen)


def _render(root: Path, units, violations, parsed, seen) -> str:
    lines = []
    lines.append(f"G6 no-silent-zero check: {root}")
    lines.append(f"  files scanned            : {seen}")
    lines.append(f"  files parsed as results  : {parsed}")
    lines.append(f"  (lane, axis) units       : {len(units)}")
    lines.append(f"  violations               : {len(violations)}")
    by_kind: dict[str, int] = {}
    for v in violations:
        by_kind[v.kind] = by_kind.get(v.kind, 0) + 1
    if by_kind:
        lines.append("  by kind                  : "
                     + ", ".join(f"{k}={n}" for k, n in sorted(by_kind.items())))
    if violations:
        lines.append("")
        lines.append("VIOLATIONS (source | lane | task | axis | kind):")
        for v in violations:
            u = v.unit
            lines.append(f"  {u.source} | {u.lane} | {u.task} | {u.axis} | "
                         f"{v.kind} | value={u.value!r} reason={u.reason!r}")
    else:
        lines.append("  RESULT                   : GREEN (no silent zero, no NaN)")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="scoring results directory (or a single file)")
    ap.add_argument("--out", help="also write the report to this text file")
    ap.add_argument("--quiet", action="store_true",
                    help="print only the summary line and exit code")
    ap.add_argument("--strict-withheld-reason", action="store_true",
                    help="additionally require every WITHHELD axis to name a reason")
    args = ap.parse_args(argv)

    root = Path(args.path)
    if not root.exists():
        print(f"error: path does not exist: {root}", file=sys.stderr)
        return 2

    units, violations, parsed, seen = check(
        root, strict_withheld_reason=args.strict_withheld_reason)
    report = _render(root, units, violations, parsed, seen)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report + "\n", encoding="utf-8")

    if args.quiet:
        print(report.splitlines()[-1].strip())
    else:
        print(report)

    if parsed == 0:
        print("error: no parseable score-results files found under "
              f"{root}", file=sys.stderr)
        return 2
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
