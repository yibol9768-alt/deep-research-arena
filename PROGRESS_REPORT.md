# 项目进度汇报

**项目名称:** Deep Research Benchmark — 基于真实网站沙盒的 AI Agent 深度研究评测框架

**汇报日期:** 2026-04-16

---

## 一、项目定位

> 构建了第一个「可控沙盒（自有数据/可复位）+ Deep Research 任务（非 UI 操作）+ 六维确定性评分（非纯 LLM Judge）+ Arena Elo 排位」一体化的 AI Agent 评测系统。

---

## 二、已完成工作

### 1. 基础设施（4/15–4/16）

- 在远程服务器（Windows 11 + WSL2 Ubuntu + Docker CE）上成功部署两个真实网站沙盒容器：
  - **Shopping**（Magento 电商站，端口 7770）：镜像 63 GB，展开 141 GB
  - **Reddit**（Postmill 论坛站，端口 9999）：镜像 49 GB，展开 107 GB
- Mac ↔ 服务器 SSH 隧道配置完成，支持自动重连 keepalive
- Gitlab 镜像下载中（72 GB，ETA 今日下午）

### 2. 任务设计（4/16）

- 共设计 **9 条 Deep Research 任务**（5 条 Shopping + 4 条 Reddit），覆盖信息检索、比较分析、多约束择优、跨论坛统计等场景
- 每条任务配套：
  - **Oracle 脚本**（Playwright 自动验证，9/9 全部 PASS）
  - **DRACO 风格 coverage checklist**（5–6 条二值检查项）

### 3. 六维评分框架 v2（4/16）

参考 DRACO / DeepResearch Bench / FActScore / ALCE 等 2024–2025 年前沿工作，构建如下评分体系：

| 维度 | 权重 | 说明 |
|---|:---:|---|
| Deterministic | 30% | JSON Schema + 字段约束匹配，零方差 |
| Factuality | 25% | 引用页面内容是否支持所声明的事实 |
| LLM Judge | 15% | 4 维 RACE 风格评分（全面性/洞察深度/指令遵循/可读性）+ CoT |
| Citation | 15% | ALCE 风格 citation recall / precision / F1 |
| Comprehensiveness | 10% | DRACO 式 coverage checklist 逐条二值判定 |
| Efficiency | 5% | token 消耗 / 耗时 / 成本 |

### 4. Arena Elo 排位系统（4/16）

实现三种 Elo 排位模式（类比 Chatbot Arena）：

- **Composite Elo**：按 6 维加权综合分做 pairwise battle
- **Pairwise Judge Elo**：LLM 直接侧对侧对比两份报告选 winner（AB 换位各跑一次，防 position bias）
- **Per-pillar Elo**：每个维度独立 Arena，定位各 Agent 的强项维度

### 5. Agent 基线接入（4/16）

接入 4 个 Agent 进行横向对比：

| Agent | 架构 | 驱动模型 |
|---|---|---|
| react-glm51 | 单 Agent ReAct + 8 个 Playwright 工具 | GLM-5.1 |
| react-glm46 | 同上 | GLM-4.6（推理模型） |
| react-glm45 | 同上 | GLM-4.5（非推理模型） |
| deerflow-glm51 | 字节 DeerFlow v1 多 Agent（coordinator→planner→researcher→analyst→reporter） | GLM-5.1 |

---

## 三、当前最新实验结果（2026-04-16 10:39）

**实验规模:** **9 task × 4 agent × 27 battles/agent**(5 shopping + 4 reddit)

**Composite Elo 排名:**

| 排名 | Agent | Elo | 胜-负-平 |
|:---:|---|---:|:---:|
| 1 | deerflow-glm51 | **1050** | 17-10-0 |
| 2 | react-glm46 | **1045** | 13-8-6 |
| 3 | react-glm51 | 969 | 9-13-5 |
| 4 | react-glm45 | 936 | 6-14-7 |

**Pairwise Judge Elo(LLM 直接侧对侧):**

| 排名 | Agent | Elo | 胜-负-平 |
|:---:|---|---:|:---:|
| 1 | react-glm45 | **1104** | 20-7-0 |
| 2 | deerflow-glm51 | 1020 | 15-12-0 |
| 3 | react-glm46 | 981 | 12-15-0 |
| 4 | react-glm51 | 895 | 7-20-0 |

### 重大发现

1. **从 5 task 扩到 9 task,DeerFlow 优势从 +122 缩到 +5 Elo** —— 因为多 site 后 GLM 内容安全在 reddit 长 prompt 上多次拦截 DeerFlow 的研究流程(dr_red_0001 / 0004 直接 0.04 分),而单 agent ReAct 上下文短没踩雷。**多 site 暴露了 DeerFlow 的鲁棒性弱点**。

2. **react-glm46(单 agent + 中等推理模型)反超到第 2** —— 在 reddit 0001 上拿到 0.93 史诗级表现。说明:对结构化 DR 任务,单 agent + 推理模型已经够用,DeerFlow 的 Plan-Execute-Report 反而是过度设计。

3. **Composite vs Pairwise Judge 出现严重背离** —— Composite 把 glm-4.5 排第 4(垫底),Pairwise judge 把它排第 1(1104)。说明 LLM judge 对简洁回答有强偏好(length bias 复现得很干净)。**这本身是论文的一个观察点**:确定性多维评分 vs 单一 LLM judge 的可信度差异。

4. **9 task 区分度 vs 5 task**:Pairwise Elo 极差从 122 → 209,**任务越多区分越显著**。

### Per-pillar Elo(每个维度独立 Arena)

| Agent | Cite | Comp | Det | Eff | Fact | Judge |
|---|---:|---:|---:|---:|---:|---:|
| **deerflow-glm51** | **1154** | 963 | 865 | 1000 | **1154** | 988 |
| react-glm51 | 924 | 1042 | **1068** | 1000 | 924 | 1011 |
| react-glm46 | 961 | **1057** | 1034 | 1000 | 961 | **1076** |
| react-glm45 | 961 | 938 | 1032 | 1000 | 961 | 925 |

DeerFlow 仍独占 Cite/Fact 维度,但被 ReAct 反超在 Det(JSON 严格)和 Comp/Judge 维度。

### 历史对照:5 task × 4 agent(2026-04-16 06:00)

| 排名 | Agent | Elo | 胜-负-平 |
|:---:|---|---:|:---:|
| 1 | deerflow-glm51 | 1097 | 12-3-0 |
| 2 | react-glm51 | 975 | 4-6-5 |
| 3 | react-glm45 | 968 | 3-6-6 |
| 4 | react-glm46 | 960 | 3-7-5 |

---

## 四、代码产出

- 总代码量约 **3000+ 行 Python**（verifier / scorer / agent / scraper / oracle / bench CLI）
- 单元测试 **21/21 全绿**
- 完整技术文档：`PLAN.md` / `SCORING_FRAMEWORK.md` / `DEEP_RESEARCH_TASK_SPEC.md` / `ROADMAP.md`

---

## 五、进行中事项

1. **9 条任务 × 4 Agent MEGA Arena 全量评分**（Reddit 4 条已跑完 baseline，正合并评分，预计 30 分钟 API 调用完成）
2. **Gitlab 镜像下载**（72 GB，25%，ETA 今日下午 1–2 点）
3. **Shopping_admin + Wikipedia 镜像**排队下载中

---

## 六、后续计划与预估工期

| 事项 | 预计工期 |
|---|---|
| MEGA Arena 全量评分出炉 | 30 分钟 |
| Gitlab 镜像部署完成 | 今天下午 |
| Shopping_admin + Wikipedia 部署 | 今晚至明天 |
| Golden Answer 真值库（Oracle dump 固化） | 1 天 |
| DeerFlow reporter 改出 JSON（提升 Deterministic 得分） | 半天 |
| 扩展至 4 站 × 各 10 条任务（40+ 条 benchmark） | 1–2 周 |
| FActScore 原子事实提取器 | 2–3 天 |
| Dual Judge（需要非 GLM API key） | 依赖 Claude/DeepSeek key 申请 |
| 论文初稿 | 2–3 周 |

---

## 七、当前风险与应对

| 风险 | 说明 | 应对方向 |
|---|---|---|
| 自评偏差 | GLM 评 GLM 存在 self-preference 偏差 | 申请 Claude / DeepSeek key 做 Dual Judge |
| 任务约束过松 | 不同答案都能通过，评分区分度不足 | 构建 Golden Answer 真值库，收紧约束 |
| 数据污染 | WebArena 种子数据可能被新模型训练集覆盖 | 引入换皮/数据扰动机制 |
