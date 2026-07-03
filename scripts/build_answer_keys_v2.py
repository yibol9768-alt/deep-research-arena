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
  gold_contradictions / decidable_verdicts stay EMPTY pending human
                   adjudication (registry T4: never auto-populated).

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

    # vitality ranking (T1): review volume x task-subject affinity. Membership
    # stays category-based; this only orders the nugget pool so a gaming
    # task's vital nuggets are consoles, not the cluster's bar stools.
    it = _intent_tokens(spec.get("intent") or spec.get("angle") or "")

    def _affinity(name: str) -> int:
        toks = {w for w in name.lower().split() if len(w) > 3}
        return len(toks & it)

    ranked = sorted((s for s in sent.values() if s.get("n_reviews", 0) >= 3),
                    key=lambda s: -(s["n_reviews"] * (1 + 2 * _affinity(s["name"]))))
    vital, useful = [], []
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

    reqs = [SpecRequirement(
        id="min_words", kind="min_words",
        description="Substantive report, not a one-liner",
        params={"min": 300})]
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
                                  "intent": t.get("intent", "")}

    KEYS_OUT.mkdir(parents=True, exist_ok=True)
    CHECK_OUT = ROOT / "data/golden/checklists"
    CHECK_OUT.mkdir(parents=True, exist_ok=True)
    cache: dict[str, tuple] = {}
    n = 0
    for tid, spec in sorted(specs.items()):
        cl = spec["cluster"]
        if cl not in cache:
            cache[cl] = load_cluster(cl)
        products, sent = cache[cl]
        ak = build_key(tid, spec, products, sent)
        ak.save(KEYS_OUT / f"{tid}.json")
        items = gen_checklist(ak)
        (CHECK_OUT / f"{tid}.json").write_text(json.dumps(
            {"task_id": tid, "generated_from": "answer_key_v2",
             "items": [i.__dict__ if hasattr(i, "__dict__") else i for i in items]},
            ensure_ascii=False, indent=1) + "\n")
        n += 1
    print(f"built {n} answer keys -> {KEYS_OUT} (+ checklists -> {CHECK_OUT})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
