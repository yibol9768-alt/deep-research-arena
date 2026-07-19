# `dra_v3_dev_audio_0002` 沙盒原生评分纵向实验

> 状态：development-only。受控报告的语义标签由构造已知；真实旧报告使用人工 pilot 判断，因此不能进入正式榜单。

## 本次真正跑通的链路

```text
冻结 task / case / graph / run
  -> 轻量 Task World Index
  -> Task World Model
  -> 5 facets / 8 units / 25 checks 的 Research Test Suite
  -> report + observation ledger + sealed semantic judgment
  -> ContentBreadth / Raw GRC / Official GRC / Full Pass / URL 与证据诊断
```

每个 check 只有在内容合同满足，并且至少一条完整、连贯的证据路线全部通过时才得分。不同路线之间不能逐前提拼接。构题 witness 只证明可答，不是 URL 白名单。

## 受控实验结果

| 场景 | ContentBreadth | Raw GRC | Official GRC | Full Pass | 说明 |
|---|---:|---:|---:|---:|---|
| `oracle_reference` | 1.000 | 1.000 | 1.000 | 1 | 已知论坛 witness 路线 |
| `oracle_alternative` | 1.000 | 1.000 | 1.000 | 1 | 有界搜索替代路线 |
| `null` | 0.000 | 0.000 | 0.000 | 0 | 空报告 |
| `url_dump` | 0.000 | 0.000 | 0.000 | 0 | 只有链接，没有研究内容 |
| `fluent_unsupported` | 1.000 | 0.000 | 0.000 | 0 | 内容完整但本次没有交付证据 |
| `frankenstein` | 1.000 | 0.908 | 0.908 | 0 | 把两条路线的残片拼在一起 |
| `unobserved_ipx7` | 1.000 | 0.817 | 0.817 | 0 | IPX7 技术页未在本次交付 |
| `wrong_binding` | 1.000 | 0.975 | 0.975 | 0 | 相关领域页面错绑到 watt claim |
| `contradicted_citation` | 1.000 | 0.817 | 0.817 | 0 | IPX7 支持判为反驳 |
| `fabricated_url` | 1.000 | 1.000 | 0.000 | 0 | 额外加入确认不存在的沙盒 URL |
| `real_off_world_only` | 1.000 | 0.975 | 0.975 | 0 | 用真实外部 URL 替代一个在册证据 |

## 真实旧报告重放

| 指标 | 结果 |
|---|---:|
| ContentBreadth | 0.633 |
| Raw GRC | 0.192 |
| Official GRC | 0.192 |
| Grounded checks | 6/25 |
| Full Pass | 0 |
| Fabricated URL | 0 |
| Formal eligible | false |

这个结果不再是旧固定路线的 0/15，也不会因为报告写得流畅就抬高证据分。它保留了报告确实从 Ortizan 商品页完成的局部研究，同时把 Soundcore 无 URL、技术页无引用、论坛范围过度概括、THD 条件过推和推荐依赖失败逐项暴露出来。

## 验收门

| 验收项 | 结果 |
|---|:---:|
| `oracle_full_pass` | PASS |
| `null_floor` | PASS |
| `url_dump_floor` | PASS |
| `fluent_unsupported_separation` | PASS |
| `alternative_route_equivalence` | PASS |
| `frankenstein_rejected` | PASS |
| `local_unobserved_effect` | PASS |
| `wrong_binding_rejected` | PASS |
| `contradiction_is_critical` | PASS |
| `fabrication_gate` | PASS |
| `offworld_not_mislabeled_fabrication` | PASS |
| `real_report_partial_not_zero` | PASS |
| `no_pending_controlled` | PASS |

## 仍未被这一个样例证明的内容

- 25 个 checks 是否代表跨题通用 compiler 的稳定输出，仍需 Dev-14 的双人校准与编辑率统计。
- 真实报告的语义判断尚未通过冻结双 judge 与人工金标校准；当前只证明了确定性执行与回放层。
- 真实运行使用的是两页候选商品 fetch 的评分投影，不能用来评价完整搜索 API 召回或整个 harness 的检索效率。
- Observation Ledger v2 的 raw fetch 到 model-delivered artifact 血统仍需在 12 个 adapter 上逐一做 canary。

因此，下一步应先复制这个纵向样例到另外两种任务结构，而不是直接批量生成 56 份未校准测试。
