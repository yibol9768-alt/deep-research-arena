from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import nullcontext
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / "runner_patches"


def load_registry_runner():
    spec = importlib.util.spec_from_file_location(
        "bq1_registry_runner_patch_tests",
        ROOT / "scripts" / "registry_bound_runner.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_patch(stem: str):
    # Load the overlays under the exact package name used on any2.  The
    # DeerFlow patch imports ``scripts.runners`` absolutely while the other
    # two patches use relative imports, so a made-up test-only package would
    # exercise a different import contract from production.
    scripts_name = "scripts"
    scripts = sys.modules.get(scripts_name)
    if scripts is None:
        scripts = types.ModuleType(scripts_name)
        scripts.__path__ = []
        sys.modules[scripts_name] = scripts

    package_name = "scripts.runners"
    package = sys.modules.get(package_name)
    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = []
        sys.modules[package_name] = package

        evidence = types.ModuleType(f"{package_name}.evidence_fallback")
        evidence.error_stub = lambda *args, **kwargs: "stub"
        evidence.fallback_enabled = lambda: False
        evidence.is_weak_report = lambda *args, **kwargs: False
        evidence.keep_or_stub = lambda *args, **kwargs: args[-1]
        evidence.synthesize_report = lambda *args, **kwargs: "synthetic"
        sys.modules[evidence.__name__] = evidence

        egress = types.ModuleType(f"{package_name}._egress")
        egress.scrub_or_apply = lambda env: None
        egress.enforced = lambda: False
        egress.remote_enforced = lambda: False
        egress.remote_proxy = lambda: ""
        egress.scratch_path = lambda name: Path(tempfile.gettempdir()) / name
        sys.modules[egress.__name__] = egress

        budget = types.ModuleType(f"{package_name}._budget")
        budget.native_timeout_default = lambda: None
        budget.resolve_native_timeout = lambda _name: None
        budget._coerce_none = lambda value: value
        sys.modules[budget.__name__] = budget

        lock = types.ModuleType(f"{package_name}._runner_lock")
        lock.runner_exclusive_lock = lambda _name: nullcontext()
        sys.modules[lock.__name__] = lock

    module_name = f"{package_name}.{stem}"
    spec = importlib.util.spec_from_file_location(module_name, PATCHES / f"{stem}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class RunnerPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.opencode = load_patch("opencode_runner")
        cls.deerflow = load_patch("deerflow_runner")
        cls.claudecode = load_patch("claudecode_runner")

    def test_opencode_gpt_tools_force_non_reasoning_chat_contract(self):
        cfg = self.opencode._opencode_config(
            "gpt-5.6-sol-2026-07-09",
            "http://127.0.0.1:9999/v1",
            strict_sandbox=True,
            shim_url="http://127.0.0.1:8081",
        )
        model = cfg["provider"]["ds-shim"]["models"][
            "gpt-5.6-sol-2026-07-09"
        ]
        self.assertEqual({"reasoningEffort": "none"}, model["options"])
        self.assertEqual(8192, model["limit"]["output"])
        self.assertNotIn(
            "options",
            cfg["provider"]["ds-shim"]["models"]["deepseek-chat"],
        )

    def test_deerflow_reporter_has_room_after_reasoning_tokens(self):
        self.assertEqual(8192, self.deerflow._resolve_max_output_tokens(None))
        self.assertEqual(4096, self.deerflow._resolve_max_output_tokens("4096"))
        self.assertEqual(8192, self.deerflow._resolve_max_output_tokens("bad"))

    def test_deerflow_claude_route_preserves_native_max_tokens_wire_field(self):
        self.assertTrue(self.deerflow._uses_legacy_max_tokens("claude-opus-5"))
        self.assertFalse(
            self.deerflow._uses_legacy_max_tokens("gpt-5.6-sol-2026-07-09")
        )
        document = self.deerflow._build_conf_yaml(
            "http://127.0.0.1:8081",
            legacy_max_tokens=8192,
        )
        self.assertIn("  extra_body:\n    max_tokens: 8192\n", document)

    def test_claudecode_reads_and_proves_ccr_v3_sqlite_route(self):
        model = "gpt-5.6-sol-2026-07-09"
        endpoint = "http://127.0.0.1:32799/v1/chat/completions"
        document = {
            "PORT": 3481,
            "preferredProvider": "gateway",
            "Providers": [
                {
                    "name": "gateway",
                    "api_base_url": endpoint,
                    "models": [model],
                }
            ],
            "Router": {"rules": []},
            "gateway": {"port": 3481},
        }
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            db = self.claudecode._ccr_sqlite_path(home)
            db.parent.mkdir(parents=True)
            connection = sqlite3.connect(db)
            connection.execute(
                "CREATE TABLE app_config "
                "(key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO app_config VALUES (?, ?, ?)",
                ("default", json.dumps(document), "2026-08-26T00:00:00Z"),
            )
            connection.commit()
            connection.close()

            self.assertEqual(db, self.claudecode._effective_ccr_config_path(home))
            loaded = self.claudecode._read_ccr_config(db)
            self.assertEqual(
                f"gateway,{model}",
                self.claudecode._router_default(loaded, model),
            )
            self.assertTrue(
                self.claudecode._config_routes_model(loaded, model, endpoint)
            )
            self.assertFalse(
                self.claudecode._config_routes_model(
                    loaded, "gpt-5.6-sol-wrong", endpoint
                )
            )

    def test_claudecode_ccr_home_is_bound_to_ephemeral_cell_gateway(self):
        model = "gpt-5.6-sol-2026-07-09"
        first = self.claudecode._ccr_home_for_backbone(
            model, "http://127.0.0.1:32001/v1/chat/completions"
        )
        same = self.claudecode._ccr_home_for_backbone(
            model, "http://127.0.0.1:32001/v1/chat/completions/"
        )
        second = self.claudecode._ccr_home_for_backbone(
            model, "http://127.0.0.1:32002/v1/chat/completions"
        )
        self.assertEqual(first, same)
        self.assertNotEqual(first, second)
        self.assertTrue(first.name.startswith(model + "--"))

    def test_claudecode_cli_inherits_owned_ccr_home_and_disables_telemetry(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            env = self.claudecode._local_claude_environment(
                "http://127.0.0.1:3481", home
            )
        self.assertEqual(str(home), env["HOME"])
        self.assertEqual(str(home / ".claude"), env["CLAUDE_CONFIG_DIR"])
        self.assertEqual("http://127.0.0.1:3481", env["ANTHROPIC_BASE_URL"])
        self.assertEqual("1", env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"])
        self.assertEqual("1", env["DISABLE_TELEMETRY"])
        self.assertEqual("1", env["DISABLE_ERROR_REPORTING"])
        self.assertEqual("127.0.0.1", env["NO_PROXY"])

    def test_registry_installs_all_overlays_under_production_module_names(self):
        registry = load_registry_runner()
        old_root = os.environ.get("DRA_REPO_ROOT")
        try:
            receipt = registry.install_runner_overlays(PATCHES, repo_root=ROOT)
        finally:
            if old_root is None:
                os.environ.pop("DRA_REPO_ROOT", None)
            else:
                os.environ["DRA_REPO_ROOT"] = old_root
        self.assertEqual(
            [
                "scripts.runners.deerflow_runner",
                "scripts.runners.opencode_runner",
                "scripts.runners.claudecode_runner",
            ],
            [row["module"] for row in receipt],
        )
        for row in receipt:
            path = Path(row["path"])
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"]
            )
            module = sys.modules[row["module"]]
            self.assertEqual(path, Path(module.__file__))
            self.assertEqual(ROOT, module.ROOT)
            self.assertIs(
                module,
                getattr(sys.modules["scripts.runners"], row["module"].rsplit(".", 1)[1]),
            )

    def test_registry_overlay_configuration_fails_closed_if_one_is_missing(self):
        registry = load_registry_runner()
        with tempfile.TemporaryDirectory() as temp:
            patch_dir = Path(temp)
            (patch_dir / "deerflow_runner.py").write_text("VALUE = 1\n")
            with self.assertRaisesRegex(
                FileNotFoundError, "missing required runner overlay"
            ):
                registry.install_runner_overlays(patch_dir, repo_root=ROOT)


if __name__ == "__main__":
    unittest.main()
