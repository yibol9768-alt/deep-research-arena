#!/usr/bin/env python3
"""Compile one selected B-stage graph candidate into dual C-stage views."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.case_discovery_v3 import (  # noqa: E402
    CandidateDiscoveryError,
    CandidateSubgraph,
    discover_candidates,
)
from src.eval.evidence_graph import (  # noqa: E402
    EvidenceGraphError,
    load_graph_structure,
    save_json,
)
from src.eval.motif_compiler_v3 import (  # noqa: E402
    MotifCompilationError,
    compile_motif_views,
)


OUTPUT_SCHEMA = "motif_candidate_compilation_bundle_v1"


def _load_generator_view(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MotifCompilationError(
            f"cannot load GeneratorView from {source}: {exc}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise MotifCompilationError("GeneratorView input must be a JSON object")
    if isinstance(payload.get("generator_view"), Mapping):
        payload = payload["generator_view"]
    expected = {"scenario", "constraints", "candidate_actions", "target"}
    unknown = sorted(set(payload) - expected)
    missing = sorted(expected - set(payload))
    if missing or unknown:
        raise MotifCompilationError(
            f"GeneratorView fields disagree with the frozen projection; "
            f"missing={missing}, unknown={unknown}"
        )
    return dict(payload)


def _select_candidate(
    candidates: tuple[CandidateSubgraph, ...],
    candidate_id: str | None,
) -> CandidateSubgraph:
    if candidate_id is None:
        if len(candidates) != 1:
            raise CandidateDiscoveryError(
                "candidate ID is required unless deterministic selection returns exactly one"
            )
        return candidates[0]
    matches = [row for row in candidates if row.candidate_id == candidate_id]
    if len(matches) != 1:
        raise CandidateDiscoveryError(
            f"selected candidate {candidate_id!r} was not found in the Pareto-stratified set"
        )
    return matches[0]


def compile_selected_candidate(
    *,
    graph_dir: str | Path,
    generator_view_path: str | Path,
    max_expansion_depth: int = 3,
    per_stratum: int = 1,
    selection_seed: str = "dra-v3-strata-v1",
    candidate_id: str | None = None,
) -> dict[str, Any]:
    graph = load_graph_structure(graph_dir)
    discovery = discover_candidates(
        graph,
        max_depth=max_expansion_depth,
        per_stratum=per_stratum,
        seed=selection_seed,
    )
    candidate = _select_candidate(discovery.selected_candidates, candidate_id)
    compiled = compile_motif_views(
        graph,
        candidate,
        generator_view=_load_generator_view(generator_view_path),
    )
    return {
        "schema": OUTPUT_SCHEMA,
        "directly_scorable_gold": False,
        "graph_stamp": graph.graph_stamp,
        "discovery_parameters": {
            "max_expansion_depth": max_expansion_depth,
            "per_stratum": per_stratum,
            "selection_seed": selection_seed,
        },
        "candidate": candidate.to_dict(),
        "compilation": compiled.to_dict(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-dir", required=True)
    parser.add_argument("--generator-view", required=True)
    parser.add_argument("--candidate-id")
    parser.add_argument("--max-expansion-depth", type=int, default=3)
    parser.add_argument("--per-stratum", type=int, default=1)
    parser.add_argument("--selection-seed", default="dra-v3-strata-v1")
    parser.add_argument("--out", required=True)
    parser.add_argument("--print", dest="print_payload", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = compile_selected_candidate(
            graph_dir=args.graph_dir,
            generator_view_path=args.generator_view,
            max_expansion_depth=args.max_expansion_depth,
            per_stratum=args.per_stratum,
            selection_seed=args.selection_seed,
            candidate_id=args.candidate_id,
        )
        save_json(args.out, payload)
        summary = {
            "ok": True,
            "out": str(Path(args.out)),
            "candidate_id": payload["candidate"]["candidate_id"],
            "graph_motif": payload["candidate"]["graph_motif"],
            "required_proof_steps": len(
                payload["compilation"]["evaluator_view"]["required_proof_steps"]
            ),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        if args.print_payload:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (
        CandidateDiscoveryError,
        EvidenceGraphError,
        MotifCompilationError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"motif compilation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["OUTPUT_SCHEMA", "compile_selected_candidate", "main"]
