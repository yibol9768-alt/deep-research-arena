"""Regression tests for the Route-B search pollution incident.

The negative titles below are taken from the real audio pilot: iPhone battery,
basement waterproofing, apartment radiators, deep-learning inputs and unrelated
Soundcore products were returned for Ortizan/Flare-2 research queries.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from integrations.search_shim import backend


def _hit(
    title: str,
    content: str = "",
    *,
    source: str = "reddit",
    slug: str | None = None,
) -> backend.SearchHit:
    slug = slug or title.lower().replace(" ", "-")
    return backend.SearchHit(
        url=f"http://localhost:9999/{slug}",
        title=title,
        content=content,
        score=0.0,
        source=source,
    )


@pytest.mark.parametrize(
    ("query", "relevant", "polluted"),
    [
        (
            "Ortizan 40W portable Bluetooth speaker under $60 budget",
            _hit(
                "Ortizan 40W portable Bluetooth speaker",
                "IPX7, dual pairing and a 15-hour battery claim.",
                source="shopping",
                slug="ortizan-40w",
            ),
            _hit(
                "How to make a monthly baby budget",
                "Budgeting for diapers, food and childcare.",
                slug="baby-budget",
            ),
        ),
        (
            "Soundcore Flare 2 battery life volume lights charging time",
            _hit(
                "Anker Soundcore Flare 2 Bluetooth speaker",
                "Twelve-hour battery life varies with volume and lights.",
                source="shopping",
                slug="flare-2",
            ),
            _hit(
                "3rd swollen iPhone battery",
                "The phone battery expanded while charging.",
                slug="iphone-battery",
            ),
        ),
        (
            "portable Bluetooth speaker comparison for a balcony",
            _hit(
                "Portable Bluetooth speaker comparison",
                "Balcony listening tests compare two wireless speakers.",
                slug="speaker-comparison",
            ),
            _hit(
                "Cross-validation comparison for machine learning",
                "A comparison of neural-network training methods.",
                slug="ml-comparison",
            ),
        ),
        (
            "passive radiator speaker mechanism",
            _hit(
                "Passive radiator loudspeaker enclosure",
                "The passive diaphragm resonates with the enclosed air mass.",
                source="wiki",
                slug="passive-radiator",
            ),
            _hit(
                "Your annual apartment radiator reminder",
                "A steam radiator can make a New York apartment hot.",
                slug="apartment-radiator",
            ),
        ),
        (
            "Soundcore Flare 2 IPX7 waterproof test review",
            _hit(
                "Soundcore Flare 2 IPX7 waterproof speaker",
                "The listing claims an IPX7 rating.",
                source="shopping",
                slug="flare-ipx7",
            ),
            _hit(
                "Waterproofing and insulating an interior basement",
                "Advice about basement walls and moisture.",
                slug="basement-waterproofing",
            ),
        ),
    ],
)
def test_real_incident_pollution_is_removed(query, relevant, polluted):
    ranked = backend._rerank_hits(query, [polluted, relevant], 10)
    assert [row.url for row in ranked] == [relevant.url]
    assert ranked[0].score == 1.0


def test_exact_tokens_prevent_anc_substring_matches():
    assert backend._score_reddit(
        "ANC headphones",
        "Headphone performance discussion",
        "A general performance comparison without active noise control.",
    ) == 0.0
    assert backend._score_reddit(
        "ANC headphones",
        "ANC headphone comparison",
        "Active noise cancelling performance.",
    ) > 0.0


def test_exact_model_phrase_beats_same_brand_noise():
    query = "Soundcore Flare 2 official specifications"
    exact = _hit(
        "Anker Soundcore Flare 2 Bluetooth speaker",
        "Flare 2 output and battery specifications.",
        source="shopping",
        slug="flare-2-exact",
    )
    same_brand = _hit(
        "Anker Soundcore Motion Boom outdoor speaker",
        "Soundcore product specifications.",
        source="shopping",
        slug="motion-boom",
    )
    headphone = _hit(
        "Soundcore Q45 Momentum 3 HD560S in one week",
        "A headphone review.",
        slug="soundcore-q45",
    )
    ranked = backend._rerank_hits(query, [same_brand, headphone, exact], 10)
    assert [row.url for row in ranked] == [exact.url]


def test_single_brand_with_model_value_rejects_accessory_and_wrong_wattage():
    query = "Ortizan 40W portable Bluetooth speaker Amazon price 2026"
    exact = _hit(
        "Ortizan portable Bluetooth speaker 40W",
        "IPX7 speaker with dual pairing.",
        source="shopping",
        slug="ortizan-40w-exact",
    )
    accessory = _hit(
        "Khanka case for Ortizan portable Bluetooth speaker",
        "Protective travel case only.",
        source="shopping",
        slug="ortizan-case",
    )
    wrong_model = _hit(
        "Ortizan portable Bluetooth speaker 24W",
        "IPX7 speaker with dual pairing.",
        source="shopping",
        slug="ortizan-24w",
    )
    rows = backend._rerank_hits(query, [accessory, wrong_model, exact], 10)
    assert [row.url for row in rows] == [exact.url]


def test_technical_acronyms_are_properties_not_product_identity():
    row = _hit(
        "Anker Soundcore Flare 2 Bluetooth speaker",
        "Official product specifications.",
        source="shopping",
        slug="flare-tech",
    )
    rows = backend._rerank_hits(
        "Soundcore Flare 2 codec SBC AAC aptX LDAC THD RMS", [row], 5
    )
    assert len(rows) == 1
    assert rows[0].url == row.url


def test_comparison_query_can_keep_each_named_side_without_generic_noise():
    query = "Compare Ortizan 40W Bluetooth speaker with Soundcore Flare 2"
    ortizan = _hit(
        "Ortizan 40W Bluetooth speaker",
        "Portable speaker product page.",
        source="shopping",
        slug="ortizan-side",
    )
    flare = _hit(
        "Soundcore Flare 2 Bluetooth speaker",
        "Portable speaker product page.",
        source="shopping",
        slug="flare-side",
    )
    noise = _hit(
        "D best deal with varying number of inputs",
        "Deep-learning comparison with variable input counts.",
        slug="deep-learning-inputs",
    )
    ranked = backend._rerank_hits(query, [noise, ortizan, flare], 10)
    assert {row.url for row in ranked} == {ortizan.url, flare.url}


def test_comparison_identity_groups_keep_either_named_side():
    bose = _hit("Bose QuietComfort headphones", slug="bose")
    sony = _hit("Sony wireless headphones", slug="sony")
    rows = backend._rerank_hits("Compare Bose versus Sony headphones", [bose, sony], 5)
    assert {row.url for row in rows} == {bose.url, sony.url}
    rows = backend._rerank_hits("Bose compared with Sony headphones", [bose, sony], 5)
    assert {row.url for row in rows} == {bose.url, sony.url}


def test_context_free_generic_query_is_not_overclaimed():
    """With only 'budget', the shim has no domain context and keeps exact hits."""
    rows = backend._rerank_hits(
        "budget",
        [_hit("Baby budget"), _hit("Speaker budget")],
        10,
    )
    assert len(rows) == 2


def test_source_quota_merge_preserves_each_nonempty_source():
    groups = {
        "shopping": [_hit("Product", source="shopping", slug="p")],
        "reddit": [_hit("Community", source="reddit", slug="r")],
        "wiki": [_hit("Concept", source="wiki", slug="w")],
    }
    rows = backend._merge_source_hits("portable speaker comparison", groups, 3)
    assert {row.source for row in rows} == {"shopping", "reddit", "wiki"}


def test_concept_query_prioritises_wiki_without_padding():
    groups = {
        "shopping": [_hit("Product", source="shopping", slug="p")],
        "reddit": [],
        "wiki": [_hit("IP code", source="wiki", slug="w")],
    }
    rows = backend._merge_source_hits("IPX7 definition", groups, 2)
    assert [row.source for row in rows] == ["wiki"]


def test_concept_query_honours_explicit_multi_source_request():
    groups = {
        "shopping": [_hit("IPX7 speaker", source="shopping", slug="p")],
        "wiki": [_hit("IP code", source="wiki", slug="w")],
    }
    rows = backend._merge_source_hits(
        "IPX7 definition",
        groups,
        2,
        explicit_sources=True,
    )
    assert [row.source for row in rows] == ["wiki", "shopping"]


def test_multi_item_shopping_query_is_split_into_named_product_phrases():
    assert backend._shopping_query_variants(
        "home fitness resistance bands yoga mat dumbbell foam roller"
    ) == (
        "resistance band",
        "yoga mat",
        "dumbbell",
        "foam roller",
    )


def test_decomposed_product_heads_reject_known_lexical_homonyms():
    yoga_sandal = _hit(
        "Yoga Mat Leather Flip Flops Sandals",
        source="shopping",
        slug="yoga-sandal",
    )
    hair_roller = _hit(
        "Foam Sponge Hair Rollers and Curlers",
        source="shopping",
        slug="hair-roller",
    )
    assert backend._product_variant_conflicts("yoga mat", yoga_sandal)
    assert backend._product_variant_conflicts("foam roller", hair_roller)


def test_exact_product_identity_is_never_split():
    query = "Ortizan 40W portable Bluetooth speaker under $60 budget"
    assert backend._shopping_query_variants(query) == (query,)


def test_long_forum_query_accepts_an_exact_topic_phrase():
    row = _hit(
        "Coffee grinder still working after eleven years",
        "The burrs remain aligned after daily use.",
        slug="coffee-grinder",
    )
    rows = backend._rerank_hits(
        "coffee grinder burr durability long term owner experience",
        [row],
        5,
        allow_phrase_relaxation=True,
    )
    assert [item.url for item in rows] == [row.url]


def test_concept_only_search_does_not_query_commerce_or_forum(monkeypatch):
    wiki = _hit("IP code", source="wiki", slug="ip-code")

    def unexpected(*_args, **_kwargs):
        raise AssertionError("concept-only query reached a non-canonical source")

    monkeypatch.setattr(backend, "_search_shopping", unexpected)
    monkeypatch.setattr(backend, "_search_reddit", unexpected)
    monkeypatch.setattr(backend, "_search_kiwix", lambda *_a, **_k: [wiki])
    assert backend.search("IPX7 definition", max_results=5) == [wiki]


def test_search_respects_single_source_include_filter(monkeypatch):
    wiki = _hit("Loudspeaker", source="wiki", slug="wiki-only")

    def unexpected(*_args, **_kwargs):
        raise AssertionError("an excluded source was queried")

    monkeypatch.setattr(backend, "_search_shopping", unexpected)
    monkeypatch.setattr(backend, "_search_reddit", unexpected)
    monkeypatch.setattr(backend, "_search_kiwix", lambda *_a, **_k: [wiki])
    rows = backend.search("loudspeaker", include_domains=["wiki"])
    assert rows == [wiki]


def test_kiwix_variants_extract_explicit_audio_concepts():
    query = (
        "Compare speaker IPX7 scope, passive radiator mechanism, THD distortion, "
        "and RMS watt output"
    )
    assert backend._kiwix_query_variants(query) == (
        "IP code",
        "Passive radiator (speaker)",
        "Total harmonic distortion",
        "Audio power",
    )


def test_kiwix_variants_use_frozen_audio_concept_pages():
    assert backend._kiwix_query_variants(
        "360 degree speaker dispersion off-axis acoustics"
    ) == ("Loudspeaker acoustics",)
    assert backend._kiwix_query_variants(
        "Soundcore Flare 2 360-degree sound passive radiator driver specs"
    ) == (
        "Passive radiator (speaker)",
        "Loudspeaker acoustics",
    )
    assert backend._kiwix_query_variants(
        "Bluetooth hi-res audio codec aptX LDAC"
    ) == (
        "LDAC (codec)",
        "High-resolution audio",
        "Bluetooth",
    )


def test_kiwix_variants_cover_explicit_general_research_concepts():
    assert backend._kiwix_query_variants(
        "artificial intelligence large language model job displacement"
    ) == (
        "Artificial intelligence",
        "Large language model",
        "Technological unemployment",
    )
    assert backend._kiwix_query_variants(
        "noise cancelling wireless headphones under 100"
    ) == ("Active noise control",)


def test_kiwix_uses_short_concept_queries_and_filters_rows(monkeypatch):
    calls: list[str] = []

    def fake_get_source(source, base, public, path, *, params=None, timeout=20):
        pattern = params["pattern"]
        calls.append(pattern)
        if pattern == "IP code":
            text = """
            <ul class="results">
              <li><a href="/content/wiki/IP_code">IP code</a>
                  <cite>IPX7 covers temporary water immersion.</cite></li>
              <li><a href="/content/wiki/ZIP_Code">ZIP Code</a>
                  <cite>A postal routing code.</cite></li>
            </ul>
            """
        else:
            text = """
            <ul class="results">
              <li><a href="/content/wiki/Passive_radiator">Passive radiator (speaker)</a>
                  <cite>A passive speaker diaphragm driven by cabinet pressure.</cite></li>
              <li><a href="/content/wiki/Radiator">Radiator</a>
                  <cite>A heating appliance.</cite></li>
            </ul>
            """
        return SimpleNamespace(text=text)

    monkeypatch.setattr(backend, "_get_source", fake_get_source)
    rows = backend._search_kiwix("IPX7 and passive radiator speaker", 4)
    assert calls == ["IP code", "Passive radiator (speaker)"]
    assert {row.title for row in rows} == {"IP code", "Passive radiator (speaker)"}


def test_product_named_wiki_query_returns_empty_instead_of_alexa_pollution(monkeypatch):
    html = """
    <ul class="results">
      <li><a href="/content/wiki/Amazon_Alexa">Amazon Alexa</a>
          <cite>A virtual assistant and smart speaker platform.</cite></li>
    </ul>
    """
    monkeypatch.setattr(
        backend,
        "_get_source",
        lambda *_a, **_k: SimpleNamespace(text=html),
    )
    assert backend._search_kiwix(
        "Soundcore Flare 2 Wikipedia specifications", 5
    ) == []


def test_kiwix_keeps_only_the_best_page_per_explicit_concept(monkeypatch):
    html = """
    <ul class="results">
      <li><a href="/content/wiki/Bluetooth">Bluetooth</a>
          <cite>A short-range wireless technology standard.</cite></li>
      <li><a href="/content/wiki/Bluetooth_stack">Bluetooth stack</a>
          <cite>Software implementing the Bluetooth protocol.</cite></li>
      <li><a href="/content/wiki/Bluetooth_mesh">Bluetooth mesh networking</a>
          <cite>A Bluetooth networking profile.</cite></li>
    </ul>
    """
    monkeypatch.setattr(
        backend,
        "_get_source",
        lambda *_a, **_k: SimpleNamespace(text=html),
    )
    rows = backend._search_kiwix("Bluetooth codec definition", 5)
    assert [row.title for row in rows] == ["Bluetooth"]


def test_shopping_reranks_model_and_drops_unrelated_battery(monkeypatch):
    html = """
    <ul class="products-grid">
      <li class="item product product-item">
        <a class="product-item-link" href="/iphone-battery.html">iPhone battery case</a>
      </li>
      <li class="item product product-item">
        <a class="product-item-link" href="/flare-2.html">Anker Soundcore Flare 2 speaker</a>
        <span data-price-amount="53.49"></span>
      </li>
    </ul>
    """
    monkeypatch.setattr(
        backend,
        "_get_source",
        lambda *_a, **_k: SimpleNamespace(text=html),
    )
    rows = backend._search_shopping("Soundcore Flare 2 battery specs", 5)
    assert [row.url for row in rows] == ["http://localhost:7770/flare-2.html"]


def test_shopping_trusts_hidden_category_match_only_for_one_topic(monkeypatch):
    html = """
    <ul class="products-grid">
      <li class="item product product-item">
        <a class="product-item-link" href="/sony-xm4.html">Sony WH-1000XM4</a>
      </li>
    </ul>
    """
    monkeypatch.setattr(
        backend,
        "_get_source",
        lambda *_a, **_k: SimpleNamespace(text=html),
    )

    assert backend._search_shopping("headphones", 5)
    assert backend._search_shopping(
        "portable Bluetooth speaker battery life", 5
    ) == []


def test_forum_index_drops_iphone_battery_from_speaker_query(monkeypatch):
    html = """
    <article class="submission">
      <a class="submission__link" href="/f/gadgets/1/speaker-battery">Speaker battery</a>
      <a href="/f/gadgets/1/speaker-battery">comments</a>
      <div class="submission__body">Portable Bluetooth speaker battery life.</div>
    </article>
    <article class="submission">
      <a class="submission__link" href="/f/iphone/2/swollen">Swollen battery</a>
      <a href="/f/iphone/2/swollen">comments</a>
      <div class="submission__body">An iPhone battery failed while charging.</div>
    </article>
    """
    monkeypatch.setattr(
        backend,
        "_get_source",
        lambda *_a, **_k: SimpleNamespace(text=html),
    )
    rows = backend._search_reddit_index("portable Bluetooth speaker battery life", 5)
    assert len(rows) == 1
    assert "/f/gadgets/1/" in rows[0].url


def test_relevance_scores_are_bounded_and_sorted():
    rows = backend._rerank_hits(
        "passive radiator speaker",
        [
            _hit("Speaker with radiator", "passive enclosure", slug="weak"),
            _hit("Passive radiator speaker", "speaker mechanism", slug="strong"),
        ],
        10,
    )
    assert rows
    assert all(
        backend.SEARCH_MIN_RELATIVE_SCORE <= row.score <= 1.0
        for row in rows
    )
    assert [row.score for row in rows] == sorted(
        (row.score for row in rows), reverse=True
    )
