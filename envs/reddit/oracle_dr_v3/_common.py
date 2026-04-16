"""Shared helpers for v3 reddit oracles."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_DIR = REPO_ROOT / "data" / "golden"


def write_golden(task_id: str, triples: list[dict]) -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    (GOLDEN_DIR / f"{task_id}.json").write_text(json.dumps(triples, indent=2, ensure_ascii=False))


def md_link(text: str, url: str) -> str:
    safe = re.sub(r"[\[\]]", "", text or "")[:120]
    return f"[{safe}]({url})"
