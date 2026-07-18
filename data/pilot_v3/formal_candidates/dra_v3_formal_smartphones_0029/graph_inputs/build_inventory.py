#!/usr/bin/env python3
"""Build the reviewed Q29 graph inventory from the frozen atomic capture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
CAPTURE = ROOT / "data/evidence_graph/captures/v3-corpus-formal-smartphones-0029-display-value-20260716-r1-20260716T161756Z"
AUTHORING = ROOT / "data/pilot_v3/formal_candidates/dra_v3_formal_smartphones_0029/graph_inputs/case_authoring_source.json"
OUT = ROOT / "data/pilot_v3/formal_candidates/dra_v3_formal_smartphones_0029/graph_inputs/inventory.json"
SNAPSHOT = "dra-v3-formal-smartphones-0029-display-value-20260716-r1"
CASE_URL = "http://case-spec.local/dra_v3_formal_smartphones_0029"
CLUSTER = "smartphone_display_value_and_personal_threshold"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def span(span_id: str, quote: str, occurrence: int = 0) -> dict[str, object]:
    return {
        "support_span_id": span_id,
        "exact_quote": quote,
        "occurrence": occurrence,
        "support_type": "body",
    }


def typed_node(
    evidence_id: str,
    node_type: str,
    subject: str,
    predicate: str,
    obj: object,
    source_url: str,
    spans: list[dict[str, object]],
    accepted_phrase: str,
    role: str,
    scope: str,
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "node_type": node_type,
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "source_url": source_url,
        "support_spans": spans,
        "verifier": {
            "kind": "typed_claim",
            "matcher": "normalized_text",
            "accepted_phrases": [accepted_phrase],
            "normalizers": ["casefold", "whitespace", "punctuation", "hyphen"],
        },
        "metadata": {
            "acceptable_source_roles": [role],
            "critical": True,
            "scope": scope,
            "topic_cluster": CLUSTER,
        },
    }


def assertion_node(
    evidence_id: str,
    subject: str,
    obj: str,
    source_url: str,
    spans: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "node_type": "assertion",
        "subject": subject,
        "predicate": "states",
        "object": obj,
        "source_url": source_url,
        "support_spans": spans,
        "verifier": {"kind": "quoted_assertion"},
        "metadata": {"topic_cluster": CLUSTER},
    }


def derived_node(
    evidence_id: str,
    node_type: str,
    subject: str,
    predicate: str,
    obj: object,
    rule_id: str,
    *,
    decision: bool = False,
) -> dict[str, object]:
    metadata: dict[str, object] = {"rule_id": rule_id, "topic_cluster": CLUSTER}
    if decision:
        metadata["oracle_unique_or_admissible"] = True
    return {
        "evidence_id": evidence_id,
        "node_type": node_type,
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "source_url": CASE_URL,
        "verifier": {"kind": "deterministic_rule"},
        "metadata": metadata,
    }


def main() -> None:
    manifest = json.loads((CAPTURE / "capture_manifest.json").read_text(encoding="utf-8"))
    captured_documents = json.loads((CAPTURE / "documents.json").read_text(encoding="utf-8"))["documents"]

    search_rows = [
        ("tcl_lcd", "search_tcl_lcd", "ev_tcl_lcd_snapshot"),
        ("samsung_a51_amoled", "search_samsung_a51_amoled", "ev_samsung_a51_amoled_snapshot"),
        ("motorola_edge_oled", "search_motorola_edge_oled", "ev_motorola_90hz_oled_snapshot"),
        ("xperia_oled", "search_xperia_oled", "ev_xperia_4k_120hz_oled_snapshot"),
        ("refresh_experience", "search_refresh_experience", "prop_refresh_value_disagreement"),
        ("eye_strain_experience", "search_eye_strain_experience", "prop_oled_eye_strain_experience"),
        ("lcd_better_experience", "search_lcd_better_experience", "prop_lcd_brightness_disagreement"),
        ("lcd_mechanism", "search_lcd_mechanism", "prop_lcd_light_modulation"),
        ("oled_mechanism", "search_oled_mechanism", "prop_oled_pixel_emission"),
        ("high_refresh_definition", "search_high_refresh_definition", "prop_refresh_rate_scope"),
        ("luminance", "search_luminance", "prop_luminance_brightness_scope"),
        ("contrast", "search_contrast", "prop_contrast_measurement_context"),
        ("retina_threshold", "search_retina_threshold", "prop_pixel_threshold_distance"),
    ]
    if len(search_rows) != len(manifest["searches"]):
        raise RuntimeError("capture search count changed")

    documents: list[dict[str, object]] = []
    search_nodes: list[dict[str, object]] = []
    discovery_edges: list[dict[str, object]] = []
    for index, ((suffix, search_node_id, content_node_id), capture_search) in enumerate(
        zip(search_rows, manifest["searches"]), start=1
    ):
        response_path = CAPTURE / capture_search["response_path"]
        response = json.loads(response_path.read_text(encoding="utf-8"))
        source_url = (
            "http://localhost:8081/search?capture_run="
            f"{manifest['run_id']}&request_id={response['request_id']}"
        )
        documents.append(
            {
                "registry_id": f"reg_search_{suffix}",
                "source_url": source_url,
                "source_type": "search_result",
                "content_sha256": sha256(response_path.read_bytes()),
                "blob_path": response_path.relative_to(ROOT).as_posix(),
                "in_corpus": True,
            }
        )
        search_nodes.append(
            {
                "evidence_id": search_node_id,
                "node_type": "search_result",
                "subject": capture_search["query"],
                "predicate": "returned",
                "object": capture_search["required_urls"],
                "source_url": source_url,
                "body_support": False,
                "search_snippet_support": True,
                "verifier": {"kind": "search_observation"},
                "metadata": {
                    "discovery_root": True,
                    "discovery_root_policy": "search_result",
                    "topic_cluster": CLUSTER,
                },
            }
        )
        discovery_edges.append(
            {
                "edge_id": f"edge_discover_{suffix}",
                "source_id": content_node_id,
                "relation": "DISCOVERABLE_FROM",
                "target_id": search_node_id,
                "discovery_method": "S",
                "discovery_order": 1,
            }
        )

    for document in captured_documents:
        documents.append(
            {
                "registry_id": document["registry_id"],
                "source_url": document["source_url"],
                "source_type": document["source_type"],
                "content_sha256": document["content_sha256"],
                "blob_path": (CAPTURE / document["blob_path"]).relative_to(ROOT).as_posix(),
                "in_corpus": True,
            }
        )
    documents.append(
        {
            "registry_id": "reg_case_spec_smartphone_display_value",
            "source_url": CASE_URL,
            "source_type": "case_spec",
            "content_sha256": sha256(AUTHORING.read_bytes()),
            "blob_path": AUTHORING.relative_to(ROOT).as_posix(),
            "in_corpus": True,
        }
    )

    urls = {row["registry_id"]: row["source_url"] for row in captured_documents}
    nodes: list[dict[str, object]] = list(search_nodes)

    nodes.extend(
        [
            typed_node(
                "ev_tcl_lcd_snapshot",
                "attribute",
                "frozen TCL 10L listing",
                "advertises_snapshot",
                "179.99 dollars, a 6.53-inch FHD+ LCD, no posted review, and seller display-enhancement claims",
                urls["reg_magento_tcl_10l_lcd"],
                [
                    span(
                        "span_tcl_title",
                        'TCL 10L, Unlocked Android Smartphone with 6.53" FHD + LCD Display, 48MP Quad Rear Camera System, 64GB+6GB RAM, 4000mAh Battery',
                    ),
                    span(
                        "span_tcl_price",
                        "In stock SKU B087LYQ22N Be the first to review this product $179.99 Color Arctic White Mariana Blue Size 256GB 64GB Qty Add to Cart Add to Wish List Add to Compare",
                    ),
                    span(
                        "span_tcl_display",
                        '6.53” FHD+ Dotch LCD display, powered by NXTVISION, will upgrade your visual experience with the sharper details, vibrant images and allow you to enjoy true-to-life color accuracy in everything you present.',
                    ),
                ],
                "The frozen TCL 10L listing advertises a 179.99 dollar 6.53-inch FHD+ LCD configuration and seller display-enhancement wording while showing no posted review; it is a catalog snapshot, not an independent display measurement.",
                "product",
                "catalog_snapshot_not_independent_display_test",
            ),
            typed_node(
                "ev_samsung_a51_amoled_snapshot",
                "attribute",
                "frozen Samsung Galaxy A51 listing",
                "advertises_snapshot",
                "134.99 dollars, a 6.5-inch Super AMOLED display, no posted review, and Verizon-only compatibility",
                urls["reg_magento_samsung_a51_amoled"],
                [
                    span(
                        "span_a51_title",
                        'Samsung Galaxy A51 LTE Verizon | 6.5" AMOLED Screen | 128GB of Storage | Long Lasting Battery | Single SIM | 2020 Model | US Version & Warranty| Black - (SM-A515UZKNVZW)',
                    ),
                    span(
                        "span_a51_price",
                        "In stock SKU B08B8JSG95 Be the first to review this product $134.99 Style A01 A11 A51 A51G – 5G A71 – 5G Qty Add to Cart Add to Wish List Add to Compare",
                    ),
                    span("span_a51_carrier", "Works with VERIZON Network Only!"),
                ],
                "The frozen Samsung Galaxy A51 listing advertises a 134.99 dollar 6.5-inch Super AMOLED configuration, no posted review, and Verizon-only compatibility; its lower snapshot price does not prove a better or worse display than the other listings.",
                "product",
                "catalog_snapshot_with_configuration_caveat",
            ),
            typed_node(
                "ev_motorola_90hz_oled_snapshot",
                "attribute",
                "frozen Motorola Edge 20 Lite listing",
                "advertises_snapshot",
                "360 dollars, a 6.7-inch FHD+ 90 Hz OLED, five posted reviews, and an international model without a US warranty",
                urls["reg_magento_motorola_edge_20_lite_oled"],
                [
                    span(
                        "span_motorola_title",
                        'Motorola Edge 20 Lite (128GB, 6GB) 6.7" 90Hz OLED, 108MP Triple Camera, Dual SIM (Euro 5G / Global 4G LTE) GSM Unlocked (T-Mobile, AT&T, Metro) International Model XT2139-1 (w/ 128GB SD, Green)',
                    ),
                    span(
                        "span_motorola_price",
                        "In stock SKU B09HN52ST3 Rating: 80 % of 100 5 Reviews Add Your Review $360.00 Color Electric Graphite Lagoon Green Qty Add to Cart Add to Wish List Add to Compare",
                    ),
                    span(
                        "span_motorola_display",
                        '6.7" FHD+ Ultra-wide Max Vision display, 1080 x 2400 pixels, 90Hz refresh rate, Android 11',
                    ),
                    span(
                        "span_motorola_warranty",
                        "International Model, Does not have US Warranty.",
                    ),
                ],
                "The frozen Motorola Edge 20 Lite listing advertises a 360 dollar international configuration with a 6.7-inch FHD+ 90 Hz OLED, five posted reviews, and no US warranty; these are listing-level facts, not controlled quality results.",
                "product",
                "catalog_snapshot_with_warranty_caveat",
            ),
            typed_node(
                "ev_xperia_4k_120hz_oled_snapshot",
                "attribute",
                "frozen Xperia 1 III bundle listing",
                "advertises_snapshot",
                "1496 dollars, a 6.5-inch 4K HDR OLED at 120 Hz, twelve posted reviews, and phone-only or headphone-bundle style choices",
                urls["reg_magento_xperia_1_iii_oled"],
                [
                    span(
                        "span_xperia_title",
                        'Xperia 1 III - 5G Smartphone with 120Hz 6.5" 21:9 4K HDR OLED Display with Sony WF-1000XM3 Industry Leading Noise Canceling Truly Wireless Earbuds Headset/Headphones',
                    ),
                    span(
                        "span_xperia_price_bundle",
                        "In stock SKU B097QLK1N9 Rating: 72 % of 100 12 Reviews Add Your Review $1,496.00 Color Black Purple Style Phone only Phone Only w/ WF1000XM3 Headphones Qty Add to Cart Add to Wish List Add to Compare",
                    ),
                    span(
                        "span_xperia_display_claim",
                        "World’s first smartphone with 120Hz 6.5” 4K HDR OLED display",
                    ),
                ],
                "The frozen Xperia listing advertises a 1496 dollar phone or headphone-bundle configuration with a 6.5-inch 4K HDR OLED at 120 Hz and twelve posted reviews; it does not isolate the screen's share of price or independently measure display quality.",
                "product",
                "catalog_bundle_snapshot_not_screen_value_test",
            ),
        ]
    )

    refresh_url = urls["reg_postmill_iphone_120hz_noticeability"]
    refresh_spans = [
        span(
            "span_refresh_use_case",
            "I'll mostly be calling, texting, and browsing a few social media apps as well as youtube. I don't play mobile games very often if ever.",
        ),
        span(
            "span_refresh_nonessential",
            "At first it was super noticeable but after time the 60hz didn't feel unusable.",
        ),
        span("span_refresh_positive", "I love the 120hz."),
        span(
            "span_refresh_savings",
            "Yes it is noticeable. But in my experience (and I’m a sucker for HRR) on a phone it’s not absolutely needed, if the savings are worth it.",
        ),
    ]
    nodes.append(
        typed_node(
            "prop_refresh_value_disagreement",
            "proposition",
            "phone users discussing 60 Hz and 120 Hz",
            "report_scoped_disagreement",
            "some users call 120 Hz important or clearly noticeable, while others say 60 Hz remained usable or the saving could matter for light phone use",
            refresh_url,
            refresh_spans,
            "A phone-refresh-rate discussion contains materially different individual outcomes: some users strongly value 120 Hz, while another says 60 Hz did not become unusable and another says high refresh is noticeable but not essential when savings matter; the original poster mainly calls, texts, browses, and watches YouTube.",
            "community",
            "individual_experiences_and_disagreement_not_prevalence",
        )
    )
    nodes.append(
        assertion_node(
            "assert_refresh_value_disagreement",
            "120 Hz phone discussion",
            "participants report different importance and adaptation outcomes for 60 Hz and 120 Hz",
            refresh_url,
            [
                span(
                    "span_assert_refresh_nonessential",
                    "At first it was super noticeable but after time the 60hz didn't feel unusable.",
                ),
                span("span_assert_refresh_positive", "I love the 120hz."),
            ],
        )
    )

    eye_url = urls["reg_postmill_iphone_oled_eye_strain"]
    nodes.append(
        typed_node(
            "prop_oled_eye_strain_experience",
            "proposition",
            "users discussing eye strain after changing phones",
            "report_scoped_experiences",
            "a short store trial and replies describe different discomfort and adaptation outcomes without a controlled diagnosis",
            eye_url,
            [
                span(
                    "span_eye_short_trial",
                    "I played around with regular iPhone 14 the other day at Verizon store for like 5-10 minutes and i noticed that because of the display being more crispy and brighter, I felt more eye strain compared to my XR.",
                ),
                span(
                    "span_eye_other_user",
                    "I had the same problem when I first switched from and LCD iPhone to an OLED iPhone, I eventually got used to it",
                ),
                span(
                    "span_eye_not_used_to_it",
                    "Not necessarily used to it, but more as in I just gotta deal with it",
                ),
            ],
            "An XR user reports eye strain after a five-to-ten-minute iPhone 14 store trial, while replies describe different adjustment or continued-discomfort experiences; the thread does not provide a controlled cause, diagnosis, or population rate.",
            "community",
            "short_and_individual_comfort_reports_not_medical_causation",
        )
    )
    nodes.append(
        assertion_node(
            "assert_oled_eye_strain_experience",
            "eye-strain discussion",
            "the original author and replies describe differing personal outcomes after using newer phone displays",
            eye_url,
            [
                span(
                    "span_assert_eye_short_trial",
                    "I played around with regular iPhone 14 the other day at Verizon store for like 5-10 minutes and i noticed that because of the display being more crispy and brighter, I felt more eye strain compared to my XR.",
                ),
                span(
                    "span_assert_eye_other_user",
                    "I had the same problem when I first switched from and LCD iPhone to an OLED iPhone, I eventually got used to it",
                ),
            ],
        )
    )

    lcd_better_url = urls["reg_postmill_iphone_lcd_looks_better"]
    nodes.append(
        typed_node(
            "prop_lcd_brightness_disagreement",
            "proposition",
            "one older-LCD versus newer-OLED discussion",
            "reports_unresolved_comparison",
            "the author says the older LCD looked better or brighter in some shots, while replies raise settings or a possible defect",
            lcd_better_url,
            [
                span(
                    "span_lcd_better_report",
                    "Hey all this is really weird, but I believe my iPhone 6s Plus screen looks better in some shots in comparison to the iPhone 13 pro. It also manages to get really bright and the 13 isn’t able to match the brightness.",
                ),
                span(
                    "span_lcd_better_setting",
                    "Make sure auto brightness is off on the 13 or should be a significantly brighter and better screen than the 6s.",
                ),
                span(
                    "span_lcd_better_defect",
                    "Based on how you are describing it sounds more like a hardware defect.",
                ),
            ],
            "One user says an iPhone 6s Plus LCD looked better or brighter than an iPhone 13 Pro in some scenes, while replies suggest settings or a possible defect; the exchange is unresolved and cannot establish a general LCD-versus-OLED ranking.",
            "community",
            "unresolved_individual_comparison_not_general_panel_ranking",
        )
    )
    nodes.append(
        assertion_node(
            "assert_lcd_brightness_disagreement",
            "older-LCD versus newer-OLED discussion",
            "the original report and replies disagree about display performance and possible explanation",
            lcd_better_url,
            [
                span(
                    "span_assert_lcd_better_report",
                    "Hey all this is really weird, but I believe my iPhone 6s Plus screen looks better in some shots in comparison to the iPhone 13 pro. It also manages to get really bright and the 13 isn’t able to match the brightness.",
                ),
                span(
                    "span_assert_lcd_better_defect",
                    "Based on how you are describing it sounds more like a hardware defect.",
                ),
            ],
        )
    )

    concept_nodes = [
        typed_node(
            "prop_lcd_light_modulation",
            "proposition",
            "liquid-crystal display",
            "modulates_external_light",
            "liquid crystals and polarizers modulate light and do not emit it directly, using a backlight or reflector",
            urls["reg_wiki_liquid_crystal_display"],
            [
                span(
                    "span_lcd_definition",
                    "A liquid-crystal display ( LCD ) is a flat-panel display or other electronically modulated optical device that uses the light-modulating properties of liquid crystals combined with polarizers to display information.",
                ),
                span(
                    "span_lcd_backlight",
                    "Liquid crystals do not emit light directly [ 1 ] but instead use a backlight or reflector to produce images in color or monochrome .",
                ),
            ],
            "An LCD uses the light-modulating properties of liquid crystals and polarizers; the liquid crystals do not emit light directly, so a backlight or reflector supplies the light.",
            "concept",
            "display_mechanism_not_phone_quality_ranking",
        ),
        typed_node(
            "prop_oled_pixel_emission",
            "proposition",
            "organic light-emitting diode display",
            "emits_light_from_organic_layer",
            "an organic electroluminescent layer emits light under current, and AMOLED uses a TFT backplane to switch individual pixels",
            urls["reg_wiki_oled"],
            [
                span(
                    "span_oled_definition",
                    "An organic light-emitting diode ( OLED ), also known as organic electroluminescent ( organic EL ) diode , [ 1 ] [ 2 ] is a type of light-emitting diode (LED) in which the emissive electroluminescent layer is an organic compound film that emits light in response to an electric current.",
                ),
                span(
                    "span_oled_amoled_control",
                    "In the PMOLED scheme, each row and line in the display is controlled sequentially, one by one, [ 6 ] whereas AMOLED control uses a thin-film transistor (TFT) backplane to directly access and switch each individual pixel on or off, allowing for higher resolution and larger display sizes.",
                ),
            ],
            "An OLED contains an organic electroluminescent layer that emits light in response to current; AMOLED uses a TFT backplane to access and switch individual pixels.",
            "concept",
            "display_mechanism_not_phone_quality_ranking",
        ),
        typed_node(
            "prop_refresh_rate_scope",
            "proposition",
            "display refresh rate",
            "is_distinct_from_input_and_content_rates",
            "refresh rate counts hardware buffer updates per second and is not touch response rate or content frame rate",
            urls["reg_wiki_high_refresh_smartphones"],
            [
                span(
                    "span_refresh_definition",
                    "The refresh rate is the number of times in a second that a display hardware updates its buffer.",
                ),
                span(
                    "span_refresh_distinctions",
                    "It is not to be confused with the touch response rate, which is the frequency that the touchscreen senses input, or the frame rate , which describes how many images are stored or generated every second by the device driving the display.",
                ),
            ],
            "Display refresh rate is how often hardware updates its buffer and must not be confused with touch response rate or the content frame rate.",
            "concept",
            "metric_definition_not_universal_noticeability",
        ),
        typed_node(
            "prop_luminance_brightness_scope",
            "proposition",
            "display luminance and perceived brightness",
            "separates_objective_measurement_from_subjective_impression",
            "luminance is an objective directional intensity per area measured in cd/m2 or nits, while brightness is subjective",
            urls["reg_wiki_luminance"],
            [
                span(
                    "span_luminance_definition",
                    "Luminance is a photometric measure of the luminous intensity per unit area of light travelling in a given direction.",
                ),
                span(
                    "span_luminance_brightness",
                    "Brightness is the term for the subjective impression of the objective luminance measurement standard",
                ),
                span(
                    "span_luminance_unit",
                    "The SI unit for luminance is candela per square metre (cd/m 2 ). A non-SI term for the same unit is the nit .",
                ),
            ],
            "Luminance is an objective photometric measure expressed in candela per square metre or nits, whereas brightness is the subjective impression of that objective quantity.",
            "concept",
            "objective_metric_and_subjective_impression_are_distinct",
        ),
        typed_node(
            "prop_contrast_measurement_context",
            "proposition",
            "display contrast ratio",
            "depends_on_measurement_and_environment",
            "contrast compares white and black luminance, but manufacturer figures are not necessarily comparable and room light lowers observed contrast",
            urls["reg_wiki_contrast_ratio"],
            [
                span(
                    "span_contrast_definition",
                    "The contrast ratio ( CR ) is a property of a display system, defined as the ratio of the luminance of the brightest shade (white) to that of the darkest shade (black) that the system is capable of producing.",
                ),
                span(
                    "span_contrast_nonstandard",
                    "There is no official, standardized way to measure contrast ratio for a system or its parts, nor is there a standard for defining \"Contrast Ratio\" that is accepted by any standards organization so ratings provided by different manufacturers of display devices are not necessarily comparable to each other due to differences in method of measurement, operation, and unstated variables.",
                ),
                span(
                    "span_contrast_room",
                    "Real rooms reflect some of the light back to the displayed image, lowering the contrast ratio seen in the image.",
                ),
            ],
            "Contrast ratio compares brightest white with darkest black, but manufacturer ratings need not be comparable because methods differ, and reflected room light lowers the contrast seen in practice.",
            "concept",
            "measurement_method_and_ambient_context_required",
        ),
        typed_node(
            "prop_pixel_threshold_distance",
            "proposition",
            "visible-pixel threshold",
            "depends_on_density_and_viewing_distance",
            "there is no fixed minimum pixel density across devices because required density varies with typical viewing distance and angular resolution",
            urls["reg_wiki_retina_display"],
            [
                span(
                    "span_retina_no_fixed_density",
                    "Apple's Retina displays do not have a fixed minimum pixel density, but vary depending on and at what distance the user would typically be viewing the screen.",
                ),
                span(
                    "span_retina_distance",
                    "This definition includes the distance from the screen to the observer (the viewing distance ), because moving the eye closer to the display makes it easier to see detail up close, and moving away makes it harder.",
                ),
            ],
            "The Retina reference does not use one fixed minimum pixel density across devices: the threshold varies with typical viewing distance and angular resolution, so a universal phone-resolution stopping point is unsupported.",
            "concept",
            "viewing_distance_dependent_threshold_not_universal_ppi_cutoff",
        ),
    ]
    nodes.extend(concept_nodes)

    concept_assertions = [
        ("assert_lcd_light_modulation", "LCD reference", "liquid crystals modulate rather than directly emit the display light", urls["reg_wiki_liquid_crystal_display"], "span_assert_lcd_backlight", "Liquid crystals do not emit light directly [ 1 ] but instead use a backlight or reflector to produce images in color or monochrome ."),
        ("assert_oled_pixel_emission", "OLED reference", "the organic emissive layer produces light under current", urls["reg_wiki_oled"], "span_assert_oled_definition", "An organic light-emitting diode ( OLED ), also known as organic electroluminescent ( organic EL ) diode , [ 1 ] [ 2 ] is a type of light-emitting diode (LED) in which the emissive electroluminescent layer is an organic compound film that emits light in response to an electric current."),
        ("assert_refresh_rate_scope", "high-refresh smartphone reference", "refresh, touch response, and content frame rate are different rates", urls["reg_wiki_high_refresh_smartphones"], "span_assert_refresh_distinctions", "It is not to be confused with the touch response rate, which is the frequency that the touchscreen senses input, or the frame rate , which describes how many images are stored or generated every second by the device driving the display."),
        ("assert_luminance_brightness_scope", "luminance reference", "luminance is objective while brightness is subjective", urls["reg_wiki_luminance"], "span_assert_luminance_brightness", "Brightness is the term for the subjective impression of the objective luminance measurement standard"),
        ("assert_contrast_measurement_context", "contrast-ratio reference", "manufacturer contrast figures and real-room contrast depend on method and environment", urls["reg_wiki_contrast_ratio"], "span_assert_contrast_nonstandard", "There is no official, standardized way to measure contrast ratio for a system or its parts, nor is there a standard for defining \"Contrast Ratio\" that is accepted by any standards organization so ratings provided by different manufacturers of display devices are not necessarily comparable to each other due to differences in method of measurement, operation, and unstated variables."),
        ("assert_pixel_threshold_distance", "Retina display reference", "pixel-density thresholds vary with viewing distance", urls["reg_wiki_retina_display"], "span_assert_retina_no_fixed_density", "Apple's Retina displays do not have a fixed minimum pixel density, but vary depending on and at what distance the user would typically be viewing the screen."),
    ]
    nodes.extend(
        assertion_node(node_id, subject, obj, source_url, [span(span_id, quote)])
        for node_id, subject, obj, source_url, span_id, quote in concept_assertions
    )

    nodes.extend(
        [
            derived_node(
                "bridge_display_mechanism_scope",
                "bridge",
                "LCD and OLED phone displays",
                "derives_scope_boundary",
                "LCD and OLED use different light-generation paths, but a panel-family label alone does not determine brightness, contrast, comfort, outdoor visibility, or overall quality",
                "display_mechanism_scope_v1",
            ),
            derived_node(
                "bridge_measurement_task_mapping",
                "bridge",
                "person-specific display evaluation",
                "derives_metric_matrix",
                "map scrolling to refresh behavior, outdoor use to luminance and ambient contrast, and text sharpness to density plus viewing distance instead of collapsing them into one quality number",
                "display_measurement_context_v1",
            ),
            derived_node(
                "bridge_listing_value_matrix",
                "bridge",
                "four frozen phone configurations",
                "derives_listing_matrix",
                "compare price, panel label, size, resolution, refresh claim, carrier or warranty caveats, and bundle status against the measurement boundaries while withholding unmeasured display-quality claims",
                "listing_level_display_matrix_v1",
            ),
            derived_node(
                "bridge_scoped_personal_experience",
                "bridge",
                "display noticeability and comfort reports",
                "derives_scope_boundary",
                "interpret conflicting refresh preferences and an unresolved brightness comparison against the refresh, luminance, and contrast boundaries; short comfort reports still require person-specific testing and cannot establish prevalence or causation",
                "scoped_display_experience_v1",
            ),
            derived_node(
                "decision_person_specific_stop_rule",
                "decision",
                "budget-to-flagship display decision",
                "selects_admissible_set",
                [
                    "choose_the_least_expensive_returnable_exact_configuration_that_passes_person_specific_display_and_whole_phone_requirements_or_defer_without_a_universal_stopping_price"
                ],
                "evidence_bounded_display_value_decision_v1",
                decision=True,
            ),
        ]
    )

    edges: list[dict[str, object]] = [
        {"edge_id": "edge_assert_refresh", "source_id": "assert_refresh_value_disagreement", "relation": "ASSERTS", "target_id": "prop_refresh_value_disagreement"},
        {"edge_id": "edge_assert_eye", "source_id": "assert_oled_eye_strain_experience", "relation": "ASSERTS", "target_id": "prop_oled_eye_strain_experience"},
        {"edge_id": "edge_assert_lcd_better", "source_id": "assert_lcd_brightness_disagreement", "relation": "ASSERTS", "target_id": "prop_lcd_brightness_disagreement"},
        {"edge_id": "edge_assert_lcd_mechanism", "source_id": "assert_lcd_light_modulation", "relation": "ASSERTS", "target_id": "prop_lcd_light_modulation"},
        {"edge_id": "edge_assert_oled_mechanism", "source_id": "assert_oled_pixel_emission", "relation": "ASSERTS", "target_id": "prop_oled_pixel_emission"},
        {"edge_id": "edge_assert_refresh_scope", "source_id": "assert_refresh_rate_scope", "relation": "ASSERTS", "target_id": "prop_refresh_rate_scope"},
        {"edge_id": "edge_assert_luminance", "source_id": "assert_luminance_brightness_scope", "relation": "ASSERTS", "target_id": "prop_luminance_brightness_scope"},
        {"edge_id": "edge_assert_contrast", "source_id": "assert_contrast_measurement_context", "relation": "ASSERTS", "target_id": "prop_contrast_measurement_context"},
        {"edge_id": "edge_assert_retina", "source_id": "assert_pixel_threshold_distance", "relation": "ASSERTS", "target_id": "prop_pixel_threshold_distance"},
    ]
    edges.extend(discovery_edges)

    dependencies = {
        "bridge_display_mechanism_scope": ["prop_lcd_light_modulation", "prop_oled_pixel_emission"],
        "bridge_measurement_task_mapping": ["prop_refresh_rate_scope", "prop_luminance_brightness_scope", "prop_contrast_measurement_context", "prop_pixel_threshold_distance"],
        "bridge_listing_value_matrix": [
            "ev_tcl_lcd_snapshot",
            "ev_samsung_a51_amoled_snapshot",
            "ev_motorola_90hz_oled_snapshot",
            "ev_xperia_4k_120hz_oled_snapshot",
            "prop_refresh_rate_scope",
            "prop_luminance_brightness_scope",
            "prop_contrast_measurement_context",
            "prop_pixel_threshold_distance",
        ],
        "bridge_scoped_personal_experience": [
            "prop_refresh_value_disagreement",
            "prop_oled_eye_strain_experience",
            "prop_lcd_brightness_disagreement",
            "prop_refresh_rate_scope",
            "prop_luminance_brightness_scope",
            "prop_contrast_measurement_context",
        ],
    }
    for source_id, target_ids in dependencies.items():
        for target_id in target_ids:
            edges.append(
                {
                    "edge_id": f"edge_{source_id.removeprefix('bridge_')}_requires_{target_id.removeprefix('prop_').removeprefix('ev_')}",
                    "source_id": source_id,
                    "relation": "DERIVES_FROM",
                    "target_id": target_id,
                }
            )
    for target_id in dependencies:
        edges.append(
            {
                "edge_id": f"edge_decision_requires_{target_id.removeprefix('bridge_')}",
                "source_id": "decision_person_specific_stop_rule",
                "relation": "REQUIRES",
                "target_id": target_id,
            }
        )

    by_url = {document["source_url"]: ROOT / str(document["blob_path"]) for document in documents}
    for node in nodes:
        for support in node.get("support_spans", []):
            quote = str(support["exact_quote"]).encode("utf-8")
            blob = by_url[str(node["source_url"])].read_bytes()
            if blob.count(quote) <= int(support["occurrence"]):
                raise RuntimeError(
                    f"missing exact quote for {node['evidence_id']} / {support['support_span_id']}: {support['exact_quote']!r}"
                )

    inventory = {
        "schema_version": "evidence_graph_inventory_v1",
        "corpus_snapshot": SNAPSHOT,
        "documents": documents,
        "nodes": nodes,
        "edges": edges,
        "support_spans": [],
    }
    OUT.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "out": OUT.relative_to(ROOT).as_posix(),
                "documents": len(documents),
                "nodes": len(nodes),
                "edges": len(edges),
                "inline_support_spans": sum(len(node.get("support_spans", [])) for node in nodes),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
