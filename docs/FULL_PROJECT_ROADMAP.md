# DeepResearchArena 项目路线图

- 文档版本：v3（2026-06-09）
- 适用仓库：`/root/Desktop/lyb/deep_reserch`
- 公开站点：https://www.deepresearcharena.com
- 本版替代 v2（2026-06-03）：项目方向已由用户确认变更，**不再做 RL 训练**，全部 RL/GRPO/专利/开放模型内容废止（见文末"历史沿革"）。
- 权威现状文档：`docs/PROJECT_STATUS_2026-06-09.md`（逐文件、逐数字核验过的检查表）。本路线图所有数字均取自该文档。

---

## 1. 目标

把 DeepResearchArena 建成一个真正高质量的 Deep-Research 评测基准：约 **120 个跨站点任务**（Magento 购物 :7770、Postmill 论坛 :9999、Kiwix 维基 :8090 三站受控沙箱）、**跨厂商可复现**（第三方仅凭仓库即可从原料重建榜单）、**接地可验证**（判官无关的 reachability / quote_match / curated recall 流水线）、**诚实且有区分度的打分**（剔除死信号与可膨胀信号）、**人类对齐证据**（真实标注者的 kappa，而非合成代理），并配套一个真实在线的排行榜。锁定的打分方法学是 truth-gated Elo（真值门控 Elo）：headline = 判官 Elo × 接地门控，`gated_score = round(elo × (reachability% + quote%)/200)`。捏造者永远无法登顶：判官再喜欢，引用不可达、原文不可核对就上不了榜首。

## 2. 当前位置（2026-06-09）

详细检查表以 `docs/PROJECT_STATUS_2026-06-09.md` 为准，此处只做摘要：

- **方法学已落地**：truth-gated Elo 公式已实现并接入两块线上榜（框架榜 12 智能体 / 2615 battles / 74 任务；骨干 LLM 榜 8 LLM / 643 battles / 24 任务）；3 判官 PoLL 陪审 1553 场全部 3 票、0 判官错误；静默"判官出错判平局"bug 已修复，平局率从 50.6% 降到 16.9%；死信号 claim_nli（345/349 个打分文件为 0）已弃用，presentation 经长度残差化后才进分。核心发现：原始判官 Elo 与接地真实度解耦（框架榜 rho=0.32 n=12，模型榜 rho=-0.31 n=8，均不显著，目前仅为定性排名反转）。
- **三大缺口**：
  1. **任务规模 75/120**：可计分主任务仅 75 个（65 valid + 10 forum-invalid），25 个隔离；20 个对抗 v2 任务无 golden 不可计分。
  2. **可复现性**：榜单不可从仓库原料重建。`sandbox_cache.json` 缺失、无 `*.battles.jsonl` checkpoint、仓库内 jury 源是旧的 10 智能体 / 1553 battles 版本（无 claude-code/opencode）。
  3. **人类对齐零真实标签**：`data/human_prefs/` 为空；现有 `HUMAN_ALIGNMENT_REPORT.md` / `JUDGE_HUMAN_KAPPA.md` 是合成产物（synthetic --dry-run），不可引用。

## 3. 分阶段计划（Phase 0 到 Phase 6）

### Phase 0：沙箱稳定化（任务 #38/#39，进行中）
- **为什么**：box 不稳定是用户认定的头号风险，是其余一切的前置；购物站/论坛站这两个接地关键服务目前仍需手动启动 Docker Desktop。
- **要做什么**：把 seed 折进 reset.sh 的 bring-up；修 kiwix book 配置不一致（compose 默认 `wikipedia_en_simple_all_maxi` vs shim/恢复路径 `wikipedia_en_all_nopic`，否则 wiki URL 404 会拖垮接地）；把 boot.sh / watchdog.sh / DRA_StackGuard 纳入版本控制（当前仅在 box 的 /opt/.dra_tmp/，box 被擦即丢失）；补 `infra/wiki-zim` 默认挂载目录。
- **阻塞项**：Docker Desktop 需手动启动；box 不通 docker.io / ghcr.io，无法拉取重建重型镜像；binfmt interop 每次重启需重做。前述"要做什么"各项均零阻塞，可立即做。
- **验收标准**：`wsl --shutdown` 后三站点 + gateway 无人工干预自动恢复到 HTTP 200；自愈脚本可在仓库内核验。

### Phase 1：语料扩展 + 重爬 golden（任务 #40，进行中）
- **为什么**：根因是 Postmill 论坛为纯技术语料，导致 25 个隔离任务 + 10 个 forum-invalid 任务丢失论坛第三方来源；重爬后可计分集有望从 75 升向约 95-100。
- **要做什么**：种子工具与数据已就绪（`data/corpus_seed/forum_threads.json`，254 条非技术贴、38 个论坛含 34 个净新论坛，映射到 25 个隔离任务；`scripts/seed_forum_corpus.py` 幂等）。在 box 上先跑 `seed_forum_corpus.py` 再跑 `build_deep_golden.py` 重爬受影响任务；重新清洗；手动编辑 `docs/EVAL_SET_REMEDIATION.md` 第 2 节裁定后重生 manifest（晋级是手动裁定，非自动流水线）。
- **阻塞项**：需 box 沙箱在线；容器名不一致（reset.sh 用 webarena_reddit，种子脚本默认 dr_sandbox_reddit）；种子非持久（`envs/reddit/reset.sh` 的 `down -v` 会擦掉，故 Phase 0 须先把 seed 折进 reset.sh）。
- **验收标准**：受影响任务 golden 出现真实论坛 cite（如 `dr_cross_deep_0014` 不再 46 条全 wiki）；`_manifest.json` 重生且与文档解析逐字节一致；可计分口径升到约 95-100。

### Phase 2：对抗任务 golden（任务 #41，待办）
- **为什么**：把任务总量推向约 120。当前 **20 个**对抗 v2 任务（7 causal + 7 contradiction + 6 long_tail；注意旧文档"22 个"口径不准确）有 schema/intent/阈值，但 `data/golden/deep_v2/` 不存在，每任务仅 6-8 个 `__MACRO__` 占位种子、0 个真实 localhost URL，不可计分。
- **要做什么**：在 my5090 沙箱抓取并把结果落到 `data/golden/deep_v2/`；单独再清洗；重生 manifest 把对抗任务纳入计分口径。
- **阻塞项**：需 box 沙箱在线（依赖 Phase 0）。
- **验收标准**：20 个任务的 triples_path 全部指向真实存在的文件且含真实沙箱 URL；纳入后总可计分任务接近 120。

### Phase 3：统一打分 + 分数入库（任务 #42，进行中）
- **为什么**：让基准离线可复现、不再依赖脆弱的 box。当前接地覆盖不均：`grounding_uniform2.json` 已过时（15 个抽查里 7 个 curated_recall 与当前 golden 不符），且缺 claude-code/opencode 两行。
- **要做什么**：构建 `sandbox_cache.json` 并**提交进仓库**；重新生成 `grounding_uniform2.json`；补 claude-code/opencode 的接地行；重新提交 12 智能体 / 2615 battles 的 jury 源 + `*.battles.jsonl` checkpoint（否则连陪审成员标签都会重生成为空）；缓解 cache 中毒风险（瞬时抓取失败被存成 status 0 / 空文本并永久服务）。
- **阻塞项**：需 box 沙箱在线（无缓存的重打分会挂，60s 超时）。
- **验收标准**：第三方仅凭仓库即可从原料完整重建两块榜（原料到 board，而非只能审计成品 JSON），兑现"跨厂商可复现"。

### Phase 4：锁定打分方法学（任务 #43，待办）
- **为什么**：方法学最终文档锁定，消除并存口径。
- **要做什么**：统一两套接地门控表述（`simple_score.py` 的离线 per-report F1 硬门控 vs `load-leaderboard.ts` 的 headline 乘性门控）；floor 校准与显著性分析；统一文档与数据漂移（判官窗口已是 `PAIRWISE_REPORT_CAP=12000` 而旧文档仍写 5000 字符；首页 battle 计数 1553 / 5230 / 2615 三个数同时存在且矛盾；FINDINGS 与 board JSON 关于框架陪审 2 或 3 判官的表述矛盾）。
- **阻塞项**：依赖 Phase 5（真实 kappa）先存在，否则锁定文档缺人类对齐一节。
- **验收标准**：单一权威方法学文档，公式/参数/计数与代码和线上榜逐项一致，零漂移。

### Phase 5：真实人类 kappa（任务 #32，待办，独立于 box 与充值）
- **为什么**：headline 人类对齐当前无支撑，只有合成与借用代理（标签无关证据：synth-gold deepseek 0.906 / glm-5.1 1.0、LLMBar 0.94 n=50，可辩护但不是人类 kappa）。这是可信度锚。
- **要做什么**：招募真实标注者采集 `data/human_prefs/prefs.jsonl`；跑 `scripts/build_kappa_pairs.py` + `scripts/compute_judge_human_kappa.py`；用真实标签重生成 `HUMAN_ALIGNMENT_REPORT.md` / `JUDGE_HUMAN_KAPPA.md` 替换合成版；核验线上 `/api/annotate` 是否真的持久化一次 POST（唯一未实测的采集环节，后端 web/worker.js + KV 绑定已就绪）。
- **阻塞项**：需真实标注者。不依赖 box，不依赖判官 API 充值，可全程并行推进。
- **验收标准**：prefs.jsonl 非空且来自真实标注者；kappa 报告基于真实标签重生成；合成版工件下线或显著标注为废止。

### Phase 6：重算上线 + 定稿文档（含任务 #45、#12）
- **为什么**：把扩展后的全量任务重算上榜；模型榜补判 0032-0038 共 7 个任务（24 升到 30 任务，约 170 场全平局待重判）；框架陪审从 2 判官升回真 3 判官；扩到 30+ 任务×智能体让 rho 相关结论获得统计显著性。
- **要做什么**：全量重判与重打分；两块榜重建并部署；按 CLAUDE.md 硬规则写 `data/changelog.json` 后重建 `web/dist` 推送上线；定稿全部文档。
- **阻塞项**：**判官 API 欠费**（deepseek "402 Insufficient Balance"、DashScope/百炼 "400 overdue-payment"，即任务 #45，须用户充值或换 key）；任务供给依赖 Phase 1/2，复现底座依赖 Phase 3，显著性依赖 box 稳定 + 判官 API。
- **验收标准**：模型榜 30 任务、框架陪审 3 判官的新榜上线且 changelog 记录；rho 结论有统计功效或如实降级表述；文档与 Phase 4 锁定版一致。

## 4. 两个根阻塞

几乎一切都被两个根阻塞门控：

- **(A) box / 沙箱稳定性**（Phase 0）：门控 `sandbox_cache.json` 构建入库（Phase 3）、语料重爬（Phase 1）、对抗 golden（Phase 2）、全量重算（Phase 6）。
- **(B) 判官 API 欠费**（任务 #45）：deepseek 402、DashScope 400。门控模型榜 0032-0038 重判、框架陪审升回 3 判官、全量重判（Phase 6）。

不被 A/B 门控的并行线：Phase 5 真实人类 kappa（只需标注者）；以及零阻塞清理项（修 kiwix book 配置、seed 折进 reset.sh、自愈脚本入库、统一过时文档与首页 battle 计数、处理 28 文件前端重构工作树、把污染探测从 5/100 扩到任务 6-100）。优先级建议见 `PROJECT_STATUS_2026-06-09.md` 第 7 节：先做零阻塞清理，并行解决 A/B，box 一上线立刻做 Phase 3 的缓存入库与 checkpoint 重提交（成本最低、收益最高）。

---

## 5. 历史沿革（附录，已废止）

本文件 v2（2026-06-03）曾把项目定位为"评测 + Agentic RL 训练"双线交付：GRPO 训练开放 Qwen 模型、ResearchEnv/工具注册表、1 到 2 项发明专利、CCF-A 论文、Mac 本地路径与实习生培养等。2026-06 用户确认方向变更：**不再做 RL**，项目唯一目标是把 DeepResearchArena 建成高质量 Deep-Research 评测基准（本文件第 1 节）。v2 的 RL/GRPO/专利路线整体废止，细节不再保留于本文件，如需查阅请用 git 历史。
