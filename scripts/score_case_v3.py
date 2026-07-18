#!/usr/bin/env python3
"""Score one DRA v3 report from frozen case/graph/observation inputs.

The command prints exactly one JSON object to stdout.  A withheld result is a
successful deterministic replay (exit 0) unless ``--fail-on-withhold`` is set;
it is not converted to an agent score of zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.evidence_graph import load_corpus_registry  # noqa: E402
from src.eval.protocol_manifest_v3 import sha256_file  # noqa: E402
from src.eval.slot_scorer import (  # noqa: E402
    SCORING_SEMANTICS,
    VERIFIED_SLOTS_SEMANTICS,
    score_case,
)


def _json_file(path: str) -> Any:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        # Evidence graph JSONL commonly stores one node per line.
        if rows and all(isinstance(row, Mapping) for row in rows):
            return {"nodes": rows}
        return rows


def _report(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")


def _ledger(path: str) -> Any:
    if path != "-":
        # Passing the path delegates JSONL, blob loading, and legacy adaptation
        # to observation_ledger.py.
        return path
    text = sys.stdin.read()
    return json.loads(text)


def _registry(path: str | None) -> tuple[list[str] | None, str | None]:
    if not path:
        return None, None
    registry = load_corpus_registry(path)
    return (
        [entry.source_url for entry in registry.entries],
        registry.corpus_sha256,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="deterministically score one DRA v3 case")
    parser.add_argument("--case", required=True, help="compiled v3 case JSON")
    parser.add_argument(
        "--scoring-semantics",
        choices=(VERIFIED_SLOTS_SEMANTICS, SCORING_SEMANTICS),
        default=VERIFIED_SLOTS_SEMANTICS,
        help=(
            "explicit scorer protocol; default preserves verified_slots_v1, "
            "new formal panels must select proof_steps_v1"
        ),
    )
    parser.add_argument("--report", required=True, help="agent report path, or - for stdin")
    parser.add_argument("--ledger", required=True, help="observation JSON/JSONL path")
    parser.add_argument(
        "--semantic-match-artifact",
        help=(
            "sealed LLM semantic-match JSON; replaces strict report phrase "
            "matching only, while provenance gates remain deterministic"
        ),
    )
    parser.add_argument("--evidence-graph", help="frozen evidence graph JSON/JSONL")
    parser.add_argument(
        "--corpus-registry",
        help=(
            "typed frozen_corpus_registry_v1 JSON (or containing directory); "
            "overrides case registry URLs/hash"
        ),
    )
    parser.add_argument(
        "--protocol-manifest",
        help="sealed formal panel protocol JSON; validated before scoring",
    )
    parser.add_argument(
        "--public-task",
        help="exact rendered public task artifact used for this formal run",
    )
    parser.add_argument(
        "--agent",
        help="stable agent/lane attribution required for formal scoring",
    )
    parser.add_argument(
        "--replicate",
        type=int,
        help="positive replicate number required for formal scoring",
    )
    parser.add_argument("--seed-url", action="append", default=[], help="additional compiled discovery root")
    parser.add_argument("--expected-run-id", help="require exact ledger run attribution")
    parser.add_argument("--pretty", action="store_true", help="indent output JSON")
    parser.add_argument(
        "--fail-on-withhold",
        action="store_true",
        help="return exit 3 when deterministic scoring is withheld",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.report == "-" and args.ledger == "-":
        raise SystemExit("--report and --ledger cannot both read stdin")
    case = _json_file(args.case)
    formal_case = (
        isinstance(case, Mapping)
        and isinstance(case.get("formal_bindings"), Mapping)
        and case["formal_bindings"].get("formal") is True
    )
    if formal_case:
        missing = [
            flag
            for flag, value in (
                ("--agent", args.agent),
                ("--replicate", args.replicate),
                ("--public-task", args.public_task),
            )
            if value is None
        ]
        if missing:
            parser.error(
                "formal scoring requires " + ", ".join(missing)
            )
        if args.replicate < 1:
            parser.error("formal scoring requires --replicate >= 1")
        if args.seed_url:
            parser.error(
                "formal scoring forbids --seed-url; discovery roots are sealed "
                "in the compiled case"
            )
    graph = _json_file(args.evidence_graph) if args.evidence_graph else None
    protocol_manifest = (
        _json_file(args.protocol_manifest) if args.protocol_manifest else None
    )
    semantic_match_artifact = (
        _json_file(args.semantic_match_artifact)
        if args.semantic_match_artifact else None
    )
    case_artifact_sha256 = (
        sha256_file(args.case)
        if formal_case or protocol_manifest is not None else None
    )
    public_task_sha256 = (
        sha256_file(args.public_task) if args.public_task else None
    )
    registry_urls, registry_hash = _registry(args.corpus_registry)
    result = score_case(
        case,
        _report(args.report),
        _ledger(args.ledger),
        graph,
        corpus_urls=registry_urls,
        corpus_registry_hash=registry_hash,
        seed_urls=args.seed_url,
        protocols=protocol_manifest,
        expected_run_id=args.expected_run_id,
        case_artifact_sha256=case_artifact_sha256,
        public_task_sha256=public_task_sha256,
        agent=args.agent,
        replicate=args.replicate,
        scoring_semantics=args.scoring_semantics,
        semantic_match_artifact=semantic_match_artifact,
    )
    json.dump(
        result,
        sys.stdout,
        ensure_ascii=False,
        sort_keys=True,
        indent=2 if args.pretty else None,
    )
    sys.stdout.write("\n")
    return 3 if args.fail_on_withhold and result.get("withheld") else 0


if __name__ == "__main__":
    raise SystemExit(main())
