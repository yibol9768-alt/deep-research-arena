'use client'

/* -------------------------------------------------------------------------- */
/* /survey — Google-Search-style pairwise annotation (kappa collection).       */
/*                                                                             */
/* 目的: 用搜索结果页的熟悉形态收集人类成对偏好, 与 /annotate 同一数据源       */
/* (annotate-pairs.json) 与同一后端 (POST /api/annotate, 静默降级到           */
/* localStorage + JSONL 导出), 额外多收一个 "更信任哪份" 信号, 用于           */
/* judge-vs-human 与 grounding-vs-human 两个 kappa。                           */
/*                                                                             */
/* 与 /annotate 的差异: 报告以 SERP 卡片呈现 (蓝标题/绿 URL/摘要),           */
/* 引用以搜索结果列表样式展开, 沙箱内 URL 打绿色可验证徽标;                  */
/* 呈现顺序按 pair 稳定伪随机翻转, 标签写回时映射回规范 a/b。                  */
/* markdown 渲染与 /annotate 内的实现同源 (轻量复制, 待抽公共组件)。          */
/* -------------------------------------------------------------------------- */

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  Link2,
  Loader2,
  Search,
  ShieldCheck,
  SkipForward,
} from 'lucide-react'
import { cn } from '@/lib/cn'
import { Button } from '@/components/ui/button'
import { Chip } from '@/components/ui/chip'
import { T } from '@/components/i18n/t'
import { useLang } from '@/components/i18n/use-lang'

const PAIRS_URL = '/annotate-pairs.json'
const POST_URL = '/api/annotate'
const POST_ENABLED = process.env.NEXT_PUBLIC_ANNOTATE_POST !== '0'
const LS_LABELS = 'dra.survey.labels.v1'
const LS_PROGRESS = 'dra.survey.index.v1'
const LS_ANNOTATOR = 'dra.annotate.annotator.v1' // 与 /annotate 共用署名

const DIMS = ['coverage', 'depth', 'rigor', 'style', 'checklist', 'spec'] as const
const DIM_ZH: Record<string, string> = {
  coverage: '覆盖度',
  depth: '深度',
  rigor: '严谨性',
  style: '行文',
  checklist: '清单符合度',
  spec: '规范符合度',
}
type Dim = (typeof DIMS)[number]
type Winner = 'a' | 'b' | 'tie'
type Trust = 'a' | 'b' | 'unsure'

interface Pair {
  task_id: string
  agent_a: string
  agent_b: string
  intent: string
  words_a: number
  words_b: number
  report_a: string
  report_b: string
  intent_zh?: string
  report_a_zh?: string
  report_b_zh?: string
}
interface Bundle {
  generated: string
  pairs: Pair[]
}
interface Label {
  task_id: string
  agent_a: string
  agent_b: string
  winner: Winner
  trust: Trust | null
  dims: Dim[]
  swapped: boolean
  annotator: string
  source: 'survey'
  ts: string
}

function pairKey(p: Pick<Pair, 'task_id' | 'agent_a' | 'agent_b'>): string {
  return `${p.task_id}::${p.agent_a}::${p.agent_b}`
}

/* 稳定伪随机: 同一 pair 每次进来顺序一致, 但整体约一半被翻转。 */
function stableSwap(key: string): boolean {
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0
  return (h & 1) === 1
}

/* ------------------------------ SERP helpers ------------------------------ */

const SANDBOX_HOSTS = ['localhost:7770', 'localhost:9999', 'localhost:8090',
  '__SHOPPING__', '__REDDIT__', '__WIKIPEDIA__']

function isSandboxUrl(url: string): boolean {
  return SANDBOX_HOSTS.some((h) => url.includes(h))
}

interface Citation {
  label: string
  url: string
  sandbox: boolean
}

function extractCitations(md: string): Citation[] {
  const seen = new Set<string>()
  const out: Citation[] = []
  const re = /\[([^\]]+)\]\((https?:\/\/[^)\s]+|__[A-Z]+__[^)\s]*)\)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(md)) !== null) {
    const url = m[2]
    if (seen.has(url)) continue
    seen.add(url)
    out.push({ label: m[1].slice(0, 90), url, sandbox: isSandboxUrl(url) })
  }
  return out
}

/* 提取首个标题作 SERP 蓝标题, 首段散文作摘要。 */
function serpTitle(md: string, fallback: string): string {
  const m = /^#{1,3}\s+(.+)$/m.exec(md)
  return (m ? m[1] : fallback).replace(/[*_`#]/g, '').slice(0, 90)
}
function serpSnippet(md: string): string {
  const text = md
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/^#{1,6}\s+.*$/gm, ' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[*_`>|#-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return text.slice(0, 220)
}

/* --------------------------- tiny markdown view --------------------------- */
/* 与 /annotate 的渲染同一覆盖面 (标题/列表/链接/粗斜体/引用/表格/段落),      */
/* 全部纯 React 节点, 不用 dangerouslySetInnerHTML。                           */

let ik = 0
function inline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = []
  const pat = /(\[[^\]]+\]\([^)]+\))|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(`[^`]+`)/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = pat.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    const t = m[0]
    if (t.startsWith('[')) {
      const l = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(t)
      nodes.push(
        l ? (
          <a key={`s${ik++}`} href={l[2]} target="_blank" rel="noreferrer"
            className="text-brand underline decoration-brand/30 underline-offset-2 break-words">
            {l[1]}
          </a>
        ) : t,
      )
    } else if (t.startsWith('**')) {
      nodes.push(<strong key={`s${ik++}`} className="font-semibold text-ink">{t.slice(2, -2)}</strong>)
    } else if (t.startsWith('*')) {
      nodes.push(<em key={`s${ik++}`} className="italic">{t.slice(1, -1)}</em>)
    } else {
      nodes.push(<code key={`s${ik++}`} className="rounded bg-surface-mid px-1 font-mono text-[0.85em]">{t.slice(1, -1)}</code>)
    }
    last = m.index + t.length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

function Md({ source }: { source: string }) {
  const blocks: React.ReactNode[] = []
  const lines = source.replace(/\r\n/g, '\n').split('\n')
  let i = 0
  let k = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.trim() === '') { i++; continue }
    if (/^\s*```/.test(line)) {
      i++
      const code: string[] = []
      while (i < lines.length && !/^\s*```/.test(lines[i])) { code.push(lines[i]); i++ }
      if (i < lines.length) i++
      blocks.push(<pre key={k++} className="my-3 overflow-x-auto rounded-tab bg-surface-low p-3 font-mono text-xs leading-relaxed">{code.join('\n')}</pre>)
      continue
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line)
    if (h) {
      const lv = h[1].length
      blocks.push(
        <div key={k++} className={cn('mt-4 mb-1.5 font-semibold text-ink', lv <= 2 ? 'text-base' : 'text-sm')}>
          {inline(h[2])}
        </div>,
      )
      i++
      continue
    }
    if (/^\s*[-*+]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && (/^\s*[-*+]\s+/.test(lines[i]) || /^\s*\d+\.\s+/.test(lines[i]))) {
        items.push(lines[i].replace(/^\s*([-*+]|\d+\.)\s+/, ''))
        i++
      }
      blocks.push(
        <ul key={k++} className="my-2 list-disc space-y-1 pl-5 text-sm leading-relaxed text-muted">
          {items.map((it, ii) => <li key={ii}>{inline(it)}</li>)}
        </ul>,
      )
      continue
    }
    if (/^\s*>\s?/.test(line)) {
      const q: string[] = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) { q.push(lines[i].replace(/^\s*>\s?/, '')); i++ }
      blocks.push(<blockquote key={k++} className="my-3 border-l-2 border-brand/40 pl-3 text-sm italic text-muted">{inline(q.join(' '))}</blockquote>)
      continue
    }
    if (/^\s*\|.*\|\s*$/.test(line)) {
      const rows: string[] = []
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(lines[i]); i++ }
      const cells = (r: string) => r.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
      const isSep = (r: string) => /^[\s:|-]+$/.test(r.replace(/\|/g, ''))
      const body = rows.filter((r) => !isSep(r)).map(cells)
      blocks.push(
        <div key={k++} className="my-3 overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <tbody>
              {body.map((row, ri) => (
                <tr key={ri}>{row.map((c, ci) => <td key={ci} className="border border-hairline px-2 py-1 align-top text-muted">{inline(c)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() !== '' && !/^(#{1,6})\s+|^\s*[-*+]\s+|^\s*\d+\.\s+|^\s*\|.*\|\s*$|^\s*```|^\s*>\s?/.test(lines[i])) {
      para.push(lines[i]); i++
    }
    blocks.push(<p key={k++} className="my-2 text-sm leading-relaxed text-muted">{inline(para.join(' '))}</p>)
  }
  return <div>{blocks}</div>
}

/* ------------------------------- SERP card -------------------------------- */

function ResultCard({
  slot, title, snippet, words, citations, expanded, onToggle, children,
}: {
  slot: '1' | '2'
  title: string
  snippet: string
  words: number
  citations: Citation[]
  expanded: boolean
  onToggle: () => void
  children: React.ReactNode
}) {
  const [showCites, setShowCites] = useState(false)
  const sandboxN = citations.filter((c) => c.sandbox).length
  return (
    <div className="rounded-card border border-hairline bg-white p-4 shadow-soft">
      {/* SERP 头: 圆点 favicon + 伪站点行 */}
      <div className="flex items-center gap-2 text-xs text-muted">
        <span className={cn('inline-flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold text-white', slot === '1' ? 'bg-brand' : 'bg-ink')}>
          {slot}
        </span>
        <span className="font-medium text-ink">
          <T en={`Research result ${slot}`} zh={`调研结果 ${slot}`} />
        </span>
        <span className="truncate text-emerald-700">
          report-{slot}.dra.internal
        </span>
      </div>
      <button onClick={onToggle} className="mt-2 block text-left">
        <div className="text-lg font-medium leading-snug text-[#1a0dab] hover:underline">
          {title}
        </div>
      </button>
      <p className="mt-1 text-sm leading-relaxed text-muted">
        {snippet}…
        <span className="ml-2 whitespace-nowrap text-xs text-faint">
          {words.toLocaleString()} <T en="words" zh="词" />
        </span>
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Chip onClick={onToggle} active={expanded}>
          {expanded ? <T en="Collapse report" zh="收起全文" /> : <T en="Read full report" zh="展开全文" />}
        </Chip>
        <Chip onClick={() => setShowCites((v) => !v)} active={showCites}>
          <Link2 className="h-3 w-3" />
          <T en={`Citations · ${citations.length}`} zh={`引用来源 · ${citations.length}`} />
        </Chip>
        <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
          <ShieldCheck className="h-3.5 w-3.5" />
          <T en={`${sandboxN} sandbox-verifiable`} zh={`${sandboxN} 条站内可验证`} />
        </span>
      </div>
      {showCites ? (
        <ol className="mt-3 max-h-56 space-y-2 overflow-y-auto rounded-tab bg-surface-low p-3">
          {citations.slice(0, 40).map((c, i) => (
            <li key={i} className="text-xs leading-snug">
              <div className="truncate font-medium text-[#1a0dab]">{c.label}</div>
              <div className="flex items-center gap-1.5">
                <span className="truncate text-emerald-700">{c.url}</span>
                {c.sandbox ? null : (
                  <span className="whitespace-nowrap rounded-pill bg-amber-100 px-1.5 text-[10px] text-amber-800">
                    <T en="off-sandbox" zh="站外" />
                  </span>
                )}
              </div>
            </li>
          ))}
          {citations.length > 40 ? (
            <li className="text-xs text-faint">
              <T en={`… and ${citations.length - 40} more`} zh={`… 还有 ${citations.length - 40} 条`} />
            </li>
          ) : null}
        </ol>
      ) : null}
      {expanded ? (
        <div className="mt-3 max-h-[32rem] overflow-y-auto rounded-tab border border-hairline p-4">
          {children}
        </div>
      ) : null}
    </div>
  )
}

/* --------------------------------- page ----------------------------------- */

export default function SurveyPage() {
  const lang = useLang()
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [index, setIndex] = useState(0)
  const [labels, setLabels] = useState<Record<string, Label>>({})
  const [annotator, setAnnotator] = useState('')
  const [winner, setWinner] = useState<Winner | null>(null) // 以显示槽位记
  const [trust, setTrust] = useState<Trust | null>(null)
  const [dims, setDims] = useState<Dim[]>([])
  const [exp1, setExp1] = useState(false)
  const [exp2, setExp2] = useState(false)

  useEffect(() => {
    fetch(PAIRS_URL)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((b: Bundle) => setBundle(b))
      .catch((e) => setError(String(e)))
    try {
      const raw = localStorage.getItem(LS_LABELS)
      if (raw) setLabels(JSON.parse(raw))
      const idx = localStorage.getItem(LS_PROGRESS)
      if (idx) setIndex(Math.max(0, parseInt(idx, 10) || 0))
      const who = localStorage.getItem(LS_ANNOTATOR)
      if (who) setAnnotator(who)
    } catch { /* localStorage 不可用: 仅内存 */ }
  }, [])

  useEffect(() => {
    try { localStorage.setItem(LS_LABELS, JSON.stringify(labels)) } catch { }
  }, [labels])
  useEffect(() => {
    try { localStorage.setItem(LS_PROGRESS, String(index)) } catch { }
  }, [index])
  useEffect(() => {
    try { localStorage.setItem(LS_ANNOTATOR, annotator) } catch { }
  }, [annotator])

  const pairs = bundle?.pairs ?? []
  const pair = pairs[index] as Pair | undefined
  const swapped = pair ? stableSwap(pairKey(pair)) : false

  /* 槽位 1/2 -> 规范 a/b */
  const slotToCanon = useCallback(
    (s: '1' | '2'): 'a' | 'b' => (s === '1') !== swapped ? 'a' : 'b',
    [swapped],
  )

  const view = useMemo(() => {
    if (!pair) return null
    const zh = lang === 'zh'
    const ra = (zh && pair.report_a_zh) || pair.report_a
    const rb = (zh && pair.report_b_zh) || pair.report_b
    const one = swapped ? rb : ra
    const two = swapped ? ra : rb
    return {
      intent: (zh && pair.intent_zh) || pair.intent,
      one, two,
      words1: swapped ? pair.words_b : pair.words_a,
      words2: swapped ? pair.words_a : pair.words_b,
      cites1: extractCitations(swapped ? pair.report_b : pair.report_a),
      cites2: extractCitations(swapped ? pair.report_a : pair.report_b),
    }
  }, [pair, lang, swapped])

  /* 已有标签回填 (按规范 a/b 存, 显示时映射回槽位)。 */
  useEffect(() => {
    if (!pair) return
    const l = labels[pairKey(pair)]
    if (!l) { setWinner(null); setTrust(null); setDims([]); setExp1(false); setExp2(false); return }
    const canonToSlot = (w: Winner): Winner =>
      w === 'tie' ? 'tie' : ((w === 'a') !== swapped ? 'a' : 'b')
    setWinner(canonToSlot(l.winner))
    setTrust(l.trust === null || l.trust === 'unsure' ? l.trust : (canonToSlot(l.trust) as Trust))
    setDims(l.dims)
    setExp1(false); setExp2(false)
  }, [pair, labels, swapped])

  const submit = useCallback(() => {
    if (!pair || !winner) return
    const slotWinnerToCanon = (w: Winner): Winner =>
      w === 'tie' ? 'tie' : slotToCanon(w === 'a' ? '1' : '2')
    const label: Label = {
      task_id: pair.task_id,
      agent_a: pair.agent_a,
      agent_b: pair.agent_b,
      winner: slotWinnerToCanon(winner),
      trust: trust === null || trust === 'unsure' ? trust : (slotWinnerToCanon(trust) as Trust),
      dims,
      swapped,
      annotator: annotator.trim() || 'anon',
      source: 'survey',
      ts: new Date().toISOString(),
    }
    setLabels((prev) => ({ ...prev, [pairKey(pair)]: label }))
    if (POST_ENABLED) {
      fetch(POST_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(label),
      }).catch(() => { /* 后端缺席: localStorage 已存 */ })
    }
    if (index < pairs.length - 1) setIndex(index + 1)
  }, [pair, winner, trust, dims, swapped, annotator, index, pairs.length, slotToCanon])

  const exportJsonl = useCallback(() => {
    const lines = Object.values(labels).map((l) => JSON.stringify(l))
    const blob = new Blob([lines.join('\n') + (lines.length ? '\n' : '')], { type: 'application/jsonl' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    const stamp = new Date().toISOString().slice(0, 10)
    a.download = `survey_prefs_${annotator.trim() || 'anon'}_${stamp}.jsonl`
    a.click()
    URL.revokeObjectURL(a.href)
  }, [labels, annotator])

  const done = Object.keys(labels).length

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center">
        <AlertCircle className="mx-auto h-8 w-8 text-red-500" />
        <p className="mt-3 text-sm text-muted">
          <T en="Could not load survey pairs." zh="调研对載入失败。" /> {error}
        </p>
      </div>
    )
  }
  if (!bundle || !pair || !view) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted" />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl px-4 pb-40 pt-8">
      {/* 搜索框头部 (Google 形态) */}
      <div className="mx-auto max-w-3xl">
        <div className="flex items-start gap-3 rounded-[24px] border border-hairline bg-white px-5 py-3 shadow-soft">
          <Search className="mt-0.5 h-5 w-5 shrink-0 text-muted" />
          <p className="text-sm leading-relaxed text-ink">{view.intent}</p>
        </div>
        <div className="mt-2 flex items-center justify-between px-2 text-xs text-faint">
          <span>
            <T
              en={`2 research results · task ${pair.task_id} · pair ${index + 1} / ${pairs.length}`}
              zh={`找到 2 条调研结果 · 任务 ${pair.task_id} · 第 ${index + 1} / ${pairs.length} 对`}
            />
          </span>
          <span>
            <T en={`${done} labeled`} zh={`已标 ${done} 对`} />
          </span>
        </div>
      </div>

      {/* 两条结果 */}
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <ResultCard
          slot="1"
          title={serpTitle(view.one, lang === 'zh' ? '调研结果一' : 'Research result 1')}
          snippet={serpSnippet(view.one)}
          words={view.words1}
          citations={view.cites1}
          expanded={exp1}
          onToggle={() => setExp1((v) => !v)}
        >
          <Md source={view.one} />
        </ResultCard>
        <ResultCard
          slot="2"
          title={serpTitle(view.two, lang === 'zh' ? '调研结果二' : 'Research result 2')}
          snippet={serpSnippet(view.two)}
          words={view.words2}
          citations={view.cites2}
          expanded={exp2}
          onToggle={() => setExp2((v) => !v)}
        >
          <Md source={view.two} />
        </ResultCard>
      </div>

      {/* 底部固定裁决栏 */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-hairline bg-white/95 backdrop-blur">
        <div className="mx-auto max-w-5xl space-y-2 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-ink">
              <T en="Which result is better?" zh="哪条结果更好?" />
            </span>
            {(['a', 'tie', 'b'] as Winner[]).map((w) => (
              <Chip key={w} active={winner === w} tone="brand" onClick={() => setWinner(w)}>
                {w === 'a' ? <T en="Result 1" zh="结果一" /> : w === 'b' ? <T en="Result 2" zh="结果二" /> : <T en="Tie" zh="不相上下" />}
              </Chip>
            ))}
            <span className="ml-4 text-sm font-medium text-ink">
              <T en="Which do you trust more?" zh="更信任哪条?" />
            </span>
            {(['a', 'unsure', 'b'] as Trust[]).map((t) => (
              <Chip key={t} active={trust === t} onClick={() => setTrust(t)}>
                {t === 'a' ? <T en="1" zh="一" /> : t === 'b' ? <T en="2" zh="二" /> : <T en="Unsure" zh="说不清" />}
              </Chip>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted">
              <T en="Why (optional):" zh="判断依据(可多选):" />
            </span>
            {DIMS.map((d) => (
              <Chip
                key={d}
                active={dims.includes(d)}
                onClick={() => setDims((prev) => prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d])}
              >
                <T en={d} zh={DIM_ZH[d]} />
              </Chip>
            ))}
            <input
              value={annotator}
              onChange={(e) => setAnnotator(e.target.value)}
              placeholder={lang === 'zh' ? '署名(可选)' : 'annotator (optional)'}
              className="ml-auto h-8 w-36 rounded-tab border border-hairline px-2 text-xs focus:outline-none focus:shadow-ring"
            />
            <Button variant="ghost" size="sm" onClick={() => setIndex(Math.max(0, index - 1))} disabled={index === 0}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setIndex(Math.min(pairs.length - 1, index + 1))} disabled={index >= pairs.length - 1}>
              <SkipForward className="h-4 w-4" />
              <T en="Skip" zh="跳过" />
            </Button>
            <Button size="sm" onClick={submit} disabled={!winner}>
              <Check className="h-4 w-4" />
              <T en="Submit & next" zh="提交并下一对" />
            </Button>
            <Button variant="secondary" size="sm" onClick={exportJsonl} disabled={done === 0}>
              <Download className="h-4 w-4" />
              JSONL
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setIndex(Math.min(pairs.length - 1, index + 1))} className="hidden">
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
