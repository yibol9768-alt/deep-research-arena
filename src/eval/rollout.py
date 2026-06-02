"""Rollout artifacts consumed by the Phase 2 grounded RL reward path."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.verifiers.citation_format import canonicalize_url


_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Rollout:
    task_id: str
    report_md: str
    retrieved_snippets: dict[str, str] = field(default_factory=dict)
    fetched_urls: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    step_count: int = 0
    sessions: list[dict] = field(default_factory=list)
    trace: dict | None = None

    @property
    def pages_browsed(self) -> int:
        return len(self.fetched_urls)

    @classmethod
    def from_run_dir(
        cls,
        results_dir: Path,
        agent: str,
        task: str,
        suffix: str = "",
    ) -> "Rollout":
        sfx = f"_{suffix}" if suffix else ""
        stem = f"{agent}__{task}{sfx}"
        report = (results_dir / f"{stem}.md").read_text(encoding="utf-8")
        meta = json.loads((results_dir / f"{stem}.meta.json").read_text(encoding="utf-8"))
        snippets, fetched, calls = _load_retrieval_trace(results_dir, stem)
        return cls(
            task_id=str(meta.get("task") or task),
            report_md=report,
            retrieved_snippets=snippets,
            fetched_urls=fetched,
            tool_calls=calls,
            step_count=len(calls),
        )


def _candidate_trace_paths(results_dir: Path, stem: str) -> list[Path]:
    name = f"{stem}.jsonl"
    return [
        results_dir / "logs" / "retrieval" / name,
        results_dir.parent / "logs" / "retrieval" / name,
        _REPO_ROOT / "logs" / "retrieval" / name,
        Path.cwd() / "logs" / "retrieval" / name,
    ]


def _row_results(row: dict[str, Any]) -> list[dict[str, Any]]:
    results = row.get("results")
    if isinstance(results, list):
        return [r for r in results if isinstance(r, dict)]
    return []


def _load_retrieval_trace(
    results_dir: Path,
    stem: str,
) -> tuple[dict[str, str], list[str], list[dict]]:
    """Load the shim retrieval trace for a run.

    Missing traces are expected for historical runs and for tests that
    construct rollouts directly. In that case the grounded reward degrades
    through the evaluator's documented proxy path.
    """
    path = next((p for p in _candidate_trace_paths(results_dir, stem) if p.exists()), None)
    if path is None:
        return {}, [], []

    snippets: dict[str, str] = {}
    fetched: list[str] = []
    calls: list[dict] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue

        results = _row_results(row)
        for item in results:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            fetched.append(url)
            raw_content = item.get("raw_content")
            if raw_content is None:
                raw_content = item.get("content")
            text = str(raw_content or "")
            if text:
                snippets[canonicalize_url(url)] = text

        calls.append({
            "endpoint": row.get("endpoint"),
            "query": row.get("query"),
            "n_results": len(results),
            "ok": bool(row.get("ok", True)),
            "ts": row.get("ts"),
        })

    return snippets, fetched, calls


__all__ = ["Rollout", "_load_retrieval_trace"]
