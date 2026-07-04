# 矛盾候选人工裁决指南(#17 人评批次的一部分)

## 你要做什么

13 个簇各有一份 `cluster_<簇名>.candidates.json`(机器标出的"营销数字
疑似超出技术上限"候选)和一份 `cluster_<簇名>.adjudication.template.json`
(空白裁决表)。你的工作:

1. 把模板复制一份,改名为 `cluster_<簇名>.adjudication.json`;
2. **第一阶段(先做,省大量时间)**:模板顶部 `references` 列出该簇
   候选用到的所有参考(每簇最多两三条)。逐条看
   `reference_fact_text`:它真的在陈述"技术上限"吗?
   - 是 → `reference_verdict: "VALID_CEILING"`
   - 不是(具体产品举例、说的是别的量、感知指标等)→
     `"NOT_A_CEILING"`,该参考名下的全部候选**自动作废,不用再填**。
   例:相机簇的两条参考(DxO 感知锐度 23MP、2007 年中画幅 39MP)都
   不是类上限,两个勾就作废全部 88 条。
3. **第二阶段**:对剩下的每条 entry 填 `verdict` +
   `adjudicator`(你的名字)+ `note`(一句话理由);
4. 全部填完后运行 promote(见 README),只有 `SUPPORTED_CONFLICT`
   会成为 gold。**留空视为未完成,promote 会整份拒绝**(被
   NOT_A_CEILING 作废的条目除外)。

## 三种裁决怎么选

| verdict | 含义 | 例子 |
|---|---|---|
| `SUPPORTED_CONFLICT` | 营销数字确实超出了冻结语料支持的技术上限,矛盾成立 | 商品页宣称 ANC 降噪 45 dB,而百科冻结快照写明消费级 ANC 至多约 30 dB |
| `NOT_A_CONFLICT` | 抽取或匹配错了:数字不是这个意思 / 参考值不是上限 / 商品和参考主题对不上 | "45 dB" 其实是最大音量;参考值来自文章里无关的句子 |
| `NUANCE` | 有张力但不是可判定的数字矛盾(永不入 gold) | "沉浸式降噪"与差评的落差 |

## 判断时看什么

- `claim_snippet`:营销原文片段。先确认数字+单位真的在说这个量纲。
- `reference_fact_text` + `reference_url`:参考出处(冻结百科的句子)。
  确认它确实是"技术上限"语义(at most / up to / maximum),而不是
  文章里随手出现的一个数。
- `relative_excess`:超出幅度。超得越离谱越可能是真矛盾;刚过容差的
  多半是 NUANCE 或测量口径差异。
- 拿不准就 `NOT_A_CONFLICT`:gold 宁缺毋滥,论文只报得出
  裁决一致率的部分。

## 注意

- 每份 candidates 文件头部的 `applies_to_tasks` 列出这份裁决会影响的
  任务;promote 之后 gold 会分发到这些任务的答案键。
- `BATCH_REPORT.json` 里 `dropped_references` 是机器已经因"标记率
  过高、疑似非上限"整体丢弃的参考,不需要你处理,只供审计。
- 时间预算:每条 ≈ 30-60 秒;先做候选少的簇找手感。
