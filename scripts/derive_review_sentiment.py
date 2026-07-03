#!/usr/bin/env python3
"""Review-sentiment deriver (EXECUTION_PLAN P3.2, #27a): decidable buyer
sentiment nuggets from the store's own authenticated reviews.

Input: the TSV from dump_category_reviews.sh (one row per review). Output:
per-product sentiment records suitable for answer_key nuggets:

  {product_id, url_key, name, price, rating_pct, n_reviews,
   pct_negative, complaint_terms: [(term, count)], praise_terms: [...]}

Everything is counting, no model: negative = review's own vote <= 40/100
(2 stars); complaint/praise terms = frequent content unigrams+bigrams in
negative vs positive review text, minus stopwords and product-name tokens
(so "sound quality" can surface as a complaint about headphones without
"headphones" itself scoring). The review corpus was authenticity-audited
(data/results/real/review_authenticity_audit.json) before this deriver was
allowed to feed ground truth.

Usage:
  python3 scripts/derive_review_sentiment.py reviews_cat.tsv \
      --min-reviews 3 --out data/golden/sentiment/<task>.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

WORD = re.compile(r"[a-z][a-z']{2,}")
STOP = set("""the and for with was but are this not you have very had they
them their its it's from would could should has been were will just when
after than then that these those also because about there here what where
one two get got buy bought purchase purchased product item amazon order
ordered arrived came work works working use used using really only even
still much more most some all can cannot didn did does don doesn won isn
wasn aren too out off now day days week weeks month months year years time
first second good great nice love loved like liked well fine ok okay
""".split())


def tokens(text: str) -> list[str]:
    return [t for t in WORD.findall(text.lower()) if t not in STOP]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv")
    ap.add_argument("--min-reviews", type=int, default=3)
    ap.add_argument("--neg-threshold", type=float, default=40.0)
    ap.add_argument("--top-terms", type=int, default=8)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    prods: dict[str, dict] = {}
    neg_text = defaultdict(list)
    pos_text = defaultdict(list)
    for line in Path(args.tsv).read_text(errors="replace").splitlines():
        f = line.split("\t")
        if len(f) < 9:
            continue
        pid, url_key, name, price, rating, n_rev, rev_rating, title, detail = f[:9]
        p = prods.setdefault(pid, {
            "product_id": int(pid), "url_key": url_key, "name": name,
            "price": float(price) if price else None,
            "rating_pct": float(rating) if rating else None,
            "n_reviews": int(n_rev or 0), "n_neg": 0, "n_rated": 0})
        if not rev_rating:
            continue
        rr = float(rev_rating)
        p["n_rated"] += 1
        body = f"{title} {detail}"
        if rr <= args.neg_threshold:
            p["n_neg"] += 1
            neg_text[pid].append(body)
        elif rr >= 80:
            pos_text[pid].append(body)

    out = []
    for pid, p in prods.items():
        if p["n_reviews"] < args.min_reviews:
            continue
        name_toks = set(tokens(p["name"]))

        def term_counts(texts: list[str]) -> list[tuple[str, int]]:
            c: Counter = Counter()
            for t in texts:
                ts = [x for x in tokens(t) if x not in name_toks]
                c.update(ts)
                c.update(f"{a} {b}" for a, b in zip(ts, ts[1:]))
            return [(t, n) for t, n in c.most_common(args.top_terms * 3)
                    if n >= 2][:args.top_terms]

        p["pct_negative"] = round(100 * p["n_neg"] / p["n_rated"], 1) if p["n_rated"] else None
        p["complaint_terms"] = term_counts(neg_text.get(pid, []))
        p["praise_terms"] = term_counts(pos_text.get(pid, []))
        out.append(p)

    out.sort(key=lambda p: -(p["n_reviews"] or 0))
    doc = {"source": args.tsv, "min_reviews": args.min_reviews,
           "neg_threshold_pct": args.neg_threshold,
           "n_products": len(out), "products": out}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        print(f"wrote {args.out} ({len(out)} products)")
    else:
        for p in out[:10]:
            print(f"{p['name'][:50]:50s} rating={p['rating_pct']} "
                  f"n={p['n_reviews']} neg%={p['pct_negative']} "
                  f"complaints={[t for t, _ in p['complaint_terms'][:4]]}")
    return 0


if __name__ == "__main__":
    sys_exit = main()
    raise SystemExit(sys_exit)
