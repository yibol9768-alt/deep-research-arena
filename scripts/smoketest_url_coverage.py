#!/usr/bin/env python3
"""Smoke test for URLCoverageVerifier — uses a synthetic mock golden and mock
agent answers to prove the scoring math behaves as designed.

Run:
    python3 scripts/smoketest_url_coverage.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.verifiers.url_coverage_verifier import URLCoverageVerifier


SHOP = "http://localhost:7770"
RED = "http://localhost:9999"
WIKI = "http://localhost:8090"


def make_mock_golden() -> dict:
    must_cite = []
    pool = []
    for i in range(30):
        must_cite.append({"url": f"{SHOP}/product-{i:03d}.html", "category": "shopping_product", "weight": 1.0})
        pool.append({"url": f"{SHOP}/product-{i:03d}.html", "category": "shopping_product"})
    for i in range(30):
        pool.append({"url": f"{SHOP}/extra-{i:03d}.html", "category": "shopping_product"})

    for i in range(20):
        must_cite.append({"url": f"{RED}/f/technology/{1000+i}/thread-{i}", "category": "reddit_thread", "weight": 1.0})
        pool.append({"url": f"{RED}/f/technology/{1000+i}/thread-{i}", "category": "reddit_thread"})
    for i in range(20):
        pool.append({"url": f"{RED}/f/gadgets/{2000+i}/extra-{i}", "category": "reddit_thread"})

    for i in range(15):
        topic = f"Topic_{i}"
        must_cite.append({"url": f"{WIKI}/content/wikipedia_en_all_nopic/A/{topic}", "category": "wiki_article", "weight": 1.0})
        pool.append({"url": f"{WIKI}/content/wikipedia_en_all_nopic/A/{topic}", "category": "wiki_article"})
    for i in range(15):
        pool.append({"url": f"{WIKI}/content/wikipedia_en_all_nopic/A/Extra_{i}", "category": "wiki_article"})

    return {
        "task_id": "mock_deep_0001",
        "generated_at": "2026-04-24T00:00:00+00:00",
        "must_cite_urls": must_cite,
        "expected_pool_urls": pool,
        "triples": [],
        "metadata": {},
    }


def build_task_config(golden_path: Path) -> dict:
    return {
        "task_id": "mock_deep_0001",
        "url_coverage": {
            "golden_pool_path": str(golden_path),
            "min_unique_urls_cited": 60,
            "min_must_cite_recall": 0.50,
            "min_expected_pool_coverage": 0.35,
        },
        "citation_policy": {
            "per_domain_minimum": {
                "__SHOPPING__": 30,
                "__REDDIT__": 20,
                "__WIKIPEDIA__": 15,
            },
        },
        "domain_aliases": {
            "__SHOPPING__": ["7770"],
            "__REDDIT__":   ["9999"],
            "__WIKIPEDIA__": ["8090"],
        },
    }


def answer_from_urls(urls: list[str]) -> str:
    lines = ["# Mock Deep Research Report", ""]
    for i, u in enumerate(urls):
        lines.append(f"- Fact {i}: [label-{i}]({u})")
    return "\n".join(lines)


def scenario(name: str, urls: list[str], verifier: URLCoverageVerifier, task_cfg: dict) -> None:
    ans = answer_from_urls(urls)
    r = verifier.verify(task_config=task_cfg, answer=ans)
    status = "PASS" if r.passed else "FAIL"
    d = r.details
    print(f"[{status}] {name}")
    print(f"   score={r.score} | cited={d.get('cited_unique')} | "
          f"must_recall={d.get('must_cite_recall')} "
          f"(hit {d.get('must_cite_hit')}/{d.get('must_cite_total')}) | "
          f"pool_cov={d.get('pool_coverage')} "
          f"(hit {d.get('pool_hit')}/{d.get('pool_total')}) | "
          f"domain_balance={d.get('domain_balance')}")
    print(f"   per_domain_cited={d.get('per_domain_cited')}")
    print()


def main() -> int:
    golden = make_mock_golden()
    with tempfile.TemporaryDirectory() as td:
        gpath = Path(td) / "golden.json"
        gpath.write_text(json.dumps(golden))
        task_cfg = build_task_config(gpath)
        v = URLCoverageVerifier()

        must_urls = [e["url"] for e in golden["must_cite_urls"]]
        pool_urls = [e["url"] for e in golden["expected_pool_urls"]]

        scenario("empty report", [], v, task_cfg)
        scenario("only 5 must-cite URLs",
                 must_urls[:5], v, task_cfg)
        scenario("33 must-cite (50% recall) but nothing else",
                 must_urls[:33], v, task_cfg)
        scenario("all 65 must-cite + 20 pool extras (strong report)",
                 must_urls + pool_urls[30:50], v, task_cfg)
        scenario("70 URLs but all fake (no golden match)",
                 [f"http://random-{i}.example.com/x" for i in range(70)], v, task_cfg)
        scenario("60 cited but domain-skewed (all shopping, no reddit/wiki)",
                 [u for u in must_urls if "7770" in u][:30]
                 + [u for u in pool_urls if "7770" in u][:30], v, task_cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
