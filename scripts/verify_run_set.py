#!/usr/bin/env python3
"""Fail-closed integrity gates for governed leaderboard run sets.

This module deliberately keeps run-set provenance outside the framework
runner.  A runner writes its native report and sidecar first; this gate then
binds those exact bytes to one run set, backbone, replicate, and manifest.
Legacy artifacts without that binding are not resumable or publishable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[1]
INTEGRITY_VERSION = "run-set-integrity-v2"
RUN_PLAN_VERSION = "formal-run-plan-v1"
RUN_STATUSES = frozenset({"pass", "fail", "stalled", "infra_abort", "timeout"})
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FALLBACK_REPORT_SIGNATURES = (
    "this source remains relevant because it anchors the answer to a "
    "retrieved local record rather than an unsupported assumption",
    "evidence-fallback writer is benchmark-disabled",
    "force_evidence_fallback_all=1",
)


class IntegrityError(ValueError):
    """Raised when an artifact cannot be admitted to a formal run set."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise IntegrityError(f"{path}: unreadable JSON: {type(exc).__name__}: {exc}") from exc
    if not isinstance(value, dict):
        raise IntegrityError(f"{path}: JSON root must be an object")
    return value


def _run_plan_sha_for_manifest(manifest_path: Path) -> str | None:
    plan_path = manifest_path.parent / "run_plan.json"
    return _sha256_file(plan_path) if plan_path.is_file() else None


def _safe_id(value: str, label: str) -> None:
    if not _SAFE_ID_RE.fullmatch(value or ""):
        raise IntegrityError(
            f"{label}={value!r} is unsafe; use only letters, digits, '.', '_' and '-'"
        )


def protocol_lane_names(protocol_path: Path | None = None) -> set[str]:
    path = protocol_path or ROOT / "config" / "lane_protocol.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        raise IntegrityError(f"cannot read lane protocol {path}: {exc}") from exc
    lanes = data.get("lanes")
    if not isinstance(lanes, dict) or not lanes:
        raise IntegrityError(f"{path}: lanes must be a non-empty mapping")
    bad = sorted(name for name in lanes if not isinstance(name, str) or not name.strip())
    if bad:
        raise IntegrityError(f"{path}: invalid lane names: {bad}")
    return set(lanes)


def runtime_runner_names() -> set[str]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from scripts.run_deep_task import RUNNERS
    except Exception as exc:  # noqa: BLE001
        raise IntegrityError(
            f"cannot load scripts.run_deep_task.RUNNERS: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(RUNNERS, dict) or not RUNNERS:
        raise IntegrityError("scripts.run_deep_task.RUNNERS is empty or malformed")
    return set(RUNNERS)


def assert_lane_registry_parity(
    *,
    protocol_names: Iterable[str] | None = None,
    runner_names: Iterable[str] | None = None,
) -> list[str]:
    """Return the common lane set, or raise on either direction of drift."""
    declared = set(protocol_names) if protocol_names is not None else protocol_lane_names()
    runners = set(runner_names) if runner_names is not None else runtime_runner_names()
    missing_runners = sorted(declared - runners)
    undeclared_runners = sorted(runners - declared)
    if missing_runners or undeclared_runners:
        raise IntegrityError(
            "RUNNERS/lane_protocol mismatch: "
            f"declared_without_runner={missing_runners}, "
            f"runner_without_declaration={undeclared_runners}"
        )
    return sorted(declared)


def forbidden_fallback_env(env: Mapping[str, str] | None = None) -> list[str]:
    """List fallback controls that must not exist in a formal run process.

    Presence is rejected even when a value looks false. This avoids different
    shells disagreeing about values such as ``off``, ``native`` or ``0`` and
    keeps the formal environment unambiguous.
    """
    source = os.environ if env is None else env
    bad: list[str] = []
    for raw_name in source:
        name = str(raw_name).upper()
        forbidden = (
            name == "FORCE_EVIDENCE_FALLBACK_ALL"
            or name == "FLOWSEARCHER_MEMORY"
            or name.startswith("EVIDENCE_FALLBACK_")
            or name.endswith("_FORCE_FALLBACK")
            or ("FALLBACK" in name and "NO_WINDOWS_FALLBACK" not in name)
        )
        if forbidden:
            bad.append(str(raw_name))
    return sorted(bad)


_COMPARATIVE_OVERRIDE_SUFFIXES = (
    "_MAX_STEPS",
    "_SEARCH_MAX_RESULTS",
    "_TOKEN_LIMIT",
    "_CONTEXT_LIMIT",
    "_SEARCH_SNIPPET_CHARS",
    "_MIN_REPORT_CHARS",
    "_SHORT_RETRY_MIN_CHARS",
    "_MAX_OUTPUT_TOKENS",
    "_SEARCH_ITERATIONS",
    "_QUESTIONS_PER_ITERATION",
    "_NATIVE_TIMEOUT_S",
)
_COMPARATIVE_OVERRIDE_EXACT = frozenset({
    "DZHNG_BREADTH",
    "DZHNG_DEPTH",
    "MAX_WEB_RESEARCH_LOOPS",
    "FETCH_FULL_PAGE",
    "DEEP_RUN_SKIP_SOURCE_CHECK",
    "DRA_WALL_CLOCK_S",
    "LANGCHAIN_ODR_GRAPH_TIMEOUT_S",
    "QX_AGENTS_HARD_TIMEOUT_S",
    "OPENCODE_TIMEOUT",
    "FLOWSEARCHER_PAGES_PER_SUBGOAL",
    "FLOWSEARCHER_PER_PAGE_CHARS",
    "FLOWSEARCHER_SHIM_URL",
    "FLOWSEARCHER_LLM_TIMEOUT",
    "FLOWSEARCHER_FETCH_TIMEOUT",
})


def forbidden_comparative_env(
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Operator knobs that change only one lane's scored opportunity.

    Formal runs use the code/config defaults pinned by the manifest and lane
    protocol. Presence is forbidden even for ``"0"``, ``"false"`` or an empty
    value: adapters disagree on false-like parsing, and merely exporting a knob
    is not a locked protocol profile.
    """
    source = os.environ if env is None else env
    bad: list[str] = []
    for raw_name in source:
        name = str(raw_name).upper()
        if (name.endswith("_INTENT_MASK")
                or name.endswith(_COMPARATIVE_OVERRIDE_SUFFIXES)
                or name in _COMPARATIVE_OVERRIDE_EXACT):
            bad.append(str(raw_name))
    return sorted(bad)


def assert_formal_environment(env: Mapping[str, str] | None = None) -> None:
    fallback = forbidden_fallback_env(env)
    comparative = forbidden_comparative_env(env)
    if fallback or comparative:
        parts = []
        if fallback:
            parts.append("fallback controls: " + ", ".join(fallback))
        if comparative:
            parts.append("lane-specific comparative overrides: "
                         + ", ".join(comparative))
        raise IntegrityError(
            "formal run set forbids environment overrides; " + "; ".join(parts)
        )


def read_queue(queue_path: Path, *, valid_lanes: Iterable[str] | None = None) -> list[tuple[str, str]]:
    lanes = set(valid_lanes) if valid_lanes is not None else set(assert_lane_registry_parity())
    task_dir = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
    known_tasks = {path.stem for path in task_dir.glob("dr_cross_deep_*.json")}
    if not queue_path.is_file():
        raise IntegrityError(f"queue file does not exist: {queue_path}")
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for line_no, raw in enumerate(queue_path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) != 2 or not all(part.strip() for part in parts):
            raise IntegrityError(
                f"{queue_path}:{line_no}: expected exactly AGENT<TAB>TASK"
            )
        pair = (parts[0].strip(), parts[1].strip())
        if pair[0] not in lanes:
            raise IntegrityError(
                f"{queue_path}:{line_no}: lane {pair[0]!r} is not in the exact "
                "RUNNERS/lane_protocol set"
            )
        if pair[1] not in known_tasks:
            raise IntegrityError(f"{queue_path}:{line_no}: unknown task {pair[1]!r}")
        if pair in seen:
            raise IntegrityError(f"{queue_path}:{line_no}: duplicate queue pair {pair!r}")
        seen.add(pair)
        pairs.append(pair)
    if not pairs:
        raise IntegrityError(f"queue is empty: {queue_path}")
    return pairs


def _run_plan_document(
    *,
    run_set_id: str,
    backbone: str,
    replicates: int,
    pairs: Iterable[tuple[str, str]],
    manifest_path: Path,
) -> dict:
    _safe_id(run_set_id, "run_set_id")
    _safe_id(backbone, "backbone")
    if replicates < 1:
        raise IntegrityError("replicates must be >= 1")
    pair_list = list(pairs)
    normalized = sorted(set(pair_list))
    if not normalized:
        raise IntegrityError("run plan cannot be empty")
    if len(normalized) != len(pair_list):
        raise IntegrityError("run plan pairs contain duplicates")
    agents = sorted({agent for agent, _ in normalized})
    tasks = sorted({task for _, task in normalized})
    for agent in agents:
        _safe_id(agent, "agent")
    for task in tasks:
        _safe_id(task, "task")
    expected_cross_product = {(agent, task) for agent in agents for task in tasks}
    if set(normalized) != expected_cross_product:
        missing = sorted(expected_cross_product - set(normalized))
        raise IntegrityError(
            "formal run plan must be a complete agents x tasks cross product; "
            f"missing={missing[:8]}"
        )
    validate_manifest(
        manifest_path, run_set_id=run_set_id, backbone=backbone
    )
    return {
        "plan_version": RUN_PLAN_VERSION,
        "run_set_id": run_set_id,
        "backbone": backbone,
        "replicates": replicates,
        "agents": agents,
        "tasks": tasks,
        "pairs": [{"agent": agent, "task": task}
                  for agent, task in normalized],
        "manifest": {
            "file": manifest_path.name,
            "sha256": _sha256_file(manifest_path),
        },
    }


def create_run_plan(
    plan_path: Path,
    *,
    run_set_id: str,
    backbone: str,
    replicates: int,
    pairs: Iterable[tuple[str, str]],
    manifest_path: Path,
) -> dict:
    """Create an immutable plan with an atomic, no-clobber hard-link publish."""
    pair_list = list(pairs)
    if len(pair_list) != len(set(pair_list)):
        raise IntegrityError("run plan pairs contain duplicates")
    document = _run_plan_document(
        run_set_id=run_set_id,
        backbone=backbone,
        replicates=replicates,
        pairs=pair_list,
        manifest_path=manifest_path,
    )
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = plan_path.with_name(
        f".{plan_path.name}.tmp-{os.getpid()}-{os.urandom(6).hex()}"
    )
    payload = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    try:
        with tmp.open("x", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp, plan_path)
        except FileExistsError as exc:
            raise IntegrityError(
                f"{plan_path}: immutable run plan already exists; validate it, "
                "never overwrite it"
            ) from exc
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return document


def validate_run_plan(
    plan_path: Path,
    *,
    run_set_id: str,
    backbone: str,
    replicates: int,
    manifest_path: Path | None = None,
    queue_pairs: Iterable[tuple[str, str]] | None = None,
) -> dict:
    """Validate immutable plan identity and optionally a resume queue subset."""
    document = _load_json(plan_path)
    expected_keys = {
        "plan_version", "run_set_id", "backbone", "replicates",
        "agents", "tasks", "pairs", "manifest",
    }
    if set(document) != expected_keys:
        raise IntegrityError(
            f"{plan_path}: run plan schema keys differ: "
            f"missing={sorted(expected_keys - set(document))}, "
            f"extra={sorted(set(document) - expected_keys)}"
        )
    expected_scalars = {
        "plan_version": RUN_PLAN_VERSION,
        "run_set_id": run_set_id,
        "backbone": backbone,
        "replicates": replicates,
    }
    bad = {
        key: (document.get(key), wanted)
        for key, wanted in expected_scalars.items()
        if document.get(key) != wanted
    }
    if bad:
        raise IntegrityError(f"{plan_path}: run plan identity mismatch: {bad}")
    agents = document.get("agents")
    tasks = document.get("tasks")
    raw_pairs = document.get("pairs")
    if (not isinstance(agents, list) or not agents
            or not all(isinstance(value, str) and value for value in agents)
            or agents != sorted(set(agents))):
        raise IntegrityError(f"{plan_path}: agents must be sorted and unique")
    if (not isinstance(tasks, list) or not tasks
            or not all(isinstance(value, str) and value for value in tasks)
            or tasks != sorted(set(tasks))):
        raise IntegrityError(f"{plan_path}: tasks must be sorted and unique")
    for agent in agents:
        _safe_id(agent, "agent")
    for task in tasks:
        _safe_id(task, "task")
    if not isinstance(raw_pairs, list):
        raise IntegrityError(f"{plan_path}: pairs must be a list")
    try:
        pairs = [(item["agent"], item["task"]) for item in raw_pairs
                 if isinstance(item, dict)]
    except Exception as exc:  # noqa: BLE001
        raise IntegrityError(f"{plan_path}: malformed pairs: {exc}") from exc
    if len(pairs) != len(raw_pairs) or len(pairs) != len(set(pairs)):
        raise IntegrityError(f"{plan_path}: malformed or duplicate pairs")
    expected_pairs = {(agent, task) for agent in agents for task in tasks}
    if set(pairs) != expected_pairs or pairs != sorted(pairs):
        raise IntegrityError(
            f"{plan_path}: pairs are not the sorted agents x tasks cross product"
        )
    manifest = document.get("manifest")
    if not isinstance(manifest, dict) or set(manifest) != {"file", "sha256"}:
        raise IntegrityError(f"{plan_path}: manifest seal is missing")
    if manifest_path is None:
        manifest_path = plan_path.parent / str(manifest.get("file") or "")
    if manifest.get("file") != manifest_path.name:
        raise IntegrityError(f"{plan_path}: manifest filename mismatch")
    if not manifest_path.is_file() or manifest.get("sha256") != _sha256_file(manifest_path):
        raise IntegrityError(f"{plan_path}: manifest seal mismatch")
    validate_manifest(
        manifest_path, run_set_id=run_set_id, backbone=backbone
    )
    if queue_pairs is not None:
        queue = list(queue_pairs)
        if len(queue) != len(set(queue)):
            raise IntegrityError("resume queue contains duplicate pairs")
        outside = sorted(set(queue) - expected_pairs)
        if outside:
            raise IntegrityError(
                f"resume queue contains pairs outside immutable run plan: {outside[:8]}"
            )
    return document


def validate_manifest(
    manifest_path: Path,
    *,
    run_set_id: str,
    backbone: str,
    current_env: Mapping[str, str] | None = None,
) -> tuple[dict, str]:
    _safe_id(run_set_id, "run_set_id")
    _safe_id(backbone, "backbone")
    manifest = _load_json(manifest_path)
    if manifest.get("manifest_version") != 2:
        raise IntegrityError(
            f"{manifest_path}: manifest_version must be 2, got "
            f"{manifest.get('manifest_version')!r}"
        )
    probes = manifest.get("model_identity")
    if not isinstance(probes, list) or not probes:
        raise IntegrityError(f"{manifest_path}: no model identity probe")
    malformed = [
        p for p in probes
        if not isinstance(p, dict) or p.get("ok") is not True
        or not isinstance(p.get("endpoint"), str) or not p.get("endpoint", "").strip()
        or not isinstance(p.get("declared"), str) or not p.get("declared", "").strip()
        or not isinstance(p.get("actual"), str) or not p.get("actual", "").strip()
        or p.get("declared") != p.get("actual")
    ]
    if malformed:
        raise IntegrityError(f"{manifest_path}: failed or malformed model identity probe")
    if not any(
        p.get("declared") == backbone and p.get("actual") == backbone
        for p in probes
    ):
        raise IntegrityError(
            f"{manifest_path}: no successful exact model probe for backbone={backbone!r}"
        )
    manifest_env = manifest.get("env")
    if not isinstance(manifest_env, dict):
        raise IntegrityError(f"{manifest_path}: manifest env is missing")
    assert_formal_environment({str(k): str(v) for k, v in manifest_env.items()})
    if manifest_env.get("DRA_RUN_SET_ID") != run_set_id:
        raise IntegrityError(
            f"{manifest_path}: DRA_RUN_SET_ID={manifest_env.get('DRA_RUN_SET_ID')!r} "
            f"does not match {run_set_id!r}"
        )
    if current_env is not None:
        from scripts.run_manifest import _env_snapshot

        current_snapshot = _env_snapshot(dict(current_env))
        if manifest_env != current_snapshot:
            changed = sorted(
                key for key in set(manifest_env) | set(current_snapshot)
                if manifest_env.get(key) != current_snapshot.get(key)
            )
            raise IntegrityError(
                f"{manifest_path}: run-affecting environment differs from the "
                f"bound manifest: {changed}"
            )
    digest = _sha256_file(manifest_path)
    return manifest, digest


def _report_class(text: str) -> str:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.eval.report_stubs import classify_report

    return classify_report(text)


def _structured_pollution(value: object, path: str = "meta") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            lowered = str(key).lower()
            if "fallback" in lowered:
                benign = child in (None, False, 0, "", "disabled", "native", "none")
                if not benign:
                    findings.append(f"{child_path}={child!r}")
            if "stub" in lowered and child not in (None, False, 0, "", "ok"):
                findings.append(f"{child_path}={child!r}")
            findings.extend(_structured_pollution(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_structured_pollution(child, f"{path}[{index}]"))
    return findings


def _validate_provenance(
    report_path: Path,
    *,
    agent: str,
    task: str,
    backbone: str,
) -> None:
    path = report_path.with_suffix(".provenance.json")
    if not path.exists():
        if agent == "claude-code":
            raise IntegrityError(f"{report_path}: claude-code routing provenance is missing")
        return
    provenance = _load_json(path)
    expected = {"agent": agent, "task": task, "backbone": backbone}
    mismatches = {
        key: (provenance.get(key), wanted)
        for key, wanted in expected.items()
        if provenance.get(key) != wanted
    }
    if mismatches:
        raise IntegrityError(f"{path}: routing provenance mismatch: {mismatches}")
    if agent == "claude-code":
        route = provenance.get("config_router_default")
        if not isinstance(route, str) or not route.endswith(f",{backbone}"):
            raise IntegrityError(
                f"{path}: claude-code router is unverified or routes another backbone"
            )


def validate_entry(
    report_path: Path,
    meta_path: Path,
    manifest_path: Path,
    *,
    run_set_id: str,
    backbone: str,
    replicate: int,
    agent: str | None = None,
    task: str | None = None,
    require_binding: bool,
) -> tuple[dict, str, str]:
    if replicate < 1:
        raise IntegrityError("replicate must be >= 1")
    _, manifest_sha = validate_manifest(
        manifest_path, run_set_id=run_set_id, backbone=backbone
    )
    if not report_path.is_file() or not meta_path.is_file():
        raise IntegrityError(f"missing report/meta pair: {report_path}, {meta_path}")
    meta = _load_json(meta_path)
    expected_agent = agent or meta.get("agent")
    expected_task = task or meta.get("task")
    if not isinstance(expected_agent, str) or not expected_agent:
        raise IntegrityError(f"{meta_path}: agent is missing")
    if not isinstance(expected_task, str) or not expected_task:
        raise IntegrityError(f"{meta_path}: task is missing")
    expected = {
        "agent": expected_agent,
        "task": expected_task,
        "backbone": backbone,
        "status": "pass",
    }
    mismatches = {
        key: (meta.get(key), wanted)
        for key, wanted in expected.items()
        if meta.get(key) != wanted
    }
    if mismatches:
        raise IntegrityError(f"{meta_path}: run metadata mismatch: {mismatches}")
    run_id = meta.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise IntegrityError(f"{meta_path}: formal pass metadata has no run_id")

    report_bytes = report_path.read_bytes()
    report_sha = hashlib.sha256(report_bytes).hexdigest()
    seal = meta.get("report_seal")
    if not isinstance(seal, dict) or seal.get("sha256") != report_sha:
        raise IntegrityError(f"{report_path}: report bytes do not match meta report_seal")
    if seal.get("n_bytes") != len(report_bytes):
        raise IntegrityError(f"{report_path}: report byte count does not match meta report_seal")
    try:
        report_text = report_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntegrityError(f"{report_path}: report is not UTF-8") from exc
    report_class = _report_class(report_text)
    if report_class != "ok":
        raise IntegrityError(f"{report_path}: report is not scoreable ({report_class})")
    lowered_report = report_text.lower()
    signatures = [s for s in _FALLBACK_REPORT_SIGNATURES if s in lowered_report]
    if signatures:
        raise IntegrityError(f"{report_path}: evidence fallback signature detected")

    pollution = _structured_pollution(meta)
    error_text = str(meta.get("error") or "").lower()
    if any(s in error_text for s in ("evidence fallback", "source-grounded writer", "force fallback")):
        pollution.append("meta.error contains fallback marker")
    if pollution:
        raise IntegrityError(f"{meta_path}: fallback/stub metadata pollution: {pollution[:6]}")

    identity = meta.get("model_identity")
    if not isinstance(identity, dict) or identity.get("ok") is not True:
        raise IntegrityError(f"{meta_path}: per-run model identity probe did not pass")
    if identity.get("declared") != backbone or identity.get("actual") != backbone:
        raise IntegrityError(
            f"{meta_path}: per-run route is mislabeled: "
            f"declared={identity.get('declared')!r}, actual={identity.get('actual')!r}, "
            f"expected={backbone!r}"
        )
    _validate_provenance(
        report_path,
        agent=expected_agent,
        task=expected_task,
        backbone=backbone,
    )

    if require_binding:
        top_level_expected = {"run_set_id": run_set_id, "replicate": replicate}
        bad_top_level = {
            key: (meta.get(key), wanted)
            for key, wanted in top_level_expected.items()
            if meta.get(key) != wanted
        }
        if bad_top_level:
            raise IntegrityError(
                f"{meta_path}: top-level run-set identity mismatch: {bad_top_level}"
            )
        binding_expected = {
            "integrity_version": INTEGRITY_VERSION,
            "run_set_id": run_set_id,
            "backbone": backbone,
            "replicate": replicate,
            "agent": expected_agent,
            "task": expected_task,
            "run_id": run_id,
            "meta_file": meta_path.name,
            "report_file": report_path.name,
            "manifest_sha256": manifest_sha,
            "run_plan_sha256": _run_plan_sha_for_manifest(manifest_path),
            "report_sha256": report_sha,
        }
        binding = meta.get("run_set_binding")
        if not isinstance(binding, dict):
            raise IntegrityError(f"{meta_path}: formal run_set_binding is missing")
        bad_binding = {
            key: (binding.get(key), wanted)
            for key, wanted in binding_expected.items()
            if binding.get(key) != wanted
        }
        if bad_binding:
            raise IntegrityError(f"{meta_path}: run_set_binding mismatch: {bad_binding}")
        if binding.get("manifest_file") != manifest_path.name:
            raise IntegrityError(f"{meta_path}: bound manifest filename does not match")
    return meta, report_sha, manifest_sha


def bind_entry(
    report_path: Path,
    meta_path: Path,
    manifest_path: Path,
    *,
    run_set_id: str,
    backbone: str,
    replicate: int,
    agent: str,
    task: str,
) -> dict:
    meta, report_sha, manifest_sha = validate_entry(
        report_path,
        meta_path,
        manifest_path,
        run_set_id=run_set_id,
        backbone=backbone,
        replicate=replicate,
        agent=agent,
        task=task,
        require_binding=False,
    )
    meta["run_set_id"] = run_set_id
    meta["replicate"] = replicate
    meta["run_set_binding"] = {
        "integrity_version": INTEGRITY_VERSION,
        "run_set_id": run_set_id,
        "backbone": backbone,
        "replicate": replicate,
        "agent": agent,
        "task": task,
        "run_id": meta["run_id"],
        "meta_file": meta_path.name,
        "report_file": report_path.name,
        "manifest_file": manifest_path.name,
        "manifest_sha256": manifest_sha,
        "run_plan_sha256": _run_plan_sha_for_manifest(manifest_path),
        "report_sha256": report_sha,
    }
    tmp = meta_path.with_name(f".{meta_path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(meta_path)
    return meta["run_set_binding"]


def validate_outcome(
    meta_path: Path,
    manifest_path: Path,
    *,
    run_set_id: str,
    backbone: str,
    replicate: int,
    agent: str,
    task: str,
    require_binding: bool,
) -> tuple[dict, str]:
    """Validate a report-less terminal outcome from a formal run.

    ``run_deep_task`` deliberately leaves the report absent for watchdog and
    infrastructure exits.  Those cells still need a cryptographic run-set and
    replicate foreign key; otherwise a board can only guess ``replicate`` from
    the filename and silently drop every failed cell.  The shell driver calls
    :func:`bind_outcome` with the values from its already-validated queue.
    """
    if replicate < 1:
        raise IntegrityError("replicate must be >= 1")
    _, manifest_sha = validate_manifest(
        manifest_path, run_set_id=run_set_id, backbone=backbone
    )
    if not meta_path.is_file():
        raise IntegrityError(f"missing outcome metadata: {meta_path}")
    meta = _load_json(meta_path)
    expected = {"agent": agent, "task": task, "backbone": backbone}
    mismatches = {
        key: (meta.get(key), wanted)
        for key, wanted in expected.items()
        if meta.get(key) != wanted
    }
    if mismatches:
        raise IntegrityError(f"{meta_path}: outcome metadata mismatch: {mismatches}")
    status = meta.get("status")
    if status not in RUN_STATUSES - {"pass"}:
        raise IntegrityError(
            f"{meta_path}: report-less outcome status must be one of "
            f"{sorted(RUN_STATUSES - {'pass'})}, got {status!r}"
        )
    binding = meta.get("outcome_binding") if require_binding else None
    bound_report_file = binding.get("report_file") if isinstance(binding, dict) else None
    if bound_report_file is not None:
        if (not isinstance(bound_report_file, str)
                or Path(bound_report_file).name != bound_report_file):
            raise IntegrityError(f"{meta_path}: unsafe bound outcome report filename")
        report_path = meta_path.parent / bound_report_file
    else:
        stem = meta_path.name[: -len(".meta.json")]
        report_path = meta_path.with_name(stem + ".md")
    report_sha: str | None = None
    if report_path.exists():
        report_bytes = report_path.read_bytes()
        report_sha = hashlib.sha256(report_bytes).hexdigest()
        seal = meta.get("report_seal")
        if not isinstance(seal, dict) or seal.get("sha256") != report_sha:
            raise IntegrityError(
                f"{report_path}: non-pass report bytes do not match meta report_seal"
            )
        if seal.get("n_bytes") != len(report_bytes):
            raise IntegrityError(
                f"{report_path}: non-pass report byte count does not match seal"
            )
    if require_binding:
        top_level_expected = {"run_set_id": run_set_id, "replicate": replicate}
        bad_top_level = {
            key: (meta.get(key), wanted)
            for key, wanted in top_level_expected.items()
            if meta.get(key) != wanted
        }
        if bad_top_level:
            raise IntegrityError(
                f"{meta_path}: top-level run-set identity mismatch: {bad_top_level}"
            )
        wanted_binding = {
            "integrity_version": INTEGRITY_VERSION,
            "run_set_id": run_set_id,
            "backbone": backbone,
            "replicate": replicate,
            "agent": agent,
            "task": task,
            "meta_file": meta_path.name,
            "report_file": report_path.name if report_path.exists() else None,
            "status": status,
            "manifest_sha256": manifest_sha,
            "run_plan_sha256": _run_plan_sha_for_manifest(manifest_path),
            "report_sha256": report_sha,
        }
        binding = meta.get("outcome_binding")
        if not isinstance(binding, dict):
            raise IntegrityError(f"{meta_path}: formal outcome_binding is missing")
        bad = {
            key: (binding.get(key), wanted)
            for key, wanted in wanted_binding.items()
            if binding.get(key) != wanted
        }
        if bad:
            raise IntegrityError(f"{meta_path}: outcome_binding mismatch: {bad}")
        if binding.get("manifest_file") != manifest_path.name:
            raise IntegrityError(f"{meta_path}: bound manifest filename does not match")
    return meta, manifest_sha


def bind_outcome(
    meta_path: Path,
    manifest_path: Path,
    *,
    run_set_id: str,
    backbone: str,
    replicate: int,
    agent: str,
    task: str,
    status: str | None = None,
    error: str | None = None,
) -> dict:
    """Bind a non-pass outcome, creating minimal metadata when the process died.

    An outer ``timeout`` can kill Python before its watchdog writes a sidecar.
    Supplying ``status`` lets the owning shell record that terminal cell without
    pretending a report or model probe exists.  If metadata does exist, its
    identity and status are never overwritten.
    """
    if meta_path.exists():
        meta = _load_json(meta_path)
        if status is not None and meta.get("status") != status:
            raise IntegrityError(
                f"{meta_path}: existing status={meta.get('status')!r} does not "
                f"match requested {status!r}"
            )
    else:
        if status not in RUN_STATUSES - {"pass"}:
            raise IntegrityError(
                "creating an outcome sidecar requires an explicit non-pass status"
            )
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "agent": agent,
            "task": task,
            "backbone": backbone,
            "status": status,
            "error": error,
            "attempts": 1,
        }
        meta_path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    meta, manifest_sha = validate_outcome(
        meta_path,
        manifest_path,
        run_set_id=run_set_id,
        backbone=backbone,
        replicate=replicate,
        agent=agent,
        task=task,
        require_binding=False,
    )
    meta["run_set_id"] = run_set_id
    meta["replicate"] = replicate
    meta["outcome_binding"] = {
        "integrity_version": INTEGRITY_VERSION,
        "run_set_id": run_set_id,
        "backbone": backbone,
        "replicate": replicate,
        "agent": agent,
        "task": task,
        "meta_file": meta_path.name,
        "report_file": (
            meta_path.name[: -len(".meta.json")] + ".md"
            if meta_path.with_name(
                meta_path.name[: -len(".meta.json")] + ".md"
            ).exists()
            else None
        ),
        "status": meta["status"],
        "manifest_file": manifest_path.name,
        "manifest_sha256": manifest_sha,
        "run_plan_sha256": _run_plan_sha_for_manifest(manifest_path),
        "report_sha256": (
            hashlib.sha256(
                meta_path.with_name(
                    meta_path.name[: -len(".meta.json")] + ".md"
                ).read_bytes()
            ).hexdigest()
            if meta_path.with_name(
                meta_path.name[: -len(".meta.json")] + ".md"
            ).exists()
            else None
        ),
    }
    tmp = meta_path.with_name(f".{meta_path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(meta_path)
    return meta["outcome_binding"]


def entry_resume_violations(
    score_path: Path,
    meta_path: Path,
    report_path: Path,
    manifest_path: Path,
    *,
    run_set_id: str,
    backbone: str,
    replicate: int,
    agent: str | None = None,
    task: str | None = None,
) -> list[str]:
    try:
        meta, report_sha, _ = validate_entry(
            report_path,
            meta_path,
            manifest_path,
            run_set_id=run_set_id,
            backbone=backbone,
            replicate=replicate,
            agent=agent,
            task=task,
            require_binding=True,
        )
        if not score_path.is_file():
            raise IntegrityError(f"missing score: {score_path}")
        score = _load_json(score_path)
        seal_check = score.get("report_seal_check")
        if not isinstance(seal_check, dict):
            raise IntegrityError(f"{score_path}: scorer did not record report_seal_check")
        if seal_check.get("checked") is not True or seal_check.get("ok") is not True:
            raise IntegrityError(f"{score_path}: scorer did not verify the report seal")
        if seal_check.get("actual_sha256") != report_sha:
            raise IntegrityError(f"{score_path}: score belongs to different report bytes")
        answer_path = Path(str(score.get("answer_path") or ""))
        if not answer_path.is_absolute():
            answer_path = ROOT / answer_path
        if answer_path.resolve() != report_path.resolve():
            raise IntegrityError(
                f"{score_path}: answer_path={answer_path} does not name {report_path}"
            )
        if score.get("task") != (task or meta.get("task")):
            raise IntegrityError(f"{score_path}: score task does not match run metadata")
    except IntegrityError as exc:
        return [str(exc)]
    return []


def is_entry_resumable(*args, **kwargs) -> bool:
    return not entry_resume_violations(*args, **kwargs)


def _entry_paths_from_meta(
    meta_path: Path, binding: Mapping[str, object] | None = None
) -> tuple[Path, Path]:
    report_file = binding.get("report_file") if binding else None
    if isinstance(report_file, str) and Path(report_file).name == report_file:
        stem = Path(report_file).stem
        return (
            meta_path.parent / report_file,
            meta_path.parent.parent / "scores" / (stem + ".score.json"),
        )
    stem = meta_path.name[: -len(".meta.json")]
    return meta_path.with_name(stem + ".md"), meta_path.parent.parent / "scores" / (stem + ".score.json")


def audit_run_set(run_set_dir: Path, *, verify_live_manifests: bool = True) -> dict:
    run_set_dir = run_set_dir.resolve()
    run_set_id = run_set_dir.name
    _safe_id(run_set_id, "run_set_id")
    violations: list[str] = []
    entries: list[dict] = []
    outcomes: list[dict] = []
    report_groups: dict[str, list[dict]] = defaultdict(list)

    backbone_dirs = sorted(
        path for path in run_set_dir.iterdir()
        if path.is_dir() and (path / "raw").is_dir()
    ) if run_set_dir.is_dir() else []
    if not backbone_dirs:
        violations.append(f"{run_set_dir}: no backbone/raw directories")

    for run_dir in backbone_dirs:
        backbone = run_dir.name
        manifests = {path.name: path for path in run_dir.glob("run_manifest*.json")}
        if not manifests:
            violations.append(f"{run_dir}: no run_manifest*.json")
        elif verify_live_manifests:
            from scripts.run_manifest import verify as verify_manifest_live

            for manifest_path in manifests.values():
                try:
                    live_violations = verify_manifest_live(
                        _load_json(manifest_path), run_dir, root=ROOT
                    )
                except Exception as exc:  # noqa: BLE001
                    live_violations = [
                        f"live manifest verification crashed: "
                        f"{type(exc).__name__}: {exc}"
                    ]
                violations.extend(
                    f"{manifest_path}: {reason}" for reason in live_violations
                )
        raw_dir = run_dir / "raw"
        score_dir = run_dir / "scores"
        meta_paths = sorted(raw_dir.glob("*.meta.json"))
        report_paths = set(raw_dir.glob("*.md"))
        score_paths = set(score_dir.glob("*.score.json")) if score_dir.is_dir() else set()
        paired_reports: set[Path] = set()
        paired_scores: set[Path] = set()
        for meta_path in meta_paths:
            try:
                raw_meta = _load_json(meta_path)
                status = raw_meta.get("status")
                if status not in RUN_STATUSES:
                    raise IntegrityError(
                        f"{meta_path}: unknown run status {status!r}"
                    )
                binding_key = ("run_set_binding" if status == "pass"
                               else "outcome_binding")
                binding = raw_meta.get(binding_key) or {}
                manifest_name = binding.get("manifest_file")
                manifest_path = manifests.get(str(manifest_name))
                if manifest_path is None:
                    raise IntegrityError(
                        f"{meta_path}: bound manifest {manifest_name!r} is absent"
                    )
                replicate = binding.get("replicate")
                if not isinstance(replicate, int):
                    raise IntegrityError(f"{meta_path}: replicate binding is missing")
                report_path, score_path = _entry_paths_from_meta(meta_path, binding)
                if status == "pass":
                    paired_reports.add(report_path)
                    paired_scores.add(score_path)
                    entry_violations = entry_resume_violations(
                        score_path,
                        meta_path,
                        report_path,
                        manifest_path,
                        run_set_id=run_set_id,
                        backbone=backbone,
                        replicate=replicate,
                    )
                    if entry_violations:
                        raise IntegrityError("; ".join(entry_violations))
                    record = {
                        "agent": raw_meta["agent"],
                        "task": raw_meta["task"],
                        "backbone": backbone,
                        "replicate": replicate,
                        "status": status,
                        "report": str(report_path),
                        "report_sha256": binding["report_sha256"],
                    }
                    entries.append(record)
                    report_groups[record["report_sha256"]].append(record)
                else:
                    validate_outcome(
                        meta_path,
                        manifest_path,
                        run_set_id=run_set_id,
                        backbone=backbone,
                        replicate=replicate,
                        agent=raw_meta.get("agent"),
                        task=raw_meta.get("task"),
                        require_binding=True,
                    )
                    if report_path.exists():
                        paired_reports.add(report_path)
                    outcomes.append({
                        "agent": raw_meta["agent"],
                        "task": raw_meta["task"],
                        "backbone": backbone,
                        "replicate": replicate,
                        "status": status,
                    })
            except IntegrityError as exc:
                violations.append(str(exc))
        for orphan in sorted(report_paths - paired_reports):
            violations.append(f"{orphan}: legacy/orphan report has no bound meta")
        for orphan in sorted(score_paths - paired_scores):
            violations.append(f"{orphan}: legacy/orphan score has no bound report/meta")

    replicate_disclosures: list[dict] = []
    duplicate_contamination: list[dict] = []
    for digest, group in sorted(report_groups.items()):
        if len(group) < 2:
            continue
        triplets = {(r["agent"], r["task"], r["backbone"]) for r in group}
        replicates = {r["replicate"] for r in group}
        benign_replicates = len(triplets) == 1 and len(replicates) == len(group)
        disclosure = {"sha256": digest, "count": len(group), "entries": group}
        if benign_replicates:
            replicate_disclosures.append(disclosure)
        else:
            duplicate_contamination.append(disclosure)
            identities = sorted({(r["agent"], r["backbone"]) for r in group})
            violations.append(
                "duplicate report contamination: "
                f"sha256={digest}, identities={identities}, count={len(group)}"
            )

    if not entries and not outcomes:
        violations.append(f"{run_set_dir}: no fully bound entries or outcomes")

    return {
        "integrity_version": INTEGRITY_VERSION,
        "run_set_id": run_set_id,
        "ok": not violations,
        "n_entries": len(entries),
        "n_outcomes": len(outcomes),
        "outcome_status_counts": {
            status: sum(1 for item in outcomes if item["status"] == status)
            for status in sorted(RUN_STATUSES - {"pass"})
        },
        "max_cross_identity_duplicate_groups": 0,
        "observed_duplicate_contamination_groups": len(duplicate_contamination),
        "violations": violations,
        "duplicate_contamination": duplicate_contamination,
        "same_lane_replicate_disclosures": replicate_disclosures,
    }


def _print_error(exc: IntegrityError) -> int:
    print(f"RUN-SET INTEGRITY REFUSAL: {exc}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)

    p_parity = sub.add_parser("lane-parity")
    p_parity.add_argument("--queue", type=Path)

    sub.add_parser("formal-env")

    p_manifest = sub.add_parser("manifest")
    p_manifest.add_argument("--manifest", type=Path, required=True)
    p_manifest.add_argument("--run-set-id", required=True)
    p_manifest.add_argument("--backbone", required=True)
    p_manifest.add_argument("--compare-current-env", action="store_true")

    p_plan = sub.add_parser("run-plan")
    p_plan.add_argument("--plan", type=Path, required=True)
    p_plan.add_argument(
        "--manifest",
        type=Path,
        help="required on create; optional on verify (defaults to plan's sealed file)",
    )
    p_plan.add_argument("--run-set-id", required=True)
    p_plan.add_argument("--backbone", required=True)
    p_plan.add_argument("--replicates", type=int, required=True)
    p_plan.add_argument("--queue", type=Path, required=True)
    p_plan.add_argument(
        "--create",
        action="store_true",
        help="atomically create; without this flag, validate immutable plan",
    )

    p_bind = sub.add_parser("bind-entry")
    p_bind.add_argument("--report", type=Path, required=True)
    p_bind.add_argument("--meta", type=Path, required=True)
    p_bind.add_argument("--manifest", type=Path, required=True)
    p_bind.add_argument("--run-set-id", required=True)
    p_bind.add_argument("--backbone", required=True)
    p_bind.add_argument("--replicate", type=int, required=True)
    p_bind.add_argument("--agent", required=True)
    p_bind.add_argument("--task", required=True)

    p_outcome = sub.add_parser("bind-outcome")
    p_outcome.add_argument("--meta", type=Path, required=True)
    p_outcome.add_argument("--manifest", type=Path, required=True)
    p_outcome.add_argument("--run-set-id", required=True)
    p_outcome.add_argument("--backbone", required=True)
    p_outcome.add_argument("--replicate", type=int, required=True)
    p_outcome.add_argument("--agent", required=True)
    p_outcome.add_argument("--task", required=True)
    p_outcome.add_argument("--status", choices=sorted(RUN_STATUSES - {"pass"}))
    p_outcome.add_argument("--error")

    p_entry = sub.add_parser("verify-entry")
    p_entry.add_argument("--score", type=Path, required=True)
    p_entry.add_argument("--report", type=Path, required=True)
    p_entry.add_argument("--meta", type=Path, required=True)
    p_entry.add_argument("--manifest", type=Path, required=True)
    p_entry.add_argument("--run-set-id", required=True)
    p_entry.add_argument("--backbone", required=True)
    p_entry.add_argument("--replicate", type=int, required=True)
    p_entry.add_argument("--agent")
    p_entry.add_argument("--task")

    p_audit = sub.add_parser("audit")
    p_audit.add_argument("--run-set-dir", type=Path, required=True)
    p_audit.add_argument("--out", type=Path)

    args = ap.parse_args(argv)
    try:
        if args.command == "lane-parity":
            lanes = assert_lane_registry_parity()
            pairs = read_queue(args.queue, valid_lanes=lanes) if args.queue else []
            print(f"lane parity OK: {len(lanes)} lanes; queue pairs={len(pairs)}")
        elif args.command == "formal-env":
            assert_formal_environment()
            print("formal environment OK: no fallback or lane-specific overrides")
        elif args.command == "manifest":
            _, digest = validate_manifest(
                args.manifest,
                run_set_id=args.run_set_id,
                backbone=args.backbone,
                current_env=os.environ if args.compare_current_env else None,
            )
            print(f"manifest binding OK: sha256={digest}")
        elif args.command == "run-plan":
            pairs = read_queue(args.queue)
            if args.create:
                if args.manifest is None:
                    raise IntegrityError("run-plan --create requires --manifest")
                document = create_run_plan(
                    args.plan,
                    run_set_id=args.run_set_id,
                    backbone=args.backbone,
                    replicates=args.replicates,
                    pairs=pairs,
                    manifest_path=args.manifest,
                )
                print(
                    f"run plan created: agents={len(document['agents'])} "
                    f"tasks={len(document['tasks'])} replicates={document['replicates']}"
                )
            else:
                document = validate_run_plan(
                    args.plan,
                    run_set_id=args.run_set_id,
                    backbone=args.backbone,
                    replicates=args.replicates,
                    manifest_path=args.manifest,
                    queue_pairs=pairs,
                )
                print(
                    f"run plan verified: agents={len(document['agents'])} "
                    f"tasks={len(document['tasks'])} replicates={document['replicates']}"
                )
        elif args.command == "bind-entry":
            binding = bind_entry(
                args.report,
                args.meta,
                args.manifest,
                run_set_id=args.run_set_id,
                backbone=args.backbone,
                replicate=args.replicate,
                agent=args.agent,
                task=args.task,
            )
            print(json.dumps(binding, sort_keys=True))
        elif args.command == "bind-outcome":
            binding = bind_outcome(
                args.meta,
                args.manifest,
                run_set_id=args.run_set_id,
                backbone=args.backbone,
                replicate=args.replicate,
                agent=args.agent,
                task=args.task,
                status=args.status,
                error=args.error,
            )
            print(json.dumps(binding, sort_keys=True))
        elif args.command == "verify-entry":
            violations = entry_resume_violations(
                args.score,
                args.meta,
                args.report,
                args.manifest,
                run_set_id=args.run_set_id,
                backbone=args.backbone,
                replicate=args.replicate,
                agent=args.agent,
                task=args.task,
            )
            if violations:
                raise IntegrityError("; ".join(violations))
            print("entry binding OK")
        elif args.command == "audit":
            result = audit_run_set(args.run_set_dir)
            rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                tmp = args.out.with_name(f".{args.out.name}.tmp-{os.getpid()}")
                tmp.write_text(rendered, encoding="utf-8")
                tmp.replace(args.out)
            print(rendered, end="")
            return 0 if result["ok"] else 1
    except (IntegrityError, FileNotFoundError) as exc:
        return _print_error(IntegrityError(str(exc)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
