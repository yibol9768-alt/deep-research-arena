# Deep Research Arena 非 GPU 技术执行计划

版本：2026-06-03

范围：本计划只覆盖不需要 GPU 的工作。GPU 训练、真实 VLM 权重、Qwen GRPO 长跑、5090 上的模型训练全部暂缓。当前目标是把本地已经完成的 Track A 能力接成任务、验证、文档、Demo 和交付闭环。

## 0. 总原则

1. 不改 `data/changelog.json`，不改 `web/dist`，不部署。
2. 不改变默认 read-only 任务路径。`build_tool_registry({}, ctx)` 仍只暴露 `search` 和 `fetch`。
3. 所有新增能力必须 opt-in：只在 task JSON 明确声明时启用。
4. 重依赖继续惰性导入。没有 faiss、torch、playwright、mcp、数据库驱动时，模块 import 仍必须成功。
5. 每个阶段都跑：

```bash
PYTHON_BIN=/Users/liuyibo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  bash scripts/check_track_a_local.sh import

PYTHON_BIN=/Users/liuyibo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  bash scripts/check_track_a_local.sh track-a

PYTHON_BIN=/Users/liuyibo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  bash scripts/check_track_a_local.sh core
```

## 1. 当前本地状态

已经完成并通过本地 smoke：

| 能力 | 文件 | 当前状态 |
| --- | --- | --- |
| write actions | `src/rl/tools_write.py` | `cart_add`、`order_place`、`order_cancel` 已有 mock store 测试 |
| state diff verifier | `src/verifiers/state_diff_verifier.py` | 可从 observed_state 或 rollout trace 重建状态 |
| user simulator seam | `src/rl/user_sim.py` | scripted fake + LLM client seam |
| vision read_image | `src/rl/tools_vision.py` | fake captioner 把 caption 落到 snippets |
| computer-use loop | `src/rl/backends.py` | page-backed observe-act loop，真实 VLM 仍为 seam |
| RAG index CLI | `scripts/build_rag_index.py` | no-dense 离线路径和默认 dense 入口 |
| local smoke | `scripts/check_track_a_local.sh` | import、track-a、core 三种模式 |

还没闭环：

1. `StateDiffVerifier` 尚未接进 `ArenaEvaluator.evaluate_rollout`。
2. 还没有 `rl_tool_write_0001.json` 和 `rl_tool_vision_0001.json` 演示任务。
3. 还没有 golden URL 批量 live validation 脚本。
4. 还没有 benchmark datasheet、model eval card、实验矩阵模板。
5. `frontend` 还没有 Deep Research Demo mock 页面。

## 2. P0：工程入口与资产治理

目标：先让后续多 agent 不会改错目录。

### 2.1 已完成

- `AGENT.md`：多 agent、worktree、互不 revert、主 agent 集成规则。
- `docs/LOCAL_DEV_CHECKS.md`：本地验证说明。
- `scripts/check_track_a_local.sh`：本地 smoke。
- `docs/ASSET_OWNERSHIP_AND_DELIVERY.md`：资产归属初版。

### 2.2 还要做

#### 任务 P0.1：补顶层命令入口

文件：

- 可选：`Makefile`
- 可选：`pyproject.toml`

建议先加 `Makefile`，因为不改变 Python packaging。

目标内容：

```make
check-import:
	PYTHON_BIN ?= /Users/liuyibo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
	PYTHON_BIN=$(PYTHON_BIN) bash scripts/check_track_a_local.sh import

check-track-a:
	PYTHON_BIN ?= /Users/liuyibo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
	PYTHON_BIN=$(PYTHON_BIN) bash scripts/check_track_a_local.sh track-a

check-core:
	PYTHON_BIN ?= /Users/liuyibo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
	PYTHON_BIN=$(PYTHON_BIN) bash scripts/check_track_a_local.sh core
```

测试：

```bash
make check-import
make check-track-a
make check-core
```

完成标志：不需要记忆脚本参数，新 agent 可以从 `make check-*` 开始。

## 3. P1：StateDiff 执行奖励闭环

目标：让 write-action 任务能被 evaluator 评分，而不是只在单测里可用。

### 3.1 技术路线

当前 `StateDiffVerifier` 已经能做两件事：

1. 直接比较 `observed_state` 与 `execution_goal.expected_state`。
2. 从 `rollout.trace["tool_state_deltas"]` 重建 final state。

下一步要让 `ArenaEvaluator._evaluate_rollout_async()` 在 task 含有 `execution_goal.expected_state` 时 opt-in 调用它。

### 3.2 具体改法

文件：`src/eval/evaluator.py`

位置：`_evaluate_rollout_async()` 中，在 `s_ground, reach, ground_details = ...` 之后、`score_dict` 计算之前。

新增逻辑：

1. 写一个私有 helper：

```python
def _has_execution_goal(task_config: dict[str, Any]) -> bool:
    goal = task_config.get("execution_goal") or task_config.get("state_diff") or {}
    return isinstance(goal, dict) and isinstance(goal.get("expected_state"), dict)
```

2. 在 `_evaluate_rollout_async()` 中：

```python
execution_details = {}
execution_score = None
if _has_execution_goal(task_config):
    try:
        from src.verifiers.state_diff_verifier import StateDiffVerifier
        vr = StateDiffVerifier().verify(task_config=task_config, rollout=rollout)
        execution_score = float(vr.score)
        execution_details = dict(vr.details or {})
    except Exception as exc:
        execution_score = 0.0
        execution_details = {"error": f"{type(exc).__name__}: {exc}"}
```

3. 定义 opt-in reward blend。建议 task schema 支持：

```json
"execution_goal": {
  "reward_mode": "state_diff_only",
  "expected_state": {...}
}
```

允许三种模式：

| 模式 | 行为 | 用途 |
| --- | --- | --- |
| `state_diff_only` | final composite = state_diff score | 纯执行任务 |
| `blend` | composite = alpha * grounding + (1-alpha) * state_diff | 研究 + 执行混合任务 |
| absent | 不接入 state_diff | 默认 read-only 任务 |

推荐默认：若有 `execution_goal.expected_state` 但没有 `reward_mode`，用 `state_diff_only`。这能避免写任务被 markdown/grounding floors 不合理压低。

4. reward_terms 增加：

```python
reward_terms["execution"] = {
  "score": execution_score,
  "details": execution_details,
  "mode": reward_mode,
}
```

5. 不要把 `state_diff` 加进 `_ALL_DIMS`，先作为 opt-in override 或 blend，避免影响现有权重表。

### 3.3 测试

新增文件：`tests/test_state_diff_reward_integration.py`

测试 1：没有 `execution_goal` 的 read-only task composite 不变。

做法：

- 用 `tests/test_rl_reward.py` 里的 synth rollout 思路。
- 复制一个普通 task_config。
- 评估前后没有 `reward_terms["execution"]`。

测试 2：`state_diff_only` 完全匹配得 1。

构造：

```python
cfg = {
  "task_id": "write_reward",
  "execution_goal": {
    "reward_mode": "state_diff_only",
    "expected_state": {"orders": {"ord-1": {"status": "cancelled"}}}
  }
}
rollout.trace = {
  "tool_state_deltas": [
    {"delta": {"op": "order_cancel", "result": {"order_id": "ord-1", "status": "cancelled"}}}
  ]
}
```

断言：

- `result.composite == 1.0`
- `result.reward_terms["execution"]["score"] == 1.0`

测试 3：`state_diff_only` 部分匹配得分按比例。

测试 4：没有 observed state 时 composite 为 0 或 details 标记 missing。

命令：

```bash
PYTHONPATH=. uv run --offline --with pytest pytest -q tests/test_state_diff_reward_integration.py
```

完成标志：默认 read-only reward 没变，execution task 有 opt-in score。

## 4. P2：Write Action 演示任务

目标：让 `cart_add` / `order_place` / `order_cancel` 从工具单测变成可被任务 schema 表达的 execution task。

### 4.1 新增任务文件

文件：

- `data/tasks/deep_research/rl/rl_tool_write_0001.json`

建议 schema：

```json
{
  "schema_version": "rl-1.0.0",
  "task_id": "rl_tool_write_0001",
  "tier": "rl_train",
  "sites": ["shopping"],
  "difficulty": 1,
  "language": "en",
  "intent": "A simulated user asks you to add the NovaMax Pro headphones to the cart, place the order, then cancel it after the user changes their mind. Use write tools only when needed. Do not claim the order was cancelled unless the tool result says so.",
  "acquisition": {
    "modalities": ["mock"],
    "backend": "mock",
    "tools_allowed": ["search", "fetch", "cart_add", "order_place", "order_cancel"]
  },
  "execution_goal": {
    "reward_mode": "state_diff_only",
    "initial_state": {"cart": {"items": []}, "orders": {}},
    "expected_state": {
      "orders": {
        "ord-1": {"status": "cancelled"}
      }
    }
  },
  "user_sim": {
    "mode": "scripted",
    "turns": [
      "Please add NovaMax Pro headphones to my cart.",
      "Place the order.",
      "Actually cancel that order."
    ]
  }
}
```

注意：

- 如果 `rl_task_validate.py` 仍只验证 report reward，它不一定适合 execution task。不要强行让它判 READY。先新增一个专门的 execution validator 或测试。

### 4.2 新增测试

新增文件：`tests/test_write_task_execution.py`

测试：

1. 读取 `rl_tool_write_0001.json`，确认 `tools_allowed` 包含三个 write tools。
2. 用 `ResearchEnv + MockSandboxBackend + FakeWriteStore` 跑 scripted actions：
   - `CallTool("cart_add", {"sku": "NMX-PRO", "quantity": 1})`
   - `CallTool("order_place", {"order_id": "ord-1"})`
   - `CallTool("order_cancel", {"order_id": "ord-1"})`
3. 转成 rollout。
4. 用 `StateDiffVerifier` 或接入后的 `ArenaEvaluator.evaluate_rollout()` 验证 composite。

完成标志：

- `tests/test_write_task_execution.py` 通过。
- `rollout.trace["tool_state_deltas"]` 有三个 delta。
- default Search/Open/Read episode 没有 `tool_state_deltas` 污染。

## 5. P3：Vision 演示任务

目标：让 `read_image` 从工具单测变成任务级演示，证明图像 caption 作为 snippets 被 grounding reward 认可。

### 5.1 新增任务文件

文件：

- `data/tasks/deep_research/rl/rl_tool_vision_0001.json`

建议从 `rl_tool_rag_0001.json` 派生，保留三域 citation floors，但在 intent 加上：

```text
Also inspect one product image using the read_image tool and cite the image URL
if the caption supports a visual claim. The image caption must be treated as
evidence, not as a separate reward channel.
```

`acquisition.tools_allowed`：

```json
["search", "fetch", "read_image"]
```

### 5.2 新增测试

新增文件：`tests/test_vision_task_execution.py`

测试：

1. 读取 task JSON，确认 `read_image` allowlisted。
2. 用 fake captioner 注入 `ctx.extras["captioner"]`。
3. `CallTool("read_image", {"image_url": "http://localhost:7770/media/product/novamax.jpg"})`。
4. 断言 `retrieved_snippets[canonicalize_url(image_url)] == caption`。
5. 构造报告引用 image URL，跑 `ArenaEvaluator(mode="fast")`，确认不因没有 page fetch 被 strict grounding 归零。

风险：

- 如果 image URL 不在 sandbox_hosts 检查里，需要确认 URL host 仍是 `localhost:7770`。
- image caption 不应写入 `state_delta`。

完成标志：read_image 任务能展示图像证据进入同一 grounding contract。

## 6. P4：Golden URL Live Validation 脚本

目标：不需要 GPU，只需要沙盒服务启动时批量确认 `data/golden/rl/*.json` 的 URL 是否真实可达。

### 6.1 新增脚本

文件：

- `scripts/validate_golden_urls.py`

CLI：

```bash
python scripts/validate_golden_urls.py \
  --golden-glob 'data/golden/rl/*.json' \
  --timeout 8 \
  --out reports/golden_url_audit.json
```

参数：

| 参数 | 作用 |
| --- | --- |
| `--golden-glob` | golden JSON glob，默认 `data/golden/rl/*.json` |
| `--timeout` | HTTP timeout |
| `--out` | 写 JSON audit report |
| `--rewrite-host` | 可选，把 `__SHOPPING__` 或老 host 映射到当前 localhost |
| `--no-network` | 只解析和列 URL，不请求 |

实现步骤：

1. 读取每个 golden JSON。
2. 收集 `must_cite_urls[*].url` 和 `expected_pool_urls[*].url`。
3. 用 `requests.get(url, timeout=timeout, proxies={"http": None, "https": None})`。
4. 记录 status：`ok_2xx`、`redirect`、`client_4xx`、`server_5xx`、`error`。
5. 输出 summary：

```json
{
  "totals": {"urls": 31, "ok": 28, "client_4xx": 3},
  "files": {
    "data/golden/rl/rl_easy_0001.json": {
      "ok": 4,
      "bad": [
        {"url": "...", "status": 404}
      ]
    }
  }
}
```

### 6.2 测试

新增文件：

- `tests/test_validate_golden_urls.py`

测试方法：

- 不真实联网。
- monkeypatch 脚本内 `_get_status(url)` 或传入 fake transport。
- 创建 tmp golden JSON，断言 audit 分类正确。

完成标志：

- 沙盒未启动时脚本能给出 error report，不崩。
- 沙盒启动时能定位 404 列表。
- 脚本不自动改 golden，repoint 必须人工确认。

## 7. P5：RAG 全量索引 Runbook

目标：CLI 已有，现在补怎么在无 GPU/CPU 路径准备全量索引，dense 作为后续可选。

### 7.1 新增文档

文件：

- `docs/RAG_INDEX_RUNBOOK.md`

内容结构：

1. 输入语料格式：

```jsonl
{"url":"http://localhost:8090/content/...","text":"..."}
{"url":"http://localhost:7770/product.html","text":"..."}
{"url":"http://localhost:9999/f/...","text":"..."}
```

2. 三路语料导出方式：
   - Kiwix：从 ZIM 或 shim extract 导出。
   - Magento：从 catalog/product pages 或 MySQL 只读导出。
   - Postmill：从 post pages 或 PostgreSQL 只读导出。

3. no-dense 构建：

```bash
python scripts/build_rag_index.py \
  --corpus-jsonl data/corpus/sandbox_corpus.jsonl \
  --out data/indexes/rag_sandbox_nodense \
  --no-dense
```

4. dense 构建：

```bash
python scripts/build_rag_index.py \
  --corpus-jsonl data/corpus/sandbox_corpus.jsonl \
  --out data/indexes/rag_sandbox_dense \
  --model sentence-transformers/all-MiniLM-L6-v2
```

5. 验证：

```bash
PYTHONPATH=. python - <<'PY'
from pathlib import Path
from src.rl.tools_rag import _load_persisted_store
store = _load_persisted_store(Path("data/indexes/rag_sandbox_nodense"))
print(store.search("active noise cancellation", k=3))
PY
```

完成标志：没有 dense 依赖时 no-dense index 可加载并返回 BM25 结果。

## 8. P6：Benchmark Datasheet 与 Eval Card 模板

目标：为开源 benchmark 和模型 release 先准备格式，不等训练完成。

### 8.1 Benchmark Datasheet

文件：

- `docs/templates/BENCHMARK_DATASHEET_TEMPLATE.md`

必须字段：

1. benchmark 名称和版本。
2. 任务来源和构造流程。
3. 语料边界：Magento/Postmill/Kiwix。
4. 是否可联网：否，只允许 sandbox hosts。
5. task split：train、validation、public leaderboard、held-out。
6. golden 生成方式。
7. 评分维度和权重。
8. 已知限制：语料小、URL case-sensitive、oracle false negatives、LLM judge bias。
9. 复现命令。
10. license 和 release note。

### 8.2 Model Eval Card

文件：

- `docs/templates/MODEL_EVAL_CARD_TEMPLATE.md`

必须字段：

1. base model。
2. adapter 类型。
3. training data。
4. reward config。
5. tool config。
6. eval tasks。
7. benchmark results。
8. safety constraints。
9. limitations。
10. checkpoint hash。

完成标志：即使还没训练，也能明确未来开放模型要交什么。

## 9. P7：非 GPU Demo Mock

目标：先做 Demo 信息架构和 mock 数据，不接模型训练，不改 `web/dist`。

### 9.1 前端页面

文件建议：

- `frontend/app/demo/page.tsx`
- `frontend/components/demo/demo-shell.tsx`
- `frontend/components/demo/trace-panel.tsx`
- `frontend/components/demo/reward-breakdown.tsx`
- `frontend/lib/demo/mock-run.ts`

页面结构：

1. 左侧：任务选择。
2. 中间：research trace。
3. 右侧：reward breakdown。
4. 底部：final report markdown。

Mock 数据字段：

```ts
type DemoTraceStep = {
  step: number
  action: "search" | "fetch" | "call_tool" | "cite" | "finalize"
  tool?: string
  input: string
  output: string
  urls?: string[]
}
```

验收：

```bash
cd frontend
npm run typecheck
npm run build
```

注意：

- 不同步 `frontend/out` 到 `web/dist`。
- 不改 `data/changelog.json`。
- 页面不写大段说明文字，直接展示可用 Demo。

## 10. P8：实验矩阵和人工审计方案

目标：论文证据先设计好，不等训练完成。

### 10.1 新增文档

文件：

- `docs/EXPERIMENT_MATRIX.md`
- `docs/HUMAN_AUDIT_PROTOCOL.md`

实验矩阵：

| 轴 | 取值 |
| --- | --- |
| acquisition | shim、browser、computer_use text-proxy、rag、sql、crawl、vision |
| reward | grounding only、grounding + process、state_diff only、blend |
| task | easy、medium、harder、bilingual、tool demonstrators |
| agent | scripted oracle、MockPolicy high/low、baseline ReAct、future Qwen |
| failure | no-fetch、fabricated citation、single-domain、padding、one-sided |

人工审计：

1. 抽样 50 到 100 个报告段落。
2. 每条标注 citation 是否支持 claim。
3. 标注报告是否回答问题、是否跨源综合、是否有明显编造。
4. 计算人类标注与自动分数相关性。

完成标志：论文 A/B 都知道需要哪些表和图。

## 11. 推荐执行顺序

按低风险到高价值排序：

1. P6：datasheet 和 eval card 模板。
2. P5：RAG runbook。
3. P4：golden URL validation 脚本。
4. P1：StateDiff 接入 evaluator。
5. P2：write 演示任务。
6. P3：vision 演示任务。
7. P8：实验矩阵和人工审计方案。
8. P7：frontend mock demo。
9. P0：可选 Makefile。

理由：

- 模板和 runbook 几乎不碰核心代码，先补交付完整性。
- golden URL validation 能马上为 live sandbox 做准备。
- StateDiff 接入是唯一需要小心的 evaluator 改动，放在文档和脚本后做。
- 前端 Demo 需要更多 UI 判断，排在后面，但不需要 GPU。

## 12. 非 GPU 本轮验收目标

本轮完成后，应该满足：

1. 所有非 GPU 工程任务都有文件级技术路线。
2. Track A 已完成能力不再停留在单测，有任务级演示闭环。
3. benchmark/model release 有模板。
4. live sandbox 前置检查有脚本。
5. Demo 有 mock 页面，可以展示系统价值。
6. 本地 smoke 持续通过。

## 13. P9：主线 Deep Research 评测闭环

状态：路线已收敛。旧的独立 `dr_harness` 方案已经移除，不再作为实现方向。
后续所有非 GPU 评测能力都接入现有三层主线：

| 层 | 入口 | 用途 |
| --- | --- | --- |
| V2 public leaderboard | `scripts/run_deep_task.py`、`scripts/score_deep_answer.py`、`scripts/build_deep_leaderboard.py` | 公开榜和 truth gate 结论 |
| V3-RL reward | `src/eval/evaluator.py::ArenaEvaluator`、`src/scoring/leaderboard_composites.py::composite_v3_rl` | AgentRL 训练奖励和诊断 |
| FullEval | `src/eval/full_report_evaluator.py` | 用户可交付长报告验收 |

### 13.1 已保留能力

| 能力 | 文件 | 状态 |
| --- | --- | --- |
| browser acquisition | `integrations/agents/browser_dr/`、`scripts/runners/browser_dr_runner.py` | 已接入 agent registry |
| modality parity | `tests/test_modality_parity.py` | 验证 browser 和 shim 不应改变任务语义 |
| StateDiff reward | `src/verifiers/state_diff_verifier.py`、`src/eval/evaluator.py` | 仅在任务声明 `execution_goal.expected_state` 时启用 |
| tool registry | `src/rl/tools*.py` | RAG、SQL、crawl、exec、vision、write 均为 lazy import |
| RAG index CLI | `scripts/build_rag_index.py` | `--no-dense` 本地可跑，dense 路径留给 sandbox |

### 13.2 后续本地命令

跑一个 agent 任务：

```bash
python scripts/run_deep_task.py --agent browser-dr --task dr_cross_deep_0001
```

评分一个报告：

```bash
python scripts/score_deep_answer.py \
  --task dr_cross_deep_0001 \
  --answer data/results/deep/browser-dr__dr_cross_deep_0001_matrix.md
```

构建公开榜：

```bash
python scripts/build_deep_leaderboard.py
```

构建 V3 schema dry-run：

```bash
python scripts/build_deep_leaderboard_v3.py --dry-run
```

### 13.3 下一步验收

1. `browser-dr` 能通过 `run_deep_task.py` 进入现有结果目录。
2. `score_deep_answer.py` 继续产出 V2 headline 所需 score JSON。
3. `build_deep_leaderboard.py` 继续只用 `composite_v2_truthful` 排公开榜。
4. `ArenaEvaluator.evaluate_rollout` 继续服务 AgentRL，不承担用户报告验收。
5. 新增 `FullReportEvaluator` 后，用户报告验收走 FullEval，不再新增第二套 harness。
6. Import checks 仍不强制 Playwright、faiss、torch 或 GPU runtime。
