"""Annotation web server for the lighthouse Phase B work.

One FastAPI app on localhost:5050 with three workflows. Open your
browser, click through, no terminal needed.

  /              landing page with 3 cards + progress
  /b1            B.1 quote-span review (494 cards, k/r/e per card)
  /b2            B.2 must-cite picker (browse URL universe, tick 60-80)
  /b3            B.3 human-baseline editor (markdown + 4h timer)

Run from the repo root:
    cd /Users/liuyibo/Desktop/lyb/deep_reserch
    python3 scripts/annotation_server.py
Then visit http://localhost:5050/

State files (auto-created):
    data/annotation/0001/quote_review.json    — verdicts per span
    data/annotation/0001/reviewer_must_cite.json  — your must-cite list
    data/annotation/0001/baseline.md          — your report
    data/annotation/0001/baseline.notes.md    — your notes
    data/annotation/0001/baseline.session.json — timer state
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
except ImportError:
    sys.exit("pip install fastapi uvicorn")


ROOT = Path(__file__).resolve().parents[1]
TASK_ID = os.environ.get("ANNOTATION_TASK", "dr_cross_deep_0001")
ANN_DIR = ROOT / "data" / "annotation" / TASK_ID.split("_")[-1]
ANN_DIR.mkdir(parents=True, exist_ok=True)


def _load_task() -> dict:
    p = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / f"{TASK_ID}.json"
    return json.loads(p.read_text())


def _load_golden() -> dict:
    p = ROOT / "data" / "golden" / "deep" / f"{TASK_ID}.json"
    return json.loads(p.read_text())


def _expand(s: str) -> str:
    return (s.replace("__SHOPPING__", "http://localhost:7770")
              .replace("__REDDIT__",   "http://localhost:9999")
              .replace("__WIKIPEDIA__", "http://localhost:8090"))


# ─────────────────────────────────────────────────────────────────────────────
# B.1 state
# ─────────────────────────────────────────────────────────────────────────────

B1_STATE = ANN_DIR / "quote_review.json"


_USELESS_PREDICATES = {
    "product_url",          # the URL itself, not a page-supported fact
    "feature_claim",        # wrapper around the specific feature predicate
    "thread_classification",  # derived locally, not a quote-supported fact
    "wiki_defines",         # already covered by the wiki page being cited
}


def _b1_load() -> dict:
    if B1_STATE.exists():
        return json.loads(B1_STATE.read_text())
    g = _load_golden()
    seen_url_span: set[tuple[str, str]] = set()
    cards = []
    for i, t in enumerate(g.get("triples", [])):
        span = (t.get("quoted_span") or "").strip()
        if not span:
            continue
        if t.get("predicate") in _USELESS_PREDICATES:
            continue
        url = t.get("source_url", "")
        key = (url, span)
        if key in seen_url_span:
            continue
        seen_url_span.add(key)
        cards.append({
            "i": i,
            "subject":   t.get("subject", "")[:200],
            "predicate": t.get("predicate", ""),
            "object":    str(t.get("object", ""))[:200],
            "url":       url,
            "span":      span,
            "verdict":   None,   # null | "keep" | "reject" | "edit"
            "edited_span": None,
        })
    state = {"task_id": TASK_ID, "cards": cards, "cursor": 0}
    B1_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    return state


def _b1_save(state: dict) -> None:
    B1_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ─────────────────────────────────────────────────────────────────────────────
# B.2 state
# ─────────────────────────────────────────────────────────────────────────────

B2_REVIEWER = ANN_DIR / "reviewer_must_cite.json"
B2_SCRAPER = ANN_DIR / "scraper_must_cite.json"


def _b2_init() -> None:
    g = _load_golden()
    if not B2_SCRAPER.exists():
        B2_SCRAPER.write_text(json.dumps(
            [e["url"] for e in g.get("must_cite_urls", [])], indent=2))
    if not B2_REVIEWER.exists():
        B2_REVIEWER.write_text(json.dumps([], indent=2))


def _b2_universe() -> list[dict]:
    g = _load_golden()
    seen: dict[str, dict] = {}
    for e in g.get("expected_pool_urls", []):
        seen.setdefault(e["url"], e)
    for e in g.get("must_cite_urls", []):
        seen.setdefault(e["url"], e)
    rows = []
    for url, e in seen.items():
        rows.append({
            "url": url,
            "category": e.get("category", ""),
            "why": e.get("why", "")[:120],
            "domain": ("shopping" if "7770" in url
                       else "reddit" if "9999" in url
                       else "wiki"   if "8090" in url
                       else "other"),
        })
    rows.sort(key=lambda r: (r["domain"], r["url"]))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# B.3 state
# ─────────────────────────────────────────────────────────────────────────────

B3_REPORT = ANN_DIR / "baseline.md"
B3_NOTES  = ANN_DIR / "baseline.notes.md"
B3_SESS   = ANN_DIR / "baseline.session.json"

REPORT_TEMPLATE = """# Human Baseline — {task_id}

(Write the full report here. Format: markdown, every cited fact must be
`[label](http://localhost:7770|9999|8090/...)`. Include a References
section at the end with `[N] [title](url)` lines. See the rules panel.

Phases:
- 0:00–0:45  exploration (no writing)
- 0:45–2:45  drafting + citing in-line
- 2:45–3:30  cross-source synthesis section
- 3:30–4:00  bibliography + URL validation

Sandbox URL aliases:
- __SHOPPING__   = http://localhost:7770
- __REDDIT__     = http://localhost:9999
- __WIKIPEDIA__  = http://localhost:8090

DO NOT use any LLM, no agent, no scripts. Browser only.)

## Executive summary

## (A) Product landscape

## (B) Community sentiment

## (C) Technical grounding

## (D) Cross-source synthesis

## Top 10 buy list

## References
"""


def _b3_init() -> None:
    if not B3_REPORT.exists():
        B3_REPORT.write_text(REPORT_TEMPLATE.format(task_id=TASK_ID))
    if not B3_NOTES.exists():
        B3_NOTES.write_text(f"# Notes — {TASK_ID}\n\n")
    if not B3_SESS.exists():
        B3_SESS.write_text(json.dumps({"task_id": TASK_ID, "started_at": None}))


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────

def _shell(body: str, title: str = "Annotation") -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{title}</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;margin:0;padding:0;background:#f6f6f6;color:#222}}
  nav{{background:#222;color:#fff;padding:.6rem 1rem;display:flex;gap:1.5rem;align-items:center}}
  nav a{{color:#fff;text-decoration:none;opacity:.7}}
  nav a.on,nav a:hover{{opacity:1;text-decoration:underline}}
  .wrap{{max-width:1200px;margin:1.5rem auto;padding:0 1rem}}
  .card{{background:#fff;border-radius:8px;padding:1.5rem;margin-bottom:1rem;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
  h1{{margin-top:0}}
  button{{padding:.6rem 1.2rem;font-size:1rem;cursor:pointer;border:none;border-radius:6px;font-weight:600}}
  .btn-keep{{background:#28a745;color:#fff}}
  .btn-reject{{background:#dc3545;color:#fff}}
  .btn-edit{{background:#ffc107;color:#222}}
  .btn-skip{{background:#6c757d;color:#fff}}
  .btn-back{{background:#0066cc;color:#fff}}
  button:hover{{opacity:.85}}
  .url{{color:#06c;font-size:.85rem;word-break:break-all}}
  .progress{{height:8px;background:#eee;border-radius:4px;overflow:hidden;margin:.5rem 0 1rem}}
  .progress div{{height:100%;background:#28a745;transition:width .3s}}
  pre{{background:#f4f4f4;padding:1rem;border-radius:6px;white-space:pre-wrap;font-size:.85rem;max-height:400px;overflow-y:auto}}
  .span-display{{background:#fffbe6;border-left:4px solid #ffc107;padding:.7rem 1rem;margin:.7rem 0;font-size:1rem;line-height:1.45}}
  .meta{{color:#666;font-size:.85rem}}
  .domain-bar{{display:flex;gap:.5rem;margin-bottom:.6rem}}
  .domain-bar button{{padding:.3rem .8rem;font-size:.85rem}}
  .url-row{{padding:.3rem .5rem;border-bottom:1px solid #eee;font-size:.85rem;display:flex;gap:.5rem;align-items:start}}
  .url-row:hover{{background:#fff8e1}}
  textarea{{width:100%;font-family:Menlo,monospace;font-size:.85rem;border:1px solid #ccc;border-radius:6px;padding:.6rem}}
  .stats{{font-size:.85rem;color:#666;margin:.5rem 0}}
  .small{{font-size:.85rem}}
  .row{{display:flex;gap:1rem;align-items:start}}
  .col{{flex:1}}
  details>summary{{cursor:pointer;font-weight:600;padding:.3rem 0}}
  .timer{{font-size:1.2rem;font-weight:700;color:#dc3545}}
</style>
</head><body>
<nav>
  <strong>Lighthouse 0001 annotation</strong>
  <a href="/" class="on">Home</a>
  <a href="/b1">B.1 quote review</a>
  <a href="/b2">B.2 must-cite</a>
  <a href="/b3">B.3 human baseline</a>
</nav>
<div class="wrap">{body}</div>
</body></html>"""


def _index_html() -> str:
    state1 = _b1_load()
    cards = state1["cards"]
    total = len(cards)
    done = sum(1 for c in cards if c["verdict"])
    keep = sum(1 for c in cards if c["verdict"] == "keep")
    rej = sum(1 for c in cards if c["verdict"] == "reject")
    edt = sum(1 for c in cards if c["verdict"] == "edit")

    _b2_init()
    rev = json.loads(B2_REVIEWER.read_text())
    rev_count = len(rev)

    _b3_init()
    sess = json.loads(B3_SESS.read_text())
    started = sess.get("started_at")
    elapsed = ""
    if started:
        try:
            t0 = datetime.fromisoformat(started.replace("Z", "+00:00")).timestamp()
            mins = int((time.time() - t0) / 60)
            elapsed = f" — elapsed {mins} min"
        except Exception:
            pass

    body = f"""
<h1>Lighthouse Phase B — annotation home</h1>

<div class="card">
<h2>B.1 — quote-span review</h2>
<p>Click through {total} LLM-drafted spans. Each span is the verbatim
text the agent SHOULD cite when claiming the fact. Decide: keep / reject / edit.</p>
<div class="progress"><div style="width:{(100*done/max(1,total)):.0f}%"></div></div>
<p class="stats">{done} / {total} reviewed &nbsp;·&nbsp;
{keep} keep &nbsp;·&nbsp; {rej} reject &nbsp;·&nbsp; {edt} edited</p>
<a href="/b1"><button class="btn-back">Continue B.1 →</button></a>
</div>

<div class="card">
<h2>B.2 — independent must-cite</h2>
<p>Pretend you have not seen the existing must-cite list. Read ONLY the
task intent and tick the URLs you would require an agent to cite (aim
60–80). I'll compute Cohen's κ with the scraper-derived list.</p>
<p class="stats">{rev_count} URLs ticked so far</p>
<a href="/b2"><button class="btn-back">Open B.2 picker →</button></a>
</div>

<div class="card">
<h2>B.3 — human baseline (4-hour run)</h2>
<p>Do the task yourself. Browser only, no LLM. Your composite score is
the human ceiling.</p>
<p class="stats">{'started ' + started + elapsed if started else 'not started'}</p>
<a href="/b3"><button class="btn-back">Open B.3 editor →</button></a>
</div>

<details>
  <summary>Task intent (full text)</summary>
  <pre>{_expand(_load_task().get("intent",""))}</pre>
</details>
"""
    return _shell(body, "Annotation home")


def _b1_html() -> str:
    state = _b1_load()
    cards = state["cards"]
    cursor = state["cursor"]
    total = len(cards)
    done = sum(1 for c in cards if c["verdict"])
    if cursor >= total:
        return _shell(f"""
<div class="card">
<h1>B.1 done!</h1>
<p>All {total} spans reviewed. <a href="/">Back home</a>.</p>
<p class="stats">keep={sum(1 for c in cards if c['verdict']=='keep')}
&nbsp; reject={sum(1 for c in cards if c['verdict']=='reject')}
&nbsp; edit={sum(1 for c in cards if c['verdict']=='edit')}</p>
</div>""", "B.1 done")

    c = cards[cursor]
    pct = 100 * done / max(1, total)
    page_html_body = f"""
<div class="card">
<div class="row" style="justify-content:space-between">
  <div><strong>Card {cursor+1} / {total}</strong> &nbsp;·&nbsp; reviewed: {done}</div>
  <div><a href="/">← back to home</a></div>
</div>
<div class="progress"><div style="width:{pct:.0f}%"></div></div>

<div class="meta">
  <strong>Subject:</strong> {_html_escape(c['subject'])}<br>
  <strong>Predicate:</strong> {_html_escape(c['predicate'])}<br>
  <strong>Object:</strong> {_html_escape(c['object'])}<br>
  <strong>Source URL:</strong> <a class="url" href="{_html_escape(c['url'])}" target="_blank">{_html_escape(c['url'])}</a>
</div>

<div class="span-display">{_html_escape(c['span'])}</div>

<p class="small">Question: does this span actually support the (subject, predicate, object) above?
Open the URL in a tab to confirm if you're unsure.</p>

<div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-top:1rem">
  <button class="btn-keep" onclick="verdict('keep')">✓ Keep (k)</button>
  <button class="btn-reject" onclick="verdict('reject')">✗ Reject (r)</button>
  <button class="btn-edit" onclick="editSpan()">✎ Edit (e)</button>
  <button class="btn-skip" onclick="skip()">→ Skip (s)</button>
  <button class="btn-back" onclick="back()">← Back (b)</button>
</div>
</div>

<script>
function post(verdict, edited){{
  fetch('/b1/verdict', {{method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{cursor:{cursor}, verdict, edited_span: edited}})}})
    .then(()=>location.reload());
}}
function verdict(v){{ post(v, null); }}
function skip(){{
  fetch('/b1/skip', {{method:'POST'}}).then(()=>location.reload());
}}
function back(){{
  fetch('/b1/back', {{method:'POST'}}).then(()=>location.reload());
}}
function editSpan(){{
  const cur = {json.dumps(c['span'])};
  const v = prompt('Edit the span (≤200 chars):', cur);
  if (v && v.trim()) post('edit', v.trim());
}}
document.addEventListener('keydown', e=>{{
  if (e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA') return;
  if (e.key==='k') verdict('keep');
  else if (e.key==='r') verdict('reject');
  else if (e.key==='e') editSpan();
  else if (e.key==='s') skip();
  else if (e.key==='b') back();
}});
</script>
"""
    return _shell(page_html_body, "B.1 quote review")


def _b2_html() -> str:
    _b2_init()
    universe = _b2_universe()
    saved = set(json.loads(B2_REVIEWER.read_text()))
    task = _load_task()
    intent = _expand(task.get("intent", ""))

    rows_html: list[str] = []
    by_dom: dict[str, list[dict]] = {"shopping": [], "reddit": [], "wiki": [], "other": []}
    for r in universe:
        by_dom[r["domain"]].append(r)
    titles = {"shopping": "Shopping (Magento :7770)",
              "reddit":   "Reddit / Postmill (:9999)",
              "wiki":     "Kiwix Wikipedia (:8090)",
              "other":    "Other"}
    for dom in ("shopping", "reddit", "wiki", "other"):
        items = by_dom[dom]
        if not items:
            continue
        rows_html.append(f'<h2>{titles[dom]} — {len(items)} URLs</h2>')
        for r in items:
            url = r["url"]
            checked = " checked" if url in saved else ""
            rows_html.append(
                f'<div class="url-row">'
                f'<input type="checkbox" class="must" data-url="{_html_escape(url)}"{checked} onchange="onTick()">'
                f'<a class="url" href="{_html_escape(url)}" target="_blank">{_html_escape(url)}</a>'
                f'<span class="meta">{_html_escape(r["why"][:80])}</span>'
                f'</div>'
            )

    body = f"""
<div class="card" style="position:sticky;top:0;z-index:10">
  <div class="row" style="justify-content:space-between">
    <div><strong>B.2 — independent must-cite picker</strong></div>
    <div><span class="stats" id="cnt">{len(saved)} ticked</span>
      &nbsp; <a href="/">← home</a></div>
  </div>
  <details>
    <summary>Task intent (read this — do NOT look at the existing must-cite list)</summary>
    <pre>{_html_escape(intent)}</pre>
  </details>
</div>

<div class="card">
{''.join(rows_html)}
</div>

<script>
function selected(){{
  return [...document.querySelectorAll('input.must:checked')].map(x=>x.dataset.url);
}}
function onTick(){{
  const urls = selected();
  document.getElementById('cnt').textContent = urls.length + ' ticked';
  fetch('/b2/save', {{method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{urls}})}});
}}
</script>
"""
    return _shell(body, "B.2 must-cite picker")


def _b3_html() -> str:
    _b3_init()
    sess = json.loads(B3_SESS.read_text())
    started = sess.get("started_at")
    report_text = B3_REPORT.read_text()
    notes_text = B3_NOTES.read_text()

    body = f"""
<div class="card">
  <div class="row" style="justify-content:space-between">
    <div><strong>B.3 — Human baseline (4-hour cap)</strong></div>
    <div>
      <span class="timer" id="timer">--:--</span>
      &nbsp; <a href="/">← home</a>
    </div>
  </div>
  <p class="small">{'Started ' + started if started else 'not started'} &nbsp;·&nbsp;
  <button class="btn-back" id="startBtn" onclick="startTimer()">{'Restart timer' if started else 'Start timer'}</button>
  &nbsp; <button class="btn-keep" onclick="saveAll()">Save now</button>
  &nbsp; <button class="btn-skip" onclick="finishAndScore()">Finish & request scoring</button>
  </p>
  <details>
    <summary>Rules (read once)</summary>
    <p class="small">Browser only. No LLM, no scripts. Sandbox URLs only
    (localhost:7770 / 9999 / 8090). Tick every URL you visited into the
    "tabs" textarea below — used as audit trail.</p>
  </details>
</div>

<div class="row">
  <div class="col card">
    <h3>Report (markdown)</h3>
    <textarea id="report" rows="32">{_html_escape(report_text)}</textarea>
  </div>
  <div class="col card">
    <h3>Notes (free-text running log)</h3>
    <textarea id="notes" rows="14">{_html_escape(notes_text)}</textarea>
    <h3>Tabs visited</h3>
    <textarea id="tabs" rows="14" placeholder="paste each visited URL on its own line"></textarea>
  </div>
</div>

<script>
const STARTED = {json.dumps(started)};
function fmt(s){{
  const m = Math.floor(Math.abs(s)/60), sec = Math.floor(Math.abs(s)%60);
  return (s<0?'-':'') + String(m).padStart(2,'0')+':'+String(sec).padStart(2,'0');
}}
function tick(){{
  if (!STARTED) {{ document.getElementById('timer').textContent='not started'; return; }}
  const t0 = new Date(STARTED).getTime()/1000;
  const cap = t0 + 4*3600;
  const now = Date.now()/1000;
  const remaining = cap - now;
  const t = document.getElementById('timer');
  t.textContent = fmt(remaining);
  t.style.color = remaining < 0 ? '#dc3545' : (remaining < 1800 ? '#ffc107' : '#28a745');
}}
setInterval(tick, 1000); tick();
function startTimer(){{ fetch('/b3/start',{{method:'POST'}}).then(()=>location.reload()); }}
function saveAll(){{
  const body = {{
    report: document.getElementById('report').value,
    notes:  document.getElementById('notes').value,
    tabs:   document.getElementById('tabs').value,
  }};
  fetch('/b3/save',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}})
    .then(()=>alert('saved'));
}}
function finishAndScore(){{
  saveAll();
  alert('Saved. Now run on the terminal:\\n\\nset -a && . ./.env && set +a\\npython3 scripts/score_deep_answer.py --task {TASK_ID} --answer {B3_REPORT} --out {ANN_DIR}/baseline.score.json');
}}
let saveTO=null;
['report','notes','tabs'].forEach(id=>{{
  document.getElementById(id).addEventListener('input',()=>{{
    if(saveTO) clearTimeout(saveTO);
    saveTO = setTimeout(saveAll, 1500);
  }});
}});
</script>
"""
    return _shell(body, "B.3 human baseline")


def _html_escape(s: Any) -> str:
    if s is None: return ""
    s = str(s)
    return (s.replace("&", "&amp;").replace("<", "&lt;")
              .replace(">", "&gt;").replace('"', "&quot;"))


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Annotation server")


@app.get("/", response_class=HTMLResponse)
async def index():
    return _index_html()


@app.get("/b1", response_class=HTMLResponse)
async def b1():
    return _b1_html()


@app.post("/b1/verdict")
async def b1_verdict(req: Request):
    body = await req.json()
    state = _b1_load()
    i = int(body["cursor"])
    if 0 <= i < len(state["cards"]):
        state["cards"][i]["verdict"] = body["verdict"]
        if body.get("edited_span"):
            state["cards"][i]["edited_span"] = body["edited_span"]
        state["cursor"] = i + 1
    _b1_save(state)
    return {"ok": True, "cursor": state["cursor"]}


@app.post("/b1/skip")
async def b1_skip():
    state = _b1_load()
    state["cursor"] = min(state["cursor"] + 1, len(state["cards"]))
    _b1_save(state)
    return {"ok": True}


@app.post("/b1/back")
async def b1_back():
    state = _b1_load()
    state["cursor"] = max(state["cursor"] - 1, 0)
    _b1_save(state)
    return {"ok": True}


@app.get("/b2", response_class=HTMLResponse)
async def b2():
    return _b2_html()


@app.post("/b2/save")
async def b2_save(req: Request):
    body = await req.json()
    urls = list(dict.fromkeys(body.get("urls", [])))
    B2_REVIEWER.write_text(json.dumps(urls, indent=2, ensure_ascii=False))
    return {"ok": True, "n": len(urls)}


@app.get("/b3", response_class=HTMLResponse)
async def b3():
    return _b3_html()


@app.post("/b3/start")
async def b3_start():
    sess = json.loads(B3_SESS.read_text())
    sess["started_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    B3_SESS.write_text(json.dumps(sess, indent=2))
    return {"ok": True}


@app.post("/b3/save")
async def b3_save(req: Request):
    body = await req.json()
    if "report" in body:
        B3_REPORT.write_text(body["report"])
    if "notes" in body:
        B3_NOTES.write_text(body["notes"])
    if "tabs" in body:
        (ANN_DIR / "baseline.tabs.txt").write_text(body["tabs"])
    return {"ok": True}


@app.get("/healthz")
async def healthz():
    return {"ok": True, "task_id": TASK_ID, "ann_dir": str(ANN_DIR)}


def main() -> int:
    print()
    print("=" * 60)
    print(f"  Annotation server for {TASK_ID}")
    print(f"  open: http://localhost:5050/")
    print(f"  data: {ANN_DIR}")
    print("=" * 60)
    print()
    uvicorn.run(app, host="127.0.0.1", port=5050)
    return 0


if __name__ == "__main__":
    sys.exit(main())
