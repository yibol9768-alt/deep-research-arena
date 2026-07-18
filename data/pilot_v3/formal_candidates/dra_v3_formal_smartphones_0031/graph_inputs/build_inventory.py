#!/usr/bin/env python3
"""Build the reviewed Q31 graph inventory from the frozen atomic capture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
CAPTURE = ROOT / "data/evidence_graph/captures/v3-corpus-formal-smartphones-0031-runner-ingress-20260716-r1-20260716T170923Z"
AUTHORING = ROOT / "data/pilot_v3/formal_candidates/dra_v3_formal_smartphones_0031/graph_inputs/case_authoring_source.json"
OUT = ROOT / "data/pilot_v3/formal_candidates/dra_v3_formal_smartphones_0031/graph_inputs/inventory.json"
SNAPSHOT = "dra-v3-formal-smartphones-0031-runner-ingress-20260716-r1"
CASE_URL = "http://case-spec.local/dra_v3_formal_smartphones_0031"
CLUSTER = "smartphone_runner_ingress_conditional_choice"


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
        ("ip_levels", "search_ip_levels", "prop_ip_rating_digit_scope"),
        ("iphone_conditions", "search_iphone_conditions", "ev_iphone_11_pro_max_ip68_conditions"),
        ("samsung_conditions", "search_samsung_conditions", "ev_samsung_s22_ip68_conditions"),
        ("perspiration", "search_perspiration", "prop_perspiration_exertion_scope"),
        ("sweat_solutes", "search_sweat_solutes", "prop_sweat_solutes_scope"),
        ("corrosion", "search_corrosion", "prop_corrosion_conditions_scope"),
        ("aicase", "search_aicase", "ev_aicase_ip68_listing"),
        ("runbach", "search_runbach", "ev_runbach_sweatproof_listing"),
        ("diving_housing", "search_diving_housing", "ev_diving_housing_listing"),
        ("ordinary_case", "search_ordinary_case", "ev_ordinary_shock_case_listing"),
        ("wash_assumption", "search_wash_assumption", "prop_wash_ip68_assumption"),
        ("tap_water", "search_tap_water", "prop_tap_water_disagreement"),
        ("moisture_warranty", "search_moisture_warranty", "prop_moisture_warranty_anecdote"),
        ("case_experience", "search_case_experience", "prop_case_use_experiences"),
    ]
    if len(search_rows) != len(manifest["searches"]):
        raise RuntimeError("capture search count changed")

    documents: list[dict[str, object]] = []
    search_nodes: list[dict[str, object]] = []
    discovery_edges: list[dict[str, object]] = []
    for (suffix, search_node_id, content_node_id), capture_search in zip(
        search_rows, manifest["searches"]
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
            "registry_id": "reg_case_spec_runner_ingress",
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
                "prop_ip_rating_digit_scope",
                "proposition",
                "smartphone ingress-protection code",
                "separates_solid_and_liquid_levels",
                "IP67 combines solid level 6 with liquid level 7, while IP68 combines solid level 6 with liquid level 8 whose immersion depth is set by the manufacturer",
                urls["reg_wiki_rugged_smartphone_ip_levels"],
                [
                    span(
                        "span_ip67_levels",
                        "IP67 â Solid particle (dust) protection level 6 (protection from all dust) and liquid ingress (waterproof) protection level 7",
                    ),
                    span(
                        "span_ip68_manufacturer_depth",
                        "IP68 â Solid particle (dust) protection level 6 (protection from all dust) and liquid ingress (waterproof) protection level 8 (protection from full immersion at depths determined by the manufacturer).",
                    ),
                ],
                "IP67 and IP68 each combine a solid-particle level with a separate liquid-ingress level; for IP68 the cited immersion depth is determined by the manufacturer, so the code alone is not one universal water promise.",
                "concept",
                "ip_digit_definition_not_permanent_or_arbitrary_liquid_guarantee",
            ),
            typed_node(
                "ev_iphone_11_pro_max_ip68_conditions",
                "proposition",
                "iPhone 11 Pro and iPhone 11 Pro Max",
                "states_model_specific_water_condition",
                "both models are IP68 water and dust resistant for 30 minutes at 4 meters, while the page says water damage is not covered by warranty",
                urls["reg_wiki_iphone_11_pro_ip68"],
                [
                    span("span_iphone_both_models_named", "iPhone 11 Pro iPhone 11 Pro Max"),
                    span(
                        "span_iphone_both_models_condition",
                        "Both models are rated IP68 water and dust resistant, and are resistant for 30 minutes at a depth of 4 meters. The warranty does not cover any water damage to the phone.",
                    ),
                ],
                "The captured page explicitly names the iPhone 11 Pro and iPhone 11 Pro Max and says both models are IP68 water and dust resistant for 30 minutes at 4 meters; it also says the warranty does not cover water damage.",
                "concept",
                "model_specific_condition_not_sweat_or_permanent_waterproofing",
            ),
            typed_node(
                "ev_samsung_s22_ip68_conditions",
                "proposition",
                "Samsung Galaxy S22 series",
                "states_model_specific_water_condition",
                "IP68 water and dust resistance up to 1.5 meters for 30 minutes",
                urls["reg_wiki_samsung_s22_ip68"],
                [
                    span(
                        "span_samsung_s22_condition",
                        "Water resistance IP68 water and dust resistance, up to 1.5 m for 30 minutes",
                    )
                ],
                "The Samsung Galaxy S22 series reference states IP68 water and dust resistance up to 1.5 meters for 30 minutes, a different added condition from the other IP68 model page.",
                "concept",
                "comparison_of_model_specific_ip68_conditions_only",
            ),
            typed_node(
                "prop_perspiration_exertion_scope",
                "proposition",
                "human eccrine perspiration",
                "is_watery_brackish_and_increases_with_exertion",
                "eccrine sweat is watery and brackish, and heat or exertion increases sweating",
                urls["reg_wiki_perspiration_runner"],
                [
                    span(
                        "span_perspiration_brackish",
                        "The eccrine sweat glands are distributed over much of the body and are responsible for secreting the watery, brackish sweat most often triggered by excessive body temperature.",
                    ),
                    span(
                        "span_perspiration_exertion",
                        "Hence, in hot weather, or when the individual's muscles heat up due to exertion, more sweat is produced.",
                    ),
                ],
                "The perspiration reference describes eccrine sweat as watery and brackish and says heat or muscular exertion increases sweating; it does not test any phone or accessory.",
                "concept",
                "exposure_background_not_device_damage_or_survival_test",
            ),
            typed_node(
                "prop_sweat_solutes_scope",
                "proposition",
                "human sweat composition",
                "contains_water_and_multiple_solutes",
                "sweat is mostly water and can contain sodium and chloride among other solutes",
                urls["reg_wiki_sweat_solutes"],
                [
                    span(
                        "span_sweat_mostly_water",
                        "Although sweat is mostly water, [ 3 ] there are many solutes which are found in sweat that have at least some relation to biomarkers found in blood.",
                    ),
                    span("span_sweat_sodium_chloride", "These include: sodium (Na + ), chloride"),
                ],
                "The sweat-diagnostics reference says sweat is mostly water and lists sodium and chloride among its solutes; that composition fact does not establish damage or protection for this device combination.",
                "concept",
                "composition_background_not_phone_specific_failure_evidence",
            ),
            typed_node(
                "prop_corrosion_conditions_scope",
                "proposition",
                "galvanic corrosion",
                "depends_on_environmental_conditions",
                "temperature, humidity, and salinity are among conditions that affect galvanic corrosion",
                urls["reg_wiki_corrosion_conditions"],
                [
                    span(
                        "span_corrosion_conditions",
                        "Factors such as relative size of anode , types of metal, and operating conditions ( temperature , humidity , salinity , etc.) affect galvanic corrosion.",
                    )
                ],
                "The corrosion reference says temperature, humidity, and salinity affect galvanic corrosion; this is generic mechanism context and does not show that the selected phone or accessory will corrode or fail.",
                "concept",
                "generic_mechanism_context_not_device_specific_causation",
            ),
        ]
    )

    nodes.extend(
        [
            typed_node(
                "ev_aicase_ip68_listing",
                "attribute",
                "frozen AICase listing for iPhone 11 Pro Max",
                "advertises_sealed_case_conditions",
                "IP68, tested over 10 feet for 12 hours, recommended around 10 feet, maximum around 19.6 feet, not recommended for daily use, with no posted review",
                urls["reg_magento_aicase_iphone_11_pro_max_ip68"],
                [
                    span(
                        "span_aicase_title",
                        "AICase Waterproof Case for iPhone 11 Pro Max, Snowproof, Dustproof and Shockproof, IP68 Certified 360° Protection Fully Sealed Underwater Protective Cover for Apple iPhone 11 Pro Max (6.5-inch), 2019",
                    ),
                    span(
                        "span_aicase_conditions",
                        "IP68 Certified waterproof, tested and passed over 10ft for 12 Hours, Maximum submersible around 19.6 ft deep, recommended to submersible around 10ft",
                    ),
                    span("span_aicase_daily_caveat", "not recommend for daily use"),
                    span("span_aicase_no_review", "Be the first to review this product $5.99"),
                ],
                "The frozen AICase seller listing explicitly fits the iPhone 11 Pro Max and advertises IP68, a test over 10 feet for 12 hours, a recommended depth around 10 feet, a maximum around 19.6 feet, and that it is not recommended for daily use; it has no posted review and is not an independent runner test.",
                "product",
                "seller_claims_and_conditions_not_marathon_combo_test",
            ),
            typed_node(
                "ev_runbach_sweatproof_listing",
                "attribute",
                "frozen RUNBACH armband listing",
                "advertises_runner_protection_claims",
                "fits an iPhone 11 Pro Max with a slim case and advertises water and sweat resistance plus marathon use, with twelve posted reviews but no matching exposure test",
                urls["reg_magento_runbach_iphone_11_pro_max_sweatproof"],
                [
                    span(
                        "span_runbach_compatibility",
                        "Speciallly designed Compatible with iPhone 13 Pro Max/iPhone 12 Pro Max/iPhone 11 Pro Max/iPhone XS Max with a slim case on",
                    ),
                    span("span_runbach_sweat_claim", "Water resistant and sweat resistant"),
                    span(
                        "span_runbach_marathon_claim",
                        "also can stand up to the toughest of workouts and marathons",
                    ),
                    span("span_runbach_reviews", "Rating: 73 % of 100 12 Reviews"),
                ],
                "The frozen RUNBACH seller listing says the armband fits an iPhone 11 Pro Max with a slim case and advertises water resistance, sweat resistance, and marathon use; twelve posted reviews do not provide a matching sweat, rain, salt, heat, humidity, or duration test.",
                "product",
                "seller_runner_claim_not_controlled_combination_survival_test",
            ),
            typed_node(
                "ev_diving_housing_listing",
                "attribute",
                "frozen universal diving-housing listing",
                "advertises_ipx8_and_depth",
                "lists the iPhone 11 Pro Max as compatible and advertises IPX8 with a maximum diving depth of 20 meters, with no posted review",
                urls["reg_magento_iphone_11_pro_max_diving_case"],
                [
                    span(
                        "span_diving_depth",
                        "Maximum diving water depth: 20 Meters (66 feet). IPX8 standard waterproof level.",
                    ),
                    span(
                        "span_diving_iphone_compatibility",
                        "iPhone 6/ 6 Plus/6s/6s Plus/7/7 Plus/8/8 Plus/X/Xs/Xs Max/XR/11/11 Pro/11 Pro Max/12 Mini/12/12 Pro/12 Pro Max/13Mini/13/13 Pro/13 Pro Max.",
                    ),
                    span("span_diving_no_review", "Be the first to review this product $45.99"),
                ],
                "The frozen universal diving-housing seller page lists the iPhone 11 Pro Max, advertises IPX8 and 20 meters, and has no posted review; it does not document a runner sweat, rain, heat, humidity, or repeated-cycle test.",
                "product",
                "seller_housing_claim_not_runner_cycle_evidence",
            ),
            typed_node(
                "ev_ordinary_shock_case_listing",
                "attribute",
                "frozen Hitaoyou iPhone 11 Pro Max case listing",
                "advertises_impact_protection",
                "fits the iPhone 11 Pro Max and advertises a 16-foot drop test with shock, scratch, and bump protection",
                urls["reg_magento_iphone_11_pro_max_ordinary_case"],
                [
                    span(
                        "span_ordinary_drop_claim",
                        "Pass 16ft Drop Test. Military Grade protective phone case with Air Cushions Technology for anti-shock/anti-scratch/anti-bumps.",
                    ),
                    span(
                        "span_ordinary_compatibility",
                        "Designed for iphone iPhone 11 Pro max (6.5 inch), defend against the physical damages to your phone screen and camera lens.",
                    ),
                ],
                "The frozen Hitaoyou seller listing fits the iPhone 11 Pro Max and advertises a 16-foot drop test with shock, scratch, and bump protection; those cited attributes are impact claims and cannot be promoted into liquid protection or a changed phone IP rating.",
                "product",
                "impact_listing_only_not_liquid_ingress_upgrade",
            ),
        ]
    )

    wash_url = urls["reg_postmill_iphone_wash_ip68"]
    tap_url = urls["reg_postmill_iphone_cooling_water_ip68"]
    moisture_url = urls["reg_postmill_iphone_moisture_warranty"]
    case_url = urls["reg_postmill_iphone_case_waterproof_belief"]

    nodes.extend(
        [
            typed_node(
                "prop_wash_ip68_assumption",
                "proposition",
                "one phone-washing post",
                "reports_waterproof_assumption_and_uncertainty",
                "the author calls an IP68 phone waterproof but remains uneasy about even rinsing it",
                wash_url,
                [
                    span(
                        "span_wash_assumption",
                        "I know it’s waterproof being ip68, but it doesn’t feel right. Even a rinse with water",
                    )
                ],
                "One community author calls an IP68 phone waterproof while expressing uncertainty about even rinsing it; this is an individual belief and question, not evidence that the phone is permanently waterproof.",
                "community",
                "individual_assumption_not_product_fact",
            ),
            typed_node(
                "prop_tap_water_disagreement",
                "proposition",
                "one tap-water cooling discussion",
                "reports_deliberate_exposure_and_disagreement",
                "the author used tap water because of IP68, while replies recommend against deliberate wetting or report a different personal outcome",
                tap_url,
                [
                    span(
                        "span_tap_author",
                        "I am doing this because the phone is rated IP68. But I don't know if I should continue doing this.",
                    ),
                    span(
                        "span_tap_avoidance_reply",
                        "For this reason, I never get my phone wet on purpose.",
                    ),
                    span(
                        "span_tap_other_outcome",
                        "I’ve done this with my 12 PM for years. No issues yet. I haven’t done it more than a few dozen times total though.",
                    ),
                ],
                "A community author reports deliberately cooling an IP68 iPhone 13 mini under tap water; replies recommend avoiding deliberate wetting or report a different individual outcome, so the thread is disagreement rather than controlled evidence.",
                "community",
                "individual_exposure_reports_not_policy_causation_or_prevalence",
            ),
            typed_node(
                "prop_moisture_warranty_anecdote",
                "proposition",
                "one reported iPhone warranty dispute",
                "reports_moisture_based_refusal",
                "the author says moisture was cited to refuse replacement while denying water exposure",
                moisture_url,
                [
                    span(
                        "span_moisture_warranty_report",
                        "They claim there was moisture inside, voiding the warranty (never around water) has anyone else had bad experiences like this?",
                    )
                ],
                "One community author says moisture was cited when replacement of an iPhone 13 Pro Max was refused while denying water exposure; this is a single disputed report, not verified warranty policy or proof about another model.",
                "community",
                "single_disputed_warranty_experience_not_policy",
            ),
            typed_node(
                "prop_case_use_experiences",
                "proposition",
                "one case-or-no-case discussion",
                "mixes_waterproof_belief_with_drop_experience",
                "the author assumes newer iPhones are waterproof, while a respondent reports personally avoiding breakage after using cases through multiple drops",
                case_url,
                [
                    span(
                        "span_case_waterproof_belief",
                        "I mean I know the new Iphone models are pretty strong and sturdy and even water proof but I'm not sure, should i get a case for it as well just to be on the safe side",
                    ),
                    span(
                        "span_case_drop_experience",
                        "I’ve owned several models of iPhone (3G, 4, 5s, 6s, 8), encased all of them, dropped each multiple times, even on concrete—and never broken a single one.",
                    ),
                ],
                "A case discussion combines the author's general waterproof belief with another user's personal drop-and-case experience; it can inform the existence of different beliefs and habits but not liquid protection or population outcomes.",
                "community",
                "individual_case_and_drop_experience_not_ingress_evidence",
            ),
        ]
    )

    assertion_rows = [
        (
            "assert_ip_rating_digit_scope",
            "rugged-smartphone IP reference",
            "IP67 and IP68 use separate solid and liquid levels, with IP68 immersion depth determined by the manufacturer",
            urls["reg_wiki_rugged_smartphone_ip_levels"],
            [
                span(
                    "span_assert_ip68_manufacturer_depth",
                    "IP68 â Solid particle (dust) protection level 6 (protection from all dust) and liquid ingress (waterproof) protection level 8 (protection from full immersion at depths determined by the manufacturer).",
                )
            ],
            "prop_ip_rating_digit_scope",
        ),
        (
            "assert_iphone_conditions",
            "iPhone 11 Pro reference",
            "the page explicitly includes the Pro Max and applies the four-meter thirty-minute condition to both models",
            urls["reg_wiki_iphone_11_pro_ip68"],
            [
                span(
                    "span_assert_iphone_both_models",
                    "Both models are rated IP68 water and dust resistant, and are resistant for 30 minutes at a depth of 4 meters. The warranty does not cover any water damage to the phone.",
                )
            ],
            "ev_iphone_11_pro_max_ip68_conditions",
        ),
        (
            "assert_samsung_conditions",
            "Samsung Galaxy S22 reference",
            "the series page states a different IP68 depth with the same duration",
            urls["reg_wiki_samsung_s22_ip68"],
            [
                span(
                    "span_assert_samsung_s22",
                    "Water resistance IP68 water and dust resistance, up to 1.5 m for 30 minutes",
                )
            ],
            "ev_samsung_s22_ip68_conditions",
        ),
        (
            "assert_perspiration_scope",
            "perspiration reference",
            "eccrine sweat is watery and brackish",
            urls["reg_wiki_perspiration_runner"],
            [
                span(
                    "span_assert_perspiration",
                    "The eccrine sweat glands are distributed over much of the body and are responsible for secreting the watery, brackish sweat most often triggered by excessive body temperature.",
                )
            ],
            "prop_perspiration_exertion_scope",
        ),
        (
            "assert_sweat_solutes_scope",
            "sweat-diagnostics reference",
            "sweat is mostly water and contains multiple solutes including sodium and chloride",
            urls["reg_wiki_sweat_solutes"],
            [span("span_assert_sweat_solutes", "These include: sodium (Na + ), chloride")],
            "prop_sweat_solutes_scope",
        ),
        (
            "assert_corrosion_scope",
            "corrosion reference",
            "temperature humidity and salinity can affect galvanic corrosion",
            urls["reg_wiki_corrosion_conditions"],
            [
                span(
                    "span_assert_corrosion",
                    "Factors such as relative size of anode , types of metal, and operating conditions ( temperature , humidity , salinity , etc.) affect galvanic corrosion.",
                )
            ],
            "prop_corrosion_conditions_scope",
        ),
        (
            "assert_wash_assumption",
            "phone-washing post",
            "the author equates IP68 with waterproofing but expresses doubt",
            wash_url,
            [
                span(
                    "span_assert_wash",
                    "I know it’s waterproof being ip68, but it doesn’t feel right. Even a rinse with water",
                )
            ],
            "prop_wash_ip68_assumption",
        ),
        (
            "assert_tap_disagreement",
            "tap-water cooling discussion",
            "participants report different choices and outcomes around deliberate exposure",
            tap_url,
            [
                span(
                    "span_assert_tap_author",
                    "I am doing this because the phone is rated IP68. But I don't know if I should continue doing this.",
                ),
                span(
                    "span_assert_tap_other",
                    "I’ve done this with my 12 PM for years. No issues yet. I haven’t done it more than a few dozen times total though.",
                ),
            ],
            "prop_tap_water_disagreement",
        ),
        (
            "assert_moisture_anecdote",
            "reported warranty dispute",
            "the author reports a moisture finding while denying water exposure",
            moisture_url,
            [
                span(
                    "span_assert_moisture",
                    "They claim there was moisture inside, voiding the warranty (never around water) has anyone else had bad experiences like this?",
                )
            ],
            "prop_moisture_warranty_anecdote",
        ),
        (
            "assert_case_experience",
            "case-or-no-case discussion",
            "the thread mixes a waterproof belief with a personal impact-protection history",
            case_url,
            [
                span(
                    "span_assert_case_drop",
                    "I’ve owned several models of iPhone (3G, 4, 5s, 6s, 8), encased all of them, dropped each multiple times, even on concrete—and never broken a single one.",
                )
            ],
            "prop_case_use_experiences",
        ),
    ]
    assertion_targets: list[tuple[str, str]] = []
    for node_id, subject, obj, source_url, spans, target_id in assertion_rows:
        nodes.append(assertion_node(node_id, subject, obj, source_url, spans))
        assertion_targets.append((node_id, target_id))

    nodes.extend(
        [
            derived_node(
                "bridge_ip_code_conditions",
                "bridge",
                "IP67 and IP68 interpretation",
                "derives_bounded_model_conditions",
                "separate solid and liquid digits, then attach the exact model depth, duration, and warranty statement instead of treating IP68 as a universal waterproof promise",
                "ip_rating_scope_v1",
            ),
            derived_node(
                "bridge_sweat_non_equivalence",
                "bridge",
                "runner sweat and hot humid exposure",
                "derives_non_equivalence_boundary",
                "sweat composition and generic corrosion conditions show why exposure context matters, but they neither prove phone damage nor extend an IP water condition to sweat, salts, rain, or repeated cycles",
                "sweat_non_equivalence_v1",
            ),
            derived_node(
                "bridge_protection_listing_matrix",
                "bridge",
                "four iPhone 11 Pro Max protection listings",
                "derives_claim_matrix",
                "compare each exact compatibility and advertised condition while keeping sealed-case, sweatproof-armband, diving-housing, and impact-case claims at seller-listing scope",
                "protection_listing_matrix_v1",
            ),
            derived_node(
                "bridge_scoped_ingress_experience",
                "bridge",
                "community ingress and case reports",
                "derives_scope_boundary",
                "use the posts only to show individual beliefs, exposures, disagreement, and a disputed warranty experience, not product performance, policy, prevalence, or causation",
                "scoped_ingress_experience_v1",
            ),
            derived_node(
                "bridge_conditional_ingress_trial",
                "bridge",
                "reversible runner protection trial",
                "derives_low_exposure_process",
                "verify exact fit, instructions, closure, return and service terms; if allowed, test only the empty accessory with dry absorbent material, then use short incremental runs with inspection while withholding any long-term guarantee",
                "conditional_ingress_trial_v1",
            ),
            derived_node(
                "decision_evidence_bounded_runner_choice",
                "decision",
                "marathon runner phone-protection choice",
                "selects_admissible_set",
                [
                    "choose_the_least_exposure_returnable_setup_that_passes_exact_fit_terms_empty_accessory_and_short_run_checks_or_keep_the_phone_out_of_exposure_and_defer_without_a_marathon_proof_claim"
                ],
                "evidence_bounded_runner_decision_v1",
                decision=True,
            ),
        ]
    )

    edges: list[dict[str, object]] = []
    for assertion_id, target_id in assertion_targets:
        edges.append(
            {
                "edge_id": f"edge_{assertion_id.removeprefix('assert_')}",
                "source_id": assertion_id,
                "relation": "ASSERTS",
                "target_id": target_id,
            }
        )
    edges.extend(discovery_edges)

    dependencies = {
        "bridge_ip_code_conditions": [
            "prop_ip_rating_digit_scope",
            "ev_iphone_11_pro_max_ip68_conditions",
            "ev_samsung_s22_ip68_conditions",
        ],
        "bridge_sweat_non_equivalence": [
            "prop_perspiration_exertion_scope",
            "prop_sweat_solutes_scope",
            "prop_corrosion_conditions_scope",
            "prop_ip_rating_digit_scope",
        ],
        "bridge_protection_listing_matrix": [
            "ev_iphone_11_pro_max_ip68_conditions",
            "ev_aicase_ip68_listing",
            "ev_runbach_sweatproof_listing",
            "ev_diving_housing_listing",
            "ev_ordinary_shock_case_listing",
            "prop_ip_rating_digit_scope",
        ],
        "bridge_scoped_ingress_experience": [
            "prop_wash_ip68_assumption",
            "prop_tap_water_disagreement",
            "prop_moisture_warranty_anecdote",
            "prop_case_use_experiences",
            "ev_iphone_11_pro_max_ip68_conditions",
            "prop_perspiration_exertion_scope",
            "prop_sweat_solutes_scope",
            "prop_corrosion_conditions_scope",
        ],
        "bridge_conditional_ingress_trial": [
            "bridge_ip_code_conditions",
            "bridge_sweat_non_equivalence",
            "bridge_protection_listing_matrix",
            "bridge_scoped_ingress_experience",
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
                "source_id": "decision_evidence_bounded_runner_choice",
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
