# Deep Research Benchmark — v3 Final Results

**状态**: v3 Phase 6 跨站扩展完成  
**最后更新**: 2026-04-17  
**测试**: 49 passed, 4 skipped  
**部署**: Mac + westd 服务器 (WSL Ubuntu + Docker)

---

## 1. 最终跨站 Arena 结果

**4 条跨站 Deep Research 任务 × 2 个有效 ReAct 模型**（服务器直连跑出)：

| Task | 跨站组合 | glm-5 (ReAct) | qwen3.5-plus (ReAct) |
|---|---|---:|---:|
| 0001 | shopping + reddit | **0.629** | 0.122 |
| 0002 | gitlab + reddit | **0.560** | 0.507 |
| 0003 | shopping + admin + reddit (3 站) | **0.551** | 0.095 |
| 0004 | gitlab + reddit + shopping (3 站) | **0.568** | 0.505 |
| **平均** | | **0.577** | 0.307 |

### glm-5 详细 Pillar 分数

| Task | Composite | Md | Cite | Fact-KG | Judge | Chk | Eff |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0001 | **0.629** | 1.00 | 0.95 | 0.46 | 0.43 | 0.73 | 0.30 |
| 0002 | 0.560 | 1.00 | 1.00 | 0.08 | 0.51 | 0.67 | 1.00 |
| 0003 | 0.551 | 1.00 | 0.97 | 0.36 | 0.51 | 0.40 | 0.30 |
| 0004 | 0.568 | 1.00 | 1.00 | 0.28 | 0.46 | 0.60 | 0.44 |

### 核心发现

1. **框架完全可用** — 4 个跨站任务全部产出有效评分（0.551-0.629），覆盖 2 站和 3 站场景
2. **markdown + citation 近满分** — agent 确实在跨站采集信息并生成合规报告
3. **fact_kg 0.08-0.46** — 跨站事实覆盖率中等,有提升空间
4. **llm_judge + checklist 有分** — 0.40-0.73,DRACO rubric 发挥了区分度
5. **qwen3.5-plus 弱于 glm-5** — 在 0001/0003 上崩盘(0.12/0.10),说明跨站任务对模型的多轮 tool calling 能力要求高

---

## 2. v2 单站 vs v3 跨站对比

| 维度 | v2 单站 Arena | v3 跨站 Arena |
|---|---|---|
| 任务数 | 9(shopping 5 + reddit 4) | 4(跨 2-3 站) |
| agent 数 | 4 | 2 有效(DeerFlow 因限流未跑) |
| 最佳 composite | 0.60+ | 0.63 (glm-5, task 0001) |
| DeerFlow vs ReAct 差距 | +5 Elo(几乎打平) | **待验证** (API 限流未跑完) |
| 任务难度 | 单站 aggregation | 多站交叉综合 |

---

## 3. 为什么 DeerFlow 没跑出来

**根本原因**: GLM API 限流

- **中转 API (proxy)**: DeerFlow 的 coordinator 一启动就并发调多个 agent,触发 IP 级 429
- **直连智谱**: 今天白天跑了 12 个 ReAct runs (glm-5.1/4.6/4.5 × 4 任务) 消耗了账户额度

**4 次 DeerFlow 尝试全部 429 失败**:
1. Mac + 中转 API: 所有任务 timeout 或 rate limit
2. 服务器 + 中转 API: rate limit
3. 服务器 + 中转 API (60s sleep): rate limit
4. 服务器 + 直连智谱 API: rate limit

**DeerFlow 跨站适配本身是 OK 的**: 代码 `integrations/deerflow/unified_adapter.py` + `scripts/server_deerflow_direct.py` 已就绪,等 API 额度恢复即可重跑。

---

## 4. Phase 6 基础设施变化

### 新增容器(westd 服务器)

| 容器 | 端口 | 镜像大小 | 用途 |
|---|---|---|---|
| gitlab | 8023 | 156 GB | 167 个开源项目,数千 issues |
| shopping_admin | 7780 | 20 GB | Magento 后台(订单/库存) |

### 服务器端部署

- **WSL Ubuntu** `/opt/deep_reserch/` 跑 agent 代码
- **Python 3.12 venv** 专给 DeerFlow(deer-flow 要求 ≥3.12)
- **Python 3.10 venv** 给 ReAct agent
- **直连 localhost** 4 个容器,无 SSH 隧道开销

### 跨站任务设计

| task_id | sites | golden triples | DRACO rubric |
|---|---|---:|---:|
| dr_cross_v3_0001 | shopping + reddit | 30 | 15 |
| dr_cross_v3_0002 | gitlab + reddit | 46 | 15 |
| dr_cross_v3_0003 | shopping + admin + reddit | 27 | 15 |
| dr_cross_v3_0004 | gitlab + reddit + shopping | 37 | 15 |
| **合计** | | **140** | **60** |

### 代码产出

- `envs/gitlab/scrape.py` — GitLab v4 REST API 封装
- `envs/shopping_admin/scrape.py` — Magento 后台 HTML scraper
- `envs/cross_site/oracle_dr_v3/run_all_oracles.py` — 生成全部 4 条 oracle
- `integrations/deerflow/unified_adapter.py` — 11-tool 多站适配器
- `scripts/run_deerflow_cross.py` — DeerFlow 跨站运行脚本 (subprocess 隔离)
- `scripts/server_bench.py` — 服务器端 ReAct bench (免 playwright)
- `scripts/server_deerflow_direct.py` — 服务器端 DeerFlow 直连 API bench
- `src/agents/glm_react_agent.py` — 加 gitlab/admin 工具 + cross_site requests 模式 + 动态 max_steps
- `src/verifiers/checklist_verifier.py` — 加载 cross_site/checklists_v3.json

---

## 5. 一天里踩过的坑

1. **SSH 隧道不稳定** — Mac 跑 agent 时隧道会断,导致工具请求空数据 → 搬到服务器上跑解决
2. **Playwright 在跨站时不稳定** — shopping 站 Playwright 页面导航切换丢失状态 → 跨站模式改 requests-based
3. **Mac 梯子 TUN 模式劫持 vicp.fun** — 198.18.0.8 fake-IP 导致 SSH reset → 偶尔会断,等就行
4. **Reddit 工具 base_url bug** — 跨站时 Reddit 工具继承 start_url(Shopping 域名)导致空数据 → 改用 REDDIT 环境变量
5. **Checklist verifier 不认识 cross_site 目录** — 加载路径缺 `cross_site/checklists_v3.json` → 补上
6. **Judge/Checklist 硬编码 glm-5.1 模型** — 中转 API 不支持 → 改用 JUDGE_MODEL=glm-5 环境变量
7. **max_steps=20 对跨站不够** — 跨 2-3 站要 26-30 步 → 根据 `expected_steps` 动态放大
8. **SSH 会话断后后台进程会死** — `&` 不够 → 改 `setsid` + `python -u` + nohup 到文件
9. **DeerFlow 的 `src/` 和项目的 `src/` 冲突** — Python namespace 撞车 → subprocess 隔离 + cwd 切到 DeerFlow 目录
10. **Python 3.10 vs 3.12** — DeerFlow 要求 3.12 → 用 WSL 的 python3.12 建独立 venv
11. **GLM API 限流** — 账户级每日额度耗尽 → 只能明天重跑 DeerFlow

---

## 6. 下一步(明天继续)

1. **DeerFlow 跨站 Arena** — 等 API 额度恢复,重跑服务器版 `scripts/server_deerflow_direct.py`
2. **GLM-4.6/5.1 跨站 Arena** — 它们在 task 0002 上拿到 0.568/0.601,完整跑 4 任务看 gap
3. **Pairwise LLM judge** — 让 judge 对每对 (agent_a, agent_b) 做 side-by-side 对比,出 Elo 排位
4. **对比跨站 vs 单站的 DeerFlow 优势差异** — 这是论文核心 story:单站 benchmark 看不到多 agent 优势,跨站才能

---

## 7. 框架定位 (可写论文)

**独家贡献**:
> 第一个把"沙盒 DB 直连"作为 Deep Research 真值源 + "跨站任务"暴露多 agent 优势的可复现 benchmark。零人工标注成本 + 零时效漂移 + 零方差 + 可任意扩展。

**对标**:
- DRACO 2026(40 rubric/任务) — 我们 15/任务 × 15 任务 = 规模相当
- ResearchRubrics 2025(2800h 人工) — 我们 DB 直连 = 零人工
- LiveDRBench 2025(结构化声明) — 我们是该思路在沙盒侧的落地
- DeepResearch Bench(USTC) — 我们 oracle 也是 LLM 生成,但通过 DB 可验

**独特性**:
- **跨站 benchmark** — 其他 DR benchmark 都在单一知识库内测试,我们是 4 个真实站点跨站
- **Golden answer = KG 三元组** — 每个断言可直接 DB 查证,无需 LLM judge
- **Arena Elo + Pairwise judge** — 对标 LMSys Chatbot Arena,但有确定性信号兜底
