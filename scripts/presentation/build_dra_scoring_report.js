const pptxgen = require('pptxgenjs');
const path = require('path');
const fs = require('fs');
const sizeOf = require('image-size');

const pptx = new pptxgen();
pptx.defineLayout({ name: 'DRA_WIDE', width: 13.333, height: 7.5 });
pptx.layout = 'DRA_WIDE';
pptx.author = '刘弈博 / DRA';
pptx.company = 'Deep Research Arena';
pptx.subject = 'DRA 沙盒原生 Deep Research 评测体系重构';
pptx.title = 'DRA 评测重构：从报告级乘法到沙盒原生证据测试';
pptx.lang = 'zh-CN';
pptx.theme = {
  headFontFace: 'Microsoft YaHei',
  bodyFontFace: 'Microsoft YaHei',
  lang: 'zh-CN'
};
pptx.layout = 'DRA_WIDE';
pptx.margin = 0;

const ROOT = path.resolve(__dirname, '..', '..');
const OUT_DIR = path.join(ROOT, 'docs', 'presentations');
const ASSET_DIR = path.join(OUT_DIR, 'assets', 'papers');
const OUTPUT = path.join(OUT_DIR, 'DRA_SCORING_REDESIGN_REPORT_2026-07-18.pptx');

const C = {
  navy: '0B132B',
  navy2: '1C2541',
  blue: '2563EB',
  cyan: '3A86FF',
  teal: '2EC4B6',
  green: '06D6A0',
  orange: 'FF9F1C',
  red: 'EF476F',
  purple: '7C3AED',
  ink: '16202A',
  muted: '64748B',
  line: 'D9E1EA',
  soft: 'EEF3F8',
  bg: 'F7F9FC',
  white: 'FFFFFF',
  paleBlue: 'EAF2FF',
  paleTeal: 'E6FBF8',
  paleOrange: 'FFF3DD',
  paleRed: 'FDEBF0',
  palePurple: 'F0EAFE'
};

const FONT = 'Microsoft YaHei';
const FONT_MONO = 'Consolas';
const FONT_MATH = 'Cambria Math';
const W = 13.333;
const H = 7.5;
let slideNumber = 0;

function addNotes(slide, notes) {
  if (notes) slide.addNotes(notes);
}

function newSlide(bg = C.bg) {
  slideNumber += 1;
  const slide = pptx.addSlide();
  slide.background = { color: bg };
  return slide;
}

function addFooter(slide, source = '', dark = false) {
  const color = dark ? 'B9C5D6' : C.muted;
  slide.addShape(pptx.ShapeType.line, {
    x: 0.55, y: 7.12, w: 12.23, h: 0,
    line: { color: dark ? '30405E' : C.line, width: 0.8 }
  });
  slide.addText(source, {
    x: 0.62, y: 7.17, w: 11.6, h: 0.18,
    fontFace: FONT, fontSize: 7.5, color,
    margin: 0, breakLine: false, valign: 'mid'
  });
  slide.addText(String(slideNumber).padStart(2, '0'), {
    x: 12.25, y: 7.14, w: 0.5, h: 0.22,
    fontFace: FONT_MONO, fontSize: 8.5, color,
    bold: true, align: 'right', margin: 0
  });
}

function addTitle(slide, title, section = '', subtitle = '') {
  if (section) {
    slide.addText(section.toUpperCase(), {
      x: 0.64, y: 0.38, w: 3.6, h: 0.22,
      fontFace: FONT_MONO, fontSize: 9.5, bold: true,
      color: C.blue, charSpacing: 1.2, margin: 0
    });
  }
  const visualLength = [...title].reduce((sum, ch) => sum + (ch.charCodeAt(0) > 255 ? 1 : 0.55), 0);
  const titleSize = visualLength > 42 ? 18.5 : visualLength > 32 ? 20.5 : visualLength > 24 ? 23 : 26;
  slide.addText(title, {
    x: 0.62, y: section ? 0.64 : 0.48, w: 12.0, h: section ? 0.44 : 0.56,
    fontFace: FONT, fontSize: titleSize, bold: true, color: C.navy,
    margin: 0, breakLine: false, valign: 'mid', fit: 'shrink'
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.64, y: section ? 1.08 : 1.03, w: 11.9, h: 0.19,
      fontFace: FONT, fontSize: 10.5, color: C.muted,
      margin: 0, fit: 'shrink'
    });
  }
}

function addSectionSlide(num, title, subtitle, accent = C.teal) {
  const slide = newSlide(C.navy);
  slide.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: 0.18, h: H, fill: { color: accent }, line: { color: accent } });
  slide.addText(String(num).padStart(2, '0'), {
    x: 0.72, y: 0.84, w: 2.0, h: 1.0,
    fontFace: FONT_MONO, fontSize: 58, bold: true, color: accent, margin: 0
  });
  slide.addText(title, {
    x: 0.75, y: 2.2, w: 11.5, h: 1.2,
    fontFace: FONT, fontSize: 34, bold: true, color: C.white, margin: 0, fit: 'shrink'
  });
  slide.addText(subtitle, {
    x: 0.78, y: 3.65, w: 10.8, h: 0.9,
    fontFace: FONT, fontSize: 16, color: 'C7D2E4', margin: 0, breakLine: false, fit: 'shrink'
  });
  addFooter(slide, 'DRA sandbox-native scoring redesign · 2026-07-18', true);
  addNotes(slide, `章节过渡：${title}。${subtitle}`);
  return slide;
}

function addCard(slide, x, y, w, h, title, body = '', opts = {}) {
  const fill = opts.fill || C.white;
  const line = opts.line || C.line;
  const accent = opts.accent;
  const radius = opts.radius === false ? pptx.ShapeType.rect : pptx.ShapeType.roundRect;
  slide.addShape(radius, {
    x, y, w, h,
    rectRadius: 0.08,
    fill: { color: fill, transparency: opts.transparency || 0 },
    line: { color: line, width: opts.lineWidth || 1 },
    shadow: opts.shadow === false ? undefined : { type: 'outer', color: '9AA9BC', opacity: 0.12, blur: 1.5, angle: 45, distance: 1 }
  });
  if (accent) {
    slide.addShape(pptx.ShapeType.rect, { x, y, w: 0.08, h, fill: { color: accent }, line: { color: accent } });
  }
  const tx = x + (accent ? 0.25 : 0.2);
  if (h < 0.72) {
    const runs = [{ text: title, options: { bold: true, breakLine: Boolean(body) } }];
    if (body) runs.push({ text: body, options: { bold: false } });
    slide.addText(runs, {
      x: tx, y: y + 0.07, w: w - (accent ? 0.4 : 0.35), h: Math.max(0.2, h - 0.13),
      fontFace: FONT, fontSize: opts.bodySize || opts.titleSize || 8.8,
      color: opts.bodyColor || opts.titleColor || C.ink, margin: 0,
      valign: 'mid', fit: 'shrink'
    });
    return;
  }
  const compact = h < 1.2;
  slide.addText(title, {
    x: tx, y: y + (compact ? 0.11 : 0.18), w: w - (accent ? 0.4 : 0.35), h: compact ? 0.25 : 0.34,
    fontFace: FONT, fontSize: opts.titleSize || (compact ? 11.5 : 15), bold: true,
    color: opts.titleColor || C.navy, margin: 0, fit: 'shrink'
  });
  if (body) {
    slide.addText(body, {
      x: tx, y: y + (compact ? 0.39 : 0.62), w: w - (accent ? 0.42 : 0.38), h: compact ? Math.max(0.22, h - 0.47) : h - 0.78,
      fontFace: FONT, fontSize: opts.bodySize || (compact ? 9.5 : 11.5), color: opts.bodyColor || C.ink,
      margin: 0, breakLine: false, valign: 'top', fit: 'shrink',
      bold: opts.bodyBold || false
    });
  }
}

function addBulletList(slide, items, x, y, w, h, opts = {}) {
  const gap = opts.gap || 0.08;
  const lineH = (h - gap * (items.length - 1)) / items.length;
  items.forEach((item, i) => {
    const color = item.color || opts.color || C.ink;
    const bulletColor = item.bulletColor || opts.bulletColor || C.blue;
    slide.addShape(pptx.ShapeType.ellipse, {
      x, y: y + i * (lineH + gap) + 0.11, w: 0.1, h: 0.1,
      fill: { color: bulletColor }, line: { color: bulletColor }
    });
    slide.addText(item.text || item, {
      x: x + 0.22, y: y + i * (lineH + gap), w: w - 0.22, h: lineH,
      fontFace: FONT, fontSize: item.size || opts.fontSize || 12.3,
      color, margin: 0, fit: 'shrink', valign: 'mid',
      bold: item.bold || false
    });
  });
}

function addPill(slide, text, x, y, w, color = C.blue, fill = C.paleBlue) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h: 0.34,
    rectRadius: 0.08,
    fill: { color: fill }, line: { color: fill }
  });
  slide.addText(text, {
    x: x + 0.05, y: y + 0.05, w: w - 0.1, h: 0.21,
    fontFace: FONT, fontSize: 9.3, bold: true, color,
    align: 'center', margin: 0, fit: 'shrink'
  });
}

function addKpi(slide, value, label, x, y, w, opts = {}) {
  slide.addText(value, {
    x, y, w, h: 0.58,
    fontFace: FONT_MONO, fontSize: opts.valueSize || 28, bold: true,
    color: opts.color || C.blue, align: opts.align || 'left', margin: 0, fit: 'shrink'
  });
  slide.addText(label, {
    x, y: y + 0.62, w, h: 0.35,
    fontFace: FONT, fontSize: opts.labelSize || 10.5, color: opts.labelColor || C.muted,
    align: opts.align || 'left', margin: 0, fit: 'shrink'
  });
}

function addArrow(slide, x1, y1, x2, y2, color = C.blue, width = 1.5) {
  slide.addShape(pptx.ShapeType.line, {
    x: x1, y: y1, w: x2 - x1, h: y2 - y1,
    line: { color, width, beginArrowType: 'none', endArrowType: 'triangle' }
  });
}

function addImageContain(slide, imagePath, x, y, w, h, opts = {}) {
  if (!fs.existsSync(imagePath)) return;
  const dim = sizeOf(imagePath);
  const scale = Math.min(w / dim.width, h / dim.height);
  const iw = dim.width * scale;
  const ih = dim.height * scale;
  slide.addImage({
    path: imagePath,
    x: x + (w - iw) / 2,
    y: y + (h - ih) / 2,
    w: iw,
    h: ih,
    transparency: opts.transparency || 0
  });
}

function addEquationBox(slide, equation, x, y, w, h, opts = {}) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h,
    fill: { color: opts.fill || C.navy },
    line: { color: opts.line || opts.fill || C.navy, width: 1.2 },
    shadow: { type: 'outer', color: '0B132B', opacity: 0.14, blur: 2, angle: 45, distance: 1 }
  });
  slide.addText(equation, {
    x: x + 0.2, y: y + 0.15, w: w - 0.4, h: h - 0.3,
    fontFace: opts.fontFace || FONT_MATH, fontSize: opts.fontSize || 20,
    bold: opts.bold !== false, color: opts.color || C.white,
    align: 'center', valign: 'mid', margin: 0, fit: 'shrink'
  });
}

function addMiniTable(slide, rows, x, y, colWidths, rowH, opts = {}) {
  const totalW = colWidths.reduce((a, b) => a + b, 0);
  rows.forEach((row, ri) => {
    let cx = x;
    row.forEach((cell, ci) => {
      const header = ri === 0 && opts.header !== false;
      slide.addShape(pptx.ShapeType.rect, {
        x: cx, y: y + ri * rowH, w: colWidths[ci], h: rowH,
        fill: { color: header ? (opts.headerFill || C.navy2) : (ri % 2 ? C.white : C.soft) },
        line: { color: C.line, width: 0.7 }
      });
      slide.addText(String(cell), {
        x: cx + 0.08, y: y + ri * rowH + 0.05, w: colWidths[ci] - 0.16, h: rowH - 0.1,
        fontFace: FONT, fontSize: header ? (opts.headerSize || 9.2) : (opts.bodySize || 8.8),
        bold: header, color: header ? C.white : C.ink,
        margin: 0, valign: 'mid', fit: 'shrink', align: opts.align || 'left'
      });
      cx += colWidths[ci];
    });
  });
  return totalW;
}

// 01 — Cover
{
  const slide = newSlide(C.navy);
  slide.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: W, h: H, fill: { color: C.navy }, line: { color: C.navy } });
  slide.addShape(pptx.ShapeType.arc, { x: 8.6, y: -1.5, w: 6.6, h: 6.6, adjustPoint: 0.4, rotate: 18, fill: { color: C.teal, transparency: 70 }, line: { color: C.teal, transparency: 30, width: 2 } });
  slide.addShape(pptx.ShapeType.arc, { x: 9.6, y: 2.0, w: 5.2, h: 5.2, rotate: 188, fill: { color: C.blue, transparency: 82 }, line: { color: C.blue, transparency: 40, width: 2 } });
  slide.addText('DRA 评测重构', {
    x: 0.82, y: 1.05, w: 7.4, h: 0.72,
    fontFace: FONT, fontSize: 38, bold: true, color: C.white, margin: 0
  });
  slide.addText('从报告级乘法到沙盒原生证据测试', {
    x: 0.85, y: 1.94, w: 8.4, h: 0.66,
    fontFace: FONT, fontSize: 25, bold: true, color: C.teal, margin: 0, fit: 'shrink'
  });
  slide.addText('旧评分为什么不够  ·  LoHoSearch 给我们的启发  ·  DRA v3.2 基线 + v3.3 候选修订', {
    x: 0.88, y: 2.85, w: 8.7, h: 0.55,
    fontFace: FONT, fontSize: 14, color: 'CAD5E5', margin: 0, fit: 'shrink'
  });
  addPill(slide, '长篇 Deep Research', 0.88, 3.68, 1.72, C.teal, '173A45');
  addPill(slide, '冻结网页沙盒', 2.74, 3.68, 1.55, C.cyan, '183154');
  addPill(slide, '12 Harness', 4.43, 3.68, 1.25, C.orange, '49371E');
  addPill(slide, '可审计证据', 5.82, 3.68, 1.47, C.green, '153D38');
  addPill(slide, '长版 · 约 90 分钟', 0.88, 4.25, 1.85, C.purple, '2C214B');
  slide.addText('刘弈博 · 2026-07-18', {
    x: 0.9, y: 6.42, w: 3.4, h: 0.34,
    fontFace: FONT, fontSize: 11.5, color: 'B7C4D8', margin: 0
  });
  addFooter(slide, 'Deep Research Arena · Sandbox-native evaluation redesign', true);
  addNotes(slide, '开场先给结论：我们不是把旧系统推翻重做，而是把旧系统中有价值的 URL、抓取和事实检测器下沉到正确的评分层级。整套汇报依次讲问题、文献、方案和实施。');
}

// 02 — One-sentence thesis
{
  const slide = newSlide();
  addTitle(slide, '一句话结论', 'Executive thesis', 'DRA 的优势不是“有一个更聪明的 LLM judge”，而是我们拥有一个有限、冻结、可回放的网页世界。');
  slide.addText('我们不需要写出一份唯一标准答案，\n也不需要抽取全世界所有事实。', {
    x: 0.75, y: 1.75, w: 5.35, h: 1.15,
    fontFace: FONT, fontSize: 23, bold: true, color: C.navy, margin: 0, breakLine: false, fit: 'shrink'
  });
  addArrow(slide, 6.1, 2.28, 7.15, 2.28, C.orange, 3);
  slide.addText('我们需要把每一项“研究工作”编译成\n可执行、可追溯、允许替代证据的测试。', {
    x: 7.35, y: 1.75, w: 5.15, h: 1.15,
    fontFace: FONT, fontSize: 23, bold: true, color: C.blue, margin: 0, breakLine: false, fit: 'shrink'
  });
  const labels = [
    ['World Index', '世界里有哪些文档？'],
    ['Task World Model', '这道题的证据区域说了什么？'],
    ['Research Test Suite', '怎样算完成了这项调研？'],
    ['Execution Audit', '证据本次真的交付并被正确使用了吗？']
  ];
  labels.forEach((d, i) => {
    addCard(slide, 0.78 + i * 3.08, 3.55, 2.78, 1.58, d[0], d[1], {
      accent: [C.blue, C.teal, C.orange, C.purple][i], bodySize: 11.5, titleSize: 13.5
    });
    if (i < 3) addArrow(slide, 3.58 + i * 3.08, 4.34, 3.82 + i * 3.08, 4.34, C.muted, 1.3);
  });
  addEquationBox(slide, '主分：有本次交付证据完成的必要研究工作占比', 2.25, 5.7, 8.8, 0.82, { fill: C.navy2, fontFace: FONT, fontSize: 17 });
  addFooter(slide, 'Internal design: DRA_SANDBOX_NATIVE_SCORING_DESIGN_2026-07-17.md (v3.2)');
  addNotes(slide, '这一页是全场主线。全量层做廉价结构，按题层做昂贵语义，评分层看报告是否以本次可观察证据完成用户要求。');
}

// 03 — Agenda
{
  const slide = newSlide();
  addTitle(slide, '今天要回答五个问题', 'Agenda');
  const items = [
    ['01', '旧评分为什么不够', 'Fact / PoF / Completeness / Provenance 的层级错位'],
    ['02', 'DRA 真正应该测什么', '发现、观察、利用、完成；广度与报告质量分离'],
    ['03', 'LoHoSearch 做对了什么', '全图轻量结构 + 局部昂贵语义 + 自动与人工验证'],
    ['04', '其他论文提供了哪些积木', 'rubric co-design、冻结环境、广度分母、引用审计'],
    ['05', '我们接下来怎么落地', 'DRA v3.2 基线 + v3.3 候选修订、验证矩阵、Dev-14 与 56 题扩展']
  ];
  items.forEach((d, i) => {
    const y = 1.42 + i * 1.02;
    slide.addText(d[0], { x: 0.78, y, w: 0.68, h: 0.48, fontFace: FONT_MONO, fontSize: 18, bold: true, color: i === 2 ? C.orange : C.blue, margin: 0 });
    slide.addText(d[1], { x: 1.62, y, w: 3.35, h: 0.42, fontFace: FONT, fontSize: 16, bold: true, color: C.navy, margin: 0, fit: 'shrink' });
    slide.addText(d[2], { x: 5.08, y: y + 0.02, w: 7.2, h: 0.42, fontFace: FONT, fontSize: 11.7, color: C.muted, margin: 0, fit: 'shrink' });
    if (i < items.length - 1) slide.addShape(pptx.ShapeType.line, { x: 1.62, y: y + 0.69, w: 10.65, h: 0, line: { color: C.line, width: 0.8 } });
  });
  addFooter(slide, 'Presentation structure · 2026-07-18');
  addNotes(slide, '说明这不是单纯的评分公式讨论。我们从测量目标出发，先用文献验证，再落到可实现、可校准、可发布的工程计划。');
}

// 04 — What DRA is
{
  const slide = newSlide();
  addTitle(slide, 'DRA 的实验对象：同一世界中的 12 种研究系统', 'Part I · Why the old score failed', '控制变量不是一句口号，而是任务、底模、网页、工具身份与运行证据都被冻结。');
  addCard(slide, 0.72, 1.58, 2.5, 3.9, '统一输入', '同一 query\n同一公共输出要求\n同一任务 manifest\n不向 agent 暴露 scorer-shaped 提示', { accent: C.blue, bodySize: 14 });
  addCard(slide, 3.44, 1.58, 2.5, 3.9, '统一世界', '冻结 Magento 商城\n冻结 Postmill 论坛\n离线 Kiwix Wikipedia\n统一 URL registry 与搜索 API', { accent: C.teal, bodySize: 14 });
  addCard(slide, 6.16, 1.58, 2.5, 3.9, '统一比较', '12 个 harness adapter\n相同底模与预算协议\n运行日志与报告 seal\n固定任务集做宏平均', { accent: C.orange, bodySize: 14 });
  addCard(slide, 8.88, 1.58, 3.72, 3.9, '输出不是一个答案', '长篇报告需要：\n• 多方向检索\n• 跨来源比较与机制解释\n• 冲突、条件和不确定性\n• 面向用户约束的建议\n• 就地引用与可复核证据', { accent: C.purple, bodySize: 13.5 });
  slide.addText('v3 目标配置', { x: 0.78, y: 5.9, w: 1.4, h: 0.3, fontFace: FONT, fontSize: 11, bold: true, color: C.muted, margin: 0 });
  addPill(slide, '56 道正式任务', 2.1, 5.86, 1.55, C.blue, C.paleBlue);
  addPill(slide, 'Dev-14 校准子集', 3.85, 5.86, 1.68, C.teal, C.paleTeal);
  addPill(slide, '12 Harness', 5.73, 5.86, 1.2, C.orange, C.paleOrange);
  addPill(slide, '一个固定文档世界', 7.13, 5.86, 1.85, C.purple, C.palePurple);
  addFooter(slide, 'DRA current method + v3.2 design; internal task/harness manifests');
  addNotes(slide, '强调 DRA 研究对象是 harness，而不仅是模型。网页世界和工具面可控，让我们有条件做开放网络基准做不到的运行内证据审计。');
}

// 05 — Closed documents, not closed semantics
{
  const slide = newSlide();
  addTitle(slide, '我们“拥有整个世界”——但只拥有文档世界', 'Part I · Measurement boundary', '可辩护的闭合边界必须比“全知事实表”更精确。');
  addCard(slide, 0.75, 1.55, 5.88, 4.75, '可以穷尽并冻结', '', { accent: C.green, fill: 'F4FFFB' });
  addBulletList(slide, [
    { text: '允许访问的 URL、canonical alias 与 redirect', bulletColor: C.green },
    { text: '每个 URL 的快照、状态、内容 hash 与结构 span', bulletColor: C.green },
    { text: '表格、商品字段、论坛 post/reply、页面链接图', bulletColor: C.green },
    { text: '本次运行真正交付给 agent 的 artifact 与 span', bulletColor: C.green },
    { text: '固定 compiler 在单题范围生成的语义资产与测试', bulletColor: C.green }
  ], 1.08, 2.25, 5.15, 3.42, { fontSize: 13 });
  addCard(slide, 6.88, 1.55, 5.7, 4.75, '不能声称穷尽', '', { accent: C.red, fill: 'FFF8FA' });
  addBulletList(slide, [
    { text: '每页中所有可能的自然语言命题', bulletColor: C.red },
    { text: '所有合理的人类解释与推理路线', bulletColor: C.red },
    { text: 'agent 可能生成的无限搜索词', bulletColor: C.red },
    { text: '所有替代证据组合与未来策略', bulletColor: C.red },
    { text: '沙盒外现实世界的完整真理', bulletColor: C.red }
  ], 7.23, 2.25, 4.95, 3.42, { fontSize: 13 });
  addEquationBox(slide, 'Closed document universe  ≠  complete semantic universe', 2.35, 6.47, 8.7, 0.48, { fill: C.navy2, fontSize: 16 });
  addFooter(slide, 'DRA v3.2 §4.1 — Closed Documents, Task-Scoped Semantics');
  addNotes(slide, '这页纠正“我们拥有整个世界”可能引发的过度主张。我们拥有可审计文档边界，但不拥有全部语义。后面因此采用全量轻量结构、按题局部语义。');
}

// 06 — Task taxonomy
{
  const slide = newSlide();
  addTitle(slide, 'Deep Research 不是把 QA 做得更长', 'Part I · Construct definition');
  const rows = [
    ['任务形态', '主要输出', '关键难点', 'DRA 的关系'],
    ['Fact QA', '一个事实 / 短答案', '定位并验证', '不是'],
    ['Deep Search', '少量难找答案', '多跳定位与消歧', '相邻能力'],
    ['Wide Search', '大规模实体 / 字段表', '枚举、去重、停止', '覆盖“广度”的一部分'],
    ['Deep Research', '长篇、结构化、带引用报告', '分解、跨源综合、冲突、条件、建议', '核心对象']
  ];
  addMiniTable(slide, rows, 0.72, 1.55, [1.55, 2.55, 4.15, 3.55], 0.78, { headerSize: 10, bodySize: 11 });
  addCard(slide, 0.74, 5.78, 12.0, 0.9, '因此不能只问“答案对不对”', '底层事实可以做确定性核验，但正式评分对象必须覆盖比较、机制、冲突、跨来源综合、教程、预算方案和推荐。', { accent: C.orange, fill: C.paleOrange, titleSize: 14, bodySize: 12.2, shadow: false });
  addFooter(slide, 'WideSearch (arXiv:2508.07999); DeepWideSearch (arXiv:2510.20168); DRA v3.2 §1');
  addNotes(slide, '用四类任务划边界。DRA 的广度不等于列全表，深度也不等于多跳答案；最终产物是综合报告。');
}

// 07 — Old formula
{
  const slide = newSlide();
  addTitle(slide, '最开始的做法：三个质量项加权，再乘 Provenance', 'Part I · Historical baseline', '旧方案抓住了重要信号，但把不同层级的构念压成了一个报告级混合分。');
  addEquationBox(slide, 'Q_old = 0.39 × Fact + 0.28 × ProofOfFetch + 0.33 × Completeness', 1.05, 1.66, 11.2, 0.92, { fill: C.navy2, fontSize: 21 });
  addEquationBox(slide, 'Truth_old = Provenance × Q_old', 3.15, 2.87, 7.0, 0.9, { fill: C.blue, fontSize: 24 });
  const cards = [
    ['Fact', '结构化商品事实：主要是价格与 overall rating', C.red],
    ['ProofOfFetch', '报告引用页是否出现在本次抓取集合', C.orange],
    ['Completeness', '答案键 vital nuggets / concept / forum slot 覆盖', C.teal],
    ['Provenance', '引用 URL 能否由搜索、抓取或已抓页面链接解释', C.purple]
  ];
  cards.forEach((d, i) => addCard(slide, 0.82 + i * 3.08, 4.35, 2.78, 1.45, d[0], d[1], { accent: d[2], titleSize: 13.5, bodySize: 10.6 }));
  slide.addText('历史候选还讨论过 Provenance^1.5，但没有独立构念或校准依据。', {
    x: 2.68, y: 6.18, w: 8.0, h: 0.32, fontFace: FONT, fontSize: 11.2, color: C.muted, italic: true, align: 'center', margin: 0
  });
  addFooter(slide, 'DRA_CURRENT_METHOD_2026-07-14.md §0, §10; formula tv2.5 linear provenance gate');
  addNotes(slide, '不要把旧方案描述成拍脑袋。它试图同时覆盖内容、抓取与 URL 来源。问题在于这些信号的抽象层级不同，报告级相加再相乘无法表达局部 claim—evidence 关系。');
}

// 08 — Provenance S/F/L
{
  const slide = newSlide();
  addTitle(slide, '旧 Provenance 能证明“URL 不是凭空猜的”，但不能证明“说法有证据”', 'Part I · Provenance semantics');
  const circles = [
    { x: 1.15, y: 2.02, w: 3.0, h: 3.0, color: C.blue, label: 'S', sub: '搜索接口返回过的 URL' },
    { x: 3.15, y: 2.02, w: 3.0, h: 3.0, color: C.teal, label: 'F', sub: '本次成功抓取、HTTP 200' },
    { x: 5.15, y: 2.02, w: 3.0, h: 3.0, color: C.orange, label: 'L', sub: '已抓正文中出现过的链接' }
  ];
  circles.forEach(d => {
    slide.addShape(pptx.ShapeType.ellipse, { x: d.x, y: d.y, w: d.w, h: d.h, fill: { color: d.color, transparency: 67 }, line: { color: d.color, width: 2 } });
    slide.addText(d.label, { x: d.x + 1.12, y: d.y + 0.84, w: 0.78, h: 0.62, fontFace: FONT_MONO, fontSize: 30, bold: true, color: d.color, align: 'center', margin: 0 });
    slide.addText(d.sub, { x: d.x + 0.42, y: d.y + 1.62, w: 2.15, h: 0.62, fontFace: FONT, fontSize: 10.3, color: C.ink, align: 'center', margin: 0, fit: 'shrink' });
  });
  addCard(slide, 8.65, 1.62, 3.85, 1.55, '旧规则回答', '引用 URL ∈ S ∪ F ∪ L 吗？\n——能解释 URL 从哪里来。', { accent: C.green, fill: C.paleTeal, bodySize: 13 });
  addCard(slide, 8.65, 3.45, 3.85, 2.05, '仍然回答不了', '• 支持段落真的交付了吗？\n• 引用是否就地绑定 claim？\n• 页面是否语义支持？\n• 来源角色是否适合该推断？', { accent: C.red, fill: C.paleRed, bodySize: 12.3 });
  addEquationBox(slide, 'URL 可解释  ≠  引用支持  ≠  证据完成', 2.0, 5.86, 6.3, 0.64, { fill: C.navy2, fontFace: FONT, fontSize: 16 });
  addFooter(slide, 'DRA current method §10.3–10.4; S/F/L terminology normalized in DRA v3.2 §7.3');
  addNotes(slide, 'S、F、L 分别是搜索暴露、成功抓取、页面链接出现。旧 provenance 很适合检测 URL 是否可由本次运行解释，但它没有把支持段落和附近 claim 绑定起来。');
}

// 09 — Fact failure
{
  const slide = newSlide();
  addTitle(slide, '问题一：Fact 检查得很确定，但测到的不是“研究完成度”', 'Part I · Failure 1');
  addCard(slide, 0.78, 1.52, 4.0, 4.62, 'Fact 实际检查什么', '1. 识别商品实体\n2. 抽取价格或 overall rating\n3. 在 ±40 字符窗口绑定实体\n4. 对照商城 DB truth\n5. 检查同句商品 citation\n6. 计算 precision × recall volume', { accent: C.blue, bodySize: 13 });
  addCard(slide, 4.98, 1.52, 3.05, 4.62, '它的确定性优势', '• 数值可复现\n• 型号绑定可审计\n• 相似变体不共享事实\n• 可作为具体 check 的 verifier', { accent: C.green, fill: C.paleTeal, bodySize: 13.2 });
  addCard(slide, 8.23, 1.52, 4.32, 4.62, '为什么固定 0.39 不合理', '• 很多题没有足够可比数值\n• 技术机制、耐久、冲突与取舍没有进入\n• “无可检查 claim”直接为 0\n• 写对外围价格可能掩盖核心研究缺失\n• 字段多的题天然获得更多奖励机会', { accent: C.red, fill: C.paleRed, bodySize: 13 });
  slide.addText('裁决：保留 deterministic parser，但把它下沉为 research check 的执行器。', {
    x: 1.85, y: 6.43, w: 9.65, h: 0.37, fontFace: FONT, fontSize: 14.2, bold: true, color: C.navy, align: 'center', margin: 0
  });
  addFooter(slide, 'DRA current method §10.6; DRA v3.2 §2.3, §9.1');
  addNotes(slide, 'Fact 不是没用，而是应该在需要价格、规格、评分等原子前提时执行。它不应以固定报告级权重代表整个 Deep Research 质量。');
}

// 10 — PoF failure
{
  const slide = newSlide();
  addTitle(slide, '问题二：抓取过页面，不等于模型看到了支持内容，更不等于正确使用', 'Part I · Failure 2');
  const stages = [
    ['HTTP 200', '服务器返回页面', C.blue],
    ['Raw fetch', '工具获得原始正文', C.cyan],
    ['Delivered artifact', '经过解析/分块/摘要后交付模型', C.teal],
    ['Local use', '报告 claim 与引用就地绑定', C.orange],
    ['Verified support', 'span 支持且来源角色适合', C.green]
  ];
  stages.forEach((d, i) => {
    const x = 0.68 + i * 2.52;
    addCard(slide, x, 2.0, 2.18, 2.45, d[0], d[1], { accent: d[2], titleSize: 13.2, bodySize: 11.3, shadow: false });
    if (i < stages.length - 1) addArrow(slide, x + 2.18, 3.19, x + 2.47, 3.19, C.muted, 1.4);
  });
  slide.addShape(pptx.ShapeType.line, { x: 0.86, y: 5.0, w: 3.95, h: 0, line: { color: C.red, width: 4 } });
  slide.addText('旧 ProofOfFetch 大致停在这里', { x: 1.1, y: 5.12, w: 3.5, h: 0.35, fontFace: FONT, fontSize: 12.5, bold: true, color: C.red, align: 'center', margin: 0 });
  slide.addShape(pptx.ShapeType.line, { x: 5.73, y: 5.0, w: 6.22, h: 0, line: { color: C.green, width: 4 } });
  slide.addText('DRA 真正需要证据门覆盖的区间', { x: 6.4, y: 5.12, w: 5.0, h: 0.35, fontFace: FONT, fontSize: 12.5, bold: true, color: C.green, align: 'center', margin: 0 });
  addCard(slide, 2.1, 5.78, 9.15, 0.75, '根本问题', '把 PoF 作为独立加分项，会奖励“抓了但没用”；而“写对了但没看证据”又可能被其他质量项补回来。', { accent: C.orange, fill: C.paleOrange, titleSize: 12.5, bodySize: 11.8, shadow: false });
  addFooter(slide, 'DRA current method §10.4–10.5; DRA v3.2 §2.4, §7.2');
  addNotes(slide, '新版必须记录 raw fetch 到 delivered artifact 的变换血统。只有支持跨度确实进入模型可见上下文，才能认为本次运行观察到了证据。');
}

// 11 — Completeness / route binding
{
  const slide = newSlide();
  addTitle(slide, '问题三：Completeness 容易把“答案键覆盖”变成“复现出题者路线”', 'Part I · Failure 3');
  slide.addText('出题时用过的页面', { x: 0.95, y: 1.58, w: 2.4, h: 0.4, fontFace: FONT, fontSize: 16, bold: true, color: C.red, align: 'center', margin: 0 });
  slide.addShape(pptx.ShapeType.roundRect, { x: 0.84, y: 2.08, w: 2.65, h: 3.25, fill: { color: C.paleRed }, line: { color: C.red, width: 1.6 } });
  ['商品页 A', '概念页 B', '论坛页 C', '预选推荐 D'].forEach((t, i) => addPill(slide, t, 1.3, 2.45 + i * 0.63, 1.72, C.red, C.white));
  addArrow(slide, 3.55, 3.62, 5.0, 3.62, C.red, 3);
  addCard(slide, 5.12, 2.0, 3.05, 3.42, '旧答案键', '14–17 个 vital slots\n+ 虚拟论坛 slot\n+ concept nuggets\n+ structured nuggets\n\n覆盖越多，Completeness 越高', { accent: C.orange, bodySize: 13.2 });
  addArrow(slide, 8.25, 3.62, 9.33, 3.62, C.orange, 3);
  addCard(slide, 9.45, 1.82, 3.1, 1.42, '测到了什么？', '是否命中了我们预先保存的内容与 URL 路线', { accent: C.red, fill: C.paleRed, bodySize: 12.2 });
  addCard(slide, 9.45, 3.62, 3.1, 1.82, '真正想测什么？', '是否用任何真实、充分、角色合适的证据完成同一研究要求', { accent: C.green, fill: C.paleTeal, bodySize: 12.2 });
  addEquationBox(slide, 'Known witness 只应证明“可答”  ·  不应成为 URL allowlist', 2.2, 5.85, 8.95, 0.68, { fill: C.navy2, fontFace: FONT, fontSize: 16 });
  addFooter(slide, 'DRA current method §10.7; DRA route-flexible pilot; DRA v3.2 §2.5, §4.5');
  addNotes(slide, '强调 route-binding。出题者使用的 witness 是答案存在性的证书，不是参赛系统必须复现的路径。运行时应按证据合同接受未预选但合格的在册页面。');
}

// 12 — Multiplication and arbitrary weights
{
  const slide = newSlide();
  addTitle(slide, '问题四：报告级乘法把局部证据错误“平均掉”，任意权重又难以解释', 'Part I · Failure 4');
  addEquationBox(slide, 'Truth_old = Provenance × (0.39F + 0.28PoF + 0.33C)', 1.05, 1.45, 11.25, 0.78, { fill: C.navy2, fontSize: 20 });
  const cases = [
    ['关键推荐无证据', '只让整体 provenance 小幅下降；其余段落仍可能把总分拉高', C.red],
    ['抓了很多无关页', 'PoF 仍可能得分，却没有完成任何研究要求', C.orange],
    ['文风与引用光环', 'Quality judge 或 completeness 已奖励“像报告”，再乘 grounding 可能重复计分', C.purple],
    ['权重 / 指数敏感', '0.39/0.28/0.33 与 ^1.5 不能从构念自然推导，换参数可能翻榜', C.blue]
  ];
  cases.forEach((d, i) => addCard(slide, 0.78 + (i % 2) * 6.08, 2.68 + Math.floor(i / 2) * 1.7, 5.72, 1.38, d[0], d[1], { accent: d[2], titleSize: 14, bodySize: 11.6, shadow: false }));
  slide.addText('证据门应该放在每个可验证研究要求内部，而不是整篇报告末尾。', {
    x: 1.35, y: 6.2, w: 10.65, h: 0.42, fontFace: FONT, fontSize: 17, bold: true, color: C.navy, align: 'center', margin: 0
  });
  addFooter(slide, 'DRA v3.2 §2.6–2.7; literature review found no report-level product precedent among surveyed DR benchmarks');
  addNotes(slide, '报告级乘法不是数学上非法，而是不能表达“哪条研究义务由哪份证据支撑”。新版把乘法保留为 check 内的逻辑门 C×E。');
}

// 13 — Pilot
{
  const slide = newSlide();
  addTitle(slide, '一个真实 pilot 暴露了问题：0 分不等于“完全没做”', 'Part I · Empirical motivation', '同一份音频购买报告，用三种视角得到完全不同的诊断。');
  const bars = [
    ['旧固定路线评分', 0, 15, C.red, '0 / 15'],
    ['内容完成度', 5, 9, C.orange, '5 / 9  ·  55.6%'],
    ['有证据完成度', 1, 9, C.teal, '1 / 9  ·  11.1%']
  ];
  bars.forEach((d, i) => {
    const y = 1.72 + i * 1.25;
    slide.addText(d[0], { x: 0.86, y, w: 2.25, h: 0.42, fontFace: FONT, fontSize: 14, bold: true, color: C.navy, margin: 0 });
    slide.addShape(pptx.ShapeType.roundRect, { x: 3.2, y: y + 0.02, w: 6.4, h: 0.42, fill: { color: C.soft }, line: { color: C.line } });
    const frac = d[1] / d[2];
    if (frac > 0) slide.addShape(pptx.ShapeType.roundRect, { x: 3.2, y: y + 0.02, w: 6.4 * frac, h: 0.42, fill: { color: d[3] }, line: { color: d[3] } });
    slide.addText(d[4], { x: 9.85, y: y - 0.01, w: 2.15, h: 0.45, fontFace: FONT_MONO, fontSize: 14, bold: true, color: d[3], margin: 0 });
  });
  addCard(slide, 0.82, 5.42, 3.72, 1.05, '报告确实做了', '设计、IPX7、电池、Hi-Res 等 5 个必要方向', { accent: C.orange, fill: C.paleOrange, titleSize: 12.5, bodySize: 10.8, shadow: false });
  addCard(slide, 4.76, 5.42, 3.72, 1.05, '但证据很弱', '只有 Ortizan 商品页同时满足内容、引用、观察与支持', { accent: C.teal, fill: C.paleTeal, titleSize: 12.5, bodySize: 10.8, shadow: false });
  addCard(slide, 8.7, 5.42, 3.72, 1.05, '核心诊断', '旧 0/15 同时混入“没走预设路线”和“证据不足”', { accent: C.red, fill: C.paleRed, titleSize: 12.5, bodySize: 10.8, shadow: false });
  addFooter(slide, 'Route-flexible pilot: dra_v3_dev_audio_0002; old fixed route 0/15, content 5/9, grounded 1/9');
  addNotes(slide, 'pilot 不是正式榜结果，但非常适合作为方法动机。新评分需要保留“做了一部分”的信息，同时严格区分内容写到与证据真正通过。');
}

// 14 — Requirements
{
  const slide = newSlide();
  addTitle(slide, '替代方案必须同时满足八个约束', 'Part I · Design requirements', '不是“加一个更强 judge”就能解决。');
  const req = [
    ['自动化高', '不为每题从零写复杂答案 rubric', C.blue],
    ['可复现', '固定 world / compiler / matcher / judge / scorer 版本', C.teal],
    ['同一程序', '12 个 harness 使用同一语义，不按工具名特判', C.orange],
    ['证据可审计', 'URL、交付 span、绑定、支持、来源角色可下钻', C.purple],
    ['广度有分母', '从 query facets 编译，不用 URL 数或篇幅代替', C.green],
    ['不绑路线', '新在册证据满足合同即可通过', C.blue],
    ['排名简单', '一个主分能一句话解释，不重新发明复合指数', C.orange],
    ['边界诚实', '不声称穷尽全部语义或覆盖未来所有策略', C.red]
  ];
  req.forEach((d, i) => {
    const col = i % 4;
    const row = Math.floor(i / 4);
    addCard(slide, 0.62 + col * 3.18, 1.52 + row * 2.28, 2.92, 1.92, d[0], d[1], { accent: d[2], titleSize: 14.2, bodySize: 11.2, shadow: false });
  });
  addEquationBox(slide, '目标：测“有证据地覆盖了多少必要研究工作”，并把 URL 造假独立、强制地暴露出来', 1.3, 6.2, 10.75, 0.63, { fill: C.navy2, fontFace: FONT, fontSize: 15.2 });
  addFooter(slide, 'DRA v3.2 §1, §17.1; user-locked design principles');
  addNotes(slide, '这一页把后续所有设计选择变成约束满足问题。特别强调自动化、固定程序和不依赖复杂人工 rubric 是不可丢的初心。');
}

// 15 — Section II
addSectionSlide(2, 'DRA 真正应该怎样评', '把 Deep Research 拆成发现 → 观察 → 利用 → 完成；广度有分母，质量有独立面板。', C.teal);

// 16 — Four stages
{
  const slide = newSlide();
  addTitle(slide, '一条研究结论要经过四个阶段', 'Part II · Evaluation object');
  const stages = [
    ['发现 Discover', '搜索暴露相关 URL 或从链接进入', 'SearchExposed', C.blue],
    ['观察 Observe', '支持内容经过 adapter 变换后真正交付', 'Delivered', C.teal],
    ['利用 Use', '报告就地引用、正确绑定并使用证据', 'Bound & Supported', C.orange],
    ['完成 Complete', '完成 query 要求的比较、解释或建议', 'Research Check Pass', C.green]
  ];
  stages.forEach((d, i) => {
    const x = 0.7 + i * 3.14;
    addCard(slide, x, 1.82, 2.75, 3.5, d[0], d[1], { accent: d[3], bodySize: 12.6, titleSize: 15.2 });
    addPill(slide, d[2], x + 0.42, 4.48, 1.9, d[3], C.white);
    if (i < 3) addArrow(slide, x + 2.78, 3.56, x + 3.08, 3.56, C.muted, 1.6);
  });
  slide.addText('过程诊断', { x: 1.05, y: 5.75, w: 2.1, h: 0.32, fontFace: FONT, fontSize: 13, bold: true, color: C.blue, align: 'center', margin: 0 });
  slide.addShape(pptx.ShapeType.line, { x: 0.85, y: 6.12, w: 5.78, h: 0, line: { color: C.blue, width: 3 } });
  slide.addText('正式主分：完成 + 每个外部前提通过证据门', { x: 7.05, y: 5.75, w: 5.05, h: 0.32, fontFace: FONT, fontSize: 13, bold: true, color: C.green, align: 'center', margin: 0 });
  slide.addShape(pptx.ShapeType.line, { x: 6.75, y: 6.12, w: 5.68, h: 0, line: { color: C.green, width: 3 } });
  addFooter(slide, 'DRA v3.2 §1, §11 — Search → delivery → utilization → verified pass funnel');
  addNotes(slide, '发现不等于观察，观察不等于利用，利用不等于完成。DRA-GRC 在“完成”层计分，但证据门会检查此前关键环节。');
}

// 17 — Breadth denominator
{
  const slide = newSlide();
  addTitle(slide, 'Deep Research 的“广度”必须由 query 定义分母', 'Part II · Breadth');
  addCard(slide, 0.72, 1.45, 3.2, 4.8, '错误的广度代理', '• 访问 URL 数\n• 搜索次数\n• 引用数量\n• 报告字数\n• 事实原子数量\n\n这些都能被重复页、无关页、冗长写作或字段密度刷高。', { accent: C.red, fill: C.paleRed, bodySize: 14 });
  addArrow(slide, 4.1, 3.8, 5.0, 3.8, C.orange, 3);
  addCard(slide, 5.18, 1.45, 7.42, 4.8, '正确的分母：query facets → research units → checks', '', { accent: C.green, fill: C.white });
  const facets = [
    ['技术与营销', ['识别主张', '解释机制', '说明不能推出什么']],
    ['用户场景', ['噪声/预算/空间约束', '条件差异', '风险边界']],
    ['方案比较', ['共同维度', '跨页对齐', '冲突处理']],
    ['推荐与行动', ['多个可行方案', '取舍理由', '可执行建议']]
  ];
  facets.forEach((d, i) => {
    const x = 5.55 + (i % 2) * 3.38;
    const y = 2.05 + Math.floor(i / 2) * 1.72;
    slide.addShape(pptx.ShapeType.roundRect, { x, y, w: 3.0, h: 1.37, fill: { color: i % 2 ? C.paleTeal : C.paleBlue }, line: { color: i % 2 ? C.teal : C.blue, width: 1 } });
    slide.addText(d[0], { x: x + 0.15, y: y + 0.13, w: 2.7, h: 0.3, fontFace: FONT, fontSize: 13, bold: true, color: C.navy, margin: 0 });
    slide.addText(d[1].join(' · '), { x: x + 0.15, y: y + 0.55, w: 2.7, h: 0.55, fontFace: FONT, fontSize: 9.8, color: C.muted, margin: 0, fit: 'shrink' });
  });
  addEquationBox(slide, '广度 = 在平级用户研究方向上，完成了多少可执行检查', 2.0, 6.42, 9.35, 0.5, { fill: C.navy2, fontFace: FONT, fontSize: 15 });
  addFooter(slide, 'DRA v3.2 §6.7–6.8, §15.1; WideSearch supplies the “explicit denominator” lesson');
  addNotes(slide, 'facet 来自用户明示需求和不可删除的研究义务。每个 facet 等权，避免一个有很多规格字段的方向淹没一个需要真正综合的方向。');
}

// 18 — Atom/check/unit/facet
{
  const slide = newSlide();
  addTitle(slide, '评分对象的层级：事实是证据，研究工作才是一分', 'Part II · Hierarchy');
  const levels = [
    ['Evidence atom', '网页里一个规格、主张、机制说明或用户经验事件', C.blue, 0.9, 4.2],
    ['Research check', '对报告局部能力的可执行检查；内容合同 + 证据合同', C.teal, 3.28, 5.2],
    ['Research unit', '用户可感知的一项完整调研工作：比较、审核、教程、推荐', C.orange, 5.95, 6.0],
    ['Query facet', '平衡用户的多个研究方向，防止事实数量决定权重', C.purple, 9.0, 3.3]
  ];
  levels.forEach((d, i) => {
    slide.addShape(pptx.ShapeType.roundRect, { x: d[4], y: 1.85 + i * 1.02, w: 8.0 - i * 0.9, h: 0.78, fill: { color: d[2], transparency: 7 + i * 4 }, line: { color: d[2], width: 1.2 } });
    slide.addText(d[0], { x: d[4] + 0.22, y: 2.02 + i * 1.02, w: 1.65, h: 0.3, fontFace: FONT_MONO, fontSize: 11.2, bold: true, color: C.white, margin: 0, fit: 'shrink' });
    slide.addText(d[1], { x: d[4] + 2.0, y: 2.0 + i * 1.02, w: 5.4 - i * 0.8, h: 0.34, fontFace: FONT, fontSize: 11.5, color: C.white, margin: 0, fit: 'shrink' });
  });
  addCard(slide, 0.78, 1.58, 3.0, 4.82, '例：审核“Hi-Res 蓝牙”宣传', 'Atom：商品页是否写 Hi-Res\n\nChecks：\n1. 准确转述主张\n2. 用机制/条件解释能推出什么\n3. 说明不能推出什么\n4. 连接到用户决策\n\nUnit：完成一次技术宣传审核\nFacet：技术与营销', { accent: C.orange, bodySize: 12.2 });
  addFooter(slide, 'DRA v3.2 §1, §4.7, §9');
  addNotes(slide, '这一层级解决 rubric 粒度和事实密度问题。原子事实不会因为数量多就自动拿更多主分，它们只是完成更高层 research checks 的前提。');
}

// 19 — Link failure taxonomy
{
  const slide = newSlide();
  addTitle(slide, '链接真实性没有被取消：先分清“虚构”、“越界”与“基准错误”', 'Part II · Link integrity');
  const rows = [
    ['失败类型', '判定', '含义', '主分处理'],
    ['nonexistent_fabrication', 'URL 在 canonicalize / alias / redirect 盲复核后确认不存在', '真正的虚构引用', '对应 check 失败；整道 task 清零'],
    ['off_world_citation', 'URL 真实，但不属于冻结 registry / snapshot', '越出评测世界，不能据此证明本次调研', '引用无资格；check 失败；独立 protocol flag'],
    ['canonicalization_or_registry_error', 'URL 真实且应在世界内，但 alias / redirect / registry 漏记', 'benchmark 仪器错误，不是 harness 造假', '暂停裁决；修复后全体同 epoch 重算'],
    ['malformed_citation', '引用格式或拼写有误，但可唯一恢复目标', '呈现 / 格式违约，不自动等同虚构', '按公开 canonicalization 规则裁决；记独立 flag']
  ];
  addMiniTable(slide, rows, 0.55, 1.42, [2.3, 3.2, 3.15, 3.55], 0.92, { headerSize: 10.2, bodySize: 10.2 });
  slide.addText('registry membership 可以判“是否属于冻结世界”，但不能单独判“现实互联网上是否存在”。', {
    x: 1.0, y: 6.32, w: 11.25, h: 0.38, fontFace: FONT, fontSize: 12.2, bold: true, color: C.navy, align: 'center', margin: 0
  });
  addFooter(slide, 'DRA proposed integrity taxonomy; v3.2 terminology refined for the presentation');
  addNotes(slide, '冻结 registry 不是互联网存在性谕机。因此必须把确认不存在的虚构 URL，与真实但越出冻结世界的 URL 分开。两者都不能支持得分，但只有前者默认触发任务级造假门。');
}

// 20 — Evidence use failures
{
  const slide = newSlide();
  addTitle(slide, 'URL 真实也不够：证据必须本次交付、就地绑定并真的支持', 'Part II · Evidence-use failures');
  const rows = [
    ['失败类型', '判定', '含义', '处理'],
    ['unobserved_citation', 'URL 存在，但支持 span 本次未交付', '可能靠参数知识或事后补引用', '对应 check 失败'],
    ['unsupported_citation', '页面已交付，但不支持附近说法', '主题相关不等于证据支持', '对应 check 失败'],
    ['wrong_binding', '页面可能支持，但引用没有绑定对应 claim', '读者无法知道引用支撑哪句话', '对应 check 失败'],
    ['contradicted_citation', '页面实际反驳报告', '方向性事实错误', 'check 失败；决定性结论记 critical'],
    ['source_role_misuse', '来源角色不满足合同', '营销主张被冒充独立测量等', '对应 check 失败']
  ];
  addMiniTable(slide, rows, 0.55, 1.42, [2.25,3.35,3.65,3.05], 0.78, { headerSize: 10.2, bodySize: 10.4 });
  addCard(slide, 0.95, 6.1, 5.52, 0.73, '不一票否决整题', '这些默认只使对应 check 失败；决定性反驳另记 critical error。', { accent: C.teal, fill: C.paleTeal, titleSize: 10.5, bodySize: 8.9, shadow: false });
  addCard(slide, 6.85, 6.1, 5.52, 0.73, '可下钻', '每个 verdict 必须指向 report span、evidence span、delivery record 和合同前提。', { accent: C.blue, fill: C.paleBlue, titleSize: 10.5, bodySize: 8.9, shadow: false });
  addFooter(slide, 'Evidence-use diagnostics: observation · support · binding · contradiction · source role');
  addNotes(slide, '这些分类解决“一个报告到底好在哪、坏在哪”。只有 URL 真实不代表证据真的进入过当次模型上下文，也不代表它支持附近说法。');
}

// 20 — Quality panel
{
  const slide = newSlide();
  addTitle(slide, '报告质量要评，但不能再乘回主分', 'Part II · Long-form quality', '“有没有完成”由 Research Test Suite 判断；“完成得怎样”由独立质量面板判断。');
  const axes = [
    ['Synthesis', '多份证据是否组织成连贯比较、机制或因果链', C.blue],
    ['Uncertainty & Conflict', '是否诚实表达条件、冲突、证据强弱与未知', C.teal],
    ['Decision / User Utility', '是否回应预算、场景、风险、步骤与取舍', C.orange],
    ['Presentation', '结构、连贯、简洁、可读、引用呈现自然', C.purple]
  ];
  axes.forEach((d, i) => {
    const x = 0.76 + i * 3.08;
    addCard(slide, x, 1.72, 2.78, 3.25, d[0], d[1], { accent: d[2], titleSize: 13.5, bodySize: 12.2 });
    slide.addShape(pptx.ShapeType.ellipse, { x: x + 0.84, y: 4.28, w: 1.1, h: 0.28, fill: { color: d[2], transparency: 15 }, line: { color: d[2] } });
  });
  addCard(slide, 1.15, 5.45, 5.2, 1.02, '评法', '同题、同轴、匿名两两比较；位置交换；固定 anchor reports；遮蔽 harness 与 DRA-GRC。', { accent: C.green, fill: C.paleTeal, titleSize: 12.5, bodySize: 10.7, shadow: false });
  addCard(slide, 6.95, 5.45, 5.2, 1.02, '榜单角色', '单独展示四轴与人工校准；不合成 Overall，不用成本或质量面板偷偷破同分。', { accent: C.red, fill: C.paleRed, titleSize: 12.5, bodySize: 10.7, shadow: false });
  addFooter(slide, 'DRA v3.2 §16; ALCE separates fluency/correctness/citation quality (arXiv:2305.14627)');
  addNotes(slide, '质量面板不再判断事实真假或 URL 真实，只看相同 grounded work 完成后的表达、综合和效用差异。这样避免双重计分。');
}

// 21 — Section III
addSectionSlide(3, '美团 LoHoSearch：全量世界如何真正被利用', '详细拆解：全图轻量建模、局部子图采样、自然语言化、唯一性检查、难度过滤与人工审核。', C.orange);

// 22 — LoHoSearch overview
{
  const slide = newSlide();
  addTitle(slide, 'LoHoSearch 一页概览', 'Part III · Meituan LoHoSearch', '这是一套长时程 Search Agent 基准，不是长篇 Deep Research 报告基准。');
  addCard(slide, 0.72, 1.46, 4.1, 4.9, '论文与目标', 'LoHoSearch: Benchmarking Long-Horizon Search Agents Beyond the Human Difficulty Ceiling\n\n美团团队\n2026-06-11 提交；v2 2026-06-17\n\n目标：用全局图统计系统性提高单题搜索空间和结构复杂度。', { accent: C.orange, bodySize: 13.2 });
  addKpi(slide, '7.62M', 'Wikipedia 实体节点', 5.22, 1.72, 2.05, { color: C.green });
  addKpi(slide, '265M', '正文有向超链接', 7.48, 1.72, 2.05, { color: C.green });
  addKpi(slide, '544', '人工复核问题', 9.75, 1.72, 1.55, { color: C.blue });
  addKpi(slide, '11', '主题领域', 11.25, 1.72, 1.25, { color: C.blue });
  addKpi(slide, '34.74%', '最强系统准确率', 5.22, 3.47, 2.25, { color: C.red });
  addKpi(slide, '61', '正确轨迹平均工具调用', 7.75, 3.47, 2.1, { color: C.orange });
  addKpi(slide, '+6.8', 'DeepSeek-V4-Flash 上下文实验绝对增益', 10.05, 3.47, 2.3, { color: C.purple });
  addCard(slide, 5.15, 5.15, 7.3, 1.18, '对 DRA 最重要的启发', '“全量”只做便宜、稳定、可复现的结构；昂贵语义生成、验证和人工审核只发生在采样局部。', { accent: C.teal, fill: C.paleTeal, titleSize: 13, bodySize: 12.4, shadow: false });
  addFooter(slide, 'LoHoSearch, arXiv:2606.12837v2, Abstract & §1–§3 · https://arxiv.org/abs/2606.12837');
  addNotes(slide, '先把工作定位清楚：它测的是最终唯一实体答案和长时程搜索，不生成长报告。我们借鉴其数据构建工程原则，不照搬评分对象。');
}

// 23 — Difficulty ceiling and figure 1
{
  const slide = newSlide();
  addTitle(slide, 'LoHoSearch 的出发点：作者将快速饱和归因于人工缺少全局统计视角', 'Part III · Motivation');
  const img = path.join(ASSET_DIR, 'lohosearch-img-000.png');
  addCard(slide, 0.62, 1.32, 8.45, 4.82, 'BrowseComp 在十个月内快速饱和', '', { line: C.line, shadow: false });
  addImageContain(slide, img, 0.82, 1.72, 8.05, 3.9);
  slide.addText('论文 Figure 1', { x: 0.95, y: 5.72, w: 1.3, h: 0.22, fontFace: FONT, fontSize: 8.5, color: C.muted, margin: 0 });
  addCard(slide, 9.32, 1.32, 3.38, 2.08, '原因：人没有全局统计视角', '人工更容易选择熟悉、流行、直接相连的实体；约束数量和候选空间难以系统控制。', { accent: C.red, fill: C.paleRed, bodySize: 12.5 });
  addCard(slide, 9.32, 3.68, 3.38, 2.46, '两条难度轴', '① 单个约束的搜索空间\n候选越多，验证与排除越长。\n\n② 结构复杂度\n多个约束必须联合满足，图中循环与交叉约束难以分解。', { accent: C.orange, fill: C.paleOrange, bodySize: 12 });
  addFooter(slide, 'Source: LoHoSearch Figure 1 and §1, arXiv:2606.12837v2 (CC BY 4.0)');
  addNotes(slide, '这是 LoHoSearch 的论证和设计动机，不是一个已被因果实验证明的通用规律。论文不是简单增加 hop 数，而是同时放大单关系候选集和联合约束结构。');
}

// 24 — Figure 2 pipeline
{
  const slide = newSlide(C.white);
  addTitle(slide, 'LoHoSearch 的完整数据构建流水线', 'Part III · Pipeline', '四阶段：知识图谱构建 → 子图采样 → QA 生成与验证 → 后过滤与人工审核。');
  const img = path.join(ASSET_DIR, 'lohosearch-figure-2-pipeline.png');
  addImageContain(slide, img, 0.58, 1.28, 12.18, 5.48);
  addFooter(slide, 'Source: LoHoSearch Figure 2, arXiv:2606.12837v2, p.3 (CC BY 4.0)');
  addNotes(slide, '这一页停留稍久。指出真正的全量工作只在左侧：页面、链接、P31 类型与入度。关系描述抽取、问题生成和人工审核都在采样子图或最终问题上。');
}

// 25 — Stage 1 KG construction
{
  const slide = newSlide();
  addTitle(slide, '阶段一：全量遍历 Wikipedia，但只构建廉价结构图', 'Part III · Stage 1');
  const x0 = 0.82;
  slide.addShape(pptx.ShapeType.ellipse, { x: x0, y: 2.15, w: 1.55, h: 1.55, fill: { color: C.paleBlue }, line: { color: C.blue, width: 2 } });
  slide.addText('Page', { x: x0 + 0.3, y: 2.67, w: 0.95, h: 0.38, fontFace: FONT_MONO, fontSize: 18, bold: true, color: C.blue, align: 'center', margin: 0 });
  const targets = [
    ['Body hyperlink', 3.4, 1.52, C.teal],
    ['Wikidata P31 type', 3.4, 2.82, C.orange],
    ['In-degree popularity', 3.4, 4.12, C.purple]
  ];
  targets.forEach(d => {
    addArrow(slide, 2.4, 2.92, d[1] - 0.15, d[2] + 0.45, d[3], 1.7);
    addCard(slide, d[1], d[2], 2.75, 0.92, d[0], '', { accent: d[3], shadow: false, titleSize: 13.5 });
  });
  addCard(slide, 6.68, 1.42, 5.78, 4.85, '这一步没有做什么', '', { accent: C.red, fill: C.paleRed });
  addBulletList(slide, [
    { text: '没有让 LLM 为 762 万页面抽取“全部事实”', bulletColor: C.red },
    { text: '没有在全库生成自然语言关系描述', bulletColor: C.red },
    { text: '没有在全库尝试每种问题或答案路线', bulletColor: C.red },
    { text: '没有以图谱为现实世界完整真理', bulletColor: C.red }
  ], 7.05, 2.25, 5.0, 2.7, { fontSize: 13.2 });
  addEquationBox(slide, '全量成本 ≈ 解析 + 链接 + 类型 + 统计', 7.35, 5.42, 4.4, 0.58, { fill: C.navy2, fontFace: FONT, fontSize: 14 });
  addKpi(slide, '7.62M', 'nodes', 1.0, 5.58, 1.6, { color: C.blue, align: 'center' });
  addKpi(slide, '265M', 'directed edges', 3.0, 5.58, 1.85, { color: C.teal, align: 'center' });
  addFooter(slide, 'LoHoSearch §2.1, arXiv:2606.12837v2');
  addNotes(slide, '这是 DRA 从 LoHoSearch 得到的关键纠偏：全量轻量索引是可行的，全量开放式语义抽取则不是论文做过的事情。');
}

// 26 — Tree sampling
{
  const slide = newSlide();
  addTitle(slide, '阶段二 A：树结构用“交集唯一 + 删除不唯一”保证约束必要', 'Part III · Stage 2 · Tree sampling');
  // Tree drawing
  const nodes = [
    ['ans', 3.0, 1.55, C.navy2],
    ['E₁₁', 1.55, 2.8, C.blue], ['E₁₂', 3.0, 2.8, C.blue], ['E₁₃', 4.45, 2.8, C.blue],
    ['E₂₁', 1.15, 4.12, C.green], ['E₂₂', 1.95, 4.12, C.green],
    ['E₂₃', 2.8, 4.12, C.orange],
    ['E₂₄', 4.05, 4.12, C.red], ['E₂₅', 4.85, 4.12, C.red]
  ];
  const edges = [[0,1],[0,2],[0,3],[1,4],[1,5],[2,6],[3,7],[3,8]];
  edges.forEach(([a,b]) => addArrow(slide, nodes[a][1]+0.28, nodes[a][2]+0.28, nodes[b][1]+0.28, nodes[b][2]+0.28, '8FA0B6', 1));
  nodes.forEach(d => {
    slide.addShape(pptx.ShapeType.ellipse, { x: d[1], y: d[2], w: 0.58, h: 0.58, fill: { color: d[3], transparency: d[0]==='ans'?0:75 }, line: { color: d[3], width: 1.4 } });
    slide.addText(d[0], { x: d[1]+0.03, y: d[2]+0.14, w: 0.52, h: 0.2, fontFace: FONT_MONO, fontSize: 9.5, bold: true, color: d[0]==='ans'?C.white:C.navy, align: 'center', margin: 0 });
  });
  addCard(slide, 6.2, 1.43, 6.28, 4.85, '默认参数与三条约束', '', { accent: C.orange });
  addBulletList(slide, [
    { text: 'N = 3 个一级关系；每个中间实体最多 M = 2 个二级关系；τ = 3', bulletColor: C.orange },
    { text: '每个关系的候选搜索空间 |S| > τ', bulletColor: C.blue },
    { text: '任意删除一个一级关系，剩余候选交集仍 > 1 —— 每条关系都必要', bulletColor: C.red },
    { text: '全部 N 个关系的候选交集恰为 {root} —— 图内答案唯一', bulletColor: C.green },
    { text: '二级 pseudo-candidate 不能与其他中间实体组合出另一个唯一答案', bulletColor: C.purple }
  ], 6.58, 2.05, 5.4, 3.72, { fontSize: 12.1 });
  addEquationBox(slide, '∩₁ᴺ Sᵢ = {root}     但     ∩_{j≠i} Sⱼ > 1', 1.08, 5.45, 4.35, 0.76, { fill: C.navy2, fontSize: 18 });
  addFooter(slide, 'LoHoSearch §2.2.1, arXiv:2606.12837v2');
  addNotes(slide, '删除测试是很强的构造思想：任何一级条件被删掉，答案不再唯一，因此每条关系都是必要的。DRA 可以借鉴 deletion test，但目标不是唯一答案，而是必要研究方向。');
}

// 27 — Graph sampling
{
  const slide = newSlide();
  addTitle(slide, '阶段二 B：图结构用循环与交叉约束提高不可分解性', 'Part III · Stage 2 · Graph sampling');
  const pts = [
    [2.2,1.72,C.blue,'E_B'], [0.95,2.75,C.orange,'E_A'], [3.65,2.75,C.gray || C.muted,'ans'],
    [1.15,4.18,C.red,'E_D'], [2.45,4.58,C.orange,'E_E'], [3.75,4.12,C.green,'E_C']
  ];
  const graphEdges = [[0,1],[0,2],[0,3],[0,4],[0,5],[1,3],[1,4],[2,5],[3,4],[4,5],[1,5]];
  graphEdges.forEach(([a,b]) => slide.addShape(pptx.ShapeType.line, { x: pts[a][0]+0.28, y: pts[a][1]+0.28, w: pts[b][0]-pts[a][0], h: pts[b][1]-pts[a][1], line: { color: '4B5563', width: 1.2 } }));
  pts.forEach(d => {
    slide.addShape(pptx.ShapeType.ellipse, { x: d[0], y: d[1], w: 0.62, h: 0.62, fill: { color: d[2], transparency: d[3]==='ans'?15:70 }, line: { color: d[2], width: 1.6 } });
    slide.addText(d[3], { x: d[0]+0.04, y: d[1]+0.16, w: 0.54, h: 0.22, fontFace: FONT_MONO, fontSize: 9.5, bold: true, color: C.navy, align: 'center', margin: 0 });
  });
  addCard(slide, 5.35, 1.42, 3.18, 4.95, '采样', '1. 选低流行度 seed（答案）\n2. 贪心扩展到最多 10 个实体\n3. 优先与当前子图连边最多、关系搜索空间最大的候选\n4. 要求类型多样、边数充分、整体连通', { accent: C.blue, bodySize: 12.5 });
  addCard(slide, 8.78, 1.42, 3.72, 4.95, '唯一性与抗捷径', '• 在完整图上穷举回溯，寻找满足相同类型和有向邻接的替代实体集合\n\n• 找不到替代才确认图级唯一\n\n• 还要求 seed 有足够同类型混淆候选，避免只靠类型枚举暴力解题', { accent: C.green, fill: C.paleTeal, bodySize: 12.5 });
  slide.addText('树：大候选空间   ·   图：大候选空间 + 循环 / 交叉约束', { x: 0.72, y: 5.76, w: 4.25, h: 0.55, fontFace: FONT, fontSize: 14.5, bold: true, color: C.navy, align: 'center', margin: 0, fit: 'shrink' });
  addFooter(slide, 'LoHoSearch §2.2.2, arXiv:2606.12837v2');
  addNotes(slide, '图结构不是简单增加更多节点，而是通过循环和交叉边让问题无法拆成独立子问题。其唯一性检查在完整图上做回溯。');
}

// 28 — QA generation and verification
{
  const slide = newSlide();
  addTitle(slide, '阶段三：图结构不是直接交给 agent，必须转成自然、难检索的问题', 'Part III · Stage 3');
  const steps = [
    ['1', '关系描述抽取', 'LLM 从源实体 Wikipedia 页提取被混淆的关系描述；树叶再抽 1–2 个属性。', C.blue],
    ['2', '关系可检索性验证', '用搜索验证描述不能被直接搜到，也不能被 LLM 轻易猜出；同一实体的多个关系联合验证。', C.teal],
    ['3', '隐藏实体并自然语言化', '把关系和属性组装为结构化描述，隐藏实体名，再由 LLM 改写为自然问题。', C.orange],
    ['4', '两轮自动验证', 'Subgraph coverage：无遗漏/新增/失真；Answer satisfaction：搜索 agent 确认 gold 满足条件。', C.green]
  ];
  steps.forEach((d, i) => {
    const x = 0.65 + i * 3.16;
    slide.addShape(pptx.ShapeType.ellipse, { x: x + 0.9, y: 1.52, w: 0.78, h: 0.78, fill: { color: d[3] }, line: { color: d[3] } });
    slide.addText(d[0], { x: x + 1.03, y: 1.7, w: 0.52, h: 0.28, fontFace: FONT_MONO, fontSize: 15, bold: true, color: C.white, align: 'center', margin: 0 });
    addCard(slide, x, 2.55, 2.82, 3.4, d[1], d[2], { accent: d[3], titleSize: 13.3, bodySize: 11.5 });
    if (i < 3) addArrow(slide, x + 2.83, 4.2, x + 3.1, 4.2, C.muted, 1.4);
  });
  addPill(slide, '所有 LLM 步骤：DeepSeek-V3.2', 5.03, 6.33, 3.25, C.purple, C.palePurple);
  addFooter(slide, 'LoHoSearch §2.3, arXiv:2606.12837v2');
  addNotes(slide, '这一阶段防止生成题退化成关键词搜索。DRA 可借鉴“先结构后自然语言化”和 round-trip coverage check，但我们隐藏的是证据路线，不应隐藏用户研究需求。');
}

// 29 — Post filtering and audit stats
{
  const slide = newSlide();
  addTitle(slide, '阶段四：自动流水线之后，仍需要多 agent 过滤与专业人工审核', 'Part III · Stage 4');
  const flow = [
    ['候选 QA', '约 2,000 original pairs（Figure 2）', C.blue],
    ['唯一性过滤', '多能力搜索 agent 独立尝试；找到替代有效答案即删除', C.teal],
    ['难度过滤', 'DeepSeek-V3.2 多次尝试；多次答对的“容易题”删除', C.orange],
    ['人工审核', '答案正确、唯一性、条件逻辑、语言、冗余', C.purple],
    ['最终集', '544 道，11 个领域', C.green]
  ];
  flow.forEach((d, i) => {
    const x = 0.5 + i * 2.57;
    addCard(slide, x, 1.55, 2.25, 2.25, d[0], d[1], { accent: d[2], titleSize: 13.2, bodySize: 10.6, shadow: false });
    if (i < 4) addArrow(slide, x + 2.25, 2.67, x + 2.51, 2.67, C.muted, 1.4);
  });
  addKpi(slide, '75.5%', '进入专业人工审核的自动构造题：直接通过', 0.9, 4.43, 2.85, { color: C.green, align: 'center' });
  addKpi(slide, '22.3%', '进入专业审核的题：少量修改后通过', 3.75, 4.43, 2.85, { color: C.orange, align: 'center' });
  addKpi(slide, '2.2%', '进入专业审核的题：严重问题被拒', 6.6, 4.43, 2.65, { color: C.red, align: 'center' });
  addKpi(slide, '70.8%', '最终集唯一性审核：明确确认唯一答案', 9.38, 4.43, 2.75, { color: C.blue, align: 'center' });
  addCard(slide, 1.45, 5.82, 10.5, 0.78, '必须诚实报告的 29.2%', '人工没有找到替代答案，但也无法完全排除；“未发现替代”不是“证明唯一”。', { accent: C.red, fill: C.paleRed, titleSize: 12.4, bodySize: 11.1, shadow: false });
  addFooter(slide, 'LoHoSearch §2.4–2.5 and Limitations, arXiv:2606.12837v2');
  addNotes(slide, 'LoHoSearch 的自动化并不等于零人工。它公开了直接通过、轻微修改和严重拒绝比例。DRA 也应公开 compiler 编辑率、致命错误率和人工时间。');
}

// 30 — Results and figure 4
{
  const slide = newSlide();
  addTitle(slide, 'LoHoSearch 的结果：难点不只是“多跳”，而是更长轨迹与上下文管理', 'Part III · Findings');
  const img = path.join(ASSET_DIR, 'lohosearch-img-006.png');
  addCard(slide, 0.58, 1.35, 7.65, 4.85, '正确轨迹工具调用分布（论文 Figure 4）', '', { shadow: false });
  addImageContain(slide, img, 0.86, 1.83, 7.08, 3.75);
  addCard(slide, 8.5, 1.35, 4.2, 1.08, '准确率', 'GPT-5.5：34.74%\nDeepSeek-V4-Pro：15.99%', { accent: C.red, fill: C.paleRed, bodySize: 12.7, titleSize: 12.5, shadow: false });
  addCard(slide, 8.5, 2.67, 4.2, 1.35, '轨迹长度', 'BrowseComp：mean 35 / median 26\nLoHoSearch：mean 61 / median 59\n平均工具调用增加 74%', { accent: C.orange, fill: C.paleOrange, bodySize: 12.4, titleSize: 12.5, shadow: false });
  addCard(slide, 8.5, 4.27, 4.2, 1.23, '结构复杂度', 'DeepSeek-V4-Flash：树题 11.89%\n图题 8.01%', { accent: C.purple, fill: C.palePurple, bodySize: 12.4, titleSize: 12.5, shadow: false });
  addCard(slide, 8.5, 5.75, 4.2, 0.74, '上下文策略', '最佳组合只带来 +6.8 个百分点。', { accent: C.teal, fill: C.paleTeal, bodySize: 10.8, titleSize: 11.5, shadow: false });
  addFooter(slide, 'Source: LoHoSearch Figure 4, Table 2–3, §3.2–3.4, arXiv:2606.12837v2');
  addNotes(slide, '强调 LoHoSearch 的贡献是更长、更难管理的搜索过程。它用最终实体准确率即可评分，因为目标答案形态简单；DRA 的长报告需要更丰富的研究测试。');
}

// 31 — What LoHo proves and does not prove
{
  const slide = newSlide();
  addTitle(slide, 'LoHoSearch 证明了什么，也没有证明什么', 'Part III · Methodological boundary');
  addCard(slide, 0.72, 1.45, 5.85, 4.95, '可以借鉴', '', { accent: C.green, fill: 'F4FFFB' });
  addBulletList(slide, [
    { text: '全量轻量结构索引可以系统控制数据构建', bulletColor: C.green },
    { text: '先采样结构，再做局部语义生成与验证', bulletColor: C.green },
    { text: '删除测试与全图回溯可以校验必要性 / 唯一性', bulletColor: C.green },
    { text: '自动生成必须配多 agent 过滤与人工审核', bulletColor: C.green },
    { text: '公开编辑率、拒绝率和无法证明的边界', bulletColor: C.green }
  ], 1.08, 2.18, 5.05, 3.55, { fontSize: 12.8 });
  addCard(slide, 6.82, 1.45, 5.78, 4.95, '不能照搬', '', { accent: C.red, fill: C.paleRed });
  addBulletList(slide, [
    { text: '它没有做全 Wikipedia 的开放式事实抽取', bulletColor: C.red },
    { text: '唯一实体答案 ≠ 多 facet 长篇研究报告', bulletColor: C.red },
    { text: '图内唯一性不能排除图外 / 现实世界替代答案', bulletColor: C.red },
    { text: '29.2% 只是“未找到替代”，不是形式化唯一证明', bulletColor: C.red },
    { text: '难度过滤依赖单一校准模型，可能有家族偏差', bulletColor: C.red }
  ], 7.18, 2.18, 4.95, 3.55, { fontSize: 12.8 });
  addEquationBox(slide, '借工程分层原则，不借“唯一答案路线”目标', 3.05, 6.52, 7.25, 0.46, { fill: C.navy2, fontFace: FONT, fontSize: 15.2 });
  addFooter(slide, 'LoHoSearch §5 Limitations; DRA v3.2 §3.1, §4.3, §25.3');
  addNotes(slide, '这是防止汇报被 challenge 的关键页。不要说“美团证明了全量事实抽取可行”。他们全量的是结构图，语义处理是局部的。');
}

// 32 — Transfer principle
{
  const slide = newSlide();
  addTitle(slide, '从 LoHoSearch 到 DRA：同一分层原则，不同评分对象', 'Part III · Transfer');
  addCard(slide, 0.72, 1.42, 5.85, 4.95, 'LoHoSearch', '', { accent: C.green });
  const left = [
    ['全量层', 'Wikipedia nodes / hyperlinks / P31 / indegree'],
    ['局部层', '采样子图关系描述与自然语言问题'],
    ['构造目标', '大候选空间 + 高结构复杂度 + 图内唯一答案'],
    ['评分对象', '最终实体答案 accuracy']
  ];
  left.forEach((d, i) => {
    addPill(slide, d[0], 1.05, 2.15 + i * 0.88, 1.1, C.green, C.paleTeal);
    slide.addText(d[1], { x: 2.3, y: 2.18 + i * 0.88, w: 3.85, h: 0.35, fontFace: FONT, fontSize: 11.2, color: C.ink, margin: 0, fit: 'shrink' });
  });
  addCard(slide, 6.82, 1.42, 5.78, 4.95, 'DRA v3.2', '', { accent: C.blue });
  const right = [
    ['全量层', '所有沙盒 URL / span / table / link / structured field'],
    ['局部层', '单题事实、经验、机制、冲突、source role'],
    ['构造目标', '多 facet research shape + 可答性 + 不绑路线'],
    ['评分对象', '有本次交付证据的研究覆盖 DRA-GRC']
  ];
  right.forEach((d, i) => {
    addPill(slide, d[0], 7.15, 2.15 + i * 0.88, 1.1, C.blue, C.paleBlue);
    slide.addText(d[1], { x: 8.4, y: 2.18 + i * 0.88, w: 3.75, h: 0.35, fontFace: FONT, fontSize: 11.2, color: C.ink, margin: 0, fit: 'shrink' });
  });
  addArrow(slide, 6.35, 3.9, 6.72, 3.9, C.orange, 2.2);
  addEquationBox(slide, '全量廉价结构化  →  局部昂贵语义处理  →  自动与人工验证', 2.15, 6.52, 9.05, 0.46, { fill: C.navy2, fontFace: FONT, fontSize: 15 });
  addFooter(slide, 'DRA v3.2 §0, §4.2–4.3; LoHoSearch §2');
  addNotes(slide, '用对照表明确迁移关系。DRA 的全量层更异构，但仍是结构性；按题层需要更多语义类型；最终评分是报告研究覆盖，不是唯一答案。');
}

// 33 — Section IV
addSectionSlide(4, '其他工作提供了哪些“积木”', '没有一篇论文直接给出完整答案；我们需要组合 evidence-first 构题、广度分母、冻结环境、引用审计与长报告质量。', C.purple);

// 34 — DeepRubric + QUBRIC
{
  const slide = newSlide();
  addTitle(slide, 'Evidence-first 共构：DEEPRUBRIC 与 QUBRIC', 'Part IV · Query and rubric construction');
  addCard(slide, 0.72, 1.48, 5.85, 4.95, 'DEEPRUBRIC', '先采样 seed topic，递归扩展 evidence-backed sub-questions，形成 evidence tree；叶子是原子、可验证评价目标。随后从树反向生成 query 与 rubric，使“题目问什么”和“奖励什么”同源。\n\n9K query–rubric supervision；以约 13× 更少 RL GPU-hours 达到可比结果。', { accent: C.blue, fill: C.paleBlue, bodySize: 13.1 });
  addCard(slide, 6.82, 1.48, 5.78, 4.95, 'QUBRIC', '指出结构瓶颈：开放 query 产生模糊 rubric；粗暴收窄 query 又会引入无法验证的虚构参考。\n\n通过 teacher key points、query–rubric co-design、contrastive criteria 与 learnability filtering，保留真正有区分度的训练样本。', { accent: C.purple, fill: C.palePurple, bodySize: 13.1 });
  addCard(slide, 1.35, 5.67, 10.65, 0.78, 'DRA 的取舍', '接受“证据结构与 query / tests 同源”，但把 witness 降级为可答性证书；用合同接受新证据，避免训练式 rubric 绑定构题路线。', { accent: C.orange, fill: C.paleOrange, titleSize: 12.5, bodySize: 11.1, shadow: false });
  addFooter(slide, 'DEEPRUBRIC arXiv:2606.17029; QUBRIC arXiv:2606.03968');
  addNotes(slide, '这两篇说明 rubric 不能在看不到证据的情况下凭 query 盲猜。DRA 保留反向构造，但必须防止 witness URL 变成唯一合法路线。');
}

// 35 — Breadth benchmarks
{
  const slide = newSlide();
  addTitle(slide, '广度类基准告诉我们：必须同时报告连续覆盖与严格成功', 'Part IV · Breadth and stopping');
  const works = [
    ['WideSearch', '200 道人工题；收集大规模原子信息；最强整体 success 约 5%', '显式集合分母 + strict success', C.blue],
    ['DeepSearchQA', '900 个多步任务；要求穷尽答案列表；强调去重、实体解析、停止条件', '高 recall 与 precision 的张力', C.teal],
    ['DeepWideSearch', '220 题、15 领域；同一任务同时要求多跳深度和大规模宽度', '深度 / 宽度应分解诊断', C.orange]
  ];
  works.forEach((d, i) => addCard(slide, 0.75 + i * 4.17, 1.55, 3.82, 4.72, d[0], `${d[1]}\n\n对 DRA 的启发：\n${d[2]}`, { accent: d[3], bodySize: 12.6 }));
  addEquationBox(slide, 'DRA：连续 DRA-GRC 做主排序  +  Full Pass / Task Solve Rate 单独报告', 1.8, 6.5, 9.72, 0.46, { fill: C.navy2, fontFace: FONT, fontSize: 14.7 });
  addFooter(slide, 'WideSearch arXiv:2508.07999; DeepSearchQA arXiv:2601.20975; DeepWideSearch arXiv:2510.20168');
  addNotes(slide, '严格完整通过在广泛任务上会很低，这不代表 benchmark 失败。连续覆盖告诉我们完成到哪里，Task Solve Rate 告诉我们有多少任务完整解决。');
}

// 36 — Frozen environments
{
  const slide = newSlide();
  addTitle(slide, '冻结环境解决“可复现”，但不会自动解决“怎样评分报告”', 'Part IV · Reproducible worlds');
  const rows = [
    ['工作', '冻结方式', '主要评分 / 分析', 'DRA 借鉴与边界'],
    ['DeepResearchGym', 'ClueWeb22 + FineWeb 稳定搜索 API', '信息需求、retrieval faithfulness、report quality', '冻结检索可行；语义 ground truth 仍按题构建'],
    ['FutureSearch DRB / RetroSearch', '冻结大量历史网页', '人工解题答案 + 长轨迹自动分析', '证明 offline 与 live agent 可比；缺少 delivered-span audit'],
    ['BrowseComp-Plus', '固定支持文档 + hard negatives', '答案、检索、引用、上下文工程', '支持受控消融；gold documents 可能绑定证据路线']
  ];
  addMiniTable(slide, rows, 0.55, 1.35, [2.0, 2.55, 3.4, 4.3], 1.05, { headerSize: 9.4, bodySize: 9.7 });
  addCard(slide, 1.2, 5.92, 10.9, 0.68, '结论', '“有冻结语料”只是必要条件；DRA 额外利用 Observation Ledger 判断原页面内容经过 harness 变换后是否真正交付。', { accent: C.teal, fill: C.paleTeal, titleSize: 12.2, bodySize: 10.8, shadow: false });
  addFooter(slide, 'DeepResearchGym arXiv:2505.19253; Deep Research Bench arXiv:2506.06287; BrowseComp-Plus arXiv:2508.06600');
  addNotes(slide, '冻结环境让不同系统看到同一世界，但如果只检查最终答案或 gold 文档，仍不能判断模型是否使用了替代证据、是否看到支持跨度。');
}

// 37 — Long-form rubric benchmarks
{
  const slide = newSlide();
  addTitle(slide, '长报告 rubric 路线：表达力强，但构建成本与路线继承风险都很高', 'Part IV · Report evaluation');
  addCard(slide, 0.72, 1.48, 5.85, 4.95, 'Mind2Web 2', '130 个真实长时程 web 任务，投入超过 1,000 人时；用 tree-structured rubrics 构建 task-specific judge agents，同时评价 answer correctness 与 source attribution。\n\n优势：贴近真实 agentic search。\n代价：高人力；开放网络答案随时间变化。', { accent: C.blue, bodySize: 13 });
  addCard(slide, 6.82, 1.48, 5.78, 4.95, 'DeepResearch Bench II', '132 个 grounded research tasks，22 个领域，共 9,430 个细粒度二值 rubrics；覆盖 information recall、analysis、presentation。\n\nrubrics 来自专家调查文章，经四阶段 LLM+human 管线和 400+ 专家人时。', { accent: C.purple, bodySize: 13 });
  addCard(slide, 1.45, 5.72, 10.4, 0.72, 'DRA 的选择', '不用粗粒度 Likert，也不为每题写庞大唯一答案 rubric；由统一 compiler 生成少量分层 tests，并公开人审编辑率与异常率。', { accent: C.orange, fill: C.paleOrange, titleSize: 12.4, bodySize: 10.7, shadow: false });
  addFooter(slide, 'Mind2Web 2 arXiv:2506.21506; DeepResearch Bench II arXiv:2601.08536');
  addNotes(slide, 'rubric 并不是坏方法，问题是每题手工成本、细粒度一致性和参考报告路线继承。DRA 改成 compiler-generated, audit-frozen test suite。');
}

// 38 — Citation metrics and faithfulness
{
  const slide = newSlide();
  addTitle(slide, '引用研究告诉我们：正确、完整、真实依赖是三件不同的事', 'Part IV · Citation and faithfulness');
  const items = [
    ['ALCE', '分别评 fluency、answer correctness、citation correctness / completeness；引用质量可自动化，但仍主要是 claim 级。', C.blue],
    ['FActScore', '把长文本拆成 atomic facts，计算有可靠来源支持的比例；精确度强，但分母来自报告自己说了什么。', C.teal],
    ['Correctness is not Faithfulness', '引用页支持说法，并不保证模型真的依赖该页；研究发现 post-rationalization，最多 57% 引用缺乏 faithfulness。', C.red]
  ];
  items.forEach((d, i) => addCard(slide, 0.75 + i * 4.17, 1.55, 3.82, 4.52, d[0], d[1], { accent: d[2], bodySize: 12.7 }));
  addCard(slide, 1.1, 6.0, 11.1, 0.63, 'DRA 的增量', 'registry + delivered-span ledger 排除“未观察引用”；8–10 道反事实双胞胎世界再抽样检查结论是否随证据改变。', { accent: C.purple, fill: C.palePurple, titleSize: 11.8, bodySize: 10.4, shadow: false });
  addFooter(slide, 'ALCE arXiv:2305.14627; FActScore arXiv:2305.14251; Correctness is not Faithfulness arXiv:2412.18004');
  addNotes(slide, 'FActScore 类指标适合做报告 claim precision 诊断，但会奖励少说。DRA 主分的分母来自 query，claim audit 则作为补充。');
}

// 39 — Literature matrix
{
  const slide = newSlide();
  addTitle(slide, '在本次核查的代表性工作中，五项能力通常被分开处理', 'Part IV · Synthesis');
  const rows = [
    ['方法', '冻结世界', '广度分母', '运行内交付', '替代证据', '长报告综合'],
    ['LoHoSearch', '●', '结构约束', '—', '图条件等价', '—'],
    ['DEEPRUBRIC / QUBRIC', '局部证据', 'rubric', '—', 'rubric 条件化', '训练侧'],
    ['Wide / DeepSearchQA', '开放网', '答案集', '—', '答案集等价', '聚合为主'],
    ['DeepResearchGym', '●', 'key points', '事后 claim–citation', '引用 URL', '报告 rubric'],
    ['BrowseComp-Plus', '●', '答案', 'gold-document 核验', 'gold documents', '答案为主'],
    ['Mind2Web 2 / DRB II', '开放网/专家文', 'rubric', '轨迹/引用接口', 'rubric 接受', '报告 rubric'],
    ['ALCE / FActScore', '检索语料', 'report claims', '—', '任意支持源', 'claim-level'],
    ['DRA 候选目标', '●', 'query facets', '● span-level', '● contract', '独立质量面板']
  ];
  addMiniTable(slide, rows, 0.46, 1.25, [2.25, 1.6, 1.8, 2.0, 2.0, 2.6], 0.62, { headerSize: 8.6, bodySize: 8.7, align: 'center' });
  slide.addText('● = 正式设计目标；“—”表示论文不以该构念为核心。矩阵用于定位，不表示优劣总评。', {
    x: 0.75, y: 6.76, w: 11.9, h: 0.23, fontFace: FONT, fontSize: 8.7, color: C.muted, align: 'center', margin: 0
  });
  addFooter(slide, 'Primary-source comparison; exact scope follows cited papers, not a universal leaderboard');
  addNotes(slide, '矩阵说明 DRA 的组合创新空间：冻结文档世界、query-conditioned 广度、运行内 span 交付、合同接受替代证据、长报告质量分离。');
}

// 40 — Gap and contribution
{
  const slide = newSlide();
  addTitle(slide, '可验证的设计机会：这些现在还是 hypotheses，不是已证明贡献', 'Part IV · Design opportunities');
  const gaps = [
    ['Gap 1', '广度与证据常被分开评', 'DRA 在每个 research check 内把内容完成与证据门合取。', C.blue],
    ['Gap 2', '固定 gold URL 容易绑路线', '证据合同定义认识论要求，known witness 只证可答；新在册证据可按同一 matcher 通过。', C.teal],
    ['Gap 3', '“抓取过”通常停在工具事件', 'Observation Ledger v2 保存 raw → transforms → delivered artifact 血统。', C.orange],
    ['Gap 4', '引用正确不等于证据依赖', '反事实双胞胎世界与 canary 作为独立因果接地证书。', C.purple],
    ['Gap 5', '自动 rubric 很难证明有效', 'Dev-14 + 自然/腐蚀/替代/边界四层校准，公开 FRR/FAR 与人工编辑率。', C.red]
  ];
  gaps.forEach((d, i) => {
    const y = 1.35 + i * 1.08;
    addPill(slide, d[0], 0.72, y + 0.11, 0.82, d[3], i===4?C.paleRed:(i===1?C.paleTeal:C.paleBlue));
    slide.addText(d[1], { x: 1.75, y, w: 3.35, h: 0.5, fontFace: FONT, fontSize: 14.2, bold: true, color: C.navy, margin: 0, fit: 'shrink' });
    addArrow(slide, 5.15, y + 0.25, 5.62, y + 0.25, d[3], 1.6);
    slide.addText(d[2], { x: 5.85, y: y - 0.02, w: 6.75, h: 0.62, fontFace: FONT, fontSize: 11.4, color: C.ink, margin: 0, fit: 'shrink' });
    if (i < gaps.length - 1) slide.addShape(pptx.ShapeType.line, { x: 1.75, y: y + 0.79, w: 10.85, h: 0, line: { color: C.line, width: 0.7 } });
  });
  addFooter(slide, 'DRA literature synthesis: docs/DRA_V3_LITERATURE_SOLUTIONS_2026-07-17.md');
  addNotes(slide, '这页可以作为论文 contribution 的雏形，但每项主张必须经过后续验证门。现在只是设计目标，不能提前声称已经证明。');
}

// 41 — Section V
addSectionSlide(5, 'DRA 沙盒原生评分：v3.2 基线 + v3.3 候选修订', 'World Index → Task World Model → Research Test Suite → Execution Audit；Raw coverage 与 integrity-adjusted ranking 分开。', C.blue);

// 42 — Architecture
{
  const slide = newSlide();
  addTitle(slide, '整体架构：三层资产 + 一层运行审计', 'Part V · Architecture');
  const pipeline = [
    ['Frozen Sandbox', 'URL · snapshot · page structure', C.navy2],
    ['World Index', '全量解析 · span · link · structured fields · retrieval', C.blue],
    ['Task World Model', '单题 assertions · events · mechanisms · conflicts · roles', C.teal],
    ['Research Test Suite', 'facet · unit · check · evidence contract · witnesses', C.orange],
    ['Execution Audit', 'report · citations · ledger · matcher · certificates', C.purple]
  ];
  pipeline.forEach((d, i) => {
    const x = 0.4 + i * 2.57;
    addCard(slide, x, 2.02, 2.25, 2.78, d[0], d[1], { accent: d[2], titleSize: 13.1, bodySize: 11.1, shadow: false });
    if (i < 4) addArrow(slide, x + 2.25, 3.42, x + 2.51, 3.42, C.muted, 1.4);
  });
  slide.addText('Query / Case Blueprint', { x: 4.42, y: 1.3, w: 2.2, h: 0.34, fontFace: FONT_MONO, fontSize: 11, bold: true, color: C.orange, align: 'center', margin: 0 });
  addArrow(slide, 5.52, 1.68, 6.22, 2.0, C.orange, 1.7);
  slide.addText('Harness run', { x: 10.45, y: 1.3, w: 1.35, h: 0.34, fontFace: FONT_MONO, fontSize: 11, bold: true, color: C.purple, align: 'center', margin: 0 });
  addArrow(slide, 11.12, 1.67, 11.12, 2.0, C.purple, 1.7);
  addEquationBox(slide, '输出：Penalized mean DRA-GRC  +  Full Pass / URL / Funnel / Quality / Cost / Counterfactual', 1.2, 5.55, 10.95, 0.75, { fill: C.navy2, fontFace: FONT, fontSize: 14.2 });
  addFooter(slide, 'DRA v3.2 §4.2, §4.6');
  addNotes(slide, 'World Index 负责文档闭合，Task World Model 负责按题语义，Research Test Suite 负责把用户需求变成可执行测试，Execution Audit 负责在一次运行上执行。');
}

// 43 — World Index
{
  const slide = newSlide();
  addTitle(slide, 'Layer 1：World Index 全量做什么', 'Part V · World Compiler', '约 23 万页面可以全量结构化，但不做每页“所有事实”的 LLM 枚举。');
  const tasks = [
    ['1', 'URL canonicalization / alias / redirect'],
    ['2', 'HTTP 状态、快照、内容 hash 与 manifest'],
    ['3', '正文 section / paragraph / list 的稳定 span'],
    ['4', '表格 header-row-column-cell 关系'],
    ['5', '论坛 post / reply / quote / author 层级'],
    ['6', '页面与 span 级出链图'],
    ['7', 'JSON-LD、商品规格与确定性结构字段'],
    ['8', 'source family + exact / BM25 / dense 检索'],
    ['9', 'exact duplicate 与 near-duplicate clusters']
  ];
  tasks.forEach((d, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.68 + col * 4.18;
    const y = 1.52 + row * 1.45;
    addPill(slide, d[0], x, y + 0.1, 0.42, C.white, [C.blue,C.teal,C.orange][col]);
    slide.addText(d[1], { x: x + 0.62, y, w: 3.35, h: 0.62, fontFace: FONT, fontSize: 11.7, color: C.ink, bold: true, margin: 0, fit: 'shrink' });
  });
  addCard(slide, 1.28, 5.95, 10.75, 0.72, '成本原则', '全量只做线性解析/索引；小规模可枚举的高风险规则/域名全审，其余按 source family×parser×template 分层抽样；进入 TWM core witness 或高复用 certificate 的 span 全审。', { accent: C.red, fill: C.paleRed, titleSize: 11.5, bodySize: 9.7, shadow: false });
  addFooter(slide, 'DRA v3.2 §5.1–5.3, §21 Phase 1');
  addNotes(slide, '强调表格和论坛结构不能扁平化丢上下文。World Index 的验收是重复构建 hash/ID 一致、span 可回到原页面、没有静默丢页。');
}

// 44 — Task World Model
{
  const slide = newSlide();
  addTitle(slide, 'Layer 2：只在单题候选区域做昂贵语义抽取', 'Part V · Task World Model');
  const sources = [
    ['商品页', '规格值 / 原值\n厂商与零售主张\n限定条件 / 版本 / 时间\n“没有写”只允许有界范围', C.blue],
    ['论坛与社区', '同型号 / 相似型号\n事件与场景条件\n使用时长 / 时间\n个案不能升级为发生率', C.orange],
    ['Wikipedia / 标准 / 技术页', '机制 / 定义 / 测量方法\n适用条件\n一般机制到具体商品必须有 bridge\n不把百科当产品实测', C.teal]
  ];
  sources.forEach((d, i) => addCard(slide, 0.72 + i * 4.18, 1.48, 3.82, 4.62, d[0], d[1], { accent: d[2], bodySize: 13 }));
  slide.addShape(pptx.ShapeType.line, { x: 1.05, y: 6.38, w: 11.2, h: 0, line: { color: C.line, width: 1 } });
  slide.addText('抽取结果不是“真 / 假”一列，而是：谁在什么时间、什么条件、以什么来源角色说了什么；以及支持、冲突、限定、异质、unknown 的关系。', {
    x: 1.05, y: 6.47, w: 11.2, h: 0.45, fontFace: FONT, fontSize: 11.4, bold: true, color: C.navy, align: 'center', margin: 0, fit: 'shrink'
  });
  addFooter(slide, 'DRA v3.2 §5.5–5.13');
  addNotes(slide, 'TWM 是 task-scoped semantics，不是全库真理。商品主张、社区经验和技术机制保存不同 modality，防止营销页或个案被升级成客观性能事实。');
}

// 45 — Task Contract & compiler
{
  const slide = newSlide();
  addTitle(slide, 'Layer 3：从 query 编译研究结构，不是随机从事实池抽题', 'Part V · Research Test Compiler');
  const flow = [
    ['Query / Case Blueprint', '用户约束 · 候选范围 · facets · 输出需求'],
    ['Task Contract', '显式需求 · 隐含不可删除义务 · 条件与禁止推断'],
    ['Research Units', '比较 · claim audit · 机制 · 冲突 · 教程 · 预算 · 推荐'],
    ['Executable Checks', '每 unit 2–5 个 canonical checks'],
    ['Frozen RTS', 'content contract · evidence contract · premise DAG · witnesses']
  ];
  flow.forEach((d, i) => {
    const y = 1.25 + i * 1.04;
    addPill(slide, String(i + 1), 0.72, y + 0.12, 0.42, C.white, [C.blue,C.cyan,C.teal,C.orange,C.purple][i]);
    slide.addText(d[0], { x: 1.35, y, w: 2.65, h: 0.42, fontFace: FONT_MONO, fontSize: 12.5, bold: true, color: C.navy, margin: 0, fit: 'shrink' });
    addArrow(slide, 4.08, y + 0.23, 4.55, y + 0.23, [C.blue,C.cyan,C.teal,C.orange,C.purple][i], 1.5);
    slide.addText(d[1], { x: 4.82, y: y - 0.03, w: 7.55, h: 0.55, fontFace: FONT, fontSize: 11.6, color: C.ink, margin: 0, fit: 'shrink' });
  });
  addCard(slide, 0.92, 6.02, 5.6, 0.72, 'Route S · 前 14 道人工 seed', 'query-first 恢复 facets；双人抽样审核必要性与自然性。', { accent: C.blue, fill: C.paleBlue, titleSize: 11.8, bodySize: 9.8, shadow: false });
  addCard(slide, 6.8, 6.02, 5.6, 0.72, 'Route G · 后续生成题', '先选 research shape 和 blueprint，再共同生成 query / RTS。', { accent: C.teal, fill: C.paleTeal, titleSize: 11.8, bodySize: 9.8, shadow: false });
  addFooter(slide, 'DRA v3.2 §5.4, §6.1–6.12');
  addNotes(slide, '每题仍有 task-specific tests，但由统一 compiler 从 query 和 TWM 生成，人工负责校准 builder 而不是写唯一答案路线。');
}

// 46 — The denominator is still a hypothesis
{
  const slide = newSlide();
  addTitle(slide, '必须诚实：Compiler 产生的分母仍是“待验证假设”', 'Part V · Construct validity');
  const claims = [
    ['不是什么', '不是世界自动吐出的客观真理，也不是 LLM 生成后就冻结。', C.red],
    ['谁来提案', 'Compiler 从 query、任务类型学和 TWM 提出 facets / units / checks。', C.blue],
    ['谁判必要', '双人盲标 + deletion test：删掉它是否实质改变用户任务？', C.orange],
    ['谁证可答', '冻结世界中的 evidence contract + 至少一组 known witness；不将 witness 当唯一路线。', C.teal],
    ['谁验区分度', 'oracle / null / 流畅空话 / URL dump / 合法替代 / 无效路线。', C.purple]
  ];
  claims.forEach((d, i) => {
    const y = 1.26 + i * 1.02;
    addPill(slide, d[0], 0.7, y + 0.12, 1.55, C.white, d[2]);
    slide.addText(d[1], { x: 2.6, y, w: 9.85, h: 0.58, fontFace: FONT, fontSize: 11.6, color: C.ink, margin: 0, fit: 'shrink' });
    if (i < claims.length - 1) slide.addShape(pptx.ShapeType.line, { x: 2.6, y: y + 0.72, w: 9.8, h: 0, line: { color: C.line, width: 0.8 } });
  });
  addEquationBox(slide, '能声称的是“经校准的 query-conditioned 分母”，不是“唯一客观 rubric”', 1.05, 6.5, 11.2, 0.46, { fill: C.navy2, fontFace: FONT, fontSize: 13.6 });
  addFooter(slide, 'Validity evidence required: edit rate · inter-annotator band · deletion test · route FRR · shortcut FAR');
  addNotes(slide, '这页主动承认评分设计的最核心主观源。我们不靠口头说 rubric 合理，而是对 builder 做人工带、删除测试、合法替代误拒率和捷径误收率验证。');
}

// 47 — One complete task compilation example
{
  const slide = newSlide();
  addTitle(slide, '单题编译例：$60 阳台/泳池扬声器决策', 'Part V · End-to-end example', '任务并不要求一个固定胜者，它要求审计 Soundcore Flare 2 与 Ortizan 40W 的可证性。');
  const rows = [
    ['Facet / Unit', '核心 check（节选）', '证据合同 / 分支'],
    ['价格与候选', '对齐两个 listing 的精确价格，确认是否满足 $60 总预算', '两个商品页；版本/时点一致'],
    ['输出与失真', '准确转述 watt / THD 文案；不把 <1% THD+N 直推成“高音量更低失真”', 'listing + 测量/机制页；禁止过度推断'],
    ['泳池场景', '解释 IPX7 的测试边界；分开标准含义、商品声明和用户个案', '角色合同：标准/技术 + listing；论坛不可替代认证']
  ];
  addMiniTable(slide, rows, 0.42, 1.65, [2.2,6.2,4.0], 1.12, { headerSize: 10.8, bodySize: 11.2, align: 'left' });
  slide.addText('前三个 units 展示一个重要原则：不能把不同版本、时点或条件的有利前提拼接成合法路线。', {
    x: 0.82, y: 6.47, w: 11.7, h: 0.38, fontFace: FONT, fontSize: 11.5, bold: true, color: C.navy, align: 'center', margin: 0, fit: 'shrink'
  });
  addFooter(slide, 'dra_v3_dev_audio_0002 · illustrative compiler target, subject to Dev-14 calibration');
  addNotes(slide, '这页从 query 里拆出价格/候选、输出/失真和泳池场景三项研究工作。价格必须同时点，失真必须保留测试条件，IPX7 必须分开标准定义、商品主张与用户个案。');
}

// Single-task compilation example, conditional branches
{
  const slide = newSlide();
  addTitle(slide, '单题编译例（续）：条件分支和推荐包络避免固定路线', 'Part V · End-to-end example');
  const rows = [
    ['Facet / Unit', '核心 check（节选）', '证据合同 / 分支'],
    ['Hi-Res 宣传', '若两个 listing 均无该宣传，报告有界说明后可判“不影响决策”', 'absence branch OR claim-audit branch；不强制 LDAC 路线'],
    ['社区证据', '区分一般扬声器讨论与同型号涉水验证；可报告有界未找到', '任意合格论坛页 OR bounded absence protocol'],
    ['推荐', '任一候选都可通过，但必须与预算、审计性、失真风险和未知项一致', 'Decision Envelope；不固定 soundcore_flare2']
  ];
  addMiniTable(slide, rows, 0.42, 1.65, [2.2,6.2,4.0], 1.12, { headerSize: 10.8, bodySize: 11.2, align: 'left' });
  addCard(slide, 0.92, 6.12, 5.55, 0.7, '允许多路线', '新 URL、有界未发现、独立测量页都可在同一契约下裁决。', { accent: C.teal, fill: C.paleTeal, titleSize: 10.4, bodySize: 8.8, shadow: false });
  addCard(slide, 6.85, 6.12, 5.55, 0.7, '允许多结论', '推荐不锁定商品名；只要它属于约束与证据一致的 Decision Envelope。', { accent: C.blue, fill: C.paleBlue, titleSize: 10.4, bodySize: 8.8, shadow: false });
  addFooter(slide, 'dra_v3_dev_audio_0002 · conditional branches and open recommendation set');
  addNotes(slide, '比如 Hi-Res 不再强制调研 LDAC；如果两个商品页都没有该宣传，有界未发现本身就是一条合法路线。论坛证据也不强制命中预选页面；合法的有界未发现可以通过。推荐不锁定商品名。');
}

// 46 — Evidence contract and OR-of-AND
{
  const slide = newSlide();
  addTitle(slide, '不设唯一标准路线：冻结的是证据合同，不是 URL 白名单', 'Part V · Contract-admissible evidence');
  addEquationBox(slide, 'Aᵤ = { E ⊆ W : E ⊨ Γᵤ }       known witnesses Kᵤ ⊂ Aᵤ', 1.65, 1.38, 10.05, 0.72, { fill: C.navy2, fontSize: 19 });
  addCard(slide, 0.72, 2.47, 3.4, 3.65, 'Γᵤ：证据合同', '规定：\n• 哪些外部前提必须支持\n• 允许何种来源角色\n• 单页还是多页联合\n• 条件与范围如何绑定\n• 哪些推断被禁止', { accent: C.orange, bodySize: 13 });
  addCard(slide, 4.35, 2.47, 3.95, 3.65, 'OR of AND 路线', '同一前提可有多个 evidence bundles：\n\n(bundle A：商品页 + 技术页)\n      OR\n(bundle B：独立测量页)\n\n每个 bundle 内是 AND；bundles 之间是 OR。', { accent: C.teal, bodySize: 12.3 });
  addCard(slide, 8.53, 2.47, 4.08, 3.65, '运行时新页面如何通过', '1. URL 属于冻结 registry\n2. 支持 span 本次交付\n3. 与附近 claim 正确绑定\n4. 语义满足合同前提\n5. source role / scope 合格\n\n收集为 novel pair，在同一榜单 epoch 内批量盲裁。', { accent: C.blue, bodySize: 12.0 });
  slide.addText('若当前只知道一个支持页面，诚实标记 single_source；不虚构“所有命题都有多路线”。', {
    x: 1.25, y: 6.47, w: 10.85, h: 0.35, fontFace: FONT, fontSize: 12, bold: true, color: C.red, align: 'center', margin: 0
  });
  addFooter(slide, 'DRA v3.2 §4.5, §5.11, §6.10–6.11');
  addNotes(slide, '这是 reference-route overfitting 的直接解法。known witnesses 只用于 answerability；任何未预选但满足 Γ 的在册证据都能通过。');
}

// Certificate ledger governance
{
  const slide = newSlide();
  addTitle(slide, '替代证据不能“边跑边改榜”：用 leaderboard epoch 冻结 certificate ledger', 'Part V · Evidence governance');
  const flow = [
    ['1', '收齐本 epoch 提交', '只收集未知 (claim, span, contract) novel pairs', C.blue],
    ['2', '去重与 canonical batch', '同义 claim、同一 span、同一证据角色合并', C.teal],
    ['3', '盲裁 + 复核', '裁决 support / role / scope / binding；强制附摘录', C.orange],
    ['4', '冻结 ledger hash', '对所有 submission 使用同一 certificate snapshot 重算', C.purple],
    ['5', '下一 epoch', '新证据进下一批；不静默改变历史榜', C.green]
  ];
  flow.forEach((d, i) => {
    const x = 0.43 + i * 2.57;
    addPill(slide, d[0], x + 0.79, 1.38, 0.46, C.white, d[3]);
    addCard(slide, x, 2.1, 2.25, 3.35, d[1], d[2], { accent: d[3], titleSize: 12.4, bodySize: 10.7, shadow: false });
    if (i < 4) addArrow(slide, x + 2.26, 3.78, x + 2.5, 3.78, C.muted, 1.35);
  });
  addCard(slide, 1.0, 5.82, 5.43, 0.78, '防污染', '一次误判不会只影响后来的 harness；复核后同 epoch 统一重算。', { accent: C.red, fill: C.paleRed, titleSize: 10.8, bodySize: 9.2, shadow: false });
  addCard(slide, 6.87, 5.82, 5.43, 0.78, '可复现', '报告 world / TWM / RTS / certificate-ledger / judge / scorer 全部 hash。', { accent: C.blue, fill: C.paleBlue, titleSize: 10.8, bodySize: 9.2, shadow: false });
  addFooter(slide, 'Proposed leaderboard-epoch protocol for on-demand evidence certificates');
  addNotes(slide, '这解决提交顺序依赖。如果运行时遇到一个新的合法页面，不能当场改全局接受集；应收齐当期 novel pairs，批量盲裁后对所有提交在同一 snapshot 下重算。');
}

// 47 — Observation Ledger v2
{
  const slide = newSlide();
  addTitle(slide, 'Layer 4：Observation Ledger v2 统一 12 个 harness 的“观察”语义', 'Part V · Execution audit');
  const nodes = [
    ['raw_fetch_hash', 'HTTP body / API response', C.blue],
    ['transform_lineage[]', 'html→text · normalize · chunk · summarize', C.orange],
    ['delivered_artifact_hash', '真正进入模型上下文的 artifact', C.teal],
    ['delivered span IDs', '支持证据在交付物中的可定位片段', C.green]
  ];
  nodes.forEach((d, i) => {
    const x = 0.65 + i * 3.15;
    addCard(slide, x, 1.72, 2.78, 2.2, d[0], d[1], { accent: d[2], titleSize: 12.5, bodySize: 11.4, shadow: false });
    if (i < 3) addArrow(slide, x + 2.78, 2.82, x + 3.08, 2.82, C.muted, 1.5);
  });
  const classes = [
    ['raw', '原样交付'], ['normalized', '确定性规范化'], ['extractive', '抽取片段'], ['abstractive', '摘要式 mediated observation']
  ];
  classes.forEach((d, i) => addPill(slide, `${d[0]} · ${d[1]}`, 0.85 + i * 3.03, 4.48, 2.65, [C.blue,C.cyan,C.teal,C.purple][i], [C.paleBlue,C.paleBlue,C.paleTeal,C.palePurple][i]));
  addCard(slide, 0.92, 5.3, 5.65, 1.1, '资格门', '每个 harness 先通过 delivery canary 与 lineage 回放；无法捕获真正交付物则进入 report-only 轨。', { accent: C.red, fill: C.paleRed, titleSize: 12.2, bodySize: 10.5, shadow: false });
  addCard(slide, 6.82, 5.3, 5.65, 1.1, '不按工具名称特判', 'browser、shell、HTTP、RAG、摘要器只要能证明交付血统，就使用同一 Evidence gate 语义。', { accent: C.green, fill: C.paleTeal, titleSize: 12.2, bodySize: 10.5, shadow: false });
  addFooter(slide, 'DRA v3.2 §7.1–7.5, §21 Phase 4');
  addNotes(slide, 'raw HTTP 200 不足以证明观察。adapter 可能截断、抽取或摘要；只有 delivered artifact 对应模型可见内容。摘要还需要 CaptureFidelity / Sufficiency canary。');
}

// 48 — Check-level score
{
  const slide = newSlide();
  addTitle(slide, '最小评分单元：Content Contract × Evidence Gate', 'Part V · Scoring core');
  addEquationBox(slide, 'zₜ,ᶠ,ᵘ,ₖ = Cₜ,ᶠ,ᵘ,ₖ × Eₜ,ᶠ,ᵘ,ₖ', 3.65, 1.35, 6.0, 0.82, { fill: C.blue, fontSize: 26 });
  addCard(slide, 0.72, 2.52, 4.05, 3.35, 'C：内容合同', '报告是否真的完成这个 check：\n• 提到要求的对象 / 维度\n• 做出比较或解释\n• 正确表达条件与范围\n• 把结论连接到用户需求\n\n由 typed pointwise judge / deterministic executor 判定。', { accent: C.orange, bodySize: 12.6 });
  addCard(slide, 5.0, 2.52, 7.6, 3.35, 'E：证据门', '', { accent: C.teal });
  const gates = [
    ['V', 'Valid in registry'], ['O', 'Observed / delivered'], ['B', 'Bound locally'], ['S', 'Semantically supportive'], ['R', 'Role compatible']
  ];
  gates.forEach((d, i) => {
    const x = 5.42 + i * 1.36;
    slide.addShape(pptx.ShapeType.ellipse, { x, y: 3.25, w: 0.72, h: 0.72, fill: { color: [C.blue,C.teal,C.orange,C.green,C.purple][i] }, line: { color: [C.blue,C.teal,C.orange,C.green,C.purple][i] } });
    slide.addText(d[0], { x: x + 0.13, y: 3.43, w: 0.46, h: 0.25, fontFace: FONT_MONO, fontSize: 15, bold: true, color: C.white, align: 'center', margin: 0 });
    slide.addText(d[1], { x: x - 0.24, y: 4.12, w: 1.2, h: 0.48, fontFace: FONT, fontSize: 8.9, color: C.muted, align: 'center', margin: 0, fit: 'shrink' });
    if (i < 4) slide.addText('×', { x: x + 0.82, y: 3.38, w: 0.3, h: 0.25, fontFace: FONT_MATH, fontSize: 16, bold: true, color: C.navy, margin: 0 });
  });
  addEquationBox(slide, 'Eₖ = Xₖ · maxᵣ∈ᴿₖ [ Coherent(r) · ∏ₚ ∏ₑ∈ᵣ(ₚ) VₑOₑBₑ,ₚSₑ,ₚRₑ,ₚ ]', 5.25, 4.98, 6.98, 0.6, { fill: C.navy2, fontSize: 12.1 });
  slide.addText('Coherent(r)：型号 / 版本 / 时间 / 条件 / scope 一致  ·  Xₖ：冻结的 material conflicts 已被观察并处理', {
    x: 5.14, y: 5.72, w: 7.22, h: 0.35, fontFace: FONT, fontSize: 8.9, bold: true, color: C.red, align: 'center', margin: 0, fit: 'shrink'
  });
  slide.addText('部分完成来自一个 unit 的 2–5 个 checks 通过了多少，而不是 judge 随意给 0.5。', {
    x: 1.05, y: 6.38, w: 11.2, h: 0.36, fontFace: FONT, fontSize: 11.9, bold: true, color: C.navy, align: 'center', margin: 0
  });
  addFooter(slide, 'DRA v3.2 §8.1–8.3 baseline; coherent-route and conflict gate refined in v3.3 candidate');
  addNotes(slide, '这里保留了乘法，但位置正确：在每个 check 内做逻辑合取。先选一条完整路线 r，确认它的型号、版本、时间、实验条件和 scope 一致，再在路线内合取。这防止不同页面的有利前提被拼成不存在的 Frankenstein route。Xₖ 另外防止忽略 material counterevidence。');
}

// 49 — Hierarchical macro average
{
  const slide = newSlide();
  addTitle(slide, '层级宏平均：等权是默认规则，不是“无权重”', 'Part V · Aggregation');
  // hierarchy diagram
  addCard(slide, 0.72, 1.62, 2.48, 4.35, 'Task', 'DRA-GRCₜ', { accent: C.navy2, titleSize: 18, bodySize: 19, bodyBold: true });
  addArrow(slide, 3.2, 3.78, 3.65, 3.78, C.muted, 1.5);
  addCard(slide, 3.78, 1.62, 2.48, 4.35, 'Facets', '技术 / 价格 / 社区 / 推荐\n\nquery 中共等重要的 facets 默认等权；显式优先级预编码', { accent: C.blue, titleSize: 16, bodySize: 11.6 });
  addArrow(slide, 6.26, 3.78, 6.72, 3.78, C.muted, 1.5);
  addCard(slide, 6.85, 1.62, 2.48, 4.35, 'Research Units', '每个 facet 下若干完整研究工作\n\n硬约束可设 gate；其余 units 使用冻结 obligation mass', { accent: C.teal, titleSize: 15.5, bodySize: 11.6 });
  addArrow(slide, 9.33, 3.78, 9.78, 3.78, C.muted, 1.5);
  addCard(slide, 9.92, 1.62, 2.7, 4.35, 'Checks', '每 unit 2–5 个 canonical checks\n\n一个语义义务被 split 后共享原质量：∑ mₖ = m_group', { accent: C.orange, titleSize: 16, bodySize: 11.6 });
  addEquationBox(slide, 'Raw GRCₜ = weighted-mean_facets ( weighted-mean_units ( Σₖ mₖ zₖ / Σₖ mₖ ) )', 1.2, 6.35, 10.95, 0.48, { fill: C.navy2, fontSize: 14.2 });
  addFooter(slide, 'DRA v3.2 §8.4–8.5');
  addNotes(slide, '不能把所有 checks 直接 micro average，否则 compiler 更啰嗦的任务权重更高。同时不能声称所有 facet 天然等重：如果 query 说“失真风险优先于原始功率”，Task Contract 必须在冻结前编码这个优先级。所谓粒度不变不是自然成立，需用 obligation group mass 和 split/merge 敏感性审计保证。');
}

// End-to-end verdict example
{
  const slide = newSlide();
  addTitle(slide, '同一个技术主张，如何从报告句子一路得到任务分', 'Part V · Scoring walkthrough');
  addCard(slide, 0.64, 1.36, 5.93, 2.18, '失败路线', '报告：“<1% THD+N 证明它在高音量下失真更低。”\n\nC=1：确实做了失真比较\nV=1, O=1, B=1, R=1；S=0：页面没有音量/频率/测试条件\n⇒ z=0（unsupported over-inference）', { accent: C.red, fill: C.paleRed, titleSize: 14.5, bodySize: 11.2 });
  addCard(slide, 6.78, 1.36, 5.93, 2.18, '合法路线', '报告：“listing 标称 <1% THD+N，但未给出音量、频率与测试设置，不足以比较高音量失真。”\n\nC=1；listing + 测量解释页组成 coherent route\nV=O=B=S=R=1，且未忽略 material conflict\n⇒ z=1', { accent: C.green, fill: C.paleTeal, titleSize: 14.5, bodySize: 11.2 });
  const rows = [
    ['单题结果（当前 pilot 的人工校准记录）', '数值', '含义'],
    ['ContentBreadth', '5 / 9 = 55.6%', '九个必要检查中，内容讨论到五个'],
    ['Raw grounded coverage', '1 / 9 = 11.1%', '只有一个同时满足内容与证据门'],
    ['Full Pass', '0', '并非“完成”这道调研任务'],
    ['Integrity-adjusted', '11.1% 或 0', '无确认不存在 URL 时为 11.1%；若有则当题为 0']
  ];
  addMiniTable(slide, rows, 0.7, 4.02, [4.2,2.15,5.45], 0.56, { headerSize: 8.8, bodySize: 9.4, align: 'left' });
  slide.addText('这个示例是方法闭环记录，非正式榜单分；自动裁判校准未过前标记 formal_eligible=false。', {
    x: 0.95, y: 6.64, w: 11.4, h: 0.25, fontFace: FONT, fontSize: 9.6, color: C.muted, align: 'center', margin: 0
  });
  addFooter(slide, 'Pilot: gpt-researcher × deepseek-v4-pro × dra_v3_dev_audio_0002; manual semantic calibration');
  addNotes(slide, '这页是最具体的评分推演。它也说明 C 不能等于正确：报告确实讨论了失真，但把商品页的一个数值过度推断成高音量表现，因此 evidence support 失败。');
}

// 50 — Content breadth, GRC, full pass
{
  const slide = newSlide();
  addTitle(slide, '最终每道题同时给出三个直觉量', 'Part V · Task-level outputs');
  addCard(slide, 0.72, 1.55, 3.75, 4.75, 'ContentBreadth', '只看 C：\n报告讨论到了多少必要研究检查？\n\n可识别“写到了但没证据”。', { accent: C.orange, fill: C.paleOrange, titleSize: 17, bodySize: 15 });
  addCard(slide, 4.78, 1.55, 3.75, 4.75, 'Raw DRA-GRC', '看 z = C×E：\n有本次交付、就地绑定且支持的证据完成了多少研究工作？\n\n这才是 grounded research coverage 构念分。', { accent: C.teal, fill: C.paleTeal, titleSize: 17, bodySize: 14.2 });
  addCard(slide, 8.84, 1.55, 3.75, 4.75, 'Full Pass', '所有 core checks 通过 + 输出合同满足 + 无 critical error + 无 confirmed nonexistent citation。\n\nTask Solve Rate = 完整通过任务 / 固定正式任务。', { accent: C.blue, fill: C.paleBlue, titleSize: 17, bodySize: 13.7 });
  slide.addText('UnsupportedBreadthGap = ContentBreadth − DRA-GRC', { x: 2.85, y: 6.55, w: 7.65, h: 0.35, fontFace: FONT_MATH, fontSize: 17, bold: true, color: C.red, align: 'center', margin: 0 });
  addFooter(slide, 'DRA v3.2 §8.6–8.7');
  addNotes(slide, '用户此前确认要汇报完整通过与部分通过。这里的部分通过不是走了参考路线多少步，而是必要 research checks 有证据地完成了多少。');
}

// 51 — Fabrication gate
{
  const slide = newSlide();
  addTitle(slide, '链接“真实性”与“冻结世界合规”分开处理', 'Part V · Integrity gate');
  addEquationBox(slide, 'Gₜ official = 0  if confirmed nonexistent_fabrication;   otherwise Gₜ official = Gₜ pre', 1.4, 1.32, 10.55, 0.72, { fill: C.red, fontSize: 17.5 });
  addCard(slide, 0.72, 2.38, 5.77, 3.05, 'Lane A · 确认不存在的 URL', '1. canonicalize 并查 alias / redirect\n2. 排除 registry 缺失与 benchmark 错误\n3. 盲复核确认 URL 不存在\n4. 当题 GRC 清零，记 nonexistent-fabrication event', { accent: C.red, fill: C.paleRed, titleSize: 14.3, bodySize: 11.5 });
  addCard(slide, 6.83, 2.38, 5.77, 3.05, 'Lane B · 真实但 off-world 的 URL', '1. URL 在开放网可能真实\n2. 但不属于冻结 registry / snapshot\n3. 无法证明本次 sandbox 内调研；证据无资格\n4. 对应 check 失败 + off-world protocol flag', { accent: C.orange, fill: C.paleOrange, titleSize: 14.3, bodySize: 11.5 });
  addCard(slide, 0.9, 5.75, 5.62, 0.78, '敏感性分析', '同时报告“off-world 仅使证据失效”与“off-world 也任务清零”两种排名。', { accent: C.purple, fill: C.palePurple, titleSize: 10.7, bodySize: 9, shadow: false });
  addCard(slide, 6.8, 5.75, 5.62, 0.78, '主表强制展示', 'nonexistent-fabrication rate · off-world rate · affected-task rate · clean-run rate · CI。', { accent: C.blue, fill: C.paleBlue, titleSize: 10.7, bodySize: 9, shadow: false });
  addFooter(slide, 'Proposed integrity rule; task-gate sensitivity must be preregistered before leaderboard release');
  addNotes(slide, '不再用“不在 registry”直接推出“URL 不存在”。默认只有盲复核后确认不存在的 fabricated citation 触发当题清零；off-world 首先作为证据无效与协议违规，并在 Dev-14 / 对照输出上做 task-gate 敏感性分析。');
}

// 52 — Quality panel operationalization
{
  const slide = newSlide();
  addTitle(slide, 'Research Quality Panel 的操作化：只比较“怎么写”，不重复判事实', 'Part V · Quality panel');
  const compare = [
    ['输入', '同一道 query 的两份匿名报告；状态遮蔽的 evidence packet'],
    ['单位', '一次只问一个轴：Synthesis / Conflict / Utility / Presentation'],
    ['防偏', 'A/B 位置交换；矛盾 pair 标 unstable；固定长报告分段协议'],
    ['标尺', '固定 anchor reports + 固定配对图；可估 anchored Bradley–Terry 轴向分'],
    ['校准', 'pilot 每轴 ≥200 对、3 名标注者；最终 n 由 power/MDE 决定；报 κ/α 与偏差'],
    ['榜单', '四轴另表 / 雷达图；不合成 Overall，不进入 tie-break']
  ];
  compare.forEach((d, i) => {
    const y = 1.35 + i * 0.86;
    addPill(slide, d[0], 0.75, y + 0.08, 0.76, [C.blue,C.teal,C.orange,C.purple,C.red,C.green][i], [C.paleBlue,C.paleTeal,C.paleOrange,C.palePurple,C.paleRed,C.paleTeal][i]);
    slide.addText(d[1], { x: 1.75, y, w: 10.9, h: 0.47, fontFace: FONT, fontSize: 12, color: C.ink, bold: i===5, margin: 0, fit: 'shrink' });
    if (i < compare.length - 1) slide.addShape(pptx.ShapeType.line, { x: 1.75, y: y + 0.62, w: 10.85, h: 0, line: { color: C.line, width: 0.7 } });
  });
  addEquationBox(slide, '主榜回答“有证据完成了多少”   ·   面板回答“完成得是否清楚、诚实、有用”', 1.45, 6.55, 10.45, 0.43, { fill: C.navy2, fontFace: FONT, fontSize: 14.3 });
  addFooter(slide, 'DRA v3.2 §16');
  addNotes(slide, '如果质量轴之间无法建立判别效度，就联合报告或降为探索性，不强行合成。κ 只说明一致性，不能替代主分构念效度验证。');
}

// 53 — Leaderboard
{
  const slide = newSlide();
  addTitle(slide, '最后榜单长什么样：一个排名分 + 强制完整性列', 'Part V · Reporting');
  const rows = [
    ['Rank', 'Harness', 'Integrity-adjusted GRC ↑ (95% CI)', 'Raw GRC ↑', 'Task Solve ↑', 'Eligible'],
    ['1', 'Harness A', '0.63 [0.57, 0.69]', '0.63', '0.18', 'Yes'],
    ['2', 'Harness B', '0.55 [0.49, 0.61]', '0.61', '0.11', 'Yes']
  ];
  addMiniTable(slide, rows, 0.55, 1.35, [0.78,1.9,3.75,1.75,1.75,1.4], 0.82, { headerSize: 9.1, bodySize: 11.1, align: 'center' });
  const panels = [
    ['任务下钻', 'facet / unit / check 通过率\nContentBreadth 与 gap\n失败类型与实际证据路线', C.blue],
    ['引用面板', 'nonexistent / off-world / unobserved / unsupported / wrong-binding / contradicted\naffected-task / clean-run / 引用数相关性', C.red],
    ['过程漏斗', 'SearchExposed → Delivered → UtilizedDelivered → VerifiedPass', C.teal],
    ['质量与效率', '四轴质量面板\n页面 / token / 时间 / 成本\n反事实审计证书', C.purple]
  ];
  panels.forEach((d, i) => addCard(slide, 0.65 + i * 3.15, 4.35, 2.82, 1.9, d[0], d[1], { accent: d[2], titleSize: 13, bodySize: 10.2, shadow: false }));
  slide.addText('若 DRA-GRC 差异落入预注册等效区间：宣布并列，不用质量或成本偷偷破同分。', {
    x: 1.25, y: 6.58, w: 10.85, h: 0.3, fontFace: FONT, fontSize: 11.7, bold: true, color: C.navy, align: 'center', margin: 0
  });
  addFooter(slide, 'DRA v3.2 §18, §20');
  addNotes(slide, 'Raw GRC 保留了“有证据覆盖率”的构念含义；Integrity-adjusted GRC 是榜单政策分。两者必须并列，否则一个由造假门得到的 0 会被误读成“研究覆盖为 0”。还要报分数与报告长度/引用数的相关性。');
}

// 54 — Validation matrix
{
  const slide = newSlide();
  addTitle(slide, '验证门 I：先证明分数不可被捷径骗取，世界与分母可重现', 'Part V · Validation');
  const gates = [
    ['Gate A · Scoring invariants', 'V1–V10', 'oracle ceiling · null floor · URL/fact dump · fluent unsupported · valid/invalid route · unobserved injection · local corruption · monotonicity · granularity invariance', C.blue],
    ['Gate B · World / Compiler', 'V11–V19', 'World Index determinism · candidate saturation · assertion/role/conflict · query round-trip · test necessity · answerability · held-out probes', C.teal]
  ];
  gates.forEach((d, i) => {
    const y = 1.55 + i * 2.2;
    slide.addShape(pptx.ShapeType.roundRect, { x: 0.7, y, w: 11.95, h: 1.72, fill: { color: i%2?C.white:C.soft }, line: { color: d[3], width: 1.3 } });
    addPill(slide, d[1], 0.98, y + 0.68, 1.06, C.white, d[3]);
    slide.addText(d[0], { x: 2.28, y: y + 0.28, w: 3.1, h: 0.45, fontFace: FONT, fontSize: 15.2, bold: true, color: C.navy, margin: 0, fit: 'shrink' });
    slide.addText(d[2], { x: 5.55, y: y + 0.24, w: 6.7, h: 1.0, fontFace: FONT, fontSize: 12.1, color: C.ink, margin: 0, fit: 'shrink' });
  });
  addCard(slide, 1.05, 6.18, 11.2, 0.6, '门与门不能相互抵消', 'oracle 通过不能抵消合法替代路线误拒；World Index 可重建不能抵消 compiler 分母错误。', { accent: C.red, fill: C.paleRed, titleSize: 10.8, bodySize: 9.4, shadow: false });
  addFooter(slide, 'DRA v3.2 §19.1–19.5');
  addNotes(slide, 'Gate A 与 Gate B 是方法的基础。必须先用可控的参考报告和局部腐蚀证明评分器的单调性、局部性和抗捷径，再证明 World Index / TWM / compiler 给出的任务结构稳定且可答。');
}

// Validation matrix II
{
  const slide = newSlide();
  addTitle(slide, '验证门 II：再证明运行仪器可接受，主分对人类调研广度有效', 'Part V · Validation');
  const gates = [
    ['Gate C · Execution acceptance', 'V20–V22', '12 adapter observation normalization · delivery canary · runner/matcher/judge 人工盲标 · route FRR/FAR with confidence bounds', C.orange],
    ['Gate D · Benchmark validity', 'V23–V30', '盲专家 grounded-breadth（不看 RTS/分数） · old-vs-new validity · counterfactual · reproducibility · repair · gaming · integrity · capacity', C.purple]
  ];
  gates.forEach((d, i) => {
    const y = 1.55 + i * 2.2;
    slide.addShape(pptx.ShapeType.roundRect, { x: 0.7, y, w: 11.95, h: 1.72, fill: { color: i%2?C.white:C.soft }, line: { color: d[3], width: 1.3 } });
    addPill(slide, d[1], 0.98, y + 0.68, 1.06, C.white, d[3]);
    slide.addText(d[0], { x: 2.28, y: y + 0.28, w: 3.1, h: 0.45, fontFace: FONT, fontSize: 15.2, bold: true, color: C.navy, margin: 0, fit: 'shrink' });
    slide.addText(d[2], { x: 5.55, y: y + 0.24, w: 6.7, h: 1.0, fontFace: FONT, fontSize: 12.1, color: C.ink, margin: 0, fit: 'shrink' });
  });
  addCard(slide, 0.92, 6.06, 5.6, 0.78, '校准样本量', '1,500–2,500 判定对是 pilot target；最终 n 按 power/MDE；稀疏层只报 CI。', { accent: C.blue, fill: C.paleBlue, titleSize: 10.6, bodySize: 9, shadow: false });
  addCard(slide, 6.82, 6.06, 5.6, 0.78, '独立效度', '专家只看 query、report 和可访问引用；不看 RTS、check pass 或 DRA 分数。', { accent: C.green, fill: C.paleTeal, titleSize: 10.6, bodySize: 9, shadow: false });
  addFooter(slide, 'DRA validation gates · construct validity must be independent of the Research Test Suite');
  addNotes(slide, '这页避免循环证明。如果专家看到了 RTS 或 DRA 分数，再评“调研广度”，只是在复述 evaluator。专家必须在不知道新旧评分结果的前提下独立判断。');
}

// 55 — Section: implementation
addSectionSlide(6, '后续实施路线', '先证明一道题的方法闭环，再扩到三类任务、Dev-14 和 56 题；发布门不过，不发榜。', C.green);

// Query construction: two routes
{
  const slide = newSlide();
  addTitle(slide, 'Query 构建保留两条路：自然种子与世界反向生成分层报告', 'Part VI · Query construction');
  addCard(slide, 0.68, 1.42, 5.82, 4.78, 'Route S · Seed / query-first（前 14 题）', '1. 保留人手写的自然用户问题\n2. 标注者只看 query，独立恢复用户约束、facets 和不可删除的研究工作\n3. 再从冻结世界建 TWM，审计每项是否可答/可达\n4. Compiler 只提出 tests，人工记录 merge / split / delete\n5. 不因为某个 harness 没做到就改 query 义务', { accent: C.blue, fill: C.paleBlue, titleSize: 15, bodySize: 12.1 });
  addCard(slide, 6.82, 1.42, 5.82, 4.78, 'Route G · Generated / world-first（剩余 42 题）', '1. 预先选 research shape，而不是随机抽几个事实\n2. 从 World Index 选候选对象、用户约束和来源角色\n3. 建立局部 evidence subgraph / TWM，验证冲突、路线多样性和可答性\n4. 先编译 RTS，再隐藏实体细节、URL 和 witness route\n5. 生成自然 query，使用 round-trip 检查没有漏需求/泄答案', { accent: C.teal, fill: C.paleTeal, titleSize: 15, bodySize: 12.1 });
  slide.addText('主表整体排名，但必须同时分层报告 Route S 与 Route G，避免 42 道生成题淹没自然种子集的行为差异。', {
    x: 0.95, y: 6.56, w: 11.45, h: 0.38, fontFace: FONT, fontSize: 11.4, bold: true, color: C.red, align: 'center', margin: 0, fit: 'shrink'
  });
  addFooter(slide, 'DRA query construction proposal · Route S / Route G are separate reporting strata');
  addNotes(slide, 'Route S 和 Route G 的不同不应被隐藏。前者是自然问题的 query-first 结构恢复，后者是从可答局部世界反向生成。两者可共用同一评分协议，但数据来源不同，所以必须分层报告。');
}

// World-first query generation details
{
  const slide = newSlide();
  addTitle(slide, 'Route G 的真实生成逻辑：先定研究形状，再隐藏证据路线生成 query', 'Part VI · World-first generation');
  const nodes = [
    ['Research Shape', '比较 / 机制 / 冲突 / 决策\n需要哪些 source roles？', C.blue],
    ['Case Blueprint', '候选行动 A\n用户约束 U\n优先级 / 硬约束', C.teal],
    ['Evidence Subgraph', '商品主张 / 机制\n社区事件 / 冲突\n页面 + support spans', C.orange],
    ['TWM + RTS', '可答性\n必要性\n合法替代路线\n禁止推断', C.purple],
    ['Hidden View → Query', '隐藏 URL / witness / 参考结论\n保留用户需求\n自然化 + round-trip', C.green]
  ];
  nodes.forEach((d, i) => {
    const x = 0.42 + i * 2.58;
    addCard(slide, x, 1.7, 2.28, 3.72, d[0], d[1], { accent: d[2], titleSize: 12.6, bodySize: 10.8, shadow: false });
    if (i < 4) addArrow(slide, x + 2.28, 3.56, x + 2.52, 3.56, C.muted, 1.35);
  });
  addCard(slide, 0.78, 5.82, 3.68, 0.79, '不能做', '随机抽 E1–E4 就让 LLM 编一个故事。', { accent: C.red, fill: C.paleRed, titleSize: 10.8, bodySize: 9.1, shadow: false });
  addCard(slide, 4.83, 5.82, 3.68, 0.79, '必须检查', '隐藏任一 core obligation 后，query 是否仍忠实并需多分支调研。', { accent: C.orange, fill: C.paleOrange, titleSize: 10.8, bodySize: 9.1, shadow: false });
  addCard(slide, 8.88, 5.82, 3.68, 0.79, '不泄漏', 'agent 只看 query 和公共输出合同，不看评分步骤、必引 URL 和参考推荐。', { accent: C.green, fill: C.paleTeal, titleSize: 10.8, bodySize: 9.1, shadow: false });
  addFooter(slide, 'World-first query generation · inspired by LoHoSearch structure-first generation, adapted for DR reports');
  addNotes(slide, '这页对应用户之前的表达：先有商品、属性、论坛经验、机制、冲突和 URL，再选局部子图，用 evaluator 编译可答测试，最后隐藏证据路线只保留自然用户需求。');
}

// 56 — Phases 0–3
{
  const slide = newSlide();
  addTitle(slide, 'Phase 0–3：把“方法”先做成一道可重放的工程样本', 'Part VI · Build the first closed loop');
  const phases = [
    ['P0 · 冻结现状', '保留旧公式、56 道 query、registry / graph / result 哈希、12 个 adapter 版本。\n交付：baseline manifest + 不可变的对照表。', C.muted],
    ['P1 · World Index', '全库轻量结构化：URL、页面类型、标题、链接、段落、商品/概念实体、来源角色和可达性。\n门：确定性重建 + 抽样解析正确率。', C.blue],
    ['P2 · 单题 TWM', '以 dra_v3_dev_audio_0002 生成 Task World Model：候选页、事实簇、冲突、证据角色、可接受结论包络。\n门：专家能从写明为何每个 core check 可答。', C.teal],
    ['P3 · Compiler + Matcher', '从 query + TWM 编译 facet / unit / check；支持未预选页面的 on-demand 证据匹配。\n门：合法替代路线通过，无效路线失败。', C.green]
  ];
  phases.forEach((d, i) => {
    const x = 0.58 + i * 3.17;
    addCard(slide, x, 1.48, 2.84, 4.75, d[0], d[1], { accent: d[2], fill: i === 0 ? C.soft : C.white, titleSize: 14, bodySize: 11.2 });
    if (i < 3) addArrow(slide, x + 2.86, 3.8, x + 3.12, 3.8, C.muted, 1.5);
  });
  addEquationBox(slide, '成功标志：同一份报告 → 同一 observation ledger → 同一证据判定 → 同一分数证书', 1.18, 6.55, 10.95, 0.42, { fill: C.navy2, fontFace: FONT, fontSize: 13.4 });
  addFooter(slide, 'DRA v3.2 §20.1–20.4');
  addNotes(slide, '不先批量生成 56 份 rubric。先把一道题做到任何人都能沿着证书重放，并且明确区分 benchmark 错误、adapter 错误和 harness 错误。');
}

// Search API as benchmark instrument
{
  const slide = newSlide();
  addTitle(slide, '搜索 API 是共享的实验仪器：“所有 harness 都用它”只证公平，不证有效', 'Part VI · Retrieval instrument');
  const metrics = [
    ['Model precision', '精确型号 query 返回目标型号/兼容别名的比例', C.blue],
    ['Source coverage', '商品 / 论坛 / 技术 / Wikipedia 各来源的可达覆盖', C.teal],
    ['Oracle recall@k', '对每题的 known witness 和 held-out admissible evidence，搜索前 k 位能否触及', C.orange],
    ['Pollution rate', '与型号/技术概念无关页的比例；按 source family 分层', C.red],
    ['Determinism', '同 query + API version + snapshot 是否产生相同候选集和排序', C.purple],
    ['Latency / failure', 'p50 / p95 延迟、超时、空结果、来源给额失败', C.green]
  ];
  metrics.forEach((d, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    addCard(slide, 0.67 + col * 4.2, 1.42 + row * 2.23, 3.78, 1.82, d[0], d[1], { accent: d[2], titleSize: 13.4, bodySize: 10.7, shadow: false });
  });
  addCard(slide, 1.0, 6.02, 5.35, 0.69, '分责记录', '漏斗中分开 API 未暴露 / agent 未点击 / 抓取失败 / 已交付未使用。', { accent: C.red, fill: C.paleRed, titleSize: 10.3, bodySize: 8.8, shadow: false });
  addCard(slide, 6.92, 6.02, 5.35, 0.69, '冻结与回归', '发布 search API version + relevance test suite + 每次改动前后的证书。', { accent: C.blue, fill: C.paleBlue, titleSize: 10.3, bodySize: 8.8, shadow: false });
  addFooter(slide, 'Search API quality certificate · benchmark instrument validity');
  addNotes(slide, '这页直接吸收了之前搜索污染实验的教训。即使 12 个 harness 都面对同一个差 API，对比也只是一致地受限，不能证明 benchmark 测到了应测的研究能力。需要为 API 本身发布质量证书。');
}

// How a new harness uses the benchmark
{
  const slide = newSlide();
  addTitle(slide, '别人拿到 DRA，新 harness 应该如何使用', 'Part VI · External protocol');
  const flow = [
    ['Adapter Contract', '声明 search / fetch / delivery / report 事件', C.blue],
    ['Delivery Canary', '证明 ledger 记录的 artifact 真的进入了模型上下文', C.teal],
    ['Frozen Run', '跑固定 task manifest；不需要先看现有 12 harness 输出', C.orange],
    ['Seal Bundle', '交付 report + ledger hash + adapter / model / tool version', C.purple],
    ['Batch Evaluation', '本 epoch novel evidence 盲裁；同 certificate snapshot 重算', C.green],
    ['Certificate', 'Raw / adjusted GRC、Task Solve、integrity、funnel、quality 面板', C.red]
  ];
  flow.forEach((d, i) => {
    const x = 0.34 + i * 2.15;
    addCard(slide, x, 1.65, 1.9, 3.85, d[0], d[1], { accent: d[2], titleSize: 11.3, bodySize: 9.4, shadow: false });
    if (i < 5) addArrow(slide, x + 1.91, 3.58, x + 2.09, 3.58, C.muted, 1.2);
  });
  addCard(slide, 0.9, 5.92, 5.55, 0.72, 'Full track', '能捕获 delivered-artifact lineage：参与正式榜单与 evidence gate。', { accent: C.green, fill: C.paleTeal, titleSize: 10.7, bodySize: 9.1, shadow: false });
  addCard(slide, 6.85, 5.92, 5.55, 0.72, 'Report-only track', '无法证明本次交付证据：只报 content / post-hoc citation 诊断，不与 full track 混排。', { accent: C.orange, fill: C.paleOrange, titleSize: 10.7, bodySize: 9.1, shadow: false });
  addFooter(slide, 'A new harness does not need comparison-harness outputs; it needs an auditable adapter and frozen protocol');
  addNotes(slide, '这回应了“难道要先跑完 12 个 harness 才能判断新系统吗”。答案是不需要。12 个现有 harness 用来特征化 benchmark 和挖攻击面；新 harness 只需要满足公开 adapter 合同、跑冻结任务并提交可回放的 seal bundle。');
}

// 57 — Phases 4–7
{
  const slide = newSlide();
  addTitle(slide, 'Phase 4–7：统一观测协议，然后校准编译器和裁判器', 'Part VI · Calibrate the measurement system');
  const rows = [
    ['阶段', '核心产物', '必过验收', '不过时怎么办'],
    ['P4', '12 harness 统一 Observation Protocol v2', 'search / fetch / browser / subagent / cache 的事件规范化；令牌传递正确', '该 adapter 标记 ineligible，不用报告文字倒推观测'],
    ['P5', 'runner + evidence certificate + replay CLI', '四份参考报告与局部腐蚀版满足单调性和局部性', '回到单题修 matcher / runner，不扩题'],
    ['P6', 'Dev-14 双人盲标与 adjudication', '编译器恢复的必要要求与人类带一致性和可答性证书', '修改类型学 / 编译规则，不手工掩盖'],
    ['P7', 'pilot 1,500–2,500 个判定对', '自然 / 伪证据 / 合法替代 / 边界四层；最终 n 按 power/MDE；稀疏层只报 CI', '确定性下沉或加入 PENDING 队列；发布前 PENDING=0']
  ];
  addMiniTable(slide, rows, 0.38, 1.34, [0.72,2.8,4.65,4.36], 1.02, { headerSize: 9, bodySize: 9.1, align: 'left' });
  addCard(slide, 0.72, 6.12, 3.82, 0.67, '一致性', '报 κ / Krippendorff\'s α + 分歧类型', { accent: C.blue, fill: C.paleBlue, titleSize: 10, bodySize: 8.4, shadow: false });
  addCard(slide, 4.77, 6.12, 3.82, 0.67, '准确性', '不只看 agreement；看 FRR / FAR / macro-F1 / CI', { accent: C.teal, fill: C.paleTeal, titleSize: 10, bodySize: 8.4, shadow: false });
  addCard(slide, 8.82, 6.12, 3.82, 0.67, '偏差', '检查路线、长度、文风、位置和 harness-family 偏差', { accent: C.orange, fill: C.paleOrange, titleSize: 10, bodySize: 8.4, shadow: false });
  addFooter(slide, 'DRA v3.2 §20.5–20.8');
  addNotes(slide, '校准对象是测量系统：编译器有没有找到 query 真正需要的 research checks，matcher 和 judge 会不会拒绝合法替代证据。');
}

// 58 — Phases 8–10
{
  const slide = newSlide();
  addTitle(slide, 'Phase 8–10：扩题、因果审计、冻结发布', 'Part VI · Scale only after validity');
  const cards = [
    ['P8 · 56 题扩展', 'Route S：14 道手工种子，用于可解释的编译校准。\nRoute G：剩余 42 题从任务世界和类型模板编译。\n按主题、任务形态、来源角色、难度分层；每题先过 answerability + necessity + shortcut test。', C.blue],
    ['P9 · 抽样因果审计', '选 8–10 道 pivotal 题构造 W′：修改决定性事实、保留界面和工具协议。\n重跑 harness，检查报告中的相关结论是否跟着世界改变。\n作为 Causal Grounding 独立证书，不与主分相加。', C.purple],
    ['P10 · 冻结与发布', '同时冻结 world snapshot、index、TWM、RTS、matcher、judge、scorer、adapter 和提交协议。\n现有 12 harness 只用于特征化与攻击面发现，不反向优化正式题。\n改动走 erratum / challenger / 新版本，不静默改分。', C.green]
  ];
  cards.forEach((d, i) => addCard(slide, 0.65 + i * 4.19, 1.4, 3.78, 4.9, d[0], d[1], { accent: d[2], titleSize: 15, bodySize: 11.2 }));
  slide.addText('关键分界：评测集必须覆盖“合法证据空间”，但不能根据 12 个现有 harness 的路线定制正式答案。', {
    x: 0.95, y: 6.56, w: 11.5, h: 0.35, fontFace: FONT, fontSize: 12.3, bold: true, color: C.red, align: 'center', margin: 0, fit: 'shrink'
  });
  addFooter(slide, 'DRA v3.2 §20.9–20.11');
  addNotes(slide, '这回应一个重要质疑：不需要跑完 12 个 harness 才能定义一道题。我们用它们做 adversarial discovery，但题目的合法证据契约来自 query 和冻结世界。');
}

// Scope fences
{
  const slide = newSlide();
  addTitle(slide, '把论文最小闭环、正式 benchmark 和增强审计分开', 'Part VI · Scope control');
  const scopes = [
    ['A · 论文最小闭环', '一题端到端工程样本\n三类 DR 任务 MVP\nDev-14 compiler / matcher / judge 校准\n新旧分与盲专家广度判断的效度对照', C.blue, C.paleBlue],
    ['B · 正式 Benchmark Gate', '56 题 Route S / G 分层\nSearch API 质量证书\n12 adapter 资格与 report-only 轨\ncertificate epoch + PENDING=0 + 全部 ReleaseGates', C.teal, C.paleTeal],
    ['C · 增强研究轨', '8–10 道 twin-world 因果审计\nDecision Envelope 更完整形式化\n四轴质量面板的大规模定标\n跨版本 challenger / canary / 长期监控', C.purple, C.palePurple]
  ];
  scopes.forEach((d, i) => addCard(slide, 0.68 + i * 4.18, 1.45, 3.78, 4.82, d[0], d[1], { accent: d[2], fill: d[3], titleSize: 15, bodySize: 12.2 }));
  slide.addText('只有 A 是当前方法论必需；B 是对外发榜必需；C 是可独立发展的增强贡献，不应阻塞最小论文闭环。', {
    x: 0.88, y: 6.56, w: 11.55, h: 0.38, fontFace: FONT, fontSize: 11.4, bold: true, color: C.red, align: 'center', margin: 0, fit: 'shrink'
  });
  addFooter(slide, 'Scope fence: paper MVP ≠ formal leaderboard ≠ enhanced causal audit');
  addNotes(slide, '这页防止方案看起来像一个无法落地的愿望清单。当前应把资源集中在论文最小闭环；没有通过 A 之前，不应投入大规模 twin-world 或完整质量面板。');
}

// 59 — Dev-14
{
  const slide = newSlide();
  addTitle(slide, 'Dev-14 不是“手写 14 份标准答案”，而是标定测量过程', 'Part VI · Human calibration');
  const flow = [
    ['1', '双人盲拆 query', '独立标注用户约束、不可省略的研究方向和可选项'],
    ['2', '对照 Compiler', '只做 merge / split / delete / necessity 判定；记录所有人工修改'],
    ['3', 'Evidence audit', '确认冻结世界中至少一条合法支持组合；必须允许替代页面'],
    ['4', '删除 / 捷径测试', '删除 check 是否改变任务实质？只倒 URL 或写流畅空话能否骗分？'],
    ['5', '独立裁决', '测人际带、编译器编辑率、分歧、用时与可重现性']
  ];
  flow.forEach((d, i) => {
    const y = 1.25 + i * 1.08;
    addPill(slide, d[0], 0.72, y + 0.2, 0.46, C.white, [C.blue,C.teal,C.orange,C.purple,C.green][i]);
    slide.addText(d[1], { x: 1.45, y: y + 0.08, w: 2.55, h: 0.34, fontFace: FONT, fontSize: 13.1, bold: true, color: C.navy, margin: 0, fit: 'shrink' });
    slide.addText(d[2], { x: 4.15, y, w: 8.35, h: 0.62, fontFace: FONT, fontSize: 10.8, color: C.ink, margin: 0, fit: 'shrink' });
    if (i < flow.length - 1) slide.addShape(pptx.ShapeType.line, { x: 0.95, y: y + 0.78, w: 11.5, h: 0, line: { color: C.line, width: 0.8 } });
  });
  addEquationBox(slide, '人类标注的作用：为 Compiler / Matcher / Judge 建立效度证据，不是为每道题规定唯一路线', 1.05, 6.57, 11.2, 0.4, { fill: C.navy2, fontFace: FONT, fontSize: 13 });
  addFooter(slide, 'Dev-14 calibration protocol · DRA v3.2 §19.3, §20.7');
  addNotes(slide, '我们必须报人工编辑率和分歧类型。如果 compiler 的输出需要大量重写，自动化主张就不成立。');
}

// 60 — 56-task expansion
{
  const slide = newSlide();
  addTitle(slide, '56 题扩展：不再用“主题 × 随机原型”就直接入榜', 'Part VI · Dataset construction');
  const units = [
    ['事实 / 规格', C.blue], ['比较 / 排序', C.blue], ['宣传审核', C.orange], ['机制解释', C.teal],
    ['冲突处理', C.red], ['跨来源综合', C.purple], ['决策 / 推荐', C.green], ['有界缺失', C.muted],
    ['耐用 / 社区经验', C.orange], ['教程 / 行动计划', C.teal], ['演化 / 变化', C.purple], ['跨页聚合', C.blue]
  ];
  units.forEach((d, i) => {
    const col = i % 4;
    const row = Math.floor(i / 4);
    addPill(slide, d[0], 0.68 + col * 3.15, 1.42 + row * 0.66, 2.8, C.white, d[1]);
  });
  const routes = [
    ['Route S · 14', '前 14 道种子题\n人类可解释地校准类型学与编译器', C.teal],
    ['Route G · 42', '由冻结世界 + 任务类型生成\n反向编译 query + tests，过滤后才入集', C.blue],
    ['Held-out', '保留未参与调试的路线、文风和 harness-family 输出\n用于测 route binding 和过拟合', C.purple]
  ];
  routes.forEach((d, i) => addCard(slide, 0.66 + i * 4.18, 3.72, 3.75, 2.3, d[0], d[1], { accent: d[2], titleSize: 15, bodySize: 10.9 }));
  slide.addText('入集条件：Query round-trip 通过 ∧ Core checks 全部可答/可达 ∧ 无单路线锁定 ∧ 无捷径解 ∧ 类型配额满足', {
    x: 0.8, y: 6.55, w: 11.75, h: 0.4, fontFace: FONT, fontSize: 11.7, bold: true, color: C.navy, align: 'center', margin: 0, fit: 'shrink'
  });
  addFooter(slide, 'DRA v3.2 §5, §20.9');
  addNotes(slide, '题目数量不是主要门槛。每道题必须经过 query 语义往返检查、证据可答性和捷径测试；否则它只是一条自然语言 prompt，不是可评测任务。');
}

// 61 — Risks and gates
{
  const slide = newSlide();
  addTitle(slide, '七个最可能被 challenge 的点，必须在发榜前给出证书', 'Part VI · Risk register');
  const rows = [
    ['风险', '可观测证据', '发布门'],
    ['World Index 漏页/解析错', '分层抽样的覆盖率、字段正确率、重建 hash', 'ValidityGate'],
    ['TWM 候选池漏证据', '候选饱和曲线 + held-out 新页匹配回收率', 'ValidityGate'],
    ['Compiler 把合理报告拒绝', '合法替代层 FRR + 路线簇分层 CI', 'FRR gate'],
    ['Judge 把空话当完成', '流畅无证据 / URL dump / 局部腐蚀测试集', 'FAR gate'],
    ['原子粒度改变分数', '同义 split / merge metamorphic test', 'GranularityGate'],
    ['fabricated URL 误杀 registry 缺失', 'alias / redirect / registry 修复的盲复核日志', 'IntegrityGate'],
    ['队列和人力超出承受能力', 'PENDING 流入率、清空时间、单题成本和 p95 延迟', 'CapacityGate']
  ];
  addMiniTable(slide, rows, 0.42, 1.25, [3.05,6.35,2.7], 0.72, { headerSize: 9.5, bodySize: 9.3, align: 'left' });
  addCard(slide, 0.76, 6.48, 11.8, 0.47, '发布规则', '任意一道门未通过，不得用平均分或更多样本抵消；修复测量问题后发布新版本。', { accent: C.red, fill: C.paleRed, titleSize: 9.8, bodySize: 8.5, shadow: false });
  addFooter(slide, 'DRA v3.2 §19.5, §20.10, §21');
  addNotes(slide, '这页是审稿防线。不是说我们没有误差，而是每一个关键误差源都有可观测的指标和预先声明的停机条件。');
}

// 62 — Timeline
{
  const slide = newSlide();
  addTitle(slide, '建议时间线：以验证门为节点，不以“写完代码”为节点', 'Part VI · Gate-driven schedule');
  const stages = [
    ['W1–2', '单题世界', 'P0–P2\nWorld Index slice\nTWM + 可答性证书', C.blue],
    ['W3–4', '评分闭环', 'P3–P5\nCompiler / Matcher\nLedger / Replay / Score', C.teal],
    ['W5–7', 'Dev-14 校准', 'P6–P7\n双人盲标\n四层校准集 + FRR/FAR', C.orange],
    ['W8–10', '56 题扩展', 'P8\nRoute S + Route G\n抽样重审 + 类型平衡', C.purple],
    ['W11+', '审计与发布', 'P9–P10\nW′ 因果审计\n冻结、重跑、发榜', C.green]
  ];
  slide.addShape(pptx.ShapeType.line, { x: 1.1, y: 3.55, w: 11.1, h: 0, line: { color: C.line, width: 5 } });
  stages.forEach((d, i) => {
    const x = 0.63 + i * 2.52;
    slide.addShape(pptx.ShapeType.ellipse, { x: x + 0.85, y: 3.31, w: 0.48, h: 0.48, fill: { color: d[3] }, line: { color: C.white, width: 2 } });
    addPill(slide, d[0], x + 0.58, 1.28, 1.03, C.white, d[3]);
    slide.addText(d[1], { x, y: 1.83, w: 2.15, h: 0.4, fontFace: FONT, fontSize: 13, bold: true, color: C.navy, align: 'center', margin: 0, fit: 'shrink' });
    slide.addText(d[2], { x, y: 4.08, w: 2.15, h: 1.28, fontFace: FONT, fontSize: 9.7, color: C.ink, align: 'center', margin: 0, fit: 'shrink' });
  });
  addCard(slide, 1.05, 5.78, 11.25, 0.93, '这不是工期承诺', '每个节点都要看实测的人力、PENDING 流量和统计证书；任一 Gate 失败，时间线自动暂停。', { accent: C.red, fill: C.paleRed, titleSize: 11.2, bodySize: 9.8, shadow: false });
  addFooter(slide, 'Proposed implementation schedule · subject to ReleaseGates');
  addNotes(slide, '时间线是为了保证顺序而不是承诺日期。最关键的是不能在单题 matcher 和 observation 协议还不稳定时就扩到 56 题。');
}

// 63 — Immediate next experiment
{
  const slide = newSlide();
  addTitle(slide, '下一个实验不是“再跑一个强 harness”，而是验证测量闭环', 'Part VI · Immediate action');
  const artifacts = [
    ['世界侧', 'World Index slice\nTask Contract + TWM\nRTS + evidence pools', C.blue],
    ['参考输出', 'oracle / null\nURL dump / 流畅无证\n合法替代 / 无效路线', C.teal],
    ['局部攻击', 'unobserved citation\nwrong binding\nunsupported / contradicted\nfabricated URL', C.red],
    ['评分证书', 'Observation Ledger v2\ncheck-level verdicts\nGRC + task gate\nreplay bundle', C.purple]
  ];
  artifacts.forEach((d, i) => {
    addCard(slide, 0.62 + i * 3.18, 1.42, 2.86, 3.6, d[0], d[1], { accent: d[2], titleSize: 14.2, bodySize: 11.4 });
    if (i < 3) addArrow(slide, 3.49 + i * 3.18, 3.22, 3.74 + i * 3.18, 3.22, C.muted, 1.5);
  });
  addCard(slide, 0.85, 5.45, 3.72, 1.04, '成功条件 1', '合法替代路线与 reference route 获得等价通过。', { accent: C.green, fill: C.paleTeal, titleSize: 11, bodySize: 9.4, shadow: false });
  addCard(slide, 4.8, 5.45, 3.72, 1.04, '成功条件 2', '局部腐蚀只影响对应 check，但 fabricated citation 触发任务级门。', { accent: C.orange, fill: C.paleOrange, titleSize: 11, bodySize: 9.4, shadow: false });
  addCard(slide, 8.75, 5.45, 3.72, 1.04, '成功条件 3', '第三方能从冻结产物重放每一个 verdict 和最终分数。', { accent: C.blue, fill: C.paleBlue, titleSize: 11, bodySize: 9.4, shadow: false });
  addFooter(slide, 'First engineering smoke test · dra_v3_dev_audio_0002');
  addNotes(slide, '强 harness 的分数只是方法的一个输入样本。先用可控的参考报告和局部攻击证明评分器有所需的不变性，然后才有意义解释 harness 分数。');
}

// 64 — Conclusions
{
  const slide = newSlide(C.navy);
  slide.addText('最后带走五句话', { x: 0.72, y: 0.65, w: 11.8, h: 0.65, fontFace: FONT, fontSize: 30, bold: true, color: C.white, margin: 0 });
  const takeaways = [
    ['01', '旧系统的 Fact / PoF / Completeness 不是都无用；它们是诊断信号，但不应用任意权重先加再乘。'],
    ['02', 'DRA 的核心构念是“广度任务中，有本次交付证据地完成了多少必要研究工作”。'],
    ['03', 'LoHoSearch 告诉我们：全量做轻量结构，贵的语义工作只在单题局部世界中做。'],
    ['04', 'Raw GRC 用 check-level C×E + 层级聚合；确认不存在的 URL 另产生 integrity-adjusted 排名分；质量独立展示。'],
    ['05', '标准答案不是一条路线，而是一套允许替代证据、可重放、可校准的执行协议。']
  ];
  takeaways.forEach((d, i) => {
    const y = 1.55 + i * 0.92;
    slide.addText(d[0], { x: 0.8, y: y + 0.04, w: 0.62, h: 0.38, fontFace: FONT_MONO, fontSize: 15, bold: true, color: [C.blue,C.teal,C.orange,C.purple,C.green][i], margin: 0 });
    slide.addText(d[1], { x: 1.62, y, w: 10.85, h: 0.54, fontFace: FONT, fontSize: 13.2, color: C.white, margin: 0, fit: 'shrink' });
  });
  slide.addText('先一题 → 再三类 MVP → Dev-14 → 56 题 → 冻结后跑 12 harness', { x: 1.15, y: 6.38, w: 11, h: 0.44, fontFace: FONT_MONO, fontSize: 14.4, bold: true, color: C.green, align: 'center', margin: 0, fit: 'shrink' });
  addFooter(slide, 'DRA sandbox-native scoring redesign · conclusion', true);
  addNotes(slide, '这五句是整场汇报的最简摘要。如果只剩两分钟，就用这页收束。');
}

// 65 — References
{
  const slide = newSlide();
  addTitle(slide, '主要文献与内部依据', 'Appendix · Primary sources');
  const left = [
    '• LoHoSearch, arXiv:2606.12837 (v2, 2026-06-17)',
    '• DEEPRUBRIC, arXiv:2606.17029',
    '• QUBRIC, arXiv:2606.03968',
    '• WideSearch, arXiv:2508.07999',
    '• DeepSearchQA, arXiv:2601.20975',
    '• DeepWideSearch, arXiv:2510.20168',
    '• DeepResearchGym, arXiv:2505.19253',
    '• Mind2Web 2, arXiv:2506.21506'
  ];
  const right = [
    '• ALCE, arXiv:2305.14627',
    '• FActScore, arXiv:2305.14251',
    '• BrowseComp-Plus, arXiv:2508.06600',
    '• DeepResearch Bench II, arXiv:2601.08536',
    '• Correctness is not Faithfulness, arXiv:2412.18004',
    '• FutureSearch Deep Research Bench / RetroSearch, arXiv:2506.06287',
    '• DRA Current Method (2026-07-14)',
    '• DRA Sandbox-native Scoring Design v3.2 (2026-07-18)',
    '• DRA Scoring Redesign v3.3 candidate (this deck)'
  ];
  addCard(slide, 0.65, 1.42, 5.96, 4.95, '构题、广度与长程研究', left.join('\n'), { accent: C.blue, titleSize: 15, bodySize: 11.3 });
  addCard(slide, 6.84, 1.42, 5.84, 4.95, '引用、信实性与冻结环境', right.join('\n'), { accent: C.teal, titleSize: 15, bodySize: 11.3 });
  slide.addText('LoHoSearch 原论文图 1 / 2 / 4 按 CC BY 4.0 使用；页内数据与公式均以论文实际文本为准。', {
    x: 0.95, y: 6.62, w: 11.45, h: 0.28, fontFace: FONT, fontSize: 9.6, color: C.muted, align: 'center', margin: 0
  });
  addFooter(slide, 'Primary-source reading list · arXiv identifiers shown for reproducibility');
  addNotes(slide, '详细引文位置已放在各页页脚。这页作为主要参考文献入口，不代替正式论文中的完整参考文献表。');
}

fs.mkdirSync(OUT_DIR, { recursive: true });

(async () => {
  await pptx.writeFile({ fileName: OUTPUT, compression: true });
  console.log(`Wrote ${slideNumber} slides to ${OUTPUT}`);
})().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
