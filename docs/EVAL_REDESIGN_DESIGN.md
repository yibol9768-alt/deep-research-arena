# 评测重做 + 多接入方式 + 纯 LLM 打分 设计文档

> 状态:草案 v1,**待你 review,尚未动任何实现**。
> 生成:2026-06-02。作者:Claude(架构/规格/验收),实现将按惯例交 Codex,Claude 独立验证。
> 依据:本轮四路独立代码审计(打分栈 / 接入栈 / 产物质量 / 目录),结论均带 `file:line`。
> 目标读者:你(决策)+ Codex(实现)。本文是单一权威的"下一步要做什么",其余 roadmap 文档作背景。

---

## 0. 这份文档要解决的五件事

你这轮提了五个诉求,逐一对应本文章节:

1. 用户最终拿到的报告要是**完整、真实、长、带分析色彩**的 -> §3 设计 B(产物)。
2. 评测要支持 **computer-use(电脑类型)、Brave Search API、以及其它接入方式** -> §4 设计 C(接入)。
3. 打分要能**通过纯 LLM 的方式完美做好** -> §2 设计 A(打分重做)。
4. 如何**简单 scale up** -> §5 设计 D。
5. **目录设计干净、文档分类、临时文件整理** -> §6 设计 E。

并在 §7 列出**需要你拍板的开放项**,§8 给**落地顺序与验收**。

---

## 1. 现状诊断:四路审计的残酷结论

你说"我们的评测完全不合格",这个判断是对的,而且现在有证据。下面每条都核实到代码。

### 1.1 打分:大半是噪声,且有一个致命 bug

- **致命 bug:证据感知打分根本没接通。** `_run_judge_dims_rollout_async` 在 `src/eval/evaluator.py:854` 把 `evidence=evidence` 传给 depth/rigor/style 判分器,但这些判分器的签名是 `verify(*, task_config, answer, page=None)`(`src/verifiers/depth_verifier.py:134`、`rigor_verifier.py:109`、`style_verifier.py:112`),既无 `evidence` 参数也无 `**kwargs`。结果:每次调用抛 `TypeError`,被 `evaluator.py:868` 捕获,降级成中性 0.5。`WEIGHTS_RL` 注释里宣称的 "Q1 evidence-aware rebuild"(`leaderboard_composites.py:180`)**从未真正生效**。判分器至今只看报告正文。
- **judge 与人类一致性是 fair 到负相关。** 实测(`docs/JUDGE_HUMAN_KAPPA.md`,n=80):depth κ=0.246、style κ=0.329(均 fair),**rigor κ=−0.272(比瞎猜还差)**、checklist κ=0.133(近乎随机)。
- **"F=2.30 噪声"是一句代码注释,不是实测留档。** 只出现在 `leaderboard_composites.py:180`,没有任何 docs 记录这个数或重做后的数。
- **四个 LLM 判分器全是:绝对 1-5 标量、只看报告、6000 字截断。** depth/rigor/style 是 median-of-3,checklist 是**单样本**。没有任何一个是比较式/参考锚定;没有一个真正吃到检索证据。
- **最强的确定性信号被晾在一边。** `FactKGVerifier`(对沙盒 golden 三元组的召回,确定性、难刷)算了,却**不在** `WEIGHTS_V3`/`WEIGHTS_RL` 里。同样被排除的还有 `claim_nli`、`factual_exactness`、`internal_consistency`、`citation`(ALCE)。仓库里 25+ 个判分器,真正进奖励的只有约 6 个。
- **fast 模式(RL 每条 rollout 用的模式)把四个 judge 维度直接置 0.5 再丢弃**(`evaluator.py:453`)。也就是说**训练期间 depth/rigor/style/checklist 全程是中性桩**,GRPO 实际只在优化确定性的 coverage/长度,不在优化分析质量。
- **比较式打分基建已存在但没接。** `src/scoring/pairwise_judge.py` 有 Chatbot-Arena 式 A/B/TIE + 位置交换,`ArenaEvaluator` 从不调用它。

一句话:**现在约一半的质量权重压在 fair 到负相关的噪声判分上,而且证据感知那条线是断的;最该当主信号的沙盒确定性信号(FactKG)被排除在外。**

### 1.2 产物:又短又浅,且没人为"长且分析"发奖

- **原生可训练 policy 被要求"至少 300 字"**(`src/rl/qwen_policy.py:619`),比任务自己的 `min_words: 3500` 低约 12 倍,也远低于 longform 目标 4000。原生 agent 被 prompt 成产出比目标短一个数量级的东西。
- **实测最好的外部 agent 也就 2000-2900 字**,且常常引用不足(15 条 vs 要求 60 条),普遍达不到结构门槛。
- **唯一一个分级、随复杂度自适应的长文判分器 `LongformQualityVerifier` 不在公开榜的 composite 里。** 它只喂 RL 奖励(`WEIGHTS_RL` 0.10)。公开榜的长度项是二元 3-flag 的 `spec`,权重 0.05(约 1.7%),`grep longform_quality data/results/` 零命中。
- **最丰富的分析判分器 `AnalysisDepthVerifier`(矛盾调和、多证据链、新见解、对立观点、可执行结论)是孤儿**,`evaluator.py` 两条路都没调它。当前活着的 `depth` 是更轻的 5 点 judge,且 fast 模式跳过。
- **没有任何参考范文落盘。** golden 只有 must-cite URL 池 + KG 三元组,没有 gold 报告文本,无法做"相对参考"的长度/结构/分析校准。
- **loop 里没有"先列提纲 -> 逐节扩写 -> 自评补全"的阶段**,env 可以 Finalize 一个 300 字 blob 就干净退出。

### 1.3 接入方式:窄,且 computer-use / Brave / RAG 是半成品

- **核心契约很窄**:`SandboxBackend.search(query)->list[Hit]` + `fetch(url)->str`(`src/rl/env.py:20-25`),上面再叠一个 `CallTool` 单 opcode 的类型化 `Tool` 注册表。
- **已成型(真,部分需在线)**:`shim`(HttpSandboxBackend)、`browser`(Playwright,真 DOM)、`mock`;工具 `search/fetch/structured_lookup/crawl/sql_query/run_code/run_bash`(默认拒绝 + 安全护栏真)。
- **computer-use:observe->act 循环 + GUI 动作执行器是真的,但只发了 text-proxy 桩,没有真 VLM**(`src/rl/backends.py:341-368`)。GPU 现在不再是约束,缺的只是把 `_TextProxyPolicy` 换成真 VLM 策略对象。
- **Brave:shim 早就能回应 Brave 形状的请求**(`GET /v1/brave/web/search`,`integrations/search_shim/app.py:612-640`),但喂的是**本地沙盒语料**;而且 RL 侧**没有 `brave` 这个 modality**。详见 §4.2 的两种含义。
- **RAG / vision 是 seam**:有 Protocol 和内存实现,但没建索引、没注入 captioner。
- **奖励确实是模态无关的(地基好)**:`_compute_ground_signals`(`evaluator.py:943-1081`)只读 `retrieved_snippets` 和被引 URL,不看 bytes 怎么来的。所以加任何新接入方式都不动奖励。这是我们能放心加接入方式的根本原因。

### 1.4 目录:乱

- **根目录有 ~32 个 `.md`**,是一坨比 `docs/` 更老的、互相重叠的文档(多份 RESULTS_SUMMARY / HANDOFF / ELO_PLAN / *_AUDIT)。乱主要在根目录。
- **大小写重复且字节相同**:`AGENT.md`==`agent.md`、`CLAUDE.md`==`claude.md`(大小写不敏感文件系统上会撞)。
- **三个前端**:生产源是 `frontend/`(-> `web/dist/`,见 CLAUDE.md),`web-next/` 是废弃并行树,`web/` 留 Flask 与 dist 产物。`frontend/` 671M(塞满 `_check_*.jpeg` 审查截图)。
- **三个 paper 树**:`paper/`(89M,带 .bak.2026-05-06)、`paper_deep/`、`latex/`。
- **568 个 `.bak`/`.preV1`/`.preFix` 被提交进 `data/results/`(~4.2M),且 `*.bak` 没进 `.gitignore`**。`docs/` 还提交了 LaTeX 中间产物(`defense_paper.aux/.log/.out/.toc`)。
- **多代同功能脚本**:leaderboard builder 有 v3/v4/final 三代并存,task builder、recompute 一次性脚本若干。`scripts/archive/`(~70 文件)已是坟场,无人引用,无害。

---

## 2. 设计 A:把"纯 LLM 打分"做对(full-mode 重做)

目标:在保留确定性 truth-gate 地基的前提下,让 LLM 判分从"fair 到负相关的噪声"变成"可信、可复现、与人类对齐"。这是你"纯 LLM 完美打分"诉求的核心。六步,按性价比排序。

### A1.(P0,先修 bug)接通证据感知
- 给 depth/rigor/style/checklist 的 `verify` 加 `evidence` 与 `page`(或 `**kwargs` 吞掉),把 `rollout.retrieved_snippets` 真喂进 prompt。
- 验收:RL full 模式下四个 judge 不再降级成 0.5;`tests/` 新增"传 evidence 不抛 TypeError"断言。

### A2. 绝对 1-5 -> 参考锚定 + 比较式
- 复用已存在的 `pairwise_judge.battle`(A/B/TIE + 位置交换),把 ArenaEvaluator 的判分从"独立打绝对分"改成"对参考范文(见 B4)或对手报告做比较"。
- 比较式是 Arena-Hard / Chatbot-Arena 取得高分辨力的关键,绝对 Likert 正是 κ 低的根因。
- 验收:同一组报告,判别力(F-ratio、Bradley-Terry CI 不重叠对的比例)显著高于现状。

### A3. privileged evidence(让 judge 能查"综合是否真的发生")
- 判分 prompt 里附上该 rollout 自己检索到的证据片段,要求 judge 判断"报告的论断是否被自己的证据支撑、是否做了跨源综合而非罗列"。
- 这正是 A1 修好后才能做的事,也是把"分析色彩/洞察"变成可判信号的关键。

### A4. median-of-N + 强制跨家
- 把 checklist 与 4-dim judge 也升到 median-of-N(N>=3);depth/rigor/style 已是 median-of-3。
- 实现 `agent_family` 感知的 judge 选择,保证判分模型与被判 agent 不同家族(基建已在 `judge_client.py`,缺的是按 agent 路由,见 `depth_verifier.py:44-47` 的 TODO)。

### A5. 把确定性强信号请回 composite
- 让 `FactKGVerifier`(沙盒 golden 三元组召回)拿到真实权重,作为难刷的主信号之一;`factual_exactness`、`internal_consistency`、`citation`(ALCE)按确定性零成本接入。
- 重新推导 `WEIGHTS_V3` / `WEIGHTS_RL`:确定性信号(coverage、fact_kg、source_diversity、longform、search_breadth)拿实权重,修好的 judge 维度保留但不再独占,弱信号降权。保持 `reach_soft` 软门。
- 验收:5 个旧 V3 composite 符号字节不变(回归底线),新增的 `composite_v3_rl` 体系内调整;honest 报告与各类 hack(堆 URL / 编引用 / 注水短文 / 单域 / 一面之词)的差距扩大。

### A6. 统一 leaderboard 与 RL 两条打分路
- 现状两条路(`evaluate_async` 用 `WEIGHTS_V3`,`_evaluate_rollout_async` 用 `WEIGHTS_RL`)维度集不同,`longform_quality` 在 RL 有、在榜上没有。重做后让两条路共享同一组"已修好的维度",只在 fast/full 上有取舍,避免"训练优化的信号和榜上展示的信号不是一回事"。

> 关于"纯 LLM 完美打分"的定位说明:我建议的不是"扔掉确定性、全靠 LLM",而是**确定性 truth-gate 做地基(防刷分、可复现)+ 纯 LLM 在其上做质量分(深度/分析/综合,靠 A1-A4 做对)**。纯 LLM 单独打分在 DR 这种长文上会被注水/华丽辞藻骗(现状的 κ 已证明),证据感知 + 比较式 + 跨家 + 多采样是让 LLM 打分"完美"的四根支柱。若你要的是"展示给用户的那一栏纯粹由 LLM 给出的综合评语 + 分数",这套打分做对后可以原生产出,见 §7 开放项。

---

## 3. 设计 B:让产物变成"完整、真实、长、带分析"的报告

打分做对只是"能识别好报告";要让用户**拿到**好报告,还得改生成端。

### B1. 原生 policy 的 finalize 目标对齐任务规格
- `qwen_policy.py:619` 的 "AT LEAST 300 words" 改为读 `markdown_spec`(min_words/min_citations/min_paragraphs/sections),并显式要求 compare/contrast、tradeoffs、矛盾调和、固定多章节骨架。

### B2. loop 增"提纲 -> 逐节扩写 -> 自评补全"阶段
- 在 `ResearchEnv` 加可选的 outline-first / expand / self-critique 动作或子流程,避免 Finalize 一个短 blob 就退出。
- 这是把"长且结构化"从"靠运气"变成"流程保证"的关键。

### B3. LongformQuality 上榜 + AnalysisDepth 复活
- 把分级、复杂度自适应的 `LongformQualityVerifier` 接进 leaderboard composite(给实权重),取代当前 1.7% 的二元 `spec`。
- 复活 `AnalysisDepthVerifier` 的 Tier-A 确定性部分(矛盾词、比较语密度、多证据链、对立观点)作**始终在线(fast 模式也算)**的可奖励维度,让"分析色彩"在训练期间也真的被奖励(现状是 fast 跳过 -> 训练期等于关掉)。

### B4. 参考范文校准
- 每个任务类型落 1-2 篇 committed "好报告"(`data/reference_reports/`),作为 A2 比较式判分的锚点 + 生成端 few-shot 范例。
- 这一步同时服务打分(锚点)与生成(范例),性价比高。

---

## 4. 设计 C:多接入方式

地基(模态无关奖励、backend 工厂、tool 注册表、task `acquisition` 字段)都在,加接入方式是"接插件",不动奖励。

### C1. computer-use 真 VLM 策略(GPU 已解禁)
- 用真 `ComputerUsePolicy` 替换 `_TextProxyPolicy`:`observe()` 用 `page.screenshot()` + a11y 树(可选 Set-of-Marks),`act()` 用 VLM 输出 click/scroll/type/done 动作集。
- 循环、GUI 动作执行器、page seam 都已存在(`backends.py:441-634`),只需注入 VLM client(live-gated,保持 CI 离线)。
- 不变量:`fetch()` 仍终止于返回页面 grounding 文本,奖励契约不动。

### C2. Brave Search API(两种含义,两条路,务必分清)
- **(a) Brave 形状、沙盒后端(可复现,推荐默认)**:加一个 `brave` modality alias + 一个薄 `SandboxBackend`,`search` 打 shim 的 `/v1/brave/web/search`,`fetch` 复用 `/extract`。零复现张力,就是同一封闭语料换层皮。工作量 S。
- **(b) 真 Brave API、走真实互联网(字面意义的"Brave 介入")**:`BraveSandboxBackend` 调 `api.search.brave.com` + 订阅 token。**这会直接打破封闭 allowlist 的可复现性论点**:strict 模式会 403 掉所有非沙盒 URL,proof-of-fetch 要求被引 URL 可复现抓取,真实结果跨 run 不确定。
  - 建议:若要,必须做成**清晰标注的、非 strict、非可复现的"探索/演示 eval 模式"**,且**排除在 canonical RL/打分路之外**。决策见 §7。

### C3. 其它接入方式
- **RAG**:跑 `build_rag_index`(faiss + sentence-transformers),把 `rag_search` 从 seam 变实(live-gated)。
- **on-page image vision**:注入真 `Captioner`/VLM,`read_image` 落地(GPU 已解禁)。
- **17 modality survey** 已在 `docs/ACQUISITION_ROADMAP.md`;明确**不做**的:学术 API、开放网搜索、live email/calendar(无 live 互联网,做了要么假要么破坏封闭可复现)。

### C4. 模态无关奖励(已具备,作地基)
- 所有 backend / tool 把 `(url, text)` 落进同一 `retrieved_snippets`,奖励只读这里。新增接入方式自动继承 truth-gate,无需改打分。已有 `tests/test_modality_parity.py` 证明。

---

## 5. 设计 D:简单 scale up

按"最省力先做"排序:

1. **判分吞吐**:judge 调用异步 + 结果缓存(按 report-hash + dim + judge-identity),重复评测不重算。这是评测端 scale 的最大杠杆。
2. **任务量**:反向双语任务生成器(seed -> frontier 模型加约束 -> rubric tree -> 双语 NL 问题 -> 每叶自动 checker),把手工 120 题扩到 1000+,带跨模型外验质量过滤。详见 `FULL_PROJECT_ROADMAP.md` Phase 3。
3. **agent 量**:runner 是自动发现的(`scripts/runners/registry.py`),加一个 agent 只是加一个 `*_runner.py`。
4. **接入方式量**:加 modality = 加一个 backend + alias;加工具 = 写 `provide_tools()` + 进 `_PROVIDERS`。都是接插件。
5. **算力**:单卡 5090 只做 efficacy pilot;评测吞吐靠缓存 + 异步,不靠堆卡。

---

## 6. 设计 E:目录与文档整理(分级 + 风险)

原则:**先做零风险的清理,结构性移动给你过目后再动**(有 HIGH 风险项会断站点)。

### E1.(零风险,可立即做)忽略与清理临时/产物
- `.gitignore` 增:`*.bak`、`**/*.preV1*`、`**/*.preFix*`、`docs/*.aux/.log/.out/.toc`、`paper/*.aux/.bbl/.blg/.log/.out`。
- `git rm --cached` 那 568 个 `.bak`/`.preV1`/`.preFix`(~4.2M)+ 已提交的 LaTeX 中间产物。最大、最低风险的一刀。
- 本地删 `__pycache__`、`.pytest_cache`(已 gitignored,无影响)。

### E2.(低风险)docs/ 分类 + 根目录老草稿归档
```
docs/
  design/    ACQUISITION_MODALITIES, STRICT_SANDBOX_CONTRACT, REPOSITORY_STRUCTURE,
             ASSET_OWNERSHIP_AND_DELIVERY, EVAL_REDESIGN_DESIGN(本文)
  rl/        ACQUISITION_ROADMAP, AGENTRL_TASK_SPEC, PHASE_B_QWEN_GRPO_SPEC
  scoring/   SCORING_V3_DIFF, SEPARABILITY_*, HUMAN_EVAL_PROTOCOL,
             HUMAN_ALIGNMENT_REPORT, JUDGE_HUMAN_KAPPA
  roadmap/   FULL_PROJECT_ROADMAP, FULL_REPORT_EVAL_AGENTRL_ROADMAP,
             PROJECT_DELIVERY_ROADMAP_BRIEF, NON_GPU_TECHNICAL_EXECUTION_PLAN,
             RESEARCH_SURVEY, PATENT_DISCLOSURE_DRAFTS
  paper/     DEFENSE_DOC, PROJECT_WRITEUP(见风险), PPT_OUTLINE, defense_walkthrough.html
  handoff/   CODEX_HANDOFF, EVAL_REPO_CLEANUP, LOCAL_DEV_CHECKS, TIER0_LOCAL,
             RUN_V2_VALIDATION, FRONTEND_V3_CHANGELOG
  templates/ (不动)
  archive/   根目录老草稿:RESULTS_SUMMARY*, HANDOFF*, ELO_*PLAN_*, *_AUDIT*,
             FRAMEWORK_*, IMPROVEMENT_*, PROGRESS_REPORT 等
```

### E3.(需你拍板的结构性决定,见 §7)
- 三前端取一:生产源是 `frontend/`(CLAUDE.md 确认),建议**删 `web-next/`**,`web/` 仅留 `dist/` 产物。
- 三 paper 树合并到 `paper/`(`paper_deep/`、`latex/` 并入),build 产物 gitignore。
- 大小写重复:定 `AGENT.md`/`CLAUDE.md` 为 canonical,删小写版。

### E4. 风险红线(移动前必须处理)
- **HIGH:`docs/PROJECT_WRITEUP.md` 被 `web/build_static.py:243` 和 `web/server.py:637` 读取,移动会断站点构建。** 要么原地不动,要么同一 commit 改这两个 web 文件。
- **MEDIUM:`docs/SEPARABILITY_REPORT.md`、`HUMAN_ALIGNMENT_REPORT.md`、`JUDGE_HUMAN_KAPPA.md` 是脚本生成的产物**,移动需同步改脚本的输出路径。
- **LOW(注释引用,不断运行)**:`ACQUISITION_ROADMAP.md`/`ACQUISITION_MODALITIES.md`/`STRICT_SANDBOX_CONTRACT.md` 被多处 docstring 引用,移动后改注释即可。

---

## 7. 需要你拍板的开放项

1. **Brave 要哪种?**(§4.2)默认建议 (a) 沙盒后端(可复现);(b) 真 API 仅作隔离的非 canonical 探索模式。你要 (a)、(a)+(b),还是只 (b)?
2. **"纯 LLM 打分"的产品形态**:是 (i) 后台用纯 LLM 把质量分做对(本文 A 方案),还是 (ii) 还要在公开榜/报告页给用户展示一栏"LLM 综合评语 + 分数"?(ii) 在 (i) 做对后是附加展示层。
3. **目录结构性移动**(§6 E3):web-next 删否、三 paper 树合否、大小写 canonical 选哪个?这几项我需要你点头再动(其余 E1/E2 我可在你批准后直接做)。
4. **本轮先打哪条主线?** 建议 A1+A5(修 bug + 请回确定性信号)性价比最高,且不需要在线沙盒/GPU,可立即离线落地。

---

## 8. 落地顺序与验收

> 分工:Claude 出规格 + 验收脚本 -> Codex 实现 -> Claude 独立验证 -> 记入对应 docs。改打分/任务/沙盒/前端/方法论**部署前**必须写 `data/changelog.json`(目前都未部署,changelog 草稿待你决定上线时再落)。

**离线即可做(无需沙盒/GPU):**
- A1 修证据 bug;A5 请回 FactKG 等确定性信号 + 重推权重;B1 policy 目标对齐;B3 LongformQuality 上榜 + AnalysisDepth Tier-A 复活;E1 临时文件清理;E2 文档分类。
- 验收:5 个旧 V3 符号字节不变;全套 pytest 不回归(基线 122 passed / 4 skipped);honest >> 各 hack 差距扩大;判分传 evidence 不再抛错。

**需在线(my5090 沙盒/GPU):**
- A2/A3/A4 判分重做后用真 judge 测 F-ratio 与 κ 提升;C1 真 VLM computer-use;C2(b) 真 Brave;C3 建 RAG 索引 + vision;F 系列 golden 重建 + Half A 端到端;Phase 5 GRPO pilot。
- 验收:重做后 depth/rigor/style 的 F-ratio 显著高于 2.30、κ 抽检 > 0.4(rigor 从负转正);Tier-0 三探针(rich >> thin、奖励排序、judge 一致)作 go/no-go。

**最高杠杆的第一刀(建议本轮就做):A1 + A5 + B3。** 因为当前约一半质量权重是噪声、证据线是断的、最该当主信号的 FactKG 被排除,这三刀最便宜、影响最大,且全部离线可做可验。
