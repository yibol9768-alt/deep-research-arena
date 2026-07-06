#!/usr/bin/env python3
"""Offline HTML UI for ROUND-2 (intra-page) contradiction adjudication.

Same idea as build_adjudication_ui.py but for intra_page.candidates.json:
no reference-screening stage; every candidate shows the 2+ conflicting
value snippets from the SAME product page side by side. A programmatic
Chinese gloss states the conflict ("同一页面对「蓝牙版本」给出两个值")
so no per-snippet translation pass is needed; verdicts stay anchored to
the English originals.

The export downloads a JSON that IS a filled adjudication file for
scripts/build_intra_page_contradictions.py --promote (no applier needed).

Usage:
  python3 scripts/build_adjudication_ui_round2.py \
      [--candidates data/golden/contradictions/intra_page.candidates.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAND = ROOT / "data" / "golden" / "contradictions" / "intra_page.candidates.json"

KIND_ZH = {
    "bluetooth_version": "蓝牙版本",
    "battery_hours": "电池续航(小时)",
    "battery_mah": "电池容量(mAh)",
    "weight_g": "重量(克)",
    "lumens": "亮度(流明)",
    "impedance_ohm": "阻抗(Ω)",
    "driver_mm": "发声单元直径(mm)",
}

KIND_HINT_ZH = {
    "bluetooth_version": "同一台设备只有一个蓝牙版本;若两句都在说这台设备本身,即矛盾。常见开脱:一句说的是发射器/充电盒等别的部件,或是型号对比表。",
    "battery_hours": "注意区分:单次续航 vs 加充电盒总续航、不同音量/模式下的续航。两句若是同一口径下两个数,即矛盾。",
    "battery_mah": "注意区分:耳机本体电池 vs 充电盒电池、输入/输出规格、不同电压换算(5200mAh@7.4V=10400mAh@3.7V 不算矛盾)。",
    "weight_g": "注意区分:净重 vs 包装重、不同型号变体的重量表。两句若都是本品净重,即矛盾。",
    "lumens": "注意区分:不同灯头/模式(白光 vs 红光、泛光 vs 聚光)。两句若说的是同一光源同一模式,即矛盾。",
    "impedance_ohm": "注意区分:标称 vs 最小阻抗、家族对比表。",
    "driver_mm": "注意区分:高音/低音不同单元。",
}


def build_payload(cand_path: Path) -> dict:
    doc = json.loads(cand_path.read_text())
    kinds = []
    seen = set()
    def fmt(kind: str, value) -> str:
        if kind == "bluetooth_version":
            return f"{value:.1f}"
        s = f"{value:g}"
        return s

    for c in doc["candidates"]:
        for v in c["values"]:
            v["display"] = fmt(c["kind"], v["value"])
        vals = " 和 ".join(v["display"] for v in c["values"])
        c["gloss_zh"] = (f"同一页面对「{KIND_ZH.get(c['kind'], c['kind'])}」"
                         f"给出了 {len(c['values'])} 个值:{vals}"
                         f"(相差 {c['spread_ratio']} 倍)。")
        if c["kind"] not in seen:
            seen.add(c["kind"])
            kinds.append({"kind": c["kind"],
                          "zh": KIND_ZH.get(c["kind"], c["kind"]),
                          "hint": KIND_HINT_ZH.get(c["kind"], "")})
    return {"task_id": doc["task_id"], "kinds": kinds,
            "candidates": doc["candidates"]}


HTML_TEMPLATE = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>矛盾裁决 · 第二轮(页内自相矛盾)</title>
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
  .card { background: #fff; border: 1px solid #e3e6ea; border-radius: 10px;
         padding: 14px 16px; margin: 14px 0; }
  .card.done { border-left: 4px solid #0a7d38; }
  h2 { font-size: 16px; margin: 26px 0 4px; }
  h3 { font-size: 14px; margin: 0 0 6px; }
  .meta { font-size: 12px; color: #6b7280; word-break: break-all; }
  .gloss { font-size: 13px; color: #1e3a5f; background: #eff6ff;
         border: 1px solid #bfdbfe; border-radius: 6px; padding: 7px 10px;
         margin: 8px 0; }
  .valrow { display: flex; gap: 10px; margin: 6px 0; align-items: flex-start; }
  .valtag { min-width: 86px; text-align: center; font-weight: 700;
         font-size: 14px; color: #b91c1c; background: #fee2e2;
         border-radius: 6px; padding: 6px 8px; }
  .snippet { flex: 1; background: #f1f5f9; border-radius: 6px;
         padding: 7px 10px; font-size: 13px;
         font-family: ui-monospace, monospace; }
  mark { background: #fde047; padding: 0 2px; border-radius: 3px; }
  .btns { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
  .btns button.sel { outline: 3px solid #14532d33; font-weight: 700; }
  button.v-ok { border-color: #0a7d38; color: #0a7d38; }
  button.v-ok.sel { background: #dcfce7; }
  button.v-no { border-color: #b91c1c; color: #b91c1c; }
  button.v-no.sel { background: #fee2e2; }
  button.v-nu { border-color: #b45309; color: #b45309; }
  button.v-nu.sel { background: #fef3c7; }
  input.note { width: 100%; border: 1px solid #dfe3e8; border-radius: 6px;
         padding: 6px 9px; font-size: 13px; margin-top: 8px; }
  .hint { font-size: 13px; color: #374151; background: #fef9c3;
         border: 1px solid #eab308; border-radius: 8px; padding: 8px 12px;
         margin: 8px 0 2px; }
  .intro { font-size: 13px; color: #374151; background: #eff6ff;
         border: 1px solid #bfdbfe; border-radius: 8px; padding: 10px 12px; }
  footer.bar { position: fixed; bottom: 0; left: 0; right: 0; background: #fff;
         border-top: 1px solid #e3e6ea; padding: 10px 16px; display: flex;
         gap: 10px; align-items: center; flex-wrap: wrap; }
  .warn { color: #b91c1c; font-size: 13px; }
  .ok { color: #0a7d38; font-size: 13px; }
  .bulk { font-size: 12px; margin: 6px 0; }
</style>
</head>
<body>
<header class="top">
  <h1>矛盾裁决 · 第二轮(页内自相矛盾,__N__ 条)</h1>
  <span class="prog" id="prog"></span>
  <span style="flex:1"></span>
  <label style="font-size:13px">裁决人:
    <input type="text" id="adjudicator" placeholder="你的名字（必填）"></label>
</header>
<div class="wrap">
<div class="intro">
  <b>这轮比上轮简单:不需要维基,每条只问一个问题</b>——同一个商品页面,
  对同一个属性写了两个不同的数字(都已高亮),它们说的是不是同一样东西?<br>
  ⚠️ <b>确认矛盾</b> = 两个数说的是同一样东西,不可能同时为真(文案自相矛盾);
  ✅ <b>不构成矛盾</b> = 其实说的是两样东西(净重 vs 包装重、耳机 vs 充电盒、
  不同型号对比表)或抽取错误;🤔 <b>有张力但不可判</b> = 拿不准(不会成为 gold)。
  每类开头有一条黄色提示,列了该类常见的"开脱理由",判之前扫一眼。
  进度自动保存;全部判完点右下角导出,发我文件即可。
</div>
<div id="list"></div>
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
const LS = 'dra.contradiction.adjudication.round2.v1';
let S = { adjudicator: '', entries: {} };
try { const s = JSON.parse(localStorage.getItem(LS)); if (s) S = s; } catch (e) {}
const esc = t => (t == null ? '' : String(t))
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function hlNum(text, value) {
  const t = esc(text);
  const v = String(value).replace(/\\.0$/, '');
  const re = new RegExp('(?<![\\\\d.])(' +
    v.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') +
    '(?:\\\\.0)?)(?![\\\\d])');
  return t.replace(re, '<mark>$1</mark>');
}
function save() { localStorage.setItem(LS, JSON.stringify(S)); render(); }
function render() {
  S.adjudicator = document.getElementById('adjudicator').value || S.adjudicator;
  document.getElementById('adjudicator').value = S.adjudicator || '';
  const el = document.getElementById('list');
  const byKind = {};
  DATA.candidates.forEach(c => (byKind[c.kind] = byKind[c.kind] || []).push(c));
  el.innerHTML = DATA.kinds.map(k => {
    const ents = byKind[k.kind] || [];
    const head = `<h2>${esc(k.zh)}（${ents.length} 条）</h2>
      <div class="hint">💡 ${esc(k.hint)}</div>
      <div class="bulk btns">批量:
        <button onclick="bulkSet('${esc(k.kind)}','NOT_A_CONFLICT')">本类全部“不构成矛盾”</button>
        <button onclick="bulkSet('${esc(k.kind)}','SUPPORTED_CONFLICT')">本类全部“确认矛盾”</button>
        （之后仍可逐条改）</div>`;
    return head + ents.map(c => {
      const st = S.entries[c.candidate_id] || {};
      const rows = c.values.map(v => `<div class="valrow">
          <div class="valtag">${esc(v.display)}</div>
          <div class="snippet">…${hlNum(v.snippet, v.value)}…</div>
        </div>`).join('');
      return `<div class="card ${st.verdict ? 'done' : ''}">
        <h3>${esc(c.product_name)}</h3>
        <div class="meta">${esc(c.candidate_id)} · ${esc(c.product_url)}（仅沙箱内可达）</div>
        <div class="gloss">${esc(c.gloss_zh)}</div>
        ${rows}
        <div class="btns">
          <button class="v-no ${st.verdict==='SUPPORTED_CONFLICT'?'sel':''}"
            onclick="setE('${esc(c.candidate_id)}','SUPPORTED_CONFLICT')">⚠️ 确认矛盾</button>
          <button class="v-ok ${st.verdict==='NOT_A_CONFLICT'?'sel':''}"
            onclick="setE('${esc(c.candidate_id)}','NOT_A_CONFLICT')">✅ 不构成矛盾</button>
          <button class="v-nu ${st.verdict==='NUANCE'?'sel':''}"
            onclick="setE('${esc(c.candidate_id)}','NUANCE')">🤔 有张力但不可判</button>
        </div>
        <input class="note" placeholder="备注（可选）" value="${esc(st.note || '')}"
          onchange="S.entries['${esc(c.candidate_id)}']=S.entries['${esc(c.candidate_id)}']||{};S.entries['${esc(c.candidate_id)}'].note=this.value;save()">
      </div>`;
    }).join('');
  }).join('');
  const done = DATA.candidates.filter(c => (S.entries[c.candidate_id]||{}).verdict).length;
  document.getElementById('prog').innerHTML =
    `已判 <b>${done}/${DATA.candidates.length}</b>` +
    (done === DATA.candidates.length ? ' · <b>全部完成 ✓</b>' : '');
}
function setE(id, v) {
  S.entries[id] = S.entries[id] || {};
  S.entries[id].verdict = (S.entries[id].verdict === v ? '' : v);
  save();
}
function bulkSet(kind, v) {
  const ents = DATA.candidates.filter(c => c.kind === kind);
  if (!confirm(`把「${kind}」类全部 ${ents.length} 条设为 ${v}?（之后仍可逐条改）`)) return;
  ents.forEach(c => {
    S.entries[c.candidate_id] = S.entries[c.candidate_id] || {};
    S.entries[c.candidate_id].verdict = v;
  });
  save();
}
function buildExport() {
  const adj = (document.getElementById('adjudicator').value || '').trim();
  return {
    task_id: DATA.task_id,
    format: 'dra-intra-adjudication-v1',
    exported_at: new Date().toISOString(),
    entries: DATA.candidates.map(c => ({
      candidate_id: c.candidate_id,
      verdict: (S.entries[c.candidate_id] || {}).verdict || '',
      adjudicator: adj,
      note: (S.entries[c.candidate_id] || {}).note || '' })),
  };
}
function download(doc, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(doc, null, 2)],
    { type: 'application/json' }));
  a.download = name; a.click();
}
document.getElementById('export').onclick = () => {
  const st = document.getElementById('status');
  const adj = (document.getElementById('adjudicator').value || '').trim();
  if (!adj) { st.className='warn'; st.textContent='请先填写裁决人姓名'; return; }
  const left = DATA.candidates.filter(c => !(S.entries[c.candidate_id]||{}).verdict).length;
  if (left) { st.className='warn';
    st.textContent = `还有 ${left} 条未判;全部完成才能导出正式文件（可先导出草稿）`; return; }
  download(buildExport(), 'intra_page.adjudication.json');
  st.className='ok'; st.textContent='已导出,把该文件发回即可';
};
document.getElementById('exportDraft').onclick = () => {
  const doc = buildExport(); doc.draft = true;
  download(doc, 'intra_page.adjudication.DRAFT.json');
};
document.getElementById('imp').onchange = ev => {
  const f = ev.target.files[0]; if (!f) return;
  f.text().then(t => {
    const doc = JSON.parse(t);
    (doc.entries || []).forEach(e => {
      if (e.verdict || e.note) S.entries[e.candidate_id] =
        { verdict: e.verdict || '', note: e.note || '' };
      if (e.adjudicator) S.adjudicator = e.adjudicator;
    });
    document.getElementById('adjudicator').value = S.adjudicator || '';
    save();
    const st = document.getElementById('status');
    st.className='ok'; st.textContent='已导入';
  });
};
document.getElementById('reset').onclick = () => {
  if (confirm('清空所有已保存的裁决,确定?')) {
    S = { adjudicator: '', entries: {} }; save();
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
    ap.add_argument("--candidates", default=str(DEFAULT_CAND))
    ap.add_argument("--out")
    args = ap.parse_args()
    cand_path = Path(args.candidates)
    payload = build_payload(cand_path)
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = (HTML_TEMPLATE
            .replace("__DATA__", data_json)
            .replace("__N__", str(len(payload["candidates"]))))
    out = Path(args.out) if args.out else cand_path.parent / "adjudication_ui_round2.html"
    out.write_text(html)
    print(f"wrote {out} ({out.stat().st_size:,} bytes; "
          f"{len(payload['candidates'])} candidates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
