#!/usr/bin/env python3
"""Build a REAL, non-synthetic deep-research leaderboard.

This replaces the synthetic placeholder produced by
``build_deep_leaderboard_v3.py --dry-run`` (which fabricated scores via
``_synthesize_score_for_agent_task`` and pinned claude-code/opencode to the
top). NOTHING here is synthesized: if an agent has no real report files it is
SKIPPED and logged, never invented.

Two orthogonal numbers per the redesign (docs/SCORING_REDESIGN.md), plus a gate:

  GROUNDING (deterministic, from stored pillars / simple_score)
    Per (agent, task) we read the real ``*.score.json`` and compute a grounding
    number. We would prefer ``src.scoring.simple_score.grounding_score``, but
    that function requires three positional arguments (cited_pairs,
    retrieved_snippets, golden) which the stored JSON cannot supply, so the
    preferred path is INAPPLICABLE and the number actually computed is the
    ADDITIVE blend ``0.5 * curated_must_cite_recall + 0.5 * quote_match.score``
    (curated recall recomputed locally when a golden set exists, else the
    stored ``must_cite_recall``). This is the honest ``composite_formula``
    reported in the output; it is NOT an F1. Reachable-but-non-golden citation
    VOLUME never helps: domain_balance, pool_coverage, and the cited>=N count
    gate are deliberately ignored.

  QUALITY (pairwise LLM judge, length-controlled)
    Per task we run ``pairwise_judge.battle(dimension=None)`` between agents'
    real reports (round-robin, or vs a fixed --reference agent), using the lite
    model (deepseek-v4-flash) with position-swap (battle already swaps). LENGTH
    CONTROL: both reports are truncated to the same word budget before judging
    so a longer report cannot win on length alone; per-report word counts are
    also recorded. A pre-flight 1-battle judge SMOKE runs first and ABORTS the
    build if the judge backend is down (so a degenerate all-tie board is never
    written), and the fraction of judge-error battles is tracked and aborts /
    loudly flags past ~5%. Each battle persists ``verdicts_raw`` + any
    ``error`` into the battle_log so a degenerate run is detectable. The
    HEADLINE Bradley-Terry rating (src.scoring.bradley_terry, bootstrap CI) is
    fit on UNGATED agents only (battles touching a gated side are dropped) so
    beating gated junk cannot inflate the headline Elo; a transparency full-set
    fit and the full battle_log are also kept.

  GATE
    Agents whose mean grounding is below --grounding-floor are flagged
    ``gated: True`` (truth-gate). Both ranked views are still emitted.

Output JSON marks ``synthetic_placeholder: false`` and ``source: "real"``.
"""

from __future__ import annotations

import argparse
import glob
import inspect
import json
import os
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

# Make ``src`` importable when run as a script from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DEFAULT_REPORT_DIR = _REPO_ROOT / "data" / "results" / "deep"
DEFAULT_SCORE_DIR = _REPO_ROOT / "data" / "results" / "deep_v3"
DEFAULT_OUT = _REPO_ROOT / "data" / "results" / "real" / "leaderboard_real.json"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_GROUNDING_FLOOR = 0.30
DEFAULT_WORD_BUDGET = 1500

# The grounding number this script actually computes is an ADDITIVE blend of a
# citation-fidelity term (quote_match score) and a curated must-cite recall
# term, NOT the F1(precision, recall) that src.scoring.simple_score.grounding_score
# would compute. We surface the honest formula in the output JSON so a reader
# is never misled into thinking an F1 was used.
GROUNDING_COMPOSITE_FORMULA = "0.5 * curated_must_cite_recall + 0.5 * quote_match_score"
GROUNDING_DESCRIPTION = (
    "Additive citation-fidelity + curated recall: "
    "0.5 * curated_must_cite_recall + 0.5 * quote_match_score. "
    "This is NOT an F1; citation VOLUME (domain_balance / pool_coverage / "
    "cited counts) is deliberately ignored."
)

# Fraction of judge-error battles above which the run is degenerate and must be
# aborted (or loudly flagged). An all-error board collapses to flat ~1000 Elo.
JUDGE_ERROR_ABORT_FRACTION = 0.05


class JudgeErrorAbort(RuntimeError):
    """Raised when the judge backend is failing so the board would be garbage.

    Carries ``error_fraction`` (and for the pre-flight smoke, the failing
    battle result) so callers can report precisely why the run was aborted
    instead of silently emitting a flat ~1000-Elo board.
    """

    def __init__(self, message: str, *, error_fraction: float | None = None, sample: dict | None = None):
        super().__init__(message)
        self.error_fraction = error_fraction
        self.sample = sample

# Only matrix reports are scored (smoke runs are warm-up). Pattern:
#   <agent>__<task_id>_matrix.md
_MATRIX_RE = re.compile(r"^(?P<agent>.+?)__(?P<task>.+?)_matrix\.md$")


# --------------------------------------------------------------------------- #
# Discovery: build the (agent, task) work list from REAL files only.
# --------------------------------------------------------------------------- #
def discover_reports(report_dir: Path) -> dict[str, dict[str, Path]]:
    """Return {agent: {task_id: md_path}} for every real matrix report on disk.

    Never fabricates entries. Agents/tasks with no file simply do not appear.
    """
    out: dict[str, dict[str, Path]] = defaultdict(dict)
    for p in sorted(Path(report_dir).glob("*_matrix.md")):
        m = _MATRIX_RE.match(p.name)
        if not m:
            continue
        out[m.group("agent")][m.group("task")] = p
    return {a: dict(t) for a, t in out.items()}


def score_path_for(score_dir: Path, agent: str, task: str) -> Path:
    return Path(score_dir) / f"{agent}__{task}_matrix.score.json"


# --------------------------------------------------------------------------- #
# GROUNDING (deterministic).
# --------------------------------------------------------------------------- #
def _required_positional_count(fn) -> int:
    """Number of required (no-default) positional parameters ``fn`` accepts.

    Used to decide whether the preferred ``fn(score_json)`` single-dict calling
    convention is even applicable, WITHOUT swallowing a real signature mismatch
    at call time. ``*args`` is reported as a single optional slot (0 required).
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        # Builtin / un-introspectable: assume the single-dict shape may apply.
        return 1
    required = 0
    for p in sig.parameters.values():
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            if p.default is inspect.Parameter.empty:
                required += 1
    return required


def _load_simple_score():
    """Import grounding_score from the sibling module if usable (runtime).

    The preferred path drives the scorer with a single stored-JSON dict
    (``fn(score_json)``). The current ``simple_score.grounding_score`` instead
    requires THREE positional arguments (cited_pairs, retrieved_snippets,
    golden), which the stored JSON cannot supply (it does not retain per-claim
    (url, claim) support tuples; fabricating them would be exactly the invented
    signal this redesign forbids). So if the imported function is not callable
    with a single positional dict, the preferred path is INAPPLICABLE and we
    return None, letting the deterministic additive formula run. This decision
    is made by signature inspection, NOT by swallowing a TypeError, so a
    genuine runtime error in an applicable single-arg scorer fails loudly.
    """
    try:
        from src.scoring.simple_score import grounding_score  # type: ignore
    except Exception:
        return None
    if _required_positional_count(grounding_score) > 1:
        # Wrong calling convention for the stored-JSON path: do not pretend.
        return None
    return grounding_score


def _simple_score_from_json(fn, score_json: dict) -> float | None:
    """Drive a single-dict ``grounding_score`` from a stored score JSON.

    ``fn`` has already been vetted by ``_load_simple_score`` as callable with a
    single positional dict. We do NOT wrap the call in a bare ``except`` that
    swallows everything: a real mismatch (wrong arity, a runtime error inside
    the scorer) MUST fail loudly so a broken wiring is detected instead of
    silently and ALWAYS falling back to the additive formula.

    We do NOT synthesize cited pairs from the stored JSON, because the stored
    JSON does not retain per-claim (url, claim) support tuples; fabricating
    them would be exactly the kind of invented signal this redesign forbids.
    """
    val = fn(score_json)
    # grounding_score may return a dict {"grounding": x, ...} or a float.
    if isinstance(val, dict):
        for k in ("grounding", "score", "grounding_score"):
            if k in val:
                return float(val[k])
        return None
    if val is None:
        return None
    return float(val)


def _fallback_grounding(score_json: dict) -> float:
    """0.5*must_cite_recall + 0.5*quote_match.score from stored pillars.

    Citation VOLUME (domain_balance / pool_coverage / cited counts) is ignored
    on purpose so flooding non-golden citations cannot inflate grounding.
    """
    cov = (score_json.get("url_coverage") or {}).get("details") or {}
    recall = float(cov.get("must_cite_recall") or 0.0)
    qm = float((score_json.get("quote_match") or {}).get("score") or 0.0)
    return 0.5 * recall + 0.5 * qm


def grounding_for(score_json: dict) -> tuple[float, str]:
    """Return (grounding in [0,1], source tag)."""
    fn = _load_simple_score()
    if fn is not None:
        val = _simple_score_from_json(fn, score_json)
        if val is not None:
            return max(0.0, min(1.0, val)), "simple_score"
    return max(0.0, min(1.0, _fallback_grounding(score_json))), "fallback_recall_quote"


def load_score_json(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def load_reference_manifest(manifest: str | Path | dict) -> dict[str, str]:
    """Normalize a reference manifest into {task_id: reference_agent}.

    Accepts either an already-loaded manifest dict (as written by
    ``scripts/select_reference_reports.py``: {task: {agent, path, grounding}})
    or a path to that JSON file. Returns a flat {task: agent} mapping used to
    drive RACE-style reference-anchored battles. Malformed / agent-less entries
    are dropped rather than crashing the build.
    """
    if isinstance(manifest, (str, Path)):
        data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    else:
        data = manifest
    out: dict[str, str] = {}
    for task, entry in (data or {}).items():
        if isinstance(entry, dict):
            agent = entry.get("agent")
        else:
            # Tolerate a flat {task: agent} shape as well.
            agent = entry
        if isinstance(agent, str) and agent:
            out[str(task)] = agent
    return out


def read_report_text(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


def _golden_path(task_id: str) -> Path:
    """Resolve the golden JSON for ``task_id``, preferring the CLEANED set.

    ``data/golden/deep_clean/`` holds the relevance-cleaned goldens (off-topic
    must_cite_urls pruned; see docs/EVAL_SET_REMEDIATION.md). It is the canonical
    source once present. The raw crawl in ``data/golden/deep/`` is preserved and
    used as a fallback. Set ``USE_RAW_GOLDEN=1`` to force the raw set (for A/B).
    """
    clean = _REPO_ROOT / "data" / "golden" / "deep_clean" / f"{task_id}.json"
    raw = _REPO_ROOT / "data" / "golden" / "deep" / f"{task_id}.json"
    if os.environ.get("USE_RAW_GOLDEN") == "1":
        return raw
    return clean if clean.exists() else raw


# Map a sandbox URL to its source bucket by port. The closed sandbox exposes
# exactly three retrievable sources (see docs/EVAL_SET_REMEDIATION.md).
_SOURCE_PORTS = {"7770": "shopping", "9999": "forum", "8090": "wiki"}


def _source_of_url(url: str) -> str | None:
    m = re.search(r"://[^/]*:(\d+)/", url or "")
    return _SOURCE_PORTS.get(m.group(1)) if m else None


def load_clean_manifest() -> dict[str, dict] | None:
    """Load the cleaned-benchmark manifest ({task_id: {verdict, valid_sources}}).

    Written by scripts/build_clean_benchmark_manifest.py from the remediation
    doc. Returns the ``tasks`` mapping, or None if the manifest is absent or the
    env opt-out ``IGNORE_CLEAN_MANIFEST=1`` is set (for A/B against the raw set).
    """
    if os.environ.get("IGNORE_CLEAN_MANIFEST") == "1":
        return None
    mpath = _REPO_ROOT / "data" / "golden" / "deep_clean" / "_manifest.json"
    if not mpath.exists():
        return None
    try:
        return (json.loads(mpath.read_text(encoding="utf-8")) or {}).get("tasks") or None
    except Exception:
        return None


def _curated_recall_from_report(
    report_path: Path,
    task_id: str,
    k: int = 12,
    valid_sources: set[str] | None = None,
) -> float | None:
    """Recompute must_cite_recall against the CURATED top-K golden set.

    Pure local set-intersection of the report's cited sandbox URLs with the
    curated key golden subset (no fetch). Fixes the structurally-unreachable
    full-crawl must_cite_recall. Returns None if the golden is missing.
    """
    try:
        from src.verifiers.golden_curate import curated_recall
        from src.verifiers.citation_format import canonicalize_url
    except Exception:
        return None
    gpath = _golden_path(task_id)
    if not gpath.exists():
        return None
    try:
        golden = json.loads(gpath.read_text(encoding="utf-8"))
        mc = golden.get("must_cite_urls") or []
        # Per-task source allow-list (eval-set remediation): only count cites
        # whose source (shopping/forum/wiki, by port) is usable for this task.
        # Forum-invalid tasks pass {shopping,wiki}; a system is not penalized for
        # failing to cite forum threads that are genuinely absent for the topic.
        if valid_sources is not None:
            mc = [e for e in mc if _source_of_url(e.get("url", "")) in valid_sources]
        if not mc:
            return None
        text = read_report_text(report_path)
        urls = re.findall(r'https?://localhost:\d+/[^\s)\]"\'>]+', text)
        cited = {canonicalize_url(u) for u in urls}
        return float(curated_recall(cited, mc, k=k))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Invalid-capture detection (BUG C).
#
# Some runs do not produce a real report: STORM may write "(empty storm
# output)", a runner may crash and emit "(runner error: ...)", or the captured
# stdout is a Python traceback / a near-empty stub. Previously these were
# scored as a real (low) number ~19 and polluted the leaderboard as if the
# agent had genuinely written a weak report. They are CAPTURE FAILURES, not
# weak reports, so we exclude them into a separate `invalid_runs` bucket
# (distinct from `gated`): neither ranked nor counted as a real low score.
# --------------------------------------------------------------------------- #
MIN_REPORT_WORDS = 50

_INVALID_PREFIXES = (
    "(empty",          # "(empty storm output)"
    "(runner error",   # "(runner error: ...)"
    "(no article",     # "(no article produced)"
)
# Error markers various runners emit in lieu of a report.
_INVALID_SUBSTRINGS = (
    "(gpt-researcher produced empty output)",
    "(gpt-researcher error:",
    "(gpt-researcher produced no report",
    "(gpt-researcher timeout",
    "(gpt-researcher: missing venv",
    "(gpt-researcher: strict-sandbox refused",
    "(storm error:",
    "(empty storm output)",
)
_TRACEBACK_MARKER = "Traceback (most recent call last):"


def detect_invalid_report(text: str) -> str | None:
    """Return a reason string if ``text`` is an invalid capture, else None.

    Detects: empty/whitespace, ``(empty ...`` / ``(runner error ...`` /
    ``(no article ...`` stubs, embedded Python tracebacks, known per-runner
    error markers, and reports below ``MIN_REPORT_WORDS`` words.
    """
    s = (text or "").strip()
    if not s:
        return "empty_report"
    low = s.lower()
    for pref in _INVALID_PREFIXES:
        if low.startswith(pref):
            return f"capture_stub:{s[:60]}"
    for sub in _INVALID_SUBSTRINGS:
        if sub.lower() in low:
            return f"runner_error:{sub.strip('(').rstrip(':')}"
    if _TRACEBACK_MARKER in s:
        return "python_traceback"
    if word_count(s) < MIN_REPORT_WORDS:
        return f"too_short:{word_count(s)}_words"
    return None


# --------------------------------------------------------------------------- #
# QUALITY (pairwise) length control.
# --------------------------------------------------------------------------- #
def truncate_words(text: str, budget: int) -> str:
    """Truncate to the first ``budget`` whitespace-delimited words."""
    if budget is None or budget <= 0:
        return text
    words = text.split()
    if len(words) <= budget:
        return text
    return " ".join(words[:budget])


def word_count(text: str) -> int:
    return len(text.split())


# --------------------------------------------------------------------------- #
# Judge-error detection (BUG B3).
#
# When the judge backend errors, ``pairwise_judge`` does not raise: a per-round
# failure returns the verdict "tie" with a reasoning that starts with
# "(judge error: ...)", and a hard failure returns {"error": ...}. Either way
# the battle silently becomes a TIE. If MANY battles error, the Bradley-Terry
# fit collapses to a flat ~1000 Elo for everyone and the run looks "fine".
# We detect such battles so the build can abort / loudly flag a degenerate run
# and so the raw verdicts + error are persisted for post-hoc detection.
# --------------------------------------------------------------------------- #
_JUDGE_ERROR_PREFIX = "(judge error"


def is_judge_error_result(res: dict) -> bool:
    """True if ``res`` (a ``pairwise_judge.battle`` return) is a judge error.

    A battle is treated as a judge error when it carries an outer ``error``
    key (hard failure), OR it produced no usable verdict at all: every entry of
    ``verdicts_raw`` is None / missing, or every per-round reasoning starts with
    ``"(judge error"``. A degenerate run made of such battles collapses BT to a
    flat ~1000 Elo, so we surface it instead of silently scoring everyone tied.
    """
    if not isinstance(res, dict):
        return True
    if res.get("error"):
        return True
    verdicts = res.get("verdicts_raw")
    reasonings = res.get("reasonings") or []
    # Reasoning-based detection: every round explicitly reports a judge error.
    if reasonings and all(
        isinstance(r, str) and r.strip().startswith(_JUDGE_ERROR_PREFIX)
        for r in reasonings
    ):
        return True
    # Verdict-based detection: no usable verdict survived any round.
    if verdicts is not None:
        if len(verdicts) == 0:
            return True
        if all(v is None for v in verdicts):
            return True
    return False


# --------------------------------------------------------------------------- #
# Battle plan.
# --------------------------------------------------------------------------- #
def build_battle_plan(
    reports: dict[str, dict[str, Path]],
    agents: list[str],
    tasks: list[str],
    reference: str | None,
    reference_by_task: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """List of {task, agent_a, agent_b} for agents that have a report on task.

    Three modes, in priority order:

    * ``reference_by_task`` (RACE-style reference-anchored, eval problem #3):
      a per-task mapping {task_id: reference_agent}. On each task every OTHER
      agent battles that task's reference (Arena-Hard style fixed baseline).
      The reference agent for a task is NEVER battled against itself, so it is
      excluded from being scored against itself. Tasks whose reference has no
      report present are skipped.
    * ``reference`` (single fixed agent across all tasks): every other agent on
      a task battles that one reference.
    * neither (default): full round-robin between all present agents.

    ``reference_by_task`` takes precedence over ``reference`` when both are set.
    """
    plan: list[dict[str, str]] = []
    for task in tasks:
        present = [a for a in agents if task in reports.get(a, {})]
        if reference_by_task is not None:
            ref = reference_by_task.get(task)
            # No reference for this task, or the reference report is not present
            # in the battle scope: skip the task rather than invent a baseline.
            if not ref or ref not in present:
                continue
            for a in present:
                # Exclude the reference agent from being scored against itself.
                if a == ref:
                    continue
                plan.append({"task": task, "agent_a": a, "agent_b": ref})
        elif reference:
            if reference not in present:
                continue
            for a in present:
                if a == reference:
                    continue
                plan.append({"task": task, "agent_a": a, "agent_b": reference})
        else:
            for a, b in combinations(present, 2):
                plan.append({"task": task, "agent_a": a, "agent_b": b})
    return plan


# --------------------------------------------------------------------------- #
# Main build.
# --------------------------------------------------------------------------- #
def build(
    *,
    report_dir: Path = DEFAULT_REPORT_DIR,
    score_dir: Path = DEFAULT_SCORE_DIR,
    limit_tasks: int | None = None,
    limit_agents: int | None = None,
    agents_filter: list[str] | None = None,
    reference: str | None = None,
    reference_manifest: str | Path | dict | None = None,
    grounding_floor: float = DEFAULT_GROUNDING_FLOOR,
    word_budget: int = DEFAULT_WORD_BUDGET,
    model: str = DEFAULT_MODEL,
    dry_run: bool = False,
    n_samples: int = 3,
    bootstrap: bool = True,
    abort_on_judge_error: bool = True,
    judge_error_abort_fraction: float = JUDGE_ERROR_ABORT_FRACTION,
    judges: list[str] | None = None,
    battle_workers: int = 1,
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    reports = discover_reports(report_dir)

    # RACE-style reference-anchored mode (eval problem #3): when a per-task
    # reference manifest is supplied, each NON-reference agent is judged pairwise
    # AGAINST that task's reference report instead of round-robin. The flat
    # {task: agent} mapping is built here; it takes precedence over a single
    # fixed --reference agent.
    reference_by_task: dict[str, str] | None = None
    if reference_manifest is not None:
        reference_by_task = load_reference_manifest(reference_manifest)

    skipped: list[dict[str, str]] = []

    # ----- BUG C: drop invalid-capture (agent, task) reports -------------- #
    # A run whose report is "(empty storm output)", "(runner error: ...)", a
    # traceback, or a degenerate near-empty stub is a CAPTURE FAILURE, not a
    # weak report. We remove it from `reports` so it is never grounded,
    # battled, ranked, or counted as a real low score, and record it under
    # `invalid_runs` with the reason.
    invalid_runs: list[dict[str, str]] = []
    for a in list(reports.keys()):
        for task in list(reports[a].keys()):
            reason = detect_invalid_report(read_report_text(reports[a][task]))
            if reason is not None:
                invalid_runs.append({"agent": a, "task": task, "reason": reason})
                del reports[a][task]
        if not reports[a]:
            del reports[a]

    # Determine candidate agents.
    if agents_filter:
        candidates = list(agents_filter)
    else:
        candidates = sorted(reports.keys())

    included_agents: list[str] = []
    for a in candidates:
        if reports.get(a):
            included_agents.append(a)
        else:
            # NEVER fabricate: an agent with no real report files is skipped.
            skipped.append({"agent": a, "reason": "no real report files on disk"})

    included_agents = sorted(included_agents)
    if limit_agents is not None:
        dropped = included_agents[limit_agents:]
        included_agents = included_agents[:limit_agents]
        for a in dropped:
            skipped.append({"agent": a, "reason": "dropped by --limit-agents"})

    # Determine tasks (union across included agents).
    all_tasks = sorted({t for a in included_agents for t in reports.get(a, {})})

    # ----- Eval-set remediation: drop QUARANTINED tasks ------------------ #
    # The cleaned-benchmark manifest marks tasks whose on-topic cites collapsed
    # to wiki-only as "quarantine" (not cross-site testable). They are excluded
    # from the canonical scored set entirely (docs/EVAL_SET_REMEDIATION.md).
    clean_manifest = load_clean_manifest()
    quarantined_tasks: list[str] = []
    if clean_manifest is not None:
        keep = []
        for t in all_tasks:
            verdict = (clean_manifest.get(t) or {}).get("verdict")
            if verdict == "quarantine":
                quarantined_tasks.append(t)
            else:
                keep.append(t)
        all_tasks = keep

    if limit_tasks is not None:
        all_tasks = all_tasks[:limit_tasks]

    if reference and reference not in included_agents:
        # A reference with no reports cannot be used; fall back to round-robin.
        skipped.append({"agent": reference, "reason": "reference has no reports; round-robin used"})
        reference = None

    # Restrict the per-task reference manifest to (task, reference) pairs that
    # are actually usable in this build: the task must be in scope and the
    # reference agent must be an included agent (never fabricate a baseline).
    reference_skipped_tasks: list[dict[str, str]] = []
    if reference_by_task is not None:
        usable: dict[str, str] = {}
        included_set = set(included_agents)
        task_set = set(all_tasks)
        for task, ref in reference_by_task.items():
            if task not in task_set:
                reference_skipped_tasks.append({"task": task, "reason": "task not in scope"})
            elif ref not in included_set:
                reference_skipped_tasks.append(
                    {"task": task, "reason": f"reference agent '{ref}' not included"}
                )
            else:
                usable[task] = ref
        reference_by_task = usable

    # ----- GROUNDING (deterministic) ----------------------------------- #
    grounding_vals: dict[str, list[float]] = defaultdict(list)
    grounding_missing: list[dict[str, str]] = []
    per_agent_tasks: dict[str, set] = defaultdict(set)
    grounding_sources: set[str] = set()
    for a in included_agents:
        for task in all_tasks:
            if task not in reports.get(a, {}):
                continue
            per_agent_tasks[a].add(task)
            sj = load_score_json(score_path_for(score_dir, a, task))
            if sj is None:
                grounding_missing.append({"agent": a, "task": task})
                continue
            val, src = grounding_for(sj)
            # Prefer curated must-cite recall (recomputed locally from the report
            # + curated top-K golden) over the stale full-crawl recall in the JSON.
            # Restrict must-cite to the task's usable sources (allow-list).
            vs = None
            if clean_manifest is not None:
                allowed = (clean_manifest.get(task) or {}).get("valid_sources")
                if allowed is not None:
                    vs = set(allowed)
            cr = _curated_recall_from_report(reports[a][task], task, valid_sources=vs)
            if cr is not None:
                qm = float((sj.get("quote_match") or {}).get("score") or 0.0)
                val = max(0.0, min(1.0, 0.5 * cr + 0.5 * qm))
                src = "curated_recall+quote"
            grounding_vals[a].append(val)
            grounding_sources.add(src)

    grounding_mean = {
        a: (sum(v) / len(v) if v else 0.0) for a, v in
        ((a, grounding_vals.get(a, [])) for a in included_agents)
    }

    # ----- Battle plan ------------------------------------------------- #
    plan = build_battle_plan(
        reports, included_agents, all_tasks, reference, reference_by_task=reference_by_task
    )

    # Reference agents (RACE-style): the set of agents acting as a per-task
    # reference. A reference is NOT scored against itself, so on tasks where it
    # is the reference it accrues no win-rate; it can still be a non-reference
    # contender on OTHER tasks.
    reference_agents: set[str] = set(reference_by_task.values()) if reference_by_task else set()
    quality_mode = (
        "reference_manifest" if reference_by_task is not None
        else ("reference_fixed" if reference else "round_robin")
    )

    summary = {
        "agents_included": included_agents,
        "agents_skipped": skipped,
        "n_tasks": len(all_tasks),
        # Eval-set remediation provenance (docs/EVAL_SET_REMEDIATION.md).
        "golden_set": "deep_clean" if (_REPO_ROOT / "data" / "golden" / "deep_clean").exists()
                      and os.environ.get("USE_RAW_GOLDEN") != "1" else "deep",
        "clean_manifest_applied": clean_manifest is not None,
        "quarantined_tasks": sorted(quarantined_tasks),
        "n_quarantined": len(quarantined_tasks),
        "n_battles_planned": len(plan),
        "reference": reference or "(round-robin)",
        "quality_mode": quality_mode,
        "reference_agents": sorted(reference_agents),
        "reference_by_task": dict(reference_by_task) if reference_by_task is not None else None,
        "reference_skipped_tasks": reference_skipped_tasks,
        "word_budget": word_budget,
        "grounding_floor": grounding_floor,
        "model": model,
        "grounding_score_source": (
            "+".join(sorted(grounding_sources)) if grounding_sources else "n/a"
        ),
        # HONEST grounding formula: this is the additive citation-fidelity +
        # curated recall actually computed here, NOT an F1.
        "composite_formula": GROUNDING_COMPOSITE_FORMULA,
        "grounding_description": GROUNDING_DESCRIPTION,
        "n_invalid_runs": len(invalid_runs),
    }

    if dry_run:
        return {
            "synthetic_placeholder": False,
            "source": "real",
            "mode": "dry-run",
            "summary": summary,
            "battle_plan": plan,
            "grounding_mean": {a: round(grounding_mean[a], 4) for a in included_agents},
            "invalid_runs": invalid_runs,
        }

    # ----- QUALITY (pairwise, length-controlled) ---------------------- #
    from src.scoring.pairwise_judge import battle as _battle
    from src.scoring import bradley_terry as bt

    # GATE is deterministic (depends only on grounding_mean), so compute it
    # BEFORE battling. (BUG D) the headline Bradley-Terry rating must be fit on
    # UNGATED agents only: beating a gated junk report should not inflate Elo.
    gated_set: set[str] = {a for a in included_agents if grounding_mean[a] < grounding_floor}

    # Cache truncated report text per (agent, task).
    text_cache: dict[tuple[str, str], str] = {}
    raw_words: dict[tuple[str, str], int] = {}

    def _report(agent: str, task: str) -> str:
        key = (agent, task)
        if key not in text_cache:
            full = read_report_text(reports[agent][task])
            raw_words[key] = word_count(full)
            text_cache[key] = truncate_words(full, word_budget)
        return text_cache[key]

    def _one_judge_battle(task: str, a: str, b: str, judge_model: str) -> dict:
        return _battle(
            task_intent=f"Deep research task: {task}",
            agent_a=a,
            answer_a=_report(a, task),
            agent_b=b,
            answer_b=_report(b, task),
            model=judge_model,
            dimension=None,
            n_samples=n_samples,
        )

    # JURY_REDO_DEGRADED=1 turns the jury into a STRICT full-jury run: an
    # errored juror is retried (not silently counted as a TIE), only battles
    # where all jurors truly answered are committed to the checkpoint, and the
    # run refuses to finalize while any battle still has an errored juror. This
    # repairs the silent error->TIE bug that let a DashScope outage degrade
    # ~84% of battles into single-judge verdicts wearing a 3-judge label.
    _redo_degraded = os.environ.get("JURY_REDO_DEGRADED") == "1"
    _juror_retries = int(os.environ.get("JURY_JUROR_RETRIES", "3")) if _redo_degraded else 0
    # Minimum jurors that must carry a real verdict for a battle to count as a
    # valid PoLL result. Default 2: a 2-of-3 majority is still PoLL, so a single
    # juror timing out on a flaky network does NOT discard the battle. (The old
    # `judge_errors_partial` flag was over-sensitive -- a juror that errored on
    # one retry but still returned a verdict was wrongly marked degraded, which
    # made re-judge thrash forever on a flaky box.)
    _min_jurors = int(os.environ.get("JURY_MIN_VALID", "2"))
    # Converging contaminated re-judge: re-run battles flagged judge_errors_partial
    # (error->TIE-contaminated from a flaky-network pass) ONCE, then mark _rejudged
    # so a fresh blip can never re-trigger them -> guaranteed convergence.
    _redo_contam = os.environ.get("JURY_REDO_CONTAMINATED") == "1"

    def _n_valid_jurors(res: dict) -> int:
        votes = (res or {}).get("judge_votes") or {}
        n = 0
        for v in votes.values():
            vr = v.get("verdicts_raw") or []
            if any(x for x in vr):  # at least one non-empty verdict from this juror
                n += 1
        return n

    def _is_degraded(res: dict) -> bool:
        # Degraded only if too few jurors actually answered. A full judge error
        # (no votes dict at all) also counts.
        if is_judge_error_result(res) and not (res or {}).get("judge_votes"):
            return True
        return _n_valid_jurors(res) < _min_jurors

    def _run_battle(task: str, a: str, b: str) -> dict:
        if not judges:
            return _one_judge_battle(task, a, b, model)
        # PoLL jury (arXiv 2404.18796): each juror judges independently
        # (position-debiased internally); the battle winner is the agent with
        # MORE juror votes; tie-abstentions do not count. Jurors run
        # concurrently so battle latency = slowest juror.
        from concurrent.futures import ThreadPoolExecutor as _TPE
        import time as _time

        def _juror(m: str) -> dict:
            r = _one_judge_battle(task, a, b, m)
            attempt = 0
            while _juror_retries and is_judge_error_result(r) and attempt < _juror_retries:
                attempt += 1
                _time.sleep(min(2.0, 0.5 * attempt))
                r = _one_judge_battle(task, a, b, m)
            return r

        with _TPE(max_workers=len(judges)) as ex:
            per = dict(zip(judges, ex.map(_juror, judges)))
        a_v = b_v = errs = 0
        votes = {}
        for m, r in per.items():
            w = r.get("agent_winner", "tie")
            votes[m] = {"winner": w, "verdicts_raw": r.get("verdicts_raw")}
            if is_judge_error_result(r):
                errs += 1
            elif w == a:
                a_v += 1
            elif w == b:
                b_v += 1
        winner = a if a_v > b_v else b if b_v > a_v else "tie"
        return {
            "agent_winner": winner,
            "winner": "a" if winner == a else "b" if winner == b else "tie",
            "verdicts_raw": [v["winner"] for v in votes.values()],
            "judge_votes": votes,
            "jury": list(judges),
            "error": "all jurors errored" if errs == len(judges) else None,
            "judge_errors_partial": errs or None,
        }

    # ---- battle-level checkpoint (resumable long runs) ------------------- #
    # Every completed battle is appended to <checkpoint_path> as one JSON line
    # keyed by (task, agent_a, agent_b); on restart those battles are reused
    # instead of re-paying the judges. Lesson learned: a 400-battle jury run
    # was lost to a pause because this did not exist.
    import threading as _thr
    _ckpt: dict[tuple, dict] = {}
    _ckpt_lock = _thr.Lock()
    if checkpoint_path and Path(checkpoint_path).exists():
        _skipped_degraded = 0
        for _line in Path(checkpoint_path).read_text(encoding="utf-8").splitlines():
            try:
                _r = json.loads(_line)
                _res = _r["res"]
                _key = (_r["_task"], _r["_a"], _r["_b"])
                # Under strict re-judge, a record with any errored juror is NOT
                # a valid full-jury verdict: drop it so the battle is re-judged.
                if _redo_degraded and _is_degraded(_res):
                    _ckpt.pop(_key, None)
                    _skipped_degraded += 1
                    continue
                if _redo_contam and _res.get("judge_errors_partial") and not _r.get("_rejudged"):
                    _ckpt.pop(_key, None)
                    _skipped_degraded += 1
                    continue
                _ckpt[_key] = _res
            except Exception:
                continue
        if _ckpt:
            print(f"[checkpoint] loaded {len(_ckpt)} completed battles from {checkpoint_path}"
                  + (f" (skipped {_skipped_degraded} degraded for re-judge)" if _skipped_degraded else ""),
                  flush=True)

    def _run_battle_ckpt(task: str, a: str, b: str) -> dict:
        k = (task, a, b)
        if k in _ckpt:
            return _ckpt[k]
        res = _run_battle(task, a, b)
        # Under strict re-judge, never persist a battle whose jurors errored;
        # leave it unwritten so a later resume re-judges it once the backend
        # recovers. Otherwise persist as before.
        _persist = bool(checkpoint_path) and not (_redo_degraded and _is_degraded(res))
        if _persist:
            _rec = {"_task": task, "_a": a, "_b": b, "res": res}
            if _redo_contam:
                _rec["_rejudged"] = True
            with _ckpt_lock:
                with open(checkpoint_path, "a", encoding="utf-8") as _f:
                    _f.write(json.dumps(_rec) + "\n")
                _ckpt[k] = res
        return res

    # ----- (BUG B3.i) pre-flight judge SMOKE ------------------------- #
    # Run ONE real battle first. If the judge backend is down, that single
    # battle returns a judge error and we ABORT immediately with a clear
    # message instead of burning the whole plan and emitting a flat board.
    smoke_result: dict | None = None
    if plan:
        s0 = plan[0]
        smoke_result = _run_battle_ckpt(s0["task"], s0["agent_a"], s0["agent_b"])
        if abort_on_judge_error and is_judge_error_result(smoke_result):
            raise JudgeErrorAbort(
                "Judge SMOKE battle returned a judge error; aborting before "
                "running the full plan. Fix the judge backend (model / API "
                f"key / endpoint) and retry. Smoke result: {smoke_result!r}",
                error_fraction=1.0,
                sample=smoke_result,
            )

    battles: list[dict] = []
    battle_log: list[dict] = []
    n_judge_errors = 0
    # Pre-compute battle results (optionally in parallel); aggregation below
    # stays sequential and order-preserving.
    _results: list[dict | None] = [None] * len(plan)
    if smoke_result is not None and plan:
        _results[0] = smoke_result
    if battle_workers > 1:
        from concurrent.futures import ThreadPoolExecutor as _BTPE, as_completed as _asc
        with _BTPE(max_workers=battle_workers) as _bex:
            _futs = {
                _bex.submit(_run_battle_ckpt, it["task"], it["agent_a"], it["agent_b"]): idx
                for idx, it in enumerate(plan)
                if _results[idx] is None
            }
            _done_n = 0
            for _f in _asc(_futs):
                _results[_futs[_f]] = _f.result()
                _done_n += 1
                if _done_n % 50 == 0:
                    print(f"[battles] {_done_n}/{len(_futs)} done", flush=True)
    for i, item in enumerate(plan):
        task, a, b = item["task"], item["agent_a"], item["agent_b"]
        # Reuse the smoke result for the first battle instead of paying for it
        # twice.
        res = _results[i] if _results[i] is not None else _run_battle_ckpt(task, a, b)
        judge_errored = is_judge_error_result(res)
        if judge_errored:
            n_judge_errors += 1
        winner = res.get("agent_winner", "tie")
        battles.append({"agent_a": a, "agent_b": b, "winner": winner})
        # In RACE-style reference mode agent_b is always this task's reference
        # (build_battle_plan guarantees it), so record which side is the
        # reference to make the per-agent win-rate-vs-reference auditable.
        task_ref = reference_by_task.get(task) if reference_by_task is not None else None
        # (BUG B3.iii) persist verdicts_raw + any error so a degenerate run is
        # detectable from the saved JSON alone.
        battle_log.append({
            "task": task,
            "agent_a": a,
            "agent_b": b,
            "winner": winner,
            "reference": task_ref,
            "words_a": raw_words.get((a, task)),
            "words_b": raw_words.get((b, task)),
            "verdicts_raw": res.get("verdicts_raw"),
            "error": res.get("error"),
            "judge_error": judge_errored,
        })

    # ----- (BUG B3.ii) judge-error fraction guard -------------------- #
    judge_error_fraction = (n_judge_errors / len(battles)) if battles else 0.0
    if (
        abort_on_judge_error
        and battles
        and judge_error_fraction > judge_error_abort_fraction
    ):
        raise JudgeErrorAbort(
            f"Judge-error fraction {judge_error_fraction:.1%} exceeds the "
            f"{judge_error_abort_fraction:.1%} threshold "
            f"({n_judge_errors}/{len(battles)} battles errored). The board "
            "would collapse toward a flat ~1000 Elo; aborting. Fix the judge "
            "backend and retry.",
            error_fraction=judge_error_fraction,
        )

    # ----- strict re-judge finalize gate ----------------------------- #
    # Refuse to write a final board while ANY battle still has an errored juror
    # (after per-juror retries). The unwritten battles stay in the plan but not
    # in the checkpoint, so a resume re-judges exactly them; the board is only
    # finalized once every battle is a true full-jury verdict.
    if _redo_degraded and n_judge_errors > 0:
        raise JudgeErrorAbort(
            f"JURY_REDO_DEGRADED: {n_judge_errors}/{len(battles)} battle(s) still "
            "have an errored juror after retries; refusing to finalize a board "
            "with phantom-TIE votes. The unpersisted battles will be re-judged on "
            "the next resume once the juror backend is healthy.",
            error_fraction=judge_error_fraction,
        )

    # ----- Bradley-Terry rating --------------------------------------- #
    # (BUG D) The HEADLINE ranking is fit on UNGATED agents only: any battle
    # where either side is gated is dropped, so beating gated junk cannot
    # inflate the headline Elo. We ALSO keep a transparency fit over the FULL
    # battle set (per-agent `quality_elo`, including gated agents) so the JSON
    # still shows where every agent landed; the full battle_log is emitted
    # unfiltered for audit.
    ranked_battles = [
        b for b in battles
        if b["agent_a"] not in gated_set and b["agent_b"] not in gated_set
    ]
    n_battles_dropped_gated = len(battles) - len(ranked_battles)
    ungated_agents = [a for a in included_agents if a not in gated_set]

    def _fit(battle_list: list[dict], agents_scope: list[str]) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        if not battle_list:
            return out
        if bootstrap:
            ci = bt.bootstrap_ci(battle_list)
            for a in agents_scope:
                row = ci.get(a)
                if row:
                    out[a] = {
                        "quality_elo": row["elo"],
                        "ci_lo": row["lo"],
                        "ci_hi": row["hi"],
                        "ci_half_width": row["half_width"],
                    }
        else:
            elo = bt.fit_bradley_terry(battle_list)
            for a in agents_scope:
                if a in elo:
                    out[a] = {"quality_elo": round(elo[a], 1)}
        return out

    # Transparency fit (all battles, all included agents).
    quality = _fit(battles, included_agents)
    # Headline fit (ungated-only battles, ungated agents).
    quality_ranked = _fit(ranked_battles, ungated_agents)

    # ----- RACE-style win-rate vs reference (Arena-Hard) --------------- #
    # Only meaningful in reference-manifest mode. Per agent, win-rate vs the
    # per-task reference is (wins + 0.5 * ties) / decided battles, where a
    # decided battle is one that was NOT a judge error. The reference agent is
    # never scored against itself (build_battle_plan excludes it), so it has no
    # win-rate from the tasks where it is the reference.
    winrate_vs_reference: dict[str, float | None] = {}
    winrate_counts: dict[str, dict[str, int]] = {}
    if reference_by_task is not None:
        # `wr_credit` is the Arena-Hard numerator (full win = 1.0, tie = 0.5);
        # `wr_full_wins` counts ONLY decisive wins so the reported integer
        # `wins` is not polluted by accumulated tie half-credit.
        wr_credit: dict[str, float] = defaultdict(float)
        wr_full_wins: dict[str, int] = defaultdict(int)
        wr_decided: dict[str, int] = defaultdict(int)
        for blog in battle_log:
            if blog.get("judge_error"):
                continue
            a = blog["agent_a"]  # the non-reference contender
            ref = blog.get("reference")
            win = blog["winner"]
            wr_decided[a] += 1
            if win == a:
                wr_credit[a] += 1.0
                wr_full_wins[a] += 1
            elif win == ref:
                wr_credit[a] += 0.0
            else:
                # tie (or any non-decisive verdict): Arena-Hard half credit.
                wr_credit[a] += 0.5
        for a in included_agents:
            dec = wr_decided.get(a, 0)
            winrate_vs_reference[a] = (wr_credit[a] / dec) if dec else None
            winrate_counts[a] = {
                "decided": dec,
                "wins": wr_full_wins.get(a, 0),  # decisive wins only (ties excluded)
            }

    # ----- Assemble per-agent rows + GATE ----------------------------- #
    agent_rows: dict[str, dict[str, Any]] = {}
    n_battles_per_agent: dict[str, int] = defaultdict(int)
    for blog in battle_log:
        n_battles_per_agent[blog["agent_a"]] += 1
        n_battles_per_agent[blog["agent_b"]] += 1

    for a in included_agents:
        g = grounding_mean[a]
        q = quality.get(a, {})
        qr = quality_ranked.get(a, {})
        agent_rows[a] = {
            "agent": a,
            # Full-set Elo (transparency; includes gated agents).
            "quality_elo": q.get("quality_elo"),
            "quality_ci": (
                {"lo": q["ci_lo"], "hi": q["ci_hi"], "half_width": q["ci_half_width"]}
                if "ci_lo" in q else None
            ),
            # HEADLINE Elo: ungated-only fit, NOT inflated by beating gated
            # junk (BUG D). None for gated agents (not fit) and for ungated
            # agents that had no ungated opponent.
            "quality_elo_ranked": qr.get("quality_elo"),
            "quality_ci_ranked": (
                {"lo": qr["ci_lo"], "hi": qr["ci_hi"], "half_width": qr["ci_half_width"]}
                if "ci_lo" in qr else None
            ),
            "grounding": round(g, 4),
            "gated": bool(g < grounding_floor),
            "n_tasks": len(per_agent_tasks.get(a, set())),
            "n_battles": n_battles_per_agent.get(a, 0),
            # RACE-style reference-anchored quality (None in round-robin mode).
            # In reference mode this is the headline quality number per the
            # redesign: win-rate vs the per-task reference report.
            "winrate_vs_reference": (
                round(winrate_vs_reference[a], 4)
                if winrate_vs_reference.get(a) is not None else None
            ),
            "winrate_counts": winrate_counts.get(a) if reference_by_task is not None else None,
            # True if this agent served as a reference on at least one task (and
            # so was excluded from being scored against itself there).
            "is_reference": bool(a in reference_agents),
        }

    # Ranked views. Headline ranking is over UNGATED agents, ordered by the
    # ungated-only Elo when available, falling back to the full-set Elo for an
    # ungated agent that had no ungated opponent (so it is not silently
    # dropped from the board).
    def _headline_elo(r: dict) -> float | None:
        if r["quality_elo_ranked"] is not None:
            return r["quality_elo_ranked"]
        return r["quality_elo"]

    by_quality = sorted(
        [r for r in agent_rows.values() if not r["gated"] and _headline_elo(r) is not None],
        key=lambda r: -_headline_elo(r),
    )
    by_grounding = sorted(agent_rows.values(), key=lambda r: -r["grounding"])

    # RACE-style headline ranking (reference mode only): UNGATED, non-reference
    # agents that have a win-rate vs the reference, ordered by that win-rate.
    by_winrate: list[dict] = []
    if reference_by_task is not None:
        by_winrate = sorted(
            [
                r for r in agent_rows.values()
                if not r["gated"] and r.get("winrate_vs_reference") is not None
            ],
            key=lambda r: -r["winrate_vs_reference"],
        )

    summary["n_judge_errors"] = n_judge_errors
    summary["judge_error_fraction"] = round(judge_error_fraction, 4)
    summary["n_battles_dropped_gated"] = n_battles_dropped_gated
    summary["n_ranked_battles"] = len(ranked_battles)

    return {
        "synthetic_placeholder": False,
        "source": "real",
        "mode": "real",
        "quality_mode": quality_mode,
        "summary": summary,
        "agents": agent_rows,
        "ranked_by_quality_elo_gated": [r["agent"] for r in by_quality],
        "ranked_by_grounding": [r["agent"] for r in by_grounding],
        # RACE-style reference-anchored ranking (empty list in round-robin mode).
        "ranked_by_winrate_vs_reference": [r["agent"] for r in by_winrate],
        "battle_log": battle_log,
        "n_battles": len(battles),
        # Headline Elo is fit on UNGATED battles only (BUG D); the full
        # battle_log above is unfiltered for audit.
        "n_ranked_battles": len(ranked_battles),
        "n_battles_dropped_gated": n_battles_dropped_gated,
        "n_judge_errors": n_judge_errors,
        "judge_error_fraction": round(judge_error_fraction, 4),
        "grounding_missing": grounding_missing,
        "invalid_runs": invalid_runs,
    }


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit-tasks", type=int, default=None)
    p.add_argument("--limit-agents", type=int, default=None)
    p.add_argument("--agents", type=str, default=None, help="comma-separated agent allowlist")
    p.add_argument("--reference", type=str, default=None, help="fixed reference agent for pairwise (default round-robin)")
    p.add_argument(
        "--reference-manifest",
        type=str,
        default=None,
        help=(
            "path to a per-task reference manifest "
            "(data/reference_reports/manifest.json from select_reference_reports.py). "
            "RACE-style: each non-reference agent is judged vs that task's reference; "
            "per-agent quality is win-rate vs reference. Takes precedence over --reference."
        ),
    )
    p.add_argument("--grounding-floor", type=float, default=DEFAULT_GROUNDING_FLOOR)
    p.add_argument("--word-budget", type=int, default=DEFAULT_WORD_BUDGET)
    p.add_argument("--model", type=str, default=DEFAULT_MODEL)
    p.add_argument("--judges", type=str, default=None, help="comma-separated jury models (PoLL); overrides --model")
    p.add_argument("--battle-workers", type=int, default=1, help="concurrent battles")
    p.add_argument("--no-checkpoint", action="store_true", help="disable battle-level checkpointing")
    p.add_argument("--n-samples", type=int, default=3)
    p.add_argument("--no-bootstrap", action="store_true")
    p.add_argument(
        "--no-judge-error-abort",
        action="store_true",
        help="do NOT abort on judge errors; flag loudly but keep the (degenerate) board",
    )
    p.add_argument(
        "--judge-error-abort-fraction",
        type=float,
        default=JUDGE_ERROR_ABORT_FRACTION,
        help="abort if more than this fraction of battles are judge errors (default 0.05)",
    )
    p.add_argument("--dry-run", action="store_true", help="build work list + count battles; NO judge calls")
    p.add_argument("--report-dir", type=str, default=str(DEFAULT_REPORT_DIR))
    p.add_argument("--score-dir", type=str, default=str(DEFAULT_SCORE_DIR))
    p.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    return p.parse_args(argv)


def _print_summary(result: dict) -> None:
    s = result["summary"]
    print("=" * 64)
    print(f"REAL leaderboard build [{result['mode']}]  source={result['source']}  synthetic={result['synthetic_placeholder']}")
    print("=" * 64)
    print(f"Agents included ({len(s['agents_included'])}): {', '.join(s['agents_included']) or '(none)'}")
    if s["agents_skipped"]:
        print("Agents skipped (NOT fabricated):")
        for sk in s["agents_skipped"]:
            print(f"  - {sk['agent']}: {sk['reason']}")
    else:
        print("Agents skipped: (none)")
    inv = result.get("invalid_runs") or []
    if inv:
        print(f"Invalid-capture runs excluded (NOT ranked, NOT a low score): {len(inv)}")
        for ir in inv[:20]:
            print(f"  - {ir['agent']}__{ir['task']}: {ir['reason']}")
    print(f"Tasks: {s['n_tasks']}   Reference: {s['reference']}")
    qmode = s.get("quality_mode")
    if qmode:
        print(f"Quality mode: {qmode}")
    if qmode == "reference_manifest":
        print(f"Reference agents (per-task): {', '.join(s.get('reference_agents') or []) or '(none)'}")
        rbt = s.get("reference_by_task") or {}
        for task in sorted(rbt):
            print(f"  - {task} -> {rbt[task]}")
        rst = s.get("reference_skipped_tasks") or []
        if rst:
            print(f"Reference tasks skipped (NOT used): {len(rst)}")
            for r in rst[:20]:
                print(f"  - {r['task']}: {r['reason']}")
    print(f"Battles planned: {s['n_battles_planned']}   Word budget: {s['word_budget']}")
    print(f"Grounding floor: {s['grounding_floor']}   Grounding source: {s['grounding_score_source']}")
    print(f"Grounding formula: {s.get('composite_formula')}")
    gm = result.get("grounding_mean")
    if gm is not None:
        print("Grounding (mean) per agent:")
        for a in s["agents_included"]:
            print(f"  - {a}: {gm.get(a)}")
    if result["mode"] != "dry-run":
        print(f"Battles run: {result.get('n_battles')}")
        nje = result.get("n_judge_errors", 0)
        frac = result.get("judge_error_fraction", 0.0)
        if nje:
            print(f"WARNING: judge errors in {nje} battles ({frac:.1%}); board may be degraded.")
        print(f"Battles dropped (gated side): {result.get('n_battles_dropped_gated')}   "
              f"Ranked (ungated) battles: {result.get('n_ranked_battles')}")
        print("Ranked by quality_elo (gated):", result.get("ranked_by_quality_elo_gated"))
        print("Ranked by grounding:", result.get("ranked_by_grounding"))
        if result.get("quality_mode") == "reference_manifest":
            print("Ranked by win-rate vs reference:", result.get("ranked_by_winrate_vs_reference"))
            for a in result.get("ranked_by_winrate_vs_reference") or []:
                row = result["agents"][a]
                print(f"  - {a}: {row.get('winrate_vs_reference')} "
                      f"({row.get('winrate_counts')})")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    agents_filter = [a.strip() for a in args.agents.split(",") if a.strip()] if args.agents else None
    try:
        result = build(
            report_dir=Path(args.report_dir),
            score_dir=Path(args.score_dir),
            limit_tasks=args.limit_tasks,
            limit_agents=args.limit_agents,
            agents_filter=agents_filter,
            reference=args.reference,
            reference_manifest=args.reference_manifest,
            grounding_floor=args.grounding_floor,
            word_budget=args.word_budget,
            model=args.model,
            dry_run=args.dry_run,
            n_samples=args.n_samples,
            bootstrap=not args.no_bootstrap,
            abort_on_judge_error=not args.no_judge_error_abort,
            judge_error_abort_fraction=args.judge_error_abort_fraction,
            judges=[j.strip() for j in args.judges.split(",") if j.strip()] if args.judges else None,
            battle_workers=args.battle_workers,
            checkpoint_path=None if args.no_checkpoint else Path(args.out + ".battles.jsonl"),
        )
    except JudgeErrorAbort as exc:
        print("=" * 64)
        print("ABORTED: judge backend is failing; refusing to write a flat board.")
        print(str(exc))
        print("=" * 64)
        return 2
    _print_summary(result)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
