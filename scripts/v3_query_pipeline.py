#!/usr/bin/env python3
"""Run the human-governed DRA v3 query authoring pipeline.

The CLI is intentionally split into inspectable stages.  It never invents a
human approval, never reads private evaluator fields during model rendering,
and never silently repairs a failed query.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_v3_candidate_sources import validate_capture_plan  # noqa: E402
from src.eval.case_schema_v3 import CaseSpecV3, validate_case  # noqa: E402
from src.eval.evidence_graph import verify_evidence_graph_manifest  # noqa: E402
from src.tasks.human_query_pipeline_v3 import (  # noqa: E402
    HumanActorV1,
    HumanBlindQueryReviewV1,
    HumanFewShotDatasetV1,
    HumanFewShotExampleV1,
    HumanGraphAnnotationV1,
    HumanQueryPipelineError,
    HumanQueryReleaseV1,
    HumanSourceSelectionV1,
    QueryAttemptClosureV1,
    QueryGenerationRecordV1,
    QueryRendererModelConfigV1,
    artifact_sha256,
    build_few_shot_dataset,
    build_graph_annotation_template,
    build_human_blind_review_template,
    build_human_query_release,
    build_query_generation_record,
    build_query_attempt_closure,
    build_registered_query_messages,
    build_registered_query_prompt,
    call_registered_query_renderer,
    capture_plan_from_human_selection,
    validate_few_shot_example_for_case,
    validate_graph_annotation_for_case,
    validate_human_query_release,
    validate_query_generation_record,
    validate_query_attempt_history,
)


def _load_object(path: str | Path, label: str) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HumanQueryPipelineError(f"cannot load {label} from {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise HumanQueryPipelineError(f"{label} must be a JSON object")
    return value


def _write_json(path: str | Path, value: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        value.model_dump(mode="json", by_alias=True, exclude_none=True)
        if hasattr(value, "model_dump")
        else value
    )
    content = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _case(path: str | Path) -> CaseSpecV3:
    return validate_case(_load_object(path, "case"))


def _graph_hash(path: str | Path) -> str:
    manifest = verify_evidence_graph_manifest(path)
    value = manifest.get("evidence_graph_hash")
    if not isinstance(value, str):
        raise HumanQueryPipelineError("verified graph manifest has no graph hash")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _init_source_selection(args: argparse.Namespace) -> int:
    template = {
        "schema_version": "dra_v3_human_source_selection_v1",
        "candidate_id": args.candidate_id,
        "corpus_snapshot": args.corpus_snapshot,
        "run_id": args.run_id,
        "research_goal": "",
        "proposal_origin": "human_search",
        "selected_by": {
            "actor_type": "human",
            "actor_id": "",
            "role": "source_selector",
            "attestation": "human_completed_without_model_substitution",
        },
        "selected_at_utc": "",
        "source_requirements": [
            {
                "source_role": "product",
                "purpose": "",
                "minimum_sources": 1,
                "critical": True,
            },
            {
                "source_role": "mechanism",
                "purpose": "",
                "minimum_sources": 1,
                "critical": True,
            },
        ],
        "searches": [],
        "selected_sources": [],
        "source_identity": {},
        "status": "approved_for_capture",
    }
    _write_json(args.out, template)
    print(
        json.dumps(
            {
                "ok": True,
                "stage": "human_source_selection_template",
                "candidate_id": args.candidate_id,
                "out": str(Path(args.out)),
                "next": "human_fill_then_capture_plan",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _capture_plan(args: argparse.Namespace) -> int:
    selection = HumanSourceSelectionV1.model_validate(
        _load_object(args.selection, "human source selection")
    )
    plan = validate_capture_plan(capture_plan_from_human_selection(selection))
    _write_json(args.out, plan)
    print(
        json.dumps(
            {
                "ok": True,
                "stage": "capture_plan",
                "candidate_id": selection.candidate_id,
                "source_selection_sha256": artifact_sha256(selection),
                "searches": len(selection.searches),
                "sources": len(selection.selected_sources),
                "out": str(Path(args.out)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _init_annotation(args: argparse.Namespace) -> int:
    case = _case(args.case)
    graph_hash = _graph_hash(args.graph_dir)
    evidence_review_gate = _load_object(
        args.evidence_review_gate, "human evidence review gate"
    )
    template = build_graph_annotation_template(
        case,
        candidate_id=args.candidate_id,
        evidence_graph_sha256=graph_hash,
        evidence_review_gate=evidence_review_gate,
    )
    _write_json(args.out, template)
    print(
        json.dumps(
            {
                "ok": True,
                "stage": "graph_annotation_template",
                "task_id": case.task_id,
                "evidence_items": len(template.evidence_items),
                "proof_steps": len(template.proof_steps),
                "status": template.status,
                "out": str(Path(args.out)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _validate_annotation(args: argparse.Namespace) -> int:
    case = _case(args.case)
    graph_hash = _graph_hash(args.graph_dir)
    annotation = validate_graph_annotation_for_case(
        _load_object(args.annotation, "human graph annotation"),
        case,
        expected_graph_sha256=graph_hash,
    )
    if args.out:
        _write_json(args.out, annotation)
    print(
        json.dumps(
            {
                "ok": True,
                "stage": "graph_annotation_approved",
                "task_id": case.task_id,
                "annotation_sha256": artifact_sha256(annotation),
                "annotator": annotation.annotator.actor_id if annotation.annotator else None,
                "adjudicator": (
                    annotation.adjudicator.actor_id if annotation.adjudicator else None
                ),
                "out": str(Path(args.out)) if args.out else None,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _build_few_shots(args: argparse.Namespace) -> int:
    if not (
        len(args.case) == len(args.graph_dir) == len(args.annotation) == len(args.example) == 3
    ):
        raise HumanQueryPipelineError(
            "build-few-shots requires exactly three --case/--graph-dir/"
            "--annotation/--example groups"
        )
    examples: list[HumanFewShotExampleV1] = []
    for case_path, graph_dir, annotation_path, example_path in zip(
        args.case,
        args.graph_dir,
        args.annotation,
        args.example,
    ):
        case = _case(case_path)
        graph_hash = _graph_hash(graph_dir)
        annotation = validate_graph_annotation_for_case(
            _load_object(annotation_path, "human graph annotation"),
            case,
            expected_graph_sha256=graph_hash,
        )
        example = validate_few_shot_example_for_case(
            _load_object(example_path, "human few-shot example"),
            case,
            annotation,
        )
        examples.append(example)
    approver = HumanActorV1.model_validate(
        _load_object(args.approved_by, "few-shot dataset approver")
    )
    dataset = build_few_shot_dataset(
        dataset_id=args.dataset_id,
        examples=examples,
        approved_by=approver,
        approved_at_utc=args.approved_at_utc or _utc_now(),
    )
    _write_json(args.out, dataset)
    print(
        json.dumps(
            {
                "ok": True,
                "stage": "few_shot_dataset",
                "dataset_id": dataset.dataset_id,
                "dataset_sha256": artifact_sha256(dataset),
                "tasks": [item.task_id for item in dataset.examples],
                "motifs": [item.motif for item in dataset.examples],
                "out": str(Path(args.out)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _init_few_shot_example(args: argparse.Namespace) -> int:
    case = _case(args.case)
    graph_hash = _graph_hash(args.graph_dir)
    annotation = validate_graph_annotation_for_case(
        _load_object(args.annotation, "human graph annotation"),
        case,
        expected_graph_sha256=graph_hash,
    )
    template = {
        "schema_version": "dra_v3_human_few_shot_example_v1",
        "example_id": args.example_id,
        "task_id": case.task_id,
        "case_sha256": case.sha256(),
        "graph_annotation_sha256": artifact_sha256(annotation),
        "motif": case.motif,
        "generator_view": case.generator_view.model_dump(mode="json"),
        "human_written_query": "",
        "author": {
            "actor_type": "human",
            "actor_id": "",
            "role": "few_shot_query_author",
            "attestation": "human_completed_without_model_substitution",
        },
        "adjudicator": {
            "actor_type": "human",
            "actor_id": "",
            "role": "few_shot_adjudicator",
            "attestation": "human_completed_without_model_substitution",
        },
        "authored_at_utc": "",
        "adjudicated_at_utc": "",
        "adjudication_note": "",
        "status": "approved",
    }
    _write_json(args.out, template)
    print(
        json.dumps(
            {
                "ok": True,
                "stage": "human_few_shot_example_template",
                "task_id": case.task_id,
                "motif": case.motif,
                "out": str(Path(args.out)),
                "next": "human_write_query_then_independent_adjudication",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _init_renderer_config(args: argparse.Namespace) -> int:
    config = QueryRendererModelConfigV1(
        renderer_id=args.renderer_id,
        base_url=args.base_url,
        model=args.model,
        model_revision=args.model_revision,
        api_key_env=args.api_key_env,
        temperature=0.0,
        max_tokens=args.max_tokens,
        seed=args.seed,
        timeout_seconds=args.timeout_seconds,
    )
    _write_json(args.out, config)
    print(
        json.dumps(
            {
                "ok": True,
                "stage": "registered_renderer_config",
                "renderer_id": config.renderer_id,
                "model": config.model,
                "model_revision": config.model_revision,
                "config_sha256": artifact_sha256(config),
                "out": str(Path(args.out)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _approved_target(args: argparse.Namespace) -> tuple[
    CaseSpecV3, HumanGraphAnnotationV1, HumanFewShotDatasetV1, str
]:
    case = _case(args.case)
    graph_hash = _graph_hash(args.graph_dir)
    annotation = validate_graph_annotation_for_case(
        _load_object(args.annotation, "human graph annotation"),
        case,
        expected_graph_sha256=graph_hash,
    )
    dataset = HumanFewShotDatasetV1.model_validate(
        _load_object(args.few_shots, "human few-shot dataset")
    )
    return case, annotation, dataset, graph_hash


def _build_prompt(args: argparse.Namespace) -> int:
    case, annotation, dataset, graph_hash = _approved_target(args)
    prompt = build_registered_query_prompt(case, dataset)
    messages = build_registered_query_messages(case, dataset)
    artifact = {
        "schema_version": "dra_v3_registered_query_prompt_inspection_v1",
        "task_id": case.task_id,
        "case_sha256": case.sha256(),
        "evidence_graph_sha256": graph_hash,
        "graph_annotation_sha256": artifact_sha256(annotation),
        "few_shot_dataset_sha256": artifact_sha256(dataset),
        "prompt_sha256": artifact_sha256(prompt),
        "messages_sha256": artifact_sha256(messages),
        "prompt": prompt,
        "messages": messages,
    }
    _write_json(args.out, artifact)
    print(
        json.dumps(
            {
                "ok": True,
                "stage": "registered_query_prompt",
                "task_id": case.task_id,
                "prompt_sha256": artifact["prompt_sha256"],
                "messages_sha256": artifact["messages_sha256"],
                "out": str(Path(args.out)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _generate(args: argparse.Namespace) -> int:
    case, _annotation, dataset, _graph_hash_value = _approved_target(args)
    config = QueryRendererModelConfigV1.model_validate(
        _load_object(args.model_config, "registered renderer config")
    )
    prior_attempts = [
        QueryAttemptClosureV1.model_validate(
            _load_object(path, "closed prior query attempt")
        )
        for path in args.prior_attempt
    ]
    if args.attempt != len(prior_attempts) + 1:
        raise HumanQueryPipelineError(
            "--attempt must equal one plus the number of --prior-attempt files"
        )
    if prior_attempts:
        validated_prior = validate_query_attempt_history(
            prior_attempts,
            case,
            dataset,
            require_final_accepted=False,
        )
        if validated_prior[-1].disposition != "retry_required":
            raise HumanQueryPipelineError(
                "a new generation may follow only a retry_required attempt"
            )
        if artifact_sha256(validated_prior[-1].generation.renderer) != artifact_sha256(
            config
        ):
            raise HumanQueryPipelineError("renderer config cannot change across retries")
    query, raw = call_registered_query_renderer(case, dataset, config)
    record = build_query_generation_record(
        case,
        dataset,
        config,
        attempt=args.attempt,
        generated_at_utc=args.generated_at_utc or _utc_now(),
        assistant_text=query,
        raw_response_bytes=raw,
    )
    _write_json(args.out, record)
    print(
        json.dumps(
            {
                "ok": record.status == "hard_rules_passed",
                "stage": "query_generation",
                "task_id": case.task_id,
                "attempt": record.attempt,
                "model": record.renderer.model,
                "query_sha256": record.query_sha256,
                "status": record.status,
                "missing_constraints": record.hard_rules.missing_constraints,
                "missing_options": record.hard_rules.missing_options,
                "findings": [
                    item.model_dump(mode="json") for item in record.hard_rules.findings
                ],
                "out": str(Path(args.out)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if record.status == "hard_rules_passed" else 3


def _blind_packet(args: argparse.Namespace) -> int:
    case, _annotation, dataset, _graph_hash_value = _approved_target(args)
    generation = validate_query_generation_record(
        _load_object(args.generation, "query generation record"),
        case,
        dataset,
    )
    packet, template = build_human_blind_review_template(case, generation)
    _write_json(args.packet_out, packet)
    _write_json(args.review_template_out, template)
    print(
        json.dumps(
            {
                "ok": True,
                "stage": "blind_query_review_packet",
                "task_id": case.task_id,
                "packet_sha256": artifact_sha256(packet),
                "packet_out": str(Path(args.packet_out)),
                "review_template_out": str(Path(args.review_template_out)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _close_attempt(args: argparse.Namespace) -> int:
    case, _annotation, dataset, _graph_hash_value = _approved_target(args)
    generation = QueryGenerationRecordV1.model_validate(
        _load_object(args.generation, "query generation record")
    )
    blind_review = (
        HumanBlindQueryReviewV1.model_validate(
            _load_object(args.blind_review, "human blind query review")
        )
        if args.blind_review
        else None
    )
    closure = build_query_attempt_closure(
        case,
        dataset,
        generation,
        blind_review=blind_review,
    )
    _write_json(args.out, closure)
    print(
        json.dumps(
            {
                "ok": True,
                "stage": "query_attempt_closed",
                "task_id": case.task_id,
                "attempt": closure.generation.attempt,
                "disposition": closure.disposition,
                "closure_sha256": artifact_sha256(closure),
                "out": str(Path(args.out)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _release(args: argparse.Namespace) -> int:
    case, annotation, dataset, graph_hash = _approved_target(args)
    attempts = [
        QueryAttemptClosureV1.model_validate(
            _load_object(path, "closed query attempt")
        )
        for path in args.attempt
    ]
    release = build_human_query_release(
        case,
        expected_graph_sha256=graph_hash,
        graph_annotation=annotation,
        few_shot_dataset=dataset,
        attempts=attempts,
    )
    _write_json(args.out, release)
    print(
        json.dumps(
            {
                "ok": True,
                "stage": "query_release",
                "task_id": case.task_id,
                "query_sha256": release.query_sha256,
                "release_sha256": artifact_sha256(release),
                "status": release.status,
                "out": str(Path(args.out)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _validate_release(args: argparse.Namespace) -> int:
    case = _case(args.case)
    graph_hash = _graph_hash(args.graph_dir)
    release = validate_human_query_release(
        _load_object(args.release, "human query release"),
        case,
        expected_graph_sha256=graph_hash,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "stage": "query_release_validation",
                "task_id": case.task_id,
                "query_sha256": release.query_sha256,
                "release_sha256": artifact_sha256(release),
                "status": release.status,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _add_target_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case", required=True)
    parser.add_argument("--graph-dir", required=True)
    parser.add_argument("--annotation", required=True)
    parser.add_argument("--few-shots", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    source_template = sub.add_parser(
        "init-source-selection",
        help="write the JSON form a human fills before any source capture",
    )
    source_template.add_argument("--candidate-id", required=True)
    source_template.add_argument("--corpus-snapshot", required=True)
    source_template.add_argument("--run-id", required=True)
    source_template.add_argument("--out", required=True)
    source_template.set_defaults(handler=_init_source_selection)

    capture = sub.add_parser("capture-plan", help="compile a human source selection")
    capture.add_argument("--selection", required=True)
    capture.add_argument("--out", required=True)
    capture.set_defaults(handler=_capture_plan)

    init = sub.add_parser(
        "init-annotation", help="create a pending human graph annotation template"
    )
    init.add_argument("--case", required=True)
    init.add_argument("--graph-dir", required=True)
    init.add_argument("--candidate-id", required=True)
    init.add_argument(
        "--evidence-review-gate",
        required=True,
        help=(
            "eligible human gate report emitted by import_v3_review_decisions.py; "
            "its evidence judgments are imported into the annotation template"
        ),
    )
    init.add_argument("--out", required=True)
    init.set_defaults(handler=_init_annotation)

    validate = sub.add_parser(
        "validate-annotation", help="validate a completed human graph annotation"
    )
    validate.add_argument("--case", required=True)
    validate.add_argument("--graph-dir", required=True)
    validate.add_argument("--annotation", required=True)
    validate.add_argument("--out")
    validate.set_defaults(handler=_validate_annotation)

    few = sub.add_parser(
        "build-few-shots", help="freeze three approved human development examples"
    )
    few.add_argument("--case", action="append", required=True)
    few.add_argument("--graph-dir", action="append", required=True)
    few.add_argument("--annotation", action="append", required=True)
    few.add_argument("--example", action="append", required=True)
    few.add_argument("--dataset-id", required=True)
    few.add_argument("--approved-by", required=True)
    few.add_argument("--approved-at-utc")
    few.add_argument("--out", required=True)
    few.set_defaults(handler=_build_few_shots)

    few_template = sub.add_parser(
        "init-few-shot-example",
        help="write a hash-bound form for one human-written development query",
    )
    few_template.add_argument("--case", required=True)
    few_template.add_argument("--graph-dir", required=True)
    few_template.add_argument("--annotation", required=True)
    few_template.add_argument("--example-id", required=True)
    few_template.add_argument("--out", required=True)
    few_template.set_defaults(handler=_init_few_shot_example)

    renderer = sub.add_parser(
        "init-renderer-config",
        help="freeze a versioned non-Codex OpenAI-compatible renderer config",
    )
    renderer.add_argument("--renderer-id", required=True)
    renderer.add_argument("--base-url", required=True)
    renderer.add_argument("--model", required=True)
    renderer.add_argument("--model-revision", required=True)
    renderer.add_argument("--api-key-env", required=True)
    renderer.add_argument("--max-tokens", type=int, default=1024)
    renderer.add_argument("--seed", type=int, default=7)
    renderer.add_argument("--timeout-seconds", type=float, default=120.0)
    renderer.add_argument("--out", required=True)
    renderer.set_defaults(handler=_init_renderer_config)

    prompt = sub.add_parser(
        "build-prompt", help="write the exact public-only LLM input for inspection"
    )
    _add_target_inputs(prompt)
    prompt.add_argument("--out", required=True)
    prompt.set_defaults(handler=_build_prompt)

    generate = sub.add_parser(
        "generate", help="call the registered non-Codex API renderer"
    )
    _add_target_inputs(generate)
    generate.add_argument("--model-config", required=True)
    generate.add_argument("--attempt", type=int, choices=range(1, 4), required=True)
    generate.add_argument(
        "--prior-attempt",
        action="append",
        default=[],
        help="closed retry_required attempt; repeat in attempt order",
    )
    generate.add_argument("--generated-at-utc")
    generate.add_argument("--out", required=True)
    generate.set_defaults(handler=_generate)

    blind = sub.add_parser(
        "blind-packet", help="create the GeneratorView-only human review packet"
    )
    _add_target_inputs(blind)
    blind.add_argument("--generation", required=True)
    blind.add_argument("--packet-out", required=True)
    blind.add_argument("--review-template-out", required=True)
    blind.set_defaults(handler=_blind_packet)

    close = sub.add_parser(
        "close-attempt",
        help="close one attempt using hard rules and, when eligible, blind review",
    )
    _add_target_inputs(close)
    close.add_argument("--generation", required=True)
    close.add_argument(
        "--blind-review",
        help="required only when the generation passed deterministic hard rules",
    )
    close.add_argument("--out", required=True)
    close.set_defaults(handler=_close_attempt)

    release = sub.add_parser(
        "release", help="create a formal query-release certificate"
    )
    _add_target_inputs(release)
    release.add_argument(
        "--attempt",
        action="append",
        required=True,
        help="closed attempt; repeat from attempt 1 through the accepted attempt",
    )
    release.add_argument("--out", required=True)
    release.set_defaults(handler=_release)

    check = sub.add_parser(
        "validate-release", help="replay every query-release gate"
    )
    check.add_argument("--case", required=True)
    check.add_argument("--graph-dir", required=True)
    check.add_argument("--release", required=True)
    check.set_defaults(handler=_validate_release)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (HumanQueryPipelineError, ValueError, TypeError, OSError) as exc:
        print(f"v3 query pipeline failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
