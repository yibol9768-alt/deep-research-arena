#!/usr/bin/env python3
"""Build the Q43 decaf/low-caffeine synthetic replay suite.

The three positive rows are synthetic test fixtures.  In particular, the row
named ``human`` is explicitly synthetic and cannot satisfy the real-human gate.
The stable report/ledger helpers are reused from the already validated Q38
builder, while every task binding and run identifier is replaced here.
"""

from __future__ import annotations

import json
import runpy
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[5]
TASK_ID = "dra_v3_formal_coffee_tea_0043"
ANSWER = (
    "order_only_a_verified_clinician_limit_compatible_candidate_then_rebuy_"
    "if_the_fixed_ritual_trial_passes_or_defer"
)
CAPTURE = ROOT / (
    "data/evidence_graph/captures/"
    "v3-corpus-formal-coffee-tea-0043-decaf-low-caffeine-ritual-boundary-20260716-r1"
)
CASE_SOURCE = ROOT / f"data/golden/cases_v3/formal_candidates/{TASK_ID}.json"
TASK_SOURCE = ROOT / f"data/tasks/deep_research/v3/formal_candidates/{TASK_ID}.json"
PROTOCOL_SOURCE = (
    ROOT
    / f"data/pilot_v3/formal_candidates/{TASK_ID}/protocol_manifests/protocol.json"
)
OUT = HERE / "synthetic"
FABRICATED_URL = (
    "http://localhost:7770/fabricated-q43-decaf-low-caffeine-ritual.html"
)
ADVERSARIAL_CATEGORIES = (
    "url_dump",
    "correct_plus_fabricated",
    "fetch_all_no_answer",
    "unsupported_answer",
    "fact_dump",
    "single_source",
    "guessed_then_fetched",
    "wrong_binding",
    "contradictory_decision",
    "silence",
)


BASE_PATH = (
    ROOT
    / "data/pilot_v3/formal_candidates/dra_v3_formal_coffee_tea_0038/"
    "oracle_suites/build_synthetic_suite.py"
)
_loaded = runpy.run_path(str(BASE_PATH), run_name="q43_synthetic_helper_base")
_globals = _loaded["full_report"].__globals__
_globals.update(
    {
        "TASK_ID": TASK_ID,
        "ANSWER": ANSWER,
        "CAPTURE": CAPTURE,
        "CASE_SOURCE": CASE_SOURCE,
        "TASK_SOURCE": TASK_SOURCE,
        "PROTOCOL_SOURCE": PROTOCOL_SOURCE,
        "OUT": OUT,
        "FABRICATED_URL": FABRICATED_URL,
        "ADVERSARIAL_CATEGORIES": ADVERSARIAL_CATEGORIES,
    }
)

artifact = _loaded["artifact"]
bridge_paragraphs = _loaded["bridge_paragraphs"]
decision_paragraphs = _loaded["decision_paragraphs"]
evidence_paragraphs = _loaded["evidence_paragraphs"]
file_sha256 = _loaded["file_sha256"]
full_report = _loaded["full_report"]
ledger = _loaded["ledger"]
write_json = _loaded["write_json"]
write_run = _loaded["write_run"]


def oracle_entry(case: dict, kind: str) -> dict:
    run_id = f"q43-synthetic-{kind}"
    report_path, ledger_path = write_run(
        run_id, full_report(case), ledger(run_id, case)
    )
    entry: dict = {
        "run_id": run_id,
        "kind": kind,
        "answer": ANSWER,
        "report": artifact(report_path),
        "ledger": artifact(ledger_path),
    }
    if kind == "minimal":
        entry["minimal_evidence_ids"] = [
            str(source["evidence_id"]) for source in case["evidence_sources"]
        ]
    if kind == "human":
        access_path: list[str] = []
        for source in case["evidence_sources"]:
            source_url = str(source["source_url"])
            if not access_path or access_path[-1] != source_url:
                access_path.append(source_url)
        entry["manual_record"] = {
            "origin": "manual",
            "reviewer": "synthetic-fixture-not-a-human-oracle",
            "solve_minutes": 1.0,
            "access_path": access_path,
            "attested": True,
            "synthetic": True,
        }
    return entry


def adversarial_entry(case: dict, category: str) -> dict:
    run_id = f"q43-synthetic-negative-{category}"
    complete = full_report(case)
    facts = "\n\n".join(evidence_paragraphs(case))
    bridges = "\n\n".join(bridge_paragraphs(case))
    ledger_mode = "full"
    answer: str | None = None
    if category == "url_dump":
        report = "\n".join(
            f"[Frozen page]({source['source_url']})"
            for source in case["evidence_sources"]
        )
    elif category == "correct_plus_fabricated":
        report = f"{complete}\n\nFabricated extra source: {FABRICATED_URL}"
    elif category == "fetch_all_no_answer":
        report = "I opened every relevant frozen page."
    elif category == "unsupported_answer":
        report = f"{complete}\n\n{ANSWER}"
        ledger_mode = "empty"
        answer = ANSWER
    elif category == "fact_dump":
        report = facts
    elif category == "single_source":
        report = "\n\n".join(
            [evidence_paragraphs(case)[0], bridges, *decision_paragraphs(case)]
        )
    elif category == "guessed_then_fetched":
        report = complete
        ledger_mode = "guessed"
    elif category == "wrong_binding":
        report = "\n\n".join(
            [
                *evidence_paragraphs(case, rotate_citations=True),
                bridges,
                *decision_paragraphs(case),
            ]
        )
    elif category == "contradictory_decision":
        rejected = next(
            item
            for item in case["decidable_claims"]
            if item["contradicts_slot_id"] == "D1"
        )["rejected_matcher"]["accepted_phrases"][0]
        report = f"{facts}\n\n{bridges}\n\n{rejected}"
    elif category == "silence":
        report = ""
        ledger_mode = "empty"
    else:
        raise RuntimeError(f"unknown adversarial category: {category}")
    report_path, ledger_path = write_run(
        run_id, report, ledger(run_id, case, ledger_mode)
    )
    entry: dict = {
        "run_id": run_id,
        "category": category,
        "report": artifact(report_path),
        "ledger": artifact(ledger_path),
    }
    if answer is not None:
        entry["answer"] = answer
    return entry


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    case = json.loads(CASE_SOURCE.read_text(encoding="utf-8"))
    shutil.copyfile(CASE_SOURCE, OUT / "case.json")
    shutil.copyfile(TASK_SOURCE, OUT / "public_task.json")
    shutil.copyfile(PROTOCOL_SOURCE, OUT / "protocol.json")
    graph_path = OUT / "evidence_graph.json"
    write_json(
        graph_path,
        {
            "nodes": {
                str(source["evidence_id"]): source
                for source in case["evidence_sources"]
            }
        },
    )
    suite = {
        "schema": "dra_v3_oracle_suite_v1",
        "suite_id": "q43-decaf-low-caffeine-ritual-synthetic-mechanism-v1",
        "validation_scope": "synthetic_test",
        "scoring_semantics": "proof_steps_v1",
        "case": artifact(OUT / "case.json"),
        "public_task": artifact(OUT / "public_task.json"),
        "evidence_graph": artifact(graph_path),
        "protocols": artifact(OUT / "protocol.json"),
        "oracles": [
            oracle_entry(case, "machine"),
            oracle_entry(case, "human"),
            oracle_entry(case, "minimal"),
        ],
        "adversarial": [
            adversarial_entry(case, category)
            for category in ADVERSARIAL_CATEGORIES
        ],
    }
    write_json(OUT / "suite.json", suite)
    print(
        json.dumps(
            {
                "suite": str(OUT / "suite.json"),
                "suite_sha256": file_sha256(OUT / "suite.json"),
                "oracles": len(suite["oracles"]),
                "adversarial": len(suite["adversarial"]),
                "human_status": "pending_human",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
