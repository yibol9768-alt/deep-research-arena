"""Versioned evolving-rubric storage for per-task checklist snapshots."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_RUBRIC_DIR = _REPO_ROOT / "data" / "rubrics"
_POLARITIES = {"positive", "negative"}
_TIERS = {"persist", "active", "negative"}


@dataclass(slots=True)
class RubricItem:
    id: str
    criterion: str
    weight: float
    is_deterministic: bool = False
    polarity: str = "positive"
    tier: str = "active"
    origin: str = "generated"
    version: int = 0

    def __post_init__(self) -> None:
        self.id = str(self.id).strip()
        self.criterion = str(self.criterion).strip()
        self.weight = float(self.weight)
        self.polarity = str(self.polarity).strip()
        self.tier = str(self.tier).strip()
        self.origin = str(self.origin).strip()
        self.version = int(self.version)
        self.is_deterministic = bool(self.is_deterministic)

        if not self.id:
            raise ValueError("rubric item id must be non-empty")
        if not self.criterion:
            raise ValueError("rubric criterion must be non-empty")
        if not math.isfinite(self.weight):
            raise ValueError("rubric item weight must be finite")
        if self.polarity not in _POLARITIES:
            raise ValueError(f"rubric polarity must be one of {sorted(_POLARITIES)}")
        if self.tier not in _TIERS:
            raise ValueError(f"rubric tier must be one of {sorted(_TIERS)}")
        if not self.origin:
            raise ValueError("rubric origin must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RubricItem":
        return cls(
            id=str(data["id"]),
            criterion=str(data["criterion"]),
            weight=float(data.get("weight", 1.0)),
            is_deterministic=bool(data.get("is_deterministic", False)),
            polarity=str(data.get("polarity", "positive")),
            tier=str(data.get("tier", "active")),
            origin=str(data.get("origin", "generated")),
            version=int(data.get("version", 0)),
        )


def _rubric_path(task_id: str, base_dir: Path | str | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else _DEFAULT_RUBRIC_DIR
    return root / f"{task_id}.json"


def _copy_item(
    item: RubricItem,
    *,
    tier: str | None = None,
    polarity: str | None = None,
    version: int | None = None,
) -> RubricItem:
    data = item.to_dict()
    if tier is not None:
        data["tier"] = tier
    if polarity is not None:
        data["polarity"] = polarity
    if version is not None:
        data["version"] = version
    return RubricItem.from_dict(data)


class RubricStore:
    """Holds fixed, evolving, and veto rubric sets for one task.

    ``snapshot()`` intentionally merges ``persist + active`` into top-level
    ``items`` because ``ChecklistVerifier.verify(rubric_snapshot=...)`` scores
    only that positive list. Veto rubrics are kept out of ``items`` and exposed
    under ``negative_items`` for the later reward nullification path.
    """

    def __init__(self, task_id: str) -> None:
        self.task_id = str(task_id).strip()
        if not self.task_id:
            raise ValueError("task_id must be non-empty")
        self.persist: list[RubricItem] = []
        self.active: list[RubricItem] = []
        self.negative: list[RubricItem] = []
        self.version = 0

    def set_persist(self, items: list[RubricItem]) -> None:
        self.persist = [
            _copy_item(item, tier="persist", polarity=item.polarity)
            for item in items
        ]

    def replace_active(self, items: list[RubricItem]) -> None:
        self.version += 1
        self.active = [
            _copy_item(item, tier="active", polarity="positive", version=self.version)
            for item in items
        ]

    def add_negative(self, items: list[RubricItem]) -> None:
        if not items:
            return
        self.version += 1
        self.negative.extend(
            _copy_item(item, tier="negative", polarity="negative", version=self.version)
            for item in items
        )

    def snapshot(self) -> dict[str, Any]:
        positive_items = [
            item.to_dict()
            for item in [*self.persist, *self.active]
            if item.polarity == "positive"
        ]
        return {
            "version": self.version,
            "items": positive_items,
            "negative_items": [item.to_dict() for item in self.negative],
        }

    def to_json(self, *, base_dir: Path | str | None = None) -> Path:
        path = _rubric_path(self.task_id, base_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "task_id": self.task_id,
            "version": self.version,
            "persist": [item.to_dict() for item in self.persist],
            "active": [item.to_dict() for item in self.active],
            "negative": [item.to_dict() for item in self.negative],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    @classmethod
    def from_json(
        cls,
        task_id: str,
        *,
        base_dir: Path | str | None = None,
    ) -> "RubricStore":
        path = _rubric_path(task_id, base_dir)
        payload = json.loads(path.read_text(encoding="utf-8"))
        store = cls(str(payload.get("task_id") or task_id))
        store.version = int(payload.get("version", 0))
        store.persist = [
            RubricItem.from_dict(item)
            for item in payload.get("persist", [])
        ]
        store.active = [
            RubricItem.from_dict(item)
            for item in payload.get("active", [])
        ]
        store.negative = [
            RubricItem.from_dict(item)
            for item in payload.get("negative", [])
        ]
        return store
