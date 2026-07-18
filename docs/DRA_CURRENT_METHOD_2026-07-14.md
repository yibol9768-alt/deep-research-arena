# Deep Research Arena 当前做法：方法、执行、打分、审计与最新状态

版本日期：2026-07-15  
状态口径：以当前代码树、远端权威箱运行产物和正式 formula stamp 为准  
适用仓库：`/root/Desktop/lyb/deep_reserch`  
当前分支：`fix/pof-citation-extractor`

## 0. 这份文档解决什么问题

这是一份面向研究、复现、工程执行和审计的现行版说明。它描述的不是早期 DRA，也不是旧 README 中仍残留的历史口径，而是 2026-07-15 当前代码实际实现的方法。

最重要的更新只有一句话：

> 正式 `transport_v2` 榜单的头条分使用 `provenance` 线性门控。`reach` 仍然计算和展示，但在正式可观测运行中只是诊断列，不再是头条 truth 的门。

当前正式公式为：

```text
quality = 0.39 * fact + 0.28 * proof_of_fetch + 0.33 * completeness
truth   = provenance * quality
```

其中 `provenance` 表示：报告引用的 URL 中，有多少能够由本次运行的可观测检索、抓取或已抓取页面上的链接解释，而不是仅仅“这个 URL 碰巧存在”。

只有历史 `text_v1` 运行因为没有传输证据，才保留旧式：

```text
truth_legacy = reach * quality
```

两种语义必须由 `gate_semantics` 和 `pof_semantics` 明确盖章，禁止混在同一张榜中比较。

## 1. 权威来源与版本判定

### 1.1 当前代码身份

2026-07-14 核验结果：

| 位置 | commit | Git tree |
|---|---|---|
| 本地工作区 | `51d0268822a37ff721bafcd126fb175605a78cae` | `05f0d292838d05a7fa0a5b2859334253e0758eca` |
| `my5090` 权威箱 | `be5eb3f9b516c52f52063afdcb492f893efac07f` | `05f0d292838d05a7fa0a5b2859334253e0758eca` |

两个 commit hash 不同，是同步方式导致提交对象被重写；两端 tree hash 完全相同，因此代码内容一致。

### 1.2 方法口径的优先级

发生冲突时，按以下优先级判断：

1. 当前执行代码与测试。
2. 正式榜单 JSON 中的 `protocols`、`formula_version`、`pof_semantics`、`gate_semantics`。
3. `docs/SPEC_DECISIONS.md` 的已裁决语义。
4. `config/lane_protocol.yaml` 的车道协议与差异披露。
5. 本文档。
6. `README.md`、旧交接、旧复现手册和历史论文稿。

当前正式 formula stamp 是：

```text
formula_version = tv2.5-linear-provenance-gate-factscope-forum-attribution
extractor_commit = 46e716e3+63d220b3+answer_keys_b636b149
formula_commit   = linear_gamma1+factscope_forum_attribution_locality
gamma            = 1.0
eps_floor        = 0.0
```

任何两个榜单，只要 formula、extractor、task set、PoF 语义或 gate 语义不同，就不能直接比较数字和名次。

### 1.3 明确废弃的旧说法

以下说法不再是当前正式方法：

- `Elo * (reach% + quote%) / 200`：已退休。
- `truth = reach^1.5 * quality`：过时。当前 transport 运行使用 `provenance * quality`，历史 `text_v1` 重新计分时使用 `reach * quality`。
- 把 evaluator 事后抓取页面并做文本匹配叫作 Proof of Fetch：过时。那只能叫 `quote_support`。
- 认为引用一个真实 URL 就足以通过真实性门：过时。正式门要求本次运行能够解释该 URL 从哪里获得。
- 把论坛描述成与商城、Wikipedia 对称的完整计分源：不准确。论坛目前主要是 provenance 维度，并只有一个虚拟 completeness 槽位。
- 把 2026-07-13 交接中的“没有产生新报告”当作当前状态：过时。2026-07-14 已产生 12 份汇集报告，但尚未形成一轮完整通过的正式 12 车道 smoke。

## 2. 我们到底在评测什么

DRA 评测的是：不同 Deep Research 框架在相同任务、相同底模、相同封闭语料和受控工具面下，能否产出有证据、可核验、覆盖充分且对读者有用的研究报告。

我们把两个构念分开：

1. `truth`：由封闭世界、运行证据和答案键确定性计算，不依赖 LLM judge。
2. `presentation/usefulness`：由独立 LLM jury 做两两比较，再拟合 Bradley-Terry 分数。

这两个分数回答不同问题：

| 分数 | 回答的问题 | 是否进入头条 truth |
|---|---|---:|
| provenance | 引用能否由本次运行的检索、抓取或页面链接解释 | 是，作为乘法门 |
| reach | 引用 URL 是否属于冻结语料 | 否，正式 transport 榜只作诊断 |
| proof_of_fetch | agent 是否真的打开过它引用的页面 | 是，作为 quality 一项 |
| fact | 明确写出的结构化事实是否正确且与任务相关 | 是 |
| completeness | 是否覆盖答案键的全部 vital 内容 | 是 |
| compliance/spec | 是否满足可判定的输出格式要求 | 否，单列 |
| usefulness | 报告作为交付物是否好读、好用 | 否，只允许在近似 truth 平局时破同分 |

我们的核心原则是：一个低分必须能归因到框架自己的行为，而不是仪器失明。

因此：

- 观察到没做，才记 0。
- 仪器无法观察，必须 `withhold`，不能假装 0。
- 基础设施失败与框架失败分开记录。
- 缺失报告不能从平均分里消失，正式榜按 0 补齐。

## 3. 整体系统

```text
任务 intent + 共享输出要求
            |
            v
12/16 个框架车道中的一个
            |
            | 仅允许通过受控服务门
            v
每 worker 独立 search shim + LLM proxy + root-owned egress recorder
            |
            +--> 冻结 Magento 商城
            +--> 冻结 Postmill 论坛
            +--> 离线 Kiwix Wikipedia
            +--> CLIProxyAPI / 指定底模
            |
            v
原始 Markdown 报告 + meta + fetch evidence + usage ledger
            |
            v
离线、无网络打分
            |
            +--> provenance / reach / PoF / fact / completeness / compliance
            +--> 可选 usefulness jury
            |
            v
带 manifest、run plan、formula stamp、置信区间和披露信息的榜单
```

## 4. 冻结沙盒与数据源

### 4.1 三个语料源

| 源 | 正式公共身份 | 内容 | 用途 |
|---|---|---|---|
| Shopping | `http://localhost:7770` | 冻结 Magento 商品、价格、评分、评论 | 商品检索、结构化事实、购买建议 |
| Forum | `http://localhost:9999` | 冻结 Postmill 论坛主题和评论 | 社区观点、引用 provenance、虚拟论坛槽 |
| Wikipedia | `http://localhost:8090` | 离线 Kiwix Wikipedia | 概念、原理、背景知识 |

正式评测不允许访问实时互联网。这样做的价值是：

- URL 是否存在可以判定。
- 页面内容固定，可以重复评分。
- 报告引用是否来自本次运行可以从传输日志判定。
- evaluator 不需要用自己的联网请求替 agent 补证据。

### 4.2 传输地址与公共身份分离

服务在宿主机上可以通过 `127.0.0.1` 传输，但生成给模型和 registry 识别的 URL 使用 `localhost` 公共身份。例如 Magento 若收到错误 Host，可能 302 到错误地址并丢失查询参数。

因此现行 smoke 显式区分：

```text
SHOPPING        = http://127.0.0.1:7770
SHOPPING_PUBLIC = http://localhost:7770
```

论坛和 Wikipedia 同理。不能通过给 URL registry 随意增加新端口来“修复”源不一致，因为那会改变冻结语料的身份定义。

### 4.3 当前论坛的真实地位

当前答案键中：

- 商城提供结构化商品事实和大量 vital nuggets。
- Wikipedia 提供 concept coverage。
- 论坛还没有像商城那样批量构建 `thread_score`、`comment_count` 等真实 vital nuggets。
- 每个声明论坛来源的任务增加一个虚拟论坛 completeness 槽。

这个虚拟槽只有在报告满足以下条件时覆盖：

1. 引用了允许论坛中的真实内容页。
2. 引用与当前任务词面相关。
3. 引用出现在正文，不是脱离上下文的链接倾倒。
4. 正文对页面内容有 quote support。
5. `transport_v2` 下该页面还必须在本次运行中被抓取。

所以当前 DRA 不能宣传为三个来源完全对称计分。更准确的表述是：商城和 Wikipedia 构成主要内容计分源，论坛是 provenance 和有限社区覆盖维度。

## 5. 任务与答案键

### 5.1 当前规模

当前代码树中：

| 对象 | 数量 |
|---|---:|
| `cross_site_deep` 正式任务 | 100 |
| v2 adversarial 任务文件 | 22 |
| `data/golden/answer_keys` v2 答案键 | 100 |
| 每题 vital nuggets | 14 到 17，均值 14.78 |
| 每题 useful nuggets | 20 |
| 声明论坛的任务 | 100 |

旧 `deep_clean/_manifest.json` 中的 `canonical_scorable=75` 属于早期 golden 清洗管线。当前 100 题 gate 和正式打分读的是 `data/golden/answer_keys/<task_id>.json`。二者不能混为同一个 eval set 口径。

### 5.2 v2 任务中的遗留字段

当前任务 JSON 仍保留一些 v1 字段，例如旧 `golden.triples_path`、旧 `synthesis_requirements`、旧主题说明。对于已升级到 `task_version: 2` 的任务，这些字段可能和当前 `intent` 不一致。

现行规则：

> v2 打分只以 `data/golden/answer_keys/<task_id>.json` 为权威答案键。不得用任务 JSON 内标有 legacy/deprecated 的旧 golden 或旧 synthesis 字段打分。

这点非常重要。例如 `dr_cross_deep_0010` 的当前 intent 是“戴眼镜长途飞行时选择降噪耳机”，但文件里仍保留机械键盘历史的 v1 synthesis 元数据。现行系统必须忽略后者。

### 5.3 答案键结构

每份 v2 答案键主要包含：

- `relevant_set`：可识别的商城实体及 DB 事实。
- `vital_nuggets`：必须覆盖的核心内容。
- `useful_nuggets`：用于定义任务相关结构化事实范围。
- `gold_contradictions`：可判定矛盾。
- `decidable_verdicts`：可机械核验的结论槽。
- `spec_requirements`：输出形态要求。
- `metadata`：主题、论坛、Wikipedia 概念、inline citation 要求等。

当前 100 题 vital 谓词构成为：

- `buyer_sentiment`：1200 条。
- `concept_coverage`：278 条。

每题还会按 metadata 增加一个虚拟论坛槽。

### 5.4 为什么不是直接把任务里的 60 引用、120 页等要求告诉模型

任务 JSON 中仍可能保存高引用数、长篇幅和多页浏览的设计目标，但公平 prompt 不把这些 scorer-shaped 指标直接喂给任何车道。

原因是：如果告诉某个框架“至少引用 60 个 URL”或“必须浏览 120 页”，就直接针对 reach、PoF、completeness 进行提示优化，框架比较会变成 harness prompt 比较。

模型真正收到的共享内容只有：

1. 当前任务的 `intent`。
2. 一句共享输出要求：

```text
Deliver your answer as a single self-contained markdown report. Return the
report only, with no planning notes or tool transcripts.
```

## 6. 车道、框架与公平性

### 6.1 当前 maintained 12 车道

GPT-5.6 Luna smoke matrix 当前维护以下 12 个框架：

1. `camel-ai`
2. `claude-code`
3. `deerflow`
4. `flowsearcher-ds`
5. `gpt-researcher`
6. `ii-researcher`
7. `langchain-odr`
8. `ldr`
9. `opencode`
10. `qx-agents`
11. `smolagents`
12. `storm`

`config/lane_protocol.yaml` 共声明 17 条车道。除上述 12 条外，还有：

- `co-storm`
- `deepagents`
- `local-deep-researcher`
- `tongyi-dr`
- `codex`

其中 `codex` 标记为 `runnable: false`，原因是它通过远程 SSH 执行，而当前强制 netns 隔离既没有放行 SSH，也没有完整 remote isolation proof 写端。它必须作为 `excluded_lane` 发布，不能解释为“运行后得分低”。

### 6.2 当前 full planner 的一个操作陷阱

`scripts/plan_full_leaderboard.py` 的默认 agent 集来自全部 protocol-declared lanes，目前不会自动过滤 `runnable: false`。因此正式计划不能盲用默认值，必须显式传入获准的 agent 列表。

对当前 GPT-5.6 Luna 比较，应显式传 maintained 12 车道，除非已经单独完成另外 4 条可跑车道的环境、依赖和隔离验证。

### 6.3 公平协议

所有车道必须遵守：

- 同一任务 intent。
- 同一共享输出句。
- 同一底模。
- 同一 sampling policy。
- 同一可见输出 token ceiling。
- 同一冻结数据源。
- 同一隔离边界。
- 同一报告捕获、seal、证据和打分流程。

prompt 中禁止：

- 引用数量。
- 单词、字符或段落数量。
- 搜索次数。
- “多发几个 query”之类的搜索广度处方。
- “抓取所有结果”之类的策略处方。
- 引用格式示例。
- 评分 rubric 枚举。
- 示例 URL。

harness 中禁止：

- 给报告追加 URL 或 sources block。
- 把模型写出的外部 URL 改写成沙盒 URL。
- 根据 reach、PoF、completeness 等分数触发重试或修复。
- 以“报告里沙盒 URL 太少”为由拒绝保存。
- 用旧运行记忆、golden URL 或答案键内容给某条车道开小灶。

### 6.4 能力公平不等于 prompt 字符串完全相同

原生 agent 可以接收搜索工具对象；CLI agent 没有该工具，只能接收如何调用受控 shim 的最小操作说明。这种 delivery 差异是必要的。

真正要求一致的是任务目标和能力边界，而不是 prompt 每个字符相同。所有不可避免差异都必须写入 `lane_protocol.yaml` 的 `deviations`，并在榜单中披露。

### 6.5 当前 sampling 和预算

共享默认：

```text
temperature      = 0.2
top_p            = 1.0
max_output_tokens = 8192
```

代理层会为未提供 `max_tokens` 的请求显式补上 ceiling，并把超过 ceiling 的请求夹紧。对于 `gpt-5.6-luna`，当前走共享 8192 上限。

预算单位是各底模自己的 tokenizer token，不是字数或字符数。因此跨底模比较中，同样 8192 token 可能对应不同长度的英文报告。

历史 backbone 仍有 thinking 和 GLM 例外：

- qwen thinking on。
- GLM thinking on，且历史例外为 131072。
- deepseek thinking off。

所以跨底模对比不是严格单变量实验。当前 GPT-5.6 Luna 的 12 车道同底模比较，比混合 qwen、GLM、deepseek 的跨底模解释更可靠。

### 6.6 两层安全预算必须区分

正式比较预算和 smoke 防失控 fuse 不是同一件事。

正式比较层：

- 每次请求可见输出 ceiling 默认 8192 token。
- 没有比较用的总 wall clock。
- 15 分钟无 LLM 调用、无 shim 调用才判定 `stalled`。

当前 12 车道 smoke 的安全 fuse：

- 每车道默认最多 256 次 LLM 调用。
- 每车道默认最多 750,000 aggregate tokens。
- 多 worker 对同一 CLIProxyAPI 上游默认只开放 2 个并发 admission slots。
- 可用 `--harness-max-calls HARNESS=N` 对单车道调整 call fuse。
- 可用 `--unlimited-token-harness HARNESS` 只解除指定车道 aggregate token fuse。

任何 per-harness 例外都必须作为修复运行的显式条件记录，不能把它静默混入标准比较。

## 7. 模型接入与账号代理

### 7.1 当前路径

当前 GPT-5.6 Luna 正式接入路径为：

```text
framework
  -> worker-local ds_proxy
  -> my5090 WSL localhost:8317 CLIProxyAPI
  -> gpt-5.6-luna
```

Arena 不经过 Hermes。把 Hermes agent 套在 DRA harness 上游会形成 harness 套 harness，污染工具循环、上下文、token、重试和评测语义。

### 7.2 CLIProxyAPI

当前服务：

- systemd：`cliproxyapi-dra.service`
- endpoint：`http://127.0.0.1:8317/v1`
- 仅绑定本机。
- Management API 和控制面板关闭。
- 多凭证、round-robin、session affinity、cooldown 和失败换号由 CLIProxyAPI 管理。

manifest 只记录：

- CLIProxyAPI 版本。
- binary SHA-256。
- 运行时配置 SHA-256。
- 凭证数量。
- 凭证池匿名聚合 SHA-256。

不得记录 token、邮箱、session 内容或密钥正文。

### 7.3 session affinity 和身份探针

每个正式 run 使用稳定 `run_id` 作为会话亲和依据。模型身份探针要求返回的 model 字段严格等于声明模型，例如：

```text
declared = gpt-5.6-luna
actual   = gpt-5.6-luna
ok       = true
```

该探针只能证明端点自报身份一致，不能从密码学上证明具体权重。榜单必须保留：

```text
identity_scope = endpoint-self-reported
```

### 7.4 额度解释

代理加载多份认证文件不等于拥有同倍数的独立额度。除非通过独立 reset 时间、额度变化和 workspace identity 证明，否则不能宣称 N 份凭证等于 N 倍容量。

## 8. 强制网络隔离

2026-07-09 的旧运行文档仍把“sandbox origins 直接可达”列为未解决问题。当前代码已经实现网络级生产隔离，因此那一节已过时。

### 8.1 每个 worker 的边界

`run_full_leaderboard.sh` 在任何 lane 启动前执行：

1. 创建独立 Linux network namespace。
2. 给 worker 分配独立非 root UID。
3. 移除默认路由。
4. 安装 nftables 规则，只允许访问 root-owned recording door 和明确的宿主服务端口。
5. 以只读方式暴露安全仓库视图和依赖环境。
6. 隐藏答案键、URL registry 等评分私有材料。
7. 给 worker 创建私有 `/dev/shm`，兼容 multiprocessing，同时避免共享内存越界。
8. 启动 worker-owned egress recorder。
9. 用与真实 lane 相同 UID、capability、netns 跑 live probe。

### 8.2 live probe 必须证明什么

正式 worker 启动前必须证明：

- 通过 recorder 能访问沙盒语料。
- `curl --noproxy '*'` 不能直连语料。
- `requests` 的 `trust_env=False` 不能绕过 recorder。
- raw socket 不能绕过。
- localhost、127.0.0.1、宿主别名、容器别名不能绕过。
- 公网 HTTP、HTTPS 和 DNS 不能访问。
- worker 不能修改 evidence 文件。
- root-owned proof 文件和 namespace 状态一致。

只要任一项失败，正式 run 直接拒绝，退出码进入 infrastructure 类，不允许降级为“尽量跑”。

### 8.3 为什么需要 egress recorder

仅在 Python 里 monkey-patch `requests` 不够，因为框架可能使用：

- `aiohttp`
- `httpx`
- shell `curl`
- 子进程浏览器
- 自己的 socket 客户端

网络级隔离把所有这些路径统一收口。任何页面读取要么通过记录门并留下证据，要么失败。

### 8.4 私有材料边界

可信 supervisor 可以使用 URL registry 和答案键做 source preflight，但这些文件不能进入 lane chroot。worker 只收到：

- 任务 intent。
- 允许的搜索、抓取、模型服务。
- 自己的运行目录和输出路径。

这避免框架直接读取 golden 或枚举答案 URL。

## 9. 每次运行的证据闭环

### 9.1 run_id 和 bracket

每次 `(agent, task, backbone, replicate)` 生成唯一 `run_id`。运行开始时，shim、egress recorder 和模型 proxy 打开 `/_mark` bracket；运行结束时在 `finally` 中关闭。

一个 recorder 同时只能有一个 open run。并发时必须每 worker 一个 shim、一个模型 usage stream、一个 evidence root，避免归因串线。

### 9.2 每个 cell 的正式产物

| 产物 | 作用 |
|---|---|
| `raw/<agent>__<task>_repN.md` | 框架原始报告字节 |
| 同名 `.meta.json` | status、run_id、时间、模型身份、source check、网络 proof、report seal |
| `evidence/worker-N/<run_id>.jsonl` | shim 搜索和抓取证据 |
| `evidence/egress-worker-N/<run_id>.jsonl` | 网络门捕获的语料访问 |
| evidence blobs | agent 实际看到的页面字节 |
| usage JSONL | 每次 LLM 调用、token、归因状态 |
| `api_costs.worker-N.json` | 每 worker 汇总成本台账 |
| `scores/*.score.json` | 确定性单报告打分 |
| `isolation/proofs/*.json` | 网络隔离证明 |

### 9.3 报告 seal

报告保存后计算 SHA-256，并写入 meta。打分前再次核验。

如果后处理追加 sources、修改 URL、润色正文或改变一个字节，seal 失配，cell 标记为 tampered/integrity failure，不能进入正式榜。

### 9.4 断点续跑

当前支持两种安全 resume：

1. report、meta、score 全部存在且 manifest、proof、seal、agent/task/backbone/replicate 绑定全通过：整个 cell 跳过。
2. report 和 meta 已完整绑定，但 scoring 被中断：只恢复 scoring，不重新调用模型。

裸 score、裸 report、来自另一 model、另一 commit、另一 run set 的文件都不能命中缓存。

### 9.5 取消和迟到用量

当前实现把 worker 取消信号传播到 egress/model proxy；已断开的请求会在 admission 前丢弃。proxy heartbeat 可让 stall watchdog 区分“模型仍在处理”和“完全没有进展”。迟到的 usage 会尽量归入原 run_id，而不是静默落到下一 run。

## 10. 正式打分

### 10.1 先提取引用

评分器从 Markdown 中提取可支持的引用形式，包括正文 Markdown 链接和声明支持的其他 citation style。导航页、reference-only 区域、正文内联引用的作用不同：

- 真实内容 URL 进入 reach/provenance 分母。
- search/navigation URL 不应当作为事实页面参与同样分母。
- 脱离正文的链接列表不能解锁 fact 或 structured completeness。
- URL slug 中出现的实体名和数字不能冒充正文事实。

### 10.2 Reach

```text
reach = in_corpus_cited_content_urls / cited_content_urls
```

它回答“这个 URL 是否属于冻结语料”。

正式 `transport_v2` 中，reach 只作诊断，因为模型可能从参数记忆猜中一个真实 URL。猜中不等于本次研究过程获得了它。

### 10.3 Provenance

provenance 检查每个引用能否被本次运行解释。可获得 provenance credit 的路径包括：

- 本次搜索结果中出现过该 URL。
- 本次实际抓取过该 URL。
- 该 URL 出现在本次已抓取页面的链接中。

以下不获得 credit：

- 仅因为 URL 在 registry 中真实存在。
- 从未搜索、抓取，也不在已读页面链接中的真实 URL。
- 沙盒外 URL。
- 不存在的 URL。

因此：

```text
provenance <= reach
```

若某报告大量“猜中”真实沙盒 URL，可能 `reach` 很高而 `provenance` 很低。正式 truth 使用后者作为门，防止参数记忆洗白。

榜单同时展示：

- `reach_frac`
- `provenance_frac`
- `guessed_frac`

### 10.4 Proof of Fetch

正式定义：

```text
proof_of_fetch = |cited pages intersect fetched pages| / |cited pages|
```

证据只能来自本次 run 的 transport log。它回答“引用的页面是否真的打开过”。

特别分类：

- `snippet_only`：搜索见过 URL 和 snippet，但未打开页面。
- `linked`：从已抓取页面上的链接获得。
- `guessed`：本次搜索、抓取、页面链接都无法解释。
- `fabricated`：URL 不属于冻结语料。

如果 evidence log 缺失、损坏或 bracket 不完整：

- 正式模式 `withhold` 或拒绝整个 lane/cell。
- 绝不能记 `PoF=0`。
- 绝不能让 evaluator 自己联网补抓。

### 10.5 Quote support

`quote_support` 是报告文本与 evaluator 持有页面副本的词面匹配。它能作为“读后写作是否贴近页面”的下界，但不能证明 agent 打开过页面。

当前阈值：

```text
POF_THRESHOLD_DEFAULT = 0.35
```

在 transport 榜中，proof_of_fetch 和 quote_support 是两个不同诊断问题。旧 `text_v1` 只能计算 quote support，并会把轴名明确改为 `grounding_quote_support`。

### 10.6 Fact support

fact 只检查报告明确写出的、可绑定到商城 DB 实体的价格和 overall rating 声明。它不是通用自然语言正确性评分。

核心步骤：

1. 从可见正文识别商品实体。
2. 提取带价格 cue 的数字或明确 overall rating。
3. 在同一句内，以不超过正负 40 字符的窗口把数值绑定到唯一实体。
4. 对照该实体自己的 DB truth，不允许相似变体共享事实。
5. 检查同句 inline citation 是否指向该商品。
6. 只让 task-ranked 商品事实进入 recall volume。

当前计算：

```text
precision  = supported / tested
recall_vol = min(distinct_task_scoped_supported / 10, 1)
fact       = harmonic_mean(precision, recall_vol)
```

规则细节：

- 没有可检查声明时，fact 为 0，原因 `no_checkable_claims`。
- 正确但任务范围外的事实移出 tested，不得用来稀释低 precision。
- 范围外错误仍算 contradiction。
- 同一事实换不同数字写法重复，不得重复填满 volume。
- `special_price` 可作为允许的正确价格。
- 产品名内部的年份、型号、尺寸、包数不能被误认作 claim value。
- “5 stars for build quality”不能当 overall product rating。
- 正确数字但没有同句商品 citation，可以进入诊断，但不能买 recall volume。

### 10.7 Completeness

当前 completeness 不是“覆盖任意 20 条即可饱和”。虽然保留 `K*=20`，但每题 vital pool 只有 14 到 17 条，低于 20，因此实际语义是普查：覆盖全部 vital 内容才满分。

```text
completeness = covered / k_effective
k_effective  = min(20, coverable vital pool + forum slot)
```

100 题的基础 vital pool 为 14 到 17 条；每题还声明一个虚拟论坛槽，因此未发生排除/withhold 时，实际 denominator 通常是 15 到 18。

structured nugget 只有同时满足下列要求才算覆盖：

- 正文讨论了该 subject。
- typed value 在 subject 附近正负 40 字符内。
- 该 nugget 的 source citation 与 subject/value 位于同一 Markdown 行。
- `transport_v2` 下该 source page 已抓取。

concept nugget 还要求页面文字能够支持正文表述。

如果某 concept page 本身只是无法接地的 stub，任何报告都不可能覆盖，则该槽从分母排除，并在 `excluded_slots` 明示。

正式模式没有 page cache 时直接拒绝构榜。只有显式 `--diagnostic` 才允许运行，并把仪器无法判断的 concept/forum 槽从分母 withhold，且给出原因。

声明 `fetch_mode:none` 的 snippet-only 架构可按已裁决语义豁免 completeness 的 fetch 要求，因为这些框架本身没有 page-read 工具。该豁免必须出现在 lane disclosure 中，不能伪装成与 fetch-capable lane 完全相同。

### 10.8 Compliance/spec

spec 由答案键中的可判定要求构成，例如：

- 最低字数。
- 是否有 actionable shortlist / recommendation section。
- 是否出现特定结构。
- 全文 bullet 上限。

spec 只作为：

```text
compliance = spec
```

单独展示。它不进入 quality 或 truth。原因是格式完整的空壳不能因为结构漂亮而获得真实性分。

### 10.9 Truth composition

正式 transport 运行：

```text
quality = 0.39 * fact + 0.28 * proof_of_fetch + 0.33 * completeness
truth   = provenance * quality
```

设计性质：

- provenance 为 0，则 truth 为 0。
- quality 三轴全为 0，则 truth 为 0。
- 没有 epsilon floor，`EPS_FLOOR=0.0`。
- 只擦到每个轴一点点的 mini-shell 只能得到实际的小分，不会被抬到 0.05 平台。
- 权重是声明的 harm ordering，经归一化后得到 0.39/0.28/0.33，不是从评测榜拟合出来的最优参数。
- gamma=1.0，头条分就是 provenance 与 quality 的直接乘积，含义和边际惩罚都可直接解释。
- 1.25、1.5、2.0 只作为敏感性分析披露；旧 fabrication 注入实验只能说明指数越大惩罚越强，不能唯一识别 1.5。

### 10.10 Zero 与 Withhold

0 的含义必须是“观测到且确实没有做到”。每个 0 都必须有 machine-readable reason code，例如：

- `no_citations`
- `all_citations_off_corpus`
- `no_page_fetched`
- `no_checkable_claims`
- `no_supported_claims`
- `no_vital_covered`
- `no_spec_requirement_passed`

仪器盲区必须走 withhold，例如：

- `no_evidence_log`
- `fetch_not_observable`
- `concept_page_not_cached`
- `forum_thread_not_cached`
- bracket 或 evidence 损坏

正式系统不允许把 withhold 显示成 0。

## 11. 榜单聚合

### 11.1 正式输入

正式 board 读取 governed run directory：

```text
<results_root>/<run_set_id>/<backbone>/
```

它要求：

- immutable `run_plan.json`
- `run_manifest*.json`
- flat `raw/*.md` 和 `raw/*.meta.json`
- `scores/*.score.json`
- `evidence/` 下完整 recorder logs
- sandbox page cache
- report seals
- source check 成功
- model identity 成功
- production-comparable timeout contract

### 11.2 缺失和失败

正式榜默认 `missing_as_zero=true`：

- pass report：用实际 truth。
- missing：0。
- timeout：0，除非仍在允许的 infrastructure rerun 欠账期。
- infra_abort：不能静默消失，按正式状态规则处理。
- stalled：先要求 rerun；rerun 未还清时拒绝构榜。
- tampered：拒绝或记 integrity failure，不能使用被改过的报告。

这样避免某个框架只完成容易题，却只在幸存题上求平均。

### 11.3 Macro、micro 和置信区间

头条排名使用：

```text
truth_macro = 所有计划 task x replicate cell 的平均 truth
```

同时发布：

- `truth_macro_ci95`
- `truth_micro`
- `min_report_truth`
- `min_report_truth_surviving`
- coverage
- pass/fail/stalled/timeout/missing rates
- reach/provenance/guessed 三列
- fact precision 和 fact active rate
- compliance
- deviations/exclusions

95% 区间按 task 做 cluster bootstrap，replicates 保留在 task 内，不能把同一题的多个 replicate 当作独立题目扩大样本量。

### 11.4 低 coverage

低于 `--min-coverage` 的 lane 仍可显示，但标记 `low_coverage=true`，不得用于 headline claim。

### 11.5 usefulness jury

presentation 由 pairwise LLM judge 产生，再拟合 Bradley-Terry。现行规则：

- jury 不负责验证 citation truth。
- infrastructure timeout/watchdog/harness 错误的 stub 不进入 BT，记为待补运行。
- 健康运行下真实空交付可记败。
- presentation 不乘进 truth。
- 只允许在 `tie_eps=0.005` 的 truth 近似平局组内破同分。

当前 jury 仍缺少人类偏好 anchor。juror 间 kappa 不等于它与人类 usefulness 一致，因此不能用 jury 推翻 decidable truth。

## 12. Gates 与正式开跑条件

### 12.1 七道 gate

| Gate | 目的 | 现行含义 |
|---|---|---|
| G0 | 协议对等与差异披露 | runner、protocol、prompt、预算、特殊适配必须一致或已披露 |
| G1 | Oracle 顶格 | 机械 oracle 应达到可达上限 |
| G2 | 空壳归零 | 无证据、无内容的 shell 各轴为 0 |
| G3 | 扰动必降 | 改错数字、删引用、换 URL 必须让对应轴下降 |
| G4 | withhold 不打 0 | 仪器失明必须 unavailable + reason |
| G5 | 箱上 preflight | 三源、registry、真实 transport 在生产箱通过 |
| G6 | 无静默零 | 每个 0 或不可评分都有机器原因 |

### 12.2 生产 preflight

正式入口必须 fail closed。至少检查：

- goal gates 可收集且通过。
- lane parity。
- deviation disclosure 完整。
- backbone sampling 与声明一致。
- 三源 canned query 有结果。
- search hits 全部能被 URL registry 分类为 in-corpus。
- egress 能捕获不同 HTTP transport。
- scorer 不会联网 refetch。
- evidence bracket 能自愈且不串 run。
- fetched page 上的链接不会被误判为 guessed。
- worker live isolation proof 通过。
- manifest 在执行主机生成且与当前树、环境一致。

任何 required production check 为 skip，也应视为不满足正式开跑条件。

### 12.3 分阶段扩大

当前安全顺序：

1. 不调用模型的 gates。
2. production source/isolation preflight。
3. `1 harness x 1 task`。
4. 检查报告、meta、evidence、identity、usage、session affinity、账号选择和成本归因。
5. maintained `12 harness x 1 task` smoke。
6. 只有整轮 smoke 完整通过后，才考虑 13-task mini。
7. mini 完整通过后，才申请 12 harness x 100 task x replicates 的正式批准。

不得因为桌面上已经收集到 12 份报告，就跳过第 5 步的“一轮统一、完整、可审计通过”。

## 13. 推荐的正式运行流程

以下是现行方法的操作顺序。命令中的 ID 和路径应按实际运行替换。

### 13.1 只读确认服务

```bash
systemctl is-active cliproxyapi-dra.service
curl --noproxy '*' -fsS http://127.0.0.1:8317/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

不要把密钥写进命令历史、日志、manifest 或文档。应从 root-only env 文件读取。

### 13.2 跑确定性 gate

```bash
python3 scripts/run_gates.py --quick
python3 scripts/check_parity.py
python3 scripts/check_disclosure.py
```

正式全量前再跑完整 gate：

```bash
python3 scripts/run_gates.py
```

### 13.3 生成显式 queue

当前不要依赖 planner 默认 agent 集。显式写 maintained 12 车道：

```bash
python3 scripts/plan_full_leaderboard.py \
  --agents camel-ai claude-code deerflow flowsearcher-ds gpt-researcher \
           ii-researcher langchain-odr ldr opencode qx-agents smolagents storm \
  --task-range all \
  --backbone gpt-5.6-luna \
  --replicates 1 \
  --out data/results/run_queue_gpt56_luna.tsv
```

### 13.4 预注册 manifest 与 immutable run plan

正式 board 强制要求 immutable `run_plan.json`。当前 `run_full_leaderboard.sh` 会创建或验证 manifest，但不会自动创建 run plan。因此正式全量不能只生成 queue 就直接忘记 plan。

正确原则是：

1. 确定 `RUN_SET_ID`、backbone、queue 和 replicates。
2. 在执行主机生成 manifest。
3. 用 manifest 和完整 agents x tasks queue 原子创建 `run_plan.json`。
4. 此后只能验证，不能覆盖。

run plan 创建接口：

```bash
python3 scripts/verify_run_set.py run-plan \
  --plan <run-dir>/run_plan.json \
  --manifest <run-dir>/run_manifest.json \
  --run-set-id <run-set-id> \
  --backbone gpt-5.6-luna \
  --replicates 1 \
  --queue data/results/run_queue_gpt56_luna.tsv \
  --create
```

如果 plan 已存在，`--create` 必须拒绝覆盖。resume 时只做 validate。

### 13.5 运行单条或 smoke matrix

单条开发诊断：

```bash
python3 scripts/run_deep_task.py \
  --agent smolagents \
  --task dr_cross_deep_0010 \
  --backbone gpt-5.6-luna
```

这条命令本身不等于正式生产运行。正式 smoke 使用：

```bash
python3 scripts/run_harness_smoke_matrix.py \
  --model gpt-5.6-luna \
  --task dr_cross_deep_0010 \
  --api-base http://127.0.0.1:8317/v1 \
  --client-env /etc/cliproxyapi/client.env
```

它会为 12 个 harness 各自创建：

- 独立 run set。
- 独立 worker ID。
- 独立 search shim。
- 独立 ds_proxy。
- 独立 netns 和 egress recorder。
- 独立 evidence 与 usage ledger。

只有上游 admission pool 共享，用来避免 12 个框架同时打爆同一账号池。

### 13.6 正式 queue

在 manifest、plan、服务、source preflight 和用户批准均满足后：

```bash
export BACKBONE=gpt-5.6-luna
export RUN_SET_ID=<immutable-run-set-id>
export REPLICATES=1
export DS_PROXY_URL=http://127.0.0.1:<worker-dsproxy-port>/v1
export OPENAI_BASE_URL="$DS_PROXY_URL"
export JUDGE_BASE_URL="$DS_PROXY_URL"
export JUDGE_MODEL=gpt-5.6-luna

bash scripts/run_full_leaderboard.sh data/results/run_queue_gpt56_luna.tsv
```

不要把 `RUN_TIMEOUT` 设置成比较预算。默认 0 表示无 comparative wall clock。任何非零 operator override 都必须进入 manifest，且该 run 不应冒充标准协议结果。

### 13.7 构建正式 board

```bash
python3 scripts/build_truth_board.py \
  --run-dir <results-root>/<run-set-id>/gpt-5.6-luna \
  --replicates 1 \
  --cache <sandbox_cache.json> \
  --require-transport-pof \
  --missing-as-zero \
  --out <board.json>
```

正式模式必须有 cache。没有 cache 时不要用 `--diagnostic` 产物冒充 headline board。

### 13.8 最终审计

```bash
python3 scripts/production_isolation.py audit-meta \
  --proof-dir <proof-dir> \
  --meta-dir <raw-dir> \
  --out <isolation_audit.json>

python3 scripts/verify_run_set.py audit \
  --run-set-dir <results-root>/<run-set-id> \
  --out <integrity_report.json>
```

最终交付至少包含：

- queue 和 immutable run plan。
- manifest。
- per-cell report、meta、score。
- evidence 和 blobs。
- usage/cost ledger。
- isolation audit。
- integrity report。
- board JSON。
- 失败、withhold、excluded 和 rerun 欠账列表。

## 14. 2026-07-14 最新实际状态

### 14.1 服务与代码

- `my5090` 的 `cliproxyapi-dra.service`：`active`。
- 本地与远端代码 tree 一致。
- 核验时没有真实 `run_full_leaderboard`、`run_harness_smoke_matrix` 或 `run_deep_task` 在后台继续运行；进程查询只命中查询命令自身。

### 14.2 已收集报告

桌面目录：

```text
/root/Desktop/dra_12_reports_gpt56_luna_20260714
```

包含 12 个 harness 对 `dr_cross_deep_0010_rep1` 的报告文件：

| Harness | 行数 | 词数，按 `wc -w` |
|---|---:|---:|
| camel-ai | 334 | 2573 |
| claude-code | 91 | 1086 |
| deerflow | 314 | 2909 |
| flowsearcher-ds | 146 | 1308 |
| gpt-researcher | 198 | 2349 |
| ii-researcher | 167 | 2449 |
| langchain-odr | 841 | 5772 |
| ldr | 124 | 1276 |
| opencode | 102 | 1832 |
| qx-agents | 1408 | 14237 |
| smolagents | 111 | 1493 |
| storm | 201 | 7224 |

这些文件证明各 harness 在不同修复尝试中曾产出报告，但它们是汇集副本。没有附带一套统一的 run plan、manifest、meta、evidence、score 和同轮 integrity audit，因此不能直接构成正式榜。

### 14.3 最新名为 final 的 smoke 结果

最新控制摘要：

```text
/opt/dra-smoke-control/
  smoke12-final-gpt56l-20260714T120500Z/summary.json
```

摘要关键值：

```text
model            = gpt-5.6-luna
task             = dr_cross_deep_0010
harness_count    = 12
all_workers_zero = false
scoreable        = 0
total_tokens     = 70064
cost             = null
```

这一轮不能标记为通过。主要硬失败：

```text
[PASS] sandbox sources answer a canned query: forum=5, shopping=5, wiki=5
[FAIL] search hits are in-corpus: source(s) ['wiki'] returned no URL to classify
```

这说明“源有响应”和“源返回了能够由 registry 分类的 URL”是两个不同条件。后者失败时，可信 supervisor 正确地拒绝开跑。

本轮还出现：

- 多数 worker 在 trusted source/registry preflight 以 rc=6 退出。
- `smolagents` 已生成 pass report，但 scoring 期间收到外部 SIGTERM，`score_exists=false`。
- `claude-code` 记录为 external/operator wall-clock wrapper 终止。
- gpt-5.6-luna 尚未配置正式价格，成本汇总为 `unpriced`、`cost=null`。

所以当前准确结论是：

> 12 个 harness 都已经在若干修复运行中产出过报告，但尚无一轮统一的 12-harness smoke 同时满足 source preflight、完整运行、打分、隔离审计和 run-set 完整性。全量队列仍不应启动。

### 14.4 下一步唯一合理顺序

1. 修复或诊断 wiki 搜索结果“有命中但无可分类 URL”的 source identity 问题。
2. 在旧代码上能红、修复后变绿的回归测试中固定该问题。
3. 重跑 deterministic source preflight。
4. 重跑单条 harness smoke。
5. 重跑统一 12-harness x 1-task smoke。
6. 要求 `all_workers_zero=true`、12 个 cell 都有完整 meta/report/score、network verified、egress enforced、identity ok。
7. 运行 isolation 和 integrity audit。
8. 把 smoke 摘要交给用户确认。
9. 用户批准后才进入 13-task mini。

## 15. 已知限制与不能过度解释的地方

### 15.1 人类 usefulness anchor 缺失

LLM jury 内部一致不代表与人类判断一致。当前论文中仍需人类 pairwise anchor、kappa 或相关性验证。

### 15.2 当前还没有正式 truth board

论文 open problems 已明确指出自家 production truth board 尚未完成。当前报告样本和历史榜都不能替代正式 tv2.5 transport board。

### 15.3 n 小，统计功效有限

单题 smoke 只能验证管线，不能证明框架能力。13-task mini 也只能诊断，不适合做强排名结论。正式结论应基于预注册的完整 task set 和 replicates。

### 15.4 论坛 coverage 不对称

没有真实论坛 vital nugget 库，不能把 forum 贡献解释成与商城/Wikipedia 同等的事实覆盖。

### 15.5 fact 轴经常不激活

只有报告明确写出可绑定的价格或 overall rating 时 fact 才激活。如果大多数报告不写这类结构化 claim，名义 0.39 权重并不等于实际有 39% 的区分力。必须同时看 `fact_active_rate` 和 `fact_precision`。

### 15.6 quote support 是词面下界

合理 paraphrase 可能匹配不到。它不能替代语义 entailment，也不能证明 fetch。

### 15.7 模型身份是端点自报

identity probe 可以抓出路由错误，但不能证明底层权重未被服务端替换。

### 15.8 跨底模仍有混杂

thinking 支持、tokenizer、上下文策略和历史 GLM 例外使跨底模比较不完全同质。应优先解释同一 backbone 下的 lane 差异。

### 15.9 当前价格表不含 GPT-5.6 Luna

usage 可统计，但正式成本为 null。不能把缺价格解释成零成本。

### 15.10 当前 run plan 装配需要人工保证

board 已要求 immutable run plan，但 launcher 不自动创建它。正式全量前必须显式预注册，不能等运行结束后补写。

## 16. 结果发布时的最小诚信清单

发布任何 DRA 排名或论文数字前，逐项确认：

- [ ] 使用 `transport_v2`。
- [ ] `gate_semantics=provenance_v2`。
- [ ] formula stamp 完整且一致。
- [ ] task set hash 一致。
- [ ] immutable run plan 在开跑前注册。
- [ ] queue 是完整 agents x tasks 交叉积。
- [ ] 明确排除 `codex` 或已经补齐 remote isolation proof。
- [ ] 每 worker 独立 shim、proxy、evidence 和 usage。
- [ ] source preflight 全通过。
- [ ] worker live isolation proof 全通过。
- [ ] hidden gold 不进入 chroot。
- [ ] model identity exact match。
- [ ] report seal 全通过。
- [ ] missing/non-pass 按 0 补齐。
- [ ] stalled rerun 欠账清零。
- [ ] 正式 page cache 非空。
- [ ] mixed PoF/gate semantics 为零。
- [ ] 每个 0 有 reason code。
- [ ] 每个 withhold 有 reason code。
- [ ] low coverage 不进入 headline claim。
- [ ] presentation 不乘进 truth。
- [ ] 论坛贡献按真实有限口径描述。
- [ ] GPT-5.6 成本若未定价，显示 unknown/null，不显示 0。
- [ ] isolation audit 与 run-set integrity audit 全通过。
- [ ] 论文、网站和 board JSON 使用同一 formula 文案。

## 17. 一句话总结我们的最新做法

DRA 让不同 Deep Research 框架在同一个冻结三源沙盒、同一个底模和同一个受控能力边界中完成相同任务；用网络级隔离和逐 run 传输证据证明它们实际搜索、打开和引用了什么，再用 `provenance * quality` 直接门控结构化事实、真实抓取和 vital 内容覆盖组成的确定性质量分；所有格式和 LLM usefulness 只单列披露，不允许洗白真实性分，所有缺失、失败、盲区和车道差异都必须机器可读地进入最终榜单。
