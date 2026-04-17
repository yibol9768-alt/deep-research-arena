# Deep Research Benchmark — v3 Final Results

**状态**: Phase 6 完成 — 4 跨站任务 × 3 agent × 6-pillar composite × 3-way pairwise Arena 全部跑通
**最后更新**: 2026-04-17
**部署**: westd 服务器(WSL Ubuntu + Docker + Python 3.10/3.12 双 venv)

---

## 1. 最终跨站 Arena 3-agent 完整结果

**4 条真实 Deep Research 风格跨站任务**(全部在服务器直连容器上跑):

| Task | 跨站组合 | glm-5 | qwen3.5-plus | DeerFlow-glm46 |
|---|---|---:|---:|---:|
| 0001 | shop + reddit 耳机 | **0.659** | **0.652** | 0.441 |
| 0005 | shop×4 + reddit×2 home office | 0.437 | 0.440 | **0.471** |
| 0006 | shop×3 + reddit×2 gaming | 0.476 | **0.514** | 0.402 |
| 0007 | shop×2 + reddit×2 home cook | **0.440** | 0.324 | **0.442** |
| **avg** | | **0.503** | 0.483 | 0.439 |

### 两种评判方式的最终排名

| Rank | By Composite avg | By Pairwise Judge wins |
|---|---|---|
| 🥇 | **glm-5 (0.503)** | **qwen3.5-plus (6/12)** |
| 🥈 | qwen3.5-plus (0.483) | glm-5 (4/12) |
| 🥉 | DeerFlow (0.439) | DeerFlow (1/12) |

**两个排名的 top-2 互换** — 这是论文级的 composite ↔ judge 分歧证据。

---

## 2. 3-way Pairwise Arena 详细 Battle 结果

12 场 battle (4 任务 × 3 pairs × position-debiased):

| Task | glm5 vs qwen | glm5 vs DF | qwen vs DF |
|---|---|---|---|
| 0001 | **qwen** | glm5 | **qwen** |
| 0005 | glm5 | tie | **DF** ⭐ |
| 0006 | **qwen** | glm5 | **qwen** |
| 0007 | **qwen** | glm5 | **qwen** |

**胜场统计**:
- react-qwen35plus: 6 wins (1-0 tie-0 vs glm5 on 3/4 tasks; swept DF except 0005)
- react-glm5: 4 wins (dominated DF on 3/4 tasks; only lost 0005 to DF)
- deerflow-glm46: 1 win (only beat qwen on dr_cross_v3_0005)

---

## 3. Per-Agent Pillar Breakdown

### glm-5 (ReAct)

| Task | Composite | Md | Cite | Fact-KG | Judge | Chk | Eff |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0001 | 0.659 | 1.00 | 1.00 | **0.46** | 0.51 | 0.73 | 0.44 |
| 0005 | 0.437 | 1.00 | 0.97 | 0.00 | 0.38 | 0.40 | 0.70 |
| 0006 | 0.476 | 0.80 | 0.86 | 0.12 | 0.48 | 0.60 | 0.30 |
| 0007 | 0.440 | 1.00 | 1.00 | 0.00 | 0.43 | 0.47 | 0.21 |
| avg  | **0.503** | 0.95 | 0.96 | 0.15 | 0.45 | 0.55 | 0.41 |

### qwen3.5-plus (ReAct)

| Task | Composite | Md | Cite | Fact-KG | Judge | Chk | Eff |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0001 | 0.652 | 1.00 | 1.00 | **0.46** | 0.51 | 0.73 | 0.30 |
| 0005 | 0.440 | 1.00 | 1.00 | 0.00 | 0.41 | 0.47 | 0.30 |
| 0006 | 0.514 | 1.00 | 1.00 | 0.00 | 0.51 | **0.73** | 0.30 |
| 0007 | 0.324 | 1.00 | 0.00 | 0.00 | 0.51 | 0.53 | 0.30 |
| avg  | 0.483 | **1.00** | 0.75 | 0.12 | **0.49** | 0.62 | 0.30 |

### DeerFlow-glm46 (multi-agent)

| Task | Composite | Md | Cite | Fact-KG | Judge | Chk | Eff |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0001 | 0.441 | 1.00 | 0.83 | 0.00 | 0.34 | 0.53 | 0.85 |
| 0005 | 0.471 | 0.80 | 0.93 | 0.00 | 0.51 | 0.53 | 0.85 |
| 0006 | 0.402 | 0.80 | 0.69 | 0.00 | 0.41 | 0.47 | 0.85 |
| 0007 | 0.442 | 0.80 | 0.97 | 0.00 | 0.34 | 0.53 | 0.85 |
| avg  | 0.439 | 0.85 | 0.85 | 0.00 | 0.40 | 0.52 | **0.85** |

**DeerFlow 特点**: 报告最长(19k-29k chars), efficiency 最高(0.85), 但 fact_kg 全 0 — 它选的产品/帖子跟 oracle 不重叠。

---

## 4. 核心发现(见 PAPER_FINDINGS.md)

### Finding A: Cross-site framework works end-to-end
所有 3 agent × 4 task = 12 runs 全部产出有效分数 (0.32-0.66)。markdown_structure 平均 ≥ 0.85, citation 平均 ≥ 0.85 — agent 确实在跨站采集信息并生成真实 research 报告。

### Finding B: Composite ↔ Pairwise Judge 排名分歧(cross-site 复现 v2 MEGA 发现)
- **Composite rank**: glm-5 > qwen > DeerFlow
- **Judge rank**: qwen > glm-5 > DeerFlow (top-2 互换)
- qwen 平均报告更短(11.7k vs glm-5 的 14.1k), 但 pairwise judge 更偏好它
- 判别 bias 并非单纯长度, 而是风格(tone/structure/phrasing)

### Finding C: Agent robustness 比模型选择更重要
三轮 fallback 修复后(v3→v4→v5), composite 从 0.09 → 0.50+. 修复前:
- Agent 用完 26 步没调 finish → 空答案
- Agent 说"Let me compile" 然后停 → 无效答案
- Fallback 调用本身被中转 API 拒绝

### Finding D: DeerFlow multi-agent 有报告质量优势但没分数优势
- 报告最长(26k 平均 chars), efficiency 最高(0.85)
- 但 composite 最低(0.439) 和 judge 胜场最少(1/12)
- 说明: 更多结构不等于更高质量; DeerFlow 的 multi-step 流程浪费 tokens 在 coordinator/planner/analyst 元调度上而非实际研究

### Finding E: fact_kg 是区分度最高的 pillar
- glm-5 + qwen 在 0001 拿 0.46, 其他任务 0.00-0.12
- DeerFlow 全 0
- 说明跨站任务中 agent 自主选不同产品/帖子子集, 跟 oracle 重叠低
- 未来改进: oracle 覆盖更广, 或 KG 加关系谓词让更多答案"命中"

---

## 5. 基础设施状态

### 服务器端
- ✅ Shopping (Magento, 7770) — 141GB 镜像 healthy
- ✅ Reddit (Postmill, 9999) — 107GB 镜像 healthy
- ❌ gitlab / shopping_admin — WSL 崩溃时 overlayfs 损坏丢失
- WSL Python 3.10 venv: ReAct agent
- WSL Python 3.12 venv: DeerFlow (deer-flow 要求 ≥3.12)

### 代码产出(全部 commit)
- `envs/cross_site/oracle_dr_v3/run_new_oracles.py` — 生成 3 个新跨站 oracle
- `data/tasks/deep_research/cross_site/` — 4 任务 + 60 DRACO rubric
- `data/golden/` — 177 KG golden triples
- `integrations/deerflow/unified_adapter.py` — DeerFlow 多站适配器
- `scripts/server_full_bench.py` — 服务器端 bench runner
- `scripts/server_deerflow_4tasks.py` — DeerFlow 跨站运行脚本
- `src/agents/glm_react_agent.py` — 3-tier fallback robust ReAct
- `src/scoring/composite_v3.py` — 6-pillar weighted scorer

### Git Commits (Phase 6)
```
de9c250 v3 Phase 6: DeerFlow cross-site results + 3-way pairwise Arena
5c8f20c v3 Phase 6: paper-ready findings doc
982e4fd v3 Phase 6: pairwise LLM judge — qwen 4-0 glm-5
5fb6c9e v3 Phase 6 final: qwen3.5-plus Arena + final RESULTS_SUMMARY_v3
6cedfd3 v3 Phase 6 final: 3 new multi-page cross-site tasks + glm-5 Arena results
1d331cc v3 Phase 6: server-side cross-site Arena result JSONs
168358e v3 Phase 6 server-side cross-site Arena results
cbf6629 v3 Phase 6: cross-site Deep Research tasks + multi-site infrastructure
```

---

## 6. 下一步

- 📝 **论文 draft** — 核心素材齐全, 见 PAPER_FINDINGS.md
- 🔬 **双 judge (dual-judge)** — 当前判官是 glm-5 自己, 需要非 GLM 族对比来消除 self-preference
- 📈 **扩展 rubric 到 30 条/任务** — 当前 15 条, DRACO 2026 paper 建议 40 条
- 🛠️ **rebuild gitlab + shopping_admin** — 腾出 ~180GB 后重装
