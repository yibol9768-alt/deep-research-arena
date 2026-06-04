#!/usr/bin/env python3
"""Content-hash the Deep Research eval inputs into a reproducible manifest.

Eval problem #4 ("make the benchmark reproducible + documented") asks for a
single, stable fingerprint of everything that determines a leaderboard number:
the task set, the golden references, the judge prompts, the judge model, and the
scoring formula. Anyone can re-run this script and diff the resulting
`data/results/benchmark_manifest.json` against a published one to confirm they
are scoring against byte-identical inputs.

Design choices (all deterministic, no network):
  * Every hash is sha256 over the SORTED list of (relative_path, raw_bytes)
    for the in-scope files. Sorting by path makes the digest independent of
    filesystem walk order. Hashing raw bytes (not re-serialized JSON) means the
    manifest detects any change, including whitespace, that a re-pretty-print
    would hide.
  * Only the CANONICAL eval inputs are hashed. The task and golden directories
    also contain editor/macOS cruft and derivation artifacts
    (`._*`, `*.bak`, `*.cleaned.json`, `*.quotes*.json`, `*.uncleaned.*`) that
    are NOT consumed by the scorer; including them would make the digest depend
    on incidental local files. The canonical task/golden corpus is the set of
    `dr_cross_deep_NNNN.json` files plus the shared `checklists_deep.json`
    coverage file that tasks reference via `coverage_checklist_path`.
  * The judge-prompt hash is taken over the LIVE `_SYSTEM` and
    `_DIMENSION_FOCUS` objects imported from `src.scoring.pairwise_judge`, so it
    can never drift from the prompts actually used at judging time.

Run:
    python3 scripts/benchmark_manifest.py
Writes:
    data/results/benchmark_manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make `src...` importable when run from anywhere.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# --- Paths (all relative to the repo root) ---------------------------------
TASK_DIR = REPO_ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
GOLDEN_DIR = REPO_ROOT / "data" / "golden" / "deep"
GOLDEN_CLEAN_DIR = REPO_ROOT / "data" / "golden" / "deep_clean"
OUT_PATH = REPO_ROOT / "data" / "results" / "benchmark_manifest.json"

# Canonical eval-input filename: dr_cross_deep_0001.json ... dr_cross_deep_0100.json
_CANON_RE = re.compile(r"^dr_cross_deep_\d{4}\.json$")
# Extra task-side input that is a real eval input (referenced by tasks via
# `coverage_checklist_path`), not a per-task file.
_TASK_EXTRA = {"checklists_deep.json"}


def _canon_json_files(directory: Path) -> list[Path]:
    """Return the canonical dr_cross_deep_NNNN.json files in `directory`, sorted
    by name. Skips backups / variants / macOS resource forks so the digest only
    depends on files the scorer actually consumes.
    """
    if not directory.is_dir():
        return []
    return sorted(
        (p for p in directory.iterdir() if p.is_file() and _CANON_RE.match(p.name)),
        key=lambda p: p.name,
    )


def _hash_files(files: list[Path]) -> tuple[str, int]:
    """sha256 over the sorted list of (relative_path, raw_bytes).

    Returns (hex_digest, n_files). The digest binds each file's repo-relative
    path AND its exact bytes, so a rename or a content edit both change it.
    """
    items: list[tuple[str, bytes]] = []
    for p in files:
        rel = p.relative_to(REPO_ROOT).as_posix()
        items.append((rel, p.read_bytes()))
    items.sort(key=lambda kv: kv[0])

    h = hashlib.sha256()
    for rel, raw in items:
        # Length-prefix both fields so concatenation is unambiguous (no two
        # different (path, bytes) splits can collide into the same stream).
        rel_b = rel.encode("utf-8")
        h.update(len(rel_b).to_bytes(8, "big"))
        h.update(rel_b)
        h.update(len(raw).to_bytes(8, "big"))
        h.update(raw)
    return h.hexdigest(), len(items)


def _judge_prompt_hash() -> tuple[str, dict]:
    """sha256 over the live pairwise-judge prompts.

    Imports `_SYSTEM` and `_DIMENSION_FOCUS` from src.scoring.pairwise_judge so
    the hash always reflects the prompts actually shipped. Serialized as a
    canonical JSON object with sorted keys for stability across runs.
    """
    from src.scoring.pairwise_judge import _DIMENSION_FOCUS, _SYSTEM

    payload = {
        "system": _SYSTEM,
        "dimension_focus": {k: _DIMENSION_FOCUS[k] for k in sorted(_DIMENSION_FOCUS)},
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    detail = {
        "system_chars": len(_SYSTEM),
        "dimensions": sorted(_DIMENSION_FOCUS),
    }
    return digest, detail


def _resolve_judge_model() -> str:
    """The pairwise judge model that scoring would use, resolved the same way
    pairwise_judge._default_judge_model() resolves it: PAIRWISE_JUDGE_MODEL,
    then JUDGE_MODEL, then CHECKLIST_JUDGE_MODEL, then the project default.

    The published Deep Research leaderboard uses the cross-family GLM-5.1 judge
    on Bailian/DashScope; when no judge env is exported the project default is
    deepseek-v4-flash. We record whatever is resolved here AND the canonical
    intended judge so the manifest is honest about both.
    """
    return (
        os.environ.get("PAIRWISE_JUDGE_MODEL")
        or os.environ.get("JUDGE_MODEL")
        or os.environ.get("CHECKLIST_JUDGE_MODEL")
        or "deepseek-v4-flash"
    )


# The grounding gate formula, stated as a single auditable string. This mirrors
# src/scoring/simple_score.py (grounding_score + gate_and_rank) exactly.
GROUNDING_FORMULA = (
    "grounding = F1(citation_precision, must_cite_recall); "
    "citation_precision = supported_cited_pairs / total_cited_pairs "
    "(a cited URL must pass proof-of-fetch [actually retrieved] AND its claim "
    "must be supported by the retrieved snippet); "
    "must_cite_recall = curated_golden_must_cite_hits / total_curated_must_cite "
    "(no domain-balance or raw-count term); "
    "TRUTH GATE: final_quality = 0 if fabricated (a cited URL was never fetched) "
    "OR grounding_f1 < floor (default 0.15), else QUALITY passes through "
    "unchanged. QUALITY and GROUNDING are reported as two separate numbers; "
    "QUALITY = length-controlled pairwise Bradley-Terry Elo from a cross-family "
    "judge with position-swap debiasing and majority over n_samples rounds."
)

GENERATED_NOTE = (
    "Reproducibility manifest for the Deep Research cross-site benchmark. "
    "Each *_hash is sha256 over the sorted list of (repo-relative-path, raw-bytes) "
    "for the in-scope files (task set, golden references) or over the canonical "
    "JSON of the live judge prompts. Only canonical dr_cross_deep_NNNN.json files "
    "plus checklists_deep.json are hashed; backups/variants (*.bak, *.cleaned.json, "
    "*.quotes*.json, ._*) are excluded because the scorer does not consume them. "
    "Regenerate with: python3 scripts/benchmark_manifest.py. Diff this file "
    "against a published manifest to confirm byte-identical eval inputs."
)


def build_manifest() -> dict:
    # --- task set: canonical per-task files + the shared checklists file -----
    task_files = _canon_json_files(TASK_DIR)
    for extra in sorted(_TASK_EXTRA):
        p = TASK_DIR / extra
        if p.is_file():
            task_files.append(p)
    task_set_hash, n_tasks_files = _hash_files(task_files)
    # n_tasks counts the per-task specs only (exclude the shared checklists file).
    n_tasks = sum(1 for p in task_files if _CANON_RE.match(p.name))

    # --- golden: deep + deep_clean (deep_clean only if present) --------------
    golden_files = _canon_json_files(GOLDEN_DIR)
    golden_clean_files = _canon_json_files(GOLDEN_CLEAN_DIR)
    all_golden = golden_files + golden_clean_files
    golden_hash, _ = _hash_files(all_golden)
    n_golden = len(golden_files)
    n_golden_clean = len(golden_clean_files)

    # --- judge prompts -------------------------------------------------------
    judge_prompt_hash, judge_prompt_detail = _judge_prompt_hash()

    resolved_judge = _resolve_judge_model()

    manifest = {
        "generated_note": GENERATED_NOTE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_set_hash": task_set_hash,
        "golden_hash": golden_hash,
        "judge_prompt_hash": judge_prompt_hash,
        "judge_model": resolved_judge,
        "grounding_formula": GROUNDING_FORMULA,
        "n_tasks": n_tasks,
        "n_golden": n_golden,
        # --- extra provenance (does not change the headline contract) --------
        "details": {
            "task_dir": TASK_DIR.relative_to(REPO_ROOT).as_posix(),
            "golden_dir": GOLDEN_DIR.relative_to(REPO_ROOT).as_posix(),
            "golden_clean_dir": GOLDEN_CLEAN_DIR.relative_to(REPO_ROOT).as_posix(),
            "n_task_input_files_hashed": n_tasks_files,
            "n_golden_clean": n_golden_clean,
            "judge_prompt": judge_prompt_detail,
            "canonical_judge_model": "glm-5.1",
            "canonical_judge_provider": "openai (Bailian/DashScope OpenAI-compatible)",
            "judge_model_note": (
                "judge_model is resolved from PAIRWISE_JUDGE_MODEL / JUDGE_MODEL / "
                "CHECKLIST_JUDGE_MODEL at run time, falling back to the project "
                "default deepseek-v4-flash when no judge env is exported. The "
                "published leaderboard uses the cross-family glm-5.1 judge; export "
                "PAIRWISE_JUDGE_MODEL=glm-5.1 (and the DashScope JUDGE_* env) before "
                "regenerating to stamp glm-5.1 here."
            ),
            "hash_algorithm": "sha256 over sorted (repo-relative-path, raw-bytes), "
            "length-prefixed",
            "canonical_filename_pattern": _CANON_RE.pattern,
            "excluded_patterns": ["._*", "*.bak", "*.cleaned.json",
                                  "*.quotes*.json", "*.uncleaned.*"],
        },
    }
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        default=str(OUT_PATH),
        help="output path for the manifest JSON (default: data/results/benchmark_manifest.json)",
    )
    ap.add_argument(
        "--print",
        dest="do_print",
        action="store_true",
        help="also print the manifest to stdout",
    )
    args = ap.parse_args()

    manifest = build_manifest()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Concise, key-free summary to stderr-style stdout (no secrets are involved).
    print(f"wrote {out}")
    print(f"  task_set_hash     {manifest['task_set_hash']}")
    print(f"  golden_hash       {manifest['golden_hash']}")
    print(f"  judge_prompt_hash {manifest['judge_prompt_hash']}")
    print(f"  judge_model       {manifest['judge_model']}")
    print(f"  n_tasks           {manifest['n_tasks']}")
    print(f"  n_golden          {manifest['n_golden']}")
    if args.do_print:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
