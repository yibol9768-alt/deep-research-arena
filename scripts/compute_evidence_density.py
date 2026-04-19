#!/usr/bin/env python3
"""Half-hour validation: compute evidence-density metrics on existing reports.

For each data/results/final_*.answer.md (and deerflow_final_*.md), emit:
  - total_words
  - unique_pdp_urls      (shopping product-detail pages, slug-based)
  - unique_reddit_posts  (Reddit post IDs)
  - meta_word_ratio      (words under headers like Methodology/Future Work/etc)
  - substance_words      = total_words * (1 - meta_word_ratio)
  - evidence_density_score (0-1 composite of above)

Then re-simulate a composite with a new evidence_density pillar at weight 0.10
and see whether the agent ordering better matches subjective review.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

RESULTS = Path(__file__).parent.parent / "data" / "results"

_PDP_SLUG_RE = re.compile(
    r"http://localhost:7770/([a-z0-9][a-z0-9\-]+)\.html",
    re.I,
)
_PDP_ID_RE = re.compile(
    r"http://localhost:7770/catalog/product/view/id/(\d+)",
    re.I,
)
# Exclude category landing pages, search URLs, homepage
_PDP_EXCLUDE = {
    "home-kitchen", "office-products", "electronics", "health-household",
    "cell-phones-accessories", "beauty-personal-care", "sports-outdoors",
    "grocery-gourmet-food", "video-games", "clothing-shoes-jewelry",
    "baby", "toys-games", "pet-supplies", "tools-home-improvement",
    "automotive", "patio-lawn-garden", "kitchen-dining",
    "cell-phones", "computers-accessories", "musical-instruments",
}

_REDDIT_POST_RE = re.compile(
    r"http://localhost:9999/f/[A-Za-z0-9_]+/(\d+)",
)

_META_HEADER_PAT = re.compile(
    r"^#{1,6}\s+(methodology|limitations?|future research|future work|"
    r"survey note|literature review|critical discussion|key citations|"
    r"research methodology|data extraction|theoretical framework|"
    r"data access|access limitations|extraction challenges|"
    r"future research directions)\b",
    re.I | re.M,
)


def count_unique_pdp_urls(text: str) -> int:
    refs = set()
    for m in _PDP_SLUG_RE.finditer(text):
        slug = m.group(1).lower()
        if slug in _PDP_EXCLUDE:
            continue
        if slug.count("-") < 2:
            continue
        refs.add(("slug", slug))
    for m in _PDP_ID_RE.finditer(text):
        refs.add(("id", m.group(1)))
    return len(refs)


def count_unique_reddit_posts(text: str) -> int:
    ids = set()
    for m in _REDDIT_POST_RE.finditer(text):
        ids.add(m.group(1))
    return len(ids)


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split a markdown document into (header, body) sections."""
    lines = text.split("\n")
    sections: list[tuple[str, str]] = []
    cur_header = ""
    cur_body: list[str] = []
    for ln in lines:
        if re.match(r"^#{1,6}\s+", ln):
            if cur_header or cur_body:
                sections.append((cur_header, "\n".join(cur_body)))
            cur_header = ln
            cur_body = []
        else:
            cur_body.append(ln)
    sections.append((cur_header, "\n".join(cur_body)))
    return sections


def meta_word_ratio(text: str) -> tuple[float, int, int]:
    """Return (ratio, meta_words, total_words) where meta = words under
    meta-style headers (Methodology / Limitations / Future Research /
    Survey Note / Literature Review / ...).
    """
    total = len(text.split())
    if total == 0:
        return 0.0, 0, 0
    meta_words = 0
    for header, body in _split_sections(text):
        if _META_HEADER_PAT.search(header):
            meta_words += len(body.split())
    return meta_words / total, meta_words, total


def evidence_density_score(
    pdps: int, posts: int, meta_ratio: float,
    req_products: int = 6, req_posts: int = 4,
) -> float:
    pdp_component = min(pdps / req_products, 1.0)
    post_component = min(posts / req_posts, 1.0)
    substance_component = max(0.0, 1.0 - meta_ratio)
    return round(0.4 * pdp_component + 0.3 * post_component + 0.3 * substance_component, 3)


def analyze_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    pdps = count_unique_pdp_urls(text)
    posts = count_unique_reddit_posts(text)
    ratio, meta_w, total_w = meta_word_ratio(text)
    ed = evidence_density_score(pdps, posts, ratio)
    return {
        "file": path.name,
        "total_words": total_w,
        "unique_pdp_urls": pdps,
        "unique_reddit_posts": posts,
        "meta_word_ratio": round(ratio, 3),
        "substance_words": int(total_w * (1 - ratio)),
        "evidence_density_score": ed,
    }


def load_composite(path: Path) -> dict:
    """Load the matching final_*.json for existing composite scores."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def main() -> None:
    # Match final_<agent>_<task>.answer.md with final_<agent>_<task>.json
    answers = sorted(RESULTS.glob("final_*.answer.md"))

    rows = []
    for ans in answers:
        result = analyze_file(ans)
        json_path = RESULTS / ans.name.replace(".answer.md", ".json")
        composite_data = load_composite(json_path)
        result["old_composite"] = composite_data.get("composite", None)
        # Decompose agent + task from filename
        stem = ans.name.replace("final_", "").replace(".answer.md", "")
        # e.g. "react-qwen35plus_dr_cross_v3_0007"
        parts = stem.split("_", 1)
        result["agent"] = parts[0]
        result["task"] = parts[1] if len(parts) > 1 else ""
        rows.append(result)

    # Print summary
    print("=" * 100)
    print(f"{'agent':<22} {'task':<22} {'words':>6} {'pdp':>4} {'red':>4} "
          f"{'meta%':>6} {'ED':>5} {'old':>5}")
    print("-" * 100)
    for r in rows:
        print(
            f"{r['agent']:<22} {r['task']:<22} "
            f"{r['total_words']:>6} {r['unique_pdp_urls']:>4} {r['unique_reddit_posts']:>4} "
            f"{int(r['meta_word_ratio']*100):>5}% "
            f"{r['evidence_density_score']:>5.2f} "
            f"{(r['old_composite'] or 0):>5.2f}"
        )
    print("=" * 100)

    # Aggregate per-agent
    agg = {}
    for r in rows:
        a = r["agent"]
        agg.setdefault(a, []).append(r)

    print("\nPer-agent aggregates:")
    print(f"{'agent':<22} {'mean_ED':>8} {'mean_old':>9} {'mean_pdp':>9} {'mean_red':>9} {'mean_meta%':>11}")
    for a, lst in agg.items():
        import statistics
        mean_ed = statistics.mean(r["evidence_density_score"] for r in lst)
        mean_old = statistics.mean(r["old_composite"] or 0 for r in lst)
        mean_pdp = statistics.mean(r["unique_pdp_urls"] for r in lst)
        mean_red = statistics.mean(r["unique_reddit_posts"] for r in lst)
        mean_meta = statistics.mean(r["meta_word_ratio"] for r in lst)
        print(f"{a:<22} {mean_ed:>8.3f} {mean_old:>9.3f} {mean_pdp:>9.1f} {mean_red:>9.1f} {int(mean_meta*100):>10}%")

    # Simulated new composite: inject evidence_density (0.10) taking from
    #   markdown_structure 0.10 -> 0.05 AND efficiency 0.05 -> 0.00 (drop)
    # Old: md=0.10 cit=0.15 fkg=0.30 jdg=0.20 chk=0.20 eff=0.05
    # New: md=0.05 cit=0.15 fkg=0.30 jdg=0.20 chk=0.20 ed=0.10 eff=0.00
    # (efficiency dropped only in this simulation — full plan keeps it at 0.05)
    print("\nSimulated new composite (drops efficiency, adds evidence_density@0.10):")
    for r in rows:
        jp = RESULTS / f"final_{r['agent']}_{r['task']}.json"
        try:
            data = json.loads(jp.read_text())
        except Exception:
            continue
        p = data.get("pillars", {})
        new = (
            0.05 * p.get("markdown_structure", {}).get("score", 0)
            + 0.15 * p.get("citation", {}).get("score", 0)
            + 0.30 * p.get("fact_kg", {}).get("score", 0)
            + 0.20 * p.get("llm_judge", {}).get("score", 0)
            + 0.20 * p.get("checklist", {}).get("score", 0)
            + 0.10 * r["evidence_density_score"]
        )
        r["new_composite"] = round(new, 3)

    print(f"{'agent':<22} {'task':<22} {'OLD':>6} {'NEW':>6} {'Δ':>7}")
    for r in sorted(rows, key=lambda x: (x.get("new_composite", 0) or 0), reverse=True):
        old = r.get("old_composite") or 0
        new = r.get("new_composite") or 0
        delta = new - old
        print(f"{r['agent']:<22} {r['task']:<22} {old:>6.2f} {new:>6.2f} {delta:>+7.2f}")

    # Per-agent mean NEW composite
    print("\nPer-agent mean NEW composite (evidence-density-aware):")
    for a, lst in agg.items():
        import statistics
        lst_with_new = [r for r in lst if "new_composite" in r]
        if not lst_with_new:
            continue
        mean_new = statistics.mean(r["new_composite"] for r in lst_with_new)
        mean_old = statistics.mean(r["old_composite"] or 0 for r in lst_with_new)
        print(f"{a:<22} old={mean_old:.3f}   new={mean_new:.3f}   Δ={mean_new-mean_old:+.3f}")


if __name__ == "__main__":
    main()
