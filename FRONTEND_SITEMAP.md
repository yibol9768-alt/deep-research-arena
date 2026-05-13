# Deep Research Arena — 前端完整内容地图

> v1.0 · 2026-05-12 · 配合 `C:\Users\liuyibo\.claude\plans\fluffy-purring-moonbeam.md` 使用
>
> 本文档把项目里**每一项**值得展示的资产都映射到前端页面/区块。基础页面参照 artificialanalysis.ai/models,创新页面是我们独有的差异点(标 ⭐)。

---

## 0. 站点结构总览

```
deep-research-arena.ai/
│
├─ /                         ⓘ Leaderboard 主页 (the 门面)
│
├─ /agents                   Agents Hub —— 14 个框架并排陈列
│   └─ /agents/[name]        Agent 个人主页 (动态,共 14 页)
│
├─ /tasks                    Tasks Explorer —— 107 道任务的可筛检索
│   └─ /tasks/[id]           Task 详情 (动态,共 107 页)
│
├─ /pillars                  7-Pillar Hub —— 评分体系总览
│   └─ /pillars/[name]       单 Pillar 深度页 (动态,共 7 页)
│
├─ /arena            ⭐      Live 1v1 — 任选两个 agent,实时算 Bradley-Terry
│
├─ /insights                 Findings & Stories — 把 F6/双 judge/Pareto 写成故事
│   ├─ /insights/f6-fluent-hallucination   ⭐ F6 流畅幻觉发现
│   ├─ /insights/dual-judge                ⭐ 双 judge 偏差实验
│   ├─ /insights/adapter-quality           ⭐ DeerFlow +162 Elo 案例
│   ├─ /insights/judge-length-bias         ⭐ smolagents 长度偏差
│   └─ /insights/pareto-front              Pareto 前沿
│
├─ /methodology              方法论(可锚链长文)
│   ├─ #composite             7-Pillar 公式
│   ├─ #bradley-terry         Elo + bootstrap CI 算法
│   ├─ #dual-judge            为什么用不同家族的 judge
│   ├─ #intent-typology       6 种 intent 分类
│   └─ #ablation              Ablation 结果
│
├─ /sandbox          ⭐      系统架构 3D 漫游(Shim + Sandbox + Verifier + Arena)
│   ├─ #magento              Shopping 沙盒规模与示例
│   ├─ #postmill             Reddit 沙盒
│   ├─ #kiwix                Wikipedia 沙盒
│   ├─ #shim                 Tavily/Firecrawl 兼容 Shim
│   └─ #ds-proxy             DeepSeek 代理
│
├─ /playground       ⭐      Pillar 权重游乐场 — 拖动权重看 Elo 重排
│
├─ /paper                    论文页 — 嵌入 NeurIPS PDF + 在线快读
│
├─ /changelog                项目时间线 (2026-04-15 → 至今,自动从 PROJECT_TIMELINE.md 渲染)
│
├─ /about                    项目介绍 + 团队 + 致谢
│
├─ /contribute               接入新框架指南
│
└─ /api/*                    静态 JSON 端点(供外部消费)
```

**总页数**:
| 类型 | 数量 |
|---|---|
| 一级页面 | **15** |
| Agent 详情(动态) | 14 |
| Task 详情(动态) | 107 |
| Pillar 详情(动态) | 7 |
| Insight 文章(动态,可拓展) | 5+ |
| **合计静态导出页面** | **≈ 148+** |

---

## 1. 全站通用组件

### 1.1 Header(顶部药丸 nav,所有页面都有)
- Logo(品牌字标 + 小动效呼吸圈)
- 主菜单:Leaderboard / Agents / Tasks / Pillars / Arena / Insights / Methodology / Sandbox / Paper
- 右侧:⌘K 全局搜索 / GitHub ⭐ stars 实时 badge / Twitter / Discord / Theme toggle
- ⭐ **创新**:右上角"Live Run Indicator" — 一个 1px 高的进度条,显示「当前正在 westd 上跑的 schtask」状态(从 sandbox `/api/health` ping)

### 1.2 Footer(紫色大区,所有页面都有)
- 大字标识 + Newsletter 订阅
- Explore / Project / Resources 三栏链接
- ⭐ **创新**:页脚最底部一行"Last leaderboard rebuild: 2026-05-06 02:14 UTC · 14 agents · 8 tasks · 52 battles" — 自动从 leaderboard JSON `mtime` 抓

---

## 2. 一级页面详细规划

---

### 2.1 `/` — Leaderboard 主页(门面页,最重要)

**目标**:5 秒内让访客理解「这是个 14 框架 × 107 任务的可复现 Elo 基准」。

**Sections(从上到下)**:

#### S1. Hero
- 大字 Serif: **Deep Research Arena**
- 副标 Inter: "The first reproducible Elo benchmark for Deep Research agents"
- 数字滚动条:`14 frameworks · 107 tasks · 312 battles · 7 pillars · 95% CI`(GSAP count-up)
- CTA: [Explore leaderboard ↓] [Read paper] [⭐ GitHub] [Try Arena]
- tsparticles 神经网络背景(品牌色粒子 + 连线)
- ⭐ **创新**:Hero 右下角悬浮一个迷你 tournament-bracket SVG 动效(随机两个 agent 名互相挑战,2 秒一换)

#### S2. Highlights 条(5 张卡片,模板化文案)
| 卡片 | 内容模板 | 数据源 |
|---|---|---|
| 🏆 Composite Elo | "**react-qwen35plus (1295)** and **gpt-researcher (1278)** lead the leaderboard" | `FINAL_LEADERBOARD.md` |
| 🎯 Citation Quality | "**gpt-researcher (91%)** and **react-glm5 (88%)** cite most accurately" | composite.citation_alignment |
| 🔬 Analysis Depth | "**deerflow-glm46-shim** writes the deepest analysis (4.6/5)" | composite.analysis_depth |
| ⚡ Efficiency | "**smolagents** runs at $0.18/task — 12× cheaper than the leader" | meta.cost_estimate |
| 🔥 Risers | "**deerflow-glm46-shim** jumped +162 Elo after adapter swap" | git diff over leaderboard |

⭐ **创新**:卡片 hover 时,背景品牌色渐变扩散一圈,中间数字"重新滚一次"(Framer Motion + GSAP)。

#### S3. 主排行榜表
列:
- Rank(🥇🥈🥉 Lottie 三甲,4-14 是普通数字)
- Agent 名 + 厂商品牌色边
- Elo + 95% CI(横向 errorbar 图,不只是数字)
- W-L-D 进度条
- Coverage(完成多少 task 的进度环)
- ⭐ **Mini Radar** — 7 维迷你雷达,鼠标 hover 行展开成中等大小
- ⭐ **Trend** — 该 agent 自首次出现以来 Elo 时间线(sparkline,基于 commit 历史)

筛选条件(顶部 chip):
- Backbone:All / GLM / DeepSeek / Qwen / Tongyi
- Type:All / ReAct / Plan-Execute / Multi-agent / Code-as-Action / Graph-based
- Score system:Composite v3.1 / v2 / v1 / per-pillar
- Confidence:show / hide CI bars

⭐ **创新**:每行最右侧加一个 `⚔️ Challenge` 按钮 → 跳到 `/arena?vs=X` 直接发起 1v1。

#### S4. Composite Elo 柱状图
- 14 个 agent 的 Composite Elo,品牌色,errorbar 95% CI
- GSAP scrollTrigger 入场:从 baseline grow 上来,40ms stagger
- ⭐ **创新**:点击柱子 → 整个图变成"该 agent vs 其他人的 win-rate matrix"(layoutId 变形)

#### S5. Per-Pillar Breakdown(8 tabs)
- Tabs:Citation / Evidence Density / LLM Judge / Checklist / Fact-KG / Markdown / Efficiency / Composite
- 每 tab 一张柱图 + 一段「这个 pillar 测什么、为什么重要」短文
- ⭐ **创新**:Tab 切换时,所有 agent 的位置用 Framer Motion `layoutId` 动画"重新排序"——不是简单 tab,而是同一组数据按不同维度的动态重排

#### S6. Quality vs Cost 散点图
- x = $/run,y = Composite Elo
- 左上"Pareto 前沿"区域填浅紫,标注"Pareto-optimal"
- ⭐ **创新**:连接 Pareto 前沿点的虚线 + 该曲线上方着色"无 agent 触达区"
- 散点 hover 弹卡片:agent 名 + 详细分数 + → 跳详情页

#### S7. Per-Task Heatmap(14 × 107)
- 行 = agent,列 = task(按 intent 分组着色:Recommendation 紫 / Comparison 青 / Debunking 红 / Causal 黄 / Timeline 绿 / Enumeration 橙)
- 单元格颜色 = composite_v3,深色好
- ⭐ **创新**:列的列头显示任务领域 favicon(electronics / medical / policy 等);hover 列高亮所有 agent 在该任务的分;hover 单元格弹任务标题 + 跳转链接

#### S8. Pareto / Trade-off 卡片网格
四个小图,每张说明一个 trade-off:
1. **Speed vs Quality**:wall-time vs composite
2. **Cost vs Quality**:$/run vs composite
3. **Citation vs Depth**:精准但浅 ↔ 深入但乱
4. **Reasoning vs Reliability**:reasoning 模型常常 grounding 较差

每张图自带"哪个 agent 是该象限赢家"标签。

#### S9. Methodology Accordion(3-4 项)
- ⓘ 怎么算 Composite v3.1
- ⓘ Bradley-Terry Elo + bootstrap CI 是什么
- ⓘ 为什么 grounding gate 从 0.30 降到 0.05
- ⓘ 双 judge 设计(每 ⓘ 都带"详情 →"链接到 `/methodology`)

#### S10. Recent Updates 时间线
- 最近 5 条变更(从 PROJECT_TIMELINE.md 自动抓)
- "View full history →" 跳 `/changelog`

#### S11. Footer

---

### 2.2 `/agents` — Agents Hub

**目标**:让人快速浏览所有 14 个框架的卡片墙。

**Sections**:

#### S1. Hero — "14 Frameworks · 5 Architectural Families"
- 数字大屏:14 / 5 / 80 runs
- 简介一段

#### S2. 架构家族过滤器(顶部 5 个胶囊)
- All · ReAct · Plan-Execute-Report · Multi-agent · Code-as-Action · Graph-based
- 选中后下方卡片墙 filter

#### S3. 14 个 Agent 卡片墙
每张卡片:
- 厂商 logo + 品牌色边框
- Agent 名(react-qwen35plus 等)
- Backbone 模型(GLM-4.7 / DeepSeek V4 等)
- Composite Elo 大字(配上下箭头表示比上版本变化)
- W-L-D 数字
- 7-pillar Spider mini(在卡片下半部填充)
- ⭐ **悬浮态**:卡片 lift + brand-color glow,显示 [Detail →] [Challenge ⚔️] 两个按钮

#### S4. Family Comparison 表
按 architectural family 对比平均表现。

#### S5. Notable Variants("-ds" 后缀解释)
- 解释 -ds 变体为什么存在(双 judge 设计)
- 5 个 -ds agent 与原版的 Δ Elo 表

---

### 2.3 `/agents/[name]` — Agent 个人主页(动态 14 页)

**例**:`/agents/react-qwen35plus`

**Sections**:

#### S1. Hero
- 厂商 logo 大图 + agent 名
- Backbone:Qwen 3.5-plus
- Architecture family:ReAct (custom)
- 当前排名 🥇 #1 + Elo 1295 [1224, 1360]
- GitHub 链接 + Paper 链接(若有)
- 三个一句话 fact:Best at __ · Worst at __ · Most cost-effective for __

#### S2. 7-Pillar Radar(大图)
- Recharts RadarChart,实心填充品牌色 .35 透明度
- 旁边数值列表
- 一行说明每 pillar 的好坏

#### S3. vs Best Agent Δ 表
该 agent 与排名第 1 的 agent 在每个 pillar 上的差(数值 + 进度条)

#### S4. Per-Task Performance(横向柱形)
107 task 上的 composite_v3 score,品牌色,按分数排序
- ⭐ **创新**:点击任意 bar → 弹模态显示该 task 上的报告 markdown 截选 + judge 评语

#### S5. Strength / Weakness 标签云
- ⭐ **创新**:用 GPT 自动从该 agent 的所有 audit report 里抽出关键词:擅长 ["product comparison", "URL coverage"],差在 ["timeline reasoning", "long-horizon planning"]

#### S6. Recent Reports(最近 3 篇报告)
- 每篇展示:task name + composite + 报告前 200 字预览 + → 全文链接
- 用 react-markdown 渲染

#### S7. Run Metadata
- 平均 wall-time / token usage / cost / tool-call count
- 图:每次 run 的成本分布 boxplot

#### S8. Head-to-Head 矩阵
- 该 agent 与其他 13 个 agent 的胜负数(13×1 表)+ 总胜率
- ⭐ **创新**:每行带 [Battle 详情] 按钮 → `/arena?a=本人&b=对手`

#### S9. Citation Trail(创新展示)
- ⭐ **创新**:抽取该 agent 在所有 task 中引用的 URL,按域名分布画 treemap(看它偏爱哪类来源)

---

### 2.4 `/tasks` — Tasks Explorer

**目标**:让评审者能快速 grok "我们这 107 道题到底是什么样"。

**Sections**:

#### S1. Hero
- "107 reproducible deep-research tasks across 6 intent types"
- 数字宫格:107 / 6 intent / 87 consumer / 20 academic / ≥120 must-cite URLs/task

#### S2. 任务分布可视化(横排 3 张)
1. **Intent 饼图**:6 种 intent 占比(品牌色)
2. **Site mix 条形堆叠**:每任务用了几个 site(shopping/reddit/wiki)
3. **Difficulty 直方图**:1-5 分难度分布

#### S3. 筛选器 + Task 网格
顶部 chips:
- Intent:All / Recommendation / Comparison / Debunking / Causal / Timeline / Enumeration
- Domain:All / Electronics / Medical / Finance / Policy / History / AI / ...
- Sites:All / shopping+reddit / 全部 3 个 / ...
- Difficulty:1-2 / 3 / 4-5
- Search box:full-text 搜 intent

下方 107 个任务卡片(虚拟列表):
- task_id + intent type 标签
- 第一行截选(intent 头 80 字)
- 标签:🛒 shopping · 💬 reddit · 📖 wiki · ⭐ 难度
- ⭐ **创新**:卡片右下角小条显示「14 个 agent 在这题上的 composite 分布」mini-density-plot

#### S4. ⭐ 创新:Task Authoring 透明度
- 一段说明:这些题目是怎么写出来的(intent 模板 + 沙盒约束)
- 链接到 `RESEARCH_TASK_DESIGN.md`

---

### 2.5 `/tasks/[id]` — Task 详情(动态 107 页)

**例**:`/tasks/dr_cross_deep_0001`

**Sections**:

#### S1. 题面卡片
- task_id 标题 + 复制按钮
- Intent type 大标签(品牌色)
- Sites 标签(3 个 favicon)
- Difficulty 星 ⭐⭐⭐⭐
- Markdown spec 要求(min words/citations/paragraphs)

#### S2. 完整 Intent 文本
- 大段落引用样式
- ⭐ **创新**:右上角 [📋 Copy as prompt] [▶️ Try in playground] 两按钮

#### S3. Golden URL Pool(必引 URL)
- 三栏:🛒 Shopping · 💬 Reddit · 📖 Wikipedia
- 每栏列出 must-cite URL,带 favicon + 标题
- 总数显示 "must-cite: 135 URLs"

#### S4. Agent Performance(该 task 上 14 个 agent 的成绩)
- 横向条形,按 composite_v3 排序
- 品牌色,errorbar
- 每条带 [View report →] 跳到 markdown 预览

#### S5. Reports Gallery
- 每个 agent 的 markdown 报告内嵌渲染(可折叠)
- 高亮:✅ 引用对、❌ 引用错、❓ 未引证
- ⭐ **创新**: hover 高亮的引用 → 弹出对应 URL 真实截图(从 sandbox 抓)

#### S6. Verdict 一行
- 该任务谁最好 / 最差 / 最多产 / 最高效

#### S7. Per-Pillar Breakdown(该任务上)
- 该 task 在 7 个 pillar 上的 14 agent 分数小图网格
- 看出"哪个 pillar 在这道题上最分化"

#### S8. ⭐ 创新:"Reproduce this task" 命令面板
```bash
.venv-camel/bin/python3 scripts/run_deep_task.py \
  --agent <pick> --task dr_cross_deep_0001 --backbone deepseek-v4-flash
```
- 选下拉框 agent → 自动改命令 → 一键 [📋 Copy]

---

### 2.6 `/pillars` — 7-Pillar Hub

**目标**:把 7 个 pillar 各自单独讲清楚。

**Sections**:

#### S1. Hero
- "7 Pillars · 29 Verifiers · One Composite Score"

#### S2. Composite v3.1 公式可视化
- 大字渲染:`composite = 0.25c + 0.20e + 0.20j + 0.20ck + 0.05f + 0.05m + 0.05ef`
- 配饼图:7 块,大小 = 权重
- 每块 hover → 弹 pillar 名 + 描述 + → 跳详情

#### S3. 7 个 Pillar 卡片墙
每卡片:
- Pillar 名 + 权重大字 + 主色
- 一句话定义("Are claims actually supported by cited URLs?")
- 该 pillar 上的 Top-3 agent
- [Deep dive →]

#### S4. Pillar 之间的相关性 heatmap
- 7×7 相关系数矩阵
- ⭐ **创新**:发现"高 LLM judge 的不一定 citation 高",直观可视化 F6

#### S5. Verifier Inventory
- 29 个 verifier 文件名 + 每个一句话作用
- 按 pillar 分组

---

### 2.7 `/pillars/[name]` — 单 Pillar 深度页(动态 7 页)

**例**:`/pillars/citation`

**Sections**:

#### S1. Pillar 定义
- 大字:Citation Alignment
- 权重 0.25
- 一段说明:这个 pillar 用 ALCE substring (+ optional NLI) 验证每条 claim 是否被引用 URL 支持

#### S2. 该 pillar 上的 Elo 排名
- 14 agent 在该 pillar 上的 Elo + CI
- 与 composite Elo 的 Δ 对比

#### S3. 算法说明 + 公式
- 用 KaTeX 渲染数学
- 流程图:claim 提取 → URL 取页面 → ALCE substring match → score

#### S4. Verifier 代码摘要
- `src/verifiers/citation_alignment_verifier.py` 关键代码片段(shiki 高亮)
- GitHub 链接

#### S5. Common Failure Modes
- 收集该 pillar 上分数最低的几次报告,展示典型错误模式
- ⭐ **创新**:用红框圈出报告里"虚假引用"的具体段落

#### S6. ⭐ 创新:Mini Playground
- 一个 textarea 让用户粘贴自己的报告
- 后端跑该 pillar 的 verifier(若静态站就退化为 client-side 模拟)
- 输出该 pillar 分

---

### 2.8 `/arena` — ⭐ Live Arena (1v1 Head-to-Head)

**目标**:让访客能像玩游戏一样,挑两个 agent 实时看结果。

**Sections**:

#### S1. Hero
- "Pick two agents. See who wins."
- 大字搜索框 + 两个 agent 选择卡

#### S2. 选手卡(左 vs 右)
两边镜像布局:
- Avatar(厂商 logo)
- Agent 名 + Backbone
- 综合 Elo
- 7-pillar mini-radar
- 中间是个发光的 ⚔️ "VS" 字符

#### S3. ⭐ 创新:Live 结果面板
- Battle history:这两个 agent 在 30 task 上对战胜负 (X-Y-Z)
- 7-pillar 逐项胜率柱图
- Bradley-Terry 的局部 Elo(只用这两人的对战重新算)
- 95% CI 显示 "差距是否显著"(p-value)

#### S4. 任务级胜负网格
107 个任务 × 2 列(L/R 谁赢):
- 蓝 = 左赢,红 = 右赢,灰 = 平
- ⭐ **创新**:hover 单元格弹"这道题 L 赢/输的关键一句"(从 audit report 抽)

#### S5. 报告并排对照
- 选一道两人都跑过的 task,左右双栏并排展示报告 markdown
- 同步滚动
- 关键差异标黄

#### S6. Share / Export
- "🔗 Copy share URL" → `/arena?a=react-qwen35plus&b=gpt-researcher`
- "📷 Snapshot as image" → 用 html2canvas 截图分享

---

### 2.9 `/insights` — Findings & Stories Hub

**目标**:把项目里最有故事性的 5 个发现做成"长文阅读"。

**Sections**:

#### S1. Hero
- "5 Findings That Will Change How You Benchmark Deep Research"
- 5 张大卡片,每个 finding 一张

#### S2. Finding 卡片墙
| Finding | 一句话 hook |
|---|---|
| F6: Fluent Hallucination | "The agent that wrote the most beautiful reports also faked 97% of its URLs" |
| Dual-Judge Effect | "Switch the judge model and 5 agents move ±150 Elo" |
| Adapter Quality | "DeerFlow gained +162 Elo without changing a line of its core code" |
| Length Bias | "smolagents ranks #1 on LLM judge but #9 on truth — judges love long answers" |
| Pareto Front | "These 4 agents are the only Pareto-optimal choices; the rest are dominated" |

每卡片右下角 [Read story →]

---

### 2.10 `/insights/[slug]` — Insight 长文(动态 5+ 页)

**例**:`/insights/f6-fluent-hallucination`

**长文结构(scrollytelling)**:

1. **Hook 区**(全屏)
   - 大字标题 + 关键数字 88% / 97%
   - GSAP ScrollTrigger 触发"这两个数字 count up"

2. **故事开场**:gpt-researcher 报告示例(右侧渲染 markdown,左侧滚动文字解说)

3. **戏剧揭示**(一屏 GSAP pin):
   - 报告里 100 条引用,逐条在屏幕上飞出
   - 红色 95 条变虚假、绿色 5 条真实

4. **数据可视化**:对比 LLM judge score vs grounding score 散点

5. **结论 + 下一步**

⭐ **创新**:整个页面用 GSAP `ScrollTrigger.create({ pin: ..., scrub: ... })` 做"滚动驱动的电影感叙事",这是普通 benchmark 网站完全没有的。

---

### 2.11 `/methodology` — 方法论长文

**目标**:学术严谨地讲清算法。

**Sections**(都用锚点):

#### #intro — 核心理念
- 三个非协商原则:Reproducibility / Grounding / Multi-pillar

#### #composite — Composite v3.1 公式
- 大公式 + 7 个 pillar 拆解
- 各权重的来历(参考 SCORING_FRAMEWORK.md)

#### #grounding-gate — Grounding Gate 详解
- 为什么 v2 的 multiplicative truth gate 太严
- v3.1 的 max(0.1, reachability) 妥协

#### #bradley-terry — Elo 算法
- Bradley-Terry MLE 公式 + 1000-sample bootstrap
- 1000-sample permutation rank test
- ⭐ **创新**:展示"为什么相邻 rank 通常不显著"+ 互动小图

#### #dual-judge — 双 Judge 设计
- 引用 Wataoka 2024 NeurIPS
- 表格:agent backbone × judge backbone × Elo Δ

#### #intent-typology — 6 种 intent 分类
- 每 intent 类的定义 + 代表任务

#### #verifier-inventory — 29 个 verifier 列表
- 表格:文件名 + 作用 + pillar 归属

#### #ablation — Ablation 结果
- 引用 SCORING_ABLATION.md
- 表格:删掉每个 pillar 后 Kendall τ 变化

#### #limitations — 已知局限
- DeepSeek 写假 URL 问题
- oracle v1 假阴性
- 53 个未跑完的 dual-judge battles
- ⭐ **创新**:每条 limitation 后加 "Working on it →" 链接到对应 GitHub issue

⭐ 整页**左侧 sticky ToC**(可点跳转,scrollspy 高亮当前 section)

---

### 2.12 `/sandbox` — ⭐ 系统架构漫游

**目标**:用 3D / 等距图把"沙盒 + Shim + Verifier + Arena"画清楚。

**Sections**:

#### S1. Hero
- 大字:"How it works"
- 一行字:"From task → agent → verified report → Elo"

#### S2. Architecture Diagram(交互式)
- 用现成的 `latex/fig_architecture.png` 作底图,但**重画为 SVG 可交互**:
  - 5 个组件块:Magento / Postmill / Kiwix / Shim / Verifier / Elo Arena
  - 连线动画(粒子沿线流动,Framer Motion)
  - 点击任意块跳到下方对应 section

#### S3. #magento — Shopping Sandbox
- 端口 :7770
- 规模:2000+ products
- ⭐ **创新**:嵌入一个 iframe / 截图轮播展示真实 sandbox 页面
- 一句话:"Static. Reproducible. Same as last week's."

#### S4. #postmill — Reddit Sandbox
- 端口 :9999
- 完整 thread + 投票

#### S5. #kiwix — Wikipedia Sandbox
- 端口 :8090
- 49 GB Simple English

#### S6. #shim — Tavily/Firecrawl Shim
- 端口 :8081
- 接口列表:`/search`, `/v1/search`, `/v2/scrape`, `/extract`
- ⭐ **创新**:展示「零代码接入」一行命令:
  ```bash
  export TAVILY_API_URL=http://localhost:8081
  ```
- 解释为什么 DeerFlow 因此 +162 Elo

#### S7. #ds-proxy — DS Proxy
- 端口 :8088
- OpenAI-compat,自动注入 `thinking:disabled`

#### S8. #memory — Hierarchical Memory(可选)
- src/memory/ 介绍
- L1 / L2 / L3 三层

#### S9. Tech Stack 全景
- 所有依赖一张图(类似 mermaid)

#### S10. ⭐ 创新:Live Status Dashboard
- westd 上各端口 ping 状态(:7770 ✅ :9999 ✅ ...)
- 最近一次 leaderboard rebuild 时间
- 当前正在跑的 task(若有)

---

### 2.13 `/playground` — ⭐ Pillar 权重游乐场

**目标**:让访客拖动 7 个 pillar 权重,实时看 leaderboard 重排。

**Sections**:

#### S1. Hero
- "Adjust the weights. Watch the ranking flip."
- 副标:"Why does composite_v3 use these weights? Try your own."

#### S2. 主交互区
左侧:7 个 pillar 滑块(初始值 = composite_v3 默认权重)
- 每滑块带:pillar 名 + 当前值 + 一句话定义
- 总和锁定 = 1.0(动一个,其他自动调)
- "Reset to v3.1 default" 按钮

右侧:实时排行榜
- 14 agent 按新公式重排
- ⭐ **创新**:Framer Motion `layoutId` 让每行从旧位置"飞"到新位置
- 每行右侧显示:「比 v3.1 排名 ▲3 / ▼2」

#### S3. 预设方案
按钮组:
- "Composite v3.1 (current)"
- "Composite v2 (truth-gated)"
- "Composite v1 (additive)"
- "Citation-only"
- "Judge-only"
- "Equal weight"

每按一个,滑块自动到位,看排行榜动起来。

#### S4. 解读区
- "When you weight citation > 0.4, gpt-researcher dominates."
- "When you weight LLM judge alone, smolagents wins — but its citations are 12% accurate."
- 几条预生成的 insights

#### S5. Share
- 把当前权重组合编码进 URL
- "🔗 Share my weighting" → 别人打开看到一模一样的状态

---

### 2.14 `/paper` — 论文页

**Sections**:

#### S1. Cover
- 论文标题 + 作者(从 `paper/findings.tex` 抓)+ 摘要
- 大图:`latex/main.pdf` 第一页缩略图
- [📥 Download PDF (2.5 MB)] [arXiv 链接 (when published)]

#### S2. TL;DR(3 个 takeaway)
- 引用 PAPER_FINDINGS.md

#### S3. Figures(精选)
- `latex/fig_architecture.png` 系统图
- `latex/fig_f6_finding.png` F6 发现图
- 每图一段 caption

#### S4. 嵌入 PDF
- 用 `<iframe src="/main.pdf">` 或 `react-pdf` 内嵌
- 旁侧滚动显示当前 section
- ⭐ **创新**:右栏 sticky "本节关键引用" + 一键跳到对应 reference

#### S5. Cite this work
- BibTeX 卡片(可复制)

#### S6. Related Reading
- BENCHMARK_LANDSCAPE_REPORT.md 摘要
- BYTEDANCE_DEEP_RESEARCH_SURVEY.md 摘要
- paper_survey/articles/ 列表

---

### 2.15 `/changelog` — 项目时间线

**Sections**:

#### S1. Hero
- "From zero to NeurIPS draft in 22 days"

#### S2. Vertical Timeline
从 PROJECT_TIMELINE.md 自动渲染:
- 2026-04-15 — WebArena sandbox up
- 2026-04-16 — v3 schema + 8 tasks + KG truth
- 2026-04-17 — Cross-site tasks + Tavily shim
- 2026-04-19 — Dual-judge + bootstrap CI + 107 tasks
- 2026-05-02 — handoff
- 2026-05-06 — final leaderboard frozen
- 2026-05-12 — frontend rewrite started

每条带:
- 日期
- 一句话标题
- 关键 commit / file 链接
- ⭐ **创新**:每条带"对应 leaderboard snapshot"按钮 → 在 mini 模态里看那时的排行榜

#### S3. ⭐ 创新:Elo Trajectory 时间线图
- x = 日期,y = 各 agent Elo,多线
- 看每个 agent Elo 怎么演变(每次 leaderboard rebuild 一个数据点)

---

### 2.16 `/about`

**Sections**:
- 项目使命
- 团队(头像 + 角色 + 联系方式)
- 致谢(WebArena, BrowseComp-Plus, kiwix, etc.)
- 联系方式 / 引用

---

### 2.17 `/contribute`

**Sections**:

#### S1. Three Ways to Contribute
- Add a framework / Add a task / Improve a verifier(三张大卡)

#### S2. Add a Framework(主要内容)
- 五步走:实现 runner → 注册 RUNNERS → 跑 smoke → 提交 PR
- 代码模板可复制

#### S3. Add a Task
- 任务 schema 介绍
- 用 author_notes 字段标注思路

#### S4. Reproduce in 5 minutes
```bash
git clone ...
docker compose up sandbox
.venv/bin/python3 scripts/smoke_test.py
```

#### S5. Code of Conduct + License

---

## 3. 跨页面共用组件清单

| 组件 | 用在哪 | 关键 props |
|---|---|---|
| `<HighlightTile>` | / | type, title, leader, subtitle, value |
| `<LeaderboardTable>` | /, /agents, /tasks/[id] | data, sortKey, showRadar, showCI |
| `<EloBarChart>` | / S4, /pillars/[name] | data, errorBar, brandColors |
| `<MiniRadar>` | inline 表格 | scores, brandColor, size |
| `<FullRadar>` | /agents/[name] | scores, comparisonScores |
| `<ScatterQualityCost>` | /, /insights/pareto-front | data, paretoFrontHighlight |
| `<TaskAgentHeatmap>` | / S7 | data, intentColors |
| `<MarkdownReportViewer>` | /tasks/[id], /agents/[name] | reportPath, citationHighlights |
| `<MethodologyAccordion>` | /, /pillars/[name] | items |
| `<ProviderIcon>` | 全站 | provider |
| `<MedalLottie>` | leaderboard top-3 | rank (1/2/3) |
| `<CountUp>` | hero | from, to, duration |
| `<ParticlesBackdrop>` | /, /arena | density, brandColors |
| `<ChallengeButton>` | /agents, /agents/[name] | targetAgent |
| `<TimelineList>` | /changelog | events |
| `<CodeBlock>` | /methodology, /contribute | code, language |
| `<KaTeXBlock>` | /methodology, /pillars/[name] | latex |

---

## 4. 数据源映射(每页吃哪些 JSON)

| 页面 | 主数据源 |
|---|---|
| `/` | `data/results/deep_v3/leaderboard_deep.json` + `FINAL_LEADERBOARD.md` |
| `/agents` | leaderboard.json + `scripts/runners/registry.py` (派生) |
| `/agents/[name]` | leaderboard.json + 该 agent 所有 `*_matrix.score.json` + `*.md` |
| `/tasks` | `data/tasks/deep_research/cross_site_deep/*.json` (107 个) |
| `/tasks/[id]` | 单 task json + 该 task 所有 agent 的 score.json + .md |
| `/pillars` | leaderboard.json (pillar_elo) + `SCORING_FRAMEWORK.md` |
| `/pillars/[name]` | 同上 + 该 pillar 的 verifier 源码片段 |
| `/arena` | leaderboard.json + 所有 score.json(算两两胜负) |
| `/insights/*` | `PAPER_FINDINGS.md` + `PAPER_ADVANTAGE_ANALYSIS.md` + `MULTI_JUDGE_SLICE_RESULTS.json` |
| `/methodology` | `SCORING_FRAMEWORK.md` + `SCORING_ABLATION.md` + `REVIEW_2026-05-06.md` |
| `/sandbox` | static + 可选 live ping(若保留 FastAPI) |
| `/playground` | leaderboard.json (per-pillar 分数)|
| `/paper` | `paper/findings.pdf` + `latex/main.pdf` + `latex/fig_*.png` |
| `/changelog` | `PROJECT_TIMELINE.md` + git log |

---

## 5. 创新点优先级(按 wow factor 排序)

| # | 创新点 | 在哪 | 实现难度 | wow |
|---|---|---|---|---|
| 1 | **Live Arena 1v1** | `/arena` | 中 | ⭐⭐⭐⭐⭐ |
| 2 | **Pillar 权重游乐场** | `/playground` | 中(纯前端算) | ⭐⭐⭐⭐⭐ |
| 3 | **F6 Scrollytelling** | `/insights/f6-...` | 中(GSAP pin) | ⭐⭐⭐⭐⭐ |
| 4 | **Sandbox 可交互 SVG** | `/sandbox` | 中 | ⭐⭐⭐⭐ |
| 5 | **Per-task 引用 X-Ray** | `/tasks/[id]` S5 | 高(预处理) | ⭐⭐⭐⭐ |
| 6 | **Tab 切换 layoutId 重排** | `/` S5 | 易 | ⭐⭐⭐⭐ |
| 7 | **Hero mini bracket 动效** | `/` S1 | 中 | ⭐⭐⭐ |
| 8 | **Citation Trail treemap** | `/agents/[name]` S9 | 中 | ⭐⭐⭐ |
| 9 | **Elo Trajectory 历史线** | `/changelog` | 易(若有 git 历史 leaderboard 快照) | ⭐⭐⭐ |
| 10 | **Mini Pillar Playground** | `/pillars/[name]` S6 | 高 | ⭐⭐⭐ |
| 11 | **Live Status Dashboard** | `/sandbox` S10 | 易(若保留 ping) | ⭐⭐ |

---

## 6. 实施顺序建议

如果只能做 **MVP**(2 天能上线):
- `/`(完整)
- `/agents`(列表)
- `/agents/[name]`(基础)
- `/tasks/[id]`(基础)
- `/methodology`
- `/about`

**MVP+1 周**(把项目骨架全展示):
+ `/pillars` + `/pillars/[name]`
+ `/tasks`
+ `/changelog`
+ `/contribute`

**MVP+2 周**(创新点上线):
+ `/arena` ⭐
+ `/playground` ⭐
+ `/insights` + `/insights/[slug]` ⭐
+ `/sandbox`
+ `/paper`

---

## 7. 总结

- **15 个一级页面 + 128 个动态页面 = 总共 143+ 静态页**
- **17 个跨页面通用组件**
- **11 个创新点**(Arena / Playground / Scrollytelling 是三大杀手锏)
- **数据全部来自仓库内 JSON,build 时静态化**

把这份地图配合 `fluffy-purring-moonbeam.md` 那份 PRD 看,所有信息架构、视觉规范、动效系统、实施步骤就齐了。

每个页面先按"基础内容"实现,再叠"⭐ 创新"。基础内容自动让我们做到对标 AA 70% 的水准;创新点把我们拔到对标 AA 之上,因为 AA 没有任何这种交互。

End.
