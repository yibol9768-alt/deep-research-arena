#!/usr/bin/env python3
"""Five-axis truth board builder (EXECUTION_PLAN P5; #16 code side).

Consumes the v2 decidable stack end to end:
  governed run dir (<run-set>/<backbone>/raw/*.meta.json) x answer keys
  x URL registry x page cache
  -> per-report five-axis scores -> per-agent aggregate -> board JSON.

Ranking = macro-mean truth (decidable axes only). Presentation (the LLM
panel, when a results file is supplied) is a SEPARATE column: it may only
order agents whose truth scores tie within --tie-eps, and never enters the
truth number (M-C1). Per M-M1 the board carries macro, micro and
min_report_truth for every agent.

Usage (formal, default):
  python3 scripts/build_truth_board.py --run-dir <run-set>/<backbone> \
      --replicates 3 \
      [--keys-dir data/golden/answer_keys] [--cache sandbox_cache.json] \
      [--panel panel_results.json] [--gamma 1.5] [--out board.json]

Legacy nested report trees remain readable only behind both
``--reports-dir`` and ``--legacy-nested-layout``.  Formal and legacy layouts
are mutually exclusive and are never pooled into one board.

The live v1 leaderboard pipeline (build_real_leaderboard.py) stays untouched
until the re-judge lands; this builder is the v2 replacement, validated on
the sample tasks first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.answer_key import AnswerKey                     # noqa: E402
from src.eval import decidable_scorer as ds                   # noqa: E402
from src.eval.closed_world_eval import evaluate, load_registry  # noqa: E402
from src.eval.report_stubs import is_stub as is_stub_report       # noqa: E402

def _board_axes(pof_semantics: str) -> tuple:
    """The board's axis-key set under this pof semantics. The grounding-fidelity
    axis is named by ds._axis_key: a text_v1 board carries
    ``grounding_quote_support`` (it observed no fetch), a transport_v2 board
    carries ``grounding_proof_of_fetch`` (it did). The two names must never
    co-occur in one board; rc=3 (mixed semantics) and the coexistence assertion
    below enforce that."""
    return ("grounding_reach", ds._axis_key(pof_semantics),
            "correctness_fact_support", "completeness", "spec")


def _axes_mean(cells, axis_keys, denom) -> dict:
    """Per-axis mean over ``cells`` (evaluate() outputs carrying "axes").

    ``.get(a, 0.0)`` and not ``[a]``: when one lane MIXES pof semantics its
    reports carry different grounding-axis keys (grounding_proof_of_fetch vs
    grounding_quote_support), and indexing the FIRST report's key set into every
    other report used to raise a bare KeyError here, before the rc=3
    mixed-semantics gate could refuse the board with its machine-readable
    reason (SPEC_ISSUES G6: a rejected board must exit rc=3, never crash). On a
    well-formed single-semantics board every report carries every key, so the
    numbers are unchanged there; a mixed lane now survives to the rc=3 refusal.
    """
    return {
        a: round(math.fsum(d["axes"].get(a, 0.0) for d in cells) / denom, 4)
        for a in axis_keys
    }

# D7: version stamp so a board can self-certify which scoring/extractor/formula
# it was produced under. The three headline fields (formula_version,
# extractor_commit, formula_commit) are the cross-version identity; the numeric
# knobs (gamma/weights/eps_floor/floor_mode/pof_threshold) are read straight
# from the live scorer constants so the stamp can never drift from the code that
# produced the numbers. Boards carrying different formula_version are NOT
# comparable (FORMULA_LOCK: "跨版本禁比").
FORMULA_VERSION = "tv2.4-provenance-gate-factscope-forum-attribution"
EXTRACTOR_COMMIT = "46e716e3+63d220b3+answer_keys_b636b149"
FORMULA_COMMIT = "ca7a7c7e+factscope_forum_attribution_locality"


def _task_set_hash(task_ids) -> str:
    """Deterministic short hash of the scored task-id set (order-independent)."""
    import hashlib
    joined = ",".join(sorted(task_ids)).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()[:16]


def _protocols(gamma: float, task_ids, pof_semantics: str = "text_v1",
               gate_semantics: str = "reach_v1") -> dict:
    """The board's version stamp. floor_mode/eps_floor are derived from the live
    ds.EPS_FLOOR so a future re-enabling of the floor is reflected automatically.
    """
    eps = ds.EPS_FLOOR
    return {
        "formula_version": FORMULA_VERSION,
        "extractor_commit": EXTRACTOR_COMMIT,
        "formula_commit": FORMULA_COMMIT,
        "gamma": gamma,
        "weights": dict(ds.QUALITY_WEIGHTS),
        "eps_floor": eps,
        "floor_mode": "none" if eps <= 0.0 else "floor_if_active",
        "spec_in_truth": False,
        "pof_threshold": ds.POF_THRESHOLD_DEFAULT,
        "pof_semantics": pof_semantics,
        "gate_semantics": gate_semantics,
        "gate_axis": ("transport provenance" if gate_semantics == "provenance_v2"
                      else "grounding_reach"),
        # The axis key these rows carry, so a reader never has to guess whether
        # the grounding column is a proof-of-fetch or a quote-support column.
        "grounding_axis": ds._axis_key(pof_semantics),
        "grounding_axis_note": (
            "grounding_quote_support (text_v1) is a verbatim lexical lower bound "
            "against an evaluator-fetched copy; it does not observe whether the "
            "agent opened anything. It is NOT citation support: paraphrase is "
            "missed and the miss rate is unmeasured (task #56). "
            "grounding_proof_of_fetch (transport_v2) is the only name that "
            "witnesses a fetch."),
        "pof_semantics_note": (
            "transport_v2 = |cited & fetched| / |cited|, from the run's shim "
            "evidence log. text_v1 = page-level any-occurrence verbatim match "
            "against an evaluator-fetched copy; it cannot see whether the agent "
            "opened anything. Boards with different pof_semantics are NOT "
            "comparable."),
        "citation_styles": sorted(ds.POF_EVIDENCE_STYLES),
        "judge_model": "n/a (decidable, model-free)",
        "task_set_hash": _task_set_hash(task_ids),
        "n_tasks_scored": len(set(task_ids)),
        # Which sandbox sources can move `truth`. Fact credit is restricted to
        # task-ranked shopping products. Completeness combines the ranked
        # shopping/wiki pool with one virtual forum slot for tasks that declare
        # community sources. Reach and PoF remain source-agnostic.
        "sources_scored": {
            "reach": ["shopping", "forum", "wiki"],
            "proof_of_fetch": ["shopping", "forum", "wiki"],
            "correctness_fact_support": ["shopping"],
            "completeness": ["shopping", "wiki", "forum"],
        },
        "sources_note": (
            "A task that declares forums contributes one virtual completeness "
            "slot. It requires an inline citation to an allowed, lexically "
            "task-relevant thread plus quote support; when transport evidence "
            "is available that thread must also have been fetched. Structured "
            "Shopping fact credit requires the product citation in the same "
            "sentence or table row as the claim. Structured completeness requires its "
            "source citation on the same Markdown line as the subject/value; a "
            "detached source dump cannot unlock credit. Under transport, each "
            "credited source page must also have been fetched."),
    }


def _declared_lanes() -> set[str]:
    """Lanes `config/lane_protocol.yaml` governs. Empty when the file is absent."""
    try:
        import yaml
        doc = yaml.safe_load((ROOT / "config" / "lane_protocol.yaml").read_text(
            encoding="utf-8")) or {}
        return set((doc.get("lanes") or {}).keys())
    except Exception:  # noqa: BLE001
        return set()


def _merge_evidence_fragments(items):
    """Merge shim and owned-egress fragments for exactly one ``run_id``.

    Each recorder owns a complete bracket.  A missing/invalid bracket in either
    fragment poisons the merged run rather than letting the healthy recorder
    hide evidence loss.  URL sets are unions and a successful fetch is sticky
    across recorders and retries.  This is the transport analogue of a database
    join: run/lane/task/backbone/worker must agree before any traffic is pooled.
    """
    from src.eval.fetch_log import RunEvidence, linked_urls

    fragments = [(p, ev) for p, ev in items]
    merged = RunEvidence()
    if not fragments:
        merged.unavailable_reason = "no evidence fragments"
        return merged
    if len(fragments) > 1:
        required = ("run_id", "lane", "task", "backbone", "worker")
        missing = [
            f"{path}:{field}"
            for path, ev in fragments
            for field in required
            if getattr(ev, field) is None
        ]
        if missing:
            merged.unavailable_reason = (
                "multi-recorder evidence lacks attribution field(s): "
                + ", ".join(missing)
            )
            return merged
    identity_fields = ("run_id", "lane", "task", "backbone", "worker")
    for field in identity_fields:
        values = {getattr(ev, field) for _, ev in fragments
                  if getattr(ev, field) is not None}
        if len(values) > 1:
            merged.unavailable_reason = (
                f"evidence fragments disagree on {field}: {sorted(map(str, values))}"
            )
            return merged
        setattr(merged, field, next(iter(values), None))
    if not merged.run_id:
        merged.unavailable_reason = "evidence fragments carry no run_id"
        return merged
    bad = [(str(p), ev.unavailable_reason or "invalid bracket")
           for p, ev in fragments if not ev.available]
    if bad:
        merged.unavailable_reason = "invalid evidence fragment(s): " + "; ".join(
            f"{path}: {why}" for path, why in bad
        )
        return merged
    observability = {ev.fetch_observable for _, ev in fragments}
    if len(observability) != 1:
        merged.unavailable_reason = (
            "evidence fragments disagree on fetch_observable"
        )
        return merged
    merged.fetch_observable = next(iter(observability))
    merged.t_start = min(ev.t_start for _, ev in fragments if ev.t_start is not None)
    merged.t_end = max(ev.t_end for _, ev in fragments if ev.t_end is not None)
    merged.unattributed_in_window = sum(ev.unattributed_in_window
                                        for _, ev in fragments)
    merged.unattributed_ambiguous = sum(ev.unattributed_ambiguous
                                        for _, ev in fragments)
    merged.write_errors = sum(ev.write_errors for _, ev in fragments)
    unique_searches = {
        json.dumps(rec, sort_keys=True, separators=(",", ":")): rec
        for _, ev in fragments for rec in ev.searches
    }
    merged.searches = sorted(
        unique_searches.values(),
        key=lambda rec: (float(rec.get("ts") or 0), json.dumps(rec, sort_keys=True)),
    )
    for _, ev in fragments:
        merged.search_returned.update(ev.search_returned)
        merged.blocked.extend(ev.blocked)
    merged.blocked = list({
        json.dumps(rec, sort_keys=True, separators=(",", ":")): rec
        for rec in merged.blocked
    }.values())

    records_by_url: dict[str, list[dict]] = {}
    recovered_links: set[str] = set()
    for path, ev in fragments:
        for url, rec in ev.fetched.items():
            records_by_url.setdefault(url, []).append(rec)

        # Old recorder versions omitted the parsed ``links`` list. Recover it
        # from this fragment's own content-addressed blob store now, before the
        # two evidence roots are joined. A process-global SHIM_EVIDENCE_DIR can
        # name only one root and would silently lose the other recorder's links.
        def load_blob(digest: str, root=path.parent):
            try:
                return (root / "blobs" / digest).read_bytes()
            except OSError:
                return None

        recovered_links.update(linked_urls(ev, load_blob))

    for url, records in records_by_url.items():
        successful = [r for r in records if int(r.get("status") or 0) == 200]
        candidates = successful or records
        chosen = max(candidates, key=lambda r: float(r.get("ts") or 0))
        chosen = dict(chosen)
        stored_links = {
            str(link) for rec in successful
            for link in (rec.get("links") or []) if link
        }
        if stored_links:
            chosen["links"] = sorted(stored_links)
        merged.fetched[url] = chosen
    if recovered_links and merged.fetched:
        first = sorted(merged.fetched)[0]
        rec = dict(merged.fetched[first])
        rec["links"] = sorted(set(rec.get("links") or []) | recovered_links)
        merged.fetched[first] = rec
    merged.available = True
    return merged


def _index_evidence(evidence_dirs: Path | Iterable[Path]):
    """Index and merge one or more recursively scanned evidence roots.

    Formal runs write shim traffic under ``evidence/worker-N`` and direct-page
    traffic under ``evidence/egress-worker-N``.  Both carry the same ``run_id``
    and both are needed for PoF.  Filenames and glob order never determine
    ownership; the bracket records do, and duplicate paths from overlapping
    ``--evidence-dir`` arguments are de-duplicated before loading.
    """
    from src.eval.fetch_log import load_run_evidence

    roots = ([evidence_dirs] if isinstance(evidence_dirs, Path)
             else list(evidence_dirs))
    paths: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            if path.stem.startswith("_"):
                continue
            paths[str(path.resolve())] = path
    fragments_by_run: dict[str, list[tuple[Path, object]]] = {}
    for path in sorted(paths.values(), key=lambda p: str(p.resolve())):
        ev = load_run_evidence(path)
        if ev.run_id:
            fragments_by_run.setdefault(ev.run_id, []).append((path, ev))

    by_key: dict[tuple[str, str], object] = {}
    by_run: dict[str, object] = {}
    for run_id in sorted(fragments_by_run):
        ev = _merge_evidence_fragments(fragments_by_run[run_id])
        by_run[run_id] = ev
        if not (ev.available and ev.lane and ev.task):
            continue
        key = (ev.lane, ev.task)
        prior = by_key.get(key)
        if prior is not None and getattr(prior, "backbone", None) != ev.backbone:
            raise ValueError(
                f"evidence collision on {key}: backbones "
                f"{getattr(prior, 'backbone', None)!r} and {ev.backbone!r} share "
                "one evidence root. Use one governed backbone run-dir per board."
            )
        if prior is None or (ev.t_end or 0) >= (getattr(prior, "t_end", 0) or 0):
            by_key[key] = ev
    return by_key, by_run


def _run_status(agent_dir: Path, task_id: str, meta_dir: Path | None = None,
                backbone: str | None = None) -> dict:
    """Why is there no report for this (agent, task)?

    `run_deep_task` deliberately writes no `.md` when the watchdog kills a run,
    so a stalled task stays rerunnable and cannot be mistaken for a framework
    that genuinely produced nothing. The distinction lives in the meta sidecar.
    An absent sidecar means the run never started or never reported, which is a
    delivery failure and scores 0.

    The sidecar is not where this function used to look. `run_deep_task` writes
    it FLAT, as `<out>/<agent>__<task><suffix>.meta.json` (:2227), while the
    board reads a nested `<agent>/<task>.md` tree. Nothing ever staged the
    sidecars into that tree, so `_run_status` returned `{}` for every stalled
    run and the whole rerun policy -- `--max-stall-reruns`, `rc=4` stall debt,
    `n_stalled_after_reruns` -- was unreachable code. An infrastructure kill was
    silently scored as a lane that delivered nothing: exactly the conflation the
    policy exists to prevent.

    So look in the nested tree first, then for the flat sibling, then in
    `--meta-dir`. The suffix (`_matrix`) is part of the written filename and is
    not in `task_id`, hence the glob.
    """
    for name in (f"{task_id}.meta.json", f"{task_id}.status.json"):
        p = agent_dir / name
        if p.exists():
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
                if backbone and meta.get("backbone") not in (None, backbone):
                    continue
                return meta
            except Exception:
                return {}

    roots = [agent_dir.parent]
    if meta_dir is not None:
        roots.append(meta_dir)
    # `<agent>__<task><suffix>.meta.json`. The suffix, when present, starts with
    # `_` (e.g. `_matrix`, `_smoke`). Anchoring on that stops `t1` from claiming
    # `t10`'s sidecar, which a bare `{task_id}*` glob would happily do.
    #
    # The filename carries NO backbone, so one meta-dir holding two backbones (or
    # two out-suffixes) offers several sidecars for the same (agent, task). Taking
    # the first in sorted order would let rc=4, rc=6 and the run_id used to pin
    # transport evidence read another run's meta. `backbone` disambiguates; when
    # it cannot, this fails loud rather than picking one.
    prefix = f"{agent_dir.name}__{task_id}"
    found: list[dict] = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.glob(f"{prefix}*.meta.json")):
            tail = p.name[len(prefix):-len(".meta.json")]
            if tail and not tail.startswith("_"):
                continue
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if backbone and meta.get("backbone") not in (None, backbone):
                continue
            found.append(meta)
        if found:
            break     # nearer root wins, as before

    if not found:
        return {}
    if len(found) > 1:
        seen = {(m.get("backbone"), m.get("run_id")) for m in found}
        if len(seen) > 1:
            raise ValueError(
                f"{len(found)} sidecars match {prefix}*.meta.json "
                f"({sorted(str(x) for x in seen)}). The filename carries no "
                "backbone, so the board cannot tell which run wrote this report. "
                "Pass --backbone, or use one --meta-dir per backbone.")
    return found[0]


def _report_seal_error(report_path: Path, meta: dict, *,
                       require_legacy_seal: bool) -> str | None:
    """Return why a report cannot be bound to its producing run.

    Every current run carries ``run_id`` and a sha256/length seal.  Missing
    seals are allowed only for genuinely legacy metadata and only behind the
    explicit CLI opt-out.  A present seal is always enforced: an opt-out for old
    data must never become permission to score a known mismatch.
    """
    seal = meta.get("report_seal") if isinstance(meta, dict) else None
    is_current_run = bool((meta or {}).get("run_id"))
    if not isinstance(seal, dict) or not seal.get("sha256"):
        if is_current_run or require_legacy_seal:
            return "report seal missing"
        return None
    try:
        raw = report_path.read_bytes()
    except OSError as exc:
        return f"report unreadable: {exc}"
    got = hashlib.sha256(raw).hexdigest()
    want = seal.get("sha256")
    if not (isinstance(want, str) and len(want) == 64):
        return "report seal sha256 is malformed"
    if got != want:
        return f"report seal mismatch (sealed={want}, actual={got})"
    if seal.get("n_bytes") != len(raw):
        return (f"report seal byte length mismatch (sealed={seal.get('n_bytes')}, "
                f"actual={len(raw)})")
    return None


@dataclass(frozen=True)
class _FormalCell:
    agent: str
    task: str
    backbone: str
    run_set_id: str
    replicate: int
    status: str
    meta_path: Path
    report_path: Path | None
    meta: dict
    manifest_path: Path


def _discover_formal_cells(
    run_dir: Path,
    *,
    replicates: int,
) -> tuple[dict[tuple[str, str, int], _FormalCell], set[Path]]:
    """Read governed flat artifacts using metadata bindings as identity.

    A same-stem ``.md`` is only the physical payload paired with a sidecar.  Its
    lane, task and replicate are never parsed from the filename.  Those values
    come from the signed binding and must exactly match the metadata fields,
    manifest, run-set directory and backbone directory.
    """
    from scripts.verify_run_set import (
        INTEGRITY_VERSION,
        RUN_STATUSES,
        IntegrityError,
        validate_entry,
        validate_outcome,
    )

    if replicates < 1:
        raise ValueError("--replicates must be >= 1")
    run_dir = run_dir.resolve()
    raw_dir = run_dir / "raw"
    if not raw_dir.is_dir():
        raise ValueError(f"formal run dir has no raw/ directory: {run_dir}")
    run_set_id = run_dir.parent.name
    backbone = run_dir.name
    manifests = {p.name: p for p in run_dir.glob("run_manifest*.json")}
    if not manifests:
        raise ValueError(f"formal run dir has no run_manifest*.json: {run_dir}")

    cells: dict[tuple[str, str, int], _FormalCell] = {}
    used_manifests: set[Path] = set()
    paired_reports: set[Path] = set()
    for meta_path in sorted(raw_dir.glob("*.meta.json"), key=lambda p: p.name):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"{meta_path}: unreadable metadata: {type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(meta, dict):
            raise ValueError(f"{meta_path}: metadata root must be an object")
        status = meta.get("status")
        if status not in RUN_STATUSES:
            raise ValueError(f"{meta_path}: unknown status {status!r}")
        binding_key = "run_set_binding" if status == "pass" else "outcome_binding"
        binding = meta.get(binding_key)
        if not isinstance(binding, dict):
            raise ValueError(f"{meta_path}: formal {binding_key} is missing")
        agent = meta.get("agent")
        task = meta.get("task")
        replicate = binding.get("replicate")
        if not isinstance(agent, str) or not agent:
            raise ValueError(f"{meta_path}: agent is missing")
        if not isinstance(task, str) or not task:
            raise ValueError(f"{meta_path}: task is missing")
        if not isinstance(replicate, int) or not (1 <= replicate <= replicates):
            raise ValueError(
                f"{meta_path}: replicate={replicate!r} falls outside 1..{replicates}"
            )
        wanted_binding = {
            "integrity_version": INTEGRITY_VERSION,
            "run_set_id": run_set_id,
            "backbone": backbone,
            "replicate": replicate,
            "agent": agent,
            "task": task,
        }
        bad_binding = {
            field: (binding.get(field), wanted)
            for field, wanted in wanted_binding.items()
            if binding.get(field) != wanted
        }
        if bad_binding:
            raise ValueError(f"{meta_path}: formal binding mismatch: {bad_binding}")
        manifest_name = binding.get("manifest_file")
        manifest_path = manifests.get(str(manifest_name))
        if manifest_path is None:
            raise ValueError(
                f"{meta_path}: bound manifest {manifest_name!r} is absent"
            )
        report_file = binding.get("report_file")
        if report_file is not None and (
            not isinstance(report_file, str) or Path(report_file).name != report_file
        ):
            raise ValueError(f"{meta_path}: unsafe bound report filename")
        report_path = (
            raw_dir / report_file
            if report_file is not None
            else meta_path.with_name(
                meta_path.name[: -len(".meta.json")] + ".md"
            )
        )
        try:
            if status == "pass":
                validate_entry(
                    report_path,
                    meta_path,
                    manifest_path,
                    run_set_id=run_set_id,
                    backbone=backbone,
                    replicate=replicate,
                    agent=agent,
                    task=task,
                    require_binding=True,
                )
                paired_reports.add(report_path)
                payload: Path | None = report_path
            else:
                validate_outcome(
                    meta_path,
                    manifest_path,
                    run_set_id=run_set_id,
                    backbone=backbone,
                    replicate=replicate,
                    agent=agent,
                    task=task,
                    require_binding=True,
                )
                if report_path.exists():
                    paired_reports.add(report_path)
                payload = None
        except IntegrityError as exc:
            raise ValueError(str(exc)) from exc
        key = (agent, task, replicate)
        if key in cells:
            raise ValueError(
                f"duplicate governed cell {key}: {cells[key].meta_path}, {meta_path}"
            )
        cells[key] = _FormalCell(
            agent=agent,
            task=task,
            backbone=backbone,
            run_set_id=run_set_id,
            replicate=replicate,
            status=status,
            meta_path=meta_path,
            report_path=payload,
            meta=meta,
            manifest_path=manifest_path,
        )
        used_manifests.add(manifest_path)

    run_id_owners: dict[str, list[tuple[str, str, int]]] = {}
    for key, cell in cells.items():
        run_id = cell.meta.get("run_id")
        if isinstance(run_id, str) and run_id:
            run_id_owners.setdefault(run_id, []).append(key)
    duplicates = {
        run_id: owners for run_id, owners in run_id_owners.items()
        if len(owners) > 1
    }
    if duplicates:
        run_id, owners = sorted(duplicates.items())[0]
        raise ValueError(
            f"run_id {run_id!r} is bound to multiple task/replicate cells: "
            f"{sorted(owners)}"
        )

    orphan_reports = sorted(set(raw_dir.glob("*.md")) - paired_reports)
    if orphan_reports:
        raise ValueError(
            "formal raw directory contains report(s) without a bound pass meta: "
            + ", ".join(str(p) for p in orphan_reports[:8])
        )
    return cells, (used_manifests or set(manifests.values()))


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _cluster_bootstrap_ci(
    per_task_replicates: dict[str, list[float]],
    *,
    samples: int,
    seed: int,
) -> tuple[float, float]:
    """Bootstrap tasks as clusters, keeping all replicates inside each draw."""
    if samples < 1:
        raise ValueError("bootstrap samples must be >= 1")
    clusters = [
        math.fsum(sorted(per_task_replicates[task])) / len(per_task_replicates[task])
        for task in sorted(per_task_replicates)
    ]
    if not clusters:
        return 0.0, 0.0
    rng = random.Random(seed)
    n = len(clusters)
    draws = [
        math.fsum(clusters[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(samples)
    ]
    return _percentile(draws, 0.025), _percentile(draws, 0.975)


def _load_lane_info(manifest_path: Path) -> dict[str, dict]:
    """Derive per-agent lane-failure accounting from an extraction manifest.

    A lane fails when the runs that never produced a real report (stub reports
    plus runs missing versus the fullest lane) exceed half of that lane's total
    runs. ``n_runs_total`` is the agent's own attempted-run count; ``n_missing``
    counts tasks it never even recorded, measured against the most complete
    lane in the manifest. Neither number touches the truth score: it only tells
    the board that a 0.0 (or an absent agent) is a broken pipe, not a real zero.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    agents = manifest.get("agents", {})
    expected = max((a.get("n_records", 0) for a in agents.values()), default=0)
    info: dict[str, dict] = {}
    for agent, a in agents.items():
        n_records = a.get("n_records", 0)
        n_stub = sum(a.get("n_stubs_by_class", {}).values())
        n_missing = max(0, expected - n_records)
        lane_failed = (n_stub + n_missing) > (n_records / 2) if n_records else True
        info[agent] = {
            "n_runs_total": n_records,
            "n_stub_reports": n_stub,
            "n_missing_runs": n_missing,
            "lane_failed": lane_failed,
        }
    return info


def load_panel(path: str | None) -> tuple[dict, dict | None]:
    """Load the --panel file and split out its provenance stamp.

    The presentation panel was the ONLY board input with zero provenance
    binding: any {agent: float} json reordered tie-broken ranks and board.json
    recorded nothing (SPEC_ISSUES §2). run_usefulness_jury.panel_from_fit now
    stamps a reserved "_provenance" key (protocol / rubric_hash / word_budget /
    backbone); this pops it so agent lookups are unaffected and returns it for
    publication as `panel_provenance`. An unstamped panel is still accepted --
    refusing is a maintainer call -- but it is called out loudly and the board
    records `{"unstamped": true}` so the omission is disclosed, not silent.
    """
    if not path:
        return {}, None
    panel = json.loads(Path(path).read_text())
    if not isinstance(panel, dict):
        raise SystemExit(f"--panel {path}: expected a JSON object")
    prov = panel.pop("_provenance", None)
    if isinstance(prov, dict) and prov.get("rubric_hash"):
        prov = dict(prov, source_file=str(path))
        return panel, prov
    print(
        f"WARNING: --panel {path} carries no _provenance stamp; the board "
        "will record panel_provenance={'unstamped': true}. Regenerate it with "
        "run_usefulness_jury.py --fit --panel-out.",
        file=sys.stderr,
    )
    return panel, {"unstamped": True, "source_file": str(path)}


def main() -> int:
    ap = argparse.ArgumentParser()
    layout = ap.add_mutually_exclusive_group(required=True)
    layout.add_argument(
        "--run-dir",
        help=("governed <run-set>/<backbone> directory containing raw/, "
              "run_manifest*.json and evidence/. This is the formal layout."),
    )
    layout.add_argument(
        "--reports-dir",
        help="legacy nested layout <agent>/<task_id>.md",
    )
    ap.add_argument(
        "--run-plan",
        default=None,
        help="immutable formal run plan (default: <run-dir>/run_plan.json)",
    )
    ap.add_argument(
        "--require-run-plan",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=("require the immutable plan to prove expected lanes, tasks, "
              "replicates and manifest seal. Formal default on."),
    )
    ap.add_argument(
        "--legacy-nested-layout",
        action="store_true",
        help=("explicitly opt out of governed run-set/replicate binding and read "
              "--reports-dir. Never allowed with --run-dir."),
    )
    ap.add_argument(
        "--replicates",
        type=int,
        default=None,
        help=("planned replicates per task. Required for --run-dir so a wholly "
              "missing replicate is still an explicit zero."),
    )
    ap.add_argument(
        "--agents",
        action="append",
        default=[],
        help=("expected lane name (repeatable or comma-separated). Formal default "
              "is every lane present in bound metadata; pass this to retain a "
              "lane with no sidecar at all."),
    )
    ap.add_argument("--bootstrap-samples", type=int, default=2000)
    ap.add_argument("--bootstrap-seed", type=int, default=1729)
    ap.add_argument("--run-manifest", default="",
                    help="run_manifest.json for this report set (commit, host, env, "
                         "formula_version). NOT --manifest, which is the extraction "
                         "manifest. Defaults to <meta-dir>/run_manifest.json then "
                         "<reports-dir>/run_manifest.json")
    ap.add_argument("--require-manifest", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="refuse to build a board whose report set carries no manifest, "
                         "or whose manifest names another commit/host/formula_version.")
    ap.add_argument("--require-declared-lanes", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="refuse to rank a lane that config/lane_protocol.yaml does not "
                         "declare. tongyi-dr, co-storm, deepagents, dzhng and "
                         "local-deep-researcher are wired in run_deep_task and governed "
                         "by nothing.")
    ap.add_argument("--require-verified-corpus", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="refuse to build a board from runs whose meta does not say "
                         "source_check.state == 'ok'. Pass --no-require-verified-corpus "
                         "for reports produced before the pre-run source gate existed.")
    ap.add_argument(
        "--require-report-seals", action=argparse.BooleanOptionalAction,
        default=True,
        help=("require every report to match the byte-level seal in its run meta. "
              "Default on. Use --no-require-report-seals only for report sets "
              "created before run_id/report_seal existed; a present mismatch is "
              "never waived."),
    )
    ap.add_argument(
        "--require-model-identity", action=argparse.BooleanOptionalAction,
        default=True,
        help=("require each current report meta to carry a successful exact "
              "per-run model identity probe matching its backbone"),
    )
    ap.add_argument(
        "--require-production-comparable", action=argparse.BooleanOptionalAction,
        default=True,
        help=("refuse current reports produced with operator timeout overrides "
              "or any timeout contract marked non-comparable"),
    )
    ap.add_argument("--backbone", default=None,
                    help="disambiguate sidecars when one --meta-dir holds several "
                         "backbones; the filename does not carry one")
    ap.add_argument("--meta-dir", default="data/results/deep",
                    help="where run_deep_task wrote its flat <agent>__<task>.meta.json "
                         "sidecars. Without them a watchdog `stalled` run is "
                         "indistinguishable from a lane that delivered nothing, and "
                         "the rerun policy never fires.")
    ap.add_argument("--keys-dir", default="data/golden/answer_keys")
    ap.add_argument("--cache", default=None, help="sandbox page cache json")
    ap.add_argument(
        "--diagnostic", action=argparse.BooleanOptionalAction, default=False,
        help="Build a DIAGNOSTIC (non-headline) board when no page cache is "
             "supplied (SPEC_DECISIONS #2). Without this flag a board built "
             "with no --cache (or an empty cache) is REFUSED fail-closed: the "
             "concept/forum completeness slots cannot be grounded, so a formal "
             "number would be produced while the instrument is half-blind. In "
             "diagnostic mode the board is stamped cache_policy='diagnostic' "
             "and that policy is threaded to the scorer so the missing slots "
             "are withheld from the completeness denominator rather than "
             "silently scored 0.")
    ap.add_argument("--panel", default=None,
                    help="presentation panel results json: {agent: score}")
    ap.add_argument("--manifest", default=None,
                    help="extraction_manifest.json from extract_unified_reports.py; "
                         "surfaces lane failures instead of letting a broken "
                         "lane silently vanish or read as a real 0.0")
    ap.add_argument("--gamma", type=float, default=ds.GAMMA_DEFAULT)
    ap.add_argument("--tie-eps", type=float, default=0.005)
    ap.add_argument("--out", default=None)
    ap.add_argument("--missing-as-zero", dest="missing_as_zero",
                    action=argparse.BooleanOptionalAction, default=True,
                    help="A task with no report scores 0 instead of vanishing "
                         "from the agent's mean. Default on: without it, the "
                         "board rewards failing to produce a report (see "
                         "--min-coverage).")
    ap.add_argument("--min-coverage", type=float, default=0.5,
                    help="Agents completing less than this fraction of the "
                         "answer-key tasks are ranked, but flagged "
                         "low_coverage=true and excluded from headline claims.")
    ap.add_argument("--evidence-dir", action="append", default=[],
                    help="evidence root (repeatable, recursively scanned) of "
                         "<run_id>.jsonl transport logs written "
                         "by the shim. With it, proof_of_fetch means 'the agent "
                         "opened this page'; without it, it means 'the prose "
                         "resembles a page the evaluator fetched afterwards'.")
    ap.add_argument("--require-transport-pof", dest="require_transport_pof",
                    action=argparse.BooleanOptionalAction, default=True,
                    help="Refuse to score proof_of_fetch from anything but the "
                         "run's transport evidence. ON BY DEFAULT: with it off, "
                         "a lane whose fetches were never observed silently "
                         "falls back to the textual measure, which is how "
                         "`shim_search_delta == 0` survived 312 runs unnoticed. "
                         "A lane that cannot be observed is reported as "
                         "unscorable, never as zero. Turn off only to rescore "
                         "historical reports that have no evidence log, and then "
                         "the board is not comparable to a transport_v2 board.")
    ap.add_argument("--max-stall-reruns", type=int, default=1,
                    help="A `stalled` run (no LLM and no shim call for the "
                         "watchdog window) is an infrastructure fault, not a "
                         "framework failure. It must be rerun. A task still "
                         "stalled after this many reruns scores 0, like any "
                         "other undelivered report. The board REFUSES to build "
                         "if a stalled task has not yet exhausted its reruns.")
    args = ap.parse_args()

    if args.run_dir:
        if args.legacy_nested_layout:
            ap.error("--legacy-nested-layout cannot be combined with --run-dir")
        if args.replicates is None or args.replicates < 1:
            ap.error("formal --run-dir requires --replicates >= 1")
        if not args.missing_as_zero:
            ap.error("formal --run-dir requires --missing-as-zero")
    else:
        if not args.legacy_nested_layout:
            ap.error("--reports-dir is legacy and requires --legacy-nested-layout")
        if args.replicates not in (None, 1):
            ap.error("legacy nested layout has no replicate binding; use --replicates 1")
        args.replicates = 1
    if args.bootstrap_samples < 1:
        ap.error("--bootstrap-samples must be >= 1")

    keys_dir = ROOT / args.keys_dir
    keys = {p.stem: AnswerKey.load(p) for p in sorted(keys_dir.glob("*.json"))}
    if not keys:
        print(f"no answer keys under {keys_dir}")
        return 2
    cache = json.loads(Path(args.cache).read_text()) if args.cache else {}
    # Fail-closed cache policy (SPEC_DECISIONS #2). A formal (headline) board
    # MUST be built against the sandbox page cache: without it the concept-quote
    # and forum-coverage completeness slots have no page text to ground against
    # and score 0 for every lane -- a silent, instrument-caused zero for ~a
    # quarter of the completeness denominator, which is exactly the "0 must mean
    # observed-and-bad, never blind" contract. So a strict build with an empty
    # cache is refused here, before any number is produced. `--diagnostic`
    # opts into a non-headline build that is stamped cache_policy='diagnostic'
    # and threads that policy to the scorer, which withholds the ungroundable
    # slots from the completeness denominator instead of zeroing them.
    cache_policy = "diagnostic" if args.diagnostic else "strict"
    if cache_policy == "strict" and not cache:
        print(
            "ERROR: refusing to build a formal truth board with no page cache. "
            "Pass --cache <sandbox_cache.json> so the concept/forum completeness "
            "slots can be grounded, or pass --diagnostic to build a non-headline "
            "board (cache_policy='diagnostic') that withholds the ungroundable "
            "slots from the denominator rather than silently scoring them 0.",
            file=sys.stderr,
        )
        return 11
    # Interface contract with the scorer lane (SPEC_DECISIONS #2): the diagnostic
    # withhold behaviour lives in score_completeness(..., cache_policy=...),
    # implemented on a separate lane. Thread the policy through evaluate() ->
    # score_report() -> score_completeness only once the parameter exists, so
    # this board stays runnable before that lane merges and activates the
    # behaviour automatically after. The board is stamped with cache_policy
    # regardless, so a reader always knows which regime produced the numbers.
    import inspect as _inspect
    _scorer_accepts_cache_policy = (
        "cache_policy" in _inspect.signature(ds.score_report).parameters
    )
    _scorer_kw = ({"cache_policy": cache_policy}
                  if _scorer_accepts_cache_policy else {})
    panel, panel_provenance = load_panel(args.panel)
    registry = load_registry()
    # build_page_stats(cache) is a document-frequency pass over the WHOLE
    # cache; it is the same for every report in this run, so compute it once
    # here rather than paying its cost inside score_report() per report.
    page_stats = ds.build_page_stats(cache)

    formal_layout = bool(args.run_dir)
    formal_cells: dict[tuple[str, str, int], _FormalCell] = {}
    formal_manifests: set[Path] = set()
    formal_plan: dict | None = None
    if formal_layout:
        run_dir = Path(args.run_dir).resolve()
        rdir = run_dir / "raw"
        if args.backbone and args.backbone != run_dir.name:
            print(
                f"ERROR: --backbone={args.backbone!r} does not match governed "
                f"run-dir backbone {run_dir.name!r}",
                file=sys.stderr,
            )
            return 9
        args.backbone = run_dir.name
        args.meta_dir = str(rdir)
        default_plan_path = (run_dir / "run_plan.json").resolve()
        plan_path = (Path(args.run_plan).resolve() if args.run_plan
                     else default_plan_path)
        if plan_path != default_plan_path:
            print(
                "ERROR: formal plan must be the canonical <run-dir>/run_plan.json "
                "so every entry binding seals the same file",
                file=sys.stderr,
            )
            return 9
        if args.require_run_plan:
            try:
                from scripts.verify_run_set import validate_run_plan

                formal_plan = validate_run_plan(
                    plan_path,
                    run_set_id=run_dir.parent.name,
                    backbone=run_dir.name,
                    replicates=args.replicates,
                )
                formal_manifests.add(
                    run_dir / formal_plan["manifest"]["file"]
                )
            except Exception as exc:  # noqa: BLE001
                print(
                    f"ERROR: formal run plan violation: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                return 9
        try:
            formal_cells, discovered_manifests = _discover_formal_cells(
                run_dir, replicates=args.replicates
            )
            formal_manifests.update(discovered_manifests)
        except ValueError as exc:
            print(f"ERROR: formal run-set integrity violation: {exc}", file=sys.stderr)
            return 9
        evidence_roots = [Path(p) for p in args.evidence_dir]
        if not evidence_roots and (run_dir / "evidence").is_dir():
            evidence_roots = [run_dir / "evidence"]
    else:
        run_dir = None
        rdir = Path(args.reports_dir)
        evidence_roots = [Path(p) for p in args.evidence_dir]

    if evidence_roots:
        # Bind the shim's blob loader to the evidence dir we are scoring. The
        # back-compat `linked` path (logs written before `links` was stamped on
        # each fetch record) reads page bytes via evidence.load_blob, which keys
        # off SHIM_EVIDENCE_DIR/blobs. If that env pointed elsewhere (or was
        # unset while scoring a relocated dir), every blob load would miss, the
        # `linked` set would silently empty, and on-page-link citations would be
        # over-charged as hallucinated_grounding. Setting it here keeps blobs and
        # logs pointing at the same dir. New logs carry `links` and do not need
        # this, but old ones do.
        # Legacy scorer code has a process-global blob root. The multi-root
        # index recovers old link blobs per fragment before merging; keep this
        # variable only for remaining single-root legacy paths.
        os.environ["SHIM_EVIDENCE_DIR"] = str(evidence_roots[0].resolve())
    ev_by_key, ev_by_run = (_index_evidence(evidence_roots)
                            if evidence_roots else ({}, {}))
    if evidence_roots:
        print(
            f"transport evidence: {len(ev_by_run)} runs indexed from "
            + ", ".join(str(p) for p in evidence_roots)
        )

    rows = []
    seen_semantics: set[str] = set()
    seen_gate_semantics: set[str] = set()
    unscorable: dict[str, str] = {}
    stall_debt: list[str] = []
    unverified: list[str] = []
    report_integrity_errors: list[str] = []
    report_hash_owners: dict[str, list[tuple[str, str, int]]] = {}
    declared_lanes = _declared_lanes()
    undeclared: set[str] = set()
    requested_agents = {
        lane.strip()
        for value in args.agents
        for lane in value.split(",")
        if lane.strip()
    }
    if formal_layout:
        if formal_plan is not None:
            plan_agents = set(formal_plan["agents"])
            plan_tasks = set(formal_plan["tasks"])
            if plan_tasks != set(keys):
                missing = sorted(set(keys) - plan_tasks)
                extra = sorted(plan_tasks - set(keys))
                print(
                    "ERROR: formal run plan is not the complete answer-key task set: "
                    f"missing={missing[:8]} extra={extra[:8]}",
                    file=sys.stderr,
                )
                return 9
            if requested_agents and requested_agents != plan_agents:
                print(
                    "ERROR: --agents does not exactly match immutable run plan: "
                    f"requested={sorted(requested_agents)} "
                    f"planned={sorted(plan_agents)}",
                    file=sys.stderr,
                )
                return 9
            requested_agents = plan_agents
        unknown_tasks = sorted({cell.task for cell in formal_cells.values()} - set(keys))
        if unknown_tasks:
            print(
                f"ERROR: formal metadata names task(s) with no answer key: {unknown_tasks}",
                file=sys.stderr,
            )
            return 9
        agent_names = sorted(
            requested_agents | {cell.agent for cell in formal_cells.values()}
        )
        if formal_plan is not None:
            extra_agents = sorted(set(agent_names) - set(formal_plan["agents"]))
            if extra_agents:
                print(
                    f"ERROR: bound metadata contains lane(s) outside run plan: "
                    f"{extra_agents}",
                    file=sys.stderr,
                )
                return 9
        agent_dirs: dict[str, Path] = {}
    else:
        dirs = sorted(p for p in rdir.iterdir() if p.is_dir())
        agent_dirs = {p.name: p for p in dirs}
        agent_names = sorted(set(agent_dirs) | requested_agents)

    for agent_name in agent_names:
        agent_dir = agent_dirs.get(agent_name, rdir / agent_name)
        if declared_lanes and agent_name not in declared_lanes:
            undeclared.add(agent_name)
        per_cell: dict[tuple[str, int], dict] = {}
        cell_status: dict[tuple[str, int], str] = {}
        stalled_cells: list[tuple[str, int]] = []
        source_states: dict[str, int] = {}
        lane_unscorable = False
        for tid, ak in sorted(keys.items()):
            for replicate in range(1, args.replicates + 1):
                if formal_layout:
                    formal_cell = formal_cells.get((agent_name, tid, replicate))
                    if formal_cell is None:
                        cell_status[(tid, replicate)] = "missing"
                        continue
                    rp = formal_cell.report_path
                    _meta = formal_cell.meta
                    status = formal_cell.status
                else:
                    formal_cell = None
                    rp = agent_dir / f"{tid}.md"
                    _meta = _run_status(
                        agent_dir, tid, Path(args.meta_dir), args.backbone
                    )
                    status = ("pass" if rp.exists()
                              else str(_meta.get("status") or "missing"))
                    if status not in {
                        "pass", "fail", "stalled", "infra_abort", "timeout", "missing"
                    }:
                        status = "missing"
                cell_status[(tid, replicate)] = status

                if status != "pass":
                    # No report. Two very different reasons, and the board must not
                    # confuse them: the framework delivered nothing (worth 0), or
                    # the watchdog/infrastructure killed the run. Infrastructure
                    # cells remain rerunnable until their attempt allowance is spent.
                    if status in ("stalled", "infra_abort"):
                        if int(_meta.get("attempts", 1)) <= args.max_stall_reruns:
                            stall_debt.append(
                                f"{agent_name}/{tid}/rep{replicate}: {status} after "
                                f"{_meta.get('attempts', 1)} attempt(s), "
                                f"{args.max_stall_reruns} rerun(s) allowed"
                            )
                        else:
                            stalled_cells.append((tid, replicate))
                    continue

                assert rp is not None
                # Was the corpus proved reachable before this run started? The
                # harness stamps the answer; a board that never reads it pools an
                # unverified run with verified ones and cannot say which is which.
                # A watchdog report beside a newer infra sidecar is stale output.
                if _meta.get("status") in ("stalled", "infra_abort"):
                    report_integrity_errors.append(
                        f"{agent_name}/{tid}/rep{replicate}: report exists but "
                        f"current meta is {_meta.get('status')} "
                        "(stale report from another attempt)"
                    )
                    continue

                # A report is scoreable only when its sidecar describes this
                # exact lane/task and a successful run.
                if _meta.get("run_id"):
                    for field, want in (("agent", agent_name), ("task", tid)):
                        if _meta.get(field) != want:
                            report_integrity_errors.append(
                                f"{agent_name}/{tid}/rep{replicate}: meta "
                                f"{field}={_meta.get(field)!r} does not match {want!r}"
                            )
                    if _meta.get("status") != "pass":
                        report_integrity_errors.append(
                            f"{agent_name}/{tid}/rep{replicate}: report meta "
                            f"status is {_meta.get('status')!r}, not 'pass'"
                        )
                    meta_backbone = _meta.get("backbone")
                    if args.backbone and meta_backbone != args.backbone:
                        report_integrity_errors.append(
                            f"{agent_name}/{tid}/rep{replicate}: meta "
                            f"backbone={meta_backbone!r} does not match requested "
                            f"{args.backbone!r}"
                        )
                    if args.require_model_identity:
                        ident = _meta.get("model_identity") or {}
                        if (ident.get("ok") is not True
                                or ident.get("declared") != meta_backbone
                                or ident.get("actual") != meta_backbone
                                or not ident.get("endpoint")):
                            report_integrity_errors.append(
                                f"{agent_name}/{tid}/rep{replicate}: invalid per-run "
                                f"model identity for backbone {meta_backbone!r}: {ident}"
                            )
                    if args.require_production_comparable:
                        contract = _meta.get("timeout_contract") or {}
                        if contract.get("production_comparable") is not True:
                            report_integrity_errors.append(
                                f"{agent_name}/{tid}/rep{replicate}: timeout contract "
                                f"is not production-comparable: {contract}"
                            )

                seal_error = _report_seal_error(
                    rp, _meta, require_legacy_seal=args.require_report_seals
                )
                if seal_error:
                    report_integrity_errors.append(
                        f"{agent_name}/{tid}/rep{replicate}: {seal_error}"
                    )
                    continue
                _sc = _meta.get("source_check") or {}
                _state = str(_sc.get("state") or "unknown")
                source_states[_state] = source_states.get(_state, 0) + 1
                if _state != "ok":
                    unverified.append(
                        f"{agent_name}/{tid}/rep{replicate}: source_check={_state}"
                    )
                elif (_meta.get("run_id") and args.require_verified_corpus
                      and _sc.get("sample_in_corpus") is not True):
                    unverified.append(
                        f"{agent_name}/{tid}/rep{replicate}: source_check did not "
                        "prove returned sample URLs are in the scoring registry"
                    )

                md = rp.read_text(errors="replace")
                if not is_stub_report(md):
                    digest = hashlib.sha256(rp.read_bytes()).hexdigest()
                    report_hash_owners.setdefault(digest, []).append(
                        (agent_name, tid, replicate)
                    )
                try:
                    per_cell[(tid, replicate)] = evaluate(
                        md, ak, cache, registry=registry,
                        gamma=args.gamma, page_stats=page_stats,
                        # A run_id is an exact foreign key. Never borrow the
                        # latest sibling attempt's transport evidence.
                        evidence=(ev_by_run.get(_meta.get("run_id"))
                                  if _meta.get("run_id")
                                  else ev_by_key.get((agent_name, tid))),
                        require_transport_pof=args.require_transport_pof,
                        **_scorer_kw,
                    )
                except ds.MissingEvidenceLog as exc:
                    unscorable[agent_name] = str(exc)
                    per_cell = {}
                    lane_unscorable = True
                    break
                seen_semantics.add(per_cell[(tid, replicate)]["pof_semantics"])
                seen_gate_semantics.add(
                    per_cell[(tid, replicate)]["gate_semantics"]
                )
            if lane_unscorable:
                break
        if lane_unscorable:
            continue
        if not per_cell and not formal_layout:
            continue
        # Survivorship bias (fairness audit 2026-07-08, B2). The loop above
        # `continue`s past every task with no report file, and the mean below
        # used to divide by the number of SURVIVING tasks. An agent that
        # crashed on 11 of 13 tasks was then ranked on the 2 it happened to
        # finish, against agents ranked on all 13. Measured: claude-code moved
        # from #2 to #8 (qwen) and #4 to #9 (deepseek) once its missing tasks
        # counted as zero.
        #
        # A missing report is a failure to deliver a report, which is worth
        # exactly what an empty report is worth. `n_scored` keeps the number of
        # real reports visible so the two can never be confused.
        n_scored = len(per_cell)
        n_keys = len(keys)
        n_expected = n_keys * args.replicates
        n_stalled_final = len(stalled_cells)
        coverage = n_scored / n_expected if n_expected else 0.0
        scored_truths = [d["truth"] for _, d in sorted(per_cell.items())]
        task_truth_replicates = {
            tid: [
                float(per_cell.get((tid, rep), {}).get("truth", 0.0))
                for rep in range(1, args.replicates + 1)
            ]
            for tid in sorted(keys)
        }
        truths_all = [value for tid in sorted(task_truth_replicates)
                      for value in task_truth_replicates[tid]]
        truths = truths_all if args.missing_as_zero else list(scored_truths)
        n = len(truths)
        macro = math.fsum(truths) / n if n else 0.0
        # micro: pool numerators/denominators where meaningful (reach), else
        # report the mean over tasks weighted by citation volume. Missing tasks
        # carry no citations, so they cannot enter a citation-weighted mean;
        # micro is therefore a SURVIVING-TASK statistic and must be read with
        # `coverage`, never on its own.
        dens = [d["reach_detail"].get("den", 0)
                for _, d in sorted(per_cell.items())]
        micro = (math.fsum(t * w for t, w in zip(scored_truths, dens)) / sum(dens)
                 if sum(dens) else (math.fsum(scored_truths) / n_scored
                                    if n_scored else 0.0))
        # axes are means over the reports that exist: an axis value for a report
        # that was never produced is undefined, not zero. Keys come from the
        # reports themselves (ds._axis_key stamps the grounding axis per
        # semantics), so a text_v1 lane's mean lands under
        # `grounding_quote_support` and never under a proof_of_fetch header it
        # did not earn (P1).
        axis_keys = (
            tuple(next(iter(per_cell.values()))["axes"].keys())
            if per_cell else _board_axes(
                "transport_v2" if args.require_transport_pof else "text_v1"
            )
        )
        axes_mean_surviving = (
            _axes_mean(per_cell.values(), axis_keys, n_scored)
            if n_scored else {a: 0.0 for a in axis_keys})
        # Headline axis/compliance columns use the same all-task denominator as
        # truth_macro.  Publish the surviving-report view too, but name it and
        # expose both denominators so coverage differences cannot masquerade as
        # stronger axis performance.
        axes_mean_all_tasks = _axes_mean(per_cell.values(), axis_keys, n_expected)
        # fact_active_rate (P2): fraction of this lane's PRODUCED reports that
        # made any checkable structured claim. Denominator is n_scored, not
        # n_keys: a missing report is not a report on which fact was "inert", it
        # is a report that does not exist (truth 0 across every axis). A rate
        # near 0 means the 0.39 fact weight did nothing here and truth was
        # driven by pof + completeness. This is EFFECTIVE weight, read straight
        # from each report's fact detail, not a nominal constant.
        n_fact_active = sum(1 for d in per_cell.values()
                            if d["detail"]["fact"].get("fact_active"))
        fact_active_rate = n_fact_active / n_scored if n_scored else 0.0
        # reach_zero_rate (Y2): fraction of this lane's PRODUCED reports whose
        # reach axis is 0. truth = reach^gamma * quality, so on every reach==0
        # report the ENTIRE quality term (all three weights) is multiplied out
        # and carries NO information. A high rate means the 0.39/0.28/0.33 weights
        # were inert on that share of the lane's reports; read WITH
        # fact_active_rate it shows truth was driven by the reach gate, not by the
        # nominal weight triple. Denominator is n_scored (missing reports do not
        # exist; they are not reach==0 reports).
        n_reach_zero = sum(1 for d in per_cell.values()
                           if d["axes"].get("grounding_reach", 0.0) <= 0.0)
        reach_zero_rate = n_reach_zero / n_scored if n_scored else 0.0
        n_gate_zero = sum(1 for d in per_cell.values()
                          if float(d.get("gate_value", 0.0)) <= 0.0)
        gate_zero_rate = n_gate_zero / n_scored if n_scored else 0.0
        outcome_counts = {
            status: sum(1 for got in cell_status.values() if got == status)
            for status in ("pass", "fail", "stalled", "infra_abort", "timeout", "missing")
        }
        outcome_rates = {
            status: round(count / n_expected, 6) if n_expected else 0.0
            for status, count in outcome_counts.items()
        }
        ci_low, ci_high = _cluster_bootstrap_ci(
            task_truth_replicates,
            samples=args.bootstrap_samples,
            seed=args.bootstrap_seed,
        )
        per_task_summary = {}
        for tid in sorted(keys):
            replicate_rows = {}
            for rep in range(1, args.replicates + 1):
                score = per_cell.get((tid, rep))
                replicate_rows[str(rep)] = ({
                    "status": "pass",
                    "truth": score["truth"],
                    "axes": score["axes"],
                    # G6: carry the per-axis zero-reason map through aggregation
                    # so a board's 0 is never a silent 0 (mandate: 汇总不丢弃).
                    "axis_reasons": dict(score.get("axis_reasons", {})),
                } if score is not None else {
                    "status": cell_status.get((tid, rep), "missing"),
                    "truth": 0.0,
                    "axes": {a: 0.0 for a in axis_keys},
                    # No report at all: every axis is 0 for one machine-readable
                    # reason -- the run outcome (missing / stalled / infra_abort /
                    # timeout). That IS the reason code for these zeros.
                    "axis_reasons": {a: cell_status.get((tid, rep), "missing")
                                     for a in axis_keys},
                })
            per_task_summary[tid] = {
                "truth": math.fsum(sorted(task_truth_replicates[tid])) / args.replicates,
                "axes": {
                    a: math.fsum(sorted(
                        row["axes"].get(a, 0.0)
                        for row in replicate_rows.values()
                    )) / args.replicates
                    for a in axis_keys
                },
                "replicates": replicate_rows,
            }
        rows.append({
            "agent": agent_name,
            "n_tasks": len({tid for tid, _ in per_cell}),
            "n_reports_scored": n_scored,
            "n_keys": n_keys,
            "n_replicates": args.replicates,
            "n_task_replicates_expected": n_expected,
            "coverage": round(coverage, 4),
            # Tasks still stalled after their reruns. They score 0 (user
            # decision 2026-07-08), but the count stays visible so a lane
            # sunk by a flaky inference backend is never silently read as a
            # lane that could not do the work.
            "n_stalled_after_reruns": n_stalled_final,
            "run_outcomes": {
                "denominator": n_expected,
                "counts": outcome_counts,
                "rates": outcome_rates,
            },
            **{f"{status}_rate": outcome_rates[status]
               for status in ("pass", "fail", "stalled", "infra_abort", "timeout")},
            "missing_rate": outcome_rates["missing"],
            # How many of this lane's scored reports ran against a corpus whose
            # reachability was confirmed before the run opened.
            "source_check_states": dict(sorted(source_states.items())),
            "n_source_unverified": sum(v for k, v in source_states.items() if k != "ok"),
            "low_coverage": coverage < args.min_coverage,
            "missing_as_zero": bool(args.missing_as_zero),
            "truth_macro": round(macro, 4),
            "truth_macro_ci95": {
                "low": round(ci_low, 4),
                "high": round(ci_high, 4),
                "method": "task_cluster_bootstrap",
                "cluster": "task",
                "replicates_within_cluster": args.replicates,
                "samples": args.bootstrap_samples,
                "seed": args.bootstrap_seed,
            },
            "truth_micro": round(micro, 4),
            "min_report_truth": round(min(truths_all), 4) if truths_all else 0.0,
            "min_report_truth_surviving": (
                round(min(scored_truths), 4) if scored_truths else 0.0
            ),
            "axes_mean": axes_mean_all_tasks,
            "axes_mean_all_tasks_zero_padded": axes_mean_all_tasks,
            "axes_mean_surviving": axes_mean_surviving,
            "axes_denominator_all_tasks": n_expected,
            "axes_denominator_all_task_replicates": n_expected,
            "axes_denominator_surviving": n_scored,
            "fact_active_rate": round(fact_active_rate, 4),
            "reach_zero_rate": round(reach_zero_rate, 4),
            "gate_zero_rate": round(gate_zero_rate, 4),
            # spec is OUT of truth (FORMULA_LOCK K6): surfaced as a separate
            # compliance column, never multiplied in. Kept in axes_mean too.
            "compliance": axes_mean_all_tasks.get("spec", 0.0),
            "compliance_all_tasks_zero_padded": axes_mean_all_tasks.get("spec", 0.0),
            "compliance_surviving": axes_mean_surviving.get("spec", 0.0),
            "compliance_denominator_all_tasks": n_expected,
            "compliance_denominator_all_task_replicates": n_expected,
            "compliance_denominator_surviving": n_scored,
            "presentation": panel.get(agent_name),
            "per_task": per_task_summary,
        })

    for digest, owners in report_hash_owners.items():
        identities = {(lane, task) for lane, task, _ in owners}
        if len(identities) > 1:
            report_integrity_errors.append(
                f"identical non-stub report sha256={digest} appears across "
                "lane/task identities: "
                + ", ".join(
                    f"{lane}/{task}/rep{rep}" for lane, task, rep in sorted(owners)
                )
            )

    if report_integrity_errors:
        print(
            f"ERROR: {len(report_integrity_errors)} report/run integrity "
            "violation(s):\n  " + "\n  ".join(report_integrity_errors[:20])
            + (f"\n  ... and {len(report_integrity_errors) - 20} more"
               if len(report_integrity_errors) > 20 else ""),
            file=sys.stderr,
        )
        return 9

    # rank: truth first; presentation may only break ties within tie_eps
    rows.sort(key=lambda r: -r["truth_macro"])
    i = 0
    while i < len(rows):
        j = i
        while (j + 1 < len(rows) and
               rows[i]["truth_macro"] - rows[j + 1]["truth_macro"] <= args.tie_eps):
            j += 1
        if j > i:
            rows[i:j + 1] = sorted(
                rows[i:j + 1],
                key=lambda r: -(r["presentation"] if isinstance(
                    r.get("presentation"), (int, float)) else float("-inf")))
        i = j + 1
    prior_rank_key = None
    prior_rank = 0
    for position, row in enumerate(rows, 1):
        presentation = (row["presentation"] if isinstance(
            row.get("presentation"), (int, float)) else None)
        rank_key = (row["truth_macro"], presentation)
        if rank_key != prior_rank_key:
            prior_rank = position
            prior_rank_key = rank_key
        # Exact metric ties share a rank. Filename/agent-name iteration order
        # can change row display order, but can never award a different rank.
        row["rank"] = prior_rank

    # The board's axis-key set. If semantics are mixed this picks one of them,
    # but such a board is rejected by rc=3 below and never written; placeholders
    # are all-zero regardless, so only the KEY NAMES matter here.
    board_pof_semantics = next(
        iter(seen_semantics),
        "transport_v2" if args.require_transport_pof else "text_v1",
    )
    board_axes = _board_axes(board_pof_semantics)

    lane_info = _load_lane_info(Path(args.manifest)) if args.manifest else {}
    if lane_info:
        scored_agents = {r["agent"] for r in rows}
        for r in rows:
            li = lane_info.get(r["agent"])
            if li:
                r.update(li)
        # A lane whose every run was a stub (or missing) produces no report file
        # for the board to score, so it would silently disappear. Keep it in,
        # flagged, so the failure is visible rather than absent. Placeholders are
        # ranked after every scored agent and carry no truth signal.
        next_rank = len(rows) + 1
        for agent in sorted(lane_info):
            li = lane_info[agent]
            if agent in scored_agents or not li["lane_failed"]:
                continue
            placeholder = {
                "agent": agent,
                "n_tasks": 0,
                "truth_macro": 0.0,
                "truth_micro": 0.0,
                "min_report_truth": 0.0,
                "min_report_truth_surviving": 0.0,
                "axes_mean": {a: 0.0 for a in board_axes},
                "axes_mean_all_tasks_zero_padded": {a: 0.0 for a in board_axes},
                "axes_mean_surviving": {a: 0.0 for a in board_axes},
                "axes_denominator_all_tasks": len(keys),
                "axes_denominator_all_task_replicates": len(keys),
                "axes_denominator_surviving": 0,
                "compliance": 0.0,
                "compliance_all_tasks_zero_padded": 0.0,
                "compliance_surviving": 0.0,
                "compliance_denominator_all_tasks": len(keys),
                "compliance_denominator_all_task_replicates": len(keys),
                "compliance_denominator_surviving": 0,
                "presentation": panel.get(agent),
                "per_task": {},
                "rank": next_rank,
            }
            placeholder.update(li)
            rows.append(placeholder)
            next_rank += 1

    # A stalled task has not been measured. Scoring it before the rerun that the
    # policy requires would publish an infrastructure fault as a framework's
    # score. Refuse, name the tasks, and let the harness rerun them.
    # The manifest is the only thing tying these numbers to the code, host, and
    # formula that produced them. `run_manifest.verify()` says in its own
    # docstring that "the scorer calls this and refuses on any non-empty
    # result". No scorer called it. Reports from an old commit, a dirty tree, a
    # different host, or a different FORMULA_VERSION were scored and published.
    if args.require_manifest:
        from scripts import run_manifest as rm
        if formal_layout:
            mpaths = set(formal_manifests)
            if args.run_manifest:
                mpaths.add(Path(args.run_manifest).resolve())
            verify_root = run_dir
        else:
            mpath = Path(args.run_manifest) if args.run_manifest else None
            if mpath is None:
                for cand in (Path(args.meta_dir) / "run_manifest.json",
                             rdir / "run_manifest.json"):
                    if cand.exists():
                        mpath = cand
                        break
            mpaths = {mpath} if mpath is not None else set()
            verify_root = rdir
        if not mpaths or any(not path.exists() for path in mpaths):
            print("ERROR: no run manifest found. It records the commit, host, "
                  "env and formula_version these reports were produced under, "
                  "and without it a board cannot say what it measured. Pass "
                  "--run-manifest, or --no-require-manifest to score anyway.",
                  file=sys.stderr)
            return 7
        for mpath in sorted(mpaths):
            try:
                reasons = rm.verify(
                    json.loads(mpath.read_text(encoding="utf-8")), verify_root
                )
            except Exception as e:  # noqa: BLE001
                reasons = [f"manifest unreadable: {type(e).__name__}: {e}"]
            if reasons:
                print(f"ERROR: run manifest {mpath} does not vouch for this report "
                      "set:\n  " + "\n  ".join(reasons), file=sys.stderr)
                return 7

    if undeclared and args.require_declared_lanes:
        print(f"ERROR: lane(s) {sorted(undeclared)} are not declared in "
              "config/lane_protocol.yaml, so their prompts, budgets and samplers "
              "were never checked by check_parity. Ranking them against the "
              "governed lanes compares a measured thing with an unmeasured one. "
              "Declare them, or pass --no-require-declared-lanes.", file=sys.stderr)
        return 8

    if unverified and args.require_verified_corpus:
        print(f"ERROR: {len(unverified)} scored report(s) ran without a confirmed "
              "corpus. A run whose sources were never proved reachable is not a "
              "measurement of the framework:\n  " +
              "\n  ".join(sorted(unverified)[:12]) +
              (f"\n  ... and {len(unverified) - 12} more" if len(unverified) > 12 else "") +
              "\nRerun them, or pass --no-require-verified-corpus to score reports "
              "produced before the pre-run source gate existed.", file=sys.stderr)
        return 6

    if stall_debt:
        print("ERROR: stalled tasks have not exhausted their reruns.\n  " +
              "\n  ".join(stall_debt) +
              "\nRerun them, or pass --max-stall-reruns 0 to accept the stall "
              "as a delivered zero (this attributes an infrastructure fault to "
              "the framework).", file=sys.stderr)
        return 4

    if unscorable:
        print("\nUNSCORABLE LANES (proof_of_fetch cannot be measured):",
              file=sys.stderr)
        for lane, why in sorted(unscorable.items()):
            print(f"  {lane}: {why.splitlines()[0]}", file=sys.stderr)
        print("  Nothing observed whether these lanes opened the pages they "
              "cite: either the run produced no evidence log, or the lane reads "
              "pages off-shim (see config/lane_protocol.yaml fetch_observable). "
              "They are withheld from the board rather than scored 0, which "
              "would accuse them of citing pages they never read.\n",
              file=sys.stderr)

    if not rows:
        # Every lane withheld. Emitting an empty board with exit 0 is how a dead
        # instrument looks exactly like a clean run, which is the failure this
        # whole rework exists to prevent.
        print("ERROR: no lane could be scored. Refusing to write an empty board.",
              file=sys.stderr)
        return 5

    # A board must answer ONE question per axis. If some reports had their
    # proof_of_fetch decided by "the agent opened this page" and others by "the
    # prose resembles a page we fetched afterwards", the column is two different
    # measurements stacked in one row, and every comparison across it is void.
    if len(seen_semantics) > 1:
        print(f"ERROR: mixed pof semantics in one board: {sorted(seen_semantics)}.\n"
              "Some reports have a transport evidence log and some do not. Score "
              "them as two boards, or pass --require-transport-pof and fix the "
              "runs that produced no log.", file=sys.stderr)
        return 3
    pof_semantics = board_pof_semantics
    if len(seen_gate_semantics) > 1:
        print(f"ERROR: mixed truth-gate semantics in one board: "
              f"{sorted(seen_gate_semantics)}.", file=sys.stderr)
        return 3
    gate_semantics = next(iter(seen_gate_semantics),
                          "provenance_v2" if pof_semantics == "transport_v2"
                          else "reach_v1")

    # Double insurance over rc=3 (P1). rc=3 keys off the per-report semantics
    # stamp; this keys off the axis names that actually landed in the rows, so a
    # future bug that emitted the wrong key WITHOUT flipping the stamp still
    # cannot ship a board carrying both grounding names at once.
    _grounding_keys = {k for r in rows for k in r.get("axes_mean", {})
                       if k in ("grounding_proof_of_fetch", "grounding_quote_support")}
    assert _grounding_keys <= {ds._axis_key(pof_semantics)}, (
        f"board mixes grounding axis names {sorted(_grounding_keys)} but declares "
        f"pof_semantics={pof_semantics!r} (expected only {ds._axis_key(pof_semantics)!r})")

    eps = ds.EPS_FLOOR
    floor_desc = ("NO floor (D1: EPS_FLOOR=0.0)" if eps <= 0.0
                  else f"floor-if-active eps={eps}")
    board = {
        "board": "truth_v2",
        # Fail-closed cache regime (SPEC_DECISIONS #2). "strict" == a headline
        # board built against the sandbox page cache (concept/forum slots
        # grounded). "diagnostic" == a non-headline board built with no cache;
        # the ungroundable slots are withheld from the completeness denominator
        # by the scorer rather than scored 0. A diagnostic board must NOT be
        # compared against a strict one.
        "cache_policy": cache_policy,
        # Where the presentation column came from (or None without --panel;
        # {"unstamped": true} for a legacy stampless file). See load_panel.
        "panel_provenance": panel_provenance,
        "composition": (f"truth = "
                        f"{'provenance' if gate_semantics == 'provenance_v2' else 'reach'}"
                        f"^gamma * (0.39 fact + 0.28 pof + "
                        f"0.33 completeness), {floor_desc} "
                        "(FORMULA_LOCK K6 + D1/D4); spec/compliance and "
                        "presentation are separate columns, tie-break only, "
                        "never in truth"),
        "gamma": args.gamma,
        "aggregation_version": "task-cluster-replicate-v1",
        "aggregation": ("macro over ALL answer-key task x replicate cells; every "
                        "missing or non-pass cell scores 0 (missing_as_zero). "
                        "Replicates are averaged inside their task cluster, then "
                        "tasks are macro-averaged. truth_micro is a surviving-report "
                        "statistic; read it with `coverage`. min_report_truth and "
                        "the headline axes_mean/compliance are all-cell zero-padded; "
                        "explicitly named *_surviving fields preserve the produced-"
                        "report view and every variant carries its denominator."
                        if args.missing_as_zero else
                        "macro over SURVIVING tasks only (missing_as_zero=off): "
                        "rewards failing to produce a report"),
        "min_coverage": args.min_coverage,
        "eps_floor": eps,
        "floor_mode": "none" if eps <= 0.0 else "floor_if_active",
        "spec_in_truth": False,
        # Nominal vs EFFECTIVE weight (Y2). The 0.39/0.28/0.33 triple is the
        # DECLARED harm-ordering, not the axes' realised influence. Because
        # truth = reach^gamma * quality, the quality term (and every weight in it)
        # is inert on any report with reach==0; and fact recall stays 0 unless a
        # task-ranked structured claim carries its own nearby citation. Both
        # diagnostic fractions are
        # published PER ROW (reach_zero_rate, fact_active_rate) so a consumer can
        # read an axis's realised weight instead of the nominal constant. This is
        # disclosure, not a formula change: the number is untouched.
        "weight_disclosure": {
            "nominal_quality_weights": dict(ds.QUALITY_WEIGHTS),
            "per_row_effective_signals": ["gate_zero_rate", "fact_active_rate"],
            "note": (
                "truth = reach^gamma * (0.39 fact + 0.28 pof + 0.33 completeness). "
                "The weights are NOMINAL. On any report with gate==0 (see each "
                "row's gate_zero_rate) the whole quality term is multiplied out, "
                "so no weight carries information there. Among reach>0 reports fact "
                "recall scores 0 unless a task-ranked structured claim carries "
                "its own citation in the same sentence or table row. "
                "fact_active_rate only says that some "
                "claim was tested; it does not prove recall was eligible. When "
                "fact is inert its EFFECTIVE "
                "weight is far below 0.39 and truth is driven by the reach gate "
                "then pof + completeness. Do NOT read 0.39/0.28/0.33 as the axes' "
                "actual influence; read reach_zero_rate and fact_active_rate."),
        },
        # Name-vs-thing (Y2/Y1). Each axis KEY is retained for continuity, but the
        # board states what the number actually measures and what it does NOT, so
        # the name cannot over-promise. The grounding-fidelity axis has its own
        # note in `protocols.grounding_axis_note`.
        "axis_semantics": {
            "grounding_reach": (
                "corpus-URL MEMBERSHIP, not use: a cited URL parses, is canonical, "
                "and is in the enumerated corpus. It does NOT witness a fetch; a "
                "report that guessed a real corpus URL from parametric memory "
                "scores reach=1. Under transport_v2 this is a DIAGNOSTIC, not the "
                "truth gate; provenance_v2 is the gate. Legacy text_v1 boards use "
                "reach_v1 because they cannot observe provenance."),
            "correctness_fact_support": (
                "accuracy of CHECKABLE structured claims (price or overall "
                "rating bound to a named DB entity). Precision tests every bound "
                "claim, but recall credit is restricted to task-ranked products "
                "and requires that product's own nearby citation in the same "
                "claim sentence or table row. A correct "
                "uncited or out-of-scope catalog value cannot fill recall. A "
                "report with no checkable claim scores 0; use fact_active_rate "
                "and claims_tested to distinguish silence from wrong claims. "
                "NOT report-level correctness."),
            "completeness": (
                f"vital-fact recall over min(K*={ds.K_STAR_DEFAULT}, "
                f"|ranked structured/concept pool + forum slot|). Saturation is "
                "the design intent but does not fire: each task's vital pool "
                "holds ~14-17 nuggets (below K*), so the denominator is |pool| "
                "and the axis is in practice a CENSUS -- covering EVERY vital "
                "fact the task offers scores 1.0 (ruling #5); K* is only an upper "
                "cap and does not bind at current pool sizes. Every structured "
                "nugget requires its source citation on the same Markdown line "
                "as the subject/value and, when transport is "
                "available, a fetch of that source page. A declared community "
                "requirement adds one virtual slot covered only by a fetched, "
                "quoted, task-relevant allowed-forum thread. Detached source "
                "dumps, unrelated catalog rows, or URL shells do not count. NOT "
                "uncapped exhaustiveness."),
            "spec": (
                "output-shape compliance (format checks). Separate column, NOT in "
                "truth. Row-level compliance is the all-task-replicate zero-padded mean; "
                "compliance_surviving is the produced-report mean, with both "
                "denominators published."),
        },
        # Which axis keys this board's rows use. The grounding-fidelity axis is
        # named for what it measured: `grounding_quote_support` under text_v1
        # (no fetch observed) vs `grounding_proof_of_fetch` under transport_v2
        # (a fetch observed). Consumers should read the grounding axis by this
        # name, not a hard-coded string (P1).
        "axis_names": list(board_axes),
        "protocols": {
            **_protocols(args.gamma, keys.keys(), pof_semantics, gate_semantics),
            "aggregation_version": "task-cluster-replicate-v1",
            "n_replicates": args.replicates,
            "n_task_replicates": len(keys) * args.replicates,
            # Fail-closed cache regime (SPEC_DECISIONS #2). Boards carrying
            # different cache_policy are NOT comparable: a diagnostic board
            # withholds ungroundable concept/forum slots from the completeness
            # denominator that a strict board grounds against the page cache.
            "cache_policy": cache_policy,
        },
        "gate_semantics": gate_semantics,
        "artifact_layout": ("formal_flat_run_set" if formal_layout
                            else "legacy_nested_opt_out"),
        "run_plan": ({
            "required": True,
            "plan_version": formal_plan["plan_version"],
            "sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            "agents": formal_plan["agents"],
            "n_tasks": len(formal_plan["tasks"]),
            "replicates": formal_plan["replicates"],
            "manifest": formal_plan["manifest"],
        } if formal_plan is not None else {
            "required": bool(formal_layout and args.require_run_plan),
            "legacy_or_explicit_opt_out": True,
        }),
        "run_set_id": (run_dir.parent.name if run_dir else None),
        "backbone": (run_dir.name if run_dir else args.backbone),
        "n_replicates": args.replicates,
        "n_task_replicates": len(keys) * args.replicates,
        "uncertainty": {
            "headline_interval": "truth_macro_ci95",
            "method": "deterministic nonparametric bootstrap",
            "cluster": "task",
            "replicates": "kept within task cluster; never sampled as independent tasks",
            "samples": args.bootstrap_samples,
            "seed": args.bootstrap_seed,
        },
        "require_transport_pof": bool(args.require_transport_pof),
        "max_stall_reruns": args.max_stall_reruns,
        "unscorable_lanes": unscorable,
        "n_answer_keys": len(keys),
        "rows": [{k: v for k, v in r.items() if k != "per_task"} for r in rows],
        "per_task": {r["agent"]: r["per_task"] for r in rows},
    }
    out = json.dumps(board, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(out + "\n")
        print(f"wrote {args.out}")
    for r in rows:
        pres = r["presentation"]
        suffix = ""
        if r.get("lane_failed"):
            # Numerator must count runs that never produced a real report: stubs
            # PLUS tasks never recorded (n_missing_runs). The old label used only
            # n_stub_reports, so a lane that recorded 3 and skipped 10 printed
            # "0/3" instead of "10/13". Denominator is the fullest lane's count
            # (n_runs_total + n_missing_runs = expected), not this lane's own.
            n_stub = r.get("n_stub_reports", 0)
            n_missing = r.get("n_missing_runs", 0)
            expected = r.get("n_runs_total", 0) + n_missing
            suffix = f"  [LANE FAILED {n_stub + n_missing}/{expected} runs]"
        print(f"#{r['rank']} {r['agent']:20s} truth={r['truth_macro']:.4f} "
              f"min={r['min_report_truth']:.4f} reports={r.get('n_reports_scored', r['n_tasks'])} "
              f"pres={pres if pres is not None else '-'}{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
