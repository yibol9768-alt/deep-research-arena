#!/usr/bin/env python3
"""Build the frozen Q48 chocolate price-ladder evidence inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
SNAPSHOT = "dra-v3-formal-snacks-chocolate-0048-price-ladder-sensory-cutoff-20260716-r1"
RUN_ID = "v3-corpus-formal-snacks-chocolate-0048-price-ladder-sensory-cutoff-20260716-r1"
CAPTURE_REL = Path("data/evidence_graph/captures") / RUN_ID
CAPTURE = ROOT / CAPTURE_REL
TASK_ID = "dra_v3_formal_snacks_chocolate_0048"
TOPIC = "dark_chocolate_price_ladder_personal_sensory_cutoff"
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_snacks_chocolate_0048/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")


SEARCHES = [
    ("dove", "001-shopping-dove-dark-pack-twelve.json", "DOVE twelve-pack offer", "http://localhost:7770/dove-dark-chocolate-bars-3-30-ounce-bar-pack-of-12.html"),
    ("lindt", "002-shopping-lindt-excellence-seventy-pack-twelve.json", "Lindt 70-percent twelve-pack offer", "http://localhost:7770/lindt-excellence-bar-70-cocoa-smooth-dark-chocolate-gluten-free-great-for-holiday-gifting-3-5-ounce-pack-of-12.html"),
    ("ritter", "003-shopping-ritter-seventy-four-single.json", "Ritter Sport 74-percent single-bar offer", "http://localhost:7770/ritter-sport-74-intense-dark-chocolate-bar-candy-original-german-chocolate-100g-3-52oz.html"),
    ("green_black", "004-shopping-green-black-seventy-pack-three.json", "Green and Black 70-percent three-pack offer", "http://localhost:7770/green-black-organic-70-dark-chocolate-100g-pack-of-3.html"),
    ("raaka", "005-shopping-raaka-coconut-sixty-pack-three.json", "Raaka coconut-milk bean-to-bar offer", "http://localhost:7770/raaka-chocolate-coconut-milk-60-cacao-dark-chocolate-gourmet-dark-chocolate-gift-organic-vegan-dairy-free-fair-trade-soy-free-non-gmo-gluten-free-kosher-1-8oz-bars-3-pack.html"),
    ("bean_to_bar", "006-wiki-bean-to-bar-model.json", "bean-to-bar manufacturing model", "http://localhost:8090/content/wikipedia_en_all_nopic/Bean-to-bar"),
    ("cocoa_solids", "007-wiki-cocoa-solids-composition.json", "cocoa-solids composition boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Cocoa_solids"),
    ("bulk_cocoa", "008-wiki-bulk-cocoa-quality-boundary.json", "bulk-versus-flavor cocoa boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Bulk_cocoa"),
    ("fair_trade", "009-wiki-fair-trade-cocoa-ethics.json", "Fairtrade cocoa price-support scope", "http://localhost:8090/content/wikipedia_en_all_nopic/Fair_trade_cocoa"),
    ("sensory", "010-wiki-sensory-analysis-difference-liking.json", "analytical-versus-affective sensory testing", "http://localhost:8090/content/wikipedia_en_all_nopic/Sensory_analysis"),
    ("hedonic", "011-wiki-hedonic-scale-liking.json", "nine-point hedonic liking scale", "http://localhost:8090/content/wikipedia_en_all_nopic/Hedonic_scale"),
    ("blinding", "012-wiki-blind-experiment-bias.json", "blinding and expectation-bias boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Blinded_experiment"),
    ("daily_habit", "013-forum-daily-chocolate-habit.json", "one author's daily chocolate habit", "http://localhost:9999/f/LifeProTips/120364/lpt-request-how-do-i-stop-myself-from-eating-chocolates"),
    ("variety_gift", "014-forum-dark-bar-variety-gift.json", "one six-bar dark-chocolate gift incident", "http://localhost:9999/f/tifu/71318/tifu-by-sending-my-parents-chocolate-for-christmas"),
    ("aldi_value", "015-forum-aldi-price-quality-list.json", "one author's Aldi price-and-quality list", "http://localhost:9999/f/pittsburgh/25456/god-tier-aldi-products"),
]


def ev(
    evidence_id: str,
    subject: str,
    predicate: str,
    object_: str,
    search_index: int,
    role: str,
    scope: str,
    quotes: list[str],
    accepted: str,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "subject": subject,
        "predicate": predicate,
        "object": object_,
        "source_url": SEARCHES[search_index][3],
        "search_id": SEARCHES[search_index][0],
        "role": role,
        "scope": scope,
        "quotes": quotes,
        "accepted": accepted,
    }


EVIDENCE = [
    ev(
        "prop_dove_pack_price_scope",
        "frozen DOVE seller page",
        "shows_a_twelve_bar_offer",
        "SKU B07L9TTQN6 at 25.45 dollars with no reviews shown and a nominal twelve times 3.30-ounce pack",
        0,
        "product",
        "frozen_seller_offer_not_current_delivered_price_or_taste_result",
        [
            "DOVE Dark Chocolate Bars, 3.30-Ounce Bar (Pack of 12)",
            "In stock SKU B07L9TTQN6 Be the first to review this product $25.45",
            "Contains twelve (12) 3.30-ounce extra-large DOVE Dark Chocolate Bars",
        ],
        "The frozen DOVE page shows SKU B07L9TTQN6 at 25.45 dollars with no reviews shown and describes twelve 3.30-ounce dark bars. Conditional title arithmetic is about 2.12 dollars per nominal bar and 0.64 dollars per nominal ounce, but this is neither a verified current delivered price nor a blind taste or health result.",
    ),
    ev(
        "prop_lindt_pack_price_scope",
        "frozen Lindt seller page",
        "shows_a_seventy_percent_twelve_bar_offer",
        "SKU B000H26J7E at 30 dollars rated 67 percent over twelve reviews with twelve 3.5-ounce 70-percent bars",
        1,
        "product",
        "frozen_seller_offer_and_marketing_not_independent_quality_evidence",
        [
            "Lindt Excellence Bar, 70% Cocoa Smooth Dark Chocolate, Gluten Free, Great for Holiday Gifting, 3.5 Ounce (Pack of 12)",
            "In stock SKU B000H26J7E Rating: 67 % of 100 12 Reviews Add Your Review $30.00",
            "Contains 12 individually wrapped 70% cocoa dark chocolate bars, perfect for gifting, baking, or savoring piece by piece",
        ],
        "The frozen Lindt page shows SKU B000H26J7E at 30 dollars, rated 67 percent over twelve reviews, and describes twelve individually wrapped 3.5-ounce 70-percent bars. Conditional title arithmetic is 2.50 dollars per nominal bar and about 0.71 dollars per nominal ounce; rating, premium wording and this arithmetic do not establish blind preference or current delivered value.",
    ),
    ev(
        "prop_ritter_single_price_scope",
        "frozen Ritter Sport seller page",
        "shows_one_seventy_four_percent_bar_and_source_claims",
        "SKU B07PTSPCVS at 8.99 dollars with no reviews shown for one 100-gram or 3.52-ounce 74-percent bar carrying three-ingredient single-origin and sustainability claims",
        2,
        "product",
        "frozen_seller_offer_and_claims_not_verified_composition_origin_or_taste",
        [
            "Ritter Sport 74% Intense Dark Chocolate Bar Candy Original German Chocolate 100g/3.52oz",
            "In stock SKU B07PTSPCVS Be the first to review this product $8.99",
            "Made with only three ingredients and single origin certified sustainable sourced Peruvian cocoa, the fine, fruity and slightly spicy taste is perfect for all who just love intense chocolate.",
        ],
        "The frozen Ritter Sport page shows SKU B07PTSPCVS at 8.99 dollars with no reviews shown for one 74-percent 100-gram or 3.52-ounce bar and makes three-ingredient, single-origin, sustainable-source and flavor claims. Those remain exact seller assertions rather than an ingredient-panel audit, origin verification, blind taste result or proof that 8.99 dollars crosses a quality threshold.",
    ),
    ev(
        "prop_green_black_pack_price_scope",
        "frozen Green and Black seller page",
        "shows_a_three_bar_seventy_percent_offer",
        "SKU B008FRKKV4 at 21.99 dollars with no reviews shown for three 100-gram 70-percent bars carrying organic Fairtrade and Trinitario claims",
        3,
        "product",
        "frozen_seller_offer_and_claims_not_verified_label_or_taste",
        [
            "Green & Black Organic 70% Dark Chocolate 100G (Pack Of 3)",
            "In stock SKU B008FRKKV4 Be the first to review this product $21.99",
            "70% cocoa. Organic. Fairtrade. Suitable for vegetarians.",
            "The cocoa solids are a combination of cocoa mass and cocoa butter.",
        ],
        "The frozen Green and Black page shows SKU B008FRKKV4 at 21.99 dollars with no reviews shown for three 100-gram 70-percent bars and carries organic, Fairtrade, Trinitario and flavor statements. Conditional title arithmetic is 7.33 dollars per nominal 100-gram bar; the claims and price do not independently establish the current label, certification, bean quality or blind preference.",
    ),
    ev(
        "prop_raaka_pack_identity_conflict_scope",
        "frozen Raaka seller page",
        "shows_a_coconut_recipe_three_pack_and_mass_conflict",
        "SKU B07811Q1PR at 14.95 dollars rated 58 percent over twelve reviews with a selected 60-percent coconut-milk 1.8-ounce three-pack and a Product Dimensions field of only 1.8 ounces",
        4,
        "product",
        "frozen_flavored_offer_with_unresolved_total_mass_not_plain_bar_or_taste_guarantee",
        [
            "Raaka Chocolate Coconut Milk 60% Cacao Dark Chocolate | Gourmet Dark Chocolate Gift| Organic, Vegan, Dairy Free, Fair Trade, Soy Free, Non GMO, Gluten Free, Kosher | 1.8oz Bars, 3-Pack",
            "In stock SKU B07811Q1PR Rating: 58 % of 100 12 Reviews Add Your Review $14.95",
            "BEAN-TO-BAR: We make our chocolate from scratch, starting with unroasted cacao beans.",
            "Raaka Chocolate Coconut Milk Dark Chocolate 60% Cacao, (1.8oz Bar - 3 Pack).",
            "Package Dimensions ‏ ‎ 5.5 x 2.4 x 1.3 inches; 1.8 Ounces",
        ],
        "The frozen Raaka page shows SKU B07811Q1PR at 14.95 dollars, rated 58 percent over twelve reviews, for a selected coconut-milk 60-percent 1.8-ounce three-pack and carries bean-to-bar and unroasted claims, while Product Dimensions reports only 1.8 ounces. Conditional title arithmetic is about 4.98 dollars per bar and 2.77 dollars per ounce, but total delivered mass remains unresolved and this flavored recipe cannot be treated as a plain-bar taste control.",
    ),
    ev(
        "prop_bean_to_bar_process_scope",
        "bean-to-bar model",
        "defines_control_and_whole_bean_processing",
        "a manufacturer controls the process from bean procurement to finished chocolate and processes whole cocoa beans rather than remelting an existing base",
        5,
        "concept",
        "general_process_definition_not_exact_claim_audit_or_quality_guarantee",
        [
            "Bean-to-bar is a business model [ 1 ] in which a chocolate manufacturer controls the entire manufacturing process from procuring cocoa beans to creating the end product of consumer chocolate.",
            "All bean-to-bar chocolate makers process whole cocoa beans into a final product versus melting chocolate or starting with ground cocoa mass for use as a base, coating, filling or for mixing and molding into truffles, pralines, or other chocolate confectionery.",
        ],
        "The bean-to-bar page defines a business model in which a manufacturer controls production from procuring beans to finished consumer chocolate and processes whole beans instead of remelting an existing base. This is process context, not proof that Raaka's exact claim is true or that bean-to-bar universally tastes better, costs more ethically, or delivers a health benefit.",
    ),
    ev(
        "prop_cocoa_solids_definition_scope",
        "cocoa-solids terminology",
        "distinguishes_dry_solids_from_broader_legal_usage",
        "dry cocoa solids remain after cocoa butter extraction while some legal definitions include cocoa mass powder and butter",
        6,
        "concept",
        "general_composition_definition_not_exact_bar_formula_or_health_rank",
        [
            "Dry cocoa solids are the components of cocoa beans remaining after cocoa butter , the fatty component of the bean, is extracted from chocolate liquor , roasted cocoa beans that have been ground into a liquid state.",
            "Other definitions of cocoa solids, especially legal ones, include all cocoa ingredients (cocoa mass, cocoa powder and cocoa butter).",
        ],
        "The cocoa-solids page distinguishes dry solids left after cocoa-butter extraction from broader legal definitions that include cocoa mass, powder and butter. Therefore a cocoa percentage alone does not disclose the exact balance of non-fat solids, cocoa butter, sugar and other ingredients or establish a taste, quality or health ranking for the five bars.",
    ),
    ev(
        "prop_bulk_cocoa_subjective_scope",
        "bulk cocoa classification",
        "uses_a_partly_subjective_processing_sensitive_boundary",
        "bulk cocoa is contrasted with flavor cocoa through a subjective definition involving undesirable flavor drying or fermentation and can vary in quality",
        7,
        "concept",
        "general_classification_not_grade_for_any_captured_bar",
        [
            "Bulk cocoa is a class of cocoa beans . It is contrasted with flavor cocoa .",
            "Bulk cocoa is distinguished from flavor cocoa using the subjective definition of containing undesirable or poor flavor, drying or fermentation.",
            "Indonesia produces bulk cocoa of variable quality.",
        ],
        "The bulk-cocoa page contrasts bulk with flavor cocoa using a subjective definition involving flavor, drying or fermentation and notes variable quality in one origin. It supports treating bean class and processing as variables, but it neither grades any captured bar nor proves that origin, price or a craft label maps monotonically to quality.",
    ),
    ev(
        "prop_fairtrade_price_support_scope",
        "Fairtrade cocoa",
        "defines_a_certified_price_support_scheme",
        "the scheme is designed to support sustainable farmer income and may be signaled by a Fairtrade mark",
        8,
        "concept",
        "general_certification_definition_not_exact_payment_taste_or_total_ethics_proof",
        [
            "Fair trade cocoa is an agricultural product harvested from a cocoa tree under a Fairtrade certified price support scheme used by cocoa farmers, buyers, and chocolate manufacturers, and is designed to create sustainable incomes for farmers and their families.",
            "Food manufacturers that use fair trade certified cocoa in their products often display the Fairtrade symbol to indicate that they are contributing to social, economic, and environmental sustainability in agriculture.",
        ],
        "The Fairtrade-cocoa page defines a certified price-support scheme designed to support sustainable farmer income and describes use of a Fairtrade symbol. It does not verify the exact seller labels, payments, supply chain, complete ethical outcome, taste superiority or value of any captured bar.",
    ),
    ev(
        "prop_sensory_difference_liking_scope",
        "sensory analysis",
        "separates_analytical_difference_from_affective_acceptance",
        "analytical testing addresses product facts such as detectable difference while affective testing addresses subjective preference and acceptance",
        9,
        "concept",
        "general_method_boundary_not_result_for_the_five_bars",
        [
            "Sensory analysis can mainly be broken down into three sub-sections: [ 2 ] Analytical testing (dealing with objective facts about products) Affective testing (dealing with subjective facts such as preferences) Perception (the biochemical and psychological aspects of sensation)",
            "This could range from basic discrimination testing (e.g. Do two or more products differ from each other?) to descriptive analysis (e.g. What are the characteristics of two or more products?).",
            "Affective testing Also known as consumer testing , this type of testing concerns obtaining subjective data, or how well products are likely to be accepted.",
        ],
        "The sensory-analysis page separates analytical tests of product difference from affective tests of subjective preference and acceptance. Detecting that two bars differ is not the same as preferring the expensive one or judging the gain worth its price, and the page provides no result for the captured bars.",
    ),
    ev(
        "prop_hedonic_liking_scale_scope",
        "hedonic scale",
        "measures_degree_of_liking",
        "a common nine-level scale ranges from dislike extremely to like extremely",
        10,
        "concept",
        "general_liking_instrument_not_exact_preference_or_willingness_to_pay_result",
        [
            "The hedonic scale is a sensory evaluation tool used to measure the degree of pleasure or liking of a product or service.",
            "The scale usually consists of 9 levels ranging from 1 to 9, or  \"dislike extremely\" to \"like extremely\".",
        ],
        "The hedonic-scale page describes a sensory tool for degree of liking, commonly from one to nine between dislike extremely and like extremely. A rating can record this buyer's declared liking under test conditions but does not by itself establish detectable difference, population preference, value or willingness to pay.",
    ),
    ev(
        "prop_blinding_bias_scope",
        "blinded experiment",
        "withholds_influential_information_to_reduce_bias",
        "brand package price and other cues can be masked and the report should say who was blinded to what and whether blinding succeeded",
        11,
        "concept",
        "general_bias_control_not_automatic_success_or_exact_bar_result",
        [
            "In a blind or blinded experiment , information that could influence participants or investigators is withheld until the experiment is completed.",
            "Blinding is used to reduce or eliminate potential sources of bias , such as participantsâ expectations, the observer-expectancy effect , observer bias , confirmation bias , and other cognitive or procedural influences.",
            "To describe an experiment's blinding, it is necessary to report who has been blinded to what information, and how well each blind succeeded.",
        ],
        "The blinded-experiment page says influential information is withheld to reduce expectation and observer biases and says reports should identify who was blinded to what and how well the blind succeeded. Hiding brand, package, price and marketing cues is useful, but perceptible recipes can unblind the buyer and no captured page proves a successful blind comparison.",
    ),
    ev(
        "prop_daily_habit_anecdote_scope",
        "daily chocolate-habit post",
        "reports_one_authors_frequency_and_goal",
        "one 21-year-old author reports a bar or two per day and a desire to cut down",
        12,
        "community",
        "single_author_self_report_not_population_intake_or_dark_bar_value_evidence",
        [
            "I eat a bar or two every day.",
            "And I wanna cut down on chocolates.",
        ],
        "One forum author reports eating a bar or two every day and wanting to cut down. This self-report can motivate recording use frequency and total recurring cost, but it is not evidence about the current buyer's intake, dark-chocolate health effects, any exact product, or a safe or optimal daily amount.",
    ),
    ev(
        "prop_variety_gift_anecdote_scope",
        "dark-bar gift incident",
        "reports_six_varied_roughly_three_ounce_bars",
        "one author sent six dark bars of various types at about three ounces each before an unrelated pet-ingestion event",
        13,
        "community",
        "single_gift_incident_not_controlled_variety_trial_or_product_safety_evidence",
        [
            "So I got them six dark chocolate bars of various types. They are about three ounces each.",
            "Unfortunately my gifts were all mixed together with other gifts and they didn't want to open anything until Christmas.",
        ],
        "One author reports sending six dark bars of various types at about three ounces each before an unrelated dog-ingestion incident. The post can motivate a small varied purchase and safe storage, but it is not a controlled taste ladder, does not identify the five exact offers and provides no human consumption or product-ranking evidence.",
    ),
    ev(
        "prop_aldi_value_anecdote_scope",
        "Aldi price-and-quality post",
        "lists_one_authors_favorites",
        "one Pittsburgh author lists products liked for price and quality and mentions chocolate-flavored ice cream rather than dark bars",
        14,
        "community",
        "single_author_local_list_not_dark_bar_price_quality_curve",
        [
            "I have been thinking about the things that I love from Aldi — both because of their price and quality.",
            "Specialty coffee or chocolate flavored ice cream",
        ],
        "One Pittsburgh author lists Aldi products liked for price and quality and mentions chocolate-flavored ice cream, not a controlled dark-bar comparison. This supports keeping price and perceived quality as separate axes but supplies no exact bar price, blind preference, current availability or universal price-quality cutoff.",
    ),
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def typed_verifier(accepted: str) -> dict[str, Any]:
    return {
        "kind": "typed_claim",
        "matcher": "normalized_text",
        "accepted_phrases": [accepted],
        "normalizers": ["casefold", "whitespace", "punctuation", "hyphen"],
    }


def build() -> dict[str, Any]:
    capture_documents = json.loads(
        (CAPTURE / "documents.json").read_text(encoding="utf-8")
    )["documents"]
    documents: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for search_id, filename, subject, target_url in SEARCHES:
        path = CAPTURE / "searches" / filename
        data = path.read_bytes()
        payload = json.loads(data)
        source_url = (
            f"http://localhost:8081/search?capture_run={RUN_ID}"
            f"&request_id={payload['request_id']}"
        )
        documents.append(
            {
                "registry_id": f"reg_search_{search_id}",
                "source_url": source_url,
                "source_type": "search_result",
                "content_sha256": sha256_bytes(data),
                "blob_path": rel(path),
                "in_corpus": True,
            }
        )
        nodes.append(
            {
                "evidence_id": f"search_{search_id}",
                "node_type": "search_result",
                "subject": subject,
                "predicate": "returned",
                "object": [target_url],
                "source_url": source_url,
                "body_support": False,
                "search_snippet_support": True,
                "verifier": {"kind": "search_observation"},
                "metadata": {
                    "discovery_root": True,
                    "discovery_root_policy": "search_result",
                    "topic_cluster": TOPIC,
                },
            }
        )

    raw_content_by_url: dict[str, str] = {}
    for row in capture_documents:
        documents.append(
            {
                "registry_id": row["registry_id"],
                "source_url": row["source_url"],
                "source_type": row["source_type"],
                "content_sha256": row["content_sha256"],
                "blob_path": (CAPTURE_REL / row["blob_path"]).as_posix(),
                "in_corpus": True,
            }
        )
        raw_content_by_url[row["source_url"]] = (
            CAPTURE / row["blob_path"]
        ).read_text(encoding="utf-8")

    case_source = f"http://case-spec.local/{TASK_ID}"
    documents.append(
        {
            "registry_id": "reg_case_spec_chocolate_price_0048",
            "source_url": case_source,
            "source_type": "case_spec",
            "content_sha256": sha256_bytes(CASE_SPEC.read_bytes()),
            "blob_path": CASE_SPEC_REL.as_posix(),
            "in_corpus": True,
        }
    )

    for item in EVIDENCE:
        content = raw_content_by_url[item["source_url"]]
        spans = []
        for index, quote in enumerate(item["quotes"], start=1):
            if quote not in content:
                raise ValueError(
                    f"quote missing from {item['evidence_id']}: {quote!r}"
                )
            spans.append(
                {
                    "support_span_id": f"span_{item['evidence_id']}_{index}",
                    "exact_quote": quote,
                    "occurrence": 0,
                    "support_type": "body",
                }
            )
        nodes.append(
            {
                "evidence_id": item["evidence_id"],
                "node_type": "proposition",
                "subject": item["subject"],
                "predicate": item["predicate"],
                "object": item["object"],
                "source_url": item["source_url"],
                "support_spans": spans,
                "verifier": typed_verifier(item["accepted"]),
                "metadata": {
                    "acceptable_source_roles": [item["role"]],
                    "critical": True,
                    "scope": item["scope"],
                    "topic_cluster": TOPIC,
                },
            }
        )
        assertion_id = f"assert_{item['evidence_id'].removeprefix('prop_')}"
        nodes.append(
            {
                "evidence_id": assertion_id,
                "node_type": "assertion",
                "subject": f"source for {item['subject']}",
                "predicate": "states",
                "object": item["object"],
                "source_url": item["source_url"],
                "support_spans": [
                    {
                        "support_span_id": f"span_{assertion_id}_1",
                        "exact_quote": item["quotes"][0],
                        "occurrence": 0,
                        "support_type": "body",
                    }
                ],
                "verifier": {"kind": "quoted_assertion"},
                "metadata": {"topic_cluster": TOPIC},
            }
        )
        edges.extend(
            [
                {
                    "edge_id": f"edge_assert_{item['evidence_id']}",
                    "source_id": assertion_id,
                    "relation": "ASSERTS",
                    "target_id": item["evidence_id"],
                },
                {
                    "edge_id": f"edge_discover_{item['evidence_id']}",
                    "source_id": item["evidence_id"],
                    "relation": "DISCOVERABLE_FROM",
                    "target_id": f"search_{item['search_id']}",
                    "discovery_method": "S",
                    "discovery_order": 1,
                },
            ]
        )

    deterministic_nodes = [
        ("bridge_seller_price_pack_normalization", "bridge", "five frozen seller offers", "normalizes_literal_price_pack_and_mass_fields_conditionally", "audit exact seller fields and show conditional price-per-bar and price-per-mass arithmetic while preserving pack assumptions the Raaka mass conflict and the absence of current delivered prices or taste results", "seller_price_pack_normalization_scope_v1"),
        ("bridge_comparable_form_price_ladder", "bridge", "product percentage recipe flavor and form", "requires_a_like_for_like_price_ladder", "separate comparable plain dark bars from flavored coconut-containing and otherwise unmatched offers before attributing sensory differences to price", "comparable_form_price_ladder_boundary_v1"),
        ("bridge_process_ethics_label_boundary", "bridge", "bean-to-bar Fairtrade and seller process claims", "separates_process_and_ethics_from_sensory_guarantees", "retain bean-to-bar as production-control context and Fairtrade as price-support context while refusing exact verification taste health or total ethical guarantees", "process_ethics_label_boundary_v1"),
        ("bridge_cocoa_composition_quality_boundary", "bridge", "percentage cocoa-solids and bean-class evidence", "requires_exact_composition_and_testing_before_quality_ranking", "distinguish dry and broad cocoa-solids definitions and subjective processing-sensitive bean classifications without turning percentage origin or bean class into a monotonic quality curve", "cocoa_composition_quality_boundary_v1"),
        ("bridge_community_habit_value_scope", "bridge", "three community pages", "retains_author_incident_product_place_and_time_scope", "use daily frequency varied small bars and price-versus-quality as trial variables while refusing population intake safety brand preference or universal value conclusions", "community_habit_value_scope_v1"),
        ("bridge_blinded_difference_liking_protocol", "bridge", "matched within-person chocolate trial", "separates_detectability_liking_and_willingness_to_pay", "verify comparable offers mask brand package price and marketing randomize equal portions repeat sessions record unblinding and score difference nine-point liking and purchase willingness separately", "blinded_difference_liking_protocol_v1"),
        ("bridge_person_specific_price_stop_rule", "bridge", "verified price tiers and repeated sensory outcomes", "locates_only_a_person_specific_conditional_stopping_point", "advance tiers only while the next tier clears predeclared repeatable difference liking gain and incremental evening-cost ceilings otherwise keep the lower tier correct the trial or defer", "person_specific_price_stop_rule_v1"),
        ("bridge_price_ladder_decision_preparation", "bridge", "evidence-bounded daily dark-chocolate choice", "combines_offer_comparability_process_ethics_sensory_and_cost_axes", "build a pass fail unresolved table and preserve ethics as its own priority without allowing marketing ratings anecdotes or one passing axis to replace identity allergen sensory and budget gates", "price_ladder_decision_preparation_v1"),
        ("decision_evidence_bounded_price_ladder", "decision", "daily dark-chocolate price ladder", "selects_the_lowest_cost_exact_comparable_passing_bar_or_keep_trial_or_defer", "choose the lowest-cost exact comparable bar passing identity allergen repeatable sensory and budget gates otherwise keep the current bar run a smaller corrected trial or defer and report no universal cutoff", "evidence_bounded_price_ladder_decision_v1"),
    ]
    for evidence_id, node_type, subject, predicate, object_, rule_id in deterministic_nodes:
        metadata: dict[str, Any] = {"rule_id": rule_id, "topic_cluster": TOPIC}
        if node_type == "decision":
            metadata["oracle_unique_or_admissible"] = True
        nodes.append(
            {
                "evidence_id": evidence_id,
                "node_type": node_type,
                "subject": subject,
                "predicate": predicate,
                "object": object_,
                "source_url": case_source,
                "verifier": {"kind": "deterministic_rule"},
                "metadata": metadata,
            }
        )

    products = [
        "prop_dove_pack_price_scope",
        "prop_lindt_pack_price_scope",
        "prop_ritter_single_price_scope",
        "prop_green_black_pack_price_scope",
        "prop_raaka_pack_identity_conflict_scope",
    ]
    derives = {
        "bridge_seller_price_pack_normalization": products,
        "bridge_comparable_form_price_ladder": products + ["prop_cocoa_solids_definition_scope"],
        "bridge_process_ethics_label_boundary": ["prop_raaka_pack_identity_conflict_scope", "prop_bean_to_bar_process_scope", "prop_fairtrade_price_support_scope"],
        "bridge_cocoa_composition_quality_boundary": ["prop_ritter_single_price_scope", "prop_green_black_pack_price_scope", "prop_raaka_pack_identity_conflict_scope", "prop_cocoa_solids_definition_scope", "prop_bulk_cocoa_subjective_scope"],
        "bridge_community_habit_value_scope": ["prop_daily_habit_anecdote_scope", "prop_variety_gift_anecdote_scope", "prop_aldi_value_anecdote_scope"],
        "bridge_blinded_difference_liking_protocol": products + ["prop_sensory_difference_liking_scope", "prop_hedonic_liking_scale_scope", "prop_blinding_bias_scope"],
        "bridge_person_specific_price_stop_rule": ["bridge_seller_price_pack_normalization", "bridge_comparable_form_price_ladder", "bridge_blinded_difference_liking_protocol", "bridge_community_habit_value_scope"],
        "bridge_price_ladder_decision_preparation": ["bridge_seller_price_pack_normalization", "bridge_comparable_form_price_ladder", "bridge_process_ethics_label_boundary", "bridge_cocoa_composition_quality_boundary", "bridge_community_habit_value_scope", "bridge_blinded_difference_liking_protocol", "bridge_person_specific_price_stop_rule"],
    }
    for source_id, targets in derives.items():
        for target_id in targets:
            edges.append(
                {
                    "edge_id": f"edge_{source_id}_from_{target_id}",
                    "source_id": source_id,
                    "relation": "DERIVES_FROM",
                    "target_id": target_id,
                }
            )
    for target_id in derives:
        edges.append(
            {
                "edge_id": f"edge_decision_requires_{target_id}",
                "source_id": "decision_evidence_bounded_price_ladder",
                "relation": "REQUIRES",
                "target_id": target_id,
            }
        )

    return {
        "schema_version": "evidence_graph_inventory_v1",
        "corpus_snapshot": SNAPSHOT,
        "documents": documents,
        "nodes": nodes,
        "edges": edges,
        "support_spans": [],
    }


def main() -> None:
    inventory = build()
    OUT.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "out": rel(OUT),
                "documents": len(inventory["documents"]),
                "nodes": len(inventory["nodes"]),
                "edges": len(inventory["edges"]),
                "critical_evidence": len(EVIDENCE),
                "sha256": sha256_bytes(OUT.read_bytes()),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
