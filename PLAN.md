# Deep Research Benchmark — 进度 & 规划

**项目**:刘奕博
**最后更新**:2026-04-16 10:50
**目标(总)**:构建一个**真实网站沙盒 + Deep Research 任务 + 确定性评分 + Arena Elo 排位**的 AI Agent 评测框架,用于量化比较不同多智能体系统在 Deep Research 上的能力。最终产出:**学术论文 + 可复现 benchmark**。

---

## 0. 一句话现状

> **已经可以用的东西**:2 个真实沙盒站(shopping + reddit)、9 条 DR 任务(5 shop + 4 red)、Oracle 全过、6 pillar 评分框架、3 种 Elo 排位、4 agent × 9 task × **27 battles/agent** MEGA Arena 跑通。**关键反转**:加 reddit 后 DeerFlow 优势从 +122 缩到 +5 Elo(GLM 内容安全在长 prompt 上拦了 DeerFlow);**glm-4.6 单 agent 反超到第 2**;**LLM judge 暴露 length-bias**(glm-4.5 简洁回答被 judge 排第 1,composite 排第 4)。

---

## 1. 时间线

| 日期 | 里程碑 |
|---|---|
| 2026-04-15 (日间) | 187 条 WebArena 原版 shopping 任务归档;Runner + 基础 verifier |
| 2026-04-15 (夜) | Shopping Docker 部署到 westd;端到端 smoke task 21 score 1.0 |
| 2026-04-16 00:00 | Stage B 5 条 shopping DR 任务;Oracle 5/5 PASS;GLM-5.1 ReAct 基线 0/5 |
| 2026-04-16 02:20 | DeerFlow v1 接入;shop_adapter monkey-patch;首次多 agent 报告 |
| 2026-04-16 03:00 | **Scoring v2**(ALCE 双指标 / 4 维 LLM judge / Efficiency / Composite) |
| 2026-04-16 03:30 | **Arena Elo**(Composite + Pairwise judge + Per-pillar)|
| 2026-04-16 04:00 | **DRACO checklist verifier**(替换 comprehensiveness 占位)|
| 2026-04-16 04:15 | 3 个 GLM ReAct variant(5.1 / 4.6 / 4.5)+ DeerFlow = 4-way Arena |
| 2026-04-16 06:00 | 5 task × 4 agent × 15 battle **最终 Arena**(DeerFlow 1097 ≫ ReAct ~960-975)|
| 2026-04-16 07:40 | Reddit (Postmill) 沙盒就位,容器 healthy,Mac tunnel 9999 ✓ |
| 2026-04-16 08:45 | 4 条 reddit DR 任务 + Oracles + Checklists(4/4 PASS)|
| 2026-04-16 09:00 | ReAct agent **泛化**(支持 site-aware tool registry,shopping + reddit 共用) |
| 2026-04-16 09:30 | 3 GLM ReAct × 4 reddit task = 12 runs |
| 2026-04-16 09:50 | DeerFlow `reddit_adapter.py` —— DeerFlow 也能跑 reddit |
| 2026-04-16 10:30 | **MEGA Arena**:9 task × 4 agent × 27 battles/agent + 全量评分 + pairwise judge |
| 🟡 进行中 | gitlab 镜像下载(25% ETA 4h);shopping_admin + wikipedia 排队 |

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

17 单测 + 4 Arena 测试 = **21/21 全绿**。

### 2.6 文档

- `RESEARCH.md` —— 最初愿景
- `SCORING_FRAMEWORK.md` —— v2 六柱评分设计
- `DEEP_RESEARCH_TASK_SPEC.md` —— DR 任务规范
- `ROADMAP.md` —— Stage A/B/C 路线图
- `data/results/NIGHT_RUN_SUMMARY.md` —— 通宵工作流水账(最新)

---

## 3. 未完成 / 待做(按优先级)

### P0(本周内,最大投资回报)

~~1. Reddit agent baseline~~ ✅ **已完成**(MEGA Arena 包含全部 9 task × 4 agent)

1. **Golden Answer 真值库** — 目前约束过松,两个 agent 返回不同产品都能过
   - 方案 1:Oracle 跑一次把答案固化到 `data/golden/<task>.json`,评分加"关键字段 set 匹配"
   - 方案 2(并行):直连 Magento MySQL 导出 Product / Category / Review 实体 + 关系 → networkx 图,每条任务写图查询作为真值
   - 先做方案 1(1 天),方案 2 慢慢搞

2. **修 DeerFlow reporter 出 JSON** — 目前 DeerFlow composite 里 deterministic=0(prose markdown),Composite 被硬拖 30%
   - 方法 A:patch `src/prompts/reporter.md` 加"如果 user 消息里有 report_schema,只输出 JSON"
   - 方法 B:加个后置 `json_extractor` 节点用 LLM 把 prose 转 JSON
   - 做完后 DeerFlow Composite 预期破 0.8,对 ReAct 重新拉开优势

3. **追加任务** —— 9 task 已可区分(Elo 极差 209 分),但每 site 4-5 条还是单薄,扩到 8-10 条会把 Elo 误差棒(±σ)收窄一半
   - 新设计 5 条 shop + 4 条 reddit = 18 task 总量
   - 已知薄弱:0003/0004 这种"多页聚合"题目特别区分能力,多设计这种类型

### P1(本月内)

4. **FActScore 原子事实提取器** — factuality pillar 当前是 citation_precision 的 proxy
   - LLM 从 agent 输出提 `(entity, attribute, value)` 三元组
   - 每个三元组:若有 citation URL 就 fetch URL 验;若没有就直接 query Magento
   - 目标:factuality ≠ citation,独立信号

5. **DRACO checklist 扩量** — 每条任务现在 5-6 条二值项,DRACO 是 40 条
   - 用 LLM 自动生成 checklist 候选,人工挑过筛
   - 提 IAA(多标注者 Cohen's κ)

6. **Dual judge** — 目前 GLM-5.1 既当 agent 又当 judge,self-preference 风险
   - 需要 **非 GLM 族**的 judge(Claude / DeepSeek / Doubao / Kimi)—— **缺 API key**
   - 先用 GLM-5.1 + GLM-4.6 做粗的 dual 看 κ;再等申请到 key 后换

7. **gitlab / shopping_admin / wikipedia 沙盒** — 等下载完(gitlab ETA 10h)
   - 写 `envs/gitlab/` docker-compose + reset.sh(已预置)
   - shopping_admin 是 shopping 的运营后台,复用 shopping 的知识
   - wikipedia 走 kiwix-serve(已下 base image)

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
