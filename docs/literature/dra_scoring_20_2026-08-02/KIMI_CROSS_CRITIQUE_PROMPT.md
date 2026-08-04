# Kimi K3 max cross-critique prompt

请继续保持只读角色。现在读取 `GPT56_INITIAL_SCORING_PROPOSAL.md`，把它当作另一位方法学设计者提出的候选，而不是既定结论。

请输出一份中文 Markdown 交叉审查，逐项回答：

1. 该方案最强的三点是什么？
2. `Grounded Claim Precision` 与 `Grounded Research Recall` 是否真的共享足够一致的 matching universe，可以正当地计算 F1？如果不完全一致，应如何修正命名、匹配或公式？
3. \(e_c=A_c\cdot \sum b/|J_c|\) 是否会重复惩罚、误罚必要的多来源联合证据、奖励少引或被 citation spam 攻击？请给反例和替代定义。
4. 对不需要外部引用的 claim 直接令 \(e_c=1\) 是否会让模型把外部事实包装成“推理”？怎样机械化区分 citation-required 与 exempt？
5. `fabricated_url` 只做 clean leaderboard 排除是否足够，还是需要数值门控？比较两者的可解释性。
6. 必要研究单元 \(U_{t,d}\) 是否又回到昂贵逐题 rubric？怎样借助 query、TEC、冻结索引和少量审查减少主观性？
7. unresolved/census_gap 的上下界是否过宽或易被利用？什么时候必须 withheld？
8. 现有四轴里 Evidence 已经是 Citation P/R/F1。GPT 方案会不会把 Evidence 在 \(g_c\) 与 Research Recall 中重复计算？请给无重复计分的最终结构。
9. 提出你修订后的最小公式，以及一个保守兼容公式。
10. 列出 GPT 方案必须通过的五个 falsification tests。若不能通过，就不能升级为正式主榜。

请明确引用 `PAPER_SCORING_EXTRACTION.md` 中的论文编号或原 PDF 位置。不要修改文件，只输出评审正文。
