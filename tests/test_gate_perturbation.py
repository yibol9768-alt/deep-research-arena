"""Gate G3 (perturbation must lose): corrupting the oracle report must
strictly lower the corresponding axis, on every task.

This is the gate that kills "silently zeroed / silently saturated" defects:
an axis that cannot see a wrong number, a deleted citation or a fabricated
URL is not measuring anything. Four deterministic corruptions per task:

  wrong sentiment number  -> completeness strictly drops
  delete one citation     -> completeness strictly drops (reach must NOT drop:
                             the remaining citations are all real)
  swap URL out of corpus  -> reach strictly drops; three variants spanning the
                             three sources (off-sandbox host / content-shaped
                             absent store page / absent forum thread)
  wrong price value       -> fact strictly drops
  re-point concept citation at ANOTHER real wiki page (cache only)
                          -> completeness strictly drops (quote no longer
                             matches the cited page; citing a real-but-wrong
                             page must earn nothing)

Every corruption is a pure string edit of the oracle report; nothing is
random, timed or networked. Marked ``gates`` (deselected by default; run via
scripts/run_gates.py).

The file also pins (as an always-on test, not gates-marked) the four-digit
plain-number price behaviour flagged in docs/SPEC_ISSUES.md section 2 (转 G3):
reproduction was attempted in six phrasings and the current baseline supports
all of them, so the entry is pinned green here and would go red on any
regression of ``_NUM_RE`` / ``_standalone_number``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import src.eval.decidable_scorer as ds
from src.eval.answer_key import AnswerKey
from src.eval.oracle_report import build_oracle_report
from src.verifiers.citation_format import iter_markdown_links

_SENT_RE = re.compile(r"is rated ([\d.]+)% positive")
_PRICE_RE = re.compile(r"price of \$([\d,]+\.\d{2})")

# Out-of-corpus URLs, one per source class. The store and forum ones are
# content-SHAPED but absent from the enumerated corpus (the sneaky case);
# the first is an off-sandbox host.
FAB_OFF_SANDBOX = "https://example.com/research/whitepaper-2024"
FAB_STORE = "http://localhost:7770/this-product-does-not-exist-xyzzy-42.html"
FAB_FORUM = "http://localhost:9999/f/technology/999999997"


def _wrong_sentiment(orig: float) -> float:
    """A deterministic wrong rating value: outside the scorer's +-1.0 percent
    tolerance AND outside the /20-scale +-0.1 tolerance, whatever the truth."""
    for delta in (37.0, 43.0, 29.0):
        cand = (orig + delta) % 100.0
        if abs(cand - orig) > 1.2 and abs(cand - orig / 20.0) > 0.15:
            return round(cand, 1)
    return round((orig + 50.0) % 100.0, 1)  # pragma: no cover - unreachable


def _corrupt_sentiment_number(md: str) -> str:
    m = _SENT_RE.search(md)
    assert m, "oracle report carries no sentiment line"
    return md[:m.start(1)] + f"{_wrong_sentiment(float(m.group(1))):.1f}" \
        + md[m.end(1):]


def _delete_first_citation(md: str, url: str) -> str:
    """Strip the first markdown link to ``url`` down to its bare label."""
    for link in iter_markdown_links(md):
        if link.url == url:
            return md[:link.start] + link.label + md[link.end:]
    raise AssertionError(f"no citation of {url} in report")


def _swap_first_citation(md: str, url: str, fab: str) -> str:
    return md.replace(f"({url})", f"({fab})", 1)


def _corrupt_price(md: str) -> str:
    m = _PRICE_RE.search(md)
    assert m, "oracle report carries no price line"
    true_val = float(m.group(1).replace(",", ""))
    wrong = f"{true_val * 2 + 11.13:,.2f}"
    return md[:m.start(1)] + wrong + md[m.end(1):]


@pytest.fixture(scope="module")
def baselines(gates_key_paths, gates_registry, gates_concept_cache,
              gates_page_stats):
    """Oracle report + baseline axis scores per task, computed once."""
    cache = gates_concept_cache or {}
    runs = []
    for path in gates_key_paths:
        ak = AnswerKey.load(path)
        rep = build_oracle_report(ak, cache=cache, registry=gates_registry)
        generic = ds.build_generic_tokens(ak)
        comp, cd = ds.score_completeness(
            rep.markdown, ak, generic=generic, cache=cache,
            page_stats=gates_page_stats, registry=gates_registry)
        fact, _ = ds.score_fact_support(rep.markdown, ak, generic=generic)
        reach, _ = ds.score_reachability(rep.cited_urls, cache,
                                         registry=gates_registry)
        runs.append({
            "ak": ak, "md": rep.markdown, "plan": rep.plan,
            "generic": generic, "comp": comp, "fact": fact, "reach": reach,
        })
    return runs


def _comp(r, md, cache, stats, registry):
    score, _ = ds.score_completeness(
        md, r["ak"], generic=r["generic"], cache=cache,
        page_stats=stats, registry=registry)
    return score


# ---------------------------------------------------------------------------
# G3
# ---------------------------------------------------------------------------

@pytest.mark.gates
def test_g3_wrong_sentiment_number_drops_completeness(
        baselines, gates_registry, gates_concept_cache, gates_page_stats):
    cache = gates_concept_cache or {}
    bad = []
    for r in baselines:
        corrupted = _corrupt_sentiment_number(r["md"])
        comp = _comp(r, corrupted, cache, gates_page_stats, gates_registry)
        if not comp < r["comp"]:
            bad.append(f"{r['ak'].task_id}: comp {r['comp']:.4f} -> {comp:.4f}")
    assert not bad, "wrong sentiment number did NOT lower completeness on:\n" \
        + "\n".join(bad)


@pytest.mark.gates
def test_g3_deleted_citation_drops_completeness_not_reach(
        baselines, gates_registry, gates_concept_cache, gates_page_stats):
    """Removing one inline citation (keeping the prose) uncovers that nugget:
    completeness strictly drops. Reach must NOT drop -- every REMAINING
    citation is still a real page, and punishing the deletion there would mean
    reach is counting prose, not citations."""
    cache = gates_concept_cache or {}
    bad = []
    for r in baselines:
        url = r["plan"]["struct_urls"][0]
        corrupted = _delete_first_citation(r["md"], url)
        comp = _comp(r, corrupted, cache, gates_page_stats, gates_registry)
        reach, _ = ds.score_reachability(ds._cited_urls(corrupted), cache,
                                         registry=gates_registry)
        if not comp < r["comp"]:
            bad.append(f"{r['ak'].task_id}: comp {r['comp']:.4f} -> {comp:.4f}")
        if reach != pytest.approx(r["reach"], abs=1e-9):
            bad.append(f"{r['ak'].task_id}: reach moved {r['reach']:.4f} -> "
                       f"{reach:.4f} on a citation DELETION")
    assert not bad, "citation deletion mis-scored on:\n" + "\n".join(bad)


@pytest.mark.gates
@pytest.mark.parametrize("fab", [FAB_OFF_SANDBOX, FAB_STORE, FAB_FORUM],
                         ids=["off_sandbox", "store_absent", "forum_absent"])
def test_g3_out_of_corpus_url_drops_reach(baselines, gates_registry,
                                          gates_concept_cache, fab):
    """Swapping one real citation for an out-of-corpus URL must strictly lower
    reach, whether the fake is off-sandbox or content-shaped on a real host
    (store product / forum thread)."""
    cache = gates_concept_cache or {}
    bad = []
    for r in baselines:
        url = r["plan"]["struct_urls"][0]
        corrupted = _swap_first_citation(r["md"], url, fab)
        reach, rd = ds.score_reachability(ds._cited_urls(corrupted), cache,
                                          registry=gates_registry)
        if not reach < r["reach"]:
            bad.append(f"{r['ak'].task_id}: reach {r['reach']:.4f} -> "
                       f"{reach:.4f} detail={rd.get('reasons')}")
    assert not bad, f"fabricated URL {fab} did NOT lower reach on:\n" \
        + "\n".join(bad)


@pytest.mark.gates
def test_g3_wrong_price_drops_fact(baselines):
    bad = []
    for r in baselines:
        corrupted = _corrupt_price(r["md"])
        fact, fd = ds.score_fact_support(corrupted, r["ak"],
                                         generic=r["generic"])
        if not fact < r["fact"]:
            bad.append(f"{r['ak'].task_id}: fact {r['fact']:.4f} -> {fact:.4f} "
                       f"(supported={fd.get('supported')} "
                       f"contradicted={fd.get('contradicted')})")
        elif fd.get("contradicted", 0) < 1:
            bad.append(f"{r['ak'].task_id}: wrong price not CONTRADICTED "
                       f"(detail={fd.get('sample')})")
    assert not bad, "wrong price did NOT lower fact on:\n" + "\n".join(bad)


@pytest.mark.gates
def test_g3_concept_cited_to_wrong_real_page_drops_completeness(
        baselines, gates_registry, gates_concept_cache, gates_page_stats):
    """Re-pointing a concept's citation at a DIFFERENT real wiki page (while
    keeping the quote) must lose the concept: the quote no longer matches the
    cited page, and citing a real-but-wrong page may not earn coverage."""
    if gates_concept_cache is None:
        pytest.skip("concept page cache fixture absent: concept perturbation "
                    "unverifiable (G1 skips its concept share the same way)")
    cache = gates_concept_cache
    wiki_urls = sorted(cache)
    bad = checked = 0
    lines = []
    for r in baselines:
        covered = r["plan"]["concept_covered_urls"]
        if not covered:
            continue
        target = covered[0]
        other = next((u for u in wiki_urls
                      if ds._page_identity(u, gates_registry)
                      != ds._page_identity(target, gates_registry)), None)
        if other is None:
            continue
        checked += 1
        corrupted = _swap_first_citation(r["md"], target, other)
        comp = _comp(r, corrupted, cache, gates_page_stats, gates_registry)
        if not comp < r["comp"]:
            bad += 1
            lines.append(f"{r['ak'].task_id}: comp {r['comp']:.4f} -> {comp:.4f}")
    assert checked, "no task offered a coverable concept to perturb"
    assert not bad, "wrong-page concept citation kept its credit on:\n" \
        + "\n".join(lines)


# ---------------------------------------------------------------------------
# SPEC_ISSUES section 2 (转 G3) pin: four-digit plain-number prices.
# Always-on (NOT gates-marked): fast, single answer key.
# ---------------------------------------------------------------------------

def _four_digit_entity():
    ak = AnswerKey.load(Path(__file__).resolve().parents[1]
                        / "data/golden/answer_keys/dr_cross_deep_0004.json")
    ents = {e.url: e for e in ak.relevant_set}
    for n in ak.vital_nuggets:
        if n.predicate != "buyer_sentiment":
            continue
        e = ents.get(n.source_url)
        try:
            if e is not None and float((e.facts or {}).get("price")) >= 1000:
                return ak, e
        except (TypeError, ValueError):
            continue
    return ak, None


@pytest.mark.parametrize("phrasing", [
    "[{name}]({url}) is priced at ${int_val}.",
    "[{name}]({url}) is priced at ${val:.2f}.",
    "[{name}]({url}): the price is {val:.2f}.",
    "[{name}]({url}) costs {int_val}. Good value.",
    "[{name}]({url}) is priced at ${comma_val}.",
    "| Product | Price |\n|---|---|\n| [{name}]({url}) | ${int_val} |",
], ids=["dollar_int", "dollar_decimals", "price_word_no_dollar",
        "costs_end_period", "comma_thousands", "table_row"])
def test_fact_axis_supports_four_digit_plain_price(phrasing):
    """Pin for docs/SPEC_ISSUES.md section 2 '四位数纯数字价格被静默漏检':
    reproduction attempted in six phrasings against a real >=1000 price entity;
    the current baseline extracts and SUPPORTS all of them (the report's
    supported=0/contradicted=0 signature does not reproduce). Would go red on
    any regression of _NUM_RE / _standalone_number for 4-digit values.

    The report also cites a wiki and a forum page so a per-source parsing
    asymmetry cannot hide (HANDOFF trap 1); those citations must not create
    claims of their own."""
    ak, e = _four_digit_entity()
    if e is None:
        pytest.skip("answer key 0004 no longer carries a >=1000 price entity")
    pv = float(e.facts["price"])
    iv = int(pv)
    claim = phrasing.format(name=e.name, url=e.url, val=pv, int_val=iv,
                            comma_val=f"{iv:,}")
    report = (
        "# Report\n\n"
        f"{claim}\n\n"
        "Background: [wireless charging]"
        "(http://localhost:8090/content/wikipedia_en_all_nopic/A/Wireless_charging) "
        "and an [owner thread](http://localhost:9999/f/technology/27823)."
    )
    fact, fd = ds.score_fact_support(report, ak)
    assert fd["supported"] == 1, fd["sample"]
    assert fd["contradicted"] == 0, fd["sample"]
    assert fd["claims_tested"] == 1, fd
    assert fact > 0.0
