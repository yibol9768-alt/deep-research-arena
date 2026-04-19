# Deep Research Framework Inventory (2026-04-19)

## 已接入 / 接入中(7)

| # | Framework | Tag | Shim 路径 | 状态 |
|---|---|---|---|---|
| 1 | DeerFlow (adapter) | `deerflow-glm46-new` | custom unified_adapter | ✅ 4 task 完成 |
| 2 | DeerFlow (shim) | `deerflow-glm46-shim` | Tavily via shim | ✅ 4 task 完成 |
| 3 | GPT-Researcher | `gpt-researcher` | Tavily via shim | ✅ 4 task 完成 |
| 4 | react-qwen35plus (自研) | `react-qwen35plus` | adapter | ✅ 4 task 完成 |
| 5 | react-glm5 (自研) | `react-glm5` | adapter | ✅ 4 task 完成 |
| 6 | LangChain open_deep_research | `open-deep-research` | Tavily via shim | 🟡 install 中 |
| 7 | CAMEL-AI ChatAgent | `camel-ai` | Tavily via shim | 🟡 install 中 |
| 8 | dzhng/deep-research | `dzhng-deep-research` | Firecrawl v1 via shim | 🟡 install 中 |

## 新候选 Top 推荐(扫完 20 个后排的 ROI 前 5)

| 序 | Framework | 架构亮点 | 接入成本 | Shim 路径 |
|---|---|---|---|---|
| A | **LearningCircuit/local-deep-research** (4.3k ⭐) | multi-strategy,SearXNG+Tavily+Brave 原生 | 极低 (`pip install local-deep-research` + env) | TAVILY_API_KEY → shim |
| B | **InternLM/MindSearch** (6k ⭐) | 动态图规划 multi-agent | 低(Docker) | Brave/Bing endpoint env |
| C | **huggingface/smolagents/open_deep_research** (26.7k ⭐) | **code-as-action 范式**,独一份 | 低(Python) | Serper shim 劫持 |
| D | **stanford-oval/storm** (28k ⭐) | Wiki 风长报告,学术权威 | 低(`pip install knowledge-storm`) | SearXNG / Tavily retriever |
| E | **Alibaba-NLP/DeepResearch (Tongyi)** (18.7k ⭐) | 30B 专训 MoE 模型 + ReAct | 中(需算力或 DashScope) | Serper + Jina |

## 次选(暂不接,只登记)

| 项目 | Star | 一行评价 |
|---|---:|---|
| CopilotKit/open-research-ANA | 1k | HITL 独有维度,Tavily 原生 |
| Tencent/CognitiveKernel-Pro | 510 | Tencent SFT 同款 agent |
| qx-labs/agents-deep-research | 753 | OpenAI Agents SDK canonical |
| MiroMindAI/MiroThinker | 8.1k | BrowseComp 88.2 最高 OSS |
| jina-ai/node-DeepResearch | 5.1k | TS,Jina-only,劫持 jina 域即可 |
| Intelligent-Internet/ii-researcher | ~2k | OpenAI SDK 风格 + MCP |
| nickscamara/open-deep-research | 6.2k | TS Next.js + Firecrawl(已停滞) |
| btahir/open-deep-research | 2.1k | TS 多搜索源开关最齐 |
| mshumer/OpenDeepResearcher | 2.8k | Jupyter notebook minimal baseline |
| kortix-ai/suna | ~20k | 通用 agent,research 是子能力 |
| microsoft/magentic-ui | 9.8k | AutoGen + Web UI human-centered |
| open-webui community DR tool | 132k | UI 层对照 |

## 下一步

本阶段目标:**从目前接入 8 个 扩到 12 个**(加 A/B/C/D)。

12 agents × 80 tasks × battles → 能出论文级 Arena 分布(每 pair ~30 battles,Elo CI ±20 左右)。
