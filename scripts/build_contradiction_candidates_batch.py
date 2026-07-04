#!/usr/bin/env python3
"""Batch-drive build_gold_contradictions across the 13 tri-source clusters.

Adjudication economy: tasks in one cluster share products and anchor
articles, so per-task candidate files would hand the human adjudicator the
same conflict up to 8 times. This driver therefore builds ONE candidate set
per cluster (pseudo task id ``cluster_<name>``) and records which task ids
it applies to; promotion later distributes adjudicated gold to every task
whose relevant set holds the product.

Inputs:
  --products-tsv   box-side dump: entity_id \t cats \t url_key \t name \t
                   description  (mysql -N -B escaping: \\n \\t \\\\, literal
                   NULL for null fields)
  --wiki-facts     scripts/extract_wiki_numeric_facts.py output
  --clusters       data/golden/tri_source_clusters.json
  --tasks-dir      v2 task JSONs (domain field -> cluster mapping)

Curation meta-rule (the only filtering this driver adds on top of the
builder): an auto-extracted wiki reference whose value is too LOW is not a
technology ceiling and floods the human with junk; any single reference
that flags more than --max-ref-flag-rate of the cluster's extracted claims
of its kind (and at least --min-ref-flags of them) is dropped WHOLE, and
the drop is recorded in the batch report. References are never edited,
only kept or dropped; errors in the too-high direction are already
conservative (they suppress candidates).

Outputs (per cluster, under data/golden/contradictions/):
  cluster_<name>.candidates.json
  cluster_<name>.adjudication.template.json
plus BATCH_REPORT.json with counts, dropped references, and task mapping.
Nothing this driver writes is gold (builder honesty contract unchanged).
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "golden" / "contradictions"

_spec = importlib.util.spec_from_file_location(
    "build_gold_contradictions", ROOT / "scripts" / "build_gold_contradictions.py")
_bgc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _bgc  # dataclass decorators need the module visible
_spec.loader.exec_module(_bgc)


# ---------------------------------------------------------------------------
# mysql -B decoding and HTML stripping
# ---------------------------------------------------------------------------

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


_TAG_RE = re.compile(r"<[^>]+>")
_STYLE_RE = re.compile(r"<(style|script)\b[^>]*>.*?</\1>", re.S | re.I)


def strip_html(text: str) -> str:
    text = _STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def load_products(tsv_path: Path) -> list[dict]:
    """Parse the box dump into product dicts with sandbox-canonical URLs."""
    products = []
    for line in tsv_path.read_text(errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) != 5:
            continue
        _entity_id, cats, url_key, name, description = parts
        url_key = mysql_unescape(url_key)
        if not url_key or url_key == "NULL":
            continue  # not citable without a content URL
        name = mysql_unescape(name)
        description = mysql_unescape(description)
        products.append({
            "url": f"http://localhost:7770/{url_key}.html",
            "name": "" if name == "NULL" else name,
            "description": "" if description == "NULL"
            else strip_html(description),
            "category_ids": [int(x) for x in cats.split(",") if x.strip().isdigit()],
        })
    return products


# ---------------------------------------------------------------------------
# Cluster assignment and task mapping
# ---------------------------------------------------------------------------

def assign_cluster_products(products: list[dict], cluster: dict) -> list[dict]:
    cat_ids = set(cluster["category_ids"])
    kw = (cluster.get("keyword_filter") or "").lower()
    out = []
    for p in products:
        if not cat_ids.intersection(p["category_ids"]):
            continue
        if kw and kw not in f"{p['name']} {p['description']}".lower():
            continue
        out.append(p)
    return out


def load_task_mapping(tasks_dir: Path) -> dict[str, list[str]]:
    """cluster name -> sorted v2 task ids (task JSON `domain` field)."""
    mapping: dict[str, list[str]] = {}
    for f in sorted(tasks_dir.glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        if d.get("task_version") != 2 or "task_id" not in d:
            continue
        dom = d.get("domain")
        if dom:
            mapping.setdefault(dom, []).append(d["task_id"])
    return {k: sorted(v) for k, v in mapping.items()}


# ---------------------------------------------------------------------------
# Reference curation (flag-rate rule)
# ---------------------------------------------------------------------------

def curate_references(doc: dict, max_rate: float, min_flags: int) -> list[dict]:
    """Drop whole references that flag implausibly many claims of their kind.

    Mutates doc["candidates"]; returns the drop records for the report."""
    claims_per_kind: dict[str, int] = {}
    for c in doc["extracted_claims"]:
        claims_per_kind[c["kind"]] = claims_per_kind.get(c["kind"], 0) + 1
    per_ref: dict[tuple, int] = {}
    for c in doc["candidates"]:
        key = (c["reference_topic"], c["kind"], c["reference_value"])
        per_ref[key] = per_ref.get(key, 0) + 1

    dropped = []
    drop_keys = set()
    for (topic, kind, ref_value), n_flags in per_ref.items():
        n_claims = max(1, claims_per_kind.get(kind, 0))
        rate = n_flags / n_claims
        if n_flags >= min_flags and rate > max_rate:
            drop_keys.add((topic, kind, ref_value))
            dropped.append({
                "reference_topic": topic, "kind": kind,
                "reference_value": ref_value,
                "n_flags": n_flags, "n_claims_of_kind": n_claims,
                "flag_rate": round(rate, 3),
                "reason": "flag_rate_exceeds_ceiling_plausibility "
                          f"(> {max_rate:.0%} of {kind} claims): the "
                          "auto-extracted value is presumptively not a "
                          "technology ceiling",
            })
    if drop_keys:
        doc["candidates"] = [
            c for c in doc["candidates"]
            if (c["reference_topic"], c["kind"], c["reference_value"])
            not in drop_keys]
        # candidate ids stay as assigned (gaps are fine; ids must not be
        # renumbered once a human may have seen them)
        doc["n_candidates"] = len(doc["candidates"])
        doc["curation_dropped_references"] = dropped
    return dropped


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--products-tsv",
                     help="full box dump (extract claims locally)")
    src.add_argument("--box-claims",
                     help="scripts/box_extract_claims.py output (claims "
                          "pre-extracted on the corpus host; slow-tunnel "
                          "mode, same extraction code)")
    ap.add_argument("--wiki-facts", default=str(
        DEFAULT_OUT / "wiki_numeric_facts.json"))
    ap.add_argument("--clusters", default=str(
        ROOT / "data" / "golden" / "tri_source_clusters.json"))
    ap.add_argument("--tasks-dir", default=str(
        ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--max-ref-flag-rate", type=float, default=0.2)
    ap.add_argument("--min-ref-flags", type=int, default=8)
    args = ap.parse_args()

    box_doc = None
    if args.box_claims:
        box_doc = json.loads(Path(args.box_claims).read_text())
        products = box_doc["products"]  # claim-carrying only, no desc text
    else:
        products = load_products(Path(args.products_tsv))
    wiki_doc = json.loads(Path(args.wiki_facts).read_text())
    facts_by_topic: dict[str, list[dict]] = {}
    for fact in wiki_doc["facts"]:
        facts_by_topic.setdefault(fact["topic"], []).append(fact)
    clusters = json.loads(Path(args.clusters).read_text())["clusters"]
    task_map = load_task_mapping(Path(args.tasks_dir))
    out_dir = Path(args.out_dir)

    report = {
        "generated_by": "scripts/build_contradiction_candidates_batch.py",
        "inputs": {
            "products_tsv_rows": len(products),
            "wiki_facts": wiki_doc["n_facts"],
            "wiki_articles": wiki_doc["n_articles"],
        },
        "curation_rule": {
            "max_ref_flag_rate": args.max_ref_flag_rate,
            "min_ref_flags": args.min_ref_flags,
        },
        "clusters": {},
    }

    total_candidates = 0
    for name, cluster in clusters.items():
        claims = None
        if box_doc is not None:
            cluster_products = [p for p in products
                                if name in p.get("clusters", [])]
            claims = [_bgc.Claim(product_url=p["url"],
                                 product_name=p["name"],
                                 kind=c["kind"], unit=c["unit"],
                                 value=c["value"], snippet=c["snippet"])
                      for p in cluster_products for c in p["claims"]]
        else:
            cluster_products = assign_cluster_products(products, cluster)
        cluster_facts = [f for t in cluster.get("wiki_topics", [])
                         for f in facts_by_topic.get(t, [])]
        pseudo_id = f"cluster_{name}"
        doc = _bgc.build_candidates(pseudo_id, cluster_products, cluster_facts,
                                    claims=claims)
        if box_doc is not None:
            # products list holds only claim-carrying items; the honest scan
            # count is the box-side census
            doc["n_products_scanned"] = box_doc["census"].get(name, 0)
        dropped = curate_references(
            doc, args.max_ref_flag_rate, args.min_ref_flags)
        doc["cluster"] = name
        doc["applies_to_tasks"] = task_map.get(name, [])
        cand_path, adj_path = _bgc.write_outputs(out_dir, doc)
        total_candidates += doc["n_candidates"]
        report["clusters"][name] = {
            "n_products": len(cluster_products),
            "n_wiki_facts": len(cluster_facts),
            "n_claims_extracted": doc["n_claims_extracted"],
            "n_candidates": doc["n_candidates"],
            "n_dropped_references": len(dropped),
            "dropped_references": dropped,
            "applies_to_tasks": doc["applies_to_tasks"],
            "candidates_file": cand_path.name,
            "adjudication_template": adj_path.name,
        }
        print(f"{name}: {len(cluster_products)} products, "
              f"{len(cluster_facts)} refs, "
              f"{doc['n_claims_extracted']} claims -> "
              f"{doc['n_candidates']} candidates"
              + (f" ({len(dropped)} refs dropped)" if dropped else ""))

    report["total_candidates"] = total_candidates
    report_path = out_dir / "BATCH_REPORT.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False)
                           + "\n")
    print(f"\ntotal: {total_candidates} candidates across "
          f"{len(clusters)} clusters (0 gold, by design)")
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
