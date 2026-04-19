"""Generate 20 scholarly/policy deep-research tasks (dr_cross_v3_0088..0107).

These tasks address P0-3 from the peer-review audit: domain diversity.
Earlier 87 tasks were consumer/UGC-heavy (Magento + Reddit). These 20
tasks weave in Wikipedia's policy, historical, medical, and scientific
articles so the benchmark covers multiple domains — while still being
fully reproducible inside our kiwix+Magento+Postmill sandbox.

Each task requires cross-site evidence from:
  - Wikipedia (kiwix) for the scholarly / policy / historical ground truth
  - Reddit (Postmill) for contemporary community sentiment
  - Magento (One Stop Market) for a concrete consumer application (when
    domain permits — not all tasks use shopping)

Usage:
    python scripts/generate_scholarly_tasks.py      # writes 0088..0107
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site"


def _tmpl(**k):
    """Fill the standard dr_cross_v3 schema."""
    return {
        "schema_version": "3.0.0",
        "task_id": k["task_id"],
        "sites": k["sites"],
        "intent": k["intent"],
        "start_url": k["start_url"],
        "storage_state": None,
        "require_login": False,
        "markdown_spec": {
            "min_words": k.get("min_words", 1000),
            "max_words": k.get("max_words", 2800),
            "min_paragraphs": k.get("min_paragraphs", 7),
            "min_citations": k.get("min_citations", 8),
            "min_pages_browsed": k.get("min_pages_browsed", 8),
        },
        "citation_policy": {
            "required_for": [],
            "must_be_in_domain": [f"__{s.upper()}__" for s in k["domains"]],
            "min_distinct_sources": k.get("min_sources", 6),
        },
        "golden": {
            "triples_path": f"data/golden/{k['task_id']}.json",
            "expected_predicates": k["predicates"],
        },
        "coverage_checklist_path":
            "data/tasks/deep_research/cross_site/checklists_v3.json",
        "difficulty": k.get("difficulty", 4),
        "expected_steps": k.get("expected_steps", 14),
        "author_notes": k.get("author_notes", ""),
    }


TASKS = [
    # ---- Public health / medicine (4)
    _tmpl(
        task_id="dr_cross_v3_0088",
        sites=["wikipedia", "reddit"],
        intent=(
            "Write a policy-informed consumer guide on 'what actually works "
            "for the common cold'. (1) Wikipedia — open 'Common cold' and "
            "'Over-the-counter drug' and extract 4+ facts on pathogenesis, "
            "evidence-based interventions, and OTC regulatory history. "
            "(2) Reddit /f/AskScience AND /f/LifeProTips — find posts / "
            "comments on what people *report* working versus what is "
            "evidence-based; collect 3+ posts with title, score, comment "
            "count. The report must: (a) separate evidence-backed remedies "
            "from community folklore, (b) cite Wikipedia for the biology, "
            "(c) flag 2+ common misconceptions. Cite every claim."
        ),
        start_url="__WIKIPEDIA__/A/Common_cold",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "publication_year", "forum", "score", "comment_count"],
        difficulty=4, expected_steps=12,
        author_notes="Scholarly/medicine domain, wiki-heavy.",
    ),
    _tmpl(
        task_id="dr_cross_v3_0089",
        sites=["wikipedia", "reddit"],
        intent=(
            "Produce a briefing on the 'history and science of vaccination'. "
            "(1) Wikipedia — 'Vaccine', 'Vaccination schedule', and "
            "'History of vaccination'. Extract 5+ facts covering Edward "
            "Jenner, pathogen-specific mechanisms (live vs. subunit), and "
            "regulatory milestones. (2) Reddit /f/AskScience for public "
            "misconceptions and counter-evidence. The report must: (a) "
            "summarise the science, (b) trace regulatory evolution, "
            "(c) contrast Wikipedia-backed consensus with 2+ community "
            "misconceptions you found on Reddit. Cite every factual claim."
        ),
        start_url="__WIKIPEDIA__/A/Vaccine",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "forum", "score"],
        difficulty=5, expected_steps=16,
        author_notes="Historical + medical scholarly task.",
    ),
    _tmpl(
        task_id="dr_cross_v3_0090",
        sites=["wikipedia", "reddit", "shopping"],
        intent=(
            "Create a consumer-health report on 'sunscreen: what the "
            "science says and what people actually buy'. (1) Wikipedia — "
            "'Sunscreen' and 'Ultraviolet': extract the mechanism of "
            "action, SPF scale definition, and known limitations. "
            "(2) One Stop Market — browse beauty-personal-care for at "
            "least 3 sunscreen products under $30 (name, price, rating, "
            "SPF if stated). (3) Reddit /f/LifeProTips — 2+ posts on how "
            "people actually reapply / mistakes to avoid. Report must: "
            "(a) ground biology via Wikipedia, (b) evaluate each product "
            "against that biology, (c) close with 'what Reddit gets wrong "
            "or right'. Cite every claim."
        ),
        start_url="__WIKIPEDIA__/A/Sunscreen",
        domains=["wikipedia", "reddit", "shopping"],
        predicates=["article_title", "price", "rating", "forum", "score"],
        difficulty=5, expected_steps=18,
        author_notes="3-site: medicine + consumer + community.",
    ),
    _tmpl(
        task_id="dr_cross_v3_0091",
        sites=["wikipedia", "reddit"],
        intent=(
            "Write a technical brief on 'sleep hygiene: what the textbooks "
            "say vs. what the internet advises'. (1) Wikipedia — 'Sleep' "
            "and 'Insomnia'. Pull the circadian-rhythm mechanism, the "
            "DSM criteria for insomnia, and 3+ evidence-based treatments. "
            "(2) Reddit /f/LifeProTips AND /f/AskReddit for 3+ highly "
            "voted tips; note score and comment count. Contrast pharma vs "
            "behavioural interventions; quantify where community advice "
            "aligns with clinical evidence. Cite every claim."
        ),
        start_url="__WIKIPEDIA__/A/Sleep",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "forum", "score"],
        difficulty=4, expected_steps=12,
    ),
    # ---- Policy / history (6)
    _tmpl(
        task_id="dr_cross_v3_0092",
        sites=["wikipedia", "reddit"],
        intent=(
            "Write a balanced policy primer on 'universal basic income (UBI)'. "
            "(1) Wikipedia — 'Basic income', 'Milton Friedman', and "
            "'Mincome'. Extract 5+ facts: historical pilots, economic "
            "arguments for and against, and empirical findings from "
            "Finnish / Canadian trials. (2) Reddit /f/AskReddit OR "
            "/f/politics — 3+ posts discussing public sentiment. The "
            "report must: (a) summarise scholarly consensus (or lack "
            "thereof), (b) present 2+ concrete policy experiments with "
            "outcomes, (c) note where community sentiment diverges. Cite."
        ),
        start_url="__WIKIPEDIA__/A/Basic_income",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "publication_year", "forum", "score"],
        difficulty=5, expected_steps=14,
        author_notes="Policy / economics scholarly task.",
    ),
    _tmpl(
        task_id="dr_cross_v3_0093",
        sites=["wikipedia", "reddit"],
        intent=(
            "Produce a short historical analysis: 'the industrial "
            "revolution — drivers, divergence, and modern analogies'. "
            "(1) Wikipedia — 'Industrial Revolution' and 'Second "
            "Industrial Revolution' (5+ facts: dates, geography, "
            "productivity gains). (2) Reddit /f/history or /f/AskReddit "
            "for 2+ threads on how people understand the period today. "
            "The report must have a table comparing 1st vs 2nd revolutions "
            "(invention, region, productivity multiplier), and close "
            "with a 1-paragraph analogy to the present AI wave. Cite."
        ),
        start_url="__WIKIPEDIA__/A/Industrial_Revolution",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "publication_year", "forum", "score"],
        difficulty=4, expected_steps=12,
    ),
    _tmpl(
        task_id="dr_cross_v3_0094",
        sites=["wikipedia", "reddit"],
        intent=(
            "Brief: 'climate policy — the Paris Agreement and its discontents'. "
            "(1) Wikipedia — 'Paris Agreement' and 'Climate change mitigation'. "
            "Extract 5+ facts on signatories, NDC architecture, and 1.5 C "
            "vs 2 C targets. (2) Reddit /f/environment or /f/politics — "
            "3+ posts on enforcement, criticisms, or alternatives. The "
            "report must: (a) explain the architecture, (b) present 2+ "
            "concrete criticisms with the scholarly rebuttal (from "
            "Wikipedia), (c) close with public-sentiment summary. Cite."
        ),
        start_url="__WIKIPEDIA__/A/Paris_Agreement",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "publication_year", "forum", "score"],
        difficulty=5, expected_steps=15,
    ),
    _tmpl(
        task_id="dr_cross_v3_0095",
        sites=["wikipedia", "reddit"],
        intent=(
            "Analysis: 'the scientific method — canonical vs. practised'. "
            "(1) Wikipedia — 'Scientific method', 'Philosophy of science', "
            "and 'Thomas Kuhn'. Pull 5+ facts on falsification, paradigm "
            "shifts, and reproducibility. (2) Reddit /f/AskScience — 3+ "
            "posts on where practising scientists say they diverge from "
            "the textbook method. Close with a short commentary on the "
            "replication crisis. Cite every claim."
        ),
        start_url="__WIKIPEDIA__/A/Scientific_method",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "forum", "score"],
        difficulty=5, expected_steps=14,
    ),
    _tmpl(
        task_id="dr_cross_v3_0096",
        sites=["wikipedia", "reddit"],
        intent=(
            "Short brief on 'the Cold War and nuclear deterrence'. "
            "(1) Wikipedia — 'Cold War', 'Mutual assured destruction', and "
            "'Cuban Missile Crisis'. Extract 5+ dated facts. (2) Reddit "
            "/f/history — 2+ posts on how people now interpret deterrence "
            "doctrine (especially post-Ukraine). The report must include "
            "a timeline table and a closing paragraph on whether "
            "deterrence logic still applies. Cite."
        ),
        start_url="__WIKIPEDIA__/A/Cold_War",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "publication_year", "forum"],
        difficulty=4, expected_steps=12,
    ),
    _tmpl(
        task_id="dr_cross_v3_0097",
        sites=["wikipedia", "reddit"],
        intent=(
            "Briefing: 'surveillance capitalism — theory and practice'. "
            "(1) Wikipedia — 'Surveillance capitalism' and "
            "'General Data Protection Regulation'. 4+ facts on Shoshana "
            "Zuboff's framework and GDPR scope. (2) Reddit /f/technology "
            "or /f/privacy — 3+ posts on how users actually change "
            "behaviour. The report must: present the theory, map it to "
            "2+ Reddit examples, close with a 'what the public gets wrong' "
            "paragraph. Cite."
        ),
        start_url="__WIKIPEDIA__/A/Surveillance_capitalism",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "forum", "score"],
        difficulty=4, expected_steps=12,
    ),
    # ---- Legal / economic (4)
    _tmpl(
        task_id="dr_cross_v3_0098",
        sites=["wikipedia", "reddit"],
        intent=(
            "Explain the doctrine of 'fair use' in US copyright. "
            "(1) Wikipedia — 'Fair use' and 'Copyright Act of 1976'. 5+ "
            "facts on the 4-factor test and 2+ landmark cases. "
            "(2) Reddit /f/YouTube or /f/AskReddit — 2+ posts on how "
            "creators interpret fair use in practice. The report must: "
            "(a) present the 4 factors with citations, (b) apply them "
            "to a hypothetical, (c) close with where creator intuition "
            "diverges from case law. Cite every claim."
        ),
        start_url="__WIKIPEDIA__/A/Fair_use",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "publication_year", "forum"],
        difficulty=5, expected_steps=14,
    ),
    _tmpl(
        task_id="dr_cross_v3_0099",
        sites=["wikipedia", "reddit"],
        intent=(
            "Personal-finance primer: 'compound interest and the 4% rule'. "
            "(1) Wikipedia — 'Compound interest' and 'Trinity study'. "
            "Extract 5+ facts on the maths and the empirical 4%-withdrawal "
            "finding. (2) Reddit /f/personalfinance — 3+ posts on how "
            "people execute the rule in practice. The report must "
            "include a sample compounding table for a $10k principal, "
            "apply the 4% rule to a retirement scenario, and note "
            "where community advice diverges. Cite."
        ),
        start_url="__WIKIPEDIA__/A/Compound_interest",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "publication_year", "forum", "score"],
        difficulty=4, expected_steps=12,
    ),
    _tmpl(
        task_id="dr_cross_v3_0100",
        sites=["wikipedia", "reddit"],
        intent=(
            "Economics brief: 'inflation — definitions, measurement, and "
            "recent dynamics'. (1) Wikipedia — 'Inflation', 'Consumer "
            "price index', and 'Quantitative easing'. 5+ facts on "
            "measurement methodology and monetary-policy levers. "
            "(2) Reddit /f/Economics or /f/personalfinance — 3+ posts on "
            "public perception of inflation vs. the official CPI. The "
            "report must: (a) present the measurement methodology, "
            "(b) explain 2+ divergences between felt and measured "
            "inflation, (c) suggest what a layperson should watch. Cite."
        ),
        start_url="__WIKIPEDIA__/A/Inflation",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "forum", "score"],
        difficulty=5, expected_steps=14,
    ),
    _tmpl(
        task_id="dr_cross_v3_0101",
        sites=["wikipedia", "reddit"],
        intent=(
            "Explain 'antitrust law — from Sherman to the FTC today'. "
            "(1) Wikipedia — 'Antitrust' and 'Sherman Antitrust Act'. "
            "5+ facts on the historical arc. (2) Reddit /f/technology "
            "or /f/politics — 3+ posts on current big-tech antitrust "
            "action. Report must: present the legal basis, map 2+ current "
            "cases to the Sherman Act text, and note public reaction. "
            "Cite every claim."
        ),
        start_url="__WIKIPEDIA__/A/United_States_antitrust_law",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "publication_year", "forum", "score"],
        difficulty=5, expected_steps=14,
    ),
    # ---- Technology / AI ethics (3)
    _tmpl(
        task_id="dr_cross_v3_0102",
        sites=["wikipedia", "reddit"],
        intent=(
            "Brief: 'large language models — architecture, capabilities, "
            "and failure modes'. (1) Wikipedia — 'Large language model' "
            "and 'Transformer (machine learning model)'. 5+ facts on the "
            "architecture and capability taxonomy. (2) Reddit /f/technology "
            "or /f/MachineLearning — 3+ posts on hallucination, prompt "
            "injection, or empirical use. Report must: summarise the "
            "architecture, list 3 canonical failure modes with Wikipedia "
            "citations, and map 2+ community observations to each. Cite."
        ),
        start_url="__WIKIPEDIA__/A/Large_language_model",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "forum", "score", "comment_count"],
        difficulty=5, expected_steps=16,
        author_notes="Tech/AI scholarly task — meta-relevant.",
    ),
    _tmpl(
        task_id="dr_cross_v3_0103",
        sites=["wikipedia", "reddit"],
        intent=(
            "Policy brief: 'encryption backdoors and the crypto wars'. "
            "(1) Wikipedia — 'Crypto Wars' and 'Clipper chip'. 5+ facts "
            "on the historical fights and their resolutions. (2) Reddit "
            "/f/technology or /f/privacy — 3+ posts on current "
            "government vs. platform encryption debates. Report must "
            "cover: historical precedent, current landscape, 2+ "
            "community arguments, and a closing on trade-offs. Cite."
        ),
        start_url="__WIKIPEDIA__/A/Crypto_Wars",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "publication_year", "forum", "score"],
        difficulty=5, expected_steps=14,
    ),
    _tmpl(
        task_id="dr_cross_v3_0104",
        sites=["wikipedia", "reddit", "shopping"],
        intent=(
            "Consumer+policy report: 'privacy-respecting smart home — "
            "what the science says, what communities recommend, what "
            "One Stop Market sells'. (1) Wikipedia — 'Smart home' and "
            "'Internet of things': pull 4+ facts on protocols "
            "(Zigbee, Matter) and documented privacy risks. (2) One Stop "
            "Market — browse electronics for 3+ smart-home devices under "
            "$150 (name, price, rating). (3) Reddit /f/technology or "
            "/f/privacy — 3+ posts on device choice and risk "
            "minimisation. Report must map each product to a Wikipedia "
            "risk/protocol citation and close with a 3-rule buyer's "
            "guide. Cite every claim."
        ),
        start_url="__WIKIPEDIA__/A/Smart_home",
        domains=["wikipedia", "reddit", "shopping"],
        predicates=["article_title", "price", "rating", "forum", "score"],
        difficulty=5, expected_steps=18,
        author_notes="3-site task: wiki policy + shopping + community.",
    ),
    # ---- Urban / infrastructure (3)
    _tmpl(
        task_id="dr_cross_v3_0105",
        sites=["wikipedia", "reddit"],
        intent=(
            "Urban-planning brief: 'induced demand and highway expansion'. "
            "(1) Wikipedia — 'Induced demand' and 'Braess's paradox'. 4+ "
            "facts on the phenomenon and its empirical evidence. (2) "
            "Reddit /f/urbanplanning or /f/AskReddit — 3+ posts on why "
            "people support or oppose highway widening. Report must "
            "present the theoretical basis, give 2+ empirical examples, "
            "and close with community-sentiment analysis. Cite."
        ),
        start_url="__WIKIPEDIA__/A/Induced_demand",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "forum", "score"],
        difficulty=4, expected_steps=12,
    ),
    _tmpl(
        task_id="dr_cross_v3_0106",
        sites=["wikipedia", "reddit"],
        intent=(
            "Brief: 'public-transit success factors — Tokyo, Curitiba, "
            "Bogotá'. (1) Wikipedia — 'Transport in Tokyo', 'Curitiba', "
            "and 'TransMilenio'. 5+ facts on each system (ridership, "
            "year, fare structure, key innovation). (2) Reddit "
            "/f/urbanplanning for 2+ posts on why these systems succeed. "
            "Report must include a 3-column comparison table plus 1 "
            "paragraph on transferability to a US city. Cite."
        ),
        start_url="__WIKIPEDIA__/A/Transport_in_Tokyo",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "publication_year", "forum", "score"],
        difficulty=5, expected_steps=15,
    ),
    _tmpl(
        task_id="dr_cross_v3_0107",
        sites=["wikipedia", "reddit"],
        intent=(
            "Energy-policy brief: 'nuclear vs. solar — where the "
            "engineering meets the politics'. (1) Wikipedia — 'Nuclear "
            "power', 'Solar power', and 'Levelized cost of electricity'. "
            "5+ quantitative facts (capacity factors, LCOE ranges, "
            "waste / land-use). (2) Reddit /f/energy or /f/technology — "
            "3+ posts on public attitudes. Report must include a "
            "comparison table (capacity factor, LCOE, lifecycle CO2, "
            "land-use), 2+ policy trade-offs, and close with "
            "community-sentiment divergence. Cite every claim."
        ),
        start_url="__WIKIPEDIA__/A/Nuclear_power",
        domains=["wikipedia", "reddit"],
        predicates=["article_title", "forum", "score", "comment_count"],
        difficulty=5, expected_steps=16,
    ),
]


def main() -> None:
    assert len(TASKS) == 20, f"expected 20 tasks, got {len(TASKS)}"
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    for t in TASKS:
        p = TASKS_DIR / f"{t['task_id']}.json"
        p.write_text(json.dumps(t, indent=2, ensure_ascii=False))
        print(f"Wrote {p}")
    print(f"\nTotal {len(TASKS)} scholarly/policy tasks written.")
    print("IDs:", ", ".join(t["task_id"] for t in TASKS))


if __name__ == "__main__":
    main()
