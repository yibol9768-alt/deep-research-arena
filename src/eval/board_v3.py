"""Aggregation for the two explicitly separate DRA v3 score protocols.

The original ``verified_slots_v1`` board remains replayable through
``aggregate_scores``.  The independent ``proof_steps_v1`` board uses only
Partial Completion Rate and Full Pass Rate as headlines.  Replicates are
averaged inside a task first and tasks are then macro-averaged.  Withheld runs
are never converted to zero; a formal board refuses incomplete coverage.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping

from .protocol_manifest_v3 import (
    ProtocolManifestV3Error,
    validate_v3_protocol_manifest,
)
from .protocol_v3 import (
    DIAGNOSTIC_METRICS,
    HEADLINE_METRICS,
    LEGACY_SCORING_SEMANTICS,
    SCORING_SEMANTICS,
    assert_comparable,
    stable_hash,
    validate_proof_steps_protocol,
    validate_protocol,
    validate_verified_slots_protocol,
)


class V3BoardError(ValueError):
    """A score set cannot honestly produce a v3 board."""


_REPLAY_SHA_FIELDS = (
    "report_sha256",
    "observation_ledger_sha256",
    "case_artifact_sha256",
    "public_task_sha256",
    "protocol_manifest_sha256",
    "corpus_registry_hash",
    "scoring_input_sha256",
)

_FORMAL_PROOF_FORBIDDEN_ALIASES = {
    "slot_results",
    "required_slot_ids",
    "tp",
    "fn",
    "fp",
    "precision",
    "recall",
    "f1",
    "verified_precision",
    "verified_recall",
    "verified_f1",
    "verified_research_completion",
    "research_subgoal_results",
    "research_completion_diagnostics",
    "evidence_completion",
    "bridge_completion",
    "decision_completion",
    "task_pass",
    "legacy_compatibility_aliases",
}


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _canonical_json_digest(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _validate_replay_identity(
    rec: Mapping,
    base_protocol: Mapping,
    manifest: Mapping,
    key: tuple[str, str, int],
) -> dict[str, object]:
    agent, task_id, replicate = key
    run_id = rec.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise V3BoardError(f"{key}: formal scored record missing run_id")
    for field in _REPLAY_SHA_FIELDS:
        if not _is_sha256(rec.get(field)):
            raise V3BoardError(
                f"{key}: formal scored record has invalid {field}"
            )
    if rec["corpus_registry_hash"] != base_protocol.get("corpus_registry_hash"):
        raise V3BoardError(
            f"{key}: score corpus_registry_hash disagrees with protocol stamp"
        )
    expected_bindings = {
        "case_artifact_sha256": manifest["case_hashes"][task_id],
        "public_task_sha256": manifest["public_task_hashes"][task_id],
        "protocol_manifest_sha256": manifest["manifest_sha256"],
    }
    for field, expected_value in expected_bindings.items():
        if rec[field] != expected_value:
            raise V3BoardError(
                f"{key}: score {field} disagrees with the validated protocol manifest"
            )
    identity = {
        "run_id": run_id,
        "agent": agent,
        "task_id": task_id,
        "replicate": replicate,
        "cluster_id": rec["cluster_id"],
        "report_sha256": rec["report_sha256"],
        "observation_ledger_sha256": rec["observation_ledger_sha256"],
        "case_artifact_sha256": rec["case_artifact_sha256"],
        "public_task_sha256": rec["public_task_sha256"],
        "protocol_manifest_sha256": rec["protocol_manifest_sha256"],
        "corpus_registry_hash": rec["corpus_registry_hash"],
    }
    expected = _canonical_json_digest({
        "version": "dra_v3_scoring_input_v2",
        **identity,
    })
    if rec["scoring_input_sha256"] != expected:
        raise V3BoardError(
            f"{key}: scoring_input_sha256 does not match replay identity"
        )
    return identity


def _agent(rec: Mapping, *, formal: bool) -> str:
    value = rec.get("agent")
    if not formal:
        value = value or rec.get("lane") or rec.get("framework")
    if not value:
        label = "agent" if formal else "agent/lane/framework"
        raise V3BoardError(f"score record missing {label}")
    if formal and (not isinstance(value, str) or not value.strip()):
        raise V3BoardError("formal score record agent must be a non-empty string")
    return str(value)


def _replicate(rec: Mapping, *, formal: bool) -> int | str:
    if formal:
        if "replicate" not in rec:
            raise V3BoardError("formal score record missing explicit replicate")
        value = rec["replicate"]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise V3BoardError(
                "formal score record replicate must be a positive integer"
            )
        return value
    return str(rec.get("replicate", rec.get("rep", 1)))


def _expected_agents(values: Iterable[str] | None, *, formal: bool) -> list[str] | None:
    if values is None:
        if formal:
            raise V3BoardError("formal board requires explicit expected_agents")
        return None
    result = list(values)
    if not result or any(not isinstance(value, str) or not value.strip() for value in result):
        raise V3BoardError("expected_agents must be a non-empty list of strings")
    if len(set(result)) != len(result):
        raise V3BoardError("expected_agents must be unique")
    return sorted(result)


def _expected_replicates(
    values: Iterable[int] | None, *, formal: bool
) -> list[int] | None:
    if values is None:
        if formal:
            raise V3BoardError("formal board requires explicit expected_replicates")
        return None
    result = list(values)
    if (
        not result
        or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
               for value in result)
    ):
        raise V3BoardError(
            "expected_replicates must be a non-empty list of positive integers"
        )
    if len(set(result)) != len(result):
        raise V3BoardError("expected_replicates must be unique")
    return sorted(result)


def _status(rec: Mapping) -> str:
    raw = str(rec.get("status") or "scored").lower()
    return "withheld" if raw in {"withhold", "withheld", "unscorable"} else raw


def _metric(rec: Mapping, key: str) -> float:
    value = rec.get(key)
    if value is None and isinstance(rec.get("metrics"), Mapping):
        value = rec["metrics"].get(key)
    if isinstance(value, bool):
        return float(value)
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise V3BoardError(f"scored record has invalid {key}: {value!r}")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise V3BoardError(f"{key} outside [0,1]: {value!r}")
    return value


def _diagnostic(rec: Mapping, key: str, default=None):
    value = rec.get(key, default)
    if value is default and isinstance(rec.get("diagnostics"), Mapping):
        value = rec["diagnostics"].get(key, default)
    return value


def _ci(values: list[float]) -> list[float] | None:
    if not values:
        return None
    values = sorted(values)
    lo = values[int(0.025 * (len(values) - 1))]
    hi = values[int(0.975 * (len(values) - 1))]
    return [round(lo, 6), round(hi, 6)]


def _cluster_bootstrap(
    task_rows: list[dict], *, samples: int, seed: int
) -> tuple[list[float], list[float], list[float]]:
    by_cluster: dict[str, list[dict]] = defaultdict(list)
    for row in task_rows:
        by_cluster[row["cluster_id"]].append(row)
    clusters = sorted(by_cluster)
    if not clusters or samples <= 0:
        return [], [], []
    rng = random.Random(seed)
    completion, solve, f1 = [], [], []
    for _ in range(samples):
        sampled = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        rows = [r for cluster in sampled for r in by_cluster[cluster]]
        completion.append(
            math.fsum(r["verified_research_completion"] for r in rows) / len(rows)
        )
        solve.append(math.fsum(r["task_pass"] for r in rows) / len(rows))
        f1.append(math.fsum(r["verified_f1"] for r in rows) / len(rows))
    return completion, solve, f1


def aggregate_scores(
    records: Iterable[Mapping],
    *,
    protocol_manifest: Mapping | None = None,
    expected_agents: Iterable[str] | None = None,
    expected_tasks: Iterable[str] | None = None,
    expected_replicates: Iterable[int] | None = None,
    require_complete: bool = True,
    bootstrap_samples: int = 2000,
    bootstrap_seed: int = 1729,
) -> dict:
    """Build a v3 board from per-run score records.

    Every input must carry a comparable v3 ``protocols`` block.  A formal call
    requires a validated full protocol manifest plus explicit agent and
    replicate axes.  It refuses any missing or withheld cell in the resulting
    agent by task by replicate grid.  Diagnostic mode may omit those formal
    inputs and excludes missing or withheld observations from denominators.
    """

    records = [dict(r) for r in records]
    if not records:
        raise V3BoardError("no score records")
    formal_protocol = bool(require_complete)
    if formal_protocol and (
        isinstance(bootstrap_samples, bool)
        or not isinstance(bootstrap_samples, int)
        or bootstrap_samples <= 0
    ):
        raise V3BoardError("formal board requires bootstrap_samples > 0")

    validated_manifest = None
    if protocol_manifest is not None:
        try:
            validated_manifest = validate_v3_protocol_manifest(protocol_manifest)
        except (ProtocolManifestV3Error, TypeError, ValueError) as exc:
            raise V3BoardError(f"invalid formal protocol manifest: {exc}") from exc
    if formal_protocol and validated_manifest is None:
        raise V3BoardError(
            "formal board requires a complete validated protocol_manifest"
        )

    formal_agents = _expected_agents(expected_agents, formal=formal_protocol)
    formal_replicates = _expected_replicates(
        expected_replicates, formal=formal_protocol
    )
    if validated_manifest is not None:
        try:
            base_protocol = validate_verified_slots_protocol(
                validated_manifest["protocols"], formal=True
            )
        except ValueError as exc:
            raise V3BoardError(
                "verified-slot board requires verified_slots_v1 protocol"
            ) from exc
        for rec in records:
            try:
                assert_comparable(base_protocol, rec, formal=True)
            except ValueError as exc:
                raise V3BoardError(
                    f"score protocol disagrees with validated manifest: {exc}"
                ) from exc
            score_protocol = validate_verified_slots_protocol(rec, formal=True)
            mismatches = [
                field
                for field, value in base_protocol.items()
                if score_protocol.get(field) != value
            ]
            if mismatches:
                raise V3BoardError(
                    "score protocol block does not match validated manifest fields: "
                    + ", ".join(sorted(mismatches))
                )
    else:
        base_protocol = validate_verified_slots_protocol(
            records[0], formal=False
        )
        for rec in records[1:]:
            assert_comparable(base_protocol, rec, formal=False)
    for rec in records:
        if "quality" in rec or "truth" in rec:
            raise V3BoardError("legacy quality/truth fields are forbidden in v3 scores")

    task_universe = set(str(t) for t in (expected_tasks or []))
    if validated_manifest is not None:
        manifest_tasks = set(validated_manifest["task_ids"])
        if expected_tasks is not None and task_universe != manifest_tasks:
            raise V3BoardError(
                "expected task universe does not match the validated protocol manifest"
            )
        task_universe = manifest_tasks
    elif not task_universe:
        task_universe = {str(r.get("task_id") or "") for r in records}
        task_universe.discard("")
    if not task_universe:
        raise V3BoardError("no task ids")
    stamped_count = base_protocol.get("n_tasks")
    stamped_hash = base_protocol.get("task_set_hash")
    if expected_tasks is not None:
        if stamped_count != len(task_universe) or stamped_hash != stable_hash(task_universe):
            raise V3BoardError(
                "expected task universe does not match the stamped v3 task set"
            )
    elif require_complete and validated_manifest is None and (
        stamped_count != len(task_universe)
        or stamped_hash != stable_hash(task_universe)
    ):
        raise V3BoardError(
            "formal board inputs do not cover the complete stamped v3 task set"
        )

    expected_agent_set = set(formal_agents or [])
    expected_replicate_set = set(formal_replicates or [])
    seen: set[tuple[str, str, int | str]] = set()
    task_clusters: dict[str, str] = {}
    by_agent_task: dict[tuple[str, str], list[dict]] = defaultdict(list)
    withheld: dict[str, list[dict]] = defaultdict(list)
    agents: set[str] = set(formal_agents or [])
    replay_run_ids: set[str] = set()
    replay_input_hashes: set[str] = set()
    for rec in records:
        agent = _agent(rec, formal=formal_protocol)
        if expected_agent_set and agent not in expected_agent_set:
            raise V3BoardError(
                f"score record agent {agent!r} is outside expected_agents"
            )
        agents.add(agent)
        task_id = str(rec.get("task_id") or "")
        if not task_id:
            raise V3BoardError("score record missing task_id")
        if task_id not in task_universe:
            raise V3BoardError(
                f"score record task_id {task_id!r} is outside the expected task set"
            )
        replicate = _replicate(rec, formal=formal_protocol)
        if expected_replicate_set and replicate not in expected_replicate_set:
            raise V3BoardError(
                f"score record replicate {replicate!r} is outside expected_replicates"
            )
        key = (agent, task_id, replicate)
        if key in seen:
            raise V3BoardError(f"duplicate score record {key}")
        seen.add(key)
        cluster = str(rec.get("cluster_id") or "")
        if not cluster:
            raise V3BoardError(f"{key}: missing evidence subgraph cluster_id")
        if validated_manifest is not None:
            expected_cluster = validated_manifest["task_clusters"][task_id]
            if cluster != expected_cluster:
                raise V3BoardError(
                    f"{key}: cluster_id disagrees with the validated protocol manifest"
                )
        if formal_protocol:
            identity = _validate_replay_identity(
                rec,
                base_protocol,
                validated_manifest,
                (agent, task_id, replicate),
            )
            if identity["run_id"] in replay_run_ids:
                raise V3BoardError(
                    f"{key}: run_id {identity['run_id']!r} is reused"
                )
            replay_run_ids.add(identity["run_id"])
            scoring_input_hash = str(rec["scoring_input_sha256"])
            if scoring_input_hash in replay_input_hashes:
                raise V3BoardError(
                    f"{key}: scoring_input_sha256 is reused across score records"
                )
            replay_input_hashes.add(scoring_input_hash)
        if _status(rec) == "withheld":
            withheld[agent].append({
                "task_id": task_id,
                "replicate": replicate,
                "reason": rec.get("reason") or rec.get("withheld_reason"),
            })
            continue
        if _status(rec) != "scored":
            raise V3BoardError(f"unknown score status {_status(rec)!r}")
        previous_cluster = task_clusters.setdefault(task_id, cluster)
        if previous_cluster != cluster:
            raise V3BoardError(
                f"{task_id}: score records disagree on cluster_id "
                f"{previous_cluster!r} != {cluster!r}"
            )
        task_pass = _metric(rec, "task_pass")
        if task_pass not in {0.0, 1.0}:
            raise V3BoardError(f"{key}: per-run task_pass must be binary")
        fabricated = _diagnostic(rec, "fabricated_citations")
        contradictions = _diagnostic(rec, "critical_contradictions")
        observable = _diagnostic(
            rec,
            "scorer_observability_complete",
            _diagnostic(rec, "observability_complete"),
        )
        if not isinstance(fabricated, int) or isinstance(fabricated, bool) or fabricated < 0:
            raise V3BoardError(f"{key}: missing/invalid fabricated_citations")
        if (not isinstance(contradictions, int) or isinstance(contradictions, bool)
                or contradictions < 0):
            raise V3BoardError(f"{key}: missing/invalid critical_contradictions")
        if observable is not True:
            raise V3BoardError(
                f"{key}: incomplete observability must be withheld, not scored"
            )
        if task_pass and (fabricated or contradictions):
            raise V3BoardError(
                f"{key}: TaskPass=1 contradicts fabricated/critical diagnostics"
            )
        by_agent_task[(agent, task_id)].append({
            "verified_research_completion": _metric(
                rec, "verified_research_completion"
            ),
            "task_pass": task_pass,
            "verified_f1": _metric(rec, "verified_f1"),
            "evidence_completion": _metric(rec, "evidence_completion"),
            "bridge_completion": _metric(rec, "bridge_completion"),
            "decision_completion": _metric(rec, "decision_completion"),
            "cluster_id": cluster,
            "fabricated_citations": fabricated,
            "critical_contradictions": contradictions,
        })

    rows = []
    incomplete = []
    for agent in sorted(agents):
        task_rows = []
        missing = []
        missing_grid = []
        for task_id in sorted(task_universe):
            reps = by_agent_task.get((agent, task_id), [])
            if formal_protocol:
                for replicate in formal_replicates or []:
                    if (agent, task_id, replicate) not in seen:
                        missing_grid.append({
                            "task_id": task_id,
                            "replicate": replicate,
                        })
            if not reps:
                missing.append(task_id)
                continue
            clusters = {r["cluster_id"] for r in reps}
            if len(clusters) != 1:
                raise V3BoardError(
                    f"{agent}/{task_id}: replicates disagree on cluster_id {clusters}"
                )
            task_rows.append({
                "task_id": task_id,
                "cluster_id": next(iter(clusters)),
                "n_replicates": len(reps),
                "verified_research_completion": math.fsum(
                    r["verified_research_completion"] for r in reps
                ) / len(reps),
                "task_pass": math.fsum(r["task_pass"] for r in reps) / len(reps),
                "verified_f1": math.fsum(r["verified_f1"] for r in reps) / len(reps),
                "evidence_completion": math.fsum(
                    r["evidence_completion"] for r in reps
                ) / len(reps),
                "bridge_completion": math.fsum(
                    r["bridge_completion"] for r in reps
                ) / len(reps),
                "decision_completion": math.fsum(
                    r["decision_completion"] for r in reps
                ) / len(reps),
                "fabricated_citations": sum(r["fabricated_citations"] for r in reps),
                "critical_contradictions": sum(
                    r["critical_contradictions"] for r in reps
                ),
            })
        if missing or missing_grid or withheld.get(agent):
            incomplete.append({
                "agent": agent,
                "missing_tasks": missing,
                "missing_grid_cells": missing_grid,
                "withheld": withheld.get(agent, []),
            })
        if not task_rows:
            continue
        completion_samples, solve_samples, f1_samples = _cluster_bootstrap(
            task_rows,
            samples=bootstrap_samples,
            seed=bootstrap_seed,
        )
        completion_ci = _ci(completion_samples)
        solve_ci = _ci(solve_samples)
        f1_ci = _ci(f1_samples)
        if formal_protocol and any(value is None for value in (completion_ci, solve_ci, f1_ci)):
            raise V3BoardError("formal board confidence intervals must be non-null")
        rows.append({
            "agent": agent,
            "n_attributable_tasks": len(task_rows),
            "verified_research_completion": round(
                math.fsum(
                    r["verified_research_completion"] for r in task_rows
                ) / len(task_rows),
                6,
            ),
            "task_solve_rate": round(
                math.fsum(r["task_pass"] for r in task_rows) / len(task_rows), 6
            ),
            "macro_verified_f1": round(
                math.fsum(r["verified_f1"] for r in task_rows) / len(task_rows), 6
            ),
            "macro_evidence_completion": round(
                math.fsum(r["evidence_completion"] for r in task_rows)
                / len(task_rows),
                6,
            ),
            "macro_bridge_completion": round(
                math.fsum(r["bridge_completion"] for r in task_rows)
                / len(task_rows),
                6,
            ),
            "macro_decision_completion": round(
                math.fsum(r["decision_completion"] for r in task_rows)
                / len(task_rows),
                6,
            ),
            "verified_research_completion_ci95": completion_ci,
            "task_solve_rate_ci95": solve_ci,
            "macro_verified_f1_ci95": f1_ci,
            "diagnostics": {
                "fabricated_citations": sum(
                    r["fabricated_citations"] for r in task_rows
                ),
                "critical_contradictions": sum(
                    r["critical_contradictions"] for r in task_rows
                ),
            },
            "tasks": task_rows,
        })
    if require_complete and incomplete:
        summary = "; ".join(
            f"{x['agent']}: missing={x['missing_tasks']}, withheld={len(x['withheld'])}"
            for x in incomplete
        )
        raise V3BoardError(
            "formal v3 board requires complete attributable coverage; " + summary
        )
    # The two headline metrics remain visibly separate; this ordering is only a
    # deterministic presentation order and never constructs a weighted rank.
    rows.sort(key=lambda r: (
        -r["verified_research_completion"],
        -r["task_solve_rate"],
        -r["macro_verified_f1"],
        r["agent"],
    ))
    return {
        "schema": "dra_verified_slots_board_v1",
        "formal": formal_protocol,
        "protocols": base_protocol,
        "protocol_manifest_sha256": (
            validated_manifest["manifest_sha256"]
            if validated_manifest is not None
            else None
        ),
        "scorer_implementation_sha256": (
            validated_manifest["scorer_implementation_sha256"]
            if validated_manifest is not None
            else None
        ),
        "formal_grid": (
            {
                "agents": formal_agents,
                "task_ids": sorted(task_universe),
                "replicates": formal_replicates,
                "n_expected_runs": (
                    len(formal_agents or [])
                    * len(task_universe)
                    * len(formal_replicates or [])
                ),
            }
            if formal_protocol
            else None
        ),
        "headline_metrics": [
            "verified_research_completion",
            "task_solve_rate",
        ],
        "diagnostic_metric": "macro_verified_f1",
        "rows": rows,
        "incomplete": incomplete,
        "aggregation": {
            "replicates": "mean within task before task macro-average",
            "task_aggregation": (
                "macro mean of task-level research completion and TaskPass; "
                "no weighted composite"
            ),
            "bootstrap": "evidence-subgraph cluster bootstrap",
            "bootstrap_samples": bootstrap_samples,
            "bootstrap_seed": bootstrap_seed,
            "withheld": "excluded as unobserved; never converted to zero",
            "replay_identity": (
                "formal scored records require a unique run_id and a verified "
                "agent/task/replicate/report/ledger/case/public-task/manifest/registry "
                "scoring-input hash chain"
            ),
        },
    }


def _validate_proof_replay_identity(
    rec: Mapping,
    base_protocol: Mapping,
    manifest: Mapping,
    key: tuple[str, str, int],
) -> dict[str, object]:
    agent, task_id, replicate = key
    run_id = rec.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise V3BoardError(f"{key}: formal proof-step record missing run_id")
    for field in _REPLAY_SHA_FIELDS:
        if not _is_sha256(rec.get(field)):
            raise V3BoardError(
                f"{key}: formal proof-step record has invalid {field}"
            )
    if rec["corpus_registry_hash"] != base_protocol.get("corpus_registry_hash"):
        raise V3BoardError(
            f"{key}: score corpus_registry_hash disagrees with protocol stamp"
        )
    expected_bindings = {
        "case_artifact_sha256": manifest["case_hashes"][task_id],
        "public_task_sha256": manifest["public_task_hashes"][task_id],
        "protocol_manifest_sha256": manifest["manifest_sha256"],
    }
    for field, expected_value in expected_bindings.items():
        if rec[field] != expected_value:
            raise V3BoardError(
                f"{key}: score {field} disagrees with the validated protocol manifest"
            )
    identity = {
        "run_id": run_id,
        "agent": agent,
        "task_id": task_id,
        "replicate": replicate,
        "cluster_id": rec["cluster_id"],
        "report_sha256": rec["report_sha256"],
        "observation_ledger_sha256": rec["observation_ledger_sha256"],
        "case_artifact_sha256": rec["case_artifact_sha256"],
        "public_task_sha256": rec["public_task_sha256"],
        "protocol_manifest_sha256": rec["protocol_manifest_sha256"],
        "corpus_registry_hash": rec["corpus_registry_hash"],
    }
    expected = _canonical_json_digest({
        "version": "dra_v3_scoring_input_v3",
        **identity,
    })
    if rec["scoring_input_sha256"] != expected:
        raise V3BoardError(
            f"{key}: scoring_input_sha256 does not match proof-step replay identity"
        )
    return identity


def _proof_steps_from_record(
    rec: Mapping, *, key: tuple[str, str, int | str], formal: bool
) -> dict[str, object]:
    if rec.get("scoring_semantics") != SCORING_SEMANTICS:
        raise V3BoardError(
            f"{key}: scored record must declare scoring_semantics={SCORING_SEMANTICS}"
        )
    raw_steps = rec.get("step_results")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise V3BoardError(f"{key}: step_results must be a non-empty array")
    steps: list[dict] = []
    step_ids: list[str] = []
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, Mapping):
            raise V3BoardError(f"{key}: step_results[{index}] must be an object")
        step = dict(raw)
        step_id = step.get("step_id")
        if not isinstance(step_id, str) or not step_id:
            raise V3BoardError(f"{key}: step_results[{index}] requires step_id")
        step_ids.append(step_id)
        if step.get("type") not in {"evidence", "bridge", "decision"}:
            raise V3BoardError(f"{key}: {step_id} has invalid proof-step type")
        if type(step.get("vital")) is not bool:
            raise V3BoardError(f"{key}: {step_id}.vital must be boolean")
        if type(step.get("required")) is not bool:
            raise V3BoardError(f"{key}: {step_id}.required must be boolean")
        if formal and step["required"] is not True:
            raise V3BoardError(
                f"{key}: formal step_results may contain only required proof steps"
            )
        axes = []
        for axis in ("D", "O", "S", "B", "R"):
            if type(step.get(axis)) is not bool:
                raise V3BoardError(f"{key}: {step_id}.{axis} must be boolean")
            axes.append(step[axis])
        if type(step.get("passed")) is not bool or step["passed"] != all(axes):
            raise V3BoardError(
                f"{key}: {step_id}.passed must equal D AND O AND S AND B AND R"
            )
        route_branches = step.get("route_branches", [])
        if (
            not isinstance(route_branches, list)
            or any(
                not isinstance(branch, str) or not branch
                for branch in route_branches
            )
            or len(route_branches) != len(set(route_branches))
        ):
            raise V3BoardError(
                f"{key}: {step_id}.route_branches must be unique non-empty strings"
            )
        steps.append(step)
    if len(step_ids) != len(set(step_ids)):
        raise V3BoardError(f"{key}: step_id values must be unique")

    required = [step for step in steps if step["required"]]
    required_ids = [str(step["step_id"]) for step in required]
    if rec.get("required_step_ids") != required_ids:
        raise V3BoardError(
            f"{key}: required_step_ids must exactly match step_results order"
        )
    m = len(required)
    k = sum(1 for step in required if step["passed"])
    if type(rec.get("required_steps")) is not int or rec["required_steps"] != m:
        raise V3BoardError(f"{key}: required_steps does not equal m_t")
    if type(rec.get("passed_steps")) is not int or rec["passed_steps"] != k:
        raise V3BoardError(f"{key}: passed_steps does not equal k_t")
    expected_partial = k / m if m else 0.0
    partial = _metric(rec, "partial_completion")
    if not math.isclose(partial, expected_partial, rel_tol=0.0, abs_tol=1e-12):
        raise V3BoardError(
            f"{key}: partial_completion must equal passed_steps/required_steps"
        )

    final_steps = [step for step in required if step["type"] == "decision"]
    expected_final = bool(final_steps) and all(step["passed"] for step in final_steps)
    if type(rec.get("final_answer_pass")) is not bool or (
        rec["final_answer_pass"] != expected_final
    ):
        raise V3BoardError(
            f"{key}: final_answer_pass disagrees with final proof step"
        )
    fabricated = _diagnostic(rec, "fabricated_citations")
    contradictions = _diagnostic(rec, "critical_contradictions")
    if (
        not isinstance(fabricated, int)
        or isinstance(fabricated, bool)
        or fabricated < 0
    ):
        raise V3BoardError(f"{key}: missing/invalid fabricated_citations")
    if (
        not isinstance(contradictions, int)
        or isinstance(contradictions, bool)
        or contradictions < 0
    ):
        raise V3BoardError(f"{key}: missing/invalid critical_contradictions")
    expected_full = int(
        all(step["passed"] for step in required if step["vital"])
        and expected_final
        and contradictions == 0
        and fabricated == 0
    )
    full = _metric(rec, "full_pass")
    if full not in {0.0, 1.0} or full != float(expected_full):
        raise V3BoardError(
            f"{key}: full_pass violates vital/final/contradiction/fabrication gates"
        )
    expected_failures: list[dict[str, object]] = []
    vital_failures = [
        str(step["step_id"])
        for step in required
        if step["vital"] and not step["passed"]
    ]
    if vital_failures:
        expected_failures.append({
            "reason_code": "vital_proof_steps_failed",
            "step_ids": vital_failures,
        })
    if not expected_final:
        expected_failures.append({
            "reason_code": "final_answer_contract_failed",
            "step_ids": [str(step["step_id"]) for step in final_steps],
        })
    if contradictions:
        expected_failures.append({
            "reason_code": "critical_contradictions_present",
            "count": contradictions,
        })
    if fabricated:
        expected_failures.append({
            "reason_code": "fabricated_citations_present",
            "count": fabricated,
        })
    if rec.get("full_pass_failure_reasons") != expected_failures:
        raise V3BoardError(
            f"{key}: full_pass_failure_reasons disagree with the exact gates"
        )
    observable = _diagnostic(
        rec,
        "scorer_observability_complete",
        _diagnostic(rec, "observability_complete"),
    )
    if observable is not True:
        raise V3BoardError(
            f"{key}: incomplete observability must be withheld, not scored"
        )

    route = rec.get("route_coverage")
    if not isinstance(route, Mapping) or route.get("metric") != "route_coverage_v1":
        raise V3BoardError(f"{key}: route_coverage_v1 diagnostic is required")
    if route.get("score_bearing") is not False:
        raise V3BoardError(f"{key}: route_coverage must be diagnostic-only")
    overall = route.get("overall")
    if not isinstance(overall, Mapping):
        raise V3BoardError(f"{key}: route_coverage.overall is required")
    expected_overall = {
        "required_steps": m,
        "passed_steps": k,
        "coverage": expected_partial,
    }
    if dict(overall) != expected_overall:
        raise V3BoardError(
            f"{key}: route_coverage.overall disagrees with proof steps"
        )
    by_type = route.get("by_type")
    if not isinstance(by_type, Mapping):
        raise V3BoardError(f"{key}: route_coverage.by_type is required")
    type_coverages: dict[str, float] = {}
    for label, expected_type in (
        ("evidence", "evidence"),
        ("bridge", "bridge"),
        ("final_answer", "decision"),
    ):
        bucket = by_type.get(label)
        if not isinstance(bucket, Mapping):
            raise V3BoardError(f"{key}: route_coverage.by_type.{label} is required")
        type_steps = [step for step in required if step["type"] == expected_type]
        type_passed = sum(1 for step in type_steps if step["passed"])
        expected_bucket = {
            "required_steps": len(type_steps),
            "passed_steps": type_passed,
            "coverage": type_passed / len(type_steps) if type_steps else 0.0,
        }
        if dict(bucket) != expected_bucket:
            raise V3BoardError(
                f"{key}: route_coverage.by_type.{label} disagrees with steps"
            )
        type_coverages[label] = float(expected_bucket["coverage"])

    by_branch = route.get("by_branch")
    if not isinstance(by_branch, Mapping):
        raise V3BoardError(f"{key}: route_coverage.by_branch is required")
    branch_steps: dict[str, list[dict]] = defaultdict(list)
    for step in required:
        for branch in step.get("route_branches", []):
            branch_steps[str(branch)].append(step)
    expected_by_branch = {
        branch: {
            "required_steps": len(rows),
            "passed_steps": sum(1 for row in rows if row["passed"]),
            "coverage": (
                sum(1 for row in rows if row["passed"]) / len(rows)
                if rows
                else 0.0
            ),
        }
        for branch, rows in sorted(branch_steps.items())
    }
    if dict(by_branch) != expected_by_branch:
        raise V3BoardError(
            f"{key}: route_coverage.by_branch disagrees with proof steps"
        )

    acquisition = rec.get("acquisition_diagnostics")
    if (
        not isinstance(acquisition, Mapping)
        or acquisition.get("metric") != "acquisition_diagnostics_v1"
        or acquisition.get("score_bearing") is not False
    ):
        raise V3BoardError(
            f"{key}: acquisition_diagnostics_v1 diagnostic is required"
        )
    acquisition_counts: dict[str, int] = {}
    for field in (
        "required_evidence_steps",
        "discovery_licensed",
        "content_observed",
        "content_supported",
        "guessed_then_fetched",
    ):
        value = acquisition.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise V3BoardError(f"{key}: acquisition_diagnostics.{field} is invalid")
        acquisition_counts[field] = value
    evidence_count = sum(1 for step in required if step["type"] == "evidence")
    evidence_steps = [step for step in required if step["type"] == "evidence"]
    expected_acquisition = {
        "required_evidence_steps": evidence_count,
        "discovery_licensed": sum(1 for step in evidence_steps if step["D"]),
        "content_observed": sum(1 for step in evidence_steps if step["O"]),
        "content_supported": sum(1 for step in evidence_steps if step["S"]),
        "guessed_then_fetched": sum(
            1
            for step in evidence_steps
            if step.get("discovery_class") == "guessed_then_fetched"
        ),
    }
    if acquisition_counts != expected_acquisition:
        raise V3BoardError(
            f"{key}: acquisition diagnostics disagree with evidence-step axes"
        )
    return {
        "partial_completion": partial,
        "full_pass": full,
        "route_by_type": type_coverages,
        "route_by_branch": {
            branch: float(bucket["coverage"])
            for branch, bucket in expected_by_branch.items()
        },
        "acquisition": acquisition_counts,
        "fabricated_citations": fabricated,
        "critical_contradictions": contradictions,
    }


def _cluster_bootstrap_proof(
    task_rows: list[dict], *, samples: int, seed: int
) -> tuple[list[float], list[float]]:
    by_cluster: dict[str, list[dict]] = defaultdict(list)
    for row in task_rows:
        by_cluster[str(row.get("bootstrap_cluster") or row["cluster_id"])].append(row)
    clusters = sorted(by_cluster)
    if not clusters or samples <= 0:
        return [], []
    rng = random.Random(seed)
    partial_samples: list[float] = []
    full_samples: list[float] = []
    for _ in range(samples):
        sampled = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        rows = [row for cluster in sampled for row in by_cluster[cluster]]
        partial_samples.append(
            math.fsum(row["partial_completion"] for row in rows) / len(rows)
        )
        full_samples.append(
            math.fsum(row["full_pass"] for row in rows) / len(rows)
        )
    return partial_samples, full_samples


def aggregate_proof_step_scores(
    records: Iterable[Mapping],
    *,
    protocol_manifest: Mapping | None = None,
    expected_agents: Iterable[str] | None = None,
    expected_tasks: Iterable[str] | None = None,
    expected_replicates: Iterable[int] | None = None,
    require_complete: bool = True,
    bootstrap_samples: int = 2000,
    bootstrap_seed: int = 1729,
) -> dict:
    """Aggregate only ``proof_steps_v1`` scores into the new dual headline."""

    records = [dict(record) for record in records]
    if not records:
        raise V3BoardError("no proof-step score records")
    formal = bool(require_complete)
    if formal and (
        isinstance(bootstrap_samples, bool)
        or not isinstance(bootstrap_samples, int)
        or bootstrap_samples <= 0
    ):
        raise V3BoardError("formal board requires bootstrap_samples > 0")

    validated_manifest = None
    if protocol_manifest is not None:
        try:
            validated_manifest = validate_v3_protocol_manifest(protocol_manifest)
            base_protocol = validate_proof_steps_protocol(
                validated_manifest["protocols"], formal=True
            )
        except (ProtocolManifestV3Error, TypeError, ValueError) as exc:
            raise V3BoardError(f"invalid proof-step protocol manifest: {exc}") from exc
    elif formal:
        raise V3BoardError(
            "formal proof-step board requires a complete validated protocol_manifest"
        )
    else:
        base_protocol = validate_proof_steps_protocol(records[0], formal=False)

    formal_agents = _expected_agents(expected_agents, formal=formal)
    formal_replicates = _expected_replicates(expected_replicates, formal=formal)
    for record in records:
        try:
            assert_comparable(
                base_protocol,
                record,
                formal=validated_manifest is not None,
            )
            score_protocol = validate_proof_steps_protocol(
                record, formal=validated_manifest is not None
            )
        except ValueError as exc:
            raise V3BoardError(f"proof-step score protocol mismatch: {exc}") from exc
        mismatches = [
            field
            for field, value in base_protocol.items()
            if score_protocol.get(field) != value
        ]
        if mismatches:
            raise V3BoardError(
                "proof-step score protocol block does not match manifest: "
                + ", ".join(sorted(mismatches))
            )
        if "quality" in record or "truth" in record:
            raise V3BoardError("legacy quality/truth fields are forbidden")
        if formal:
            present = sorted(_FORMAL_PROOF_FORBIDDEN_ALIASES & set(record))
            if present:
                raise V3BoardError(
                    f"formal proof-step score contains legacy aliases: {present}"
                )

    task_universe = set(str(value) for value in (expected_tasks or []))
    if validated_manifest is not None:
        manifest_tasks = set(validated_manifest["task_ids"])
        if expected_tasks is not None and task_universe != manifest_tasks:
            raise V3BoardError(
                "expected task universe does not match proof-step manifest"
            )
        task_universe = manifest_tasks
    elif not task_universe:
        task_universe = {
            str(record.get("task_id") or "") for record in records
        }
        task_universe.discard("")
    if not task_universe:
        raise V3BoardError("no proof-step task ids")
    if expected_tasks is not None and (
        base_protocol.get("n_tasks") != len(task_universe)
        or base_protocol.get("task_set_hash") != stable_hash(task_universe)
    ):
        raise V3BoardError(
            "expected task universe does not match stamped proof-step task set"
        )

    expected_agent_set = set(formal_agents or [])
    expected_replicate_set = set(formal_replicates or [])
    agents: set[str] = set(formal_agents or [])
    seen: set[tuple[str, str, int | str]] = set()
    withheld: dict[str, list[dict]] = defaultdict(list)
    by_agent_task: dict[tuple[str, str], list[dict]] = defaultdict(list)
    run_ids: set[str] = set()
    input_hashes: set[str] = set()
    for record in records:
        agent = _agent(record, formal=formal)
        if expected_agent_set and agent not in expected_agent_set:
            raise V3BoardError(f"proof-step score agent {agent!r} is unexpected")
        agents.add(agent)
        task_id = str(record.get("task_id") or "")
        if not task_id or task_id not in task_universe:
            raise V3BoardError(
                f"proof-step score task_id {task_id!r} is outside expected tasks"
            )
        replicate = _replicate(record, formal=formal)
        if expected_replicate_set and replicate not in expected_replicate_set:
            raise V3BoardError(
                f"proof-step replicate {replicate!r} is unexpected"
            )
        key = (agent, task_id, replicate)
        if key in seen:
            raise V3BoardError(f"duplicate proof-step score record {key}")
        seen.add(key)
        cluster = str(record.get("cluster_id") or "")
        if not cluster:
            raise V3BoardError(f"{key}: missing cluster_id")
        if validated_manifest is not None and (
            cluster != validated_manifest["task_clusters"][task_id]
        ):
            raise V3BoardError(f"{key}: cluster_id disagrees with manifest")
        if formal:
            identity = _validate_proof_replay_identity(
                record, base_protocol, validated_manifest, key
            )
            if str(identity["run_id"]) in run_ids:
                raise V3BoardError(f"{key}: run_id is reused")
            if str(record["scoring_input_sha256"]) in input_hashes:
                raise V3BoardError(f"{key}: scoring_input_sha256 is reused")
            run_ids.add(str(identity["run_id"]))
            input_hashes.add(str(record["scoring_input_sha256"]))
        status = _status(record)
        if status == "withheld":
            withheld[agent].append({
                "task_id": task_id,
                "replicate": replicate,
                "reasons": list(record.get("withhold_reasons") or []),
            })
            continue
        if status != "scored":
            raise V3BoardError(f"unknown proof-step score status {status!r}")
        metrics = _proof_steps_from_record(record, key=key, formal=formal)
        graph_motif = (
            str(validated_manifest["task_contracts"][task_id]["motif"])
            if validated_manifest is not None
            else str(record.get("graph_motif") or "unspecified")
        )
        by_agent_task[(agent, task_id)].append({
            **metrics,
            "cluster_id": cluster,
            "graph_motif": graph_motif,
            "bootstrap_cluster": f"{cluster}\x1f{graph_motif}",
        })

    rows: list[dict] = []
    incomplete: list[dict] = []
    for agent in sorted(agents):
        task_rows: list[dict] = []
        missing: list[str] = []
        missing_grid: list[dict] = []
        for task_id in sorted(task_universe):
            reps = by_agent_task.get((agent, task_id), [])
            if formal:
                for replicate in formal_replicates or []:
                    if (agent, task_id, replicate) not in seen:
                        missing_grid.append({
                            "task_id": task_id,
                            "replicate": replicate,
                        })
            if not reps:
                missing.append(task_id)
                continue
            clusters = {str(rep["cluster_id"]) for rep in reps}
            if len(clusters) != 1:
                raise V3BoardError(
                    f"{agent}/{task_id}: replicates disagree on cluster_id"
                )
            motifs = {str(rep["graph_motif"]) for rep in reps}
            if len(motifs) != 1:
                raise V3BoardError(
                    f"{agent}/{task_id}: replicates disagree on graph_motif"
                )
            bootstrap_clusters = {
                str(rep["bootstrap_cluster"]) for rep in reps
            }
            if len(bootstrap_clusters) != 1:
                raise V3BoardError(
                    f"{agent}/{task_id}: replicates disagree on bootstrap cluster"
                )
            route_labels = ("evidence", "bridge", "final_answer")
            branch_sets = {
                tuple(sorted(str(branch) for branch in rep["route_by_branch"]))
                for rep in reps
            }
            if len(branch_sets) != 1:
                raise V3BoardError(
                    f"{agent}/{task_id}: replicates disagree on route branches"
                )
            route_branches = list(next(iter(branch_sets)))
            acquisition_fields = (
                "required_evidence_steps",
                "discovery_licensed",
                "content_observed",
                "content_supported",
                "guessed_then_fetched",
            )
            task_rows.append({
                "task_id": task_id,
                "cluster_id": next(iter(clusters)),
                "graph_motif": next(iter(motifs)),
                "bootstrap_cluster": next(iter(bootstrap_clusters)),
                "n_replicates": len(reps),
                "partial_completion": math.fsum(
                    float(rep["partial_completion"]) for rep in reps
                ) / len(reps),
                "full_pass": math.fsum(
                    float(rep["full_pass"]) for rep in reps
                ) / len(reps),
                "route_coverage": {
                    "by_type": {
                        label: math.fsum(
                            float(rep["route_by_type"][label]) for rep in reps
                        ) / len(reps)
                        for label in route_labels
                    },
                    "by_branch": {
                        branch: math.fsum(
                            float(rep["route_by_branch"][branch]) for rep in reps
                        ) / len(reps)
                        for branch in route_branches
                    },
                },
                "acquisition_diagnostics": {
                    field: sum(
                        int(rep["acquisition"][field]) for rep in reps
                    )
                    for field in acquisition_fields
                },
                "fabricated_citations": sum(
                    int(rep["fabricated_citations"]) for rep in reps
                ),
                "critical_contradictions": sum(
                    int(rep["critical_contradictions"]) for rep in reps
                ),
            })
        if missing or missing_grid or withheld.get(agent):
            incomplete.append({
                "agent": agent,
                "missing_tasks": missing,
                "missing_grid_cells": missing_grid,
                "withheld": withheld.get(agent, []),
            })
        if not task_rows:
            continue
        partial_samples, full_samples = _cluster_bootstrap_proof(
            task_rows, samples=bootstrap_samples, seed=bootstrap_seed
        )
        partial_ci = _ci(partial_samples)
        full_ci = _ci(full_samples)
        if formal and (partial_ci is None or full_ci is None):
            raise V3BoardError("formal proof-step confidence intervals are required")
        route_labels = ("evidence", "bridge", "final_answer")
        all_route_branches = sorted({
            branch
            for task_row in task_rows
            for branch in task_row["route_coverage"]["by_branch"]
        })
        acquisition_fields = (
            "required_evidence_steps",
            "discovery_licensed",
            "content_observed",
            "content_supported",
            "guessed_then_fetched",
        )
        rows.append({
            "agent": agent,
            "n_attributable_tasks": len(task_rows),
            "partial_completion_rate": round(
                math.fsum(row["partial_completion"] for row in task_rows)
                / len(task_rows),
                6,
            ),
            "full_pass_rate": round(
                math.fsum(row["full_pass"] for row in task_rows)
                / len(task_rows),
                6,
            ),
            "partial_completion_rate_ci95": partial_ci,
            "full_pass_rate_ci95": full_ci,
            "diagnostics": {
                "route_coverage": {
                    "by_type": {
                        label: round(
                            math.fsum(
                                row["route_coverage"]["by_type"][label]
                                for row in task_rows
                            ) / len(task_rows),
                            6,
                        )
                        for label in route_labels
                    },
                    "by_branch": {
                        branch: {
                            "coverage": round(
                                math.fsum(
                                    row["route_coverage"]["by_branch"][branch]
                                    for row in task_rows
                                    if branch in row["route_coverage"]["by_branch"]
                                )
                                / sum(
                                    1
                                    for row in task_rows
                                    if branch in row["route_coverage"]["by_branch"]
                                ),
                                6,
                            ),
                            "n_tasks": sum(
                                1
                                for row in task_rows
                                if branch in row["route_coverage"]["by_branch"]
                            ),
                        }
                        for branch in all_route_branches
                    },
                },
                "acquisition_diagnostics": {
                    field: sum(
                        row["acquisition_diagnostics"][field]
                        for row in task_rows
                    )
                    for field in acquisition_fields
                },
                "fabricated_citations": sum(
                    row["fabricated_citations"] for row in task_rows
                ),
                "critical_contradictions": sum(
                    row["critical_contradictions"] for row in task_rows
                ),
            },
            "tasks": task_rows,
        })
    if formal and incomplete:
        summary = "; ".join(
            f"{item['agent']}: missing={item['missing_tasks']}, "
            f"withheld={len(item['withheld'])}"
            for item in incomplete
        )
        raise V3BoardError(
            "formal proof-step board requires complete attributable coverage; "
            + summary
        )
    rows.sort(key=lambda row: (
        -row["partial_completion_rate"],
        -row["full_pass_rate"],
        row["agent"],
    ))
    return {
        "schema": "dra_proof_steps_board_v1",
        "formal": formal,
        "protocols": base_protocol,
        "protocol_manifest_sha256": (
            validated_manifest["manifest_sha256"]
            if validated_manifest is not None
            else None
        ),
        "scorer_implementation_sha256": (
            validated_manifest["scorer_implementation_sha256"]
            if validated_manifest is not None
            else None
        ),
        "formal_grid": (
            {
                "agents": formal_agents,
                "task_ids": sorted(task_universe),
                "replicates": formal_replicates,
                "n_expected_runs": (
                    len(formal_agents or [])
                    * len(task_universe)
                    * len(formal_replicates or [])
                ),
            }
            if formal
            else None
        ),
        "headline_metrics": list(HEADLINE_METRICS),
        "diagnostic_metrics": list(DIAGNOSTIC_METRICS),
        "rows": rows,
        "incomplete": incomplete,
        "aggregation": {
            "replicates": "mean within task before task macro-average",
            "task_aggregation": (
                "macro mean of task PartialCompletion and FullPass; no weights"
            ),
            "bootstrap": "topic_cluster x graph_motif cluster bootstrap",
            "bootstrap_samples": bootstrap_samples,
            "bootstrap_seed": bootstrap_seed,
            "withheld": "excluded as unobserved; never converted to zero",
            "route_coverage": "diagnostic-only; never enters either headline",
            "replay_identity": (
                "formal records bind agent/task/replicate/report/ledger/case/"
                "public-task/manifest/registry under dra_v3_scoring_input_v3"
            ),
        },
    }


__all__ = [
    "V3BoardError",
    "aggregate_scores",
    "aggregate_proof_step_scores",
]
