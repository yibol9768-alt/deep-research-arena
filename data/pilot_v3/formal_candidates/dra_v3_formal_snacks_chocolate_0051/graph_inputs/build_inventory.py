#!/usr/bin/env python3
"""Build the frozen Q51 clean-label snack evidence inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
SNAPSHOT = "dra-v3-formal-snacks-chocolate-0051-clean-label-premium-claim-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-snacks-chocolate-0051-clean-label-premium-claim-boundary-20260716-r1"
CAPTURE_REL = Path("data/evidence_graph/captures") / RUN_ID
CAPTURE = ROOT / CAPTURE_REL
TASK_ID = "dra_v3_formal_snacks_chocolate_0051"
TOPIC = "clean_label_snack_premium_formula_and_claim_boundary"
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_snacks_chocolate_0051/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")


SEARCHES = [
    ("muya", "001-shopping-muya-no-msg-natural-banana.json", "Muya no-MSG banana-chip offer", "http://localhost:7770/muya-crispy-banana-fruit-chips-high-fibre-low-carb-no-msg-non-gmo-healthy-snack-4-x-38grams-tom-yum-flavour-gluten-free-healthy-snacks-perfect-for-adults-kids-4-packs.html"),
    ("fisher", "002-shopping-fisher-no-artificial-almonds.json", "Fisher no-artificial almond offer", "http://localhost:7770/fisher-snack-smoke-and-bacon-flavored-almonds-5-5-ounces-pack-of-6-no-artificial-colors-or-flavors.html"),
    ("orchard", "003-shopping-orchard-no-artificial-chickpea.json", "Orchard no-artificial chickpea-chip offer", "http://localhost:7770/orchard-valley-harvest-chickpea-chips-chili-lime-3-75oz-pack-of-8-non-gmo-no-artificial-ingredients.html"),
    ("natural_cheetos", "004-shopping-natural-cheetos-no-msg.json", "Natural Cheetos no-MSG offer", "http://localhost:7770/frito-lay-natural-cheetos-white-cheddar-cheese-puffs-8-ounce-pack-of-3.html"),
    ("regular_cheetos", "005-shopping-regular-cheetos-jumbo.json", "regular Cheetos Jumbo Puffs offer", "http://localhost:7770/cheetos-cheese-flavored-snacks-jumbo-puffs-2-38-ounce-pack-of-12.html"),
    ("clean_label", "006-wiki-clean-label-boundary.json", "clean-label ambiguity", "http://localhost:8090/content/wikipedia_en_all_nopic/Clean_label"),
    ("msg", "007-wiki-monosodium-glutamate-identity.json", "MSG identity and umami function", "http://localhost:8090/content/wikipedia_en_all_nopic/Monosodium_glutamate"),
    ("glutamate", "008-wiki-glutamate-flavoring-mechanism.json", "glutamate-flavoring mechanism", "http://localhost:8090/content/wikipedia_en_all_nopic/Glutamate_flavoring"),
    ("food_additive", "009-wiki-food-additive-functions.json", "food-additive functions", "http://localhost:8090/content/wikipedia_en_all_nopic/Food_additive"),
    ("food_coloring", "010-wiki-food-coloring-functions.json", "food-coloring functions", "http://localhost:8090/content/wikipedia_en_all_nopic/Food_coloring"),
    ("flavoring", "011-wiki-flavoring-source-class.json", "flavoring source classes", "http://localhost:8090/content/wikipedia_en_all_nopic/Flavoring"),
    ("natural_food", "012-wiki-natural-food-label.json", "natural-food label ambiguity", "http://localhost:8090/content/wikipedia_en_all_nopic/Natural_food"),
    ("til_msg", "013-forum-msg-naturally-tomatoes.json", "community naturally occurring MSG debate", "http://localhost:9999/f/todayilearned/135635/til-msg-occurs-naturally-in-tomatoes-and-other-vegetables"),
    ("msg_eli5", "014-forum-msg-taste-fear.json", "community MSG taste-and-fear debate", "http://localhost:9999/f/explainlikeimfive/18622/eli5-why-does-msg-make-food-taste-so-irresistible-and-why-is"),
    ("front_label", "015-forum-front-label-whole-wheat.json", "community front-label discussion", "http://localhost:9999/f/explainlikeimfive/39199/eli5-what-do-food-product-labels-that-say-whole-wheat-or-100"),
    ("kids_survey", "016-forum-kids-snack-survey-critique.json", "community child-snack survey criticism", "http://localhost:9999/f/dataisbeautiful/103915/the-u-s-states-where-children-consume-the-most-sugary-snacks"),
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


# Keeping the reviewed evidence table separate makes every authored phrase
# and exact support quote independently inspectable as JSON.
EVIDENCE_SPEC = Path(__file__).with_name("evidence_spec.json")
EVIDENCE = [
    ev(
        item["evidence_id"],
        item["subject"],
        item["predicate"],
        item["object"],
        item["search_index"],
        item["role"],
        item["scope"],
        item["quotes"],
        item["accepted"],
    )
    for item in json.loads(EVIDENCE_SPEC.read_text(encoding="utf-8"))
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
            "registry_id": "reg_case_spec_clean_label_snacks_0051",
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
        ("bridge_clean_label_natural_ambiguity", "bridge", "clean-label and natural terminology", "separates_marketing_categories_from_exact_formula_and_outcomes", "retain clean-label and natural as ambiguous labeling and formulation concepts without converting them into additive-free organic whole healthy or safe conclusions", "clean_label_natural_ambiguity_v1"),
        ("bridge_msg_glutamate_mechanism_boundary", "bridge", "MSG and broader glutamate flavoring", "separates_exact_compound_claim_from_broader_flavor_chemistry", "distinguish monosodium glutamate from glutamic acid free glutamate other salts and yeast extract and require exact formula and claim meaning without medical or safety conclusions", "msg_glutamate_mechanism_boundary_v1"),
        ("bridge_additive_color_flavor_function_boundary", "bridge", "additive color and flavor categories", "retains_function_and_source_class_scope", "describe sensory functions overlapping categories and natural artificial or nature-identical source classes without ranking whole-product health safety or quality", "additive_color_flavor_function_boundary_v1"),
        ("bridge_seller_claim_quantity_price_scope", "bridge", "five frozen seller offers", "audits_literal_claim_quantity_and_price_fields", "bind each field to the exact frozen SKU retain generic-weight ambiguities show conditional title arithmetic and refuse a matched clean-label premium or formula conclusion", "seller_claim_quantity_price_scope_v1"),
        ("bridge_community_claim_method_scope", "bridge", "four community pages", "retains_thread_and_method_scope", "use the debates only for beliefs label questions and survey-method criticism without treating them as chemistry law medicine exact-product audits or population estimates", "community_claim_method_scope_v1"),
        ("bridge_exact_formula_matched_cost_trial", "bridge", "verified household snack comparison", "requires_exact_formula_comparability_and_reversible_trial", "define criteria narrowly verify exact current formula allergens net quantity and delivered price compare like with like and use a masked repeated acceptability and waste trial without causal label attribution", "exact_formula_matched_cost_trial_v1"),
        ("bridge_clean_label_decision_preparation", "bridge", "evidence-bounded snack choice", "combines_claim_formula_cost_comparability_and_acceptability_gates", "build a pass fail unresolved table where no marketing phrase source class sticker price anecdote or liking result compensates for unresolved identity allergen formula package or budget gates", "clean_label_decision_preparation_v1"),
        ("decision_evidence_bounded_snack", "decision", "clean-label snack rotation", "selects_the_lowest_cost_exact_passing_offer_or_baseline_trial_or_defer", "choose only the lowest-cost exact offer passing formula label budget allergen package and family acceptability gates otherwise keep the baseline run a smaller matched trial or defer without a universal clean-label health or safety conclusion", "evidence_bounded_snack_decision_v1"),
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
        "prop_muya_no_msg_natural_scope",
        "prop_fisher_no_artificial_scope",
        "prop_orchard_no_artificial_scope",
        "prop_natural_cheetos_scope",
        "prop_regular_cheetos_scope",
    ]
    derives = {
        "bridge_clean_label_natural_ambiguity": [
            "prop_clean_label_ambiguity_scope",
            "prop_natural_food_label_scope",
        ],
        "bridge_msg_glutamate_mechanism_boundary": [
            "prop_msg_identity_umami_scope",
            "prop_glutamate_flavoring_scope",
        ],
        "bridge_additive_color_flavor_function_boundary": [
            "prop_food_additive_function_scope",
            "prop_food_coloring_function_scope",
            "prop_flavoring_source_class_scope",
        ],
        "bridge_seller_claim_quantity_price_scope": products,
        "bridge_community_claim_method_scope": [
            "prop_til_msg_natural_debate_scope",
            "prop_msg_community_debate_scope",
            "prop_front_label_discussion_scope",
            "prop_kids_survey_method_scope",
        ],
        "bridge_exact_formula_matched_cost_trial": [
            "bridge_clean_label_natural_ambiguity",
            "bridge_msg_glutamate_mechanism_boundary",
            "bridge_additive_color_flavor_function_boundary",
            "bridge_seller_claim_quantity_price_scope",
            "bridge_community_claim_method_scope",
        ],
        "bridge_clean_label_decision_preparation": [
            "bridge_clean_label_natural_ambiguity",
            "bridge_msg_glutamate_mechanism_boundary",
            "bridge_additive_color_flavor_function_boundary",
            "bridge_seller_claim_quantity_price_scope",
            "bridge_community_claim_method_scope",
            "bridge_exact_formula_matched_cost_trial",
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
                "source_id": "decision_evidence_bounded_snack",
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
