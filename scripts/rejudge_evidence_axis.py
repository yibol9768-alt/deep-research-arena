#!/usr/bin/env python3
"""Rejudge Evidence from frozen claims and a corrected native trace.

This utility is for scorer regression studies. It never changes Fact,
Completeness, Rubric, or Provenance judgments in the supplied base packet.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.audited_judge import AuditedJudge
from src.scoring.four_axis_pipeline import (
    judge_citation_bindings,
    reconstruct_native_observations,
)
from src.scoring.four_axis_score import score_four_axis
from src.scoring.url_registry import FrozenURLRegistry


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", required=True, type=Path)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--citation-map", required=True, type=Path)
    parser.add_argument("--url-registry", required=True, type=Path)
    parser.add_argument("--base-score-packet", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--model", default="deepseek-v4-flash")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    claims = _read_jsonl(args.claims)
    trace = _read_json(args.trace)
    citation_map = _read_json(args.citation_map)
    registry = FrozenURLRegistry.load(args.url_registry)
    observations = reconstruct_native_observations(trace, citation_map)
    (args.output_dir / "native-observation-ledger.json").write_text(
        json.dumps(observations, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    judge = AuditedJudge(args.output_dir / "judge_calls", model=args.model)
    bindings, required_units = judge_citation_bindings(
        claims,
        citation_map,
        observations,
        registry,
        judge,
        args.output_dir,
    )
    packet = _read_json(args.base_score_packet)
    packet["schema"] = "dra_four_axis_judgment_packet_v2_evidence_rejudge"
    packet["citation_bindings"] = bindings
    packet["citation_required_units"] = required_units
    (args.output_dir / "score-packet.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    score = score_four_axis(packet)
    result = {
        "schema": "dra_evidence_axis_rejudge_v1",
        "model": args.model,
        "manual_semantic_decisions": 0,
        "scope": (
            "Evidence is newly judged; all other axes are copied from the "
            "base packet and are reported only as an ablation."
        ),
        "observation_tier_counts": observations.get(
            "documents", {}
        )
        and {
            tier: sum(
                row.get("observation_tier") == tier
                for row in observations["documents"].values()
            )
            for tier in ("full_page", "search_snippet")
        },
        **score,
    }
    (args.output_dir / "score.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "evidence": score["evidence"],
                "ablation_truth": score["truth"],
                "observation_tier_counts": result[
                    "observation_tier_counts"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
