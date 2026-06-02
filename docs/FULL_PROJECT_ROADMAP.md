# Deep Research Arena 全量项目交付路线图

- 文档版本：v2（2026-06-03，本地校准版）
- 适用仓库：本地 `/Users/liuyibo/Desktop/lyb/deep_reserch`
- 公开站点：`https://www.deepresearcharena.com/`（Cloudflare 托管，GitHub `main` 为更新源）
- 本文件性质：项目路线文档。不触碰 `data/changelog.json` 与 `web/dist`，不提交、不推送、不部署。
- 阅读顺序建议：先读第 1 节执行摘要，再按工作流（WP0 到 WP7）认领任务，最后按里程碑（M0 到 M5）排期。
- 校准说明：本文件按本地最新代码状态、文档资产和本地测试结果校准。
- 非 GPU 详细执行手册：见 `docs/NON_GPU_TECHNICAL_EXECUTION_PLAN.md`。该文件把不需要显卡的任务拆到文件级、测试级、验收级。

本路线图把仓库从"一个基准 + 排行榜代码库"升级为一个完整交付项目，覆盖七项合同交付目标：1 到 2 项发明专利、一套基于 Agentic RL 的评测与训练系统、一个通用 Deep Research 原型、一套开放的 Deep Research 智能体模型与基准评测集、完整的交付包（技术文档、源码、数据集、模型权重、实验结果、演示系统）、1 到 2 篇 CCF-A 或等级相当的论文、1 到 2 名实习生培养。

---

## 1. 执行摘要

### 1.1 当前一句话定位

我们已经有一个可复现的"受控沙箱 Deep Research 评测竞技场"：把研究任务放进我们自己控制的 Magento（购物 :7770）、Postmill（论坛 :9999）、Kiwix（维基 :8090）三套本地服务里，用沙箱自身的数据库与语料作为事实基准，让任意 Deep Research 框架通过一个 Tavily/Firecrawl 兼容的搜索 shim（:8081）零改造接入，再用一个七维加权打分器（citation、evidence_density、llm_judge、checklist、fact_kg、markdown_structure、efficiency）和双裁判 Elo 排行榜（自举置信区间 + 置换显著性检验）对 13 个框架打分。

在这个评测底座之上，我们已经搭好了 Agentic RL 训练环境的骨架：`ResearchEnv`、统一的工具注册表（`CallTool` 单一新增动作）、模态无关的 grounding 奖励、一套预算可行且经过离线验证的 RL 训练任务集、以及 GRPO 训练循环与 Qwen 策略的实现规格（Unsloth + vLLM colocate + LoRA）。

### 1.2 当前最大的三个缺口（决定交付成败）

1. **训练闭环未跑通**：GRPO pilot（`scripts/train_grpo_pilot.py`）至今只在离线 `fast` 模式做过奖励曲线验证，从未在真实 GPU（my5090，RTX 5090 32GB）上跑过一次"真实 Qwen + 真实奖励 + 活沙箱"的训练。没有训练曲线，就没有"开放模型"交付物，也没有论文 B 的核心证据。
2. **模型与基准两个"开放交付物"尚未定义版本与冻结**：既没有冻结的基准切分（schema、golden、打分脚本、baseline 表、license、datasheet），也没有定义"开放 Deep Research 智能体模型"到底是什么（基座、LoRA 适配器、训练配方、eval card、限制说明）。
3. **专利与论文的证据链还需加厚**：`docs/RESEARCH_SURVEY.md` 和 `docs/PATENT_DISCLOSURE_DRAFTS.md` 已有初版，但还缺正式引用、人工审计集、消融矩阵、预注册主张、专利图和代理人风格的权利要求书。

### 1.3 交付目标与工作流映射

| 合同目标 | 主责工作流 | 关键产物 |
| --- | --- | --- |
| 1 到 2 项发明专利 | WP1 + WP6 | 2 份发明披露书 + 权利要求草案 |
| Agentic RL 评测与训练系统 | WP2 | 版本化任务 schema、双奖励路径、GRPO pilot 报告、工具安全包络 |
| 通用 Deep Research 原型 | WP3 | 多步取证 + 报告生成的端到端 agent、轨迹可视化 |
| 开放模型 + 基准评测集 | WP4 | benchmark v0.1 包 + 模型适配器 v0.1 + eval card |
| 交付包（文档/源码/数据/模型/结果/演示） | WP7 | 最终交付清单 + 验收脚本 |
| 1 到 2 篇 CCF-A 或等级相当论文 | WP1 + WP5 | 论文 A（基准）+ 论文 B（Agentic RL）证据与初稿 |
| 1 到 2 名实习生 | WP7 | 2 个范围清晰的实习项目 + 导师制产出 |

---

## 2. 当前仓库资产盘点（已建成且已验证的部分）

### 2.1 受控沙箱评测竞技场（已建成）

- 三套本地服务 + 搜索 shim：Magento :7770、Postmill :9999、Kiwix :8090、FastAPI shim :8081。shim 暴露 Tavily `/search` 与 Firecrawl `/v1,/v2/scrape`，外加 kiwix 直通与结构化 `/product_lookup`、`/post_lookup`。
- 严格沙箱契约（`docs/STRICT_SANDBOX_CONTRACT.md`）：三层强制（适配器工具白名单、shim 级 URL 闸门 `SHIM_MODE=strict`、运行后域名审计 `sandbox_compliance_verifier`），任何报告里出现一条非沙箱 URL 即判违规。
- 证据来源溯源（proof-of-fetch）：`integrations/wiki_overlay/`、`contamination_verifier`、`logs/retrieval/<run_id>.jsonl`。

### 2.2 基准与排行榜（已建成，论文级）

- 七维加权打分器 CompositeScorer v3.1（`src/scoring/`），`src/verifiers/` 下约 35 个 verifier 模块，覆盖 citation（ALCE 子串 / NLI 可切换）、evidence_density、llm_judge（RACE 四维 CoT）、checklist（DRACO 15 项）、fact_kg（DB 校验三元组）、markdown_structure、efficiency。
- 双裁判 Elo 排行榜（`src/scoring/arena`）：N=1000 自举 95% 置信区间 + N=1000 置换秩显著性检验 + 七张 per-pillar 独立 Elo 板。当前 52 runs、312 battles，13 个框架，react-qwen35plus 居首（Elo 约 1295）。
- 任务库：公开站点显示 107 个沙箱任务（消费 + 学术/政策两层），arena 内部规格累计 124 个任务规格。每个任务含 `markdown_spec`、`citation_policy`、`golden` 三元组路径。
- 公开站点：`frontend/`（Next.js 静态导出），页面含 leaderboard、arena、pillars、methodology、tasks、agents、insights、changelog、sandbox 等。`web/dist/` 为部署产物。

### 2.3 Agentic RL 训练底座（已建成骨架）

- 环境与动作：`src/rl/env.py` 的 `ResearchEnv`（七动作 `Search/Open/Read/WriteMemory/ReadMemory/Cite/Finalize` + 单一新增 `CallTool`）；`src/rl/action_parser.py` 支持 `TOOL:` 与 JSON 动作解析（已有 `tests/test_action_parser.py`）。
- 工具注册表：`src/rl/tools.py`（`Tool`/`ToolResult`/`ToolContext`/`ToolRegistry` + `build_tool_registry`），默认仅暴露 `search`、`fetch`，按任务 `acquisition.tools_allowed` 增量放开。
- 已落地的工具 provider（全部惰性导入、离线可测）：`tools_rag.py`（dense+hybrid 检索 + no-dense sparse loader）、`tools_sql.py`（只读 SELECT + 表/列白名单 + 行上限 + 超时）、`tools_crawl.py`（BFS 三主机白名单内爬取）、`tools_exec.py`（`run_code`/`run_bash`，网络锁定到三个 localhost、临时 cwd、RLIMIT_AS、默认拒绝）、`tools_write.py`（`cart_add`、`order_place`、`order_cancel`，只落 `state_delta`）、`tools_vision.py`（`read_image`，通过 `ctx.extras["captioner"]` 注入 captioner），以及 `integrations/mcp_server/`（把 shim 能力暴露为标准 MCP server）。
- 状态验证与用户模拟：`src/verifiers/state_diff_verifier.py` 已实现 recursive subset match，读取 `task_config.execution_goal.expected_state`；`src/rl/user_sim.py` 已提供脚本化 user simulator 与 LLM client seam。
- RAG 索引 CLI：`scripts/build_rag_index.py` 已支持 `--corpus-jsonl`、`--out`、`--model`、`--chunk-words`、`--chunk-overlap`、`--no-dense`。`--no-dense` 写 `chunks.json` / `meta.json`，不需要 faiss 或 sentence-transformers。
- 模态后端：`src/rl/backends.py` 的 `BrowserSandboxBackend`（Playwright）、`ComputerUseBackend`（Protocol + text-proxy stub + page-backed observe-act loop）、`make_backend` / `backend_from_task_config`。模态无关奖励由 `src/eval/evaluator.py::_compute_ground_signals` 保证（`s_ground = 0.6*f1_claim + 0.4*r_resolve`），并有 `tests/test_modality_parity.py` 三路证明。
- GRPO 训练：`src/rl/grpo.py`（`GRPOTrainer` + `GRPOConfig`）、`src/rl/qwen_policy.py`（按 `docs/PHASE_B_QWEN_GRPO_SPEC.md` 实现真实策略的规格）、`scripts/train_grpo_pilot.py`（pilot 入口，已接 `backend_from_task_config`）。

### 2.4 RL 训练任务集（已建成且离线验证 READY）

- `data/tasks/deep_research/rl/`：6 个可训练任务（rl_easy_0001/0002、rl_medium_0001/0002、rl_harder_0001、rl_bilingual_0001 中文）+ 2 个模态演示任务（browser、computer_use）+ 5 个工具演示任务（rag/sql/crawl/exec/mcp），共 13 个任务文件。
- golden 种子在 `data/golden/rl/`（6 个可训练任务各一份，3 到 5 条 must-cite）。
- 验证器 `scripts/rl_task_validate.py`：六项就绪检查（headroom、gradient、balance_bites、no_perverse、variance、feasible）全部 PASS。离线 FAST 奖励曲线：competent 约 0.74 到 0.81，one_sided 约 0.61 到 0.72，mediocre 约 0.45 到 0.65，shallow 约 0.40 到 0.47，fabricated 严格归零，组 std 约 0.26（见 `data/tasks/deep_research/rl/MANIFEST.md`）。
- 设计规格在 `docs/AGENTRL_TASK_SPEC.md`：解释了为何 arena 124 任务不可用于 RL（floored-reward / zero-variance），以及预算可行阈值（8 次工具调用内可达成）。

### 2.5 离线测试基线（已建成）

回归基线（2026-06-02 验证）：

```
python3 -m pytest tests/test_tool_registry.py tests/test_modality_parity.py \
  tests/test_rl_reward.py tests/test_grpo_harness.py tests/test_action_parser.py \
  tests/test_composite_v3.py tests/test_tools_rag.py tests/test_tools_sql.py \
  tests/test_tools_crawl.py tests/test_tools_exec.py tests/test_mcp_server.py -q
# => 122 passed, 4 skipped
```

4 个 skip 为 `mcp` 包缺失保护 + 一个 browser parity skip。所有重依赖（faiss、torch、playwright、psycopg2、mysql、sentence-transformers、mcp）均惰性导入，纯 `python3` 可 import 全部模块。

本地 Track A 校准（2026-06-03 验证）：

```
bash scripts/check_track_a_local.sh import
# => import check ok

bash scripts/check_track_a_local.sh track-a
# => 66 passed

bash scripts/check_track_a_local.sh core
# => 20 passed
```

---

## 3. 缺口分析（尚缺什么）

下表把缺口分为本地已完成但尚未闭环、未执行的实验、未沉淀的交付物三类，并标注证据。

### 3.1 本地 Track A 状态与剩余闭环缺口

| 能力 | 本地路径 | 现状 | 剩余缺口 |
| --- | --- | --- | --- |
| 写操作工具 | `src/rl/tools_write.py` | 已实现并测试 | 加 `rl_tool_write_0001` 演示任务；把 `StateDiffVerifier` 接进 execution-goal 评测路径 |
| 状态差异验证器 | `src/verifiers/state_diff_verifier.py` | 已实现 recursive subset match | 增加真实 sandbox state snapshot 输入与 pass^k 报告 |
| 用户模拟器 seam | `src/rl/user_sim.py` | 已实现 scripted fake + LLM seam | 加写任务场景化脚本与未来 LLM client 配置 |
| 图像内容视觉工具 | `src/rl/tools_vision.py` | 已实现 `read_image` + fake captioner 测试 | 加 `rl_tool_vision_0001` 演示任务；Track B 接真实 VLM captioner |
| computer-use 循环 | `src/rl/backends.py` | 已有 page-backed observe-act loop 与 fake page 测试 | Track B 接真实 VLM policy；活浏览器验证动作稳定性 |
| RAG 索引构建 CLI | `scripts/build_rag_index.py` | 已实现 no-dense 与默认 dense 路径入口 | Track B 构建 Kiwix + Magento + Postmill 全量索引 |
| 本地冒烟脚本与文档 | `scripts/check_track_a_local.sh`、`docs/LOCAL_DEV_CHECKS.md` | 已实现并验证 | 可选增加顶层 `Makefile` 或 `pyproject.toml` 统一入口 |

注意：上述 Track A 能力已经在本地实现。后续不要重复实现这些文件，优先做演示任务、评测接入、live-gated 验证与文档沉淀。

### 3.2 未执行的实验（live-gated，需活沙箱 / GPU）

1. golden 种子 URL 从未做活沙箱可达性确认（沙箱当时未启动）。`data/golden/rl/*.json` 里多条 URL 为占位（如 `/anc-over-ear-headphones.html`、`/novamax-pro.html`），首次活沙箱运行必须逐条确认并对 404 重定位。
2. GRPO pilot 从未在真实 GPU 跑过：奖励方差、有限 loss、checkpoint/resume、活沙箱奖励曲线与离线设计目标是否一致，全部待验证（`docs/PHASE_B_QWEN_GRPO_SPEC.md` 第 6 节验收项）。
3. SQL / RAG / code-exec 的真实后端（真 Magento MySQL、真 Postmill PostgreSQL、真 microVM、真语料 FAISS 索引）从未接通，安全闸门是否在真实环境保持也未验证（CODEX_HANDOFF Track B1 到 B5）。
4. 107 个 arena 任务只有 4 个被实际打分，学术层（0088 到 0107）扩展打分未做；oracle v2（`*.filtered.json`）已生成但未用于重打分。

### 3.3 未沉淀的交付物（文档/证据/版本）

1. 程序级研究综述与新颖性映射表已有初版（`docs/RESEARCH_SURVEY.md`），但还需要扩成论文 Related Work，补正式引用、数据规模、评价协议和 claim-to-evidence 证据表。
2. 人工审计集（citation 支持度、报告质量）未建立；消融矩阵、anti-fabrication 证据、modality parity 的论文级呈现未整理。
3. 基准 v0.1 未冻结：schema 文档、license、datasheet、baseline 结果表、leaderboard 复现路径未打包。
4. "开放模型"未定义：基座选择（Qwen3-3B/4B）、LoRA 权重、训练配方、tokenizer/prompt 格式、eval card、checkpoint 哈希、限制说明未成文。
5. Demo：尚无面向用户的 Deep Research 演示流（任务选择、检索轨迹、引用、打分拆解、报告输出）；`frontend`/`web`/`web-next` 的归属边界已有初版清单，后续需要按发布实践复核。
6. 专利披露书与权利要求草案已有初版（`docs/PATENT_DISCLOSURE_DRAFTS.md`），但还缺系统图、实施例、对比表、代理人审查和公开披露时间表。
7. 多智能体协作的工程卫生（大小写碰撞 `AGENT.md`/`agent.md`、`CLAUDE.md`/`claude.md`，worktree 流程，统一开发入口）未收口。

---

## 4. 总体技术路线

一条主线，五个不变量，三段推进。

### 4.1 主线

把"模态无关 grounding 奖励 + 受控沙箱 + 严格证据契约"这一条护城河，从评测（13 个框架打分）一路贯通到训练（GRPO 训出开放模型）再到产品（Deep Research 原型 + Demo），最后用同一套机制支撑专利与论文。所有新增能力都以"加后端 / 加工具，不改奖励契约"的方式接入。

### 4.2 五个不变量（任何改动违反其一即视为缺陷）

1. **奖励契约不变**：grounding 只读 `rollout.retrieved_snippets`（url -> text）与被引 URL，`s_ground = 0.6*f1_claim + 0.4*r_resolve`。任何新取证工具必须把证据落成 `(url, text)` 进 `ToolResult.snippets` / `fetched_urls`，奖励侧零改动。状态变更类工具走独立 verifier，不动 grounding。
2. **默认路径字节一致**：无 `acquisition.tools_allowed`（或恰为 `["search","fetch"]`）的任务行为、奖励、env trace 与从前完全一致。
3. **重依赖惰性**：faiss/torch/playwright/psycopg2/mysql/sentence-transformers/mcp 一律函数内惰性导入，纯 `python3` 可 import。
4. **回归常绿**：上述 11 文件 pytest 保持 >= 122 passed。
5. **安全闸门不放宽**：`run_code`/`run_bash` 网络锁定三个 localhost；SQL 只读 + 表/列白名单；写操作仅对可重置沙箱快照生效。

### 4.3 三段推进

- 第一段（离线先行，无需 GPU/沙箱）：补齐 Track A 代码（write/vision/computer-use loop/RAG CLI），写演示任务，做综述与新颖性映射，起草专利骨架，定义模型与基准 release 模板。
- 第二段（活沙箱 + 单 5090）：确认 golden URL、接通真实 SQL/RAG/exec 后端、跑通 GRPO pilot、产出第一条真实训练曲线、做第一版 Demo。
- 第三段（规模化 + 收口）：扩 RL 课程与训练步数、做消融与人工审计、冻结基准 v0.1 与模型适配器 v0.1、产出论文图表、提交论文、提交专利、交付最终包。

---

## 5. 工作流、里程碑、角色建议与交付物

下面七个工作流（WP0 到 WP7）可并行认领。每个工作流给出目的、交付物、角色建议、验收。

### WP0 工程卫生与协作

- 目的：在规模化前让多智能体协作可靠。
- 已完成：本地冒烟脚本 `scripts/check_track_a_local.sh`、文档 `docs/LOCAL_DEV_CHECKS.md`、资产归属与交付清单 `docs/ASSET_OWNERSHIP_AND_DELIVERY.md`、多 agent 规则与大小写碰撞说明已写入 `AGENT.md`。
- 剩余交付物：干净的 worktree 流程执行规范；`frontend`/`web`/`web-next`/数据输出/release 产物的归属表；可选的统一入口（`pyproject.toml` 或 `Makefile` 本地冒烟目标）。
- 角色：1 名工程负责人（兼 CI）。
- 验收：新人按 `docs/LOCAL_DEV_CHECKS.md` 一条命令跑通离线冒烟；归属表评审通过。

### WP1 研究综述与新颖性映射

- 目的：界定科学贡献与可专利点。
- 已完成初版：`docs/RESEARCH_SURVEY.md`，含 related work 表、创新点映射、claim-to-evidence map、论文 A/B 证据需求。
- 剩余交付物：把综述扩成论文 Related Work 可直接使用的版本；补每个代表工作的正式引用、数据规模、评价协议、局限和我们差异。
- 角色：1 名研究负责人 + 1 名实习生（文献整理）。
- 验收：综述覆盖 `docs/ACQUISITION_ROADMAP.md` 已引用的全部 2026 对标工作；novelty map 与专利候选交叉引用一致。

### WP2 Agentic RL 评测与训练系统

- 目的：把当前 RL 环境变成可靠训练系统。
- 交付物：
  - 版本化任务 schema（acquisition tools、expected state、markdown_spec、citation_policy、golden seeds）。
  - 确定性 FAST 奖励路径 + 活沙箱奖励路径双轨。
  - 已完成工具：`src/rl/tools_write.py`（`cart_add`、`order_place`、`order_cancel`，仅落 `state_delta`）+ `src/verifiers/state_diff_verifier.py`（expected state recursive subset match）+ `src/rl/user_sim.py`（注入式 LLM seam，脚本化 fake 离线测试）。
  - 已完成工具：`src/rl/tools_vision.py`（`read_image`，`Captioner` Protocol + `ctx.extras["captioner"]` DI seam）。
  - 已完成 computer-use wiring：`src/rl/backends.py` 中的 page-backed observe-act loop，动作集覆盖 click、double_click、scroll、type、keypress、drag、move、wait、screenshot、done；VLM 仍为注入 seam。
  - 已完成 RAG 索引 CLI：`scripts/build_rag_index.py`，支持 no-dense 离线路径与默认 dense 路径入口。
  - 待补演示任务：`rl_tool_write_0001.json`、`rl_tool_vision_0001.json`（从 READY 任务派生，扩 `tools_allowed`）。
  - GRPO pilot 报告（trend.jsonl + checkpoint/resume 验证）。
  - 工具安全包络文档（SQL/code/crawl/write/RAG/vision/computer-use 各自的网络锁、白名单、超时、行/页上限）。
- 角色：2 名 RL 工程师（1 主奖励/课程，1 主工具/安全）。
- 验收（离线 Track A）：已完成工具测试与本地 smoke，下一步以演示任务和评测接入为准；`build_tool_registry({"acquisition":{"tools_allowed":[...,"<tool>"]}}, ctx)` 暴露该工具，默认仍恰为 `["fetch","search"]`；新演示任务 `rl_task_validate.py` 退出 0；回归 >= 122 passed（加入新测试文件后总数上调）。
- 验收（Track B 活沙箱/GPU）：见第 11 节验收命令与 `docs/PHASE_B_QWEN_GRPO_SPEC.md` 第 6 节（组内奖励方差、loss 有限、resume 复现、3 步可完成）。

### WP3 通用 Deep Research 原型

- 目的：交付真正的 Deep Research agent 体验，而不仅是打分后端。
- 交付物：多步取证循环（search/fetch/RAG/SQL/crawl/browser/vision/可选 computer-use seam）；报告写作器（引用、来源摘要、不确定性注记、结构化分节）；面向用户的 Demo（任务选择、检索轨迹、被引 URL、奖励维度拆解、报告输出、失败用例）；MCP/适配器表面（外部 agent 跑同一沙箱）。
- 角色：1 名 agent 工程师 + 1 名前端工程师/实习生。
- 验收：在 `frontend` 中能选一个 RL 或 arena 任务，看到完整轨迹、引用、七维拆解与最终报告；外部 agent 经 MCP server 跑通一次 search/fetch 往返且字节一致。

### WP4 开放模型与基准集

- 目的：产出开源 agent 模型与基准交付物。
- 交付物：
  - 基准 v0.1 包：任务 JSON、golden seeds、schema 文档、打分代码、license、datasheet、baseline 结果表，并把训练任务集与公开 leaderboard 任务集明确分离（训练集是 `data/tasks/deep_research/rl/`，不进公开 arena）。
  - 模型 release：基座选择（首选 Unsloth Qwen3-3B/4B）、LoRA 适配器权重、训练配方（GRPO 配置、lr、ctx、g、reward weights）、tokenizer/prompt 格式、eval card、checkpoint 哈希、限制与安全说明。
  - 复现包：环境说明、沙箱搭建、本地冒烟、期望指标区间、leaderboard 再生路径。
- 角色：1 名模型负责人（兼训练）+ 1 名数据负责人。
- 验收：第三方按复现包能离线重建 leaderboard 并落在期望区间；eval card 模板在训练完成前先行就位。

### WP5 实验、论文与排行榜证据

- 目的：形成 1 到 2 篇 CCF-A 或等级相当投稿。
- 见第 7 节论文方向。
- 角色：研究负责人 + 全体共建实验矩阵。

### WP6 专利储备

- 目的：在公开 release 前保护最强机制。
- 已完成初版：`docs/PATENT_DISCLOSURE_DRAFTS.md`，含两个专利候选的技术问题、技术方案、独立权利要求草案、从属权利要求方向和公开披露风险。
- 剩余交付物：补系统图、实施例、对比表，并交给专利代理人改写正式申请文本。
- 角色：研究负责人 + 法务/专利代理对接。

### WP7 交付与人才培养

- 目的：可交付且利于实习生成长。
- 交付物：最终源码与文档包、数据与基准包、模型与结果包、Demo 与部署说明、实习生 onboarding 材料与 2 个范围清晰的实习项目（见第 10 节）。
- 角色：项目经理 + 导师。

---

## 6. 专利方向与权利要求草案

目标：1 到 2 项发明专利。两项候选都建立在仓库已实现且可演示的机制上，避免空泛主张。专利申报必须早于任何会构成公开披露的 release（站点、论文预印、开源），由 WP1 排程把关。

### 6.1 专利候选 1：受控沙箱 Deep Research 评测与训练方法

- 解决的问题：开放网检索不可复现（搜索每日漂移）、人工标注基准刷新成本极高（ResearchRubrics 2800 人时）、WebArena 类沙箱只测 UI 机制不测研究综合。
- 核心方法（对应代码）：把长文研究任务置于受控本地语料（Magento/Postmill/Kiwix）之内；用统一 wire-protocol shim（Tavily/Firecrawl 兼容）让任意框架零改造接入；用 proof-of-fetch 检索日志与证据溯源 overlay 把"被取回的页面"锁为事实基准；用引用解析（被引 URL 必须落在检索存储中）与模态无关 grounding 奖励 `s_ground = 0.6*f1_claim + 0.4*r_resolve` 对报告评分；严格沙箱契约（三层强制 + 域名审计）保证任何越界 URL 即判违规。
- 独立权利要求草案（要点）：一种基于受控本地语料库的研究型智能体评测方法，其特征在于：1）将研究任务的全部可引用证据约束于一个由若干本地服务构成的封闭来源白名单内；2）通过统一检索协议适配层使外部智能体在不修改其代码的前提下接入该白名单语料；3）记录每次取页的来源溯源日志，并以"被引 URL 必须命中取页日志"为门控；4）以一个不依赖证据获取方式（检索/浏览/视觉/SQL）的统一接地信号对报告打分，该信号由逐引用页面支持度与被引解析率加权构成。
- 从属权利要求要点：双裁判异族评审与自举置信区间 + 置换显著性检验的排行榜生成；oracle 三元组的数据库校验生成；越界 URL 的三层强制与运行后审计。
- 公开披露风险：站点 methodology 页与 README 已部分公开思路，需评估是否构成新颖性障碍；建议在扩展性技术细节（统一接地信号、proof-of-fetch 门控的具体实现）公开前完成申报。

### 6.2 专利候选 2：面向工具使用研究智能体的 Agentic RL 系统

- 解决的问题：前沿研究任务对小模型预算不可行导致 GRPO 组内零方差无梯度；多模态工具引入易破坏奖励一致性或安全边界。
- 核心方法（对应代码）：按任务的工具白名单（`acquisition.tools_allowed`）动态构建工具注册表，单一新增 `CallTool` 动作把任意类型工具折叠进固定七动作环；保方差的预算可行任务课程（所有硬门限可在 8 次工具调用内达成，competent 与 shallow 之间保持 >= 0.10 的可分离奖励差）；执行态 state-diff 验证器作为与 grounding 并列的第二奖励契约；对代码/SQL/写操作的严格安全包络（网络锁定本地三主机、只读 SELECT + 列白名单、写操作仅对可重置快照生效）。
- 独立权利要求草案（要点）：一种工具使用研究型智能体的强化学习训练系统，其特征在于：1）以每任务工具白名单动态装配工具注册表，并以单一通用工具调用动作将异构工具接入固定动作空间；2）训练任务的全部硬性阈值被设计为在固定工具调用预算内可达成，从而在策略组内维持非零奖励方差；3）对落地 `(url, text)` 证据的工具沿用统一接地奖励，对改变环境状态的工具改用独立的状态差异奖励；4）对可执行类工具施加网络锁定与只读/快照隔离的安全包络。
- 从属权利要求要点：用户模拟器约束下的 pass^k 评分；模态无关性的形式化保证（相同取证结果下不同后端奖励相等）；惰性导入与注入式 seam 的可离线测试结构。
- 公开披露风险：`docs/AGENTRL_TASK_SPEC.md`、`docs/ACQUISITION_ROADMAP.md` 已较详细，建议这两项机制的申报优先级高于综述/论文公开。

---

## 7. 论文方向、目标会议、实验要求与风险控制

目标：1 到 2 篇 CCF-A 或等级相当。两篇分别对应基准与训练，可独立投稿亦可互为支撑。

### 7.1 论文 A：受控沙箱 Deep Research 基准与可复现排行榜

- 主题：以受控本地语料 + 模态无关 grounding 奖励 + proof-of-fetch 构建可复现 Deep Research 长文综合基准与双裁判 Elo 排行榜。
- 目标会议（CCF-A 或等级相当）：NeurIPS Datasets and Benchmarks（CCF-A）、SIGIR、WWW、KDD、ACL/EMNLP；ICLR 作为等级相当备选。
- 实验要求：基准构建与任务覆盖统计（107 公开 + 124 内部规格）；人工审计集（citation 支持度与报告质量，建议 >= 200 条逐引用标注，报告标注者间一致性 kappa）；baseline agent 表（当前 13 框架，扩到学术层全部打分）；打分有效性（七维与人工评分相关性、per-pillar 区分度）；消融（ALCE 子串 vs NLI、fact_kg 权重、oracle v1 vs v2）；失败分类（URL 幻觉、单域、单边、padding）。
- 风险控制：当前 48 battles/agent 下相邻名次几乎不显著，需把 battle 规模扩到能分辨相邻名次或明确只主张分层；oracle v2（`*.filtered.json`）必须用于重打分以消除已知假阴性；裁判长度/风格偏置需用结构化维度（fact_kg、evidence_density）交叉验证。

### 7.2 论文 B：受控证据获取下的 Agentic RL grounded Deep Research

- 主题：在受控证据获取与严格 grounding 门控下，用 GRPO 训练工具使用的 Deep Research 小模型，并开放模型与课程。
- 目标会议：NeurIPS、ICML（CCF-A）、ACL/EMNLP；ICLR/COLM 作为等级相当备选。
- 实验要求：RL 任务课程（easy 到 harder + bilingual，保方差证据）；GRPO 训练曲线（组内奖励方差、advantage std、loss、reward 上升）；工具消融（shim vs RAG vs browser 同任务奖励差）；模态 parity（相同取证结果下不同后端奖励相等，已有离线证明，补活沙箱版）；anti-fabrication 奖励（no-fetch 得 0、cite-without-fetch 归零的训练前后行为对比）；模型 release（适配器 + eval card）。
- 风险控制：单 5090 资源下先做 honest pilot（非 SOTA），明确 reward 上升为 Tier-1 目标而非冒烟必需；vLLM/unsloth 不得把 torch 降级离开 2.11+cu128/sm_120；大规模训练前预注册主张（claims）避免事后挑选。

---

## 8. 开放模型与基准发布计划

### 8.1 基准发布（benchmark v0.1）

- 内容：冻结一个版本化切分（公开 leaderboard 任务集，与训练集 `rl/` 严格分离）+ 任务 schema 文档 + golden + 打分脚本 + license + datasheet + baseline 结果表 + leaderboard 再生路径。
- 版本与冻结：在 oracle v2 重打分完成、学术层全部打分后冻结 v0.1；后续以 `v<MAJOR>-<YYYY-MM-DD>` 记入 changelog（仅在真正部署时，由具备权限者执行，本路线图不触碰）。
- 复现命令（公开）：见第 11 节"基准再生"。

### 8.2 模型发布（adapter v0.1）

- 基座：Unsloth Qwen3-3B（pilot）/ Qwen3-4B（扩展），4bit + LoRA（r=16, alpha=32, 目标模块 q/k/v/o/gate/up/down）。
- 产物：LoRA 适配器权重 + `qwen_policy.json`（model_name、ctx、step）+ 训练配方 + tokenizer/prompt 格式 + eval card（任务、指标、限制、安全、复现）+ checkpoint 哈希。
- 发布前置：训练曲线证据、模态 parity 活沙箱版、安全包络验证报告齐备；专利申报先于权重公开。

---

## 9. 演示系统计划

- 落点：收敛到 `frontend` 为唯一公开站点源，明确 `web`/`web-next` 归属（WP0 归属表）。
- 新增 Demo 流：在现有 leaderboard/arena/tasks/agents/insights 页之外，加一个"Deep Research 演示"页，支持：1）从 RL 任务集或 arena 任务中选题；2）展示多步轨迹（search -> open -> read -> cite -> finalize 与 `CallTool` 调用）；3）展示被引 URL 与 proof-of-fetch；4）展示七维（或 RL 十维）奖励拆解；5）展示最终 markdown 报告与失败用例对照。
- 外部接入：MCP server（`integrations/mcp_server/`）作为外部前沿 agent 的标准接入面，Demo 页给出连接说明。
- 部署纪律：任何对 Demo 的部署改动必须先按 CLAUDE.md 硬规则在 `data/changelog.json` 记录并重建 `web/dist`，再由具备权限者推送 `main`。本路线图不执行任何部署或 changelog 写入。

---

## 10. 实习生培养计划

目标：1 到 2 名实习生，范围清晰、可独立产出、有明确导师验收。

### 实习项目 1：RL 任务校验与 golden URL 审计（偏数据/评测）

- 任务：在活沙箱上逐条确认 `data/golden/rl/*.json` 的 URL 可达性，对 404 重定位到真实 opened URL，重跑 `rl_task_validate.py`；产出任务 datasheet（每任务的 sites、difficulty、language、competent composite、golden 域分布、可行性注记）。
- 产出：审计报告 + 修正后的 golden + 全部任务 READY 截图/日志 + datasheet。
- 导师验收：所有受影响任务验证器退出 0；datasheet 评审通过。

### 实习项目 2：前端 Demo 与实验可视化（偏前端/可视化）

- 任务：在 `frontend` 实现第 9 节 Demo 流的轨迹、引用、奖励拆解视图；整理实验图表（训练曲线、per-pillar Elo、消融）；记录小规模可用性日志。
- 产出：可运行 Demo 页（本地）+ 实验可视化组件 + 可用性日志。
- 导师验收：本地按一个任务跑通完整 Demo；可视化与论文图表口径一致。

两个项目都不触碰奖励契约与安全闸门，适合实习生在受控范围内成长，并直接喂给 WP3/WP4/WP5 的交付。

---

## 11. 里程碑（1 周 / 1 月 / 2 月 / 3 月 / 6 月）

### M0：1 周

- WP0 工程卫生收口（冒烟脚本 + 文档 + 归属表 + 大小写碰撞处置）。其中冒烟脚本、local checks、资产归属初版已完成。
- 本路线图评审通过，认领七个工作流与多智能体 owner。
- 起草两份专利披露骨架（problem/method/claims 占位）。当前已完成初版，下一步交给代理人风格改写。
- 验收：`docs/LOCAL_DEV_CHECKS.md` 一条命令跑通离线冒烟；回归 >= 122 passed。

### M1：1 月（含 2 到 4 周）

- WP1 综述与新颖性映射定稿（`docs/RESEARCH_SURVEY.md`）。
- WP2 Track A 集成闭环：基于已完成的 write、vision、computer-use loop、RAG CLI，补 `rl_tool_write_0001`/`rl_tool_vision_0001` 演示任务，把 `StateDiffVerifier` 接入 execution-goal 评测路径，并写 Track B runbook。
- WP4 冻结基准与模型 release 模板（schema 文档 + eval card 模板 + datasheet 模板）。
- 验收：新增工具/任务全部离线测试通过且 `rl_task_validate.py` 退出 0；回归总数上调后仍全绿。

### M2：1 到 2 月（活沙箱 + 单 5090）

- 接通活沙箱：逐条确认 golden URL（实习项目 1），接 SQL/RAG/exec 真实后端（Track B1/B2/B3），验证安全闸门在真实环境保持。
- 跑通第一次 GRPO pilot（`scripts/train_grpo_pilot.py`），产出 trend.jsonl，验证组内奖励方差、loss 有限、checkpoint/resume。
- WP3 第一版 Demo（检索轨迹 + 引用 + 奖励拆解）。
- 起草两份专利披露书完整版。
- 验收：见 `docs/PHASE_B_QWEN_GRPO_SPEC.md` 第 6 节；活沙箱模态 parity 通过。

### M3：2 到 3 月

- 扩展训练与消融（工具 ablation、modality parity 活沙箱版、anti-fabrication 前后对比）。
- oracle v2 重打分 + 学术层全部打分；冻结基准 v0.1 与模型适配器 v0.1。
- 产出论文 A/B 图表与表格；实习生主导审计与 Demo 打磨。
- 验收：基准 v0.1 可第三方复现并落在期望区间；适配器 v0.1 + eval card 齐备。

### M4 到 M5：3 到 6 月

- 提交论文 A（先行），准备论文 B。
- 申报 1 到 2 项专利（先于任何会构成公开披露的 release）。
- 按约定披露时间表发布基准、模型、代码、数据、Demo 包。
- 交付最终技术报告与 handoff 包（第 12 节交付清单）。
- 验收：见第 12 节最终交付验收。

---

## 12. 验收标准与验证命令

### 12.1 离线回归（任何阶段、任何机器，无重依赖）

```
# 全模块可 import（无 faiss/torch/playwright/psycopg2/mysql/sentence-transformers/mcp）
python3 -c "import src.rl.tools, src.rl.tools_rag, src.rl.tools_sql, src.rl.tools_crawl, \
  src.rl.tools_exec, src.rl.env, integrations.agents; print('imports OK')"

# 回归基线（保持 >= 122 passed；新增工具后把新测试文件加入列表并上调阈值）
python3 -m pytest tests/test_tool_registry.py tests/test_modality_parity.py tests/test_rl_reward.py \
  tests/test_grpo_harness.py tests/test_action_parser.py tests/test_composite_v3.py \
  tests/test_tools_rag.py tests/test_tools_sql.py tests/test_tools_crawl.py tests/test_tools_exec.py \
  tests/test_mcp_server.py -q
```

### 12.2 RL 任务就绪（每个新增/改动任务）

```
python3 scripts/rl_task_validate.py data/tasks/deep_research/rl/<task_id>.json
# 退出 0 = READY（headroom/gradient/balance_bites/no_perverse/variance/feasible 六项全 PASS）
```

工具注册表验收：`build_tool_registry({"acquisition":{"tools_allowed":[...,"<tool>"]}}, ctx)` 暴露该工具；默认 `build_tool_registry({}, ctx)` 仍恰为 `["fetch","search"]`。

### 12.3 GRPO pilot（活沙箱 + GPU，my5090）

- trend.jsonl 显示组内奖励有方差（rewards 变化时 advantage_std 约 1）。
- update loss 有限、无 OOM。
- resume 复现 step + reward。
- 3 步运行可完成（reward 上升为 Tier-1 目标，非冒烟必需）。

### 12.4 基准再生（公开复现）

```
python3 scripts/rescore_all_with_deepseek.py   # 写 final_<agent>_<task>.json
python3 scripts/build_final_leaderboard.py      # 写 FINAL_LEADERBOARD.md（自举 CI + 置换检验）
```

期望：复现出的 Elo 点估计落在已发布 95% 置信区间内；分层结论稳定。

### 12.5 最终交付验收（M5）

- 源码与文档包：仓库可离线 import + 回归全绿 + 关键文档齐备。
- 数据与基准包：benchmark v0.1（schema/golden/打分脚本/license/datasheet/baseline 表）可第三方复现。
- 模型与结果包：LoRA 适配器 + eval card + checkpoint 哈希 + 训练曲线 + 消融表。
- Demo 与部署说明：本地可跑通一个任务的完整 Demo；MCP 接入往返字节一致。
- 专利与论文：2 份披露书 + 至少 1 篇投稿、1 篇在投/准备。

---

## 13. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| GRPO pilot 在真实 GPU 不收敛或 OOM | 论文 B 与开放模型受阻 | 先 honest pilot；ctx 降到 4096、per-turn token 降到 384；单轨迹处理 + grad-checkpointing；reward 上升非冒烟必需 |
| vLLM/unsloth 安装把 torch 降级离开 sm_120 | 5090 不可用 | 分阶段安装后每步验 MATMUL_OK；必要时 `--no-deps` 装 vllm/unsloth 并手补依赖 |
| golden 种子 URL 在活沙箱 404 | RL 任务奖励门限不可达 | 实习项目 1 逐条确认并重定位，重跑验证器 |
| oracle v1 假阴性污染 fact_kg | 基准结论被质疑 | 用已生成的 `*.filtered.json` v2 重打分；fact_kg 权重过渡期保持 0.05 |
| 排行榜样本量不足（48 battles/agent） | 相邻名次不显著 | 扩 battle 规模或只主张分层；置换检验如实报告 |
| 裁判长度/风格偏置 | 打分有效性受质疑 | 结构化维度（fact_kg、evidence_density）交叉验证；双裁判异族评审 |
| 代码/SQL/写操作越界（host-escape） | 安全事故 | 网络锁定三主机、只读 SELECT + 列白名单、写操作仅对可重置快照；真实后端在 microVM 层验证网络锁 |
| 公开披露早于专利申报 | 丧失新颖性 | WP1 排程把关；专利申报先于站点/论文/开源 release |
| `frontend`/`web`/`web-next` 归属不清导致误部署 | 站点事故 | WP0 归属表 + CLAUDE.md changelog 硬规则；本路线图不执行部署 |
| 跨机器工作区状态不一致 | 路线图或 agent 分工误判 | 以本地 smoke 与本地文件为准；同步前先明确差异 |

---

## 14. 立即可做的下一步 10 项行动

1. WP1：把 `docs/RESEARCH_SURVEY.md` 扩成论文 Related Work 草稿，补正式引用、数据规模和评价协议。
2. WP6：给 `docs/PATENT_DISCLOSURE_DRAFTS.md` 补 3 张图的文字版：系统架构图、工具注册表与奖励折叠图、RL 训练闭环图。
3. WP2：派生 `rl_tool_write_0001.json`，接入 `StateDiffVerifier` 到 execution-goal 评测路径，跑 `rl_task_validate.py` 与本地 smoke。
4. WP2：派生 `rl_tool_vision_0001.json`，把 `read_image` 的 caption snippets 纳入演示任务 trace。
5. WP2：为 `scripts/build_rag_index.py` 写 Track B 全量索引 runbook，明确 Kiwix、Magento、Postmill 三路语料输入。
6. WP2：写 golden URL live-validation 脚本，批量检查 `data/golden/rl/*.json` 并报告 404/repoint 候选。
7. WP4：基于 `docs/templates/BENCHMARK_DATASHEET_TEMPLATE.md` 与 `docs/templates/MODEL_EVAL_CARD_TEMPLATE.md` 落地具体版本，明确训练集与公开 leaderboard 集分离。
8. Track B 准备：把 SQL/RAG/exec 真实后端的连接配置与"如何在 my5090 上跑"的 runbook 写成脚本注释，留待活沙箱会话执行（不在离线执行）。
9. WP5：建立实验矩阵草案（baselines × tools × modalities × reward variants × model sizes）与人工审计集采样方案，预注册论文主张。
10. WP3：在 `frontend` 设计 Deep Research Demo 信息架构，先做本地 mock 数据版，不触碰 `web/dist`。

---

附：本路线图遵守 CODEX_HANDOFF 与 CLAUDE.md 的硬规则。不修改奖励契约、不放宽安全闸门、不改 `data/changelog.json`、不部署、不提交、不推送。所有"已建成"判断以本地文件与本地测试实证为准。
