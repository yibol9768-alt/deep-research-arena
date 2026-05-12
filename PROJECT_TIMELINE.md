# Deep Research Arena — 完整项目时间线

**日期范围**: 2026-03-30(雏形)→ 2026-04-20(HANDOFF 交接)
**数据源**: 11 个 session (jsonl) + 27 个 git commit + 项目内 17 个 `.md` 文档
**适用**: 从头到尾了解这个项目每一步干了什么、踩了什么坑、用户怎么拍板的

---

## 0. 一句话概括

> 从"AI Agent 基准(Phase 1 scaffold)"起步,转向"真实沙盒 + Deep Research 任务 + 确定性评分 + Arena Elo",中间经过 v2(9 task × 4 agent MEGA Arena)→ v3(KG Fact Verifier + 跨站)→ Phase 7-9(Shim 统一接入层 + 14 agent + DeepSeek judge)→ Phase 10a-d(49 GB Wiki + GPT-5-chat-latest + IRT + 中文 paper 7 页可编译),最终产出一篇可复现 benchmark 论文雏形。

---

## 1. Phase 总览

| Phase | 时间 | 目标 | 关键成果 | 代表 commit |
|---|---|---|---|---|
| **Phase 0(Scaffold)** | 2026-03-30 → 04-10 | AI Agent 基准 scaffold(WebArena + SWE-Bench + GAIA 范式),Pydantic 数据模型 + 4 维度评分器 | 1200+ 行代码 + 3 个示例 task(ec/dev/cms)+ `claude.md` 初版(Phase 1 生产就绪) | — (pre-git) |
| **Phase 1(调研)** | 04-11 | 研究字节 DeepResearch / DRACO / ResearchRubrics 等范式,决定走哪条路 | `BYTEDANCE_DEEP_RESEARCH_SURVEY.md`(35 KB)+ `RESEARCH.md`(23 KB) | — |
| **Phase 2(环境搭建)** | 04-15 凌晨 → 04-16 | WebArena shopping(Magento 141 GB) + reddit(Postmill 107 GB)容器部署到 westd;SSH + 梯子 + WSL Docker 调通 | 2 个沙盒容器 healthy;Mihomo 计划任务持久化 | `5caf5e8` Initial commit (2026-04-16 11:22) |
| **Phase 3(v3 Schema)** | 04-16 凌晨 | `MarkdownReportSpec` + `DeepResearchTaskV3` schema(替代 JSON 输出) | 31 tests 绿 | `b9b4661` v3 Phase 1: schema |
| **Phase 4(Task + Oracle)** | 04-16 下午 | 8 条 v3 task + 8 oracle + 193 KG 三元组真值 | `data/golden/*.json` | `b002532` v3 Phase 2 |
| **Phase 5(Fact KG Verifier)** | 04-16 晚 | 直连 Magento/Postmill DB 做 fact check | 16 tests 活体回环;recall 96.9%,bogus recall = 0 | `ac31d1a` v3 Phase 3 |
| **Phase 6(Markdown Verifier + Composite v3)** | 04-16 晚 | `markdown_report_verifier` + 120-item DRACO checklist + `composite_v3`(fact_kg 0.30 + checklist 0.20) | 27 tests 绿 | `0934b6f` v3 Phase 4 |
| **Phase 6 跨站** | 04-16 晚 → 04-17 下午 | 4 条跨站 DR 任务(shopping+reddit / gitlab+reddit / 3 站三角)+ GitLab/Shopping Admin 容器 + 统一 adapter | 3 agent × 4 cross-site task + 12 pairwise battles;**核心发现**: composite(glm-5 领先) vs judge(qwen 领先)分歧 | `cbf6629` → `16bc9f9` |
| **Phase 7(Shim 统一搜索层)** | 04-17 晚 → 04-18 凌晨 | FastAPI `:8081` 伪装 Tavily + Firecrawl,任何 DR 框架零代码接入 | DeerFlow 走 shim +162 Elo;GPT-Researcher / CAMEL-AI / smolagents 上线 | `16e217c` Phase 7-9 (335 files) |
| **Phase 8(Peer-review P0 修复)** | 04-18 下午 → 04-19 凌晨 | DeepSeek V3.2 judge(解 self-preference)+ Citation NLI entailment + scholarly/policy 20 task(0088-0107) | 87 → 107 task;bootstrap 95% CI + permutation test | 同上 `16e217c` |
| **Phase 9(角色互换方法论)** | 04-18 晚 | 发现 GLM JSON mode 不兼容 → 所有 agent 切 DeepSeek,judge 换回 GLM-4.7 | ODR/dzhng/smolagents 解锁;新增 `*-ds` 系列 agent | `16e217c` |
| **Phase 10a(Quick wins)** | 04-19 上午 | 49 GB 全英文 Wikipedia 上线 + smolagents 哨兵修 + oracle v2 plumbing | kiwix 双 ZIM 挂载;filter 产出 `.filtered.json` | `c2639ca` / `2108b64` |
| **Phase 10b(9 项 landed + paper scaffold)** | 04-19 晚 → 04-20 上午 | GPT-5-chat-latest agent + Bradley-Terry + token budget + WebArena 187 + length ablation + error taxonomy + adversarial + IRT 2-PL | `latex/findings.tex` 7 页 PDF(中文 + xeCJK);F1-F4 四大发现 | `5141d0c` / `5b140b9` / `9bfa102` / `e1684ec` |
| **Phase 10c(#65 全 matrix 重跑)** | 04-20 下午 | 14 × 8 = 80 scholarly runs + DeepSeek judge 重评 + paper 自动重生 | IRT 从 n=4 扩到 n=8;撤 "directional only" caveat | `6508535` / `8753e82` |
| **Phase 10d(bias + source diversity)** | 04-20 晚 | react agent bias 公开 + source_diversity 作为 pillar 候选 + shim 加 `/post_lookup`+`/product_lookup` | 5 项 paper 更新 | `4e9724c` / `92e52fd` |
| **HANDOFF** | 04-20 晚 | 把整个 project 交接给下个 agent | `HANDOFF.md` 16 KB + `~/.claude/plans/iterative-doodling-parrot.md` | `7ee11cb`(HANDOFF 12:34)+ 当前未提交的 24 个 answer.md |

---

## 2. 逐会话详细记录

> 按"用户第一条消息时间"升序。**纯技术 / 非 deep_reserch 的 session(mobol_app / agent_benchmark / daily / ScholarMind / bug_exam)** 只挂一行索引,不展开。


### Session A — 2026-03-31 `73c10be4`(前置,ScholarMind)

- **cwd**: `/Users/liuyibo/Desktop/lyb/agent_keyan`(后来演化成 ScholarMind / deep_reserch 前身)
- **用户需求**: "做一个九步研究 agent 系统(文献调研 → 选题 → 打分 → 生成代码 → 实验 → 写论文 → 按 ACLR 打分),调研已有仓库,拼起来"
- **做了什么**: 调研 9 个模块的开源仓库;分前端(React 桌面 + React Native)/ 后端(FastAPI M1-M9)两个文件夹;推 GitHub 仓库 `yibol9768-alt/ScholarMind`(100 files,23k lines)
- **产出**: ScholarMind repo(非本项目,但用户的"AI agent 系统"原始想法来自这里)
- **结尾**: 解压 `school mind mobile.zip` 放进 mobile/,推 GitHub

---

### Session B — 2026-04-11 `51ec92ce`(调研 Deep Research 评测范式)

- **cwd**: `/Users/liuyibo/Desktop/lyb/deep_reserch/paper_dr_lab`
- **用户需求(T1 贴的原文)**: "2024-2025 Deep Research 评测分化成三种范式(rubric-based / 可执行 / checklist),调研现状";**T6 果断**: "先开 planmode 仔细想想你该干什么"
- **做了什么**:
  1. 进 plan mode,列出 DRACO / ResearchRubrics / BrowseComp-Plus / LiveDRBench 对照矩阵
  2. 尝试 ssh 到 `connect.westd.seetacloud.com:36254` —— **首次遇到 Clash fake-IP 劫持**(`198.18.0.9`,TCP 通但 SSH 握手被断)
  3. 建议用户:加 `connect.westd.seetacloud.com` 直连规则 / 关 TUN / 服务器本地动手 三选一
  4. T71 "使用 glm5.1" —— 确定主力 LLM 是 GLM-5.1
  5. 调研开源 DR 框架(LDR / knowledge-storm / smolagents / CAMEL / GPT-Researcher / DeerFlow / ODR / dzhng),列出硬卡点(Py 版本 / Docker / 结构 trace)
- **踩坑**: Mac 5 个 utun 接口暴露透明代理;DNS 被 fake-IP 劫持,`dig @8.8.8.8` 也拿不到真实 IP → **后续所有 session 都要处理这个劫持**
- **结尾**: 用户说"试试我们服务器上面行不行",session interrupted(context run out)

---

### Session C — 2026-04-15 凌晨 `7b358cd8`(WebArena 下载 + 梯子 + claude.md)

- **cwd**: `/Users/liuyibo/Desktop/lyb/deep_reserch/webarena_ref`
- **用户需求流**(前 10 条):
  - "连接 ssh" / "找找 配置过了" / "我记得配置过免密"
  - T17 给出 `8ll05950fh36.vicp.fun:28744`(vicp.fun 内网穿透)
  - T21 "你帮我搞吧 我就记得这些了 root 密码 xopowo128456"
  - T31 **"创建 claude.md 写到根目录 默认 ssh 不要链接梯子 而且记住这个远程"** ← claude.md 起源
- **做了什么**:
  1. 写 `~/.ssh/config` westd alias;生成 `~/.ssh/westd_key` 免密
  2. 写 `/Users/liuyibo/Desktop/lyb/CLAUDE.md`(远程主机文档 + cmd 陷阱 + PowerShell 模板)
  3. T33 "还记得我们想干嘛来着吗" → 回顾 deep_reserch Phase 1 scaffold,决定做 "固定环境 + 固定网页"评测集
  4. 调研字节 Deep Research → 生成 `BYTEDANCE_DEEP_RESEARCH_SURVEY.md`
  5. T86 用户给机场订阅 URL:`https://afdbce8c48cba7cf564ff6c42536523c.cdn-res-oss-cn-hongkong-aliyuncs-file.com/...` → 装 Mihomo 到 westd,订阅 YAML 模式,7890 端口
  6. 下载 WebArena 67 GB shopping 镜像(mihomo = 1 节点,ETA 98 min → 65% → complete)
  7. T213 生成 `scripts/deploy_to_westd.sh` 一键部署脚本
- **踩坑**:
  - 梯子订阅必须带 `User-Agent: ClashforWindows/0.20.39`,否则拿到 base64 SS 格式,Mihomo 吃不了(教训进 CLAUDE.md)
  - `Invoke-WebRequest -Proxy` 要显式指定,Docker daemon / apt / /etc/environment 要单独配代理
- **结尾**: T214 "我们原来的任务是干嘛来着"(用户忘了目标)→ T215 agent 回溯整条路径:**deep_reserch Phase 1 → Phase 2 MVP → Magento + Verifier + Runner + Oracle 第一条任务**

---

### Session D — 2026-04-15 下午 → 04-16 `43e7d20f`(v3 六阶段 + 飞书 MCP)

- **cwd**: `/Users/liuyibo/Desktop/lyb/deep_reserch/third_party`
- **核心用户指令链**(按时间):
  - T1 "忘记了 可以找找聊天记录吗 忘记进行到哪里了"(**典型用户 — 记不得上次做到哪**)
  - T22 **"坚持 Deep Research,停掉 WebArena 这条线"** → 方向拍板
  - T25 "写一个文档 做一个 todolist"
  - T32 **"不要问我 一直持续的做完 不要停止 好吗 GLM-5.1 用这个 把你的 tasks 都做完了再向我汇报"** ← autonomous 模式授权
  - T51 "先写一个 plan.md 我给老师汇报一下" → `PLAN.md` 诞生
  - T59 "我记得我之前调研过要怎么给深度研究打分 可以参考一下"
  - T72 **"改一下吧...两个最终 elo 分是一样的太夸张了"** → Arena 6 pillar 加权起源
  - T146 **"深度研究不应该是 json 格式 改一下吧"** → 从 JSON 输出切到 markdown 报告(v3 核心决策)
  - T153 **"我需要的正是 deerflow 这种的深度研究...多网页的...评分逻辑和题目...知识图谱...开 plan 模式一个一个来吧"** → v3 完整蓝图拍板
  - T158 "对的对的 继续往下做吧 你现在需要做的是 v3"
  - T176 "开 chrome mcp 飞书 wiki 搞得好看一些" → 飞书 MCP 起源
  - T185 **"帮我配置一个写飞书的好用的东西 以后都让你写了"** → `lark` MCP 装好(App ID `cli_a96a3765fa4d1cc9`,20 API 权限)
  - T272 "commit 吧 然后做一个详细的 readme"
- **做了什么**(按阶段):
  1. **Phase 2 落地**: 9 task × 4 agent × 27 battles MEGA Arena 跑完(`bench_v2_MEGA.md`)—— 发现 **glm-4.6 反超到第 2**、**LLM judge 暴露 length-bias**(简洁回答被 judge 排第 1)
  2. **v3 Phase 1-5** 在 04-16 一天之内全部落地:
     - Phase 1 schema: `MarkdownReportSpec` + `DeepResearchTaskV3`(31 tests 绿)
     - Phase 2: 8 条 v3 task + 8 oracle + 193 KG 三元组
     - Phase 3: `db_connect` / `db_schema_map` / `db_verifier` / `triple_extractor` + `fact_kg_verifier` + 16 tests(活体 DB 回环)
     - Phase 4: `markdown_report_verifier` + 120-item DRACO checklist + `composite_v3`(fact_kg 0.30 主力)
     - Phase 5: `bench_v3.py` + ReAct agent 双提示(JSON / markdown 自动切换)
  3. **Phase 6 跨站**: 4 条跨站任务 + GitLab(8023)+ Shopping Admin(7780)容器 + `unified_adapter.py`
  4. **飞书 MCP**: 自建应用 Claude Code Helper v1.0.0 上线,拿 `tenant_access_token` 通,wiki 写入 OK
- **产出 commit**:
  - `5caf5e8` Initial commit: Deep Research Benchmark(303 files)
  - `b9b4661` v3 Phase 1: schema
  - `b002532` v3 Phase 2: 8 tasks + oracles + KG
  - `ac31d1a` v3 Phase 3: KG fact verifier
  - `0934b6f` v3 Phase 4: markdown + composite v3
  - `cbf6629` v3 Phase 6: cross-site tasks + multi-site infra
- **踩坑**:
  - D 盘空间吃紧(Magento 141 + Postmill 107 GB → reddit image 下完立刻 load + prune)
  - 飞书文档"格式都怪怪的"(早期用 JS 直写 block,块类型映射不全)→ 切 `lark` MCP 后规范
  - context 爆掉两次(T204 + 45ffd795 T369 / T479 都有 "session continued" 摘要)
- **结尾**: T278 "你好"(新 session 开头)→ 转入 45ffd795 这条主线

---

### Session E — 2026-04-17 凌晨 `f8d8a97e`(8 turns,被打断)

- **cwd**: `/Users/liuyibo/Desktop/lyb/deep_reserch`
- **用户需求**: T3 贴 HANDOFF.md 概览 + T7 "是我让你接着干的"
- **做了什么**: agent 读 HANDOFF,列出 P0-1/P0-2/P0-3(qwen citation=0、DeerFlow fact_kg 全 0、0007 markdown_structure=0.4)
- **结尾**: T8 被用户打断(request interrupted)→ 跳到 45ffd795 主线

---

### Session F — 2026-04-17 下午 → 04-20 凌晨 `45ffd795` ⭐ **主力 session,17 MB / 623 turns / 4 天**

- **cwd**: `/Users/liuyibo/Desktop/lyb/deep_reserch/data/tasks/deep_research/cross_site`
- **阶段划分**(按时间切)

#### F.1 Phase 6 收尾 + Phase 7 Shim 设计(04-17 下午 → 04-18 凌晨)
- T13 **"两个消息不是一个项目 你干那个 deepreserch 的就可以了 肉眼先看一下那个做得好 你可以调研一下各家的先"**(用户区分 bug_exam vs deep_reserch)
- T28 "deerflow 改一下 然后我们是想做一个 elo 分的 deepreserch 框架 继续下去"
- T76 **"5e4b5082f8954dc98d63935220002707.9Go2OiZMkcbDDXVx...用 glm4.7 和 5 使用这个 codingplan 套餐 不要用通用套餐"** → 切 GLM Coding Plan(月费包)
- T81 "不行单并发慢慢跑"(中转 API 429)→ 改 2s 单并发 + 6 次 429 重试
- 多个 ssh smoke test 循环:DeerFlow 0001 → 4 task batch → 0006 rerun 解决
- 核心决策:把 DeerFlow 的 custom adapter(5000-char 截断)换成 shim 层 → DeerFlow Elo +162
- **产出**:
  - `integrations/search_shim/` FastAPI(Tavily `/search` + Firecrawl `/v1/search|scrape` + kiwix)
  - commits `168358e` / `1d331cc` / `6cedfd3` / `5fb6c9e` / `982e4fd` / `5c8f20c` / `de9c250` / `16bc9f9`(Phase 6 扫尾)

#### F.2 Phase 7 多框架接入(04-18 上午-下午)
- T196 **"deerflow 应该是一个很牛逼的框架...网络环境可以伪装成 deerflow 需要的 api 或者是搜索工具 不只是 deerflow 其他的 research 框架也要有...开发者很简单可以介入我们的框架"** ← 把"shim 作 product"这个论点钉死
- T264 "就只有 gpt research 和 deerflow 吗 不能介入更多更多吗"
- T267 "有多少加多少 全加进去 多多的"
- T282 **"都用我们刚刚的伪装搜索 API"**
- T286 "调研一下还有没有其他的开源 ds 框架 而且我们的题目也少了 扩展到 80-100 题的规模吧"
- T292 "妈的 20+ 都上 我们评测一定要多"(真实语气)
- **接入 agent**: DeerFlow(legacy / new / shim 三版)+ GPT-Researcher + CAMEL-AI + smolagents + ODR + CAMEL-DS + dzhng(失败,loop 30+ min)+ LDR(prompt 模板没填入)+ STORM(内置 scraper 绕开 shim 直连 Wikipedia)
- **8 agent × 4 task = 32 runs** 跑通

#### F.3 Phase 8 peer-review P0 修复(04-18 下午 → 04-19 凌晨)
- T305 **"你这样做出来的 task 怎么保证他的答案是准确的呢?"** → 推动 Oracle v2 + KG 扩容
- T309 "调研一下我们评测合理吗 这个是对的吗我们这么搞"
- T408 **"为什么要返回 json 我们不是 deep_research 吗"** → 再次钉死 markdown-only 输出
- T412 **"那就全面使用 deepseekv3.2 的 api"** → 所有 agent 切 DeepSeek,judge 回到 GLM-4.7(角色互换)
- **Phase 8 产出**:
  - DeepSeek V3.2 judge(`deepseek-chat`,不同 family → self-preference 解)
  - `CITATION_MODE=entailment` NLI via DeepSeek
  - 20 条 scholarly/policy task(0088-0107,医学/经济/历史/AI 伦理/城市规划)→ **task 总量 87 → 107**
  - `compute_elo_with_ci`(N=1000 bootstrap)+ `rank_significance_test`(N=1000 permutation)+ `per_pillar_elo`
  - `rebuild_oracle_filtered.py` → `data/golden/*.filtered.json`(拒 Magic Home Nightstands 类伪阳性)

#### F.4 Phase 10a Quick wins(04-19 上午)
- T455 "ds 幻觉严重 glm5.1 好一点对吗" → 对角指派策略成熟
- T457 "现在有什么可以改善的吧 我感觉题目丰富度可以上来"
- T460 agent 交了 P0/P1/P2/P3 优先级 → 用户 T462 "该做的做一下吧"
- **做了**: kiwix 双 ZIM(3 GB Simple + 49 GB nopic)挂载;smolagents `</code>` 哨兵修(之前 zero tool call 纯幻觉);oracle v2 filter partial;commit `c2639ca` / `2108b64`

#### F.5 Phase 10b 9 项 landed(04-19 下午 → 04-20 上午)
- T469 "一句话给老师..."(agent 起草一句话成果)
- T504 **"假如说我用 openai 的 api 做一轮测试 gpt5.4 大概什么价格"** → 接 OpenAI agent
- T508 给了 OpenAI key + 代理 `http://35.164.11.19:3887/v1`
- T516 "judge 不一样会导致分数相差很大吗" → 促成 cross-family judge 讨论
- T520 "查一下有不是 resoning 的模型吗 除了 5.4" → 发现 **gpt-5-chat-latest 才是纯 chat**,gpt-5.4 在 multi-turn tool loop 里偷烧 reasoning tokens(教训进 HANDOFF.md)
- T544 "链接远程搞啊"
- T591 agent 总结 3 个 paper 发现 → T593 **"新建一个文件夹 latex 写好我们的 findings"** → `latex/findings.tex` 起源
- **9 项**(按 task 编号):
  - #52 49 GB Wiki + scholarly smoke(shim `_search_kiwix`)
  - #53 GPT-5-chat-latest agent(`scripts/run_gpt5.py`,8 runs)
  - #54 Per-agent token guard(`src/budget/token_guard.py`)
  - #55 WebArena 187 tasks(`adapt_webarena_tasks.py` + `factoid_verifier.py`)
  - #56 Bradley-Terry MLE + bootstrap CI(`src/scoring/bradley_terry.py`)
  - #58 Length-controlled ablation(`length_ablation.py` → F1:ρ=-0.30,judge 无长度偏好)
  - #59 Error taxonomy(`error_taxonomy.py` → F2:18 URL 幻觉全在 4 个特定 agent,各 100%)
  - #60 Adversarial corpus poisoning(5 task + `adversarial_verifier.py`)
  - #64 IRT 2-PL calibration(`irt_calibration.py` → F3:Spearman ρ=1.00 与 BT-Elo)
- **产出**: commit `5141d0c`(+25 diversity tasks)+ `5b140b9`(9 items + paper scaffold,218 files)

#### F.6 latex 中文化 + HANDOFF(04-20 凌晨)
- T611 **"改成全部都是中文吧 先停下来吧 实验"** → `xeCJK` + `ctex` 切换
- T617 "有编译问题 格式问题" → 修 2 处 overfull hbox、enumitem negative labelwidth、引号半角、中英字符粘连
- commit `9bfa102` 中文化 + `e1684ec` 排版定版 → **findings.pdf 7 页,0 warning**
- T622 "写一个文档让下一个 agent 继续你的工作" → `HANDOFF.md` 诞生(commit `7ee11cb`)

---

### Session G — 2026-04-17 下午 → 04-19 `e7050cf7`(54 turns,agent_benchmark → public GitHub)

- **cwd**: `/Users/liuyibo/Desktop/lyb/deep_reserch`
- **场景**: 并行 session,主要做 `bug_exam` public 化,但最后 T51 **发现 `bug_exam/CLAUDE.md` 和 `scripts/deploy.sh` 硬编码了失效的 GLM API key**(`sk-EZaFIa6P...`)
- **用户 T49 "public" + T52 "不管,直接 push"** → 第三选项(key 已 401 失效,直接 push)
- 产出: `yibol9768-alt/agent_benchmark` public repo 上线
- **与 deep_reserch 关系**: 证明"两个项目共用一个 workspace"的工作流 + secret scanning 经验

---

### Session H — 2026-04-17 `45ffd795` 前夜 `f8d8a97e`(见 Session E,已并入)

---

### Session I — 2026-04-20 中午 `a294c9c0` ⭐ **当前 session(就是本篇)**

- **cwd**: `/Users/liuyibo/Desktop/lyb/deep_reserch`
- **用户 3 条 request**:
  1. T1 "找一下 session 有关于 /Users/liuyibo/Desktop/lyb/deep_reserch 继续我们的实验"
  2. T6 "我们的项目是干嘛的来着"(典型用户 — 记不得上下文)
  3. T8 **"我们这个 pdf 还不够详细 找一找以前的 session 把我们每一步 每一步都干了什么说的清清白白 明明白白"** ← 触发本时间线
- **做了什么**: 本文 `PROJECT_TIMELINE.md` 生成

---

### Session J/K/L — 非 deep_reserch(仅索引)

| ID | 日期 | cwd | 概要 |
|---|---|---|---|
| `73c10be4` | 2026-03-31 | agent_keyan | ScholarMind 9 步 agent,推 `yibol9768-alt/ScholarMind` |
| `c8609f38` | 2026-04-02 | lyb | 小 session(34 turns)|
| `b9081fdf` | 2026-04-11 | bug_exam | bug_exam 相关 |
| `9cf4b8bf` / `aec6a883` | 2026-04-15/16 | Quantifying-Representation-Reliability | 另一个 paper |
| `2a47ce4e` | 2026-04-15 | lyb | 23 turns |
| `d8635beb` | 2026-04-18 | mobol_app | 40 个 mobol_app 评测 + Expo APK 构建 |
| `4022a4c3` | 2026-04-20 | daily | 微信 MCP 公众号自动写 |
| `4925bfc8` | 2026-04-20 | agent_benchmark | bug_exam M3 probe,被 Clash fake-IP 198.18.0.30 断 |
| `a49a54ba` | 2026-04-20 | bug_exam/dumps | bug_exam 相关 |
| `cd74f010` | 2026-04-20 | lyb | 学雅思规划 |

---

## 3. 关键里程碑(数字进化)

| 日期 | 指标 | 数值 |
|---|---|---|
| 2026-03-30 | Phase 1 scaffold 代码量 | 1 200 行,3 个示例 task |
| 2026-04-16 凌晨 | v2 MEGA Arena | 9 task × 4 agent × 27 battles/agent |
| 2026-04-16 晚 | v3 KG recall | 96.9%(187/193),bogus=0 |
| 2026-04-16 晚 | DRACO checklist | 120-item(15×8 task) |
| 2026-04-17 下午 | v3 Phase 6 cross-site Arena | 3 agent × 4 cross-site task,12 pairwise |
| 2026-04-18 凌晨 | Shim 启用后 DeerFlow Elo | +162(原 custom adapter 截断 5000-char) |
| 2026-04-19 凌晨 | Phase 7-8 Arena 规模 | 8 agent × 4 task = 32 runs;task 87 → 107 |
| 2026-04-19 凌晨 | Bootstrap CI + permutation | N=1000 |
| 2026-04-20 上午 | Phase 10b 落地 | **14 agent × 4 task,4 个 paper 发现**;paper 7 页 |
| 2026-04-20 下午 | Phase 10c #65 | 14 × 8 = 80 scholarly runs;IRT n_tasks 4 → 8 |
| 2026-04-20 晚 | HANDOFF 落地 | 16 KB HANDOFF.md,commit `7ee11cb` |
| **未提交** | 24 个 answer.md | 6 ds agent × 4 scholarly + gpt5chat 8 consumer/scholarly,judge 未打分 |

---

## 4. 4 个 paper 发现(`latex/findings.tex`)

| # | 发现 | 证据 | 位置 |
|---|---|---|---|
| **F1** | LLM Judge 无长度偏好(反向) | Spearman ρ = -0.30 across 7 pillars | `data/results/length_ablation.json` → `scripts/length_ablation.py` |
| **F2** | URL 幻觉是架构问题,非 LLM 问题 | 18 次 URL 幻觉集中在 4 个特定 agent(各 100%),其他 9 agent 各 0% | `data/results/error_taxonomy.json` → `scripts/error_taxonomy.py` |
| **F3** | IRT 与 BT-Elo 排序自洽 | Spearman ρ = 1.00;n_tasks 4→8 后仍成立 | `data/results/irt_calibration.json` → `scripts/irt_calibration.py` |
| **F4** | 同 shim 下 agent 架构决定源多样性 | gpt5chat 平均引 2.5 Wiki;gpt-researcher 引 0 | Phase 10c 80 runs |

---

## 5. 踩坑大全(按教训价值降序)

1. **Clash fake-IP 劫持 SSH**(`198.18.0.9` / `198.18.0.30`):域名 `*.vicp.fun` / `*.seetacloud.com` 被 TUN 模式透明代理接管,TCP 能连但握手被断。**不改代理**(用户反复叮嘱,见 CLAUDE.md 顶),只能重试 + `ProxyCommand` 直连。
2. **GPT-5.4 在 tool-loop 里偷烧 reasoning tokens**:单 prompt 测 `reasoning_tokens=0` 像 pure chat,多轮 tool-call 对话下却突然开启 reasoning,每次烧 ~750 output tokens 直到 budget 耗尽。**agent benchmark 必须用 `gpt-5-chat-latest`**(写进 `run_gpt5.py` docstring 和 HANDOFF.md)。
3. **shim 是 FastAPI 不是脚本**:`python -m integrations.search_shim.app` 加载模块后立即退出。正确启动要 `setsid nohup .venv-camel/bin/uvicorn ... --host 0.0.0.0 --port 8081`。shim 挂了的症状是 POST `/search` connection refused。
4. **GLM JSON mode 不兼容**:ODR / dzhng / smolagents 装好后 `langchain.with_structured_output` + `ai-sdk generate-object` 双双 ValidationError → Phase 9 角色互换(agent 切 DeepSeek,judge 换 GLM)解锁。
5. **DeerFlow custom adapter 截断 5000-char**:原以为 DeerFlow 弱,走 shim 后 +162 Elo → 教训:**评测不能对框架降级**(paper 里写进 position)。
6. **smolagents 哨兵格式错**:GLM-4.7 输出 `</code>` 代替 `<end_code>` → code parser 每步失败 → 零 tool call 纯幻觉。修法:`CodeAgent(..., stop_sequences=["</code>", "<end_code>"])`。
7. **gpt-5-chat-latest 把 tool 参数塞 content**:偶尔把 `finish(markdown_report=…)` 参数 JSON 打在 `content` 而不是 `tool_calls` 里。`run_gpt5.py` 的 `_unwrap_markdown_json` 用正则救。
8. **机场订阅 UA 敏感**:不带 `User-Agent: ClashforWindows/0.20.39` 会拿到 base64 SS 列表,Mihomo 吃不了。
9. **cmd 缺 head**:执行远端命令模板是 `ssh westd "powershell -NoProfile -Command \"[Console]::OutputEncoding=[Text.Encoding]::UTF8; <cmd>\""`,引号多了写 `.ps1` 到 `/tmp` → `scp` → WSL 内 `tr -d '\r'` 处理 CRLF。
10. **飞书 MCP 写块类型不全**:早期直接 JS 改 doc 结果格式怪怪的,切 `lark` MCP 后用规范化 API 调用(docx block batch update)。
11. **context 爆两次**:session `43e7d20f` T204 + session `45ffd795` T369 / T479 都触发了 "This session is being continued..."。经验是:**PLAN.md / HANDOFF.md / findings.tex 要反复更新**,让新 agent 能冷启动。
12. **d 盘吃紧**:Magento 141 + Postmill 107 = 250 GB,加 49 GB kiwix 和各镜像后频繁 `docker image prune`。

---

## 6. 未提交状态(HANDOFF 之后)

- HANDOFF 写于 2026-04-20 12:34(commit `7ee11cb`)
- 之后又提了 4 个 commit(`6508535` / `8753e82` / `4e9724c` / `92e52fd`),HANDOFF 内容已落后
- **工作树上 24 个未跟踪 answer.md**(agent 跑完,judge 未打分):
  - `camel-ai-ds × 4 scholarly`(0088/0095/0100/0105)
  - `gpt-researcher-ds × 4 scholarly`
  - `odr-ds × 4 scholarly`
  - `smolagents-ds × 4 scholarly`
  - `gpt5chat × 4 consumer + 4 scholarly`
- 继续路径 A(收尾):把 24 个 answer.md 跑 `scripts/rescore_all_with_deepseek.py` → 重生 `arena_elo_ED.json` → `python latex/generate_tables.py && make -C latex pdf`
- 继续路径 B:开工 #62 multi-LLM compositional agent

---

## 7. git log 对照表(27 个 commit)

| Commit | 日期 | 改了几个文件 | 含义 |
|---|---|---|---|
| `5caf5e8` | 2026-04-16 11:22 | 303 | Initial commit: Deep Research Benchmark |
| `b9b4661` | 2026-04-16 17:41 | 5 | v3 Phase 1: schema |
| `b002532` | 2026-04-16 17:41 | 38 | v3 Phase 2: 8 tasks + oracles + golden KG |
| `ac31d1a` | 2026-04-16 17:42 | 9 | v3 Phase 3: KG fact verifier(直连 DB)|
| `0934b6f` | 2026-04-16 17:42 | 9 | v3 Phase 4: markdown verifier + DRACO checklist + composite_v3 |
| `cbf6629` | 2026-04-16 20:28 | 33 | v3 Phase 6: 跨站 DR 任务 + 多站 infra |
| `168358e` | 2026-04-17 06:07 | 3 | server-side cross-site Arena results (glm-5 + qwen35plus) |
| `1d331cc` | 2026-04-17 06:08 | 13 | server-side Arena result JSONs |
| `6cedfd3` | 2026-04-17 14:27 | 21 | 3 个新 multi-page cross-site tasks + glm-5 Arena |
| `5fb6c9e` | 2026-04-17 14:35 | 10 | qwen3.5-plus Arena + final RESULTS_SUMMARY_v3 |
| `982e4fd` | 2026-04-17 14:52 | 2 | pairwise LLM judge — qwen 4-0 glm-5 |
| `5c8f20c` | 2026-04-17 15:01 | 2 | paper-ready findings doc |
| `de9c250` | 2026-04-17 16:06 | 14 | DeerFlow cross-site + 3-way pairwise Arena |
| `16bc9f9` | 2026-04-17 16:08 | 2 | RESULTS_SUMMARY_v3: full 3×4 cross-site Arena |
| `f46f80c` | 2026-04-17 21:20 | 2 | HANDOFF.md: full project handoff v1 |
| `16e217c` | 2026-04-19 09:05 | **335** | Phase 7-9: shim + multi-framework Elo + dual-judge |
| `c2639ca` | 2026-04-19 09:46 | 7 | Phase 10a quick wins: kiwix full-en + smolagents sentinel |
| `2108b64` | 2026-04-19 09:54 | 4 | Phase 10a: Oracle v2 plumbing(partial)|
| `5141d0c` | 2026-04-19 11:57 | 27 | Phase 10b P0: +25 diversity tasks(smoke/expert/adversarial)|
| `5b140b9` | 2026-04-20 10:50 | **219** | Phase 10b: 9 items + paper scaffold(`findings.tex` 7 页)|
| `9bfa102` | 2026-04-20 12:26 | 4 | latex: 中文化(ctex + xelatex)|
| `e1684ec` | 2026-04-20 12:30 | 2 | latex: 排版 / 编译 warning 修完 |
| `7ee11cb` | 2026-04-20 12:34 | 2 | **HANDOFF.md 重写为 2026-04-20 版** |
| `6508535` | 2026-04-20 13:51 | 4 | Phase 10c infra: rescore filtering + scholarly orch |
| `8753e82` | 2026-04-20 18:33 | 41 | **Phase 10c #65**: 14×8=80 scholarly runs + paper 重生 |
| `4e9724c` | 2026-04-20 20:06 | 6 | Phase 10d: react bias + ablation + source_diversity pillar |
| `92e52fd` | 2026-04-20 20:10 | 4 | shim 加 `/post_lookup` + `/product_lookup`,paper 更新 |

---

## 8. session 对照索引

| Session | 时间 | deep_reserch 角色 | 关键词 |
|---|---|---|---|
| `73c10be4` | 2026-03-31 07:10 → 18:02 | 前置(ScholarMind)| 9 步 agent,agent_keyan |
| `51ec92ce` | 2026-04-11 02:09 → 09:06 | 调研 Phase 1 | plan mode,DR 范式,fake-IP 首次 |
| `7b358cd8` | 2026-04-15 00:17 → 13:35 | 基建 Phase 2 | SSH,梯子,claude.md,67GB 下载 |
| `43e7d20f` | 2026-04-15 16:02 → 04-16 11:26 | v3 Phase 1-6 + 飞书 | PLAN.md,v3 schema,fact_kg,跨站 |
| `f8d8a97e` | 2026-04-17 13:17 → 13:24 | 过渡(8 turns)| 读 HANDOFF,被打断 |
| `45ffd795` | 2026-04-17 13:17 → 04-20 04:31 | **Phase 7-10b 主力 session** | shim,14 agent,DeepSeek,IRT,latex |
| `e7050cf7` | 2026-04-17 13:25 → 04-19 03:36 | 并行 agent_benchmark public | bug_exam,secret scanning |
| `a294c9c0` | 2026-04-20 17:11 → 当前 | **本篇时间线 session** | PROJECT_TIMELINE |

---

## 9. 参考文档优先级

1. `HANDOFF.md`(2026-04-20)— 全景
2. `PROJECT_TIMELINE.md`(本篇)— 每一步细节
3. `PLAN.md` — Phase 1-10 历史详细日志
4. `latex/findings.tex` — 4 个 paper 发现
5. `~/.claude/plans/iterative-doodling-parrot.md` — 下次执行推荐
6. `METHODOLOGY_AUDIT_2026-04-19.md` / `PAPER_POSITIONING.md` / `PAPER_FINDINGS.md`
7. `FRAMEWORK_INVENTORY.md` / `FRAMEWORK_INSTALL_STATUS.md` / `CORPUS_DOWNLOAD_STATUS.md`
