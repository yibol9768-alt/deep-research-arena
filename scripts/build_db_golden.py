#!/usr/bin/env python3
"""Build a DB-derived closed-world golden (CLOSED_WORLD_REDESIGN.md section 6).

Replaces the keyword-CRAWL golden (build_deep_golden.py) with DB ENUMERATION. In
a closed world the relevant set is a query, not a scrape: there is no ear-piercing
gun in ``SELECT ... WHERE name LIKE '%headphones%'``. Emits, per task:

  relevant_set : the complete set of on-topic sandbox entities with DB-true facts
                 (the exact completeness denominator, section 8).
  fact_nuggets : atomic, weighted (vital/useful) facts a good report should convey
                 (the content key, section 6.3; scored by semantic coverage).

Runs on the box (my5090) via DBRunner (ssh -> docker exec mysql/psql). The shopping
container (Magento) and reddit container (Postmill) must be queryable.

    WESTD_SSH_HOST=my5090 python3 scripts/build_db_golden.py \
        --task-id dr_cross_deep_0001 \
        --topic-config configs/deep_topics/0001_audio_headphones.yaml \
        --out data/golden/db/dr_cross_deep_0001.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.golden.db_connect import DBRunner  # noqa: E402

MAG_BASE_URL = "http://localhost:7770"
REDDIT_BASE_URL = "http://localhost:9999"

# Ambiguous single tokens that pull off-topic rows on their own (the old
# crawl's failure mode). Keywords reduced to these are skipped for enumeration.
_AMBIGUOUS = {
    "audio", "wireless", "ear", "over", "in", "sound", "smart", "pro", "new",
    "best", "mini", "bass", "music", "stereo", "hd", "hi", "fi",
}


def _sql_escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace("'", "''")


def load_topic(path: str | None) -> dict:
    default = {
        "shopping_keywords": ["headphones", "earbuds", "earphones", "noise cancelling", "gaming headset"],
        "reddit_keywords": ["headphones", "earbuds", "bluetooth", "noise cancelling", "airpods"],
    }
    if not path:
        return default
    txt = Path(path).read_text()
    try:
        import yaml  # type: ignore
        cfg = yaml.safe_load(txt) or {}
    except Exception:
        cfg = json.loads(txt)
    return {
        "shopping_keywords": cfg.get("shopping_keywords") or default["shopping_keywords"],
        "reddit_keywords": cfg.get("reddit_keywords") or default["reddit_keywords"],
    }


def _good_keywords(kws: list[str]) -> list[str]:
    """Keep only keywords with at least one non-ambiguous, >=4-char token."""
    out = []
    for kw in kws:
        toks = [t for t in kw.lower().split() if len(t) >= 4 and t not in _AMBIGUOUS]
        if toks:
            out.append(kw)
    return out


def enumerate_shopping(db: DBRunner, keywords: list[str], limit_per_kw: int = 300) -> list[dict]:
    seen: dict[str, dict] = {}
    for kw in _good_keywords(keywords):
        like = _sql_escape_like(kw)
        sql = (
            "SELECT p.entity_id, nv.value, uv.value, "
            "CAST(d.value AS CHAR), "
            "CAST(ROUND(res.rating_summary/20,1) AS CHAR), "
            "CAST(res.reviews_count AS CHAR) "
            "FROM catalog_product_entity p "
            "JOIN catalog_product_entity_varchar nv ON nv.entity_id=p.entity_id AND nv.attribute_id=73 "
            "LEFT JOIN catalog_product_entity_varchar uv ON uv.entity_id=p.entity_id AND uv.attribute_id=121 "
            "LEFT JOIN catalog_product_entity_decimal d ON d.entity_id=p.entity_id AND d.attribute_id=77 "
            "LEFT JOIN review_entity_summary res ON res.entity_pk_value=p.entity_id AND res.store_id=1 "
            f"WHERE nv.value LIKE '%{like}%' ESCAPE '\\\\' "
            f"LIMIT {limit_per_kw}"
        )
        r = db.mysql(sql, timeout=40)
        if not r.ok:
            print(f"  ! mysql fail kw={kw!r}: {r.stderr[:120]}", file=sys.stderr)
            continue
        for row in r.rows:
            if len(row) < 3:
                continue
            eid, name, url_key = row[0], row[1], row[2]
            price = row[3] if len(row) > 3 else ""
            rating = row[4] if len(row) > 4 else ""
            reviews = row[5] if len(row) > 5 else ""
            if not url_key or url_key == "NULL":
                continue
            url = f"{MAG_BASE_URL}/{url_key}.html"
            facts = {}
            if price and price != "NULL":
                facts["price"] = str(price)
            if rating and rating not in ("NULL", "None"):
                facts["rating"] = str(rating)
            if reviews and reviews not in ("NULL", "0"):
                facts["review_count"] = str(reviews)
            # vital if it carries review evidence (a concrete, reviewed product);
            # useful otherwise. This is an importance signal, not relevance.
            weight = 1.0 if "review_count" in facts and "rating" in facts else 0.5
            seen[url] = {"url": url, "name": name, "category": "shopping_product",
                        "weight": weight, "facts": facts}
    return list(seen.values())


def enumerate_reddit(db: DBRunner, keywords: list[str], limit_per_kw: int = 300) -> list[dict]:
    seen: dict[str, dict] = {}
    for kw in _good_keywords(keywords):
        safe = kw.replace("'", "''")
        sql = (
            "SELECT s.id, s.title, s.net_score, s.comment_count, f.normalized_name "
            "FROM submissions s JOIN forums f ON f.id=s.forum_id "
            f"WHERE s.title ILIKE '%{safe}%' "
            f"LIMIT {limit_per_kw}"
        )
        r = db.postgres(sql, timeout=40)
        if not r.ok:
            print(f"  ! psql fail kw={kw!r}: {r.stderr[:120]}", file=sys.stderr)
            continue
        for row in r.rows:
            if len(row) < 5:
                continue
            sid, title, score, ccount, forum = row[0], row[1], row[2], row[3], row[4]
            url = f"{REDDIT_BASE_URL}/f/{forum}/{sid}"
            facts = {}
            if score not in ("", "NULL", None):
                facts["thread_score"] = str(score)
            if ccount not in ("", "NULL", None):
                facts["comment_count"] = str(ccount)
            if forum:
                facts["forum"] = str(forum)
            weight = 1.0 if "thread_score" in facts and "comment_count" in facts else 0.5
            seen[url] = {"url": url, "name": title, "category": "reddit_thread",
                        "weight": weight, "facts": facts}
    return list(seen.values())


def make_nuggets(relevant: list[dict]) -> list[dict]:
    """Atomic, self-contained, weighted fact nuggets from the relevant set."""
    nuggets = []
    for e in relevant:
        name = e.get("name", "")
        for pred, val in (e.get("facts") or {}).items():
            if pred in ("price",):
                text = f"{name} is priced at {val}."
                vital = e.get("weight", 0.5) >= 1.0
            elif pred in ("rating",):
                text = f"{name} has a {val}-star rating."
                vital = True
            elif pred in ("thread_score",):
                text = f'The thread "{name[:60]}" has a score of {val}.'
                vital = e.get("weight", 0.5) >= 1.0
            elif pred in ("review_count", "comment_count", "forum"):
                continue  # secondary; captured via the entity, not a headline nugget
            else:
                continue
            nuggets.append({"text": text, "subject": name, "predicate": pred,
                           "object": str(val), "source_url": e.get("url"),
                           "importance": "vital" if vital else "useful"})
    return nuggets


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--topic-config")
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip", choices=["shopping", "reddit"], action="append", default=[])
    args = ap.parse_args()

    topic = load_topic(args.topic_config)
    db = DBRunner()

    relevant: list[dict] = []
    if "shopping" not in args.skip:
        shop = enumerate_shopping(db, topic["shopping_keywords"])
        print(f"[shopping] {len(shop)} relevant products")
        relevant += shop
    if "reddit" not in args.skip:
        red = enumerate_reddit(db, topic["reddit_keywords"])
        print(f"[reddit] {len(red)} relevant threads")
        relevant += red

    nuggets = make_nuggets(relevant)
    vital = sum(1 for n in nuggets if n["importance"] == "vital")
    bundle = {
        "task_id": args.task_id,
        "relevant_set": relevant,
        "fact_nuggets": nuggets,
        "metadata": {
            "n_relevant": len(relevant),
            "n_nuggets": len(nuggets),
            "n_vital_nuggets": vital,
            "source": "db_enumeration",
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False))
    print(f"=== wrote {out}: {len(relevant)} entities, {len(nuggets)} nuggets ({vital} vital) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
