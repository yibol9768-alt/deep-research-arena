#!/usr/bin/env python3
"""Stamp the ``acquisition`` capability field onto a Deep Research task JSON.

The ``acquisition`` block declares which evidence-acquisition channel a task
wants (see ``docs/ACQUISITION_MODALITIES.md``). This helper adds that block to a
task file **in place** and is intended to be run by whatever process authors the
RL task set; it is deliberately standalone and is NOT run against any task data
on import.

Behaviour:
    * Idempotent. Stamping a file whose ``acquisition`` already names the same
      modality is a no-op (exit 0, "unchanged"). Without ``--force`` an existing
      block is left untouched (the existing block wins); ``--force`` overwrites.
    * Two layouts are supported transparently:
        - a single-task file:  ``{ "task_id": ..., "sites": ..., ... }``
        - a collection file:    ``{ "<task_id>": { ...task... }, ... }``
      For a collection, every task entry is stamped.
    * The modality is validated against the same allowed set the runtime factory
      (``src.rl.backends.make_backend``) accepts, so a typo fails here rather
      than silently at reward time. Validation uses a local copy of the allowed
      values so this script imports with no project dependencies; it falls back
      to that local set if ``src.rl.backends`` is not importable.

No network, no GPU, no heavy deps. Pure stdlib.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

# Allowed modality strings, mirroring src.rl.backends._MODALITY_ALIASES keys.
# Kept as a local fallback so this script runs with zero project imports; we
# still prefer the live set when importable so the two never drift.
_FALLBACK_ALLOWED = {
    "shim",
    "search_shim",
    "search-shim",
    "http",
    "browser",
    "computeruse",
    "computer_use",
    "computer-use",
    "mock",
}

DEFAULT_MODALITY = "shim"


def _allowed_modalities() -> set[str]:
    try:
        from src.rl.backends import _MODALITY_ALIASES  # type: ignore

        return set(_MODALITY_ALIASES.keys())
    except Exception:
        return set(_FALLBACK_ALLOWED)


def _validate_modality(modality: str) -> str:
    m = str(modality).strip().lower()
    allowed = _allowed_modalities()
    if m not in allowed:
        raise ValueError(
            f"unknown acquisition modality: {modality!r} "
            f"(allowed: {sorted(allowed)})"
        )
    return m


def build_acquisition_block(
    modality: str,
    *,
    shim_url: str | None = None,
    max_results: int | None = None,
) -> dict[str, Any]:
    """Construct the ``acquisition`` block for ``modality``.

    ``modalities`` (the ordered-preference list) and the convenience scalar
    ``backend`` are both set to ``modality`` so the block is unambiguous and the
    factory resolves it the same way regardless of which it reads first.
    """
    block: dict[str, Any] = {"modalities": [modality], "backend": modality}
    if shim_url is not None:
        block["shim_url"] = shim_url
    if max_results is not None:
        block["max_results"] = int(max_results)
    return block


def _looks_like_task(obj: Any) -> bool:
    """A task entry is a dict carrying any of the canonical task keys."""
    if not isinstance(obj, dict):
        return False
    markers = ("task_id", "id", "intent", "sites", "markdown_spec", "prompt")
    return any(k in obj for k in markers)


def _stamp_one(
    task: dict[str, Any],
    block: dict[str, Any],
    *,
    force: bool,
) -> bool:
    """Stamp one task dict in place. Return True if it was modified."""
    existing = task.get("acquisition")
    if isinstance(existing, dict) and existing:
        if existing == block:
            return False  # already exactly what we want -> idempotent no-op
        if not force:
            return False  # respect an author-set block unless --force
    task["acquisition"] = copy.deepcopy(block)
    return True


def stamp_file(
    path: Path,
    *,
    modality: str = DEFAULT_MODALITY,
    shim_url: str | None = None,
    max_results: int | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Stamp ``path`` (single-task or collection). Return (n_tasks, n_changed)."""
    modality = _validate_modality(modality)
    block = build_acquisition_block(
        modality, shim_url=shim_url, max_results=max_results
    )

    data = json.loads(path.read_text(encoding="utf-8"))

    n_tasks = 0
    n_changed = 0
    if _looks_like_task(data):
        # Single-task file.
        n_tasks = 1
        if _stamp_one(data, block, force=force):
            n_changed = 1
    elif isinstance(data, dict):
        # Collection file: {task_id -> task_config}.
        for key, entry in data.items():
            if _looks_like_task(entry):
                n_tasks += 1
                if _stamp_one(entry, block, force=force):
                    n_changed += 1
    else:
        raise ValueError(
            f"{path}: top-level JSON is neither a task object nor a "
            f"{{task_id -> task}} collection"
        )

    if n_changed and not dry_run:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return n_tasks, n_changed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Stamp the acquisition modality field onto a task JSON in place.",
    )
    p.add_argument("task_file", type=Path, help="Path to a task JSON (single or collection).")
    p.add_argument(
        "--modality",
        default=DEFAULT_MODALITY,
        help=f"Acquisition modality (default: {DEFAULT_MODALITY}).",
    )
    p.add_argument("--shim-url", default=None, help="Optional shim base URL to record.")
    p.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Optional search-breadth passthrough to record.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing acquisition block (default: leave it).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.task_file.exists():
        print(f"error: no such file: {args.task_file}", file=sys.stderr)
        return 2
    try:
        n_tasks, n_changed = stamp_file(
            args.task_file,
            modality=args.modality,
            shim_url=args.shim_url,
            max_results=args.max_results,
            force=args.force,
            dry_run=args.dry_run,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    verb = "would stamp" if args.dry_run else "stamped"
    status = "unchanged" if n_changed == 0 else f"{verb} {n_changed}/{n_tasks}"
    print(f"{args.task_file}: {status} (modality={_validate_modality(args.modality)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
