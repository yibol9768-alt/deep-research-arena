#!/usr/bin/env python3
"""Compile reviewed Route A atom drafts against an exact public task."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.query_rubric_schema import (  # noqa: E402
    audit_known_support_directory,
    compile_query_rubric,
)


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="compile a query_rubric_v1 artifact; writes JSON to stdout"
    )
    parser.add_argument("--task", required=True, help="v2 public task JSON")
    parser.add_argument(
        "--atoms",
        required=True,
        help="JSON list of atom drafts, or an object with an atoms list",
    )
    parser.add_argument("--status", choices=("draft", "reviewed", "frozen"), default="draft")
    parser.add_argument("--reviewer", action="append", default=[])
    parser.add_argument("--generator", default="manual_or_llm_proposal_then_deterministic_review")
    parser.add_argument("--evidence-graph-stamp")
    parser.add_argument(
        "--evidence-graph-dir",
        help="directory containing nodes.jsonl, support_spans.jsonl and corpus_registry.json",
    )
    registry = parser.add_mutually_exclusive_group()
    registry.add_argument("--corpus-registry", help="registry artifact; SHA-256 is computed")
    registry.add_argument("--corpus-registry-hash", help="precomputed registry artifact SHA-256")
    parser.add_argument("--pretty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    task = _load(args.task)
    draft = _load(args.atoms)
    atoms = draft.get("atoms") if isinstance(draft, dict) else draft
    if not isinstance(atoms, list):
        raise SystemExit("--atoms must contain a JSON list")
    registry_hash = args.corpus_registry_hash
    if args.corpus_registry:
        registry_hash = hashlib.sha256(Path(args.corpus_registry).read_bytes()).hexdigest()
    rubric = compile_query_rubric(
        task,
        atoms,
        status=args.status,
        reviewers=args.reviewer,
        generator=args.generator,
        evidence_graph_stamp=args.evidence_graph_stamp,
        corpus_registry_hash=registry_hash,
    )
    if args.status == "frozen" and not args.evidence_graph_dir:
        raise SystemExit("--status frozen requires --evidence-graph-dir for witness replay")
    if args.evidence_graph_dir:
        audit = audit_known_support_directory(rubric, args.evidence_graph_dir)
        if audit["status"] != "passed":
            raise SystemExit(
                "known-support audit failed: "
                + json.dumps(audit, ensure_ascii=False, sort_keys=True)
            )
    print(json.dumps(rubric.to_dict(), ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
