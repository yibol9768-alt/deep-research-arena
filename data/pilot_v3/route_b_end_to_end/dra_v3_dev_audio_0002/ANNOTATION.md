# Route B proof-step pilot：便携音箱宣传核查

任务：`dra_v3_dev_audio_0002`

> I have a total budget 60 dollars and need one portable speaker for balcony and poolside use. Compare the Soundcore Flare2 with the Ortizan 40W. Put claim auditability first and distortion risk before raw wattage. Audit each listing's exact price, output and distortion wording, 360-degree and passive-radiator claims, IPX7, battery caveats, and any hi-res-over-Bluetooth claim. Interpret IPX7 within test scope, and separate general forum experience from same model water validation rather than treating unrelated discussion as owner testing of either speaker. Recommend one route, explain the key tradeoff and remaining measurement limits, and cite each factual claim to its sandbox source.

本次是 AI pilot review，不是人工 gold。15 个步骤全部保留，用于先跑通 scorer。

| 步骤 | 类型 | 依赖 | 标注意义 |
|---|---|---|---|
| E1 | 证据 | 无 | 核查 Ortizan 商品页的价格、40W Max、失真、IPX7、续航等完整声明。 |
| E2 | 证据 | 无 | 核查 Soundcore Flare 2 商品页的价格、20W、THD+N、360 度、IPX7、续航等声明。 |
| E3 | 证据 | 无 | 限定社区编码讨论的适用范围，不能把一般讨论当成候选产品实测。 |
| E4 | 证据 | 无 | 解释扬声器扩散/指向性的物理意义与质量推断边界。 |
| E5 | 证据 | 无 | 解释 hi-res audio 标签能说明什么、不能说明什么。 |
| E6 | 证据 | 无 | 解释 IPX7 的标准测试边界，避免推成无限防水。 |
| E7 | 证据 | 无 | 解释 LDAC 码率和连接条件，避免推成稳定无损。 |
| E8 | 证据 | 无 | 解释被动振膜是实际结构，但不能单独证明低频质量。 |
| E9 | 证据 | 无 | 限定一般音箱偏好论坛经验，不能冒充同型号泳池或海滩验证。 |
| E10 | 证据 | 无 | 解释瓦数、效率、连续/峰值功率和允许失真的关系。 |
| B1 | 桥接 | E3, E4, E5, E7, E8 | 综合 E3/E4/E5/E7/E8，区分真实机制与营销推论。 |
| B2 | 桥接 | E1, E8, E10 | 综合 Ortizan 商品声明、被动振膜和功率知识，判断 40W Max 与无失真说法的证据边界。 |
| B3 | 桥接 | E2, E4, E10 | 综合 Soundcore 商品声明、扩散概念和功率知识，形成可审计的声明矩阵。 |
| B4 | 桥接 | E1, E2, E3, E6, E9 | 综合两商品页、IPX7 和论坛范围，判断防水声明及真实用户验证边界。 |
| D1 | 最终决策 | B1, B2, B3, B4 | 依赖四个桥接结论，在审计性和失真风险优先的约束下给出最终选择。 |

## 当前缺口

- 这份既有 development case 的证据步骤大多只枚举一个冻结 source ID；后续需要在语料允许时补充等价 source IDs，避免把代表性 witness 误成唯一路线。
- 本次标注是 AI pilot review，正式冻结仍需人工检查步骤边界、依赖和最终答案合同。
