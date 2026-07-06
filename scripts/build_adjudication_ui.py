#!/usr/bin/env python3
"""Build a single-file offline HTML UI for contradiction adjudication.

The candidate/reference JSONs cite sandbox URLs (localhost:7770 magento,
localhost:8090 kiwix) that only resolve on the experiment box, so a human
adjudicator cannot open them. This script embeds everything needed to judge
into one static HTML file:

  - stage 1: every unique wiki reference, with the FULL frozen-wiki article
    text inlined (from data/golden/contradictions/wiki_articles/) and the
    ceiling sentence highlighted -> VALID_CEILING / NOT_A_CEILING
  - stage 2: every candidate entry (product name + marketing snippet with the
    claimed number highlighted vs the reference value) -> SUPPORTED_CONFLICT /
    NOT_A_CONFLICT / NUANCE

Progress autosaves to localStorage; "导出" downloads one combined JSON which
scripts/apply_adjudication_export.py splits into the per-cluster
cluster_<name>.adjudication.json files that build_gold_contradictions.py
--promote consumes. The honesty contract is enforced downstream by promote();
the UI only refuses to export a *final* file while anything is unjudged.

Usage:
  python3 scripts/build_adjudication_ui.py \
      [--dir data/golden/contradictions] [--out .../adjudication_ui.html]
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "golden" / "contradictions"


def load_article(articles_dir: Path, topic: str) -> str:
    path = articles_dir / (topic.replace(" ", "_") + ".txt")
    if not path.exists():
        return ""
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    # drop the extractor's TOPIC/FINAL_URL header lines
    while lines and (lines[0].startswith(("TOPIC\t", "FINAL_URL\t"))
                     or not lines[0].strip()):
        lines.pop(0)
    body = "\n".join(ln.rstrip() for ln in lines)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def build_payload(base_dir: Path) -> dict:
    articles_dir = base_dir / "wiki_articles"
    clusters, refs = [], {}
    for path in sorted(glob.glob(str(base_dir / "cluster_*.candidates.json"))):
        doc = json.loads(Path(path).read_text())
        tid = doc["task_id"]
        entries = []
        for c in doc["candidates"]:
            key = f"{c['reference_topic']}|{c['kind']}|{c['reference_value']}"
            if key not in refs:
                refs[key] = {
                    "reference_key": key,
                    "reference_topic": c["reference_topic"],
                    "kind": c["kind"],
                    "unit": c.get("unit", ""),
                    "reference_value": c["reference_value"],
                    "reference_fact_text": c["reference_fact_text"],
                    "reference_url": c["reference_url"],
                    "clusters": [],
                    "n_candidates": 0,
                    "article_text": load_article(
                        articles_dir, c["reference_topic"]),
                }
            refs[key]["n_candidates"] += 1
            if tid not in refs[key]["clusters"]:
                refs[key]["clusters"].append(tid)
            entries.append({
                "candidate_id": c["candidate_id"],
                "reference_key": key,
                "product_name": c["product_name"],
                "product_url": c["product_url"],
                "claim_value": c["claim_value"],
                "unit": c.get("unit", ""),
                "claim_snippet": c["claim_snippet"],
                "relative_excess": c.get("relative_excess"),
            })
        clusters.append({"task_id": tid, "entries": entries})
    missing = [r["reference_topic"] for r in refs.values()
               if not r["article_text"]]
    if missing:
        raise SystemExit(f"missing wiki article text for: {missing} "
                         f"(expected under {articles_dir})")
    return {
        "clusters": clusters,
        "references": sorted(refs.values(), key=lambda r: r["reference_key"]),
        "n_entries": sum(len(c["entries"]) for c in clusters),
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>矛盾候选人工裁决</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, "Segoe UI", "PingFang SC",
         "Microsoft YaHei", sans-serif; background: #f6f7f9; color: #1a1d21;
         line-height: 1.55; }
  .wrap { max-width: 980px; margin: 0 auto; padding: 16px 16px 120px; }
  header.top { position: sticky; top: 0; z-index: 10; background: #fff;
         border-bottom: 1px solid #e3e6ea; padding: 10px 16px; display: flex;
         flex-wrap: wrap; gap: 10px; align-items: center; }
  header.top h1 { font-size: 16px; margin: 0 12px 0 0; }
  .prog { font-size: 13px; color: #555; }
  .prog b { color: #0a7d38; }
  input[type=text] { border: 1px solid #ccd2d9; border-radius: 6px;
         padding: 6px 9px; font-size: 13px; }
  button { border: 1px solid #ccd2d9; background: #fff; border-radius: 6px;
         padding: 6px 12px; font-size: 13px; cursor: pointer; }
  button:hover { background: #f0f2f5; }
  button.primary { background: #14532d; border-color: #14532d; color: #fff; }
  button.primary:hover { background: #1a6b3a; }
  .card { background: #fff; border: 1px solid #e3e6ea; border-radius: 10px;
         padding: 14px 16px; margin: 14px 0; }
  .card.ref { border-left: 4px solid #b45309; }
  .card.done { border-left-color: #0a7d38; }
  .card.void { opacity: .55; }
  h2 { font-size: 17px; margin: 26px 0 4px; }
  h3 { font-size: 14px; margin: 0 0 8px; }
  .meta { font-size: 12px; color: #6b7280; word-break: break-all; }
  .facttext { background: #fef9c3; border: 1px solid #eab308; border-radius: 6px;
         padding: 8px 10px; font-size: 13px; margin: 8px 0; }
  .snippet { background: #f1f5f9; border-radius: 6px; padding: 8px 10px;
         font-size: 13px; margin: 6px 0; font-family: ui-monospace, monospace; }
  mark { background: #fde047; padding: 0 2px; border-radius: 3px; }
  .vs { display: flex; gap: 16px; font-size: 13px; margin: 6px 0; flex-wrap: wrap; }
  .vs .n { font-weight: 700; font-size: 15px; }
  .claimn { color: #b91c1c; } .refn { color: #b45309; }
  .btns { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
  .btns button.sel { outline: 3px solid #14532d33; font-weight: 700; }
  button.v-ok { border-color: #0a7d38; color: #0a7d38; }
  button.v-ok.sel { background: #dcfce7; }
  button.v-no { border-color: #b91c1c; color: #b91c1c; }
  button.v-no.sel { background: #fee2e2; }
  button.v-nu { border-color: #b45309; color: #b45309; }
  button.v-nu.sel { background: #fef3c7; }
  textarea, input.note { width: 100%; border: 1px solid #dfe3e8;
         border-radius: 6px; padding: 6px 9px; font-size: 13px; margin-top: 8px; }
  details.article { margin-top: 8px; }
  details.article summary { cursor: pointer; font-size: 13px; color: #1d4ed8; }
  .articlebox { max-height: 420px; overflow: auto; white-space: pre-wrap;
         background: #fafafa; border: 1px solid #e5e7eb; border-radius: 6px;
         padding: 12px; font-size: 13px; margin-top: 6px; }
  .hint { font-size: 13px; color: #374151; background: #eff6ff;
         border: 1px solid #bfdbfe; border-radius: 8px; padding: 10px 12px; }
  .bulk { font-size: 12px; }
  .voidmsg { font-size: 13px; color: #6b7280; font-style: italic; }
  footer.bar { position: fixed; bottom: 0; left: 0; right: 0; background: #fff;
         border-top: 1px solid #e3e6ea; padding: 10px 16px; display: flex;
         gap: 10px; align-items: center; flex-wrap: wrap; }
  .warn { color: #b91c1c; font-size: 13px; }
  .ok { color: #0a7d38; font-size: 13px; }
</style>
</head>
<body>
<header class="top">
  <h1>矛盾候选人工裁决</h1>
  <span class="prog" id="prog"></span>
  <span style="flex:1"></span>
  <label style="font-size:13px">裁决人:
    <input type="text" id="adjudicator" placeholder="你的名字（必填）"></label>
</header>
<div class="wrap">

<div class="hint">
  <b>怎么做（两步，先看这里）：</b><br>
  <b>第 1 步（最重要，先做）</b>：下面每张橙边卡片是一条“维基上限引用”。判断黄色高亮句是否真的陈述了
  <i>技术上限</i>（如“最大衰减约 20 dB”）。如果它只是某个产品例子、或说的是别的量，选
  <b>不是上限</b> —— 依赖它的全部候选会整批自动作废，不用再看。可展开“查看完整文章”核对上下文
  （文章全文已内嵌，就是沙箱冻结维基的原文，不需要联网）。<br>
  <b>第 2 步</b>：对剩下的每条候选,看商品文案里的红色数字是否真的与引用上限构成矛盾：
  <b>确认矛盾</b> = 营销数字确实超过了技术上限;<b>不构成矛盾</b> = 抽取或匹配错误
  （数字说的不是这个量）;<b>有张力但不可判</b> = 有点问题但不是可判定的数值矛盾（不会成为 gold）。<br>
  进度自动保存在浏览器里,做完点右下角<b>导出</b>,把下载的 JSON 文件发回即可。
</div>

<h2>第 1 步 · 引用甄别（__NREFS__ 条）</h2>
<div id="refs"></div>

<h2>第 2 步 · 逐条裁决（__NENTRIES__ 条）</h2>
<div id="clusters"></div>

</div>
<footer class="bar">
  <button id="export" class="primary">导出裁决 JSON</button>
  <button id="exportDraft">导出草稿（未完成也可）</button>
  <label><button onclick="document.getElementById('imp').click()">导入已有导出</button>
    <input type="file" id="imp" accept=".json" style="display:none"></label>
  <button id="reset">清空重来</button>
  <span id="status"></span>
</footer>

<script id="data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const LS = 'dra.contradiction.adjudication.v1';
let S = { adjudicator: '', refs: {}, entries: {} };
try { const s = JSON.parse(localStorage.getItem(LS)); if (s) S = s; } catch (e) {}

const esc = t => (t == null ? '' : String(t))
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function hlNum(text, value, all) {
  const t = esc(text);
  const v = String(value).replace(/\\.0$/, '');
  const re = new RegExp('(?<![\\\\d.])(' +
    v.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') +
    '(?:\\\\.0)?)(?![\\\\d])', all ? 'g' : '');
  return t.replace(re, '<mark>$1</mark>');
}
function save() { localStorage.setItem(LS, JSON.stringify(S)); render(); }

function refVerdict(key) { return (S.refs[key] || {}).verdict || ''; }

function render() {
  S.adjudicator = document.getElementById('adjudicator').value || S.adjudicator;
  document.getElementById('adjudicator').value = S.adjudicator || '';

  // stage 1
  const refsEl = document.getElementById('refs');
  refsEl.innerHTML = DATA.references.map(r => {
    const st = S.refs[r.reference_key] || {};
    const done = st.verdict === 'VALID_CEILING' || st.verdict === 'NOT_A_CEILING';
    return `<div class="card ref ${done ? 'done' : ''}">
      <h3>${esc(r.reference_topic)} · ${esc(r.kind)} · 上限 ${r.reference_value} ${esc(r.unit)}</h3>
      <div class="meta">影响 ${r.n_candidates} 条候选（${r.clusters.join(', ')}）
        · 原地址 ${esc(r.reference_url)}（仅沙箱内可达,原文已嵌入下方）</div>
      <div class="facttext">…${hlNum(r.reference_fact_text, r.reference_value)}…</div>
      <div class="btns">
        <button class="v-ok ${st.verdict==='VALID_CEILING'?'sel':''}"
          onclick="setRef('${esc(r.reference_key)}','VALID_CEILING')">✅ 是技术上限</button>
        <button class="v-no ${st.verdict==='NOT_A_CEILING'?'sel':''}"
          onclick="setRef('${esc(r.reference_key)}','NOT_A_CEILING')">❌ 不是上限（作废其全部候选）</button>
      </div>
      <input class="note" placeholder="备注（可选,例如:这是产品例子不是上限）"
        value="${esc(st.note || '')}"
        onchange="S.refs['${esc(r.reference_key)}']=S.refs['${esc(r.reference_key)}']||{};S.refs['${esc(r.reference_key)}'].note=this.value;save()">
      <details class="article"><summary>查看完整文章原文（${esc(r.reference_topic)}）</summary>
        <div class="articlebox">${hlNum(r.article_text, r.reference_value, true)}</div>
      </details>
    </div>`;
  }).join('');

  // stage 2
  const clEl = document.getElementById('clusters');
  clEl.innerHTML = DATA.clusters.filter(c => c.entries.length).map(c => {
    const groups = {};
    c.entries.forEach(e => (groups[e.reference_key] = groups[e.reference_key] || []).push(e));
    const inner = Object.entries(groups).map(([key, ents]) => {
      const rv = refVerdict(key);
      if (rv === 'NOT_A_CEILING')
        return `<div class="card void"><h3>${esc(key)}</h3>
          <div class="voidmsg">该引用已在第 1 步判为“不是上限”,这 ${ents.length} 条候选整批作废,无需逐条看。</div></div>`;
      const gate = rv === '' ? `<div class="voidmsg">（先在第 1 步甄别该引用,再回来逐条判）</div>` : '';
      const bulk = rv === 'VALID_CEILING' && ents.length > 3 ?
        `<div class="bulk btns">
          批量:<button onclick="bulkSet('${esc(key)}','NOT_A_CONFLICT')">本组全部“不构成矛盾”</button>
          <button onclick="bulkSet('${esc(key)}','SUPPORTED_CONFLICT')">本组全部“确认矛盾”</button>
          （之后仍可逐条改）</div>` : '';
      const rows = ents.map(e => {
        const st = S.entries[e.candidate_id] || {};
        const dis = rv !== 'VALID_CEILING' ? 'disabled' : '';
        return `<div class="card ${st.verdict ? 'done' : ''}">
          <h3>${esc(e.product_name)}</h3>
          <div class="meta">${esc(e.candidate_id)} · 商品页 ${esc(e.product_url)}（仅沙箱内可达）</div>
          <div class="snippet">…${hlNum(e.claim_snippet, e.claim_value)}…</div>
          <div class="vs">
            <span>文案宣称:<span class="n claimn">${e.claim_value} ${esc(e.unit)}</span></span>
            <span>维基上限:<span class="n refn">${DATA.references.find(r=>r.reference_key===key).reference_value} ${esc(e.unit)}</span></span>
            ${e.relative_excess != null ? `<span>超出 ${e.relative_excess}×</span>` : ''}
          </div>
          <div class="btns">
            <button ${dis} class="v-no ${st.verdict==='SUPPORTED_CONFLICT'?'sel':''}"
              onclick="setEntry('${esc(e.candidate_id)}','SUPPORTED_CONFLICT')">⚠️ 确认矛盾</button>
            <button ${dis} class="v-ok ${st.verdict==='NOT_A_CONFLICT'?'sel':''}"
              onclick="setEntry('${esc(e.candidate_id)}','NOT_A_CONFLICT')">✅ 不构成矛盾</button>
            <button ${dis} class="v-nu ${st.verdict==='NUANCE'?'sel':''}"
              onclick="setEntry('${esc(e.candidate_id)}','NUANCE')">🤔 有张力但不可判</button>
          </div>
          <input class="note" ${dis} placeholder="备注（可选）" value="${esc(st.note || '')}"
            onchange="S.entries['${esc(e.candidate_id)}']=S.entries['${esc(e.candidate_id)}']||{};S.entries['${esc(e.candidate_id)}'].note=this.value;save()">
        </div>`;
      }).join('');
      return gate + bulk + rows;
    }).join('');
    return `<h2 style="font-size:15px">${esc(c.task_id)}（${c.entries.length} 条）</h2>` + inner;
  }).join('');

  // progress
  const nRefDone = DATA.references.filter(r => refVerdict(r.reference_key)).length;
  let need = 0, done = 0;
  DATA.clusters.forEach(c => c.entries.forEach(e => {
    const rv = refVerdict(e.reference_key);
    if (rv === 'NOT_A_CEILING') return;
    need++;
    if ((S.entries[e.candidate_id] || {}).verdict) done++;
  }));
  document.getElementById('prog').innerHTML =
    `引用 <b>${nRefDone}/${DATA.references.length}</b> · 候选 <b>${done}/${need}</b>` +
    (nRefDone === DATA.references.length && done === need ? ' · <b>全部完成 ✓</b>' : '');
}

function setRef(key, v) {
  S.refs[key] = S.refs[key] || {};
  S.refs[key].verdict = (S.refs[key].verdict === v ? '' : v);
  save();
}
function setEntry(id, v) {
  S.entries[id] = S.entries[id] || {};
  S.entries[id].verdict = (S.entries[id].verdict === v ? '' : v);
  save();
}
function bulkSet(key, v) {
  const n = DATA.clusters.reduce((a,c)=>a+c.entries.filter(e=>e.reference_key===key).length,0);
  if (!confirm(`把该引用下全部 ${n} 条候选设为 ${v}?（之后仍可逐条修改）`)) return;
  DATA.clusters.forEach(c => c.entries.forEach(e => {
    if (e.reference_key === key) {
      S.entries[e.candidate_id] = S.entries[e.candidate_id] || {};
      S.entries[e.candidate_id].verdict = v;
    }
  }));
  save();
}

function buildExport() {
  const adj = (document.getElementById('adjudicator').value || '').trim();
  const clusters = {};
  DATA.clusters.forEach(c => {
    clusters[c.task_id] = {
      task_id: c.task_id,
      references: DATA.references
        .filter(r => r.clusters.includes(c.task_id))
        .map(r => ({ reference_key: r.reference_key,
                     reference_verdict: refVerdict(r.reference_key),
                     note: (S.refs[r.reference_key] || {}).note || '' })),
      entries: c.entries.map(e => ({
        candidate_id: e.candidate_id,
        reference_key: e.reference_key,
        verdict: refVerdict(e.reference_key) === 'NOT_A_CEILING'
          ? '' : ((S.entries[e.candidate_id] || {}).verdict || ''),
        adjudicator: adj,
        note: (S.entries[e.candidate_id] || {}).note || '' })),
    };
  });
  return { format: 'dra-contradiction-adjudication-export-v1',
           adjudicator: adj, exported_at: new Date().toISOString(), clusters };
}
function download(doc, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(doc, null, 2)],
    { type: 'application/json' }));
  a.download = name;
  a.click();
}
document.getElementById('export').onclick = () => {
  const adj = (document.getElementById('adjudicator').value || '').trim();
  const st = document.getElementById('status');
  if (!adj) { st.className = 'warn'; st.textContent = '请先填写裁决人姓名'; return; }
  const unref = DATA.references.filter(r => !refVerdict(r.reference_key)).length;
  let unent = 0;
  DATA.clusters.forEach(c => c.entries.forEach(e => {
    if (refVerdict(e.reference_key) !== 'NOT_A_CEILING'
        && !(S.entries[e.candidate_id] || {}).verdict) unent++;
  }));
  if (unref || unent) {
    st.className = 'warn';
    st.textContent = `还有 ${unref} 条引用、${unent} 条候选未判;全部完成才能导出正式文件（可先导出草稿）`;
    return;
  }
  download(buildExport(), 'contradiction_adjudication_export.json');
  st.className = 'ok'; st.textContent = '已导出,把该文件发回即可';
};
document.getElementById('exportDraft').onclick = () => {
  const doc = buildExport(); doc.draft = true;
  download(doc, 'contradiction_adjudication_DRAFT.json');
};
document.getElementById('imp').onchange = ev => {
  const f = ev.target.files[0]; if (!f) return;
  f.text().then(t => {
    const doc = JSON.parse(t);
    S.adjudicator = doc.adjudicator || S.adjudicator;
    Object.values(doc.clusters || {}).forEach(c => {
      (c.references || []).forEach(r => {
        if (r.reference_verdict) S.refs[r.reference_key] =
          { verdict: r.reference_verdict, note: r.note || '' };
      });
      (c.entries || []).forEach(e => {
        if (e.verdict || e.note) S.entries[e.candidate_id] =
          { verdict: e.verdict || '', note: e.note || '' };
      });
    });
    document.getElementById('adjudicator').value = S.adjudicator || '';
    save();
    const st = document.getElementById('status');
    st.className = 'ok'; st.textContent = '已导入';
  });
};
document.getElementById('reset').onclick = () => {
  if (confirm('清空所有已保存的裁决,确定?')) {
    S = { adjudicator: '', refs: {}, entries: {} }; save();
  }
};
document.getElementById('adjudicator').addEventListener('change', function () {
  S.adjudicator = this.value; save();
});
render();
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    ap.add_argument("--out")
    args = ap.parse_args()
    base = Path(args.dir)
    payload = build_payload(base)
    data_json = json.dumps(payload, ensure_ascii=False)
    data_json = data_json.replace("</", "<\\/")  # never close the script tag
    html = (HTML_TEMPLATE
            .replace("__DATA__", data_json)
            .replace("__NREFS__", str(len(payload["references"])))
            .replace("__NENTRIES__", str(payload["n_entries"])))
    out = Path(args.out) if args.out else base / "adjudication_ui.html"
    out.write_text(html)
    print(f"wrote {out} ({out.stat().st_size:,} bytes; "
          f"{len(payload['references'])} references, "
          f"{payload['n_entries']} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
