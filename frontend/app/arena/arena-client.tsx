'use client'

import { Suspense, useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Swords } from 'lucide-react'
import { T } from '@/components/i18n/t'
import { MetricCard } from '@/components/layout/metric-card'
import { agentMeta } from '@/lib/providers'
import { backboneShort } from '@/lib/backbones'
import type { ArenaEntry } from '@/lib/data/load-arena-v2'

export function ArenaClient({ entries }: { entries: ArenaEntry[] }) {
  return (
    <Suspense fallback={null}>
      <ArenaInner entries={entries} />
    </Suspense>
  )
}

function ArenaInner({ entries }: { entries: ArenaEntry[] }) {
  const params = useSearchParams()
  const initialA = useMemo(() => {
    const want = params.get('a')
    return entries.find((e) => e.id === want)?.key ?? entries[0]?.key
  }, [params, entries])
  const initialB = useMemo(() => {
    const want = params.get('b')
    const found = entries.find((e) => e.id === want && e.key !== initialA)
    return found?.key ?? entries.find((e) => e.key !== initialA)?.key
  }, [params, entries, initialA])

  const [aKey, setAKey] = useState<string | undefined>(undefined)
  const [bKey, setBKey] = useState<string | undefined>(undefined)
  const a = entries.find((e) => e.key === (aKey ?? initialA)) ?? entries[0]
  const b = entries.find((e) => e.key === (bKey ?? initialB)) ?? entries[1]
  if (!a || !b) return null

  return (
    <>
      <section className="container">
        <div className="grid grid-cols-1 items-stretch gap-4 lg:grid-cols-[1fr_auto_1fr]">
          <RunCard run={a} value={a.key} onChange={setAKey} entries={entries} />
          <div className="flex items-center justify-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-ink text-white shadow-hover">
              <Swords className="h-7 w-7" />
            </div>
          </div>
          <RunCard run={b} value={b.key} onChange={setBKey} entries={entries} />
        </div>
      </section>

      <section className="container mt-10">
        <div className="card p-6">
          <h2 className="font-serif text-h-sm text-ink"><T en="Head-to-head breakdown" zh="逐项对比" /></h2>
          <div className="mt-6 space-y-5">
            <CompareRow label={<T en="Arena score" zh="Arena 主分" />} a={a} b={b} value={(e) => e.arena * 100} format={(v) => v.toFixed(1)} />
            <CompareRow label={<T en="Jury Elo (BT)" zh="陪审团 Elo（BT）" />} a={a} b={b} value={(e) => e.bt_elo} format={(v) => String(Math.round(v))} />
            <CompareRow label={<T en="Win rate" zh="胜率" />} a={a} b={b} value={(e) => e.winrate * 100} format={(v) => `${v.toFixed(1)}%`} />
            <CompareRow label={<T en="Grounding (reach)" zh="接地（可达）" />} a={a} b={b} value={(e) => e.reach * 100} format={(v) => `${v.toFixed(0)}%`} />
            <CompareRow label={<T en="Truth score" zh="真值分" />} a={a} b={b} value={(e) => e.truth * 100} format={(v) => (v / 100).toFixed(3)} />
          </div>
          <p className="mt-6 text-xs text-muted">
            <T
              en="Bars are normalised to the better side of each metric. Win-rate CIs and battle counts live on each run's detail page."
              zh="每项条形以较优一方为基准归一化。胜率置信区间与对战数见各 run 的明细页。"
            />
          </p>
        </div>
      </section>
    </>
  )
}

function RunCard({
  run,
  value,
  onChange,
  entries,
}: {
  run: ArenaEntry
  value: string
  onChange: (key: string) => void
  entries: ArenaEntry[]
}) {
  const meta = agentMeta(run.id)
  return (
    <article className="card relative overflow-hidden p-7">
      <span className="absolute inset-x-0 top-0 h-1" style={{ backgroundColor: meta.color }} />
      <select
        aria-label="Pick a run"
        className="w-full rounded-tab border border-hairline bg-white px-3 py-2 text-sm text-ink"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {entries.map((e) => (
          <option key={e.key} value={e.key}>
            {agentMeta(e.id).display} · {backboneShort(e.backbone)}
          </option>
        ))}
      </select>
      <h2 className="mt-5 font-serif text-3xl text-ink">{meta.display}</h2>
      <p className="mt-1 text-sm text-muted">
        {meta.family} · {backboneShort(run.backbone)}
      </p>
      <div className="mt-6 grid grid-cols-3 gap-3">
        <MetricCard label={<T en="Arena" zh="Arena" />} value={(run.arena * 100).toFixed(1)} detail={<T en="reach^1.5 × win rate" zh="可达^1.5 × 胜率" />} className="shadow-none" />
        <MetricCard label={<T en="Reach" zh="可达" />} value={`${(run.reach * 100).toFixed(0)}%`} detail={<T en="judge-free" zh="不依赖裁判" />} className="shadow-none" />
        <MetricCard label={<T en="Jury Elo" zh="陪审团 Elo" />} value={String(Math.round(run.bt_elo))} detail={`${run.n_battles} battles`} className="shadow-none" />
      </div>
      <Link href={`/agents/${run.id}#run-${run.backbone}`} className="mt-5 inline-block text-sm text-brand hover:underline">
        <T en="Full breakdown →" zh="完整明细 →" />
      </Link>
    </article>
  )
}

function CompareRow({
  label,
  a,
  b,
  value,
  format,
}: {
  label: ReactNode
  a: ArenaEntry
  b: ArenaEntry
  value: (e: ArenaEntry) => number
  format: (v: number) => string
}) {
  const va = value(a)
  const vb = value(b)
  const top = Math.max(va, vb, 0.0001)
  const metaA = agentMeta(a.id)
  const metaB = agentMeta(b.id)
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted">{label}</p>
      {[
        { v: va, meta: metaA, run: a },
        { v: vb, meta: metaB, run: b },
      ].map(({ v, meta, run }) => (
        <div key={run.key} className="mb-1.5 flex items-center gap-3">
          <span className="w-44 shrink-0 truncate text-xs text-muted">
            {meta.display} · {backboneShort(run.backbone)}
          </span>
          <div className="h-3 flex-1 rounded-pill bg-surface-mid">
            <div className="h-full rounded-pill" style={{ width: `${(v / top) * 100}%`, backgroundColor: meta.color }} />
          </div>
          <span className="w-16 shrink-0 text-right text-sm font-medium tnum text-ink">{format(v)}</span>
        </div>
      ))}
    </div>
  )
}
