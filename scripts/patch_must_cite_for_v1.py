#!/usr/bin/env python3
"""Patch must_cite_urls in existing deep goldens for v1 intent shift.

Tasks 0003/0004/0006/0007/0008/0009/0010 had their golden scraped under
template-clone Recommendation intent. V1 design (configs/deep_topics/
V1_TASK_DESIGN_GRID.md) shifted them to Comparison / Debunking / Causal /
Timeline. Most wiki articles needed by the new intent ARE already in the
existing golden's expected_pool_urls (because the original yaml had a
broad wiki_extra list), but they're tagged as low-weight pool entries
rather than must_cite.

This script:
  - reads `data/golden/deep/dr_cross_deep_<NN>.json`
  - for each task, takes a v1-mandatory wiki title list
  - constructs `http://localhost:8090/content/wikipedia_en_all_nopic/A/<slug>`
    URLs (Kiwix nopic-zim slug format)
  - either promotes a matching pool entry to must_cite (if found) or
    appends a new must_cite entry with weight=1.0
  - writes back the golden, preserves existing must_cite entries

Run on Mac:
    python3 scripts/patch_must_cite_for_v1.py
    python3 scripts/patch_must_cite_for_v1.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "data" / "golden" / "deep"
WIKI_BASE = "http://localhost:8090/content/wikipedia_en_all_nopic/A"


# Kiwix nopic-zim slug rules (matches build_deep_golden.py _wiki_slug):
# - drop parenthesised qualifiers: "Thread (network protocol)" -> "Thread_(network_protocol)"
#   actually kiwix keeps them, with underscored spaces
# - replace spaces with underscores
def slugify(title: str) -> str:
    # replace spaces -> underscore
    s = re.sub(r"\s+", "_", title.strip())
    return s


def build_url(title: str) -> str:
    return f"{WIKI_BASE}/{slugify(title)}"


# v1 mandatory wiki titles per task (from V1_TASK_DESIGN_GRID.md)
V1_MANDATORY = {
    "dr_cross_deep_0003": [
        # Comparison: home fitness
        "Strength training", "Hypertrophy", "Aerobic exercise", "Calisthenics",
        "Resistance band", "Olympic weightlifting", "Powerlifting",
        "Range of motion", "Progressive overload",
    ],
    "dr_cross_deep_0004": [
        # Comparison: photography starter
        "Mirrorless camera", "Digital single-lens reflex camera", "Image sensor format",
        "Crop factor", "Aperture", "Shutter speed", "ISO", "Depth of field",
        "Bokeh", "Computational photography", "Exposure (photography)",
    ],
    "dr_cross_deep_0006": [
        # Debunking: cookware safety
        "Polytetrafluoroethylene", "Perfluorooctanoic acid", "Non-stick surface",
        "Cast-iron cookware", "Stainless steel", "Anodizing",
        "Aluminium toxicity", "Maillard reaction", "Heat capacity", "Thermal conductivity",
    ],
    "dr_cross_deep_0007": [
        # Debunking: dog supplies
        "Dog food", "Raw feeding", "Dilated cardiomyopathy", "Bisphenol A",
        "Theanine", "Dog anxiety", "Periodontal disease", "Plaque",
        "Veterinary medicine", "Salmonella",
    ],
    "dr_cross_deep_0008": [
        # Debunking: baby essentials
        "Sudden infant death syndrome", "Infant formula", "Breast milk",
        "Child safety seat", "Swaddling", "Sleep sack", "Colic",
        "Pacifier", "ISOFIX", "Breastfeeding",
    ],
    "dr_cross_deep_0009": [
        # Causal: EV winter
        "Lithium-ion battery", "Battery thermal management", "Heat pump",
        "Internal resistance", "Electrolyte", "Lithium plating",
        "Regenerative braking", "Cabin heater", "Specific heat capacity",
        "Arrhenius equation",
    ],
    "dr_cross_deep_0010": [
        # Timeline: mechanical keyboard
        "Buckling spring", "Cherry (keyboards)", "Hall effect", "Optical switch",
        "Computer keyboard", "Tactile bump", "Keycap", "Membrane keyboard",
        "Scissor mechanism", "Topre",
    ],
}


def patch_golden(path: Path, mandatory_titles: list[str], dry_run: bool) -> dict:
    """Add v1 mandatory wiki entries to must_cite. Returns stats."""
    g = json.loads(path.read_text())
    must_cite = g.setdefault("must_cite_urls", [])
    pool = g.setdefault("expected_pool_urls", [])
    must_urls = {e["url"]: e for e in must_cite}
    pool_urls = {e["url"]: e for e in pool}

    promoted = 0
    appended = 0
    already_must = 0

    for title in mandatory_titles:
        target_url = build_url(title)
        if target_url in must_urls:
            already_must += 1
            continue
        if target_url in pool_urls:
            # promote: copy entry from pool to must_cite, set weight=1.0
            entry = dict(pool_urls[target_url])
            entry["weight"] = 1.0
            entry["why"] = f"V1 mandatory wiki for new intent ({path.stem})"
            must_cite.append(entry)
            promoted += 1
        else:
            # append fresh
            must_cite.append({
                "url": target_url,
                "category": "wiki_definition",
                "weight": 1.0,
                "why": f"V1 mandatory wiki for new intent ({path.stem})",
            })
            appended += 1

    # Update metadata.summary if present
    if "metadata" in g:
        summary = g["metadata"].setdefault("summary", {})
        summary["n_must_cite"] = len(must_cite)
        # recompute domain breakdown
        from urllib.parse import urlparse
        breakdown = {}
        for e in must_cite:
            host = urlparse(e["url"]).netloc
            breakdown[host] = breakdown.get(host, 0) + 1
        summary["must_cite_domain_breakdown"] = breakdown
        summary["v1_patched"] = True

    if not dry_run:
        path.write_text(json.dumps(g, indent=2, ensure_ascii=False) + "\n")

    return {
        "task_id": path.stem,
        "v1_mandatory_total": len(mandatory_titles),
        "already_must": already_must,
        "promoted_from_pool": promoted,
        "appended_new": appended,
        "n_must_cite_after": len(must_cite),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not GOLDEN_DIR.exists():
        sys.exit(f"missing {GOLDEN_DIR}")

    print(f"{'task':<22}  total  already  promoted  appended  must_cite_after")
    print("-" * 75)
    for task_id, titles in V1_MANDATORY.items():
        path = GOLDEN_DIR / f"{task_id}.json"
        if not path.exists():
            print(f"{task_id:<22}  SKIP (no golden file)")
            continue
        s = patch_golden(path, titles, args.dry_run)
        tag = "[DRY] " if args.dry_run else ""
        print(f"{tag}{task_id:<22}  {s['v1_mandatory_total']:>5}  "
              f"{s['already_must']:>7}  {s['promoted_from_pool']:>8}  "
              f"{s['appended_new']:>8}  {s['n_must_cite_after']:>15}")


if __name__ == "__main__":
    main()
