#!/usr/bin/env python3
"""Build v1 deep-tier task json + checklist json from V1_TASK_DESIGN_GRID.md spec.

Source of truth: configs/deep_topics/V1_TASK_DESIGN_GRID.md.
Run once; overwrites task jsons 0003-0012 + checklists_deep.json.

Idempotent. Safe to re-run after editing the per-task dict below.

Usage:
    python3 scripts/build_v1_deep_tasks.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
CHECKLIST_PATH = TASKS_DIR / "checklists_deep.json"


def base_task(task_id: str, *, intent: str, start_url: str, synthesis_extra: dict) -> dict:
    """Common deep-tier task json shape. Per-task overrides go in synthesis_extra."""
    base = {
        "schema_version": "deep-1.0.0",
        "task_id": task_id,
        "tier": "deep",
        "sites": ["shopping", "reddit", "wikipedia"],
        "difficulty": 5,
        "expected_steps": 80,
        "intent": intent,
        "start_url": start_url,
        "storage_state": None,
        "require_login": False,
        "markdown_spec": {
            "min_words": 3500,
            "max_words": 8000,
            "min_paragraphs": 25,
            "min_citations": 60,
            "min_pages_browsed": 120,
        },
        "citation_policy": {
            "required_for": ["price", "rating", "thread_score", "feature_claim", "wiki_definition"],
            "must_be_in_domain": ["__SHOPPING__", "__REDDIT__", "__WIKIPEDIA__"],
            "min_distinct_sources": 60,
            "min_distinct_domains": 3,
            "per_domain_minimum": {"__SHOPPING__": 30, "__REDDIT__": 20, "__WIKIPEDIA__": 15},
        },
        "url_coverage": {
            "golden_pool_path": f"data/golden/deep/{task_id}.json",
            "min_unique_urls_browsed": 100,
            "min_unique_urls_cited": 60,
            "min_must_cite_recall": 0.45,
            "min_expected_pool_coverage": 0.0,
            "min_domain_balance": 0.8,
            "weight_in_composite": 0.25,
            "scoring_weights": {"must_cite_recall": 0.55, "pool_coverage": 0.15, "domain_balance": 0.3},
        },
        "url_reachability": {"min_reachability_rate": 0.3, "probe_timeout_seconds": 6.0},
        "golden": {
            "triples_path": f"data/golden/deep/{task_id}.json",
            "expected_predicates": [
                "price", "rating", "review_count", "feature_claim",
                "forum", "thread_score", "comment_count", "thread_classification", "wiki_defines",
            ],
        },
        "synthesis_requirements": synthesis_extra,
        "coverage_checklist_path": "data/tasks/deep_research/cross_site_deep/checklists_deep.json",
        "author_notes": f"Deep-tier task v1 — see configs/deep_topics/V1_TASK_DESIGN_GRID.md §2 for spec.",
    }
    return base


# ---- per-task definitions (intent text shortened in repr; full text in V1_TASK_DESIGN_GRID.md) ----

TASKS = {}  # filled in by chunk modules; see below


TASKS["dr_cross_deep_0003"] = {
    "intent": (
        "Produce a Comparison report on three home-fitness equipment paths under a fixed $300 starter budget — "
        "(P1) Adjustable dumbbells + bench, (P2) Barbell + plate set + rack, (P3) Bodyweight + resistance bands + pull-up bar — "
        "across exactly 5 use cases: (UC1) muscle hypertrophy, (UC2) cardio + fat loss, (UC3) small-apartment friendliness, (UC4) injury rehab / mobility, (UC5) progression beyond 12 months.\n\n"
        "Ground in >= 120 distinct sandbox URLs and cite >= 60 as markdown links. "
        "(A) `__SHOPPING__` >= 12 products per path with price + rating + review_count + feature_claim. "
        "(B) `__REDDIT__` >= 30 threads from /f/Fitness, /f/xxfitness, /f/bodyweightfitness, /f/homegym etc., classified as {praise, complaint, technical_question, comparison, purchase_advice}. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Strength training, Hypertrophy, Aerobic exercise, Calisthenics, Resistance band, Olympic weightlifting, Powerlifting, Range of motion, Progressive overload — plus >= 15 more.\n\n"
        "Output a 3 x 5 decision matrix (path x use case), every cell rated {best / acceptable / poor} with >= 1 shopping URL + >= 1 reddit URL + >= 1 wiki URL as cited evidence. "
        "End with a 'when to pick which path' section: 3 short paragraphs each explaining which user profile picks P1/P2/P3, citing >= 5 reddit threads in support. "
        "Do NOT output a TOP-10 list — this is comparison, not ranking.\n\n"
        "Format: every fact is a markdown link `[label](url)`. Sandbox-local URLs only. No fabrication. Begin directly with the comparison report."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=dumbbell",
    "synthesis_extra": {
        "task_type": "comparison",
        "comparison_paths": ["adjustable_dumbbells", "barbell_set", "bodyweight"],
        "use_cases": ["hypertrophy", "cardio_fatloss", "small_apartment", "rehab_mobility", "long_term_progression"],
        "matrix_cells_required": 15,
        "min_evidence_per_cell": {"shopping": 1, "reddit": 1, "wikipedia": 1},
        "path_persona_paragraphs": 3,
        "min_reddit_per_persona": 5,
        "contradiction_findings_min": 3,
        "explicitly_forbid_top10": True,
    },
}

TASKS["dr_cross_deep_0004"] = {
    "intent": (
        "Produce a Comparison report on three photography starter stacks under a fixed $800 first-year budget — "
        "(S1) Mirrorless body + 1 prime + 1 zoom, (S2) Used DSLR body + 2 primes + flash, (S3) Smartphone + lens-attachment kit + tripod (no dedicated camera body) — "
        "across exactly 5 use cases: (UC1) family/portrait indoor, (UC2) travel/landscape outdoor, (UC3) low-light event/concert, (UC4) social-media short-video, (UC5) growth path to professional within 18 months.\n\n"
        "Ground in >= 120 sandbox URLs and cite >= 60. "
        "(A) `__SHOPPING__` >= 36 product pages spanning 3 stacks (>= 10 per stack incl. body + lens + accessory), price + rating + feature_claim. "
        "(B) `__REDDIT__` >= 30 threads from /f/photography, /f/AskPhotography, /f/photocritique, /f/M43, /f/MirrorlessCamera, /f/AnalogCommunity etc. — at least 4 forums. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Mirrorless camera, Digital single-lens reflex camera, Image sensor format, Crop factor, Aperture, Shutter speed, ISO, Depth of field, Bokeh, Computational photography, Exposure (photography) — plus >= 14 more.\n\n"
        "Output a 3 x 5 taxonomy matrix (stack x use case) rated {strong / workable / weak} with cited evidence per cell. "
        "Add a '5 hidden costs the marketing claim hides' section — each cost is a contradiction between vendor feature claim (cited shopping URL) and reddit-reported reality (cited thread URL) backed by a Wikipedia definition (cited wiki URL). "
        "End with 'upgrade path each stack supports past month-12' — 3 paragraphs, >= 4 reddit threads each.\n\n"
        "Format: markdown links only. Sandbox-local. No fabrication. Begin with comparison content."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=camera",
    "synthesis_extra": {
        "task_type": "comparison",
        "comparison_stacks": ["mirrorless", "used_dslr", "smartphone_kit"],
        "use_cases": ["portrait_indoor", "landscape_outdoor", "low_light_event", "social_short_video", "pro_growth_18m"],
        "matrix_cells_required": 15,
        "matrix_rating_levels": ["strong", "workable", "weak"],
        "min_evidence_per_cell": {"shopping": 1, "reddit": 1, "wikipedia": 1},
        "hidden_cost_findings_min": 5,
        "upgrade_path_paragraphs": 3,
        "min_reddit_per_upgrade_path": 4,
        "explicitly_forbid_top10": True,
    },
}


TASKS["dr_cross_deep_0006"] = {
    "intent": (
        "Produce a Debunking / Fact-Check report auditing 5 specific marketing claims common on consumer cookware: "
        "(CL1) 'PFOA-free non-stick is safe at all temperatures', (CL2) 'Ceramic-coated pans last as long as PTFE pans', "
        "(CL3) 'Cast iron skillets contribute meaningful dietary iron', (CL4) 'Stainless steel is non-reactive with all foods', "
        "(CL5) 'Hard-anodized aluminum cannot leach into food'. "
        "For each claim, produce a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED} backed by triple evidence.\n\n"
        "Ground in >= 120 sandbox URLs (>= 60 cited). "
        "(A) `__SHOPPING__` >= 36 cookware product pages (cast iron, non-stick, ceramic-coated, stainless, hard-anodized) with their **verbatim marketing language** for the audited claim + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/Cooking, /f/AskCulinary, /f/castiron, /f/Cookware, /f/BuyItForLife, /f/Frugal — capturing real-world failure modes (peeling coating, rust, scratches, residue). "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Polytetrafluoroethylene, Perfluorooctanoic acid, Non-stick surface, Cast-iron cookware, Stainless steel, Anodizing, Aluminium toxicity, Maillard reaction, Heat capacity, Thermal conductivity — plus >= 15 more.\n\n"
        "Output a 5-claim verdict table: each row = one claim, with columns (verdict, key supporting product URL with literal marketing quote, key reddit URL with user counter-evidence, key wiki URL with the underlying chemistry / physics, 1-paragraph reasoning). "
        "Add a 'safety risk rank' section: rank the 5 cookware materials by aggregate risk score derived from the 5 claim verdicts. "
        "End with a 'shopping rules' cheat-sheet (<= 8 bullet points), each rule cited with >= 1 wiki URL.\n\n"
        "Format: markdown links only. Begin with the verdict table. No chain-of-thought."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=cookware",
    "synthesis_extra": {
        "task_type": "debunking",
        "claim_count": 5,
        "claim_ids": ["pfoa_safety", "ceramic_durability", "cast_iron_iron", "stainless_reactivity", "anodized_leaching"],
        "verdict_levels": ["SUPPORTED", "PARTIALLY_SUPPORTED", "DEBUNKED"],
        "min_evidence_per_claim": {"shopping_with_verbatim_quote": 1, "reddit": 1, "wikipedia": 1, "reasoning_paragraphs": 1},
        "safety_risk_rank_size": 5,
        "shopping_rules_count": [6, 8],
        "min_wiki_per_rule": 1,
        "explicitly_forbid_top10": True,
    },
}

TASKS["dr_cross_deep_0007"] = {
    "intent": (
        "Produce a Debunking report auditing 5 dog-care marketing/folk claims: "
        "(CL1) 'Grain-free dog food is healthier than grain-inclusive', (CL2) 'Raw / BARF diet is more natural and reduces allergies', "
        "(CL3) 'BPA-free plastic dog bowls are safe for daily use', (CL4) 'Calming chews with L-theanine actually reduce anxiety', "
        "(CL5) 'Dental chews replace teeth brushing'. "
        "Each claim must receive a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}.\n\n"
        "Ground in >= 120 sandbox URLs (>= 60 cited). "
        "(A) `__SHOPPING__` >= 36 dog products carrying the audited claims (food bags with grain-free / raw / dental, calming chews, plastic bowls) — cite the exact marketing language. "
        "(B) `__REDDIT__` >= 30 threads from /f/dogs, /f/puppy101, /f/DogAdvice, /f/AskVet, /f/DogTraining — owner experience reports + vet AMAs + breed-specific advice. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Dog food, Raw feeding, Dilated cardiomyopathy, Bisphenol A, Theanine, Dog anxiety, Periodontal disease, Plaque (dental), Veterinary medicine, Salmonella — plus >= 15 more.\n\n"
        "Output a 5-claim verdict table (verdict / shopping URL with marketing quote / reddit URL / wiki URL / reasoning). "
        "Add a 'FDA / AAFCO regulatory gap' section that names >= 3 specific gaps in US pet food regulation that allow these claims to persist (cited to wiki). "
        "End with a 'vet-aligned shopping list' (<= 8 bullets) — products that align with the SUPPORTED claims, each cited with shopping URL + corroborating reddit + wiki definition.\n\n"
        "Format: markdown links. Begin with verdict table. No chain-of-thought."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=dog+food",
    "synthesis_extra": {
        "task_type": "debunking",
        "claim_count": 5,
        "claim_ids": ["grainfree_health", "raw_diet_allergies", "bpa_free_safety", "calming_chews_efficacy", "dental_chews_replace_brushing"],
        "verdict_levels": ["SUPPORTED", "PARTIALLY_SUPPORTED", "DEBUNKED", "UNDETERMINED"],
        "min_evidence_per_claim": {"shopping_with_verbatim_quote": 1, "reddit": 1, "wikipedia": 1, "reasoning_paragraphs": 1},
        "regulatory_gap_findings_min": 3,
        "vet_aligned_shopping_list_count": [6, 8],
        "explicitly_forbid_top10": True,
    },
}


TASKS["dr_cross_deep_0008"] = {
    "intent": (
        "Produce a Debunking / Fact-Check report auditing 5 marketing or folk claims about first-baby essentials: "
        "(CL1) 'Wedge / positioner pillows reduce SIDS', (CL2) 'Formula brand X is closer to breast milk than competitors', "
        "(CL3) 'Convertible car seats can safely be used rear-facing past 2 years', (CL4) 'Sleep sacks are safer than swaddles past 8 weeks', "
        "(CL5) 'Anti-colic bottles measurably reduce crying time'. "
        "Each gets a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}.\n\n"
        "Ground in >= 120 sandbox URLs (>= 60 cited). "
        "(A) `__SHOPPING__` >= 36 baby product pages (positioners, formulas, car seats, sleep sacks, bottles) with their **verbatim marketing language** + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/beyondthebump, /f/NewParents, /f/Parenting, /f/breastfeeding, /f/predaddit — recording experiences, AAP-style guidance discussions, hospital nurse Q&A. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Sudden infant death syndrome, Infant formula, Breast milk, Child safety seat, Swaddling, Sleep sack, Colic, Pacifier, ISOFIX, Breastfeeding — plus >= 15 more.\n\n"
        "Output a 5-claim verdict table. Add a section 'AAP / NHS guideline alignment': for each claim, note explicitly whether the verdict aligns with major pediatric body guidance (American Academy of Pediatrics / NHS / WHO), citing wiki URLs. "
        "End with a 'safe-sleep checklist' of <= 8 bullet rules, each cited.\n\n"
        "Format: markdown links. Begin with verdict table. No chain-of-thought."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=baby",
    "synthesis_extra": {
        "task_type": "debunking",
        "claim_count": 5,
        "claim_ids": ["positioner_sids", "formula_equiv", "extended_rear_facing", "sleep_sack_safety", "anti_colic_bottle"],
        "verdict_levels": ["SUPPORTED", "PARTIALLY_SUPPORTED", "DEBUNKED", "UNDETERMINED"],
        "min_evidence_per_claim": {"shopping_with_verbatim_quote": 1, "reddit": 1, "wikipedia": 1, "reasoning_paragraphs": 1},
        "guideline_alignment_required": True,
        "guideline_bodies": ["AAP", "NHS", "WHO"],
        "safe_sleep_checklist_count": [6, 8],
        "min_debunked_or_partial": 3,
        "explicitly_forbid_top10": True,
    },
}

TASKS["dr_cross_deep_0009"] = {
    "intent": (
        "Produce a Causal Explanation report answering: 'Why does an electric vehicle's effective range typically drop 20-40% in cold-weather (sub-freezing) operation, and what physical, chemical, and behavioural factors compose that loss?' "
        "The report is NOT a buying guide; it must build a causal chain from first principles to road-tested numbers.\n\n"
        "Ground in >= 120 sandbox URLs (>= 60 cited). "
        "(A) `__SHOPPING__` >= 30 EV-related products (Level 2 chargers, battery heaters / blankets, cold-weather accessories, replacement batteries) with marketing claims + price. "
        "(B) `__REDDIT__` >= 30 threads from /f/electricvehicles, /f/teslamotors, /f/cars, /f/BoltEV, /f/Volt — winter range reports, real-world MPGe drop logs, charging speed degradation reports. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Lithium-ion battery, Battery thermal management, Heat pump, Internal resistance, Electrolyte, Lithium plating, Regenerative braking, Cabin heater, Specific heat capacity, Arrhenius equation — plus >= 15 more.\n\n"
        "Output a multi-layer causal diagram in markdown (indented bullet hierarchy, NOT graphviz) tracing 4 causal layers:\n"
        "- L1 chemistry: lithium-ion electrolyte conductivity drop, lithium plating risk, internal resistance increase (cite wiki).\n"
        "- L2 thermal: cabin heating energy budget, battery preconditioning, heat pump efficiency (cite wiki + shopping for heat-pump-equipped models).\n"
        "- L3 driver behaviour: HVAC settings, regen reduction in cold, route planning (cite reddit experience reports).\n"
        "- L4 measured impact: empirical % range drop reported by users (cite >= 8 reddit threads with explicit %).\n\n"
        "Add a 'mitigation strategies ranked by % range recovered' table — each strategy cited with one shopping URL (product implementing it) + one reddit URL (user reporting the recovery). "
        "End with a 'what cars handle cold best' section ranking >= 3 EV models by aggregated reddit cold-weather sentiment, citing >= 3 reddit threads / model.\n\n"
        "Format: markdown links only. Begin with the L1 layer. No chain-of-thought."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=ev+charger",
    "synthesis_extra": {
        "task_type": "causal",
        "causal_layers": ["L1_chemistry", "L2_thermal", "L3_behaviour", "L4_measured_impact"],
        "min_wiki_per_layer": {"L1_chemistry": 3, "L2_thermal": 3},
        "min_reddit_per_layer": {"L3_behaviour": 5, "L4_measured_impact": 8},
        "l4_must_have_explicit_percent": True,
        "mitigation_strategies_min": 5,
        "min_evidence_per_strategy": {"shopping": 1, "reddit": 1},
        "model_ranking_min": 3,
        "min_reddit_per_model": 3,
        "explicitly_forbid_top10": True,
    },
}


TASKS["dr_cross_deep_0010"] = {
    "intent": (
        "Produce a Timeline / Evolution report tracing the 30+ year history of mechanical keyboard switch technology from buckling-spring (IBM Model F/M, 1980s) -> Cherry MX dominance (1990s-2010s) -> modern hot-swap / optical / magnetic-Hall (2020s). "
        "The report is NOT a buying guide; it is a chronological narrative + current-day taxonomy.\n\n"
        "Ground in >= 120 sandbox URLs (>= 60 cited). "
        "(A) `__SHOPPING__` >= 30 keyboard / switch products spanning the historical lineage (Cherry MX Red/Brown/Blue, optical Razer Yellow, Gateron, Kailh, Hall-effect Wooting / SteelSeries OmniPoint) with price + rating + feature_claim. "
        "(B) `__REDDIT__` >= 30 threads from /f/MechanicalKeyboards, /f/MechanicalKeyboardsActions, /f/keyboards, /f/ergodox, /f/olkb. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Buckling spring, Cherry (keyboards), Hall effect, Optical switch, Computer keyboard, Tactile bump, Keycap, Membrane keyboard, Scissor mechanism, Topre — plus >= 15 more.\n\n"
        "Output a chronological timeline divided into 4 eras (Era 1: 1980s buckling-spring / Era 2: 1990s-2010s Cherry MX dominance / Era 3: 2015-2022 hot-swap explosion / Era 4: 2023+ analog/Hall era). "
        "For each era: >= 3 wiki articles defining the technology, >= 3 shopping products embodying it, >= 3 reddit threads showing community adoption. "
        "Add a modern taxonomy of switch types organized by actuation mechanism (mechanical contact / optical / magnetic) — a markdown nested list with each leaf citing a shopping product + a wiki article. "
        "End with '7 myths the community now considers debunked' — each myth cited with a wiki + reddit pair.\n\n"
        "Format: markdown links only. Begin with Era 1. No chain-of-thought."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=mechanical+keyboard",
    "synthesis_extra": {
        "task_type": "timeline",
        "eras": ["1980s_buckling_spring", "1990s_2010s_cherry_dominance", "2015_2022_hotswap", "2023plus_analog_hall"],
        "min_per_era": {"wiki": 3, "shopping": 3, "reddit": 3},
        "taxonomy_branches": ["mechanical_contact", "optical", "magnetic_hall"],
        "min_taxonomy_leaves_with_evidence": 6,
        "debunked_myths_count": 7,
        "min_per_myth": {"wiki": 1, "reddit": 1},
        "explicitly_forbid_top10": True,
    },
}

TASKS["dr_cross_deep_0011"] = {
    "intent": (
        "Produce a Debunking / Fact-Check report auditing 5 popular sleep-aid claims: "
        "(CL1) '10 mg melatonin is more effective than 0.3 mg for sleep onset', "
        "(CL2) 'Wrist-worn sleep trackers (Fitbit / Garmin / Apple Watch) measure sleep stages accurately', "
        "(CL3) 'Blue-light blocking glasses meaningfully improve sleep latency', "
        "(CL4) 'Magnesium glycinate supplements consistently reduce insomnia', "
        "(CL5) 'Weighted blankets reduce anxiety and improve sleep'. "
        "Each receives a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}.\n\n"
        "Ground in >= 120 sandbox URLs (>= 60 cited). "
        "(A) `__SHOPPING__` >= 36 sleep-aid products (melatonin SKUs of varying doses, sleep trackers, blue-light glasses, magnesium supplements, weighted blankets) with verbatim marketing claim + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/sleep, /f/insomnia, /f/Supplements, /f/Biohackers, /f/AskScience, /f/Fitness — user efficacy reports + dose comparisons + clinical-trial discussions. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Melatonin, Sleep, Polysomnography, Actigraphy, Circadian rhythm, Blue light, Magnesium deficiency, Weighted blanket, Insomnia, Placebo — plus >= 15 more.\n\n"
        "Output a 5-claim verdict table. Add a section 'dose-response curves where they exist': for the 2 claims with quantitative evidence (melatonin dose, magnesium dose), present what the literature actually says about dose response (cite wiki + reddit clinical-trial discussions). "
        "End with a 'sleep hygiene' cheat-sheet (<= 8 bullets) — non-product practices the literature supports — each cited.\n\n"
        "Format: markdown links. Begin with verdict table. No chain-of-thought."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=melatonin",
    "synthesis_extra": {
        "task_type": "debunking",
        "claim_count": 5,
        "claim_ids": ["melatonin_dose", "tracker_accuracy", "blue_light_glasses", "magnesium_insomnia", "weighted_blanket"],
        "verdict_levels": ["SUPPORTED", "PARTIALLY_SUPPORTED", "DEBUNKED", "UNDETERMINED"],
        "min_evidence_per_claim": {"shopping_with_verbatim_quote": 1, "reddit": 1, "wikipedia": 1, "reasoning_paragraphs": 1},
        "dose_response_findings": ["melatonin", "magnesium"],
        "sleep_hygiene_checklist_count": [6, 8],
        "min_wiki_per_hygiene_bullet": 1,
        "explicitly_forbid_top10": True,
    },
}


TASKS["dr_cross_deep_0012"] = {
    "intent": (
        "Produce an Enumeration / Catalog report cataloguing every smart-home wireless protocol present on commercial smart locks, cameras, and hubs, organised by security model and threat surface. "
        "The report is NOT a buying guide; it is a comprehensive taxonomy in which every protocol gets a security profile.\n\n"
        "Ground in >= 120 sandbox URLs (>= 60 cited). "
        "(A) `__SHOPPING__` >= 40 smart-home device pages (smart locks, IP cameras, hubs, smart plugs, motion sensors) covering at minimum these protocols: Wi-Fi (WPA2/WPA3), Z-Wave, Zigbee, Thread, Matter, Bluetooth Low Energy, Z-Wave Plus, Insteon, Lutron Clear Connect — cite product URL + protocol(s) it advertises + price. "
        "(B) `__REDDIT__` >= 30 threads from /f/homeautomation, /f/smarthome, /f/HomeKit, /f/homeassistant, /f/Hue, /f/AmazonEcho — discussions of pairing failures, security incidents, mesh-network reliability. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Wi-Fi Protected Access, Z-Wave, Zigbee, Thread (network protocol), Matter (standard), Bluetooth Low Energy, Mesh networking, Public-key cryptography, Internet of things, Pre-shared key — plus >= 15 more.\n\n"
        "Output a protocol catalog table with columns: protocol name / band / mesh-or-not / pairing model / encryption used / known vulnerabilities (cited wiki) / typical product cost (cited shopping) / community reliability sentiment (cited reddit). "
        "Add a 'threat-model decision tree': starting from the user's choice between cloud-routed vs local-only vs hybrid, walk to recommended protocols — each node cited. "
        "End with '5 protocols / products to AVOID and why' — each w/ shopping URL + reddit URL + wiki URL of the failure mode.\n\n"
        "Format: markdown links. Begin with the catalog table. No chain-of-thought."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=smart+lock",
    "synthesis_extra": {
        "task_type": "enumeration",
        "protocols_min": 8,
        "catalog_columns": ["name", "band", "mesh", "pairing", "encryption", "vulnerabilities", "cost", "sentiment"],
        "min_evidence_per_protocol": {"wikipedia": 1, "shopping": 1, "reddit": 1},
        "decision_tree_levels": 3,
        "decision_tree_branches": ["cloud_routed", "local_only", "hybrid"],
        "avoid_findings_count": 5,
        "min_evidence_per_avoid": {"shopping": 1, "reddit": 1, "wikipedia": 1},
        "explicitly_forbid_top10": True,
    },
}


# ---- 21-item checklists per task (full task-specific) ----

CHECKLISTS = {
    "dr_cross_deep_0003": [
        "Are exactly 3 paths (dumbbell, barbell, bodyweight) defined and labelled P1/P2/P3?",
        "Are exactly 5 use cases (muscle, cardio, apartment, rehab, progression) enumerated?",
        "Does each of the 3 paths list >= 12 distinct shopping products with URL + price + rating?",
        "Does the report show product totals stay under the $300 starter budget for each path?",
        "Are >= 30 reddit threads cited across at least 4 fitness-related sub-forums?",
        "Is each cited reddit thread classified as one of {praise, complaint, technical_question, comparison, purchase_advice}?",
        "Are >= 25 distinct wiki articles cited with URL + defining statement?",
        "Are all 9 mandatory wiki articles (Strength training, Hypertrophy, Aerobic exercise, Calisthenics, Resistance band, Olympic weightlifting, Powerlifting, Range of motion, Progressive overload) present?",
        "Is the 3 x 5 decision matrix fully populated (15 cells, no blanks)?",
        "Does each of the 15 cells cite >= 1 shopping URL + >= 1 reddit URL + >= 1 wiki URL?",
        "Does each cell rate the path on that use case as {best, acceptable, poor}?",
        "Are >= 3 cross-source contradictions surfaced (marketing claim vs reddit reality vs wiki definition)?",
        "Are 3 path-persona paragraphs present (one per path) explaining the user profile that should pick that path?",
        "Does each path-persona paragraph cite >= 5 reddit threads?",
        "Are all cited URLs markdown-linked `[label](url)` and resolvable on the sandbox?",
        "Are >= 60 distinct URLs cited in total?",
        "Is per-domain minimum met: >= 30 shopping, >= 20 reddit, >= 15 wiki cited URLs?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid producing a TOP-10 list (this is Comparison, not Ranking)?",
        "Does the report avoid chain-of-thought and start directly with comparison content?",
        "Are reddit thread metadata (forum, score, comment_count) recorded for every cited thread?",
    ],
    "dr_cross_deep_0004": [
        "Are exactly 3 stacks (mirrorless, used-DSLR, phone-attachment) defined and labelled S1/S2/S3?",
        "Are exactly 5 use cases (portrait, landscape, low-light, social-video, growth) enumerated?",
        "Does each of the 3 stacks list >= 10 shopping products with body + lens + accessory breakdown?",
        "Are total stack costs shown to fit within the $800 budget?",
        "Are >= 30 reddit threads cited across at least 4 photography sub-forums?",
        "Is each reddit thread classified by topic role (sensor-debate, sample-critique, beginner-advice, gear-purchase)?",
        "Are >= 25 wiki articles cited with URL + defining statement?",
        "Are all 11 mandatory wiki articles cited (Mirrorless camera, DSLR, Image sensor format, Crop factor, Aperture, Shutter speed, ISO, Depth of field, Bokeh, Computational photography, Exposure)?",
        "Is the 3 x 5 taxonomy matrix fully populated and each cell rated {strong / workable / weak}?",
        "Does each of the 15 cells cite >= 1 shopping + >= 1 reddit + >= 1 wiki URL?",
        "Are >= 5 'hidden cost' contradictions surfaced with full triple evidence (shopping URL + reddit URL + wiki URL)?",
        "Does each hidden cost name the specific marketing claim and the specific reality contradiction?",
        "Are 3 upgrade-path paragraphs present (one per stack)?",
        "Does each upgrade-path paragraph cite >= 4 reddit threads?",
        "Are all cited URLs markdown-linked and resolvable on the sandbox?",
        "Are >= 60 distinct URLs cited in total?",
        "Is per-domain minimum met: >= 30 shopping, >= 20 reddit, >= 15 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid TOP-10 ranking format?",
        "Does the report avoid chain-of-thought?",
        "Does the report explicitly call out which stack is wrong for each use case (not only positive ratings)?",
    ],
    "dr_cross_deep_0006": [
        "Are exactly 5 marketing claims defined upfront (PFOA-free safety / ceramic durability / iron leaching / stainless reactivity / anodized aluminum)?",
        "Does each of the 5 claims receive a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED}?",
        "For each claim, is there a shopping product URL cited with the **verbatim marketing quote** that makes the claim?",
        "For each claim, is there >= 1 reddit URL with user counter-evidence (or supporting evidence if SUPPORTED)?",
        "For each claim, is there >= 1 wiki URL grounding the underlying chemistry or physics?",
        "Does each claim include a 1-paragraph reasoning explaining how the evidence supports the verdict?",
        "Are >= 36 shopping product pages enumerated across 5 cookware categories with price + rating?",
        "Are >= 30 reddit threads from at least 4 cooking sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles (PTFE, PFOA, Non-stick surface, Cast-iron, Stainless steel, Anodizing, Aluminium toxicity, Maillard, Heat capacity, Thermal conductivity) cited?",
        "Is a safety-risk ranking of all 5 cookware materials presented?",
        "Is the safety-risk ranking justified with citations to the 5 claim verdicts?",
        "Are 6-8 shopping rules listed in a cheat-sheet?",
        "Does each shopping rule cite >= 1 wiki URL?",
        "Are at least 2 of the 5 verdicts DEBUNKED or PARTIALLY_SUPPORTED (i.e., the report is not a marketing whitewash)?",
        "Are >= 60 distinct URLs cited in total?",
        "Is per-domain minimum met: >= 30 shopping, >= 20 reddit, >= 15 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Does the report avoid TOP-10 product ranking (this is Debunking, not Recommendation)?",
        "Does the report avoid chain-of-thought and start with the verdict table?",
    ],
    "dr_cross_deep_0007": [
        "Are exactly 5 dog-care marketing/folk claims defined upfront?",
        "Does each claim receive a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}?",
        "For each claim, is there a shopping product URL with the verbatim marketing quote?",
        "For each claim, is there >= 1 reddit thread URL with owner-experience or vet-AMA evidence?",
        "For each claim, is there >= 1 wiki article URL with biological/chemical grounding?",
        "Does each claim include a 1-paragraph reasoning?",
        "Are >= 36 shopping product pages enumerated across food/chews/bowls/supplements?",
        "Are >= 30 reddit threads from at least 4 dog/pet sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles (Dog food, Raw feeding, DCM, BPA, Theanine, Dog anxiety, Periodontal disease, Plaque, Veterinary medicine, Salmonella) cited?",
        "Are >= 3 FDA/AAFCO regulatory gaps named with wiki citations?",
        "Does the regulatory-gap section name specific regulations or their absence?",
        "Is a 'vet-aligned shopping list' of 6-8 bullets included?",
        "Does each shopping-list bullet cite >= 1 shopping + >= 1 reddit + >= 1 wiki URL?",
        "Are at least 2 of the 5 verdicts DEBUNKED or PARTIALLY_SUPPORTED?",
        "Are >= 60 distinct URLs cited in total?",
        "Is per-domain minimum met: >= 30 shopping, >= 20 reddit, >= 15 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Are all cited URLs markdown-linked and resolvable on the sandbox?",
        "Does the report avoid producing a generic Top-10 dog product ranking?",
        "Does the report avoid chain-of-thought and start with the verdict table?",
    ],
}


CHECKLISTS["dr_cross_deep_0008"] = [
    "Are exactly 5 baby-essential claims defined upfront (positioner SIDS / formula equivalence / extended rear-facing / sleep sack / anti-colic bottle)?",
    "Does each receive a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}?",
    "Is the verbatim marketing claim quoted from a cited shopping URL for each claim?",
    "Is >= 1 reddit thread URL cited per claim (parent experience / nurse advice)?",
    "Is >= 1 wiki URL cited per claim grounding the medical / safety basis?",
    "Does each claim include a 1-paragraph reasoning?",
    "Are >= 36 shopping product pages enumerated across positioners / formulas / car seats / sleep sacks / bottles?",
    "Are >= 30 reddit threads from >= 4 parenting sub-forums cited?",
    "Are >= 25 wiki articles cited?",
    "Are all 10 mandatory wiki articles (SIDS, Infant formula, Breast milk, Child safety seat, Swaddling, Sleep sack, Colic, Pacifier, ISOFIX, Breastfeeding) present?",
    "Is each verdict explicitly compared to AAP / NHS / WHO guidance with wiki citation?",
    "Does the report flag any claim that contradicts the relevant pediatric body's stance?",
    "Is a 6-8 bullet safe-sleep checklist provided?",
    "Does each safe-sleep bullet cite >= 1 source (shopping / reddit / wiki)?",
    "Are at least 3 of the 5 verdicts DEBUNKED, PARTIALLY_SUPPORTED, or UNDETERMINED (the report is not a marketing whitewash)?",
    "Are >= 60 distinct URLs cited?",
    "Is per-domain minimum met: >= 30 shopping, >= 20 reddit, >= 15 wiki?",
    "Is the report 3500-8000 words / >= 25 paragraphs?",
    "Are all cited URLs markdown-linked and sandbox-resolvable?",
    "Does the report avoid TOP-10 product ranking?",
    "Does the report avoid chain-of-thought and start with the verdict table?",
]

CHECKLISTS["dr_cross_deep_0009"] = [
    "Does the report explicitly address 'why does EV range drop in cold weather' as the central question?",
    "Are exactly 4 causal layers defined (L1 chemistry, L2 thermal, L3 behaviour, L4 measured)?",
    "Does L1 cite >= 3 wiki articles on battery chemistry (electrolyte, internal resistance, lithium plating)?",
    "Does L2 cite >= 3 wiki articles on thermal management (heat pump, cabin heater, specific heat capacity)?",
    "Does L3 cite >= 5 reddit threads on driver behaviour and HVAC adjustments?",
    "Does L4 cite >= 8 reddit threads with **explicit percentage** range-drop numbers?",
    "Are >= 30 shopping products related to cold-weather EV operation cited (chargers, heaters, accessories)?",
    "Are >= 30 reddit threads from >= 4 EV-related sub-forums cited?",
    "Are >= 25 wiki articles cited?",
    "Are all 10 mandatory wiki articles (Li-ion, Thermal mgmt, Heat pump, Internal resistance, Electrolyte, Li plating, Regen, Cabin heater, Specific heat, Arrhenius) cited?",
    "Is a multi-layer causal hierarchy presented in markdown (indented bullets, not flat list)?",
    "Are >= 5 mitigation strategies ranked by % range recovered?",
    "Does each mitigation strategy cite >= 1 shopping URL + >= 1 reddit URL?",
    "Are >= 3 EV models ranked by aggregated reddit cold-weather sentiment?",
    "Does each ranked model cite >= 3 reddit threads in support?",
    "Are >= 60 distinct URLs cited?",
    "Is per-domain minimum met: >= 30 shopping, >= 20 reddit, >= 15 wiki?",
    "Is the report 3500-8000 words / >= 25 paragraphs?",
    "Does the report avoid giving a generic 'best EV' Top-10 (this is Causal, not Recommendation)?",
    "Are all cited URLs markdown-linked and sandbox-resolvable?",
    "Does the report avoid chain-of-thought and start with L1 chemistry?",
]

CHECKLISTS["dr_cross_deep_0010"] = [
    "Are exactly 4 eras defined chronologically (buckling-spring / Cherry MX dominance / hot-swap / analog/Hall)?",
    "Is each era given >= 3 wiki + >= 3 shopping + >= 3 reddit citations?",
    "Is the chronology genuinely chronological (Era 1 -> 4 in increasing time)?",
    "Are at least 5 distinct switch families named across the timeline (buckling-spring, Cherry MX, Topre, optical, Hall)?",
    "Does the modern taxonomy split switch types by actuation mechanism (>= 3 branches)?",
    "Does each leaf in the taxonomy cite a shopping URL + a wiki URL?",
    "Are exactly 7 community-debunked myths enumerated?",
    "Does each myth cite >= 1 wiki URL (technical grounding) + >= 1 reddit URL (community discussion)?",
    "Are >= 30 shopping product pages cited spanning the timeline?",
    "Are >= 30 reddit threads from >= 4 keyboard sub-forums cited?",
    "Are >= 25 wiki articles cited?",
    "Are all 10 mandatory wiki articles (Buckling spring, Cherry, Hall effect, Optical switch, Computer keyboard, Tactile bump, Keycap, Membrane, Scissor, Topre) cited?",
    "Are >= 60 distinct URLs cited?",
    "Is per-domain minimum met: >= 30 shopping, >= 20 reddit, >= 15 wiki?",
    "Is the report 3500-8000 words / >= 25 paragraphs?",
    "Are all cited URLs markdown-linked and sandbox-resolvable?",
    "Does the report avoid producing a TOP-10 keyboard ranking (this is Timeline, not Recommendation)?",
    "Does the report distinguish between 'currently sold' products and 'historically significant' products?",
    "Does the report cite at least 3 vintage / discontinued products as historical anchors?",
    "Does the report avoid chain-of-thought and start with Era 1?",
    "Does each era include reddit-sourced community sentiment, not just product specs?",
]

CHECKLISTS["dr_cross_deep_0011"] = [
    "Are exactly 5 sleep-aid claims defined upfront (melatonin dose / tracker accuracy / blue-light glasses / magnesium / weighted blanket)?",
    "Does each claim receive a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}?",
    "Is the verbatim marketing claim quoted from a shopping URL for each claim?",
    "Is >= 1 reddit thread cited per claim?",
    "Is >= 1 wiki article cited per claim?",
    "Does each claim include a 1-paragraph reasoning?",
    "Are >= 36 shopping product pages enumerated across the 5 product categories?",
    "Are >= 30 reddit threads from >= 4 sleep / supplement / biohacker sub-forums cited?",
    "Are >= 25 wiki articles cited?",
    "Are all 10 mandatory wiki articles (Melatonin, Sleep, Polysomnography, Actigraphy, Circadian rhythm, Blue light, Magnesium deficiency, Weighted blanket, Insomnia, Placebo) cited?",
    "Are 2 dose-response analyses presented (melatonin and magnesium)?",
    "Does the dose-response section cite both wiki definitions AND reddit user-trial discussions?",
    "Is the sleep-hygiene cheat-sheet 6-8 bullets long?",
    "Does each cheat-sheet bullet describe a NON-product practice (the report doesn't push more shopping)?",
    "Does each cheat-sheet bullet cite >= 1 wiki URL?",
    "Are >= 60 distinct URLs cited?",
    "Is per-domain minimum met: >= 30 shopping, >= 20 reddit, >= 15 wiki?",
    "Is the report 3500-8000 words / >= 25 paragraphs?",
    "Are all cited URLs markdown-linked and sandbox-resolvable?",
    "Are at least 2 of the 5 verdicts DEBUNKED, PARTIALLY_SUPPORTED, or UNDETERMINED?",
    "Does the report avoid chain-of-thought and start with the verdict table?",
]

CHECKLISTS["dr_cross_deep_0012"] = [
    "Are >= 8 distinct wireless protocols catalogued (Wi-Fi, Z-Wave, Zigbee, Thread, Matter, BLE, Z-Wave Plus, Insteon, Lutron, etc.)?",
    "Does the catalog table have >= 7 columns (name / band / mesh / pairing / encryption / vulnerabilities / cost / sentiment)?",
    "Does each catalog row cite >= 1 wiki URL for the protocol's vulnerability discussion?",
    "Does each row cite >= 1 shopping URL showing a product implementing it with price?",
    "Does each row cite >= 1 reddit URL for community reliability sentiment?",
    "Is a threat-model decision tree presented with >= 3 levels of decision (cloud / local / hybrid -> protocols)?",
    "Does each decision-tree node cite at least 1 source?",
    "Are exactly 5 'protocols / products to AVOID' enumerated?",
    "Does each AVOID entry cite >= 1 shopping URL (the bad product), >= 1 reddit URL (community report), >= 1 wiki URL (the underlying vulnerability)?",
    "Are >= 40 shopping product pages cited spanning 5 device categories (locks / cameras / hubs / plugs / sensors)?",
    "Are >= 30 reddit threads from >= 4 home-automation sub-forums cited?",
    "Are >= 25 wiki articles cited?",
    "Are all 10 mandatory wiki articles (WPA, Z-Wave, Zigbee, Thread, Matter, BLE, Mesh networking, Public-key cryptography, IoT, Pre-shared key) cited?",
    "Does the catalog distinguish mesh-vs-star topology for each protocol?",
    "Does the catalog name specific encryption (AES-128, ChaCha20, none, etc.) where applicable?",
    "Are >= 60 distinct URLs cited?",
    "Is per-domain minimum met: >= 30 shopping, >= 20 reddit, >= 15 wiki?",
    "Is the report 3500-8000 words / >= 25 paragraphs?",
    "Are all cited URLs markdown-linked and sandbox-resolvable?",
    "Does the report avoid TOP-10 product ranking (this is Enumeration, not Recommendation)?",
    "Does the report avoid chain-of-thought and start with the catalog table?",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="show what would be written without touching files")
    args = parser.parse_args()

    # 1. Write each task json
    written_tasks = []
    for task_id, spec in TASKS.items():
        task_json = base_task(
            task_id,
            intent=spec["intent"],
            start_url=spec["start_url"],
            synthesis_extra=spec["synthesis_extra"],
        )
        out_path = TASKS_DIR / f"{task_id}.json"
        if args.dry_run:
            print(f"[DRY] would write {out_path} ({len(json.dumps(task_json))} bytes)")
        else:
            out_path.write_text(json.dumps(task_json, indent=2, ensure_ascii=False) + "\n")
            print(f"WROTE {out_path}")
        written_tasks.append(task_id)

    # 2. Write merged checklists_deep.json
    # Preserve existing 0001 / 0002 / 0005 (anchors), overwrite 0003-0012
    existing = {}
    if CHECKLIST_PATH.exists():
        existing = json.loads(CHECKLIST_PATH.read_text())

    merged = {}
    # Keep anchors from existing file (or pull from existing 0001 if 0002/0005 missing)
    for anchor in ["dr_cross_deep_0001", "dr_cross_deep_0002", "dr_cross_deep_0005"]:
        if anchor in existing:
            merged[anchor] = existing[anchor]
        else:
            print(f"WARN anchor {anchor} not found in existing checklist — copying from 0001")
            merged[anchor] = existing.get("dr_cross_deep_0001", [])

    # Overwrite 0003-0012 from CHECKLISTS dict
    for tid, items in CHECKLISTS.items():
        merged[tid] = items
        if len(items) != 21:
            print(f"WARN {tid} checklist has {len(items)} items, expected 21")

    if args.dry_run:
        print(f"[DRY] would write {CHECKLIST_PATH} with {len(merged)} tasks")
    else:
        CHECKLIST_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
        print(f"WROTE {CHECKLIST_PATH} (n_tasks={len(merged)})")

    # 3. Sanity summary
    print(f"\n=== summary ===")
    print(f"task jsons: {len(written_tasks)} ({', '.join(written_tasks)})")
    print(f"checklist tasks: {len(merged)} (anchors: 0001,0002,0005; v1: 0003,0004,0006,0007,0008,0009,0010,0011,0012)")


if __name__ == "__main__":
    main()
