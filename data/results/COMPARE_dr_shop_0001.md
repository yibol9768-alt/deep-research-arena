# 人工对比:dr_shop_0001(找 3 款 4+ 星耳机)

## 任务

> On the One Stop Market, find three distinct On-Ear / Over-Ear headphones
> that have a customer rating of at least 4.0 stars. For each, report the
> product name, current price (USD), rating, and the product-page URL.
> Also provide a one-sentence recommendation naming your top pick and why.

---

# A. 单 Agent (react-glm51)

> 实现:GLM-5.1 ReAct + 8 个 Playwright 工具,单 LLM 循环。
> 耗时:58 秒。Token 消耗:14k in / 1.3k out。
> 成本:$0.018。

## 找到的产品

| # | 产品 | 价格 | 评分 |
|:-:|---|---:|:-:|
| 1 | **Harphonic E7 Active Noise Cancelling Headphones** Bluetooth Wireless Over Ear with Microphone Deep Bass | $34.99 | 4.3⭐ |
| 2 | **Reverbix E7 Active Noise Canceling Headphones** Overhead Bluetooth with Mic, 35-Hour Battery | $54.99 | 4.3⭐ |
| 3 | **Wireless Headphones for Acura MDX** | $49.69 | 4.8⭐ |

## 推荐

> 我的首选是 **Harphonic E7 Active Noise Cancelling Over Ear Headphones**($34.99),
> 因为它提供出色的主动降噪、蓝牙无线连接、内置麦克风、深沉低音,
> 4.3 星(12 条评论),且是三款中价格最低的。

## 引用(JSON 字段形式)

- Harphonic E7 → http://localhost:7770/harphonic-e7-active-noise-cancelling-headphones-...html
- Reverbix E7 → http://localhost:7770/reverbix-e7-active-noise-canceling-headphones-...html
- Wireless Headphones for Acura MDX → http://localhost:7770/wireless-headphones-for-acura-mdx.html

## ⚠️ 人工观察

- 第 3 款 **"Wireless Headphones for Acura MDX"** 是**汽车后排座椅蓝牙耳机配件**,不是普通用户用的 over-ear 耳机。Agent 没意识到这是品类外。
- 推荐理由很表层(就是"评分高 + 便宜"),没分析样本量、没分析品类、没考虑 5 星但只有 1-2 评的可信度。
- 输出立刻完成 → 但研究本质上很浅。

---

# B. 多 Agent (deerflow-glm51)

> 实现:DeerFlow v1 多 agent 流水线 (coordinator → planner → researcher → analyst → reporter),
> GLM-5.1 驱动 5 个角色。
> 耗时:~5 分钟。Token 消耗:~200k(researcher 跑了 16 次工具调用)。
> 成本:~$0.20。

## 完整研究报告

### 1. Methodology(方法)

研究分四步:
1. **搜索阶段**:用 4 个不同关键词扫遍("on-ear headphones" / "over-ear headphones" / "headphones over ear wireless noise cancelling" / "Bluetooth headphones on ear")
2. **筛选阶段**:仅保留评分 ≥ 4.0
3. **验证阶段**:逐个进商品页核对名/价/评分/评论数/URL
4. **选择阶段**:从评分可靠性、价值比、功能集三维度比较

### 2. 完整候选清单(7 款合格产品)

| # | 产品 | 价格 | 评分 | 评论数 | 类型 |
|---|---|---:|:-:|:-:|---|
| 1 | Edifier H840 Audiophile Over-The-Ear Headphones (Renewed) | $50.19 | 5.0⭐ | 4 | Over-Ear, 有线 |
| 2 | Denon AH-D5200 Over-Ear Headphones | $699.00 | 5.0⭐ | 3 | Over-Ear, 有线 |
| 3 | Ulian Over Ear Headphones MH5 Black | $19.99 | 5.0⭐ | 2 | Over-Ear, 无线 |
| 4 | Srhythm NC35 Noise Cancelling Headphones | $79.99 | 5.0⭐ | 1 | Over-Ear, 无线 |
| 5 | Sony WH-1000XM4 Bundle | $406.00 | 5.0⭐ | 1 | Over-Ear, 无线 |
| 6 | **TECNO Bluetooth Headphones N1** | **$39.99** | **4.3⭐** | **12** | **Over-Ear, 无线** |
| 7 | **Harphonic E7 Active Noise Cancelling Headphones** | **$34.99** | **4.2⭐** | **12** | **Over-Ear, 无线** |

### 3. 评分可靠性分析(★ 关键洞察)

> 评分越少越脆弱:Ulian MH5 的 5.0 星(只有 2 评),只要再来一条差评就会跌到约 3.3 星;
> 而 TECNO N1 的 4.3 星(12 评),同一条差评只会让它跌到约 3.98 星。

| 产品 | 评分 | 评论数 | 加 1 条差评后预估 | 可靠性 |
|---|:-:|:-:|:-:|:-:|
| TECNO N1 | 4.3 | 12 | ~3.98 | **高** |
| Harphonic E7 | 4.2 | 12 | ~3.88 | **高** |
| Edifier H840 | 5.0 | 4 | ~4.00 | 中 |
| Denon AH-D5200 | 5.0 | 3 | ~3.75 | 低 |
| Ulian MH5 | 5.0 | 2 | ~3.33 | 低 |
| Srhythm NC35 | 5.0 | 1 | ~2.50 | 极低 |
| Sony WH-1000XM4 | 5.0 | 1 | ~2.50 | 极低 |

### 4. Top 3 推荐

#### 🥇 第 1:TECNO Bluetooth Headphones N1 — $39.99(4.3⭐ × 12 评)

> 在样本量足够的产品里评分最高,价格亲民,功能齐全(内置麦克风 / 记忆海绵耳罩 / 便携收纳盒),综合最均衡。

#### 🥈 第 2:Harphonic E7 Active Noise Cancelling Headphones — $34.99(4.2⭐ × 12 评)

> 是评分可靠的产品中**最便宜**的。带主动降噪 + 30 小时续航,这两个功能在同价位里少见。

#### 🥉 第 3:Edifier H840 Audiophile (Renewed) — $50.19(5.0⭐ × 4 评)

> 服务于 audiophile(发烧友)细分市场。是评论数 > 1 的产品里评分最高的;翻新版本,价格亲民。
> 注意:有线 + 翻新需要在购买时考虑。

### 5. 评估但未选入(及理由)

| 排除产品 | 价格 | 评分 | 评论数 | 排除理由 |
|---|---:|:-:|:-:|---|
| Denon AH-D5200 | $699.00 | 5.0 | 3 | 价格离谱,评论太少不足以支撑 premium 定价 |
| Sony WH-1000XM4 Bundle | $406.00 | 5.0 | 1 | 单条评论不可信(尽管旗舰品牌) |
| Srhythm NC35 | $79.99 | 5.0 | 1 | 单条评论无统计意义 |
| Ulian MH5 | $19.99 | 5.0 | 2 | 最便宜但评论太少 |

### 6. 差点合格(对照组)

> 两款 on-ear 模型未达 4.0 阈值,作为参考列出:

| 产品 | 价格 | 评分 | 缺口 |
|---|---:|:-:|---|
| JBL TUNE500BT Wireless On-Ear | $45.32 | 3.9 | -0.1⭐ |
| Koss SP330 On Ear Dynamic | $50.00 | 3.9 | -0.1⭐ |

### 7. Survey Note(综述笔记)

DeerFlow 还自带了一段学术综述风格的尾注,引用了:
- **Chevalier and Mayzlin (2006)**:消费者购买决策同时被 average rating 和 review count 影响
- **Filieri et al. (2015)**:评论数大的评分被认为更可信

并自我反省了 4 条研究局限:
1. 样本量普遍较低(1-12 评),4.2 vs 4.3 在统计上其实没差别
2. 平台不区分 verified vs unverified purchase 评论
3. Edifier "Renewed" 状态是 confounding 变量
4. 价格只是 snapshot,可能有时段促销

---

# 对比观察(人工)

| 维度 | react-glm51 | deerflow-glm51 |
|---|---|---|
| **答完任务** | ✅(给了 3 款 + 推荐) | ✅(给了 3 款 + 推荐 + 大量上下文)|
| **品类敏感度** | ❌ 把汽车配件耳机选进 top 3 | ✅ 7 款全是真 over-ear,排除了对照组 |
| **统计素养** | ❌ 只看绝对评分 | ✅ 显式做"加 1 差评后"分析,优先选 12 评的产品 |
| **取舍决策** | "便宜+评分高=赢" | "可靠性 vs 价格 vs 功能集"三维权衡 |
| **批判性** | 无 | 自我反省 4 条 limitation,引文献 |
| **格式** | 紧凑结构化 JSON | 长篇 markdown(7 个段落 + 5 张表)|
| **耗时 / 成本** | 58 秒 / $0.018 | ~5 分 / $0.20(约 11×)|
| **可机器评分** | ✅ JSON 直接走 schema | ⚠️ markdown,要解析 |

**核心差异**:
- 单 agent 是"完成任务执行者"——给我 3 款产品就行
- 多 agent 是"研究分析师"——同样答 3 款,但围绕"为什么是这 3 款"做了一整套论证

**给老师汇报时可强调**:
> Deep Research 的本质就是这种**"为什么"的论证密度**。
> 单 agent 即使技术上"答对了",研究质量也明显比多 agent 浅。
> 这正是我们要量化评测的东西。

---

## 当前评分器给出的分数(供参考,不影响人工判断)

| Pillar | react-glm51 | deerflow-glm51 |
|---|:-:|:-:|
| Deterministic(JSON schema)| ✅ 1.00 | ❌ 0.00(prose)|
| Citation(ALCE F1)| ❌ 0.00(字段名错)| ✅ 1.00 |
| Factuality | ❌ 0.00 | ✅ 1.00 |
| LLM Judge(4 维)| 0.83 | 0.70 |
| Comprehensiveness | 0.80 | 0.80 |
| Efficiency | 1.00 | 0.00 |
| **Composite** | **0.51** | **0.55** |

> 你的判断是对的:**强制 JSON 输出确实抹平了"研究深度"的真实差距**。
> 下一步要把 ReportVerifier 改成评 markdown 字段提取,而不是死磕 JSON schema。
