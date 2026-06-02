# Deep Research Arena 调研与创新点映射

版本：2026-06-03 本地初版

用途：本文件回答三个问题：已有工作怎么分布，我们已经做了什么差异化东西，还需要补哪些证据才能支撑论文、专利和交付。

## 1. 调研结论

Deep Research 评测和训练工作大体分成五类：

| 类别 | 代表方向 | 优点 | 主要短板 | 我们的位置 |
| --- | --- | --- | --- | --- |
| Live web Deep Research benchmark | DeepResearch Bench、DRACO、ResearcherBench、BrowseComp 类任务 | 真实开放网，生态感强 | 搜索与网页漂移，复现实验困难，检索器和 agent 能力混在一起 | 不和它们争开放网覆盖，主打可复现科学测量 |
| 静态语料检索 benchmark | BrowseComp-Plus、固定文档 RAG QA | 检索路径可复现，能拆分 retrieval 和 reasoning | 多数偏 QA，不测交易型网页和长报告综合 | 我们继承静态语料可复现性，但加入 Magento/Postmill/Kiwix 混合场景 |
| WebArena 类沙盒 | WebArena、WebArena-Verified、VisualWebArena | 真实网页交互，容器化，任务可重放 | 多数测 UI task completion，不测 Deep Research 长文 | 我们把 WebArena 血统扩展成 Deep Research 报告评测 |
| Grounded generation / citation eval | ALCE、FactScore、RAGAS、citation NLI | 可以检查引用支持和事实性 | 往往没有完整 agent 环境和工具链 | 我们把引用支持变成受控沙盒 reward 的核心 |
| Agentic RL 与 tool-use training | GRPO、tau-bench/tau2-bench、code/tool agents、computer-use | 能训练工具使用与多步策略 | 奖励容易被 hack，任务预算不匹配会零方差 | 我们用预算可行 RL task、strict grounding gate、state-diff verifier 保持训练信号 |

一句话定位：Deep Research Arena 是一个可复现的混合场景 Deep Research 系统，结合静态语料 benchmark 的复现性、WebArena 的真实网页沙盒、ALCE 类引用支撑检查，以及 Agentic RL 的工具使用训练。

## 2. 相关工作要点

### 2.1 开放网 Deep Research benchmark

这类 benchmark 的价值是生态真实，能测产品级 agent 的开放网能力。问题是同一查询、同一 URL、同一网页在不同时间和机器上会漂移。评分者无法区分 agent 编造、网页 404、搜索重排、地区 CDN 差异和访问权限变化。对论文来说，这会削弱可复现性和可证伪性。

我们的取舍是：牺牲开放网广度，换取受控语料、固定 URL、固定 search shim 和可重跑评分。

### 2.2 静态语料与 RAG benchmark

静态语料 benchmark 的强点是可以把 retrieval quality 和 reasoning quality 分开分析。BrowseComp-Plus 一类工作证明固定语料有学术正当性，能避免黑盒搜索 API 带来的不稳定。

我们的扩展是：不只做固定文档 QA，而是把商品页、论坛帖子、百科文章放进同一个 Deep Research 环境，让 agent 同时处理产品事实、用户观点和背景知识。

### 2.3 WebArena 与视觉/浏览器环境

WebArena 系列证明了容器化网页环境可以测 agent 的交互能力。VisualWebArena 和 OSWorld 进一步强调截图、a11y tree、GUI action 的重要性。

我们的扩展是：把网页交互从 task completion 转成 evidence acquisition。浏览器、computer-use、vision 的最终目标不是完成 UI 操作，而是把可引用证据落到 `retrieved_snippets`，再由同一 grounding reward 评分。

### 2.4 引用、事实性与 LLM judge

ALCE、FactScore、RAGAS、LLM-as-judge 系列工作都说明，长文报告不能只看流畅度。引用是否真实、引用页面是否支持 claim、结构是否完整、覆盖是否充分，必须拆开评分。

我们已经有七维 composite：citation、evidence_density、llm_judge、checklist、fact_kg、markdown_structure、efficiency。后续论文需要补的是人工审计校准和消融：证明这些维度确实和人类判断一致，并且能抓住 URL hallucination、single-domain、padding、style bias 等失败模式。

### 2.5 Agentic RL、tau-bench 与 state-diff

Agentic RL 的关键难点不是只把 reward 写出来，而是任务预算和奖励曲线要匹配。大任务对 4B/3B 小模型来说会全部失败，GRPO 组内奖励变成常数，没有梯度。

我们已经单独设计 RL-suitable task set，让 8 次左右工具调用内能产生非零分化，并加入 strict grounding gate。write action 和 `StateDiffVerifier` 则把 tau-bench 风格的执行结果评价接进来，作为 grounding 之外的第二奖励契约。

## 3. 我们已经做成的东西

| 资产 | 状态 | 证据路径 |
| --- | --- | --- |
| 受控沙盒环境 | 已建成 | `README.md`、`docs/STRICT_SANDBOX_CONTRACT.md` |
| 搜索 shim 与 strict allowlist | 已建成 | `integrations/search_shim/`、`docs/STRICT_SANDBOX_CONTRACT.md` |
| 多框架 leaderboard | 已建成 | `README.md`、`data/results/`、`src/scoring/` |
| 七维 composite scorer | 已建成 | `src/verifiers/`、`src/scoring/` |
| RL 环境与 GRPO harness | 已建成骨架 | `src/rl/env.py`、`src/rl/grpo.py`、`scripts/train_grpo_pilot.py` |
| 工具注册表与 `CallTool` | 已建成 | `src/rl/tools.py`、`src/rl/action_parser.py` |
| RAG/SQL/crawl/exec/write/vision tools | 已建成离线路径 | `src/rl/tools_*.py` |
| state-diff verifier | 已建成离线路径 | `src/verifiers/state_diff_verifier.py` |
| computer-use observe-act wiring | 已建成离线路径 | `src/rl/backends.py` |
| RL-suitable task set | 已建成并离线 READY | `data/tasks/deep_research/rl/`、`docs/AGENTRL_TASK_SPEC.md` |
| 本地 smoke | 已建成 | `scripts/check_track_a_local.sh`、`docs/LOCAL_DEV_CHECKS.md` |

## 4. 创新点映射

| 创新点 | 对应实现 | 论文证据需求 | 专利潜力 |
| --- | --- | --- | --- |
| 受控沙盒 Deep Research benchmark | Magento/Postmill/Kiwix + shim + strict sandbox | 多框架 leaderboard、人工审计、复现实验 | 高 |
| 模态无关 grounding reward | `retrieved_snippets` + cited URLs + `s_ground` | modality parity、工具 ablation、反编造实验 | 高 |
| 工具注册表上的异构工具接入 | `ToolRegistry` + `CallTool` + `tools_allowed` | 默认路径不变、工具安全测试、任务增益 | 中高 |
| 预算可行 RL 课程 | `data/tasks/deep_research/rl/` + validator | reward curve、GRPO variance、pilot 曲线 | 高 |
| 执行态 state-diff verifier | `tools_write.py` + `state_diff_verifier.py` | write task、mock 到真实 DB 迁移 | 高 |
| 严格本地安全包络 | SQL allowlist、exec 网络锁、strict URL audit | 攻击用例、microVM 验证 | 中高 |
| 开放小模型 Deep Research agent | QwenPolicy + GRPO + LoRA release | 训练曲线、eval card、baseline 对比 | 中 |

## 5. Claim-to-Evidence Map

| 论文/交付主张 | 当前证据 | 还缺的证据 |
| --- | --- | --- |
| 我们的 benchmark 可复现 | strict sandbox、shim、固定任务、离线回归 | 第三方复现脚本、benchmark datasheet |
| 模态无关 reward 成立 | `tests/test_modality_parity.py` | 活沙箱 parity，工具 acquired evidence parity |
| RL task 有训练信号 | `rl_task_validate.py` reward curve | 真实 Qwen GRPO pilot trend |
| 工具使用不会破坏安全 | SQL/exec/crawl 单测 | 真实 sandbox + microVM/DB allowlist 验证 |
| 小模型能学 grounded Deep Research | QwenPolicy/GRPO 规格 | 训练曲线、held-out eval、消融 |
| leaderboard 结论有学术可信度 | dual judge Elo、bootstrap、per-pillar | 人工审计、更多 battles、oracle v2 重打分 |

## 6. 还需要补的调研和实验

1. 文献侧：把 DeepResearch Bench、DRACO、ResearcherBench、BrowseComp-Plus、WebArena-Verified、tau2-bench、OSWorld、VisualWebArena、ALCE、FactScore、RAGAS、DR Tulu、CaRR、QUEST 做成论文 related work 表。
2. 数据侧：为 benchmark v0.1 写 datasheet，说明任务来源、语料边界、污染风险、license、训练集/测试集分离。
3. 实验侧：补 human audit、oracle v2 重打分、modality ablation、tool ablation、anti-fabrication、GRPO pilot。
4. 发布侧：先完成专利披露，再公开模型、benchmark、Demo 和论文预印。

## 7. 论文落点建议

### 论文 A：Benchmark

核心问题：如何构建一个可复现、可打分、可比较多框架的 Deep Research benchmark。

核心贡献：受控混合沙盒、strict grounding gate、dual-judge Elo、多框架结果、失败模式分析。

证据优先级：人工审计、leaderboard 扩展、oracle v2、per-pillar 消融。

### 论文 B：Agentic RL

核心问题：如何在受控证据获取下训练一个小模型 Deep Research agent。

核心贡献：预算可行 RL 课程、工具注册表、grounding + state-diff 双奖励契约、single 5090 GRPO pilot、开放 LoRA。

证据优先级：reward variance、finite loss、checkpoint/resume、before/after report quality、tool ablation。
