#!/usr/bin/env python3
"""Freeze or verify the replay identity of the DRA task-v2 legacy baseline.

This script never scores or rewrites a v2 report.  It records the exact task,
answer-key, registry, scorer, and formula bytes that remain available for
historical replay while v3 is developed in separate modules.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SCORING_ENTRYPOINTS = (
    "scripts/score_deep_answer.py",
    "scripts/build_truth_board.py",
    "src/eval/decidable_scorer.py",
    "src/eval/fetch_log.py",
    "src/eval/closed_world_eval.py",
)
SCORING_NON_PYTHON_FILES = (
    "config/lane_protocol.yaml",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_map(paths: list[Path], root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): _sha(p) for p in sorted(paths)}


def _map_hash(values: dict[str, str]) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _module_files(root: Path, parts: tuple[str, ...]) -> list[Path]:
    if not parts:
        return []
    stem = root.joinpath(*parts)
    candidates = [stem.with_suffix(".py"), stem / "__init__.py"]
    return [path for path in candidates if path.is_file()]


def _package_init_files(root: Path, path: Path) -> list[Path]:
    relative = path.relative_to(root)
    parents = relative.parts[:-1]
    return [
        root.joinpath(*parents[:index], "__init__.py")
        for index in range(1, len(parents) + 1)
        if root.joinpath(*parents[:index], "__init__.py").is_file()
    ]


def _imported_local_files(root: Path, path: Path) -> set[Path]:
    """Resolve static local imports, including imports nested in functions."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ValueError(f"cannot parse v2 scoring dependency {path}: {exc}") from exc
    relative = path.relative_to(root).with_suffix("")
    current_parts = list(relative.parts)
    package_parts = (
        current_parts[:-1]
        if current_parts[-1] != "__init__"
        else current_parts[:-1]
    )
    discovered: set[Path] = set()
    for node in ast.walk(tree):
        module_names: list[tuple[str, ...]] = []
        if isinstance(node, ast.Import):
            module_names.extend(tuple(alias.name.split(".")) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                trim = node.level - 1
                if trim > len(package_parts):
                    continue
                prefix = package_parts[: len(package_parts) - trim]
            else:
                prefix = []
            base = tuple(prefix + ((node.module or "").split(".") if node.module else []))
            if base:
                module_names.append(base)
            for alias in node.names:
                if alias.name != "*":
                    module_names.append((*base, *alias.name.split(".")))
        for parts in module_names:
            for candidate in _module_files(root, parts):
                discovered.add(candidate)
                discovered.update(_package_init_files(root, candidate))
    return discovered


def scoring_dependency_files(root: Path) -> list[Path]:
    """Return the transitive local Python closure of the frozen v2 scorers."""

    queue = [root / name for name in SCORING_ENTRYPOINTS]
    missing = [str(path.relative_to(root)) for path in queue if not path.is_file()]
    if missing:
        raise ValueError(f"missing v2 scoring entrypoints: {missing}")
    seen: set[Path] = set()
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        for dependency in _imported_local_files(root, path):
            if dependency not in seen:
                queue.append(dependency)
    for name in SCORING_NON_PYTHON_FILES:
        path = root / name
        if not path.is_file():
            raise ValueError(f"missing v2 scoring file: {name}")
        seen.add(path)
    return sorted(seen)


def _git(root: Path) -> dict:
    def run(*args):
        proc = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False
        )
        return proc.stdout.strip() if proc.returncode == 0 else None

    status = run("status", "--short")
    return {
        "commit": run("rev-parse", "HEAD"),
        "tree": run("rev-parse", "HEAD^{tree}"),
        "dirty": bool(status),
        "status_sha256": hashlib.sha256((status or "").encode()).hexdigest(),
    }


def build_manifest(root: Path = ROOT) -> dict:
    from scripts.build_truth_board import (  # imported from the frozen v2 path
        EXTRACTOR_COMMIT,
        FORMULA_COMMIT,
        FORMULA_VERSION,
    )

    tasks = sorted(
        (root / "data/tasks/deep_research/cross_site_deep").glob(
            "dr_cross_deep_[0-9][0-9][0-9][0-9].json"
        )
    )
    keys = sorted(
        (root / "data/golden/answer_keys").glob(
            "dr_cross_deep_[0-9][0-9][0-9][0-9].json"
        )
    )
    checklists = sorted(
        (root / "data/golden/checklists").glob(
            "dr_cross_deep_[0-9][0-9][0-9][0-9].json"
        )
    )
    if not tasks or not keys or not checklists:
        raise ValueError("v2 task, answer-key, or checklist set is empty")
    task_names = {path.name for path in tasks}
    if {path.name for path in keys} != task_names or {
        path.name for path in checklists
    } != task_names:
        raise ValueError("v2 task, answer-key, and checklist identities disagree")
    task_docs = [json.loads(p.read_text(encoding="utf-8")) for p in tasks]
    bad_versions = [d.get("task_id") for d in task_docs if d.get("task_version") != 2]
    if bad_versions:
        raise ValueError(f"non-v2 task in legacy set: {bad_versions}")
    task_hashes = _file_map(tasks, root)
    key_hashes = _file_map(keys, root)
    checklist_hashes = _file_map(checklists, root)
    scoring_paths = scoring_dependency_files(root)
    scoring_hashes = _file_map(scoring_paths, root)
    registry = root / "data/golden/url_registry.json"
    return {
        "schema": "dra-v2-legacy-baseline-v1",
        "status": "legacy_replay_only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocols": {
            "task_version": 2,
            "pof_semantics": "transport_v2",
            "gate_semantics": "provenance_v2",
            "formula_version": FORMULA_VERSION,
            "extractor_commit": EXTRACTOR_COMMIT,
            "formula_commit": FORMULA_COMMIT,
            "headline_semantics": "provenance_times_weighted_quality_v2_legacy",
            "comparable_to_verified_slots_v1": False,
        },
        "counts": {
            "tasks": len(tasks),
            "answer_keys": len(keys),
            "checklists": len(checklists),
        },
        "hashes": {
            "task_set": _map_hash(task_hashes),
            "answer_key_set": _map_hash(key_hashes),
            "checklist_set": _map_hash(checklist_hashes),
            "scoring_code": _map_hash(scoring_hashes),
            "url_registry": _sha(registry) if registry.is_file() else None,
        },
        "files": {
            "tasks": task_hashes,
            "answer_keys": key_hashes,
            "checklists": checklist_hashes,
            "scoring": scoring_hashes,
        },
        "git": _git(root),
        "migration_rule": (
            "Do not recompute or overwrite historical v2 boards with v3 slots. "
            "Diagnostics parsed from v2 reports are not formal v3 scores."
        ),
    }


def verify_manifest(doc: dict, root: Path = ROOT) -> list[str]:
    """Return byte-identity violations; timestamps and git dirtiness are ignored."""

    now = build_manifest(root)
    violations = []
    for key in ("schema", "status"):
        if doc.get(key) != now.get(key):
            violations.append(f"{key}: {doc.get(key)!r} != {now.get(key)!r}")
    if doc.get("protocols") != now.get("protocols"):
        violations.append("protocol stamp changed")
    if doc.get("counts") != now.get("counts"):
        violations.append("task/answer-key/checklist counts changed")
    if doc.get("hashes") != now.get("hashes"):
        violations.append("task/answer-key/checklist/scorer bytes changed")
    if doc.get("files") != now.get("files"):
        violations.append("per-file identity changed")
    return violations


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, help="write a new frozen manifest")
    ap.add_argument("--verify", type=Path, help="verify an existing manifest")
    args = ap.parse_args(argv)
    if bool(args.out) == bool(args.verify):
        ap.error("choose exactly one of --out or --verify")
    if args.verify:
        doc = json.loads(args.verify.read_text(encoding="utf-8"))
        violations = verify_manifest(doc)
        if violations:
            for violation in violations:
                print(f"FAIL: {violation}", file=sys.stderr)
            return 1
        print("OK: v2 legacy baseline bytes match")
        return 0
    doc = build_manifest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
