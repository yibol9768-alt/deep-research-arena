# my5090 沙箱灾难恢复手册

> 现象:WSL 重启后,评测沙箱(部分)挂掉;`/status` 页变红或某些端口不响应。
> 本文档记录:**为什么会坏**、**怎么(脱离 docker)复活**、**怎么验证**。
> 配套长期记忆:`my5090-sandbox-recovery`。

## 沙箱五件套(全部要活)

| 端口 | 服务 | 怎么跑(恢复后) |
|---|---|---|
| 7770 | shopping (Magento) | 幽灵 docker 引擎里还活着,别动 |
| 9999 | forum (Postmill) | 同上 |
| 8090 | wiki (Kiwix) | **kiwix 静态二进制**:`/opt/kiwix/kiwix-serve --port 8090 /opt/corpus/wiki/wikipedia_en_all_nopic.zim` |
| 8081 | search shim (FastAPI) | `uvicorn integrations.search_shim.app:app --host 0.0.0.0 --port 8081` |
| 8088 | ds_proxy (FastAPI) | `OPENAI_PROXY_UPSTREAM=https://api.deepseek.com uvicorn integrations.ds_proxy.app:app --host 0.0.0.0 --port 8088` |

## 为什么会坏(三重故障叠加)

1. **WSL 重启杀掉所有 tmux**(jury、watchdog、shim、ds_proxy、wiki 全没)。
2. **docker 被卡死**:重启后 Ubuntu 的 docker CLI 指向一个**空引擎**(`docker ps`
   在 `default` 和 `desktop-linux` 两个 context 里都是 0),而原来跑 7770/9999 的
   容器困在一个 CLI 够不着的**"幽灵引擎"**里。`~/.docker/config.json` 里的
   `"credsStore":"desktop.exe"` 让每次 `docker compose` 都去调那个凭证助手,WSL
   重启后它必失败:`error getting credentials ... A specified logon session does
   not exist`。
3. **box 连不上镜像仓库**:`docker.io` / `registry-1.docker.io` 超时(000),
   `ghcr.io` 返回 401。**无法 pull/重建任何镜像**。自定义镜像
   (shopping_final_0712 / postmill-populated-exposed-withimg)够不着 ->
   要真修 docker 必须在 Windows 上重启 Docker Desktop。

## 脱离 docker 的复活(不需要镜像、不需要仓库)

1. 去掉坏掉的凭证助手:`echo '{}' > ~/.docker/config.json`(本地镜像无需 auth)。
2. 7770 / 9999 由幽灵引擎继续服务 —— 别去 `compose up` 它们(会在空引擎里报
   "No such image")。
3. wiki:kiwix 是**静态二进制**(.zim 在 `/opt/corpus/wiki/`,49GB)。
   `download.kiwix.org` 可达(Docker Hub 不可达),二进制已放
   `/opt/kiwix/kiwix-serve`(v3.8.2)。
   - 注意:kiwix 3.8.2 把 `/content/<book>/<Article>` 当 200,把老的 `/A/` 形式
     302 重定向;shim 返回的是 200 那种,新引用可达。旧 agent 的 `/A/` 引用已在
     冻结缓存里记为 200,不受影响。
4. shim / ds_proxy 都是纯 FastAPI,用 uvicorn 跑(见上表),不碰 docker。
5. 以上三个已写进 `/opt/deep_reserch/.dra_tmp/boot.sh`(幂等),Windows 的
   `DRA_StackGuard` 计划任务每 5 分钟跑一次 boot.sh,WSL 重启后自动复活整套。

## 验证(五个端口都要对)

```
:7770=200  :9999=200  :8090=200
:8081 -> GET / 是 404 但 POST /search 是 200
:8088 -> GET / 是 404 但 POST /v1/chat/completions 是 200(经 ds_proxy 打到 deepseek)
```
一行自检:
```
for p in 7770 9999 8090 8081 8088; do printf ":%s=%s " $p "$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 http://localhost:$p/)"; done
curl -s -X POST -H 'Content-Type: application/json' -d '{"query":"coffee","max_results":3}' http://localhost:8081/search | head -c 120
```

## 什么时候才需要沙箱

- **判官重打分 / 真值门控建榜**:不需要活沙箱(走冻结缓存
  `data/results/sandbox_cache.json`)。
- **生成新报告**(eff 跑批、矩阵填格、claude-code/opencode):**需要**活沙箱
  (shim 8081 + 对应后端;claude-code 另需 ds_proxy 8088 + ccr 3456 + Windows
  上的 claude.exe)。

## 教训(已固化)

- 长任务四件套:tmux 常驻 + 断点续跑 + 看门狗(救"死"也救"卡死") + 流式日志。
- 看门狗别误杀聚合阶段(BT+bootstrap 期间 checkpoint 不前进 != 卡死;ckpt 接近
  完成时禁用卡死击杀)。
- 远程命令一律 `ssh my5090 'bash -s' <<'EOF' ... EOF`;经 Windows cmd 的单行命令
  引号会被粉碎。写远端脚本用**带引号的** heredoc,否则本地会先展开 `$VAR`。
- 写凭证类 secret 到仓库会被安全分类器拦(STATUS_TOKEN/钥匙只进 box 本地 env 或
  CF dashboard secret,绝不入库)。
