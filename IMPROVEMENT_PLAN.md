# Deep Research Benchmark 改进计划

**创建日期**: 2026-05-01
**目标**: 论文级 benchmark，10+ 框架 × 100 task

---

## Phase 1: 修 Golden 数据（最高优先级）
**预计: 1 天**

### 1.1 修 scraper 相关性过滤
- `scripts/build_deep_golden.py` 的 `scrape_shopping()` 没有相关性过滤
- 对 Finance/Law/Science 等非消费品域，Magento 全文搜索返回大量无关产品
- **修法**: 加 TF-IDF 或关键词匹配过滤，只保留和 topic 相关的产品
- **验证**: 重 scrape 一个 task（如 0013 Finance），检查 must_cite 里的产品是否相关

### 1.2 重新 scrape 0013-0030 的 golden
- 18 个 task 需要重 scrape
- 在 westd 上跑，约 2-3 小时
- 验证每个 golden 的 `n_must_cite ≥ 120` 且产品相关

### 1.3 给 30 个 task JSON 加 domain/intent_type 字段
- 简单元数据补全，30 分钟

---

## Phase 2: 修 5 个框架集成 Bug
**预计: 半天**

| 框架 | Bug | 修法 | 难度 |
|---|---|---|---|
| **camel-ai** | wiki=0 + CoT泄漏 | 确认 shim 搜索覆盖 wiki 关键词；strip planning prefix | 小 |
| **smolagents** | 输出是 raw JSON | `agent.run()` 结果解析 `answer` 字段 | 小 |
| **gpt-researcher** | wiki 搜索没生效 | 检查 embedding 后 wiki tool 配置 | 小 |
| **ii-researcher** | wiki 有描述没 URL | 确保搜索结果 URL 传到报告模板 | 中 |
| **local-deep-researcher** | wiki 走真 Wikipedia | HTTP 拦截 `en.wikipedia.org` → kiwix | 小 |

每个修完跑 smoke test 验证。

---

## Phase 3: 重跑全量 Matrix
**预计: 1 天（大部分是机器跑的时间）**

### 3.1 用修好的框架 + 修好的 golden 重跑
- 8 个能用的框架 × 30 task = 240 runs
- 每 run ~3-5 min，约 12-20 小时
- 在 westd 上用 schtask 过夜跑

### 3.2 V3 公式评分
- 8 维评分：url_coverage + reachability + quote_match + checklist + citation_alignment + presentation + analysis_depth + spec
- 约 2-3 小时

### 3.3 重建 Leaderboard
- Bradley-Terry Elo + bootstrap CI + permutation test

---

## Phase 4: 扩题到 100
**预计: 3-5 天**

### 4.1 新增 5 个域
- Health/Medicine, Technology, Environment, Business, Politics/Society
- 每域 8 题

### 4.2 平衡 Intent 类型
- Timeline 从 2 → 16
- Causal 从 4 → 17
- 每类 ~16-17 题

### 4.3 半自动生成 pipeline
- `gen_topic_candidates.py` → LLM 生成 YAML
- `validate_yaml_batch.py` → 验证沙盒覆盖
- `build_deep_golden.py` → scrape golden（带新的相关性过滤）
- `gen_task_spec.py` → 生成 intent + checklist
- 人工 review 每个 topic（~5 min/topic × 70 = 6 小时）

### 4.4 跑 100-task matrix
- 8 框架 × 100 task = 800 runs
- 约 40-60 小时机器时间（westd 过夜跑 2-3 晚）

---

## Phase 5: 增加新框架（可选）
**预计: 2-3 天**

### 5.1 tongyi-dr
- 修 intent 文件传递（已修，需重测）
- 如果 DeepSeek backbone 效果不好，考虑在 5090 上跑 4-bit 量化版

### 5.2 deepagents
- pip install 网络问题，需要在 westd 上用 proxy 安装
- 安装后 runner 代码已就绪

### 5.3 storm / co-storm 的评分适配
- 它们用 `[N]` 脚注引用，不是 `[label](url)`
- 需要在评分时解析脚注引用 + 关联到搜索结果 URL
- 或者单独报告它们的分数（不可直接比）

---

## Phase 6: 论文写作准备
**预计: 2-3 天**

### 6.1 人工 URL audit
- Top-3 agent × 10 task × 20 URL = 600 行
- 约 5 小时人工

### 6.2 Multi-backbone 消融
- Top-3 agent × GPT-5-chat × 10 task
- ~$12 API 费，1-2 天运行

### 6.3 写 paper sections
- Section 3: Benchmark 设计（sandbox + scoring）
- Section 4: Findings (F5 URL幻觉 + F6 排名翻转 + F7 memory)
- Section 5: Leaderboard + 分析

---

## 时间线

| 周 | Phase | 产出 |
|---|---|---|
| 第 1 周 | P1 + P2 | 修好的 golden + 修好的框架 |
| 第 1-2 周 | P3 | 干净的 8×30 leaderboard |
| 第 2-3 周 | P4 | 100-task dataset |
| 第 3-4 周 | P5 + P6 | 12 框架 × 100 task + paper draft |

---

## 状态标记

- [x] P1.1 修 scraper 相关性过滤 (strict matching + ambiguous word list)
- [x] P1.2 重 scrape 0013-0030 (adaptive compensation: reddit up to 74, wiki up to 56)
- [x] P1.3 加 domain/intent_type 元数据 (7 domains, 7 intent types)
- [x] P2.1 修 camel-ai wiki + CoT (wiki search prompt + CoT stripping)
- [x] P2.2 修 smolagents JSON 输出 (parse dict/JSON answer field)
- [x] P2.3 修 gpt-researcher wiki (explicit citation requirements)
- [x] P2.4 修 ii-researcher wiki URL (collect search URLs + inject into report)
- [x] P2.5 修 local-deep-researcher wiki 重定向 (en.wikipedia.org -> Kiwix rewriting)
- [~] P3.1 重跑 10×30 matrix (running on westd as schtask, ~25h ETA)
- [~] P3.2 V3 评分 (included in batch script, runs after matrix)
- [~] P3.3 重建 leaderboard (included in batch script, runs after scoring)
- [ ] P4.1 新增 5 域 × 8 题
- [ ] P4.2 平衡 intent 类型
- [ ] P4.3 跑 100-task matrix
- [ ] P5 新框架集成
- [ ] P6 论文写作
