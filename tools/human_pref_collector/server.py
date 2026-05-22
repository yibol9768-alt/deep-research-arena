"""Tiny stdlib HTTP server for the Human Pairwise Preference Collector.

Run from the repository root:

    python tools/human_pref_collector/server.py --port 8000

Endpoints:

    GET  /        -> serves index.html
    GET  /pairs   -> next unannotated pair (or {"done": true} when finished)
    POST /save    -> appends a JSON preference record to
                     data/human_prefs/prefs.jsonl and advances the queue.

The pair queue lives at
``tools/human_pref_collector/pair_queue.jsonl`` and is auto-generated from
``data/results/deep_v3/leaderboard_deep.json`` (top-5 agents x 30 tasks ->
300 pairs, randomised) when missing. Each line:

    {"task_id": ..., "agent_a": ..., "agent_b": ...}

Annotated cursor is stored at
``tools/human_pref_collector/.cursor`` (single integer).

No external dependencies; pure stdlib so the collector can run on the
jump host without touching the project venv.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

INDEX_HTML = HERE / "index.html"
PAIR_QUEUE = HERE / "pair_queue.jsonl"
CURSOR_FILE = HERE / ".cursor"

PREFS_DIR = ROOT / "data" / "human_prefs"
PREFS_FILE = PREFS_DIR / "prefs.jsonl"

LEADERBOARD_JSON = ROOT / "data" / "results" / "deep_v3" / "leaderboard_deep.json"
REPORTS_DIR = ROOT / "data" / "results" / "deep"  # <agent>__<task>.md
TASK_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
GOLDEN_DIR = ROOT / "data" / "golden" / "deep"


# ---------------------------------------------------------------------------
# Queue construction
# ---------------------------------------------------------------------------

def _top_agents_from_leaderboard(k: int = 5) -> list[str]:
    if not LEADERBOARD_JSON.exists():
        # Best-effort: scan reports dir for distinct agent prefixes.
        if REPORTS_DIR.exists():
            agents = sorted({p.name.split("__", 1)[0] for p in REPORTS_DIR.glob("*.md")})
            return agents[:k]
        return []
    data = json.loads(LEADERBOARD_JSON.read_text())
    elo = data.get("elo_v2_ci") or {}
    ranked = sorted(elo.items(), key=lambda kv: -float(kv[1].get("elo") or 0))
    return [a for a, _ in ranked[:k]]


def _tasks_from_leaderboard(n: int = 30) -> list[str]:
    if LEADERBOARD_JSON.exists():
        data = json.loads(LEADERBOARD_JSON.read_text())
        tasks = data.get("tasks") or []
        if tasks:
            return list(tasks[:n])
    if TASK_DIR.exists():
        return sorted(p.stem for p in TASK_DIR.glob("dr_cross_deep_*.json"))[:n]
    return []


def _build_pair_queue(k_agents: int = 5, n_tasks: int = 30, seed: int = 17) -> int:
    agents = _top_agents_from_leaderboard(k_agents)
    tasks = _tasks_from_leaderboard(n_tasks)
    if len(agents) < 2 or not tasks:
        # Not enough material -- write an empty queue and let the UI show "done".
        PAIR_QUEUE.write_text("")
        return 0
    pairs: list[dict] = []
    for t in tasks:
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                pairs.append({"task_id": t, "agent_a": agents[i], "agent_b": agents[j]})
    rng = random.Random(seed)
    rng.shuffle(pairs)
    PAIR_QUEUE.write_text("\n".join(json.dumps(p) for p in pairs) + "\n")
    return len(pairs)


def _ensure_queue() -> list[dict]:
    if not PAIR_QUEUE.exists() or PAIR_QUEUE.stat().st_size == 0:
        _build_pair_queue()
    if not PAIR_QUEUE.exists():
        return []
    lines = [ln for ln in PAIR_QUEUE.read_text().splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def _read_cursor() -> int:
    if not CURSOR_FILE.exists():
        return 0
    try:
        return int(CURSOR_FILE.read_text().strip() or 0)
    except ValueError:
        return 0


def _write_cursor(i: int) -> None:
    CURSOR_FILE.write_text(str(i))


# ---------------------------------------------------------------------------
# Task / report hydration
# ---------------------------------------------------------------------------

def _hydrate_pair(pair: dict) -> dict:
    task_id = pair["task_id"]
    agent_a = pair["agent_a"]
    agent_b = pair["agent_b"]

    task_intent = ""
    must_cite: list[str] = []
    task_path = TASK_DIR / f"{task_id}.json"
    if task_path.exists():
        try:
            tj = json.loads(task_path.read_text())
            task_intent = tj.get("intent", "") or ""
        except Exception:
            pass

    golden_path = GOLDEN_DIR / f"{task_id}.json"
    if golden_path.exists():
        try:
            gj = json.loads(golden_path.read_text())
            mc = gj.get("must_cite") or gj.get("must_cite_urls") or []
            if isinstance(mc, list):
                must_cite = [str(u) for u in mc]
        except Exception:
            pass

    def _load_report(agent: str) -> str:
        # Try canonical filenames in priority order.
        candidates = [
            REPORTS_DIR / f"{agent}__{task_id}.md",
            REPORTS_DIR / f"{agent}__{task_id}_matrix.md",
            REPORTS_DIR / f"{agent}__{task_id}_smoke.md",
        ]
        for c in candidates:
            if c.exists():
                return c.read_text(errors="replace")
        return f"_(no report file found at `data/results/deep/{agent}__{task_id}.md`)_"

    return {
        "task_id": task_id,
        "agent_a": agent_a,
        "agent_b": agent_b,
        "task_intent": task_intent,
        "must_cite_urls": must_cite,
        "report_a_md": _load_report(agent_a),
        "report_b_md": _load_report(agent_b),
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # noqa: A003 - stdlib API
        # Keep stdout clean unless debugging.
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            if not INDEX_HTML.exists():
                self._send_text(404, b"index.html missing", "text/plain")
                return
            self._send_text(200, INDEX_HTML.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/pairs":
            queue = _ensure_queue()
            cursor = _read_cursor()
            total = len(queue)
            if cursor >= total:
                self._send_json(200, {"done": True, "total": total, "cursor": cursor})
                return
            pair = queue[cursor]
            payload = _hydrate_pair(pair)
            payload["cursor"] = cursor
            payload["total"] = total
            self._send_json(200, payload)
            return
        if path == "/healthz":
            self._send_json(200, {"ok": True})
            return
        self._send_text(404, b"not found", "text/plain")

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        if path != "/save":
            self._send_text(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            self._send_json(400, {"error": f"bad json: {e}"})
            return
        required = ("task_id", "agent_a", "agent_b", "winner", "annotator", "timestamp")
        missing = [k for k in required if k not in obj]
        if missing:
            self._send_json(400, {"error": f"missing fields: {missing}"})
            return
        if obj["winner"] not in ("a", "b", "tie"):
            self._send_json(400, {"error": "winner must be a|b|tie"})
            return
        obj.setdefault("dims_cited", [])
        PREFS_DIR.mkdir(parents=True, exist_ok=True)
        with PREFS_FILE.open("a") as f:
            f.write(json.dumps(obj) + "\n")
        _write_cursor(_read_cursor() + 1)
        self._send_json(200, {"ok": True, "cursor": _read_cursor()})


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--rebuild-queue", action="store_true",
                    help="Regenerate pair_queue.jsonl from leaderboard before serving.")
    args = ap.parse_args()
    if args.rebuild_queue and PAIR_QUEUE.exists():
        PAIR_QUEUE.unlink()
        if CURSOR_FILE.exists():
            CURSOR_FILE.unlink()
    queue = _ensure_queue()
    sys.stderr.write(
        f"[server] queue size={len(queue)}  cursor={_read_cursor()}  "
        f"prefs={PREFS_FILE}\n"
    )
    httpd = HTTPServer((args.host, args.port), Handler)
    sys.stderr.write(f"[server] listening on http://{args.host}:{args.port}/\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n[server] shutting down\n")
        httpd.server_close()


if __name__ == "__main__":
    main()
