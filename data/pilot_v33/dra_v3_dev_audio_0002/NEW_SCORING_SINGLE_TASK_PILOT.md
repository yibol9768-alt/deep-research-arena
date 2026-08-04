# `dra_v3_dev_audio_0002` 新评分单题试跑

> 日期：2026-07-23
> 结论：Writing Elo 已真实跑通并通过位置交换检查；新版 `Truth` 本次应当标记为 `withheld`，不能把旧 GRC 换名后冒充新分数。

## 1. 本次评了什么

任务要求在 60 美元预算内比较 Soundcore Flare 2 与 Ortizan 40W，重点审核价格、输出与失真措辞、360 度与被动辐射器宣传、IPX7、续航限制、Hi-Res Bluetooth、论坛证据边界，并给出有约束的推荐。

本次使用：

- 真实 GPT Researcher 报告：`real_run/report.md`
- 真实运行的 observation-ledger projection：`real_run/observation-ledger-projection.json`
- 现有单题 TWM 与 25 项 research test suite
- 对照报告：`controlled/reports/oracle_alternative.md`
- Writing judge：`deepseek-v4-flash`
- Writing 协议：`dra_writing_elo_v1`
- Prompt hash：`c401ffbd8f8e1e5c`

所有持久化产物均不包含 API 密钥。

## 2. 新版 Truth 的正式结果

| 项目 | 本次结果 |
|---|---:|
| `Fact` | withheld |
| `Evidence` | withheld |
| `Completeness` | withheld |
| `Provenance` | 1.000 |
| `Quality = (Fact + Evidence + Completeness) / 3` | withheld |
| `Truth = Provenance × Quality` | withheld |
| 正式榜单资格 | false |

这不是“报告得 0 分”，而是“当前输入不足以按新版协议产生可比较的正式分数”。原因有三项。

### 2.1 现有单题资产不是冻结 TEC

现有 TWM 来自 20 个预选页面，包含 15 条 assertion、6 条 relation、8 个 unit 和 25 个 check。它足以验证旧纵向原型，但没有 TEC manifest 所要求的全库候选扫描统计、排除记录、等价证据集合完备性、停止规则与挑战审计。

因此，它不能证明新版 `Fact` recall 与 `Completeness` 的分母已经 protocol-complete。

### 2.2 真实报告立即暴露了 census gap

报告使用了会影响判断、但没有进入现有 atomic bank 的材料，例如：

- Flare 2 的 5200 mAh；
- Ortizan 的 6600 mAh；
- “Flare 电池容量小约 21%”这一比较；
- 若干频率范围、尺寸、重量与连接规格。

其中电池容量及 21% 比较被用于续航推理，属于物质性任务 claim。冻结商品页确实包含相应文本，因此不能把它简单判为错误；按新版规则应触发 `census_gap`，补齐 TEC、升版并统一重算，而不是只给这一份报告临时加分。

### 2.3 仓库内 projection 不含发现链，但已找回原始完整 ledger

仓库内用于旧纵向原型的 ledger projection 只保留两次 `fetch_body`：

- Soundcore 商品页，HTTP 200；
- Ortizan 商品页，HTTP 200。

它没有保存这两个 URL 是由 task seed、搜索返回还是已观察页面链接发现的事件链。只使用 projection 时，可以确定“页面被观察过”，却不能确定新版 `LegalOrigin = InRegistry ∧ Discovered` 中的 `Discovered`。

随后找回了与报告 SHA-256 完全对应的原始完整 ledger：

```text
/root/Desktop/lyb/deep_reserch/data/results/route_b_pilot/
gpt-researcher-deepseek-v4-pro-dra_v3_dev_audio_0002_en/
observation-ledger.json
```

它包含 45 个事件，`capture_complete=true`。Ortizan URL 同时出现于 `search_result` 和 HTTP 200 `fetch_body`，并属于冻结 registry；因此报告唯一 cited canonical URL 的 `LegalOrigin` 通过，当前可独立计算 `Provenance=1.000`。

这不会解除整个 `Truth` 的 withheld：Fact、Evidence 和 Completeness 仍缺合格 TEC，且 census gap 尚未修复。

## 3. 仍然可以确定的诊断

| 诊断 | 结果 |
|---|---:|
| 报告中唯一 canonical evidence URL | 1 |
| 该 URL 在冻结 registry 中 | 1 |
| 该 URL 本次实际观察 | 1 |
| fabricated URL | 0 |
| unobserved citation URL | 0 |
| 合法发现路径 | 原始完整 ledger 中存在 |
| `Provenance` | 1.000 |

这说明“URL 真实性”并没有被丢掉。当前可以确认 Ortizan URL 真实、由搜索返回且被抓取；Soundcore 的大量事实虽然写进报告，却没有提供可解析 URL。由于 Provenance 按 cited canonical URL 集计算，单个合法 Ortizan URL 使该轴为 1；Soundcore 的缺证问题由 Evidence recall 捕获，而不是把 Provenance 的分母偷偷改成“应该引用的 URL”。

现有旧原型还能提供以下开发诊断，但它们不是新版三轴分数：

| 旧开发指标 | 结果 |
|---|---:|
| ContentBreadth | 0.658 |
| Raw / Official GRC | 0.192 |
| grounded checks | 6 / 25 |
| content-passed checks | 19 / 25 |
| Full Pass | 0 |

这些结果符合报告观感：它覆盖了不少要求，但真正由本次可追溯页面支持的主要是 Ortizan 商品页相关内容。Flare、IPX7 技术解释、声学机制和论坛范围大多没有有效 URL 与证据绑定。

报告还把 `<1% THD+N` 推导成“额定 20W 下保持线性”“高音量失真风险更低”，而冻结页面没有给出测试条件。旧 suite 已把对应输出比较、最终优先级等项判为 contradicted；这应在新版中分别降低 Fact precision、Evidence coverage 与相关高阶 unit coverage。

## 4. Writing Elo 真实试跑

匿名比较了：

- `real_gpt_researcher`
- `controlled_oracle_alternative`

并交换 A/B 位置各判一次：

| 顺序 | A | B | judge 选择 | 映射后的胜者 |
|---|---|---|---|---|
| AB | real | oracle | A，high | real |
| BA | oracle | real | B，medium | real |

两次都选择真实报告，说明本次没有检测到位置偏差。judge 的主要理由是：真实报告的章节导航、比较表、句子完整性和结论可定位性更好。

仅为了验证 Bradley–Terry 管线，二节点拟合得到：

| 报告 | 演示 Elo |
|---|---:|
| real GPT Researcher | 1389.17 |
| controlled oracle alternative | 610.83 |

这两个数不能作为榜单分数：只有一道题、一个 judge、两个节点，而且 oracle 不是参赛 harness。真正有意义的结果是“位置交换后，真实报告仍然两次获胜”。

## 5. 这次试跑证明了什么

这道题出现了很有价值的分离：

- 真实报告写作更好；
- 受控 oracle 的旧 grounded task score 更高；
- URL 没有造假，不等于引用覆盖充分；
- 页面确实抓过，不等于能证明合法发现；
- 现有 25 项 suite 能做开发诊断，但不等于新版 TEC 已经完成。

因此 Writing Elo 必须独立汇报，不能乘进 `Truth`。否则一个写得漂亮、但大部分关键事实没有证据绑定的报告会被错误抬高。

## 6. 要得到这道题的首个新版数值，还差四步

1. 从冻结语料按新版多通道 census protocol 编译并冻结该题 TEC，而不是沿用 20 页 witness 集。
2. 补齐 atomic fact bank、higher-order research units、support/contradiction spans、证据等价集合及 TEC manifest。
3. 从完整运行轨迹生成包含 seed/search/link/fetch/delivery 的 observation ledger，恢复合法发现链。
4. 对报告做原子 claim extraction、逐 binding 判定和高阶 unit matching，再计算四项原始分与 `Truth`。

完成后才可以发布：

```text
Fact / Evidence / Completeness / Provenance
→ Quality
→ Truth

Writing Elo
→ 独立展示
```
