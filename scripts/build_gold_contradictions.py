#!/usr/bin/env python3
"""Build CANDIDATE gold contradictions, restricted to numeric/spec conflicts.

Registry T4/T5 (paper_iclr/UNREASONABLE_PARTS_REGISTRY.md): the
gold_contradictions pillar is empty in every published golden, and soft
marketing-vs-review tension ("immersive noise cancelling" vs "ANC weak at
high frequencies") is a nuance, not a decidable contradiction. This builder
therefore handles ONLY the reliably decidable kind: a product's marketing
text claims a unit-typed number (battery hours, driver mm, Bluetooth
version, bitrate kbps, impedance ohm, weight g, ANC dB, lumens, mAh,
watts, megapixels, refresh Hz, color-temperature K) that conflicts with
a wiki/DB numeric reference for the same product or technology beyond a
typed tolerance.

Honesty contract:
  * every emitted item has status="candidate_needs_human_adjudication";
  * nothing this script writes is gold. Gold exists only after a human
    fills the adjudication file, and only verdict=SUPPORTED_CONFLICT
    entries are promoted (see data/golden/contradictions/README.md);
  * wiki references are treated as technology upper bounds (the maximum
    the frozen corpus supports). A claim at or below the reference is
    never flagged: older Bluetooth versions, smaller drivers, and shorter
    battery lives are legitimate, not contradictions;
  * prose-only marketing language with no extractable number is never
    flagged (that is a nuance for the subjective rubric, per T5).

Inputs (local files; no ssh, no DB connection):
  --products-json    [{"url", "name", "description"}, ...]
  --wiki-facts-json  [{"topic", "fact_text", "source_url",
                       "numeric_value", "unit"}, ...]

Outputs (under --out-dir, default data/golden/contradictions/):
  <task_id>.candidates.json             candidate conflicts, never auto-gold
  <task_id>.adjudication.template.json  one row per candidate for a human
                                        (candidate_id, verdict, adjudicator,
                                        note)

Modes:
  --demo      run the built-in fixture (3 fake products + 2 wiki facts) and
              check that the one true numeric conflict is caught and the
              nuance case is NOT flagged; prints only, unless --out-dir is
              given explicitly
  --promote   read a fully filled adjudication file and emit
              <task_id>.gold.json containing only SUPPORTED_CONFLICT entries

Usage:
  python3 scripts/build_gold_contradictions.py --task-id dr_cross_deep_0001 \
      --products-json products.json --wiki-facts-json wiki_facts.json
  python3 scripts/build_gold_contradictions.py --demo
  python3 scripts/build_gold_contradictions.py --task-id dr_cross_deep_0001 \
      --promote data/golden/contradictions/dr_cross_deep_0001.adjudication.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "golden" / "contradictions"

STATUS_CANDIDATE = "candidate_needs_human_adjudication"
STATUS_GOLD = "gold_supported_conflict"
ALLOWED_VERDICTS = ["SUPPORTED_CONFLICT", "NOT_A_CONFLICT", "NUANCE"]

_STOPWORDS = {"the", "and", "for", "with", "control", "system"}


# ---------------------------------------------------------------------------
# Typed quantity kinds (the ONLY contradiction surface this builder touches)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QuantityKind:
    """One unit-typed quantity we know how to extract and compare."""
    kind: str
    unit: str
    unit_aliases: tuple  # how a wiki fact's `unit` field may spell it
    rel_tolerance: float  # claim > ref * (1 + tol) => candidate conflict
    patterns: tuple  # regexes; group 1 captures the numeric value


KINDS = (
    QuantityKind(
        kind="battery_hours", unit="hours",
        unit_aliases=("hours", "hour", "hrs", "hr", "h"),
        rel_tolerance=0.15,
        patterns=(
            r"(?:battery(?:\s+life)?|playtime|play\s*time|playback|"
            r"listening(?:\s+time)?)\W{0,3}(?:(?:of|up\s+to|:|is|lasts?)\s*){0,3}"
            r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\b",
            r"(\d+(?:\.\d+)?)[\s-]*(?:hours?|hrs?)[\s-]+(?:of\s+)?"
            r"(?:battery|playtime|play\s*time|playback|listening)",
        ),
    ),
    QuantityKind(
        kind="driver_mm", unit="mm",
        unit_aliases=("mm", "millimeter", "millimetre"),
        rel_tolerance=0.10,
        patterns=(
            r"(\d+(?:\.\d+)?)\s*mm\s+(?:dynamic\s+|neodymium\s+)?drivers?\b",
            r"drivers?\W{0,3}(?:of|:)?\s*(\d+(?:\.\d+)?)\s*mm\b",
        ),
    ),
    QuantityKind(
        kind="bluetooth_version", unit="version",
        unit_aliases=("version", "bt_version", "bluetooth_version", "v"),
        rel_tolerance=0.0,  # the version ladder is exact; any value above
        # the latest released version is impossible
        patterns=(
            # a version is a DOTTED number ("Bluetooth 5.3") or explicitly
            # marked ("Bluetooth V5"); a bare integer after the word is a
            # model number, an inch size, a wattage, or a range in feet
            # (all observed in the corpus) and must not match
            r"bluetooth\s*(?:v|version\s*)?(\d\.\d)\b",
            r"bluetooth\s+(?:v|version)\s*(\d+(?:\.\d+)?)\b",
        ),
    ),
    QuantityKind(
        kind="bitrate_kbps", unit="kbps",
        unit_aliases=("kbps", "kbit/s", "kbits"),
        rel_tolerance=0.10,
        patterns=(
            r"(\d+(?:\.\d+)?)\s*kbps\b",
        ),
    ),
    QuantityKind(
        kind="impedance_ohm", unit="ohm",
        unit_aliases=("ohm", "ohms", "Ω"),
        rel_tolerance=0.15,
        patterns=(
            # "ohm" spelled out only: under IGNORECASE the Ω sign also
            # matches lowercase omega in chemistry prose (verified on the
            # frozen Nylon article), so the sign is not accepted
            r"(\d+(?:\.\d+)?)\s*ohms?\b",
        ),
    ),
    QuantityKind(
        kind="weight_g", unit="g",
        unit_aliases=("g", "gram", "grams"),
        rel_tolerance=0.15,
        patterns=(
            # context-required: a bare "10 g" (gold plating, sugar, ...)
            # must not become a weight claim
            r"(?:weighs?|weight\W{0,3}(?:of|:)?)\s*(\d+(?:\.\d+)?)\s*"
            r"(?:g|grams?)\b",
        ),
    ),
    QuantityKind(
        kind="anc_db", unit="dB",
        unit_aliases=("db", "dB", "decibel", "decibels"),
        rel_tolerance=0.10,
        patterns=(
            # bare "noise" is not enough context: "Signal Noise Ratio (SNR):
            # 120dB" is not an attenuation claim (observed in the corpus)
            r"(?:\banc\b|noise[\s-]+cancell\w*|cancell\w*|attenuat\w*|"
            r"noise[\s-]+reduc\w*)"
            r".{0,40}?(\d+(?:\.\d+)?)\s*dB\b",
            r"(\d+(?:\.\d+)?)\s*dB\b\s*(?:of\s+)?"
            r"(?:noise|anc|attenuation|cancellation|reduction)",
        ),
    ),
    # --- cross-cluster kinds (tri-source task set v2, 13 clusters) ---
    QuantityKind(
        kind="lumens", unit="lm",
        unit_aliases=("lm", "lumen", "lumens"),
        rel_tolerance=0.20,
        patterns=(
            # the unit word itself is unambiguous; bare "lm" is not accepted
            # without a digit right before it; "683 lm/W" is an efficacy,
            # not a light output, and must not match
            r"(\d{1,3}(?:,\d{3})+|\d{2,6}(?:\.\d+)?)\s*(?:lumens?|lm)\b"
            r"(?!\s*(?:/|per\b))",
        ),
    ),
    QuantityKind(
        kind="battery_mah", unit="mAh",
        unit_aliases=("mah", "mAh", "milliampere-hour"),
        rel_tolerance=0.15,
        patterns=(
            # thousands separators are common ("10,000mAh"); without the
            # comma alternative the pattern would capture the tail "000"
            # "1200 mAh/g" is a per-mass rate, not a capacity
            r"(\d{1,3}(?:,\d{3})+|\d{3,6})\s*mAh\b(?!\s*(?:/|per\b))",
        ),
    ),
    QuantityKind(
        kind="power_watts", unit="W",
        unit_aliases=("w", "W", "watt", "watts"),
        rel_tolerance=0.20,
        patterns=(
            # context-required: bare "10 W" (a width, a size code) must not
            # become a power claim
            r"(?:power|motor|output|heating|brew\w*|bulb|lamp|speaker|"
            r"amplifier|charg\w*)\W{0,30}?(\d+(?:\.\d+)?)\s*(?:watts?|W)\b",
            r"(\d+(?:\.\d+)?)[\s-]*(?:watts?|W)\b[\s-]*(?:of\s+)?"
            r"(?:power|motor|output|heating|charging)",
        ),
    ),
    QuantityKind(
        kind="megapixels", unit="MP",
        unit_aliases=("mp", "MP", "megapixel", "megapixels"),
        rel_tolerance=0.10,
        patterns=(
            # \b after MP cannot match inside "MP3"/"MP4" (digit follows)
            r"(\d+(?:\.\d+)?)\s*(?:megapixels?|MP)\b",
        ),
    ),
    QuantityKind(
        kind="refresh_hz", unit="Hz",
        unit_aliases=("hz", "Hz", "hertz"),
        rel_tolerance=0.10,
        patterns=(
            # context-required: audio frequency-response text ("20 Hz-20 kHz")
            # must not become a display refresh-rate claim
            r"(?:refresh(?:\s+rate)?|display|screen|monitor|panel)"
            r".{0,40}?(\d{2,4})\s*Hz\b",
            r"(\d{2,4})\s*Hz\b\s*(?:refresh|display|screen|monitor|panel)",
        ),
    ),
    QuantityKind(
        kind="color_temp_k", unit="K",
        unit_aliases=("k", "K", "kelvin"),
        rel_tolerance=0.15,
        patterns=(
            # context-required and 3-5 digits: "4K" resolution and "24k gold"
            # must not become a color-temperature claim
            r"(?:color\s+temperature|white|warm|cool|daylight|kelvin)"
            r".{0,40}?(\d{3,5})\s*K\b",
            r"(\d{3,5})\s*K\b\s*(?:color|white|warm|cool|daylight)",
        ),
    ),
)

def kind_for_unit(unit: str) -> QuantityKind | None:
    u = (unit or "").strip()
    for k in KINDS:
        if u in k.unit_aliases or u.lower() in k.unit_aliases:
            return k
    return None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    """One numeric, unit-typed marketing claim pulled from a product page."""
    product_url: str
    product_name: str
    kind: str
    unit: str
    value: float
    snippet: str
    matched_reference: bool = False


def extract_claims(product: dict) -> list[Claim]:
    """Pull every unit-typed numeric claim from a product's name+description.

    Prose with no extractable number yields nothing by construction: nuance
    cases ("immersive noise cancelling") can never enter the candidate set.
    """
    text = f"{product.get('name', '')}. {product.get('description', '')}"
    out: list[Claim] = []
    seen: set[tuple] = set()
    for qk in KINDS:
        for pat in qk.patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                try:
                    value = float(m.group(1).replace(",", ""))
                except ValueError:
                    continue
                key = (qk.kind, value)
                if key in seen:
                    continue
                seen.add(key)
                lo, hi = max(0, m.start() - 30), min(len(text), m.end() + 30)
                out.append(Claim(
                    product_url=product.get("url", ""),
                    product_name=product.get("name", ""),
                    kind=qk.kind, unit=qk.unit, value=value,
                    snippet=text[lo:hi].strip(),
                ))
    return out


def topic_anchored(topic: str, product: dict) -> bool:
    """The wiki fact applies to this product only if the topic is actually
    talked about on the page (same product/technology requirement)."""
    if "anchored_topics" in product:
        # precomputed on the corpus host (same tokenizer, full page text);
        # used when the full description does not travel with the product
        return topic in product["anchored_topics"]
    text = f"{product.get('name', '')} {product.get('description', '')}".lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", (topic or "").lower())
              if len(t) >= 4 and t not in _STOPWORDS]
    if not tokens:
        return (topic or "").lower() in text
    return any(t in text for t in tokens)


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------

def build_candidates(task_id: str, products: list[dict],
                     wiki_facts: list[dict],
                     claims: list[Claim] | None = None) -> dict:
    """Cross every extracted claim with every unit-compatible, topic-anchored
    wiki reference; flag only value conflicts beyond the typed tolerance.

    ``claims`` may inject claims pre-extracted on the corpus host (same
    extract_claims code); None means extract here from the product texts."""
    products_by_url = {p.get("url", ""): p for p in products}
    if claims is not None:
        all_claims = list(claims)
    else:
        all_claims = []
        for p in products:
            all_claims.extend(extract_claims(p))

    candidates = []
    for fact in wiki_facts:
        qk = kind_for_unit(str(fact.get("unit", "")))
        if qk is None:
            continue
        try:
            ref_value = float(fact["numeric_value"])
        except (KeyError, TypeError, ValueError):
            continue
        for claim in all_claims:
            if claim.kind != qk.kind:
                continue
            product = products_by_url.get(claim.product_url, {})
            if not topic_anchored(fact.get("topic", ""), product):
                continue
            claim.matched_reference = True
            threshold = ref_value * (1.0 + qk.rel_tolerance)
            if claim.value <= threshold + 1e-9:
                continue  # at/below the upper bound: legitimate, not flagged
            candidates.append({
                "candidate_id": f"{task_id}-{qk.kind}-{len(candidates) + 1:04d}",
                "task_id": task_id,
                "kind": qk.kind,
                "unit": qk.unit,
                "product_url": claim.product_url,
                "product_name": claim.product_name,
                "claim_value": claim.value,
                "claim_snippet": claim.snippet,
                "reference_topic": fact.get("topic", ""),
                "reference_fact_text": fact.get("fact_text", ""),
                "reference_url": fact.get("source_url", ""),
                "reference_value": ref_value,
                "relative_excess": round(claim.value / ref_value - 1.0, 4)
                if ref_value else None,
                "tolerance": qk.rel_tolerance,
                "status": STATUS_CANDIDATE,
            })

    return {
        "task_id": task_id,
        "builder": "scripts/build_gold_contradictions.py",
        "restriction": "numeric_spec_conflicts_only (registry T5)",
        "auto_gold": False,
        "note": "Nothing in this file is gold. Every candidate requires human "
                "adjudication; only SUPPORTED_CONFLICT verdicts are promoted.",
        "n_products_scanned": len(products),
        "n_wiki_facts": len(wiki_facts),
        "n_claims_extracted": len(all_claims),
        "n_candidates": len(candidates),
        "extracted_claims": [asdict(c) for c in all_claims],
        "candidates": candidates,
    }


REF_VERDICTS = ["VALID_CEILING", "NOT_A_CEILING"]


def _reference_key(c: dict) -> str:
    return f"{c['reference_topic']}|{c['kind']}|{c['reference_value']}"


def adjudication_template(candidates_doc: dict) -> dict:
    """Two-stage form: screen the (few) references first, then the entries.

    A reference marked NOT_A_CEILING voids every candidate built on it in
    one stroke; those entries may then stay empty. This caps the human cost
    of an auto-extracted reference that carries ceiling language without
    ceiling semantics (a product example, a metric of a different thing)."""
    refs = {}
    for c in candidates_doc["candidates"]:
        key = _reference_key(c)
        if key not in refs:
            refs[key] = {
                "reference_key": key,
                "reference_topic": c["reference_topic"],
                "kind": c["kind"],
                "reference_value": c["reference_value"],
                "reference_fact_text": c["reference_fact_text"],
                "reference_url": c["reference_url"],
                "n_candidates": 0,
                "reference_verdict": "",
                "note": "",
            }
        refs[key]["n_candidates"] += 1
    return {
        "task_id": candidates_doc["task_id"],
        "instructions": (
            "STAGE 1: for every entry in `references`, set "
            "`reference_verdict` to VALID_CEILING (the cited sentence "
            "really states a technology upper bound) or NOT_A_CEILING "
            "(a product example, a different quantity, or otherwise not a "
            "ceiling). Candidates of a NOT_A_CEILING reference are void and "
            "their entries may stay empty. "
            "STAGE 2: fill `verdict` for every remaining entry with one of "
            "allowed_verdicts, put your name in `adjudicator`, and explain "
            "in `note`. SUPPORTED_CONFLICT = the marketing number really "
            "conflicts with the reference; NOT_A_CONFLICT = extraction or "
            "matching error; NUANCE = real tension but not a decidable "
            "numeric conflict (these never become gold)."
        ),
        "allowed_verdicts": ALLOWED_VERDICTS,
        "allowed_reference_verdicts": REF_VERDICTS,
        "references": sorted(refs.values(), key=lambda r: r["reference_key"]),
        "entries": [
            {"candidate_id": c["candidate_id"],
             "reference_key": _reference_key(c), "verdict": "",
             "adjudicator": "", "note": ""}
            for c in candidates_doc["candidates"]
        ],
    }


def write_outputs(out_dir: Path, candidates_doc: dict) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tid = candidates_doc["task_id"]
    cand_path = out_dir / f"{tid}.candidates.json"
    adj_path = out_dir / f"{tid}.adjudication.template.json"
    cand_path.write_text(json.dumps(candidates_doc, indent=2,
                                    ensure_ascii=False) + "\n")
    adj_path.write_text(json.dumps(adjudication_template(candidates_doc),
                                   indent=2, ensure_ascii=False) + "\n")
    return cand_path, adj_path


# ---------------------------------------------------------------------------
# Promotion (only after complete human adjudication)
# ---------------------------------------------------------------------------

def promote(task_id: str, out_dir: Path, adjudication_path: Path) -> int:
    cand_path = out_dir / f"{task_id}.candidates.json"
    if not cand_path.exists():
        print(f"error: {cand_path} not found (run the builder first)")
        return 1
    cand_doc = json.loads(cand_path.read_text())
    by_id = {c["candidate_id"]: c for c in cand_doc["candidates"]}
    adj = json.loads(adjudication_path.read_text())

    gold, counts = [], {"SUPPORTED_CONFLICT": 0, "NOT_A_CONFLICT": 0,
                        "NUANCE": 0, "unadjudicated": 0,
                        "reference_rejected": 0}
    problems = []

    # Stage 1: every reference must be screened; NOT_A_CEILING voids its
    # candidates wholesale (their entries may stay empty).
    rejected_refs = set()
    for ref in adj.get("references", []):
        rv = (ref.get("reference_verdict") or "").strip()
        key = ref.get("reference_key", "")
        if rv not in REF_VERDICTS:
            problems.append(f"reference {key!r}: verdict {rv!r} "
                            f"(must be one of {REF_VERDICTS})")
        elif rv == "NOT_A_CEILING":
            rejected_refs.add(key)
    screened = {r.get("reference_key", "") for r in adj.get("references", [])}
    used = {_reference_key(c) for c in cand_doc["candidates"]}
    for key in sorted(used - screened):
        problems.append(f"reference {key!r} used by candidates but missing "
                        "from the adjudication file's references section")

    seen_ids = set()
    for entry in adj.get("entries", []):
        cid = entry.get("candidate_id", "")
        if cid in seen_ids:
            # duplicate rows are an adjudication-file corruption; refuse
            # rather than let the later row silently win (verify finding)
            problems.append(f"duplicate candidate_id {cid!r} in adjudication file")
            continue
        seen_ids.add(cid)
        if cid not in by_id:
            problems.append(f"unknown candidate_id {cid!r}")
            continue
        if _reference_key(by_id[cid]) in rejected_refs:
            counts["reference_rejected"] += 1
            if (entry.get("verdict") or "").strip() == "SUPPORTED_CONFLICT":
                problems.append(f"{cid}: SUPPORTED_CONFLICT on a "
                                "NOT_A_CEILING reference")
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
    missing = sorted(set(by_id) - seen_ids)
    if missing:
        problems.append(f"adjudication file misses candidates: {missing}")
    if counts["unadjudicated"]:
        problems.append(f"{counts['unadjudicated']} entries still have an "
                        "empty verdict (adjudication must be complete)")
    if problems:
        print("refusing to promote (honesty contract):")
        for p in problems:
            print(f"  - {p}")
        return 1

    gold_doc = {
        "task_id": task_id,
        "source_candidates": str(cand_path.relative_to(ROOT))
        if cand_path.is_relative_to(ROOT) else str(cand_path),
        "adjudication_file": str(adjudication_path),
        "counts": counts,
        "rejected_references": sorted(rejected_refs),
        "gold_contradictions": gold,
    }
    gold_path = out_dir / f"{task_id}.gold.json"
    gold_path.write_text(json.dumps(gold_doc, indent=2, ensure_ascii=False)
                         + "\n")
    print(f"promoted {len(gold)} SUPPORTED_CONFLICT of "
          f"{len(by_id)} candidates -> {gold_path}")
    return 0


# ---------------------------------------------------------------------------
# Built-in demo fixture (3 fake products, 2 wiki facts)
# ---------------------------------------------------------------------------

DEMO_TASK_ID = "demo_fixture"

DEMO_PRODUCTS = [
    {
        # true numeric conflict: claims 45 dB ANC vs the 30 dB reference
        "url": "http://localhost:7770/sonicmax-pro-x.html",
        "name": "SonicMax Pro X Wireless Over-Ear Headphones",
        "description": ("Flagship active noise cancelling reduces ambient "
                        "noise by up to 45 dB. Bluetooth 5.3 with 40mm "
                        "dynamic drivers and 30 hours of battery playback."),
    },
    {
        # nuance case: pure marketing prose, no extractable number.
        # T5 says this must NOT be flagged (it goes to the subjective rubric).
        "url": "http://localhost:7770/calmbuds-lite.html",
        "name": "CalmBuds Lite True Wireless Earbuds",
        "description": ("Immersive noise cancelling for deep focus and "
                        "feather-light all-day comfort. Studio-inspired "
                        "sound tuned by our audio lab."),
    },
    {
        # numeric claims that stay within the references: not flagged
        "url": "http://localhost:7770/bassline-900.html",
        "name": "BassLine 900 Bluetooth Headset",
        "description": ("28 hours of battery playback, Bluetooth 5.2, and "
                        "aptX streaming at 352 kbps."),
    },
]

DEMO_WIKI_FACTS = [
    {
        "topic": "Active noise control",
        "fact_text": ("Consumer active noise-cancelling headphones attenuate "
                      "ambient noise by at most about 30 dB, mostly at low "
                      "frequencies."),
        "source_url": ("http://localhost:8888/viewer#wikipedia/A/"
                       "Active_noise_control"),
        "numeric_value": 30,
        "unit": "dB",
    },
    {
        "topic": "Bluetooth",
        "fact_text": ("The latest released Bluetooth Core Specification "
                      "version in the frozen corpus is 5.4."),
        "source_url": "http://localhost:8888/viewer#wikipedia/A/Bluetooth",
        "numeric_value": 5.4,
        "unit": "version",
    },
]


def run_demo(out_dir: Path | None) -> int:
    doc = build_candidates(DEMO_TASK_ID, DEMO_PRODUCTS, DEMO_WIKI_FACTS)
    cands = doc["candidates"]
    nuance_url = DEMO_PRODUCTS[1]["url"]
    nuance_claims = [c for c in doc["extracted_claims"]
                     if c["product_url"] == nuance_url]

    checks = [
        ("exactly one candidate conflict", len(cands) == 1),
        ("it is the 45 dB ANC overclaim on SonicMax",
         bool(cands) and cands[0]["kind"] == "anc_db"
         and cands[0]["claim_value"] == 45.0
         and "sonicmax" in cands[0]["product_url"]),
        ("nuance product (CalmBuds prose) yields zero numeric claims",
         len(nuance_claims) == 0),
        ("nuance product is NOT in the candidate set",
         all(c["product_url"] != nuance_url for c in cands)),
        ("within-bound claims (BT 5.3 / 5.2, 28 h) are NOT flagged",
         all(c["kind"] == "anc_db" for c in cands)),
        ("every candidate carries the adjudication-required status",
         all(c["status"] == STATUS_CANDIDATE for c in cands)),
    ]

    print(f"demo fixture: {doc['n_products_scanned']} products, "
          f"{doc['n_wiki_facts']} wiki facts, "
          f"{doc['n_claims_extracted']} claims extracted, "
          f"{doc['n_candidates']} candidate conflict(s)")
    for c in cands:
        print(f"  candidate {c['candidate_id']}: {c['product_name']} claims "
              f"{c['claim_value']} {c['unit']} vs reference "
              f"{c['reference_value']} {c['unit']} "
              f"({c['reference_topic']}), excess {c['relative_excess']:+.0%}")
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed

    # exercise the full template -> adjudication -> promotion protocol in a
    # throwaway directory, both the accept and the reference-reject path
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        write_outputs(tmp, doc)
        template = adjudication_template(doc)

        adj_ok = json.loads(json.dumps(template))
        for r in adj_ok["references"]:
            r["reference_verdict"] = "VALID_CEILING"
        for e in adj_ok["entries"]:
            e.update(verdict="SUPPORTED_CONFLICT", adjudicator="demo-fixture",
                     note="fixture accept path")
        p_ok = tmp / "adj_ok.json"
        p_ok.write_text(json.dumps(adj_ok))
        rc_accept = promote(DEMO_TASK_ID, tmp, p_ok)
        gold_n = len(json.loads((tmp / f"{DEMO_TASK_ID}.gold.json")
                                .read_text())["gold_contradictions"])

        adj_rej = json.loads(json.dumps(template))
        for r in adj_rej["references"]:
            r["reference_verdict"] = "NOT_A_CEILING"
        # entries stay empty: a rejected reference voids them wholesale
        p_rej = tmp / "adj_rej.json"
        p_rej.write_text(json.dumps(adj_rej))
        rc_reject = promote(DEMO_TASK_ID, tmp, p_rej)
        gold_rej_n = len(json.loads((tmp / f"{DEMO_TASK_ID}.gold.json")
                                    .read_text())["gold_contradictions"])

        protocol_checks = [
            ("promotion accepts a fully adjudicated file",
             rc_accept == 0 and gold_n == 1),
            ("NOT_A_CEILING voids candidates without per-entry verdicts",
             rc_reject == 0 and gold_rej_n == 0),
        ]
        for label, passed in protocol_checks:
            print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
            ok = ok and passed

    if out_dir is not None:
        cand_path, adj_path = write_outputs(out_dir, doc)
        print(f"wrote {cand_path}\nwrote {adj_path}")
    print("DEMO", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build candidate (never auto-gold) numeric/spec "
                    "contradictions for one task.")
    ap.add_argument("--task-id", help="task id for output file naming")
    ap.add_argument("--products-json",
                    help='JSON list of {"url","name","description"}')
    ap.add_argument("--wiki-facts-json",
                    help='JSON list of {"topic","fact_text","source_url",'
                         '"numeric_value","unit"}')
    ap.add_argument("--out-dir",
                    help=f"output directory (default {DEFAULT_OUT})")
    ap.add_argument("--demo", action="store_true",
                    help="run the built-in fixture and self-check")
    ap.add_argument("--promote", metavar="ADJUDICATION_JSON",
                    help="promote a fully adjudicated candidates file to gold")
    args = ap.parse_args()

    if args.demo:
        out_dir = Path(args.out_dir) if args.out_dir else None
        return run_demo(out_dir)

    if not args.task_id:
        ap.error("--task-id is required outside --demo")
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT

    if args.promote:
        return promote(args.task_id, out_dir, Path(args.promote))

    if not (args.products_json and args.wiki_facts_json):
        ap.error("--products-json and --wiki-facts-json are required to build")
    products = json.loads(Path(args.products_json).read_text())
    wiki_facts = json.loads(Path(args.wiki_facts_json).read_text())
    doc = build_candidates(args.task_id, products, wiki_facts)
    cand_path, adj_path = write_outputs(out_dir, doc)
    print(f"{args.task_id}: {doc['n_claims_extracted']} claims from "
          f"{doc['n_products_scanned']} products x {doc['n_wiki_facts']} wiki "
          f"facts -> {doc['n_candidates']} candidate(s), 0 gold (by design)")
    print(f"wrote {cand_path}\nwrote {adj_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
