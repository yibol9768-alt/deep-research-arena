'use client'

import { useState, type ReactNode } from 'react'
import { motion } from 'motion/react'
import Link from 'next/link'
import { agentMeta } from '@/lib/providers'
import type { ArenaEntry } from '@/lib/data/load-arena-v2'
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

export function ArenaTable({ entries }: { entries: ArenaEntry[] }) {
  const [tab, setTab] = useState<TabKey>('arena')

  const sorted = (() => {
    const arr = [...entries]
    if (tab === 'elo') return arr.sort((a, b) => b.bt_elo - a.bt_elo)
    if (tab === 'winrate') return arr.sort((a, b) => b.winrate - a.winrate)
    if (tab === 'reach') return arr.sort((a, b) => b.reach - a.reach || b.arena - a.arena)
    return arr.sort((a, b) => b.arena - a.arena || b.bt_elo - a.bt_elo)
  })()

  const totalBattles = entries.reduce((s, e) => s + e.n_battles, 0)

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
            en={<>{sorted.length} runs · {fmt(totalBattles)} jury battles</>}
            zh={<>{sorted.length} 条记录 · {fmt(totalBattles)} 场陪审团对战</>}
          />
        </span>
      </header>

      {/* Desktop */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full whitespace-nowrap text-left text-sm">
          <thead className="hairline-b bg-surface-low">
            <tr className="text-[11px] uppercase tracking-wider text-muted">
              <th className="w-12 px-4 py-3 text-center">#</th>
              <th className="px-4 py-3 font-medium"><T en="Harness (LLM)" zh="框架（主干模型）" /></th>
              <th className="px-4 py-3 font-medium"><T en="Arena score" zh="Arena 主分" /></th>
              <th className="px-4 py-3 text-center font-medium"><T en="Jury Elo (BT)" zh="陪审团 Elo（BT）" /></th>
              <th className="px-4 py-3 text-center font-medium"><T en="Win rate · 95% CI" zh="胜率 · 95% 置信区间" /></th>
              <th className="px-4 py-3 text-center font-medium"><T en="Battles" zh="对战" /></th>
              <th className="px-4 py-3 text-center font-medium"><T en="Grounding (reach)" zh="接地（可达）" /></th>
              <th className="px-4 py-3 text-center font-medium"><T en="Truth" zh="真值分" /></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((e, i) => {
              const meta = agentMeta(e.id)
              const rank = i + 1
              const metric = selectedMetric(e, tab)
              const reachPct = e.reach * 100
              return (
                <motion.tr
                  key={e.key}
                  layout
                  layoutId={`arena-row-${e.key}`}
                  className="hairline-b transition-colors hover:bg-surface-low"
                >
                  <td className="px-4 py-3 text-center">
                    <span className={cn('tnum', rank <= 3 ? 'font-semibold text-ink' : 'text-muted')}>{rank}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: meta.color }} />
                      <Link href={`/agents/${e.id}#run-${e.backbone}`} className="text-sm font-medium text-ink hover:text-brand">
                        {meta.display}
                      </Link>
                      <span className="rounded-pill bg-surface-mid px-2 py-0.5 text-[11px] text-muted">{backboneShort(e.backbone)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-semibold text-ink tnum">{metric.value}</span>
                    <span className="ml-1.5 text-[11px] text-muted">{metric.detail}</span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="font-semibold text-ink tnum">{Math.round(e.bt_elo)}</span>
                  </td>
                  <td className="px-4 py-3 text-center tnum">
                    <span>{(e.winrate * 100).toFixed(1)}%</span>
                    {e.winrate_ci95 ? (
                      <span className="ml-1 text-[11px] text-muted">
                        [{(e.winrate_ci95[0] * 100).toFixed(0)}–{(e.winrate_ci95[1] * 100).toFixed(0)}]
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-center text-muted tnum">{e.n_battles}</td>
                  <td className="px-4 py-3 text-center tnum">
                    <span className={`font-semibold ${reachPct >= 60 ? 'text-good' : reachPct >= 25 ? 'text-warn' : 'text-bad'}`}>
                      {reachPct.toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center text-muted tnum">{e.truth.toFixed(3)}</td>
                </motion.tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile card list */}
      <ul className="md:hidden">
        {sorted.map((e, i) => {
          const meta = agentMeta(e.id)
          const rank = i + 1
          const metric = selectedMetric(e, tab)
          return (
            <li key={e.key} className="hairline-b px-4 py-3.5 active:bg-surface-low">
              <Link href={`/agents/${e.id}#run-${e.backbone}`} className="flex items-center gap-3">
                <span className={cn('w-7 text-center text-sm tnum', rank <= 3 ? 'font-semibold text-ink' : 'text-muted')}>{rank}</span>
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: meta.color }} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{meta.display}</p>
                  <p className="truncate text-xs text-muted">
                    <T
                      en={<>{backboneShort(e.backbone)} · {e.n_battles} battles</>}
                      zh={<>{backboneShort(e.backbone)} · {e.n_battles} 场对战</>}
                    />
                  </p>
                </div>
                <div className="text-right">
                  <p className="tnum text-base font-semibold text-ink">{metric.value}</p>
                  <p className="tnum text-[10px] text-muted">{metric.detail}</p>
                </div>
              </Link>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function selectedMetric(e: ArenaEntry, tab: TabKey): { value: string; detail: ReactNode } {
  if (tab === 'elo') return { value: String(Math.round(e.bt_elo)), detail: <T en="BT Elo" zh="BT Elo" /> }
  if (tab === 'winrate') return { value: `${(e.winrate * 100).toFixed(1)}%`, detail: <T en="jury win rate" zh="陪审团胜率" /> }
  if (tab === 'reach') return { value: `${(e.reach * 100).toFixed(0)}%`, detail: <T en="citations reachable" zh="引用可达" /> }
  return {
    value: (e.arena * 100).toFixed(1),
    detail: <T en={<>reach^1.5 × win rate</>} zh={<>可达^1.5 × 胜率</>} />,
  }
}
