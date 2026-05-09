"""Smoke-test every deep-research runner against local LM Studio.

Goal: catch the common ways a DR runner silently regresses to the point where
its score files would be discarded by `_looks_degenerate` and the agent ends up
with no Elo entry. The leaderboard's audit-trail diagnostic shows *that* an
agent is excluded; this script tells you *why* before any score files are
written.

Three tiers, run for each runner module under ``scripts/runners/*_runner.py``:

1. **Import & contract** — does the module load and expose
   ``AGENT_NAME: str`` + ``async def run(intent, model, shim_url, proxy_url, ...)``?
   Failures here mean the registry can't even see the runner. (No LM call.)

2. **LM Studio ping** — issue one tiny chat completion against LM Studio so
   we know the backend is healthy *before* blaming the runner. If this tier
   fails the rest of the report is meaningless.

3. **End-to-end mini run** — call ``run()`` with a per-runner timeout (see
   `_PER_AGENT_TIMEOUT`), the shortest plausible intent, ``qwen3.5-35b-a3b``
   as the backbone, and a tiny in-process mock shim returning canned
   Tavily-style hits. Either we get a non-empty markdown report or we don't.
   Most heavy frameworks (storm needs dspy, ldr needs langgraph, ...) will
   trip the import tier on a Windows dev box without the matching .venv:
   that's expected and the report flags "framework deps missing" plus a
   pip-install hint rather than failing CI.

Per-runner timeouts:
    Subprocess runners (ldr, qx-agents) routinely take ~200s for a real run
    against the mock shim. The default 240s baseline plus a per-agent
    override map (`_PER_AGENT_TIMEOUT`) keeps fast in-process runners from
    waiting full 4 minutes while still giving the slow ones room. The CLI
    `--timeout` becomes the fallback for any agent not in the override map.

Usage:
    python3 scripts/smoke_test_drs.py             # run all
    python3 scripts/smoke_test_drs.py --agents storm deerflow
    python3 scripts/smoke_test_drs.py --no-end-to-end   # skip tier 3
    python3 scripts/smoke_test_drs.py --timeout 240     # baseline timeout

Output: ``data/results/smoke/smoke_<timestamp>.md`` + matching .json so the
report is reproducible in CI. The JSON also embeds the per-agent timeout map
that was in effect, so a future re-run can match the original timing budget.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import http.server
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Windows console defaults to gbk/cp1252 and chokes on the ✅/⚠️/⏭️ glyphs we
# print as a quick status indicator. Re-encode stdout/stderr as UTF-8 so the
# smoke output stays readable on a plain `cmd`/PowerShell session — without
# this the script crashes mid-loop the first time it prints a tier-3 result.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001 — best-effort
            pass

LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")
LM_STUDIO_MODEL = os.environ.get("LM_STUDIO_MODEL", "qwen3.5-35b-a3b")
SMOKE_INTENT = (
    "Compare the price and rating of two arbitrary items. Cite at least one URL "
    "from each source. Keep the report under 500 words."
)
# Baseline budget. ldr / qx-agents launch a child venv subprocess that boots a
# whole framework (langgraph / openai-agents) before the first LM call lands;
# 90s used to false-flag them as failures. 240s is the empirical p95 for a
# subprocess runner against the mock shim with qwen3.5-35b-a3b.
DEFAULT_END_TO_END_TIMEOUT_S = 240
OUT_DIR = ROOT / "data" / "results" / "smoke"

# ---------------------------------------------------------------------------
# Per-agent timeout overrides
# ---------------------------------------------------------------------------
# In-process runners (deepagents, local-deep-researcher, storm, co-storm,
# tongyi-dr, deerflow) finish in <60s when their tier-1 import succeeds: most
# of them fail import on a Windows dev box anyway, so the timeout is moot.
# Subprocess runners (ldr, qx-agents) need the full baseline. Keep this map
# the single source of truth so `--timeout` becomes the fallback only.
_PER_AGENT_TIMEOUT: dict[str, int] = {
    "deepagents": 60,
    "local-deep-researcher": 60,
    "tongyi-dr": 120,
    "deerflow": 120,
    "ldr": 240,
    "qx-agents": 240,
    "storm": 60,
    "co-storm": 60,
}

# ---------------------------------------------------------------------------
# Remediation hints for missing python modules
# ---------------------------------------------------------------------------
# When tier 1 trips ModuleNotFoundError we surface a copy-pasteable pip
# command in the report's Notes section. The static map covers the modules we
# already know map to non-obvious package names (``dspy`` -> ``dspy-ai``, the
# storm umbrella package ``knowledge_storm`` etc). Anything not in the map
# falls back to ``pip install <module-stem>``, which is right ~80% of the
# time for one-word PyPI packages.
_REMEDIATION_HINTS: dict[str, str] = {
    "dspy": ".venv-camel/bin/pip install dspy-ai (or run from .venv-storm)",
    "knowledge_storm": ".venv-camel/bin/pip install knowledge-storm (or run from .venv-storm)",
    "numpy": ".venv-camel/bin/pip install numpy",
    "langgraph": ".venv-camel/bin/pip install langgraph (or run from .venv-ldr312)",
    "langchain": ".venv-camel/bin/pip install langchain",
    "langchain_core": ".venv-camel/bin/pip install langchain-core",
    "langchain_openai": ".venv-camel/bin/pip install langchain-openai",
    "langchain_community": ".venv-camel/bin/pip install langchain-community",
    "openai_agents": ".venv-camel/bin/pip install openai-agents (or run from .venv-qx)",
    "agents": ".venv-camel/bin/pip install openai-agents (or run from .venv-qx)",
    "deepagents": ".venv-camel/bin/pip install deepagents",
    "tongyi": "run from .venv-tongyi (Alibaba-NLP/DeepResearch installs in editable mode)",
    "tavily": ".venv-camel/bin/pip install tavily-python",
    "duckduckgo_search": ".venv-camel/bin/pip install duckduckgo-search",
    "yaml": ".venv-camel/bin/pip install pyyaml",
    "PIL": ".venv-camel/bin/pip install pillow",
    "cv2": ".venv-camel/bin/pip install opencv-python",
    "sklearn": ".venv-camel/bin/pip install scikit-learn",
    "bs4": ".venv-camel/bin/pip install beautifulsoup4",
}

# Catches ``No module named 'foo'`` (with single or double quotes) at the end
# of an error string. We only care about the top-level module stem; submodule
# imports like ``foo.bar.baz`` are reduced to ``foo`` for the install hint
# (pip installs are package-level anyway).
_MISSING_MODULE_RE = re.compile(r"No module named ['\"]([^'\"]+)['\"]")


def _remediation_for(error_text: str) -> str | None:
    """If ``error_text`` looks like a ``ModuleNotFoundError``, return a
    pip-install hint string. Otherwise return None.

    The returned hint is copy-pasteable (no leading ``$`` etc.) so a human
    can paste it straight into a westd shell. We *do not* shell out to pip
    ourselves: the smoke script must remain side-effect-free.
    """
    if not error_text:
        return None
    m = _MISSING_MODULE_RE.search(error_text)
    if not m:
        return None
    full = m.group(1)
    stem = full.split(".", 1)[0]
    # Prefer an exact match on the full dotted path (some projects ship a
    # submodule with a different install package than the top-level), then
    # fall back to the stem, then to the generic pip-install template.
    if full in _REMEDIATION_HINTS:
        cmd = _REMEDIATION_HINTS[full]
    elif stem in _REMEDIATION_HINTS:
        cmd = _REMEDIATION_HINTS[stem]
    else:
        cmd = f".venv-camel/bin/pip install {stem}"
    return f"needs `{full}` -- install with `{cmd}`"


# ---------------------------------------------------------------------------
# Tier 2: LM Studio health check
# ---------------------------------------------------------------------------

def lm_studio_ping(model: str = LM_STUDIO_MODEL, timeout_s: float = 30.0) -> dict:
    """Hit /v1/chat/completions with a one-token prompt. Returns {ok, latency_s, sample, error}.

    We don't trust /v1/models alone — LM Studio can list a model that hasn't
    been loaded into VRAM, in which case /v1/chat/completions is the first
    thing that errors. Prove the backend can complete BEFORE judging runners.
    """
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the literal token OK."}],
        "temperature": 0,
        "max_tokens": 16,
    }).encode("utf-8")
    req = urllib.request.Request(
        LM_STUDIO_URL.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer lmstudio"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            payload = json.loads(r.read())
        dt = time.time() - t0
        sample = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"ok": True, "latency_s": round(dt, 2), "sample": sample[:200]}
    except Exception as e:  # noqa: BLE001 — surface any failure to the report
        return {"ok": False, "latency_s": round(time.time() - t0, 2), "error": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------------------
# Mock shim: stand-in for the Tavily-compatible search shim that lives on
# westd:8081. Returns deterministic dummy hits so a runner can complete a
# search step without real network access. We do *not* try to mimic every
# field — runners that crash on missing fields are themselves a smoke fail.
# ---------------------------------------------------------------------------

class _MockShimHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        # Silence the default per-request stderr spam — the smoke report is
        # what we care about, not a wall of HTTP access logs.
        return

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 — http.server contract
        if self.path.startswith("/health"):
            return self._send_json({"ok": True})
        return self._send_json({"results": []}, status=200)

    def do_POST(self):  # noqa: N802
        # Tavily-like search shape: {"query": "...", "max_results": N, ...}
        # plus the proxy/extract endpoints some runners hit. A canned response
        # is enough — the runner only needs to *not crash* on a real HTTP
        # round-trip. Citations are scored separately by the leaderboard.
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            self.rfile.read(length)
        except Exception:
            pass
        canned = {
            "answer": "Mock smoke-test answer.",
            "results": [
                {
                    "title": "Smoke test product A",
                    "url": "http://localhost:7770/smoke-product-a",
                    "content": "A smoke-test sandbox product with a stable price of $19.99 and a 4-star rating.",
                    "score": 0.91,
                },
                {
                    "title": "Smoke test product B",
                    "url": "http://localhost:7770/smoke-product-b",
                    "content": "A second smoke-test product priced at $24.50 with a 4.5-star rating.",
                    "score": 0.88,
                },
            ],
        }
        self._send_json(canned)


def _start_mock_shim() -> tuple[http.server.HTTPServer, str]:
    """Start the mock shim on an ephemeral port (so parallel smoke runs don't
    fight for 18081). Returns (server, url)."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _MockShimHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, f"http://127.0.0.1:{port}"


# ---------------------------------------------------------------------------
# Tier 3: end-to-end mini run
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class RunnerResult:
    agent: str
    tier1_import: str        # "ok" | error string
    tier3_run: str           # "ok" | "skipped" | error string
    elapsed_s: float = 0.0
    report_chars: int = 0
    report_preview: str = ""


def _set_lm_studio_env() -> dict:
    """Point an OpenAI-compatible runner at LM Studio. Returns the original
    env so the caller can restore it after the smoke run."""
    keys = ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_API_KEY", "DS_PROXY_URL", "JUDGE_BASE_URL", "JUDGE_MODEL")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["OPENAI_BASE_URL"] = LM_STUDIO_URL
    os.environ["OPENAI_API_BASE"] = LM_STUDIO_URL
    os.environ["OPENAI_API_KEY"] = "lmstudio"
    os.environ["DS_PROXY_URL"] = LM_STUDIO_URL
    os.environ["JUDGE_BASE_URL"] = LM_STUDIO_URL
    os.environ["JUDGE_MODEL"] = LM_STUDIO_MODEL
    return saved


def _restore_env(saved: dict) -> None:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


async def _run_one(agent: str, run_fn, shim_url: str, timeout_s: int) -> RunnerResult:
    res = RunnerResult(agent=agent, tier1_import="ok", tier3_run="ok")
    t0 = time.time()
    try:
        coro = run_fn(
            intent=SMOKE_INTENT,
            model=LM_STUDIO_MODEL,
            shim_url=shim_url,
            proxy_url=LM_STUDIO_URL,
        )
        report = await asyncio.wait_for(coro, timeout=timeout_s)
        res.elapsed_s = round(time.time() - t0, 1)
        res.report_chars = len(report or "")
        res.report_preview = (report or "")[:300]
        if not report or len(report) < 80:
            res.tier3_run = f"empty/short report ({res.report_chars} chars)"
    except asyncio.TimeoutError:
        res.elapsed_s = round(time.time() - t0, 1)
        res.tier3_run = f"timeout after {timeout_s}s"
    except TypeError as e:
        # run() didn't accept the keyword args — contract violation that
        # bypassed the registry's signature check (e.g. **kwargs swallowed
        # one of them and the inner code raised). Treat distinctly.
        res.elapsed_s = round(time.time() - t0, 1)
        res.tier3_run = f"signature mismatch: {e}"
    except Exception as e:  # noqa: BLE001 — runner failures are the *signal*
        res.elapsed_s = round(time.time() - t0, 1)
        tb = traceback.format_exc(limit=3)
        res.tier3_run = f"{type(e).__name__}: {e} | {tb.splitlines()[-2] if tb else ''}"
    return res


async def _smoke_main(only: list[str] | None, end_to_end: bool, timeout_s: int) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[smoke] LM Studio: {LM_STUDIO_URL}  model: {LM_STUDIO_MODEL}")
    print(f"[smoke] baseline timeout: {timeout_s}s; per-agent overrides: {sorted(_PER_AGENT_TIMEOUT.items())}")

    # Tier 2 first — no point running tier 3 if the LLM is dead.
    ping = lm_studio_ping()
    if ping["ok"]:
        print(f"[smoke] LM Studio ping: ok in {ping['latency_s']}s — sample: {ping['sample']!r}")
    else:
        print(f"[smoke] LM Studio ping FAILED: {ping['error']}", file=sys.stderr)
        if end_to_end:
            print("[smoke] aborting tier 3 (LM Studio down).", file=sys.stderr)
            end_to_end = False

    # Tier 1: discover registry
    from scripts.runners.registry import discover  # type: ignore
    runners, errs = discover()

    if only:
        runners = {a: f for a, f in runners.items() if a in only}
        for a in only:
            if a not in runners and a not in (e.split("_runner")[0] for e in errs.keys()):
                print(f"[smoke] warn: --agents requested {a!r} but it isn't a registered runner")

    print(f"[smoke] {len(runners)} runners registered, {len(errs)} import errors")
    for stem, why in errs.items():
        print(f"[smoke]   skip (import): {stem}: {why[:140]}")

    results: list[RunnerResult] = []

    if end_to_end and runners:
        shim_server, shim_url = _start_mock_shim()
        saved_env = _set_lm_studio_env()
        try:
            print(f"[smoke] mock shim listening on {shim_url}")
            for agent in sorted(runners.keys()):
                # Per-agent timeout: subprocess runners need ~200s, in-process
                # runners 60s is plenty. CLI --timeout is the fallback for any
                # agent not in _PER_AGENT_TIMEOUT.
                eff_timeout = _PER_AGENT_TIMEOUT.get(agent, timeout_s)
                print(f"[smoke] running {agent} (timeout {eff_timeout}s) ...")
                r = await _run_one(agent, runners[agent], shim_url, eff_timeout)
                status = "✅" if r.tier3_run == "ok" else "⚠️"
                print(f"[smoke]   {status} {agent}: {r.tier3_run}  ({r.elapsed_s}s, {r.report_chars} chars)")
                results.append(r)
        finally:
            shim_server.shutdown()
            _restore_env(saved_env)
    else:
        for a in sorted(runners.keys()):
            results.append(RunnerResult(agent=a, tier1_import="ok", tier3_run="skipped"))

    # Augment with import-failed entries so the report shows everything the
    # caller might be expecting to see.
    for stem, why in errs.items():
        # The agent name is unknown when import fails; use the stem so the row
        # is at least debuggable.
        results.append(RunnerResult(agent=stem, tier1_import=why, tier3_run="skipped (import failed)"))

    return _write_report(results, ping, end_to_end, baseline_timeout=timeout_s)


def _write_report(results: list[RunnerResult], ping: dict, end_to_end: bool, baseline_timeout: int) -> int:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = OUT_DIR / f"smoke_{ts}.md"
    json_path = OUT_DIR / f"smoke_{ts}.json"

    lines = [
        "# Deep-Research smoke test",
        "",
        f"**Timestamp:** {ts}",
        f"**LM Studio:** `{LM_STUDIO_URL}`  ·  **Model:** `{LM_STUDIO_MODEL}`",
        f"**LM Studio ping:** {'✅ ' + str(ping.get('latency_s')) + 's — ' + repr(ping.get('sample', '')) if ping['ok'] else '❌ ' + ping.get('error', 'unknown')}",
        f"**End-to-end runs:** {'yes' if end_to_end else 'no (tier 3 skipped)'}",
        "",
        "## Per-runner results",
        "",
        "| Agent | Tier 1: import | Tier 3: end-to-end | Elapsed (s) | Report chars |",
        "|---|---|---|---:|---:|",
    ]
    n_ok = 0

    def _esc(s: str) -> str:
        # Markdown tables explode if a cell contains an unescaped pipe; some
        # framework tracebacks include `|` (lambda expressions, traceback line
        # separators) and would render as a half-empty row.
        return s.replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    # Collect remediation hints as we walk the rows so the Notes section can
    # include them in the same order as the results table.
    remediation: list[tuple[str, str]] = []  # (agent, hint)

    for r in sorted(results, key=lambda x: x.agent):
        t1 = "✅" if r.tier1_import == "ok" else f"❌ {_esc(r.tier1_import[:120])}"
        if r.tier3_run == "ok":
            t3 = "✅"
            n_ok += 1
        elif r.tier3_run.startswith("skipped"):
            t3 = "⏭️ " + _esc(r.tier3_run)
        else:
            t3 = "⚠️ " + _esc(r.tier3_run[:160])
        lines.append(f"| {r.agent} | {t1} | {t3} | {r.elapsed_s} | {r.report_chars} |")

        # Tier-1 ModuleNotFoundError -> install hint. We deliberately do NOT
        # try to remediate tier-3 errors: those usually mean "framework dep
        # was found but blew up at runtime" and a blind pip install rarely
        # helps.
        if r.tier1_import != "ok":
            hint = _remediation_for(r.tier1_import)
            if hint:
                remediation.append((r.agent, hint))

    # Per-agent timeout summary table so a future re-run can match the timing
    # budget that was in effect for this report.
    timeout_rows = [
        "",
        "## Per-agent timeout (s)",
        "",
        f"Baseline (`--timeout`): **{baseline_timeout}s**. Overrides:",
        "",
        "| Agent | Timeout (s) |",
        "|---|---:|",
    ]
    for agent, t in sorted(_PER_AGENT_TIMEOUT.items()):
        timeout_rows.append(f"| {agent} | {t} |")

    lines += [
        "",
        f"**{n_ok}/{len(results)} runners passed end-to-end.**",
    ] + timeout_rows + [
        "",
        "## Notes",
        "",
        "- Tier 1 catches import / contract violations (wrong signature, missing AGENT_NAME, broken framework deps).",
        "- Tier 3 calls `run()` with the LM Studio backbone and a mock shim; non-empty markdown response = pass.",
        "- 'framework deps missing' on Windows is **expected** for storm/ldr/etc.: those frameworks live in dedicated venvs on westd. Re-run there for the full picture.",
        "- A runner that ranks low on the leaderboard but passes here is a tuning/quality issue, not a wiring issue.",
    ]

    if remediation:
        lines += [
            "",
            "## Remediation hints",
            "",
        ]
        for agent, hint in remediation:
            lines.append(f"- **{agent}** {hint}")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "timestamp": ts,
                "lm_studio_url": LM_STUDIO_URL,
                "lm_studio_model": LM_STUDIO_MODEL,
                "ping": ping,
                "end_to_end": end_to_end,
                "baseline_timeout_s": baseline_timeout,
                # Snapshot the override map exactly as it was used so a
                # future re-run can pin its budget. Sort for stable diffs.
                "per_agent_timeout": dict(sorted(_PER_AGENT_TIMEOUT.items())),
                "remediation": [{"agent": a, "hint": h} for a, h in remediation],
                "results": [dataclasses.asdict(r) for r in results],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"\n[smoke] WROTE {md_path.relative_to(ROOT)}")
    print(f"[smoke] WROTE {json_path.relative_to(ROOT)}")
    print(f"[smoke] {n_ok}/{len(results)} runners passed end-to-end.")
    return 0 if n_ok == len(results) or not end_to_end else 0


def main() -> int:
    overrides = ", ".join(f"{a}={t}s" for a, t in sorted(_PER_AGENT_TIMEOUT.items()))
    ap = argparse.ArgumentParser(
        description=(
            "Smoke-test deep-research runners against LM Studio. "
            "Per-agent timeout overrides live in `_PER_AGENT_TIMEOUT` "
            f"(currently: {overrides}); --timeout is the fallback for any "
            "agent not in that map."
        ),
    )
    ap.add_argument("--agents", nargs="*", help="restrict to these AGENT_NAMEs")
    ap.add_argument("--no-end-to-end", action="store_true",
                    help="run only the registry/import tier (no LLM calls)")
    ap.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_END_TO_END_TIMEOUT_S,
        help=(
            "fallback per-runner end-to-end timeout in seconds (default: "
            f"{DEFAULT_END_TO_END_TIMEOUT_S}). Agents listed in "
            "_PER_AGENT_TIMEOUT use their override instead; this flag is "
            "consulted only for agents not in that map."
        ),
    )
    args = ap.parse_args()
    return asyncio.run(_smoke_main(only=args.agents, end_to_end=not args.no_end_to_end,
                                   timeout_s=args.timeout))


if __name__ == "__main__":
    sys.exit(main())
