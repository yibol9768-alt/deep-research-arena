# v2 试点首跑 · 交接文档(2026-07-03)

> 接手者:任意后续 agent。本文档自足:目标、现状、全部已踩的坑、
> 逐步操作、验收标准、硬约束。相关 todo = #38(试点)→ #39(全量)。

---

## 0. 硬约束(先读,违反会出事故)

1. **GPU 必须保持静音**:`nvidia-smi -pl 400` + `nvidia-smi -lgc 0,1500`
   已设,**任何情况下不得恢复默认功率/频率**(用户明令)。实测 27B 推理
   103W/41°C/风扇30%,这是正常状态。
2. **禁用付费 API**:一切 LLM 调用走本地 vLLM(:8001)。ds_proxy(:8088)
   的上游是付费 DeepSeek,**不要**把 DS_PROXY_URL 留默认值。
3. **box 会杀断连进程**:最后一个 SSH 会话关闭 ~13 秒后,tmux/nohup 全被杀
   (Windows 侧行为,无法关闭)。**长任务必须配 SSH 心跳**:
   ```bash
   # 工作站侧后台循环, 每 12s 一发
   while true; do timeout 25 ssh my5090 "echo hb" >/dev/null 2>&1; sleep 12; done &
   ```
   我的心跳随本会话结束会停 → **接手第一件事就是自己起心跳,然后检查
   vllm27/pilot1/zimenum 三个 tmux 是否还活着,死了按 §4 复活**。
4. **隧道 ~50% 连接成功率**:每条 ssh 前跑 recon 重试循环
   (ControlMaster + ControlPath=/tmp/.../cm-my5090 复用连接);
   命令输出为空 ≠ 失败,先重试。
5. **cmd→wsl→bash 引号会被吃**:不要内联复杂命令;**先把脚本 cat 到箱上
   文件再执行**(本文所有脚本已在箱上,直接用)。

## 1. 目标与验收

**试点(todo #38)**:3 agents(camel-ai / deerflow / smolagents)×
13 题(每簇一题)× 本地 Qwen3.6-27B-AWQ ⇒ 39 份真实报告
(`data/results/deep/<agent>__<task>_pilot.md`,>3KB 算成)。

**验收**:①报告非空非错误页;②vLLM 日志里 `POST /v1/chat` 请求数随任务
增长;③拉回工作站后 `build_truth_board.py` 能出榜且轴分有区分度。

**通过后(todo #39)**:TASKS 扩到全部 100 题、agents 酌情加
(gpt-researcher/langchain-odr/storm,各有专属 venv,见 §3),跑全量。

## 2. 当前状态(2026-07-03 ~04:00 交接时刻)

- ✅ 沙箱四件套健康:magento **:17770**(不是 7770!)、postmill :9999、
  kiwix :8090、shim :8081(`/healthz` 返回 ok)、ds_proxy :8088
- ✅ vLLM 27B 已就绪过:`qwen3.6-27b-awq` @ :8001,PROBE-OK
  (**如果被 box 杀了**:`tmux new -d -s vllm27 'bash /root/pilot_v2/vllm27_up.sh > /root/pilot_v2/up.log 2>&1'`,
  加载 ~5 分钟,等 up.log 出 `VLLM-READY`)
- ✅ v2 任务 100/100 已上箱(v1 备份在 `cross_site_deep_v1_backup/`)
- 🔄 **单发验证进行中**(tmux `pilot1`:camel-ai × 0001,带 tiktoken 缓存
  的重试):看 `/root/pilot_v2/single_test.log` 尾部 +
  `wc -c /opt/deep_reserch/data/results/deep/camel-ai__dr_cross_deep_0001_pilot.md`
  —— **>3KB 即通过,可放全量**
- 🔄 wiki 全量枚举(tmux `zimenum`,todo #40):`/tmp/zim_enum.log` 看进度,
  产物 `/tmp/wiki_full_enum.txt`(拉回后重建 url_registry,见 §6)
- 判官重判素材未动:`/root/local_jury/`(123 场断点,relaunch.sh 可续,todo #15)

## 3. 箱端地图(全部已存在,勿重建)

| 东西 | 位置 |
|---|---|
| 仓库 | `/opt/deep_reserch`(WSL Ubuntu;`wsl -d Ubuntu -- bash ...`)|
| 单任务跑器 | `scripts/run_deep_task.py --agent X --task Y --backbone Z --out-suffix pilot` |
| **正宗发射器** | `scripts/pilot_oneagent.sh`(我从 smoke_deep_oneagent.sh 克隆,底模吃 `$BACKBONE` 环境变量;**按 agent 自动选 venv,必须用它**)|
| venv 地图 | 每框架一个:`.venv-smol` `.venv-camel`(deerflow 也用它)`.venv-gptr` `.venv-storm` `.venv-langchain-odr` `.venv-ldr312` 等 14 个;**裸 python3 全会 import 炸** |
| 试点驱动 | `/root/pilot_v2/pilot_driver.sh`(3×13 断点续跑,>3KB 才 SKIP)|
| vLLM 起服 | `/root/pilot_v2/vllm27_up.sh`(**必须 --enforce-eager**,WSL 上 CUDA graph 捕获会崩;--max-model-len 20480 --gpu-mem 0.88)|
| tiktoken 缓存 | `/root/tiktoken_cache/`(o200k+cl100k 已放;跑任务时 **必须 export TIKTOKEN_CACHE_DIR=/root/tiktoken_cache**)|
| 任务/报告 | `data/tasks/deep_research/cross_site_deep/`(v2)/ `data/results/deep/` |

## 4. 已踩的坑(照此办理,不要重踩)

1. **裸 python3 跑框架** → 全部 ModuleNotFoundError 秒败(还会因报告非空
   误标完成)。→ 只用 `pilot_oneagent.sh`。
2. **runner 清空代理变量断外网** → camel 下载 tiktoken 词表 SSL 崩。
   → 词表已离线放 `/root/tiktoken_cache`,驱动里已 export;若新框架要
   下别的资源,同法:工作站下好、按其缓存键名船过去。
3. **camel 不认 qwen3.6-27b-awq** → 上下文当 1e9(曾产生 max_tokens 超限
   的 400)。camel 自身 max_tokens=8192 已兜底;若再见 400,患处是别的
   框架把 max_tokens 设成 (context-prompt),对症限死即可。
4. **孤儿 CUDA 上下文钉死显存**(vLLM 崩溃残留,pkill 无用)→ 唯一解
   `wsl --shutdown`(Windows 侧执行)+ 重启后 `bash /tmp/stack_up.sh`
   (起 docker+全栈)。本次 docker 顺利回来;若 wedge,修复见
   memory[my5090-sandbox-recovery]。
5. **kiwix 8090 端口抢占**(boot.sh 的静态 kiwix 和 docker wiki 容器打架)
   → 杀 tmux `wiki` 会话 + `docker restart dr_sandbox_wiki`。
6. **vLLM 起服自杀坑**:`pkill -9 -f vllm` 会匹配自己 → 用
   `pkill -9 -f '[v]llm serve'`(方括号技巧,脚本里已写对)。
7. 模型在 /mnt/e(9P 文件系统),27B 加载 ~4 分钟,是正常的,别提前判死。

## 5. 接手操作序(试点 → 全量)

```bash
# ① 心跳(工作站后台,全程保持)
# ② 检查三个 tmux + 服务健康:
wsl -d Ubuntu -- bash /tmp/final_check.sh     # 全栈+vLLM 一屏
# ③ 看单发验证:
tail /root/pilot_v2/single_test.log
wc -c /opt/deep_reserch/data/results/deep/camel-ai__dr_cross_deep_0001_pilot.md
#    >3KB → ④;失败 → 读日志对症(§4),修后重放 pilot1
# ④ 放全量试点:
tmux new -d -s pilot 'TIKTOKEN_CACHE_DIR=/root/tiktoken_cache bash /root/pilot_v2/pilot_driver.sh > /root/pilot_v2/driver.log 2>&1'
#    盯 driver.log 的 "=== DONE ... size=";smolagents/deerflow 若露新坑,对症修
# ⑤ 拉回报告(gzip+重试;13 份 × 3 agents,~1-2MB):
cd /opt/deep_reserch/data/results/deep && tar czf /tmp/pilot_reports.tgz *_pilot.md
#    (工作站) ssh my5090 "wsl -d Ubuntu -- cat /tmp/pilot_reports.tgz" > ... && gzip -t 验证
```

## 6. 评分与出榜(工作站侧,全部就绪)

```bash
cd /root/Desktop/lyb/deep_reserch
# 报告摆成 <agent>/<task_id>.md 布局(去掉 __ 和 _pilot 后缀):
#   pilot_boards/camel-ai/dr_cross_deep_0001.md ...
python3 scripts/build_truth_board.py --reports-dir pilot_boards \
  --out data/results/real/truth_board_pilot.json
# 注意: 无页面缓存时 pof 轴=0(地板 0.05, 已知限制); 如需 pof 真值,
# 用箱上 sandbox_cache.json(43k URL)当 --cache
```
预期:诚实系统 truth ~0.2-0.5,若有系统伪造 URL 会被注册表压到 <0.05。
出榜后:更新 todo #38→completed、#39 开跑;把榜和轴分布贴给用户。

## 7. 交接时的未完事项(不归试点,别顺手乱动)

- `zimenum` 跑完后:`/tmp/wiki_full_enum.txt` 拉回工作站
  `data/golden/registry_src/wiki_full_enum.txt`,再
  `python3 scripts/build_url_registry.py --wiki-list <新文件> ...`
  重建注册表 + registry meta 标 `wiki_complete: true`(todo #40)
- 重判恢复(#15):`/root/local_jury/relaunch.sh`,与试点**不能同时**
  (共享 :8001 和显存)——先试点后重判
- 论文侧另有会话在改(§3/§5.6 mock),不要碰 paper_iclr/
