# DRA Phase E2：Wikimedia Backbone 直接流式构建手册

状态：direct-stream compiler v2 已实现；本地单元测试、真实 ZIM 主动停机
恢复、`kill -9` 崩溃恢复及 W100K 稀疏选择前缀测试已通过。新版 W100K
已于 2026-07-20 完成完整 population 扫描并通过全部 W1M 晋级门，W1M 已在
独立目录启动。本文件只说明 Wikimedia structural backbone 组件，不提前把
Wikidata 对齐、served-artifact HTTP 审计或整个 E2 阶段记为完成。

## 1. 这一阶段“全量抽取”什么

全量对象是冻结 ZIM 中的全部 19,551,505 个 user entries。对入选视图中的
每个 entry，编译器确定性生成：

- document identity、canonical URL、redirect 与 raw locator；
- heading、paragraph、list、table cell 等 canonical blocks；
- 表格的物理 cell 顺序、逻辑 grid column、rowspan/colspan 与空 cell；
- 页面链接、anchor、exact aliases 与 contentless FTS5/BM25；
- resource 的路径、MIME、大小、raw hash 与 omission marker；
- parsed/rendered/artifact/search hashes 与重复簇。

它不调用 LLM 给全部页面抽取“所有事实”。事实、机制、冲突、经验和来源角色
仍只在 query 的高召回候选区上构建 Task World Model。

## 2. 不生成全量 JSONL staging

正式数据流为：

```text
frozen ZIM entry
  -> shared E1/E2 Wikimedia record builder
  -> parser v3 canonical artifact
  -> compact SQLite + FTS
  -> atomic checkpoint
```

`scripts/compile_e2_wikimedia_backbone.py` 直接读取 libzim entry，并复用
`scripts/export_e1_shard_sources.py::build_wikimedia_record`。因此 E2 不另写
一份可能达到数百 GiB 的全量 JSONL，也不会与 E1 已审计的页面转换逻辑漂移。

## 3. 嵌套视图合同

对同一 `snapshot_id`、pack 和 `source_id` 定义 64 位稳定秩：

```text
r(x) = uint64_be(
  sha256(snapshot_id + NUL + pack_id + NUL + source_id)[:8]
)
```

若冻结 population 为 `N`、目标规模为 `K`：

```text
x in W_K iff r(x) < ceil(2^64 * K / N)
```

于是相同输入上机械保证：

```text
W100K subset W1M subset Wfull
```

W100K/W1M 是期望规模为 100,000/1,000,000 的 Bernoulli rank-threshold
视图，不谎称实际文档数恰好等于目标。实际 `compiled` 和各 page type census
写入 manifest。Wfull 的 threshold 为 `2^64`，选择全部 entry。

## 4. checkpoint 与恢复不变量

每个 checkpoint 在同一个 SQLite transaction 中原子提交：

- 本批新增 documents、artifacts、aliases 与 FTS rows；
- `next_entry_index`；
- scanned/compiled/by-type census；
- content bytes、rolling record chain 与 checkpoint sequence；
- 累计时间、峰值内存和稀疏资源曲线。

数据库内 metadata 是恢复真值。外部 `checkpoint.json` 只在数据库 commit
成功后用 `fsync + atomic replace` 更新。若进程在两次 checkpoint 之间退出，
SQLite 回滚整批未提交写入，恢复时从最后提交的 `next_entry_index` 重放。

`--resume` 会拒绝以下情况：

- ZIM UUID/checksum/size/census 改变；
- snapshot、view threshold 或 scan end 改变；
- compiler、record builder、compact store、parser 或 libzim binding hash 改变；
- Python/SQLite runtime contract 改变；
- checkpoint 的 documents/FTS/count/cursor 与数据库不一致。

checkpoint 的批次大小不影响内容身份，可以在恢复时调整。

## 5. 运行命令

### 5.1 W100K

```bash
PYTHONPATH=. python3 scripts/compile_e2_wikimedia_backbone.py \
  --zim /root/dra-e2/sources/wikipedia_en_all_nopic.zim \
  --out /root/dra-e2/w100k-v2 \
  --snapshot-id dra-world-v0-2026-07-19 \
  --view w100k \
  --checkpoint-every-scanned 250000 \
  --checkpoint-every-compiled 10000 \
  --progress-every 100000 \
  --roundtrip-sample 100
```

恢复使用同一个 output、snapshot、view 和输入：

```bash
PYTHONPATH=. python3 scripts/compile_e2_wikimedia_backbone.py \
  --zim /root/dra-e2/sources/wikipedia_en_all_nopic.zim \
  --out /root/dra-e2/w100k-v2 \
  --snapshot-id dra-world-v0-2026-07-19 \
  --view w100k \
  --resume \
  --checkpoint-every-scanned 250000 \
  --checkpoint-every-compiled 10000 \
  --progress-every 100000 \
  --roundtrip-sample 100
```

### 5.2 W1M 与 Wfull

W100K 全部门通过后，用独立 output 将 `--view` 改为 `w1m`。W1M 通过后
再运行 `wfull`。三个数据库是同一 membership 合同的独立物化视图，避免
上一级工程事故污染下一级正式产物。

### 5.3 长运行 ladder supervisor

`scripts/run_e2_ladder_supervisor.py` 可在已启动的 W1M 后台等待，不接管或
重复启动当前 compiler。观察到 W1M manifest 后，它依次执行：completed
resume validation、URL identity、canonical 全审、原生 Kiwix 回源、调试
HTTP、资源预算与 Wfull promotion。只有全部门通过才创建 Wfull；Wfull 若有
checkpoint 则严格恢复，否则从空目录开始。最后同样完成全套审计并写
`wfull-candidate-certificate.json`。

supervisor 将每个状态原子写入 `ladder-state.json`，每条外部命令有独立 log；
任何非零退出都会把 ladder 标为 failed 并停止，不会自动跳过失败 entry 或
绕过 promotion。Wfull candidate 仍固定 `formal_eligible=false`，因为该
supervisor 不替代 Wikidata 和 E2 外部阶段证书。

## 6. 产物

每个完成的 view 包含：

- `world-index.sqlite`；
- `checkpoint.json`；
- `quality-report.json`；
- `resource-report.json`；
- `build-manifest.json`；
- 仅失败时存在的 `failure.json`。

build manifest 绑定 source identity、pipeline contract、view threshold、
logical build ID、raw SQLite hash、代码版本、census 与 checkpoint chain。
Wfull 通过这里只能成为 `full_backbone_candidate=true`。本脚本始终写
`formal_eligible=false`，因为正式 E2 还需要：

- Kiwix served artifact 的完整枚举和抽样 HTTP round-trip；
- exact sitelink map 与 uncertain alignment 分离；
- construction-only Wikidata global statistics；
- 独立 E2 stage certificate。

## 7. 已完成的故障恢复实测

### 7.1 主动停机恢复

- 真实 ZIM、Wfull 工程前缀 2,000 entries；
- 第 700 个 entry checkpoint 后退出，数据库 documents、FTS、内外
  checkpoint 均为 700；
- 恢复时改变 checkpoint 批次大小，从 entry 700 继续到 2,000；
- 最终 2,000 documents、20,270 blocks、23,495 links；
- exact alias 100%，可判定 BM25 Top-20 18/18，全部质量门通过。

最终部署包还使用相同正式 snapshot 做了 2,000-entry 重跑，全部质量门通过；
对完成目录再次执行 `--resume` 只返回同一 logical build ID，不改写数据库。
部署包、源码包和远端副本的 SHA-256 已逐一核对。

另外分别做了“一次完成”和“750 条后停机、改变提交批次后恢复”两次独立构建。
两者最终 checkpoint sequence 分别为 6 和 8，raw SQLite hash 因事务历史不同而不同，
但 logical build ID 同为
`ae44cd17c4db1098b4f929e4901fd97ec954a630483d9b8b85f0095b4581b232`，
record chain、census 和质量门一致。该边界由
`scripts/verify_e2_reproducibility.py` 机器判定，不把物理页布局误当成世界内容。

### 7.2 `kill -9` 崩溃恢复

- 真实 ZIM、Wfull 工程前缀 5,000 entries；
- checkpoint 4,000 后在下一未提交批次中强制终止进程；
- 重开数据库后 documents=4,000、FTS=4,000、内外 cursor=4,000，
  `PRAGMA integrity_check=ok`；
- `--resume` 从 4,000 编到 5,000，全部质量门通过。

### 7.3 W100K 稀疏选择 smoke

- 扫描真实 ZIM 前 100,000 entries；
- 按全体 population 的 W100K threshold 入选 540 个，理论期望约 511.5；
- scanned checkpoint 在没有大量选中页面时仍持续推进；
- 最终结构、round-trip、exact alias 和 BM25 门全部通过。

这些结果证明流式、稀疏选择和恢复机制已跑通；smoke 不替代完整 W100K 的
全 source scan、资源曲线和分层内容审计。

### 7.4 百万视图暴露的 URL 身份碰撞与 v2 修复

compiler v1 在 W1M 的 entry 26,375 处按唯一约束失败。根因不是重复页面，
而是新 namespace ZIM 中两个不同 source path：`/0.9` 与 `0.9`，被旧兼容
函数同时投影为 `A/0.9`。前者是指向 HTTP 条目的合法 redirect，后者是独立
百科条目；静默跳过或覆盖任何一个都会破坏闭世界身份。

v2 对 `archive.has_new_namespace_scheme=true` 的 ZIM 精确保留 URL-index path，
包括有意义的前导 `/`，并将 mapping version、namespace scheme、builder hash
写入 source/pipeline contract。完整 W1M 身份预检扫描 19,551,505 entries，
实际选择 999,921 个 source IDs 与 999,921 个 canonical URLs，二者碰撞均为
零。跨过原故障点的 30,000-entry 正文 smoke 编译 1,620 页并通过内置门；其
原生 Kiwix 回源抽样中 59/59 内容或跳转一致，含 39 个路径归一化边界样本。

旧 W100K v1 因使用旧 URL projection，只保留为发现故障的工程证据，不进入
v2 正式谱系。修复后从零重建，不通过跳过异常行伪造连续性。

### 7.5 W100K v2 正式结果

W100K v2 完整扫描 19,551,505 entries，实际编译 99,810 documents：37,025
article、60,193 redirect、2,592 resource。构建耗时 1,693.622 秒，SQLite
为 888,602,624 bytes，峰值 RSS 553,056 KiB，读取 1,804,134,423 content
bytes，共完成 80 次原子 checkpoint。

独立门的结果为：

- exhaustive canonical structure audit：99,810/99,810，无失败；
- table cells 3,645,113，empty cells 436,446，tables 154,939；
- exact alias 99,810/99,810，BM25 Top-20 96/98；
- debug HTTP projection document hash 100/100；
- native Kiwix content/redirect round-trip 328/328，其中 identity edge 28/28；
- URL identity、SQLite hash/integrity、census、task blindness 和资源预算全过。

最终 logical build ID 为
`5b64fa56ca7fcb22471a7cc78b3781c1338e156370537e893810902832f21a76`，
promotion report 的 20 项检查全部为 true，`promote_next_view=true`。这只批准
启动 W1M，不等于整个 E2 阶段完成。

## 8. 晋级规则

W100K 必须满足：

1. 扫描完整 19,551,505 entry population；
2. entry 读取或编译错误为零；
3. checkpoint/document/FTS/census 一致；
4. canonical structure audit 无失败；
5. exact alias 为 100%，标题 BM25 Top-20 至少 90%；
6. 分层 round-trip 与浏览器 projection 检查通过；
7. selected source IDs 与 canonical URLs 一一对应；
8. canonical URL 能回到原生 Kiwix，正文/资源 raw hash 或 redirect target 一致；
9. 实测资源曲线没有突破磁盘、时间和内存上界。

只有 W100K 通过才启动 W1M；只有 W1M 通过才启动 Wfull。不得因为长时间
运行而跳过失败 entry、手工补 task witness，或把未完成 manifest 标成正式。
