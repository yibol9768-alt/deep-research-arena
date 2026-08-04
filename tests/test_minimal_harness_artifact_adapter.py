from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from src.scoring.minimal_harness_artifact_adapter import (
    adapt_minimal_harness_run,
    project_minimal_harness_non_delivery,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_sealed_run_projects_delivered_report_and_strict_fetch(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "demo-20260724"
    report = run_dir / "worker/native/report.md"
    report.parent.mkdir(parents=True)
    report.write_text(
        "The product costs $10 "
        "[listing](http://localhost:7770/product.html). "
        "The native index repeats it [1].\n",
        encoding="utf-8",
    )
    attachment = (
        run_dir
        / "worker/native/native/users/default/thread/user-data/outputs/detail.md"
    )
    attachment.parent.mkdir(parents=True)
    attachment.write_text("## Detailed comparison\n\nA delivered table.\n")
    internal_tool_result = (
        attachment.parent
        / ".tool-results"
        / "write_file-failed.txt"
    )
    internal_tool_result.parent.mkdir(parents=True)
    internal_tool_result.write_text(
        "Error invoking write_file with an escaped duplicate of the report.\n",
        encoding="utf-8",
    )
    _write_json(
        run_dir / "worker/native/native/topic/url_to_info.json",
        {
            "url_to_unified_index": {
                "http://localhost:7770/product.html": 1
            },
            "url_to_info": {},
        },
    )
    _write_json(
        run_dir / "control/run-manifest.json",
        {
            "run_id": run_dir.name,
            "harness": "demo",
            "completed": True,
            "report": str(report),
        },
    )

    body = "Product page\nPrice: $10"
    digest = hashlib.sha256(body.encode()).hexdigest()
    blob = run_dir / "control/audit/strict-evidence/blobs" / digest
    blob.parent.mkdir(parents=True)
    blob.write_text(body, encoding="utf-8")
    strict = (
        run_dir
        / "control/audit/strict-evidence"
        / f"{run_dir.name}.jsonl"
    )
    strict.write_text(
        "\n".join(
            [
                json.dumps({"kind": "mark", "phase": "start"}),
                json.dumps(
                    {
                        "kind": "search",
                        "urls_returned": [
                            "http://localhost:7770/product.html"
                        ],
                    }
                ),
                json.dumps(
                    {
                        "kind": "fetch",
                        "url": "http://localhost:7770/product.html",
                        "status": 200,
                        "body_sha256": digest,
                        "endpoint": "/fetch",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = adapt_minimal_harness_run(
        run_dir=run_dir,
        output_dir=tmp_path / "adapted",
    )
    normalized = result["report"].read_text(encoding="utf-8")
    assert '<cite id="legacyobs-0">listing</cite>' in normalized
    assert '<cite id="legacyobs-0">[1]</cite>' in normalized
    assert "Detailed comparison" in normalized
    assert "Error invoking write_file" not in normalized
    sources = json.loads(result["sources"].read_text(encoding="utf-8"))
    assert sources == [
        {
            "url": "http://localhost:7770/product.html",
            "title": "",
            "text": body,
            "raw_content": body,
            "observation_tier": "full_page",
            "strict_body_sha256": digest,
            "strict_endpoint": "/fetch",
        }
    ]
    projection = json.loads(
        result["projection_manifest"].read_text(encoding="utf-8")
    )
    assert projection["report_bundle"]["semantic_inference_used"] is False
    assert projection["observation_projection"]["full_page_document_count"] == 1
    assert projection["native_numbered_source_count"] == 1


def _write_search_ledger(
    run_dir: Path,
    *,
    urls: list[str],
) -> None:
    strict = (
        run_dir
        / "control/audit/strict-evidence"
        / f"{run_dir.name}.jsonl"
    )
    strict.parent.mkdir(parents=True, exist_ok=True)
    strict.write_text(
        json.dumps({"kind": "search", "urls_returned": urls}) + "\n",
        encoding="utf-8",
    )


def _write_minimal_manifest(
    run_dir: Path,
    *,
    harness: str,
) -> None:
    report = run_dir / "worker/native/report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        "A sufficiently long delivered research report with explicit "
        "analysis and a conclusion.\n",
        encoding="utf-8",
    )
    _write_json(
        run_dir / "control/run-manifest.json",
        {
            "run_id": run_dir.name,
            "harness": harness,
            "completed": True,
            "report": str(report),
        },
    )


def test_gpt_researcher_sources_are_ledger_gated_observations(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "gpt-researcher-run"
    _write_minimal_manifest(run_dir, harness="gpt-researcher")
    observed = "http://localhost:7770/observed.html"
    unobserved = "http://localhost:7770/model-only.html"
    _write_search_ledger(run_dir, urls=[observed])
    _write_json(
        run_dir / "worker/native/sources.json",
        [
            {
                "url": observed,
                "title": "Observed",
                "raw_content": "Exact search-result content.",
            },
            {
                "url": unobserved,
                "title": "Not in strict ledger",
                "raw_content": "Must not become evidence.",
            },
        ],
    )

    result = adapt_minimal_harness_run(
        run_dir=run_dir,
        output_dir=tmp_path / "adapted",
    )
    sources = json.loads(result["sources"].read_text(encoding="utf-8"))
    assert [row["url"] for row in sources] == [observed]
    assert sources[0]["text"] == "Exact search-result content."
    assert sources[0]["observation_tier"] == "search_snippet"
    summary = result["summary"]["observation_projection"]
    assert summary["native_artifact_url_count"] == 1
    assert summary["native_artifact_rejected_url_count"] == 1
    assert summary["nonempty_search_observation_count"] == 1


def test_opencode_completed_websearch_output_is_projected(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "opencode-run"
    _write_minimal_manifest(run_dir, harness="opencode")
    url = "http://localhost:9999/f/audio/1/example"
    _write_search_ledger(run_dir, urls=[url])
    event_path = run_dir / "worker/native/native-events.jsonl"
    event_path.write_text(
        json.dumps(
            {
                "type": "tool_use",
                "part": {
                    "tool": "websearch",
                    "state": {
                        "status": "completed",
                        "output": json.dumps(
                            {
                                "results": [
                                    {
                                        "url": url,
                                        "title": "Forum result",
                                        "content": "Exact returned snippet.",
                                    }
                                ]
                            }
                        ),
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = adapt_minimal_harness_run(
        run_dir=run_dir,
        output_dir=tmp_path / "adapted",
    )
    sources = json.loads(result["sources"].read_text(encoding="utf-8"))
    assert sources[0]["url"] == url
    assert sources[0]["text"] == "Exact returned snippet."


def test_miroflow_tool_messages_are_projected_but_assistant_text_is_not(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "miroflow-run"
    _write_minimal_manifest(run_dir, harness="miroflow")
    url = "http://localhost:8090/content/wikipedia_en_all_nopic/IP_Code"
    _write_search_ledger(run_dir, urls=[url])
    trace_path = run_dir / "worker/native/native/task-trace.json"
    _write_json(
        trace_path,
        {
            "sub_agent_message_history_sessions": {
                "worker-1": {
                    "message_history": [
                        {
                            "role": "assistant",
                            "content": "The result must come from the tool.",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "tool-searching-google_search",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        },
                        {
                            "role": "tool",
                            "tool_call_id": "call-1",
                            "content": json.dumps(
                                {
                                    "organic": [
                                        {
                                            "link": url,
                                            "title": "IP Code",
                                            "snippet": "Ingress protection snippet.",
                                        }
                                    ]
                                }
                            ),
                        },
                    ]
                }
            }
        },
    )

    result = adapt_minimal_harness_run(
        run_dir=run_dir,
        output_dir=tmp_path / "adapted",
    )
    sources = json.loads(result["sources"].read_text(encoding="utf-8"))
    assert len(sources) == 1
    assert sources[0]["text"] == "Ingress protection snippet."


def test_gzipped_search_response_blob_is_decoded(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "generic-run"
    _write_minimal_manifest(run_dir, harness="demo")
    url = "http://localhost:7770/compressed.html"
    _write_search_ledger(run_dir, urls=[url])
    payload = json.dumps(
        {
            "results": [
                {
                    "url": url,
                    "title": "Compressed",
                    "content": "Gzip-backed exact snippet.",
                }
            ]
        }
    ).encode()
    body = gzip.compress(payload)
    digest = hashlib.sha256(body).hexdigest()
    blob = run_dir / "control/audit/response-blobs" / digest
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(body)
    egress = run_dir / "control/audit/egress.jsonl"
    egress.write_text(
        json.dumps(
            {
                "status": 200,
                "path": "/search",
                "response_blob_sha256": digest,
                "response_blob_path": str(blob),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = adapt_minimal_harness_run(
        run_dir=run_dir,
        output_dir=tmp_path / "adapted",
    )
    sources = json.loads(result["sources"].read_text(encoding="utf-8"))
    assert sources[0]["text"] == "Gzip-backed exact snippet."


def test_failed_run_without_report_projects_non_delivery(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "qx-failed"
    _write_json(
        run_dir / "control/run-manifest.json",
        {
            "run_id": run_dir.name,
            "harness": "qx-agents",
            "completed": False,
            "failure_type": "OfficialWorkflowFailed",
            "execution": {"outcome": "upstream_failed"},
        },
    )
    _write_search_ledger(
        run_dir,
        urls=["http://localhost:7770/partial-search-result.html"],
    )

    result = project_minimal_harness_non_delivery(
        run_dir=run_dir,
        output_dir=tmp_path / "adapted",
    )
    projection = json.loads(
        result["projection_manifest"].read_text(encoding="utf-8")
    )
    assert projection["non_delivery"] is True
    assert projection["scoreable"] is False
    assert projection["run_failure"] == "OfficialWorkflowFailed"
    assert projection["execution_outcome"] == "upstream_failed"
    assert projection["report_bundle"]["files"] == []
    assert not (tmp_path / "adapted/scorer-inputs").exists()
