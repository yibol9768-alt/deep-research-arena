#!/usr/bin/env python3
"""Run the audited DRA four-axis report scoring pipeline."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.four_axis_pipeline import run_four_axis_pipeline


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
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--task-contract-dir",
        type=Path,
        help=(
            "reuse a hash-verified task-level contract; when omitted the "
            "transition contract is compiled inside this scoring run"
        ),
    )
    parser.add_argument(
        "--frozen-claims-dir",
        type=Path,
        help=(
            "reuse a report-bound Claim Ledger; required for a controlled "
            "cross-judge comparison"
        ),
    )
    parser.add_argument(
        "--frozen-fact-packets-dir",
        type=Path,
        help=(
            "reuse the exact candidate evidence packets; with a frozen task "
            "contract and Claim Ledger this changes only semantic judges"
        ),
    )
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--claim-proposal-model")
    parser.add_argument("--nli-model")
    parser.add_argument("--structural-model")
    parser.add_argument("--fact-model")
    parser.add_argument("--evidence-model")
    fact_transport = parser.add_mutually_exclusive_group()
    fact_transport.add_argument(
        "--fact-search-base-url",
        help=(
            "co-located frozen search service, for example "
            "http://localhost:8081"
        ),
    )
    fact_transport.add_argument(
        "--fact-ssh-host",
        help=(
            "diagnostic no-port-forward transport to a Windows sandbox host; "
            "the remote search service is expected at http://localhost:8081"
        ),
    )
    parser.add_argument(
        "--judge-cache-dir",
        action="append",
        type=Path,
        default=[],
        help="reuse an audited response only when the complete request hash matches",
    )
    args = parser.parse_args()
    if args.judge_cache_dir:
        os.environ["DRA_JUDGE_CACHE_DIRS"] = os.pathsep.join(
            str(path) for path in args.judge_cache_dir
        )

    result = run_four_axis_pipeline(
        task_path=args.task,
        report_path=args.report,
        trace_path=args.trace,
        citation_map_path=args.citation_map,
        task_world_model_path=args.task_world_model,
        research_test_suite_path=args.research_test_suite,
        graph_dir=args.graph_dir,
        url_registry_path=args.url_registry,
        output_dir=args.output_dir,
        model=args.model,
        claim_proposal_model=args.claim_proposal_model,
        nli_model=args.nli_model,
        structural_model=args.structural_model,
        fact_model=args.fact_model,
        evidence_model=args.evidence_model,
        fact_search_base_url=args.fact_search_base_url,
        fact_ssh_host=args.fact_ssh_host,
        task_contract_dir=args.task_contract_dir,
        frozen_claims_dir=args.frozen_claims_dir,
        frozen_fact_packets_dir=args.frozen_fact_packets_dir,
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "task_id": result["task_id"],
                "truth_linear_diagnostic": result["truth_linear_diagnostic"],
                "truth_geometric_candidate": result[
                    "truth_geometric_candidate"
                ],
                "formal_truth": result["formal_truth"],
                "quality": result["quality"],
                "provenance": result["provenance"]["score"],
                "fact": result["fact"]["score"],
                "evidence": result["evidence"]["score"],
                "completeness": result["completeness"]["score"],
                "rubric": result["rubric"]["score"],
                "formal_eligible": result["formal_eligible"],
                "diagnostic_label": result["diagnostic_label"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
