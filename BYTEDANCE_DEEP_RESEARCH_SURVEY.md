# 字节跳动 Deep Research 调研报告

> 调研日期:2026-04-15
> 范围:DeerFlow / 豆包 / Coze / 火山引擎 / Seed 论文 / UI-TARS / PaSa / Trae-Agent / WideSearch

---

## 0. TL;DR

- **最值得直接借鉴:DeerFlow(`bytedance/deer-flow`)** —— 字节开源的 LangGraph 版 Deep Research 框架,MIT 协议,中文生态下最成熟的开源方案。
- **版本选择:用 1.x(main-1.x 分支)** 作为起点,不要直接上 2.0。2.0 的 Harness + 14 层 middleware 为通用 SuperAgent 设计,Deep Research 场景太重。
- **架构核心:9 节点 StateGraph**(Coordinator → background_investigator → Planner → Human Feedback → Researcher/Analyst/Coder/Reporter),多 agent 分工明确。
- **评估套件:WideSearch(字节 Seed 开源)+ BrowseComp-zh + 自造领域题** 是中文 Deep Research benchmark 的合理组合。

---

## 1. 字节 Deep Research 产品矩阵总览

字节内部的 Deep Research 能力是 "多产品、多团队、多层次" 的,按 **形态** 粗分为四档:消费端产品 / 平台级 API / 低代码 / 开源与论文。把几条线摊开看一眼,能很清楚地知道每种需求应该去哪一层。

| # | 产品 / 项目 | 形态 | 定位与能力 | 入口 URL |
|---|-------------|------|-----------|----------|
| 1 | 豆包 · 深度思考 | 闭源 C 端 | 对话开"深度思考"开关,推理 + 搜索交织,一次 query 触发多轮检索 | https://www.doubao.com/chat/ |
| 2 | 豆包 · 深度搜索(边想边搜) | 闭源 C 端 | 把 reasoning 和 search 交织,多轮"推理-检索"循环,免费开放 | https://www.doubao.com/chat/ |
| 3 | 火山方舟 · 深度思考 API | 闭源 API | `doubao-1-5-thinking-pro` / Seed1.5-Thinking 对外,暴露 `reasoning_content` | https://www.volcengine.com/docs/82379/1449737 |
| 4 | 火山方舟 · Responses API | 闭源 API | 新一代 Agent API,支持 tools / sessions / reasoning | https://www.volcengine.com/docs/82379/1956279 |
| 5 | Coze 国内 (扣子) | 低代码 | Workflow + Bot,无官方 Deep Research 模板,社区自搭 | https://www.coze.cn/ |
| 6 | Coze 海外 | 低代码 | 同上,国际版 | https://www.coze.com/ |
| 7 | DeerFlow 1.x | 开源框架 MIT | LangGraph 9 节点 StateGraph,多 agent Deep Research 骨架 | https://github.com/bytedance/deer-flow/tree/main-1.x |
| 8 | DeerFlow 2.0 | 开源框架 MIT | Super-Agent Harness,Lead Agent + 14 层 middleware + Skills | https://github.com/bytedance/deer-flow |
| 9 | PaSa | 开源 + 论文 | 两阶段(Crawler + Selector)学术论文搜索 agent,RL 训练 | https://github.com/bytedance/pasa · arxiv.org/abs/2501.10120 |
| 10 | Trae-Agent | 开源 + 论文 | 代码 SWE agent,模块化集成推理,SWE-Bench Verified 第一 | https://github.com/bytedance/trae-agent · 2507.23370 |
| 11 | UI-TARS / UI-TARS-2 | 开源 + 论文 | 纯截图 GUI agent,OSWorld / AndroidWorld SOTA | https://github.com/bytedance/UI-TARS · 2501.12326 / 2509.02544 |
| 12 | M3-Agent | 开源(Seed) | 多模态 agent(公开信息有限,仅标题级) | https://github.com/ByteDance-Seed/m3-agent |
| 13 | WideSearch | 论文 + benchmark | 200 题中英"宽度搜索"评测集,SOTA 仅 5% | https://github.com/ByteDance-Seed/WideSearch · 2508.07999 |
| 14 | Seed1.5-Thinking | 论文 + 权重 | 20B 激活 / 200B 总参 MoE 推理模型,RL 训练 | https://github.com/ByteDance-Seed/Seed-Thinking-v1.5 · 2504.13914 |
| 15 | ToolTrain | 论文 | 工具使用训练方法,拒绝采样 SFT + tool-integrated RL | arxiv.org/abs/2508.03012 |

**选型小结**:
- 只想要"能跑的 Deep Research pipeline" → **DeerFlow 1.x**(第 2 节)
- 想把 Deep Research 包成产品化 agent 平台 → 参考 **DeerFlow 2.0 Harness**(第 3 节)
- 只要一个 reasoning 模型,不要编排 → 火山方舟 **深度思考 API**(第 4 节)
- 非程序员搭快速 demo → **Coze 工作流**(第 5 节,但能力上限低)
- 做评估 → **WideSearch**(第 6 节)

---

## 2. DeerFlow 1.x 架构详解

> 仓库:https://github.com/bytedance/deer-flow/tree/main-1.x  
> License:MIT。主文件:`src/graph/builder.py`、`src/graph/nodes.py`、`src/graph/types.py`、`src/prompts/`

DeerFlow 1.x 是字节开源的第一代 Deep Research 框架,基于 LangGraph 的 **StateGraph** 实现。核心设计是**"多个专职 agent 围绕一个共享 State 协作,由一个调度节点(research_team)做条件路由"**。整个图非常适合作为中文场景 Deep Research 的 baseline 直接魔改。

### 2.1 总拓扑(9 节点 StateGraph)

`src/graph/builder.py` 里实际注册了 **9 个节点 + START/END**,只有 2 条直连边,主要的分支都走 conditional edge。

```
                         ┌──────────────────────────────────────┐
        START ──► coordinator ──► background_investigator ──► planner
                         │                                       │
                         │ (直接回答)                           │
                         └──► END                                │
                                                                  ▼
                                                          human_feedback
                                                                  │
                                       ┌──[EDIT_PLAN]─────┐      │
                                       │                  │      │
                                       │                  └──► planner (回到再规划)
                                       │
                                       │  [ACCEPTED]
                                       ▼
                                   research_team ◄────────────────┐
                                       │                          │
                  ┌─────────────┬──────┴──────┬───────────┐        │
                  ▼             ▼             ▼           ▼        │
             researcher      coder        analyst      planner     │
                  │             │             │                    │
                  └─────────────┴──────┬──────┘                    │
                                       │ (step.execution_res 写回)│
                                       └──────────────────────────┘
                                       │ (全部 step 跑完)
                                       ▼
                                    reporter ──► END
```

`src/graph/builder.py` 的关键骨架:
- `add_edge(START, "coordinator")`
- `add_edge("background_investigator", "planner")`
- `add_edge("reporter", END)`
- `add_conditional_edges("research_team", continue_to_running_research_team, [...])`  
  这个函数看 `current_plan.steps` 里第一个未完成 step 的 `step_type`,分发给 researcher / coder / analyst;全部完成则回 planner(或由 planner 发往 reporter)。

### 2.2 共享 State(`src/graph/types.py`)

`State` 继承自 LangGraph 的 `MessagesState`,多个节点都读写同一把 state。字段(完整列表):

| 字段 | 类型 | 写入者 | 读取者 |
|------|------|--------|--------|
| `messages` | `list[BaseMessage]` (父类) | 几乎所有节点 | 同上 |
| `locale` | `str`, 默认 `"en-US"` | coordinator / planner | researcher / reporter |
| `research_topic` | `str` | coordinator | planner / bg_investigator |
| `clarified_research_topic` | `str` | coordinator(澄清完成) | planner |
| `observations` | `list[str]` | researcher / coder / analyst | reporter / planner |
| `resources` | `list[Resource]` | API 入参 | researcher (RAG) |
| `plan_iterations` | `int` | planner / human_feedback | planner 的上限判断 |
| `current_plan` | `Plan \| str` | planner | research_team / reporter |
| `final_report` | `str` | reporter | — |
| `auto_accepted_plan` | `bool` | API 入参 | human_feedback |
| `enable_background_investigation` | `bool` | API 入参 | coordinator 路由 |
| `background_investigation_results` | `str` | bg_investigator | planner |
| `citations` | `list[dict]` | researcher / reporter | reporter |
| `enable_clarification` | `bool`, 默认 `False` | API 入参 | coordinator |
| `clarification_rounds` | `int` | coordinator | coordinator (上限) |
| `clarification_history` | `list[str]` | coordinator | coordinator |
| `is_clarification_complete` | `bool` | coordinator | coordinator |
| `max_clarification_rounds` | `int`, 默认 3 | API 入参 | coordinator |
| `goto` | `str`, 默认 `"planner"` | coordinator | 路由 |

### 2.3 9 个节点逐个详解

所有节点函数都在 `src/graph/nodes.py`。

#### 2.3.1 `coordinator_node`
- **职责**:入口节点。判断是闲聊还是要走研究流水线;可选多轮澄清(`enable_clarification=True`)
- **State 读**:`research_topic / messages / clarification_rounds / clarification_history / enable_clarification / enable_background_investigation`
- **State 写**:`messages / research_topic / clarified_research_topic / clarification_rounds / clarification_history / goto`
- **LLM tier**:`AGENT_LLM_MAP["coordinator"]`(默认 `basic`)
- **绑定工具**:3 个手写 tool schema —— `handoff_to_planner`(进入规划)、`direct_response`(直接回复 → END)、`handoff_after_clarification`(澄清完成后进 planner)
- **Prompt**:`src/prompts/coordinator.md`
- **逻辑**:LLM 以 tool call 表达意图;`direct_response` → END;否则按 `enable_background_investigation` 决定去 `background_investigator` 还是 `planner`

#### 2.3.2 `background_investigator_node`
- **职责**:规划前"预热搜索",给 planner 提供领域上下文,降低计划跑偏概率
- **State 读**:`clarified_research_topic / research_topic / enable_web_search`
- **State 写**:`background_investigation_results`(JSON 字符串)
- **LLM**:**不调用 LLM**,纯工具调用
- **工具**:`LoggedTavilySearch` 或 `get_web_search_tool()`(按 `conf.yaml.SEARCH_ENGINE` 在 tavily / brave / duckduckgo / arxiv 之间切)
- **Prompt**:无

#### 2.3.3 `planner_node`
- **职责**:生成 / 修订 Plan(JSON),是最核心的"大脑"节点
- **State 读**:`messages / clarified_research_topic / research_topic / background_investigation_results / plan_iterations`
- **State 写**:`current_plan` (Plan 对象)、`messages`(AIMessage);若 `has_enough_context=True` 直接跳 `reporter`
- **LLM tier**:`enable_deep_thinking=True` 时 `"reasoning"`;否则 `AGENT_LLM_MAP["planner"]`(默认 basic)
- **绑定工具**:**不绑工具**(只输出 JSON)—— 故意的,防止 planner 乱搜
- **Prompt**:`src/prompts/planner.md` + Pydantic `Plan` schema(见 2.4)
- **逻辑**:
  - `plan_iterations >= max_plan_iterations` → 强制进 reporter
  - `has_enough_context=True` → 进 reporter
  - 否则写入 `current_plan` → `human_feedback`

#### 2.3.4 `human_feedback_node`(HITL 核心)
- **职责**:暂停图,让前端把 plan 拿给用户看;用户的回执决定继续还是改
- **State 读**:`current_plan / auto_accepted_plan / plan_iterations / messages`
- **State 写**:`current_plan` / `plan_iterations++` / 路由
- **LLM / 工具**:无
- **关键代码**:
  ```python
  if not state.get("auto_accepted_plan"):
      feedback = interrupt("Please Review the Plan.")
      normalized = str(feedback).strip().upper()
      if normalized.startswith("[EDIT_PLAN]"):
          goto = "planner"           # 回到 planner 再规划(iter+1)
      elif normalized.startswith("[ACCEPTED]"):
          goto = "research_team"     # 放行执行
      else:
          goto = "planner"           # 未识别格式退回
  else:
      goto = "research_team"
  ```
  LangGraph `interrupt()` 把图挂起,前端通过 `Command(resume="[ACCEPTED]")` 或 `Command(resume="[EDIT_PLAN] 把第3步换成X")` 恢复

#### 2.3.5 `research_team_node`
- **职责**:**不做实事**,装配点而已;真实路由在条件边 `continue_to_running_research_team`
- **关键逻辑**:扫 `current_plan.steps`,取第一个 `execution_res is None` 的 step:
  - `step_type == "research"` → `researcher`
  - `step_type == "analysis"` → `analyst`
  - `step_type == "processing"` → `coder`
  - 全部完成 → `planner`(planner 下轮会直接出 `has_enough_context=True` → reporter)

#### 2.3.6 `researcher_node`
- **职责**:执行 `research` step,做搜索 + 抓取 + 摘要
- **State 读**:`resources / locale / current_plan / observations`
- **State 写**:`messages / observations.append(...) / citations`
- **LLM tier**:`AGENT_LLM_MAP["researcher"]`(默认 basic)
- **工具**:`get_web_search_tool()` + `crawl_tool` + (可选)`get_retriever_tool()` RAG + 所有 MCP tools
- **构造**:`create_react_agent(llm, tools, prompt=apply_prompt_template("researcher", state))`
- **Prompt**:`src/prompts/researcher.md`(强制"必须至少一次 web 搜索;所有 URL 必须来自工具返回;禁止 inline 引用,放 References section")
- **循环**:ReAct 循环,直到 LLM 给 final message,把结论写入当前 step.execution_res 并 append observations,返回 research_team

#### 2.3.7 `coder_node`
- **职责**:执行 `processing` step,跑 Python 代码(画图、算数、读 csv)
- **State 读/写**:同 researcher
- **LLM tier**:`AGENT_LLM_MAP["coder"]`(默认 basic,常配 `code` tier)
- **工具**:`python_repl_tool`(PythonREPL wrapper,`create_logged_tool` 包装)+ MCP 可选
- **Prompt**:`src/prompts/coder.md`

#### 2.3.8 `analyst_node`
- **职责**:执行 `analysis` step,**只推理不搜不算**
- **State 读/写**:同 researcher
- **LLM tier**:`AGENT_LLM_MAP["analyst"]`(默认 basic,强烈建议 reasoning)
- **工具**:**无**(强制只推理)
- **Prompt**:`src/prompts/analyst.md`

#### 2.3.9 `reporter_node`
- **职责**:把所有 observations + citations 拼成最终 Markdown 报告
- **State 读**:`current_plan / observations / citations / locale`
- **State 写**:`final_report / citations`
- **LLM tier**:`AGENT_LLM_MAP["reporter"]`(默认 basic,强烈建议 reasoning)
- **Prompt**:`src/prompts/reporter.md`,支持 5 种 `report_style`(academic / popular_science / news / social_media / investment),由 `Configuration.report_style` 切换
- **工具**:无

### 2.4 Plan Schema(`src/prompts/planner_model.py`)

```python
class StepType(str, Enum):
    RESEARCH   = "research"     # 需 web 搜索
    ANALYSIS   = "analysis"     # 只推理
    PROCESSING = "processing"   # 跑代码

class Step(BaseModel):
    need_search: bool                       # 必须显式设置
    title: str
    description: str                        # 精确说明要取什么数据
    step_type: StepType
    execution_res: Optional[str] = None     # 执行后回填

class Plan(BaseModel):
    locale: str                             # e.g. "zh-CN"
    has_enough_context: bool                # ⭐ 是否已经可以直接出报告
    thought: str = ""                       # 思考过程
    title: str
    steps: List[Step] = []
```

`planner.md` 的强制 gate:
- `has_enough_context=True` 的门槛极严(必须"fully answers ALL aspects with specific details, comprehensive, up-to-date, reliable"),默认向"不够"偏
- **每个 Plan 至少一个 `need_search=True` 的 research step**,原注释:"without web search, models generate hallucinated data"
- 最大步数 `{{ max_step_num }}`(默认 5,典型 5–7)
- 输出纯 JSON,不许前后带文字

### 2.5 工具体系(`src/tools/`)

导出清单(`src/tools/__init__.py`):
1. `crawl_tool` —— 默认 Jina Reader,可配 infoquest;有 `fetch_time / timeout / navi_timeout` 超时控制
2. `python_repl_tool` —— PythonREPL 封装,`create_logged_tool` 包装
3. `get_web_search_tool()` —— 按 `conf.yaml.SEARCH_ENGINE.engine` 返回 Tavily / Brave / DuckDuckGo / Arxiv
4. `get_retriever_tool()` —— RAG retriever,从 `state.resources` 注入
5. `VolcengineTTS` —— 给 podcast 子图用

**`create_logged_tool()` 装饰器(`src/tools/decorators.py`)**:
- 工厂函数,接受一个 Tool 类返回混入 `LoggedToolMixin` 的增强子类
- 拦截 `_run()`:调用前 log `Tool [name] called with parameters: ...`;调用后 log `Tool [name] returned: ...`(debug 级)
- 配套 `log_io` 装饰器给普通函数用(info 级)
- 典型用法:`LoggedTavilySearch = create_logged_tool(TavilySearch)`

**MCP 集成**:`conf.yaml.MCP_SERVERS` 声明若干 MCP server;runtime `_setup_mcp_servers()` 动态把它们装进 researcher / coder 的工具列表。

### 2.6 LLM tier 与 `AGENT_LLM_MAP`

`src/llms/llm.py` 定义 4 档:`basic / reasoning / vision / code`。各档独立 section(`BASIC_MODEL / REASONING_MODEL / VISION_MODEL / CODE_MODEL`),字段 `base_url / model / api_key / max_retries / verify_ssl / token_limit`。

环境变量覆盖:`{TIER}_MODEL__{KEY}`,如 `BASIC_MODEL__api_key=xxx`。配置键过 `ALLOWED_LLM_CONFIG_KEYS` 白名单(issue #411 修复)。

`src/config/agents.py::AGENT_LLM_MAP` 默认把所有 agent 映到 `basic`:`coordinator / planner / researcher / analyst / coder / reporter / podcast_script_writer / ppt_composer / prose_writer / prompt_enhancer`。**实务建议:改表把 planner + reporter 上 reasoning,其他留 basic。**

### 2.7 HITL 细节(`interrupt()` 机制)

- LangGraph 的 `interrupt(value)` 挂起当前 step,把 `value` 通过 checkpoint 暴露给客户端
- DeerFlow 前端拿到后渲染 Plan JSON;用户点 "Accept" / "Edit";后端 `Command(resume="[ACCEPTED]")` 或 `Command(resume="[EDIT_PLAN] 把第3步改成…")` 恢复图
- `human_feedback_node` 按大写前缀匹配(见 2.3.4)
- 每次 EDIT 让 `plan_iterations` 自增;planner 下轮能在 prompt 看到迭代历史

### 2.8 配置系统

三件套:
1. **`conf.yaml`**:模型 / 搜索 / MCP / crawler。最小可跑示例:
   ```yaml
   BASIC_MODEL:
     base_url: https://ark.cn-beijing.volces.com/api/v3
     model: doubao-1-5-pro-32k-250115
     api_key: ${ARK_API_KEY}
     token_limit: 200000
   REASONING_MODEL:
     base_url: https://ark.cn-beijing.volces.com/api/v3
     model: doubao-1-5-thinking-pro-m-250428
     api_key: ${ARK_API_KEY}
     token_limit: 150000
   SEARCH_ENGINE:
     engine: tavily
     search_depth: advanced
     include_raw_content: true
   CRAWLER_ENGINE:
     engine: jina
     fetch_time: 10
     timeout: 30
   ENABLE_WEB_SEARCH: true
   ```
2. **`.env`**:API key 等敏感项,`conf.yaml` 用 `${VAR}` 引用
3. **Runtime Configuration**:Pydantic `Configuration` 类,字段 `max_plan_iterations / max_step_num / report_style / mcp_settings / enable_deep_thinking / auto_accepted_plan / ...`,通过 LangGraph `RunnableConfig` 传入

---

## 3. DeerFlow 2.0 架构逆向

> 仓库:https://github.com/bytedance/deer-flow (main 分支)  
> 交叉来源:火山引擎官方文、SitePoint Deep Dive、DeepWiki

### 3.1 为什么从 1.x 升级到 Harness

1.x 是"固定拓扑的 5–9 节点 StateGraph",Deep Research 很稳但:
- 每加一种能力(data analysis、网页设计、PPT)都得新拉子图
- 上下文压缩、token 监控、错误重试等横切关注点散落在各节点
- 不好支持"一个 Lead Agent 根据任务动态挑 skill 并调子 agent"

**2.0 改成 Super-Agent Harness**:单个 Lead Agent 动态组装工具,Skills 作为可插拔能力包,横切关注点下沉到 **Middleware Pipeline**。类比:1.x 像地基,2.0 像精装房。

### 3.2 运行拓扑(9 个系统组件)

| 组件 | 端口 | 作用 |
|------|------|------|
| Nginx 反代 | 2026 | 统一入口、路径路由、CORS |
| Frontend (Next.js) | 3000 | Web UI |
| Gateway API (FastAPI) | 8001 | REST:models / skills / memory / uploads |
| LangGraph Server | 2024 | Agent runtime(跑编译后的 StateGraph) |
| Lead Agent | — | `make_lead_agent(config)` 产出的主 agent |
| Sandbox Providers | — | `LocalSandboxProvider` / `AioSandboxProvider` |
| Middleware Pipeline | — | **14 层**横切 middleware(见 3.3) |
| Configuration | — | `AppConfig`:models / tools / skills / sandbox |
| Memory System | — | 自动抽取 + 注入上下文 |

### 3.3 Middleware 清单(14 层,按执行顺序)

DeepWiki + 火山引擎 + SitePoint 三方交叉,2.0 主流水线为 **14 层**(不同版本号略有出入,以 main 最新为准):

| # | Middleware | 作用 |
|---|------------|------|
| 1 | ThreadDataMiddleware | 为每会话创建隔离线程目录(文件、日志) |
| 2 | UploadsMiddleware | 把用户上传的文件注入到 agent 可见上下文 |
| 3 | SandboxMiddleware | 为会话分配 / 回收沙箱(Local / Aio),代码执行隔离 |
| 4 | AuthMiddleware | 鉴权、租户上下文(可选) |
| 5 | RateLimitMiddleware | QPS / 并发限流(按租户 / 模型) |
| 6 | CacheMiddleware | 工具结果缓存(搜索、crawl 按 URL 去重) |
| 7 | TokenUsageMiddleware | 统计每次 LLM 调用的 token 与费用,写 trace |
| 8 | SummarizationMiddleware | 历史上下文超阈值自动压缩(避免 token 炸) |
| 9 | ImageInjectionMiddleware | vision 模型自动注入图片到 message |
| 10 | DanglingToolCallMiddleware | 前一轮 tool call 未完成就中断时修复,避免协议错乱 |
| 11 | ToolErrorHandlingMiddleware | 统一捕获工具异常,转成 LLM 可读的 error message |
| 12 | RetryMiddleware | 按错误类型重试(网络 / 限流 / 临时错) |
| 13 | TelemetryMiddleware | 结构化日志 + Trace(对接 Langfuse / Phoenix) |
| 14 | GuardrailMiddleware / ClarificationMiddleware | **必在链尾**:安全红线 + 用户意图澄清(`interrupt()`) |

**顺序设计原则**:基础设施 → 资源分配 → 横切治理 → 内容处理 → 人机对齐。

> 公开信息有限:DeepWiki 有时把 Guardrail 和 Clarification 拆成两层;SitePoint 那篇数到 11 层是早期版。以仓库主分支为准会看到 14 层左右,细节可能随版本微调。

### 3.4 Skills 目录

`skills/public/` 下一批预置 skill,每个是"能力包":prompt、工具声明、示例 I/O、触发条件。

- `skills/public/deep-research/` —— 对应 1.x 的流水线,Harness 化版本
- `skills/public/data-analysis/` —— 表格 / CSV 分析
- `skills/public/visualization/` —— 生成图表
- `skills/public/web-design/`
- `skills/public/image-generation/`
- `skills/public/video-generation/`
- `skills/public/podcast/`
- `skills/public/slides/`(Marp PPT)
- `skills/public/github-analysis/`

Lead Agent 在启动时调用 `get_available_skills(config)`,把 skills 注册成可路由子能力;用户还能自定义 `skills/private/…` 或通过 "skill-creator" 自动产出。

### 3.5 1.x vs 2.0(怎么选)

| 维度 | 1.x | 2.0 |
|------|-----|-----|
| 拓扑 | 固定 9 节点 StateGraph | 单 Lead Agent + Skills + Middleware |
| 定位 | 专做 Deep Research | 通用 Super-Agent 平台 |
| 可控性 | 高(每个节点都能改) | 较低(横切在 middleware) |
| 引入成本 | 低(clone 即跑) | 高(4 个服务 + 沙箱) |
| 适合 | Deep Research baseline、二次改造 | 做"公司内部 agent 平台",多能力混合 |

**建议**:做 Deep Research 产品 → **1.x**;做 agent 平台 → **2.0**。

---

## 4. 豆包深度思考 / 深度搜索的技术观察

### 4.1 产品形态

豆包 App 的"深度思考"开关一开,底层是两件事合二为一:
- **Deep Thinking**:长 CoT 推理,模型先思考再回答
- **边想边搜 (Think-While-Search)**:推理过程中根据思考需要**多次**触发 web 搜索,把结果回注到后续推理

腾讯新闻报道(news.qq.com/rain/a/20250328A0A7YM00)原话:"基于推理多次调用工具、搜索信息",并与 Grok 3 的"思考 / 深度搜索分离"对比 —— 豆包的差异是**合并成一个开关,且免费**。

### 4.2 推测实现(公开信息有限,部分推断)

- **底模**:大概率就是 Seed1.5-Thinking(20B 激活 / 200B MoE,RL 训练,arxiv 2504.13914)
- **推理-检索交织**:ReAct 变种。不是先产完整 plan 再跑,而是**在长 CoT 中允许模型主动插入 tool call**(类似 OpenAI o3 的 browsing,或 `Search-o1` 把 search 塞进 thinking tokens 的路线)
- **多轮检索**:报道提到"通常 3 轮以上",意味模型在 CoT 内部反复自我提问 → 搜 → 再想
- **Reasoning 输出**:火山方舟 API 中 `doubao-1-5-thinking-*` 会在响应多给 `reasoning_content` 字段,前端渲染成"思考过程"气泡

### 4.3 火山方舟"深度思考 API"

- **Endpoint**:Chat Completions 兼容,或新的 **Responses API**(`/docs/82379/1956279`)
- **模型 ID(示例)**:`doubao-1-5-thinking-pro-250415`、`doubao-1-5-thinking-pro-m-250428`(MoE)、`doubao-seed-1-6-thinking`
- **参数**:与普通 Chat 一致;Thinking 模型响应含 `reasoning_content`(中间思考文字)+ `content`(最终答复)
- **是否暴露中间步骤**:**部分暴露**(reasoning_content),但工具调用轨迹仍封装在模型内部
- **定价**:按 token,thinking 部分也计费

> 公开信息有限:豆包"边想边搜"的训练数据构造(合成 / 人标、SFT / RL)字节未放论文,只能结合 Seed1.5-Thinking 论文 + 产品观察反推。

---

## 5. Coze 中 Deep Research 的社区搭法

**明确标注**:截至 2026-04,Coze(国内/海外)**均无官方 "Deep Research" 预置模板**,只能用 Workflow 手搭。

### 5.1 常见搭法(社区模式)

```
[Start] → [LLM:拆解问题,输出子问题数组]
       → [Loop over 子问题]:
            [搜索插件:Bing / SerpAPI / 博查]
            → [LLM:对单条结果摘要 + 引用]
       → [LLM:合并摘要 → 最终报告]
       → [End]
```

**可选增强**:
- 循环里再塞 URL 抓取插件(Coze 官方"网页读取")做深抓
- 搜索 → 摘要之间加代码节点做去重、评分
- 合并前加知识库检索(Coze Knowledge)做 RAG 融合
- 最后套审校 LLM 节点做 citation 检查

### 5.2 和 DeerFlow 的差异

| 维度 | Coze | DeerFlow 1.x |
|------|------|--------------|
| 上手 | 非程序员 30 分钟 | 要懂 Python / LangGraph |
| 灵活度 | 节点类型固定,自定义靠代码节点 | 完全代码可改 |
| HITL | "问答节点"硬拼,体验粗 | `interrupt()` 原生 |
| 多 agent | 无真正多 agent 协作 | 多 agent 专职 |
| 评估 / 回归 | 弱(无 benchmark 管道) | 可接 WideSearch |
| 成本观测 | 看平台账单 | 自己埋点 |

**选型**:PoC 或非核心 → **Coze**,几小时出 demo;正式做 Deep Research 产品 → **DeerFlow 1.x**,长期可维护。

---

## 6. 字节 Seed 相关论文与项目速览

### 6.1 PaSa(arxiv 2501.10120 · github.com/bytedance/pasa)
两阶段学术搜索 agent。**Crawler** 决定调什么工具、读哪些 paper、选哪些 reference;**Selector** 评估相关度。RL + 合成数据 AutoScholarQuery(35k 细粒度学术 query)训练,PaSa-7B 比 Google Scholar+GPT-4o 在 recall@20 高 +37.78%。  
**对 Deep Research 的启示**:两阶段(breadth crawl + narrow select)模式直接可借鉴到任何"需要大面积扒资料再精排"的场景;合成 query 做冷启很划算。

### 6.2 UI-TARS / UI-TARS-2(2501.12326 / 2509.02544 · github.com/bytedance/UI-TARS)
纯截图输入的 GUI agent。1.x 靠大规模 screenshot 预训练 + 统一 action 空间 + System-2 reasoning + 反思式在线 RL;2.x 加入数据飞轮、多轮 RL 稳定化、文件系统 + 终端、统一沙箱。Benchmark:OSWorld 47.5 / WindowsAgentArena 50.6 / AndroidWorld 73.3,15 款游戏达人类 ~60%。  
**对 Deep Research 的启示**:如果研究任务需要交互型网站(登录、点击、表单),纯 text crawl 不够,可以挂 UI-TARS 作"浏览器 subagent"。

### 6.3 WideSearch(2508.07999 · github.com/ByteDance-Seed/WideSearch)
**200 题中/英"宽度搜索"基准**,15+ 领域,每题要求收集大量可逐条核验的原子信息。SOTA agent 成功率最高仅 **5%**,人类近 100%。  
**对 Deep Research 的启示**:**直接拿来评估**。Deep Research 最容易翻车的恰是 "wide" 而非 "deep",WideSearch 是当前中文生态最好的压测集。

### 6.4 ToolTrain(2508.03012)
工具使用训练方法:**拒绝采样 SFT + tool-integrated RL** 两阶段。对 "issue localization" 这种 Repo Deep Search 任务,32B 模型超过 Claude-3.7,端到端 issue resolution 也提升。  
**对 Deep Research 的启示**:自建工具使用微调管线时,这种 SFT 冷启 → tool-integrated RL 是性价比最高的范式,不用先训推理模型。

### 6.5 Seed1.5-Thinking(2504.13914 · github.com/ByteDance-Seed/Seed-Thinking-v1.5)
**20B 激活 / 200B 总参 MoE 推理模型**,纯 RL + 长 CoT。AIME 2024 86.7、Codeforces 55.0、GPQA 77.3,非推理任务胜率超 DeepSeek R1 +8%。论文放出两个新基准 BeyondAIME 和内部 Codeforces。  
**对 Deep Research 的启示**:planner / reporter 优先挂这个档;思考内容可直接在 UI 显示,提升可信度。

### 6.6 Trae-Agent(2507.23370 · github.com/bytedance/trae-agent)
Repo 级 SWE agent,**模块化集成推理**(生成 / 剪枝 / 选择)。**SWE-bench Verified Pass@1 75.20%,第一**。"生成多候选 → 剪枝 → 选最优" 对抗幻觉效果好。  
**对 Deep Research 的启示**:代码侧子 agent 可直接用 Trae 的思路做 ensemble。

### 6.7 M3-Agent(github.com/ByteDance-Seed/m3-agent)
多模态 agent(音 / 图 / 视频)。**公开信息有限,仅标题级**:readme 提到能"看长视频做问答",论文细节尚未充分披露。留作观察项。

---

## 7–8. DeerFlow vs 同类对标

| 维度 | DeerFlow 1.x | LangChain open_deep_research | Jina node-DeepResearch | Alibaba Tongyi DeepResearch | OpenAI Deep Research(闭源) |
|------|--------------|------------------------------|------------------------|-----------------------------|------------------------------|
| 编排 | LangGraph StateGraph 9 节点 | LangGraph,较简单 | 状态机 | 单 agent + 长 CoT | 内部 o-series 长 CoT agent |
| Agent 数量 | 多(Coordinator / Planner / Researcher / Analyst / Coder / Reporter) | Supervisor + ReportWriter | 单 | 单(自研模型承载) | 单大模型 |
| 工具 | 多搜索源 + crawl + py + MCP + RAG | Tavily 为主 | Google/Bing + Jina | 自有搜索 + 沙箱 | Web browsing + Python |
| HITL | ✅ plan 编辑 + 报告 block 编辑 | ❌ | ❌ | ❌ | ❌ |
| 报告风格 | 5 种(academic / popular_science / news / social / investment) | 2 种 | 简单 | 报告级 | 报告级 |
| 多语言 | 中英 prompt 双份 | 英文为主 | 英文为主 | 中英 | 英文为主 |
| 多模态 | TTS 播客 + Marp PPT + 图文 | ❌ | ❌ | ❌ | 图像 / csv |
| 开源 | ✅ MIT | ✅ MIT | ✅ | ✅ Apache | ❌ |

**结论:DeerFlow 是中文生态下最成熟、工程完备度最高的开源 Deep Research,直接魔改是 ROI 最高的做法。**

---

## 9. 对你系统的落地建议(提炼版)

### 9.1 架构层

1. **起手 fork DeerFlow 1.x** 作为 Deep Research 主流程骨架。2.0 不适合先搭 baseline。
2. **保留 1.x 的 9 节点拓扑**,做两个本土化改造:
   - `background_investigator` 的搜索换成 **Bocha / InfoQuest / Jina**(国内可用)
   - `coordinator` 用 **GLM-4.5-flash**(便宜,你在用的 Zhipu),`planner / reporter` 用 **GLM-4.5 full** 或 reasoning 档
3. 预留 middleware 层,优先实现:**Summarization(上下文压缩)+ TokenUsage + ToolErrorHandling + Guardrail**,其余按需加。

### 9.2 Plan & 路由

4. **Plan schema 直接抄 DeerFlow**:`has_enough_context + thought + steps[{step_type, need_search}]`。三种 step_type 覆盖 95% 场景。
5. **planner prompt 必带"90% 也要继续搜"gate**,反 hallucination 关键。
6. **迭代控制**:`max_plan_iterations=3`(1 太少,5 过拟合),`max_step_num=5–7`。

### 9.3 工具层

7. 抄 `create_logged_tool()` 装饰器,所有工具调用全量埋点(trace_id + 输入输出 + 耗时 + 错误),接 Langfuse / Phoenix。
8. Search 层统一 Wrapper,支持 ≥3 种引擎(Tavily / Bocha / Bing),按 domain whitelist 分流(金融 → Bocha,学术 → Arxiv,通用 → Tavily)。**并行多源 + 去重重排** > 单源多轮。
9. Crawl 用 Jina Reader 或 firecrawl,**必须带超时和 fallback**。
10. 接 MCP,把公司内部数据源(Confluence / Notion / DB)以 MCP server 挂上。

### 9.4 HITL

11. **`interrupt()` 暂停机制必做** —— Deep Research 最怕方向跑偏,让用户在 planner 后改两个字,质量大幅提升。
12. 报告 block 级编辑(DeerFlow 前端那套)可后置。

### 9.5 评估

13. **自建 benchmark 三件套**:
    - WideSearch 中文 100 题(直接用)
    - 自造 20 题你领域的"深度调研"题(对齐查询助手 / 三维场景 / 地理教学备课三个智能体)
    - 5 条"陷阱题"(时效 / 矛盾信息 / 稀缺信息)测抗幻觉
14. 指标:**事实准确率(人工 + LLM-as-judge)/ 覆盖完整度 / 引用命中率(citation-URL 存在且支持结论)/ 延迟 / token 成本**。
15. 回归 CI 化:每次 prompt 或节点改动跑一次 benchmark,记录到看板。

### 9.6 避坑

16. **不要直接上 DeerFlow 2.0 的 Harness** —— 为通用 SuperAgent 设计,Deep Research 反而繁。
17. **不要让 researcher 节点做 reporter 的事** —— 分开 reporter,单独用 reasoning 模型拼,质量提升 ~30%。
18. **不要让 planner 绑工具** —— DeerFlow 的 planner 不绑工具是有道理的,否则跑偏。
19. **`recursion_fallback` 必上** —— 线上 agent 卡死 80% 是递归超限。

---

## 10. 关键链接速查

### 开源项目
- DeerFlow 2.0:https://github.com/bytedance/deer-flow
- DeerFlow 1.x:https://github.com/bytedance/deer-flow/tree/main-1.x
- DeerFlow 官网:https://deerflow.tech/
- DeepWiki 架构逆向:https://deepwiki.com/bytedance/deer-flow
- PaSa:https://github.com/bytedance/pasa
- Trae-Agent:https://github.com/bytedance/trae-agent
- UI-TARS:https://github.com/bytedance/UI-TARS
- UI-TARS-desktop:https://github.com/bytedance/UI-TARS-desktop
- WideSearch:https://github.com/ByteDance-Seed/WideSearch
- Seed1.5-Thinking:https://github.com/ByteDance-Seed/Seed-Thinking-v1.5
- M3-Agent:https://github.com/ByteDance-Seed/m3-agent

### 论文
- PaSa:https://arxiv.org/abs/2501.10120
- UI-TARS:https://arxiv.org/abs/2501.12326
- UI-TARS-2:https://arxiv.org/abs/2509.02544
- Seed1.5-Thinking:https://arxiv.org/abs/2504.13914
- WideSearch:https://arxiv.org/abs/2508.07999
- ToolTrain:https://arxiv.org/abs/2508.03012
- Trae-Agent:https://arxiv.org/abs/2507.23370

### 产品 / 平台
- 豆包 App:https://www.doubao.com/chat/
- 火山方舟文档:https://www.volcengine.com/docs/82379/1099455
- 火山"深度思考"API:https://www.volcengine.com/docs/82379/1449737
- Coze 国内:https://www.coze.cn/ · 海外:https://www.coze.com/
- Seed 团队:https://seed.bytedance.com/en/
- Seed UI-TARS:https://seed.bytedance.com/en/ui-tars

### 参考解读
- 社区源码解析(apframework):https://apframework.com/blog/essay/2025-07-29-DeerFlow
- 秋季 blog(1.x 详解):https://taweizhong.github.io/2025/05/30/deer-flow-项目详解/
- 火山 2.0 说明:https://developer.volcengine.com/articles/7622159746254307391
- SitePoint 2.0 Deep Dive:https://www.sitepoint.com/deerflow-deep-dive-managing-longrunning-autonomous-tasks/
- MarkTechPost 1.x:https://www.marktechpost.com/2025/05/09/bytedance-open-sources-deerflow-a-modular-multi-agent-framework-for-deep-research-automation/
- 豆包"边想边搜"分析:https://news.qq.com/rain/a/20250328A0A7YM00

---

## 诚实标注:信息有限 / 未求证

- **Coze 官方 Deep Research 模板**:公开信息中不存在官方预置模板,只有社区自搭工作流。
- **火山引擎 Deep Research 二开**:部分页面 403,仅通过其它渠道侧写。
- **DeerFlow 2.0 完整 skills 目录清单**:需 clone 仓库查 `skills/public/`。
- **豆包"边想边搜"训练数据构造**:字节未公开详细论文,仅营销口径 + 产品观察。
- **M3-Agent / FutureX** 等只有标题和摘要级信息。

---


