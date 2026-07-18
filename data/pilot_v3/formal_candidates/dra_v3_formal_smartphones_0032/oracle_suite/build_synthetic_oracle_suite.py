#!/usr/bin/env python3
"""Build the explicitly synthetic Q32 oracle/adversarial replay bundle.

This fixture exercises the production proof-step scorer.  Its human-shaped
entry is intentionally marked synthetic and cannot satisfy the independent
human-review gate.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
TASK_ID = "dra_v3_formal_smartphones_0032"
ANSWER = (
    "verify_the_exact_variant_carrier_return_terms_and_update_support_then_"
    "trial_the_real_tasks_my_mother_uses"
)
FABRICATED_URL = "http://localhost:9999/not-in-q32-frozen-corpus"

CASE_SOURCE = (
    ROOT
    / "data/golden/cases_v3/formal_candidates"
    / f"{TASK_ID}.json"
)
PUBLIC_SOURCE = (
    ROOT
    / "data/tasks/deep_research/v3/formal_candidates"
    / f"{TASK_ID}.json"
)
PROTOCOL_SOURCE = (
    ROOT
    / "data/pilot_v3/formal_candidates"
    / TASK_ID
    / "protocol_manifests/protocol.json"
)
CAPTURE_BLOBS = (
    ROOT
    / "data/evidence_graph/captures"
    / "v3-corpus-formal-smartphones-0032-rating-longevity-boundary-20260716-r1"
    / "blobs"
)

ARTIFACTS = HERE / "artifacts"
REPORTS = HERE / "reports"
LEDGERS = HERE / "ledgers"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def artifact(path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(HERE).as_posix(),
        "sha256": sha256_bytes(path.read_bytes()),
    }


def accepted_phrase(value: dict) -> str:
    phrases = value.get("accepted_phrases")
    if not isinstance(phrases, list) or not phrases:
        raise ValueError("matcher has no accepted phrase")
    return str(phrases[0])


def unique_sources(case: dict) -> list[tuple[str, str, str]]:
    by_url: dict[str, tuple[str, str, str]] = {}
    for source in case["evidence_sources"]:
        url = source["source_url"]
        digest = source["content_sha256"]
        body_path = CAPTURE_BLOBS / digest
        body = body_path.read_text(encoding="utf-8")
        if sha256_text(body) != digest:
            raise ValueError(f"blob bytes disagree for {url}")
        by_url[url] = (url, digest, body)
    return [by_url[url] for url in sorted(by_url)]


def ledger(run_id: str, sources: list[tuple[str, str, str]], mode: str) -> dict:
    if mode == "empty":
        events: list[dict] = []
    else:
        events = []
        event_id = 1
        for index, (url, digest, body) in enumerate(sources):
            if mode == "guessed" and index == 0:
                events.append(
                    {
                        "run_id": run_id,
                        "event_id": event_id,
                        "timestamp": float(event_id),
                        "event_type": "fetch_body",
                        "request_url": url,
                        "canonical_url": url,
                        "parent_event_id": None,
                        "content_sha256": digest,
                        "content_text_or_blob_ref": body,
                        "http_status": 200,
                        "observable": True,
                    }
                )
                event_id += 1
                continue
            snippet = f"Search result locating the frozen Q32 source at {url}"
            search_id = event_id
            events.append(
                {
                    "run_id": run_id,
                    "event_id": search_id,
                    "timestamp": float(search_id),
                    "event_type": "search_result",
                    "request_url": url,
                    "canonical_url": url,
                    "parent_event_id": None,
                    "content_sha256": sha256_text(snippet),
                    "content_text_or_blob_ref": snippet,
                    "http_status": None,
                    "observable": True,
                }
            )
            event_id += 1
            events.append(
                {
                    "run_id": run_id,
                    "event_id": event_id,
                    "timestamp": float(event_id),
                    "event_type": "fetch_body",
                    "request_url": url,
                    "canonical_url": url,
                    "parent_event_id": search_id,
                    "content_sha256": digest,
                    "content_text_or_blob_ref": body,
                    "http_status": 200,
                    "observable": True,
                }
            )
            event_id += 1
    return {
        "observation_semantics": "observation_ledger_v1",
        "run_id": run_id,
        "capture_complete": True,
        "events": events,
    }


def main() -> None:
    for directory in (ARTIFACTS, REPORTS, LEDGERS):
        directory.mkdir(parents=True, exist_ok=True)

    copied = {
        "case": ARTIFACTS / "case.json",
        "public_task": ARTIFACTS / "public_task.json",
        "protocols": ARTIFACTS / "protocol.json",
    }
    shutil.copyfile(CASE_SOURCE, copied["case"])
    shutil.copyfile(PUBLIC_SOURCE, copied["public_task"])
    shutil.copyfile(PROTOCOL_SOURCE, copied["protocols"])

    case = json.loads(copied["case"].read_text(encoding="utf-8"))
    sources = unique_sources(case)
    source_urls = [url for url, _, _ in sources]

    graph_path = ARTIFACTS / "evidence_graph.json"
    write_json(
        graph_path,
        {
            "nodes": {
                source["evidence_id"]: source
                for source in case["evidence_sources"]
            }
        },
    )

    evidence_rows: list[tuple[dict, str]] = []
    for source in case["evidence_sources"]:
        phrase = accepted_phrase(source["verifier"])
        evidence_rows.append(
            (source, f"{phrase} [source]({source['source_url']}).")
        )
    evidence_report = " ".join(text for _, text in evidence_rows)

    bridge_steps = [
        step
        for step in case["evaluator_view"]["required_proof_steps"]
        if step["type"] == "bridge"
    ]
    bridge_report = "\n\n".join(
        accepted_phrase(case["rule_definitions"][step["rule"]])
        for step in bridge_steps
    )

    decision_step = next(
        step
        for step in case["evaluator_view"]["required_proof_steps"]
        if step["type"] == "decision"
    )
    decision_rule = case["rule_definitions"][decision_step["rule"]]

    def conditional_decision_report(condition: dict) -> str:
        answer = condition["answer"]
        parts = [
            accepted_phrase(decision_rule["decision_matcher"]),
            accepted_phrase(condition["condition_matcher"]),
            *(
                accepted_phrase(matcher)
                for matcher in condition["tradeoff_matchers"].values()
            ),
            accepted_phrase(decision_rule["conclusion_matchers"][answer]),
        ]
        return " ".join(parts)

    condition = next(
        item
        for item in decision_rule["admissible_conditions"]
        if item["answer"] == ANSWER
    )
    decision_report = conditional_decision_report(condition)
    full_report = f"{evidence_report}\n\n{bridge_report}\n\n{decision_report}"

    positive_path = REPORTS / "positive.md"
    write_text(positive_path, full_report)
    alternative_paths: dict[str, Path] = {}
    for alternative in decision_rule["admissible_conditions"]:
        answer = alternative["answer"]
        path = REPORTS / f"admissible_{answer}.md"
        write_text(
            path,
            f"{evidence_report}\n\n{bridge_report}\n\n"
            f"{conditional_decision_report(alternative)}",
        )
        alternative_paths[answer] = path

    fact_dump_path = REPORTS / "fact_dump.md"
    write_text(fact_dump_path, evidence_report)
    url_dump_path = REPORTS / "url_dump.md"
    write_text(
        url_dump_path,
        "Sources only: " + " ".join(f"[source]({url})" for url in source_urls),
    )
    fabricated_path = REPORTS / "correct_plus_fabricated.md"
    write_text(
        fabricated_path,
        f"{full_report}\n\nFabricated extra citation: [fabricated]({FABRICATED_URL}).",
    )
    no_answer_path = REPORTS / "fetch_all_no_answer.md"
    write_text(
        no_answer_path,
        "I opened every relevant page but give no findings or conclusion.",
    )
    unsupported_path = REPORTS / "unsupported_answer.md"
    write_text(
        unsupported_path,
        full_report
        + "\n\n"
        + ANSWER.replace("_", " ").capitalize()
        + ".",
    )

    single_url = source_urls[0]
    single_evidence = " ".join(
        text
        for source, text in evidence_rows
        if source["source_url"] == single_url
    )
    single_path = REPORTS / "single_source.md"
    write_text(single_path, f"{single_evidence}\n\n{bridge_report}\n\n{decision_report}")

    rotated = {
        url: source_urls[(index + 1) % len(source_urls)]
        for index, url in enumerate(source_urls)
    }
    wrong_binding_report = " ".join(
        f"{accepted_phrase(source['verifier'])} "
        f"[wrong source]({rotated[source['source_url']]})."
        for source in case["evidence_sources"]
    )
    wrong_binding_path = REPORTS / "wrong_binding.md"
    write_text(
        wrong_binding_path,
        f"{wrong_binding_report}\n\n{bridge_report}\n\n{decision_report}",
    )

    contradiction = next(
        claim["rejected_matcher"]["accepted_phrases"][0]
        for claim in case["decidable_claims"]
        if claim["contradicts_slot_id"] == decision_step["step_id"]
    )
    contradictory_path = REPORTS / "contradictory_decision.md"
    write_text(
        contradictory_path,
        f"{evidence_report}\n\n{bridge_report}\n\n{contradiction}",
    )
    silence_path = REPORTS / "silence.md"
    write_text(silence_path, "")

    report_paths = {
        "url_dump": url_dump_path,
        "correct_plus_fabricated": fabricated_path,
        "fetch_all_no_answer": no_answer_path,
        "unsupported_answer": unsupported_path,
        "fact_dump": fact_dump_path,
        "single_source": single_path,
        "guessed_then_fetched": positive_path,
        "wrong_binding": wrong_binding_path,
        "contradictory_decision": contradictory_path,
        "silence": silence_path,
    }

    oracle_entries: list[dict] = []
    for kind, run_id in (
        ("machine", "q32-oracle-machine"),
        ("human", "q32-oracle-llm-synthetic-human-placeholder"),
        ("minimal", "q32-oracle-minimal"),
    ):
        ledger_path = LEDGERS / f"{run_id}.json"
        write_json(ledger_path, ledger(run_id, sources, "full"))
        entry: dict = {
            "run_id": run_id,
            "kind": kind,
            "answer": ANSWER,
            "report": artifact(positive_path),
            "ledger": artifact(ledger_path),
        }
        if kind == "minimal":
            entry["minimal_evidence_ids"] = sorted(
                source["evidence_id"] for source in case["evidence_sources"]
            )
        if kind == "human":
            entry["manual_record"] = {
                "origin": "manual",
                "reviewer": "llm-simulated-not-a-human-reviewer",
                "solve_minutes": 0.1,
                "access_path": source_urls,
                "attested": True,
                "synthetic": True,
            }
        oracle_entries.append(entry)

    for answer, report_path in sorted(alternative_paths.items()):
        run_id = f"q32-oracle-admissible-{answer}"
        ledger_path = LEDGERS / f"{run_id}.json"
        write_json(ledger_path, ledger(run_id, sources, "full"))
        oracle_entries.append(
            {
                "run_id": run_id,
                "kind": "admissible_alternative",
                "answer": answer,
                "report": artifact(report_path),
                "ledger": artifact(ledger_path),
            }
        )

    adversarial_entries: list[dict] = []
    categories = (
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
    for category in categories:
        run_id = f"q32-adversarial-{category}"
        ledger_mode = (
            "empty"
            if category in {"unsupported_answer", "silence"}
            else "guessed"
            if category == "guessed_then_fetched"
            else "full"
        )
        ledger_path = LEDGERS / f"{run_id}.json"
        write_json(ledger_path, ledger(run_id, sources, ledger_mode))
        entry = {
            "run_id": run_id,
            "category": category,
            "report": artifact(report_paths[category]),
            "ledger": artifact(ledger_path),
        }
        if category == "unsupported_answer":
            entry["answer"] = ANSWER
        adversarial_entries.append(entry)

    suite = {
        "schema": "dra_v3_oracle_suite_v1",
        "suite_id": "q32-llm-simulated-oracle-adversarial-v1",
        "validation_scope": "synthetic_test",
        "scoring_semantics": "proof_steps_v1",
        "case": artifact(copied["case"]),
        "public_task": artifact(copied["public_task"]),
        "evidence_graph": artifact(graph_path),
        "protocols": artifact(copied["protocols"]),
        "oracles": oracle_entries,
        "adversarial": adversarial_entries,
    }
    write_json(HERE / "suite.synthetic.json", suite)


if __name__ == "__main__":
    main()
