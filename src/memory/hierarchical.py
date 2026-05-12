"""Hierarchical memory for FlowSearcher: L1 (per-task), L2 (per-intent), L3 (global).

Standalone module — does not import anything from src.models / src.evaluators
to avoid pydantic dependency when used on machines without it.
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MEMORY_DIR = ROOT / "data" / "memory"
L1_DIR = MEMORY_DIR / "L1_task"
L2_DIR = MEMORY_DIR / "L2_intent"
L3_PATH = MEMORY_DIR / "L3_global.json"

INTENT_TYPES = [
    "recommendation", "comparison", "debunking",
    "causal", "timeline", "enumeration",
]


def classify_intent(intent_text: str) -> str:
    first_line = intent_text.strip().split("\n")[0].lower()
    for kw, itype in [
        ("comparison", "comparison"),
        ("debunking", "debunking"),
        ("fact-check", "debunking"),
        ("fact check", "debunking"),
        ("causal", "causal"),
        ("timeline", "timeline"),
        ("evolution", "timeline"),
        ("enumeration", "enumeration"),
        ("catalog", "enumeration"),
        ("recommendation", "recommendation"),
        ("market-intelligence", "recommendation"),
    ]:
        if kw in first_line:
            return itype
    return "recommendation"


def _embed_via_dashscope(texts: list[str]) -> list[list[float]]:
    import httpx
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return []
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "text-embedding-v4", "input": texts},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return [d["embedding"] for d in sorted(data, key=lambda x: x["index"])]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return dot / (na * nb)


class HierarchicalMemory:
    def __init__(self):
        self.l1: dict[str, dict] = {}
        self.l2: dict[str, dict] = {}
        self.l3: dict = {}

    @classmethod
    def load(cls) -> "HierarchicalMemory":
        mem = cls()
        for f in L1_DIR.glob("*.json"):
            mem.l1[f.stem] = json.loads(f.read_text())
        for f in L2_DIR.glob("*.json"):
            mem.l2[f.stem] = json.loads(f.read_text())
        if L3_PATH.exists():
            mem.l3 = json.loads(L3_PATH.read_text())
        return mem

    def save(self) -> None:
        L1_DIR.mkdir(parents=True, exist_ok=True)
        L2_DIR.mkdir(parents=True, exist_ok=True)
        for tid, data in self.l1.items():
            (L1_DIR / f"{tid}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
        for itype, data in self.l2.items():
            (L2_DIR / f"{itype}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
        L3_PATH.write_text(json.dumps(self.l3, indent=2, ensure_ascii=False))

    def retrieve(self, intent_text: str, task_id: str | None = None, top_k: int = 3) -> dict[str, Any]:
        itype = classify_intent(intent_text)
        l2_entry = self.l2.get(itype, {})
        l3_entry = self.l3

        # L1 retrieval: prefer same intent_type, rank by composite_v2
        candidates = []
        for tid, entry in self.l1.items():
            if tid == task_id:
                continue
            score = 0.0
            if entry.get("intent_type") == itype:
                score += 0.5
            best = entry.get("best_runs", [])
            if best:
                score += best[0].get("composite_v2", 0)
            candidates.append((tid, entry, score))

        # If embeddings exist, use cosine similarity
        try:
            query_emb = _embed_via_dashscope([intent_text[:500]])
            if query_emb:
                qvec = query_emb[0]
                for i, (tid, entry, base_score) in enumerate(candidates):
                    evec = entry.get("embedding")
                    if evec:
                        sim = _cosine_sim(qvec, evec)
                        candidates[i] = (tid, entry, base_score + sim * 0.3)
        except Exception:
            pass

        candidates.sort(key=lambda x: x[2], reverse=True)
        top = candidates[:top_k]

        return {
            "l1_neighbors": [
                {"task_id": tid, "best_runs": entry.get("best_runs", [])[:2],
                 "section_skeleton": entry.get("section_skeleton"),
                 "cited_url_patterns": entry.get("cited_url_patterns")}
                for tid, entry, _ in top
            ],
            "l2_intent_shape": l2_entry,
            "l3_globals": l3_entry,
        }

    def write_back(self, task_id: str, agent: str, score_data: dict, report_text: str) -> None:
        composite = score_data.get("composite", {}).get("composite_score", 0)
        reach = score_data.get("url_reachability", {}).get("score", 0)
        if composite < 0.04 or reach < 0.20:
            return

        coverage = score_data.get("url_coverage", {}).get("details", {})
        run_entry = {
            "agent": agent,
            "composite_v2": composite,
            "reachability": reach,
            "citation_count": coverage.get("cited_unique", 0),
            "must_cite_recall": coverage.get("must_cite_recall", 0),
            "per_domain_cited": coverage.get("per_domain_cited", {}),
        }

        sections = _extract_sections(report_text)

        if task_id not in self.l1:
            task_dir = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
            task_file = task_dir / f"{task_id}.json"
            intent = ""
            if task_file.exists():
                intent = json.loads(task_file.read_text()).get("intent", "")
            self.l1[task_id] = {
                "task_id": task_id,
                "intent_type": classify_intent(intent),
                "best_runs": [],
                "section_skeleton": sections,
            }

        entry = self.l1[task_id]
        entry["best_runs"].append(run_entry)
        entry["best_runs"].sort(key=lambda r: r["composite_v2"], reverse=True)
        entry["best_runs"] = entry["best_runs"][:5]
        if sections:
            entry["section_skeleton"] = sections

        self.save()


def _extract_sections(md_text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^#{1,3}\s+(.+)$", md_text, re.MULTILINE)][:20]
