"""Mine existing deep-tier matrix results to cold-start hierarchical memory."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .hierarchical import HierarchicalMemory, classify_intent, _extract_sections

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "data" / "results" / "deep"
TASK_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"

COMPOSITE_THRESHOLD = 0.04
REACHABILITY_THRESHOLD = 0.20


def _parse_filename(fname: str) -> tuple[str, str] | None:
    m = re.match(r"^(.+?)__(.+?)(?:_matrix|_smoke)\.score\.json$", fname)
    if m:
        return m.group(1), m.group(2)
    return None


def _load_task_intents() -> dict[str, str]:
    intents = {}
    for f in TASK_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            intents[d["task_id"]] = d.get("intent", "")
        except Exception:
            pass
    return intents


def _extract_url_patterns(md_text: str) -> dict[str, list[str]]:
    patterns: dict[str, list[str]] = {"shopping": [], "reddit": [], "wiki": []}
    urls = re.findall(r"\]\((http://localhost:\d+/[^)]+)\)", md_text)
    seen: set[str] = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        if ":7770" in u:
            patterns["shopping"].append(u)
        elif ":9999" in u:
            patterns["reddit"].append(u)
        elif ":8090" in u:
            patterns["wiki"].append(u)
    return patterns


def mine_all() -> HierarchicalMemory:
    mem = HierarchicalMemory()
    intents = _load_task_intents()
    intent_groups: dict[str, list[dict]] = defaultdict(list)

    score_files = sorted(RESULTS_DIR.glob("*_matrix.score.json"))
    print(f"[miner] scanning {len(score_files)} score files")

    for sf in score_files:
        parsed = _parse_filename(sf.name)
        if not parsed:
            continue
        agent, task_id = parsed

        try:
            score = json.loads(sf.read_text())
        except Exception:
            continue

        composite = score.get("composite", {}).get("composite_score", 0)
        reach = score.get("url_reachability", {}).get("score", 0)
        if composite < COMPOSITE_THRESHOLD or reach < REACHABILITY_THRESHOLD:
            continue

        coverage = score.get("url_coverage", {}).get("details", {})
        run_entry = {
            "agent": agent,
            "composite_v2": composite,
            "reachability": reach,
            "citation_count": coverage.get("cited_unique", 0),
            "must_cite_recall": coverage.get("must_cite_recall", 0),
            "per_domain_cited": coverage.get("per_domain_cited", {}),
            "checklist_pass_rate": score.get("checklist", {}).get("pass_rate", 0),
        }

        md_path = sf.with_name(sf.name.replace(".score.json", ".md"))
        sections: list[str] = []
        url_pats: dict[str, list[str]] = {}
        if md_path.exists():
            md_text = md_path.read_text()
            sections = _extract_sections(md_text)
            url_pats = _extract_url_patterns(md_text)

        intent_text = intents.get(task_id, "")
        itype = classify_intent(intent_text)

        if task_id not in mem.l1:
            mem.l1[task_id] = {
                "task_id": task_id,
                "intent_type": itype,
                "best_runs": [],
                "section_skeleton": sections,
                "cited_url_patterns": url_pats,
            }

        entry = mem.l1[task_id]
        entry["best_runs"].append(run_entry)
        if sections and not entry.get("section_skeleton"):
            entry["section_skeleton"] = sections
        if url_pats:
            entry["cited_url_patterns"] = url_pats

        intent_groups[itype].append({
            "task_id": task_id,
            "composite_v2": composite,
            "citation_count": run_entry["citation_count"],
            "per_domain_cited": run_entry["per_domain_cited"],
            "sections": sections,
        })

    # Sort best_runs per L1 entry
    for entry in mem.l1.values():
        entry["best_runs"].sort(key=lambda r: r["composite_v2"], reverse=True)
        entry["best_runs"] = entry["best_runs"][:5]

    # Build L2 from intent groups
    for itype, runs in intent_groups.items():
        n_tasks = len(set(r["task_id"] for r in runs))
        avg_cite = sum(r["citation_count"] for r in runs) / max(len(runs), 1)

        domain_totals: dict[str, int] = defaultdict(int)
        for r in runs:
            for d, c in r.get("per_domain_cited", {}).items():
                domain_totals[d] += c
        total_all = sum(domain_totals.values()) or 1
        cite_dist = {d: round(c / total_all, 3) for d, c in domain_totals.items()}

        all_sections: list[list[str]] = [r["sections"] for r in runs if r["sections"]]
        section_count_avg = sum(len(s) for s in all_sections) / max(len(all_sections), 1)

        mem.l2[itype] = {
            "intent_type": itype,
            "n_tasks": n_tasks,
            "n_runs": len(runs),
            "avg_citation_count": round(avg_cite, 1),
            "section_count_avg": round(section_count_avg, 1),
            "citation_distribution": cite_dist,
            "exemplar_tasks": list(set(r["task_id"] for r in sorted(runs, key=lambda x: x["composite_v2"], reverse=True)))[:5],
        }

    # Build L3 global
    all_composites = []
    for entry in mem.l1.values():
        for r in entry["best_runs"]:
            all_composites.append(r["composite_v2"])

    mem.l3 = {
        "sandbox_url_patterns": {
            "shopping": "http://localhost:7770/<slug>.html",
            "reddit": "http://localhost:9999/f/<forum>/<id>",
            "wiki": "http://localhost:8090/content/wikipedia_en_all_nopic/A/<title>",
        },
        "citation_count_typical_range": [
            int(min(all_composites) * 100) if all_composites else 60,
            int(max(all_composites) * 100) if all_composites else 120,
        ],
        "domain_balance_target": {"shopping": 0.40, "reddit": 0.30, "wiki": 0.30},
        "n_total_l1_entries": len(mem.l1),
        "n_total_qualified_runs": sum(len(e["best_runs"]) for e in mem.l1.values()),
    }

    return mem
