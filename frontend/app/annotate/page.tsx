'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  SkipForward,
  Trophy,
  Loader2,
  AlertCircle,
} from 'lucide-react'
import { cn } from '@/lib/cn'
import { Button } from '@/components/ui/button'
import { Chip } from '@/components/ui/chip'
import { PageHero, MetricCard } from '@/components/layout/metric-card'

/* -------------------------------------------------------------------------- */
/* Optional backend wiring (off by default).                                   */
/*                                                                             */
/* The site ships as a STATIC export, so localStorage + the JSONL export are   */
/* the primary path and NO backend is required. If a Cloudflare Pages Function */
/* is later added at POST /api/annotate, flip ANNOTATE_POST_ENABLED to true    */
/* (or set NEXT_PUBLIC_ANNOTATE_POST=1 at build time). Every POST is wrapped   */
/* in try/catch and silently falls back to localStorage when the endpoint is   */
/* absent or errors, so enabling it can never lose a label.                    */
/* -------------------------------------------------------------------------- */
/* POST to the Worker backend (functions in public/_worker.js) by default; if the
 * backend is absent/unconfigured the call fails silently and localStorage + the
 * JSONL export still work. Set NEXT_PUBLIC_ANNOTATE_POST=0 to force-disable.   */
const ANNOTATE_POST_ENABLED =
  process.env.NEXT_PUBLIC_ANNOTATE_POST !== '0'
const ANNOTATE_POST_URL = '/api/annotate'

const PAIRS_URL = '/annotate-pairs.json'
const LS_LABELS = 'dra.annotate.labels.v1'
const LS_PROGRESS = 'dra.annotate.index.v1'
const LS_ANNOTATOR = 'dra.annotate.annotator.v1'

/* Judge dimensions an annotator may cite as the reason for a verdict.         */
const DIMS = ['coverage', 'depth', 'rigor', 'style', 'checklist', 'spec'] as const
type Dim = (typeof DIMS)[number]
type Winner = 'a' | 'b' | 'tie'

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
  truncate_chars?: number
  pairs: Pair[]
}

interface Label {
  task_id: string
  agent_a: string
  agent_b: string
  winner: Winner
  dims: Dim[]
  annotator: string
  ts: string
}

/* Stable key for one pair (a pair is one task + ordered agent A/B).           */
function pairKey(p: Pick<Pair, 'task_id' | 'agent_a' | 'agent_b'>): string {
  return `${p.task_id}::${p.agent_a}::${p.agent_b}`
}

/* Friendly display name for a raw agent id from the bundle.                    */
function agentDisplay(id: string): string {
  const map: Record<string, string> = {
    'camel-ai': 'CAMEL-AI',
    'claude-code': 'Claude Code',
    'gpt-researcher': 'GPT Researcher',
    'langchain-odr': 'LangChain ODR',
    smolagents: 'smolagents',
    'flowsearcher-ds': 'FlowSearcher',
    storm: 'STORM',
    opencode: 'OpenCode',
    'tongyi-dr': 'Tongyi DR',
  }
  return map[id] ?? id
}

/* -------------------------------------------------------------------------- */
/* Tiny markdown renderer.                                                      */
/*                                                                             */
/* Deliberately minimal so we add no dependency and keep the bundle small. It  */
/* covers what the agent reports actually use: headings, bold / italic, inline */
/* code, links, ordered / unordered lists, horizontal rules, and paragraphs.   */
/* Everything is rendered as plain React (no dangerouslySetInnerHTML), so      */
/* report content cannot inject markup.                                         */
/* -------------------------------------------------------------------------- */

let inlineKey = 0
function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = []
  // Order matters: links, then bold, then italic, then inline code.
  const pattern =
    /(\[[^\]]+\]\([^)]+\))|(\*\*[^*]+\*\*)|(__[^_]+__)|(\*[^*]+\*)|(`[^`]+`)/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    const token = m[0]
    if (token.startsWith('[')) {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token)
      if (link) {
        nodes.push(
          <a
            key={`i${inlineKey++}`}
            href={link[2]}
            target="_blank"
            rel="noreferrer"
            className="text-brand underline decoration-brand/30 underline-offset-2 hover:decoration-brand break-words"
          >
            {link[1]}
          </a>,
        )
      } else {
        nodes.push(token)
      }
    } else if (token.startsWith('**') || token.startsWith('__')) {
      nodes.push(
        <strong key={`i${inlineKey++}`} className="font-semibold text-ink">
          {token.slice(2, -2)}
        </strong>,
      )
    } else if (token.startsWith('*')) {
      nodes.push(
        <em key={`i${inlineKey++}`} className="italic">
          {token.slice(1, -1)}
        </em>,
      )
    } else if (token.startsWith('`')) {
      nodes.push(
        <code
          key={`i${inlineKey++}`}
          className="rounded bg-surface-mid px-1 py-0.5 font-mono text-[0.85em] text-ink"
        >
          {token.slice(1, -1)}
        </code>,
      )
    }
    last = m.index + token.length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

function Markdown({ source }: { source: string }) {
  const blocks: React.ReactNode[] = []
  const lines = source.replace(/\r\n/g, '\n').split('\n')
  let i = 0
  let key = 0

  while (i < lines.length) {
    const line = lines[i]

    // Blank line.
    if (line.trim() === '') {
      i++
      continue
    }

    // Fenced code block (``` ... ```).
    if (/^\s*```/.test(line)) {
      i++
      const code: string[] = []
      while (i < lines.length && !/^\s*```/.test(lines[i])) {
        code.push(lines[i])
        i++
      }
      if (i < lines.length) i++ // closing fence
      blocks.push(
        <pre
          key={key++}
          className="my-3 overflow-x-auto rounded-tab bg-surface-low p-3 font-mono text-xs leading-relaxed text-ink"
        >
          {code.join('\n')}
        </pre>,
      )
      continue
    }

    // Blockquote (> ...), e.g. quoted forum posts.
    if (/^\s*>\s?/.test(line)) {
      const quote: string[] = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quote.push(lines[i].replace(/^\s*>\s?/, ''))
        i++
      }
      blocks.push(
        <blockquote
          key={key++}
          className="my-3 border-l-2 border-brand/40 pl-3 text-sm italic leading-relaxed text-muted"
        >
          {renderInline(quote.join(' '))}
        </blockquote>,
      )
      continue
    }

    // Horizontal rule.
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) {
      blocks.push(<hr key={key++} className="my-5 border-hairline" />)
      i++
      continue
    }

    // Heading.
    const h = /^(#{1,6})\s+(.*)$/.exec(line)
    if (h) {
      const level = h[1].length
      const content = renderInline(h[2])
      const cls =
        level <= 1
          ? 'font-serif text-xl text-ink mt-6 mb-2 first:mt-0'
          : level === 2
            ? 'font-serif text-lg text-ink mt-5 mb-2 first:mt-0'
            : 'font-semibold text-sm uppercase tracking-wide text-muted mt-4 mb-1.5'
      blocks.push(
        <p key={key++} className={cls}>
          {content}
        </p>,
      )
      i++
      continue
    }

    // Unordered list.
    if (/^\s*[-*+]\s+/.test(line)) {
      const items: React.ReactNode[] = []
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        const item = lines[i].replace(/^\s*[-*+]\s+/, '')
        items.push(
          <li key={key++} className="leading-relaxed">
            {renderInline(item)}
          </li>,
        )
        i++
      }
      blocks.push(
        <ul key={key++} className="my-2 list-disc space-y-1 pl-5 text-sm text-muted">
          {items}
        </ul>,
      )
      continue
    }

    // Ordered list.
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: React.ReactNode[] = []
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        const item = lines[i].replace(/^\s*\d+\.\s+/, '')
        items.push(
          <li key={key++} className="leading-relaxed">
            {renderInline(item)}
          </li>,
        )
        i++
      }
      blocks.push(
        <ol key={key++} className="my-2 list-decimal space-y-1 pl-5 text-sm text-muted">
          {items}
        </ol>,
      )
      continue
    }

    // Table: header row, a |---|---| separator, then body rows -> real table
    // (the reports are full of product-comparison tables; raw pipes are unreadable).
    if (/^\s*\|.*\|\s*$/.test(line)) {
      const rows: string[] = []
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        rows.push(lines[i])
        i++
      }
      const splitCells = (r: string) =>
        r.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
      const isSep = (r: string) => r.includes('-') && /^[\s:|-]+$/.test(r.replace(/\|/g, ''))
      let header: string[] | null = null
      let bodyStart = 0
      if (rows.length >= 2 && isSep(rows[1])) {
        header = splitCells(rows[0])
        bodyStart = 2
      }
      const body = rows.slice(bodyStart).filter((r) => !isSep(r)).map(splitCells)
      blocks.push(
        <div key={key++} className="my-3 overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            {header ? (
              <thead>
                <tr>
                  {header.map((c, ci) => (
                    <th
                      key={ci}
                      className="border border-hairline bg-surface-low px-2 py-1 text-left font-semibold text-ink"
                    >
                      {renderInline(c)}
                    </th>
                  ))}
                </tr>
              </thead>
            ) : null}
            <tbody>
              {body.map((row, ri) => (
                <tr key={ri}>
                  {row.map((c, ci) => (
                    <td key={ci} className="border border-hairline px-2 py-1 align-top text-muted">
                      {renderInline(c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    // Paragraph: gather consecutive non-blank, non-structural lines.
    const para: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^(#{1,6})\s+/.test(lines[i]) &&
      !/^\s*[-*+]\s+/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i]) &&
      !/^\s*\|.*\|\s*$/.test(lines[i]) &&
      !/^\s*```/.test(lines[i]) &&
      !/^\s*>\s?/.test(lines[i]) &&
      !/^\s*(---|\*\*\*|___)\s*$/.test(lines[i])
    ) {
      para.push(lines[i])
      i++
    }
    blocks.push(
      <p key={key++} className="my-2 text-sm leading-relaxed text-muted">
        {renderInline(para.join(' '))}
      </p>,
    )
  }

  return <div className="text-pretty">{blocks}</div>
}

/* -------------------------------------------------------------------------- */
/* Page.                                                                        */
/* -------------------------------------------------------------------------- */

export default function AnnotatePage() {
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [index, setIndex] = useState(0)
  const [lang, setLang] = useState<'en' | 'zh'>('en')
  const [annotator, setAnnotator] = useState('')
  const [labels, setLabels] = useState<Record<string, Label>>({})
  const [posting, setPosting] = useState(false)

  // Draft state for the current pair (winner + dims + note).
  const [winner, setWinner] = useState<Winner | null>(null)
  const [dims, setDims] = useState<Dim[]>([])
  const [note, setNote] = useState('')

  // Load bundle + restore persisted state on mount.
  useEffect(() => {
    fetch(PAIRS_URL)
      .then((r) => {
        if (!r.ok) throw new Error(`Failed to load pairs (${r.status})`)
        return r.json()
      })
      .then((data: Bundle) => setBundle(data))
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : 'Failed to load report pairs.'),
      )

    try {
      const rawLabels = localStorage.getItem(LS_LABELS)
      if (rawLabels) setLabels(JSON.parse(rawLabels))
      const rawIdx = localStorage.getItem(LS_PROGRESS)
      if (rawIdx) setIndex(Math.max(0, parseInt(rawIdx, 10) || 0))
      const rawAnnotator = localStorage.getItem(LS_ANNOTATOR)
      if (rawAnnotator) setAnnotator(rawAnnotator)
    } catch {
      /* localStorage unavailable: in-memory only, no crash. */
    }
  }, [])

  const pairs = bundle?.pairs ?? []
  const total = pairs.length
  const current = pairs[index]
  const currentKey = current ? pairKey(current) : ''

  // Persist labels whenever they change.
  useEffect(() => {
    try {
      localStorage.setItem(LS_LABELS, JSON.stringify(labels))
    } catch {
      /* ignore */
    }
  }, [labels])

  // Persist progress index.
  useEffect(() => {
    try {
      localStorage.setItem(LS_PROGRESS, String(index))
    } catch {
      /* ignore */
    }
  }, [index])

  // Persist annotator id.
  useEffect(() => {
    try {
      localStorage.setItem(LS_ANNOTATOR, annotator)
    } catch {
      /* ignore */
    }
  }, [annotator])

  // When the visible pair changes, hydrate the draft from any saved label.
  useEffect(() => {
    const saved = currentKey ? labels[currentKey] : undefined
    setWinner(saved?.winner ?? null)
    setDims(saved?.dims ?? [])
    setNote('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentKey])

  const labeledCount = Object.keys(labels).length

  const toggleDim = useCallback((d: Dim) => {
    setDims((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]))
  }, [])

  /* Optional, guarded POST to a future backend. Never throws to the caller.   */
  async function maybePost(label: Label & { note?: string }) {
    if (!ANNOTATE_POST_ENABLED) return
    setPosting(true)
    try {
      await fetch(ANNOTATE_POST_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(label),
      })
    } catch {
      /* Backend absent or failed: localStorage already holds the label. */
    } finally {
      setPosting(false)
    }
  }

  const save = useCallback(
    (advance: boolean) => {
      if (!current || !winner) return
      const label: Label = {
        task_id: current.task_id,
        agent_a: current.agent_a,
        agent_b: current.agent_b,
        winner,
        dims,
        annotator: annotator.trim(),
        ts: new Date().toISOString(),
      }
      setLabels((prev) => ({ ...prev, [pairKey(current)]: label }))
      void maybePost({ ...label, note: note.trim() || undefined })
      if (advance && index < total - 1) setIndex((i) => i + 1)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [current, winner, dims, note, annotator, index, total],
  )

  const go = useCallback(
    (delta: number) => {
      setIndex((i) => Math.min(total - 1, Math.max(0, i + delta)))
    },
    [total],
  )

  /* Build and download the labels as JSONL (the schema in SCHEMA.md).         */
  const exportJsonl = useCallback(() => {
    const lines = Object.values(labels).map((l) =>
      JSON.stringify({
        task_id: l.task_id,
        agent_a: l.agent_a,
        agent_b: l.agent_b,
        winner: l.winner,
        dims: l.dims,
        annotator: l.annotator,
        ts: l.ts,
      }),
    )
    const blob = new Blob([lines.join('\n') + (lines.length ? '\n' : '')], {
      type: 'application/x-ndjson',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const stamp = new Date().toISOString().slice(0, 10)
    a.download = `human_prefs_${annotator.trim() || 'anon'}_${stamp}.jsonl`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }, [labels, annotator])

  const savedForCurrent = currentKey ? labels[currentKey] : undefined
  const progressPct = total ? Math.round((labeledCount / total) * 100) : 0

  return (
    <>
      <PageHero
        eyebrow="Human Annotation"
        title="Compare two reports, record one preference."
        intro="Read both agent reports for a task, pick the stronger one (or a tie), and cite which dimensions drove the call. Verdicts become human-preference labels for judge-alignment kappa. Everything is saved in your browser; export to JSONL when you are done."
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Pairs" value={String(total || 0)} detail="report pairs in this bundle" />
          <MetricCard label="Labeled" value={String(labeledCount)} detail="verdicts recorded" />
          <MetricCard label="Progress" value={`${progressPct}%`} detail="of pairs labeled" />
          <MetricCard label="Dimensions" value={String(DIMS.length)} detail="judge dimensions to cite" />
        </div>
      </PageHero>

      <section className="container pb-16">
        {error ? (
          <div className="card flex items-start gap-3 border-bad/30 p-6">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-bad" />
            <div>
              <h2 className="font-serif text-h-sm text-ink">Could not load report pairs</h2>
              <p className="mt-1 text-sm text-muted">{error}</p>
              <p className="mt-2 text-xs text-muted">
                The bundle is generated by{' '}
                <code className="rounded bg-surface-mid px-1 py-0.5 font-mono">
                  scripts/build_annotate_pairs.py
                </code>{' '}
                into <code className="rounded bg-surface-mid px-1 py-0.5 font-mono">public/annotate-pairs.json</code>.
              </p>
            </div>
          </div>
        ) : !bundle ? (
          <div className="card flex items-center gap-3 p-6 text-sm text-muted">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading report pairs.
          </div>
        ) : total === 0 ? (
          <div className="card p-6 text-sm text-muted">
            The bundle contains no report pairs. Run{' '}
            <code className="rounded bg-surface-mid px-1 py-0.5 font-mono">
              python3 scripts/build_annotate_pairs.py
            </code>
            .
          </div>
        ) : (
          <div className="space-y-6">
            {/* Toolbar: annotator id, progress, navigation, export. */}
            <div className="card flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-1 flex-wrap items-center gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <span className="label-caps">Annotator</span>
                  <input
                    value={annotator}
                    onChange={(e) => setAnnotator(e.target.value)}
                    placeholder="your id"
                    className="h-9 w-40 rounded-tab border border-hairline bg-white px-3 text-sm text-ink outline-none focus:border-brand/50 focus:shadow-ring"
                  />
                </label>
                <div className="flex items-center gap-2 text-sm text-muted">
                  <span className="tnum font-medium text-ink">
                    {index + 1} / {total}
                  </span>
                  <span className="text-muted-2">·</span>
                  <span className="tnum">{labeledCount} labeled</span>
                </div>
                <div className="hidden h-2 w-40 overflow-hidden rounded-pill bg-surface-mid md:block">
                  <div
                    className="h-full rounded-pill bg-brand transition-all duration-300"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="secondary" size="sm" onClick={() => go(-1)} disabled={index === 0}>
                  <ChevronLeft className="h-4 w-4" /> Prev
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => go(1)}
                  disabled={index >= total - 1}
                >
                  Skip <SkipForward className="h-4 w-4" />
                </Button>
                <Button variant="secondary" size="sm" onClick={exportJsonl} disabled={labeledCount === 0}>
                  <Download className="h-4 w-4" /> Export labels (.jsonl)
                </Button>
              </div>
            </div>

            {/* Task prompt. */}
            <div className="card p-6">
              <div className="flex flex-wrap items-center gap-2">
                <span className="pill">{current.task_id}</span>
                {savedForCurrent ? (
                  <span className="pill border-good/40 text-good">
                    <Check className="h-3 w-3" /> labeled {savedForCurrent.winner.toUpperCase()}
                  </span>
                ) : null}
                {current.report_a_zh ? (
                  <div className="ml-auto inline-flex overflow-hidden rounded-md border border-hairline text-xs font-medium">
                    <button
                      type="button"
                      onClick={() => setLang('en')}
                      className={cn('px-2.5 py-1', lang === 'en' ? 'bg-ink text-white' : 'text-muted hover:text-ink')}
                    >
                      EN
                    </button>
                    <button
                      type="button"
                      onClick={() => setLang('zh')}
                      className={cn('px-2.5 py-1', lang === 'zh' ? 'bg-ink text-white' : 'text-muted hover:text-ink')}
                    >
                      中文
                    </button>
                  </div>
                ) : null}
              </div>
              <h2 className="mt-3 font-serif text-h-sm leading-tight text-ink">{lang === 'zh' && current.intent_zh ? current.intent_zh : current.intent}</h2>
              <p className="mt-2 text-sm text-muted">
                Two reports for this task are shown side by side. Reports may be truncated to keep the
                page light; judge on what is shown.
              </p>
            </div>

            {/* Reports side by side. */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ReportColumn
                side="A"
                agent={current.agent_a}
                words={current.words_a}
                report={lang === 'zh' && current.report_a_zh ? current.report_a_zh : current.report_a}
                selected={winner === 'a'}
              />
              <ReportColumn
                side="B"
                agent={current.agent_b}
                words={current.words_b}
                report={lang === 'zh' && current.report_b_zh ? current.report_b_zh : current.report_b}
                selected={winner === 'b'}
              />
            </div>

            {/* Verdict controls. */}
            <div className="card p-6">
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div>
                  <p className="label-caps">Winner</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <WinnerButton label="A wins" active={winner === 'a'} onClick={() => setWinner('a')} />
                    <WinnerButton label="Tie" active={winner === 'tie'} onClick={() => setWinner('tie')} />
                    <WinnerButton label="B wins" active={winner === 'b'} onClick={() => setWinner('b')} />
                  </div>
                </div>

                <div>
                  <p className="label-caps">Reason dimensions</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {DIMS.map((d) => (
                      <Chip
                        key={d}
                        tone="brand"
                        active={dims.includes(d)}
                        onClick={() => toggleDim(d)}
                      >
                        {d}
                      </Chip>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="label-caps">Note (optional)</p>
                  <textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={3}
                    placeholder="Short rationale, not exported to JSONL."
                    className="mt-3 w-full resize-none rounded-tab border border-hairline bg-white px-3 py-2 text-sm text-ink outline-none focus:border-brand/50 focus:shadow-ring"
                  />
                </div>
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-3 hairline-t pt-5">
                <Button onClick={() => save(true)} disabled={!winner || posting}>
                  {posting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trophy className="h-4 w-4" />}
                  Save and next
                </Button>
                <Button variant="secondary" onClick={() => save(false)} disabled={!winner || posting}>
                  Save and stay
                </Button>
                {!winner ? (
                  <span className="text-xs text-muted">Pick a winner (A, Tie, or B) to record a verdict.</span>
                ) : (
                  <span className="text-xs text-muted">
                    Saved locally; export to JSONL anytime. {ANNOTATE_POST_ENABLED ? 'Backend POST enabled.' : ''}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </section>
    </>
  )
}

function WinnerButton({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'inline-flex h-10 items-center justify-center rounded-tab border px-4 text-sm font-medium transition-all duration-150 ease-smooth',
        active
          ? 'border-ink bg-ink text-white'
          : 'border-hairline bg-white text-ink hover:border-ink/30 hover:shadow-soft',
      )}
    >
      {active ? <Check className="mr-1.5 h-4 w-4" /> : null}
      {label}
    </button>
  )
}

function ReportColumn({
  side,
  agent,
  words,
  report,
  selected,
}: {
  side: 'A' | 'B'
  agent: string
  words: number
  report: string
  selected: boolean
}) {
  return (
    <article
      className={cn(
        'card flex flex-col overflow-hidden p-0 transition-shadow duration-150',
        selected && 'shadow-hover ring-2 ring-brand/40',
      )}
    >
      <div className="flex items-center justify-between gap-2 border-b border-hairline bg-surface-low px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-ink font-mono text-xs font-semibold text-white">
            {side}
          </span>
          <span className="text-sm font-medium text-ink">{agentDisplay(agent)}</span>
        </div>
        <span className="tnum text-xs text-muted">{words.toLocaleString()} words</span>
      </div>
      <div className="max-h-[70vh] overflow-y-auto px-5 py-4">
        <Markdown source={report} />
      </div>
    </article>
  )
}
