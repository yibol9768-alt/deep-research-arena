#!/usr/bin/env python3
"""Category-based DB golden (the fixed query; METHODOLOGY_REDESIGN §7).

Replaces keyword-substring enumeration (`WHERE name LIKE '%headphones%'`, which
pulled in glass stickers, keyboard bundles and cables) with the store's OWN
taxonomy: a task's relevant product set is the membership of the matching
catalog categories and their descendants. In a closed world the category tree
IS the ground-truth relevance signal, so the completeness denominator is clean
by construction rather than a noisy keyword net.

Resolution:
  1. find leaf/branch categories whose NAME matches a topic head term
     (e.g. "headphones" -> Headphones/Earbud Headphones/Over-Ear/On-Ear),
  2. expand to descendants via the category `path`,
  3. enumerate products in those categories with DB-true facts,
  4. drop the residual accessories/parts inside the category with the light
     deterministic filter (cables, cases, cleaners, replacement parts).

Runs on the box where docker exec reaches the containers directly (no ssh/scp).
Reddit threads and wiki articles are enumerated as before (forums / mandatory
article list from the topic config); this module fixes the shopping half, which
is where the keyword collision lived.

Usage (on the box, inside WSL):
  python3 scripts/build_db_golden_by_category.py \
      --task-id dr_cross_deep_0001 --heads headphones,earbud,earphone,headset \
      --out data/golden/db_cat/dr_cross_deep_0001.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAG_BASE_URL = "http://localhost:7770"
MAG_CONTAINER = "dr_sandbox_shopping"
MAG = ["docker", "exec", "-i", MAG_CONTAINER, "mysql", "-u", "magentouser",
       "-pMyPassword", "-s", "-N", "magentodb"]
NAME_ATTR = 73  # catalog_product_entity_varchar name
URLKEY_ATTR = 121
PRICE_ATTR = 77

_ACCESSORY = re.compile(
    r"\b(cable|adapter|dongle|splitter|replacement|spare|cleaner|cleaning|"
    r"carrying case|hard case|ear\s?pad|cushion|cover|mount|stand|holder|"
    r"tip|tips only|charger only)\b", re.I)


def mysql(sql: str) -> list[list[str]]:
    r = subprocess.run(MAG, input=sql, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"! mysql: {r.stderr[:200]}", file=sys.stderr)
        return []
    return [ln.split("\t") for ln in r.stdout.splitlines() if ln.strip()]


def resolve_categories(heads: list[str]) -> list[tuple[str, str]]:
    """Categories whose name matches a head term, plus their descendants."""
    pat = "|".join(re.escape(h) for h in heads)
    rows = mysql(
        "SELECT c.entity_id, c.path, v.value FROM catalog_category_entity c "
        "JOIN catalog_category_entity_varchar v ON v.entity_id=c.entity_id "
        "AND v.attribute_id=(SELECT attribute_id FROM eav_attribute "
        "WHERE entity_type_id=3 AND attribute_code='name') "
        f"WHERE v.value REGEXP '{pat}';")
    matched = [(r[0], r[1], r[2]) for r in rows if len(r) >= 3]
    if not matched:
        return []
    # expand to descendants via path prefix
    all_rows = mysql(
        "SELECT c.entity_id, c.path, v.value FROM catalog_category_entity c "
        "JOIN catalog_category_entity_varchar v ON v.entity_id=c.entity_id "
        "AND v.attribute_id=(SELECT attribute_id FROM eav_attribute "
        "WHERE entity_type_id=3 AND attribute_code='name');")
    paths = {r[0]: (r[1], r[2]) for r in all_rows if len(r) >= 3}
    keep = {}
    match_ids = {m[0] for m in matched}
    for cid, (path, name) in paths.items():
        segs = set(path.split("/"))
        if cid in match_ids or (segs & match_ids):
            keep[cid] = name
    return sorted(keep.items())


def enumerate_by_category(cat_ids: list[str], limit: int = 5000) -> list[dict]:
    ids = ",".join(cat_ids)
    rows = mysql(
        "SELECT DISTINCT p.entity_id, nv.value, uv.value, CAST(d.value AS CHAR), "
        "CAST(ROUND(res.rating_summary/20,1) AS CHAR), CAST(res.reviews_count AS CHAR) "
        "FROM catalog_category_product cp "
        "JOIN catalog_product_entity p ON p.entity_id=cp.product_id "
        f"JOIN catalog_product_entity_varchar nv ON nv.entity_id=p.entity_id AND nv.attribute_id={NAME_ATTR} "
        f"LEFT JOIN catalog_product_entity_varchar uv ON uv.entity_id=p.entity_id AND uv.attribute_id={URLKEY_ATTR} "
        f"LEFT JOIN catalog_product_entity_decimal d ON d.entity_id=p.entity_id AND d.attribute_id={PRICE_ATTR} "
        "LEFT JOIN review_entity_summary res ON res.entity_pk_value=p.entity_id AND res.store_id=1 "
        f"WHERE cp.category_id IN ({ids}) LIMIT {limit};")
    seen = {}
    dropped_acc = 0
    for row in rows:
        if len(row) < 3:
            continue
        eid, name, url_key = row[0], row[1], row[2]
        if not url_key or url_key == "NULL":
            continue
        if _ACCESSORY.search(name):
            dropped_acc += 1
            continue
        price = row[3] if len(row) > 3 else ""
        rating = row[4] if len(row) > 4 else ""
        reviews = row[5] if len(row) > 5 else ""
        facts = {}
        if price and price != "NULL":
            facts["price"] = str(price)
        if rating and rating not in ("NULL", "None"):
            facts["rating"] = str(rating)
        if reviews and reviews not in ("NULL", "0"):
            facts["review_count"] = str(reviews)
        weight = 1.0 if "review_count" in facts and "rating" in facts else 0.5
        url = f"{MAG_BASE_URL}/{url_key}.html"
        seen[url] = {"url": url, "name": name, "category": "shopping_product",
                     "weight": weight, "facts": facts}
    print(f"  category enumeration: {len(seen)} products (dropped {dropped_acc} accessories)")
    return list(seen.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--heads", help="comma-separated category head terms (bootstrap suggest)")
    ap.add_argument("--category-ids", help="comma-separated curated category ids "
                    "(the precise task scope; preferred over --heads). Descendants "
                    "are expanded automatically.")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.category_ids:
        # curated scope: the exact categories this task is about, + descendants
        seed = [c.strip() for c in args.category_ids.split(",") if c.strip()]
        all_rows = mysql(
            "SELECT c.entity_id, c.path, v.value FROM catalog_category_entity c "
            "JOIN catalog_category_entity_varchar v ON v.entity_id=c.entity_id "
            "AND v.attribute_id=(SELECT attribute_id FROM eav_attribute "
            "WHERE entity_type_id=3 AND attribute_code='name');")
        paths = {r[0]: (r[1], r[2]) for r in all_rows if len(r) >= 3}
        seedset = set(seed)
        cats = sorted((cid, name) for cid, (path, name) in paths.items()
                      if cid in seedset or (set(path.split("/")) & seedset))
        heads = []
    else:
        heads = [h.strip() for h in (args.heads or "").split(",") if h.strip()]
        cats = resolve_categories(heads)
    if not cats:
        print(f"no categories matched (heads={heads or args.category_ids})", file=sys.stderr)
        return 1
    print(f"[categories] {len(cats)} matched: "
          + ", ".join(f"{name}({cid})" for cid, name in cats[:8])
          + (" ..." if len(cats) > 8 else ""))
    products = enumerate_by_category([c[0] for c in cats])

    bundle = {
        "task_id": args.task_id,
        "relevant_set": products,
        "fact_nuggets": [],  # nuggets built by build_answer_keys from facts
        "metadata": {
            "n_relevant": len(products),
            "source": "db_category_enumeration",
            "categories": [{"id": c, "name": n} for c, n in cats],
            "head_terms": heads,
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False))
    print(f"=== wrote {out}: {len(products)} category-relevant products ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
