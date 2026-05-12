#!/usr/bin/env python3
"""Batch-generate topic YAML files for tasks 0031-0100.

Reads the expansion matrix from TASK_EXPANSION_MATRIX.md and generates
one YAML per topic using DeepSeek V4 flash.

Usage:
    python3 scripts/gen_topics_batch.py [--start 31] [--end 100] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TOPICS = [
    # Health/Medicine (0031-0041)
    (31, "Health/Medicine", "Recommendation", "home blood pressure monitors", "blood_pressure_monitors"),
    (32, "Health/Medicine", "Recommendation", "vitamin D supplements", "vitamin_d_supplements"),
    (33, "Health/Medicine", "Comparison", "physical therapy vs chiropractic vs massage for back pain", "pt_vs_chiro_vs_massage"),
    (34, "Health/Medicine", "Comparison", "plant-based vs Mediterranean vs keto diet", "diet_comparison"),
    (35, "Health/Medicine", "Debunking", "detox and cleanse product health claims", "detox_cleanse_debunk"),
    (36, "Health/Medicine", "Debunking", "collagen supplement effectiveness claims", "collagen_supplement_debunk"),
    (37, "Health/Medicine", "Causal", "why do antibiotics cause bacterial resistance", "antibiotic_resistance_causal"),
    (38, "Health/Medicine", "Causal", "how does intermittent fasting affect metabolism", "intermittent_fasting_causal"),
    (39, "Health/Medicine", "Timeline", "evolution of diabetes treatment from insulin to GLP-1 agonists", "diabetes_treatment_timeline"),
    (40, "Health/Medicine", "Timeline", "history of vaccine development methods", "vaccine_dev_timeline"),
    (41, "Health/Medicine", "Enumeration", "catalog of FDA-approved weight loss medications", "weight_loss_drugs_catalog"),
    # Technology (0042-0053)
    (42, "Technology", "Recommendation", "best budget NAS devices for home server", "budget_nas_recommendation"),
    (43, "Technology", "Recommendation", "VPN services for privacy and security", "vpn_recommendation"),
    (44, "Technology", "Comparison", "React vs Vue vs Svelte for new web projects", "frontend_framework_comparison"),
    (45, "Technology", "Comparison", "AWS vs Azure vs GCP for startup workloads", "cloud_provider_comparison"),
    (46, "Technology", "Debunking", "5G cellular health risk claims", "5g_health_debunk"),
    (47, "Technology", "Debunking", "quantum computing near-term capability hype", "quantum_computing_debunk"),
    (48, "Technology", "Causal", "why do SSDs slow down over time", "ssd_slowdown_causal"),
    (49, "Technology", "Causal", "how does LLM hallucination arise mechanistically", "llm_hallucination_causal"),
    (50, "Technology", "Timeline", "evolution of smartphone processors from 2007 to 2026", "smartphone_processor_timeline"),
    (51, "Technology", "Timeline", "history of version control systems from RCS to Git", "version_control_timeline"),
    (52, "Technology", "Enumeration", "catalog of major open-source LLM model families", "opensource_llm_catalog"),
    (53, "Technology", "Enumeration", "catalog of USB standards and connector types", "usb_standards_catalog"),
    # Environment (0054-0064)
    (54, "Environment", "Recommendation", "best home solar panel kits for residential use", "solar_panel_recommendation"),
    (55, "Environment", "Recommendation", "eco-friendly household cleaning products", "eco_cleaning_recommendation"),
    (56, "Environment", "Comparison", "electric vs hybrid vs hydrogen fuel cell vehicles", "ev_hybrid_hydrogen_comparison"),
    (57, "Environment", "Debunking", "recycling effectiveness myths and misconceptions", "recycling_myths_debunk"),
    (58, "Environment", "Debunking", "organic food health and environmental benefit claims", "organic_food_debunk"),
    (59, "Environment", "Causal", "why are coral reefs bleaching at accelerating rates", "coral_bleaching_causal"),
    (60, "Environment", "Causal", "how does fast fashion impact the environment", "fast_fashion_env_causal"),
    (61, "Environment", "Timeline", "evolution of renewable energy costs from 2000 to 2026", "renewable_energy_cost_timeline"),
    (62, "Environment", "Timeline", "history of plastic pollution awareness and regulation", "plastic_pollution_timeline"),
    (63, "Environment", "Enumeration", "catalog of carbon offset certification standards", "carbon_offset_catalog"),
    (64, "Environment", "Enumeration", "catalog of endangered species recovery success stories", "species_recovery_catalog"),
    # Business (0065-0073)
    (65, "Business", "Recommendation", "best project management tools for small teams", "pm_tools_recommendation"),
    (66, "Business", "Recommendation", "CRM software for early-stage startups", "crm_startup_recommendation"),
    (67, "Business", "Comparison", "LLC vs S-Corp vs C-Corp for tech founders", "business_entity_comparison"),
    (68, "Business", "Debunking", "dropshipping passive income claims", "dropshipping_debunk"),
    (69, "Business", "Causal", "why do most startups fail in years 2-3", "startup_failure_causal"),
    (70, "Business", "Causal", "how does inflation affect small businesses differently than large ones", "inflation_small_biz_causal"),
    (71, "Business", "Timeline", "evolution of e-commerce platforms from 2000 to 2026", "ecommerce_platform_timeline"),
    (72, "Business", "Enumeration", "catalog of SBA loan types and eligibility requirements", "sba_loan_catalog"),
    (73, "Business", "Enumeration", "catalog of business intelligence and analytics tools", "bi_tools_catalog"),
    # Politics (0074-0081)
    (74, "Politics", "Recommendation", "best news literacy and fact-checking resources", "factcheck_resources_recommendation"),
    (75, "Politics", "Comparison", "ranked-choice vs plurality vs approval voting systems", "voting_system_comparison"),
    (76, "Politics", "Comparison", "universal basic income experiments across countries", "ubi_experiments_comparison"),
    (77, "Politics", "Debunking", "voter fraud prevalence claims in US elections", "voter_fraud_debunk"),
    (78, "Politics", "Causal", "why does gerrymandering persist despite court rulings", "gerrymandering_causal"),
    (79, "Politics", "Causal", "how do economic sanctions affect civilian populations", "sanctions_civilian_causal"),
    (80, "Politics", "Timeline", "evolution of social media regulation from 2016 to 2026", "social_media_regulation_timeline"),
    (81, "Politics", "Enumeration", "catalog of international climate agreements and their outcomes", "climate_agreements_catalog"),
    # Existing domain gaps (0082-0100)
    (82, "Health/Safety", "Recommendation", "best air purifiers for allergy sufferers", "air_purifier_recommendation"),
    (83, "Health/Safety", "Timeline", "evolution of food safety regulations in the US", "food_safety_timeline"),
    (84, "Health/Safety", "Enumeration", "catalog of common household toxins and exposure routes", "household_toxins_catalog"),
    (85, "Travel", "Recommendation", "best travel insurance policies for international trips", "travel_insurance_recommendation"),
    (86, "Travel", "Timeline", "evolution of airline loyalty programs and frequent flyer miles", "airline_loyalty_timeline"),
    (87, "Travel", "Enumeration", "catalog of digital nomad visa programs by country", "nomad_visa_catalog"),
    (88, "Education", "Recommendation", "best online learning platforms for career changers", "online_learning_recommendation"),
    (89, "Education", "Debunking", "learning style myths (visual/auditory/kinesthetic)", "learning_styles_debunk"),
    (90, "Education", "Timeline", "evolution of MOOCs and online education from 2012 to 2026", "mooc_timeline"),
    (91, "Entertainment", "Recommendation", "best indie video games under $20", "indie_games_recommendation"),
    (92, "Entertainment", "Debunking", "video game violence and aggression claims", "game_violence_debunk"),
    (93, "Entertainment", "Enumeration", "catalog of music streaming royalty payment models", "music_royalty_catalog"),
    (94, "Finance", "Causal", "why do cryptocurrency markets crash in correlated waves", "crypto_crash_causal"),
    (95, "Finance", "Timeline", "evolution of payment systems from cash to BNPL", "payment_systems_timeline"),
    (96, "Finance", "Enumeration", "catalog of retirement account types across major economies", "retirement_accounts_catalog"),
    (97, "Law", "Causal", "how do class action lawsuits work and who benefits", "class_action_causal"),
    (98, "Law", "Timeline", "evolution of data privacy laws worldwide from GDPR onward", "privacy_law_timeline"),
    (99, "Science", "Comparison", "fusion reactor designs: tokamak vs stellarator vs laser inertial", "fusion_reactor_comparison"),
    (100, "Science", "Timeline", "history of Mars exploration missions from Mariner to Perseverance", "mars_exploration_timeline"),
]


REF_YAML = (ROOT / "configs" / "deep_topics" / "0001_audio_headphones.yaml").read_text()


def call_llm(prompt: str, system: str) -> str:
    from openai import OpenAI
    client = OpenAI(
        base_url="https://open.bigmodel.cn/api/coding/paas/v4",
        api_key=os.environ.get("GLM_API_KEY", "5e4b5082f8954dc98d63935220002707.9Go2OiZMkcbDDXVx"),
    )
    resp = client.chat.completions.create(
        model="glm-4-flash",
        max_tokens=4096,
        temperature=0.7,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content or ""


def gen_one_yaml(num: int, domain: str, intent: str, topic_desc: str, topic_id: str) -> str:
    system = (
        "You are an expert benchmark designer for AI agent evaluation. "
        "You design deep-research tasks that require agents to search across "
        "three sandbox sources: an e-commerce site (Magento shopping), a Reddit-like forum (Postmill), "
        "and a Wikipedia mirror (Kiwix). Each task must be grounded in >= 120 sandbox URLs."
    )

    prompt = f"""Generate a topic configuration YAML for a deep-research benchmark task.

Topic: {topic_desc}
Domain: {domain}
Intent type: {intent}
topic_id: {topic_id}
task_id: dr_cross_deep_{num:04d}

Produce ONLY a YAML document with these exact fields:
- topic_id: {topic_id}
- task_id: dr_cross_deep_{num:04d}
- display_name: (human readable, capitalize first letter)

- shopping_keywords: (array of 9 search terms for a general e-commerce store — these must be REALISTIC product searches, not abstract concepts. Think about what PHYSICAL PRODUCTS relate to the topic. E.g. for "antibiotics" you'd search for "health books", "supplements", "first aid kit", etc.)

- reddit_forums: (array of 8 Postmill forum names — at least 2 general forums like AskReddit/LifeProTips and 4+ domain-specific ones)
- reddit_keywords: (array of 8 search keywords for forum discussions)

- wiki_mandatory: (array of 10 Wikipedia article titles that MUST appear — use EXACT Wikipedia article titles with proper capitalization and disambiguation)
- wiki_extra: (array of 15 additional Wikipedia articles for broader coverage)

IMPORTANT constraints:
- Shopping keywords must find actual PRODUCTS on an online store (books, equipment, devices, supplements, tools, etc.)
- Wiki titles must be real Wikipedia article names (check disambiguation)
- Reddit forums should include plausible names: technology, science, AskReddit, personalfinance, Fitness, politics, worldnews, etc.

Reference format:
```yaml
{REF_YAML}
```

Output ONLY the YAML. No commentary, no markdown fences."""

    raw = call_llm(prompt, system)
    raw = re.sub(r"^```(?:yaml|YAML)?\s*\n?", "", raw.strip())
    raw = re.sub(r"\n?```\s*$", "", raw)
    return raw.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=31)
    ap.add_argument("--end", type=int, default=100)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out_dir = ROOT / "configs" / "deep_topics"
    out_dir.mkdir(parents=True, exist_ok=True)

    to_gen = [(n, d, i, t, tid) for n, d, i, t, tid in TOPICS if args.start <= n <= args.end]
    print(f"Generating {len(to_gen)} topic YAMLs ({args.start}-{args.end})")

    for num, domain, intent, topic_desc, topic_id in to_gen:
        out_path = out_dir / f"{num:04d}_{topic_id}.yaml"
        if out_path.exists():
            print(f"  [{num:04d}] SKIP (exists): {out_path.name}")
            continue

        if args.dry_run:
            print(f"  [{num:04d}] DRY RUN: {topic_id} ({domain}/{intent})")
            continue

        print(f"  [{num:04d}] generating: {topic_id} ({domain}/{intent})...", end=" ", flush=True)
        try:
            yaml_text = gen_one_yaml(num, domain, intent, topic_desc, topic_id)
            out_path.write_text(yaml_text + "\n")
            print(f"OK ({len(yaml_text)} chars)")
        except Exception as e:
            print(f"ERROR: {e}")
            continue
        time.sleep(0.5)

    print(f"\nDone. YAMLs in {out_dir}")


if __name__ == "__main__":
    main()
