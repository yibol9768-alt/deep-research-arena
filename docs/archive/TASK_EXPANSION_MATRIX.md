# Task Expansion Matrix: 30 → 100

## Current 30 Tasks (by domain × intent)

| # | Domain | Intent | Topic |
|---|---|---|---|
| 0001 | Consumer | Recommendation | audio headphones |
| 0002 | Consumer | Recommendation | coffee brewing |
| 0003 | Lifestyle | Comparison | home fitness |
| 0004 | Lifestyle | Comparison | photography starter |
| 0005 | Consumer | Recommendation | indoor gardening |
| 0006 | Health/Safety | Debunking | kitchen cookware (PFAS) |
| 0007 | Health/Safety | Debunking | pet dog supplies |
| 0008 | Health/Safety | Debunking | baby essentials |
| 0009 | Consumer | Causal | EV road trip range |
| 0010 | Consumer | Timeline | mechanical keyboard |
| 0011 | Health/Safety | Debunking | sleep aid supplements |
| 0012 | Consumer | Enumeration | smart home security |
| 0013 | Finance | Comparison | ETF passive vs active |
| 0014 | Finance | Recommendation | brokerage choice |
| 0015 | Finance | Debunking | FIRE movement |
| 0016 | Law | Comparison | tenant rights states |
| 0017 | Law | Enumeration | GDPR rights |
| 0018 | Law | Enumeration | US work visa |
| 0019 | Travel | Comparison | visa-free passport |
| 0020 | Travel | Debunking | jet lag remedies |
| 0021 | Travel | Comparison | nomad tax residency |
| 0022 | Education | Comparison | SWE career paths |
| 0023 | Education | Causal | CS PhD decline |
| 0024 | Education | Enumeration | cloud certs |
| 0025 | Entertainment | Comparison | streaming compare |
| 0026 | Entertainment | Timeline | boardgame evolution |
| 0027 | Entertainment | Causal | Spotify pay causal |
| 0028 | Science | Debunking | CRISPR claims |
| 0029 | Science | Enumeration | dark matter evidence |
| 0030 | Science | Causal | mRNA vaccine |

## Current Distribution

| Intent \ Domain | Consumer | Health/Safety | Finance | Law | Travel | Education | Entertainment | Science | **TOTAL** |
|---|---|---|---|---|---|---|---|---|---|
| Recommendation | 3 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | **4** |
| Comparison | 0 | 0 | 1 | 1 | 2 | 1 | 1 | 0 | **8** (includes 0003,0004 as Lifestyle) |
| Debunking | 0 | 4 | 1 | 0 | 1 | 0 | 0 | 1 | **7** |
| Causal | 1 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | **4** |
| Timeline | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | **2** |
| Enumeration | 1 | 0 | 0 | 2 | 0 | 1 | 0 | 1 | **5** |
| **TOTAL** | **6** | **4** | **3** | **3** | **3** | **3** | **3** | **3** | **30** |

## Missing Domains (need ~10 each)

1. **Health/Medicine** — medical conditions, treatments, wellness, nutrition
2. **Technology** — software, hardware, AI, cybersecurity, networking
3. **Environment** — climate, sustainability, energy, conservation, pollution
4. **Business** — startups, management, marketing, economics, supply chain
5. **Politics** — policy, governance, elections, international relations, regulation

## Target Distribution (100 tasks)

Target per intent: ~balanced 16-17 each.

| Intent \ Domain | Consumer | Health/Safety | Finance | Law | Travel | Education | Entertainment | Science | Health/Med | Technology | Environment | Business | Politics | **TOTAL** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Recommendation | 3 | +1 | 1 | 0 | +1 | +1 | +1 | 0 | +2 | +2 | +2 | +2 | +1 | **17** |
| Comparison | 2 | 0 | 1 | 1 | 2 | 1 | 1 | +1 | +2 | +2 | +1 | +1 | +2 | **17** |
| Debunking | 0 | 4 | 1 | 0 | 1 | +1 | +1 | 1 | +2 | +2 | +2 | +1 | +1 | **17** |
| Causal | 1 | 0 | +1 | +1 | +1 | 1 | 1 | 1 | +2 | +2 | +2 | +2 | +2 | **17** |
| Timeline | 1 | +1 | +1 | +1 | +1 | +1 | 1 | +1 | +2 | +2 | +2 | +1 | +1 | **16** |
| Enumeration | 1 | +1 | +1 | 2 | +1 | 1 | +1 | 1 | +1 | +2 | +2 | +2 | +1 | **16** |
| **TOTAL** | **8** | **7** | **6** | **5** | **7** | **6** | **6** | **5** | **11** | **12** | **11** | **9** | **8** | **100** |

## New Tasks (0031-0100): 70 to generate

### Health/Medicine (11 new: 0031-0041)
| # | Intent | Topic Idea |
|---|---|---|
| 0031 | Recommendation | best home blood pressure monitors |
| 0032 | Recommendation | vitamin D supplements comparison |
| 0033 | Comparison | physical therapy vs chiropractic vs massage |
| 0034 | Comparison | plant-based vs Mediterranean vs keto diet |
| 0035 | Debunking | detox/cleanse product claims |
| 0036 | Debunking | collagen supplement effectiveness |
| 0037 | Causal | why do antibiotics cause resistance |
| 0038 | Causal | how does intermittent fasting affect metabolism |
| 0039 | Timeline | evolution of diabetes treatment (insulin→GLP-1) |
| 0040 | Timeline | history of vaccine development methods |
| 0041 | Enumeration | catalog of FDA-approved weight loss drugs |

### Technology (12 new: 0042-0053)
| # | Intent | Topic Idea |
|---|---|---|
| 0042 | Recommendation | best budget NAS for home server |
| 0043 | Recommendation | VPN services for privacy |
| 0044 | Comparison | React vs Vue vs Svelte for new projects |
| 0045 | Comparison | cloud providers (AWS vs Azure vs GCP) for startups |
| 0046 | Debunking | 5G health risk claims |
| 0047 | Debunking | quantum computing hype claims |
| 0048 | Causal | why do SSDs slow down over time |
| 0049 | Causal | how does LLM hallucination arise |
| 0050 | Timeline | evolution of smartphone processors (2007-2026) |
| 0051 | Timeline | history of version control (RCS→Git→?) |
| 0052 | Enumeration | catalog of open-source LLM families |
| 0053 | Enumeration | catalog of USB standards and connectors |

### Environment (11 new: 0054-0064)
| # | Intent | Topic Idea |
|---|---|---|
| 0054 | Recommendation | best home solar panel kits |
| 0055 | Recommendation | eco-friendly cleaning products |
| 0056 | Comparison | electric vs hybrid vs hydrogen vehicles |
| 0057 | Debunking | recycling effectiveness myths |
| 0058 | Debunking | organic food health benefit claims |
| 0059 | Causal | why are coral reefs bleaching |
| 0060 | Causal | how does fast fashion impact environment |
| 0061 | Timeline | evolution of renewable energy costs (2000-2026) |
| 0062 | Timeline | history of plastic pollution awareness |
| 0063 | Enumeration | catalog of carbon offset certification standards |
| 0064 | Enumeration | catalog of endangered species recovery programs |

### Business (9 new: 0065-0073)
| # | Intent | Topic Idea |
|---|---|---|
| 0065 | Recommendation | best project management tools for small teams |
| 0066 | Recommendation | CRM software for startups |
| 0067 | Comparison | LLC vs S-Corp vs C-Corp for founders |
| 0068 | Debunking | dropshipping passive income claims |
| 0069 | Causal | why do most startups fail in year 2-3 |
| 0070 | Causal | how does inflation affect small business differently |
| 0071 | Timeline | evolution of e-commerce platforms (2000-2026) |
| 0072 | Enumeration | catalog of SBA loan types and requirements |
| 0073 | Enumeration | catalog of business intelligence tools |

### Politics (8 new: 0074-0081)
| # | Intent | Topic Idea |
|---|---|---|
| 0074 | Recommendation | best news literacy / fact-checking resources |
| 0075 | Comparison | ranked-choice vs plurality vs approval voting |
| 0076 | Comparison | universal basic income experiments across countries |
| 0077 | Debunking | voter fraud prevalence claims |
| 0078 | Causal | why does gerrymandering persist despite court rulings |
| 0079 | Causal | how do sanctions affect civilian populations |
| 0080 | Timeline | evolution of social media regulation (2016-2026) |
| 0081 | Enumeration | catalog of international climate agreements |

### Existing Domain Gaps (19 new: 0082-0100)
| # | Domain | Intent | Topic Idea |
|---|---|---|---|
| 0082 | Health/Safety | Recommendation | best air purifiers for allergies |
| 0083 | Health/Safety | Timeline | evolution of food safety regulations |
| 0084 | Health/Safety | Enumeration | catalog of common household toxins |
| 0085 | Travel | Recommendation | best travel insurance policies |
| 0086 | Travel | Timeline | evolution of airline loyalty programs |
| 0087 | Travel | Enumeration | catalog of digital nomad visa programs |
| 0088 | Education | Recommendation | best online learning platforms |
| 0089 | Education | Debunking | learning style myths (visual/auditory/kinesthetic) |
| 0090 | Education | Timeline | evolution of MOOCs and online education |
| 0091 | Entertainment | Recommendation | best indie games under $20 |
| 0092 | Entertainment | Debunking | video game violence claims |
| 0093 | Entertainment | Enumeration | catalog of music streaming royalty models |
| 0094 | Finance | Causal | why do crypto markets crash together |
| 0095 | Finance | Timeline | evolution of payment systems (cash→BNPL) |
| 0096 | Finance | Enumeration | catalog of retirement account types globally |
| 0097 | Law | Causal | how do class action lawsuits work and who benefits |
| 0098 | Law | Timeline | evolution of data privacy laws worldwide |
| 0099 | Science | Comparison | fusion reactor designs (tokamak vs stellarator vs laser) |
| 0100 | Science | Timeline | history of Mars exploration missions |
