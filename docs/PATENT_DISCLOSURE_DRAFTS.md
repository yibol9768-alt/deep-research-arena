# Deep Research Arena 专利披露草案

版本：2026-06-03 初版

说明：本文是技术披露草案，不是法律意见。正式递交前需要专利代理人把技术方案改写为权利要求书，并检查公开披露时间线。

## 1. 专利候选一：受控沙盒 Deep Research 评测与训练方法

### 1.1 要解决的问题

开放网 Deep Research 评测存在三个核心问题：

1. 检索结果和网页内容随时间漂移，导致同一任务难以复现。
2. 长报告的事实性无法稳定验证，URL 可能 404、页面可能改版、地理位置可能影响访问。
3. 不同 agent 的检索器、浏览器、工具接口不统一，评价结果混入大量底层 retrieval 差异。

### 1.2 技术方案

构建一个封闭的本地沙盒语料环境，由商品站、论坛站、百科站和统一 search shim 组成。所有 agent 只能从允许的本地 URL 获取证据，所有最终报告的引用必须解析到取回过的本地页面。评分时不关心证据是通过搜索、浏览器、RAG、SQL、vision 还是 computer-use 得到，只关心它是否以 `(url, text)` 形式进入检索存储并支持报告中的 claim。

核心组件：

- 受控语料：Magento、Postmill、Kiwix。
- 统一协议：Tavily/Firecrawl-compatible search shim。
- 证据记录：`retrieved_snippets`、`fetched_urls`、proof-of-fetch logs。
- 严格边界：adapter allowlist、shim strict mode、post-run sandbox audit。
- 打分：引用解析率、页面支持度、事实三元组、结构和质量维度。

### 1.3 独立权利要求草案

一种用于研究型智能体评测和训练的方法，其特征在于：

1. 将智能体可访问的信息源限制在一个由多个本地服务组成的封闭语料环境中。
2. 通过统一检索协议适配层向不同智能体框架提供一致的搜索和页面抽取接口。
3. 记录智能体在任务执行过程中实际取回的 URL 与文本内容。
4. 在评分时要求最终报告中的引用 URL 命中实际取回记录。
5. 使用与证据获取方式无关的接地评分信号，对报告内容与被引用页面之间的支持关系进行评价。

### 1.4 从属权利要求方向

- 多来源本地语料的组合方式：商品页、论坛帖、百科文章。
- 对越界 URL 的三层拦截和审计。
- 不同智能体框架通过同一 shim 接入，从而降低框架适配差异。
- 双裁判 Elo、bootstrap 置信区间和 per-pillar 评分。
- 将同一接地评分信号用于评测和强化学习训练。

### 1.5 可落地实施例

本项目中的 `integrations/search_shim/`、`docs/STRICT_SANDBOX_CONTRACT.md`、`src/eval/evaluator.py`、`src/verifiers/`、`src/scoring/` 可作为实施例素材。

### 1.6 公开披露风险

README、站点和部分文档已经描述了受控沙盒 benchmark 的思想。正式申报时应把重点放在组合机制、取回记录门控、模态无关接地评分和统一协议适配这几个更具体的技术特征上。

## 2. 专利候选二：面向工具使用 Deep Research 智能体的 Agentic RL 训练系统

### 2.1 要解决的问题

Deep Research 任务通常要求大量页面、长报告、多引用和多步综合，小模型在有限工具调用预算内会全部失败，导致 GRPO 或类似 RL 算法没有组内奖励方差。同时，工具越多，越容易出现安全越界和 reward hacking。

### 2.2 技术方案

构建一个按任务声明工具能力的 Agentic RL 环境。基础动作空间保持稳定，仅增加通用 `CallTool` 动作。每个任务通过 `acquisition.tools_allowed` 决定工具注册表，默认只开放 `search` 和 `fetch`。能产生证据的工具把 `(url, text)` 写入 snippets，写操作工具只产生 `state_delta`，由独立 state-diff verifier 评分。

训练任务被设计为预算可行：硬阈值低于 8 次左右工具调用可达上限，使 competent、mediocre、shallow、fabricated rollout 之间保持可区分奖励差。strict grounding gate 让 no-fetch 和 cite-without-fetch 的 rollout 归零，阻止只写流畅报告拿分。

### 2.3 独立权利要求草案

一种面向工具使用研究型智能体的强化学习训练系统，其特征在于：

1. 根据任务配置动态构建工具注册表，并通过单一工具调用动作接入异构工具。
2. 对每个工具设置输入 schema、允许列表、安全约束和结果折叠规则。
3. 将证据型工具的输出折叠为 URL 与文本片段，并由统一接地奖励评分。
4. 将状态变更型工具的输出折叠为状态差异，并由独立状态验证器评分。
5. 将训练任务的长度、引用、页面数和覆盖率阈值设计在固定工具调用预算内，以保持组内奖励方差。

### 2.4 从属权利要求方向

- `tools_allowed` 对工具能力按任务授权。
- SQL 只读、表/列白名单、行上限和 timeout。
- code/batch 执行的本地主机网络锁和资源限制。
- computer-use 或 vision 工具通过注入 seam 接入，不改变奖励契约。
- 用户模拟器和 pass^k state-diff 评价。
- no-dense RAG index 路径与 dense 路径共存，重依赖惰性导入。

### 2.5 可落地实施例

本项目中的 `src/rl/tools.py`、`src/rl/env.py`、`src/rl/action_parser.py`、`src/rl/tools_write.py`、`src/rl/tools_vision.py`、`src/verifiers/state_diff_verifier.py`、`scripts/build_rag_index.py`、`data/tasks/deep_research/rl/` 和 `scripts/rl_task_validate.py` 可作为实施例素材。

### 2.6 公开披露风险

`docs/AGENTRL_TASK_SPEC.md`、`docs/ACQUISITION_ROADMAP.md` 和本路线图已经较具体。建议在公开发布模型、benchmark v0.1 或论文预印前完成该专利方向的正式披露。

## 3. 申报前检查清单

1. 确认两个候选是否拆成两件申请，或作为一件主案加一个分案。
2. 画 3 张图：系统架构图、工具注册表与奖励折叠图、RL 训练闭环图。
3. 准备 2 个实施例：只读报告任务、写操作 state-diff 任务。
4. 准备对比表：live web benchmark、static corpus benchmark、WebArena、tau-bench、我们。
5. 在公开站点、论文预印、模型权重和 benchmark release 之前完成代理人审查。
