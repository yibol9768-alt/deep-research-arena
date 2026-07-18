#!/usr/bin/env python3
"""Build the reviewed Q34 OLED-commuter graph inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
CAPTURE = ROOT / "data/evidence_graph/captures/v3-corpus-formal-gaming-0034-oled-commute-20260716-r1"
AUTHORING = ROOT / "data/pilot_v3/formal_candidates/dra_v3_formal_gaming_0034/graph_inputs/case_authoring_source.json"
OUT = ROOT / "data/pilot_v3/formal_candidates/dra_v3_formal_gaming_0034/graph_inputs/inventory.json"
SNAPSHOT = "dra-v3-formal-gaming-0034-oled-commute-20260716-r1"
CASE_URL = "http://case-spec.local/dra_v3_formal_gaming_0034"
CLUSTER = "gaming_oled_commute_evidence_boundary"


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
        "node_type": "proposition",
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
    prop: dict[str, object],
    assertion_id: str,
) -> dict[str, object]:
    assertion_spans = []
    for index, raw in enumerate(prop["support_spans"]):
        support = dict(raw)
        support["support_span_id"] = f"span_{assertion_id}_{index + 1}"
        assertion_spans.append(support)
    return {
        "evidence_id": assertion_id,
        "node_type": "assertion",
        "subject": prop["subject"],
        "predicate": "states",
        "object": prop["object"],
        "source_url": prop["source_url"],
        "support_spans": assertion_spans,
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
        ("switch_oled", "search_switch_oled", "ev_switch_oled_listing"),
        ("switch_base_bundle", "search_switch_base_bundle", "ev_switch_base_bundle_listing"),
        ("switch_normal_owner", "search_switch_normal_owner", "prop_switch_normal_owner_preference"),
        ("switch_upgrade_opinion", "search_switch_upgrade_opinion", "prop_switch_oled_upgrade_opinion"),
        ("handheld_commute", "search_handheld_commute", "prop_steam_deck_commute_battery_anecdotes"),
        ("oled_tv_experience", "search_oled_tv_experience", "prop_oled_tv_preference_burnin_disagreement"),
        ("switch_models", "search_switch_models", "prop_switch_historical_launch_msrp"),
        ("amoled", "search_amoled", "prop_amoled_pixel_mechanism"),
        ("backlight", "search_backlight", "prop_lcd_backlight_mechanism"),
        ("image_persistence", "search_image_persistence", "prop_lcd_image_persistence_boundary"),
        ("depth_discharge", "search_depth_discharge", "prop_depth_of_discharge_boundary"),
    ]
    if len(search_rows) != len(manifest["searches"]):
        raise RuntimeError("capture search count changed")

    documents: list[dict[str, object]] = []
    search_nodes: list[dict[str, object]] = []
    discovery_edges: list[dict[str, object]] = []
    for (suffix, search_node_id, content_node_id), capture_search in zip(search_rows, manifest["searches"]):
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
            "registry_id": "reg_case_spec_oled_commute",
            "source_url": CASE_URL,
            "source_type": "case_spec",
            "content_sha256": sha256(AUTHORING.read_bytes()),
            "blob_path": AUTHORING.relative_to(ROOT).as_posix(),
            "in_corpus": True,
        }
    )

    urls = {row["registry_id"]: row["source_url"] for row in captured_documents}
    props: list[dict[str, object]] = [
        typed_node(
            "ev_switch_oled_listing",
            "Nintendo Switch OLED Model Neon Red and Neon Blue seller page",
            "shows_frozen_listing",
            "in stock SKU B098RL6SBJ, 55/100 over 12 reviews, 3.66 dollars, with Neon Blue and Red or White color choices",
            urls["reg_magento_switch_oled_neon"],
            [span("span_oled_listing_snapshot", "In stock SKU B098RL6SBJ Rating: 55 % of 100 12 Reviews Add Your Review $3.66 Color Neon Blue and Red White")],
            "The frozen OLED seller page shows SKU B098RL6SBJ as in stock, 55/100 over 12 reviews, at 3.66 dollars, with Neon Blue and Red or White choices; this is a seller snapshot, not a current market price or display test.",
            "product",
            "frozen_anomalous_seller_claim_only",
        ),
        typed_node(
            "ev_switch_base_bundle_listing",
            "Nintendo Switch Neon base plus Mario Kart 8 Deluxe seller page",
            "shows_frozen_bundle_listing",
            "SKU B07YZQ9QMD, no posted review, 35.67 dollars, and a Mario Kart 8 Deluxe full-game-download bundle",
            urls["reg_magento_switch_base_mario_kart_bundle"],
            [
                span("span_base_bundle_title", "Nintendo Switch w/ Neon Blue & Neon Red Joy-Con + Mario Kart 8 Deluxe (Full Game Download) - Switch"),
                span("span_base_bundle_snapshot", "In stock SKU B07YZQ9QMD Be the first to review this product $35.67 Platform Nintendo Switch Gray Nintendo Switch Neon"),
            ],
            "The frozen base seller page is SKU B07YZQ9QMD at 35.67 dollars with no posted review and explicitly bundles Mario Kart 8 Deluxe; it is not configuration-matched to the OLED page and cannot define a screen-tier premium.",
            "product",
            "frozen_anomalous_bundle_claim_only",
        ),
        typed_node(
            "prop_switch_historical_launch_msrp",
            "Nintendo Switch original and OLED historical introductory prices",
            "lists_historical_launch_msrp",
            "original US 299.99 dollars and OLED US 349.99 dollars",
            urls["reg_wiki_nintendo_switch_models"],
            [span("span_switch_intro_prices", "Introductory price Original: US$ 299.99 Â· Â¥ 29,980 Â· â¬ 329.99 Lite: US$199.99 Â· Â¥19,980 Â· â¬229.99 OLED: US$349.99 Â· Â¥37,980 Â· â¬349.99")],
            "The captured Nintendo Switch reference lists historical introductory US prices of 299.99 dollars for Original and 349.99 dollars for OLED, a 50-dollar launch gap; these are not current street prices and do not verify the user's roughly 100-dollar shop quote.",
            "concept",
            "historical_launch_msrp_not_current_offer",
        ),
        typed_node(
            "prop_switch_display_storage",
            "Nintendo Switch original and OLED model table",
            "lists_display_and_storage",
            "Original/Lite 32 GB versus OLED 64 GB; Original 6.2-inch 720p IPS versus OLED 7-inch 720p OLED",
            urls["reg_wiki_nintendo_switch_models"],
            [
                span("span_switch_storage", "Storage Original/Lite: 32 GB eMMC OLED: 64 GB eMMC Removable storage microSD , up to 2 TB"),
                span("span_switch_displays", "Display Original: 6.2-in, IPS (237 ppi ), 720p Lite: 5.5-in, IPS (267 ppi), 720p OLED: 7-in, OLED (210 ppi), 720p"),
            ],
            "The same captured table lists Original/Lite storage at 32 GB and OLED at 64 GB, and lists the Original as a 6.2-inch 720p IPS display and OLED as a 7-inch 720p OLED display; those are model-table facts, not a perceived-quality or performance result.",
            "concept",
            "exact_model_table_not_user_preference",
        ),
        typed_node(
            "prop_switch_battery_table_boundary",
            "Nintendo Switch family power table",
            "lists_battery_and_two_duration_ranges",
            "3.7 V 15.95 Wh 4,310 mAh Li-ion and duration ranges 2.5–6.5 hours and 4.5–9 hours with footnote markers",
            urls["reg_wiki_nintendo_switch_models"],
            [span("span_switch_battery_table", "Power 3.7 V 15.95 Wh ( 4,310 mAh ) Li-ion battery Duration: 2.5â6.5 hours [ g ] / 4.5â9 hours [ h ]")],
            "The frozen power table shows a 3.7 V, 15.95 Wh, 4,310 mAh Li-ion line and two duration ranges, 2.5–6.5 and 4.5–9 hours, with footnote markers; the captured body does not support assigning one range to an unverified exact shop revision or predicting a commute runtime.",
            "concept",
            "table_ranges_require_revision_and_workload_binding",
        ),
        typed_node(
            "prop_switch_weight_table",
            "Nintendo Switch original and OLED model table",
            "lists_console_weight_field",
            "Original 297 g and OLED 319 g",
            urls["reg_wiki_nintendo_switch_models"],
            [span("span_switch_weight_table", "Weight Original: 297 g (10.5 oz) [ k ] Lite: 277 g (9.8 oz) OLED: 319 g (11.3 oz) [ l ]")],
            "The captured model table lists Original at 297 g and OLED at 319 g, but this field is not a measurement of the buyer's complete carried setup with controllers, case, charger, or accessories.",
            "concept",
            "model_table_weight_not_full_commute_load",
        ),
        typed_node(
            "prop_amoled_pixel_mechanism",
            "AMOLED display",
            "uses_individually_controlled_light_generating_pixels",
            "an active matrix of OLED pixels generates light under electrical activation and TFTs control current to individual pixels",
            urls["reg_wiki_amoled_mechanism_degradation"],
            [span("span_amoled_pixel_mechanism", "An AMOLED display consists of an active matrix of OLED pixels generating light (luminescence) upon electrical activation that have been deposited or integrated onto a thin-film transistor (TFT) array, which functions as a series of switches to control the current flowing to each individual pixel .")],
            "The generic AMOLED reference says an active matrix of OLED pixels generates light under electrical activation and a TFT array controls current to individual pixels; this mechanism does not itself establish the Switch OLED's subjective value.",
            "concept",
            "generic_display_mechanism_only",
        ),
        typed_node(
            "prop_amoled_power_content_dependency",
            "AMOLED display power",
            "varies_with_content_and_brightness",
            "power consumption varies significantly with displayed color and brightness",
            urls["reg_wiki_amoled_mechanism_degradation"],
            [span("span_amoled_power_dependency", "The amount of power the display consumes varies significantly depending on the color and brightness shown.")],
            "The generic AMOLED reference says display power varies significantly with shown color and brightness; it does not provide a Nintendo Switch workload, model comparison, route runtime, or fixed battery advantage.",
            "concept",
            "generic_content_dependence_not_model_runtime",
        ),
        typed_node(
            "prop_amoled_generic_degradation",
            "AMOLED organic materials",
            "can_degrade_unevenly",
            "generic degradation can produce color shifts, image persistence, or burn-in",
            urls["reg_wiki_amoled_mechanism_degradation"],
            [span("span_amoled_degradation", "The organic materials used in AMOLED displays are very prone to degradation over a relatively short period of time, resulting in color shifts as one color fades faster than another, image persistence , or burn-in .")],
            "The generic AMOLED page associates organic-material degradation with color shifts, image persistence, or burn-in; it supplies no Nintendo Switch OLED incidence, usage threshold, years-to-failure, or comparison with an exact LCD unit.",
            "concept",
            "generic_risk_not_model_incidence_or_timeline",
        ),
        typed_node(
            "prop_lcd_backlight_mechanism",
            "LCD and OLED illumination",
            "uses_different_light_paths",
            "LCDs require ambient or dedicated illumination because they do not produce light; OLED does not require a backlight",
            urls["reg_wiki_lcd_backlight_mechanism"],
            [
                span("span_lcd_requires_light", "LCDs do not produce light on their own, so they require illuminationâeither from ambient light or a dedicated light sourceâto create a visible image."),
                span("span_oled_no_backlight", "Many types of displays other than LCD generate their own light and do not require a backlight, for example, OLED displays"),
            ],
            "The backlight reference says LCDs do not produce light and need ambient or dedicated illumination, while OLED displays do not require a backlight; mechanism alone does not rank complete displays or users' outcomes.",
            "concept",
            "generic_light_path_not_quality_ranking",
        ),
        typed_node(
            "prop_lcd_image_persistence_boundary",
            "image persistence in LCD and plasma displays",
            "is_usually_temporary_and_differs_from_burn_in",
            "unwanted information from a previous state is usually temporary, unlike screen burn-in",
            urls["reg_wiki_image_persistence_boundary"],
            [span("span_image_persistence_boundary", "Unlike screen burn-in, the effects are usually temporary and often not visible without close inspection.")],
            "The image-persistence reference says that, unlike screen burn-in, its effects are usually temporary and often not visible without close inspection; a retained image should not automatically be called permanent OLED burn-in.",
            "concept",
            "phenomenon_definition_not_switch_failure_evidence",
        ),
        typed_node(
            "prop_depth_of_discharge_boundary",
            "depth of discharge",
            "has_multiple_definitions_and_generic_cycle_relation",
            "two non-identical definitions exist and cycle life can correlate with depth of discharge for rechargeable batteries",
            urls["reg_wiki_depth_of_discharge_boundary"],
            [
                span("span_dod_two_definitions", "Two non-identical definitions can be found in commercial and scientific sources."),
                span("span_dod_cycle_relation", "For almost all known rechargeable battery technologies, such as lead-acid batteries of all kinds like AGM , there is a correlation between the depth of discharge and the cycle life of the battery."),
            ],
            "The depth-of-discharge reference notes two non-identical definitions and a generic relationship with cycle life across rechargeable technologies; it does not predict Switch battery aging, usable years, or an OLED-versus-base difference.",
            "concept",
            "generic_battery_background_not_product_prediction",
        ),
        typed_node(
            "prop_switch_normal_owner_preference",
            "one normal Nintendo Switch owner",
            "values_portability_without_prioritizing_graphics",
            "the owner loves portability and says they have the normal version because graphics do not matter much to them",
            urls["reg_postmill_switch_normal_or_oled"],
            [span("span_normal_owner_preference", "I love my Switch because it’s portable. On days like today when I’m stuck in bed due to chronic pain, Switch is the best. I have the normal version bc I don’t care much about graphics.")],
            "One participant says they love the Switch for portability and own the normal version because graphics do not matter much to them; this is one person's use and preference, not a display comparison or commuter prevalence estimate.",
            "community",
            "individual_direct_switch_preference_only",
        ),
        typed_node(
            "prop_switch_oled_upgrade_opinion",
            "one commenter in an unopened-OLED deliberation",
            "says_upgrade_not_worth_it",
            "the commenter says the OLED model is not worth the upgrade",
            urls["reg_postmill_switch_oled_upgrade_deliberation"],
            [span("span_oled_upgrade_opinion", "I wouldn't say the OLED model is worth the upgrade to be honest")],
            "In a thread where the author has not opened the OLED unit, one commenter says the OLED model is not worth the upgrade; this is an individual opinion without a matched screen trial in the captured text.",
            "community",
            "individual_unverified_upgrade_opinion_only",
        ),
        typed_node(
            "prop_steam_deck_commute_battery_anecdotes",
            "Steam Deck community discussion",
            "reports_commute_value_and_variable_battery",
            "one user values commuting and travel while another says battery life is not always great",
            urls["reg_postmill_handheld_commute_battery_use"],
            [
                span("span_deck_commute_use", "using it on the commute or travelling for work or just picking up for a quick 10mins here and there"),
                span("span_deck_battery_anecdote", "The fan can get a bit loud, and the battery life isn't always great"),
            ],
            "The Steam Deck discussion contains individual commute, travel, short-session, and variable-battery comments; it can motivate commuter test criteria but cannot be transferred as Nintendo Switch model runtime or superiority.",
            "community",
            "different_handheld_anecdote_non_transferable",
        ),
        typed_node(
            "prop_oled_tv_preference_burnin_disagreement",
            "OLED television community discussion",
            "contains_strong_preference_and_conflicting_burnin_histories",
            "participants report a striking picture-quality difference, visible burn-in after one usage history, and no burn-in after another history",
            urls["reg_postmill_oled_preference_burn_in"],
            [
                span("span_oled_tv_picture_preference", "I was amazed at the picture quality difference. It's a stunning panel with absolutely no visible flaws."),
                span("span_oled_tv_burnin_report", "It now has burn-in showing BOTW's hearts in the top left, Splatoon 2's matchmaking screen on the right half, and some strange perfectly vertical bar down the center that I can't explain."),
                span("span_oled_tv_no_burnin_report", "Not my experience with the C1. I have used it for a year as my desktop computer for work and play. No burn in yet"),
            ],
            "The OLED-TV thread contains strong picture-quality preference and conflicting individual burn-in histories. Those large-TV experiences show subjectivity and uncertainty but do not estimate Nintendo Switch OLED preference, incidence, or lifespan.",
            "community",
            "different_display_category_anecdotes_non_transferable",
        ),
    ]

    nodes: list[dict[str, object]] = list(search_nodes)
    nodes.extend(props)
    assertion_targets: list[tuple[str, str]] = []
    for prop in props:
        prop_id = str(prop["evidence_id"])
        assertion_id = f"assert_{prop_id.removeprefix('prop_').removeprefix('ev_')}"
        nodes.append(assertion_node(prop, assertion_id))
        assertion_targets.append((assertion_id, prop_id))

    nodes.extend(
        [
            derived_node(
                "bridge_exact_price_configuration_boundary",
                "bridge",
                "seller snapshots, historical MSRP, and local quote",
                "derives_price_verification_boundary",
                "the two seller pages are anomalous and configuration-mismatched, historical launch MSRP implies a 50-dollar launch gap, and the roughly 100-dollar local gap remains unverified until exact offers are matched",
                "exact_price_configuration_boundary_v1",
            ),
            derived_node(
                "bridge_model_tradeoff_scope",
                "bridge",
                "Nintendo Switch original and OLED model facts",
                "derives_model_bound_tradeoff_matrix",
                "compare exact display, storage, table weight, and battery wording without inferring performance, full carried weight, commute runtime, or subjective value",
                "model_tradeoff_scope_v1",
            ),
            derived_node(
                "bridge_display_mechanism_scope",
                "bridge",
                "LCD and AMOLED mechanisms and screen wear",
                "derives_mechanism_and_failure_boundary",
                "different light paths, content-dependent AMOLED power, generic degradation, and temporary image persistence define questions but do not establish a Switch-specific preference, burn-in rate, or lifetime",
                "display_and_aging_mechanism_scope_v1",
            ),
            derived_node(
                "bridge_battery_aging_scope",
                "bridge",
                "Switch battery table and generic depth of discharge",
                "derives_battery_evidence_boundary",
                "the table ranges require exact revision and workload binding, and generic depth-of-discharge background cannot predict Switch battery aging or an OLED-versus-base advantage",
                "battery_aging_evidence_boundary_v1",
            ),
            derived_node(
                "bridge_scoped_owner_experience",
                "bridge",
                "Switch, Steam Deck, and OLED-TV community statements",
                "derives_anecdote_scope_boundary",
                "keep direct Switch views individual and keep the commute and screen-wear reports from different devices non-transferable while using them only to define trial questions",
                "scoped_owner_experience_v1",
            ),
            derived_node(
                "bridge_matched_commuter_trial",
                "bridge",
                "return-window Switch commuter comparison",
                "derives_reversible_threshold_process",
                "verify matched exact offers, predeclare a personal threshold, compare both under controlled commute-relevant conditions, and select the cheapest configuration that repeatably passes or defer",
                "matched_commuter_trial_v1",
            ),
            derived_node(
                "decision_evidence_bounded_oled_commute_choice",
                "decision",
                "Nintendo Switch OLED-versus-base commuter choice",
                "selects_admissible_set",
                [
                    "pay_the_verified_premium_only_if_a_matched_return_window_trial_repeatably_clears_the_buyers_display_threshold_without_failing_commute_constraints_otherwise_choose_the_cheaper_matched_configuration_or_defer"
                ],
                "evidence_bounded_oled_commute_decision_v1",
                decision=True,
            ),
        ]
    )

    edges: list[dict[str, object]] = []
    for assertion_id, target_id in assertion_targets:
        edges.append(
            {
                "edge_id": f"edge_{assertion_id.removeprefix('assert_')}_asserts",
                "source_id": assertion_id,
                "relation": "ASSERTS",
                "target_id": target_id,
            }
        )
    edges.extend(discovery_edges)
    dependencies = {
        "bridge_exact_price_configuration_boundary": [
            "ev_switch_oled_listing",
            "ev_switch_base_bundle_listing",
            "prop_switch_historical_launch_msrp",
        ],
        "bridge_model_tradeoff_scope": [
            "prop_switch_historical_launch_msrp",
            "prop_switch_display_storage",
            "prop_switch_battery_table_boundary",
            "prop_switch_weight_table",
        ],
        "bridge_display_mechanism_scope": [
            "prop_amoled_pixel_mechanism",
            "prop_amoled_power_content_dependency",
            "prop_amoled_generic_degradation",
            "prop_lcd_backlight_mechanism",
            "prop_lcd_image_persistence_boundary",
        ],
        "bridge_battery_aging_scope": [
            "prop_switch_battery_table_boundary",
            "prop_depth_of_discharge_boundary",
        ],
        "bridge_scoped_owner_experience": [
            "prop_switch_normal_owner_preference",
            "prop_switch_oled_upgrade_opinion",
            "prop_steam_deck_commute_battery_anecdotes",
            "prop_oled_tv_preference_burnin_disagreement",
            "prop_switch_display_storage",
            "prop_amoled_generic_degradation",
        ],
        "bridge_matched_commuter_trial": [
            "bridge_exact_price_configuration_boundary",
            "bridge_model_tradeoff_scope",
            "bridge_display_mechanism_scope",
            "bridge_battery_aging_scope",
            "bridge_scoped_owner_experience",
        ],
    }
    for source_id, target_ids in dependencies.items():
        for target_id in target_ids:
            edges.append(
                {
                    "edge_id": f"edge_{source_id.removeprefix('bridge_')}_requires_{target_id.removeprefix('prop_').removeprefix('ev_').removeprefix('bridge_')}",
                    "source_id": source_id,
                    "relation": "DERIVES_FROM",
                    "target_id": target_id,
                }
            )
    for target_id in dependencies:
        edges.append(
            {
                "edge_id": f"edge_decision_requires_{target_id.removeprefix('bridge_')}",
                "source_id": "decision_evidence_bounded_oled_commute_choice",
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
