"""Relevance gate: trim the keyword-enumerated relevant set to what a task
actually asks about (METHODOLOGY_REDESIGN_2026-07-03.md section 7.1).

Why this exists. The db golden is built with substring keyword matching
(`WHERE name LIKE '%headphones%'`), which over-includes: a headphones task
pulls in "Glass Film Window Sticker ... Funny Kitty with Headphones", a
"Gaming Keyboard + Headset Bundle", a "Magnet Cover for SteelSeries Arctis"
(an accessory). The completeness denominator (axis 3) is inflated by these,
so recall is measured against a bloated set and every report looks incomplete.

This gate marks each entity relevant / not, WITHOUT deleting it (the trim is
auditable and reversible). It has two backends:

  * deterministic (default, no model): a decorative/accessory stoplist plus
    a head-category signal. Catches the structural collisions cheaply and is
    fully reproducible. Used now.

  * llm (stage 2, GPU): a local model judges "is this entity a core instance
    of <topic>?" per entity. Higher recall on subtle cases; called later when
    the box GPU is free. Interface is here so the scorer never changes.

The gate reads the topic's category intent from the topic config
(configs/deep_topics/<id>.yaml: `relevance_head`, `accessory_terms`) when
present, else falls back to generic decorative terms.
"""

from __future__ import annotations

import re

# Items that merely DEPICT or ACCESSORIZE a product rather than being one.
# Generic across topics; a headphones task should not count a headphones poster.
_DECORATIVE = re.compile(
    r"\b(sticker|decal|poster|wall\s*art|figurine|keychain|phone\s*case|"
    r"costume|mug|pillow|curtain|window\s*(film|sticker|blind|shade)|"
    r"membrane|t-?shirt|hoodie|sock|towel|rug|mouse\s*pad|mousepad|"
    r"ornament|magnet\s*cover|puzzle|tapestry|canvas|painting|"
    r"earring|necklace|bracelet|pendant|greeting\s*card|wallpaper|blanket)\b",
    re.I,
)

# Bundle / accessory markers: the item is a case, mount, cable, replacement
# part, or a multi-item bundle where the topic item is not the primary good.
_ACCESSORY = re.compile(
    r"\b(replacement\s*(ear\s*pad|pad|cushion|cable)|ear\s*pad|cushion\s*cover|"
    r"carrying\s*case|hard\s*case|protective\s*case|stand|mount|holder|"
    r"splitter|adapter|extension\s*cable|cable\s*only|spare\s*part)\b",
    re.I,
)


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def deterministic_relevance(name: str, head_terms: list[str],
                            accessory_terms: list[str] | None = None) -> tuple[bool, str]:
    """Return (is_relevant, reason). head_terms are the topic's core product
    nouns (e.g. headphones/earbuds/headset). An entity is relevant if it names
    a head term and is not decorative/accessory."""
    acc = _ACCESSORY
    if accessory_terms:
        acc = re.compile(r"\b(" + "|".join(re.escape(t) for t in accessory_terms) + r")\b", re.I)
    if _DECORATIVE.search(name):
        return False, "decorative_depiction"
    if acc.search(name):
        return False, "accessory_or_bundle_part"
    toks = set(_tokens(name))
    if not any(any(h in t or t in h for t in toks) for h in
               (_tokens(" ".join(head_terms)))):
        return False, "no_head_term"
    return True, "head_term_present"


def apply_gate(answer_key, head_terms: list[str],
               accessory_terms: list[str] | None = None,
               backend: str = "deterministic", llm_judge=None):
    """Mark relevance on an AnswerKey in place; recompute vital/useful splits
    to exclude non-relevant entities. Returns a stats dict.

    backend='deterministic' uses the stoplist+head-term rule.
    backend='llm' calls llm_judge(name, topic) -> bool per shopping/product
    entity (stage 2); non-product categories (wiki mandatory articles, forum
    threads) keep their relevance since those sets are curated differently.
    """
    prod_kept = prod_dropped = nonprod = 0
    dropped_reasons = {}
    urls_relevant = set()
    for e in answer_key.relevant_set:
        if e.category != "shopping_product":
            e.relevant, e.relevance_reason = True, "non_product_kept"
            urls_relevant.add(e.url)
            nonprod += 1
            continue
        if backend == "llm" and llm_judge is not None:
            ok = bool(llm_judge(e.name, head_terms))
            reason = "llm_relevant" if ok else "llm_off_topic"
        else:
            ok, reason = deterministic_relevance(e.name, head_terms, accessory_terms)
        e.relevant, e.relevance_reason = ok, reason
        if ok:
            urls_relevant.add(e.url)
            prod_kept += 1
        else:
            prod_dropped += 1
            dropped_reasons[reason] = dropped_reasons.get(reason, 0) + 1

    # nuggets inherit their source entity's relevance
    for pool in (answer_key.vital_nuggets, answer_key.useful_nuggets):
        for n in pool:
            n.relevant = n.source_url in urls_relevant or not n.source_url.startswith("http://localhost:7770")

    answer_key.metadata.update({
        "relevance_gate_applied": True,
        "relevance_backend": backend,
        "n_products_kept": prod_kept,
        "n_products_dropped": prod_dropped,
        "n_nonproduct_kept": nonprod,
        "dropped_reasons": dropped_reasons,
        "n_vital_relevant": sum(1 for n in answer_key.vital_nuggets if n.relevant),
        "n_useful_relevant": sum(1 for n in answer_key.useful_nuggets if n.relevant),
        # honest flag: deterministic backend clears structural collisions only;
        # the "744 headphones is implausible" over-breadth needs the llm backend.
        "relevance_note": ("deterministic gate clears decorative/accessory "
                           "collisions; semantic over-breadth trim pending llm backend"
                           if backend == "deterministic" else "llm-gated"),
    })
    return answer_key.metadata


if __name__ == "__main__":
    import sys
    from src.eval.answer_key import migrate_db_golden
    src = sys.argv[1] if len(sys.argv) > 1 else "data/golden/db/dr_cross_deep_0001.json"
    heads = sys.argv[2].split(",") if len(sys.argv) > 2 else \
        ["headphone", "earbud", "earphone", "headset", "earpiece", "airpod"]
    ak = migrate_db_golden(src)
    before = len([e for e in ak.relevant_set if e.category == "shopping_product"])
    stats = apply_gate(ak, heads)
    print(f"products: {before} -> {stats['n_products_kept']} kept "
          f"(dropped {stats['n_products_dropped']}: {stats['dropped_reasons']})")
    print(f"vital nuggets relevant: {stats['n_vital_relevant']}")
    print(f"note: {stats['relevance_note']}")
