#!/usr/bin/env python3
"""Round-2 contradiction mining: INTRA-PAGE numeric self-contradictions.

Round 1 (marketing number vs frozen-wiki ceiling) ended with an honest
zero: the user rejected all 3 auto-extracted ceiling references. This
round needs no external reference at all: a product page that states two
incompatible values for the SAME attribute (Bluetooth 5.0 in one sentence,
4.2 in another) contradicts itself, which is decidable from the frozen
corpus alone.

Input: the box-side claim extraction (scripts/box_extract_claims.py output;
a gzipped snapshot is kept at data/golden/contradictions/
box_claims_snapshot.json.gz for reproducibility).

Noise model (each killed by a specific filter, all verified on the corpus):
  - flattened comparison tables ("Bluetooth Version 4.2 5.0 5.1 5.0" is a
    product-family spec table, not a self-contradiction) -> drop any claim
    whose snippet window contains >= 3 values of the same kind;
  - item weight vs package/battery weight -> context exclusions;
  - brightness modes (high/low/flash) and competitor comparisons -> ditto;
  - charger input/output mAh, external power banks -> ditto;
  - "Bluetooth 5.2 is faster than 5.0" marketing comparisons -> 'than';
  - bundles/multi-packs (two speakers may legitimately differ) -> name gate.

The builder NEVER emits gold (honesty contract identical to round 1):
every candidate carries status candidate_needs_human_adjudication; use
--promote with a human-filled adjudication file. There is no reference
stage this round; adjudication is per-entry only.

Usage:
  python3 scripts/build_intra_page_contradictions.py --claims <box_claims.json[.gz]>
  python3 scripts/build_intra_page_contradictions.py --promote <adjudication.json>
  python3 scripts/build_intra_page_contradictions.py --demo
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "golden" / "contradictions"
DEFAULT_CLAIMS = OUT_DIR / "box_claims_snapshot.json.gz"
TASK_ID = "intra_page"
STATUS_CANDIDATE = "candidate_needs_human_adjudication"
STATUS_GOLD = "gold_adjudicated"
ALLOWED_VERDICTS = ["SUPPORTED_CONFLICT", "NOT_A_CONFLICT", "NUANCE"]

BUNDLE_NAME = re.compile(r"\b(bundle|set of|\d+\s*(?:pcs|pack)\b|kit\b|\bw/|\+)",
                         re.I)

# how many same-kind value mentions inside one snippet window mark it as a
# flattened spec-comparison table (variants side by side, not a conflict)
TABLE_THRESHOLD = 3

KIND_VALUE_RX = {
    "bluetooth_version": re.compile(r"\b\d\.\d\b"),
    "battery_hours": re.compile(r"\b\d+(?:\.\d+)?\s*(?:hours?|hrs?|hour)\b", re.I),
    "battery_mah": re.compile(r"\b\d[\d,]*\s*mah\b", re.I),
    "weight_g": re.compile(r"\b\d[\d,]*(?:\.\d+)?\s*(?:g|grams?|oz)\b", re.I),
    "lumens": re.compile(r"\b\d[\d,]*\s*(?:lm|lumens?)\b", re.I),
    "impedance_ohm": re.compile(r"\b\d+(?:\.\d+)?\s*ohms?\b", re.I),
    "driver_mm": re.compile(r"\b\d+(?:\.\d+)?\s*mm\b", re.I),
}

RULES = {
    # kind: (min_ratio, exclude_rx, require_rx)
    "bluetooth_version": (1.0001, r"\bthan\b|compar", None),
    "battery_hours": (1.4, r"case|standby|talk|charg|per charge|vs\b|others",
                      r"play|battery life|listening|working|music"),
    "battery_mah": (1.4, r"replace|compatible|charger|input|output|"
                         r"power bank|for |fits", None),
    "weight_g": (1.6, r"package|packing|shipping|battery weight|"
                      r"cable|strap|case", r"weight"),
    "lumens": (1.6, r"dimm|mode|setting|adjust|up to|high|low|flash|"
                    r"vs\b|others|watt", None),
    "impedance_ohm": (1.2, r"\bmin\b|\bmax\b|rated from|/km|awg|resistance",
                      None),
    "driver_mm": (1.2, r"\bhf\b|\blf\b|tweeter|woofer", None),
}


def looks_like_table(snippet: str, kind: str) -> bool:
    rx = KIND_VALUE_RX.get(kind)
    return bool(rx) and len(rx.findall(snippet)) >= TABLE_THRESHOLD


def mine(claims_doc: dict) -> dict:
    candidates = []
    dropped = defaultdict(int)
    for p in claims_doc["products"]:
        if BUNDLE_NAME.search(p["name"]):
            dropped["bundle_name"] += 1
            continue
        by_kind = defaultdict(lambda: defaultdict(list))
        for c in p["claims"]:
            kind = c["kind"]
            if kind not in RULES:
                continue
            min_ratio, excl, req = RULES[kind]
            snip = c["snippet"]
            if looks_like_table(snip, kind):
                dropped[f"{kind}:table_row"] += 1
                continue
            if excl and re.search(excl, snip, re.I):
                dropped[f"{kind}:context_excluded"] += 1
                continue
            if req and not re.search(req, snip, re.I):
                dropped[f"{kind}:context_missing"] += 1
                continue
            by_kind[kind][c["value"]].append(c)
        for kind, vals in by_kind.items():
            if len(vals) < 2:
                continue
            vs = sorted(vals)
            min_ratio = RULES[kind][0]
            if vs[0] <= 0 or vs[-1] / vs[0] < min_ratio:
                dropped[f"{kind}:ratio_below_threshold"] += 1
                continue
            candidates.append({
                "candidate_id": "",  # numbered after the sort below
                "task_id": TASK_ID,
                "kind": kind,
                "unit": vals[vs[0]][0]["unit"],
                "product_url": p["url"],
                "product_name": p["name"],
                "clusters": p.get("clusters", []),
                "values": [{"value": v, "snippet": vals[v][0]["snippet"]}
                           for v in vs],
                "spread_ratio": round(vs[-1] / vs[0], 2),
                "status": STATUS_CANDIDATE,
            })
    # stable ordering: cleanest kinds first, then by product name
    kind_order = {k: i for i, k in enumerate(RULES)}
    candidates.sort(key=lambda c: (kind_order[c["kind"]], c["product_name"]))
    seq = defaultdict(int)
    for c in candidates:
        seq[c["kind"]] += 1
        c["candidate_id"] = f"{TASK_ID}-{c['kind']}-{seq[c['kind']]:04d}"
    return {
        "task_id": TASK_ID,
        "builder": "scripts/build_intra_page_contradictions.py",
        "restriction": "intra-page same-attribute numeric conflicts only",
        "auto_gold": False,
        "note": ("machine-mined candidates; every entry requires human "
                 "adjudication before it can enter any gold set"),
        "n_products_scanned": len(claims_doc["products"]),
        "n_candidates": len(candidates),
        "dropped": dict(sorted(dropped.items())),
        "candidates": candidates,
    }


def adjudication_template(doc: dict) -> dict:
    return {
        "task_id": doc["task_id"],
        "instructions": (
            "For every entry decide whether the page really contradicts "
            "itself on this attribute. SUPPORTED_CONFLICT = the two numbers "
            "describe the SAME thing and cannot both be true; "
            "NOT_A_CONFLICT = they describe different things (variant table, "
            "different component, with/without charging case, item vs "
            "package) or one is an extraction error; NUANCE = real tension "
            "but not decidable (never becomes gold). Fill verdict, "
            "adjudicator, note for every entry; partial files are refused."),
        "allowed_verdicts": ALLOWED_VERDICTS,
        "entries": [
            {"candidate_id": c["candidate_id"], "verdict": "",
             "adjudicator": "", "note": ""}
            for c in doc["candidates"]
        ],
    }


def load_claims(path: Path) -> dict:
    if str(path).endswith(".gz"):
        with gzip.open(path, "rt") as fh:
            return json.load(fh)
    return json.loads(path.read_text())


def promote(adjudication_path: Path, out_dir: Path) -> int:
    cand_path = out_dir / f"{TASK_ID}.candidates.json"
    if not cand_path.exists():
        print(f"error: {cand_path} not found (run the miner first)")
        return 1
    cand_doc = json.loads(cand_path.read_text())
    by_id = {c["candidate_id"]: c for c in cand_doc["candidates"]}
    adj = json.loads(adjudication_path.read_text())
    gold, problems, seen = [], [], set()
    counts = {v: 0 for v in ALLOWED_VERDICTS}
    counts["unadjudicated"] = 0
    for entry in adj.get("entries", []):
        cid = entry.get("candidate_id", "")
        if cid in seen:
            problems.append(f"duplicate candidate_id {cid!r}")
            continue
        seen.add(cid)
        if cid not in by_id:
            problems.append(f"unknown candidate_id {cid!r}")
            continue
        verdict = (entry.get("verdict") or "").strip()
        if not verdict:
            counts["unadjudicated"] += 1
            continue
        if verdict not in ALLOWED_VERDICTS:
            problems.append(f"{cid}: invalid verdict {verdict!r}")
            continue
        counts[verdict] += 1
        if verdict == "SUPPORTED_CONFLICT":
            if not (entry.get("adjudicator") or "").strip():
                problems.append(f"{cid}: SUPPORTED_CONFLICT without adjudicator")
                continue
            item = dict(by_id[cid])
            item["status"] = STATUS_GOLD
            item["verdict"] = verdict
            item["adjudicator"] = entry["adjudicator"].strip()
            item["note"] = entry.get("note", "")
            gold.append(item)
    missing = sorted(set(by_id) - seen)
    if missing:
        problems.append(f"adjudication file misses candidates: {missing[:5]}"
                        f"{'...' if len(missing) > 5 else ''}")
    if counts["unadjudicated"]:
        problems.append(f"{counts['unadjudicated']} entries still empty "
                        "(adjudication must be complete)")
    if problems:
        print("refusing to promote (honesty contract):")
        for p in problems:
            print(f"  - {p}")
        return 1
    gold_doc = {
        "task_id": TASK_ID,
        "source_candidates": str(cand_path),
        "adjudication_file": str(adjudication_path),
        "counts": counts,
        "gold_contradictions": gold,
    }
    gold_path = out_dir / f"{TASK_ID}.gold.json"
    gold_path.write_text(json.dumps(gold_doc, indent=2, ensure_ascii=False)
                         + "\n")
    print(f"promoted {len(gold)} SUPPORTED_CONFLICT of "
          f"{len(by_id)} candidates -> {gold_path}")
    return 0


def run_demo() -> int:
    products = [
        {"url": "http://x/a.html", "name": "Acme Wireless Headphones",
         "category_ids": [], "clusters": ["headphones_audio"], "claims": [
            {"kind": "bluetooth_version", "unit": "", "value": 4.2,
             "snippet": "with the Bluetooth 4.2 technology, built-in mic"},
            {"kind": "bluetooth_version", "unit": "", "value": 5.0,
             "snippet": "pairs instantly thanks to Bluetooth 5.0 chipset"}]},
        {"url": "http://x/b.html", "name": "Acme Family Table",
         "category_ids": [], "clusters": [], "claims": [
            {"kind": "bluetooth_version", "unit": "", "value": 4.2,
             "snippet": "Bluetooth Version 4.2 5.0 5.1 5.0 comparison"},
            {"kind": "bluetooth_version", "unit": "", "value": 5.0,
             "snippet": "Bluetooth Version 4.2 5.0 5.1 5.0 comparison"}]},
        {"url": "http://x/c.html", "name": "Acme Lamp Bundle",
         "category_ids": [], "clusters": [], "claims": [
            {"kind": "lumens", "unit": "lm", "value": 300.0,
             "snippet": "luminous flux 300 lumens sconce"},
            {"kind": "lumens", "unit": "lm", "value": 900.0,
             "snippet": "bright 900 lumens output"}]},
    ]
    doc = mine({"products": products})
    checks = []
    ids = [c["candidate_id"] for c in doc["candidates"]]
    checks.append(("real conflict mined", ids == ["intra_page-bluetooth_version-0001"]))
    checks.append(("table row dropped", doc["dropped"].get(
        "bluetooth_version:table_row", 0) == 2))
    checks.append(("bundle name gated", doc["dropped"].get("bundle_name") == 1))
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        (out / f"{TASK_ID}.candidates.json").write_text(json.dumps(doc))
        tpl = adjudication_template(doc)
        tpl["entries"][0].update(verdict="SUPPORTED_CONFLICT",
                                 adjudicator="demo", note="ok")
        adj = out / "adj.json"
        adj.write_text(json.dumps(tpl))
        checks.append(("promote accepts complete file",
                       promote(adj, out) == 0))
        gold = json.loads((out / f"{TASK_ID}.gold.json").read_text())
        checks.append(("gold has 1 entry",
                       len(gold["gold_contradictions"]) == 1))
        tpl["entries"][0]["verdict"] = ""
        adj.write_text(json.dumps(tpl))
        checks.append(("promote refuses empty verdict",
                       promote(adj, out) == 1))
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok &= passed
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--claims", default=str(DEFAULT_CLAIMS))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--promote", help="human-filled adjudication JSON")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    if args.demo:
        return run_demo()
    out_dir = Path(args.out_dir)
    if args.promote:
        return promote(Path(args.promote), out_dir)
    doc = mine(load_claims(Path(args.claims)))
    out_dir.mkdir(parents=True, exist_ok=True)
    cand = out_dir / f"{TASK_ID}.candidates.json"
    tpl = out_dir / f"{TASK_ID}.adjudication.template.json"
    cand.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    tpl.write_text(json.dumps(adjudication_template(doc), indent=2,
                              ensure_ascii=False) + "\n")
    print(f"{doc['n_candidates']} candidates -> {cand}")
    per = defaultdict(int)
    for c in doc["candidates"]:
        per[c["kind"]] += 1
    for k, n in per.items():
        print(f"  {k}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
