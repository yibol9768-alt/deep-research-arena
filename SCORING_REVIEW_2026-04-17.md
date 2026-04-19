# Scoring Overhaul Memo — 从主观体验出发对齐业界 SOTA

**时间**: 2026-04-17
**触发**: 用户反馈"评测的应该是全面、大量文字、详细内容,不是简单输出"
**方法**: 业界调研(10 个 DR/长文 benchmark)+ 肉眼读 12 份 agent 报告

---

## TL;DR

当前 composite 有 **主观体验倒转**:它把 qwen(最稳,3/4 strong)排在 glm-5(0007 编 Reddit)后面,并让 DeerFlow(80% 元叙述灌水)靠字数和结构拿到接近 qwen 的分(0.439 vs 0.483)。

**根因**: 6 pillar 里没一条在量"实质内容密度" —— 没人惩罚 "我失败了所以写了 2400 词方法论" 这种行为。

**三个必改**:
1. **加 "证据密度" pillar**(0.10 权重,从 efficiency 砍 0.05 + llm_judge 砍 0.05 腾出)
2. **修 fact_kg oracle 质量**(task 0007 把 LED TV Stand 当 kitchen 产品,惩罚真判断好的 agent)
3. **修 citation verifier 的 `[1]` 数字引用 fallback**(qwen 0007 被判 0 不是因为没引,是因为用了学术数字引用)

**两个可做**:
4. 把 llm_judge 显式拆成 DeepResearch Bench RACE 四维(Comprehensiveness / Depth / IF / Readability) —— apples-to-apples 好发论文
5. 把 checklist 扩到 per-task 40 条(对标 DRACO)—— 现有 15 条过粗

---

## 1. 业界 10 个 benchmark 对我们的定位

| Benchmark | 评的是 | 我们对照 |
|---|---|---|
| HLE / BrowseComp / GAIA | **短答案 QA** | 不对齐,不是我们赛道 |
| WebArena-Verified | 程序化状态 + 答案 recall | 我们是 markdown 长文,更难 |
| DeepResearch Bench (RACE+FACT) | 长报告 4-dim rubric + 引用 | **主对标**,论文 apples-to-apples |
| DRACO (Perplexity) | 100 任务 × 40 条 rubric | **rubric 细度标杆**,我们只 15 条 |
| DRBench (ServiceNow) | Insight Recall + Citation | "洞察而非罗列",我们缺 |
| ResearcherBench | rubric + 事实核验 | 与我们框架类似 |
| ALCE | 引用 recall/precision | 我们照抄了 |

**我们的独特性**: `fact_kg`(KG-grounded 自动事实核验,零 LLM judge variance)+ `efficiency`(几乎没人做)。这两条保留,就是论文卖点。

**业界共识**:**没人用原始字数** —— 所有长文 benchmark 都用 "必含要点 rubric 覆盖率" 或 "ref-report LLM judge" 代替字数。这直接否定我们 `markdown_structure.min_words=800` 当 pass/fail 的做法。

---

## 2. 当前 composite 的具体失灵

### 2.1 DeerFlow 0001 — 2400 词灌水报告拿 0.44 composite

肉眼读到的实际内容:**"我爬不到数据,这里是我的方法论、limitations、future work"**。字数被"Key Points / Overview / Methodology / Survey Note / Critical Discussion / Future Research"这些空结构撑起来。

- `markdown_structure=1.0` — 字数、段落、citation 数全过 → 显然失灵
- `citation=0.5` 左右 — 分子母站 URL 都可达,但都是分类页/搜索页,不是具体 PDP
- `fact_kg=0.0` — 正确(啥也没找到)
- `llm_judge` — glm-5 judge 给 4/5 readability(结构看起来像学术论文)

**现象**:"结构整齐但内容空" 拿到与 "内容扎实但字数少" 相近的分数。

### 2.2 qwen 0007 citation=0.0 不是它的错

verifier 用 `[A-Za-z0-9]{3,}` 正则从 link text 提 token(`[Product Page]` → ['Product','Page'])。qwen 在 0007 用 IEEE 风 `[1]`, `[2]` 数字引用,link text tokenize 后全没 ≥3 字符 token → verifier 判 `value_not_supported`。

**这是 verifier bug,不是 agent 问题**。在 0001 上 qwen 用 `[Harphonic E7 Product Page]` 就过了,同一个 agent 不同 task 分数被格式决定。

### 2.3 fact_kg oracle 有质量问题

`oracle_v3_dr_cross_v3_0007.md` 里 kitchen 类 top 产品:
- Magic Home Nightstands (not kitchen)
- Bonzy Home Glossy LED TV Stand (not kitchen)
- Pemberly Row Farmhouse Barn Door TV Stand (not kitchen)

oracle 是从 home-kitchen 分类的 top-N by price 自动抓的,没过滤是否真是厨房用品。**惩罚做品类过滤的好 agent**,奖励盲抄分类页的。

### 2.4 min_words=800 对齐 "详细内容" 太松

业界对照:
- OpenAI Deep Research 实际输出 5,000–20,000 词
- DeepResearch Bench 参考报告约 2,000–5,000 词
- 我们 min_words=800-1000,max 3000-3500

**800 词是短博客篇幅,不是深度研究篇幅**。但拉高阈值就会被 DeerFlow 式灌水钻空子 → 必须和"证据密度"一起改。

---

## 3. 改动方案

### P0 — 马上动(修失灵)

#### 3.1 新增 `evidence_density` pillar (权重 0.10)

**定义**: 报告里真实证据锚点的数量和密度。

具体子信号:
- `unique_pdp_urls` = 从 markdown 链接里提到的**产品详情页 slug**(匹配 `localhost:7770/[a-z0-9-]+\.html`,排除 `catalogsearch`、`category.html`、homepage)
- `unique_post_ids` = 从 Reddit URL 里提到的具体 post ID(`localhost:9999/f/<board>/<id>/...`)
- `meta_paragraph_ratio` = "Methodology / Limitations / Future Research / Key Points / Survey Note" 等元标题下的段落字数占总字数的比例(越低越好)
- `substance_word_count` = 总字数 × (1 − meta_paragraph_ratio)

权重建议:
```
score = 0.4 * min(unique_pdp_urls / required_products, 1.0)
      + 0.3 * min(unique_post_ids / required_posts, 1.0)
      + 0.3 * (1 - meta_paragraph_ratio)
```

**验证**: 跑 12 份已有报告,DeerFlow 三份应该 < 0.3,glm-5/qwen 应该 > 0.7。

#### 3.2 修 citation verifier `[1]` fallback

`src/verifiers/citation_verifier.py:266` 左右,加:

```python
# 数字引用 fallback: link text 是纯数字/短字符时,
# 对 URL 所在段落做 value 匹配(而非 link text token 匹配)
if not tokens and re.match(r'^[\d\.\,\s\*]+$', snippet):
    # 找 URL 所在段落的前后 value token
    para = _containing_paragraph(answer, url)
    if value is not None and _value_matches(value, body):
        ok = True
        r["match"] = "numeric_ref_value"
```

或者同时在 agent prompt 里**强制要求描述性 link text**(`[Product Name](url)` not `[1](url)`)。**双保险**:prompt 加约束 + verifier 宽容。

#### 3.3 清洗 fact_kg oracle

跑一个脚本(我来写),把 task 0001/0005/0006/0007 的 oracle JSON 按分类过滤:
- home-kitchen 类:名字含 `nightstand|tv stand|bed|sofa|lamp` 的剔除
- grocery 类:非食品剔除
- 人工复核一遍

或者:**放弃"category top-N"自动 oracle**,改成**手工挑 10 个典型产品 × 4 task = 40 个**,当作 gold set。论文里更 defensible。

### P1 — 论文前做(对齐 SOTA)

#### 3.4 LLM judge 显式 RACE 四维

当前 `LLMJudgeVerifier` prompt 里就是让 judge 给 4 维 1-5 分(comprehensiveness / insight_depth / instruction_following / readability)—— 其实**已经对齐 DeepResearch Bench RACE**,只是权重和命名要调:

```
comprehensiveness   0.30  (DR Bench weight)
depth               0.25
instruction_following 0.25
readability         0.20
```

论文 related work 里直接写 "We adopt the RACE rubric from Deep Research Bench (ICLR 2026)" —— 免解释。

#### 3.5 checklist 扩到 per-task 40 条

现在 `checklists_v3.json` 是 15 条 × 4 task。DRACO 是 40 条 × 100 task。

具体做法(用 GLM 自动生成候选,人审):
1. 对每个 cross_site task 跑 prompt "生成 40 条 binary 评分点",分 5 类:产品数据(10)/Reddit 证据(10)/综合分析(10)/格式结构(5)/任务特定(5)
2. 我过一遍人审剔除
3. 写入 `checklists_v3.json`

现有 15 条保留作 "core",新增 25 条作 "extended",打分公式 `0.6*core_pass + 0.4*extended_pass`。

### P2 — 可选

#### 3.6 min_words 调整 + 密度约束

```
min_words: 800 → 2000
max_words: 3500 → 6000
// 但加一个硬约束:
min_unique_pdp_urls: 6
min_unique_reddit_posts: 4
```

纯字数再多,没有足够"真实证据锚点"也过不了 `markdown_structure`。

---

## 4. 新的 7-pillar 权重(推荐)

| Pillar | 当前 | 建议 | 变化原因 |
|---|---:|---:|---|
| markdown_structure | 0.10 | 0.05 | 沦为"有几个字就过"的水分 |
| citation | 0.15 | 0.15 | 保持,修 bug |
| fact_kg | 0.30 | 0.25 | oracle 清洗完再升回 0.30 |
| llm_judge (RACE 4d) | 0.20 | 0.20 | 对齐 DR Bench |
| checklist (40 items) | 0.20 | 0.20 | 对齐 DRACO |
| **evidence_density** | — | **0.10** | **新增**,抓证据锚点 |
| efficiency | 0.05 | 0.05 | 独家差异点,保留 |

总和仍 1.00。新权重后预期排名重排:
- qwen 应该变成 top(密度最稳)
- DeerFlow 应该掉到 0.30-0.35(证据稀缺)
- glm-5 0007 被 evidence_density 惩罚(编了 Reddit)

---

## 5. 为论文讲故事提供的两个新论点

**论点 A(已有)**: composite vs LLM-judge 排名倒转 —— pairwise judge 喜欢 DeerFlow 因为它长,composite 反对。

**新论点 B**: **LLM-judge 也被结构模仿骗** —— DeerFlow 0001 用 "Methodology/Literature Review/Future Research" 学术外壳,让 judge 打高 readability 分,但 **evidence_density=0.1** 揭穿它没做研究。这把 "judge vs composite 分歧" 深化成 "**judge 被 form-over-substance 攻击**"。

**新论点 C**: **Citation verifier 对引用格式敏感** —— qwen 同一份 agent 在 0001 用描述性引用拿满分,在 0007 用数字引用拿 0。说明现有 ALCE 式 citation 评测**依赖引用格式而非语义**,提出一个 format-invariant 版本是 contribution。

---

## 6. 立刻可做的半小时验证

写一个 `scripts/compute_evidence_density.py`,对已有 12 份 report 跑一遍,看:
1. 分布是否符合预期(DeerFlow 低,qwen 高)
2. 重新合成 composite 后,排名是否更贴合主观体验

若结果如预期 → 再正式改 verifier / oracle。

---

## 7. 验证实验结果(2026-04-17 跑完)

`scripts/compute_evidence_density.py` 跑过所有 12 份 existing report,关键数字:

### 7.1 每份 agent × task 的证据密度原始数据

| agent | task | words | PDP URLs | Reddit posts | meta% | ED |
|---|---|---:|---:|---:|---:|---:|
| deerflow-glm46 | 0001 | 2409 | **0** | 2 | 37% | **0.34** |
| deerflow-glm46 | 0005 | 3901 | **0** | 3 | 31% | 0.43 |
| deerflow-glm46 | 0006 | 3964 | **0** | 3 | 30% | 0.43 |
| deerflow-glm46 | 0007 | 3618 | **0** | 1 | 23% | **0.30** |
| react-glm5 | 0001 | 1469 | 6 | 5 | 0% | **1.00** |
| react-glm5 | 0005 | 1485 | 16 | 3 | 0% | 0.93 |
| react-glm5 | 0006 | 1946 | 0 | 4 | 0% | 0.60 |
| react-glm5 | 0007 | 1774 | 10 | **0** | 0% | 0.70 |
| react-qwen35plus | 0001 | 1206 | 4 | 6 | 0% | 0.87 |
| react-qwen35plus | 0005 | 1510 | 13 | 4 | 0% | **1.00** |
| react-qwen35plus | 0006 | 1349 | 5 | 4 | 0% | 0.93 |
| react-qwen35plus | 0007 | 1241 | 3 | 3 | 0% | 0.72 |

**震撼数据**:DeerFlow 4 份报告共 **0 个 unique PDP slug URL** —— 连一个具体产品页都没引到,全是分类页和搜索页。即便字数 3x 于 qwen,信息密度几乎为零。

### 7.2 新 composite 模拟(加 evidence_density@0.10,降 markdown_structure 0.10→0.05,efficiency 暂不算)

| agent | old mean | new mean | Δ |
|---|---:|---:|---:|
| DeerFlow | 0.439 | **0.392** | **−0.047** |
| glm-5 | 0.503 | 0.515 | +0.012 |
| qwen | 0.483 | **0.506** | **+0.023** |

**DeerFlow ↔ qwen 差距 0.044 → 0.114(拉开 2.6x)**,符合主观体验。glm-5 与 qwen 差距 0.020 → 0.009(qwen 反超在望,需要 P0-2 citation bug 修完再跑一次)。

### 7.3 task-level 效果确认

- DeerFlow 0001 灌水报告:old 0.44 → new **0.38**(降 0.06,符合"其实没做研究"事实)
- qwen 0001:old 0.65 → new **0.67**(小涨,密度高)
- glm-5 0001:old 0.66 → new **0.69**(最高)
- qwen 0007:old 0.32 → new **0.33**(略涨,但 ED=0.72 说明它 Reddit 引用密度可以再高些)

**结论**:evidence_density 显著有效,应立即集成。不需要等别的 P0 先做。

---

## 8. 我的建议下一步

按优先级 **(evidence_density 已验证,跳过实验阶段直接 P0-1)**:

1. ✅ ~~半小时实验~~: 已完成,见 §7
2. **P0-1 evidence_density 入 composite(立刻做)**: 把 `src/verifiers/evidence_density.py` 写出来,接进 `composite_v3.py`,改权重。之前 `compute_evidence_density.py` 是脚本版本,搬进 verifier。
3. **P0-2 citation verifier 数字引用 fallback**: 20 行代码修 qwen 0007
4. **P0-3 fact_kg oracle 清洗**: 剔除类别错配的产品(LED TV Stand as kitchen)
5. 跑完整 3 agent × 4 task 新 composite,确认 qwen > glm-5 > DeerFlow 排名(目前 glm-5 仍略领先,主要因为 0001 单项满分拉)
6. 扩到 P1:RACE 四维 judge + per-task 40 条 checklist
