'use client'

import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import Link from 'next/link'
import { agentMeta } from '@/lib/providers'
import { fmt, rankMedal } from '@/lib/format'
import type { PerPillarElo, RankedAgent } from '@/lib/data/types'
import { Swords } from 'lucide-react'
import { cn } from '@/lib/cn'

/**
 * Render order for the per-pillar sparkline. Picked to read left-to-right as
 * "content quality (depth, rigor, style, coverage), task adherence (checklist,
 * spec), and grounding (reachability, quote_match)".
 */
const PILLAR_ORDER: Array<keyof PerPillarElo> = [
  'depth',
  'rigor',
  'style',
  'coverage',
  'checklist',
  'spec',
  'reachability',
  'quote_match',
]

const PILLAR_LABEL: Record<keyof PerPillarElo, string> = {
  depth: 'Depth',
  rigor: 'Rigor',
  style: 'Style',
  coverage: 'Coverage',
  checklist: 'Checklist',
  spec: 'Spec',
  reachability: 'Reachability',
  quote_match: 'Quote match',
}

const TABS = [
  { key: 'composite', label: 'Composite Elo v2' },
  { key: 'wins', label: 'Win count' },
  { key: 'precision', label: 'CI precision' },
] as const

type TabKey = (typeof TABS)[number]['key']

export function LeaderboardTable({ agents }: { agents: RankedAgent[] }) {
  const [tab, setTab] = useState<TabKey>('composite')

  const sorted = (() => {
    const arr = [...agents]
    if (tab === 'wins') return arr.sort((a, b) => b.wins - a.wins)
    if (tab === 'precision') return arr.sort((a, b) => a.ci_half - b.ci_half)
    return arr.sort((a, b) => b.elo - a.elo)
  })()

  // Compute global per-pillar bounds for sparkline scaling, so bar heights are
  // comparable across rows rather than re-normalised per-agent.
  const pillarBounds = useMemo(() => {
    const bounds: Record<string, { min: number; max: number }> = {}
    for (const dim of PILLAR_ORDER) {
      let mn = Number.POSITIVE_INFINITY
      let mx = Number.NEGATIVE_INFINITY
      for (const a of agents) {
        const v = a.per_pillar?.[dim]
        if (typeof v === 'number') {
          if (v < mn) mn = v
          if (v > mx) mx = v
        }
      }
      bounds[dim] = {
        min: Number.isFinite(mn) ? mn : 0,
        max: Number.isFinite(mx) ? mx : 1,
      }
    }
    return bounds
  }, [agents])

  return (
    <section id="leaderboard" className="card overflow-hidden">
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
                  layoutId="lb-tab"
                  transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                  className="absolute inset-0 -z-0 rounded-tab bg-surface-mid"
                />
              )}
              <span className={cn('relative z-10', tab === t.key ? 'font-medium text-ink' : 'text-muted')}>{t.label}</span>
            </button>
          ))}
        </div>
        <span className="hidden text-xs text-muted md:block">
          {sorted.length} agents · {sorted[0]?.n_battles ?? 0} battles each
        </span>
      </header>

      {/* Table (mobile = card list, desktop = table) */}
      {/* Desktop */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full whitespace-nowrap text-left text-sm">
          <thead className="hairline-b bg-surface-low">
            <tr className="text-[11px] uppercase tracking-wider text-muted">
              <th className="w-12 px-4 py-3 text-center">#</th>
              <th className="px-4 py-3 font-medium">Agent / Backbone</th>
              <th className="px-4 py-3 font-medium">Elo · 95% CI</th>
              <th className="px-4 py-3 text-center font-medium">Battles</th>
              <th className="px-4 py-3 text-center font-medium">W / L / D</th>
              <th className="px-4 py-3 font-medium">Pillars</th>
              <th className="w-10 px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((a, i) => {
              const meta = agentMeta(a.id)
              const rank = i + 1
              return (
                <motion.tr
                  key={a.id}
                  layout
                  layoutId={`row-${a.id}`}
                  className="hairline-b cursor-pointer transition-colors hover:bg-surface-low"
                  whileHover={{ backgroundColor: 'rgba(127,75,243,0.04)' }}
                >
                  <td className="px-4 py-3 text-center text-muted">
                    <span className="tnum">{rank <= 3 ? rankMedal(rank) : rank}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: meta.color }} />
                      <Link href={`/agents/${a.id}`} className="text-sm font-medium text-ink hover:text-brand">
                        {meta.display}
                      </Link>
                      {a.sig_vs_next ? (
                        <span
                          title="Gap to the next-ranked agent is statistically significant (p < 0.05)"
                          className="text-[11px] font-semibold text-brand"
                          aria-label="statistically significant"
                        >
                          *
                        </span>
                      ) : null}
                      <span className="rounded-pill bg-surface-mid px-2 py-0.5 text-[11px] text-muted">{meta.backbone}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-semibold text-ink tnum">{Math.round(a.elo)}</span>
                    <span className="ml-1 text-[11px] text-muted tnum">±{a.ci_half}</span>
                  </td>
                  <td className="px-4 py-3 text-center text-muted tnum">{a.n_battles}</td>
                  <td className="px-4 py-3 text-center text-muted tnum">
                    {a.wins} / {a.losses} / {a.draws}
                  </td>
                  <td className="px-4 py-3">
                    <PillarsSparkline color={meta.color} pillars={a.per_pillar} bounds={pillarBounds} />
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/arena?a=${a.id}`}
                      title="Challenge in Live Arena"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-tab text-muted hover:bg-brand/10 hover:text-brand"
                    >
                      <Swords className="h-4 w-4" />
                    </Link>
                  </td>
                </motion.tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile card list */}
      <ul className="md:hidden">
        {sorted.map((a, i) => {
          const meta = agentMeta(a.id)
          const rank = i + 1
          return (
            <li key={a.id} className="hairline-b px-4 py-3.5 active:bg-surface-low">
              <Link href={`/agents/${a.id}`} className="flex items-center gap-3">
                <span className="w-7 text-center text-sm tnum text-muted">{rank <= 3 ? rankMedal(rank) : rank}</span>
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: meta.color }} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{meta.display}</p>
                  <p className="truncate text-xs text-muted">
                    {meta.backbone} · {a.n_battles} battles
                  </p>
                </div>
                <div className="text-right">
                  <p className="tnum text-base font-semibold text-ink">{Math.round(a.elo)}</p>
                  <p className="tnum text-[10px] text-muted">±{a.ci_half}</p>
                </div>
              </Link>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/**
 * Per-pillar Elo sparkline. Renders one bar per dimension in PILLAR_ORDER.
 *
 * Heights are scaled within the table's global per-dimension min/max so a tall
 * bar means "best on this pillar" rather than "highest Elo across pillars" —
 * which would otherwise be dominated by quote_match.
 */
function PillarsSparkline({
  color,
  pillars,
  bounds,
}: {
  color: string
  pillars?: PerPillarElo
  bounds: Record<string, { min: number; max: number }>
}) {
  if (!pillars) {
    return <span className="text-xs text-muted-2" aria-label="per-pillar data unavailable">—</span>
  }
  return (
    <div className="flex h-5 w-28 items-end gap-0.5">
      {PILLAR_ORDER.map((dim) => {
        const v = pillars[dim]
        const b = bounds[dim] ?? { min: 0, max: 1 }
        const range = b.max - b.min || 1
        const norm = Math.max(0, Math.min(1, (v - b.min) / range))
        // Bar height: 18% floor so even worst-on-pillar is visible.
        const h = 18 + 82 * norm
        return (
          <div
            key={dim}
            className="w-2.5 rounded-t-sm"
            style={{
              height: `${h}%`,
              backgroundColor: color,
              opacity: 0.45 + 0.5 * norm,
            }}
            title={`${PILLAR_LABEL[dim]}: ${Math.round(v)}`}
          />
        )
      })}
    </div>
  )
}
