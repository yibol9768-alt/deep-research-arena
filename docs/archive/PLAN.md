# Deep Research Benchmark — 进度 & 规划

**项目**:刘奕博
**最后更新**:2026-04-19 凌晨(Phase 7–8:Shim + 多框架 Arena + DeepSeek judge + 107 task)
**目标(总)**:构建一个**真实网站沙盒 + Deep Research 任务 + 确定性评分 + Arena Elo 排位**的 AI Agent 评测框架,用于量化比较不同多智能体系统在 Deep Research 上的能力。最终产出:**学术论文 + 可复现 benchmark**。

---

## 0. 一句话现状

> **v2(已上线,留作历史对照)**:2 个真实沙盒站、9 条 DR 任务、6 pillar 评分、3 种 Elo 排位、4 agent × 9 task × 27 battles/agent MEGA Arena 跑完。
>
> **v3(跨站任务上线)**:Phase 1-5 完成 + **Phase 6 跨站扩展**:4 个容器全部运行(Shopping/Reddit/GitLab/Shopping Admin) + **4 条跨站 Deep Research 任务**(dr_cross_v3_0001~0004,跨 2-3 个站) + 统一多站适配器(unified_adapter.py) + 140 条 KG 三元组 + 60 条 DRACO rubric + ReAct agent 支持 gitlab/admin 工具 + DeerFlow 跨站适配。**3 个 ReAct 模型 + DeerFlow × 4 跨站任务 Arena 跑分中**。
>
> **Phase 7–8(2026-04-18 → 04-19)**:(a) **Shim 统一搜索层**(FastAPI :8081,Tavily+Firecrawl 兼容,零代码接任何 DR 框架);(b) **8 agent × 4 task MEGA Arena**(React-qwen35plus/glm5 + DeerFlow 三版 + GPT-Researcher + CAMEL-AI + smolagents);(c) **DeepSeek V3.2 judge**(self-preference 解决,P0-1);(d) **Citation NLI entailment** (P0-2);(e) **107 task**(87 consumer + 20 scholarly/policy,P0-3);(f) bootstrap 95% CI + permutation rank test;(g) `fact_kg` oracle v2(intent-aware filter,拒绝误标 $607 printer in $500 budget)。排名:react-qwen35plus 1172 Elo > gpt-researcher 1158 > react-glm5 1138 > deerflow-shim 1019 > camel-ai 983 > deerflow-new 939 > deerflow 854 > smolagents 737。
>
> **核心 v2 发现**:加 reddit 后 DeerFlow 优势从 +122 缩到 +5 Elo(GLM 内容安全在长 prompt 上拦了 DeerFlow);glm-4.6 反超到第 2;**LLM judge 暴露 length-bias**(glm-4.5 简洁回答被 judge 排第 1,composite 排第 4)→ v3 用 `fact_kg` 客观信号化解,`llm_judge` 权重降至 0.20。
>
> **Phase 7-8 核心发现**:(1) DeerFlow 原本"弱"是 custom adapter 把搜索结果截断 5000 chars 导致,走 shim 后 +162 Elo,说明**评测不能对框架降级**。(2) smolagents 排第 8 / 0 胜,根因是 GLM-4.7 输出 `</code>` 代替 `<end_code>` 哨兵,code parser 每步失败,报告完全幻觉 — 暴露**智能体格式协议与模型训练格式耦合**。(3) ODR/dzhng 装好但 GLM OpenAI-compat 不返 JSON mode,langchain `with_structured_output` + ai-sdk `generate-object` 双双 ValidationError — **国产模型 JSON schema 兼容性是开源 DR 框架普遍盲点**。
>
> **v3 vs 业界**:我们的路线 = DeepResearch Bench 的"LLM 参考报告"(oracle 生成 markdown)+ DRACO 2026 的"二值 rubric"(15-item checklist)+ LiveDRBench 的"结构化可验证事实"(KG 三元组)的交集。独家优势是**沙盒 DB 直连做 fact verifier**,零方差 / 零成本 / 零人工标注。再加 Phase 7 的 **Shim 层 + 8 agent 多框架 Arena**,定位明确落在 **BrowseComp-Plus(静态语料库)与 WebArena-Verified(事务性沙盒)之间**(见 `PAPER_POSITIONING.md`)。

---

## 1. 时间线(顺序)

| # | 里程碑 |
|---:|---|
| 1 | 187 条 WebArena 原版 shopping 任务归档;Runner + 基础 verifier |
| 2 | Shopping Docker 部署到 westd;端到端 smoke task 21 score 1.0 |
| 3 | Stage B 5 条 shopping DR 任务;Oracle 5/5 PASS;GLM-5.1 ReAct 基线 0/5 |
| 4 | DeerFlow v1 接入;shop_adapter monkey-patch;首次多 agent 报告 |
| 5 | **Scoring v2**(ALCE 双指标 / 4 维 LLM judge / Efficiency / Composite) |
| 6 | **Arena Elo**(Composite + Pairwise judge + Per-pillar) |
| 7 | **DRACO checklist verifier**(替换 comprehensiveness 占位) |
| 8 | 3 个 GLM ReAct variant(5.1 / 4.6 / 4.5)+ DeerFlow = 4-way Arena |
| 9 | 5 task × 4 agent × 15 battle **最终 Arena**(DeerFlow 1097 ≫ ReAct ~960-975) |
| 10 | Reddit (Postmill) 沙盒就位,容器 healthy,Mac tunnel 9999 ✓ |
| 11 | 4 条 reddit DR 任务 + Oracles + Checklists(4/4 PASS) |
| 12 | ReAct agent **泛化**(支持 site-aware tool registry,shopping + reddit 共用) |
| 13 | 3 GLM ReAct × 4 reddit task = 12 runs |
| 14 | DeerFlow `reddit_adapter.py` —— DeerFlow 也能跑 reddit |
| 15 | **MEGA Arena**:9 task × 4 agent × 27 battles/agent + 全量评分 + pairwise judge |
| 16 | **GitHub 上传**:`yibol9768-alt/deep-research-arena`(private),302 文件,scrub 5 处 token,21 测试绿 |
| 17 | DeerFlow vs 单 agent **逐字对比文档**(`COMPARE_dr_shop_0001.md`)→ 发现 JSON 格式抹平研究深度 |
| 18 | Plan mode + 调研业界 Deep Research 共识(DRACO/RACE/FActScore/ALCE)→ **v3 设计** |
| 19 | **v3-Phase 1 完成**:`MarkdownReportSpec` + `DeepResearchTaskV3` schema + `v3_TASK_SPEC.md`(31 测试绿) |
| 20 | **v3-Phase 2 完成**:8 条 v3 task + 8 oracle + 8 markdown 报告 + 8 KG 三元组真值(共 193 三元组) |
| 21 | **v3-Phase 3 完成**:KG fact verifier 全字段上线 —— `src/golden/{db_connect,db_schema_map,db_verifier,triple_extractor}.py` + `src/verifiers/fact_kg_verifier.py` +  16 个测试(含活体 DB 回环)。8 oracle 聚合 recall **96.9% (187/193)**,bogus 答案 recall = 0,满足 ≥0.8 / <0.3 验收 |
| 22 | **v3-Phase 4 完成**:`markdown_report_verifier`(min_words / min_paras / min_citations / min_pages) + v3 checklist 扩到 15 条/任务(120 条 DRACO 二值 rubric) + `composite_v3.py`(fact_kg 0.30 主力 + checklist 0.20 加重),27 个测试绿 |
| 23 | **v3-Phase 5 完成**:`bench_v3.py` + ReAct agent 双提示(`_SYSTEM_PROMPT` JSON mode / `_SYSTEM_PROMPT_V3` markdown mode,按 `markdown_spec` 存在自动切换) + dry-run 8-oracle pipeline 跑通(0.38–0.55 composite,符合确定性 pillar 上限) |
| 24 | **v3-Phase 6 跨站扩展**:GitLab(8023) + Shopping Admin(7780) 容器启动;清理 24GB 无关镜像;4 条跨站 DR 任务(shopping+reddit / gitlab+reddit / 3 站三角) + 140 KG 三元组 + 60 DRACO rubric |
| 25 | **统一多站适配器**:`integrations/deerflow/unified_adapter.py` + `envs/gitlab/scrape.py` + `envs/shopping_admin/scrape.py`;ReAct agent 加 gitlab_search/gitlab_issues/gitlab_browse/admin_browse 工具 |
| 🟡 进行中 | 3 ReAct 模型 + DeerFlow × 4 跨站任务 Arena 跑分中 |
| 26 | **Phase 7 — Shim 层(统一 Tavily/Firecrawl-compat)**:`integrations/search_shim/` FastAPI 在 :8081 暴露 Tavily `/search` + Firecrawl v1/v2 `/v1|v2/search` `/v1|v2/scrape` + kiwix Wikipedia,后端统一到 Magento + Postmill + kiwix。**任何 DR 框架零代码可接**(只需 `TAVILY_API_KEY=anything` + `TAVILY_API_URL=http://shim/...` 或 monkey-patch `tavily.TavilyClient.base_url`) |
| 27 | **Phase 7 — 多框架 Arena**:DeerFlow 通过 shim 而非 custom adapter(+162 Elo)、GPT-Researcher、CAMEL-AI、smolagents 接入;ODR/dzhng/LDR/STORM 接入受阻(文档化)。3 个 ReAct 变体(glm5 / qwen35plus / glm46-new)+ DeerFlow 三版(legacy / new adapter / shim) = **8 agent × 4 task = 32 runs** |
| 28 | **Phase 8 — Peer-review P0 三项修复**:(a) **DeepSeek V3.2 judge**(`deepseek-chat`,不同 family,self-preference 解决);(b) `CITATION_MODE=entailment` NLI via DeepSeek(ALCE 替代方案);(c) 20 条 scholarly/policy task(0088-0107,医学/经济/历史/AI 伦理/城市规划)。**Task 总量 87 → 107** |
| 29 | **Phase 8 — 统计显著性**:`compute_elo_with_ci`(N=1000 bootstrap)+ `rank_significance_test`(N=1000 permutation)+ `per_pillar_elo`(7 pillar 独立 Elo)。**FINAL_LEADERBOARD.md 纸 ready** |
| 30 | **Oracle v2**:`rebuild_oracle_filtered.py` 跑完 87 consumer task,按 intent 提取 budget ceiling + category allowlist,拒绝"Magic Home Nightstands in kitchen build"类伪阳性,产出 `data/golden/*.filtered.json` |
| 🔲 下一步 | (a) 把 ODR/dzhng 切换到 DeepSeek 或加 JSON-mode adapter 解 GLM 结构化输出兼容;(b) 8 agent 在 20 条 scholarly task 上再跑一轮,domain 覆盖度提升;(c) 飞书 wiki 同步 Phase 7-8 |

---

## 2. 已完成(全景)

### 2.1 基础设施

| 组件 | 状态 | 备注 |
|---|:-:|---|
| **westd 服务器**(Win11 + WSL2 Ubuntu + Docker CE)| ✅ | Mihomo 代理 + 防火墙 + systemd |
| Mac ↔ westd SSH 隧道 | ✅ | `keep_tunnel.sh` 守 7770 + 9999 自动重连 |
| **shopping (Magento) 容器** | ✅ | 141 GB 镜像,base_url rewrite,端口 7770 |
| **reddit (Postmill) 容器** | ✅ | 107 GB 镜像,端口 9999 |
| gitlab 容器 | 🟡 | 镜像下载 14%,ETA 10h+ |
| shopping_admin / wikipedia 容器 | ⏳ | 排队 |

### 2.2 任务 / Runner / Verifier

| 组件 | 状态 |
|---|:-:|
| `PlaywrightRunner`(占位符 / 浏览器 / 多 verifier 组合) | ✅ |
| `ReportVerifier`(JSON Schema + 字段约束)| ✅ |
| `CitationVerifier`(**ALCE recall / precision / F1**,prose mode 支持)| ✅ v2 |
| `LLMJudgeVerifier`(4 维 CoT,RACE 风格) | ✅ v2 |
| `ChecklistVerifier`(**DRACO 式二值 rubric**) | ✅ v2 |
| `EfficiencyMetrics`(tokens / wall-time / cost) | ✅ v2 |
| `CompositeScorer v2`(6 pillar 加权) | ✅ |
| **Arena**:`compute_elo` / `per_pillar_elo` / `pairwise_battle` | ✅ v2 |

### 2.3 Deep Research 任务库

| 站点 | 条数 | Oracle | Checklist |
|---|:-:|:-:|:-:|
| shopping | **5**(dr_shop_0001-0005)| 5/5 ✅ | 5/5 ✅ |
| reddit | **4**(dr_red_0001-0004)| 4/4 ✅ | 4/4 ✅ |
| 小计 | **9** | **9/9** | **9/9** |

### 2.4 Agent 基线(MEGA:9 task × 4 agent × 27 battles/agent)

文件:`data/results/bench_v2_MEGA.md`(2026-04-16 10:39)

#### Composite Elo(6 维加权得分驱动)

| Rank | Agent | Elo | W-L-D | 5-task 时 | 变化 |
|:-:|---|---:|:-:|---:|:-:|
| 1 | **deerflow-glm51** | **1050** | 17-10-0 | 1097 | -47 |
| 2 | **react-glm46** | **1045** | 13-8-6 | 960(#4)| **+85, 升 2 名** |
| 3 | react-glm51 | 969 | 9-13-5 | 975 | -6 |
| 4 | react-glm45 | 936 | 6-14-7 | 968 | -32 |

#### Pairwise Judge Elo(LLM 直接侧对侧)

| Rank | Agent | Elo | W-L-D |
|:-:|---|---:|:-:|
| 1 | **react-glm45** | **1104** | 20-7-0 |
| 2 | deerflow-glm51 | 1020 | 15-12-0 |
| 3 | react-glm46 | 981 | 12-15-0 |
| 4 | react-glm51 | 895 | 7-20-0 |

#### Per-pillar Elo(每个维度独立 Arena)

| Agent | Cite | Comp | Det | Eff | Fact | Judge |
|---|---:|---:|---:|---:|---:|---:|
| **deerflow-glm51** | **1154** | 963 | 865 | 1000 | **1154** | 988 |
| react-glm51 | 924 | 1042 | **1068** | 1000 | 924 | 1011 |
| react-glm46 | 961 | **1057** | 1034 | 1000 | 961 | **1076** |
| react-glm45 | 961 | 938 | 1032 | 1000 | 961 | 925 |

#### 三大发现(可写论文)

1. **多 site 暴露 DeerFlow 鲁棒性弱点** —— DeerFlow 长 prompt 在 reddit 政治内容上多次被 GLM 内容安全拦截(dr_red_0001 / 0004 直接 0.04 分)。**这是单 site benchmark 看不到的 failure mode**。结论:**评测必须跨 site**。

2. **glm-4.6 单 agent 性价比之王** —— 加上 reddit 后从 #4 跳到 #2,在 dr_red_0001 上拿 0.93 史诗级表现。说明对结构化 DR 任务,reasoning model + 单 agent 已经够用,DeerFlow Plan-Execute-Report 是 over-engineering。

3. **LLM judge length-bias 复现得很干净** —— 同一个 glm-4.5,Composite 排第 4,Pairwise judge 排第 1。**证明纯 LLM judge 不可信**,必须有结构化指标兜底。这本身是论文的一个 section。

### 2.5 测试

**53/53 单测全绿**(v2 21 + v3 schema 5 + v3 fact_kg 16 + v3 markdown 8 + v3 composite 3)。

### 2.6 v3 完成的部分(2026-04-16 凌晨~下午)

#### 2.6.1 Phase 1 — Schema(0.5 天 ✅)

- `src/models/deep_research.py` 加 `MarkdownReportSpec` / `GoldenSpec` / `DeepResearchTaskV3`
  - markdown_spec:`min_words` / `max_words` / `min_paragraphs` / `min_citations` / `min_pages_browsed`
  - golden:指向 KG 三元组 JSON + 期望 predicates 列表
  - task_id 必须匹配 `dr_[a-z]+_v3_[0-9]{4}` 模式
- `data/tasks/deep_research/v3_TASK_SPEC.md` —— 完整 v3 规范文档(任务最小特征 + 文件 shape + KG 真值格式 + scoring 权重 + anti-patterns)
- `tests/test_v3_schema.py` —— 5 个新测试全绿

#### 2.6.2 Phase 2 — 8 条 v3 task + Oracle(2 天 ✅)

| task | 主题 | words | links | triples | min_words 阈值 |
|---|---|---:|---:|---:|---:|
| dr_shop_v3_0001 | 耳机 3 品类($30-100)对比指南 | 699 | 11 | 18 | 600 |
| dr_shop_v3_0002 | home-kitchen review-rating 相关性 | 467 | 11 | 25 | 400 |
| dr_shop_v3_0003 | 茶类价格-质量象限分析 | 443 | 9 | 34 | 400 |
| dr_shop_v3_0004 | 蓝牙耳机差评聚类 | 223 | 3 | 12 | 200 |
| dr_red_v3_0001 | /f/news vs /f/worldnews 引擎对比 | 376 | 6 | 22 | 350 |
| dr_red_v3_0002 | wallstreetbets top 5 讨论 digest | 564 | 5 | 17 | 500 |
| dr_red_v3_0003 | /f/technology 趋势主题 | 491 | 12 | 51 | 450 |
| dr_red_v3_0004 | MarvelsGrantMan136 用户行为 profile | 186 | 3 | 14 | 180 |

新增模块:
- `envs/{shopping,reddit}/oracle_dr_v3/` —— 8 个 v3 oracle(每个返回 markdown 长文 + dump KG 三元组)
- `envs/shopping/oracle_dr_v3/_common.py`、`envs/reddit/oracle_dr_v3/_common.py` —— `write_golden` / `md_link` 等共享工具
- `scripts/run_v3_oracle.py` —— v3 oracle CLI(带 page.goto 重试包装,SSH tunnel 断了自动 retry 5 次)
- `data/golden/dr_*_v3_*.json` —— 8 份 KG 真值(共 193 条三元组,平均 24/task)
- `data/results/oracle_v3_dr_*_v3_*.md` —— 8 份 oracle 参考报告(共 ~3500 字)

每条 v3 task 任务设计要件(都满足):
- 跨 ≥3 个不同页面(min_pages_browsed)
- 整合 ≥5 个实体的对比 / 综合
- 报告含 ≥3 段 markdown + 论证段
- ≥3 条 markdown `[text](url)` 引用
- 无 JSON Schema 强制约束(改用 markdown_spec 量化下限)

#### 2.6.3 Phase 3 — KG Fact Verifier(3 天 ✅,完成于 2026-04-16 晚)

新增模块(全部在 `src/golden/`):
- `db_connect.py` — `DBRunner`:ssh → wsl → `docker exec` → 容器内 mysql/psql 的多层管道。难点是 Windows cmd 的引号吃字符,最终方案是**把 bash runner 脚本 scp 上去,SQL 走 stdin**,彻底绕开 cmd 层。含 SSH 瞬断自动重试。
- `db_schema_map.py` — 每个 v3 谓词对应一个 SQL 模板:
  - Magento(EAV 模型):`price` → `catalog_product_entity_decimal.attr_id=77` / `rating` → `review_entity_summary.rating_summary/20` / `review_count` → `review_entity_summary.reviews_count` / `product_url` → `catalog_product_entity_varchar.attr_id=121`
  - Postmill:`score/comment_count` → `submissions` / `forum` → `forums.normalized_name` / `author` → `users.username`
  - 聚合谓词(`avg_*`、`n_*`、`median_*`)标 `verifiable=False`,跳 DB 只做 mention check
- `db_verifier.py` — `MagentoTripleStore / PostmillTripleStore`,提供 `verify(subj, pred, obj) → True/False/None`。含模糊比对:价格 ±5%、URL slug 子串、字符串双向包含
- `triple_extractor.py` — LLM 从 markdown 抽 (subj, pred, obj),prompt pin 住谓词词表,JSON 数组 + 重试 3 次,复用 LLMJudge 的 Zhipu Anthropic-compat 通道

`src/verifiers/fact_kg_verifier.py`:
- **Recall**:确定性子串共现匹配(subject 带 prefix 识别 `theme:` / `tea-type:` / `forum:` 剥掉;数字带词边界防 `4.3` 误中 `140.35`)
- **Precision**:LLM 抽 agent 三元组 → DB 查证,DB 返 None 时 fallback 到 golden 集合交集
- 输出 `{recall, precision, f1, per_triple_misses}`,`score = f1`

**验收结果**(对 8 oracle):

| task | golden 数 | oracle recall |
|---|---:|---:|
| dr_shop_v3_0001 | 18 | 1.00 |
| dr_shop_v3_0002 | 25 | 1.00 |
| dr_shop_v3_0003 | 34 | 1.00 |
| dr_shop_v3_0004 | 12 | 1.00 |
| dr_red_v3_0001 | 22 | 1.00 |
| dr_red_v3_0002 | 17 | 1.00 |
| dr_red_v3_0003 | 51 | 0.88 |
| dr_red_v3_0004 | 14 | 1.00 |
| **聚合** | **193** | **0.969 (187/193)** |

- 全部 ≥ 0.8 ✓(验收线)
- 故意错答案 recall = 0.0 ✓(验收线 < 0.3)
- DB 活体回环测试绿(Harphonic E7 价格 34.99 / Magento EAV 查询正确返回)

16 个新测试:单元测试(prefix 剥离、数字词边界、golden 加载)+ 8 任务参数化 recall 断言 + 活体 DB 回环 + bogus 低分断言。

#### 2.6.4 Phase 4 — Markdown Verifier + Composite v3(1 天 ✅)

新增:
- `src/verifiers/markdown_report_verifier.py`(**kind=markdown_structure**)—— 验 `markdown_spec` 下限:字数 / 段落 / 引用数 / 浏览页面数 / max_words 上限。8 个测试覆盖每一条阈值 + 域白名单翻译(`__SHOPPING__` → `localhost:7770` 等)。
- `data/tasks/deep_research/{shopping,reddit}/checklists_v3.json` —— 每任务 **15 条 DRACO 二值 rubric**(共 120 条),混合正向(含 X)+ 负向(避免 Y)。举例:
  - `dr_shop_v3_0004` 有 "Does the report avoid inventing quotes not present in any review?"(防伪造)
  - `dr_red_v3_0001` 有 "Does the report quantify the engagement gap (numeric difference)?"(强制量化)
- `ChecklistVerifier` 现在优先加载 `checklists_v3.json`,v2 路径仍保留兼容
- `src/scoring/composite_v3.py`:

  | Pillar | 权重 | 说明 |
  |---|---:|---|
  | `markdown_structure` | 0.10 | MarkdownReportVerifier,结构契约 |
  | `citation` | 0.15 | CitationVerifier(ALCE F1,prose mode) |
  | **`fact_kg`** | **0.30** | FactKGVerifier(客观主力) |
  | `llm_judge` | 0.20 | LLMJudgeVerifier(RACE 4 维) |
  | **`checklist`** | **0.20** | ChecklistVerifier(DRACO 15 条) |
  | `efficiency` | 0.05 | EfficiencyMetrics(tokens/time/cost) |

v3 权重的设计理由:
- `fact_kg` 最大权重 —— 沙盒 DB 直连是我们独家客观信号,零方差
- `checklist` 从 v2 的 0.10 提到 0.20 —— DRACO 二值 rubric 方差低于 Likert
- `llm_judge` 保留但降至 0.20(v2 length-bias 发现后必须限流)
- `deterministic` pillar 下线 —— markdown 输出不再有 JSON schema,其原职责拆到 `markdown_structure` + `fact_kg`

新增 11 个测试:markdown_structure 8 + composite_v3 dry-run 3。

#### 2.6.5 Phase 5 — Arena + bench_v3.py(0.5 天 ✅)

- `scripts/bench_v3.py` —— v3 版 bench,复用 v2 的 pairwise + per-pillar Elo,换 `score_v3` 主流程。支持 `--from-file` 接入现有 markdown 文件(oracle / DeerFlow)。
- `src/agents/glm_react_agent.py` 双提示:
  - `_SYSTEM_PROMPT`(原 JSON 模式,v2 任务继续使用)
  - `_SYSTEM_PROMPT_V3`(markdown 长文模式,v3 任务自动激活)——模板化塞 `min_paragraphs / min_words / min_citations` 给 agent 看
  - 激活规则:`task_cfg.get("markdown_spec")` 存在 → 切 v3 模式
- **干跑验收**:8 oracle × composite_v3 (--no-judge --no-pairwise) 全程跑通。确定性 3 pillar(markdown 0.10 + citation 0.15 + fact_kg 0.30 = 0.55)的上限就是干跑分数上限,oracle 得 0.38–0.55,符合预期

### 2.7 文档

- `RESEARCH.md` —— 最初愿景
- `SCORING_FRAMEWORK.md` —— v2 六柱评分设计
- `DEEP_RESEARCH_TASK_SPEC.md` —— DR v2 任务规范
- **`data/tasks/deep_research/v3_TASK_SPEC.md`** —— **v3 任务规范**
- **`data/tasks/deep_research/{shopping,reddit}/checklists_v3.json`** —— **v3 15 条/任务 DRACO rubric(120 条)**
- **`data/golden/dr_*_v3_*.json`** —— **v3 KG 真值(193 三元组)**
- **`data/results/bench_v3_oracle_dryrun.md`** —— **v3 scorer dry-run 首跑验证**
- `ROADMAP.md` —— Stage A/B/C 路线图
- `RESULTS_SUMMARY.md` —— v2 实验结论汇总
- `PROGRESS_REPORT.md` —— 给老师汇报的一页纸
- `data/results/NIGHT_RUN_SUMMARY.md` —— 通宵工作流水账
- `data/results/COMPARE_dr_shop_0001.md` —— DeerFlow vs ReAct 逐字对比
- `~/.claude/plans/logical-sauteeing-mitten.md` —— v3 重设计计划(approved)
- **飞书 wiki**(`rcn52ut42d3j.feishu.cn/wiki/Mr6FwqJdci6USQk3VxNcYJlDnkd`)—— 程序化重写的进度文档,173 块结构化内容

---

## 3. 未完成 / 待做(按优先级)

### P0 — v3-Phase 3/4/5 ✅ 已完成(见 §2.6.3–2.6.5)

### P0' — v3-Phase 6 最后收尾(0.5 天,进行中)

1. **跑一轮带 LLM judge 的完整 Arena**
   - `python scripts/bench_v3.py react --tasks <all 8 v3>` × 3 GLM model + DeerFlow adapter = 4-way
   - 出 `data/results/bench_v3_FIRST.md` 作为 v3 首版 Elo
   - 预期(参照 v2 的 DeerFlow +5 Elo 小优势 + v3 加重 fact_kg/checklist):DeerFlow 重夺领先,差距拉开到 ≥100 分

2. **v2 存量处理**
   - **保留** `composite_v2.py` / `bench_v2.py` + v2 tasks + v2 oracles + v2 checklists(用于论文"v2 vs v3 方法对比"章节)
   - 在 README 添加"v3 是当前主线,v2 冻结作为历史对照"的明确说明

3. **文档收尾**
   - 更新 README.md 快速开始(换成 bench_v3 命令)
   - 更新 PROGRESS_REPORT.md 给老师汇报的一页纸
   - 写 RESULTS_SUMMARY_v3.md
   - 整理飞书 wiki 文档(已在 2026-04-16 晚重写完)

### P1(本月内)

4. ~~**FActScore 原子事实提取器**~~ → **已被 v3 `fact_kg_verifier` 取代** —— 直连 DB 比 FActScore 的 URL-fetch 验证更强,零成本、零方差。后续若要扩到沙盒外任务,再考虑 FActScore 式的 URL 验证

5. ~~**DRACO checklist 扩量**~~(v3 已 15 条/任务)→ **升级目标:扩到 30 条/任务 + 外部标注员做 IAA**
   - 现在 15 条是 LLM + 手动审查的结果;DRACO 2026 论文显示 40 条是稳定区间
   - 需要外部标注员或众包做 Cohen's κ(目标 ≥ 0.75,DRACO 论文水平)
   - 探索 ResearchRubrics(2800h 纯人工)的 active-learning 方案

6. **Dual judge** — 目前 GLM-5.1 既当 agent 又当 judge,self-preference 风险
   - 需要 **非 GLM 族**的 judge(Claude / DeepSeek / Doubao / Kimi)—— **缺 API key**
   - 先用 GLM-5.1 + GLM-4.6 做粗的 dual 看 κ;再等申请到 key 后换

7. **gitlab / shopping_admin / wikipedia 沙盒** — 等下载完(gitlab ETA 10h)
   - 写 `envs/gitlab/` docker-compose + reset.sh(已预置)
   - shopping_admin 是 shopping 的运营后台,复用 shopping 的知识
   - wikipedia 走 kiwix-serve(已下 base image)

8. **修复 `dr_red_v3_0002` oracle 空 subject bug** — Phase 3 recon 发现该 golden 的 15/17 条 subject 是空串(wallstreetbets oracle 生成 bug),目前 recall 碰巧靠对象 + 1.00 但不健康。需要回头重跑 oracle 并 regenerate golden。

### P2(这个季度)

8. **跨站任务** — 真正 "Deep Research" 必须跨 ≥2 个站
   - 例 1:在 shopping 上找一款 noise-cancelling headphones,去 reddit /f/technology 搜索其口碑并对比
   - 例 2:gitlab 某 repo 最近的 3 个 issues vs 该项目在 reddit 相关讨论的口径
   - 每个跨站任务难度直接跳一档

9. **噪声注入 + 鲁棒性曲线** — 按 ImageNet-C 风格
   - 网络延迟 / 随机 404 / 广告注入 / 图片加载失败 等 6 种扰动 × 11 级强度
   - 每 agent 出鲁棒性曲线

10. **数据污染检测**
    - 本次 WebArena 种子是 2023 年的,新模型训练集可能已包含
    - 计划:给商品随机换皮(改 SKU / 改品牌)生成 v2 任务集,比较 v1 vs v2 成绩差,差距大说明污染严重

11. **benchmark CLI + HTML 排行榜**
    - `benchmark run --agent X --tasks dr_shop,dr_red --out results.json`
    - `benchmark leaderboard --html`(静态页,含每 agent 雷达图)

### P3(论文阶段)

12. **与同期 benchmark 公平比较**
    - 跟 DeepResearchGym / BrowseComp-Plus / DeepResearch Bench 比较差异
    - 定位我们的独特性:**多站可控沙盒 + 确定性评分 + Arena Elo 三位一体**

13. **对外发布**
    - 目标 50 条任务,5 站各 10 条
    - 公开 task + Oracle + sandbox 镜像,但保留 Golden Answer 签名避免污染

---

## 4. 架构全图(2026-04-16 当前)

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Deep Research Benchmark                            │
│                                                                     │
│  ┌──── sandbox ────┐    ┌──── task + golden ────┐   ┌─ verifier ─┐  │
│  │ ✅ shopping     │    │ 5 dr_shop             │   │ Report     │  │
│  │ ✅ reddit       │    │ 4 dr_red              │   │ Citation   │  │
│  │ 🟡 gitlab       │    │ ...                   │   │ Checklist  │  │
│  │ ⏳ shopping_adm │    │ Oracle (9/9 ✅)       │   │ Judge 4dim │  │
│  │ ⏳ wiki (kiwix) │    │ Checklist (9/9 ✅)    │   │ Efficiency │  │
│  └─────────────────┘    └────────────────────────┘   └────────────┘  │
│            ▲                       │                     │          │
│            │               PlaywrightRunner              │          │
│            │                       │                     │          │
│            │             ┌─────────┴─────────┐           │          │
│            │             │  agent registry   │           │          │
│            │      ┌──────┼──────┐────────────┼────┐      │          │
│            │      │      │      │            │    │      │          │
│            │   GLM-5.1 GLM-4.6 GLM-4.5  DeerFlow  …      │          │
│            │    (ReAct)          (multi-agent)           │          │
│            │                                             │          │
│            └──────────── tool calls ─────────────────────┘          │
│                                                                     │
│                      CompositeScorer v2 (6 pillar)                  │
│                               │                                     │
│           ┌───────────────────┼───────────────────┐                 │
│           │                   │                   │                 │
│      Composite Elo      Pairwise Elo       Per-pillar Elo           │
│      (formulaic)        (LLM judge)        (每维独立)                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. 汇报用数据(给老师)

**今天能 show 的 4 个数字**(基于 9 task × 4 agent × 27 battles/agent 的 MEGA Arena):

1. **从 5 task 加到 9 task 后,DeerFlow 优势从 +122 缩到 +5 Elo** —— 加 reddit 后 GLM 内容安全在长 prompt 上拦了 DeerFlow,glm-4.6 ReAct 反超到第 2 名。这暴露了**单 site benchmark 看不到的 failure mode**,**证明跨 site 评测的必要性**。
2. **Composite vs Pairwise judge 出现严重背离** —— 同一个 glm-4.5,Composite 排第 4,Pairwise judge 排第 1。证明 **LLM judge length-bias** 真实存在,纯 LLM 评分不可信,**确定性多维评分必要**。
3. **Per-pillar 清晰拆分** —— DeerFlow 独占 Cite/Fact(均 1154);glm-46 拿 Comp/Judge;glm-51 拿 Det。**没有 agent 全维度赢**,说明评测是真正的多维不可饱和。
4. **Oracle 9/9 拿满分** —— 说明任务有解、评分器对。LLM agent 是落后那方,任务设计是 valid challenge。

**一句话定位**:

> 我们构建了第一个"**可控沙盒(自有数据 / 可复位)+ Deep Research 任务(非 UI 操作)+ 六维确定性评分(非纯 LLM judge)+ Arena Elo 排位**"一体化的 Agent 评测系统。相比 DRACO / DeepResearch Bench 这些开放网评测,我们的复现性和可对照性高;相比 WebArena 原版,我们跳出了 UI-only 局限,测的是真正的研究综合能力。

---

## 5.5 业界参考系(2024-2025 Deep Research 评测生态)

我们的技术决策都有对应的业界参照物。下面列出三类 benchmark 的对比定位:

### 5.5.1 参考答案三大范式

| 范式 | 代表 | 我们的位置 |
|---|---|---|
| **Rubric / 二值 checklist** | DRACO(Perplexity 2026,每任务 ~40 条)、ResearchRubrics(Scale 2025,2593 条纯人工 2800h 标注) | ✓ v3 用 15 条/任务,120 条总量,规模介于 DRACO 和开源 DRACO-lite 之间 |
| **可验证事实集** | DeepSearchQA(DeepMind 2025,900 个三阶段验证 QA)、LiveDRBench(MSR 2025,100 个"问题反转"任务) | ✓ v3 KG 三元组(193 条)正是"可验证事实集"路线,但我们独家是**直连沙盒 DB**,零标注成本 |
| **LLM 参考报告 + checklist** | LiveResearchBench(Salesforce 2025,100 任务 1500h 标注)、DeepResearch Bench(USTC 2025,Gemini-2.5-Pro Deep Research 生成参考报告) | ✓ v3 oracle 也是"LLM 生成的参考报告",但通过 DB 三元组可验证,避免了 LLM 参考报告本身的真实性争议 |

**我们的独家优势**:
- 沙盒 DB 直连验证 = 零成本、零方差、零时效漂移,这是上面所有框架都做不到的(它们要么靠 1500-2800h 人工标注,要么依赖实时网页搜索)
- 193 条 KG 三元组相当于"10000 条人工 rubric"级别的客观信号密度,只是用另一种形式表达

### 5.5.2 商业搜索基础设施版图(提醒:我们沙盒内不需要这些)

| 系统 | 主搜索 API | 自有索引 |
|---|---|---|
| OpenAI DR | Bing | 无 |
| Gemini DR | Google | ✓ Google 全集 |
| Perplexity DR | 自建(200B+ URL)+ Bing/Google 补排序 | ✓ EB 级 |
| Claude Research | Brave(86.7% rank overlap) | 无 |
| Grok | 自建 + X 数据流 | 部分 |

→ **我们不依赖任何外部搜索**,沙盒内是静态网页 + DB。这既是劣势(任务生态受限)也是优势(100% 可复现)。

### 5.5.3 开源搜索 API 生态

- **Tavily** 是事实标准(GPT-Researcher / DeerFlow / LangChain ODR 的默认值)
- **MCP** 成为可扩展搜索接口(DeerFlow 2.0、LangChain ODR、OpenAI、Anthropic 都支持)
- **SearXNG** 是自托管元搜索共识
- 我们的 ReAct agent 用的是**直接 Playwright + 站点内原生 URL**,不走搜索 API —— 是另一条路线(WebArena 式的"直接浏览"),更接近真实 Deep Research 的"开着浏览器上班"模式

### 5.5.4 离线语料库规模参考

| 框架 | 语料库规模 |
|---|---:|
| DeepResearchGym(CMU 2025) | ClueWeb22-B 87M + ClueWeb22 100B 全集 + FineWeb 15T token |
| FutureSearch RetroSearch | 1-18.9 万网页/任务,Serper + Playwright 离线快照 |
| BrowseComp-Plus | 10 万文档 + BM25/Qwen 索引 |
| ResearchArena | 1200 万 S2ORC 论文 |
| **我们(v3)** | **静态 Magento + Postmill 种子库,单数字级文档,但**可复位、可 diff、可扩展 |

---

## 6. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| **LLM judge self-preference** | GLM 自评 GLM,可能偏高 | 等 Claude/DeepSeek key 做 dual judge |
| **任务约束过松**导致不同答案都能过 | Arena 区分度 ↓ | Golden Answer 体系(P0.2) |
| **WebArena 种子数据污染训练集** | 评测失效 | 换皮机制(P2.10) |
| **GLM Coding Plan rate limit**(本晚经历过)| bench 中断 | keepalive + 重试 + 备用 Kimi/DeepSeek |
| **gitlab 镜像下载太慢**(10+ h)| 铺站延期 | 并行下 shopping_admin + wiki |
| **DeerFlow 内置 MCP 依赖 uvx** | 跑不起来 | 已用 `graph.astream` 直调绕过 |
| **跨站 URL 外链**(例 reddit 提到的外链 apnews)| 打破沙盒边界 | 任务设计禁止"需要外网信息"的问句 |

---

## 7. 资源需求

| 资源 | 当前 | 需要 |
|---|---|---|
| westd 服务器磁盘 | D 盘 197 GB 可用 | 再留 150 GB 给剩余镜像 |
| westd 内存 | 64 GB | 够用(shopping + reddit 同时跑占 < 10 GB) |
| GLM Coding Plan 额度 | 每天够用 | 可能扩到 Pro 档避免 rate limit |
| Claude / DeepSeek API key | 无 | **P1 阶段必须搞到**(dual judge)|
| Mac 侧 Playwright + venv | ✅ | - |
