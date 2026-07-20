# DRA Phase E1：稳定 Shard 编译与验收手册

状态：E1 正式 1% source export、row-oriented fidelity baseline 与
compact production candidate A 已完成。首轮实测发现逐 block/link 行式
SQLite 外推会达到数 TB，因此行式布局被保留为负向空间基线；紧凑布局
在同一 source manifest 上完成了全量 1% 重建、HTTP 审计、全库结构审计
与资源外推。独立 production build B 已在同一冻结输入和代码上完成；
A/B 的逻辑 ID、census、全部 SQL 表内容与规范化 SQLite 内容哈希一致。
两个 raw SQLite SHA-256 只在 SQLite [官方文件格式](https://www.sqlite.org/fileformat.html#the_database_header)定义的 file-change counter 与
version-valid-for header 字段不同，因此 raw hash 作为诊断保留，不再被错误
当作内容复现条件。180 项分层人工抽审的首轮问题标记已经回收，但正式
reviewer 字段尚未全部完成；旧 row baseline 也不是 parser v3 的同版本
oracle。在正式人审与最终 fidelity/certificate 通过前，E1 仍不得晋级。
本文只描述 Phase E1，不提前把后续工作记成 E2/E3 完成。

> **2026-07-20 surface 边界纠正**：本手册中的 E1 deterministic
> renderer 是 `canonical audit projection`，用于构图结构 round-trip、
> 搜索调试和人工抽审；它不是 Magento/Postmill/Kiwix 的替代网站，也不
> 提供给 harness。原生服务继续承担 browser surface，各 adapter 的
> delivery surface 在 E5 单独验收。R1—R3 中“生成后的网页 / 页面正常”
> 的措辞会在 R4 改成“结构审计投影 / 结构与来源一致”。缺少 CSS 不构成
> E1 parser 失败；table coordinates、rowspan/colspan、interaction parent
> edges 或 source locator 无法恢复才构成失败。

> **R3 自动复核与 R4 修复**：对审阅包 180 项逐页重新计算后，论坛
> 40 页的 1,260 条 interaction 和 1,220 条 parent edge 均未丢失，但
> 33 个含嵌套回复的页面把树视觉平铺；20 个高风险表格页的 1,415 个
> 非空 cell 均能往返，但 parser 跳过了 116 个空 cell，且 4 页中 391 个
> cell 的 DOM sibling index 不能直接当逻辑 grid column；20 个 resource
> 页全部把 ZIM 的字面 `null` 元数据当标题，投影只明显展示了字节数。
> R4 因此升级为 parser v3 / renderer v2：同时保存 `cell_index` 与逻辑
> `column_index`、保留空 cell、按 rowspan/colspan 重建可读表格、显示
> reply depth/parent，并在 resource 投影中显示 path、MIME、raw hash、
> archive locator 和显式 omission marker。新版在同一 180 项上完成
> 180/180 结构投影预检；core round-trip 也从“原文是否仍在页面中”升级为
> 对 block/type/section/DOM/structural JSON、field、interaction/parent、link
> 的有序 exact comparison。只改 parent 或 column 而不改正文的反例现在会
> 失败。这证明修复覆盖该分层样本，但不冒充独立人审。

截至 2026-07-19 的执行边界：

- 已核对冻结数据库、ZIM、容器镜像与顶层 census；
- 已完成三 pack、task-blind、稳定 bucket 0 的正式 source export，
  source manifest ID 为
  `b0c4d87bccbd3f28b85499f9ad13d6824c619c2fead538c0a9d102788124842c`；
- 正式 source 含 198,699 个对象：Commerce 1,067、Community 1,221
  （闭包保留 23,947 comments）、Wikimedia 196,411；export error 为 0；
- Wikimedia shard 中包含 72,722 个 HTML article、118,593 个 redirect
  与 5,096 个 resource；这是 19.55M ZIM entries 的 1% 身份样本，
  不是只按可见正文页重新定义分母；
- row baseline 已修复 invalid table span、soft redirect、O(n²) DOM/table
  路径以及检查点后逐条 fsync；失败尝试保留为诊断产物；
- row baseline 最终包含 198,699 documents、14,193,317 blocks、
  12,815,705 links、155,468 structured fields 与 28,112 interactions；
  compiler/structural/round-trip error 均为 0，exact alias 为 100%，
  分层标题 BM25 Top-20 为 292/298（97.99%）；
- row baseline SQLite 为 17,332,637,696 bytes，manifest 与实际 SHA-256
  一致；该布局只作为完整结构保真和空间归因基线，不作为全量生产布局；
- compact 600-document engineering smoke 已通过全部内部质量门，60 个
  分层 round-trip 全过，exact alias 与可判定 BM25 Top-20 均为 100%；
- compact candidate A 包含全部 198,699 个对象，SQLite 为
  1,748,926,464 bytes；包含 15,071,547 blocks、12,815,705 links、
  155,468 structured fields 与 28,112 interactions；全部内部质量门通过，
  300/300 exact round-trip 通过，exact alias 为 100%，可判定 BM25
  Top-20 为 292/296（98.65%）；
- 对旧 row baseline 的跨版本 comparator 如预期失败：parser v3 新增了
  878,230 个原先丢失的空表格单元，修复 5,096 个 resource title/alias，且
  renderer hash 全面变化。该旧 baseline 只保留作空间负例，不能作为 R4
  内容 oracle；正式 fidelity 必须绑定冻结 source 与 parser v3 artifact；
- HTTP 外部审计中 300/300 document hash 通过，BM25 Top-20 为
  292/296（98.65%）；全库 canonical structure audit 覆盖 198,699
  documents、7,358,310 table cells、303,096 tables 与 28,112
  interactions，failure 为 0；资源保守外推为 203.60 GiB、119.77 小时和
  0.42 GiB 峰值 RSS，均在当前冻结主机预算内；
- 180 项、9 个 strata、每层 20 项的人工抽审队列与离线审阅包已经生成；
  R3 的 hash 机器预检为 180/180，但额外结构复核发现上述三类问题；R4
  修复后的同样本结构预检为 180/180，这仍不替代人工 reviewer；
- R4 又从九个 strata 各随机打开两页完成浏览器 spot-check，共 18/18
  无新失败；其中两张回复树页面分别含 57/9 条 interaction，最大深度为
  7/3，评论、层级、表格、redirect 与 resource identity 均可见。该结果是
  补充检查，不冒充尚未完成的 180 项正式 reviewer 字段；
- 独立 compact candidate B 已完成全部 198,699 个对象，compiler failure
  为 0，300/300 round-trip 通过，exact alias 为 100%，可判定 BM25
  Top-20 为 292/296（98.65%）；耗时 2,928.054 秒，峰值 RSS
  217,352 KiB；
- A/B reproducibility report v2 已通过全部 18 项内容与绑定检查；两次构建的
  `logical_build_id` 均为
  `4dee38159cf28f257c796b1413ee82652147a6bd26004d4b34973fc788730cdb`，
  canonical SQLite SHA-256 均为
  `65b94ef93aad4a9eae677f2a67e37fc4b9f7689bf6835d9397cae5bc7c9a1ca1`。
  两个 raw SQLite SHA-256 不同，但全文件只在 header offsets 27 与 95
  各差一个字节；它们分别属于 SQLite offsets 24--27 的 file change counter
  和 offsets 92--95 的 version-valid-for number，SQL 表内容的双向
  `EXCEPT` 差集均为 0；
- 已实现 compact candidate、storage fidelity comparator、HTTP/build
  绑定、人工抽审队列与 final stage certificate；本地为
  `21 passed`；
- E1 仍是 **IN PROGRESS**。在外部门报告全部通过前不得写 E1 PASS。

## 1. 冻结输入

本轮只读取三个现有 Domain Pack：

| Pack | 冻结输入 | 已核对的顶层总体 |
|---|---|---:|
| Commerce | `dr_sandbox_shopping` 内 Magento 数据库 | 104,368 products |
| Community | `dr_sandbox_reddit` 内 Postmill 数据库 | 127,391 submissions |
| Wikimedia | `wikipedia_en_all_nopic.zim` | 19,551,505 user entries |

ZIM 冻结信息：

- file size：48.4 GB；
- UUID：`bb99e752-d98c-4bb7-6115-3aa7dfe5e695`；
- archive checksum：`c0fd49c67ce05c5b036686cfe8243bee`；
- article count：19,040,175；
- full-text index：present；
- title index：present。

这些总体来自数据库与 ZIM 本身，不来自 URL registry、56 道题、
Evidence Graph、query 或 witness list。

## 2. 稳定抽样合同

顶层对象使用：

```text
bucket =
uint64_be(
  SHA256(snapshot_id + NUL + pack_id + NUL + source_id)[0:8]
) mod 100
```

正式 E1 固定使用 `bucket = 0`，即稳定 1% shard。不同 pack 的
`source_id`：

- Commerce：Magento `entity_id`；
- Community：Postmill submission `id`；
- Wikimedia：ZIM entry path，大小写保留。

只对顶层对象抽样，子结构做闭包保留：

- 商品保留 EAV 字段、分类、库存、关系、评论与评分；
- 论坛主题保留根帖子与完整回复树；
- ZIM entry 保留正文或资源哈希；redirect 保留目标；
- 不独立抽样评论、回复或表格单元。

## 3. 两级执行

### 3.1 工程 smoke

smoke 只用于发现 SQL、ZIM binding、HTML parser、SQLite FTS5 和
renderer 接口错误。使用 `--wiki-scan-limit` 的产物会明确写入：

```json
{
  "engineering_smoke": true,
  "formal_eligible": false
}
```

示例：

```bash
PYTHONPATH=. python3 scripts/export_e1_shard_sources.py \
  --out /root/dra-e1/smoke-source \
  --modulus 1000 \
  --bucket 0 \
  --wiki-scan-limit 100000 \
  --progress-every 10000

PYTHONPATH=. python3 scripts/compile_e1_world_shard.py \
  --source-dir /root/dra-e1/smoke-source \
  --out /root/dra-e1/smoke-build \
  --roundtrip-per-pack 50
```

### 3.2 正式 1% shard

工程 smoke 过门后才能运行：

```bash
PYTHONPATH=. python3 scripts/export_e1_shard_sources.py \
  --out /root/dra-e1/formal-source-a \
  --modulus 100 \
  --bucket 0 \
  --progress-every 500000

PYTHONPATH=. python3 scripts/compile_e1_world_shard.py \
  --source-dir /root/dra-e1/formal-source-a \
  --out /root/dra-e1/formal-row-baseline \
  --roundtrip-per-pack 100
```

行式产物用于发现 parser 错误、归因空间成本和建立保真基线，不因为
内部质量门通过就自动成为 production layout。当前 production
candidate 使用相同的不可变 source records：

```bash
PYTHONPATH=. python3 scripts/compile_e1_world_shard_compact.py \
  --source-dir /root/dra-e1/formal-source-a \
  --out /root/dra-e1/formal-compact-a \
  --roundtrip-per-pack 100 \
  --progress-every 5000

PYTHONPATH=. python3 scripts/compare_e1_storage_profiles.py \
  --row-build /root/dra-e1/formal-row-baseline \
  --compact-build /root/dra-e1/formal-compact-a \
  --per-pack 100 \
  --out /root/dra-e1/storage-profile-fidelity.json
```

紧凑布局不是删除结构：完整 blocks、table coordinates、links、fields
和 interaction tree 作为确定性压缩 document artifact 保存；span/link
ID 由 `page_snapshot_id + ordinal` 随用随算；FTS 为 contentless index。
是否无损由全量 identity/hash/census 与分层 renderer/search 比较器判断，
不能只凭文件变小判断。

使用相同冻结 source manifest 和同一冻结代码独立执行第二次紧凑编译：

```bash
PYTHONPATH=. python3 scripts/verify_e1_reproducibility.py \
  /root/dra-e1/formal-compact-a \
  /root/dra-e1/formal-compact-b \
  --out /root/dra-e1/reproducibility-report.json
```

`logical_build_id`、census 与 canonical SQLite SHA-256 必须一致。
canonical hash 只把 SQLite 官方文件格式中的 24--27 字节
`file change counter` 和 92--95 字节 `version-valid-for number` 归零；
其余任一字节不同仍使复现失败。raw SQLite SHA-256、header 差异、运行时间、
创建时间与实测耗时保留为诊断，不进入内容复现判定；compiler、compact
module 与共享 structural parser 的代码 hash 必须同时一致。

单次 build manifest 只会写
`source_and_build_gates_pass=true`；`formal_eligible` 保持为 `false`。
只有双构建复现、全库 canonical structure audit、HTTP、人工分层抽样和
资源外推全部通过后，E1 汇总证书才能声明正式可用，避免把“编译成功”
误写成“阶段验收”。

## 4. 统一 World Index

行式 fidelity baseline 的 `world-index.sqlite` 包含：

- `documents`：page identity、URL、source、MIME、redirect、hash 和 locator；
- `blocks`：section、paragraph、list、table cell、post 等稳定 span；
- `links`：页面出链和 shard 内 target identity；
- `structured_fields`：规格、价格、库存、分类、论坛状态等确定性字段；
- `interactions`：评论、帖子、回复、父子关系、时间和匿名 author key；
- `aliases`：title、SKU、URL key、forum 等 exact identity；
- `duplicate_clusters`：正文 exact duplicate；
- `search_fts`：SQLite FTS5/BM25 索引。

紧凑 production candidate 对外保持同一 document/search/render/span
能力，但物理布局调整为：

- `documents`：identity、hash、结构计数和压缩 canonical artifact；
- `aliases`：只用整数 `doc_id` 做 secondary identity；
- `duplicate_clusters`：只保存真正的重复簇；
- contentless `search_fts`：保存倒排索引，不再复制整段正文；
- block/span/link/field/interaction 在 document artifact 内完整保存，
  读取时校验 artifact hash 并派生稳定 ID。

E2 的全局整数化 link graph/CSR 是 compact document artifact 的派生
索引，不允许为了节省空间丢掉原始 anchor、DOM path 或表格坐标。

这一层不抽取“厂商宣称”“独立测量”“机制解释”等任务语义，
也不调用 LLM。那些工作属于后续 Task World Model。

## 5. Raw → Canonical → Audit Projection

编译器为每个对象保存：

```text
source locator
→ raw_content_hash
→ stable blocks / links / fields / interactions
→ deterministic audit projection
→ audit_projection_hash
```

本地结构审计投影服务（不注册给 harness）：

```bash
PYTHONPATH=. python3 scripts/serve_e1_world_shard.py \
  --db /root/dra-e1/formal-build-a/world-index.sqlite \
  --host 127.0.0.1 \
  --port 18090
```

接口：

- `GET /health`
- `GET /document/{page_snapshot_id}`
- `GET /search?q=...&limit=...`

Round-trip audit 会重新解析 projection 输出，并对 canonical block 的类型、
section、DOM locator、文本和 structural JSON，以及 field、interaction、
parent edge、link 做有序 exact comparison；不能再用“每段原文仍在某处出现”
代替结构往返。R4 的 projection
precheck 还机械核对 resource identity/omission marker、重建表格的
cell 坐标与 span、以及每条 interaction 的可见 depth/parent。HTTP canary 只验证
canonical projection 的确定性与可检查性；它不证明 browser harness 已
获得正常原站页面，也不进入 agent surface equivalence 分母。

## 6. E1 验收门

E1 只有同时满足以下条件才能通过：

1. source export error 为零；
2. compiler error 为零；
3. stable sample round-trip error 为零；
4. exact alias lookup 为 100%；
5. 标题派生 BM25 query 的 Top-20 recall 至少 90%；
6. 两次独立构建的 `logical_build_id`、census、版本与 canonical SQLite
   SHA-256 相同，且 raw hash 若不同只能落在明示的 SQLite 非内容 header
   字段；
7. 全部 document artifact 必须通过 table grid、empty cell、span、interaction
   parent/cycle/depth 和 resource identity/omission 的 exhaustive structure audit；
8. audit projection 的 HTTP health 与 300 个分层 document bytes 必须 100% 通过，
   同一标题检索合同的 Top-20 recall 至少 90%；
9. 表格、商品字段、评论和论坛回复树的分层人工抽样没有系统丢失；
10. 资源曲线足以外推 E2/E3，不出现未知的磁盘或内存爆炸；
11. 构建记录确认 `task_conditioned=false` 且 witness 输入为空；
12. production artifact 必须直接对冻结 source manifest 做同版本的全量
    identity/artifact/census fidelity 审计；旧 parser 版本的 row baseline
    只可作资源负例，不得把旧 parser 的错误强制复制进新版 production layout。

任何一项失败都保留报告并修编译器，不通过手工添加题目页面解决。
资源门使用逆 inclusion probability 做点外推，并显式记录 disk/runtime/
memory safety factor；这些 factor 是当前主机的 operational budget，不伪装
成统计置信区间。全量 E2 使用 direct-stream，不能把完整 JSONL staging
副本悄悄排除在磁盘预算之外后仍按 staged pipeline 执行。

### 6.1 R4 同版本实际结果

2026-07-20 完成的 parser v3 / renderer v2 行式基线覆盖 198,699 个对象，
compiler failure 为 0，全部结构与 round-trip 门通过，标题 BM25 Top-20 为
98.65%。行式 SQLite 为 18,177,605,632 bytes，logical build ID 为
`29f8451b04fd14014a70973aa39b75791a289b1d7e3b1ab758c778d472118aad`。

与同 source、同 parser/renderer 的 compact candidate 全库比较结果为：

- 双向缺失与 identity/hash mismatch 均为 0；
- documents、blocks、links、fields、interactions、aliases、duplicates 及
  pack/type census 全部相同；
- 300 个分层 render/search 样本失败为 0；
- compact SQLite 为 1,748,926,464 bytes，即行式布局的 9.62%；
- `storage-profile-fidelity-r4-v3.json` 的 `passed=true`。

这证明 compact 物化没有依赖旧 parser 的缺陷，也没有为节省空间删除逻辑
结构。E1 仍不能因此宣布最终 PASS，因为正式 180 项双人/人工审阅门尚未完成。

人工门先生成确定性分层队列与审阅包：

抽样随机锚默认使用 `source_manifest_id`，而不是 `logical_build_id`。
这样同一冻结 source 在 parser/renderer 修复后仍审相同页面，支持 paired
regression；编译器变化只能改变 projection/hash，不能顺便换掉较难样本。
若需精确复现历史队列，可显式传 `--sampling-anchor <历史锚点>`，并把
`anchor_kind/anchor_id` 写入 queue。`logical_build_id` 仍进入 queue definition
和 finalizer 绑定，因此旧 review 不会被自动冒充为新 build 的正式 review。

```bash
PYTHONPATH=. python3 scripts/create_e1_manual_audit_queue.py \
  --build-dir /root/dra-e1/formal-compact-a \
  --per-stratum 20 \
  --out /root/dra-e1/manual-audit-queue.json

PYTHONPATH=. python3 scripts/render_e1_manual_audit_packet.py \
  --queue /root/dra-e1/manual-audit-queue.json \
  --build-dir /root/dra-e1/formal-compact-a \
  --source-dir /root/dra-e1/formal-source-a \
  --out-dir /root/dra-e1/manual-audit-packet

# 对 production artifact 全库运行，不是抽样：
PYTHONPATH=. python3 scripts/audit_e1_canonical_structures.py \
  --build-dir /root/dra-e1/formal-compact-a \
  --out /root/dra-e1/canonical-structure-audit.json

# 人工完成 queue 中全部 review 字段后：
PYTHONPATH=. python3 scripts/finalize_e1_manual_audit.py \
  --queue /root/dra-e1/manual-audit-queue-reviewed.json \
  --build-dir /root/dra-e1/formal-compact-a \
  --machine-preaudit /root/dra-e1/manual-audit-packet/machine-preaudit.json \
  --min-per-stratum 20 \
  --out /root/dra-e1/manual-audit-report.json

# 最终 E1 certificate 必须显式传入上述全库报告；报告需绑定同一
# logical_build_id、source_manifest_id、SQLite SHA-256 与 document census。
PYTHONPATH=. python3 scripts/finalize_e1_stage.py \
  --source-dir /root/dra-e1/formal-source-a \
  --build-a /root/dra-e1/formal-compact-a \
  --build-b /root/dra-e1/formal-compact-b \
  --reproducibility /root/dra-e1/reproducibility-report.json \
  --http-audit /root/dra-e1/http-audit.json \
  --canonical-structure-audit /root/dra-e1/canonical-structure-audit.json \
  --manual-audit /root/dra-e1/manual-audit-report.json \
  --resource-projection /root/dra-e1/resource-projection.json \
  --storage-fidelity /root/dra-e1/storage-fidelity.json \
  --out /root/dra-e1/e1-stage-certificate.json
```

机器 precheck 只负责暴露 source/artifact/projection hash 或结构损坏并帮助
导航；它明确写 `human_gate_satisfied=false`。R4 起，不能只比较三个 hash：
还必须验证表格投影坐标、interaction depth/parent 与 resource identity，
以免“底层尚可恢复、人工界面却无法看懂”的问题被误报为通过。审阅包的离线 `index.html`
同时展示受限原始 source record/HTML、结构 artifact 与 exact canonical
audit projection；人工 reviewer 检查 identity、文本、表格拓扑、回复树、
字段归属与 locator，不评价是否复刻原站 CSS。reviewer 逐项勾选、填写身份/失败类别/备注，再导出 reviewed
queue JSON。该导出保留不可变 `queue_definition_id`；finalizer 逐项绑定
机器预检、至少 20 个/stratum 的抽样合同与人审字段。脚本拒绝缩小样本、
替换抽样项或把 machine reviewer 冒充成人工门。source records 可能包含
benchmark-local 受限数据，在 rights/PII review 前不得发布审阅包。

实际审阅包 R2 还按 `queue_definition_id` 使用浏览器本地存储自动保存进度，
支持显式保存以及导入之前导出的 reviewed/draft JSON。导入前会同时校验
schema、logical build、source manifest、queue definition 和全部 audit item
身份；导入内容只能恢复 review 字段，不能替换文档或 required checks。
浏览器本地存储不可用时仍可随时导出 JSON 草稿。断点恢复只改善审阅操作，
不会让未完成人工字段的队列通过 finalizer。

## 7. 大产物政策

原始 JSONL、SQLite 和 renderer 临时文件保存在冻结构建主机，不直接
提交 Git。Git 中只保存：

- compiler、exporter、renderer 和测试；
- source/build manifest；
- quality/resource/reproducibility/HTTP audit 报告；
- 小型、去敏、可审计样本。

公开或移动任何 source record 前还需要单独通过 rights/PII review。
