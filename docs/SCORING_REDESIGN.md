# 打分重做:简单、抗刷分、与人类对齐

> 状态:设计草案 v1(2026-06-02)。依据:两路外部调研(DR 专用 + 通用 LLM 评测)+ 本仓库打分审计。
> 触发:用户指出 claude-code/opencode 分虚高、打分太糙太复杂,要求"调研别人怎么做、做简单做好"。
> 原则:本文只设计 + 改打分代码(离线);**替换线上榜需要沙盒真跑 + 你拍板 + changelog**。

---

## 0. 审计先说结论:现状为什么不公平、不简单

1. **线上 top-2 是假数据。** `build_deep_leaderboard_v3.py` 默认只跑 `--dry-run`,用 `_synthesize_score_for_agent_task` 编造分数;`frontend/lib/data/load-leaderboard.ts` 优先加载这个合成文件,发布的 `web/dist/api/leaderboard` 每行带 `synthetic_placeholder: true`;还有硬编码兜底把 claude-code/opencode 钉成前二。opencode 在真实数据里**根本没有任何报告/分数文件**。
2. **唯一真排名(deep_v3)奖励"灌引用"而非接地。** `url_coverage = 0.55*must_cite_recall + 0.15*pool_coverage + 0.30*domain_balance`,其中 `domain_balance` 是纯数量(每域凑够条数即满分),再加 `cited>=60` 的数量门。claude-code 引 155 条、必引命中仅 6/121(recall 2.8%)却拿高 coverage。
3. **小 bug:** `internal_consistency` 在无法判定时默认 1.0(数据缺失反给满分)。
4. **太复杂:** 25+ verifier、多套并存的 composite(V2 / V3 / V4 / v3.1 final),没有一套是"简单且被验证过"的。

## 1. 别人怎么做的(调研要点,带出处)

- **DeepResearch Bench(2506.11763)= 黄金模板**:RACE(报告质量,**4 个固定维度** Comprehensiveness/Insight/Instruction-Following/Readability,**对参考报告**打分)+ FACT(接地,**两个数**:Citation Accuracy = 被支撑的引用/总引用;Effective Citations = 每篇被支撑引用数)。**质量与接地分开,绝不合成一个数。** RACE 与人类一致 92.7%,FACT Pearson 0.88。
- **DeepResearch Bench II(2601.08536)**:更简单,**专家二元 rubric,task 分 = 通过率**(纯比例,无权重可调),3 维(Recall/Analysis/Presentation)。
- **DR-Arena(2601.10504)**:不用 rubric,**pairwise 对战 + Bradley-Terry/Elo**,与人类榜 Spearman 0.94。
- **Arena-Hard-Auto**:**对固定基线 pairwise** + 位置交换 + **style/length 控制** → 分辨力 87% vs MT-Bench 22%;style-controlled 后与人类 98.6%。
- **AlpacaEval 2.0**:**长度受控胜率**(回归掉长度),相关 0.94→0.98,杀掉"啰嗦刷分"。
- **接地度量(ALCE/FActScore/SAFE/RAGAS)殊途同归**:**支撑单元 / 总单元**(NLI 蕴含或检索判定)。加引用不支撑 → recall 降;加垃圾引用 → precision 降。**天然抗"灌数量"。**
- **LLM-judge 最佳实践**:pairwise > 绝对 1-10;位置交换取双向一致;给参考答案;跨家判分;多采样;**永远报一个人类相关性数**作为合法性证明。

## 2. 我们的新打分(推荐,与上面一致,且贴合我们已有的 truth-gate 卖点)

**一句话:两个正交的数 + 一道门,维度封顶,绝不奖励数量,产出带人类相关性验证。**

### 维度 A:接地 Grounding(确定性 + 轻量 NLI,难刷)
- `citation_precision` = 被支撑的(url, claim)对 / 抽取出的总对(proof-of-fetch:被引 URL 必须真抓取过 + quote/claim-NLI 判支撑)。
- `must_cite_recall` = 命中的 golden 必引事实 / 总数(或 fact_kg 召回)。
- `grounding = F1(precision, recall)`。**删掉 domain_balance、删掉 cited>=60 数量门。** 我们已有 quote_match / claim_nli / fact_kg / url_reachability 的零件,收敛成这两个数即可。

### 维度 B:质量 Quality(LLM judge,用我们已重做好的 pairwise)
- **对参考报告做 pairwise**(Arena-Hard 模式),位置交换 + 跨家 + 多采样 + **长度受控**,→ Bradley-Terry/Elo + bootstrap CI。
- 我们已实现 `verify_pairwise` 和 `battle(dimension=...)`,直接复用。depth/rigor/style/checklist 不再各自加权进总分,降级为**诊断维度**(或并入 pairwise 的几个比较面)。

### 组合:GATE(就是我们的 truth-gate)
- 报告先过 **grounding 下限**;不过门 → 出局(编造引用 → 0)。过门后按 **Quality Elo** 排名。
- 展示层给两个数(Quality Elo + Grounding),像 RACE/FACT 那样分开,而不是合成一个可刷的 composite。

### 长度控制
- 回归掉长度(AlpacaEval LC)或封顶;**绝不奖励原始字数/引用数**。直接消灭 claude-code 那种"72k 字 + 155 引用"的虚高。

### 合法性验证
- 产出一个**人类(或强参考)相关性数**;目标 >0.85。当前用 lite 自洽 + 小样本判别力先顶着,真人类标注到位再算 kappa。

## 3. 迁移计划(分阶段,先离线后上线)

- **P1(离线,现在做,不动线上):** (a) 新建简单打分模块:grounding 两数 + quality pairwise-BT;(b) url_coverage 去掉 domain_balance/数量门,must_cite_recall 主导;(c) 修 internal_consistency 默认 1.0;(d) 单测 + 小样本判别力(lite)。
- **P2(需沙盒 + 你拍板 + changelog):** 用新打分对真实报告**真跑一遍**,产出**真实**榜替换合成占位;`load-leaderboard.ts` 去掉合成兜底、拒绝发布带 `synthetic_placeholder` 的文件;写 changelog,push。
- **P3:** 接 30+ 任务 x 更多 agent + 显著性;真人类标注算 kappa。

## 4. 红线
- 线上替换前不动部署;合成榜的修复属于 P2(要沙盒真跑出真分)。
- 改打分要在 `data/changelog.json` 记录后才上线(CLAUDE.md 硬规则)。
- 保留 truth-gate 卖点(接地为门),这与外部调研完全一致,是我们的差异化。
