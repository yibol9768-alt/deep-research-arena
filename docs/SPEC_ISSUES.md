# SPEC_ISSUES(gates-L3-withhold 车道增量)

权威清单在主仓库提交 6d70e811 的 docs/SPEC_ISSUES.md;本文件只含 L3(G4 withhold)车道新增/补充条目,合并时并入权威清单。格式:`- [ ] [来源:L3] 问题;影响;文件:行号`。

- [ ] [来源:L3] concept/forum 槽位"评测缓存缺页即计 0"的 withhold 语义未定(权威清单 §1 第 2 条已登记同一分叉):本车道按冻结令不动分数与分母,只加可观测性——concept 路径现输出 detail 字段 concept_axis_withheld / concept_withheld_count / concept_nuggets_total / concept_axis_withheld_reason=concept_page_not_cached;拍板选"withhold 出分母"口径时改 score_completeness 的 denom 一处即可;影响:completeness(0.33 权重)概念槽约 278 条;文件:src/eval/decidable_scorer.py:1721-1723(盲判分支)、1962(withheld 计数)、2040(detail 字段)
- [ ] [来源:L3] forum_coverage 虚拟槽与 concept 同构的"线程页不在缓存→静默不可覆盖"尚未加可观测性:_forum_coverage_supported 对缓存缺失线程直接 continue,分母不动、detail 无 withhold 信号;本车道只修了 concept 路径的观测(forum 槽的候选线程集合开放,"哪个线程算被盲判"需先定义,属语义);影响:声明 forums 的 v2 任务每题 1 槽;文件:src/eval/decidable_scorer.py:1852(entry is None → continue)
- [ ] [来源:L3] 概念页 cache fixture(主仓库提交 615d8b49)形态为 {url: 页面文本字符串},打分器全链期望 {url: {"status":200,"text":...}}:字符串条目使 _concept_quote_supported / score_reachability(cache_status fallback)直接 AttributeError 崩溃(响亮失败,非静默 0;但 G1 oracle 若直接喂该 fixture 会崩,须先转换形态或给 fixture 定 schema);影响:G1/G5 供给链与任何消费该 fixture 的脚本;文件:src/eval/decidable_scorer.py:588(_cache_entry 原样透传字符串)、1697(_concept_quote_supported)
