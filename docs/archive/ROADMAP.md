# Deep Research Benchmark 路线图

**定位**:用 WebArena 的真实网站沙盒(shopping/reddit/gitlab/map/wiki)作为**承载环境**,让 agent 在其中完成**深度研究类任务**(多步检索 + 跨源综合 + 结构化报告 + 确定性评分)。

**核心假设**:真实网站 + deep research 风格任务 + 确定性评分三者能同时成立。验证此假设前不盲目铺量。

---

## 与旧计划的关系

- 旧 `PHASE2_PROGRESS.md` 默认沿用 WebArena 原版 187 条 shopping 任务,但这些任务都是 **UI 操作题**("加购、找价格"),**不是 deep research**。
- 旧任务可作为"基础设施自测用例"(验证沙盒 + runner + verifier 链路),但**不是最终数据集**。
- 最终数据集需要自己重新设计任务。

---

## 三阶段路线

### Stage A:沙盒链路验证(1-2 天)

目标:证明「真实容器 + Playwright runner + verifier」端到端可跑通。

- [ ] A1. `envs/shopping/` 部署到 westd,`./reset.sh` 起容器,curl 7770 返回 200
- [ ] A2. 写 `envs/shopping/oracle/task_21_oracle.py`,用 Playwright 手动完成 task 21 作为 baseline
- [ ] A3. 跑 `scripts/smoke_test_pipeline.py --task 21` 走一遍 runner + url_verifier
- [ ] A4. 补 `tests/test_runner_e2e.py`(真容器 + 真浏览器)
- [ ] A5. 填齐 site_map 环境变量(`SHOPPING` / `SHOPPING_ADMIN`)到 runner 和 reset.sh

**出口判据**:task 21 Oracle 能得到 verifier = PASS。

---

### Stage B:Deep Research 任务模板设计(3-5 天)

目标:在 **仅 shopping 单站** 上设计 5-10 条真·deep research 任务,验证核心假设。

- [ ] B1. 写 `DEEP_RESEARCH_TASK_SPEC.md`——定义 deep research 任务的要素:
  - 多步信息检索(至少 3 个页面 / 搜索)
  - 跨来源综合(对比 ≥ 2 个产品 / 评论 / 维度)
  - 结构化报告输出(JSON 含字段 + 可选 markdown)
  - 含引用(每条事实 → 来源 URL)
- [ ] B2. 扩展 `src/models/task.py` 支持 deep research 字段:`required_sources`, `citation_policy`, `report_schema`
- [ ] B3. 扩展 verifier:
  - `report_verifier.py`(字段完整性 + 字段值确定性匹配)
  - `citation_verifier.py`(引用 URL 可达且与声明一致)
- [ ] B4. 人工设计 5 条 shopping 深度研究任务种子(从简到难):
  - 例 1:对比 3 款蓝色冬季夹克(价格/材质/评分)→ 结构化报告
  - 例 2:某类目最畅销品与最高评分品差异分析
  - 例 3:某产品负面评论聚类(出现频率 top 3 问题)
  - 例 4:跨类目价格梯度分析(同品牌不同品类)
  - 例 5:找出满足复杂组合约束的最优产品并给出决策理由
- [ ] B5. 每条任务写 Oracle Playwright 脚本(人工解),确保任务**有解且可验证**
- [ ] B6. 跑一次 GLM-4.5 ReAct agent 基线,看多少条能 PASS

**出口判据**:5 条任务中至少 3 条 Oracle 能 PASS 且 LLM agent 得分 < 60%(说明有难度但非不可能)。

---

### Stage C:扩展与量产(视 B 结果决定)

只有 Stage B 假设立住才进入 Stage C。

- [ ] C1. 下载 reddit / gitlab / map / wiki 四个 WebArena 镜像
- [ ] C2. 每站设计 10 条 deep research 任务(共 40 条 + shopping 10 条 = 50 条 MVP)
- [ ] C3. 跨站任务设计(shopping × reddit:产品宣传 vs 真实评价)
- [ ] C4. 多标注者 IAA 流程(Cohen's κ ≥ 0.75)
- [ ] C5. 噪声注入 + 鲁棒性曲线
- [ ] C6. 污染检测 + 难度校准
- [ ] C7. 公开发布

---

## 当前进度快照(2026-04-16)

- 基础设施:westd + WSL + Docker + Mihomo 代理全就绪
- shopping 镜像:`shopping_final_0712:latest` 已 docker load 成功(141 GB disk)
- 本地代码:Phase 1 schema + Phase 2 runner/verifier 就绪
- **正在**:Stage A1(部署 envs/shopping 到 westd 起容器)

---

## 绝对不要做的事

1. ❌ 不要把 WebArena 原版 187 条 UI 任务当作最终 deep research 数据集交付
2. ❌ 不要在 Stage B 假设未验证前下载另外 4 个镜像(每个都要 1-2 小时 + 60+ GB)
3. ❌ 不要用 LLM-as-judge 做最终评分(RESEARCH.md 明确要求确定性评分)
4. ❌ 不要跳过 Oracle 脚本直接让 agent 跑(无法判断任务本身是否可解)
