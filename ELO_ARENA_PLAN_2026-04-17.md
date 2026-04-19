# Elo Arena Framework — 完善方案

**时间**: 2026-04-17
**目标**: 把现有 3 agent × 4 task × 12 battles 扩成能发论文的 Arena-style Deep Research 排位赛

---

## 0. 现有家底(跑一次 benchmark 后的状态)

| 组件 | 位置 | 状态 |
|---|---|---|
| Composite 6-pillar 评分 | `src/scoring/composite_v3.py` | ✅ 完整,正要加 evidence_density(见 SCORING_REVIEW) |
| Pairwise LLM-judge battle | `src/scoring/pairwise_judge.py` | ✅ 已有(带 position-bias swap) |
| Composite→Elo(multi-pass avg) | `src/scoring/arena.py` | ✅ 已有,但只吃 composite,不吃真实 battles |
| 3 个 agent(glm-5 / qwen / DeerFlow) | 历史跑过 | ✅ 可复现 |
| 4 个跨站 task(0001/0005/0006/0007) | `data/tasks/deep_research/cross_site/` | ✅ |
| 12 场 pairwise battle | `data/results/pairwise_3way.json` | ✅(单 judge = glm-5) |

**真实 battle 数据概览**:
- qwen: 6 wins / 4 vs glm-5 / 3-1 vs DeerFlow / 3-1
- glm-5: 4 wins / 3 vs DeerFlow
- DeerFlow: 1 win, 1 tie
- Top-2 swap(qwen>glm-5)相对于 composite(glm-5>qwen)——论文核心发现

---

## 1. 距离 "能发 Arena paper" 差什么

### 1.1 规模问题

| 维度 | 当前 | Arena SOTA | 缺口 |
|---|---:|---:|---|
| N agents | 3 | ≥ 5,最好 7+ | 4+ |
| N tasks | 4 | 30-100 | 26+ |
| N battles | 12 | 200-500 (CI ±20 Elo) | 50x |
| N judges | 1 (glm-5) | 2-3 独立 judge | 1-2 |
| Battles/agent/pair | ~4 | ≥ 30 | 大 |
| Multi-round per battle | 2 (position swap) | 2-3 | 1 |

### 1.2 方法论问题

1. **Self-preference 未校验** — glm-5 judge 打 glm-5 有无系统性偏高?没测。
2. **Arena 跟 Composite 的 Elo 是两套独立计算,没画在一起** — 论文想要的 divergence matrix 画不出来。
3. **Judge model agnostic** 没验证 — 换 Claude/DeepSeek 做 judge,ranking 会变多少?不知道。
4. **Task 覆盖太窄** — 只 shop×reddit 两站。gitlab + shopping_admin 容器丢了。

### 1.3 基础设施问题

1. 每次 benchmark 跑得还算脆 — API 429 / OpenHands 工具链不稳 / SSH tunnel 不稳(Mac 端)
2. 没有 "leaderboard 自动 render" 脚本(HANDOFF 提过 `render_leaderboard.py` 但 repo 里没找到)
3. DeerFlow 的 tool adapter 之前被截了 HTML(已修,待 smoke test 验证)

---

## 2. 目标:Elo-ready Deep Research Arena v1

### 2.1 agent 池扩到 5-7 个

**建议 7 个 agent**(已有 3 + 新增 4):

| # | Agent | Model | 备注 |
|---|---|---|---|
| 1 | react-glm5 | glm-5 | 已有 |
| 2 | react-qwen35plus | qwen3.5-plus | 已有 |
| 3 | deerflow-glm46 | glm-4.6 | 已有(工具修好重跑) |
| 4 | react-glm46 | glm-4.6 | 新:glm-4.6 驱动同 ReAct 框架,控制"同模型不同框架" |
| 5 | react-minimax | MiniMax-M2.7 | 新:换一个 family |
| 6 | deerflow-qwen | qwen3.5-plus | 新:给 DeerFlow 换模型,控制"同框架不同模型" |
| 7 | aider 或 mini-swe-agent | glm-5 | 新:第三种框架(代码在 `bug_exam/solvers/` 借用) |

**为什么这个组合**:
- 同 ReAct 下 4 个模型 → 能画出 model scaling curve
- 同 DeerFlow 下 2 个模型 → 对照"框架 vs 模型"贡献
- 2 种不同框架 × 2-3 模型 → 能分离 "framework factor" 和 "model factor"

### 2.2 Task 池扩到 15-20 个

已有 4 cross-site(0001/0005/0006/0007)。单站 v3 task 还有 shop×4 + reddit×4 = 8 个。
**合 12 个。再生 8 个 cross-site task(用 Oracle 脚本 + LLM 辅助)→ 20 task**。

- 覆盖 shop × reddit × shop_admin 组合(shop_admin 容器重建后)
- 不同 intent 类型: 产品选购 / 社区情绪分析 / 价格趋势 / 政策合规 / 品类对比

### 2.3 Battle 设计

**方案 A:Full round-robin per task(~210 battles)**
- 7 agent × C(7,2) = 21 pairs
- 20 task × 21 pairs = 420 battles
- 每 battle 2 round(swap)→ 840 judge calls
- 每 call ~20s 合 ~5 小时,$10-20 判分成本

**方案 B:Stratified sampling(~100 battles)**
- 每 pair 5-7 个 task battle(不全部)
- 更经济,统计稳定性够

**推荐方案 B** 先跑一版,若结果 CI 宽再扩 A。

### 2.4 Judge 方案

**双 judge**:
- Judge #1: glm-5(现用)—— 保留历史对比
- Judge #2: **qwen3.5-plus** 或 **MiniMax-M2.7**(同是中转 API 能访问的,非 GLM 家族)
- 或拿直连智谱的 **glm-4.6**(另一个 family node)

每个 battle 两 judge 都判。Inter-judge agreement(Cohen κ)作为 metric 上报。

**论文章节**:Reviewer 期待看"去 self-pref 后 ranking 是否稳定"。两 judge 都把 qwen 排第一 → 强结论。

### 2.5 Elo 计算(改造 `arena.py`)

当前 `compute_elo(records)` 吃 `[{task_id, agent, composite}]`,从 composite 推 battle。
要扩成吃两种数据源:

```python
# 源 1: composite-based (current)
compute_elo_from_composite(composite_records) -> {agent: elo}

# 源 2: real pairwise battles (NEW)
compute_elo_from_battles(battle_records) -> {agent: elo}
# where battle_records = [{task, a1, a2, winner: a1|a2|tie, judge}]

# 源 3: per-judge (NEW)
compute_elo_per_judge(battle_records) -> {judge: {agent: elo}}
```

**Leaderboard 对比表**:

| Agent | Composite-Elo | Judge-glm5 Elo | Judge-qwen Elo | Mean Judge Elo | Δ(Comp, Judge) |
|---|---:|---:|---:|---:|---:|
| ... |

Δ 列:如果 composite 和 judge Elo 都给 agent X 排第一 → 稳定;不一致 → 论文发现点。

### 2.6 Leaderboard 自动 render

新脚本 `scripts/render_arena_leaderboard.py`:
- 读所有 `final_<agent>_<task>.json`(composite)
- 读 `data/results/pairwise_*.json`(battles)
- 调 `arena.compute_elo_from_*` 两个版本
- 输出:
  - `data/results/LEADERBOARD_v3.md`(markdown 表)
  - `data/results/arena_elo.json`(原始数据)
  - `data/results/per_pillar_elo.md`(按 pillar 的 radar 表)

---

## 3. 具体动作清单(12 条)

按依赖排序:

### Phase A:让 DeerFlow 公平(立刻做)
- [ ] **A1** [阻塞 API]:smoke test 跑通 DeerFlow 0001,确认它能 crawl ≥5 个 PDP
- [ ] **A2**:4 task 全跑,拿新 DeerFlow 数据
- [ ] **A3**:算新 composite(含 evidence_density)

### Phase B:加 agent + task
- [ ] **B1**:跑 react-glm46 和 react-minimax 在现有 4 task 上(~$5,~1 小时)
- [ ] **B2**:用 DeerFlow 跑 qwen 版 `deerflow-qwen`(~1 小时)
- [ ] **B3**:生成 8 个新 cross-site task(配合 shop × reddit;shop_admin 先不做)
- [ ] **B4**:5 个 agent × 12 task = 60 run(~$15,~3 小时)

### Phase C:Arena 硬化
- [ ] **C1**:改 `arena.py` 加 `compute_elo_from_battles(...)`
- [ ] **C2**:改 `pairwise_judge.py` 支持 `judge_model=glm-5,qwen3.5-plus` 双 judge
- [ ] **C3**:写 `scripts/run_pairwise_battles.py`:读所有 final_*.json,对每 pair 每 task 跑双 judge battle
- [ ] **C4**:跑 ~100 battles × 2 judges = 200 judge calls(~$5)
- [ ] **C5**:写 `scripts/render_arena_leaderboard.py`

### Phase D:论文数据
- [ ] **D1**:出 composite-Elo vs judge-Elo 对比表(核心论文图)
- [ ] **D2**:Inter-judge κ(dual judge stability)
- [ ] **D3**:per-pillar Elo radar chart(showing agents 强项)
- [ ] **D4**:关键 divergence case study(例如 qwen vs glm-5 on task 0001)

---

## 4. 时间 / 成本估算

| Phase | 人工时间 | 运行时间 | API 成本 |
|---|---:|---:|---:|
| A (DeerFlow 修复重跑) | 0.5h | 30min | ~$2 |
| B (扩 agent + task) | 3-4h | 4-5h | ~$20 |
| C (Arena 硬化 + 双 judge) | 4h | 1h | ~$5 |
| D (论文数据产出) | 2-3h | <30min | 低 |
| **合计** | **~10h 人 + ~7h run** | - | **~$30** |

**其中最大时间消耗是 B 阶段的 benchmark run**。可以 setsid 后台跑,期间写 Phase C 代码。

---

## 5. 成功标准

**最小可接受(能发 workshop/short paper)**:
- 5 agent × 12 task × dual judge × stratified battles ≥ 70
- 两种 Elo(composite + judge)都有表
- 至少一个 agent 在两种 Elo 下排名稳定 top-1

**理想(能发 main track)**:
- 7 agent × 20 task × dual judge × battles ≥ 150
- per-pillar radar 画得出差异
- 能讲一个"framework factor vs model factor"的故事
- Code + data + leaderboard 全公开

---

## 6. 我的建议立刻开始

API 429 恢复后(20 min 后重试),走 **Phase A → B1(加 react-glm46)** 这条线。
A 完成后,Phase C 的 arena.py 改造 **不依赖 API** 可以立刻做,把 battle-outcome Elo 加上。

如果 API 限流持续,先做 C1-C2 代码。
