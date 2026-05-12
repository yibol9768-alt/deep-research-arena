"""Generate the task JSON + checklist entry for a deep-tier topic.

Inputs:
  configs/deep_topics/<N>_<topic>.yaml   (declares task_id + lists)
  data/golden/deep/<task_id>.json        (already scraped)

Outputs:
  data/tasks/deep_research/cross_site_deep/<task_id>.json   (task spec)
  appends 21 items to data/tasks/deep_research/cross_site_deep/checklists_deep.json

Usage:
    python3 scripts/gen_task_from_topic.py --all
    python3 scripts/gen_task_from_topic.py --topic-config configs/deep_topics/0002_coffee_brewing.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

ROOT = Path(__file__).resolve().parents[1]
TOPIC_DIR = ROOT / "configs" / "deep_topics"
GOLDEN_DIR = ROOT / "data" / "golden" / "deep"
TASK_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
CHECKLISTS_PATH = TASK_DIR / "checklists_deep.json"

TASK_DIR.mkdir(parents=True, exist_ok=True)


INTENT_TEMPLATE = """Produce a comprehensive market-intelligence report on {display_name}, spanning THREE dimensions. The report must be grounded in AT LEAST 120 distinct source URLs drawn from the sandbox (shopping / reddit / wikipedia), and MUST cite at least 60 of them as markdown links.

(A) PRODUCT LANDSCAPE — Enumerate {display_name} products on the One Stop Market (`__SHOPPING__`) across every relevant search facet: keywords at minimum {{{kw_list}}}. Target: ≥ 40 distinct product pages spanning ≥ 6 brands and ≥ 3 price tiers. For EACH product record: exact product_url, price, star rating, review_count, and every marketing feature-claim that appears on the page.

(B) COMMUNITY SENTIMENT — Harvest ≥ 30 distinct Postmill threads (`__REDDIT__`) discussing {display_name} across AT LEAST four sub-forums (e.g. {forum_list} — any four that yield on-topic posts). For each thread record: thread_url, forum, score, comment_count, and a one-sentence summary of the top-voted take. Classify each thread into one of {{praise, complaint, technical_question, comparison, purchase_advice}}.

(C) TECHNICAL GROUNDING — Using the English Wikipedia corpus served by Kiwix (`__WIKIPEDIA__`), locate ≥ 25 distinct Wikipedia articles that define OR explain the technical claims extracted from (A). Mandatory coverage for: {{{mandatory_list}}} plus ≥ 15 more articles covering the specific feature claims found in (A). For each article record: article_url and a one-sentence extraction of the defining statement.

(D) CROSS-SOURCE SYNTHESIS — The final report must include sections that:
  1. List ≥ 5 product feature claims from (A) that either LACK Wikipedia backing or CONTRADICT it — each with the product URL, the wiki URL, and the specific contradiction.
  2. Rank the brands found in (A) by aggregated Reddit sentiment, citing ≥ 2 reddit threads per brand as evidence.
  3. Surface ≥ 3 divergences where a product's star rating is high (≥ 4.0) but Reddit sentiment is negative, OR vice versa — each divergence cited with product URL + ≥ 1 reddit URL.
  4. Output a final TOP-10 list where each pick has (product URL + ≥ 2 reddit URL + ≥ 1 wiki URL) traceable evidence chain.

Formatting rules: every factual claim is a markdown link `[label](url)`. Source URLs MUST be sandbox-local. Do not fabricate URLs — the URL must resolve on the sandbox. Answer starts with the final report in Markdown; no chain-of-thought."""


CHECKLIST_TEMPLATE = [
    "Does the report enumerate at least 40 distinct product pages on the shopping site with exact URL + price + rating + review_count?",
    "Are at least 6 distinct brands represented among the enumerated products?",
    "Are at least 3 price tiers represented?",
    "Does each product entry extract at least one marketing feature-claim?",
    "Does the report harvest at least 30 distinct Postmill threads with thread_url + forum + score + comment_count?",
    "Are threads drawn from at least 4 distinct sub-forums?",
    "Is every thread classified as one of {praise, complaint, technical_question, comparison, purchase_advice}?",
    "Does the report locate at least 25 distinct Wikipedia articles with article_url + defining statement?",
    "Are the mandatory Wikipedia articles for this topic all present?",
    "Does the report surface at least 5 product-claim vs Wikipedia contradiction findings with triple evidence (product URL + wiki URL + explicit contradiction)?",
    "Does the report include a brand-sentiment ranking with at least 2 reddit threads cited per ranked brand?",
    "Does the report surface at least 3 rating-vs-sentiment divergences?",
    "Does the final TOP-10 list have exactly 10 items?",
    "Does each TOP-10 item have (≥1 shopping URL + ≥2 reddit URL + ≥1 wiki URL) as evidence chain?",
    "Are all cited URLs markdown-linked `[label](url)` form and resolvable on the sandbox?",
    "Does the report cite at least 60 distinct URLs in total?",
    "Is at least 30 of the 60+ cited URLs from shopping domain?",
    "Is at least 20 of the 60+ cited URLs from reddit domain?",
    "Is at least 15 of the 60+ cited URLs from wikipedia domain?",
    "Is the report between 3500 and 8000 words?",
    "Does the report avoid chain-of-thought and start directly with the market-intelligence content?",
]


def _build_task(cfg_path: Path) -> tuple[str, dict, list[str]]:
    cfg = yaml.safe_load(cfg_path.read_text())
    task_id = cfg["task_id"]
    display_name = cfg.get("display_name", task_id)
    golden_path = GOLDEN_DIR / f"{task_id}.json"
    if not golden_path.exists():
        raise FileNotFoundError(f"{golden_path} missing; scrape first")
    golden = json.loads(golden_path.read_text())
    must = len(golden.get("must_cite_urls", []))
    pool = len(golden.get("expected_pool_urls", []))

    kw_list = ", ".join(cfg.get("shopping_keywords", [])[:9])
    forum_list = ", ".join(f"/f/{f}" for f in cfg.get("reddit_forums", [])[:7])
    mandatory_list = ", ".join(cfg.get("wiki_mandatory", [])[:9])

    intent = INTENT_TEMPLATE.format(
        display_name=display_name,
        kw_list=kw_list,
        forum_list=forum_list,
        mandatory_list=mandatory_list,
    )

    first_kw = (cfg.get("shopping_keywords") or ["products"])[0]
    start_url = f"__SHOPPING__/catalogsearch/result/?q={first_kw.replace(' ', '+')}"

    task_json = {
        "schema_version": "deep-1.0.0",
        "task_id": task_id,
        "tier": "deep",
        "sites": ["shopping", "reddit", "wikipedia"],
        "difficulty": 5,
        "expected_steps": 80,
        "intent": intent,
        "start_url": start_url,
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
            "required_for": ["price", "rating", "thread_score", "feature_claim", "wiki_definition"],
            "must_be_in_domain": ["__SHOPPING__", "__REDDIT__", "__WIKIPEDIA__"],
            "min_distinct_sources": 60,
            "min_distinct_domains": 3,
            "per_domain_minimum": {"__SHOPPING__": 30, "__REDDIT__": 20, "__WIKIPEDIA__": 15},
        },
        "url_coverage": {
            "golden_pool_path": f"data/golden/deep/{task_id}.json",
            "min_unique_urls_browsed": 100,
            "min_unique_urls_cited": 60,
            "min_must_cite_recall": 0.45,
            "min_expected_pool_coverage": 0.00,
            "min_domain_balance": 0.80,
            "weight_in_composite": 0.25,
            "scoring_weights": {
                "must_cite_recall": 0.55,
                "pool_coverage": 0.15,
                "domain_balance": 0.30,
            },
        },
        "url_reachability": {
            "min_reachability_rate": 0.30,
            "probe_timeout_seconds": 6.0,
        },
        "golden": {
            "triples_path": f"data/golden/deep/{task_id}.json",
            "expected_predicates": [
                "price", "rating", "review_count", "feature_claim",
                "forum", "thread_score", "comment_count", "thread_classification",
                "wiki_defines",
            ],
        },
        "synthesis_requirements": {
            "contradiction_findings_min": 5,
            "brand_sentiment_rankings_min": 4,
            "rating_sentiment_divergences_min": 3,
            "final_buy_list_size": 10,
            "final_buy_list_sources_per_item": {"shopping": 1, "reddit": 2, "wikipedia": 1},
        },
        "coverage_checklist_path": "data/tasks/deep_research/cross_site_deep/checklists_deep.json",
        "author_notes": f"Deep-tier task generated from configs/deep_topics/{cfg_path.name}. "
                        f"Golden: must={must}, pool={pool}.",
    }
    return task_id, task_json, CHECKLIST_TEMPLATE


def _persist(task_id: str, task_json: dict, checklist: list[str]) -> None:
    out_path = TASK_DIR / f"{task_id}.json"
    out_path.write_text(json.dumps(task_json, indent=2, ensure_ascii=False))

    if CHECKLISTS_PATH.exists():
        existing = json.loads(CHECKLISTS_PATH.read_text())
    else:
        existing = {}
    existing[task_id] = checklist
    CHECKLISTS_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    print(f"wrote {out_path.name} (+ checklist[{task_id}] = {len(checklist)} items)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic-config")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.all:
        configs = sorted(TOPIC_DIR.glob("*.yaml"))
    elif args.topic_config:
        configs = [Path(args.topic_config)]
    else:
        ap.error("--topic-config or --all required")

    for cfg in configs:
        try:
            tid, tj, chk = _build_task(cfg)
            _persist(tid, tj, chk)
        except FileNotFoundError as e:
            print(f"skip {cfg.name}: {e}")
        except Exception as e:
            print(f"error {cfg.name}: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
