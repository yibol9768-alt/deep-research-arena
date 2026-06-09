cd /opt/deep_reserch
. /root/.config/dra/status.env
while true; do
  python3 - <<'PY' > /tmp/dra_status.json 2>/dev/null
import json, subprocess, glob, os, datetime
def sh(c):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception: return ""
tasks=[]
ck=sh("wc -l < data/results/real/leaderboard_jury_elo.json.battles.jsonl 2>/dev/null") or "0"
done=os.path.exists("data/results/real/leaderboard_jury_elo.json")
jp=sh("pgrep -fc build_real_leaderboard") or "0"
tasks.append({"name":"Jury re-judge (3 judges x 1553 battles)","nameZh":"陪审团重判（3 判官 × 1553 场）",
  "progress":int(ck),"total":1553,"state":"done" if done else ("running" if int(jp)>0 else "dead")})
for m,zh in [("qwen3-32b","qwen3-32b 基线"),("qwen3-max","qwen3-max 基线"),("qwen-flash","qwen-flash 基线"),
             ("qwen3-30b-a3b-instruct-2507","qwen3-30b-a3b 基线"),("deepseek-v4-flash","deepseek-v4-flash 基线")]:
    n=len(glob.glob(f"data/results/deep/eff-{m}__*_matrix.md"))
    if n: tasks.append({"name":f"{m} baseline","nameZh":zh,"progress":n,"total":94,
        "state":"done" if n>=94 else "paused"})
sandbox={}
for p in ("7770","9999","8090","8081"):
    c=sh(f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 http://localhost:{p}/")
    sandbox[p]=int(c) if c.isdigit() and c!="000" else "down"
errs=sh("grep -h -iE 'FAILED|ERROR' .dra_tmp/*.log 2>/dev/null | tail -4").splitlines()
st={"ts":datetime.datetime.utcnow().isoformat()+"Z","host":"my5090","tasks":tasks,
    "sandbox":sandbox,"sessions":sh("tmux ls 2>/dev/null | cut -d: -f1").split(),
    "watchdog_heartbeat":sh("cat .dra_tmp/watchdog.heartbeat 2>/dev/null"),
    "errors_tail":errs[:4]}
print(json.dumps(st))
PY
  curl -s --max-time 15 -X POST -H "Content-Type: application/json" -H "X-Status-Token: $STATUS_TOKEN" \
    --data @/tmp/dra_status.json https://www.deepresearcharena.com/api/status > /tmp/dra_status_post.out 2>&1
  sleep 60
done
