#!/usr/bin/env python3
"""Build the frozen Q50 hot-weather portability inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-snacks-chocolate-0050-hot-weather-portability-"
    "boundary-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_snacks_chocolate_0050/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = (
    "dra-v3-formal-snacks-chocolate-0050-hot-weather-portability-"
    "boundary-20260716-r1"
)
RUN_ID = (
    "v3-corpus-formal-snacks-chocolate-0050-hot-weather-portability-"
    "boundary-20260716-r1"
)
TASK_ID = "dra_v3_formal_snacks_chocolate_0050"
TOPIC = "hot_weather_sweet_snack_portability_boundary"


SEARCHES = [
    (
        "mms_milk",
        "001-shopping-mms-milk-party-bag.json",
        "M&M'S milk-chocolate party-bag seller snapshot",
        "http://localhost:7770/m-m-s-milk-chocolate-candy-38-ounce-party-size-bag.html",
    ),
    (
        "skittles_tub",
        "002-shopping-skittles-ninety-fun-size-bags.json",
        "Skittles ninety-packet tub seller snapshot",
        "http://localhost:7770/skittles-candy-skittles-bulk-variety-pack-90-individually-wrapped-fun-size-bags-in-reusable-plastic-tub-assortment-of-original-candy-flavors.html",
    ),
    (
        "jolly_rancher_sour",
        "003-shopping-jolly-rancher-sour-hard-candy.json",
        "Jolly Rancher sour hard-candy seller snapshot",
        "http://localhost:7770/jolly-rancher-assorted-sour-fruit-hard-candy-pieces-oval-hard-candy-13-oz-0010700450291.html",
    ),
    (
        "charleston_chew",
        "004-shopping-charleston-chew-chocolatey-coating.json",
        "Charleston Chew chocolatey-coated nougat seller snapshot",
        "http://localhost:7770/charleston-chew-chewy-flavored-nougat-with-a-delicious-chocolatey-coating-chocolate-strawberry-vanilla-1-87-ounce-candy-bars-individually-wrapped-great-for-holiday-stocking-stuffers-parties-gifts-more-chocolatey-1-87-ounce-6-count.html",
    ),
    (
        "melting_point",
        "005-wiki-melting-point-boundary.json",
        "generic melting-point boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Melting_point",
    ),
    (
        "crystal_polymorphism",
        "006-wiki-crystal-polymorphism-boundary.json",
        "crystal-polymorphism boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Crystal_polymorphism",
    ),
    (
        "compound_chocolate",
        "007-wiki-compound-chocolate-boundary.json",
        "compound-chocolate and coating boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Compound_chocolate",
    ),
    (
        "hard_candy",
        "008-wiki-hard-candy-formulation.json",
        "hard-candy formulation boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Hard_candy",
    ),
    (
        "glass_transition",
        "009-wiki-glass-transition-boundary.json",
        "glass-transition boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Glass_transition",
    ),
    (
        "hygroscopy",
        "010-wiki-hygroscopy-boundary.json",
        "environmental moisture-uptake boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Hygroscopy",
    ),
    (
        "ice_pack",
        "011-wiki-ice-pack-transport-boundary.json",
        "portable cooling and exposure boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Ice_pack",
    ),
    (
        "shelf_stable_food",
        "012-wiki-shelf-stable-food-boundary.json",
        "shelf-stable sealed-food boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Shelf-stable_food",
    ),
    (
        "sweat_candy",
        "013-forum-sweat-covered-pocket-candy.json",
        "sweat-sogged paper-wrapper anecdote",
        "http://localhost:9999/f/tifu/135373/tifu-by-offering-a-sweat-covered-candy-to-a-girl",
    ),
    (
        "igloo_cooler",
        "014-forum-old-igloo-cooler-anecdote.json",
        "old full-size cooler anecdote and disagreement",
        "http://localhost:9999/f/BuyItForLife/32733/my-igloo-large-cooler-been-in-the-family-for-around-35-years",
    ),
    (
        "salt_ice",
        "015-forum-salt-ice-cooler-mechanism.json",
        "salt-and-ice cooler mechanism discussion",
        "http://localhost:9999/f/askscience/102358/what-are-the-effects-of-adding-rock-salt-to-a-cooler-full-of",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_mms_offer_shell_scope",
        "subject": "frozen M&M'S milk-chocolate seller page",
        "predicate": "shows_a_rated_thirty_eight_ounce_shell_coated_offer",
        "object": "an 11.79-dollar SKU rated 73 percent over twelve reviews and described as one 38-ounce bag of real milk-chocolate centers in colorful candy shells",
        "source_url": SEARCHES[0][3],
        "search_id": "mms_milk",
        "role": "product",
        "scope": "seller_offer_and_shell_copy_not_measured_hot_route_survival_or_complete_current_label",
        "quotes": [
            "In stock SKU B07W5B43Z8 Rating: 73 % of 100 12 Reviews Add Your Review $11.79 Size 2.37 Pound (Pack of 2) 38 Ounce (Pack of 1)",
            "Contains (1) 38-ounce party size bag of M&M'S Milk Chocolate Candy",
            "Enjoy a timeless and miniature treat made with real milk chocolate surrounded by a colorful candy shell",
        ],
        "accepted": "The frozen M&M'S page shows SKU B07W5B43Z8 at 11.79 dollars, rated 73 percent over twelve reviews, and describes one 38-ounce party bag with real milk chocolate inside colorful candy shells; its road-trip, trail-mix, everywhere and shell wording is seller copy and the page supplies no controlled hot-bag survival, exact thermal threshold, full current physical label, delivered trip cost or route safety result.",
    },
    {
        "evidence_id": "prop_skittles_packet_offer_scope",
        "subject": "frozen Skittles packet-tub seller page",
        "predicate": "shows_ninety_individually_wrapped_fruit_candy_packets",
        "object": "a 29.99-dollar SKU with no posted review described as ninety individually wrapped fun-size packets in a reusable tub and an unresolved one-ounce dimensions field",
        "source_url": SEARCHES[1][3],
        "search_id": "skittles_tub",
        "role": "product",
        "scope": "seller_offer_packet_and_flavor_copy_not_complete_label_total_mass_or_hot_route_result",
        "quotes": [
            "In stock SKU B09DQV8CK1 Be the first to review this product $29.99 Qty Add to Cart Add to Wish List Add to Compare",
            "This Bulk Candy Tub is filled 90 individually wrapped packages of Skittles candy.",
            "Each bag has a random assortment of flavors and may not contain one of each.",
        ],
        "accepted": "The frozen Skittles page shows SKU B09DQV8CK1 at 29.99 dollars with no posted review and describes ninety individually wrapped fun-size packets in a reusable tub with random flavor assortments; its one-ounce product-dimensions field does not resolve total edible mass and the page does not provide a complete physical ingredient label, exact glass-transition or humidity threshold, hot-route trial or safety result.",
    },
    {
        "evidence_id": "prop_jolly_rancher_hard_offer_scope",
        "subject": "frozen Jolly Rancher sour hard-candy seller page",
        "predicate": "shows_a_rated_thirteen_ounce_hard_shell_powder_center_offer",
        "object": "a 7.96-dollar SKU rated 85 percent over twelve reviews with thirteen ounces of twist-wrapped hard candy around sour powder centers",
        "source_url": SEARCHES[2][3],
        "search_id": "jolly_rancher_sour",
        "role": "product",
        "scope": "seller_offer_and_form_copy_not_no_softening_humidity_wrapper_or_route_guarantee",
        "quotes": [
            "In stock SKU B078JS8FPJ Rating: 85 % of 100 12 Reviews Add Your Review $7.96 Qty Add to Cart Add to Wish List Add to Compare",
            "That's right hard candy on the outside with a powder sour filled center",
            "Resealable bag contains 13 ounces of twist wrapped Jolly Rancher Sour Surge Hard Candy with Sour Powder Centers",
        ],
        "accepted": "The frozen Jolly Rancher page shows SKU B078JS8FPJ at 7.96 dollars, rated 85 percent over twelve reviews, and describes a thirteen-ounce resealable bag of twist-wrapped hard candy with sour powder centers; hard-candy wording alone does not prove that this exact lot will not soften, stick, absorb humidity, lose wrapper integrity or become unsafe in an unmeasured hot bag.",
    },
    {
        "evidence_id": "prop_charleston_chew_coating_scope",
        "subject": "frozen Charleston Chew seller page",
        "predicate": "shows_a_six_count_chocolatey_coated_nougat_offer_and_frozen_serving_copy",
        "object": "a 19.95-dollar SKU with no posted review whose selected title describes six 1.87-ounce nougat bars with a chocolatey coating and whose seller copy says they are frequently enjoyed frozen",
        "source_url": SEARCHES[3][3],
        "search_id": "charleston_chew",
        "role": "product",
        "scope": "seller_offer_coating_and_serving_copy_not_compound_identity_melting_range_or_hot_route_result",
        "quotes": [
            "In stock SKU B09Q5SNTNS Be the first to review this product $19.95 Flavor Name Chocolatey - 1.87 Ounce Strawberry - 1.87 Ounce Vanilla - 1.87 Ounce Variety Set Size 12 Count 6 Count",
            "Chewy, flavored nougat wrapped in a rich, chocolaty coating have made Charleston Chew an American favorite since its launch in 1922.",
            "They’re frequently enjoyed frozen, offering the classic “Charleston Chew crack” as folks love to break them into small pieces prior to eating.",
        ],
        "accepted": "The frozen Charleston Chew page shows SKU B09Q5SNTNS at 19.95 dollars with no posted review, and its selected title and options describe six 1.87-ounce nougat bars with a chocolatey coating while seller copy says they are often enjoyed frozen; that wording does not identify the current coating fat system, prove compound-chocolate status, quantify a melting range, resolve the physical package or establish hot-route portability.",
    },
    {
        "evidence_id": "prop_melting_point_scope",
        "subject": "generic melting-point concept",
        "predicate": "defines_a_condition_dependent_solid_liquid_equilibrium",
        "object": "melting point is a solid-to-liquid equilibrium temperature that depends on pressure while a table supplies only a generic cocoa-butter entry",
        "source_url": SEARCHES[4][3],
        "search_id": "melting_point",
        "role": "concept",
        "scope": "general_substance_definition_and_table_not_exact_candy_mixture_threshold_or_route_result",
        "quotes": [
            "The melting point (or, rarely, liquefaction point ) of a substance is the temperature at which it changes state from solid to liquid .",
            "At the melting point the solid and liquid phase exist in equilibrium .",
            "The melting point of a substance depends on pressure and is usually specified at a standard pressure such as 1 atmosphere or 100 kPa .",
        ],
        "accepted": "The frozen melting-point page defines the temperature where solid and liquid coexist in equilibrium and says melting point depends on pressure; even though its general table includes cocoa butter, the page does not measure any captured candy mixture, crystal history, bag exposure, softening behavior or exact route threshold.",
    },
    {
        "evidence_id": "prop_crystal_polymorphism_scope",
        "subject": "crystal polymorphism",
        "predicate": "permits_multiple_crystal_structures_and_physical_properties_at_one_composition",
        "object": "one compound can crystallize in multiple structures and polymorphism can change physical properties without chemical change",
        "source_url": SEARCHES[5][3],
        "search_id": "crystal_polymorphism",
        "role": "concept",
        "scope": "general_crystallography_not_identification_of_any_product_crystal_form_or_thermal_history",
        "quotes": [
            "In crystallography , polymorphism is the phenomenon where a compound or element can crystallize into more than one crystal structure .",
            "These defining facts imply that polymorphism involves changes in physical properties but cannot include chemical change.",
        ],
        "accepted": "The frozen crystal-polymorphism page says a compound or element may crystallize into more than one structure and that polymorphism can alter physical properties without chemical change; it does not identify a crystal form, tempering history, inversion point or melting behavior for either captured coated candy.",
    },
    {
        "evidence_id": "prop_compound_chocolate_scope",
        "subject": "compound chocolate and chocolatey coating",
        "predicate": "uses_cocoa_vegetable_fat_and_sweetener_with_distinct_processing",
        "object": "compound chocolate uses cocoa, vegetable fat and sweetener, may be called chocolatey coating, and does not require the tempering used for true chocolate",
        "source_url": SEARCHES[6][3],
        "search_id": "compound_chocolate",
        "role": "concept",
        "scope": "general_composition_label_and_processing_boundary_not_exact_sku_classification_or_heat_superiority",
        "quotes": [
            "Compound chocolate is a product made from a combination of cocoa, vegetable fat, and sweeteners.",
            "It may be known as \"compound coating\" or \"chocolaty coating\" when used as a coating for candy.",
            "Compound coatings, however, do not need to be tempered.",
        ],
        "accepted": "The frozen compound-chocolate page describes cocoa combined with vegetable fat and sweetener, says compound coating or chocolaty coating may name a candy coating, and distinguishes its processing from tempered true chocolate; these general statements neither classify the Charleston Chew label nor prove that any exact coating has a higher hot-route tolerance or safe temperature.",
    },
    {
        "evidence_id": "prop_hard_candy_formulation_scope",
        "subject": "hard-candy formulation",
        "predicate": "describes_a_nearly_all_sugar_low_water_amorphous_confection",
        "object": "hard candy is cooked sugar syrup with negligible final water that becomes stiff and brittle near room temperature and is described as amorphous",
        "source_url": SEARCHES[7][3],
        "search_id": "hard_candy",
        "role": "concept",
        "scope": "general_candy_class_not_exact_product_temperature_humidity_or_wrapper_threshold",
        "quotes": [
            "Most hard candy is nearly 100% sugar by weight, with a tiny amount of other ingredients for color or flavor, and negligible water content in the final product.",
            "After the boiled syrup cools, it is called hard candy , since it becomes stiff and brittle as it approaches room temperature .",
            "Hard candies are non-crystalline, amorphous candies containing about 98% (or more) solid sugar.",
        ],
        "accepted": "The frozen hard-candy page describes a nearly all-sugar, negligible-water confection that becomes stiff and brittle near room temperature and identifies hard candy as amorphous; it does not supply the exact Jolly Rancher formulation, glass-transition range, humidity response, wrapper performance or safe hot-bag result.",
    },
    {
        "evidence_id": "prop_glass_transition_scope",
        "subject": "glass transition in amorphous material",
        "predicate": "changes_hard_glassy_material_toward_viscous_or_rubbery_over_a_range",
        "object": "amorphous materials can move gradually and reversibly from hard and brittle toward viscous or rubbery as temperature rises, below crystalline melting when present",
        "source_url": SEARCHES[8][3],
        "search_id": "glass_transition",
        "role": "concept",
        "scope": "general_material_mechanism_not_exact_candy_tg_softening_or_route_threshold",
        "quotes": [
            "The glassâliquid transition , or glass transition , is the gradual and reversible transition in amorphous materials (or in amorphous regions within semicrystalline materials) from a hard and relatively brittle \"glassy\" state into a viscous or \"rubbery\" state as the temperature is increased.",
            "It is always lower than the melting temperature , T m , of the crystalline state of the material, if one exists",
        ],
        "accepted": "The frozen glass-transition page describes a gradual reversible change in amorphous material from hard and brittle toward viscous or rubbery as temperature rises and says its characteristic range is below crystalline melting when such a state exists; it gives no exact candy glass-transition value, composition, history or route threshold.",
    },
    {
        "evidence_id": "prop_hygroscopy_scope",
        "subject": "environmental moisture uptake",
        "predicate": "can_change_physical_properties_after_absorption_or_adsorption",
        "object": "hygroscopic materials attract and hold environmental water and can change properties including viscosity",
        "source_url": SEARCHES[9][3],
        "search_id": "hygroscopy",
        "role": "concept",
        "scope": "general_moisture_mechanism_not_exact_candy_humidity_wrapper_or_safety_result",
        "quotes": [
            "Hygroscopy is the phenomenon of attracting and holding water molecules via either absorption or adsorption from the surrounding environment",
            "adsorbing substances can become physically changed, e.g. changing in volume, boiling point , viscosity or some other physical characteristic or property of the substance.",
        ],
        "accepted": "The frozen hygroscopy page says materials can attract and hold environmental water through absorption or adsorption and that this can change physical properties including viscosity; it does not show that either fruit candy is hygroscopic to a particular degree or establish a humidity, wrapper, texture or safety threshold for the intended route.",
    },
    {
        "evidence_id": "prop_ice_pack_exposure_scope",
        "subject": "portable ice-pack cooling",
        "predicate": "absorbs_heat_with_requirements_dependent_on_load_and_exposure",
        "object": "reusable packs can keep food cool, absorb substantial heat, and require an amount dependent on load, start temperature, insulation, ambient temperature and direct sun",
        "source_url": SEARCHES[10][3],
        "search_id": "ice_pack",
        "role": "concept",
        "scope": "general_cooling_mechanism_not_a_validated_pannier_configuration_or_current_safety_instruction",
        "quotes": [
            "the reusable type is both used as a cold compress and to keep food cool in portable coolers or in insulated shipping containers to keep products cool during transport.",
            "Both ice and other non-toxic refrigerants can absorb a considerable amount of heat before they warm above their melting point .",
            "The amount of ice needed varies with the amount of food, its initial temperature, the thermal insulation of the cooler, and the ambient temperature and exposure to direct sunlight.",
        ],
        "accepted": "The frozen ice-pack page says reusable packs can keep food cool during transport, that ice and refrigerants absorb substantial heat, and that required ice varies with food amount, initial temperature, insulation, ambient temperature and direct sun; it does not validate a specific pack, placement, duration, condensation control or safety result in the user's pannier or backpack.",
    },
    {
        "evidence_id": "prop_shelf_stable_scope",
        "subject": "shelf-stable sealed food",
        "predicate": "depends_on_processing_packaging_and_sealed_room_temperature_storage",
        "object": "shelf-stable food can be stored at room temperature in a sealed container through product and packaging controls whose seal integrity matters",
        "source_url": SEARCHES[11][3],
        "search_id": "shelf_stable_food",
        "role": "concept",
        "scope": "general_storage_category_not_exact_label_hot_texture_open_package_or_current_safety_advice",
        "quotes": [
            "Shelf-stable food (also called non-perishable food , non-perishable(s) , or ambient food ) is food of a type that can be safely stored at room temperature in a sealed container.",
            "Various food preservation and packaging techniques are used to extend a food's shelf life.",
            "Package sterility and seal integrity are vital for commercially packaged shelf-stable food products.",
        ],
        "accepted": "The frozen shelf-stable-food page defines food that can be stored at room temperature in a sealed container, describes preservation and packaging controls, and says seal integrity matters; it does not classify any captured SKU, guarantee texture or wrapper stability at 90 degrees, supersede current storage directions, or establish safety after heat exposure or seal damage.",
    },
    {
        "evidence_id": "prop_sweat_wrapper_anecdote_scope",
        "subject": "sweat-covered paper-wrapped candy anecdote",
        "predicate": "reports_one_wrapper_becoming_soggy_after_a_workout_pocket_exposure",
        "object": "one author infers that a paper-wrapped unidentified candy was soggy after forty-five minutes in a pocket during vigorous exercise",
        "source_url": SEARCHES[12][3],
        "search_id": "sweat_candy",
        "role": "community",
        "scope": "single_author_unidentified_candy_body_heat_moisture_and_paper_wrapper_anecdote_not_route_trial",
        "quotes": [
            "I had just had the most vigorous workout I have had in a while (160-180 BPM for 45mins) with this paper-wrapped candy in my freaking pocket and it must've been soggy as all hell by the time I handed it to her.",
            "TL;DR: gave a girl a paper-wrapped candy that had been in my pocket for an entire 45min workout and she was rightfully disgusted.",
        ],
        "accepted": "One TIFU author infers that an unidentified paper-wrapped candy became soggy after forty-five minutes in a pocket during vigorous exercise; the anecdote motivates humidity and wrapper controls but supplies no measured temperature, candy identity, pannier or backpack condition, repeat, safety assessment or result for the four exact offers.",
    },
    {
        "evidence_id": "prop_old_cooler_anecdote_scope",
        "subject": "old large-cooler community discussion",
        "predicate": "contains_one_long_lived_cooling_claim_and_conflicting_model_reports",
        "object": "one title praises a roughly thirty-five-year-old large Igloo cooler with one bag of ice while comments report both success and hinge or newer-model failures",
        "source_url": SEARCHES[13][3],
        "search_id": "igloo_cooler",
        "role": "community",
        "scope": "author_unit_size_age_pack_ice_and_comment_specific_anecdotes_not_small_bag_performance",
        "quotes": [
            "My IGLOO large cooler. Been in the family for around 35 years and the thing is a beast. Strong durable plastic and keeps things freezing cold with even a single bag of ice.",
            "Bought a tiny red classic cooler for my work truck and the damn handle and side grommet (that swings the cap shut/open) broke within a month.",
            "My parents have one they bought in 1980 when we lived in the US and it still keeps things cold for days if you pack it closely enough.",
        ],
        "accepted": "The BuyItForLife discussion contains one title praising an approximately thirty-five-year-old large Igloo cooler with one bag of ice, plus comments reporting both another old unit keeping cold when closely packed and failures in other units; these anecdotes are unit-, size-, age-, packing- and author-specific and cannot establish performance in a small pannier or backpack.",
    },
    {
        "evidence_id": "prop_salt_ice_discussion_scope",
        "subject": "salt-and-ice cooler discussion",
        "predicate": "reports_an_untimed_claim_and_disagreement_about_temperature_and_duration",
        "object": "the author says fishermen had not timed a claim that salt slurry stays cold longer while comments discuss lower equilibrium temperature, endothermic melting and faster environmental heat transfer",
        "source_url": SEARCHES[14][3],
        "search_id": "salt_ice",
        "role": "community",
        "scope": "forum_mechanism_discussion_not_validated_protocol_food_safety_or_snack_transport_recommendation",
        "quotes": [
            "These same fishermen claim that the resulting slurry stays cold much LONGER than just a cooler of ice without the salt. They've done no experiments with timing it, they just make the claim.",
            "Melting is an endothermic process. This process will \"remove\" heat via bond breaking in the ice.",
            "The larger temperature difference between the ice-water mixture and the ambient temperature will cause the mixture to absorb heat faster, thus speeding up the warming process.",
        ],
        "accepted": "The AskScience thread says fishermen had not timed their claim that a salt slurry stays cold longer, and comments discuss a lower equilibrium temperature, endothermic melting and competing environmental heat-transfer effects; it is a disputed community mechanism discussion, not a validated portable-cooling protocol, food-safety instruction or result for a sweet snack.",
    },
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
            "http://localhost:8081/search?capture_run="
            f"{RUN_ID}&request_id={payload['request_id']}"
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
            "registry_id": "reg_case_spec_hot_weather_portability_0050",
            "source_url": case_source,
            "source_type": "case_spec",
            "content_sha256": sha256_bytes(CASE_SPEC.read_bytes()),
            "blob_path": CASE_SPEC_REL.as_posix(),
            "in_corpus": True,
        }
    )

    for item in EVIDENCE:
        content = raw_content_by_url[item["source_url"]]
        spans: list[dict[str, Any]] = []
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
        (
            "bridge_exact_offer_heat_form_matrix",
            "bridge",
            "four exact sweet-snack seller snapshots",
            "retains_offer_fields_forms_packaging_and_missing_heat_evidence",
            "record each exact SKU price rating review count pack mass form coating wrapper and unresolved label field without converting seller wording into a hot-route result",
            "exact_offer_heat_form_matrix_v1",
        ),
        (
            "bridge_chocolate_phase_and_coating_boundary",
            "bridge",
            "melting polymorphism and coating evidence",
            "separates_general_phase_mechanisms_from_exact_sku_thresholds",
            "use melting polymorphism and compound-coating concepts only as mechanisms while requiring current exact composition crystal history and measured product behavior before classification or thermal prediction",
            "chocolate_phase_and_coating_boundary_v1",
        ),
        (
            "bridge_sugar_glass_humidity_boundary",
            "bridge",
            "hard candy glass transition and moisture evidence",
            "separates_softening_sticking_and_humidity_failure_from_classic_melting",
            "treat hard-candy form glass transition and hygroscopy as distinct possible failure paths while requiring exact formulation humidity temperature wrapper and trial evidence",
            "sugar_glass_humidity_boundary_v1",
        ),
        (
            "bridge_transport_cooling_exposure_boundary",
            "bridge",
            "portable cooling and community transport evidence",
            "requires_measured_bag_exposure_and_validated_cooling_configuration",
            "retain ice-pack load insulation ambient sun and start-temperature dependencies and keep cooler salt-ice and sweat anecdotes scoped instead of transferring them to a pannier or backpack",
            "transport_cooling_exposure_boundary_v1",
        ),
        (
            "bridge_current_label_safety_route_gate",
            "bridge",
            "current package safety and route profile",
            "blocks_unknown_label_seal_storage_filling_allergen_and_exposure_cells",
            "verify exact physical identity complete label allergens filling storage directions lot seal delivered cost and measured route temperature humidity sun duration and position before any safety or portability verdict",
            "current_label_safety_route_gate_v1",
        ),
        (
            "bridge_matched_hot_route_portability_trial",
            "bridge",
            "small contained route exposure comparison",
            "measures_local_mess_texture_and_burden_under_matched_conditions",
            "use identified lots identical secondary containment matched start temperature route duration and position logged heat and humidity separate cooling factors and predeclared leakage wrapper shape texture waste and carry-burden thresholds",
            "matched_hot_route_portability_trial_v1",
        ),
        (
            "decision_evidence_bounded_hot_weather_snack_choice",
            "decision",
            "summer pannier and hiking-pack sweet choice",
            "selects_only_the_lowest_trip_cost_passing_exact_path_or_control_or_deferral",
            "reject inherent heatproof brand claims and choose only the lowest total trip cost and carry-burden exact path passing current label safety packaging and matched route-exposure gates otherwise use a proven route control or defer",
            "evidence_bounded_hot_weather_snack_choice_v1",
        ),
    ]
    for evidence_id, node_type, subject, predicate, obj, rule_id in deterministic_nodes:
        metadata: dict[str, Any] = {"rule_id": rule_id, "topic_cluster": TOPIC}
        if node_type == "decision":
            metadata["oracle_unique_or_admissible"] = True
        nodes.append(
            {
                "evidence_id": evidence_id,
                "node_type": node_type,
                "subject": subject,
                "predicate": predicate,
                "object": obj,
                "source_url": case_source,
                "verifier": {"kind": "deterministic_rule"},
                "metadata": metadata,
            }
        )

    derives: dict[str, list[str]] = {
        "bridge_exact_offer_heat_form_matrix": [
            "prop_mms_offer_shell_scope",
            "prop_skittles_packet_offer_scope",
            "prop_jolly_rancher_hard_offer_scope",
            "prop_charleston_chew_coating_scope",
        ],
        "bridge_chocolate_phase_and_coating_boundary": [
            "prop_mms_offer_shell_scope",
            "prop_charleston_chew_coating_scope",
            "prop_melting_point_scope",
            "prop_crystal_polymorphism_scope",
            "prop_compound_chocolate_scope",
        ],
        "bridge_sugar_glass_humidity_boundary": [
            "prop_skittles_packet_offer_scope",
            "prop_jolly_rancher_hard_offer_scope",
            "prop_hard_candy_formulation_scope",
            "prop_glass_transition_scope",
            "prop_hygroscopy_scope",
            "prop_sweat_wrapper_anecdote_scope",
        ],
        "bridge_transport_cooling_exposure_boundary": [
            "prop_melting_point_scope",
            "prop_ice_pack_exposure_scope",
            "prop_sweat_wrapper_anecdote_scope",
            "prop_old_cooler_anecdote_scope",
            "prop_salt_ice_discussion_scope",
        ],
        "bridge_current_label_safety_route_gate": [
            "bridge_exact_offer_heat_form_matrix",
            "bridge_chocolate_phase_and_coating_boundary",
            "bridge_sugar_glass_humidity_boundary",
            "bridge_transport_cooling_exposure_boundary",
            "prop_shelf_stable_scope",
        ],
        "bridge_matched_hot_route_portability_trial": [
            "bridge_exact_offer_heat_form_matrix",
            "bridge_chocolate_phase_and_coating_boundary",
            "bridge_sugar_glass_humidity_boundary",
            "bridge_transport_cooling_exposure_boundary",
            "bridge_current_label_safety_route_gate",
            "prop_sweat_wrapper_anecdote_scope",
            "prop_old_cooler_anecdote_scope",
            "prop_salt_ice_discussion_scope",
        ],
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
                "source_id": "decision_evidence_bounded_hot_weather_snack_choice",
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
