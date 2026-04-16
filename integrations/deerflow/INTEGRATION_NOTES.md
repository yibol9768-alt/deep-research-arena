# DeerFlow v1 ↔ Shopping Sandbox 集成记录

**日期**:2026-04-16
**目标**:把字节 DeerFlow 多 agent Deep Research 框架接入我们的 shopping 沙盒,验证多 agent 架构是否比单 agent ReAct 更有效。

## 结论

✅ **多 agent 流水线跑通**:coordinator → planner → researcher (×N) → analyst → reporter,GLM-5.1 驱动全程。

✅ **采样/推理质量明显高于单 agent**:
- 单 agent ReAct:直接返回 top-3 rating ≥4 的结果,对"5 星但只有 1 条评论"不做区分
- DeerFlow:显式识别 "Rating Reliability"(1-4 条评论的 5.0 分统计脆弱)、选 TECNO N1(4.3 分 + 12 条评论)而非 5.0 分产品,给出理由

❌ **输出格式不匹配**:DeerFlow reporter 默认出 Markdown 叙事报告,我们的 `ReportVerifier` 要结构化 JSON。0/5 通过字段约束(但研究本身是正确的)。

## 做了什么

### 环境
- 克隆 `bytedance/deer-flow` 的 `main-1.x` 分支(2.0 是重写,不符合我们需要)
- Python 3.12 venv + `pip install -e .` 装完整 LangChain 1.x + LangGraph 栈
- `conf.yaml` 配 GLM-5.1(走智谱 OpenAI-compat `https://open.bigmodel.cn/api/paas/v4/`)

### Adapter
`shop_adapter.py`:
- **`shop_search(query)`**、**`shop_browse(url)`**、**`shop_reviews(product_id)`** 三个 LangChain `@tool`,用 `requests + BeautifulSoup` 直接打 Magento HTTP 接口(不走 Playwright,快 5-10 倍)
- `install_shop_tools()` 运行时 monkey-patch `src.tools.search.get_web_search_tool` 和 `src.graph.nodes.crawl_tool`,researcher 的工具一替换,整个多 agent 循环自动切到我们的沙盒
- 绕开 DeerFlow 默认的 `mcp-github-trending` MCP(会 spawn `uvx` 子进程,我们这里没装)——传空 `mcp_settings`

### 踩坑
1. **DeerFlow v2 是 ground-up rewrite**,变成 "super agent harness",与"多 agent Deep Research"定位不同。必须用 `main-1.x` 分支。
2. **httpx 请求 Magento 返回 502**,curl / requests / urllib 中只有 `requests` 和 `curl` 能拿 200。疑似 http2 ALPN / keep-alive 组合问题。换 `requests` 即可。
3. **DeerFlow 默认塞一个 `mcp-github-trending` MCP server 给 researcher**(见 `src/workflow.py:91`),跑起来会报 `uvx: No such file or directory`。绕过方法:不要用 `run_agent_workflow_async`,直接调 `graph.astream(...)` 并传自己的 config。
4. **默认 reporter 出 markdown**,我们的 `ReportVerifier` 要 JSON Schema。

## 首次跑分 `dr_shop_0001`(头戴/入耳式 4.0 星以上 top-3)

| 维度 | 单 agent ReAct (GLM-5.1) | DeerFlow + GLM-5.1 |
|---|---|---|
| 端到端 pass | ✗ | ✗(但原因不同) |
| `report_match` | ✓(字段都对) | ✗(输出是 markdown) |
| `citation_check` | ✗(没有 citations 块) | N/A(URL 给了但不是我们的 citations shape) |
| 研究质量 | 直接取 top-3 | 识别"统计脆弱",优先 review 多的产品 |
| 耗时 | ~95s | ~4-5 min(16 search + 6 browse) |
| Token 消耗 | ~50k | ~200k-300k |

**关键观察**:DeerFlow 的 reporter 给出了所有必需 URL(TECNO N1、Harphonic E7 等)和完整理由,但包裹在 prose 里。只要把 reporter prompt 改成"必须输出 JSON 匹配此 schema",就应该能过 `report_match` + `citation_check`。

## 下一步

1. **Patch reporter prompt**(30 min):
   - 覆盖 `src/prompts/reporter.md`,加 "If a `report_schema` is provided in the user message, output ONLY a JSON object matching it; no prose."
   - 把 shop_adapter.py 的用户 prompt 包成更明确的 JSON 指令
2. **跑完整 5 条 DR 任务**(~20 min × 5 = 100 min + tokens),得 DeerFlow 基线
3. **单/多 agent 对比表**入 `PLAN.md`
4. **若 DeerFlow 在 report_match 上显著优于 ReAct**,说明多 agent 对 Deep Research 的确有增益 → 推进 C-2 (Golden Answer)

## 资产

- `third_party/deer-flow-v1/` — DeerFlow v1 源码(git clone)
- `third_party/deer-flow-v1/shop_adapter.py` — 沙盒适配器(77 行)
- `third_party/deer-flow-v1/conf.yaml` — GLM-5.1 配置
- `data/results/deerflow_dr_shop_0001.md` — 首次跑分输出
