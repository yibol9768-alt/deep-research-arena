#!/usr/bin/env python3
"""Answer-key builder v2: tri-source task set (EXECUTION_PLAN P3.4).

For every task in data/golden/task_tri_source_specs.json (the redesign
workflow output: task_id -> {cluster, archetype, angle, wiki_topics, intent}),
assembles an AnswerKey from the cluster's box-derived data:

  relevant_set   = the cluster golden's category-enumerated products
                   (Entity list, weight = review-volume percentile: importance,
                   never relevance);
  vital_nuggets  = top sentiment products (rating + n_reviews + dominant
                   complaint, all decidable against the DB) + one nugget per
                   wiki topic (concept coverage, checked as text presence);
  useful_nuggets = second-tier sentiment products;
  spec           = archetype-derived output shape (decidable):
                   buying-dilemma/value-question -> shortlist section;
                   claim-check/community-vs-ratings -> verdict-style section;
                   all -> min_words 300 (a report, not a one-liner);
  gold_contradictions = ADJUDICATED gold only, attached from
                   data/golden/contradictions/*.gold.json by cluster match
                   (registry T4 honesty contract: the builder itself never
                   invents gold; it only reads what the adjudication
                   pipeline promoted). decidable_verdicts follow the same
                   contract, attached from data/golden/verdicts/*.gold.json by
                   task_id; they stay EMPTY until such gold is promoted.

Deterministic and offline: no model, no HTTP. Rerunnable any time the cluster
dumps refresh.

Usage: python3 scripts/build_answer_keys_v2.py [--specs data/golden/task_tri_source_specs.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.answer_key import AnswerKey, Entity, Nugget, SpecRequirement  # noqa: E402
from src.eval.checklist_gen import generate as gen_checklist  # noqa: E402

TRI = ROOT / "data/golden/tri_source"
KEYS_OUT = ROOT / "data/golden/answer_keys"
CONTRA_DIR = ROOT / "data/golden/contradictions"
VERDICTS_DIR = ROOT / "data/golden/verdicts"
ALLOWED_VERDICT_VALUES = {"SUPPORTED", "REFUTED", "UNDETERMINED"}


def load_adjudicated_gold() -> dict[str, list]:
    """cluster -> adjudicated gold contradiction entries (checklist-ready).

    Reads every *.gold.json the adjudication pipeline promoted. Entries
    carry a human/strong-model verdict already; this function only
    reshapes them (summary + provenance) and never adds candidates."""
    by_cluster: dict[str, list] = {}
    for path in sorted(CONTRA_DIR.glob("*.gold.json")):
        doc = json.loads(path.read_text())
        for it in doc.get("gold_contradictions", []):
            vals = it.get("values")
            if vals:  # intra-page self-contradiction
                shown = " vs ".join(f"{v['value']}" for v in vals)
                summary = (f"the product page for '{it['product_name']}' "
                           f"contradicts itself on {it['kind']}: "
                           f"{shown} {it.get('unit', '')}".rstrip())
            else:     # cross-source (marketing vs encyclopedia) shape
                summary = (f"'{it['product_name']}' claims "
                           f"{it.get('claim_value')} {it.get('unit', '')} "
                           f"vs reference {it.get('reference_value')} "
                           f"({it.get('reference_topic')})")
            entry = {"summary": summary,
                     "kind": it.get("kind"),
                     "unit": it.get("unit"),
                     "product_url": it.get("product_url"),
                     "product_name": it.get("product_name"),
                     "values": vals,
                     "candidate_id": it.get("candidate_id"),
                     "adjudicator": it.get("adjudicator"),
                     "source_gold_file": path.name}
            clusters = it.get("clusters") or [it.get("cluster")]
            for cl in clusters:
                if cl:
                    by_cluster.setdefault(cl, []).append(entry)
    return by_cluster


def load_adjudicated_verdicts(verdicts_dir: Path = VERDICTS_DIR) -> dict[str, dict]:
    """task_id -> {claim_id: verdict}. Reads data/golden/verdicts/*.gold.json
    only (what the verdict adjudication pipeline promoted), same honesty
    contract as load_adjudicated_gold: an entry enters a key only when a
    human / strong-model adjudicator has filled a valid verdict AND signed it.
    A missing dir or no gold files yields {}, so keys stay verdict-free until
    adjudication happens."""
    by_task: dict[str, dict] = {}
    if not verdicts_dir.exists():
        return by_task
    for path in sorted(verdicts_dir.glob("*.gold.json")):
        doc = json.loads(path.read_text())
        for it in doc.get("gold_verdicts", []):
            cid = it.get("id")
            tid = it.get("task_id")
            verdict = (it.get("adjudicated_verdict") or "").strip()
            adjudicator = (it.get("adjudicator") or "").strip()
            if not (cid and tid and adjudicator):
                continue
            if verdict not in ALLOWED_VERDICT_VALUES:
                continue
            by_task.setdefault(tid, {})[cid] = verdict
    return by_task

N_VITAL_SENT = 12      # top sentiment products as vital nuggets
N_USEFUL_SENT = 20     # next tier as useful


def load_cluster(cluster: str) -> tuple[list, dict]:
    golden = json.loads((TRI / f"golden_{cluster}.json").read_text())
    sent = json.loads((TRI / f"sent_{cluster}.json").read_text())
    return golden["relevant_set"], {p["url_key"]: p for p in sent["products"]}


_INTENT_STOP = set("""the and for with that this have from your what which would could
should about really actually honestly just like want know been over under
into been some more most them they still even only end buy pick spend
""".split())


def _intent_tokens(intent: str) -> set:
    import re as _re
    return {t for t in _re.findall(r"[a-z][a-z']{3,}", (intent or "").lower())
            if t not in _INTENT_STOP}


def build_key(task_id: str, spec: dict, products: list, sent: dict) -> AnswerKey:
    # importance weights: review-volume percentile within the cluster
    by_reviews = sorted(
        (sent.get(p["url"].rsplit("/", 1)[-1].removesuffix(".html"), {})
         .get("n_reviews", 0) for p in products))
    n = len(by_reviews) or 1

    def pct(nr: int) -> float:
        import bisect
        return 0.2 + 0.8 * bisect.bisect_left(by_reviews, nr) / n

    entities = []
    for p in products:
        key = p["url"].rsplit("/", 1)[-1].removesuffix(".html")
        s = sent.get(key)
        facts = dict(p.get("facts") or {})
        if s:
            if s.get("rating_pct") is not None:
                facts["rating_pct"] = s["rating_pct"]
            facts["n_reviews"] = s.get("n_reviews", 0)
        entities.append(Entity(
            url=p["url"], name=p["name"], category="shopping_product",
            facts=facts, weight=round(pct(s["n_reviews"]) if s else 0.2, 3)))

    # vitality ranking (T1, rebuilt after verify pass): subject affinity
    # DOMINATES review volume, affinity tokens are regex-tokenized (punctuation
    # no longer breaks matches) and IDF-weighted within the cluster (generic
    # cluster words like "laptop" in electronics stop outranking the actual
    # subject), and the pool is restricted to relevant_set members (a nugget
    # must never demand a product the key's own relevance set excludes).
    import math
    import re as _re
    member_slugs = {p["url"].rsplit("/", 1)[-1].removesuffix(".html")
                    for p in products}
    it = _intent_tokens(spec.get("intent") or spec.get("angle") or "")

    def _name_toks(name: str) -> set:
        return {t for t in _re.findall(r"[a-z][a-z']{3,}", (name or "").lower())
                if t not in _INTENT_STOP}

    pool0 = [s for s in sent.values()
             if s.get("n_reviews", 0) >= 3 and s["url_key"] in member_slugs]
    df: dict[str, int] = {}
    for s0 in pool0:
        for t in _name_toks(s0["name"]):
            df[t] = df.get(t, 0) + 1
    n_pool = max(len(pool0), 1)

    def _affinity(name: str) -> float:
        return sum(math.log(n_pool / (1 + df.get(t, 0)))
                   for t in _name_toks(name) & it)

    ranked = sorted(pool0, key=lambda s: (-_affinity(s["name"]),
                                          -s["n_reviews"]))
    vital, useful = [], []
    for s in ranked:
        if s["name"].startswith("None/"):
            s["name"] = s["name"][5:]
    for i, s in enumerate(ranked[:N_VITAL_SENT + N_USEFUL_SENT]):
        url = f"http://localhost:7770/{s['url_key']}.html"
        complaint = (s.get("complaint_terms") or [["", 0]])[0][0]
        text = (f"{s['name']}: rated {s.get('rating_pct')}% over "
                f"{s['n_reviews']} reviews"
                + (f"; buyers' top complaint: {complaint}" if complaint else ""))
        nug = Nugget(text=text, subject=s["name"],
                     predicate="buyer_sentiment",
                     object=f"{s.get('rating_pct')}%/{s['n_reviews']}rev",
                     source_url=url,
                     importance="vital" if i < N_VITAL_SENT else "useful")
        (vital if i < N_VITAL_SENT else useful).append(nug)
    for wt in spec.get("wiki_topics") or []:
        vital.append(Nugget(
            text=f"Explains the factual core: {wt}",
            subject=wt, predicate="concept_coverage", object=wt,
            source_url=f"http://localhost:8090/content/wikipedia_en_all_nopic/A/{wt.replace(' ', '_')}",
            importance="vital"))

    task_min_words = int(spec.get("min_words") or 300)
    reqs = [SpecRequirement(
        id="min_words", kind="min_words",
        description="Substantive report, not a one-liner",
        params={"min": task_min_words})]
    arche = (spec.get("archetype") or "").lower()
    if any(k in arche for k in ("buying", "value", "durability", "bifl", "use-case")):
        reqs.append(SpecRequirement(
            id="sec_shortlist", kind="section_present",
            description="An actionable shortlist / final picks section",
            params={"keywords": ["shortlist", "recommend", "pick", "buy",
                                 "top ", "verdict", "bottom line"]}))
    if any(k in arche for k in ("claim", "community-vs", "debunk")):
        reqs.append(SpecRequirement(
            id="sec_claims", kind="section_present",
            description="A claims / verdicts section addressing what is true",
            params={"keywords": ["claim", "verdict", "true", "myth",
                                 "actually", "evidence"]}))

    return AnswerKey(
        task_id=task_id, relevant_set=entities,
        vital_nuggets=vital, useful_nuggets=useful,
        spec_requirements=reqs,
        metadata={"builder": "build_answer_keys_v2", "cluster": spec["cluster"],
                  "archetype": spec.get("archetype"), "angle": spec.get("angle"),
                  "wiki_topics": spec.get("wiki_topics"),
                  "n_relevant": len(entities),
                  "sentiment_products": len(ranked),
                  "source": "db_category_enumeration + review_sentiment_deriver"})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", default=None,
                    help="optional workflow specs json; default reads the "
                         "task files' tri_source blocks (single source of "
                         "truth, covers kept tasks too)")
    args = ap.parse_args()
    if args.specs:
        specs = json.loads((ROOT / args.specs).read_text())["specs"]
    else:
        specs = {}
        task_dir = ROOT / "data/tasks/deep_research/cross_site_deep"
        for tp in sorted(task_dir.glob("dr_cross_deep_*.json")):
            t = json.loads(tp.read_text())
            ts = t.get("tri_source")
            if t.get("task_version") == 2 and ts:
                specs[tp.stem] = {"cluster": ts["cluster"],
                                  "archetype": ts.get("archetype"),
                                  "angle": ts.get("angle"),
                                  "wiki_topics": ts.get("wiki_topics"),
                                  "intent": t.get("intent", ""),
                                  "min_words": (t.get("markdown_spec") or {}).get("min_words")}

    KEYS_OUT.mkdir(parents=True, exist_ok=True)
    CHECK_OUT = ROOT / "data/golden/checklists"
    CHECK_OUT.mkdir(parents=True, exist_ok=True)
    cache: dict[str, tuple] = {}
    gold_by_cluster = load_adjudicated_gold()
    verdicts_by_task = load_adjudicated_verdicts()
    n_gold_attached = 0
    n_verdicts_attached = 0
    n = 0
    for tid, spec in sorted(specs.items()):
        cl = spec["cluster"]
        if cl not in cache:
            cache[cl] = load_cluster(cl)
        products, sent = cache[cl]
        ak = build_key(tid, spec, products, sent)
        ak.gold_contradictions = gold_by_cluster.get(cl, [])
        n_gold_attached += len(ak.gold_contradictions)
        ak.decidable_verdicts = verdicts_by_task.get(tid, {})
        n_verdicts_attached += len(ak.decidable_verdicts)
        ak.save(KEYS_OUT / f"{tid}.json")
        items = gen_checklist(ak)
        (CHECK_OUT / f"{tid}.json").write_text(json.dumps(
            {"task_id": tid, "generated_from": "answer_key_v2",
             "items": [i.__dict__ if hasattr(i, "__dict__") else i for i in items]},
            ensure_ascii=False, indent=1) + "\n")
        n += 1
    print(f"built {n} answer keys -> {KEYS_OUT} (+ checklists -> {CHECK_OUT}); "
          f"{n_gold_attached} adjudicated gold-contradiction attachments; "
          f"{n_verdicts_attached} adjudicated decidable-verdict attachments")
    return 0


if __name__ == "__main__":
    sys.exit(main())
