# Deep Research Arena × GPT-5.6 Luna × CLIProxyAPI 交接

更新时间：2026-07-14（Asia/Shanghai）

## 2026-07-14 STORM 修复跑后的权威状态

**GPT 上游当前硬停。** 截至 2026-07-14 19:29 UTC，五份 Codex JSON
（相同 `chatgpt_account_id`）在 my5090 和 vircs 两端都返回 HTTP 402
`deactivated_workspace`。vircs 是直连，my5090 经 Mihomo；两条网络路径结果一致，
所以这不是单一代理节点或 Arena 沙盒故障。取得新的可用 Codex JSON、或重新启用
该 workspace 前，不要继续启动 harness 正式跑。

本轮已完成的可靠性修复：

- DS Proxy 只对 HTTP 402 且机器码恰为 `deactivated_workspace` 的响应做有界
  退避重试；普通 402 仍直接上抛。默认/正式 smoke 上限统一为 8。
- my5090 safe worktree 提交：`88983d6`、`b2f9730`；主工作树对应提交：
  `e1a8e3f`、`c484630`。
- CLIProxyAPI 配置改为 `max-retry-credentials: 5`、
  `disable-cooling: true`。代理客户端 key 已在 vircs、my5090 WSL 和 Windows
  三处同步轮换；Windows ACL 仍仅 `SYSTEM` 与 `liuyibo`。这里不记录 key。
- Windows Mihomo selector 已恢复为 `Auto`；临时 Japan/US 测试实例和临时 auth
  副本已删除。仅保留 localhost controller `127.0.0.1:19090` 供后续诊断。
- Hermes、飞书长连接、Mac 代理、公司私钥和 SSH 密钥均未改动。

STORM 三次隔离运行证据：

1. `smoke-fix-storm-citations-v1-20260714T182803Z`：进入原生 STORM 后因 402
   失败；54 个 usage-bearing 调用，输入 74,669、输出 39,680、总 114,349
   tokens；只有失败 stub，无可用报告或引用 sidecar，不计分。
2. `smoke-fix-storm-citations-v2-20260714T191511Z`：旧 smoke 覆盖只允许 3 次
   身份探针，0 tokens 后 infra 退出；该覆盖已修复为 8。
3. `smoke-fix-storm-citations-v3-20260714T192119Z`：外层身份探针成功 308
   tokens，但 worker 内探针连续 8 次收到 402，最终正确记为 `infra_abort`
   （worker rc=8），未进入 STORM、未生成报告、不计分。

无密钥的 DS Proxy 恢复预检 ledger 保存在：
`/opt/dra-smoke-control/api-preflight-20260714/dsproxy-workspace-retry-probe.jsonl`。
该预检曾在 workspace 间歇可用时完成 5/5 HTTP 200，期间吸收 8 次 402、
0 次重试耗尽；随后 workspace 转为两端持续 402。

## 0. 硬停点

**当前禁止启动 Arena 队列。** 用户要求先完成账号代理、代码、SSH 沙盒和门禁核验，再由用户向接手 agent 补充教学并明确批准运行。

当前没有任何 `run_full_leaderboard` 或 `run_deep_task` 进程。没有产生新的 Arena 报告。

## 1. 架构边界

Arena 不经过 Hermes。禁止把 Hermes agent 当成 Arena 的上游，否则会形成 harness 套 harness，污染工具循环、上下文、token 和评测语义。

正式账号代理使用官方开源项目：

- 项目：`router-for-me/CLIProxyAPI`
- 版本：`v7.2.72`
- 上游提交：`6279bb8a`
- 官方 Linux amd64 no-plugin 发布包 SHA-256：`30d6c5179fc25f2866a8071e89128ef3cbf0bad896f45a245cbe263c81663e45`
- 能力：OpenAI Codex OAuth 多账号、OpenAI Chat Completions/Responses 协议转换、轮询、cooldown、失败换号、session affinity

当前权威实例直接部署在 `my5090` 的 Ubuntu WSL：

- 服务：`cliproxyapi-dra.service`
- binary：`/usr/local/bin/cli-proxy-api`
- config：`/etc/cliproxyapi/config.yaml`
- client API key env：`/etc/cliproxyapi/client.env`
- auth dir：`/etc/cliproxyapi/auths`
- logs：`/opt/cliproxyapi/logs`
- endpoint：`http://127.0.0.1:8317/v1`
- 仅绑定 localhost
- Management API 和控制面板关闭
- systemd：enabled + active

`vircs` 上的同版本实例继续保持 enabled + active，仅作为回退副本。Arena 不需要也不应再建立 `my5090 -> vircs` SSH 隧道。

配置策略：

- `routing.strategy: round-robin`
- `routing.session-affinity: true`
- `routing.session-affinity-ttl: 24h`
- `request-retry: 2`
- `max-retry-credentials: 5`
- `disable-cooling: true`（旧 cooldown sidecar 已隔离备份）
- 内存 usage statistics 开启，保留窗口 3600 秒

调用代理时只读取密钥文件，不要打印密钥：

```bash
set -a
. /etc/cliproxyapi/client.env
set +a
export OPENAI_BASE_URL=http://127.0.0.1:8317/v1
```

## 2. 五份凭证的真实状态

CLIProxyAPI 正常加载以下五份 Codex JSON：

1. `NicolaBrayan6673+c2api6@outlook.com.json`
2. `NoahHeron0243+c2api1@outlook.com.json`
3. `NoahHeron0243+c2api3@outlook.com.json`
4. `NoahHeron0243+c2api4@outlook.com.json`
5. `NoeliaJakai8050+c2api2@outlook.com.json`

文件与目录权限均为 `0700/0600 root:root`。禁止打印、复制到仓库、提交或写入日志任何 access/session/id token。

代理验证：

- `/v1/models` HTTP 200，能看到 `gpt-5.6-luna`
- 连续五个不同 `X-Session-ID` 的 `/v1/chat/completions` 请求均返回 `OK`
- 五个响应的 model 字段均严格为 `gpt-5.6-luna`
- CLIProxyAPI 启动日志确认加载 `5 clients / 5 auth entries`

重要风险：五份 JSON 的邮箱和 access token 不同，但 `chatgpt_account_id` 完全相同：

`fc4f8db5-72cd-44cb-ae0d-fef1370a16c8`

五份 usage 查询的 5 小时和周额度百分比也完全相同。因此不能把它们直接视为五个独立额度池，更不能承诺五倍容量。接手 agent 必须在真正 smoke 前，通过每个凭证独立查询 reset 时间、额度变化和 account/workspace identity，判断它们是同 workspace 的多凭证还是五个独立 entitlement。

另一个限制：五份 JSON 的 `refresh_token` 都为空。access token 声明到期时间集中在 2026-10-11 12:10Z 至 12:23Z。401 时不能假设 CLIProxyAPI 能自动续期，需要重新导入新 JSON。

## 3. Hermes 与飞书

Hermes 已恢复为本轮操作前的认证状态：

- `LinoEmmeline9973@outlook.com`
- 原 `codex-chatgpt` device-code 条目

五份 Arena 凭证不在 Hermes pool 中。Hermes 使用 `fill_first`，没有连接 CLIProxyAPI。

- `hermes-gateway.service` 仍 active
- 飞书 WebSocket 未重启
- Hermes cron 为空
- 不要恢复 Mac 端 Hermes
- 不要恢复 Niko 邮箱定时任务

## 4. Arena 权威代码

- 仓库：`/root/Desktop/lyb/deep_reserch`
- 分支：`fix/pof-citation-extractor`
- 当前提交：`1a21116c`
- GitHub 对应分支 tip：`98c6fe1b`
- 服务器领先 1 个本地提交，本轮修复尚未 push

本轮发现并修复：`run_gates.py --quick` 只跑前 13 题，但新 G1 专项固定要求 0038，导致 quick 必然假失败。提交 `1a21116c` 让受限 sweep 明确 skip 该专项，完整 100 题仍强制验证 0038。

验证：

- `python3 -m pytest tests/ -q`：`1245 passed, 8 skipped, 17 deselected, 0 failed`
- `python3 scripts/run_gates.py --quick`：G0/G1/G2/G3/G4/G6 全部 PASS
- 不要 reset、不要重新下载原版覆盖当前代码
- 保留原有未跟踪的 gate/smoke 结果

## 5. my5090 沙盒

正式数据源和箱上执行环境位于：`my5090` WSL `/opt/deep_reserch`。

SSH 先落到 Windows，Linux 命令必须进入 WSL：

```bash
ssh my5090 'wsl -d Ubuntu -- bash -s'
```

本轮已经把 `1a21116c` 的 Git archive 同步到箱上。两端 5634 个 Git 跟踪文件的有序 SHA-256 汇总一致：

`b4c8efdaef8e8af52c745c4f6a4911b585e45f8a2fde86d4956d9b334bc69d93`

同步前备份：`/opt/backups/deep_reserch-code-before-1a21116c-20260713.tar.gz`。

箱上 preflight：`35 passed, 0 failed, 4 skipped`。三数据源均通过 canned query 和 in-corpus 检查。四个 skip 是只有正式 worker namespace/正式 run manifest 中才能完成的隔离、模型身份、宿主证明，以及已披露的跨底模 thinking 非统一项。

`my5090` 的 Mihomo 已换成 Mac 当前实际可用的 `SSRDog.yaml`。替换前已完成配置自检，并备份旧配置：

`C:\tools\mihomo\config.yaml.bak-20260713_211431`

当前 Windows Mihomo 监听 `:::7890`。Windows 经 `127.0.0.1:7890` 访问 ChatGPT 返回 HTTP 403；WSL 经 Windows 网关的 7890 访问 ChatGPT 与 OpenAI 均返回 HTTP 403，TLS 校验成功。这里的 403 是无网页会话或无 API key 的预期边缘响应，不是 TLS 故障。

`my5090` WSL 中 CLIProxyAPI 已正式启用：

- binary：`/usr/local/bin/cli-proxy-api`
- 版本：`7.2.72`
- binary SHA-256：`ec11d8acacbb5380f6939ebb839b7db48680dc8ca474b37796c23867ccb1412d`
- systemd：`cliproxyapi-dra.service`，enabled + active
- endpoint：`http://127.0.0.1:8317/v1`
- WSL client env：`/etc/cliproxyapi/client.env`
- Windows client env：`C:\tools\dra-cliproxyapi\client.env`，ACL 仅允许 `SYSTEM` 与 `liuyibo`
- 五份凭证：`/etc/cliproxyapi/auths`

服务每次启动前由 `/usr/local/libexec/cliproxyapi-prepare-config` 自动读取 WSL 当前默认网关，并生成 `/run/cliproxyapi/config.yaml`，将上游代理指向 Windows Mihomo 的 7890。这样 WSL 重启、网关 IP 改变后不需要手工改配置。

已完成的真实验证：

- WSL `/v1/models`：HTTP 200
- `gpt-5.6-luna` `/v1/chat/completions`：HTTP 200，回复严格为 `API_OK`
- Windows `http://127.0.0.1:8317/v1/models`：未认证请求 HTTP 401，证明 Windows localhost 到 WSL API 可达
- 迁移临时包已删除
- 桌面保留 `C:\Users\liuyibo\Desktop\SSRDog.yaml`，这是用户要求放到 my5090 桌面的代理配置副本

## 6. 接手 agent 的下一步

一条基础 API smoke 已按本次授权完成。没有用户明确批准，不得继续扩大模型实验或启动 Arena 队列。

长期连接和模型 smoke 已完成，不需要 SSH 隧道。接手 agent 在任何实验前先只读确认：

- `systemctl is-active cliproxyapi-dra.service` 返回 `active`
- WSL 本机访问 `/v1/models` 返回 HTTP 200
- WSL 本机完成一条 `gpt-5.6-luna` Chat Completions 请求
- `X-Session-ID` 使用稳定的 Arena `run_id`
- `run_full_leaderboard.sh` 的 model identity probe 严格返回 `gpt-5.6-luna`
- 正式 worker namespace 能访问代理端口但不能绕过 egress 记录门
- run manifest 记录 CLIProxyAPI 版本、配置 hash、auth pool 的匿名 hash 和代码提交

正式配置 Arena 时应设置：

```bash
set -a
. /etc/cliproxyapi/client.env
set +a
export BACKBONE=gpt-5.6-luna
export DS_PROXY_URL=http://127.0.0.1:8317/v1
export OPENAI_BASE_URL="$DS_PROXY_URL"
export JUDGE_BASE_URL="$DS_PROXY_URL"
export JUDGE_MODEL=gpt-5.6-luna
```

不要使用泛化名称 `gpt-5.6`，不要接 Hermes，不要直接把 `/chat/completions` 指到 ChatGPT backend。

## 7. 用户批准后的分阶段顺序

1. 不调用模型的 quick gates 和 box preflight。
2. 只跑 `1 harness × 1 task` smoke。
3. 检查 report、evidence、模型身份、usage、session affinity 和账号选择日志。
4. 把 smoke 结果交给用户，不自动扩大。
5. 用户批准后跑 13-task mini。
6. mini 正常后再申请 12 harness × 100 tasks 全量批准。

严禁直接启动 1200 队列、覆盖旧结果、关闭隔离、把部分结果写成最终 Elo，或假设这五份凭证等于五倍额度。
