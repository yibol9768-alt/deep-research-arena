#!/usr/bin/env python3
"""Smoke test URLCoverageVerifier against the REAL scraped golden.
Simulates three agent behaviours: perfect, partial, fabricating.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.verifiers.url_coverage_verifier import URLCoverageVerifier


def answer_of(urls: list[str], prefix: str = "") -> str:
    out = [f"# {prefix}Deep Research Report", ""]
    for i, u in enumerate(urls):
        out.append(f"- fact {i}: [link-{i}]({u})")
    return "\n".join(out)


def main() -> int:
    task = json.loads(Path("data/tasks/deep_research/cross_site_deep/dr_cross_deep_0001.json").read_text())
    golden = json.loads(Path(task["url_coverage"]["golden_pool_path"]).read_text())

    task["domain_aliases"] = {
        "__SHOPPING__":  ["localhost:7770"],
        "__REDDIT__":    ["localhost:9999"],
        "__WIKIPEDIA__": ["localhost:8090"],
    }

    must = [e["url"] for e in golden["must_cite_urls"]]
    pool = [e["url"] for e in golden["expected_pool_urls"]]
    shop_pool = [u for u in pool if "7770" in u]
    red_pool  = [u for u in pool if "9999" in u]
    wiki_pool = [u for u in pool if "8090" in u]

    v = URLCoverageVerifier()
    rng = random.Random(42)

    def run(name: str, urls: list[str]) -> None:
        r = v.verify(task_config=task, answer=answer_of(urls), page=None)
        d = r.details
        tag = "PASS" if r.passed else "FAIL"
        print(f"[{tag}] {name:<48s} score={r.score:.4f}")
        print(f"      cited={d['cited_unique']:3d}  must_recall={d['must_cite_recall']:.3f}"
              f"  pool_cov={d['pool_coverage']:.3f}  dom_bal={d['domain_balance']:.3f}"
              f"  per_dom={d['per_domain_cited']}")

    print(f"=== real golden: {len(must)} must-cite, {len(pool)} pool ===\n")

    run("A: perfect (all must-cite)", must)
    run("B: excellent (all must + 50 pool extras)",
        must + rng.sample([u for u in pool if u not in must], 50))
    run("C: minimum-passing (63 must-cite = 50% of 125)", rng.sample(must, 63))
    run("D: shopping-only narrow (all 60 shop must)",
        [u for u in must if "7770" in u])
    run("E: fabricator (70 fake URLs)",
        [f"http://fake{i}.invalid/x" for i in range(70)])
    run("F: moderate (40 must + 30 pool extras)",
        rng.sample(must, 40) + rng.sample([u for u in pool if u not in must], 30))
    run("G: pool-only (no must-cite touched, 60 from pool)",
        rng.sample([u for u in pool if u not in must], 60))
    return 0


if __name__ == "__main__":
    sys.exit(main())
