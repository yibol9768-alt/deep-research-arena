#!/usr/bin/env python3
"""Build, freeze, and replay one DRA score with Qwen as the only judge.

The evaluated report and harness trace are immutable inputs.  Qwen is used
only for evaluation-side semantic work:

1. report-blind Task Evaluation Contract compilation;
2. report claim proposal, NLI, structural filtering, and deduplication;
3. Fact, Evidence, Completeness, and Rubric judgments.

The first pass builds the task/report-bound evaluation assets.  Those assets
are then cryptographically sealed and a second pass reuses them, so the score
is not confounded by a changing claim set or retrieval candidate set.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.four_axis_pipeline import run_four_axis_pipeline
from src.scoring.frozen_claim_ledger import (
    load_frozen_claim_ledger,
    seal_claim_ledger,
)
from src.scoring.frozen_fact_packets import seal_fact_packet_bundle
from src.scoring.task_evaluation_contract import (
    CONTRACT_SEMANTICS,
    load_task_evaluation_contract,
    seal_compiled_task_contract,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_new_directory(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise SystemExit(
            f"refusing to mix a controlled run with existing files: {path}"
        )
    path.mkdir(parents=True, exist_ok=True)


def _copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        raise RuntimeError(f"frozen destination already exists: {destination}")
    shutil.copytree(source, destination)


def _append_judge_cache_roots(*roots: Path) -> list[str]:
    """Expose completed audited calls for exact-request replay.

    Cache lookup is keyed by the canonical request hash, so a response is
    reused only when model, prompt, payload, temperature, and token budget are
    byte-equivalent. This avoids paying for the controlled replay twice while
    preserving a fresh transcript that points to its cache source.
    """

    existing = [
        value
        for value in os.environ.get("DRA_JUDGE_CACHE_DIRS", "").split(
            os.pathsep
        )
        if value
    ]
    discovered: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        discovered.extend(
            str(path.resolve())
            for path in sorted(root.iterdir())
            if path.is_dir()
        )
    combined = list(dict.fromkeys([*existing, *discovered]))
    os.environ["DRA_JUDGE_CACHE_DIRS"] = os.pathsep.join(combined)
    return combined


def _score_projection(score: dict[str, Any]) -> dict[str, Any]:
    return {
        "provenance": score["provenance"]["score"],
        "fact": score["fact"]["score"],
        "fact_resolution_rate": score["fact"]["resolution_rate"],
        "fact_adjudication_coverage": score["fact"][
            "adjudication_coverage"
        ],
        "evidence": score["evidence"]["score"],
        "completeness": score["completeness"]["score"],
        "rubric": score["rubric"]["score"],
        "quality": score["quality"],
        "truth_linear_diagnostic": score["truth_linear_diagnostic"],
        "truth_geometric_candidate": score["truth_geometric_candidate"],
        "formal_truth": score["formal_truth"],
        "formal_eligible": score["formal_eligible"],
        "diagnostic_label": score["diagnostic_label"],
    }


def _assert_qwen_only(
    *,
    model: str,
    builder_score: dict[str, Any],
    controlled_score: dict[str, Any],
    task_contract: dict[str, Any],
    claim_manifest: dict[str, Any],
) -> dict[str, Any]:
    if "qwen" not in model.lower():
        raise RuntimeError(
            f"unified-Qwen mode requires a Qwen model, received {model!r}"
        )

    observed_models: dict[str, Any] = {
        "builder": builder_score.get("models"),
        "controlled": controlled_score.get("models"),
        "task_contract_compiler": (
            task_contract.get("manifest", {}).get("compiler") or {}
        ).get("model"),
        "claim_extractors": claim_manifest.get("extractor_models"),
    }
    concrete: list[str] = []
    for value in observed_models.values():
        if isinstance(value, str):
            concrete.append(value)
        elif isinstance(value, dict):
            concrete.extend(
                str(item)
                for item in value.values()
                if isinstance(item, str) and item
            )
    unexpected = sorted({item for item in concrete if item != model})
    if unexpected:
        raise RuntimeError(
            "non-Qwen or unexpected evaluator model found in controlled run: "
            f"{unexpected}; expected only {model!r}"
        )
    return {
        "required_model": model,
        "observed_models": observed_models,
        "passed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--citation-map", required=True, type=Path)
    parser.add_argument("--task-world-model", required=True, type=Path)
    parser.add_argument("--research-test-suite", required=True, type=Path)
    parser.add_argument("--graph-dir", required=True, type=Path)
    parser.add_argument("--url-registry", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--shared-task-contract",
        type=Path,
        help=(
            "Reuse one already-frozen task-level contract across harnesses. "
            "When omitted, the report-blind contract is compiled and sealed "
            "during this run."
        ),
    )
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument(
        "--judge-base-url",
        default="http://127.0.0.1:8000/v1",
    )
    parser.add_argument(
        "--fact-search-base-url",
        default="http://127.0.0.1:8081",
    )
    parser.add_argument(
        "--contract-semantics",
        choices=sorted(CONTRACT_SEMANTICS),
        default="research_obligations_v1",
    )
    args = parser.parse_args()

    if "qwen" not in args.model.lower():
        raise SystemExit("--model must name a Qwen model in unified-Qwen mode")
    for path in (
        args.task,
        args.report,
        args.trace,
        args.citation_map,
        args.task_world_model,
        args.research_test_suite,
        args.graph_dir,
        args.url_registry,
    ):
        if not path.exists():
            raise SystemExit(f"required input does not exist: {path}")
    if args.shared_task_contract is not None:
        if not args.shared_task_contract.is_dir():
            raise SystemExit(
                "shared task contract is not a directory: "
                f"{args.shared_task_contract}"
            )

    output_root = args.output_root.resolve()
    _require_new_directory(output_root)
    builder_dir = output_root / "01-qwen-asset-builder"
    frozen_dir = output_root / "02-frozen-assets"
    controlled_dir = output_root / "03-qwen-controlled-score"

    os.environ["JUDGE_PROVIDER"] = "openai"
    os.environ["JUDGE_MODEL"] = args.model
    os.environ["JUDGE_MODEL_HEAVY"] = args.model
    os.environ["JUDGE_BASE_URL"] = args.judge_base_url
    os.environ.setdefault("JUDGE_API_KEY", "EMPTY")
    os.environ.setdefault("JUDGE_TIMEOUT_S", "600")
    # The local vLLM endpoint supports constrained JSON-object decoding.  The
    # evaluator still validates the requested top-level key and every
    # downstream schema; this only prevents syntactically broken/truncated
    # JSON from turning an otherwise scoreable report into a pipeline crash.
    os.environ["JUDGE_JSON_OBJECT"] = "1"

    task = _read_json(args.task)
    task_world_model = _read_json(args.task_world_model)
    research_test_suite = _read_json(args.research_test_suite)
    report = args.report.read_text(encoding="utf-8")

    shared_task_contract = None
    if args.shared_task_contract is not None:
        shared_task_contract = load_task_evaluation_contract(
            args.shared_task_contract,
            expected_task=task,
            expected_task_world_model=task_world_model,
            expected_research_test_suite=research_test_suite,
        )
        shared_semantics = shared_task_contract["manifest"][
            "contract_semantics"
        ]
        if shared_semantics != args.contract_semantics:
            raise SystemExit(
                "shared contract semantics do not match --contract-semantics: "
                f"{shared_semantics!r} != {args.contract_semantics!r}"
            )

    builder_score = run_four_axis_pipeline(
        task_path=args.task,
        report_path=args.report,
        trace_path=args.trace,
        citation_map_path=args.citation_map,
        task_world_model_path=args.task_world_model,
        research_test_suite_path=args.research_test_suite,
        graph_dir=args.graph_dir,
        url_registry_path=args.url_registry,
        output_dir=builder_dir,
        model=args.model,
        claim_proposal_model=args.model,
        nli_model=args.model,
        structural_model=args.model,
        fact_model=args.model,
        evidence_model=args.model,
        fact_search_base_url=args.fact_search_base_url,
        task_contract_dir=args.shared_task_contract,
    )

    frozen_contract_dir = frozen_dir / "task-contract"
    if args.shared_task_contract is not None:
        _copy_tree(args.shared_task_contract, frozen_contract_dir)
        task_contract = load_task_evaluation_contract(
            frozen_contract_dir,
            expected_task=task,
            expected_task_world_model=task_world_model,
            expected_research_test_suite=research_test_suite,
        )
    else:
        task_contract = seal_compiled_task_contract(
            compiled_dir=builder_dir / "tec",
            output_dir=frozen_contract_dir,
            task=task,
            task_world_model=task_world_model,
            research_test_suite=research_test_suite,
            contract_semantics=args.contract_semantics,
            # This is a retrospective pilot.  The flag must stay false even
            # though the compiler itself is report-blind.
            frozen_before_report_input=False,
        )

    frozen_claims_dir = frozen_dir / "claims"
    _copy_tree(builder_dir / "claims", frozen_claims_dir)
    claim_manifest = seal_claim_ledger(
        frozen_claims_dir,
        report,
        intended_for_cross_judge_reuse=True,
    )
    frozen_claim_artifact = load_frozen_claim_ledger(
        frozen_claims_dir,
        report,
    )

    frozen_fact_packets_dir = frozen_dir / "fact-packets"
    _copy_tree(builder_dir / "fact_packets", frozen_fact_packets_dir)
    fact_packet_manifest = seal_fact_packet_bundle(
        frozen_fact_packets_dir,
        frozen_claim_artifact["claims"],
        claim_ledger_sha256=claim_manifest["claim_ledger_sha256"],
    )

    controlled_cache_roots = _append_judge_cache_roots(
        builder_dir / "judge_calls"
    )
    controlled_score = run_four_axis_pipeline(
        task_path=args.task,
        report_path=args.report,
        trace_path=args.trace,
        citation_map_path=args.citation_map,
        task_world_model_path=args.task_world_model,
        research_test_suite_path=args.research_test_suite,
        graph_dir=args.graph_dir,
        url_registry_path=args.url_registry,
        output_dir=controlled_dir,
        model=args.model,
        fact_model=args.model,
        evidence_model=args.model,
        task_contract_dir=frozen_contract_dir,
        frozen_claims_dir=frozen_claims_dir,
        frozen_fact_packets_dir=frozen_fact_packets_dir,
    )

    qwen_only = _assert_qwen_only(
        model=args.model,
        builder_score=builder_score,
        controlled_score=controlled_score,
        task_contract=task_contract,
        claim_manifest=claim_manifest,
    )
    input_paths = {
        "task": args.task,
        "report": args.report,
        "trace": args.trace,
        "citation_map": args.citation_map,
        "task_world_model": args.task_world_model,
        "research_test_suite": args.research_test_suite,
        "graph_manifest": args.graph_dir / "manifest.json",
        "url_registry": args.url_registry,
    }
    if args.shared_task_contract is not None:
        input_paths["shared_task_contract_manifest"] = (
            args.shared_task_contract / "contract-manifest.json"
        )
    manifest = {
        "schema": "dra_unified_qwen_controlled_score_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "report_generator_unchanged": True,
        "qwen_role": "evaluation_only",
        "shared_task_contract_reused": (
            args.shared_task_contract is not None
        ),
        "qwen_only_certificate": qwen_only,
        "contract_semantics": args.contract_semantics,
        "inputs": {
            name: {
                "path": str(path.resolve()),
                "sha256": _sha256_file(path),
            }
            for name, path in input_paths.items()
        },
        "frozen_assets": {
            "task_contract_sha256": task_contract["manifest"][
                "contract_sha256"
            ],
            "claim_ledger_sha256": claim_manifest["claim_ledger_sha256"],
            "fact_packet_bundle_sha256": fact_packet_manifest[
                "fact_packet_bundle_sha256"
            ],
        },
        "asset_builder_score_is_publication_score": False,
        "controlled_replay_cache_roots": controlled_cache_roots,
        "asset_builder_diagnostic": _score_projection(builder_score),
        "controlled_score": _score_projection(controlled_score),
        "controlled_score_path": str(
            (controlled_dir / "score.json").resolve()
        ),
    }
    manifest_path = output_root / "unified-qwen-run-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output_root": str(output_root),
                "manifest": str(manifest_path),
                **manifest["controlled_score"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
