# Route A Dev-14 双人 Rubric 校准填写说明

推荐使用已安装的交互 skill，不必直接面对空白表：

```text
Use $route-a-rubric-interviewer to start the interview.
```

仓库源码位于 `skills/route-a-rubric-interviewer/`，个人 Codex 已安装到 `/root/.codex/skills/route-a-rubric-interviewer/`。首次启动时，skill 会先自我介绍，并一次性询问姓名/代号、A/B/裁决者身份和起始题号；随后一次性询问 7 个不带候选答案的问题，保存人的原始判断；第二轮再集中展示候选 requirements 和所有合并、删除、来源角色挑战。不会一项一项连续追问。

标注者 A、B 必须在两个独立 task/thread 中使用 skill。在同一对话里让 AI 同时扮演 A、B，只能算 synthetic stress test，不能作为双人一致性证据。

你实际填写的是两份独立标注包：

- `data/calibration/route_a_dev14/annotator_A.md`
- `data/calibration/route_a_dev14/annotator_B.md`

两位标注者分别复制一份文件填写。A、B 都完成前不要互看答案。

## 1. 这一轮只做什么

本轮只从 query 中识别“报告不能省略的必要要求”。不要判断语料是否已有答案，不要找 URL，不要写关键词 matcher，也不要看 agent 报告。

判断方法是删除测试：

> 如果报告完全省略这一项，它还能算完整回答 query 吗？

如果不能，它是 required requirement；如果仍然可以，它通常是 optional。

## 2. 每个 requirement 怎么写

用普通中文写一条可观察的要求，推荐使用动词开头：

```text
比较方案 A 与方案 B 在通勤降噪方面的取舍
解释某项机制是否真实以及适用边界
引用目标用户群的实际使用经验
给出与预算和使用场景一致的最终建议
```

不要写：

```text
深入研究
写得全面
引用很多页面
至少搜索五次
给出高质量答案
```

这些无法形成稳定、独立的必要项。

## 3. 一个完整填写示例

虚构 query：

> 我预算 100 美元，每天坐地铁并戴眼镜。请比较头戴式和耳塞的降噪与舒适度，参考戴眼镜通勤者的经验，最后推荐一个方案。

可以写成：

```yaml
- local_id: R1
  requirement: "比较头戴式与耳塞两种方案"
  necessity_reason: "query 明确要求比较两种形态；遗漏任一形态就没有完成比较"
  output_form: "compare"
  intrinsic_source_roles: []
  source_role_reason: "query 没有限定该比较必须来自哪类页面"

- local_id: R2
  requirement: "讨论两种方案在通勤降噪方面的取舍"
  necessity_reason: "地铁降噪是用户明确决策约束"
  output_form: "explain"
  intrinsic_source_roles: []
  source_role_reason: "none"

- local_id: R3
  requirement: "讨论戴眼镜情况下的舒适度"
  necessity_reason: "戴眼镜是用户不可删除的场景约束"
  output_form: "explain"
  intrinsic_source_roles: []
  source_role_reason: "none"

- local_id: R4
  requirement: "纳入戴眼镜通勤者的实际经验"
  necessity_reason: "query 明确要求该人群的经验"
  output_form: "experience"
  intrinsic_source_roles: ["forums"]
  source_role_reason: "需要第一人称社区经验；商品规格或百科不能替代"

- local_id: R5
  requirement: "给出不超过 100 美元且与通勤和眼镜约束一致的最终建议"
  necessity_reason: "query 明确要求最后推荐一个方案"
  output_form: "recommend"
  intrinsic_source_roles: []
  source_role_reason: "推荐需要综合前述要求，不在本轮预设唯一来源路线"
```

## 4. 什么时候要求来源角色

只有当来源角色不可替代时才填写：

- `shopping`：query 必须核对具体产品身份、价格、规格或在售候选；
- `forums`：query 明确要求 owners、frequent flyers、photographers 等实际使用者经验；
- `wiki`：query 明确要求通用定义、历史或机制解释，且产品/社区页面不能替代。

不要为了三源对称而强行写三个来源。若多个来源都能完成要求，保持空列表。

## 5. 如何避免重复 atom

下面两项可能重复：

```text
讨论十小时佩戴舒适度
讨论长途飞行佩戴舒适度
```

如果 query 中“十小时”只是“长途飞行”的具体说明，应合成一项。只有当两项可以独立通过或失败时才拆开。

方案比较和比较维度通常可以分开：

```text
R1：覆盖 over-ear、on-ear、earbuds 三种方案
R2：比较三种方案的便携性
R3：比较三种方案的长时间舒适度
```

这样能区分“提到了三种方案但没有真正比较约束”的报告。

## 6. 不要在这一轮做什么

- 不看现有 `synthesis_requirements`，其中部分字段已经过时；
- 不看 answer key、gold、rubric draft 或 evidence graph；
- 不根据某个 agent 写了什么反推 requirements；
- 不写 URL、产品答案、正则、权重或分数；
- 不要求固定引用数、网页数、搜索次数或字数。

## 7. A、B 完成以后

锁定两份独立文件，不再回改。随后使用：

```text
data/calibration/route_a_dev14/adjudication.md
```

对齐等价、部分重叠和单方独有 requirements。裁决后的最终 requirements 才进入第二阶段 evidence answerability audit；语料缺失的 requirement 会触发补语料、改题或 blocked，而不是从 rubric 中悄悄删除。
