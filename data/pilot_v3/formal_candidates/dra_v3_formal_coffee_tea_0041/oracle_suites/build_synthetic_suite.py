#!/usr/bin/env python3
"""Build Q41 synthetic replay fixtures; none are human evidence."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[5]
TASK_ID = "dra_v3_formal_coffee_tea_0041"
ANSWER = (
    "verify_exact_lots_and_package_fields_run_a_small_sealed_and_opened_"
    "calibration_then_stage_the_cheapest_configuration_that_passes_"
    "predeclared_rotation_and_stop_rules_or_defer"
)
CAPTURE = ROOT / (
    "data/evidence_graph/captures/"
    "v3-corpus-formal-coffee-tea-0041-remote-pantry-storage-formats-20260716-r1"
)
CASE_SOURCE = ROOT / f"data/golden/cases_v3/formal_candidates/{TASK_ID}.json"
TASK_SOURCE = ROOT / f"data/tasks/deep_research/v3/formal_candidates/{TASK_ID}.json"
PROTOCOL_SOURCE = ROOT / f"data/pilot_v3/formal_candidates/{TASK_ID}/protocol_manifests/protocol.json"
OUT = HERE / "synthetic"
FABRICATED_URL = "http://localhost:7770/fabricated-q41-storage-result.html"
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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def artifact(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(OUT)), "sha256": file_sha256(path)}


def source_phrase(source: dict) -> str:
    return str(source["verifier"]["accepted_phrases"][0])


def evidence_paragraphs(case: dict, *, rotate_citations: bool = False) -> list[str]:
    sources = case["evidence_sources"]
    urls = [str(source["source_url"]) for source in sources]
    return [
        f"{source_phrase(source)} [Frozen evidence]({urls[(index + 1) % len(urls)] if rotate_citations else urls[index]})."
        for index, source in enumerate(sources)
    ]


def bridge_paragraphs(case: dict) -> list[str]:
    return [
        str(case["rule_definitions"][step["rule"]]["accepted_phrases"][0])
        for step in case["evaluator_view"]["required_proof_steps"]
        if step["type"] == "bridge"
    ]


def decision_paragraphs(case: dict) -> list[str]:
    step = next(
        item for item in case["evaluator_view"]["required_proof_steps"]
        if item["type"] == "decision"
    )
    rule = case["rule_definitions"][step["rule"]]
    condition = rule["admissible_conditions"][0]
    conclusion = rule["conclusion_matchers"][ANSWER]
    return [
        str(rule["decision_matcher"]["accepted_phrases"][0]),
        str(condition["condition_matcher"]["accepted_phrases"][0]),
        *(str(value["accepted_phrases"][0]) for value in condition["tradeoff_matchers"].values()),
        str(conclusion["accepted_phrases"][0]),
    ]


def full_report(case: dict) -> str:
    return "\n\n".join([*evidence_paragraphs(case), *bridge_paragraphs(case), *decision_paragraphs(case)])


def body_for(source: dict) -> str:
    digest = str(source["content_sha256"])
    blob = CAPTURE / "blobs" / digest
    body = blob.read_bytes()
    if sha256_bytes(body) != digest:
        raise RuntimeError(f"frozen body hash mismatch for {source['evidence_id']}")
    return body.decode("utf-8")


def event(run_id: str, event_id: int, event_type: str, url: str, content: str, *, parent_event_id: int | None = None) -> dict:
    return {
        "run_id": run_id,
        "event_id": event_id,
        "timestamp": float(event_id),
        "event_type": event_type,
        "request_url": url,
        "canonical_url": url,
        "parent_event_id": parent_event_id,
        "content_sha256": sha256_text(content),
        "content_text_or_blob_ref": content,
        "http_status": 200 if event_type == "fetch_body" else None,
        "observable": True,
    }


def ledger(run_id: str, case: dict, mode: str = "full") -> dict:
    events: list[dict] = []
    if mode != "empty":
        event_id = 1
        for index, source in enumerate(case["evidence_sources"]):
            url = str(source["source_url"])
            body = body_for(source)
            if mode == "guessed" and index == 0:
                events.append(event(run_id, event_id, "fetch_body", url, body))
                event_id += 1
                continue
            search_text = f"Search result for {source['subject']}: {url}"
            search_id = event_id
            events.append(event(run_id, search_id, "search_result", url, search_text))
            event_id += 1
            events.append(event(run_id, event_id, "fetch_body", url, body, parent_event_id=search_id))
            event_id += 1
    return {"observation_semantics": "observation_ledger_v1", "run_id": run_id, "capture_complete": True, "events": events}


def write_run(run_id: str, report: str, ledger_value: dict) -> tuple[Path, Path]:
    report_path = OUT / "reports" / f"{run_id}.md"
    ledger_path = OUT / "ledgers" / f"{run_id}.json"
    write_text(report_path, report)
    write_json(ledger_path, ledger_value)
    return report_path, ledger_path


def oracle_entry(case: dict, kind: str) -> dict:
    run_id = f"q41-synthetic-{kind}"
    report_path, ledger_path = write_run(run_id, full_report(case), ledger(run_id, case))
    entry: dict = {"run_id": run_id, "kind": kind, "answer": ANSWER, "report": artifact(report_path), "ledger": artifact(ledger_path)}
    if kind == "minimal":
        entry["minimal_evidence_ids"] = [str(source["evidence_id"]) for source in case["evidence_sources"]]
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
    run_id = f"q41-synthetic-negative-{category}"
    complete = full_report(case)
    evidence = evidence_paragraphs(case)
    facts = "\n\n".join(evidence)
    bridges = "\n\n".join(bridge_paragraphs(case))
    mode = "full"
    answer: str | None = None
    if category == "url_dump":
        report = "\n".join(f"[Frozen page]({source['source_url']})" for source in case["evidence_sources"])
    elif category == "correct_plus_fabricated":
        report = f"{complete}\n\nFabricated extra source: {FABRICATED_URL}"
    elif category == "fetch_all_no_answer":
        report = "I opened every relevant frozen page."
    elif category == "unsupported_answer":
        report = f"{complete}\n\n{ANSWER}"
        mode = "empty"
        answer = ANSWER
    elif category == "fact_dump":
        report = facts
    elif category == "single_source":
        report = "\n\n".join([evidence[0], bridges, *decision_paragraphs(case)])
    elif category == "guessed_then_fetched":
        report = complete
        mode = "guessed"
    elif category == "wrong_binding":
        report = "\n\n".join([*evidence_paragraphs(case, rotate_citations=True), bridges, *decision_paragraphs(case)])
    elif category == "contradictory_decision":
        rejected_phrase = next(
            item for item in case["decidable_claims"]
            if item["contradicts_slot_id"] == "D1"
        )["rejected_matcher"]["accepted_phrases"][0]
        report = f"{facts}\n\n{bridges}\n\n{rejected_phrase}"
    elif category == "silence":
        report = ""
        mode = "empty"
    else:
        raise RuntimeError(f"unknown adversarial category: {category}")
    report_path, ledger_path = write_run(run_id, report, ledger(run_id, case, mode))
    entry: dict = {"run_id": run_id, "category": category, "report": artifact(report_path), "ledger": artifact(ledger_path)}
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
    write_json(graph_path, {"nodes": {str(source["evidence_id"]): source for source in case["evidence_sources"]}})
    suite = {
        "schema": "dra_v3_oracle_suite_v1",
        "suite_id": "q41-remote-pantry-storage-formats-synthetic-mechanism-v1",
        "validation_scope": "synthetic_test",
        "scoring_semantics": "proof_steps_v1",
        "case": artifact(OUT / "case.json"),
        "public_task": artifact(OUT / "public_task.json"),
        "evidence_graph": artifact(graph_path),
        "protocols": artifact(OUT / "protocol.json"),
        "oracles": [oracle_entry(case, "machine"), oracle_entry(case, "human"), oracle_entry(case, "minimal")],
        "adversarial": [adversarial_entry(case, category) for category in ADVERSARIAL_CATEGORIES],
    }
    write_json(OUT / "suite.json", suite)
    print(json.dumps({"suite": str(OUT / "suite.json"), "suite_sha256": file_sha256(OUT / "suite.json"), "oracles": len(suite["oracles"]), "adversarial": len(suite["adversarial"]), "human_status": "pending_human"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
