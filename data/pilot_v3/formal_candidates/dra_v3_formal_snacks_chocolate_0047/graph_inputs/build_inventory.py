#!/usr/bin/env python3
"""Build the frozen Q47 ten-week chocolate-and-nut stash inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
SNAPSHOT = "dra-v3-formal-snacks-chocolate-0047-ten-week-stash-bloom-oxidation-20260716-r1"
RUN_ID = "v3-corpus-formal-snacks-chocolate-0047-ten-week-stash-bloom-oxidation-20260716-r1"
CAPTURE_REL = Path("data/evidence_graph/captures") / RUN_ID
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_snacks_chocolate_0047/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
TASK_ID = "dra_v3_formal_snacks_chocolate_0047"
TOPIC = "ten_week_chocolate_nut_stash_bloom_oxidation"


SEARCHES = [
    ("hershey_individual", "001-shopping-hershey-individually-wrapped-dark.json", "Hershey individually wrapped snack bars", "http://localhost:7770/hershey-s-special-dark-mildly-sweet-dark-chocolate-snack-size-candy-individually-wrapped-3-6-oz-pack-8-ct.html"),
    ("ghirardelli_bulk", "002-shopping-ghirardelli-bulk-dark-squares.json", "Ghirardelli five-pound bulk squares", "http://localhost:7770/west-end-foods-bundle-of-ghirardelli-bulk-dark-chocolate-60-cacao-squares-5-pound.html"),
    ("blue_diamond", "003-shopping-blue-diamond-dark-almonds.json", "Blue Diamond cocoa-flavored almonds", "http://localhost:7770/blue-diamond-almonds-oven-roasted-dark-chocolate-flavored-snack-nuts-14-oz-resealable-bag-pack-of-1.html"),
    ("second_nature", "004-shopping-second-nature-trail-mix-pouches.json", "Second Nature twelve-pouch trail mix", "http://localhost:7770/second-nature-dark-chocolate-medley-trail-mix-4-5-oz-resealable-pouch-pack-of-12-certified-gluten-free-snack-dark-chocolate-and-nut-trail-mix-ideal-for-quick-travel-snacks-1107-cp12.html"),
    ("oh_nuts", "005-shopping-oh-nuts-bulk-almonds.json", "Oh Nuts selected two-pound almond bag", "http://localhost:7770/oh-nuts-dry-roasted-unsalted-almonds-fresh-healthy-tasty-almonds-no-salt-no-oil-all-natural-protein-keto-snacks-resealable-2-lb-bulk-bag-low-sodium-vegan-gluten-free-snacking.html"),
    ("chocolate_bloom", "006-wiki-chocolate-bloom-boundary.json", "chocolate bloom mechanism and boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Chocolate_bloom"),
    ("tempered_chocolate", "007-wiki-tempered-chocolate-crystals.json", "tempering and cocoa-butter crystal mechanism", "http://localhost:8090/content/wikipedia_en_all_nopic/Tempered_chocolate"),
    ("autoxidation", "008-wiki-autoxidation-lipid-mechanism.json", "autoxidation and food rancidity mechanism", "http://localhost:8090/content/wikipedia_en_all_nopic/Autoxidation"),
    ("mvtr", "009-wiki-moisture-vapor-transmission.json", "moisture-vapor transmission conditions", "http://localhost:8090/content/wikipedia_en_all_nopic/Moisture_vapor_transmission_rate"),
    ("otr", "010-wiki-oxygen-transmission-rate.json", "oxygen transmission and whole-package boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Oxygen_transmission_rate"),
    ("discrimination", "011-wiki-discrimination-sensory-testing.json", "sensory discrimination-test boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Discrimination_testing"),
    ("pocket_melt", "012-forum-pocket-melt-incident.json", "pocket chocolate melt incident", "http://localhost:9999/f/tifu/135236/tifu-by-putting-a-chocolate-easter-egg-in-my-pocket-and"),
    ("bag_clip", "013-forum-snack-bag-clip-tip.json", "opened snack-bag clip discussion", "http://localhost:9999/f/LifeProTips/77452/lpt-when-packing-snacks-like-chips-pretzels-for-vacation"),
    ("label_storage", "014-forum-label-storage-containers.json", "stored-container labeling tip", "http://localhost:9999/f/LifeProTips/77711/lpt-you-know-that-unmarked-bag-box-or-container-you-think"),
    ("block_chocolate", "015-forum-block-chocolate-availability.json", "Boston block-chocolate sourcing discussion", "http://localhost:9999/f/boston/38504/block-chocolate"),
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
        "prop_hershey_individual_scope",
        "frozen Hershey snack-size seller page",
        "shows_individual_wrappers_and_a_quantity_conflict",
        "a 6.87-dollar no-review offer whose title and quick look say one 3.6-ounce pack of eight individually wrapped 45-percent-cocoa bars while Product Dimensions reports 1.41 ounces",
        0, "product", "seller_offer_and_internal_mass_conflict_not_ten_week_result",
        [
            "HERSHEY'S Special Dark Mildly Sweet Dark Chocolate Snack Size Candy, Individually Wrapped, 3.6 oz Pack (8 ct)",
            "In stock SKU B01M68WYTJ Be the first to review this product $6.87",
            "Contains one (1) 3.6-ounce pack of 8 snack-size HERSHEY'S SPECIAL DARK Mildly Sweet Chocolate Bars",
            "Product Dimensions ‏ ‎ 0.42 x 8.97 x 2.93 inches; 1.41 Ounces",
        ],
        "The frozen Hershey page shows SKU B01M68WYTJ at 6.87 dollars with no reviews shown; its title and quick look describe one 3.6-ounce pack of eight individually wrapped snack-size bars with 45-percent cocoa, while Product Dimensions reports 1.41 ounces. The discrepancy remains unresolved, and individual wrapping plus seller freshness wording does not establish the exact delivered lot, package barrier, date, storage history or week-ten sensory quality.",
    ),
    ev(
        "prop_ghirardelli_bulk_scope",
        "frozen West End Foods Ghirardelli seller page",
        "shows_a_five_pound_reseller_bundle",
        "a 79.99-dollar no-review offer selected as five pounds of Ghirardelli 60-percent cacao squares and hand packed by West End Foods",
        1, "product", "seller_bulk_bundle_not_original_wrapper_or_ten_week_result",
        [
            "West End Foods Bundle of Ghirardelli Bulk Dark Chocolate 60% Cacao Squares (5 pound)",
            "In stock SKU B075V1Y762 Be the first to review this product $79.99 Size 3 Pound 5 Pound",
            "The Chocolate Snacks are hand picked and pack by West End Foods",
        ],
        "The frozen West End Foods page shows SKU B075V1Y762 at 79.99 dollars with no reviews shown and describes a selected five-pound bundle of Ghirardelli 60-percent cacao squares hand-picked and packed by West End Foods. It does not independently establish original individual wrappers, exact piece count, lot and date, complete package construction, current delivered cost or ten-week retention.",
    ),
    ev(
        "prop_blue_diamond_resealable_scope",
        "frozen Blue Diamond almond seller page",
        "shows_one_resealable_cocoa_flavored_bag",
        "a 7.70-dollar 14-ounce bag rated 83 percent over twelve reviews and described as almonds covered in real cocoa powder with dark-chocolate flavor",
        2, "product", "seller_bag_rating_and_flavor_copy_not_barrier_or_ten_week_result",
        [
            "Blue Diamond Almonds Oven Roasted Dark Chocolate Flavored Snack Nuts, 14 Oz Resealable Bag (Pack of 1)",
            "In stock SKU B0051TPWG2 Rating: 83 % of 100 12 Reviews Add Your Review $7.70",
            "Resealable bag makes this a perfect travel snack for adults and children on the way to the office, school, or just on the go",
        ],
        "The frozen Blue Diamond page shows SKU B0051TPWG2 at 7.70 dollars, rated 83 percent over twelve reviews, and describes one 14-ounce resealable bag of almonds covered in cocoa powder and dark-chocolate flavor. It is not a plain chocolate bar, and the rating and resealability do not establish exact package barrier, opening history, lot age or week-ten freshness.",
    ),
    ev(
        "prop_second_nature_multi_pouch_scope",
        "frozen Second Nature trail-mix seller page",
        "shows_twelve_resealable_pouches_and_a_warm_weather_warning",
        "a 39.85-dollar no-review offer described as twelve 4.5-ounce pouches containing dark chocolate almonds cashews and pecans while Product Dimensions reports 4.5 ounces",
        3, "product", "seller_multi_pouch_and_weather_copy_not_exact_delivery_or_ten_week_result",
        [
            "In stock SKU B0758FJ52X Be the first to review this product $39.85",
            "There are (12) 4.5 oz resealable standup pouches of delightfully wholesome snacks included.",
            "(Consider faster shipping options during warmer months to accommodate weather effects on chocolate)",
            "Product Dimensions ‏ ‎ 11.8 x 5.7 x 8.8 inches; 4.5 Ounces",
        ],
        "The frozen Second Nature page shows SKU B0758FJ52X at 39.85 dollars with no reviews shown and describes twelve 4.5-ounce resealable pouches containing dark chocolate, almonds, cashews and pecans, plus a warm-weather shipping caution, while Product Dimensions reports 4.5 ounces. The selected delivered variant, total net quantity and heat history require verification, and multiple pouches do not prove week-ten quality.",
    ),
    ev(
        "prop_oh_nuts_bulk_scope",
        "frozen Oh Nuts almond seller page",
        "shows_a_selected_two_pound_zip_lock_offer_and_mass_conflict",
        "a 21.99-dollar offer rated 85 percent over twelve reviews with selected two-pound wording and freshness claims while Package Dimensions reports 1.2 pounds",
        4, "product", "seller_bulk_freshness_claim_and_mass_conflict_not_oxidation_test",
        [
            "In stock SKU B00C6ALV0U Rating: 85 % of 100 12 Reviews Add Your Review $21.99 Weight 2.0 Pounds 5.0 Pounds",
            "No more rancid nuts! With Oh! Nuts you get the freshest, high-quality organic almonds.",
            "Once the bag has been opened, the zip lock keeps the nuts fresh and tasty.",
            "Package Dimensions ‏ ‎ 9.8 x 7.5 x 2.2 inches; 1.2 Pounds",
        ],
        "The frozen Oh Nuts page shows SKU B00C6ALV0U at 21.99 dollars, rated 85 percent over twelve reviews, with a selected two-pound option and zip-lock freshness and no-more-rancid-nuts copy, while Package Dimensions reports 1.2 pounds. The mass conflict remains unresolved, and seller claims do not measure the exact lot's oxygen exposure, oxidation rate, package barrier or week-ten sensory outcome.",
    ),
    ev(
        "prop_bloom_mechanism_boundary",
        "chocolate bloom mechanism",
        "distinguishes_fat_and_sugar_bloom_from_shelf_life",
        "a whitish coating can arise from fat-crystal change or moisture acting on sugar and harms appearance or texture without itself limiting shelf life",
        5, "concept", "general_bloom_classification_not_exact_lot_safety_or_cheapness_proof",
        [
            "Chocolate bloom is either of two types of whitish coating that can appear on the surface of chocolate : fat bloom, caused by changes in the fat crystals in the chocolate; and sugar bloom, due to crystals formed by the action of moisture on the sugar.",
            "Fat and sugar bloom damage the appearance of chocolate but do not limit its shelf life.",
            "Chocolate that has \"bloomed\" is still safe to eat (as it is a non-perishable food due to its sugar content), but may have an unappetizing appearance and surface texture.",
        ],
        "The chocolate-bloom page distinguishes fat bloom caused by fat-crystal changes from sugar bloom caused by moisture acting on sugar and says bloom damages appearance and may make texture unappetizing without limiting shelf life. Its general edibility statement classifies bloom itself; it does not prove cheap ingredients, authenticate an exact lot, or rule out contamination, allergens, package failure or another spoilage process.",
    ),
    ev(
        "prop_tempering_crystal_scope",
        "tempered chocolate mechanism",
        "links_controlled_cocoa_butter_crystallization_to_snap_gloss_and_bloom_resistance",
        "cooling agitating and reheating promote stable cocoa-butter crystal forms and improve gloss snap texture and bloom resistance",
        6, "concept", "general_crystal_mechanism_not_exact_product_process_history",
        [
            "Tempering is a technique applied in chocolate production to create chocolate that is glossy , has a good snap and smoother texture and is more resistant to chocolate bloom .",
            "It involves cooling liquid chocolate while agitating it until a small amount of cocoa butter crystallizes . The liquid is then heated to maintain only the most stable crystal forms",
            "This ability of cocoa butter to crystallize in different forms is known as polymorphism .",
        ],
        "The tempered-chocolate page links controlled cooling, agitation and reheating to stable cocoa-butter crystal forms, gloss, snap, smoother texture and bloom resistance. This explains a mechanism but does not reveal the exact tempering history, current crystal form, formula or future storage result of any captured offer.",
    ),
    ev(
        "prop_autoxidation_food_rancidity_scope",
        "autoxidation and rancidity",
        "links_ambient_oxygen_reactions_to_gradual_degradation_and_food_rancidity",
        "oxygen at normal temperatures can drive free-radical degradation and rancidity over time",
        7, "concept", "general_reaction_mechanism_not_exact_lot_rate_or_ten_week_prediction",
        [
            "Autoxidation (sometimes auto-oxidation ) refers to oxidations brought about by reactions with oxygen at normal temperatures, without the intervention of flame or electric spark.",
            "The term is usually used to describe the gradual degradation of organic compounds in air at ambient temperatures.",
            "Many common phenomena can be attributed to autoxidation, such as food going rancid",
            "The common mechanism is a free radical chain reaction , where the addition of oxygen gives rise to hydroperoxides and their associated peroxy radicals",
        ],
        "The autoxidation page describes oxygen-driven gradual degradation at ambient temperatures, associates it with food rancidity, and gives a free-radical chain mechanism. It supplies no exact almond-lot oxidation rate, induction period, oxygen exposure, packaging result, sensory threshold or ten-week prediction.",
    ),
    ev(
        "prop_mvtr_package_test_scope",
        "moisture-vapor transmission measurement",
        "requires_declared_conditions_and_complete_package_validation",
        "MVTR depends on conditions and material thickness while seams creases access points heat seals and closures can control whole-package performance",
        8, "concept", "general_measurement_boundary_not_exact_offer_package_result",
        [
            "Moisture vapor transmission rate ( MVTR ), also water vapor transmission rate ( WVTR ), is a measure of the passage of water vapor through a substance.",
            "Both the temperature and humidity gradients across the sample need to be measured, controlled and recorded with the result, and the thickness of the sample should be the same.",
            "An MVTR result without specifying these conditions is almost meaningless.",
            "Seams, creases, access points, and heat seals are critical to end-use performance.",
        ],
        "The MVTR page defines water-vapor passage and says temperature, humidity gradients and thickness must be controlled and recorded, with results nearly meaningless without conditions. It also says seams, creases, access points and heat seals affect end use, so a generic sheet mechanism or resealable label cannot establish any exact offer's complete-package moisture barrier.",
    ),
    ev(
        "prop_otr_package_test_scope",
        "oxygen transmission measurement",
        "requires_time_and_complete_package_structure",
        "OTR measures oxygen passage over time and completed packages include seals creases joints and closures that can reduce effective barrier",
        9, "concept", "general_measurement_boundary_not_exact_offer_package_result",
        [
            "Oxygen transmission rate ( OTR ) is the measurement of the amount of oxygen gas that passes through a substance over a given period.",
            "It relates to the permeation of oxygen through packaging [ 1 ] to sensitive foods and pharmaceuticals .",
            "Completed packages, however, involve heat seals, creases, joints, and closures which often reduce the effective barrier of the package.",
        ],
        "The OTR page defines oxygen passage over a period and relates it to food packaging, while warning that completed packages include heat seals, creases, joints and closures that affect effective barrier. It gives no exact material, opening state, test conditions or whole-package result for the captured offers and therefore cannot rank them.",
    ),
    ev(
        "prop_discrimination_testing_scope",
        "sensory discrimination testing",
        "detects_differences_without_quantifying_preference_or_proving_equality",
        "trained assessors and experimental designs can test detectable difference but generally do not quantify differences and failure to reject no difference is not evidence of equality",
        10, "concept", "general_sensory_method_boundary_not_exact_product_result",
        [
            "Discrimination testing is a technique employed in sensory analysis to determine whether there is a detectable difference among two or more products.",
            "Though useful, these tests typically do not quantify or describe any differences, requiring a more specifically trained panel under different study design to describe differences and assess significance of the difference.",
            "However, failure to reject H 0 should not be assumed to be sufficient evidence to accept it.",
        ],
        "The discrimination-testing page describes tests for detectable differences using panellists and experimental designs, says they generally do not quantify or describe the differences, and warns that failure to reject a no-difference null is not evidence for equality. Preference magnitude and acceptability therefore require separate measures, and the page supplies no result for these offers.",
    ),
    ev(
        "prop_pocket_melt_incident_scope",
        "pocket chocolate melt incident",
        "reports_one_body_heat_exposure_event",
        "one foil-wrapped egg became gooey after several hours in a jeans pocket during a flight",
        11, "community", "single_author_incident_not_controlled_storage_or_exact_offer_test",
        [
            "Without thinking I put foil-wrapped goodie in my jeans pocket",
            "Several hours into my flight to New York I put my hand in my pocket",
            "I had a pocket full of gooey melted chocolate!",
        ],
        "The thread reports one foil-wrapped chocolate egg becoming gooey after several hours in a jeans pocket. It supports treating heat exposure as an operational variable but is not a measured temperature history, bloom diagnosis, package comparison, ten-week storage trial or result for any exact offer.",
    ),
    ev(
        "prop_bag_clip_tip_scope",
        "opened snack-bag clip discussion",
        "contains_a_space_saving_tip_and_an_oxygen_counterpoint",
        "the author suggests opening and clipping a bag while a reply warns that doing so admits oxygen to a nitrogen-rich package and may accelerate staling",
        12, "community", "author_and_reply_scoped_tip_not_controlled_barrier_test",
        [
            "open the bag and push the extra air out, then clip it shut.",
            "The \"air\" in a sealed bag of chips is mostly nitrogen.",
            "Opening the bag is letting oxygen into a mostly oxygen free environment and will cause your snack to go stale faster.",
        ],
        "The snack-bag thread proposes opening, squeezing and clipping a bag for travel space, while a reply says the sealed headspace is mostly nitrogen and opening admits oxygen that can speed staling. These are scoped statements rather than controlled barrier measurements, but they justify preserving original seals and recording opening state instead of assuming a clip restores the package.",
    ),
    ev(
        "prop_label_storage_tip_scope",
        "stored-container labeling tip",
        "recommends_preserving_identity_and_date_context",
        "the author recommends labeling decanted or stored bags boxes and containers because their contents and dates are later forgotten",
        13, "community", "operational_traceability_tip_not_freshness_or_safety_test",
        [
            "If you decant something into an unmarked container, put a box away for storage, or collect something in a ziplock bag",
            "wonder when it was from, what it contains, all so you can figure out what to do with it.",
            "grab a marker or pen and clearly label whatever it is",
        ],
        "The labeling thread says people later forget the contents and dates of decanted or stored containers and recommends clear labels. This supports receipt, lot and opening-date traceability but is not evidence that labeling preserves quality, validates a best-before date or makes an item safe.",
    ),
    ev(
        "prop_block_chocolate_availability_scope",
        "Boston block-chocolate sourcing discussion",
        "contains_local_historical_availability_price_and_preference_comments",
        "an author seeking block dark and white chocolate for bark receives time- and location-scoped store brand and price suggestions",
        14, "community", "local_historical_sourcing_discussion_not_exact_offer_or_durability_test",
        [
            "Anyone know a good location to get some block chocolate? I'd like to make some Bark again for Christmas.",
            "Most grocery stores don't seem to carry such. Any good ideas?",
            "Trader Joe's Pound Plus chocolate bars are 17.6 oz and cost $4.99.",
        ],
        "The Boston thread asks where to find block chocolate for bark and contains historical local store, price, quality and preference suggestions. It motivates checking current rural availability and product form but does not verify any captured offer, current price, packaging, shelf life or ten-week quality.",
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
    capture_documents = json.loads((CAPTURE / "documents.json").read_text(encoding="utf-8"))["documents"]
    documents: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for search_id, filename, subject, target_url in SEARCHES:
        path = CAPTURE / "searches" / filename
        data = path.read_bytes()
        payload = json.loads(data)
        source_url = f"http://localhost:8081/search?capture_run={RUN_ID}&request_id={payload['request_id']}"
        documents.append({
            "registry_id": f"reg_search_{search_id}", "source_url": source_url,
            "source_type": "search_result", "content_sha256": sha256_bytes(data),
            "blob_path": rel(path), "in_corpus": True,
        })
        nodes.append({
            "evidence_id": f"search_{search_id}", "node_type": "search_result",
            "subject": subject, "predicate": "returned", "object": [target_url],
            "source_url": source_url, "body_support": False, "search_snippet_support": True,
            "verifier": {"kind": "search_observation"},
            "metadata": {"discovery_root": True, "discovery_root_policy": "search_result", "topic_cluster": TOPIC},
        })

    raw_content_by_url: dict[str, str] = {}
    for row in capture_documents:
        documents.append({
            "registry_id": row["registry_id"], "source_url": row["source_url"],
            "source_type": row["source_type"], "content_sha256": row["content_sha256"],
            "blob_path": (CAPTURE_REL / row["blob_path"]).as_posix(), "in_corpus": True,
        })
        raw_content_by_url[row["source_url"]] = (CAPTURE / row["blob_path"]).read_text(encoding="utf-8")

    case_source = f"http://case-spec.local/{TASK_ID}"
    documents.append({
        "registry_id": "reg_case_spec_chocolate_stash_0047", "source_url": case_source,
        "source_type": "case_spec", "content_sha256": sha256_bytes(CASE_SPEC.read_bytes()),
        "blob_path": CASE_SPEC_REL.as_posix(), "in_corpus": True,
    })

    for item in EVIDENCE:
        content = raw_content_by_url[item["source_url"]]
        spans = []
        for index, quote in enumerate(item["quotes"], start=1):
            if quote not in content:
                raise ValueError(f"quote missing from {item['evidence_id']}: {quote!r}")
            spans.append({
                "support_span_id": f"span_{item['evidence_id']}_{index}",
                "exact_quote": quote, "occurrence": 0, "support_type": "body",
            })
        nodes.append({
            "evidence_id": item["evidence_id"], "node_type": "proposition",
            "subject": item["subject"], "predicate": item["predicate"], "object": item["object"],
            "source_url": item["source_url"], "support_spans": spans,
            "verifier": typed_verifier(item["accepted"]),
            "metadata": {"acceptable_source_roles": [item["role"]], "critical": True, "scope": item["scope"], "topic_cluster": TOPIC},
        })
        assertion_id = f"assert_{item['evidence_id'].removeprefix('prop_')}"
        nodes.append({
            "evidence_id": assertion_id, "node_type": "assertion",
            "subject": f"source for {item['subject']}", "predicate": "states", "object": item["object"],
            "source_url": item["source_url"],
            "support_spans": [{"support_span_id": f"span_{assertion_id}_1", "exact_quote": item["quotes"][0], "occurrence": 0, "support_type": "body"}],
            "verifier": {"kind": "quoted_assertion"}, "metadata": {"topic_cluster": TOPIC},
        })
        edges.extend([
            {"edge_id": f"edge_assert_{item['evidence_id']}", "source_id": assertion_id, "relation": "ASSERTS", "target_id": item["evidence_id"]},
            {"edge_id": f"edge_discover_{item['evidence_id']}", "source_id": item["evidence_id"], "relation": "DISCOVERABLE_FROM", "target_id": f"search_{item['search_id']}", "discovery_method": "S", "discovery_order": 1},
        ])

    deterministic_nodes = [
        ("bridge_bloom_temper_crystal_boundary", "bridge", "bloom and cocoa-butter crystal evidence", "separates_bloom_from_cheapness_and_other_failure_modes", "classify fat and sugar bloom and connect tempering to crystal stability without treating bloom as cheapness spoilage universal unsafety or exact process proof", "bloom_temper_crystal_boundary_v1"),
        ("bridge_community_operational_scope", "bridge", "four community storage and sourcing discussions", "retains_incident_author_place_time_and_product_scope", "extract heat original-seal labeling and availability variables while refusing to convert anecdotes tips replies and local history into ten-week trials", "community_operational_scope_v1"),
        ("bridge_independent_unit_rotation_cost", "bridge", "exact offers package uncertainty and rural commitment", "requires_identity_rotation_and_waste_adjusted_cost", "verify exact identity package and dates preserve sealed independent units and compare delivered cost per week-ten accepted serving rather than ratings mass or seller freshness copy", "independent_unit_rotation_cost_v1"),
        ("bridge_oxidation_package_measurement_boundary", "bridge", "autoxidation MVTR and OTR evidence", "requires_exact_package_conditions_before_durability_inference", "retain oxygen and moisture mechanisms while requiring exact material whole-package opening-state and test-condition evidence before ranking offers", "oxidation_package_measurement_boundary_v1"),
        ("bridge_seller_offer_identity_conflict_scope", "bridge", "five frozen seller offers", "retains_literal_fields_conflicts_and_missing_lot_package_results", "record exact seller fields while preserving Hershey and Oh Nuts mass conflicts and rejecting wrappers pouches ratings resealability bulk and freshness wording as ten-week proof", "seller_offer_identity_conflict_scope_v1"),
        ("bridge_staged_ten_week_sensory_protocol", "bridge", "week-zero through week-ten retention trial", "requires_sealed_timepoint_units_environment_logs_and_bounded_sensory_tests", "allocate same-lot independent units log conditions apply safety stops and separate bloom classification discrimination and acceptability while refusing unmatched causal package claims", "staged_ten_week_sensory_protocol_v1"),
        ("bridge_stash_decision_preparation", "bridge", "evidence-bounded rural stash plan", "combines_offer_mechanism_rotation_protocol_and_cost_gates", "integrate all branches into a least-commitment week-ten test and waste-cost decision without naming an immediate universal product or package winner", "stash_decision_preparation_v1"),
        ("decision_evidence_bounded_stash", "decision", "ten-week rural chocolate-and-nut stash", "selects_only_a_least_commitment_exact_passing_configuration_or_shorter_horizon_or_deferral", "choose only the smallest independent-unit rotation passing identity package condition week-ten sensory and waste-adjusted cost gates otherwise shorten the horizon or defer", "evidence_bounded_stash_decision_v1"),
    ]
    for evidence_id, node_type, subject, predicate, object_, rule_id in deterministic_nodes:
        metadata: dict[str, Any] = {"rule_id": rule_id, "topic_cluster": TOPIC}
        if node_type == "decision":
            metadata["oracle_unique_or_admissible"] = True
        nodes.append({
            "evidence_id": evidence_id, "node_type": node_type, "subject": subject,
            "predicate": predicate, "object": object_, "source_url": case_source,
            "verifier": {"kind": "deterministic_rule"}, "metadata": metadata,
        })

    derives = {
        "bridge_bloom_temper_crystal_boundary": ["prop_bloom_mechanism_boundary", "prop_tempering_crystal_scope"],
        "bridge_community_operational_scope": ["prop_bag_clip_tip_scope", "prop_block_chocolate_availability_scope", "prop_label_storage_tip_scope", "prop_pocket_melt_incident_scope"],
        "bridge_oxidation_package_measurement_boundary": ["prop_autoxidation_food_rancidity_scope", "prop_mvtr_package_test_scope", "prop_otr_package_test_scope"],
        "bridge_seller_offer_identity_conflict_scope": ["prop_blue_diamond_resealable_scope", "prop_ghirardelli_bulk_scope", "prop_hershey_individual_scope", "prop_oh_nuts_bulk_scope", "prop_second_nature_multi_pouch_scope"],
        "bridge_independent_unit_rotation_cost": ["bridge_community_operational_scope", "bridge_oxidation_package_measurement_boundary", "prop_blue_diamond_resealable_scope", "prop_ghirardelli_bulk_scope", "prop_hershey_individual_scope", "prop_oh_nuts_bulk_scope", "prop_second_nature_multi_pouch_scope"],
        "bridge_staged_ten_week_sensory_protocol": ["bridge_bloom_temper_crystal_boundary", "prop_autoxidation_food_rancidity_scope", "prop_discrimination_testing_scope", "prop_mvtr_package_test_scope", "prop_otr_package_test_scope"],
        "bridge_stash_decision_preparation": ["bridge_bloom_temper_crystal_boundary", "bridge_community_operational_scope", "bridge_independent_unit_rotation_cost", "bridge_oxidation_package_measurement_boundary", "bridge_seller_offer_identity_conflict_scope", "bridge_staged_ten_week_sensory_protocol"],
    }
    for source_id, targets in derives.items():
        for target_id in targets:
            edges.append({"edge_id": f"edge_{source_id}_from_{target_id}", "source_id": source_id, "relation": "DERIVES_FROM", "target_id": target_id})
    for target_id in derives:
        edges.append({"edge_id": f"edge_decision_requires_{target_id}", "source_id": "decision_evidence_bounded_stash", "relation": "REQUIRES", "target_id": target_id})

    return {"schema_version": "evidence_graph_inventory_v1", "corpus_snapshot": SNAPSHOT, "documents": documents, "nodes": nodes, "edges": edges, "support_spans": []}


def main() -> None:
    inventory = build()
    OUT.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": rel(OUT), "documents": len(inventory["documents"]), "nodes": len(inventory["nodes"]), "edges": len(inventory["edges"]), "critical_evidence": len(EVIDENCE), "sha256": sha256_bytes(OUT.read_bytes())}, sort_keys=True))


if __name__ == "__main__":
    main()
