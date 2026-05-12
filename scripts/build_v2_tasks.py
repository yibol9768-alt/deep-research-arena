#!/usr/bin/env python3
"""Build v2 extension: 18 new deep tasks across 6 new domains.

Adds tasks 0013-0030, total pool = 30 tasks across 10 domains.

Per `feedback_deep_tier_constraints.md`: every task MUST keep
- n_must_cite >= 120
- 3 sandbox domains (shop+reddit+wiki), each >= 10
- min_pages_browsed >= 100, min_citations >= 60

For non-consumer domains, shopping uses tangentially-related catalog
items (books, electronics, tools); per_domain_minimum is relaxed
{shopping: 10, reddit: 30, wiki: 25} but NEVER zero.

Run: python3 scripts/build_v2_tasks.py
Idempotent — overwrites task json + checklist, appends yaml if absent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Reuse v1 base_task helper
from scripts.build_v1_deep_tasks import base_task

TASKS_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
CHECKLIST_PATH = TASKS_DIR / "checklists_deep.json"
YAML_DIR = ROOT / "configs" / "deep_topics"


def relaxed_base_task(task_id: str, *, intent: str, start_url: str,
                       synthesis_extra: dict,
                       per_domain_min: dict | None = None) -> dict:
    """Variant of base_task with relaxed per_domain_minimum for non-consumer."""
    t = base_task(task_id, intent=intent, start_url=start_url,
                  synthesis_extra=synthesis_extra)
    if per_domain_min:
        t["citation_policy"]["per_domain_minimum"] = per_domain_min
    return t


# ============================================================
# 18 new task definitions (0013-0030)
# Each entry: {intent, start_url, synthesis_extra, checklist (21 items),
#               yaml: {shopping_keywords, reddit_forums, reddit_keywords,
#                      wiki_mandatory, wiki_extra},
#               per_domain_min (optional, default {30,20,15})}
# ============================================================

TASKS = {}


# ----- Domain 5: Finance & investing (3) -----

TASKS["dr_cross_deep_0013"] = {
    "intent": (
        "Produce a Comparison report on three starter investing approaches under a $10,000 first-year portfolio: "
        "(P1) Passive index ETFs (S&P 500 / Total Market / Bond aggregate), "
        "(P2) Target-date / robo-advisor managed (Betterment / Wealthfront / Vanguard target-date fund), "
        "(P3) Active stock-picking (DIY through Fidelity / Schwab / E*TRADE), "
        "across 5 dimensions: (D1) expected return / volatility, (D2) annual cost incl. expense ratio + advisory fee, "
        "(D3) tax efficiency, (D4) time required per month, (D5) behavioural risk (panic-sell during crash). "
        "Ground in >= 120 sandbox URLs and cite >= 60. "
        "(A) `__SHOPPING__` >= 12 product pages on personal finance books / calculators / planners + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/personalfinance, /f/investing, /f/Bogleheads, /f/financialindependence, /f/wallstreetbets, /f/stocks. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Index fund, Exchange-traded fund, Modern portfolio theory, Sharpe ratio, Expense ratio, Tax-loss harvesting, Robo-advisor, Behavioral finance, Dollar cost averaging, S&P 500. "
        "Output a 3 x 5 matrix rated {best/acceptable/poor} with cited evidence per cell. End with 'who should pick which path' (3 user persona paragraphs). NO TOP-10. "
        "Format: markdown links only. Sandbox URLs only."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=personal+finance+book",
    "synthesis_extra": {
        "task_type": "comparison", "comparison_paths": ["passive_index", "robo_target", "active_diy"],
        "use_cases": ["return_volatility", "annual_cost", "tax_efficiency", "time_required", "behavioural_risk"],
        "matrix_cells_required": 15, "min_evidence_per_cell": {"shopping": 1, "reddit": 1, "wikipedia": 1},
        "explicitly_forbid_top10": True,
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["personal finance book", "investing book", "calculator", "money planner", "budget book",
                              "financial planner", "investing for beginners", "money management", "stock market book"],
        "reddit_forums": ["personalfinance", "investing", "Bogleheads", "financialindependence", "wallstreetbets",
                          "stocks", "AskReddit", "Frugal"],
        "reddit_keywords": ["index fund", "ETF", "robo-advisor", "Betterment", "401k", "Roth IRA", "expense ratio",
                            "Vanguard", "S&P 500"],
        "wiki_mandatory": ["Index fund", "Exchange-traded fund", "Modern portfolio theory", "Sharpe ratio",
                           "Expense ratio", "Tax-loss harvesting", "Robo-advisor", "Behavioral finance",
                           "Dollar cost averaging", "S&P 500"],
        "wiki_extra": ["Stock market", "Bond (finance)", "Mutual fund", "Asset allocation", "Diversification (finance)",
                       "Capital asset pricing model", "Efficient-market hypothesis", "Risk-adjusted return on capital",
                       "Vanguard Group", "Fidelity Investments", "Charles Schwab Corporation", "Wealthfront",
                       "Betterment (company)", "Roth IRA", "401(k)", "Tax-advantaged investing", "Bear market",
                       "Day trading", "Active management", "Passive management"],
    },
    "checklist": [
        "Are exactly 3 investing paths defined (passive index / robo target / active DIY) and labelled P1/P2/P3?",
        "Are exactly 5 dimensions enumerated (return-volatility / cost / tax-efficiency / time / behavioural-risk)?",
        "Does each path list >= 12 shopping items (books/calculators/planners) with URL + price + rating?",
        "Does the report present a 3 x 5 matrix with all 15 cells rated {best, acceptable, poor}?",
        "Does each cell cite >= 1 shopping + >= 1 reddit + >= 1 wiki URL?",
        "Are >= 30 reddit threads cited from at least 4 personal-finance/investing sub-forums?",
        "Is each reddit thread classified by topic role (advice / experience / debate / data)?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles (Index fund, ETF, MPT, Sharpe, Expense ratio, Tax-loss harvesting, Robo-advisor, Behavioral finance, DCA, S&P 500) cited?",
        "Does the report contain explicit annual-cost numbers (expense ratio %, advisory fee bps) for each path?",
        "Does the report quantify expected return / volatility (e.g. 7-10% annualized, 15-20% std)?",
        "Are 3 user-persona paragraphs included (one per path) explaining who should pick that path?",
        "Does each persona paragraph cite >= 5 reddit threads?",
        "Are at least 3 cross-source contradictions surfaced (marketing claim vs reddit reality vs wiki theory)?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited in total?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid producing a TOP-10 recommendation list?",
        "Does the report avoid chain-of-thought and start directly with the comparison content?",
        "Does the report explicitly cite expense-ratio data with shopping or wiki URL evidence?",
    ],
}

TASKS["dr_cross_deep_0014"] = {
    "intent": (
        "Produce a Recommendation report on choosing a brokerage / robo-advisor for a new investor with $5,000 to deploy, "
        "constrained by (C1) zero commission on US stocks/ETFs, (C2) fractional shares supported, "
        "(C3) tax-loss harvesting available, (C4) accessible app + research tools. "
        "Compare AT LEAST 4 platforms (e.g. Fidelity, Schwab, E*TRADE, Vanguard, Betterment, Wealthfront, Robinhood, Public, M1 Finance), "
        "each scored on the 4 constraints, and produce a final TOP-4 ranked recommendation. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 12 product pages on investing books, calculators, planners + price. "
        "(B) `__REDDIT__` >= 30 threads from /f/personalfinance, /f/investing, /f/Bogleheads, /f/financialindependence, /f/RobinHood, /f/M1Finance, /f/wealthfront covering platform comparisons. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Brokerage firm, Online brokerage, Discount broker, Robo-advisor, Fractional share, Tax-loss harvesting, Commission (remuneration), Robinhood Markets, Charles Schwab Corporation, Vanguard Group. "
        "Output a 4-platform x 4-constraint scoring table + final TOP-4 list with full evidence chain (>= 1 shopping + >= 2 reddit + >= 1 wiki per pick). "
        "Format: markdown links only. No fabrication. Begin with scoring table."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=investing+book",
    "synthesis_extra": {
        "task_type": "recommendation", "platforms_min": 4,
        "constraints": ["zero_commission", "fractional_shares", "tax_loss_harvesting", "app_quality"],
        "scoring_table_dimensions": [4, 4], "top_n": 4,
        "min_evidence_per_pick": {"shopping": 1, "reddit": 2, "wikipedia": 1},
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["investing book", "calculator", "planner", "stock book", "trading book",
                              "money management", "personal finance", "investment guide", "trading journal"],
        "reddit_forums": ["personalfinance", "investing", "Bogleheads", "financialindependence", "RobinHood",
                          "M1Finance", "wealthfront", "Fidelity"],
        "reddit_keywords": ["robo-advisor", "Robinhood", "fractional share", "tax-loss harvesting", "Fidelity",
                            "Schwab", "Vanguard", "Betterment"],
        "wiki_mandatory": ["Brokerage firm", "Online brokerage", "Discount broker", "Robo-advisor",
                           "Fractional share", "Tax-loss harvesting", "Commission (remuneration)",
                           "Robinhood Markets", "Charles Schwab Corporation", "Vanguard Group"],
        "wiki_extra": ["E-Trade", "TD Ameritrade", "Wealthfront", "Betterment (company)", "M1 Finance",
                       "Public.com", "Webull", "Stock", "Exchange-traded fund", "Index fund",
                       "Securities Investor Protection Corporation", "Financial Industry Regulatory Authority",
                       "Day trading", "Margin (finance)", "Short selling", "Order (exchange)", "Limit order",
                       "Market order", "Bid–ask spread", "Payment for order flow"],
    },
    "checklist": [
        "Are >= 4 brokerage / robo-advisor platforms enumerated and named?",
        "Are exactly 4 constraints used as scoring axes (zero-commission / fractional / TLH / app-quality)?",
        "Is a platform x constraint scoring table presented with >= 16 cells?",
        "Does each scoring cell cite a sandbox URL as evidence?",
        "Does the report produce a final TOP-4 ranked list?",
        "Does each TOP-4 pick include >= 1 shopping + >= 2 reddit + >= 1 wiki URL evidence chain?",
        "Are >= 12 shopping product pages enumerated with price + rating?",
        "Are >= 30 reddit threads from at least 4 personal-finance/investing sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles (Brokerage firm, Online brokerage, Discount broker, Robo-advisor, Fractional share, Tax-loss harvesting, Commission, Robinhood, Schwab, Vanguard) cited?",
        "Does the report disclose Payment-For-Order-Flow risk for any commission-free platform?",
        "Are at least 3 cross-source divergences surfaced (marketing claim vs reddit reality)?",
        "Are reddit thread classifications (praise / complaint / advice / question) included?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid chain-of-thought and start with the scoring table?",
        "Does the report distinguish robo-advisors from self-directed brokerages?",
        "Does the report cite minimum-investment thresholds for each platform?",
        "Does the report cite the SIPC insurance status of each platform?",
    ],
}

TASKS["dr_cross_deep_0015"] = {
    "intent": (
        "Produce a Debunking / Causal report auditing 5 popular FIRE (Financial Independence, Retire Early) claims: "
        "(CL1) 'You can retire on $1M at age 45 with the 4% safe withdrawal rate (SWR)', "
        "(CL2) 'Geographic arbitrage to Thailand or Mexico cuts cost-of-living by 70%', "
        "(CL3) 'Real-estate house-hacking is faster than index investing for FIRE', "
        "(CL4) 'Healthcare cost is the #1 FIRE blocker pre-Medicare', "
        "(CL5) 'Sequence-of-returns risk is overstated by Bogleheads'. "
        "Each claim gets a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED} backed by triple evidence. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 books on retirement / FIRE / passive income + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/financialindependence, /f/Fire, /f/leanfire, /f/fatFIRE, /f/personalfinance, /f/Bogleheads. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Trinity study, Safe withdrawal rate, Financial independence, FIRE movement, Sequence-of-returns risk, Geographic arbitrage, Health insurance in the United States, Real estate investing, Passive income, Withdrawal Plan. "
        "Output a 5-claim verdict table + 'sequence-of-returns risk' dose-response analysis + final 'FIRE realism cheat-sheet' (<= 8 bullets, each cited). "
        "Format: markdown links only. Begin with verdict table."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=retirement+book",
    "synthesis_extra": {
        "task_type": "debunking", "claim_count": 5,
        "claim_ids": ["four_pct_swr", "geo_arbitrage", "house_hacking", "healthcare_blocker", "sor_risk"],
        "verdict_levels": ["SUPPORTED", "PARTIALLY_SUPPORTED", "DEBUNKED", "UNDETERMINED"],
        "min_evidence_per_claim": {"shopping_with_verbatim_quote": 1, "reddit": 1, "wikipedia": 1, "reasoning_paragraphs": 1},
        "dose_response_findings": ["sor_risk"],
        "sleep_hygiene_checklist_count": [6, 8],
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["retirement book", "FIRE book", "passive income book", "real estate investing",
                              "financial freedom", "early retirement", "money book", "wealth building", "mr money mustache"],
        "reddit_forums": ["financialindependence", "Fire", "leanfire", "fatFIRE", "personalfinance",
                          "Bogleheads", "investing", "ChubbyFIRE"],
        "reddit_keywords": ["safe withdrawal rate", "4% rule", "Trinity study", "geo arbitrage", "FIRE",
                            "house hacking", "early retirement", "sequence of returns"],
        "wiki_mandatory": ["Trinity study", "Safe withdrawal rate", "Financial independence", "FIRE movement",
                           "Sequence-of-returns risk", "Geographic arbitrage", "Health insurance in the United States",
                           "Real estate investing", "Passive income", "Withdrawal Plan"],
        "wiki_extra": ["Pension", "Social Security (United States)", "Medicare (United States)",
                       "Affordable Care Act", "Cost of living", "Inflation", "Compound interest",
                       "Mr. Money Mustache", "Vicki Robin", "Your Money or Your Life", "Asset allocation",
                       "Bond ladder", "Annuity", "Stock", "Index fund", "Property tax",
                       "Capital gains tax in the United States", "Internal Revenue Code section 72(t)",
                       "Required minimum distribution", "Retirement planning"],
    },
    "checklist": [
        "Are exactly 5 FIRE claims defined (4% SWR / geo arbitrage / house hacking / healthcare blocker / SoR risk)?",
        "Does each claim receive a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}?",
        "For each claim, is there a shopping URL with the verbatim claim quote (e.g. book chapter title)?",
        "For each claim, is there >= 1 reddit URL with practitioner experience?",
        "For each claim, is there >= 1 wiki URL with the underlying mathematical or empirical basis?",
        "Does each claim include a 1-paragraph reasoning?",
        "Are >= 10 shopping product pages (FIRE / retirement books) enumerated with price + rating?",
        "Are >= 30 reddit threads from at least 4 FIRE-related sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles (Trinity study, SWR, FI, FIRE movement, SoR risk, Geo arbitrage, US health insurance, REI, Passive income, Withdrawal Plan) cited?",
        "Is a sequence-of-returns risk dose-response section included with quantitative analysis?",
        "Does the SoR section cite both wiki definitions AND reddit historical-failure-case discussions?",
        "Is a 6-8 bullet 'FIRE realism cheat-sheet' included?",
        "Does each cheat-sheet bullet describe a non-product action (savings rate, tax strategy, work-life)?",
        "Does each cheat-sheet bullet cite >= 1 wiki URL?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Are at least 2 of the 5 verdicts DEBUNKED, PARTIALLY_SUPPORTED, or UNDETERMINED?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Does the report avoid chain-of-thought and start with the verdict table?",
    ],
}


# ----- Domain 6: Law & policy (3) -----

TASKS["dr_cross_deep_0016"] = {
    "intent": (
        "Produce a Comparison report on tenant rights in 3 US states — California, New York, Texas — across 5 dimensions: "
        "(D1) eviction notice period, (D2) security deposit cap + interest requirement, (D3) repair-and-deduct entitlement, "
        "(D4) rent-control coverage / annual cap, (D5) lease-break penalty for early termination. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 books on tenant law / landlord-tenant guides + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/legaladvice, /f/AskLawyers, /f/LosAngeles, /f/NewYorkCity, /f/Austin, /f/Tenant, /f/RealEstate. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Landlord-tenant law, Eviction, Security deposit, Rent control, Rent control in California, Rent control in New York, Texas Property Code, Lease, Implied warranty of habitability, Statute of limitations. "
        "Output a 3 (state) x 5 (dimension) matrix with cited evidence per cell + 'where to lawyer up' section listing 3 specific legal-aid resources per state. "
        "Format: markdown links only. Begin with comparison matrix."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=tenant+law+book",
    "synthesis_extra": {
        "task_type": "comparison", "comparison_paths": ["california", "new_york", "texas"],
        "use_cases": ["eviction_notice", "security_deposit", "repair_deduct", "rent_control", "lease_break"],
        "matrix_cells_required": 15, "min_evidence_per_cell": {"shopping": 1, "reddit": 1, "wikipedia": 1},
        "legal_aid_resources_per_state": 3,
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["tenant law", "landlord tenant", "renting book", "lease guide", "real estate law",
                              "eviction book", "rental property", "law book", "legal handbook"],
        "reddit_forums": ["legaladvice", "AskLawyers", "LosAngeles", "NewYorkCity", "Austin",
                          "Tenant", "RealEstate", "Apartments"],
        "reddit_keywords": ["eviction", "security deposit", "rent control", "lease", "landlord",
                            "repair deduct", "tenant rights", "lease break"],
        "wiki_mandatory": ["Landlord-tenant law", "Eviction", "Security deposit", "Rent control",
                           "Rent control in California", "Rent control in New York", "Texas Property Code",
                           "Lease", "Implied warranty of habitability", "Statute of limitations"],
        "wiki_extra": ["Property law", "Real estate", "California Civil Code", "New York Real Property Law",
                       "Section 8 (housing)", "Fair Housing Act", "Eviction in the United States",
                       "Rent regulation", "Just-cause eviction", "Holdover tenant", "Constructive eviction",
                       "Quiet enjoyment", "Premises liability", "Lease purchase contract", "Sublease",
                       "Renters' insurance", "Squatting", "Tenant screening", "Property management", "Slumlord"],
    },
    "checklist": [
        "Are exactly 3 states defined (CA / NY / TX)?",
        "Are exactly 5 dimensions enumerated (eviction notice / deposit / repair-deduct / rent-control / lease-break)?",
        "Is a 3 x 5 comparison matrix presented with all 15 cells populated?",
        "Does each cell cite a state-specific statute or a wiki URL?",
        "Does each cell cite >= 1 reddit thread with a real tenant-renter case?",
        "Does each cell cite >= 1 shopping product (book) URL?",
        "Are >= 10 shopping product pages enumerated with price + rating?",
        "Are >= 30 reddit threads cited from at least 4 legal/state sub-forums?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles (Landlord-tenant law, Eviction, Security deposit, Rent control, RC-CA, RC-NY, TX Property Code, Lease, Implied warranty of habitability, SoL) cited?",
        "Are exactly 3 legal-aid resources listed per state (9 total)?",
        "Does each legal-aid resource cite a wiki or reddit URL?",
        "Does the matrix explicitly cite state statute names (e.g. CA CIV § 1950.5)?",
        "Are at least 3 cross-state divergences highlighted (e.g. CA 60-day notice vs TX 3-day)?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid generic Top-N format?",
        "Does the report avoid chain-of-thought and start with the matrix?",
        "Does the report explicitly disclaim 'not legal advice; consult attorney'?",
    ],
}

TASKS["dr_cross_deep_0017"] = {
    "intent": (
        "Produce an Enumeration / Catalog report cataloguing every GDPR data subject right (Articles 15-22) "
        "with: (a) the right's name, (b) what it lets the user demand, (c) the legal text reference, "
        "(d) typical company response time, (e) penalty for non-compliance. "
        "Then add a 'how to actually invoke each right' template section with sample request letters. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 books on GDPR / privacy law / data protection + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/europe, /f/privacy, /f/legaladvice, /f/eupersonalfinance, /f/GDPR, /f/dataisbeautiful covering real GDPR-request experience. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: General Data Protection Regulation, Right to be forgotten, Data portability, Data subject access request, Personal data, Information privacy, Schrems II, Privacy Shield, EU Data Protection Directive, ePrivacy Directive. "
        "Output a 8-row catalog table (one per GDPR right) + 'sample request letter templates' section (3 templates: erasure, access, portability). "
        "Format: markdown links only. Begin with catalog table."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=GDPR+book",
    "synthesis_extra": {
        "task_type": "enumeration", "rights_min": 8,
        "catalog_columns": ["name", "demand", "legal_ref", "response_time", "penalty"],
        "min_evidence_per_right": {"shopping": 1, "reddit": 1, "wikipedia": 1},
        "request_letter_templates": 3,
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["GDPR book", "privacy law", "data protection", "European law",
                              "consumer rights", "internet privacy", "law book", "compliance handbook", "legal guide"],
        "reddit_forums": ["europe", "privacy", "legaladvice", "eupersonalfinance", "GDPR",
                          "dataisbeautiful", "AskEurope", "Programming"],
        "reddit_keywords": ["GDPR", "data subject", "right to be forgotten", "DSAR", "privacy",
                            "consent", "Schrems", "data breach"],
        "wiki_mandatory": ["General Data Protection Regulation", "Right to be forgotten", "Data portability",
                           "Data subject access request", "Personal data", "Information privacy",
                           "Schrems II", "Privacy Shield", "EU Data Protection Directive", "ePrivacy Directive"],
        "wiki_extra": ["Data Protection Officer", "Article 29 Working Party", "European Data Protection Board",
                       "Data breach", "Data Protection Impact Assessment", "Pseudonymization", "Anonymization",
                       "Cookie (computing)", "Behavioral targeting", "Adtech", "California Consumer Privacy Act",
                       "Personal Information Protection Law of the People's Republic of China", "Convention 108",
                       "European Court of Justice", "Court of Justice of the European Union",
                       "Information Commissioner's Office", "CNIL", "Bundesdatenschutzgesetz",
                       "Web tracking", "Privacy by design"],
    },
    "checklist": [
        "Are >= 8 GDPR data-subject rights catalogued (Articles 15-22)?",
        "Does the catalog have >= 5 columns (name / demand / legal-ref / response-time / penalty)?",
        "Does each row cite the GDPR article number (e.g. Art. 17 RTBF)?",
        "Does each row cite >= 1 wiki URL?",
        "Does each row cite >= 1 reddit URL with practitioner experience?",
        "Does each row cite >= 1 shopping URL (book / handbook reference)?",
        "Are exactly 3 sample request letter templates included (erasure / access / portability)?",
        "Does each template cite a wiki article for legal basis?",
        "Are >= 10 shopping product pages enumerated with price + rating?",
        "Are >= 30 reddit threads from at least 4 EU/privacy sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles (GDPR, RTBF, Data portability, DSAR, Personal data, Info privacy, Schrems II, Privacy Shield, EU DP Directive, ePrivacy) cited?",
        "Does the report cite penalty examples (e.g. 4% global revenue or €20M, whichever higher)?",
        "Are at least 3 real-world GDPR enforcement cases cited (e.g. Google, Amazon)?",
        "Does the report distinguish controllers from processors?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid producing a TOP-10 list?",
        "Does the report explicitly cover non-EU residents' rights when their data is processed by EU companies?",
    ],
}

TASKS["dr_cross_deep_0018"] = {
    "intent": (
        "Produce an Enumeration / Catalog report cataloguing every common US work visa category, with: "
        "(a) visa code (H-1B / O-1 / L-1 / E-3 / TN / J-1 / etc.), (b) eligibility criteria, "
        "(c) annual cap + lottery odds (if applicable), (d) processing time + premium-processing option, "
        "(e) employer petition requirements + cost, (f) path to permanent residency. "
        "Cover at minimum 8 visa categories. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 books on US immigration / visa guides / job hunting + price. "
        "(B) `__REDDIT__` >= 30 threads from /f/h1b, /f/USCIS, /f/immigration, /f/cscareerquestions, /f/USPersonalFinance, /f/AskReddit. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: H-1B visa, O-1 visa, L-1 visa, E-3 visa, TN visa, J-1 visa, F-1 visa, EB-5 visa, United States Citizenship and Immigration Services, Immigration and Nationality Act of 1965. "
        "Output a 8-row catalog table with all 6 columns + 'visa-to-green-card decision tree' section showing typical timelines. "
        "Format: markdown links only. Begin with catalog table."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=immigration+book",
    "synthesis_extra": {
        "task_type": "enumeration", "visas_min": 8,
        "catalog_columns": ["code", "eligibility", "annual_cap", "processing_time", "employer_cost", "gc_path"],
        "min_evidence_per_visa": {"shopping": 1, "reddit": 1, "wikipedia": 1},
        "decision_tree_required": True,
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["immigration book", "visa guide", "US visa", "work permit",
                              "green card", "h1b book", "career guide", "law book", "moving abroad"],
        "reddit_forums": ["h1b", "USCIS", "immigration", "cscareerquestions", "USPersonalFinance",
                          "AskReddit", "AskAnAmerican", "ABoringDystopia"],
        "reddit_keywords": ["H-1B", "O-1", "L-1", "green card", "visa", "USCIS",
                            "lottery", "premium processing"],
        "wiki_mandatory": ["H-1B visa", "O-1 visa", "L-1 visa", "E-3 visa", "TN visa",
                           "J-1 visa", "F-1 visa", "EB-5 visa",
                           "United States Citizenship and Immigration Services",
                           "Immigration and Nationality Act of 1965"],
        "wiki_extra": ["Optional Practical Training", "STEM OPT", "Green card", "Adjustment of status",
                       "Premium Processing Service", "Labor Condition Application", "PERM",
                       "EB-1 visa", "EB-2 visa", "EB-3 visa", "Diversity Immigrant Visa",
                       "Visa Waiver Program", "Form I-129", "Form I-140", "Form I-485",
                       "Department of Labor (US)", "Department of State (US)",
                       "Specialty occupation", "Beneficiary (immigration)", "Sponsor (immigration)"],
    },
    "checklist": [
        "Are >= 8 US work visa categories catalogued (H-1B/O-1/L-1/E-3/TN/J-1/F-1/EB-5)?",
        "Does the catalog table have >= 6 columns (code/eligibility/cap/processing/employer-cost/GC-path)?",
        "Is the H-1B annual cap (65,000 + 20,000 master's) explicitly cited?",
        "Are H-1B lottery odds (recent year, e.g. ~25%) cited from reddit or wiki?",
        "Are processing-time numbers cited per visa with USCIS or wiki source?",
        "Does each visa row cite >= 1 wiki URL?",
        "Does each row cite >= 1 reddit URL with applicant experience?",
        "Does each row cite >= 1 shopping URL (book or guide)?",
        "Are >= 10 shopping product pages enumerated with price + rating?",
        "Are >= 30 reddit threads from at least 4 immigration / career sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited?",
        "Is a visa-to-green-card decision tree section included with typical timelines?",
        "Does the decision tree distinguish employment-based vs family-based GC paths?",
        "Are at least 2 cross-source contradictions surfaced (e.g. processing-time marketing vs reddit reality)?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid TOP-N format and avoid chain-of-thought?",
        "Does the report explicitly disclaim 'not legal advice; consult immigration attorney'?",
    ],
}


# ----- Domain 7: Travel (3) -----

TASKS["dr_cross_deep_0019"] = {
    "intent": (
        "Produce a Comparison report on visa-free destinations for 4 passport tiers — (P1) US, (P2) UK, (P3) Japan, (P4) Singapore — "
        "across 5 destination categories: (D1) Schengen Europe, (D2) East Asia, (D3) Southeast Asia, (D4) Latin America, (D5) Africa. "
        "Each cell = number of visa-free destinations + max stay duration + any visa-on-arrival exceptions. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 travel guides / passport holders / luggage + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/travel, /f/digitalnomad, /f/onebag, /f/IWantOut, /f/expats, /f/JapanTravel, /f/solotravel. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Visa policy of the United States, Visa policy of Japan, Visa policy of Singapore, Visa policy of the United Kingdom, Henley Passport Index, Schengen Area, Visa on arrival, Electronic travel authorization, Travel visa, Visa-free entry. "
        "Output a 4 (passport) x 5 (region) matrix + 'best passport for digital nomads' analysis. "
        "Format: markdown links only. Begin with matrix."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=travel+guide",
    "synthesis_extra": {
        "task_type": "comparison", "comparison_paths": ["us", "uk", "jp", "sg"],
        "use_cases": ["schengen", "east_asia", "se_asia", "latin_america", "africa"],
        "matrix_cells_required": 20, "min_evidence_per_cell": {"shopping": 1, "reddit": 1, "wikipedia": 1},
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["travel guide", "passport holder", "luggage", "carry on", "travel adapter",
                              "backpack", "travel book", "world travel", "lonely planet"],
        "reddit_forums": ["travel", "digitalnomad", "onebag", "IWantOut", "expats", "JapanTravel",
                          "solotravel", "TravelHacks"],
        "reddit_keywords": ["visa-free", "passport", "Schengen", "digital nomad", "border crossing",
                            "visa on arrival", "ETA", "travel"],
        "wiki_mandatory": ["Visa policy of the United States", "Visa policy of Japan", "Visa policy of Singapore",
                           "Visa policy of the United Kingdom", "Henley Passport Index", "Schengen Area",
                           "Visa on arrival", "Electronic travel authorization", "Travel visa", "Visa-free entry"],
        "wiki_extra": ["Passport", "Biometric passport", "Visa requirements for United States citizens",
                       "Visa requirements for Japanese citizens", "Visa requirements for Singaporean citizens",
                       "Visa requirements for British citizens", "ESTA", "ETIAS", "eTA (Canada)",
                       "Visa Waiver Program", "Schengen Visa Information System", "European Union",
                       "ASEAN", "MERCOSUR", "African Union", "Common Travel Area",
                       "Free movement of workers", "Permanent residency", "Citizenship by investment", "Diplomatic passport"],
    },
    "checklist": [
        "Are exactly 4 passport tiers compared (US / UK / JP / SG)?",
        "Are exactly 5 destination regions enumerated (Schengen / E. Asia / SE Asia / Latin America / Africa)?",
        "Is a 4 x 5 matrix presented with all 20 cells populated?",
        "Does each cell cite a wiki URL with the specific visa policy?",
        "Does each cell cite >= 1 reddit URL with traveller experience?",
        "Does each cell cite >= 1 shopping URL (travel-related product)?",
        "Are visa-free destination COUNTS explicitly cited per cell?",
        "Are max stay durations (e.g. 90 days) cited per cell?",
        "Is at least one visa-on-arrival exception flagged per region?",
        "Are >= 10 shopping product pages enumerated with price + rating?",
        "Are >= 30 reddit threads from at least 4 travel sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited?",
        "Is a 'best passport for digital nomads' analysis section included?",
        "Does the analysis cite the Henley Passport Index?",
        "Are at least 3 cross-source divergences surfaced (e.g. official policy vs reddit border-crossing reality)?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid chain-of-thought and start with the matrix?",
    ],
}

TASKS["dr_cross_deep_0020"] = {
    "intent": (
        "Produce a Debunking report auditing 5 popular jet-lag remedies: "
        "(CL1) 'Melatonin 5 mg taken at destination bedtime cures eastward jet lag', "
        "(CL2) 'Pre-trip fasting (Argonne diet) shifts circadian rhythm faster', "
        "(CL3) 'Bright-light therapy lamps work as well as sunlight for resetting', "
        "(CL4) 'Bilberry / blueberry extract supplements reduce jet-lag fatigue', "
        "(CL5) 'Sleep eye masks + noise-cancelling headphones halve adjustment days'. "
        "Each gets a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 jet-lag remedy products (melatonin, light lamps, masks, headphones) + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/travel, /f/sleep, /f/jetlag, /f/digitalnomad, /f/onebag, /f/Supplements. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Jet lag, Circadian rhythm, Melatonin, Light therapy, Suprachiasmatic nucleus, Sleep, Adenosine, Sleep onset latency, Phototherapy, Argonne anti-jet-lag diet. "
        "Output a 5-claim verdict table + 'eastward vs westward asymmetry' analysis + 'pre/during/post flight protocol' (<= 8 bullets). "
        "Format: markdown links only. Begin with verdict table."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=melatonin",
    "synthesis_extra": {
        "task_type": "debunking", "claim_count": 5,
        "claim_ids": ["melatonin_destination", "argonne_fasting", "light_therapy_lamp", "bilberry_extract", "mask_headphones"],
        "verdict_levels": ["SUPPORTED", "PARTIALLY_SUPPORTED", "DEBUNKED", "UNDETERMINED"],
        "min_evidence_per_claim": {"shopping_with_verbatim_quote": 1, "reddit": 1, "wikipedia": 1, "reasoning_paragraphs": 1},
        "asymmetry_analysis_required": True, "protocol_bullets": [6, 8],
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["melatonin", "light therapy", "sleep mask", "noise cancelling headphones",
                              "travel pillow", "jet lag", "sleep aid", "blue light glasses", "supplement"],
        "reddit_forums": ["travel", "sleep", "jetlag", "digitalnomad", "onebag",
                          "Supplements", "Biohackers", "AskScience"],
        "reddit_keywords": ["jet lag", "melatonin", "circadian", "light therapy", "fasting",
                            "Argonne diet", "sleep mask", "blue light"],
        "wiki_mandatory": ["Jet lag", "Circadian rhythm", "Melatonin", "Light therapy",
                           "Suprachiasmatic nucleus", "Sleep", "Adenosine", "Sleep onset latency",
                           "Phototherapy", "Argonne anti-jet-lag diet"],
        "wiki_extra": ["Sleep stages", "Rapid eye movement sleep", "Slow-wave sleep", "Sleep deprivation",
                       "Sleep medicine", "Pineal gland", "Cortisol", "Insomnia", "Caffeine",
                       "Modafinil", "Bilberry", "Vaccinium", "Polyphenol", "Antioxidant",
                       "Eye mask (sleep)", "Earplug", "Time zone", "Travel medicine",
                       "Phase response curve", "Light's effect on circadian rhythm"],
    },
    "checklist": [
        "Are exactly 5 jet-lag claims defined (melatonin / Argonne / light lamp / bilberry / mask-HP)?",
        "Does each claim receive a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}?",
        "For each claim, is there a shopping URL with verbatim marketing quote?",
        "For each claim, is there >= 1 reddit URL with traveller experience?",
        "For each claim, is there >= 1 wiki URL with circadian-biology grounding?",
        "Does each claim include a 1-paragraph reasoning?",
        "Are >= 10 shopping product pages enumerated with price + rating?",
        "Are >= 30 reddit threads from at least 4 travel/sleep/biohacker sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited (Jet lag, Circadian, Melatonin, Light therapy, SCN, Sleep, Adenosine, SOL, Phototherapy, Argonne diet)?",
        "Is an 'eastward vs westward asymmetry' analysis section included with PRC chart reference?",
        "Does the asymmetry section cite phase-response-curve evidence (wiki + reddit)?",
        "Is a 6-8 bullet 'pre/during/post flight protocol' included?",
        "Does each protocol bullet cite >= 1 wiki URL?",
        "Are at least 2 of the 5 verdicts DEBUNKED, PARTIALLY_SUPPORTED, or UNDETERMINED?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid TOP-N format and chain-of-thought?",
        "Does the report cite at least one peer-reviewed study via wiki citation?",
    ],
}

TASKS["dr_cross_deep_0021"] = {
    "intent": (
        "Produce a Comparison report on 4 popular digital-nomad tax / residency programs: "
        "(P1) Estonia e-Residency + 0% on undistributed corporate profit, "
        "(P2) Portugal Non-Habitual Resident (NHR) program, "
        "(P3) UAE freezone company + 9% corporate tax (post-2023), "
        "(P4) Thailand LTR (Long-Term Resident) visa, "
        "across 5 dimensions: (D1) setup cost + time, (D2) effective annual tax, (D3) physical-presence requirement, "
        "(D4) banking accessibility for remote workers, (D5) renewal / long-term outlook. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 books on remote work / digital nomad / international tax + price. "
        "(B) `__REDDIT__` >= 30 threads from /f/digitalnomad, /f/IWantOut, /f/eupersonalfinance, /f/expats, /f/PortugalExpats, /f/dubai, /f/Thailand. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: E-Residency of Estonia, Non-Habitual Resident, Free-trade zone, Thailand LTR Visa, Digital nomad, Tax residence, Permanent establishment, Double taxation, OECD Common Reporting Standard, Foreign Earned Income Exclusion. "
        "Output a 4 x 5 matrix + 'red flags' section listing at least 5 due-diligence pitfalls. "
        "Format: markdown links only. Begin with matrix."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=remote+work+book",
    "synthesis_extra": {
        "task_type": "comparison", "comparison_paths": ["estonia_e_residency", "portugal_nhr", "uae_freezone", "thailand_ltr"],
        "use_cases": ["setup_cost_time", "effective_tax", "physical_presence", "banking", "renewal_outlook"],
        "matrix_cells_required": 20, "min_evidence_per_cell": {"shopping": 1, "reddit": 1, "wikipedia": 1},
        "red_flags_min": 5,
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["remote work book", "digital nomad", "international tax",
                              "global business", "expat book", "freelance guide", "world traveler",
                              "starting business", "tax book"],
        "reddit_forums": ["digitalnomad", "IWantOut", "eupersonalfinance", "expats", "PortugalExpats",
                          "dubai", "Thailand", "ChubbyFIRE"],
        "reddit_keywords": ["e-residency", "Estonia", "NHR", "Portugal", "UAE", "Thailand LTR",
                            "tax residency", "digital nomad visa"],
        "wiki_mandatory": ["E-Residency of Estonia", "Non-Habitual Resident", "Free-trade zone",
                           "Thailand LTR Visa", "Digital nomad", "Tax residence",
                           "Permanent establishment", "Double taxation",
                           "OECD Common Reporting Standard", "Foreign Earned Income Exclusion"],
        "wiki_extra": ["Estonia", "Portugal", "United Arab Emirates", "Thailand",
                       "Tax haven", "Offshore company", "Limited liability company",
                       "Personal income tax", "Corporate tax", "Value-added tax",
                       "Taxation of digital goods", "Remote work", "Coworking", "Schengen Area",
                       "Tax treaty", "Bilateral investment treaty", "Foreign Account Tax Compliance Act",
                       "Wise (company)", "Revolut", "International banking"],
    },
    "checklist": [
        "Are exactly 4 nomad tax/residency programs compared (Estonia / Portugal / UAE / Thailand)?",
        "Are exactly 5 dimensions enumerated (setup / tax / presence / banking / renewal)?",
        "Is a 4 x 5 matrix presented with all 20 cells populated?",
        "Does each cell cite >= 1 wiki URL with the legal basis?",
        "Does each cell cite >= 1 reddit URL with practitioner experience?",
        "Does each cell cite >= 1 shopping URL (book / guide)?",
        "Does each program row cite explicit setup-cost numbers (€/USD)?",
        "Does each program row cite effective-tax-rate numbers (%)?",
        "Does each program disclose physical-presence-day requirement?",
        "Are >= 10 shopping product pages enumerated with price + rating?",
        "Are >= 30 reddit threads from at least 4 nomad/expat sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited?",
        "Are >= 5 'red flag' pitfalls listed in a dedicated section?",
        "Does each red-flag cite >= 1 wiki URL (legal basis) + >= 1 reddit URL (real case)?",
        "Does the report explicitly discuss CRS reporting impact on each jurisdiction?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report disclaim 'not tax advice; consult international tax attorney'?",
    ],
}


# ----- Domain 8: Education & career (3) -----

TASKS["dr_cross_deep_0022"] = {
    "intent": (
        "Produce a Comparison report on 4 paths to a software-engineering job from scratch in 12-18 months: "
        "(P1) 12-week intensive coding bootcamp ($15-20k), (P2) 4-year CS bachelor's degree ($40-200k), "
        "(P3) self-taught via free / cheap MOOCs (Coursera, freeCodeCamp), "
        "(P4) Apprenticeship / earn-as-you-learn programs (Multiverse, Microverse, etc.), "
        "across 5 dimensions: (D1) total cost, (D2) median time-to-first-job, (D3) reported placement rate (CIRR-audited if possible), "
        "(D4) median first-year salary, (D5) hireability at FAANG vs startups vs non-tech-co. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 books on programming / interview prep / career change + price. "
        "(B) `__REDDIT__` >= 30 threads from /f/cscareerquestions, /f/learnprogramming, /f/codingbootcamp, /f/csMajors, /f/ITCareerQuestions. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Coding bootcamp, Computer science, Software engineering, Massive open online course, Apprenticeship, Self-taught, Income share agreement, Cost of attendance, Computer programming, FAANG. "
        "Output a 4 x 5 matrix + 'who should pick which path' (4 user persona paragraphs). NO TOP-N. "
        "Format: markdown links only. Begin with comparison matrix."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=programming+book",
    "synthesis_extra": {
        "task_type": "comparison", "comparison_paths": ["bootcamp", "cs_degree", "self_taught", "apprenticeship"],
        "use_cases": ["total_cost", "time_to_job", "placement_rate", "first_year_salary", "hireability_band"],
        "matrix_cells_required": 20, "min_evidence_per_cell": {"shopping": 1, "reddit": 1, "wikipedia": 1},
        "persona_paragraphs": 4, "min_reddit_per_persona": 5, "explicitly_forbid_top10": True,
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["programming book", "coding interview", "software engineer", "career change",
                              "Python book", "JavaScript book", "data structures", "computer science", "leetcode"],
        "reddit_forums": ["cscareerquestions", "learnprogramming", "codingbootcamp", "csMajors",
                          "ITCareerQuestions", "ExperiencedDevs", "AskComputerScience", "techcareeradvice"],
        "reddit_keywords": ["bootcamp", "self taught", "CS degree", "FAANG", "leetcode",
                            "internship", "junior developer", "career switch"],
        "wiki_mandatory": ["Coding bootcamp", "Computer science", "Software engineering",
                           "Massive open online course", "Apprenticeship", "Self-taught",
                           "Income share agreement", "Cost of attendance",
                           "Computer programming", "FAANG"],
        "wiki_extra": ["Bachelor of Science in Computer Science", "App Academy", "Hack Reactor",
                       "Lambda School", "freeCodeCamp", "Coursera", "edX", "Udacity",
                       "General Assembly (school)", "Multiverse (company)", "Internship",
                       "Job interview", "Algorithm", "Data structure", "GitHub", "Stack Overflow",
                       "Software developer", "Front-end web development", "Back-end web development", "DevOps"],
    },
    "checklist": [
        "Are exactly 4 paths defined (bootcamp / CS degree / self-taught / apprenticeship)?",
        "Are exactly 5 dimensions enumerated (cost / time / placement / salary / hireability)?",
        "Is a 4 x 5 matrix presented with all 20 cells populated?",
        "Does each cell cite >= 1 shopping + >= 1 reddit + >= 1 wiki URL?",
        "Are total-cost ranges cited for each path with $ amounts?",
        "Is median time-to-first-job (months) explicitly stated per path?",
        "Are placement-rate numbers cited (with CIRR audit reference if applicable)?",
        "Are first-year salary numbers cited with reddit or wiki source?",
        "Is FAANG-hireability discussed per path with reddit evidence?",
        "Are >= 10 shopping product pages enumerated with price + rating?",
        "Are >= 30 reddit threads from at least 4 CS-career sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited?",
        "Are 4 user-persona paragraphs included (one per path)?",
        "Does each persona paragraph cite >= 5 reddit threads?",
        "Are at least 3 cross-source contradictions surfaced (marketing claim vs reddit reality)?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid TOP-N format and chain-of-thought?",
    ],
}

TASKS["dr_cross_deep_0023"] = {
    "intent": (
        "Produce a Causal explanation report answering 'Why has US CS PhD enrolment dropped post-2022 despite AI demand?'. "
        "The report must construct a causal chain across 4 layers: "
        "(L1) labour market: industry pay vs academic pay gap (cite Glassdoor / BLS / wiki), "
        "(L2) opportunity cost: 5-7 years of foregone industry comp + AI safety bootcamps as alternative, "
        "(L3) funding shifts: NSF / DARPA grant trends, OpenAI/Anthropic scholarships, "
        "(L4) cultural shift: AI hype attracting researchers to industry labs (DeepMind / FAIR / OAI), publication norms moving to arXiv-first. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 books on academia / grad school / AI research career + price. "
        "(B) `__REDDIT__` >= 30 threads from /f/csMajors, /f/MachineLearning, /f/cscareerquestions, /f/AskAcademia, /f/GradSchool, /f/PhD. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Doctor of Philosophy, Computer science, Postdoctoral researcher, Tenure track, National Science Foundation, DARPA, OpenAI, DeepMind, FAANG, Adjunct professor. "
        "Output a 4-layer causal hierarchy + 'mitigation strategies for departments' section (>= 5 strategies cited). "
        "Format: markdown links only. Begin with L1."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=PhD+book",
    "synthesis_extra": {
        "task_type": "causal", "causal_layers": ["L1_labour_market", "L2_opportunity_cost", "L3_funding_shifts", "L4_cultural_shift"],
        "min_wiki_per_layer": {"L1_labour_market": 3, "L3_funding_shifts": 3},
        "min_reddit_per_layer": {"L2_opportunity_cost": 5, "L4_cultural_shift": 5},
        "mitigation_strategies_min": 5,
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["PhD book", "graduate school", "academic career", "computer science",
                              "research career", "AI book", "machine learning", "thesis writing", "academia"],
        "reddit_forums": ["csMajors", "MachineLearning", "cscareerquestions", "AskAcademia",
                          "GradSchool", "PhD", "Professors", "AcademicTwitter"],
        "reddit_keywords": ["PhD", "tenure track", "industry vs academia", "postdoc",
                            "machine learning", "AI research", "OpenAI", "DeepMind"],
        "wiki_mandatory": ["Doctor of Philosophy", "Computer science", "Postdoctoral researcher",
                           "Tenure track", "National Science Foundation", "DARPA",
                           "OpenAI", "DeepMind", "FAANG", "Adjunct professor"],
        "wiki_extra": ["Anthropic", "Google Brain", "Meta AI", "Microsoft Research",
                       "Massachusetts Institute of Technology", "Stanford University", "Carnegie Mellon University",
                       "ArXiv", "Peer review", "Academic tenure", "Research grant", "Stipend",
                       "Graduate teaching assistant", "Adjunctification", "Faculty development",
                       "Research professor", "Visiting scholar", "Sabbatical", "Conference paper", "NeurIPS"],
    },
    "checklist": [
        "Does the report explicitly answer 'why has CS PhD enrolment dropped post-2022'?",
        "Are exactly 4 causal layers defined (labour-market / opportunity-cost / funding-shifts / cultural-shift)?",
        "Does L1 cite >= 3 wiki articles on labour market / academic-vs-industry pay?",
        "Does L2 cite >= 5 reddit threads on opportunity-cost discussions?",
        "Does L3 cite >= 3 wiki articles on NSF / DARPA / industry-lab funding?",
        "Does L4 cite >= 5 reddit threads on AI hype / arXiv-first culture?",
        "Are >= 30 shopping books on PhD / academic career cited (>= 10 with price)?",
        "Are >= 30 reddit threads from at least 4 CS-grad sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited?",
        "Is a multi-layer causal hierarchy presented in markdown (indented bullets)?",
        "Are >= 5 mitigation strategies for departments enumerated in a dedicated section?",
        "Does each mitigation cite >= 1 reddit + >= 1 wiki URL?",
        "Does the report quantify the enrolment drop with a specific number (e.g. 15% YoY)?",
        "Does the report cite at least one industry-lab researcher's salary range (FAIR/OAI/DeepMind)?",
        "Are at least 3 cross-source divergences surfaced (academic narrative vs reddit reality)?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid TOP-N format and start with L1?",
    ],
}

TASKS["dr_cross_deep_0024"] = {
    "intent": (
        "Produce an Enumeration / Catalog report cataloguing the 3 major cloud certification ladders: "
        "AWS, Google Cloud (GCP), Microsoft Azure. For each provider, enumerate ALL active certifications by tier "
        "(foundational / associate / professional / specialty), with: "
        "(a) cert name, (b) tier, (c) exam fee USD, (d) prep time weeks (typical), "
        "(e) median 1-year salary bump per reddit / industry survey, (f) renewal period. "
        "Cover at least 6 certs per provider = >= 18 certs total. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 books on AWS / GCP / Azure exams + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/AWSCertifications, /f/AZURE, /f/googlecloud, /f/cscareerquestions, /f/devops, /f/ITCareerQuestions. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Amazon Web Services, Microsoft Azure, Google Cloud Platform, Cloud computing, Cloud certification, AWS Certifications, IT certification, Public cloud, Infrastructure as a service, DevOps. "
        "Output a 3-provider grouped catalog table (>= 18 rows) + 'optimal cert path for X role' section (5 roles: SWE / SRE / DevOps / data engineer / security). "
        "Format: markdown links only. Begin with catalog table."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=AWS+book",
    "synthesis_extra": {
        "task_type": "enumeration", "providers": ["AWS", "GCP", "Azure"], "certs_min_per_provider": 6, "certs_min_total": 18,
        "catalog_columns": ["name", "tier", "exam_fee", "prep_time", "salary_bump", "renewal"],
        "min_evidence_per_cert": {"shopping": 1, "reddit": 1, "wikipedia": 1},
        "role_path_count": 5,
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["AWS book", "Azure book", "Google Cloud", "cloud certification", "DevOps book",
                              "system design", "kubernetes book", "exam guide", "study guide"],
        "reddit_forums": ["AWSCertifications", "AZURE", "googlecloud", "cscareerquestions",
                          "devops", "ITCareerQuestions", "kubernetes", "sysadmin"],
        "reddit_keywords": ["AWS", "Azure", "GCP", "cloud cert", "Solutions Architect",
                            "DevOps Engineer", "exam", "renewal"],
        "wiki_mandatory": ["Amazon Web Services", "Microsoft Azure", "Google Cloud Platform",
                           "Cloud computing", "Cloud certification", "AWS Certifications",
                           "IT certification", "Public cloud", "Infrastructure as a service", "DevOps"],
        "wiki_extra": ["Software as a service", "Platform as a service", "Serverless computing",
                       "Kubernetes", "Docker (software)", "Continuous delivery", "Continuous integration",
                       "Site reliability engineering", "AWS Lambda", "Amazon S3", "Amazon EC2",
                       "Azure DevOps", "Google Kubernetes Engine", "Big data", "Data engineering",
                       "Cloud security", "Identity and access management", "Microservices",
                       "Linux Foundation", "Cloud Native Computing Foundation"],
    },
    "checklist": [
        "Are >= 18 cloud certifications catalogued (>= 6 per AWS / GCP / Azure)?",
        "Does the catalog have >= 6 columns (name / tier / fee / prep-time / salary-bump / renewal)?",
        "Are tiers correctly tagged (foundational / associate / professional / specialty) per cert?",
        "Are exam fees cited in USD with shopping or wiki source?",
        "Are prep-time-weeks cited from reddit or shopping book references?",
        "Are 1-year salary-bump numbers cited from reddit threads?",
        "Does each cert row cite >= 1 wiki URL?",
        "Does each cert row cite >= 1 reddit URL with practitioner experience?",
        "Does each cert row cite >= 1 shopping URL (study guide / book)?",
        "Are >= 10 shopping product pages enumerated with price + rating?",
        "Are >= 30 reddit threads from at least 4 cloud / IT-career sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited?",
        "Is an 'optimal cert path for X role' section included for 5 roles (SWE / SRE / DevOps / DE / security)?",
        "Does each role path cite >= 2 reddit threads?",
        "Are renewal periods (e.g. 3 years for AWS) cited per cert?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid TOP-N format and start with the catalog table?",
    ],
}


# ----- Domain 9: Entertainment & media (3) -----

TASKS["dr_cross_deep_0025"] = {
    "intent": (
        "Produce a Comparison report on 4 major streaming services in 2026 — Netflix, Disney+, HBO Max, Apple TV+ — "
        "across 5 dimensions: (D1) monthly cost (basic / standard / 4K tier), (D2) catalog size (titles + originals), "
        "(D3) account-sharing crackdown status, (D4) live-sports / live-TV availability, (D5) cancel-anytime + retention offers. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 streaming-related products (Roku/Fire TV/Apple TV/Chromecast/HDMI cables/sound bars) + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/cordcutters, /f/television, /f/movies, /f/NetflixBestOf, /f/AppleTV, /f/DisneyPlus, /f/HBOMAX. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Streaming media, Netflix, The Walt Disney Company, HBO Max, Apple TV+, Cord cutting, Subscription video on demand, Streaming wars, Roku, Chromecast. "
        "Output a 4 x 5 matrix + 'best service for use case X' for 4 use cases (movies / TV originals / kids / sports). "
        "Format: markdown links only. Begin with matrix."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=streaming+device",
    "synthesis_extra": {
        "task_type": "comparison", "comparison_paths": ["netflix", "disney_plus", "hbo_max", "apple_tv_plus"],
        "use_cases": ["monthly_cost", "catalog_size", "sharing_crackdown", "live_sports", "cancel_retention"],
        "matrix_cells_required": 20, "min_evidence_per_cell": {"shopping": 1, "reddit": 1, "wikipedia": 1},
        "use_case_picks": 4,
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["streaming device", "Roku", "Fire TV", "Apple TV", "Chromecast",
                              "HDMI cable", "sound bar", "smart TV", "media player"],
        "reddit_forums": ["cordcutters", "television", "movies", "NetflixBestOf", "AppleTV",
                          "DisneyPlus", "HBOMAX", "PleX"],
        "reddit_keywords": ["Netflix", "Disney+", "HBO Max", "Apple TV+", "streaming",
                            "cord cutting", "subscription", "account sharing"],
        "wiki_mandatory": ["Streaming media", "Netflix", "The Walt Disney Company", "HBO Max",
                           "Apple TV+", "Cord cutting", "Subscription video on demand",
                           "Streaming wars", "Roku", "Chromecast"],
        "wiki_extra": ["Amazon Prime Video", "Hulu", "Paramount+", "Peacock (streaming service)",
                       "YouTube TV", "ESPN+", "Sling TV", "Fire TV", "Apple TV (hardware)",
                       "4K resolution", "Dolby Vision", "Dolby Atmos", "Closed captioning",
                       "Content delivery network", "Adaptive bitrate streaming",
                       "Digital rights management", "Original programming", "Cable television",
                       "Direct-to-video", "Theatrical release"],
    },
    "checklist": [
        "Are exactly 4 streaming services compared (Netflix / Disney+ / HBO Max / Apple TV+)?",
        "Are exactly 5 dimensions enumerated (cost / catalog / sharing / live-sports / cancel-retention)?",
        "Is a 4 x 5 matrix presented with all 20 cells populated?",
        "Are monthly costs cited with $ amounts for basic/standard/4K tiers?",
        "Are catalog sizes (titles + originals) cited with wiki or reddit numbers?",
        "Is account-sharing crackdown status cited per service (with 2024-2026 dates)?",
        "Does each cell cite >= 1 wiki + >= 1 reddit + >= 1 shopping URL?",
        "Are >= 10 shopping streaming products enumerated with price + rating?",
        "Are >= 30 reddit threads from at least 4 cordcutter / streaming sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited?",
        "Is a 'best service for X use case' section included covering 4 use cases?",
        "Does each use-case pick cite >= 2 reddit threads as evidence?",
        "Are at least 3 cross-source contradictions surfaced (marketing vs reddit reality)?",
        "Does the report disclose retention-offer experience (cancel + come-back discount)?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid TOP-10 format and chain-of-thought?",
        "Does the report cite at least one ad-supported tier price (e.g. Netflix with ads $6.99)?",
    ],
}

TASKS["dr_cross_deep_0026"] = {
    "intent": (
        "Produce a Timeline / Evolution report tracing the modern board-game renaissance from 1995 (Settlers of Catan) "
        "through 4 eras: "
        "(E1) 1995-2003 'gateway era' (Catan / Carcassonne / Ticket to Ride foundations), "
        "(E2) 2004-2012 'Eurogame ascendancy' (Agricola / Stone Age / Pandemic), "
        "(E3) 2013-2019 'Kickstarter explosion' (Gloomhaven / Wingspan / Scythe), "
        "(E4) 2020-present 'app-hybrid + legacy era' (Mansions of Madness 2nd / Charterstone / SagrAI). "
        "Each era cites >= 3 wiki + >= 3 reddit + >= 3 shopping product pages. "
        "Then a 'modern taxonomy by mechanism' section (worker placement / deck building / area control / hidden role / Legacy / cooperative). "
        "End with '7 myths the community has now debunked' (e.g. 'Eurogames are dry'). "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 30 board-game products + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/boardgames, /f/BoardGameGeek, /f/Eurogames, /f/PandemicLegacy, /f/Gloomhaven, /f/SoloBoardGaming. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Board game, Eurogame, Catan, Carcassonne (board game), Pandemic (board game), Gloomhaven, Wingspan (board game), Worker placement, Deck-building game, Cooperative board game. "
        "Output the 4-era timeline + taxonomy + 7-myth section. NO TOP-10 list. "
        "Format: markdown links only. Begin with E1."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=board+game",
    "synthesis_extra": {
        "task_type": "timeline",
        "eras": ["1995_2003_gateway", "2004_2012_eurogame", "2013_2019_kickstarter", "2020_app_hybrid"],
        "min_per_era": {"wiki": 3, "shopping": 3, "reddit": 3},
        "taxonomy_branches": ["worker_placement", "deck_building", "area_control", "hidden_role", "legacy", "cooperative"],
        "debunked_myths_count": 7, "explicitly_forbid_top10": True,
    },
    "yaml": {
        "shopping_keywords": ["board game", "Catan", "Carcassonne", "Pandemic game",
                              "Gloomhaven", "Wingspan", "Eurogame", "card game", "strategy game"],
        "reddit_forums": ["boardgames", "BoardGameGeek", "Eurogames", "PandemicLegacy",
                          "Gloomhaven", "SoloBoardGaming", "BoardGameDeals", "tabletopgamedesign"],
        "reddit_keywords": ["worker placement", "deck building", "Catan", "Wingspan", "Gloomhaven",
                            "Eurogame", "Kickstarter", "expansion"],
        "wiki_mandatory": ["Board game", "Eurogame", "Catan", "Carcassonne (board game)",
                           "Pandemic (board game)", "Gloomhaven", "Wingspan (board game)",
                           "Worker placement", "Deck-building game", "Cooperative board game"],
        "wiki_extra": ["Klaus Teuber", "Reiner Knizia", "Uwe Rosenberg", "Stefan Feld",
                       "Spiel des Jahres", "Kennerspiel des Jahres", "BoardGameGeek",
                       "Tabletop game", "Modern board games", "Tabletop role-playing game",
                       "Ticket to Ride (board game)", "Agricola (board game)", "Scythe (board game)",
                       "Terraforming Mars (board game)", "Settlers of Catan", "Risk (game)",
                       "Monopoly (game)", "Game design", "Asmodee Editions", "CMON Limited"],
    },
    "checklist": [
        "Are exactly 4 eras defined chronologically (gateway / Eurogame / Kickstarter / app-hybrid)?",
        "Is each era given >= 3 wiki + >= 3 shopping + >= 3 reddit citations?",
        "Is the chronology genuinely chronological (E1 to E4 increasing year)?",
        "Are >= 6 game families named across the timeline (Catan / Carcassonne / Pandemic / Gloomhaven / Wingspan / Scythe)?",
        "Does the modern taxonomy split games by >= 6 mechanisms (worker / deck / area / hidden / legacy / coop)?",
        "Does each taxonomy leaf cite a shopping URL + a wiki URL?",
        "Are exactly 7 community-debunked myths enumerated?",
        "Does each myth cite >= 1 wiki URL + >= 1 reddit URL?",
        "Are >= 30 shopping board game products cited with price + rating?",
        "Are >= 30 reddit threads from at least 4 board game sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 30 shopping, >= 20 reddit, >= 15 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Does the report avoid producing a TOP-10 ranking?",
        "Does the report distinguish 'still in print' vs 'historical only' games?",
        "Does the report cite Spiel des Jahres winners across multiple eras?",
        "Does the report avoid chain-of-thought and start with E1?",
        "Does each era include reddit-sourced community sentiment, not just product specs?",
    ],
}

TASKS["dr_cross_deep_0027"] = {
    "intent": (
        "Produce a Causal explanation report answering 'Why does Spotify pay artists ~$0.003 per stream and how does that math work?'. "
        "Build a 4-layer causal chain: "
        "(L1) revenue model: ad-supported vs premium tier ARPU breakdown, "
        "(L2) royalty pool: pro-rata vs user-centric distribution, label / publisher cut, "
        "(L3) artist economics: indie distributor (DistroKid / TuneCore) cut + tax + production cost, "
        "(L4) systemic effects: streaming as marketing vs revenue, touring economics. "
        "Include 'alternatives that pay better' enumeration (Bandcamp / Patreon / direct-to-fan). "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 books on music industry / DIY music + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/Music, /f/musicmarketing, /f/IndependentMusic, /f/WeAreTheMusicMakers, /f/SpotifyForArtists, /f/edmproduction. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Spotify, Music streaming, Royalty payment, Mechanical royalties, Performing right, Recording contract, Independent record label, Bandcamp, Patreon, Streaming media. "
        "Output 4-layer causal hierarchy + 'pay-per-stream comparison' table (Spotify vs Apple Music vs Tidal vs YouTube Music vs Bandcamp). "
        "Format: markdown links only. Begin with L1."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=music+book",
    "synthesis_extra": {
        "task_type": "causal",
        "causal_layers": ["L1_revenue_model", "L2_royalty_pool", "L3_artist_economics", "L4_systemic_effects"],
        "min_wiki_per_layer": {"L1_revenue_model": 3, "L2_royalty_pool": 3},
        "min_reddit_per_layer": {"L3_artist_economics": 5, "L4_systemic_effects": 5},
        "alternatives_enumeration_min": 3,
        "comparison_platforms": ["Spotify", "Apple Music", "Tidal", "YouTube Music", "Bandcamp"],
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["music book", "music business", "music marketing", "DIY music",
                              "music industry", "songwriting", "audio engineering", "record label", "musician guide"],
        "reddit_forums": ["Music", "musicmarketing", "IndependentMusic", "WeAreTheMusicMakers",
                          "SpotifyForArtists", "edmproduction", "WeAreTheArt", "musictheory"],
        "reddit_keywords": ["Spotify", "streaming royalties", "DistroKid", "TuneCore", "Bandcamp",
                            "music industry", "indie", "Patreon"],
        "wiki_mandatory": ["Spotify", "Music streaming", "Royalty payment", "Mechanical royalties",
                           "Performing right", "Recording contract", "Independent record label",
                           "Bandcamp", "Patreon", "Streaming media"],
        "wiki_extra": ["Apple Music", "Tidal (service)", "YouTube Music", "SoundCloud",
                       "Pandora Radio", "DistroKid", "TuneCore", "CD Baby", "ASCAP",
                       "Broadcast Music, Inc.", "Performance rights organisation",
                       "Mechanical license", "Synchronization right",
                       "Direct-to-consumer", "Universal Music Group", "Sony Music Entertainment",
                       "Warner Music Group", "Music industry", "Long tail (business)", "Network effect"],
    },
    "checklist": [
        "Does the report explicitly answer 'why ~$0.003 per stream'?",
        "Are exactly 4 causal layers defined (revenue / royalty / artist / systemic)?",
        "Does L1 cite >= 3 wiki articles on streaming revenue / ad+sub model?",
        "Does L2 cite >= 3 wiki articles on royalty pool / pro-rata vs user-centric?",
        "Does L3 cite >= 5 reddit threads from indie musicians on take-home math?",
        "Does L4 cite >= 5 reddit threads on touring vs streaming economics?",
        "Is a multi-layer causal hierarchy presented in markdown (indented bullets)?",
        "Is a 'pay-per-stream comparison' table presented for >= 5 platforms (Spotify/Apple/Tidal/YT Music/Bandcamp)?",
        "Are per-stream payouts cited per platform with reddit or wiki source?",
        "Are >= 3 alternative revenue paths (Bandcamp / Patreon / direct-to-fan) enumerated?",
        "Are >= 10 shopping books on music industry cited with price + rating?",
        "Are >= 30 reddit threads from at least 4 music-industry sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited?",
        "Does the report cite the major-label cut (typically ~50-60% of royalty)?",
        "Does the report quantify indie distributor (DistroKid/TuneCore) cut explicitly?",
        "Are at least 3 cross-source divergences surfaced (label-PR claim vs artist-reddit reality)?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs and starts with L1?",
    ],
}


# ----- Domain 10: Science & research (3) -----

TASKS["dr_cross_deep_0028"] = {
    "intent": (
        "Produce a Debunking / fact-check report auditing 5 popular CRISPR / gene-editing claims: "
        "(CL1) 'CRISPR-Cas9 is precise enough today for safe germline editing in humans', "
        "(CL2) 'He Jiankui's 2018 twin experiment was scientifically defensible', "
        "(CL3) 'CRISPR-edited crops are functionally identical to GMO regulation-wise', "
        "(CL4) 'Off-target effects have been solved by base editing / prime editing', "
        "(CL5) 'CRISPR could plausibly cure all single-gene diseases by 2030'. "
        "Each gets a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 books on biology / CRISPR / bioethics + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/AskScience, /f/biology, /f/bioinformatics, /f/ScienceBasedMedicine, /f/genetics, /f/skeptic. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: CRISPR, CRISPR gene editing, He Jiankui, Cas9, Base editing, Prime editing, Genome editing, Off-target effects, Bioethics, Germline editing. "
        "Output a 5-claim verdict table + 'consensus snapshot' section listing 5 named professional bodies' positions (NIH / WHO / NAS / Royal Society / Nuffield). "
        "Format: markdown links only. Begin with verdict table."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=CRISPR+book",
    "synthesis_extra": {
        "task_type": "debunking", "claim_count": 5,
        "claim_ids": ["germline_safety", "he_jiankui_defense", "crispr_crop_regulation", "off_target_solved", "single_gene_cure_2030"],
        "verdict_levels": ["SUPPORTED", "PARTIALLY_SUPPORTED", "DEBUNKED", "UNDETERMINED"],
        "min_evidence_per_claim": {"shopping_with_verbatim_quote": 1, "reddit": 1, "wikipedia": 1, "reasoning_paragraphs": 1},
        "consensus_bodies": 5,
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["CRISPR book", "biology textbook", "genetics", "bioethics",
                              "molecular biology", "DNA book", "biotechnology", "science book", "medicine book"],
        "reddit_forums": ["AskScience", "biology", "bioinformatics", "ScienceBasedMedicine",
                          "genetics", "skeptic", "Bioengineering", "labrats"],
        "reddit_keywords": ["CRISPR", "gene editing", "Cas9", "He Jiankui", "germline",
                            "off-target", "prime editing", "GMO"],
        "wiki_mandatory": ["CRISPR", "CRISPR gene editing", "He Jiankui", "Cas9",
                           "Base editing", "Prime editing", "Genome editing",
                           "Off-target effects", "Bioethics", "Germline editing"],
        "wiki_extra": ["Genome", "DNA", "Recombinant DNA", "Genetic engineering",
                       "Sickle cell disease", "Beta-thalassemia", "Duchenne muscular dystrophy",
                       "Mosaicism", "Chimera (genetics)", "Gene therapy", "Adeno-associated virus",
                       "Asilomar Conference on Recombinant DNA", "International Summit on Human Genome Editing",
                       "World Health Organization", "National Institutes of Health",
                       "National Academies of Sciences, Engineering, and Medicine",
                       "Royal Society", "Nuffield Council on Bioethics",
                       "Embryonic stem cell", "Genetically modified organism"],
    },
    "checklist": [
        "Are exactly 5 CRISPR claims defined (germline safety / He Jiankui / crop regulation / off-target solved / 2030 cure)?",
        "Does each claim receive a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}?",
        "For each claim, is there a shopping URL with verbatim claim quote (book chapter)?",
        "For each claim, is there >= 1 reddit URL with biologist / clinician discussion?",
        "For each claim, is there >= 1 wiki URL with mechanistic grounding?",
        "Does each claim include a 1-paragraph reasoning?",
        "Are >= 10 shopping product pages (CRISPR / biology books) enumerated with price + rating?",
        "Are >= 30 reddit threads from at least 4 science / biology sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited (CRISPR, CRISPR-Cas9, He Jiankui, Cas9, base editing, prime editing, genome editing, off-target, bioethics, germline)?",
        "Are 5 professional-body positions enumerated (NIH / WHO / NAS / Royal Society / Nuffield)?",
        "Does each professional-body position cite a wiki article?",
        "Does the report explicitly distinguish somatic from germline editing?",
        "Does the report cite the He Jiankui 3-year prison sentence?",
        "Are at least 3 cross-source contradictions surfaced (claim vs scientific consensus)?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Are at least 3 of the 5 verdicts NOT 'SUPPORTED' (i.e. report is not a marketing whitewash)?",
        "Does the report avoid TOP-N format and chain-of-thought?",
    ],
}

TASKS["dr_cross_deep_0029"] = {
    "intent": (
        "Produce an Enumeration / Catalog report cataloguing every major line of dark-matter evidence in modern astrophysics. "
        "For each evidence line: (a) name (e.g. 'galaxy rotation curves'), (b) primary observational source, "
        "(c) what dark matter property it implies (mass-to-light ratio / collisionless / cold), "
        "(d) main alternative-theory challenge (e.g. MOND), "
        "(e) consensus strength (strong / medium / contested). "
        "Cover at minimum 8 distinct evidence lines. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 books on cosmology / astrophysics / dark matter + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/AskScience, /f/Physics, /f/Astronomy, /f/cosmology, /f/AskAstronomers, /f/space. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: Dark matter, Galaxy rotation curve, Bullet Cluster, Cosmic microwave background, Gravitational lensing, Modified Newtonian dynamics, Lambda-CDM model, Dark matter halo, Velocity dispersion, Big Bang nucleosynthesis. "
        "Output a 8-row evidence catalog table + 'state of MOND vs CDM' section showing where each side fits the data. "
        "Format: markdown links only. Begin with catalog table."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=cosmology+book",
    "synthesis_extra": {
        "task_type": "enumeration", "evidence_lines_min": 8,
        "catalog_columns": ["name", "source", "implied_property", "alternative_challenge", "consensus_strength"],
        "min_evidence_per_line": {"shopping": 1, "reddit": 1, "wikipedia": 1},
        "mond_vs_cdm_section_required": True,
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["cosmology book", "astrophysics", "dark matter", "physics book",
                              "universe book", "space book", "Stephen Hawking", "Brian Greene", "telescope"],
        "reddit_forums": ["AskScience", "Physics", "Astronomy", "cosmology",
                          "AskAstronomers", "space", "PhysicsStudents", "spaceporn"],
        "reddit_keywords": ["dark matter", "galaxy rotation", "MOND", "Lambda-CDM", "Bullet Cluster",
                            "cosmic microwave background", "weakly interacting", "dark energy"],
        "wiki_mandatory": ["Dark matter", "Galaxy rotation curve", "Bullet Cluster",
                           "Cosmic microwave background", "Gravitational lensing",
                           "Modified Newtonian dynamics", "Lambda-CDM model",
                           "Dark matter halo", "Velocity dispersion", "Big Bang nucleosynthesis"],
        "wiki_extra": ["Weakly interacting massive particle", "Axion", "Sterile neutrino",
                       "Primordial black hole", "Vera Rubin", "Fritz Zwicky",
                       "Coma Cluster", "Andromeda Galaxy", "Milky Way",
                       "Hubble Space Telescope", "James Webb Space Telescope",
                       "Planck (spacecraft)", "Wilkinson Microwave Anisotropy Probe",
                       "Sloan Digital Sky Survey", "Dark energy", "Lambda",
                       "General relativity", "Standard Model", "Particle physics", "Cosmology"],
    },
    "checklist": [
        "Are >= 8 lines of dark-matter evidence catalogued?",
        "Does the catalog table have >= 5 columns (name / source / implied-property / alt-challenge / consensus-strength)?",
        "Are at least these 8 evidence lines covered: rotation curves / Bullet Cluster / CMB / gravitational lensing / BBN / structure formation / velocity dispersion / N-body simulations?",
        "Does each row cite the original observational paper / discoverer (e.g. Rubin 1980 for rotation curves)?",
        "Does each row cite >= 1 wiki URL?",
        "Does each row cite >= 1 reddit URL with physicist / astronomer discussion?",
        "Does each row cite >= 1 shopping URL (cosmology book or telescope)?",
        "Are >= 10 shopping product pages enumerated with price + rating?",
        "Are >= 30 reddit threads from at least 4 physics / astronomy sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited?",
        "Is a 'MOND vs CDM' section included that fairly presents both sides?",
        "Does the MOND section explicitly note where MOND fails (Bullet Cluster)?",
        "Does the CDM section note open questions (small-scale structure, missing satellites)?",
        "Are at least 3 cross-source debates surfaced (consensus claim vs reddit physicist skepticism)?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs?",
        "Does the report avoid TOP-N format and chain-of-thought?",
        "Does the report distinguish dark matter from dark energy?",
    ],
}

TASKS["dr_cross_deep_0030"] = {
    "intent": (
        "Produce a Causal explanation report answering 'How does an mRNA vaccine work and why was COVID mRNA so much faster than traditional vaccines?'. "
        "Build a 4-layer causal chain: "
        "(L1) molecular mechanism: mRNA → ribosome → spike protein → immune response, "
        "(L2) lipid-nanoparticle delivery: why LNPs solved the in-vivo mRNA delivery problem, "
        "(L3) platform speed: why mRNA design takes weeks vs years for inactivated vaccines, "
        "(L4) regulatory + manufacturing: Operation Warp Speed + parallel Phase 3 + at-risk manufacturing. "
        "Ground in >= 120 sandbox URLs, cite >= 60. "
        "(A) `__SHOPPING__` >= 10 books on immunology / vaccinology / pandemic + price + rating. "
        "(B) `__REDDIT__` >= 30 threads from /f/AskScience, /f/AskScienceFiction, /f/medicine, /f/Coronavirus, /f/COVID19, /f/biology, /f/Virology. "
        "(C) `__WIKIPEDIA__` >= 25 articles, mandatory: MRNA vaccine, Lipid nanoparticle, BNT162b2, MRNA-1273, Operation Warp Speed, Spike protein, Drew Weissman, Katalin Kariko, Phase III clinical trial, Vaccine. "
        "Output a 4-layer causal hierarchy + 'mRNA vs traditional vaccine timeline' table comparing dev-time per modality. "
        "Format: markdown links only. Begin with L1."
    ),
    "start_url": "__SHOPPING__/catalogsearch/result/?q=immunology+book",
    "synthesis_extra": {
        "task_type": "causal",
        "causal_layers": ["L1_molecular_mechanism", "L2_lnp_delivery", "L3_platform_speed", "L4_regulatory_manufacturing"],
        "min_wiki_per_layer": {"L1_molecular_mechanism": 3, "L2_lnp_delivery": 3},
        "min_reddit_per_layer": {"L3_platform_speed": 5, "L4_regulatory_manufacturing": 5},
        "comparison_table_modalities": ["mRNA", "inactivated", "viral_vector", "subunit"],
    },
    "per_domain_min": {"__SHOPPING__": 10, "__REDDIT__": 30, "__WIKIPEDIA__": 25},
    "yaml": {
        "shopping_keywords": ["immunology book", "vaccine book", "virology", "pandemic book",
                              "biology textbook", "medicine book", "biochemistry", "molecular biology", "RNA"],
        "reddit_forums": ["AskScience", "AskScienceFiction", "medicine", "Coronavirus",
                          "COVID19", "biology", "Virology", "labrats"],
        "reddit_keywords": ["mRNA", "vaccine", "COVID", "Pfizer", "Moderna",
                            "spike protein", "lipid nanoparticle", "Operation Warp Speed"],
        "wiki_mandatory": ["MRNA vaccine", "Lipid nanoparticle", "BNT162b2", "MRNA-1273",
                           "Operation Warp Speed", "Spike protein",
                           "Drew Weissman", "Katalin Kariko",
                           "Phase III clinical trial", "Vaccine"],
        "wiki_extra": ["Messenger RNA", "Ribosome", "Translation (biology)",
                       "Adaptive immune system", "T cell", "B cell", "Antibody",
                       "Pseudouridine", "Modified nucleoside",
                       "Pfizer", "BioNTech", "Moderna", "Severe acute respiratory syndrome coronavirus 2",
                       "Influenza vaccine", "Polio vaccine", "Inactivated vaccine",
                       "Subunit vaccine", "Viral vector vaccine", "Adjuvant",
                       "Clinical trial", "Food and Drug Administration"],
    },
    "checklist": [
        "Does the report explicitly answer 'how does mRNA vaccine work' AND 'why faster than traditional'?",
        "Are exactly 4 causal layers defined (mechanism / LNP delivery / platform speed / regulatory)?",
        "Does L1 cite >= 3 wiki articles on mRNA -> ribosome -> spike protein?",
        "Does L2 cite >= 3 wiki articles on lipid nanoparticles?",
        "Does L3 cite >= 5 reddit threads on dev-time discussions?",
        "Does L4 cite >= 5 reddit threads on Operation Warp Speed / regulatory parallels?",
        "Is a multi-layer causal hierarchy presented in markdown (indented bullets)?",
        "Is an 'mRNA vs traditional' timeline table presented covering >= 4 modalities (mRNA/inactivated/viral-vector/subunit)?",
        "Are typical dev times cited per modality (e.g. mRNA ~weeks design vs 5-15 years inactivated)?",
        "Does the report cite Drew Weissman & Katalin Kariko's pseudouridine breakthrough?",
        "Are >= 10 shopping books on immunology / vaccinology cited with price + rating?",
        "Are >= 30 reddit threads from at least 4 science / medicine sub-forums cited?",
        "Are >= 25 wiki articles cited?",
        "Are all 10 mandatory wiki articles cited (mRNA vaccine, LNP, BNT162b2, mRNA-1273, OWS, spike, Weissman, Kariko, Phase III, Vaccine)?",
        "Does the report cite at least one historical comparison (e.g. polio vaccine 5+ year dev)?",
        "Are at least 3 cross-source contradictions surfaced (public anxiety vs scientific data)?",
        "Are all cited URLs markdown-linked and sandbox-resolvable?",
        "Are >= 60 distinct URLs cited?",
        "Is per-domain minimum met: >= 10 shopping, >= 30 reddit, >= 25 wiki?",
        "Is the report 3500-8000 words / >= 25 paragraphs and starts with L1?",
        "Does the report distinguish mRNA pharmacology from genetic-modification myth?",
    ],
}


def write_yaml(task_id: str, spec: dict) -> Path:
    """Write configs/deep_topics/<NN>_<topic>.yaml from spec."""
    nn = task_id.replace("dr_cross_deep_", "")
    # Derive topic_id from intent or task — use first reddit forum + nn
    yspec = spec["yaml"]
    # Find a topic name from spec (using first wiki_mandatory or shopping kw)
    topic_id = task_id.replace("dr_cross_", "")  # fallback
    # Better: use a per-task derived name
    topic_map = {
        "0013": "finance_etf_passive_vs_active",
        "0014": "finance_brokerage_choice",
        "0015": "finance_fire_debunk",
        "0016": "law_tenant_rights_states",
        "0017": "law_gdpr_rights",
        "0018": "law_us_work_visa",
        "0019": "travel_visa_free_passport",
        "0020": "travel_jetlag_debunk",
        "0021": "travel_nomad_tax_residency",
        "0022": "edu_swe_career_paths",
        "0023": "edu_cs_phd_decline",
        "0024": "edu_cloud_certs",
        "0025": "ent_streaming_compare",
        "0026": "ent_boardgame_evolution",
        "0027": "ent_spotify_pay_causal",
        "0028": "sci_crispr_debunk",
        "0029": "sci_dark_matter_evidence",
        "0030": "sci_mrna_vaccine_causal",
    }
    topic = topic_map.get(nn, f"topic_{nn}")
    out_path = YAML_DIR / f"{nn}_{topic}.yaml"

    body = []
    body.append(f"topic_id: {topic}")
    body.append(f"task_id: {task_id}")
    body.append(f"display_name: {topic.replace('_', ' ').title()}")
    body.append("")
    body.append("shopping_keywords:")
    for k in yspec["shopping_keywords"]:
        body.append(f"  - {json.dumps(k)}" if "'" in k or ":" in k or '"' in k else f'  - "{k}"')
    body.append("")
    fmtlist = lambda lst: "[" + ", ".join(json.dumps(x) for x in lst) + "]"
    body.append(f"reddit_forums: {fmtlist(yspec['reddit_forums'])}")
    body.append(f"reddit_keywords: {fmtlist(yspec['reddit_keywords'])}")
    body.append("")
    body.append("wiki_mandatory:")
    for w in yspec["wiki_mandatory"]:
        body.append(f'  - {json.dumps(w)}')
    body.append("")
    body.append("wiki_extra:")
    for w in yspec["wiki_extra"]:
        body.append(f'  - {json.dumps(w)}')
    body.append("")
    out_path.write_text("\n".join(body))
    return out_path


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # Load existing checklist (will merge v2 tasks into it)
    existing_check = json.loads(CHECKLIST_PATH.read_text()) if CHECKLIST_PATH.exists() else {}

    written_yamls = []
    written_jsons = []
    new_check = dict(existing_check)
    for task_id, spec in TASKS.items():
        if len(spec["checklist"]) != 21:
            print(f"WARN {task_id} checklist {len(spec['checklist'])} != 21")
        # 1. yaml
        if not args.dry_run:
            yp = write_yaml(task_id, spec)
            written_yamls.append(yp.name)
        # 2. task json
        per_dm = spec.get("per_domain_min")
        if per_dm:
            t_json = relaxed_base_task(task_id, intent=spec["intent"],
                                       start_url=spec["start_url"],
                                       synthesis_extra=spec["synthesis_extra"],
                                       per_domain_min=per_dm)
        else:
            t_json = base_task(task_id, intent=spec["intent"],
                               start_url=spec["start_url"],
                               synthesis_extra=spec["synthesis_extra"])
        out_jp = TASKS_DIR / f"{task_id}.json"
        if not args.dry_run:
            out_jp.write_text(json.dumps(t_json, indent=2, ensure_ascii=False) + "\n")
            written_jsons.append(out_jp.name)
        # 3. checklist merge
        new_check[task_id] = spec["checklist"]

    if not args.dry_run:
        CHECKLIST_PATH.write_text(json.dumps(new_check, indent=2, ensure_ascii=False) + "\n")

    print(f"\n=== summary ===")
    print(f"yaml written: {len(written_yamls)}")
    print(f"task json written: {len(written_jsons)}")
    print(f"checklist tasks (merged): {len(new_check)}")


if __name__ == "__main__":
    main()
