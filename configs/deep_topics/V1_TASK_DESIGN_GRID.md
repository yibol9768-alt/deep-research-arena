# Deep-Tier Arena v1 — 12-Task Design Grid

**Created**: 2026-04-27
**Status**: source of truth. 改任何 task json / checklist / yaml 之前都先改这里。
**Compliance**: `RESEARCH_TASK_DESIGN.md` §9 12 条决策、`DATASET_METHODOLOGY.md` §2 C1-C7。

## 0. 全局约束(每 task 必须满足)

| 约束 | 数值 | 验证器 |
|---|---|---|
| ≥ 120 sandbox URLs touched | trace 检查 | future |
| ≥ 60 cited markdown links | 文本解析 | `markdown_spec.min_citations` |
| 跨 ≥ 3 sandbox domain | url 域名计数 | `url_coverage.per_domain_minimum` |
| 100% cited URL HTTP 200 | curl probe | `URLReachabilityVerifier` |
| ≥ 50% must-cite recall | golden 对比 | `URLCoverageVerifier.must_cite_recall` |
| 3500-8000 words / ≥ 25 段 | 计数 | `markdown_spec` |
| ≥ 5 cross-source 综合发现 | LLM judge checklist | per-task 21 items |

**人工只做 2 件事**(用户 2026-04-27 决定):
1. 看 leaderboard 决定 "哪个 DR 框架最好"
2. 抽查 cited URL 是否真实 + 是否合理(`scripts/sample_urls_for_human_audit.py` 给每 agent run 抽 20 cited URL,人勾选 PASS/FAIL/UNCLEAR)

不做 human baseline / IAA / quote_span 标注。

## 1. 12-task overview matrix

| # | task_id | topic | domain | intent | synthesis | unique angle |
|---:|---|---|---|---|---|---|
| 01 | audio_headphones | 消费音频耳机 | Consumer | Recommendation | Ranking + Contradiction | 原 0001,锚点不动 |
| 02 | coffee_brewing | 家用咖啡 | Consumer | Recommendation | Ranking + Contradiction | 原 0002,锚点不动 |
| 03 | home_fitness | 家用健身 | Lifestyle | **Comparison** | Ranking + Taxonomy + Gap | 3 路径 × 5 use case 矩阵 |
| 04 | photography_starter | 摄影入门 | Lifestyle | **Comparison** | Taxonomy + Gap | 3 栈 × 5 use case 决策树 |
| 05 | gardening_indoor | 室内园艺 | Consumer | Recommendation | Ranking + Contradiction | 原 0005,锚点 |
| 06 | kitchen_cookware | 厨具材料 | Health/safety | **Debunking** | Contradiction + Gap | PFAS / 陶瓷 / 铸铁安全审 |
| 07 | pet_dog_supplies | 狗用品 | Health/safety | **Debunking** | Contradiction + Gap | grain-free / 生骨肉 / BPA 食碗审 |
| 08 | baby_essentials | 婴儿用品 | Health/safety | **Debunking** | Contradiction + Gap | SIDS 预防 / 配方奶 / 安全座椅审 |
| 09 | ev_roadtrip | EV 长途 | Tech | **Causal** | Causal inference + Timeline | 冬季续航暴跌因果链 |
| 10 | mechanical_keyboard | 机械键盘 | Tech | **Timeline** | Timeline + Taxonomy | 开关演进史 + 当下 taxonomy |
| 11 | sleep_aid_supplements | 睡眠辅助 | Health/safety | **Debunking** | Contradiction + Causal | 褪黑素剂量 / 睡眠监测器准确性 / 蓝光眼镜 |
| 12 | smart_home_security | 智能家居安防 | Tech | **Enumeration** | Taxonomy + Causal | 协议 + 安全模型枚举 |

**Intent 覆盖**: Recommendation 3 / Comparison 2 / Debunking 4 / Causal 1 / Timeline 1 / Enumeration 1 = **6 种**(§7.2 要求 ≥4)
**Synthesis 覆盖**: Ranking / Contradiction / Taxonomy / Gap / Causal / Timeline = **6 种全覆盖**
**Domain**: Consumer 3 / Lifestyle 2 / Health-safety 4 / Tech 3

## 2. 每 task 详细规格(读这一节做实施)

每 task 5 个字段:
- **intent**(整段 prompt,直接进 task json `intent` 字段)
- **synthesis_requirements**(具体 count + format)
- **wiki must-cite 增量**(yaml 已有的不重复,这里只列要补的)
- **21-item checklist**(全部 task-specific 写出来)
- **adversarial wiki 候选**(2 篇,工程化留 v1.1)


---

### 2.01 dr_cross_deep_0001 — Audio headphones (Recommendation,锚点)

**保持原有 task json 不动**。已在 `data/tasks/deep_research/cross_site_deep/dr_cross_deep_0001.json` 落地,golden 125 must_cite / 739 pool / 559 triples。作为 v1 中 Recommendation+Ranking+Contradiction 范式的对照锚点。

---

### 2.02 dr_cross_deep_0002 — Home coffee brewing (Recommendation,锚点)

**保持原有 task json 不动**。golden 120/521/270。Recommendation 范式第二个对照锚点 —— 与 0001 同 intent/synthesis 不同主题,用于检验"同范式跨主题分数稳定性"。

---

### 2.03 dr_cross_deep_0003 — Home fitness 3-path comparison (Comparison)

**Intent**:

> Produce a Comparison report on three home-fitness equipment paths under a fixed $300 starter budget — (P1) **Adjustable dumbbells + bench**, (P2) **Barbell + plate set + rack**, (P3) **Bodyweight + resistance bands + pull-up bar** — across exactly **5 use cases**: (UC1) muscle hypertrophy, (UC2) cardio + fat loss, (UC3) small-apartment friendliness, (UC4) injury rehab / mobility, (UC5) progression beyond 12 months.
>
> The report MUST be grounded in ≥ 120 distinct sandbox URLs and cite ≥ 60 as markdown links across (A) `__SHOPPING__` product pages enumerating products available in each path (≥ 12 products / path, with price + rating + review_count + feature_claim), (B) `__REDDIT__` threads from `/f/Fitness, /f/xxfitness, /f/bodyweightfitness, /f/homegym` etc. — ≥ 30 threads showing personal experience under each path, classified as {praise, complaint, technical_question, comparison, purchase_advice}, (C) `__WIKIPEDIA__` articles defining the underlying biomechanics: Strength training, Hypertrophy, Aerobic exercise, Calisthenics, Resistance band, Olympic weightlifting, Powerlifting, Range of motion, Progressive overload — plus ≥ 15 more articles supporting specific feature claims.
>
> Output a **3 × 5 decision matrix** (path × use case) — every cell rated {best / acceptable / poor} with **at least one shopping URL + one reddit URL + one wiki URL** as cited evidence in that cell. End with a "**when to pick which path**" section: 3 short paragraphs each explaining which user profile picks P1/P2/P3, citing ≥ 5 reddit threads in support. Do NOT output a TOP-10 list — this is comparison, not ranking.
>
> Format: every fact is a markdown link `[label](url)`. Sandbox-local URLs only. No fabrication. Begin directly with the comparison report.

**synthesis_requirements**:
- `comparison_matrix_dimensions`: 3 paths × 5 use cases = 15 cells
- `min_evidence_per_cell`: 1 shopping + 1 reddit + 1 wiki url
- `path_persona_paragraphs`: 3, each ≥ 5 reddit threads
- `contradiction_findings_min`: 3(同一 use case 下 marketing claim vs reddit 反馈互斥)
- **不出** TOP-10 / brand-sentiment ranking / rating-divergence(改成 path-level)

**wiki must-cite 增量**(yaml 0003 wiki_mandatory 加入):Strength training, Hypertrophy, Aerobic exercise, Calisthenics, Resistance band, Olympic weightlifting, Powerlifting, Range of motion, Progressive overload(共 9 篇,替换 yaml 现有 mandatory 列表)

**21-item checklist**(全 task-specific):
1. Are exactly 3 paths (dumbbell, barbell, bodyweight) defined and labelled P1/P2/P3?
2. Are exactly 5 use cases (muscle, cardio, apartment, rehab, progression) enumerated?
3. Does each of the 3 paths list ≥ 12 distinct shopping products with URL + price + rating?
4. Does the report show product totals stay under the $300 starter budget for each path?
5. Are ≥ 30 reddit threads cited across at least 4 fitness-related sub-forums?
6. Is each cited reddit thread classified as one of {praise, complaint, technical_question, comparison, purchase_advice}?
7. Are ≥ 25 distinct wiki articles cited with URL + defining statement?
8. Are all 9 mandatory wiki articles (Strength training, Hypertrophy, Aerobic exercise, Calisthenics, Resistance band, Olympic weightlifting, Powerlifting, Range of motion, Progressive overload) present?
9. Is the 3 × 5 decision matrix fully populated (15 cells, no blanks)?
10. Does each of the 15 cells cite ≥ 1 shopping URL + ≥ 1 reddit URL + ≥ 1 wiki URL?
11. Does each cell rate the path on that use case as {best, acceptable, poor}?
12. Are ≥ 3 cross-source contradictions surfaced (marketing claim vs reddit reality vs wiki definition)?
13. Are 3 path-persona paragraphs present (one per path) explaining the user profile that should pick that path?
14. Does each path-persona paragraph cite ≥ 5 reddit threads?
15. Are all cited URLs markdown-linked `[label](url)` and resolvable on the sandbox?
16. Are ≥ 60 distinct URLs cited in total?
17. Is per-domain minimum met: ≥ 30 shopping, ≥ 20 reddit, ≥ 15 wiki cited URLs?
18. Is the report 3500-8000 words / ≥ 25 paragraphs?
19. Does the report avoid producing a TOP-10 list (this is Comparison, not Ranking)?
20. Does the report avoid chain-of-thought and start directly with comparison content?
21. Are reddit thread metadata (forum, score, comment_count) recorded for every cited thread?

**adversarial wiki 候选**:
- `Progressive overload` — 注入虚构数字 "10% per session" 作为 industry consensus(真实 Wiki 无此具体数)
- `Resistance band` — 注入虚构 "ASTM D6711 standard for tensile fatigue" reference

---

### 2.04 dr_cross_deep_0004 — Photography starter 3-stack comparison (Comparison)

**Intent**:

> Produce a Comparison report on three photography starter stacks under a fixed $800 first-year budget — (S1) **Mirrorless body + 1 prime + 1 zoom**, (S2) **Used DSLR body + 2 primes + flash**, (S3) **Smartphone + lens-attachment kit + tripod**(no dedicated camera body) — across exactly **5 use cases**: (UC1) family/portrait indoor, (UC2) travel/landscape outdoor, (UC3) low-light event/concert, (UC4) social-media short-video, (UC5) growth path to professional within 18 months.
>
> The report MUST be grounded in ≥ 120 sandbox URLs and cite ≥ 60. Sources: (A) `__SHOPPING__` ≥ 36 product pages spanning 3 stacks (≥ 10 / stack incl. body + lens + accessory), with price + rating + feature_claim. (B) `__REDDIT__` ≥ 30 threads from /f/photography, /f/AskPhotography, /f/photocritique, /f/M43 (or /f/MirrorlessCamera), /f/AnalogCommunity etc. — at least 4 forums — recording sensor/lens debate, sample-photo critique, beginner advice. (C) `__WIKIPEDIA__` ≥ 25 articles: Mirrorless camera, Digital single-lens reflex camera, Image sensor format, Crop factor, Aperture, Shutter speed, ISO, Depth of field, Bokeh, Computational photography, Exposure (photography) plus ≥ 14 more on specific feature claims.
>
> Output a **3 × 5 taxonomy matrix** (stack × use case) rated {strong / workable / weak} with cited evidence. Add a **"5 hidden costs the marketing claim hides"** section — each cost is a contradiction between a vendor feature claim (cited shopping URL) and reddit-reported reality (cited thread URL) backed by a Wikipedia definition (cited wiki URL). End with **"upgrade path each stack supports past month-12"** — 3 paragraphs, ≥ 4 reddit threads each.
>
> Format: markdown links only. Sandbox-local. No fabrication. Begin with comparison content.

**synthesis_requirements**:
- `taxonomy_matrix`: 3 stacks × 5 use cases = 15 cells, each rated {strong / workable / weak}
- `min_evidence_per_cell`: 1 shopping + 1 reddit + 1 wiki url
- `hidden_cost_findings_min`: 5(marketing claim vs reality contradictions)
- `upgrade_path_paragraphs`: 3, each ≥ 4 reddit threads

**wiki must-cite 增量**:Mirrorless camera, Digital single-lens reflex camera, Image sensor format, Crop factor, Aperture, Shutter speed, ISO, Depth of field, Bokeh, Computational photography, Exposure (photography)(11 篇 mandatory)

**21-item checklist**:
1. Are exactly 3 stacks (mirrorless, used-DSLR, phone-attachment) defined and labelled S1/S2/S3?
2. Are exactly 5 use cases (portrait, landscape, low-light, social-video, growth) enumerated?
3. Does each of the 3 stacks list ≥ 10 shopping products with body + lens + accessory breakdown?
4. Are total stack costs shown to fit within the $800 budget?
5. Are ≥ 30 reddit threads cited across at least 4 photography sub-forums?
6. Is each reddit thread classified by topic role (sensor-debate, sample-critique, beginner-advice, gear-purchase)?
7. Are ≥ 25 wiki articles cited with URL + defining statement?
8. Are all 11 mandatory wiki articles cited (Mirrorless camera, DSLR, Image sensor format, Crop factor, Aperture, Shutter speed, ISO, Depth of field, Bokeh, Computational photography, Exposure)?
9. Is the 3 × 5 taxonomy matrix fully populated and each cell rated {strong / workable / weak}?
10. Does each of the 15 cells cite ≥ 1 shopping + ≥ 1 reddit + ≥ 1 wiki URL?
11. Are ≥ 5 "hidden cost" contradictions surfaced with full triple evidence (shopping URL + reddit URL + wiki URL)?
12. Does each hidden cost name the specific marketing claim and the specific reality contradiction?
13. Are 3 upgrade-path paragraphs present (one per stack)?
14. Does each upgrade-path paragraph cite ≥ 4 reddit threads?
15. Are all cited URLs markdown-linked and resolvable on the sandbox?
16. Are ≥ 60 distinct URLs cited in total?
17. Is per-domain minimum met: ≥ 30 shopping, ≥ 20 reddit, ≥ 15 wiki?
18. Is the report 3500-8000 words / ≥ 25 paragraphs?
19. Does the report avoid TOP-10 ranking format?
20. Does the report avoid chain-of-thought?
21. Does the report explicitly call out which stack is wrong for each use case (not only positive ratings)?

**adversarial wiki 候选**:
- `Crop factor` — 注入错误的 "Micro Four Thirds = 1.6×"(实际 2.0×)
- `ISO` — 注入虚构 "ISO 12800 base" smartphone claim

---

### 2.05 dr_cross_deep_0005 — Indoor gardening (Recommendation,锚点)

**保持原有 task json 不动**(锚点 #3,Recommendation 范式第三个对照,同 0001/0002 模板)。

---

### 2.06 dr_cross_deep_0006 — Cookware materials safety debunking (Debunking)

**Intent**:

> Produce a Debunking / Fact-Check report auditing **5 specific marketing claims** common on consumer cookware: (CL1) "PFOA-free non-stick is safe at all temperatures", (CL2) "Ceramic-coated pans last as long as PTFE pans", (CL3) "Cast iron skillets contribute meaningful dietary iron", (CL4) "Stainless steel is non-reactive with all foods", (CL5) "Hard-anodized aluminum cannot leach into food". For each claim, the report must produce a verdict {SUPPORTED / PARTIALLY_SUPPORTED / DEBUNKED} backed by triple evidence.
>
> Ground the report in ≥ 120 sandbox URLs (≥ 60 cited). Sources: (A) `__SHOPPING__` ≥ 36 cookware product pages (across cast iron, non-stick, ceramic-coated, stainless, hard-anodized) with their **exact marketing language for the claim being audited** + price + rating. (B) `__REDDIT__` ≥ 30 threads from /f/Cooking, /f/AskCulinary, /f/castiron, /f/Cookware, /f/BuyItForLife, /f/Frugal — capturing real-world failure modes (peeling coating, rust, scratches, residue). (C) `__WIKIPEDIA__` ≥ 25 articles, mandatory: Polytetrafluoroethylene, Perfluorooctanoic acid, Non-stick surface, Cast-iron cookware, Stainless steel, Anodizing, Aluminium toxicity, Maillard reaction, Heat capacity, Thermal conductivity — plus ≥ 15 more articles supporting specific claims.
>
> Output a **5-claim verdict table**: each row = one claim, with columns (verdict, key supporting product URL with literal marketing quote, key reddit URL with user counter-evidence, key wiki URL with the underlying chemistry / physics, 1-paragraph reasoning). Add a **"safety risk rank"** section: rank the 5 cookware materials by aggregate risk score derived from the 5 claim verdicts. End with a **"shopping rules" cheat-sheet** (≤ 8 bullet points), each rule cited with ≥ 1 wiki URL.
>
> Format: markdown links only. Begin with the verdict table. No chain-of-thought.

**synthesis_requirements**:
- `claim_verdicts`: 5(每个 verdict ∈ {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED})
- `min_evidence_per_claim`: 1 shopping URL with verbatim marketing quote + 1 reddit URL + 1 wiki URL + 1 reasoning paragraph
- `safety_risk_rank`: 5 materials ranked
- `shopping_rules_count`: 6-8, each cited with ≥ 1 wiki URL
- **不出** TOP-10 product list

**wiki must-cite 增量**:Polytetrafluoroethylene, Perfluorooctanoic acid, Non-stick surface, Cast-iron cookware, Stainless steel, Anodizing, Aluminium toxicity, Maillard reaction, Heat capacity, Thermal conductivity(10 篇 mandatory)

**21-item checklist**:
1. Are exactly 5 marketing claims defined upfront (PFOA-free safety / ceramic durability / iron leaching / stainless reactivity / anodized aluminum)?
2. Does each of the 5 claims receive a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED}?
3. For each claim, is there a shopping product URL cited with the **verbatim marketing quote** that makes the claim?
4. For each claim, is there ≥ 1 reddit URL with user counter-evidence (or supporting evidence if SUPPORTED)?
5. For each claim, is there ≥ 1 wiki URL grounding the underlying chemistry or physics?
6. Does each claim include a 1-paragraph reasoning explaining how the evidence supports the verdict?
7. Are ≥ 36 shopping product pages enumerated across 5 cookware categories with price + rating?
8. Are ≥ 30 reddit threads from at least 4 cooking sub-forums cited?
9. Are ≥ 25 wiki articles cited?
10. Are all 10 mandatory wiki articles (PTFE, PFOA, Non-stick surface, Cast-iron, Stainless steel, Anodizing, Aluminium toxicity, Maillard, Heat capacity, Thermal conductivity) cited?
11. Is a safety-risk ranking of all 5 cookware materials presented?
12. Is the safety-risk ranking justified with citations to the 5 claim verdicts?
13. Are 6-8 shopping rules listed in a cheat-sheet?
14. Does each shopping rule cite ≥ 1 wiki URL?
15. Are at least 2 of the 5 verdicts DEBUNKED or PARTIALLY_SUPPORTED (i.e., the report is not a marketing whitewash)?
16. Are ≥ 60 distinct URLs cited in total?
17. Is per-domain minimum met: ≥ 30 shopping, ≥ 20 reddit, ≥ 15 wiki?
18. Is the report 3500-8000 words / ≥ 25 paragraphs?
19. Are all cited URLs markdown-linked and sandbox-resolvable?
20. Does the report avoid TOP-10 product ranking (this is Debunking, not Recommendation)?
21. Does the report avoid chain-of-thought and start with the verdict table?

**adversarial wiki 候选**:
- `Cast-iron cookware` — 注入虚构 "average 10 mg iron per serving" 数字
- `Polytetrafluoroethylene` — 注入虚构 "decomposes at 350 °C" temperature(实际是 ~260 °C 分解开始)

---

### 2.07 dr_cross_deep_0007 — Dog nutrition / supplies debunking (Debunking)

**Intent**:

> Produce a Debunking report auditing **5 dog-care marketing/folk claims**: (CL1) "Grain-free dog food is healthier than grain-inclusive", (CL2) "Raw / BARF diet is more natural and reduces allergies", (CL3) "BPA-free plastic dog bowls are safe for daily use", (CL4) "Calming chews with L-theanine actually reduce anxiety", (CL5) "Dental chews replace teeth brushing". Each claim must receive a verdict ∈ {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}.
>
> Ground in ≥ 120 sandbox URLs (≥ 60 cited). (A) `__SHOPPING__` ≥ 36 dog products carrying the audited claims (food bags with grain-free / raw / dental, calming chews, plastic bowls) — cite the exact marketing language. (B) `__REDDIT__` ≥ 30 threads from /f/dogs, /f/puppy101, /f/DogAdvice, /f/AskVet, /f/DogTraining, /f/Dogtraining — owner experience reports + vet AMAs + breed-specific advice. (C) `__WIKIPEDIA__` ≥ 25 articles, mandatory: Dog food, Raw feeding, Dilated cardiomyopathy, Bisphenol A, Theanine, Dog anxiety, Periodontal disease, Plaque (dental), Veterinary medicine, Salmonella — plus ≥ 15 more.
>
> Output a 5-claim verdict table (verdict / shopping URL with marketing quote / reddit URL / wiki URL / reasoning). Add a "**FDA / AAFCO regulatory gap**" section that names ≥ 3 specific gaps in US pet food regulation that allow these claims to persist (cited to wiki). End with a "**vet-aligned shopping list**" (≤ 8 bullets) — products that align with the SUPPORTED claims, each cited with shopping URL + corroborating reddit + wiki definition.
>
> Format: markdown links. Begin with verdict table. No chain-of-thought.

**synthesis_requirements**:
- `claim_verdicts`: 5
- `min_evidence_per_claim`: 1 shopping (verbatim quote) + 1 reddit + 1 wiki + 1 reasoning paragraph
- `regulatory_gap_findings`: ≥ 3, each wiki-cited
- `vet_aligned_shopping_list`: 6-8 bullets,each w/ shopping + reddit + wiki

**wiki must-cite 增量**:Dog food, Raw feeding, Dilated cardiomyopathy, Bisphenol A, Theanine, Dog anxiety, Periodontal disease, Plaque (dental), Veterinary medicine, Salmonella(10 mandatory)

**21-item checklist**:
1. Are exactly 5 dog-care marketing/folk claims defined upfront?
2. Does each claim receive a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}?
3. For each claim, is there a shopping product URL with the verbatim marketing quote?
4. For each claim, is there ≥ 1 reddit thread URL with owner-experience or vet-AMA evidence?
5. For each claim, is there ≥ 1 wiki article URL with biological/chemical grounding?
6. Does each claim include a 1-paragraph reasoning?
7. Are ≥ 36 shopping product pages enumerated across food/chews/bowls/supplements?
8. Are ≥ 30 reddit threads from at least 4 dog/pet sub-forums cited?
9. Are ≥ 25 wiki articles cited?
10. Are all 10 mandatory wiki articles (Dog food, Raw feeding, DCM, BPA, Theanine, Dog anxiety, Periodontal disease, Plaque, Veterinary medicine, Salmonella) cited?
11. Are ≥ 3 FDA/AAFCO regulatory gaps named with wiki citations?
12. Does the regulatory-gap section name specific regulations or their absence?
13. Is a "vet-aligned shopping list" of 6-8 bullets included?
14. Does each shopping-list bullet cite ≥ 1 shopping + ≥ 1 reddit + ≥ 1 wiki URL?
15. Are at least 2 of the 5 verdicts DEBUNKED or PARTIALLY_SUPPORTED?
16. Are ≥ 60 distinct URLs cited in total?
17. Is per-domain minimum met: ≥ 30 shopping, ≥ 20 reddit, ≥ 15 wiki?
18. Is the report 3500-8000 words / ≥ 25 paragraphs?
19. Are all cited URLs markdown-linked and resolvable on the sandbox?
20. Does the report avoid producing a generic Top-10 dog product ranking?
21. Does the report avoid chain-of-thought and start with the verdict table?

**adversarial wiki 候选**:
- `Dilated cardiomyopathy` — 注入虚构 "FDA confirmed grain-free causes 80% of canine DCM"(实际 FDA 立场未结论)
- `Bisphenol A` — 注入虚构 "EU banned all BPA plastics in 2018"(实际只对 thermal paper 等部分限制)

---

### 2.08 dr_cross_deep_0008 — Baby essentials safety debunking (Debunking)

**Intent**:

> Produce a Debunking / Fact-Check report auditing **5 marketing or folk claims** about first-baby essentials: (CL1) "Wedge / positioner pillows reduce SIDS", (CL2) "Formula brand X is closer to breast milk than competitors", (CL3) "Convertible car seats can safely be used rear-facing past 2 years", (CL4) "Sleep sacks are safer than swaddles past 8 weeks", (CL5) "Anti-colic bottles measurably reduce crying time". Each gets a verdict ∈ {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}.
>
> Ground in ≥ 120 sandbox URLs (≥ 60 cited). (A) `__SHOPPING__` ≥ 36 baby product pages (positioners, formulas, car seats, sleep sacks, bottles) with their **verbatim marketing language** + price + rating. (B) `__REDDIT__` ≥ 30 threads from /f/beyondthebump, /f/NewParents, /f/Parenting, /f/breastfeeding, /f/predaddit — recording experiences, AAP-style guidance discussions, hospital nurse Q&A. (C) `__WIKIPEDIA__` ≥ 25 articles, mandatory: Sudden infant death syndrome, Infant formula, Breast milk, Child safety seat, Swaddling, Sleep sack, Colic, Pacifier, ISOFIX, Breastfeeding — plus ≥ 15 more.
>
> Output a 5-claim verdict table. Add a section **"AAP / NHS guideline alignment"**: for each claim, note explicitly whether the verdict aligns with major pediatric body guidance (American Academy of Pediatrics / NHS / WHO), citing wiki URLs. End with a **"safe-sleep checklist"** of ≤ 8 bullet rules, each cited.
>
> Format: markdown links. Begin with verdict table. No chain-of-thought.

**synthesis_requirements**:
- `claim_verdicts`: 5
- `min_evidence_per_claim`: 1 shopping verbatim + 1 reddit + 1 wiki + reasoning
- `guideline_alignment_findings`: 5(每 claim 一段 alignment 注释,wiki 引)
- `safe_sleep_checklist`: 6-8 bullets, each cited

**wiki must-cite 增量**:Sudden infant death syndrome, Infant formula, Breast milk, Child safety seat, Swaddling, Sleep sack, Colic, Pacifier, ISOFIX, Breastfeeding(10 mandatory)

**21-item checklist**:
1. Are exactly 5 baby-essential claims defined upfront (positioner SIDS / formula equivalence / extended rear-facing / sleep sack / anti-colic bottle)?
2. Does each receive a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}?
3. Is the verbatim marketing claim quoted from a cited shopping URL for each claim?
4. Is ≥ 1 reddit thread URL cited per claim (parent experience / nurse advice)?
5. Is ≥ 1 wiki URL cited per claim grounding the medical / safety basis?
6. Does each claim include a 1-paragraph reasoning?
7. Are ≥ 36 shopping product pages enumerated across positioners / formulas / car seats / sleep sacks / bottles?
8. Are ≥ 30 reddit threads from ≥ 4 parenting sub-forums cited?
9. Are ≥ 25 wiki articles cited?
10. Are all 10 mandatory wiki articles (SIDS, Infant formula, Breast milk, Child safety seat, Swaddling, Sleep sack, Colic, Pacifier, ISOFIX, Breastfeeding) present?
11. Is each verdict explicitly compared to AAP / NHS / WHO guidance with wiki citation?
12. Does the report flag any claim that contradicts the relevant pediatric body's stance?
13. Is a 6-8 bullet safe-sleep checklist provided?
14. Does each safe-sleep bullet cite ≥ 1 source (shopping / reddit / wiki)?
15. Are at least 3 of the 5 verdicts DEBUNKED, PARTIALLY_SUPPORTED, or UNDETERMINED (the report is not a marketing whitewash)?
16. Are ≥ 60 distinct URLs cited?
17. Is per-domain minimum met: ≥ 30 shopping, ≥ 20 reddit, ≥ 15 wiki?
18. Is the report 3500-8000 words / ≥ 25 paragraphs?
19. Are all cited URLs markdown-linked and sandbox-resolvable?
20. Does the report avoid TOP-10 product ranking?
21. Does the report avoid chain-of-thought and start with the verdict table?

**adversarial wiki 候选**:
- `Sudden infant death syndrome` — 注入虚构 "AAP recommends crib wedges since 2019"(实际 AAP 2017 起明确反对)
- `Child safety seat` — 注入虚构 "ASTM standard requires 4 years rear-facing"(实际无此要求)

---

### 2.09 dr_cross_deep_0009 — EV winter range causal explanation (Causal)

**Intent**:

> Produce a Causal Explanation report answering: **"Why does an electric vehicle's effective range typically drop 20-40% in cold-weather (sub-freezing) operation, and what physical, chemical, and behavioural factors compose that loss?"** The report is NOT a buying guide; it must build a **causal chain** from first principles to road-tested numbers.
>
> Ground in ≥ 120 sandbox URLs (≥ 60 cited). (A) `__SHOPPING__` ≥ 30 EV-related products (Level 2 chargers, battery heaters / blankets, cold-weather accessories, replacement batteries) — cite the marketing claims about cold-weather performance + price. (B) `__REDDIT__` ≥ 30 threads from /f/electricvehicles, /f/teslamotors, /f/cars, /f/BoltEV, /f/Volt — winter range reports, real-world MPGe drop logs, charging speed degradation reports. (C) `__WIKIPEDIA__` ≥ 25 articles, mandatory: Lithium-ion battery, Battery thermal management, Heat pump, Internal resistance, Electrolyte, Lithium plating, Regenerative braking, Cabin heater, Specific heat capacity, Arrhenius equation — plus ≥ 15 more.
>
> Output a **multi-layer causal diagram in markdown** (not graphviz — use indented bullet hierarchy) tracing 4 causal layers:
> - **L1 chemistry**: lithium-ion electrolyte conductivity drop, lithium plating risk, internal resistance increase (cite wiki).
> - **L2 thermal**: cabin heating energy budget, battery preconditioning, heat pump efficiency (cite wiki + shopping for heat-pump-equipped models).
> - **L3 driver behaviour**: HVAC settings, regen reduction in cold, route planning (cite reddit experience reports).
> - **L4 measured impact**: empirical % range drop reported by users (cite ≥ 8 reddit threads with explicit %).
>
> Add a **"mitigation strategies ranked by % range recovered"** table — each strategy cited with one shopping URL (product implementing it) + one reddit URL (user reporting the recovery). End with a **"what cars handle cold best"** section ranking ≥ 3 EV models by aggregated reddit cold-weather sentiment, citing ≥ 3 reddit threads / model.
>
> Format: markdown links only. Begin with the L1 layer. No chain-of-thought.

**synthesis_requirements**:
- `causal_layers`: 4(L1 chemistry / L2 thermal / L3 behaviour / L4 measured)
- `min_evidence_per_layer`: ≥ 3 wiki citations (L1, L2), ≥ 5 reddit citations (L3, L4)
- `mitigation_strategies_ranked`: ≥ 5 strategies, each cited shopping + reddit
- `model_ranking`: ≥ 3 EV models, ≥ 3 reddit / model

**wiki must-cite 增量**:Lithium-ion battery, Battery thermal management, Heat pump, Internal resistance, Electrolyte, Lithium plating, Regenerative braking, Cabin heater, Specific heat capacity, Arrhenius equation(10 mandatory)

**21-item checklist**:
1. Does the report explicitly address "why does EV range drop in cold weather" as the central question?
2. Are exactly 4 causal layers defined (L1 chemistry, L2 thermal, L3 behaviour, L4 measured)?
3. Does L1 cite ≥ 3 wiki articles on battery chemistry (electrolyte, internal resistance, lithium plating)?
4. Does L2 cite ≥ 3 wiki articles on thermal management (heat pump, cabin heater, specific heat capacity)?
5. Does L3 cite ≥ 5 reddit threads on driver behaviour and HVAC adjustments?
6. Does L4 cite ≥ 8 reddit threads with **explicit percentage** range-drop numbers?
7. Are ≥ 30 shopping products related to cold-weather EV operation cited (chargers, heaters, accessories)?
8. Are ≥ 30 reddit threads from ≥ 4 EV-related sub-forums cited?
9. Are ≥ 25 wiki articles cited?
10. Are all 10 mandatory wiki articles (Li-ion, Thermal mgmt, Heat pump, Internal resistance, Electrolyte, Li plating, Regen, Cabin heater, Specific heat, Arrhenius) cited?
11. Is a multi-layer causal hierarchy presented in markdown (indented bullets, not flat list)?
12. Are ≥ 5 mitigation strategies ranked by % range recovered?
13. Does each mitigation strategy cite ≥ 1 shopping URL + ≥ 1 reddit URL?
14. Are ≥ 3 EV models ranked by aggregated reddit cold-weather sentiment?
15. Does each ranked model cite ≥ 3 reddit threads in support?
16. Are ≥ 60 distinct URLs cited?
17. Is per-domain minimum met: ≥ 30 shopping, ≥ 20 reddit, ≥ 15 wiki?
18. Is the report 3500-8000 words / ≥ 25 paragraphs?
19. Does the report **avoid** giving a generic "best EV" Top-10 (this is Causal, not Recommendation)?
20. Are all cited URLs markdown-linked and sandbox-resolvable?
21. Does the report avoid chain-of-thought and start with L1 chemistry?

**adversarial wiki 候选**:
- `Lithium-ion battery` — 注入虚构 "internal resistance doubles at -10°C"(实际数字依化学体系而异)
- `Heat pump` — 注入虚构 "COP < 1 below 0°C"(实际现代 R744 / R290 系统 COP 仍 > 1)

---

### 2.10 dr_cross_deep_0010 — Mechanical keyboard switch evolution (Timeline)

**Intent**:

> Produce a Timeline / Evolution report tracing the **30+ year history of mechanical keyboard switch technology** from buckling-spring (IBM Model F/M, 1980s) → Cherry MX dominance (1990s-2010s) → modern hot-swap / optical / magnetic-Hall (2020s). The report is NOT a buying guide; it is a **chronological narrative + current-day taxonomy**.
>
> Ground in ≥ 120 sandbox URLs (≥ 60 cited). (A) `__SHOPPING__` ≥ 30 keyboard / switch products spanning the historical lineage (Cherry MX Red/Brown/Blue, optical Razer Yellow, Gateron, Kailh, Hall-effect Wooting / SteelSeries OmniPoint) — cite price + rating + feature_claim. (B) `__REDDIT__` ≥ 30 threads from /f/MechanicalKeyboards, /f/MechanicalKeyboardsActions, /f/keyboards, /f/ergodox, /f/olkb — capturing community wisdom on switch lifecycles, vintage IBM appreciation, modern hot-swap workflows. (C) `__WIKIPEDIA__` ≥ 25 articles, mandatory: Buckling spring, Cherry (keyboards), Hall effect, Optical switch, Computer keyboard, Tactile bump, Keycap, Membrane keyboard, Scissor mechanism, Topre — plus ≥ 15 more.
>
> Output a **chronological timeline** divided into 4 eras (Era 1: 1980s buckling-spring / Era 2: 1990s-2010s Cherry MX dominance / Era 3: 2015-2022 hot-swap explosion / Era 4: 2023+ analog/Hall era). For each era: ≥ 3 wiki articles defining the technology, ≥ 3 shopping products embodying it, ≥ 3 reddit threads showing community adoption. Add a **modern taxonomy** of switch types organized by actuation mechanism (mechanical contact / optical / magnetic) — a markdown nested list with each leaf citing a shopping product + a wiki article. End with a **"7 myths the community now considers debunked"** section (e.g., "MX Blues are best for typing" / "optical can't be tactile" / "Hall switches drift") — each myth cited with a wiki + reddit pair.
>
> Format: markdown links only. Begin with Era 1. No chain-of-thought.

**synthesis_requirements**:
- `eras`: 4(80s / 90s-10s / 15-22 / 23+),each w/ ≥ 3 wiki + ≥ 3 shopping + ≥ 3 reddit
- `taxonomy_branches`: ≥ 3 (mechanical / optical / magnetic),each leaf cited w/ shopping + wiki
- `debunked_myths`: 7,each w/ wiki + reddit pair

**wiki must-cite 增量**:Buckling spring, Cherry (keyboards), Hall effect, Optical switch, Computer keyboard, Tactile bump, Keycap, Membrane keyboard, Scissor mechanism, Topre(10 mandatory)

**21-item checklist**:
1. Are exactly 4 eras defined chronologically (buckling-spring / Cherry MX dominance / hot-swap / analog/Hall)?
2. Is each era given ≥ 3 wiki + ≥ 3 shopping + ≥ 3 reddit citations?
3. Is the chronology genuinely chronological (Era 1 → 4 in increasing time)?
4. Are at least 5 distinct switch families named across the timeline (buckling-spring, Cherry MX, Topre, optical, Hall)?
5. Does the modern taxonomy split switch types by actuation mechanism (≥ 3 branches)?
6. Does each leaf in the taxonomy cite a shopping URL + a wiki URL?
7. Are exactly 7 community-debunked myths enumerated?
8. Does each myth cite ≥ 1 wiki URL (technical grounding) + ≥ 1 reddit URL (community discussion)?
9. Are ≥ 30 shopping product pages cited spanning the timeline?
10. Are ≥ 30 reddit threads from ≥ 4 keyboard sub-forums cited?
11. Are ≥ 25 wiki articles cited?
12. Are all 10 mandatory wiki articles (Buckling spring, Cherry, Hall effect, Optical switch, Computer keyboard, Tactile bump, Keycap, Membrane, Scissor, Topre) cited?
13. Are ≥ 60 distinct URLs cited?
14. Is per-domain minimum met: ≥ 30 shopping, ≥ 20 reddit, ≥ 15 wiki?
15. Is the report 3500-8000 words / ≥ 25 paragraphs?
16. Are all cited URLs markdown-linked and sandbox-resolvable?
17. Does the report **avoid** producing a TOP-10 keyboard ranking (this is Timeline, not Recommendation)?
18. Does the report distinguish between "currently sold" products and "historically significant" products?
19. Does the report cite at least 3 vintage / discontinued products as historical anchors?
20. Does the report avoid chain-of-thought and start with Era 1?
21. Does each era include reddit-sourced community sentiment, not just product specs?

**adversarial wiki 候选**:
- `Cherry (keyboards)` — 注入虚构 "Cherry MX patent expired in 2008"(实际 2014)
- `Topre` — 注入虚构 "Topre is electromagnetic"(实际 capacitive rubber-dome hybrid)

---

### 2.11 dr_cross_deep_0011 — Sleep aids debunking (Debunking,新建)

**Intent**:

> Produce a Debunking / Fact-Check report auditing **5 popular sleep-aid claims**: (CL1) "10 mg melatonin is more effective than 0.3 mg for sleep onset", (CL2) "Wrist-worn sleep trackers (Fitbit / Garmin / Apple Watch) measure sleep stages accurately", (CL3) "Blue-light blocking glasses meaningfully improve sleep latency", (CL4) "Magnesium glycinate supplements consistently reduce insomnia", (CL5) "Weighted blankets reduce anxiety and improve sleep". Each receives a verdict ∈ {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}.
>
> Ground in ≥ 120 sandbox URLs (≥ 60 cited). (A) `__SHOPPING__` ≥ 36 sleep-aid products (melatonin SKUs of varying doses, sleep trackers, blue-light glasses, magnesium supplements, weighted blankets) — cite verbatim marketing claim + price + rating. (B) `__REDDIT__` ≥ 30 threads from /f/sleep, /f/insomnia, /f/Supplements, /f/Biohackers, /f/AskScience, /f/Fitness — user efficacy reports + dose comparisons + clinical-trial discussions. (C) `__WIKIPEDIA__` ≥ 25 articles, mandatory: Melatonin, Sleep, Polysomnography, Actigraphy, Circadian rhythm, Blue light, Magnesium deficiency, Weighted blanket, Insomnia, Placebo — plus ≥ 15 more.
>
> Output a 5-claim verdict table. Add a section **"dose-response curves where they exist"**: for the 2 claims with quantitative evidence (melatonin dose, magnesium dose), present what the literature actually says about dose response (cite wiki + reddit clinical-trial discussions). End with a **"sleep hygiene" cheat-sheet** (≤ 8 bullets) — non-product practices the literature supports — each cited.
>
> Format: markdown links. Begin with verdict table. No chain-of-thought.

**synthesis_requirements**:
- `claim_verdicts`: 5
- `min_evidence_per_claim`: 1 shopping verbatim quote + 1 reddit + 1 wiki + reasoning
- `dose_response_findings`: 2(melatonin, magnesium)
- `sleep_hygiene_checklist`: 6-8 bullets,each w/ ≥ 1 wiki citation

**wiki must-cite 增量**:Melatonin, Sleep, Polysomnography, Actigraphy, Circadian rhythm, Blue light, Magnesium deficiency, Weighted blanket, Insomnia, Placebo(10 mandatory)

**21-item checklist**:
1. Are exactly 5 sleep-aid claims defined upfront (melatonin dose / tracker accuracy / blue-light glasses / magnesium / weighted blanket)?
2. Does each claim receive a verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}?
3. Is the verbatim marketing claim quoted from a shopping URL for each claim?
4. Is ≥ 1 reddit thread cited per claim?
5. Is ≥ 1 wiki article cited per claim?
6. Does each claim include a 1-paragraph reasoning?
7. Are ≥ 36 shopping product pages enumerated across the 5 product categories?
8. Are ≥ 30 reddit threads from ≥ 4 sleep / supplement / biohacker sub-forums cited?
9. Are ≥ 25 wiki articles cited?
10. Are all 10 mandatory wiki articles (Melatonin, Sleep, Polysomnography, Actigraphy, Circadian rhythm, Blue light, Magnesium deficiency, Weighted blanket, Insomnia, Placebo) cited?
11. Are 2 dose-response analyses presented (melatonin and magnesium)?
12. Does the dose-response section cite both wiki definitions AND reddit user-trial discussions?
13. Is the sleep-hygiene cheat-sheet 6-8 bullets long?
14. Does each cheat-sheet bullet describe a NON-product practice (the report doesn't push more shopping)?
15. Does each cheat-sheet bullet cite ≥ 1 wiki URL?
16. Are ≥ 60 distinct URLs cited?
17. Is per-domain minimum met: ≥ 30 shopping, ≥ 20 reddit, ≥ 15 wiki?
18. Is the report 3500-8000 words / ≥ 25 paragraphs?
19. Are all cited URLs markdown-linked and sandbox-resolvable?
20. Are at least 2 of the 5 verdicts DEBUNKED, PARTIALLY_SUPPORTED, or UNDETERMINED?
21. Does the report avoid chain-of-thought and start with the verdict table?

**adversarial wiki 候选**:
- `Melatonin` — 注入虚构 "FDA approved 10 mg as standard adult dose"(实际 FDA 不审批 melatonin 作为药物;is dietary supplement)
- `Actigraphy` — 注入虚构 "Apple Watch validated against polysomnography to 95% accuracy"(实际 sleep-stage 准确率 60-80%)

---

### 2.12 dr_cross_deep_0012 — Smart home security protocol enumeration (Enumeration)

**Intent**:

> Produce an Enumeration / Catalog report cataloguing **every smart-home wireless protocol present on commercial smart locks, cameras, and hubs**, organised by **security model and threat surface**. The report is NOT a buying guide; it is a **comprehensive taxonomy** in which every protocol gets a security profile.
>
> Ground in ≥ 120 sandbox URLs (≥ 60 cited). (A) `__SHOPPING__` ≥ 40 smart-home device pages (smart locks, IP cameras, hubs, smart plugs, motion sensors) covering at minimum these protocols: Wi-Fi (WPA2/WPA3), Z-Wave, Zigbee, Thread, Matter, Bluetooth Low Energy, Z-Wave Plus, Insteon, Lutron Clear Connect — cite product URL + the protocol(s) it advertises + price. (B) `__REDDIT__` ≥ 30 threads from /f/homeautomation, /f/smarthome, /f/HomeKit, /f/homeassistant, /f/Hue, /f/AmazonEcho — discussions of pairing failures, security incidents, mesh-network reliability. (C) `__WIKIPEDIA__` ≥ 25 articles, mandatory: Wi-Fi Protected Access, Z-Wave, Zigbee, Thread (network protocol), Matter (standard), Bluetooth Low Energy, Mesh networking, Public-key cryptography, Internet of things, Pre-shared key — plus ≥ 15 more.
>
> Output a **protocol catalog table** with columns: protocol name / band / mesh-or-not / pairing model / encryption used / known vulnerabilities (cited wiki) / typical product cost (cited shopping) / community reliability sentiment (cited reddit). Add a **"threat-model decision tree"**: starting from the user's choice between cloud-routed vs local-only vs hybrid, walk to recommended protocols — each node cited. End with a section **"5 protocols / products to AVOID and why"** — each w/ shopping URL + reddit URL + wiki URL of the failure mode.
>
> Format: markdown links. Begin with the catalog table. No chain-of-thought.

**synthesis_requirements**:
- `protocol_catalog_rows`: ≥ 8 protocols
- `min_columns`: 7(name / band / mesh / pairing / encryption / vulnerabilities / cost / sentiment)
- `decision_tree_depth`: ≥ 3 levels(cloud vs local vs hybrid → recommendation)
- `avoid_findings`: 5 protocols/products to avoid,each w/ triple evidence

**wiki must-cite 增量**:Wi-Fi Protected Access, Z-Wave, Zigbee, Thread (network protocol), Matter (standard), Bluetooth Low Energy, Mesh networking, Public-key cryptography, Internet of things, Pre-shared key(10 mandatory)

**21-item checklist**:
1. Are ≥ 8 distinct wireless protocols catalogued (Wi-Fi, Z-Wave, Zigbee, Thread, Matter, BLE, Z-Wave Plus, Insteon, Lutron, etc.)?
2. Does the catalog table have ≥ 7 columns (name / band / mesh / pairing / encryption / vulnerabilities / cost / sentiment)?
3. Does each catalog row cite ≥ 1 wiki URL for the protocol's vulnerability discussion?
4. Does each row cite ≥ 1 shopping URL showing a product implementing it with price?
5. Does each row cite ≥ 1 reddit URL for community reliability sentiment?
6. Is a threat-model decision tree presented with ≥ 3 levels of decision (cloud / local / hybrid → protocols)?
7. Does each decision-tree node cite at least 1 source?
8. Are exactly 5 "protocols / products to AVOID" enumerated?
9. Does each AVOID entry cite ≥ 1 shopping URL (the bad product), ≥ 1 reddit URL (community report), ≥ 1 wiki URL (the underlying vulnerability)?
10. Are ≥ 40 shopping product pages cited spanning 5 device categories (locks / cameras / hubs / plugs / sensors)?
11. Are ≥ 30 reddit threads from ≥ 4 home-automation sub-forums cited?
12. Are ≥ 25 wiki articles cited?
13. Are all 10 mandatory wiki articles (WPA, Z-Wave, Zigbee, Thread, Matter, BLE, Mesh networking, Public-key cryptography, IoT, Pre-shared key) cited?
14. Does the catalog distinguish mesh-vs-star topology for each protocol?
15. Does the catalog name specific encryption (AES-128, ChaCha20, none, etc.) where applicable?
16. Are ≥ 60 distinct URLs cited?
17. Is per-domain minimum met: ≥ 30 shopping, ≥ 20 reddit, ≥ 15 wiki?
18. Is the report 3500-8000 words / ≥ 25 paragraphs?
19. Are all cited URLs markdown-linked and sandbox-resolvable?
20. Does the report **avoid** TOP-10 product ranking (this is Enumeration, not Recommendation)?
21. Does the report avoid chain-of-thought and start with the catalog table?

**adversarial wiki 候选**:
- `Z-Wave` — 注入虚构 "Z-Wave Plus uses AES-256"(实际 AES-128)
- `Matter (standard)` — 注入虚构 "Matter requires cloud account"(实际 local-only 是核心设计)

---

## 3. 实施顺序与产出物

| 步骤 | 产出 | 时间 |
|---|---|---|
| **3.1** 重写 task json (0003-0012) | `data/tasks/deep_research/cross_site_deep/dr_cross_deep_000{3..12}.json` 全部 task-specific intent | 已开始 |
| **3.2** 重写 checklists_deep.json (0003-0012) | 每 task 21 个 task-specific items | 已开始 |
| **3.3** 0011 / 0012 yaml + scrape 配置 | `configs/deep_topics/0011_sleep_aid_supplements.yaml`、`0012_smart_home_security.yaml` | 30 min |
| **3.4** 0011 / 0012 golden scrape (westd) | `data/golden/deep/dr_cross_deep_001{1,2}.json` | sandbox 1.5h |
| **3.5** 0003-0010 wiki must-cite 增量补 | 重新打 must_cite tag(无需 scrape,只调 weight + 加新 wiki must) | 1h |
| **3.6** 人工 URL 抽查工具 | `scripts/sample_urls_for_human_audit.py` | 30 min |
| **3.7** Verifier 加固 | URL reachability + URL coverage 已有;新增 task-specific checklist 引擎(每 task checklist 不同需 verifier 支持) | 1h |

## 4. 评分维度与人工只做的两件事

verifier 套件最终输出 `composite_v2_truthful` per (agent, task):

```
composite_v2  = reachability × quality
quality       = 0.40 · url_coverage + 0.40 · judge_pass_rate + 0.20 · spec_pass
url_coverage  = 0.55 · must_cite_recall + 0.30 · domain_balance + 0.15 · pool_coverage
judge_pass    = #PASS / 21 (task-specific checklist)
reachability  = #(HTTP 200 cited) / #cited
```

并行报 `composite_v1` (additive, 旧版本) 用于 F6 "ranking 翻转" 论证。

**人工 2 工作流**:
1. **leaderboard 阅读** — 跑完 `LEADERBOARD_DEEP.md`,人工挑出 "哪个 DR 最好"(通常是 composite_v2 top-1,但人可以推翻)
2. **URL 抽查** — `scripts/sample_urls_for_human_audit.py` 输出每 (agent, task) 抽 20 cited URL 的 markdown checklist。人勾选 PASS/UNCLEAR/FAIL(URL 真实 + 是否真支撑了 claim)。结果落 `data/results/human_url_audit_<agent>_<task>.json`,聚合为 leaderboard 一栏 `human_url_pass_rate`,作为 truthfulness 的 ground truth。

抽查样本估算:5 agent × 12 task × 20 URL = 1200 URL × ~30s/URL = 10h 人工 → 实际只抽 ≥3 个 agent 的 top-task,~3-4h 即可。

---

## 5. V2 (adversarial) tasks — top-player separability lever

**Status**: design 2026-05-21. Created by Workstream B (separability).
**Motivation**: after the 30-task v1 leaderboard, the top three agents
(camel-ai 1188, opencode 1250, claude-code 1352 in `data/results/deep_v3/leaderboard_deep.json`)
all have ±60-95 Elo bootstrap CIs that overlap with their adjacent neighbours.
camel-ai vs smolagents gap is 119 Elo at p=0.054 — close but no significance.
Composite saturation (top agents score >= 1130 on every pillar) and pillar
correlation (reach <-> quote_match Spearman ρ=0.91) compound the problem.

Arena-Hard (Li et al. 2024) reaches **87.4% pairwise separability** vs
MT-Bench's 22.6% by **adversarial task selection** — BenchBuilder filters
prompts by 7 hardness criteria and keeps only top-quartile-difficulty items.
We adopt that for v2: add 20 tasks that stress the three orthogonal pillars
the v1 grid under-tests (depth, rigor, coverage) and that demonstrably
*flip the leaderboard ordering* under at-leaderboard agents.

### 5.1 Three new task families

| Family | Stress pillar | Mechanism | Why it discriminates |
|---|---|---|---|
| **Causal / Debunking heavy** | `rigor` | Force counter-evidence retrieval against a popular marketing claim. Pre-seed at least 3 contradictory wiki + reddit sources in golden pool. Weak-rigor agents (cited the marketing page only) fail the verdict; strong-rigor agents surface the counter-evidence and reach a DEBUNKED / PARTIALLY_SUPPORTED verdict. | The v1 grid already has Debunking tasks (0006-0008, 0011), but the verdict columns are loose — saturation at the top. v2 raises the bar: each claim has **≥ 1 wiki must-cite that contradicts** the marketing page, and the rubric explicitly penalises any verdict not backed by the contradicting URL. |
| **Synthesis-under-contradiction** | `depth` | Two pre-curated source clusters disagree on the same fact (e.g. reddit experience says X, wiki / academic says ¬X). Agent must surface **both** sides and reconcile (acknowledge the tension or pick a side with reasoning). | Single-source / surface searcher always wins one cluster, misses the other → flat one-sided summary → fails depth checklist items. Multi-hop / reasoning-trace agents (claude-code, camel-ai) surface both. **This is the lever that should split rank 1 from rank 2 most cleanly.** |
| **Long-tail recall** | `coverage` | Golden URL pool oversampled with deliberately niche items (deep-page wiki articles, low-traffic subreddit threads, long-tail product SKUs on Magento). The surface searcher (top results of the obvious query) misses them; the agent that uses a real exploration strategy lands them. | v1 must-cite recall plateaus at ~0.6 for top agents because the pools are biased toward popular URLs. v2 inverts that: ≥ 60% of must-cite items are reachable only via 2+ hops or via non-obvious search terms. Forces the **breadth + recall** lever that current top-agents tie on. |

### 5.2 v2 task budget

20 task specs total, balanced across the three families and across sandbox sites:

| Family | Count | Magento (shopping) anchor | Postmill (reddit) anchor | Kiwix (wikipedia) anchor |
|---|---:|---:|---:|---:|
| Causal / Debunking heavy | 7 | 4 | 3 | 7 (all use wiki for verdict ground truth) |
| Synthesis-under-contradiction | 7 | 3 | 7 | 5 |
| Long-tail recall | 6 | 6 | 4 | 6 |
| **Total**         | **20** | **13** | **14** | **18** |

(Each task is cross-site by design, so site counts overlap.)

### 5.3 Design recipe (per task)

Five things every v2 spec carries; the build script fans them into the
existing `cross_site_deep` JSON schema:

1. `family` — one of `{causal, contradiction, long_tail}`.
2. `topic` — short slug.
3. `must_cite_pool` — initial seed (≥ 5 URL strings). Build script expands
   to the full 120-130 must-cite golden on the westd scraper, but **the
   contradicting / niche items in this seed list are non-negotiable**.
4. `expected_dim_stress` — list of `{depth, rigor, coverage}` indicating
   which pillar(s) the task is designed to discriminate on.
5. `adversarial_rationale` — one-sentence justification: why this task
   should split top agents. Reviewed by parent before scrape.

### 5.4 Pre-screen protocol (small adversarial pilot)

Before promoting any v2 task into the full leaderboard pool, run a
**3 agents × 5 tasks** pilot to verify it actually discriminates:

1. Pick 5 v2 candidates (from `V2_ADVERSARIAL_TASKS.json`) per family.
2. Run **3 agents** — one expected winner (camel-ai or claude-code), one
   expected middle (smolagents or deerflow), one expected loser (ldr or
   langchain-odr) — through each candidate task on westd.
3. Score the 15 runs with the existing v2_truthful composite + v3 pillars.
4. **Keep**: tasks where the score variance across the 3 agents is in the
   top-50% (median across all candidates). Drop the rest.
5. From the surviving 4-5 tasks per family, expand to the full 13-agent
   matrix. The full-matrix runs go into the v3 leaderboard alongside v1.

Target: after the pilot prunes the weakest candidates and the full matrix
runs, the new pairwise separability (fraction of agent pairs with
non-overlapping CIs) should rise from current ~45% to **≥ 65%**
(intermediate target — Arena-Hard's 87% is the long-term goal).

### 5.5 Pre-registration

The 20 specs in `V2_ADVERSARIAL_TASKS.json` are pre-registered before any
agent runs. We do **not** later swap in tasks that happen to flatter
camel-ai or claude-code. The drop / keep decision in step 5.4 #4 uses
**variance** as the criterion, not "the task we like ranks our favourite
agent #1". Variance is direction-agnostic — a task that splits ldr from
ii-researcher counts as much as one that splits claude-code from opencode.

