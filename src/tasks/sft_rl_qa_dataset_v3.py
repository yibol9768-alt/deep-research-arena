"""Build graph-derived SFT QA and replay-scored RL QA for DRA v3.

The builder deliberately distinguishes three kinds of supervision:

* full-report SFT targets are exact machine-oracle reports replayed by the
  production proof-step scorer;
* proof-step SFT targets are teacher-forced derivations from those replayed
  step matches and their actually observed source content; and
* RL records are complete oracle/adversarial reports with scorer outcomes and
  observation-ledger lineage, but not fabricated assistant action traces.

All currently available source suites are synthetic mechanism fixtures.  The
caller must explicitly opt in, and the manifest prevents treating the export
as human-validated or held-out benchmark evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.eval.oracle_validation_v3 import REQUIRED_ADVERSARIAL_CATEGORIES

from .benchmark_sft_dataset_v3 import DEFAULT_SYSTEM_PROMPT, DatasetBuildError


DATASET_SCHEMA = "dra_v3_sft_rl_qa_dataset_v1"
FULL_SFT_SCHEMA = "dra_v3_full_report_sft_qa_v1"
PROOF_SFT_SCHEMA = "dra_v3_proof_step_sft_qa_v1"
RL_QA_SCHEMA = "dra_v3_replay_scored_rl_qa_v1"
PREFERENCE_SCHEMA = "dra_v3_replay_preference_pair_v1"
CASE_PROVENANCE_SCHEMA = "dra_v3_sft_rl_case_provenance_v1"

SUITE_GLOBS = (
    "*/oracle_suite/suite.json",
    "*/oracle_suites/synthetic/suite.json",
)

EVIDENCE_SYSTEM_PROMPT = (
    "You write one evidence-grounded research statement from an observed "
    "source. Use only the supplied source content, preserve seller, community, "
    "model, date, and uncertainty scope, and cite the supplied URL inline."
)
BRIDGE_SYSTEM_PROMPT = (
    "You synthesize a bounded intermediate research conclusion from verified "
    "premises. Do not introduce facts that are absent from the premises, and "
    "state important limitations or unresolved conditions."
)
DECISION_SYSTEM_PROMPT = (
    "You make a conditional evidence-bounded decision from verified research "
    "premises and the user's constraints. Do not invent missing facts or name "
    "a universal winner when the evidence only supports a test, deferral, or "
    "conditional choice."
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class BuildOptions:
    allow_synthetic: bool = False
    allow_intentional_overlap: bool = False


@dataclass
class _CaseBundle:
    candidates_root: Path
    case_root: Path
    suite_path: Path
    suite_dir: Path
    suite_raw: bytes
    suite: dict[str, Any]
    validation_path: Path
    validation_raw: bytes
    validation: dict[str, Any]
    public_path: Path
    public_raw: bytes
    public_task: dict[str, Any]
    case_path: Path
    case_raw: bytes
    case: dict[str, Any]
    graph_path: Path
    graph_raw: bytes
    protocol_path: Path
    protocol_raw: bytes
    query: str
    task_id: str
    synthetic_only: bool
    machine_entry: dict[str, Any]
    machine_result: dict[str, Any]
    machine_report_path: Path
    machine_report_raw: bytes
    machine_report: str
    machine_ledger_path: Path
    machine_ledger_raw: bytes
    machine_ledger: dict[str, Any]


def build_sft_rl_qa_dataset(
    candidates_root: str | Path,
    output_dir: str | Path,
    *,
    options: BuildOptions | None = None,
) -> dict[str, Any]:
    """Build all SFT and RL QA artifacts and return their manifest."""

    opts = options or BuildOptions()
    if not opts.allow_intentional_overlap:
        raise DatasetBuildError(
            "this pilot reuses source cases for SFT and RL/evaluation; set "
            "allow_intentional_overlap=True to acknowledge the overlap"
        )

    source_root = Path(candidates_root).resolve()
    suite_paths = sorted(
        {
            path
            for pattern in SUITE_GLOBS
            for path in source_root.glob(pattern)
        }
    )
    if not suite_paths:
        raise DatasetBuildError(f"no oracle suites found below {source_root}")

    bundles: list[_CaseBundle] = []
    skipped_synthetic = 0
    for suite_path in suite_paths:
        bundle = _load_bundle(
            suite_path,
            candidates_root=source_root,
            allow_synthetic=opts.allow_synthetic,
        )
        if bundle is None:
            skipped_synthetic += 1
            continue
        bundles.append(bundle)
    if not bundles:
        suffix = (
            "; pass allow_synthetic=True for the explicitly labelled pilot"
            if skipped_synthetic
            else ""
        )
        raise DatasetBuildError(f"no eligible validated suites{suffix}")

    task_ids = [bundle.task_id for bundle in bundles]
    if len(task_ids) != len(set(task_ids)):
        duplicates = sorted(
            task_id for task_id in set(task_ids) if task_ids.count(task_id) > 1
        )
        raise DatasetBuildError(f"duplicate task ids across suites: {duplicates}")

    full_sft: list[dict[str, Any]] = []
    proof_sft: list[dict[str, Any]] = []
    rl_qa: list[dict[str, Any]] = []
    preferences: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []

    for bundle in bundles:
        full_record = _full_sft_record(bundle)
        full_sft.append(full_record)
        proof_sft.extend(_proof_sft_records(bundle))
        case_rl, case_preferences = _rl_records(bundle)
        rl_qa.extend(case_rl)
        preferences.extend(case_preferences)
        provenance.append(_case_provenance(bundle, case_rl))

    full_sft.sort(key=lambda row: str(row["example_id"]))
    proof_sft.sort(key=lambda row: str(row["example_id"]))
    rl_qa.sort(key=lambda row: str(row["candidate_id"]))
    preferences.sort(key=lambda row: str(row["pair_id"]))
    provenance.sort(key=lambda row: str(row["task_id"]))

    all_sft = [*full_sft, *proof_sft]
    all_sft.sort(key=lambda row: str(row["example_id"]))
    proof_counts: dict[str, int] = {"evidence": 0, "bridge": 0, "decision": 0}
    for row in proof_sft:
        proof_counts[str(row["sample_type"])] += 1
    rl_kind_counts = {
        "oracle_positive": sum(row["candidate_kind"] == "oracle" for row in rl_qa),
        "adversarial_negative": sum(
            row["candidate_kind"] == "adversarial" for row in rl_qa
        ),
    }

    serialized = {
        "sft_full_qa.jsonl": _jsonl_bytes(full_sft),
        "sft_proof_qa.jsonl": _jsonl_bytes(proof_sft),
        "sft_all_messages.jsonl": _jsonl_bytes(
            [{"messages": row["messages"]} for row in all_sft]
        ),
        "rl_scored_qa.jsonl": _jsonl_bytes(rl_qa),
        "rl_preference_pairs.jsonl": _jsonl_bytes(preferences),
        "case_provenance.jsonl": _jsonl_bytes(provenance),
    }
    artifacts = {
        name: {"bytes": len(payload), "sha256": _sha256(payload)}
        for name, payload in serialized.items()
    }
    fingerprint_basis = b"".join(
        name.encode("utf-8") + b"\0" + serialized[name]
        for name in sorted(serialized)
    )
    dataset_sha256 = _sha256(fingerprint_basis)
    synthetic_count = sum(bundle.synthetic_only for bundle in bundles)

    manifest: dict[str, Any] = {
        "schema": DATASET_SCHEMA,
        "dataset_id": f"dra-v3-sft-rl-qa-{dataset_sha256[:16]}",
        "dataset_sha256": dataset_sha256,
        "source": {
            "candidates_root": _portable_path(source_root),
            "suite_globs": list(SUITE_GLOBS),
            "requires_replay_validation_status": "validated",
            "requires_machine_oracle_full_pass": 1,
            "synthetic_sources_allowed": bool(opts.allow_synthetic),
        },
        "counts": {
            "source_cases": len(bundles),
            "synthetic_source_cases": synthetic_count,
            "human_validated_source_cases": len(bundles) - synthetic_count,
            "sft_full_qa": len(full_sft),
            "sft_proof_qa": len(proof_sft),
            "sft_all": len(all_sft),
            "proof_evidence": proof_counts["evidence"],
            "proof_bridge": proof_counts["bridge"],
            "proof_decision": proof_counts["decision"],
            "rl_scored_qa": len(rl_qa),
            "rl_oracle_positive": rl_kind_counts["oracle_positive"],
            "rl_adversarial_negative": rl_kind_counts["adversarial_negative"],
            "rl_preference_pairs": len(preferences),
            "skipped_synthetic_suites": skipped_synthetic,
        },
        "supervision_contract": {
            "full_sft": "exact_report_replayed_by_proof_steps_v1",
            "proof_sft": (
                "teacher_forced_derivation_from_replayed_step_matches_and_"
                "observed_source_content"
            ),
            "rl_qa": "report_plus_replayed_scorer_outcome_and_ledger_reference",
            "rl_preference": "machine_full_pass_preferred_over_each_adversarial_run",
            "assistant_action_trace_available": False,
            "observation_ledger_available_by_reference": True,
        },
        "reward_contract": {
            "no_arbitrary_combined_scalar": True,
            "available_components": [
                "partial_completion",
                "full_pass",
                "grounding_gate_pass",
                "fabricated_citations",
                "critical_contradictions",
            ],
        },
        "overlap_and_release": {
            "exact_source_task_overlap": True,
            "formal_benchmark_eligible": False,
            "generalization_claim_allowed": False,
            "human_validity_claim_allowed": synthetic_count == 0,
        },
        "artifacts": artifacts,
    }

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for name, payload in serialized.items():
        _atomic_write(destination / name, payload)
    _atomic_write(
        destination / "manifest.json",
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
    )
    return manifest


def _load_bundle(
    suite_path: Path,
    *,
    candidates_root: Path,
    allow_synthetic: bool,
) -> _CaseBundle | None:
    suite_dir = suite_path.parent
    relative = suite_path.resolve().relative_to(candidates_root.resolve())
    case_root = candidates_root / relative.parts[0]
    suite_raw = suite_path.read_bytes()
    suite = _json_object(suite_raw, label=str(suite_path))
    validation_path = suite_dir / "validation.json"
    if not validation_path.is_file():
        raise DatasetBuildError(f"missing validation.json for {suite_path}")
    validation_raw = validation_path.read_bytes()
    validation = _json_object(validation_raw, label=str(validation_path))
    if validation.get("status") != "validated":
        raise DatasetBuildError(f"suite is not validated: {suite_path}")
    if validation.get("suite_sha256") != _sha256(suite_raw):
        raise DatasetBuildError(f"validation/suite hash mismatch: {suite_path}")
    synthetic_only = bool(validation.get("synthetic_only")) or str(
        validation.get("validation_scope") or suite.get("validation_scope") or ""
    ) == "synthetic_test"
    if synthetic_only and not allow_synthetic:
        return None

    case_path, case_raw = _artifact(suite_dir, suite.get("case"), label="case")
    graph_path, graph_raw = _artifact(
        suite_dir, suite.get("evidence_graph"), label="evidence_graph"
    )
    public_path, public_raw = _artifact(
        suite_dir, suite.get("public_task"), label="public_task"
    )
    protocol_path, protocol_raw = _artifact(
        suite_dir, suite.get("protocols"), label="protocol"
    )
    case = _json_object(case_raw, label=str(case_path))
    public_task = _json_object(public_raw, label=str(public_path))
    query = _query_from_public_task(public_task, public_path)
    task_id = str(public_task.get("task_id") or validation.get("task_id") or "")
    if not task_id or task_id != str(validation.get("task_id") or task_id):
        raise DatasetBuildError(f"task_id mismatch for {suite_path}")

    machine_entries = [
        dict(row)
        for row in suite.get("oracles") or []
        if isinstance(row, Mapping) and row.get("kind") == "machine"
    ]
    machine_results = [
        dict(row)
        for row in validation.get("oracle_results") or []
        if isinstance(row, Mapping) and row.get("kind") == "machine"
    ]
    if len(machine_entries) != 1 or len(machine_results) != 1:
        raise DatasetBuildError(f"{task_id} requires one machine oracle and result")
    machine_entry = machine_entries[0]
    machine_result = machine_results[0]
    if machine_entry.get("run_id") != machine_result.get("run_id"):
        raise DatasetBuildError(f"machine oracle/result run mismatch for {task_id}")
    machine_report_path, machine_report_raw = _artifact(
        suite_dir, machine_entry.get("report"), label="machine_report"
    )
    machine_ledger_path, machine_ledger_raw = _artifact(
        suite_dir, machine_entry.get("ledger"), label="machine_ledger"
    )
    result_report = machine_result.get("report_artifact")
    if not isinstance(result_report, Mapping) or result_report.get("sha256") != _sha256(
        machine_report_raw
    ):
        raise DatasetBuildError(f"machine validation report mismatch for {task_id}")
    machine_score = machine_result.get("score")
    if not isinstance(machine_score, Mapping):
        raise DatasetBuildError(f"machine score missing for {task_id}")
    _require_clean_machine_score(machine_score, task_id=task_id)
    machine_ledger = _json_object(machine_ledger_raw, label=str(machine_ledger_path))
    if machine_ledger.get("capture_complete") is not True:
        raise DatasetBuildError(f"machine ledger is incomplete for {task_id}")

    return _CaseBundle(
        candidates_root=candidates_root,
        case_root=case_root,
        suite_path=suite_path,
        suite_dir=suite_dir,
        suite_raw=suite_raw,
        suite=suite,
        validation_path=validation_path,
        validation_raw=validation_raw,
        validation=validation,
        public_path=public_path,
        public_raw=public_raw,
        public_task=public_task,
        case_path=case_path,
        case_raw=case_raw,
        case=case,
        graph_path=graph_path,
        graph_raw=graph_raw,
        protocol_path=protocol_path,
        protocol_raw=protocol_raw,
        query=query,
        task_id=task_id,
        synthetic_only=synthetic_only,
        machine_entry=machine_entry,
        machine_result=machine_result,
        machine_report_path=machine_report_path,
        machine_report_raw=machine_report_raw,
        machine_report=machine_report_raw.decode("utf-8").strip(),
        machine_ledger_path=machine_ledger_path,
        machine_ledger_raw=machine_ledger_raw,
        machine_ledger=machine_ledger,
    )


def _full_sft_record(bundle: _CaseBundle) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": bundle.query},
        {"role": "assistant", "content": bundle.machine_report},
    ]
    return {
        "schema": FULL_SFT_SCHEMA,
        "example_id": f"{bundle.task_id}::full_report",
        "task_id": bundle.task_id,
        "sample_type": "full_report",
        "question": bundle.query,
        "answer": bundle.machine_report,
        "messages": messages,
        "metadata": {
            "cluster_id": bundle.public_task.get("cluster_id"),
            "motif": bundle.public_task.get("motif"),
            "label_status": "synthetic_replayed_machine_oracle"
            if bundle.synthetic_only
            else "human_validated_replayed_machine_oracle",
            "query_sha256": _sha256(bundle.query.encode("utf-8")),
            "answer_sha256": _sha256(bundle.machine_report.encode("utf-8")),
            "full_pass": 1,
            "partial_completion": 1.0,
        },
    }


def _proof_sft_records(bundle: _CaseBundle) -> list[dict[str, Any]]:
    score = bundle.machine_result["score"]
    raw_rows = score.get("step_results")
    if not isinstance(raw_rows, list):
        raise DatasetBuildError(f"machine step_results missing for {bundle.task_id}")
    rows = [dict(row) for row in raw_rows if isinstance(row, Mapping)]
    row_by_id = {str(row.get("step_id")): row for row in rows}
    if len(row_by_id) != len(rows):
        raise DatasetBuildError(f"duplicate proof step ids for {bundle.task_id}")
    for row in rows:
        if row.get("passed") is not True or not str(row.get("matched_text") or "").strip():
            raise DatasetBuildError(
                f"machine proof target is not passed/matched: "
                f"{bundle.task_id}/{row.get('step_id')}"
            )

    evaluator = bundle.case.get("evaluator_view")
    raw_specs = evaluator.get("required_proof_steps") if isinstance(evaluator, Mapping) else None
    if not isinstance(raw_specs, list):
        raise DatasetBuildError(f"case proof specs missing for {bundle.task_id}")
    spec_by_id = {
        str(spec.get("step_id")): dict(spec)
        for spec in raw_specs
        if isinstance(spec, Mapping)
    }
    if set(spec_by_id) != set(row_by_id):
        raise DatasetBuildError(f"case/score proof step mismatch for {bundle.task_id}")

    requirement_map = _texts_by_step(bundle.case.get("query_requirements"), "slot_ids", "text")
    subgoal_map = _texts_by_step(
        bundle.case.get("research_subgoals"), "requires", "description"
    )
    events = {
        int(event.get("event_id")): dict(event)
        for event in bundle.machine_ledger.get("events") or []
        if isinstance(event, Mapping) and isinstance(event.get("event_id"), int)
    }
    blob_index = {
        path.name: path
        for path in bundle.case_root.rglob("*")
        if path.is_file() and _SHA256_RE.fullmatch(path.name)
    }

    records: list[dict[str, Any]] = []
    for row in rows:
        step_id = str(row["step_id"])
        step_type = str(row["type"])
        spec = spec_by_id[step_id]
        requirements = requirement_map.get(step_id, [])
        subgoals = subgoal_map.get(step_id, [])
        dependencies = [str(value) for value in row.get("requires") or []]
        dependency_statements = [
            {
                "step_id": dependency,
                "statement": str(row_by_id[dependency]["matched_text"]).strip(),
            }
            for dependency in dependencies
        ]
        target = str(row["matched_text"]).strip()

        if step_type == "evidence":
            event_id = row.get("observation_event_id")
            if not isinstance(event_id, int) or event_id not in events:
                raise DatasetBuildError(
                    f"missing observation event for {bundle.task_id}/{step_id}"
                )
            event = events[event_id]
            source_content, source_sha256 = _observed_content(
                event,
                blob_index=blob_index,
                task_id=bundle.task_id,
                step_id=step_id,
            )
            citation_urls = [str(url) for url in row.get("citation_urls") or []]
            if not citation_urls:
                raise DatasetBuildError(
                    f"evidence target has no citation for {bundle.task_id}/{step_id}"
                )
            question = _evidence_question(
                requirements=requirements,
                subgoals=subgoals,
                source_urls=citation_urls,
                source_content=source_content,
            )
            answer = _append_citations(target, citation_urls)
            system_prompt = EVIDENCE_SYSTEM_PROMPT
            input_payload: dict[str, Any] = {
                "requirements": requirements,
                "subgoals": subgoals,
                "source_urls": citation_urls,
                "source_content": source_content,
                "source_content_sha256": source_sha256,
            }
        elif step_type == "bridge":
            question = _bridge_question(
                requirements=requirements,
                subgoals=subgoals,
                dependency_statements=dependency_statements,
            )
            answer = target
            system_prompt = BRIDGE_SYSTEM_PROMPT
            input_payload = {
                "requirements": requirements,
                "subgoals": subgoals,
                "dependency_statements": dependency_statements,
            }
        elif step_type == "decision":
            question = _decision_question(
                query=bundle.query,
                requirements=requirements,
                subgoals=subgoals,
                dependency_statements=dependency_statements,
            )
            answer = target
            system_prompt = DECISION_SYSTEM_PROMPT
            input_payload = {
                "query": bundle.query,
                "requirements": requirements,
                "subgoals": subgoals,
                "dependency_statements": dependency_statements,
            }
        else:
            raise DatasetBuildError(
                f"unsupported proof type {step_type!r} for {bundle.task_id}/{step_id}"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
        records.append(
            {
                "schema": PROOF_SFT_SCHEMA,
                "example_id": f"{bundle.task_id}::{step_id}",
                "task_id": bundle.task_id,
                "sample_type": step_type,
                "question": question,
                "answer": answer,
                "messages": messages,
                "input": input_payload,
                "metadata": {
                    "step_id": step_id,
                    "requires": dependencies,
                    "vital": bool(row.get("vital")),
                    "route_branches": row.get("route_branches") or [],
                    "claim": row.get("claim") or spec.get("claim"),
                    "rule": spec.get("rule") or row.get("relation"),
                    "verifier": spec.get("verifier"),
                    "label_status": (
                        "synthetic_teacher_forced_from_replayed_machine_step"
                        if bundle.synthetic_only
                        else "teacher_forced_from_human_validated_machine_step"
                    ),
                    "target_sha256": _sha256(answer.encode("utf-8")),
                },
            }
        )
    return records


def _rl_records(
    bundle: _CaseBundle,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validation_by_run = {
        str(row.get("run_id")): dict(row)
        for row in [
            *(bundle.validation.get("oracle_results") or []),
            *(bundle.validation.get("adversarial_results") or []),
        ]
        if isinstance(row, Mapping)
    }
    records: list[dict[str, Any]] = []

    positive = _rl_candidate(
        bundle,
        entry=bundle.machine_entry,
        result=bundle.machine_result,
        candidate_kind="oracle",
        category=None,
    )
    records.append(positive)

    raw_adversarial = bundle.suite.get("adversarial")
    if not isinstance(raw_adversarial, list):
        raise DatasetBuildError(f"adversarial list missing for {bundle.task_id}")
    categories = [
        str(row.get("category")) for row in raw_adversarial if isinstance(row, Mapping)
    ]
    if sorted(categories) != sorted(REQUIRED_ADVERSARIAL_CATEGORIES):
        raise DatasetBuildError(
            f"adversarial categories incomplete for {bundle.task_id}: {categories}"
        )

    negatives: list[dict[str, Any]] = []
    for raw_entry in raw_adversarial:
        entry = dict(raw_entry)
        run_id = str(entry.get("run_id") or "")
        result = validation_by_run.get(run_id)
        if result is None or result.get("category") != entry.get("category"):
            raise DatasetBuildError(
                f"adversarial validation result missing for {bundle.task_id}/{run_id}"
            )
        candidate = _rl_candidate(
            bundle,
            entry=entry,
            result=result,
            candidate_kind="adversarial",
            category=str(entry.get("category")),
        )
        if candidate["score"]["full_pass"] != 0:
            raise DatasetBuildError(
                f"adversarial candidate unexpectedly passed: {bundle.task_id}/{run_id}"
            )
        negatives.append(candidate)
        records.append(candidate)

    preferences = [
        {
            "schema": PREFERENCE_SCHEMA,
            "pair_id": f"{bundle.task_id}::prefer_machine_over::{row['category']}",
            "task_id": bundle.task_id,
            "prompt_messages": positive["prompt_messages"],
            "chosen": positive["response"],
            "rejected": row["response"],
            "chosen_candidate_id": positive["candidate_id"],
            "rejected_candidate_id": row["candidate_id"],
            "rejected_category": row["category"],
            "preference_basis": "same_scorer_replay_full_pass_and_global_gates",
            "chosen_score": positive["score"],
            "rejected_score": row["score"],
            "metadata": {
                "synthetic_only": bundle.synthetic_only,
                "empty_rejected_response": not bool(str(row["response"]).strip()),
            },
        }
        for row in negatives
    ]
    return records, preferences


def _rl_candidate(
    bundle: _CaseBundle,
    *,
    entry: Mapping[str, Any],
    result: Mapping[str, Any],
    candidate_kind: str,
    category: str | None,
) -> dict[str, Any]:
    run_id = str(entry.get("run_id") or "")
    if run_id != str(result.get("run_id") or ""):
        raise DatasetBuildError(f"RL run/result mismatch for {bundle.task_id}/{run_id}")
    report_path, report_raw = _artifact(
        bundle.suite_dir, entry.get("report"), label=f"rl_report:{run_id}"
    )
    ledger_path, ledger_raw = _artifact(
        bundle.suite_dir, entry.get("ledger"), label=f"rl_ledger:{run_id}"
    )
    report_artifact = result.get("report_artifact")
    ledger_artifact = result.get("ledger_artifact")
    if not isinstance(report_artifact, Mapping) or report_artifact.get("sha256") != _sha256(
        report_raw
    ):
        raise DatasetBuildError(f"RL report validation mismatch for {run_id}")
    if not isinstance(ledger_artifact, Mapping) or ledger_artifact.get("sha256") != _sha256(
        ledger_raw
    ):
        raise DatasetBuildError(f"RL ledger validation mismatch for {run_id}")
    ledger = _json_object(ledger_raw, label=str(ledger_path))
    score = result.get("score")
    if not isinstance(score, Mapping) or score.get("status") != "scored":
        raise DatasetBuildError(f"RL score missing/not scored for {run_id}")
    summary = _score_summary(score)
    response = report_raw.decode("utf-8").strip()
    prompt_messages = [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": bundle.query},
    ]
    step_outcomes = [
        {
            "step_id": row.get("step_id"),
            "type": row.get("type"),
            "passed": row.get("passed"),
            "reason_codes": row.get("reason_codes") or {},
        }
        for row in score.get("step_results") or []
        if isinstance(row, Mapping)
    ]
    return {
        "schema": RL_QA_SCHEMA,
        "candidate_id": f"{bundle.task_id}::{run_id}",
        "task_id": bundle.task_id,
        "candidate_kind": candidate_kind,
        "category": category,
        "prompt_messages": prompt_messages,
        "question": bundle.query,
        "response": response,
        "score": summary,
        "reward_components": {
            "partial_completion": summary["partial_completion"],
            "full_pass": summary["full_pass"],
            "grounding_gate_pass": summary["grounding_gate_pass"],
            "fabricated_citations": summary["fabricated_citations"],
            "critical_contradictions": summary["critical_contradictions"],
        },
        "step_outcomes": step_outcomes,
        "observation": {
            "ledger_path": ledger_path.resolve()
            .relative_to(bundle.candidates_root.resolve())
            .as_posix(),
            "ledger_sha256": _sha256(ledger_raw),
            "capture_complete": ledger.get("capture_complete") is True,
            "n_events": len(ledger.get("events") or []),
            "assistant_action_trace_available": False,
        },
        "artifacts": {
            "report_path": report_path.resolve()
            .relative_to(bundle.candidates_root.resolve())
            .as_posix(),
            "report_sha256": _sha256(report_raw),
        },
        "metadata": {
            "synthetic_only": bundle.synthetic_only,
            "scoring_semantics": score.get("scoring_semantics"),
            "validation_scope": bundle.validation.get("validation_scope"),
        },
    }


def _score_summary(score: Mapping[str, Any]) -> dict[str, Any]:
    withheld = bool(score.get("withheld"))
    fabricated = int(score.get("fabricated_citations") or 0)
    contradictions = int(score.get("critical_contradictions") or 0)
    grounding_gate_pass = not withheld and fabricated == 0 and contradictions == 0
    return {
        "status": score.get("status"),
        "withheld": withheld,
        "partial_completion": score.get("partial_completion"),
        "full_pass": score.get("full_pass"),
        "final_answer_pass": score.get("final_answer_pass"),
        "passed_steps": score.get("passed_steps"),
        "required_steps": score.get("required_steps"),
        "fabricated_citations": fabricated,
        "critical_contradictions": contradictions,
        "grounding_gate_pass": grounding_gate_pass,
        "full_pass_failure_reasons": score.get("full_pass_failure_reasons") or [],
    }


def _case_provenance(
    bundle: _CaseBundle,
    rl_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    score = bundle.machine_result["score"]
    type_counts = {"evidence": 0, "bridge": 0, "decision": 0}
    for row in score.get("step_results") or []:
        if isinstance(row, Mapping) and row.get("type") in type_counts:
            type_counts[str(row["type"])] += 1
    return {
        "schema": CASE_PROVENANCE_SCHEMA,
        "task_id": bundle.task_id,
        "cluster_id": bundle.public_task.get("cluster_id"),
        "motif": bundle.public_task.get("motif"),
        "synthetic_only": bundle.synthetic_only,
        "formal_human_validation_passed": bool(
            bundle.validation.get("formal_human_validation_passed")
        ),
        "requires_real_human_followup": bool(
            bundle.validation.get("requires_real_human_followup")
        ),
        "proof_step_counts": type_counts,
        "rl_candidate_count": len(rl_records),
        "source_artifacts": {
            "suite": _root_artifact(
                bundle.suite_path, bundle.suite_raw, root=bundle.candidates_root
            ),
            "validation": _root_artifact(
                bundle.validation_path,
                bundle.validation_raw,
                root=bundle.candidates_root,
            ),
            "public_task": _root_artifact(
                bundle.public_path, bundle.public_raw, root=bundle.candidates_root
            ),
            "case": _root_artifact(
                bundle.case_path, bundle.case_raw, root=bundle.candidates_root
            ),
            "evidence_graph": _root_artifact(
                bundle.graph_path, bundle.graph_raw, root=bundle.candidates_root
            ),
            "protocol": _root_artifact(
                bundle.protocol_path, bundle.protocol_raw, root=bundle.candidates_root
            ),
            "machine_report": _root_artifact(
                bundle.machine_report_path,
                bundle.machine_report_raw,
                root=bundle.candidates_root,
            ),
            "machine_ledger": _root_artifact(
                bundle.machine_ledger_path,
                bundle.machine_ledger_raw,
                root=bundle.candidates_root,
            ),
        },
    }


def _evidence_question(
    *,
    requirements: Sequence[str],
    subgoals: Sequence[str],
    source_urls: Sequence[str],
    source_content: str,
) -> str:
    return (
        f"Research requirement:\n{_bullets(requirements or subgoals)}\n\n"
        f"Observed source URL(s):\n{_bullets(source_urls)}\n\n"
        f"Observed source content:\n{source_content}\n\n"
        "Write one concise evidence statement useful for the requirement. Use "
        "only the observed content, preserve its exact scope and uncertainty, "
        "and cite the supplied URL inline."
    )


def _bridge_question(
    *,
    requirements: Sequence[str],
    subgoals: Sequence[str],
    dependency_statements: Sequence[Mapping[str, str]],
) -> str:
    premises = "\n".join(
        f"- {row['statement']}" for row in dependency_statements
    )
    return (
        f"Research requirement:\n{_bullets(requirements or subgoals)}\n\n"
        f"Verified premises:\n{premises}\n\n"
        "Synthesize one bounded intermediate conclusion. Use every necessary "
        "premise, add no unsupported facts, and preserve important limitations."
    )


def _decision_question(
    *,
    query: str,
    requirements: Sequence[str],
    subgoals: Sequence[str],
    dependency_statements: Sequence[Mapping[str, str]],
) -> str:
    premises = "\n".join(
        f"- {row['statement']}" for row in dependency_statements
    )
    return (
        f"Original research request:\n{query}\n\n"
        f"Decision requirement:\n{_bullets(requirements or subgoals)}\n\n"
        f"Verified intermediate conclusions:\n{premises}\n\n"
        "Give the evidence-bounded final decision. Preserve unresolved fields "
        "and choose a conditional action or defer when the premises do not "
        "support a universal winner."
    )


def _texts_by_step(raw_rows: Any, step_key: str, text_key: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if not isinstance(raw_rows, list):
        return result
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            continue
        text = str(raw.get(text_key) or "").strip()
        if not text:
            continue
        for step_id in raw.get(step_key) or []:
            result.setdefault(str(step_id), []).append(text)
    return result


def _observed_content(
    event: Mapping[str, Any],
    *,
    blob_index: Mapping[str, Path],
    task_id: str,
    step_id: str,
) -> tuple[str, str]:
    reference = event.get("content_text_or_blob_ref")
    if isinstance(reference, str):
        raw = reference.encode("utf-8")
    elif isinstance(reference, Mapping) and isinstance(reference.get("blob_ref"), str):
        blob_ref = str(reference["blob_ref"])
        path = blob_index.get(blob_ref)
        if path is None:
            raise DatasetBuildError(
                f"source blob {blob_ref} missing for {task_id}/{step_id}"
            )
        raw = path.read_bytes()
    else:
        raise DatasetBuildError(
            f"unsupported observation content reference for {task_id}/{step_id}"
        )
    actual_sha = _sha256(raw)
    expected_sha = str(event.get("content_sha256") or "")
    if actual_sha != expected_sha:
        raise DatasetBuildError(
            f"observed source hash mismatch for {task_id}/{step_id}: "
            f"{actual_sha} != {expected_sha}"
        )
    return raw.decode("utf-8", errors="replace").strip(), actual_sha


def _append_citations(text: str, urls: Sequence[str]) -> str:
    missing = [url for url in urls if url not in text]
    if not missing:
        return text
    links = " ".join(
        f"[Source {index}]({url})" if len(missing) > 1 else f"[Source]({url})"
        for index, url in enumerate(missing, start=1)
    )
    return f"{text} {links}"


def _bullets(values: Sequence[str]) -> str:
    return "\n".join(f"- {value}" for value in values) or "- No additional constraint."


def _require_clean_machine_score(score: Mapping[str, Any], *, task_id: str) -> None:
    checks = {
        "status": score.get("status") == "scored",
        "full_pass": score.get("full_pass") == 1,
        "partial_completion": score.get("partial_completion") == 1.0,
        "fabricated_citations": score.get("fabricated_citations") == 0,
        "critical_contradictions": score.get("critical_contradictions") == 0,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise DatasetBuildError(
            f"machine oracle is not a clean training target for {task_id}: {failed}"
        )


def _artifact(
    suite_dir: Path,
    descriptor: Any,
    *,
    label: str,
) -> tuple[Path, bytes]:
    if not isinstance(descriptor, Mapping):
        raise DatasetBuildError(f"{label} must be a path/hash object")
    relative = str(descriptor.get("path") or "")
    expected_sha = str(descriptor.get("sha256") or "")
    if not relative or not _SHA256_RE.fullmatch(expected_sha):
        raise DatasetBuildError(f"{label} requires path and sha256")
    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise DatasetBuildError(f"{label} path must be relative")
    path = (suite_dir / relative_path).resolve()
    if not path.is_relative_to(suite_dir.resolve()):
        raise DatasetBuildError(f"{label} path escapes suite directory")
    if not path.is_file():
        raise DatasetBuildError(f"{label} file missing: {path}")
    raw = path.read_bytes()
    if _sha256(raw) != expected_sha:
        raise DatasetBuildError(f"{label} hash mismatch: {path}")
    return path, raw


def _query_from_public_task(public_task: Mapping[str, Any], path: Path) -> str:
    for key in ("intent", "query", "prompt", "question"):
        value = public_task.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise DatasetBuildError(f"public task has no query: {path}")


def _json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatasetBuildError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise DatasetBuildError(f"JSON root must be an object: {label}")
    return value


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(_jsonl_line(row) for row in rows).encode("utf-8")


def _jsonl_line(row: Mapping[str, Any]) -> str:
    # JSON permits these Unicode separators inside strings, but many JSONL
    # readers (including Python's str.splitlines) treat them as physical record
    # boundaries.  Escape them so every sample is exactly one LF-delimited line.
    line = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    for separator, escaped in (
        ("\u0085", "\\u0085"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        line = line.replace(separator, escaped)
    return line + "\n"


def _root_artifact(path: Path, raw: bytes, *, root: Path) -> dict[str, Any]:
    return {
        "path": path.resolve().relative_to(root.resolve()).as_posix(),
        "sha256": _sha256(raw),
    }


def _portable_path(path: Path) -> str:
    project_root = Path(__file__).resolve().parents[2]
    try:
        return path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
