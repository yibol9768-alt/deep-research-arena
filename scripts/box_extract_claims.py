#!/usr/bin/env python3
"""Corpus-host half of the contradiction-candidate pipeline.

Runs ON the sandbox box, next to the cleaned product dump, so only the
sparse claim set travels over the (slow) tunnel instead of the full
marketing text. Uses the SAME extract_claims / topic_anchored code as the
local builder: ship scripts/build_gold_contradictions.py alongside this
file and both halves stay in lockstep.

Inputs (paths given as args):
  products_clean.tsv   entity_id \t cats \t url_key \t name \t description
                       (mysql -N -B escaping, description already
                       HTML-stripped)
  tri_source_clusters.json  cluster definitions (category_ids,
                       keyword_filter, wiki_topics)

Output JSON:
  {"census": {cluster: n_products_assigned},
   "n_products_total": N,
   "products": [{url, name, category_ids, clusters, anchored_topics,
                 claims: [{kind, unit, value, snippet}]}]}
Only claim-carrying products are listed; anchored_topics is precomputed
here (full text available) so the local half never needs the description.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location(
    "build_gold_contradictions", HERE / "build_gold_contradictions.py")
_bgc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _bgc
_spec.loader.exec_module(_bgc)

_MYSQL_UNESCAPE = {"n": "\n", "t": "\t", "0": "\0", "\\": "\\"}


def mysql_unescape(field: str) -> str:
    out, i, n = [], 0, len(field)
    while i < n:
        c = field[i]
        if c == "\\" and i + 1 < n:
            out.append(_MYSQL_UNESCAPE.get(field[i + 1], field[i + 1]))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--products-tsv", required=True)
    ap.add_argument("--clusters", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    clusters = json.loads(Path(args.clusters).read_text())["clusters"]
    all_topics = sorted({t for c in clusters.values()
                         for t in c.get("wiki_topics", [])})

    census = {name: 0 for name in clusters}
    products_out = []
    n_total = 0
    for line in open(args.products_tsv, errors="replace"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 5:
            continue
        _eid, cats_s, url_key, name, description = parts
        url_key = mysql_unescape(url_key)
        if not url_key or url_key == "NULL":
            continue
        name = "" if name == "NULL" else mysql_unescape(name)
        description = "" if description == "NULL" else mysql_unescape(description)
        n_total += 1
        cats = [int(x) for x in cats_s.split(",") if x.strip().isdigit()]
        text_lower = f"{name} {description}".lower()
        assigned = []
        for cname, c in clusters.items():
            if not set(c["category_ids"]).intersection(cats):
                continue
            kw = (c.get("keyword_filter") or "").lower()
            if kw and kw not in text_lower:
                continue
            census[cname] += 1
            assigned.append(cname)
        if not assigned:
            continue
        product = {"url": f"http://localhost:7770/{url_key}.html",
                   "name": name, "description": description}
        claims = _bgc.extract_claims(product)
        if not claims:
            continue
        anchored = [t for t in all_topics if _bgc.topic_anchored(t, product)]
        products_out.append({
            "url": product["url"],
            "name": name,
            "category_ids": cats,
            "clusters": assigned,
            "anchored_topics": anchored,
            "claims": [{"kind": c.kind, "unit": c.unit, "value": c.value,
                        "snippet": c.snippet} for c in claims],
        })

    doc = {"generated_by": "scripts/box_extract_claims.py",
           "census": census, "n_products_total": n_total,
           "n_claim_products": len(products_out),
           "products": products_out}
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False) + "\n")
    n_claims = sum(len(p["claims"]) for p in products_out)
    print(f"{n_total} products -> {len(products_out)} claim-carrying, "
          f"{n_claims} claims")
    print("census:", json.dumps(census))
    return 0


if __name__ == "__main__":
    sys.exit(main())
