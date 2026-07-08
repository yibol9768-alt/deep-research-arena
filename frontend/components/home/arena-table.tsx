'use client'

import { Fragment, useState, type ReactNode } from 'react'
import { motion } from 'motion/react'
import Link from 'next/link'
import { ChevronDown } from 'lucide-react'
import { agentMeta } from '@/lib/providers'
import type { ArenaEntry, HarnessAgg } from '@/lib/data/load-arena-v2'
import { backboneShort } from '@/lib/backbones'
import { fmt } from '@/lib/format'
import { cn } from '@/lib/cn'
import { T } from '@/components/i18n/t'

const TABS = [
  { key: 'arena', label: 'Arena score', zh: 'Arena 主分' },
  { key: 'elo', label: 'Jury Elo (BT)', zh: '陪审团 Elo（BT）' },
  { key: 'winrate', label: 'Win rate', zh: '胜率' },
  { key: 'reach', label: 'Grounding (reach)', zh: '接地（可达）' },
] as const

type TabKey = (typeof TABS)[number]['key']

function metricOf(x: { arena: number; bt_elo: number; winrate: number; reach: number }, tab: TabKey): number {
  if (tab === 'elo') return x.bt_elo
  if (tab === 'winrate') return x.winrate
  if (tab === 'reach') return x.reach
  return x.arena
}

function metricLabel(x: { arena: number; bt_elo: number; winrate: number; reach: number }, tab: TabKey): string {
  if (tab === 'elo') return String(Math.round(x.bt_elo))
  if (tab === 'winrate') return `${(x.winrate * 100).toFixed(1)}%`
  if (tab === 'reach') return `${(x.reach * 100).toFixed(0)}%`
  return (x.arena * 100).toFixed(1)
}

export function ArenaTable({ harnesses }: { harnesses: HarnessAgg[] }) {
  const [tab, setTab] = useState<TabKey>('arena')
  const [open, setOpen] = useState<Record<string, boolean>>({})

  const sorted = [...harnesses].sort((a, b) => metricOf(b, tab) - metricOf(a, tab))
  const totalBattles = harnesses.reduce((s, h) => s + h.n_battles, 0)
  const nBackbones = Math.max(...harnesses.map((h) => h.runs.length))

  const toggle = (id: string) => setOpen((o) => ({ ...o, [id]: !o[id] }))

  return (
    <section className="card overflow-hidden">
      {/* Tab strip */}
      <header className="hairline-b flex items-center justify-between gap-3 px-4 py-3">
        <div className="relative flex items-center gap-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className="relative px-3 py-1.5 text-sm transition-colors"
              data-active={tab === t.key}
            >
              {tab === t.key && (
                <motion.span
                  layoutId="arena-tab"
                  transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                  className="absolute inset-0 -z-0 rounded-tab bg-surface-mid"
                />
              )}
              <span className={cn('relative z-10', tab === t.key ? 'font-medium text-ink' : 'text-muted')}>
                <T en={t.label} zh={t.zh} />
              </span>
            </button>
          ))}
        </div>
        <span className="hidden text-xs text-muted md:block">
          <T
            en={<>{sorted.length} harnesses · avg over {nBackbones} LLMs · {fmt(totalBattles)} jury battles</>}
            zh={<>{sorted.length} 个框架 · {nBackbones} 个模型取平均 · {fmt(totalBattles)} 场陪审团对战</>}
          />
        </span>
      </header>

      {/* Desktop */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full whitespace-nowrap text-left text-sm">
          <thead className="hairline-b bg-surface-low">
            <tr className="text-[11px] uppercase tracking-wider text-muted">
              <th className="w-12 px-4 py-3 text-center">#</th>
              <th className="px-4 py-3 font-medium"><T en="Harness" zh="框架" /></th>
              <th className="px-4 py-3 font-medium"><T en="Arena (avg)" zh="Arena（平均）" /></th>
              <th className="px-4 py-3 text-center font-medium"><T en="Jury Elo" zh="陪审团 Elo" /></th>
              <th className="px-4 py-3 text-center font-medium"><T en="Win rate" zh="胜率" /></th>
              <th className="px-4 py-3 text-center font-medium"><T en="Reach" zh="可达" /></th>
              <th className="px-4 py-3 text-center font-medium"><T en="Battles" zh="对战" /></th>
              <th className="px-4 py-3 text-right font-medium"><T en="Per-LLM" zh="分模型" /></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((h, i) => {
              const meta = agentMeta(h.id)
              const rank = i + 1
              const expanded = !!open[h.id]
              const reachPct = h.reach * 100
              return (
                <Fragment key={h.id}>
                  <tr
                    className="hairline-b cursor-pointer transition-colors hover:bg-surface-low"
                    onClick={() => toggle(h.id)}
                  >
                    <td className="px-4 py-3 text-center">
                      <span className={cn('tnum', rank <= 3 ? 'font-semibold text-ink' : 'text-muted')}>{rank}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: meta.color }} />
                        <Link
                          href={`/agents/${h.id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="text-sm font-medium text-ink hover:text-brand"
                        >
                          {meta.display}
                        </Link>
                        <span className="rounded-pill bg-surface-mid px-2 py-0.5 text-[11px] text-muted">
                          <T en={`${h.runs.length} LLMs`} zh={`${h.runs.length} 个模型`} />
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-semibold text-ink tnum">{(h.arena * 100).toFixed(1)}</span>
                    </td>
                    <td className="px-4 py-3 text-center tnum">{Math.round(h.bt_elo)}</td>
                    <td className="px-4 py-3 text-center tnum">{(h.winrate * 100).toFixed(1)}%</td>
                    <td className="px-4 py-3 text-center tnum">
                      <span className={`font-semibold ${reachPct >= 60 ? 'text-good' : reachPct >= 25 ? 'text-warn' : 'text-bad'}`}>
                        {reachPct.toFixed(0)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center text-muted tnum">{h.n_battles}</td>
                    <td className="px-4 py-3 text-right">
                      <span className="inline-flex items-center gap-1 text-xs text-muted">
                        {h.runs.map((r) => backboneShort(r.backbone)).join(' · ')}
                        <ChevronDown className={cn('h-4 w-4 transition-transform', expanded && 'rotate-180')} />
                      </span>
                    </td>
                  </tr>
                  {expanded &&
                    h.runs.map((r) => <RunRow key={r.key} run={r} tab={tab} />)}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile card list */}
      <ul className="md:hidden">
        {sorted.map((h, i) => {
          const meta = agentMeta(h.id)
          const rank = i + 1
          const expanded = !!open[h.id]
          return (
            <li key={h.id} className="hairline-b">
              <button onClick={() => toggle(h.id)} className="flex w-full items-center gap-3 px-4 py-3.5 text-left active:bg-surface-low">
                <span className={cn('w-7 text-center text-sm tnum', rank <= 3 ? 'font-semibold text-ink' : 'text-muted')}>{rank}</span>
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: meta.color }} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{meta.display}</p>
                  <p className="truncate text-xs text-muted">
                    <T en={`avg over ${h.runs.length} LLMs`} zh={`${h.runs.length} 个模型平均`} />
                  </p>
                </div>
                <div className="text-right">
                  <p className="tnum text-base font-semibold text-ink">{metricLabel(h, tab)}</p>
                  <p className="tnum text-[10px] text-muted"><T en="tap for per-LLM" zh="点开看分模型" /></p>
                </div>
                <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted transition-transform', expanded && 'rotate-180')} />
              </button>
              {expanded && (
                <ul className="bg-surface-low/60 pb-2">
                  {h.runs.map((r) => (
                    <li key={r.key}>
                      <Link href={`/agents/${r.id}#run-${r.backbone}`} className="flex items-center gap-3 py-2 pl-14 pr-4">
                        <span className="rounded-pill bg-surface-mid px-2 py-0.5 text-[11px] text-muted">{backboneShort(r.backbone)}</span>
                        <span className="ml-auto tnum text-sm font-medium text-ink">{metricLabel(r, tab)}</span>
                        <span className="tnum text-[11px] text-muted">{r.n_battles} <T en="battles" zh="场" /></span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function RunRow({ run, tab }: { run: ArenaEntry; tab: TabKey }) {
  const reachPct = run.reach * 100
  return (
    <tr className="hairline-b bg-surface-low/60 text-[13px]">
      <td className="px-4 py-2" />
      <td className="px-4 py-2">
        <div className="flex items-center gap-2.5 pl-5">
          <span className="rounded-pill bg-surface-mid px-2 py-0.5 text-[11px] text-muted">{backboneShort(run.backbone)}</span>
          <Link href={`/agents/${run.id}#run-${run.backbone}`} className="text-xs text-muted hover:text-brand">
            <T en="full breakdown →" zh="完整明细 →" />
          </Link>
        </div>
      </td>
      <td className="px-4 py-2">
        <span className={cn('tnum', tab === 'arena' ? 'font-semibold text-ink' : 'text-muted')}>{(run.arena * 100).toFixed(1)}</span>
      </td>
      <td className="px-4 py-2 text-center tnum text-muted">{Math.round(run.bt_elo)}</td>
      <td className="px-4 py-2 text-center tnum text-muted">
        {(run.winrate * 100).toFixed(1)}%
        {run.winrate_ci95 ? (
          <span className="ml-1 text-[11px] text-muted-2">
            [{(run.winrate_ci95[0] * 100).toFixed(0)}–{(run.winrate_ci95[1] * 100).toFixed(0)}]
          </span>
        ) : null}
      </td>
      <td className="px-4 py-2 text-center tnum">
        <span className={reachPct >= 60 ? 'text-good' : reachPct >= 25 ? 'text-warn' : 'text-bad'}>{reachPct.toFixed(0)}%</span>
      </td>
      <td className="px-4 py-2 text-center tnum text-muted">{run.n_battles}</td>
      <td className="px-4 py-2 text-right tnum text-[11px] text-muted">
        <T en={`truth ${run.truth.toFixed(3)}`} zh={`真值 ${run.truth.toFixed(3)}`} />
      </td>
    </tr>
  )
}

export type { TabKey }
