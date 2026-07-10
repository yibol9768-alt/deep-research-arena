"""The two grounding axes must exclude the same URLs.

A search/navigation page (`catalogsearch/result/?q=`, a forum listing) is real
and reachable but carries no claim. `score_reachability` skips it: "not evidence,
but neither fabrication". `transport_metrics` counted it in the `pof` denominator
AND in the fabricated set, because `in_corpus` is None for a nav URL and
`bool(None)` is False.

So one honest navigation citation cut `pof` in half and reported 50% fabrication
on a report that fabricated nothing. Both invariants this module states --
`fabrication == 1 - reach` and `provenance == reach - hallucinated_grounding` --
were false whenever a lane cited a page it had legitimately browsed.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.eval.decidable_scorer as ds                      # noqa: E402
from src.eval.closed_world_eval import load_registry        # noqa: E402
from src.eval.fetch_log import load_run_evidence            # noqa: E402

NAV = "http://localhost:7770/catalogsearch/result/?q=headphones"


@pytest.fixture(scope="module")
def registry():
    reg = load_registry()
    if reg is None:
        pytest.skip("no url_registry.json")
    return reg


@pytest.fixture(scope="module")
def product(registry):
    keys = json.loads((ROOT / "data/golden/url_registry.json").read_text())["products"]
    u = f"http://localhost:7770/{next(iter(keys))}.html"
    assert registry.classify(u)["in_corpus"] is True
    return u


@pytest.fixture
def evidence(tmp_path, product):
    log = tmp_path / "r.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        {"ts": 1.0, "run_id": "r", "lane": "L", "task": "T", "kind": "mark", "phase": "start"},
        {"ts": 2.0, "run_id": "r", "kind": "search", "urls_returned": [product]},
        {"ts": 3.0, "run_id": "r", "kind": "fetch", "url": product, "status": 200},
        {"ts": 4.0, "run_id": "r", "kind": "mark", "phase": "end"},
    ]) + "\n")
    return load_run_evidence(log)


def test_a_nav_url_is_what_the_registry_says_it_is(registry):
    c = registry.classify(NAV)
    assert c["kind"] == "search_nav"
    assert c["in_corpus"] is None, "neither evidence nor fabrication"


def test_citing_a_navigation_page_changes_nothing(registry, evidence, product):
    without = ds.transport_metrics_for([product], evidence, registry=registry)
    with_nav = ds.transport_metrics_for([product, NAV], evidence, registry=registry)

    for k in ("pof", "fabrication", "provenance", "hallucinated_grounding", "n_cited"):
        assert without[k] == with_nav[k], f"{k} moved when a nav page was cited"
    assert with_nav["pof"] == 1.0 and with_nav["fabrication"] == 0.0


def test_the_invariants_hold_with_a_nav_citation(registry, evidence, product):
    cited = [product, NAV]
    m = ds.transport_metrics_for(cited, evidence, registry=registry)
    reach, _ = ds.score_reachability(cited, {}, registry=registry)

    assert abs(m["fabrication"] - (1 - reach)) < 1e-9
    assert abs(m["provenance"] - (reach - m["hallucinated_grounding"])) < 1e-9


# --- the fixture above uses only a PRODUCT, whose served spelling already equals
# its registry canonical. That is exactly why it could not see the next bug:
# `served` mixed the raw `ev.search_returned` back in, so every wiki article and
# every forum thread -- whose canonical differs from the served spelling --
# dropped out of the provenance numerator while `url_provenance` still called
# them "searched". A test whose fixture cannot vary the thing under test is not a
# test of that thing.

WIKI_SERVED = "http://localhost:8090/content/wikipedia_en_all_nopic/A/Bluetooth"
WIKI_CITED = "http://localhost:8090/wiki/Bluetooth"


@pytest.fixture
def searched_only(tmp_path):
    """A fetch-less framework: the shim returned the page, the agent never opened
    it. storm and langchain-odr can produce nothing else."""
    log = tmp_path / "s.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        {"ts": 1.0, "run_id": "s", "lane": "L", "task": "T", "kind": "mark", "phase": "start"},
        {"ts": 2.0, "run_id": "s", "kind": "search", "urls_returned": [WIKI_SERVED]},
        {"ts": 3.0, "run_id": "s", "kind": "mark", "phase": "end"},
    ]) + "\n")
    return load_run_evidence(log)


def test_a_searched_wiki_citation_has_provenance(registry, searched_only):
    m = ds.transport_metrics_for([WIKI_CITED], searched_only, registry=registry)
    assert m["url_provenance"] == {
        registry.classify(WIKI_CITED)["canonical"]: "searched"}
    assert m["provenance"] == 1.0, \
        "the same call says 'searched' and then scores provenance 0"
    assert m["snippet_only"] == 1.0 and m["hallucinated_grounding"] == 0.0


def test_the_invariant_holds_for_a_wiki_page_not_just_a_product(registry, searched_only):
    cited = [WIKI_CITED]
    m = ds.transport_metrics_for(cited, searched_only, registry=registry)
    reach, _ = ds.score_reachability(cited, {}, registry=registry)
    assert abs(m["provenance"] - (reach - m["hallucinated_grounding"])) < 1e-9


def test_wiki_and_product_citations_are_scored_by_the_same_rule(registry, searched_only, product, tmp_path):
    """`provenance` must not depend on which sandbox source the page came from."""
    log = tmp_path / "p.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        {"ts": 1.0, "run_id": "p", "lane": "L", "task": "T", "kind": "mark", "phase": "start"},
        {"ts": 2.0, "run_id": "p", "kind": "search", "urls_returned": [product]},
        {"ts": 3.0, "run_id": "p", "kind": "mark", "phase": "end"},
    ]) + "\n")
    prod_ev = load_run_evidence(log)

    wiki = ds.transport_metrics_for([WIKI_CITED], searched_only, registry=registry)
    prod = ds.transport_metrics_for([product], prod_ev, registry=registry)
    assert wiki["provenance"] == prod["provenance"] == 1.0


# --- forum thread IDENTITY: the slug is decorative -------------------------
#
# A Postmill thread's identity is its numeric id. `/f/<forum>/<id>/<slug>` (the
# served spelling, carrying a title slug and possibly a decorative /-/comment
# tail) and `/f/<forum>/<id>` (a bare citation) are ONE thread, and even a
# different -- misattributed -- forum segment resolves to the same canonical id.
# The product/wiki tests above could not exercise this: a product's served
# spelling equals its registry canonical, and a wiki page varies only its path
# alias, neither of which carries a per-thread decorative slug. Forum identity
# had zero coverage (HANDOFF trap 1: vary the SOURCE, here down to the forum's
# own slug shape). Fixture uses a real submission id from the frozen registry.

FORUM_HOST = "http://localhost:9999"


@pytest.fixture(scope="module")
def forum_thread(registry):
    """A real Postmill submission id and its registry-canonical forum."""
    subs = getattr(registry, "submissions", None)
    if not subs:
        pytest.skip("registry has no forum submissions")
    sub_id, canon_forum = next(iter(subs.items()))
    return sub_id, canon_forum


def test_forum_slug_and_no_slug_and_wrong_forum_share_one_identity(registry, forum_thread):
    sub_id, forum = forum_thread
    with_slug = registry.classify(f"{FORUM_HOST}/f/{forum}/{sub_id}/best-thread-ever")
    no_slug = registry.classify(f"{FORUM_HOST}/f/{forum}/{sub_id}")
    # A decorative WRONG forum segment (misattribution) + a slug: same id.
    wrong_forum = registry.classify(f"{FORUM_HOST}/f/some-other-forum/{sub_id}/a-slug")
    for c in (with_slug, no_slug, wrong_forum):
        assert c["in_corpus"] is True and c["kind"] == "content"
    assert with_slug["canonical"] == no_slug["canonical"] == wrong_forum["canonical"]
    # The wrong-forum citation still resolves, but is flagged as a misattribution.
    assert wrong_forum["forum_mismatch"] is True
    assert no_slug["forum_mismatch"] is False


def test_a_searched_forum_thread_cited_without_its_slug_has_provenance(
        registry, forum_thread, tmp_path):
    """The shim served the thread WITH its slug; the agent cited it WITHOUT.
    Because identity is the id, `served` and `cited` must unify, so provenance
    is credited exactly as for a product or a wiki page -- not dropped because
    the two spellings differ (the `served` raw-spelling bug, on the forum side)."""
    sub_id, forum = forum_thread
    served = f"{FORUM_HOST}/f/{forum}/{sub_id}/the-thread-title-slug"
    cited = f"{FORUM_HOST}/f/{forum}/{sub_id}"
    log = tmp_path / "f.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        {"ts": 1.0, "run_id": "f", "lane": "L", "task": "T", "kind": "mark", "phase": "start"},
        {"ts": 2.0, "run_id": "f", "kind": "search", "urls_returned": [served]},
        {"ts": 3.0, "run_id": "f", "kind": "mark", "phase": "end"},
    ]) + "\n")
    ev = load_run_evidence(log)
    m = ds.transport_metrics_for([cited], ev, registry=registry)
    assert m["url_provenance"] == {registry.classify(cited)["canonical"]: "searched"}
    assert m["provenance"] == 1.0
    assert m["snippet_only"] == 1.0 and m["hallucinated_grounding"] == 0.0


def test_forum_thread_scored_by_the_same_rule_as_product_and_wiki(
        registry, forum_thread, searched_only, tmp_path):
    """provenance must not depend on the source: a forum thread cited under a
    decorative slug scores the same 1.0 a wiki page does."""
    sub_id, forum = forum_thread
    served = f"{FORUM_HOST}/f/{forum}/{sub_id}/slug-here"
    cited = f"{FORUM_HOST}/f/{forum}/{sub_id}"
    log = tmp_path / "ff.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        {"ts": 1.0, "run_id": "ff", "lane": "L", "task": "T", "kind": "mark", "phase": "start"},
        {"ts": 2.0, "run_id": "ff", "kind": "search", "urls_returned": [served]},
        {"ts": 3.0, "run_id": "ff", "kind": "mark", "phase": "end"},
    ]) + "\n")
    forum_ev = load_run_evidence(log)

    forum_m = ds.transport_metrics_for([cited], forum_ev, registry=registry)
    wiki_m = ds.transport_metrics_for([WIKI_CITED], searched_only, registry=registry)
    assert forum_m["provenance"] == wiki_m["provenance"] == 1.0
