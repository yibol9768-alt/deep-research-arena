#!/usr/bin/env python3
"""Build the closed-world URL registry (registry findings section G).

In a frozen sandbox the set of legitimate content URLs is enumerable, so
"is this citation reachable?" becomes a set-membership query with zero HTTP
(src/eval/url_registry.py). This script builds that enumeration from THREE
plain-file inputs and writes data/golden/url_registry.json. It deliberately
performs NO ssh and NO docker: dump the inputs on the box, copy them over,
build locally, so the registry itself is a reviewable, versionable artifact.

Inputs
------
--products-tsv     one product per line: ``entity_id<TAB>url_key``
                   Box-side dump (run where docker reaches the container):
                     docker exec -i dr_sandbox_shopping mysql -u magentouser \
                       -pMyPassword -s -N magentodb -e "SELECT entity_id, value
                       FROM catalog_product_entity_varchar WHERE attribute_id=121
                       AND store_id=0" > products.tsv
                   Category url_keys may be appended to the same file if bare
                   category pages should count as citable content.

--submissions-tsv  one submission per line: ``id<TAB>canonical_forum``
                   Box-side dump:
                     docker exec -i dr_sandbox_forums psql -U postmill -At -F $'\t' \
                       -c "SELECT s.id, f.name FROM submissions s
                           JOIN forums f ON f.id = s.forum_id" > submissions.tsv

--wiki-list        one Kiwix article path (or bare article id) per line,
                   CASE PRESERVED (kiwix-serve is case-sensitive, G-F3).
                   v1 note: until a ZIM index dump exists, this list may be
                   derived from the HTTP cache's observed-200 kiwix URLs
                   (grep the cache for localhost:8090 entries with status 200).
                   That is a lower bound on the corpus, which is safe for the
                   numerator side but can under-credit unvisited articles;
                   replace with a full `zimdump list` enumeration when
                   available.

Usage
-----
  python3 scripts/build_url_registry.py \
      --products-tsv products.tsv \
      --submissions-tsv submissions.tsv \
      --wiki-list wiki_articles.txt \
      --out data/golden/url_registry.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval.url_registry import DEFAULT_HOSTS, DEFAULT_KIWIX_BOOK, UrlRegistry


def _read_lines(path: Path) -> list[str]:
    out = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n").rstrip("\r")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            out.append(line)
    return out


def parse_products(path: Path, stats: dict) -> list[str]:
    """``entity_id<TAB>url_key`` lines -> deduped url_key list."""
    seen: dict[str, str] = {}  # url_key -> entity_id (first wins)
    for i, line in enumerate(_read_lines(path), 1):
        parts = line.split("\t")
        if len(parts) < 2:
            stats["products_bad_lines"] += 1
            continue
        entity_id, url_key = parts[0].strip(), parts[1].strip()
        # Tolerate url_keys pasted with suffix/slashes/percent-encoding.
        url_key = unquote(url_key).strip("/")
        if url_key.lower().endswith(".html"):
            url_key = url_key[: -len(".html")]
        if not url_key or "://" in url_key:
            stats["products_bad_lines"] += 1
            continue
        if url_key in seen:
            stats["products_dupes"] += 1
            if seen[url_key] != entity_id:
                stats["products_dupe_conflicts"] += 1
            continue
        seen[url_key] = entity_id
    return sorted(seen)


def parse_submissions(path: Path, stats: dict) -> dict[str, str]:
    """``id<TAB>canonical_forum`` lines -> {id: forum}."""
    out: dict[str, str] = {}
    for line in _read_lines(path):
        parts = line.split("\t")
        if len(parts) < 2:
            stats["submissions_bad_lines"] += 1
            continue
        sub_id, forum = parts[0].strip(), parts[1].strip()
        if not sub_id.isdigit() or not forum:
            stats["submissions_bad_lines"] += 1
            continue
        prev = out.get(sub_id)
        if prev is not None:
            stats["submissions_dupes"] += 1
            if prev != forum:
                stats["submissions_conflicts"] += 1
                print(f"! submission {sub_id}: forum conflict "
                      f"{prev!r} vs {forum!r}, keeping first", file=sys.stderr)
            continue
        out[sub_id] = forum
    return out


def parse_wiki(path: Path, stats: dict) -> list[str]:
    """Article paths / URLs / bare ids -> deduped case-preserved id list.

    Accepts full URLs (http://localhost:8090/content/<book>/A/<id>), rooted
    paths (/A/<id>, /wiki/<id>, /content/<book>/A/<id>) and bare ids. Case is
    NEVER folded (G-F3); duplicates differing only in case are flagged so the
    corpus dump can be inspected (kiwix-serve treats them as distinct pages).
    """
    ids: list[str] = []
    exact: set[str] = set()
    ci_seen: set[str] = set()
    for line in _read_lines(path):
        s = line.strip()
        if "://" in s:
            s = urlparse(s).path
        article = None
        rooted = s if s.startswith("/") else "/" + s
        idx = rooted.rfind("/A/")
        if idx != -1:
            article = rooted[idx + 3:]
        else:
            idx = rooted.rfind("/wiki/")
            if idx != -1:
                article = rooted[idx + 6:]
            elif not s.startswith("/"):
                # Bare id line (may legitimately contain "/", e.g. AC/DC).
                article = s
        if article is None:
            stats["wiki_bad_lines"] += 1
            continue
        article = unquote(article).strip("/").split("#")[0].split("?")[0]
        article = article.replace(" ", "_")
        if not article:
            stats["wiki_bad_lines"] += 1
            continue
        if article in exact:
            stats["wiki_dupes"] += 1
            continue
        if article.lower() in ci_seen:
            stats["wiki_case_collisions"] += 1
            print(f"! wiki id case collision: {article!r}", file=sys.stderr)
        exact.add(article)
        ci_seen.add(article.lower())
        ids.append(article)
    return sorted(ids)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--products-tsv", required=True, type=Path,
                    help="entity_id<TAB>url_key per line")
    ap.add_argument("--submissions-tsv", required=True, type=Path,
                    help="id<TAB>canonical_forum per line")
    ap.add_argument("--wiki-list", required=True, type=Path,
                    help="one article path/id per line, case preserved")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "data" / "golden" / "url_registry.json")
    ap.add_argument("--kiwix-book", default=DEFAULT_KIWIX_BOOK)
    args = ap.parse_args()

    for p in (args.products_tsv, args.submissions_tsv, args.wiki_list):
        if not p.exists():
            print(f"! input not found: {p}", file=sys.stderr)
            return 2

    stats = {
        "products_bad_lines": 0, "products_dupes": 0, "products_dupe_conflicts": 0,
        "submissions_bad_lines": 0, "submissions_dupes": 0, "submissions_conflicts": 0,
        "wiki_bad_lines": 0, "wiki_dupes": 0, "wiki_case_collisions": 0,
    }
    products = parse_products(args.products_tsv, stats)
    submissions = parse_submissions(args.submissions_tsv, stats)
    wiki = parse_wiki(args.wiki_list, stats)

    if not products or not submissions or not wiki:
        print("! refusing to write a registry with an EMPTY section "
              f"(products={len(products)}, submissions={len(submissions)}, "
              f"wiki={len(wiki)}): an empty section silently classifies every "
              "citation of that source as fabricated", file=sys.stderr)
        return 2

    registry = {
        "version": 1,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hosts": DEFAULT_HOSTS,
        "kiwix_book": args.kiwix_book,
        "products": products,
        "submissions": submissions,
        "wiki": wiki,
        "stats": {
            "n_products": len(products),
            "n_submissions": len(submissions),
            "n_forums": len(set(submissions.values())),
            "n_wiki": len(wiki),
            **{k: v for k, v in stats.items() if v},
        },
    }

    # Self-check: the artifact must round-trip through UrlRegistry and answer
    # membership for one sample of each source before it is trusted on disk.
    reg = UrlRegistry.from_dict(registry)
    sample_checks = [
        (f"http://localhost:7770/{products[0]}.html", "product"),
        (next(f"http://localhost:9999/f/{f}/{i}" for i, f in submissions.items()),
         "submission"),
        (f"http://localhost:8090/content/{args.kiwix_book}/A/{wiki[0]}", "wiki"),
    ]
    for sample_url, label in sample_checks:
        res = reg.classify(sample_url)
        if res["in_corpus"] is not True:
            print(f"! self-check failed for {label}: {res}", file=sys.stderr)
            return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=1)
        f.write("\n")

    print(f"wrote {args.out}")
    print(f"  products    : {len(products):>7}  "
          f"(dupes dropped {stats['products_dupes']}, "
          f"bad lines {stats['products_bad_lines']})")
    print(f"  submissions : {len(submissions):>7}  "
          f"over {len(set(submissions.values()))} forums  "
          f"(dupes {stats['submissions_dupes']}, "
          f"conflicts {stats['submissions_conflicts']}, "
          f"bad lines {stats['submissions_bad_lines']})")
    print(f"  wiki        : {len(wiki):>7}  "
          f"(dupes {stats['wiki_dupes']}, "
          f"case collisions {stats['wiki_case_collisions']}, "
          f"bad lines {stats['wiki_bad_lines']})")
    print("  self-check  : product/submission/wiki membership OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
