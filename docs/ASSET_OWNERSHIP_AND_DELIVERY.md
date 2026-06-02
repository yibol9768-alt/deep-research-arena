# Deep Research Arena 资产归属与交付清单

版本：2026-06-03 初版

用途：明确哪些目录是源代码，哪些是发布产物，哪些是实验数据，避免多 agent 并发和网站发布时改错地方。

## 1. 目录归属

| 路径 | 角色 | 当前处理规则 |
| --- | --- | --- |
| `src/` | 核心评测、RL、verifier、scoring 代码 | 可以开发，但必须跑本地 smoke 或相关 pytest |
| `integrations/` | search shim、MCP、外部 agent adapter | 可以开发，重依赖必须惰性导入 |
| `scripts/` | runner、训练、评测、构建脚本 | 可以开发，发布脚本和 destructive 脚本需主 agent 复核 |
| `data/tasks/` | task specs | 修改需跑对应 validator，并记录任务版本含义 |
| `data/golden/` | golden seeds 和 oracle | 修改需说明来源，并在活沙箱验证 URL |
| `data/results/` | 实验结果 | 原始结果不要随便清理；发布前统一整理 |
| `docs/` | 技术文档、路线图、报告 | 当前阶段主要写这里 |
| `frontend/` | Next.js public site 源码 | 前端开发主入口 |
| `frontend/out/` | Next.js export 输出 | 生成产物，不作为普通开发目标 |
| `web/dist/` | Cloudflare 发布产物 | 只有正式发布阶段才能改 |
| `web/` | 旧 FastAPI 门户 | 保留为旧工具/参考，不作为主 public site |
| `web-next/` | 旧或并行前端原型 | 需要后续归档或明确用途 |
| `worktrees/` | 多 agent 临时工作树 | 不提交，不作为交付产物 |

## 2. 发布规则

离线工程阶段：

- 不改 `data/changelog.json`。
- 不改 `web/dist/`。
- 不 commit、不 push、不部署。
- 只更新源码、测试、docs 和必要的本地脚本。

正式网站发布阶段：

1. 先更新 `data/changelog.json`。
2. 在 `frontend/` 跑 typecheck 和 build。
3. 将 `frontend/out/` 同步到 `web/dist/`，保留 `web/dist/wrangler.jsonc`。
4. 复核 public site 内容和 deploy artifact。
5. 经用户确认后再 commit/push。

## 3. 交付包拆分

| 交付包 | 内容 | 验收方式 |
| --- | --- | --- |
| 技术文档包 | 路线图、调研、专利草案、系统设计、runbook | 文档路径齐全，关键 claim 有代码或实验锚点 |
| 源码包 | `src/`、`integrations/`、`scripts/`、必要测试 | import check + pytest smoke |
| 数据集包 | task JSON、golden、datasheet、schema | validator 通过，license 和版本明确 |
| 模型包 | LoRA adapter、config、prompt、eval card、hash | 能加载，能跑固定 eval |
| 结果包 | leaderboard、训练曲线、消融、人工审计 | 指标可复现，图表口径一致 |
| Demo 包 | `frontend` 页面、demo 数据、部署说明 | 本地能打开并完整跑一个任务 |

## 4. 多 agent 分工建议

| Agent | 负责范围 | 不碰范围 |
| --- | --- | --- |
| RL agent | `src/rl/`、RL tests、RL task validator | `frontend/`、`web/dist/` |
| Verifier agent | `src/verifiers/`、scoring tests | 训练脚本、发布产物 |
| Frontend agent | `frontend/` 页面和组件 | `data/changelog.json`、`web/dist/`，除非进入发布阶段 |
| Docs agent | `docs/` 路线图、调研、runbook | 核心代码和数据结果 |
| Release agent | changelog、build、deploy artifact | 只有用户明确进入发布阶段才启用 |

## 5. 当前优先交付物

1. `docs/FULL_PROJECT_ROADMAP.md`
2. `docs/NON_GPU_TECHNICAL_EXECUTION_PLAN.md`
3. `docs/RESEARCH_SURVEY.md`
4. `docs/PATENT_DISCLOSURE_DRAFTS.md`
5. `docs/ASSET_OWNERSHIP_AND_DELIVERY.md`
6. `docs/templates/BENCHMARK_DATASHEET_TEMPLATE.md`
7. `docs/templates/MODEL_EVAL_CARD_TEMPLATE.md`
8. `docs/LOCAL_DEV_CHECKS.md`
9. `scripts/check_track_a_local.sh`
