from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


build_matrix = load("experimental_build", ROOT / "scripts" / "build_matrix.py")
executor = load("experimental_executor", ROOT / "scripts" / "matrix_executor.py")
registry = load("registry_bound", ROOT / "scripts" / "registry_bound_runner.py")
search_shim = load("cell_search", ROOT / "scripts" / "cell_search_shim.py")
ds_proxy = load("cell_ds", ROOT / "scripts" / "cell_ds_proxy.py")
adapter = load("cell_adapter", ROOT / "scripts" / "task_matrix_adapter.py")
preflight = load("experimental_preflight", ROOT / "scripts" / "preflight.py")
gpt_probe = load("gpt_route_probe", ROOT / "scripts" / "probe_gpt_route_payloads.py")
route_probe = load("all_route_probe", ROOT / "scripts" / "probe_model_routes.py")
supervisor = load("cross5_goal_supervisor", ROOT / "scripts" / "goal_supervisor.py")


def request_json(url: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", "replace")
        raise AssertionError(f"unexpected HTTP {exc.code} from {url}: {payload}") from exc


class OfflineRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((ROOT / "config" / "matrix.source.json").read_text())
        cls.manifest = build_matrix.build(cls.source)
        cls.runtime = json.loads((ROOT / "config" / "runtime.contract.json").read_text())
        cls.routes = json.loads((ROOT / "config" / "model_routes.json").read_text())

    def test_matrix_has_102_runnable_cells(self):
        self.assertEqual(102, len(self.manifest["cells"]))
        blocked = [x for x in self.manifest["cells"] if x["status"] == "blocked"]
        self.assertEqual([], blocked)
        self.assertEqual(102, self.manifest["cell_summary"]["runnable"])
        self.assertEqual("deerflow", self.manifest["cells"][0]["harness_id"])
        self.assertEqual("gpt-5-6-sol", self.manifest["cells"][0]["model_id"])

    def test_cross5_selection_is_exact_and_not_a_cartesian_product(self):
        selection = json.loads((ROOT / "config/cross5.selection.json").read_text())
        manifest = build_matrix.build(self.source, selection)
        self.assertEqual(5, len(manifest["cells"]))
        self.assertEqual(
            list(supervisor.EXPECTED_CROSS5_CELL_IDS),
            [row["cell_id"] for row in manifest["cells"]],
        )
        self.assertEqual("CROSS5_FIXED_HARNESS_FIXED_MODEL", manifest["design"])
        self.assertEqual(3, manifest["concurrency"]["global_cells"])

    def test_runtime_uses_versioned_process_local_runner_overlays(self):
        environment = self.runtime["local_only_harness_environment"]
        self.assertEqual(
            "/data1/deep-research-arena/matrix_workspaces/"
            "biodiv_q1_cross5_20260826_v6/runner_patches",
            environment["DRA_RUNNER_PATCH_DIR"],
        )
        self.assertEqual("", environment["CLAUDE_CODE_SSH_HOST"])
        self.assertEqual("", environment["OPENCODE_SSH_HOST"])

    def test_experimental_labels_do_not_upgrade_formal_state(self):
        self.assertEqual("EXPERIMENTAL_ENABLED", self.manifest["execution_mode"])
        self.assertEqual("STRUCTURAL_READY_UNCALIBRATED", self.manifest["package_decision"])
        self.assertFalse(self.manifest["formal_eligible"])
        self.assertTrue(self.manifest["evaluation_phase_authorized"])
        self.assertTrue(self.manifest["report_generation_authorized"])
        self.assertEqual("SHADOW_EXPERIMENTAL_ONLY", self.manifest["scoring_mode"])

    def test_v2_package_task_and_question_are_sha_bound(self):
        ref = self.manifest["source_package"]["task_json"]
        self.assertIn("biodiv_q1_v2_package_20260826_v1/task_json.json", ref["path"])
        question = "bound question"
        doc = {"task_id": self.manifest["task_id"], "question": question, "formal_eligible": False}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "task.json"
            path.write_text(json.dumps(doc))
            runtime, receipt = registry.load_bound_task(
                path, expected_file_sha=hashlib.sha256(path.read_bytes()).hexdigest(),
                task_id=doc["task_id"], question_sha=hashlib.sha256(question.encode()).hexdigest(),
            )
            self.assertEqual(question, runtime["intent"])
            self.assertEqual("question", receipt["source_field"])
            self.assertFalse(receipt["source_mutated"])
            self.assertNotIn("intent", doc)

    def test_source_census_validator_accepts_only_one_kiwix_source(self):
        self.assertTrue(preflight.source_census_is_kiwix_only({"sources": [{"source": "kiwix", "support_ref_count": 37}]}))
        self.assertFalse(preflight.source_census_is_kiwix_only({"sources": [{"source": "kiwix", "support_ref_count": 37}, {"source": "shopping", "support_ref_count": 1}]}))
        self.assertFalse(preflight.source_census_is_kiwix_only({"sources": [{"source": "kiwix", "support_ref_count": 0}]}))

    def test_initializer_creates_102_non_overwriting_cell_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            executor.initialize(run, "offline-run", self.manifest, self.runtime)
            states = [json.loads(p.read_text()) for p in run.glob("cells/*/state.json")]
            self.assertEqual(102, len(states))
            self.assertEqual(0, sum(x["status"] == "blocked" for x in states))
            header = json.loads((run / "run.json").read_text())
            self.assertEqual("EXPERIMENTAL_ENABLED", header["mode"])
            self.assertFalse(header["formal_eligible"])
            self.assertTrue(header["evaluation_phase_authorized"])
            with self.assertRaises(FileExistsError):
                executor.initialize(run, "offline-run", self.manifest, self.runtime)

    def test_two_search_shims_have_independent_brackets_and_evidence(self):
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_args): return
            def do_POST(self):
                body = json.dumps({"results": [{"url": "https://example.test/a"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True); thread.start()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            servers = [search_shim.start_proxy(upstream=f"http://127.0.0.1:{upstream.server_address[1]}", cell_id=f"cell-{i}", evidence_dir=root/f"evidence-{i}", slot_dir=root/"slots", slot_ledger=root/"slots.jsonl") for i in range(2)]
            try:
                for i, server in enumerate(servers):
                    self.assertEqual(200, request_json(server[2] + "/_mark", {"run_id": f"run-{i}", "phase": "start"})[0])
                    self.assertEqual(200, request_json(server[2] + "/search", {"q": "x"})[0])
                    self.assertEqual(200, request_json(server[2] + "/_mark", {"run_id": f"run-{i}", "phase": "end"})[0])
            finally:
                for server in servers: search_shim.stop_proxy(server[0], server[1])
                upstream.shutdown(); upstream.server_close(); thread.join(timeout=2)
            for i in range(2):
                rows = [json.loads(x) for x in (root/f"evidence-{i}"/f"run-{i}.jsonl").read_text().splitlines()]
                self.assertEqual({f"cell-{i}"}, {x["cell_id"] for x in rows})
                self.assertEqual(["mark", "search", "mark"], [x["kind"] for x in rows])

    def test_cell_ds_proxy_forwards_adams_credential_and_writes_usage(self):
        seen = {}
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_args): return
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0")); request = json.loads(self.rfile.read(length))
                seen.update(
                    path=self.path,
                    authorization=self.headers.get("Authorization"),
                    platform_user=self.headers.get("Adams-Platform-User"),
                    business=self.headers.get("Adams-Business"),
                    model=request.get("model"),
                )
                body = json.dumps({"model": "Qwen3-4B", "choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True); thread.start()
        with tempfile.TemporaryDirectory() as tmp:
            usage = Path(tmp) / "usage.jsonl"
            proxy = ds_proxy.start_proxy(
                upstream_url=f"http://127.0.0.1:{upstream.server_address[1]}/v1",
                credential="secret", credential_header="Authorization",
                credential_scheme="Bearer", cell_id="cell-a", run_id="matrix-a",
                harness_id="smolagents",
                requested_model="Qwen3-4B", expected_identity="Qwen3-4B",
                usage_log=usage,
                extra_headers={"Adams-Platform-User": "sivenfuuliu", "Adams-Business": "3939"},
            )
            try:
                status, _ = request_json(proxy[2] + "/chat/completions", {"model": "caller-alias", "messages": []})
                self.assertEqual(200, status)
            finally:
                ds_proxy.stop_proxy(proxy[0], proxy[1]); upstream.shutdown(); upstream.server_close(); thread.join(timeout=2)
            self.assertEqual("/v1/chat/completions", seen["path"])
            self.assertEqual("Bearer secret", seen["authorization"])
            self.assertEqual("sivenfuuliu", seen["platform_user"])
            self.assertEqual("3939", seen["business"])
            self.assertEqual("Qwen3-4B", seen["model"])
            event = json.loads(usage.read_text())
            self.assertEqual("cell-a", event["matrix_attribution"]["cell_id"])
            self.assertEqual("smolagents", event["harness_id"])
            self.assertEqual("standard", event["service_tier"])
            self.assertEqual(11, event["prompt_tokens_for_pricing"])
            self.assertEqual(11, event["tokens"]["input"])
            self.assertEqual(7, event["tokens"]["output"])
            self.assertNotIn("secret", usage.read_text())

    def test_ds_proxy_never_invents_identity_when_response_omits_model(self):
        actual, usage, service_tier = ds_proxy._parse_response(json.dumps({"error": {"message": "rate limited"}}).encode(), "application/json")
        self.assertIsNone(actual)
        self.assertEqual({}, usage)
        self.assertIsNone(service_tier)

    def test_adapter_reads_observed_actual_identity_and_never_declared_backbone(self):
        self.assertEqual(
            "google/gemini-3.1-pro-preview",
            adapter._actual_identity({
                "backbone": "gemini-3.1-pro-preview",
                "model_identity": {"actual": "google/gemini-3.1-pro-preview"},
            }),
        )
        self.assertIsNone(adapter._actual_identity({"backbone": "declared-only"}))

    def test_gemini_route_separates_upstream_request_name_from_declared_identity(self):
        route = next(
            row for row in self.routes["models"]
            if row["model_id"] == "gemini-3-1-pro-preview"
        )
        self.assertEqual("gemini-3.1-pro-preview", route["request_name"])
        self.assertEqual(
            "google/gemini-3.1-pro-preview",
            route["expected_actual_identity"],
        )
        self.assertNotEqual(route["request_name"], route["expected_actual_identity"])

    def test_gpt_probe_compares_legacy_and_compatible_payloads(self):
        variants = dict(gpt_probe.payloads())
        legacy = variants["legacy_max_tokens_temperature"]
        compatible = variants["max_completion_tokens_no_temperature"]
        self.assertEqual(1, legacy["max_tokens"])
        self.assertEqual(0, legacy["temperature"])
        self.assertNotIn("max_completion_tokens", legacy)
        self.assertEqual(16, compatible["max_completion_tokens"])
        self.assertNotIn("max_tokens", compatible)
        self.assertNotIn("temperature", compatible)

    def test_matrix_gpt_identity_probe_keeps_exact_versioned_identity(self):
        route = next(
            row for row in self.routes["models"]
            if row["model_id"] == "gpt-5-6-sol"
        )
        declared = route["expected_actual_identity"]
        self.assertEqual("gpt-5.6-sol-2026-07-09", declared)
        body = registry.model_probe_payload(
            declared,
            {
                "model": declared,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "temperature": 0,
            },
        )
        self.assertEqual(16, body["max_completion_tokens"])
        self.assertNotIn("max_tokens", body)
        self.assertNotIn("temperature", body)

    def test_all_route_probe_uses_short_request_names_and_exact_identities(self):
        self.assertEqual(6, len(self.routes["models"]))
        for route in self.routes["models"]:
            body = route_probe.probe_payload(route)
            self.assertEqual(route["request_name"], body["model"])
            self.assertTrue(route["expected_actual_identity"])
            if route["model_id"] == "gpt-5-6-sol":
                self.assertEqual(16, body["max_completion_tokens"])
                self.assertNotIn("max_tokens", body)
                self.assertNotIn("temperature", body)
            else:
                self.assertEqual(1, body["max_tokens"])
                self.assertEqual(0, body["temperature"])

    def test_adapter_retry_receipts_are_narrow_and_429_is_terminal(self):
        transport = adapter.normalized_failure_receipt(1, [{"event_id": "e1", "http_status": None, "transport_error_type": "ConnectTimeout"}])
        self.assertTrue(executor.retry_allowed(transport, 0))
        for status in (500, 502, 503, 504):
            receipt = adapter.normalized_failure_receipt(1, [{"event_id": "e", "http_status": status}])
            self.assertTrue(executor.retry_allowed(receipt, 0))
        rate_limited = adapter.normalized_failure_receipt(1, [{"event_id": "e429", "http_status": 429}])
        self.assertEqual("rate_limited", rate_limited["failure_class"])
        self.assertFalse(executor.retry_allowed(rate_limited, 0))
        self.assertFalse(executor.retry_allowed(transport, 1))

    def test_kiwix_only_health_uses_real_upstream_hit_url_and_backend(self):
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_args): return
            def do_GET(self):
                body = json.dumps({
                    "ok": False,
                    "sources": {"shopping": {"n_results": 0}, "forum": {"n_results": 0}, "wiki": {"n_results": 3, "error": None}},
                    "down": {"shopping": "down", "forum": "down"},
                    "sample_urls": ["http://localhost:8090/content/wikipedia_en_all/page"],
                    "query": "biodiversity", "backend_sha256": "a" * 64,
                }).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True); thread.start()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = os.environ.get("DRA_TASK_SOURCE_CENSUS_SHA256")
            os.environ["DRA_TASK_SOURCE_CENSUS_SHA256"] = "b" * 64
            proxy = search_shim.start_proxy(upstream=f"http://127.0.0.1:{upstream.server_address[1]}", cell_id="health-cell", evidence_dir=root/"evidence", slot_dir=root/"slots", slot_ledger=root/"slots.jsonl")
            try:
                with urllib.request.urlopen(proxy[2] + "/_sources/health?fresh=true", timeout=3) as response:
                    health = json.loads(response.read())
                self.assertTrue(health["ok"])
                self.assertEqual({"wiki"}, set(health["sources"]))
                self.assertEqual("a" * 64, health["backend_sha256"])
            finally:
                search_shim.stop_proxy(proxy[0], proxy[1]); upstream.shutdown(); upstream.server_close(); thread.join(timeout=2)
                if old is None: os.environ.pop("DRA_TASK_SOURCE_CENSUS_SHA256", None)
                else: os.environ["DRA_TASK_SOURCE_CENSUS_SHA256"] = old
            receipt = json.loads((root/"evidence"/"source_health_receipts.jsonl").read_text())
            self.assertEqual("PASS", receipt["decision"])
            self.assertEqual(3, receipt["wiki_n_results"])
            self.assertEqual("b" * 64, receipt["task_source_census_sha256"])

    def test_102_runnable_cells_dispatch_with_one_failure_isolated(self):
        fake = '''import json,os,pathlib,sys\nout=pathlib.Path(os.environ["DEEP_RUN_OUT_DIR"]); cell=os.environ["DRA_CELL_ID"]; expected=os.environ["DRA_EXPECTED_MODEL_IDENTITY"]\n(out/"identity.json").write_text(json.dumps({"identity_consistent":True}))\nrow={"cell_id":cell,"actual_model_identity":expected,"matrix_attribution":{"cell_id":cell}}\n(out/"gateway_usage.jsonl").write_text(json.dumps(row)+"\\n")\n(out/"report.md").write_text("report")\n(out/"meta.json").write_text(json.dumps({"status":"pass"}))\n(out/"task_binding.json").write_text(json.dumps({"source_field":"question"}))\n(out/"observability.json").write_text(json.dumps({"schema_version":"2.0.0","recorder_initialized":True,"capture_bracket_valid":True,"capture_healthy":True,"search_call_count":1,"fetch_call_count":1,"search":"observed","fetch":"observed"}))\n(out/"report_provenance.json").write_text(json.dumps({"model_output_attested":True,"length_threshold_used":False,"url_count_threshold_used":False}))\nev=out/"search_evidence"; ev.mkdir(); (ev/"run.jsonl").write_text(json.dumps({"kind":"search"})+"\\n"+json.dumps({"kind":"fetch"})+"\\n")\nfailed="--camel-ai--qwen3-4b" in cell\nif failed: (out/"failure_receipt.json").write_text(json.dumps({"source":"adapter_normalized_exception","failure_class":"rate_limited","http_status":429}))\npathlib.Path(os.environ["DRA_PROGRESS_HEARTBEAT"]).touch()\nsys.exit(1 if failed else 0)\n'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fake_path = root / "fake.py"; fake_path.write_text(fake)
            run = root / "run"; executor.initialize(run, "dispatch-test", self.manifest, self.runtime)
            env = dict(os.environ); env.update(TRUTH1000_ADAMS_USER_TOKEN="memory-only", DRA_SEARCH_UPSTREAM_URL="http://127.0.0.1:1")
            summary = asyncio.run(executor.dispatch(self.manifest, self.runtime, self.routes, run, env_base=env, adapter_command=[sys.executable, str(fake_path)], watchdog=3))
            self.assertEqual(102, summary["cell_count"])
            self.assertEqual(101, summary["success"])
            self.assertEqual(1, summary["failed"])
            self.assertEqual(0, summary["blocked"])
            self.assertEqual(102, summary["usage_event_count"])
            self.assertTrue(all(value == 1 for value in summary["max_active_per_model"].values()))
            self.assertEqual(1, summary["max_active_cells"])
            self.assertEqual("STRICT_MANIFEST_ORDINAL_SERIAL", summary["execution_policy"])
            failed = next(row for row in summary["results"] if row["status"] == "failed")
            self.assertEqual("rate_limited_http_429", failed["reason"])
            transitions = [json.loads(line) for line in (run/"ledger"/"transitions.jsonl").read_text().splitlines()]
            ready = [row["cell_id"] for row in transitions if row["to"] == "ready"]
            first = self.manifest["cells"][0]
            self.assertEqual(first["cell_id"], ready[0])
            ordinal = {cell["cell_id"]: cell["ordinal"] for cell in self.manifest["cells"]}
            model = {cell["cell_id"]: cell["model_id"] for cell in self.manifest["cells"]}
            self.assertEqual(sorted(ordinal[cell_id] for cell_id in ready), [ordinal[cell_id] for cell_id in ready])

    def test_five_cell_cross_design_runs_parallel_without_same_model_overlap(self):
        selected_ids = {
            "biodiversity-q1-v2--deerflow--gpt-5-6-sol",
            "biodiversity-q1-v2--deerflow--gemini-3-1-pro-preview",
            "biodiversity-q1-v2--deerflow--claude-opus-5",
            "biodiversity-q1-v2--opencode--gpt-5-6-sol",
            "biodiversity-q1-v2--claude-code--gpt-5-6-sol",
        }
        selected = [
            cell for cell in self.manifest["cells"]
            if cell["cell_id"] in selected_ids
        ]
        self.assertEqual(5, len(selected))
        fake = '''import json,os,pathlib,time\nout=pathlib.Path(os.environ["DEEP_RUN_OUT_DIR"]); cell=os.environ["DRA_CELL_ID"]; expected=os.environ["DRA_EXPECTED_MODEL_IDENTITY"]\n(out/"identity.json").write_text(json.dumps({"identity_consistent":True}))\nrow={"cell_id":cell,"actual_model_identity":expected,"matrix_attribution":{"cell_id":cell}}\n(out/"gateway_usage.jsonl").write_text(json.dumps(row)+"\\n")\n(out/"report.md").write_text("report")\n(out/"meta.json").write_text(json.dumps({"status":"pass"}))\n(out/"task_binding.json").write_text(json.dumps({"source_field":"question"}))\n(out/"observability.json").write_text(json.dumps({"schema_version":"2.0.0","recorder_initialized":True,"capture_bracket_valid":True,"capture_healthy":True,"search_call_count":1,"fetch_call_count":1,"search":"observed","fetch":"observed"}))\n(out/"report_provenance.json").write_text(json.dumps({"model_output_attested":True,"length_threshold_used":False,"url_count_threshold_used":False}))\nev=out/"search_evidence"; ev.mkdir(); (ev/"run.jsonl").write_text(json.dumps({"kind":"search"})+"\\n"+json.dumps({"kind":"fetch"})+"\\n")\npathlib.Path(os.environ["DRA_PROGRESS_HEARTBEAT"]).touch(); time.sleep(.1)\n'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fake_path = root / "fake.py"; fake_path.write_text(fake)
            run = root / "run"; executor.initialize(run, "five-cell-test", self.manifest, self.runtime)
            env = dict(os.environ); env.update(TRUTH1000_ADAMS_USER_TOKEN="memory-only", DRA_SEARCH_UPSTREAM_URL="http://127.0.0.1:1")
            summary = asyncio.run(executor.dispatch(
                self.manifest, self.runtime, self.routes, run,
                cells=selected, env_base=env,
                adapter_command=[sys.executable, str(fake_path)], watchdog=3,
                parallel=True, global_cells=3,
            ))
            self.assertEqual(5, summary["success"])
            self.assertEqual(97, summary["pending"])
            self.assertEqual(0, summary["blocked"])
            self.assertEqual(5, summary["processed_this_invocation"])
            self.assertEqual("PARALLEL_MODEL_LANES_ONE_CELL_PER_MODEL", summary["execution_policy"])
            self.assertEqual(3, summary["global_cell_limit"])
            self.assertGreaterEqual(summary["max_active_cells"], 2)
            self.assertTrue(all(value == 1 for value in summary["max_active_per_model"].values()))

    def test_attested_harness_failure_retries_as_new_attempt_without_overwrite(self):
        cell = self.manifest["cells"][0]
        fake = '''import json,os,pathlib,sys
out=pathlib.Path(os.environ["DEEP_RUN_OUT_DIR"]); cell=os.environ["DRA_CELL_ID"]; expected=os.environ["DRA_EXPECTED_MODEL_IDENTITY"]
attempt=int(out.name.split("-")[-1]); failed=attempt == 1
(out/"identity.json").write_text(json.dumps({"identity_consistent":True}))
row={"cell_id":cell,"actual_model_identity":expected,"matrix_attribution":{"cell_id":cell}}
(out/"gateway_usage.jsonl").write_text(json.dumps(row)+"\\n")
(out/"report.md").write_text("internal stub" if failed else "real model report")
(out/"meta.json").write_text(json.dumps({"status":"fail" if failed else "pass"}))
(out/"task_binding.json").write_text(json.dumps({"source_field":"question"}))
(out/"observability.json").write_text(json.dumps({"schema_version":"2.0.0","recorder_initialized":True,"capture_bracket_valid":True,"capture_healthy":True,"search_call_count":1,"fetch_call_count":1,"search":"observed","fetch":"observed"}))
(out/"report_provenance.json").write_text(json.dumps({"model_output_attested":not failed,"internal_error_stub":failed,"length_threshold_used":False,"url_count_threshold_used":False}))
ev=out/"search_evidence"; ev.mkdir(); (ev/"run.jsonl").write_text(json.dumps({"kind":"search"})+"\\n"+json.dumps({"kind":"fetch"})+"\\n")
if failed: (out/"failure_receipt.json").write_text(json.dumps({"source":"adapter_normalized_exception","failure_class":"task_failure","runner_exit_code":1,"http_status":200}))
pathlib.Path(os.environ["DRA_PROGRESS_HEARTBEAT"]).touch(); sys.exit(1 if failed else 0)
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_path = root / "fake_retry.py"
            fake_path.write_text(fake)
            run = root / "run"
            executor.initialize(run, "retry-test", self.manifest, self.runtime)
            env = dict(os.environ)
            env.update(
                TRUTH1000_ADAMS_USER_TOKEN="memory-only",
                DRA_SEARCH_UPSTREAM_URL="http://127.0.0.1:1",
            )
            first = asyncio.run(
                executor.dispatch(
                    self.manifest,
                    self.runtime,
                    self.routes,
                    run,
                    cells=[cell],
                    env_base=env,
                    adapter_command=[sys.executable, str(fake_path)],
                    watchdog=3,
                )
            )
            self.assertEqual(1, first["failed"])
            attempt_one_seal = run / "cells" / cell["cell_id"] / "attempt-1/seal.json"
            attempt_one_sha = hashlib.sha256(attempt_one_seal.read_bytes()).hexdigest()

            second = asyncio.run(
                executor.dispatch(
                    self.manifest,
                    self.runtime,
                    self.routes,
                    run,
                    cells=[cell],
                    env_base=env,
                    adapter_command=[sys.executable, str(fake_path)],
                    watchdog=3,
                    retry_failed_infrastructure=True,
                )
            )
            self.assertEqual(1, second["success"])
            self.assertEqual(
                attempt_one_sha,
                hashlib.sha256(attempt_one_seal.read_bytes()).hexdigest(),
            )
            state = json.loads(
                (run / "cells" / cell["cell_id"] / "state.json").read_text()
            )
            self.assertEqual("success", state["status"])
            self.assertEqual(2, state["attempt_count"])
            self.assertEqual(2, state["usage_event_count"])
            self.assertTrue(
                (run / "cells" / cell["cell_id"] / "attempt-2/seal.json").is_file()
            )
            cell_seal = json.loads(
                (run / "cells" / cell["cell_id"] / "seal.json").read_text()
            )
            self.assertEqual(2, len(cell_seal["attempt_seals"]))
            transitions = [
                json.loads(line)
                for line in (run / "ledger/transitions.jsonl").read_text().splitlines()
            ]
            self.assertIn(
                ("failed", "retry_ready"),
                [(row["from"], row["to"]) for row in transitions],
            )
            self.assertIn(
                ("retry_ready", "running"),
                [(row["from"], row["to"]) for row in transitions],
            )
            with self.assertRaisesRegex(ValueError, "unsafe infrastructure retry"):
                asyncio.run(
                    executor.dispatch(
                        self.manifest,
                        self.runtime,
                        self.routes,
                        run,
                        cells=[cell],
                        env_base=env,
                        adapter_command=[sys.executable, str(fake_path)],
                        watchdog=3,
                        retry_failed_infrastructure=True,
                    )
                )
            self.assertEqual(
                "success",
                json.loads(
                    (run / "cells" / cell["cell_id"] / "state.json").read_text()
                )["status"],
            )


if __name__ == "__main__":
    unittest.main()
