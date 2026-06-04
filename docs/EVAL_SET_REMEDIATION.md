# Deep Eval Set Remediation

Status: remediation complete for the cleaned-golden layer; deep forum reseed is future work.
Date: 2026-06-03.
Scope: the 100-task cross-site deep-research eval set `dr_cross_deep_0001` .. `dr_cross_deep_0100`.

## 0. Background: the three sandbox sources and the contamination cause

The closed sandbox exposes exactly three retrievable sources:

- shopping: Magento "One Stop Market" on `localhost:7770`, product pages served as `<slug>.html`.
- forum: Postmill on `localhost:9999`, threads at `/f/<forum>/<id>/<slug>`. The seeded forum corpus is TECH-ONLY. It only covers these subforums: technology, headphones, gaming, videogames, LifeProTips, personalfinance, news, science, AskReddit, Art.
- wiki: Kiwix on `localhost:8090`, articles at `/content/wikipedia_en_all_nopic/A/<article>`.

The golden auto-builder selected `must_cite` URLs by keyword matching the task topic against source slugs. Keyword matching has no topic-relevance gate, so it pulled in slugs that merely share a token. The classic failure mode is the forum third: because the forum corpus is tech-only, a non-tech task can only keyword-match incidental threads. For example the COFFEE task (`dr_cross_deep_0002`) matched forum threads like `/f/AskReddit/.../beans-or-no-beans-in-chili` and `/f/Art/.../magic-bean-water`, which are OFF-topic. A `must_cite` URL is counted ON-topic only if its slug is genuinely about the task topic, not merely a token collision.

The remediation pass re-audited every `must_cite` URL for genuine topical relevance, wrote a cleaned golden (on-topic cites only) for each task, and assigned each task a verdict plus a per-task list of usable (`valid_sources`).

## 1. Headline stats

100 unique tasks audited. (The raw audit log contains 103 rows because `dr_cross_deep_0001` was rebuilt 4 times during iteration; the canonical numbers below use the latest rebuild per task_id.)

Verdict breakdown:

| Verdict | Count | Share | Meaning |
|---|---|---|---|
| valid | 65 | 65% | enough on-topic cites across its `valid_sources`; usable as-is |
| forum-invalid | 10 | 10% | forum third is contaminated/empty; score shopping+wiki only |
| mostly-off-topic | 25 | 25% | too few on-topic cites after cleaning; QUARANTINE |
| broken | 0 | 0% | no task lost all cites; every task retains on-topic wiki cites |

On-topic fraction (cleaned on-topic cites / original auto-built must_cite):

- Mean across all 100 tasks: 0.378
- Median: 0.346
- Range: 0.15 (worst) to 0.97 (best, `dr_cross_deep_0082`)
- Aggregate: 5,121 on-topic cites kept out of 13,475 auto-built must_cite cites. 62% of auto-built cites were OFF-topic and dropped.
- VALID subset mean on-topic fraction: 0.417 (cleaner than the full set, as expected).

On-topic cites kept, by source (across all 100 tasks):

- wiki: 3,141 (keyword match on Wikipedia is the most reliable; wiki survives almost everywhere)
- shopping: 1,190 (survives on product/market tasks, ~0 on causal/policy/timeline tasks)
- forum: 790 (the most contaminated third)

Forum-third contamination, quantified:

- 24 of 100 tasks ended with ZERO on-topic forum cites after cleaning.
- 31 of 100 tasks have forum REMOVED from `valid_sources` entirely (25 quarantined wiki-only tasks plus 6 of the 10 forum-invalid tasks; the other 4 forum-invalid tasks retain a token forum count of 1 that is still not enough to score on).
- Forum is the dominant reason a task fails: every one of the 25 quarantined tasks and 10 forum-invalid tasks lost most or all of its forum third because the task topic (brokerage, FIRE, antibiotic resistance, dark matter, frontend frameworks, etc.) has no tech-only forum coverage. Tasks that DO map onto the tech-only forum corpus (headphones, gaming/videogames, personalfinance, LLMs, voting/news) keep strong forum thirds: `dr_cross_deep_0082` (72 forum), `dr_cross_deep_0075` (59), `dr_cross_deep_0091` (57), `dr_cross_deep_0052` (47).

## 2. The canonical clean benchmark

The canonical clean benchmark is the cleaned goldens under `data/golden/deep_clean/` (100 files written), with scoring restricted to the 75 non-quarantined tasks and, per task, to the listed `valid_sources`.

Canonical set size: 75 scorable tasks = 65 valid (score all listed sources) + 10 forum-invalid (score shopping+wiki only). 25 tasks are quarantined.

### 2a. VALID tasks (65) and usable sources per task

Format: `task_id | usable sources | on-topic/total | shopping/forum/wiki on-topic`.

```
dr_cross_deep_0001 | shopping+forum+wiki |  85/125 | s57 f4  w24
dr_cross_deep_0002 | shopping+forum+wiki |  46/120 | s24 f2  w20
dr_cross_deep_0003 | shopping+forum+wiki |  41/127 | s4  f10 w27
dr_cross_deep_0004 | shopping+wiki       |  90/128 | s60 f2  w28
dr_cross_deep_0005 | shopping+forum+wiki |  59/123 | s28 f8  w23
dr_cross_deep_0006 | shopping+forum+wiki |  32/126 | s1  f5  w26
dr_cross_deep_0007 | forum+wiki          |  40/130 | s0  f10 w30
dr_cross_deep_0008 | shopping+forum+wiki |  66/129 | s31 f6  w29
dr_cross_deep_0009 | forum+wiki          |  33/128 | s0  f6  w27
dr_cross_deep_0010 | shopping+forum+wiki |  46/124 | s5  f17 w24
dr_cross_deep_0011 | shopping+forum+wiki |  58/129 | s14 f15 w29
dr_cross_deep_0013 | forum+wiki          |  60/141 | s0  f4  w56
dr_cross_deep_0016 | forum+wiki          |  39/123 | s0  f16 w23
dr_cross_deep_0017 | forum+wiki          |  29/123 | s0  f7  w22
dr_cross_deep_0018 | forum+wiki          |  29/128 | s0  f1  w28
dr_cross_deep_0019 | shopping+forum+wiki |  50/124 | s3  f23 w24
dr_cross_deep_0020 | shopping+wiki       |  55/127 | s26 f2  w27
dr_cross_deep_0023 | forum+wiki          |  51/126 | s0  f25 w26
dr_cross_deep_0025 | shopping+forum+wiki |  49/127 | s13 f10 w26
dr_cross_deep_0028 | shopping+forum+wiki |  41/127 | s11 f3  w27
dr_cross_deep_0030 | forum+wiki          |  35/129 | s0  f6  w29
dr_cross_deep_0031 | shopping+wiki       |  53/120 | s20 f4  w29
dr_cross_deep_0033 | shopping+forum+wiki |  43/144 | s12 f7  w24
dr_cross_deep_0034 | shopping+forum+wiki |  91/149 | s54 f8  w29
dr_cross_deep_0035 | shopping+forum+wiki |  97/143 | s54 f20 w23
dr_cross_deep_0038 | shopping+forum+wiki |  51/140 | s22 f4  w25
dr_cross_deep_0039 | forum+wiki          |  61/138 | s0  f6  w55
dr_cross_deep_0040 | forum+wiki          |  33/129 | s0  f4  w29
dr_cross_deep_0041 | shopping+forum+wiki |  57/140 | s17 f4  w36
dr_cross_deep_0042 | shopping+forum+wiki |  27/126 | s8  f2  w17
dr_cross_deep_0043 | shopping+forum+wiki | 103/144 | s54 f25 w24
dr_cross_deep_0045 | forum+wiki          |  22/136 | s0  f6  w16
dr_cross_deep_0046 | shopping+forum+wiki |  43/144 | s17 f2  w24
dr_cross_deep_0047 | forum+wiki          |  32/141 | s0  f11 w21
dr_cross_deep_0049 | shopping+forum+wiki |  53/142 | s4  f13 w36
dr_cross_deep_0052 | forum+wiki          |  86/141 | s0  f47 w39
dr_cross_deep_0053 | shopping+forum+wiki |  80/132 | s60 f8  w12
dr_cross_deep_0054 | shopping+forum+wiki |  54/133 | s6  f8  w40
dr_cross_deep_0056 | forum+wiki          |  25/134 | s0  f11 w14
dr_cross_deep_0057 | shopping+forum+wiki |  40/139 | s5  f6  w29
dr_cross_deep_0058 | shopping+forum+wiki |  49/138 | s30 f1  w18
dr_cross_deep_0059 | shopping+forum+wiki |  66/135 | s2  f13 w51
dr_cross_deep_0061 | forum+wiki          |  87/143 | s0  f25 w62
dr_cross_deep_0062 | shopping+forum+wiki |  28/142 | s1  f5  w22
dr_cross_deep_0064 | shopping+forum+wiki |  33/149 | s1  f2  w30
dr_cross_deep_0067 | forum+wiki          |  48/115 | s0  f9  w39
dr_cross_deep_0068 | forum+wiki          |  31/145 | s2  f4  w25
dr_cross_deep_0071 | forum+wiki          |  66/139 | s0  f10 w56
dr_cross_deep_0074 | forum+wiki          |  61/138 | s0  f5  w56
dr_cross_deep_0075 | forum+wiki          | 123/148 | s0  f59 w64
dr_cross_deep_0076 | shopping+forum+wiki |  67/149 | s32 f6  w29
dr_cross_deep_0078 | forum+wiki          |  63/145 | s0  f4  w59
dr_cross_deep_0081 | forum+wiki          |  38/156 | s0  f4  w34
dr_cross_deep_0082 | shopping+forum+wiki | 130/134 | s12 f72 w46
dr_cross_deep_0083 | shopping+forum+wiki |  76/138 | s35 f23 w18
dr_cross_deep_0084 | shopping+forum+wiki |  85/144 | s58 f3  w24
dr_cross_deep_0087 | forum+wiki          |  20/133 | s0  f7  w13
dr_cross_deep_0091 | shopping+forum+wiki | 100/142 | s6  f57 w37
dr_cross_deep_0092 | shopping+forum+wiki | 105/137 | s52 f28 w25
dr_cross_deep_0094 | shopping+forum+wiki |  56/142 | s1  f1  w54
dr_cross_deep_0096 | forum+wiki          |  62/143 | s0  f7  w55
dr_cross_deep_0097 | forum+wiki          |  34/150 | s0  f4  w30
dr_cross_deep_0098 | shopping+forum+wiki |  33/146 | s6  f1  w26
dr_cross_deep_0099 | forum+wiki          |  42/140 | s0  f29 w13
dr_cross_deep_0100 | shopping+forum+wiki |  99/142 | s60 f17 w22
```

Of the 65 valid tasks, 39 keep shopping as a usable source and 62 keep forum. The 3 valid tasks that drop forum (forum on-topic too thin to score, but shopping+wiki carry them) are `dr_cross_deep_0004` (shopping+wiki) and the shopping+wiki pair `dr_cross_deep_0020`, `dr_cross_deep_0031`.

### 2b. FORUM-INVALID tasks (10): score shopping + wiki only

These are otherwise good market/product/timeline tasks whose forum third collapsed (0 or 1 on-topic forum cite) because the topic has no tech-only forum coverage. They stay in the benchmark but scored on shopping+wiki only.

```
dr_cross_deep_0012 | shopping+wiki | 83/128 | s55 f0 w28  smart-home wireless protocols catalog
dr_cross_deep_0026 | shopping+wiki | 29/128 | s1  f0 w28  modern board-game renaissance timeline
dr_cross_deep_0032 | shopping+wiki | 73/133 | s54 f0 w19  vitamin D supplements report
dr_cross_deep_0036 | shopping+wiki | 75/149 | s23 f1 w51  collagen supplement claims debunk
dr_cross_deep_0048 | shopping+wiki | 60/145 | s35 f0 w25  why SSDs slow down over time
dr_cross_deep_0050 | shopping+wiki | 27/130 | s17 f0 w10  smartphone processor evolution
dr_cross_deep_0055 | shopping+wiki | 43/127 | s17 f1 w25  eco-friendly cleaning products report
dr_cross_deep_0060 | shopping+wiki | 44/128 | s36 f0 w8   fast-fashion environmental impact
dr_cross_deep_0086 | shopping+wiki | 23/131 | s12 f0 w11  airline loyalty programs timeline
dr_cross_deep_0090 | shopping+wiki | 68/133 | s31 f0 w37  MOOCs / online-education evolution
```

### 2c. QUARANTINE tasks (25): mostly-off-topic, do NOT score

These tasks ended with too few on-topic cites after cleaning, almost always because both the shopping third (the topic is not a purchasable product) and the forum third (the topic is not tech-only) collapsed, leaving only the wiki third. They are quarantined from the canonical scored set. Most are causal/policy/catalog topics outside all three corpora.

```
dr_cross_deep_0014 wiki-only          brokerage / robo-advisor for a $5,000 investor
dr_cross_deep_0015 wiki-only          FIRE claims debunk
dr_cross_deep_0021 forum+wiki (thin)  digital-nomad tax / residency programs
dr_cross_deep_0022 wiki-only          paths to a software-engineering job
dr_cross_deep_0024 wiki-only          cloud certification ladders catalog
dr_cross_deep_0027 thin all-source    Spotify per-stream royalty math (causal)
dr_cross_deep_0029 wiki-only          dark-matter evidence lines
dr_cross_deep_0037 forum+wiki (thin)  causes of antibiotic resistance
dr_cross_deep_0044 wiki-only          frontend frameworks Vue/React/Svelte
dr_cross_deep_0051 wiki-only          version-control systems timeline
dr_cross_deep_0063 wiki-only          carbon-offset certification standards
dr_cross_deep_0065 wiki-only          project-management tools for small teams
dr_cross_deep_0066 wiki-only          CRM software for early-stage startups
dr_cross_deep_0069 forum+wiki (thin)  why most startups fail in years 2-3
dr_cross_deep_0070 wiki-only          inflation impact small vs large business
dr_cross_deep_0072 forum+wiki (thin)  SBA small-business loans catalog
dr_cross_deep_0073 wiki-only          business-intelligence / analytics tools catalog
dr_cross_deep_0077 forum+wiki (thin)  voter-fraud detection claims fact-check
dr_cross_deep_0079 wiki-only          economic sanctions impact on civilians
dr_cross_deep_0080 wiki-only          social-media regulation timeline
dr_cross_deep_0085 forum+wiki (thin)  best travel-insurance policies
dr_cross_deep_0088 wiki-only          online learning platforms for career changers
dr_cross_deep_0089 wiki-only          learning-styles / multiple-intelligences debunk
dr_cross_deep_0093 wiki-only          music-streaming royalty payment models
dr_cross_deep_0095 wiki-only          payment-systems evolution timeline
```

Quarantine reason in one line: after the off-topic keyword-collision cites were removed, fewer than roughly a third of the original must_cite survived AND no single non-wiki source had enough on-topic cites to make the cross-site comparison meaningful. A wiki-only golden cannot test the cross-site retrieval the benchmark is built to measure, so these are held out rather than scored as if cross-site.

## 3. Remediation: what was done and what is future work

Done now (cleaned-golden layer):

- Every `must_cite` URL re-audited for genuine topical relevance (slug must be about the task topic, not a keyword collision). Off-topic cites dropped.
- Cleaned goldens written for all 100 tasks to `data/golden/deep_clean/`. Each cleaned golden's `must_cite_urls` contains only on-topic cites; the per-source on-topic counts in Section 2 match these files.
- Per-task `valid_sources` assigned (the sources that retain enough on-topic cites to score on).
- Verdict assigned per task: valid (65), forum-invalid (10), mostly-off-topic / quarantine (25).

Scoring rule changes (the safe, immediate fix):

- For forum-invalid tasks, score ONLY shopping + wiki. Do not penalize a system for failing to cite forum threads that do not exist on-topic for that task.
- For quarantined (mostly-off-topic) tasks, exclude from the scored set entirely.
- For valid tasks, score only the sources listed in that task's `valid_sources`.

Future work (the deep fix, sandbox-gated):

- The root cause is corpus coverage, not the goldens: the Postmill forum corpus is tech-only, so non-tech tasks have no genuine forum content to cite. The deep fix is to seed a forum corpus that covers the non-tech topic space (finance, health/medicine, law/policy, environment, education, travel) so those tasks regain a real forum third and can be promoted from forum-invalid or quarantine back to valid.
- This requires writing into the closed sandbox (new Postmill threads), which is sandbox-gated and out of scope for this remediation pass. It is listed here as future work. Until then, the canonical clean benchmark is the 75-task shopping/wiki-or-better set defined above.

## 4. Note to the scoring pipeline

The scorer must be pointed at `data/golden/deep_clean/` (not the original `data/golden/deep/`) and must restrict each task to its `valid_sources`:

- Read the cleaned golden per task from `data/golden/deep_clean/<task_id>.json`.
- Apply the per-task `valid_sources` allow-list from this document (Section 2): only cites whose host matches an allowed source count toward must-cite coverage, and missing a disallowed source is not penalized.
- Drop the 25 quarantined task_ids from the scored set; report the canonical benchmark as 75 tasks.
- For the 10 forum-invalid tasks, the allow-list is `{shopping, wiki}`.

Pointing the scorer at the original goldens, or scoring all three sources uniformly, reintroduces the off-topic keyword-collision cites and unfairly penalizes systems on forum content that is genuinely absent for the task.
