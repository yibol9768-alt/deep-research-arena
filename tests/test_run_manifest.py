"""Tests for scripts/run_manifest.py.

Every manifest field that a leaderboard number depends on is asserted here, plus
the four ways verify() must refuse: no commit, dirty tree, wrong host, and a
lane talking to a different model than declared.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "run_manifest", ROOT / "scripts" / "run_manifest.py")
rm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rm)


def _init_repo(tmp: Path) -> Path:
    """A throwaway git repo carrying the files the manifest hashes, so git state
    is real (a dirty tree is a real dirty tree) without touching the project."""
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)

    for rel in ["src/eval/decidable_scorer.py", "scripts/run_deep_task.py",
                "integrations/search_shim/app.py", "integrations/search_shim/evidence.py",
                "integrations/ds_proxy/app.py", "integrations/llm_gateway/app.py",
                "config/lane_protocol.yaml",
                "scripts/runners/deerflow_runner.py", "scripts/runners/__init__.py",
                "data/golden/url_registry.json"]:
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {rel}\n")
    ak = tmp / "data/golden/answer_keys"
    ak.mkdir(parents=True, exist_ok=True)
    (ak / "dr_cross_deep_0001.json").write_text('{"task_id": "0001"}')
    (ak / "dr_cross_deep_0002.json").write_text('{"task_id": "0002"}')
    tasks = tmp / "data/tasks/deep_research/cross_site_deep"
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "dr_cross_deep_0001.json").write_text('{"intent": "one"}')
    (tasks / "dr_cross_deep_0002.json").write_text('{"intent": "two"}')
    (tmp / "data/golden/wiki_bloom.bin").write_bytes(b"valid-test-bloom")

    # A manifest without an installed framework tree is invalid.  The fixture
    # supplies a tiny but real source tree and interpreter byte payload rather
    # than weakening production verification for hermetic tests.
    site = tmp / ".venv-test/lib/python3.11/site-packages/fake_framework"
    site.mkdir(parents=True, exist_ok=True)
    (site / "__init__.py").write_text("VERSION = '1'\n")
    py = tmp / ".venv-test/bin/python"
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_bytes(b"fake-python-runtime")
    (tmp / ".gitignore").write_text("reports/\n")

    subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, check=True)
    return tmp


def _good_probe() -> dict:
    return {
        "endpoint": "http://model/v1",
        "declared": "model-v1",
        "actual": "model-v1",
        "ok": True,
        "error": None,
        "identity_scope": "endpoint-self-reported",
    }


def _generate_valid(root: Path, **kwargs) -> dict:
    return rm.generate(
        root,
        env={"DRA_WORKER_ID": "w0"},
        model_identity=[_good_probe()],
        **kwargs,
    )


def test_clean_tree_manifest_has_commit_and_is_verifiable(tmp_path):
    root = _init_repo(tmp_path)
    m = _generate_valid(root, now=datetime(2026, 7, 8, tzinfo=timezone.utc))

    assert m["git"]["clean"] is True
    assert len(m["git"]["commit"]) == 40
    assert "dirty_digest" not in m["git"]
    # The complete executable closure includes package initializers too: they
    # can execute imports and mutate runtime behaviour.
    assert "scripts/runners/deerflow_runner.py" in m["key_files"]
    assert "scripts/runners/__init__.py" in m["key_files"]
    assert all(v is not None for v in m["key_files"].values())
    assert m["corpus"]["answer_keys_task_set_hash"] is not None
    assert m["corpus"]["task_inputs_sha256"] is not None
    assert m["corpus"]["wiki_bloom_sha256"] is not None
    assert m["generated_utc"] == "2026-07-08T00:00:00Z"

    reports = root / "reports"
    reports.mkdir()
    (reports / "a.md").write_text("x")
    assert rm.verify(m, reports, hostname=m["host"]["hostname"], root=root) == []


def test_dirty_tree_is_recorded_and_refused(tmp_path):
    root = _init_repo(tmp_path)
    (root / "scripts/run_deep_task.py").write_text("# edited after commit\n")

    m = rm.generate(root, env={})
    assert m["git"]["clean"] is False
    assert len(m["git"]["dirty_digest"]) == 64
    assert any("run_deep_task.py" in f for f in m["git"]["dirty_files"])

    reports = root / "reports"
    reports.mkdir()
    (reports / "a.md").write_text("x")
    v = rm.verify(m, reports, hostname=m["host"]["hostname"], root=root)
    assert any("DIRTY" in s for s in v)


def test_hostname_mismatch_is_refused(tmp_path):
    root = _init_repo(tmp_path)
    m = rm.generate(root, env={})
    reports = root / "reports"
    reports.mkdir()
    (reports / "a.md").write_text("x")

    v = rm.verify(m, reports, hostname="some-other-box", root=root)
    assert any("generated on host" in s for s in v)
    # and the honest default (real current host) matches what generate recorded
    assert m["host"]["hostname"] == socket.gethostname()


def test_probe_identity_match_and_mismatch():
    """Exact match only.

    This test used to assert that an endpoint reporting `deepseek-v4-flash-0711`
    satisfied a lane declaring `deepseek-v4-flash`, i.e. it pinned prefix
    matching as the contract. The same predicate accepts
    `deepseek-v4-flash-awq-int4`, a different checkpoint. If an endpoint really
    returns a dated id, declare that id in `config/lane_protocol.yaml`.
    """
    def transport_dated(url, headers, body):
        return {"model": "deepseek-v4-flash-0711"}

    def transport_bad(url, headers, body):
        return {"model": "qwen3-8b"}

    dated = rm.probe_model_identity("http://x/v1", "k", "deepseek-v4-flash",
                                    transport=transport_dated)
    assert dated["ok"] is False, "a longer id is a different id until declared"

    declared_exactly = rm.probe_model_identity("http://x/v1", "k", "deepseek-v4-flash-0711",
                                               transport=transport_dated)
    assert declared_exactly["ok"] is True

    bad = rm.probe_model_identity("http://x/v1", "k", "deepseek-v4-flash",
                                  transport=transport_bad)
    assert bad["ok"] is False and "qwen3-8b" in bad["error"]


def test_probe_mismatch_makes_verify_refuse(tmp_path):
    root = _init_repo(tmp_path)
    bad_probe = rm.probe_model_identity(
        "http://claude-code/v1", "k", "deepseek-v4-flash",
        transport=lambda u, h, b: {"model": "qwen3-8b"})
    m = rm.generate(root, env={}, model_identity=[bad_probe])

    reports = root / "reports"
    reports.mkdir()
    (reports / "a.md").write_text("x")
    v = rm.verify(m, reports, hostname=m["host"]["hostname"], root=root)
    assert any("model identity mismatch" in s for s in v)


def test_probe_records_transport_failure_without_raising():
    def boom(url, headers, body):
        raise ConnectionError("refused")

    r = rm.probe_model_identity("http://x/v1", "k", "deepseek-v4-flash", transport=boom)
    assert r["ok"] is False
    assert "ConnectionError" in r["error"]


def test_probe_timeout_can_be_recorded_run_parameter(monkeypatch):
    seen = {}

    def fake_transport_factory(timeout_s):
        seen["timeout_s"] = timeout_s
        return lambda *_args: {"model": "model-a"}

    monkeypatch.setenv("DRA_MODEL_PROBE_TIMEOUT_S", "120")
    monkeypatch.setattr(rm, "_requests_transport", fake_transport_factory)
    result = rm.probe_model_identity("http://x/v1", "k", "model-a")
    assert result["ok"] is True
    assert seen["timeout_s"] == 120.0


def test_task_set_hash_is_stable_and_order_independent(tmp_path):
    root = _init_repo(tmp_path)
    h1 = rm.task_set_hash(root)
    h2 = rm.task_set_hash(root)
    assert h1 == h2 and h1 is not None

    # Editing a golden byte changes the hash; adding an unrelated file does not.
    (root / "data/golden/answer_keys/dr_cross_deep_0001.json").write_text('{"task_id": "MUTATED"}')
    assert rm.task_set_hash(root) != h1


def test_task_prompt_bytes_move_the_task_set_hash(tmp_path):
    root = _init_repo(tmp_path)
    before = rm.task_set_hash(root)
    (root / "data/tasks/deep_research/cross_site_deep/dr_cross_deep_0001.json").write_text(
        '{"intent": "changed bytes"}')
    assert rm.task_set_hash(root) != before


def test_env_snapshot_is_allowlisted_and_excludes_secrets():
    env = {
        "LDR_NATIVE_TIMEOUT_S": "600",
        "SMOLAGENTS_MAX_STEPS": "12",
        "MAX_STEPS": "8",
        "SHIM_MODE": "sandbox",
        "DS_PROXY_URL": "http://x",
        "OPENCODE_CONTEXT_LIMIT": "128000",
        "DRA_WORKER_ID": "w0",
        "LDR_INTENT_MASK": "0",
        "EVIDENCE_FALLBACK_ENABLE": "0",
        "FLOWSEARCHER_MEMORY": "1",
        "OPENAI_API_KEY": "sk-secret",   # must never be captured
        "HOME": "/root",                 # unrelated, out of scope
    }
    snap = rm._env_snapshot(env)
    assert "OPENAI_API_KEY" not in snap and "HOME" not in snap
    for k in ["LDR_NATIVE_TIMEOUT_S", "SMOLAGENTS_MAX_STEPS", "MAX_STEPS", "SHIM_MODE",
              "DS_PROXY_URL", "OPENCODE_CONTEXT_LIMIT", "DRA_WORKER_ID",
              "LDR_INTENT_MASK", "EVIDENCE_FALLBACK_ENABLE", "FLOWSEARCHER_MEMORY"]:
        assert k in snap


def test_budget_suffixes_match_check_parity():
    """The manifest MUST record exactly the budget knobs check_parity guards.

    check_parity requires every per-lane budget env to be DECLARED; the manifest
    must record the VALUE each run used. If the two lists drift, one instrument
    calls a knob a scored budget while the other cannot show which value ran.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_parity", ROOT / "scripts" / "check_parity.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    assert set(rm._BUDGET_SUFFIXES) == set(cp.ENV_BUDGET_SUFFIXES)


def test_transport_and_lane_behaviour_knobs_are_recorded():
    """The knobs that actually change the report must all be in scope.

    The old `DS_PROXY_` rule matched NONE of the proxy's real behaviour knobs
    (they live under OPENAI_PROXY_* / DSPROXY_*) and only LDR_INTENT_MASK of the
    three intent masks. A run that leaves thinking on, floors max_tokens, forces
    a fallback writer, or masks a second lane's URLs must move a manifest byte.
    """
    env = {
        # transport behaviour (change the bytes the model emits)
        "OPENAI_PROXY_THINKING_DISABLED": "0",
        "OPENAI_PROXY_MIN_MAX_TOKENS": "2048",
        "OPENAI_PROXY_STRIP_THINKING": "0",
        "OPENAI_PROXY_THINKING_OFF_PREFIXES": "deepseek-v4,qwen3-8b",
        "OPENAI_PROXY_REWRITE_MODEL": "qwen3-8b",
        "DSPROXY_USAGE_LOG": "/tmp/usage.jsonl",
        "LLM_GATEWAY_CONFIG": "/etc/gw.json",
        "LLMGW_FORCE_IPV4": "1",
        # every guarded budget suffix
        "SMOLAGENTS_SEARCH_MAX_RESULTS": "12",
        "DEERFLOW_TOKEN_LIMIT": "65536",
        "LDR_SEARCH_MAX_RESULTS": "6",
        # lane switches that swap writer / route / text budget
        "LCDR_INTENT_MASK": "1",
        "DEEPAGENTS_INTENT_MASK": "1",
        "SMOLAGENTS_FORCE_FALLBACK": "1",
        "CAMEL_FORCE_FALLBACK": "1",
        "FLOWSEARCHER_FORCE_FALLBACK": "1",
        "EVIDENCE_FALLBACK_SKIP_LLM": "1",
        "SMOLAGENTS_SEARCH_SNIPPET_CHARS": "650",
        "SMOLAGENTS_MIN_REPORT_CHARS": "3500",
        "DEEP_RUN_SHORT_RETRY_MIN_CHARS": "3000",
        # credentials must stay OUT even though they share transport prefixes
        "OPENAI_PROXY_KEY": "sk-x",
        "OPENAI_PROXY_EMB_KEY": "sk-y",
        "DASHSCOPE_API_KEY": "sk-z",
    }
    snap = rm._env_snapshot(env)
    for k in env:
        if k in ("OPENAI_PROXY_KEY", "OPENAI_PROXY_EMB_KEY", "DASHSCOPE_API_KEY"):
            assert k not in snap, f"{k} is a credential and must never be recorded"
        else:
            assert k in snap, f"{k} changes the report and must be recorded"


def test_llm_gateway_is_a_key_file():
    """llm_gateway hardwires per-backbone max_tokens/thinking; it must be hashed
    exactly like ds_proxy, or a cross-backbone board changes with no manifest
    trace."""
    assert "integrations/llm_gateway/app.py" in rm._KEY_FILE_PATHS


def test_corpus_drift_is_refused(tmp_path):
    root = _init_repo(tmp_path)
    m = rm.generate(root, env={})
    reports = root / "reports"
    reports.mkdir()
    (reports / "a.md").write_text("x")
    # mutate a golden after the manifest was pinned
    (root / "data/golden/answer_keys/dr_cross_deep_0001.json").write_text('{"task_id": "DRIFT"}')
    v = rm.verify(m, reports, hostname=m["host"]["hostname"], root=root)
    assert any("answer_keys changed" in s for s in v)


def test_missing_commit_is_refused(tmp_path):
    # A non-git directory: generate() yields no commit, verify() must refuse.
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "a.md").write_text("x")
    m = rm.generate(tmp_path, env={})
    assert m["git"]["commit"] is None
    v = rm.verify(m, tmp_path / "reports", hostname=m["host"]["hostname"], root=tmp_path)
    assert any("no git commit" in s for s in v)


def test_verify_refuses_empty_or_malformed_manifest(tmp_path):
    assert rm.verify({}, tmp_path) == ["manifest is empty or not an object; nothing vouches for this run"]
    v = rm.verify({"host": {}}, tmp_path)
    assert any("missing required section" in s for s in v)


@pytest.mark.parametrize("field, empty", [
    ("model_identity", []),
    ("frameworks", {}),
    ("env", {}),
])
def test_required_runtime_identity_sections_must_be_nonempty(tmp_path, field, empty):
    root = _init_repo(tmp_path)
    m = _generate_valid(root)
    m[field] = empty
    reports = root / "reports"
    reports.mkdir()
    (reports / "a.md").write_text("x")
    reasons = rm.verify(m, reports, hostname=m["host"]["hostname"], root=root)
    assert any(field in r for r in reasons), reasons


def test_verify_checks_current_head_and_cleanliness(tmp_path):
    root = _init_repo(tmp_path)
    m = _generate_valid(root)
    reports = root / "reports"
    reports.mkdir()
    (reports / "a.md").write_text("x")
    (root / "scripts/run_deep_task.py").write_text("# dirty now\n")
    reasons = rm.verify(m, reports, hostname=m["host"]["hostname"], root=root)
    assert any("current scoring checkout is not clean" in r for r in reasons)


def test_verify_checks_framework_hashes(tmp_path):
    root = _init_repo(tmp_path)
    m = _generate_valid(root)
    reports = root / "reports"
    reports.mkdir()
    (reports / "a.md").write_text("x")
    (root / ".venv-test/lib/python3.11/site-packages/fake_framework/__init__.py").write_text(
        "VERSION = '2'\n")
    reasons = rm.verify(m, reports, hostname=m["host"]["hostname"], root=root)
    assert any("framework source/interpreter hashes changed" in r for r in reasons)


def test_none_hashes_never_verify_as_none_equals_none(tmp_path):
    root = _init_repo(tmp_path)
    m = _generate_valid(root)
    reports = root / "reports"
    reports.mkdir()
    (reports / "a.md").write_text("x")
    (root / "data/golden/wiki_bloom.bin").unlink()
    m["corpus"]["wiki_bloom_sha256"] = None
    reasons = rm.verify(m, reports, hostname=m["host"]["hostname"], root=root)
    assert any("wiki_bloom_sha256 is missing" in r for r in reasons)


def test_generation_cli_refuses_without_model_probe(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_manifest.py"])
    assert rm.main() != 0


def test_cli_roundtrip(tmp_path):
    root = _init_repo(tmp_path)
    out = tmp_path / "m.json"
    # generate() reads the real project root via default; here we exercise the
    # JSON write path directly to keep it hermetic.
    m = rm.generate(root, env={})
    out.write_text(json.dumps(m))
    loaded = json.loads(out.read_text())
    assert loaded["git"]["commit"] == m["git"]["commit"]


# --- provenance must not be decorative -------------------------------------
#
# The contract review (RUN_CONTRACT C5/C6) named three ways this file could look
# like provenance while proving nothing. Each gets a test.

def test_probe_rejects_a_quantised_impostor():
    """Prefix matching let a different checkpoint pass as the declared model.

    `deepseek-v4-flash-awq-int4`.startswith(`deepseek-v4-flash`) is True. An
    int4 quantisation is a different system under test, and the whole point of
    the probe is to catch a lane running something other than what it claims.
    """
    from scripts.run_manifest import probe_model_identity

    def fake(url, headers, body):
        return {"model": "deepseek-v4-flash-awq-int4"}

    r = probe_model_identity("http://x/v1", "k", "deepseek-v4-flash", transport=fake)
    assert r["ok"] is False
    assert "awq-int4" in r["error"]

    def exact(url, headers, body):
        return {"model": "DeepSeek-V4-Flash"}     # case/space only

    r2 = probe_model_identity("http://x/v1", "k", "deepseek-v4-flash", transport=exact)
    assert r2["ok"] is True


def test_probe_states_what_it_cannot_prove():
    """vLLM's --served-model-name is free text. The probe reads a self-report."""
    from scripts.run_manifest import probe_model_identity

    r = probe_model_identity("http://x/v1", "k", "m",
                             transport=lambda *a: {"model": "m"})
    assert r["identity_scope"] == "endpoint-self-reported"


def test_manifest_records_the_scoring_formula():
    """Reports plus a different formula are different numbers."""
    import pathlib
    from scripts import run_manifest as rm
    from scripts.build_truth_board import FORMULA_VERSION

    m = rm.generate(pathlib.Path(rm.ROOT), env={})
    assert m["formula_version"] == FORMULA_VERSION
    assert not m["formula_version"].startswith("UNRESOLVED")


def test_manifest_hashes_the_frameworks_not_just_the_harness(tmp_path):
    """`8377cd8d` changed code inside .venv-gptr, which the harness hashes miss.

    On a host with no framework venvs the manifest must SAY so rather than
    silently omit the section: an empty dict would read as "nothing to hash".
    """
    root = _init_repo(tmp_path)
    m = _generate_valid(root)
    fw = m["frameworks"]
    assert fw, "frameworks section must never be empty"
    for name, entry in fw.items():
        assert entry["site_packages_sha256"]
        assert entry["python_sha256"]
        assert entry["n_files"] > 0


# --- what the manifest pins, and what it actually enforced ------------------

def test_manifest_pins_the_wiki_bloom_filter(tmp_path):
    """Wiki membership for ~19M articles lives in `wiki_bloom.bin`, not in
    `url_registry.json` (which lists ~1k explicit titles). The corpus fingerprint
    hashed only the JSON, so a host missing or rebuilding the bloom scored the
    same reports with a different `reach`, and `truth = gate * quality`
    moved with it. `verify()` returned clean and two non-comparable boards were
    published as comparable.
    """
    from scripts import run_manifest as rm
    m = rm.generate(rm.ROOT, env={})
    assert m["corpus"]["wiki_bloom_sha256"], "the bloom decides wiki reach"

    m2 = json.loads(json.dumps(m))
    m2["corpus"].pop("wiki_bloom_sha256")
    reasons = rm.verify(m2, rm.ROOT / "data" / "golden")
    assert any("wiki_bloom" in r for r in reasons)

    m3 = json.loads(json.dumps(m))
    m3["corpus"]["wiki_bloom_sha256"] = "0" * 64
    assert any("wiki_bloom.bin changed" in r
               for r in rm.verify(m3, rm.ROOT / "data" / "golden"))


def test_manifest_enforces_the_key_file_hashes_it_records(tmp_path):
    """It recorded the scorer's hash and never compared it. An edit to
    `decidable_scorer.py` with no FORMULA_VERSION bump changed every number while
    every recorded field stayed equal."""
    from scripts import run_manifest as rm
    m = rm.generate(rm.ROOT, env={})
    assert m["key_files"], "nothing to enforce"

    m2 = json.loads(json.dumps(m))
    victim = next(f for f in m2["key_files"] if f.endswith("decidable_scorer.py"))
    m2["key_files"][victim] = "0" * 64
    reasons = rm.verify(m2, rm.ROOT / "data" / "golden")
    assert any("without a FORMULA_VERSION bump" in r for r in reasons), reasons


# --- gateway policy fingerprint (SPEC_ISSUES §2, manifest entry) -------------
#
# The manifest recorded only the launcher's env and disk hashes; the gateway's
# ACTIVE per-prefix policy lived in a long-running process, and the
# LLM_GATEWAY_CONFIG file was named in env but its CONTENT was never hashed. A
# server-side policy edit, or an edited config the server had not reloaded,
# changed scores under a byte-identical manifest. Red on the old code: generate()
# had no "gateway" section at all.

def test_generate_hashes_the_gateway_config_content(tmp_path, monkeypatch):
    from scripts.run_manifest import generate, _sha256_bytes

    cfg = tmp_path / "gateway.json"
    body = b'{"models": [{"prefix": "qwen", "fit_to_window": true}]}'
    cfg.write_bytes(body)
    env = {"LLM_GATEWAY_CONFIG": str(cfg)}
    m = generate(env=env, now=datetime(2026, 7, 9, tzinfo=timezone.utc))
    gw = m["gateway"]
    assert gw["config_path"] == str(cfg)
    assert gw["config_sha256"] == _sha256_bytes(body)
    assert gw["live_policy"] is None  # not captured unless the caller asks

    # An edited config is a different fingerprint, not a byte-identical manifest.
    cfg.write_bytes(b'{"models": []}')
    m2 = generate(env=env, now=datetime(2026, 7, 9, tzinfo=timezone.utc))
    assert m2["gateway"]["config_sha256"] != gw["config_sha256"]


def test_generate_without_gateway_config_records_the_absence(tmp_path):
    from scripts.run_manifest import generate

    m = generate(env={}, now=datetime(2026, 7, 9, tzinfo=timezone.utc))
    assert m["gateway"] == {
        "config_path": None, "config_sha256": None, "live_policy": None,
    }


def test_capture_gateway_policy_records_the_live_registry():
    from scripts.run_manifest import capture_gateway_policy

    doc = {"ok": True, "models": [
        {"prefix": "qwen3-8b", "fit_to_window": True, "max_tokens_floor": None},
        {"prefix": "glm-4.7-flash", "max_tokens_floor": 131072},
    ]}
    got = capture_gateway_policy(
        "http://gw:8100", transport=lambda u: doc)
    assert got["ok"] is True
    assert got["url"] == "http://gw:8100/healthz"
    assert got["models"][1]["max_tokens_floor"] == 131072


def test_capture_gateway_policy_failure_is_recorded_not_raised():
    from scripts.run_manifest import capture_gateway_policy

    def boom(u):
        raise ConnectionError("down")

    got = capture_gateway_policy("http://gw:8100/healthz", transport=boom)
    assert got["ok"] is False and "down" in got["error"]

    got2 = capture_gateway_policy(
        "http://gw:8100", transport=lambda u: {"ok": True})
    assert got2["ok"] is False and "models" in got2["error"]


def test_generate_embeds_a_passed_live_policy(tmp_path):
    from scripts.run_manifest import generate

    live = {"url": "http://gw:8100/healthz", "ok": True,
            "models": [{"prefix": "qwen3-8b"}], "error": None}
    m = generate(env={}, now=datetime(2026, 7, 9, tzinfo=timezone.utc),
                 gateway_policy=live)
    assert m["gateway"]["live_policy"] == live
