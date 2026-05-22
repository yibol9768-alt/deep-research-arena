#!/usr/bin/env python3
"""Build fully-fleshed v2 adversarial task JSON files from the specs in
`configs/deep_topics/V2_ADVERSARIAL_TASKS.json`.

Reads:
    configs/deep_topics/V2_ADVERSARIAL_TASKS.json
        (20 specs, each {task_id, family, topic, intent_seed,
         must_cite_pool, expected_dim_stress, adversarial_rationale})

Writes:
    data/tasks/deep_research/cross_site_deep_v2/<task_id>.json
        — each task uses the same JSON schema as the v1 cross_site_deep
          tasks. Adds a `v2_meta` block carrying family / stress / rationale
          so downstream scoring can filter v2 runs by family.

Also writes a `checklists_deep_v2.json` index alongside the tasks: a
15-21 item rubric per task, customised to the family.

NOTE — real validation requires running the small pilot (3 agents x 5
tasks per family) on the westd / WSL benchmark host before promoting any
v2 task into the leaderboard pool. This script only emits the *task
artefacts*; the pre-screen protocol lives in
`configs/deep_topics/V1_TASK_DESIGN_GRID.md` section 5.4.

Usage:
    python scripts/build_v2_adversarial_tasks.py
        [--specs configs/deep_topics/V2_ADVERSARIAL_TASKS.json]
        [--out data/tasks/deep_research/cross_site_deep_v2]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPECS = ROOT / "configs" / "deep_topics" / "V2_ADVERSARIAL_TASKS.json"
DEFAULT_OUT = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep_v2"


# -----------------------------------------------------------------------------
# Per-family intent suffixes — adds the rigour bar that V1 tasks lacked.
# -----------------------------------------------------------------------------

FAMILY_INTENT_SUFFIX: dict[str, str] = {
    "causal": (
        "\n\nThe report MUST surface explicit COUNTER-EVIDENCE against the "
        "audited claim and the verdict must cite the contradicting wiki "
        "article(s) by URL. A verdict of SUPPORTED is allowed only when "
        "the agent has actively searched for counter-evidence and "
        "documented the absence — a 'no contrary evidence found' clause is "
        "required. Verdict columns without an explicit contradicting "
        "citation will be marked DEBUNKED-BY-OMISSION in the rubric."
    ),
    "contradiction": (
        "\n\nTwo source clusters DISAGREE on the central question. The "
        "report MUST identify BOTH clusters (≥ 3 citations each), name the "
        "specific disagreement, and reconcile it. A one-sided summary "
        "(only citing the cluster that agrees with the prevailing "
        "marketing or community narrative) FAILS the depth checklist "
        "regardless of word count. The reconciliation section must either "
        "(a) pick one side with explicit reasoning citing both, or "
        "(b) acknowledge irreducible tension and characterise which kind "
        "of user / question each side serves."
    ),
    "long_tail": (
        "\n\nThe golden must-cite URL pool is DELIBERATELY oversampled "
        "with niche / long-tail items: ≥ 60% of the must-cite URLs are "
        "reachable only via 2+ hops or via non-obvious search terms. "
        "Surface-only searching (cite top-3 results of the obvious query) "
        "will yield a must-cite recall under 0.40 and fail the "
        "url_coverage threshold. The report's enumeration / catalog "
        "MUST include ≥ 8 niche items beyond the popular top-3 / top-5."
    ),
}


# -----------------------------------------------------------------------------
# Per-family base checklist — task-specific items appended dynamically.
# -----------------------------------------------------------------------------

CAUSAL_BASE_CHECKLIST: list[str] = [
    "Is the audited claim stated verbatim near the start of the report?",
    "Does the report surface at least 3 distinct COUNTER-EVIDENCE citations against the claim?",
    "Is the final verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}?",
    "Does the verdict explicitly cite a contradicting wiki URL by markdown link?",
    "If the verdict is SUPPORTED, does the report contain a 'no contrary evidence found' clause documenting the search for counter-evidence?",
    "Are >= 36 shopping product pages cited carrying the audited claim or its competitors?",
    "Are >= 30 reddit threads from >= 4 sub-forums cited?",
    "Are >= 25 wiki articles cited?",
    "Are all mandatory wiki articles for this topic present in the cited set?",
    "Are >= 60 distinct URLs cited in total?",
    "Is per-domain minimum met: >= 30 shopping, >= 20 reddit, >= 15 wiki?",
    "Is the report 3500-8000 words?",
    "Are all cited URLs markdown-linked and sandbox-resolvable?",
    "Does the report avoid a TOP-10 product ranking format?",
    "Does the report avoid chain-of-thought and start with the verdict?",
]

CONTRADICTION_BASE_CHECKLIST: list[str] = [
    "Are the two source clusters explicitly named (e.g. 'manufacturer-side' vs 'community-side', 'observational vs RCT', 'registry vs independent')?",
    "Does each cluster receive >= 3 distinct citations?",
    "Is the specific point of disagreement stated as a single sentence?",
    "Does the report cite at least 2 wiki articles that ground the underlying mechanism of the disagreement?",
    "Is a RECONCILIATION section present (pick a side with reasoning OR acknowledge irreducible tension with characterisation)?",
    "Does the reconciliation section cite BOTH clusters by URL?",
    "Are >= 30 reddit threads from >= 4 sub-forums cited?",
    "Are >= 25 wiki articles cited?",
    "Are >= 30 shopping product pages cited where applicable?",
    "Are >= 60 distinct URLs cited in total?",
    "Is per-domain minimum met: >= 30 shopping, >= 20 reddit, >= 15 wiki?",
    "Is the report 3500-8000 words?",
    "Are all cited URLs markdown-linked and sandbox-resolvable?",
    "Does the report avoid producing a one-sided summary (only the popular cluster cited)?",
    "Does the report avoid chain-of-thought and start with the dual-cluster framing?",
]

LONG_TAIL_BASE_CHECKLIST: list[str] = [
    "Are >= 8 niche / long-tail items enumerated beyond the top-3 / top-5 popular options?",
    "Does the enumeration cite each niche item with a sandbox URL + a 1-sentence description?",
    "Are the niche items drawn from at least 3 distinct sandbox sub-domains (shopping / reddit / wiki)?",
    "Are >= 40 shopping product pages cited (where applicable) spanning niche SKUs, not only top-3 brands?",
    "Are >= 30 reddit threads from >= 4 sub-forums cited, including at least one specialist / niche sub-forum?",
    "Are >= 25 wiki articles cited, including at least 5 deep-page or low-traffic articles?",
    "Is per-domain minimum met: >= 30 shopping (or per-domain budget), >= 20 reddit, >= 15 wiki?",
    "Are >= 60 distinct URLs cited?",
    "Is the must-cite recall achieved against the long-tail-oversampled golden pool >= 0.45?",
    "Does the report explicitly distinguish 'mainstream' vs 'niche' tiers in the enumeration?",
    "Is the report 3500-8000 words?",
    "Are all cited URLs markdown-linked and sandbox-resolvable?",
    "Does the report avoid a flat TOP-10-only ranking format?",
    "Does the report avoid chain-of-thought?",
    "Does the report cite at least one wiki article per niche item that defines the niche category?",
]

FAMILY_BASE_CHECKLIST = {
    "causal":        CAUSAL_BASE_CHECKLIST,
    "contradiction": CONTRADICTION_BASE_CHECKLIST,
    "long_tail":     LONG_TAIL_BASE_CHECKLIST,
}


# -----------------------------------------------------------------------------
# Build per-task JSON
# -----------------------------------------------------------------------------

def _start_url_from_pool(pool: list[str]) -> str:
    """Pick the first shopping URL in the pool, else the first reddit, else
    the first wiki, else the literal first item."""
    for prefix in ("__SHOPPING__", "__REDDIT__", "__WIKIPEDIA__"):
        for url in pool:
            if url.startswith(prefix):
                return url
    return pool[0] if pool else "__SHOPPING__"


def _per_domain_minimum(family: str) -> dict[str, int]:
    """Long-tail tasks oversample wiki / reddit; causal / contradiction keep
    the v1 floor."""
    if family == "long_tail":
        return {"__SHOPPING__": 20, "__REDDIT__": 25, "__WIKIPEDIA__": 25}
    return {"__SHOPPING__": 30, "__REDDIT__": 20, "__WIKIPEDIA__": 15}


def _domains_in_pool(pool: list[str]) -> list[str]:
    sites: list[str] = []
    for url in pool:
        if url.startswith("__SHOPPING__") and "shopping" not in sites:
            sites.append("shopping")
        if url.startswith("__REDDIT__") and "reddit" not in sites:
            sites.append("reddit")
        if url.startswith("__WIKIPEDIA__") and "wikipedia" not in sites:
            sites.append("wikipedia")
    return sites or ["shopping", "reddit", "wikipedia"]


def _build_task(spec: dict) -> dict:
    family = spec["family"]
    task_id = spec["task_id"]
    intent = spec["intent_seed"] + FAMILY_INTENT_SUFFIX[family]

    return {
        "schema_version": "deep-1.0.0",
        "task_id": task_id,
        "tier": "deep_v2_adversarial",
        "sites": _domains_in_pool(spec["must_cite_pool"]),
        "difficulty": 6,
        "expected_steps": 90,
        "intent": intent,
        "start_url": _start_url_from_pool(spec["must_cite_pool"]),
        "storage_state": None,
        "require_login": False,
        "markdown_spec": {
            "min_words": 3500,
            "max_words": 8000,
            "min_paragraphs": 25,
            "min_citations": 60,
            "min_pages_browsed": 120,
        },
        "citation_policy": {
            "required_for": [
                "price",
                "rating",
                "thread_score",
                "feature_claim",
                "wiki_definition",
                "counter_evidence",
            ],
            "must_be_in_domain": [
                "__SHOPPING__",
                "__REDDIT__",
                "__WIKIPEDIA__",
            ],
            "min_distinct_sources": 60,
            "min_distinct_domains": 3,
            "per_domain_minimum": _per_domain_minimum(family),
        },
        "url_coverage": {
            "golden_pool_path": f"data/golden/deep_v2/{task_id}.json",
            "min_unique_urls_browsed": 100,
            "min_unique_urls_cited": 60,
            "min_must_cite_recall": 0.45,
            "min_expected_pool_coverage": 0.0,
            "min_domain_balance": 0.8,
            "weight_in_composite": 0.25,
            "scoring_weights": {
                "must_cite_recall": 0.60 if family == "long_tail" else 0.55,
                "pool_coverage":    0.20 if family == "long_tail" else 0.15,
                "domain_balance":   0.20 if family == "long_tail" else 0.30,
            },
        },
        "url_reachability": {
            "min_reachability_rate": 0.3,
            "probe_timeout_seconds": 6.0,
        },
        "golden": {
            "triples_path": f"data/golden/deep_v2/{task_id}.json",
            "must_cite_seed": spec["must_cite_pool"],
            "expected_predicates": [
                "price",
                "rating",
                "review_count",
                "feature_claim",
                "forum",
                "thread_score",
                "comment_count",
                "thread_classification",
                "wiki_defines",
                "counter_evidence",
            ],
        },
        "synthesis_requirements": _synthesis_for_family(family),
        "coverage_checklist_path":
            "data/tasks/deep_research/cross_site_deep_v2/checklists_deep_v2.json",
        "author_notes": (
            "v2 adversarial task. See configs/deep_topics/V2_ADVERSARIAL_TASKS.json "
            f"and V1_TASK_DESIGN_GRID.md section 5 for the design recipe. "
            f"Family: {family}. Real golden scrape happens on westd; "
            "this file only carries the must_cite seed."
        ),
        "domain": _domain_for_topic(spec["topic"]),
        "intent_type": _intent_type_for_family(family),
        "v2_meta": {
            "family": family,
            "topic":  spec["topic"],
            "expected_dim_stress": spec["expected_dim_stress"],
            "adversarial_rationale": spec["adversarial_rationale"],
        },
    }


def _synthesis_for_family(family: str) -> dict:
    if family == "causal":
        return {
            "task_type": "causal_debunking",
            "claim_count": 1,
            "verdict_levels": [
                "SUPPORTED",
                "PARTIALLY_SUPPORTED",
                "DEBUNKED",
                "UNDETERMINED",
            ],
            "min_counter_evidence_citations": 3,
            "require_contradicting_wiki_citation": True,
            "explicitly_forbid_top10": True,
        }
    if family == "contradiction":
        return {
            "task_type": "synthesis_under_contradiction",
            "cluster_count": 2,
            "min_citations_per_cluster": 3,
            "require_named_disagreement": True,
            "require_reconciliation_section": True,
            "explicitly_forbid_one_sided_summary": True,
        }
    return {
        "task_type": "long_tail_recall",
        "min_niche_items": 8,
        "min_distinct_tiers": 2,
        "min_must_cite_recall_long_tail_fraction": 0.60,
        "explicitly_forbid_top10_only": True,
    }


def _domain_for_topic(topic: str) -> str:
    t = topic.lower()
    if any(k in t for k in ("health", "vitamin", "sleep", "dog", "vaccine", "medicine", "fast")):
        return "Health"
    if any(k in t for k in ("ev", "battery", "5g", "usb", "vpn", "llm", "nas", "keyboard", "z-wave")):
        return "Tech"
    if any(k in t for k in ("etf", "carbon", "offset", "fund")):
        return "Finance"
    if any(k in t for k in ("game", "board", "mooc", "course")):
        return "Education"
    return "Consumer"


def _intent_type_for_family(family: str) -> str:
    return {
        "causal":        "Causal-Debunking",
        "contradiction": "Synthesis-Contradiction",
        "long_tail":     "Long-Tail-Enumeration",
    }[family]


# -----------------------------------------------------------------------------
# Checklist building
# -----------------------------------------------------------------------------

def _checklist_for_spec(spec: dict) -> list[str]:
    """Return 15-21 items per task: family base + per-task customisations."""
    family = spec["family"]
    base = list(FAMILY_BASE_CHECKLIST[family])
    extra: list[str] = []

    extra.append(
        f"Does the report explicitly engage with the topic '{spec['topic']}' "
        f"and not pivot to a related-but-different question?"
    )
    extra.append(
        "Does the report cite at least one URL from each of the items in "
        f"the must-cite seed list ({len(spec['must_cite_pool'])} items)?"
    )

    stress = spec.get("expected_dim_stress", [])
    if "rigor" in stress:
        extra.append(
            "Does the rigor lever surface (counter-evidence / specific "
            "numbers / verifiable factual contradiction) appear in the "
            "report body?"
        )
    if "depth" in stress:
        extra.append(
            "Does the depth lever surface (multi-source synthesis / cross-"
            "domain reconciliation / >= 2 reasoning hops) appear in the "
            "report body?"
        )
    if "coverage" in stress:
        extra.append(
            "Does the coverage lever surface (>= 8 long-tail / niche items "
            "with sandbox-local citations) appear in the report body?"
        )

    items = base + extra
    # Clamp to 15-21 — the verifier expects within that range.
    if len(items) > 21:
        items = items[:21]
    return items


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--specs",
        default=str(DEFAULT_SPECS),
        help="Path to V2_ADVERSARIAL_TASKS.json.",
    )
    ap.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="Output directory for the fully-fleshed task JSON files.",
    )
    args = ap.parse_args()

    specs_path = Path(args.specs)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(specs_path.read_text(encoding="utf-8"))
    specs = payload["tasks"]

    written = 0
    checklists: dict[str, list[str]] = {}
    for spec in specs:
        task = _build_task(spec)
        out_path = out_dir / f"{task['task_id']}.json"
        out_path.write_text(
            json.dumps(task, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        checklists[task["task_id"]] = _checklist_for_spec(spec)
        written += 1

    # Write the consolidated checklist file
    checklist_path = out_dir / "checklists_deep_v2.json"
    checklist_path.write_text(
        json.dumps(checklists, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Write an index
    index = {
        "schema_version": "v2-adversarial-1.0.0",
        "n_tasks": written,
        "family_counts": payload.get("family_counts", {}),
        "target_separability_pct": payload.get("target_separability_pct"),
        "task_ids": sorted(checklists.keys()),
        "validation_protocol": (
            "Run a 3-agent x 5-task pilot on westd / WSL before promoting "
            "any v2 task into the leaderboard. See V1_TASK_DESIGN_GRID.md "
            "section 5.4."
        ),
    }
    (out_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {written} v2 adversarial tasks to {out_dir}")
    print(f"Checklists  -> {checklist_path}")
    print(f"Index       -> {out_dir / 'index.json'}")
    print()
    print(
        "NEXT STEP: real validation requires the small adversarial pilot "
        "(3 agents x 5 tasks per family) on the westd / WSL benchmark "
        "host. See V1_TASK_DESIGN_GRID.md section 5.4 for the pre-screen "
        "protocol."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
