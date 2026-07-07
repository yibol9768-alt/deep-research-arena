#!/usr/bin/env python3
"""Candidate miner for decidable claim verdicts (answer_key.decidable_verdicts).

Same honesty contract as the contradiction pillar
(scripts/build_intra_page_contradictions.py): this builder NEVER emits gold.
It mines candidate claims for claim-check / debunking shaped tasks and writes
data/golden/verdicts/candidates.json plus an empty adjudication template. A
candidate becomes an answer-key verdict only after a human / strong-model
adjudicator fills the template and a *.gold.json is promoted from it (that
promote step and the loader live elsewhere; this miner produces no gold).

Candidate kinds (kept conservative):
  price_comparison  two named DB entities in the same cluster; the verdict is
                    derived purely from DB prices, so proposed_verdict is set.
  numeric_spec      one named DB entity whose store rating the DB carries as a
                    number; proposed_verdict restates that DB value.
  wiki_claim        a folklore claim the intent names (e.g. "dark roast really
                    has more caffeine"). The closed world cannot decide these
                    deterministically, so proposed_verdict is null and
                    adjudication must supply both the verdict and the id of the
                    wiki article that supports it.

DB truth comes from data/golden/db/dr_cross_deep_*.json. Those relevant sets
are an over-inclusive keyword net, so the topical entity selection reuses the
answer key's relevance-ranked vital nuggets (data/golden/answer_keys/*.json);
every proposed verdict number, however, is read straight from the DB golden.

Deterministic and offline: no model, no HTTP. Rerunnable any time.

Usage: python3 scripts/build_verdict_candidates.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_DIR = ROOT / "data/golden/db"
TASK_DIR = ROOT / "data/tasks/deep_research/cross_site_deep"
KEYS_DIR = ROOT / "data/golden/answer_keys"
OUT_DIR = ROOT / "data/golden/verdicts"

ALLOWED_VERDICTS = ["SUPPORTED", "REFUTED", "UNDETERMINED"]

# archetypes whose intent is a claim to check rather than a product to pick
CLAIM_ARCHETYPES = ("claim", "community-vs", "debunk")

# folklore / claim signals in intent prose. Two distinct hits (or a claim
# archetype / Debunking intent_type) mark a task as claim-check shaped.
CLAIM_MARKERS = [
    "really", "actually", "genuinely", "supposed to", "claim", "promise",
    "myth", "folklore", "people repeat", "i've heard", "is that true",
    "hold up", "what the ads say", "backed by", "pay for the logo",
    "worth it", "don't make them like", "horror stor",
]

# a sentence is kept as a wiki_claim only if it asserts folklore (one of these
# introducers) or is a truth-check question. Instruction sentences are dropped.
FOLKLORE_INTRO = [
    "people repeat", "i've heard", "folklore", "myth", "supposed to", "claim",
    "promise", "what the ads say", "backed by", "don't make them like",
    "horror stor", "are actually true", "really has", "really go", "really do",
    "ads say",
]
INSTRUCTION_MARKERS = [
    "walk me", "end with", "what would you", "what you'd", "lay out",
    "hand my", "start a beginner", "give me",
]
_QUESTION_CLAIM = re.compile(r"\b(really|genuinely|actually|true)\b", re.I)
_SENT = re.compile(r"[^.?!]*[.?!]")
_MIN_CLAIM_CHARS = 25
_MAX_WIKI_PER_TASK = 3
_MAX_NUMERIC_SPEC_PER_TASK = 1


def _markers(intent: str) -> set:
    il = (intent or "").lower()
    return {m for m in CLAIM_MARKERS if m in il}


def is_claim_shaped(task: dict) -> bool:
    ts = task.get("tri_source") or {}
    arche = (ts.get("archetype") or "").lower()
    if any(k in arche for k in CLAIM_ARCHETYPES):
        return True
    if (task.get("intent_type") or "") == "Debunking":
        return True
    return len(_markers(task.get("intent", ""))) >= 2


def extract_wiki_claims(intent: str) -> list[str]:
    """Folklore sentences the intent repeats, conservative and deduped."""
    out: list[str] = []
    for s in _SENT.findall(intent or ""):
        s = s.strip()
        sl = s.lower()
        if len(s) < _MIN_CLAIM_CHARS:
            continue
        if any(x in sl for x in INSTRUCTION_MARKERS):
            continue
        keep = (any(k in sl for k in FOLKLORE_INTRO)
                or (s.endswith("?") and _QUESTION_CLAIM.search(s)))
        if keep and s not in out:
            out.append(s)
        if len(out) >= _MAX_WIKI_PER_TASK:
            break
    return out


def _price(entity: dict):
    p = (entity.get("facts") or {}).get("price")
    return None if p in (None, "") else round(float(p), 2)


def _rating(entity: dict):
    r = (entity.get("facts") or {}).get("rating")
    return None if r in (None, "") else float(r)


def _review_count(entity: dict) -> int:
    rc = (entity.get("facts") or {}).get("review_count")
    return int(rc) if rc not in (None, "") else 0


def _topical_entities(task_id: str, db_doc: dict) -> list[dict]:
    """The DB-golden entities the answer key already flagged as topical vital
    products, joined by url so every one carries its DB price / rating."""
    ak_path = KEYS_DIR / f"{task_id}.json"
    if not ak_path.exists():
        return []
    ak = json.loads(ak_path.read_text())
    db_by_url = {e["url"]: e for e in db_doc.get("relevant_set", [])}
    out, seen = [], set()
    for n in ak.get("vital_nuggets", []):
        if n.get("predicate") != "buyer_sentiment":
            continue
        e = db_by_url.get(n.get("source_url"))
        if not e or e["url"] in seen:
            continue
        seen.add(e["url"])
        out.append({"name": e["name"], "url": e["url"],
                    "price": _price(e), "rating": _rating(e),
                    "review_count": _review_count(e)})
    return out


def _db_candidates(task_id: str, db_doc: dict) -> list[dict]:
    ents = _topical_entities(task_id, db_doc)
    db_rel = f"data/golden/db/{task_id}.json"
    cands: list[dict] = []

    priced = [e for e in ents if e["price"] is not None]
    priced.sort(key=lambda e: (e["price"], e["name"]))
    if len(priced) >= 2 and priced[-1]["price"] > priced[0]["price"]:
        hi, lo = priced[-1], priced[0]
        cands.append({
            "kind": "price_comparison",
            "claim": (f"'{hi['name']}' (${hi['price']:.2f}) is priced higher "
                      f"than '{lo['name']}' (${lo['price']:.2f})."),
            "proposed_verdict": "SUPPORTED",
            "evidence": {
                "source": "db_golden", "db_golden": db_rel,
                "entity_a": hi, "entity_b": lo,
                "derivation": (f"price_a ({hi['price']:.2f}) > "
                               f"price_b ({lo['price']:.2f})"),
            },
        })

    rated = [e for e in ents if e["rating"] is not None]
    rated.sort(key=lambda e: (-e["rating"], -e["review_count"], e["name"]))
    for e in rated[:_MAX_NUMERIC_SPEC_PER_TASK]:
        cands.append({
            "kind": "numeric_spec",
            "claim": (f"'{e['name']}' holds a store rating of {e['rating']} "
                      f"stars across {e['review_count']} reviews."),
            "proposed_verdict": "SUPPORTED",
            "evidence": {
                "source": "db_golden", "db_golden": db_rel,
                "entity": e, "predicate": "rating", "db_value": e["rating"],
            },
        })
    return cands


def _wiki_candidates(cluster: str, wiki_topics: list, intent: str) -> list[dict]:
    cands = []
    for claim in extract_wiki_claims(intent):
        cands.append({
            "kind": "wiki_claim",
            "claim": claim,
            "proposed_verdict": None,
            "evidence": {
                "source": "task_intent",
                "candidate_wiki_topics": wiki_topics or [],
                "note": ("closed world cannot decide deterministically; "
                         "adjudication must set the verdict and cite the id of "
                         "the supporting wiki article"),
            },
        })
    return cands


def mine() -> dict:
    db_tasks = {p.stem for p in DB_DIR.glob("dr_cross_deep_*.json")}
    candidates: list[dict] = []
    n_tasks = 0
    for tp in sorted(TASK_DIR.glob("dr_cross_deep_*.json")):
        task = json.loads(tp.read_text())
        if not is_claim_shaped(task):
            continue
        n_tasks += 1
        tid = tp.stem
        ts = task.get("tri_source") or {}
        cluster = ts.get("cluster")
        entry = []
        if tid in db_tasks:
            db_doc = json.loads((DB_DIR / f"{tid}.json").read_text())
            entry += _db_candidates(tid, db_doc)
        entry += _wiki_candidates(cluster, ts.get("wiki_topics"),
                                  task.get("intent", ""))
        seq = {"price_comparison": 0, "numeric_spec": 0, "wiki_claim": 0}
        abbr = {"price_comparison": "price", "numeric_spec": "spec",
                "wiki_claim": "wiki"}
        for c in entry:
            seq[c["kind"]] += 1
            c_full = {
                "id": f"verdict-{tid}-{abbr[c['kind']]}-{seq[c['kind']]:02d}",
                "task_id": tid,
                "cluster": cluster,
                "kind": c["kind"],
                "claim": c["claim"],
                "proposed_verdict": c["proposed_verdict"],
                "evidence": c["evidence"],
            }
            candidates.append(c_full)

    by_kind: dict[str, int] = {}
    for c in candidates:
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
    return {
        "builder": "scripts/build_verdict_candidates.py",
        "restriction": ("decidable claim verdicts for claim-check / debunking "
                        "tasks; DB-derived proposals plus wiki claims that need "
                        "adjudication"),
        "auto_gold": False,
        "note": ("machine-mined candidates; every entry requires adjudication "
                 "before it can enter any answer key's decidable_verdicts"),
        "db_source": "data/golden/db/dr_cross_deep_*.json",
        "allowed_verdicts": ALLOWED_VERDICTS,
        "n_claim_shaped_tasks": n_tasks,
        "n_candidates": len(candidates),
        "by_kind": dict(sorted(by_kind.items())),
        "candidates": candidates,
    }


def adjudication_template(doc: dict) -> dict:
    return {
        "builder": doc["builder"],
        "instructions": (
            "For every entry set adjudicated_verdict to one of allowed_verdicts, "
            "put your name in adjudicator, and explain in rationale. "
            "SUPPORTED = the closed world (DB and/or wiki) supports the claim; "
            "REFUTED = it contradicts the claim; UNDETERMINED = the closed world "
            "cannot decide. For price_comparison / numeric_spec the "
            "proposed_verdict is DB-derived; confirm or override it. For "
            "wiki_claim entries proposed_verdict is null: you must supply the "
            "verdict AND record the supporting wiki article id in rationale. "
            "Partial files are refused by the promote step."),
        "allowed_verdicts": ALLOWED_VERDICTS,
        "entries": [
            {"id": c["id"], "task_id": c["task_id"], "claim": c["claim"],
             "proposed_verdict": c["proposed_verdict"], "evidence": c["evidence"],
             "adjudicated_verdict": None, "rationale": None, "adjudicator": None}
            for c in doc["candidates"]
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = mine()
    cand_path = out_dir / "candidates.json"
    tpl_path = out_dir / "verdicts.adjudication.json"
    cand_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    tpl_path.write_text(json.dumps(adjudication_template(doc), indent=2,
                                   ensure_ascii=False) + "\n")

    print(f"{doc['n_candidates']} candidates from "
          f"{doc['n_claim_shaped_tasks']} claim-shaped tasks -> {cand_path}")
    for kind, n in doc["by_kind"].items():
        print(f"  {kind}: {n}")
    print(f"adjudication template -> {tpl_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
