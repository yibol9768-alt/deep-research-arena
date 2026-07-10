'use client'

import { useMemo, useState, type ReactNode } from 'react'
import { motion } from 'motion/react'
import Link from 'next/link'
import { agentMeta } from '@/lib/providers'
import { fmt, groundingGatePct, totalPairwiseBattles, truthScore } from '@/lib/format'
import type { LaneDeviation, PerPillarElo, RankedAgent } from '@/lib/data/types'
import { Swords } from 'lucide-react'
import { cn } from '@/lib/cn'
import { T } from '@/components/i18n/t'

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
  { key: 'gated', label: 'Truth-gated Elo', zh: '真值门控 Elo' },
  { key: 'judge', label: 'Judge Elo (raw)', zh: '裸判官 Elo' },
  { key: 'wins', label: 'Win count', zh: '胜场数' },
  { key: 'precision', label: 'CI precision', zh: '置信区间精度' },
] as const

type TabKey = (typeof TABS)[number]['key']

export function LeaderboardTable({ agents }: { agents: RankedAgent[] }) {
  const [tab, setTab] = useState<TabKey>('gated')
  const totalBattles = totalPairwiseBattles(agents)

  const sorted = (() => {
    const arr = [...agents]
    if (tab === 'judge') return arr.sort((a, b) => b.elo - a.elo)
    if (tab === 'wins') return arr.sort((a, b) => b.wins - a.wins)
    if (tab === 'precision') return arr.sort((a, b) => a.ci_half - b.ci_half)
    // default: truth-gated -- judge Elo scaled by the grounding gate
    return arr.sort((a, b) => (b.gated_score ?? 0) - (a.gated_score ?? 0) || b.elo - a.elo)
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
              <span className={cn('relative z-10', tab === t.key ? 'font-medium text-ink' : 'text-muted')}><T en={t.label} zh={t.zh} /></span>
            </button>
          ))}
        </div>
        <span className="hidden text-xs text-muted md:block">
          <T
            en={<>{sorted.length} rows · {fmt(totalBattles)} pairwise battles</>}
            zh={<>{sorted.length} 行 · {fmt(totalBattles)} 场两两对战</>}
          />
        </span>
      </header>

      {/* Table (mobile = card list, desktop = table) */}
      {/* Desktop */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full whitespace-nowrap text-left text-sm">
          <thead className="hairline-b bg-surface-low">
            <tr className="text-[11px] uppercase tracking-wider text-muted">
              <th className="w-12 px-4 py-3 text-center">#</th>
              <th className="px-4 py-3 font-medium"><T en="Agent / Backbone" zh="智能体 / 主干模型" /></th>
              <th className="px-4 py-3 font-medium">
                {tab === 'gated' ? (
                  <T en="Score (Elo × gate)" zh="得分(Elo × 接地门)" />
                ) : (
                  <T en="Selected metric" zh="当前指标" />
                )}
              </th>
              <th className="px-4 py-3 text-center font-medium"><T en="Judge Elo · 95% CI" zh="判官 Elo · 95% 置信区间" /></th>
              <th className="px-4 py-3 text-center font-medium"><T en="Battles" zh="对战" /></th>
              <th className="px-4 py-3 text-center font-medium"><T en="W / L / D" zh="胜 / 负 / 平" /></th>
              <th className="px-4 py-3 text-center font-medium">
                <span title="URL-grounding proxy, not a proof of fetch. R = share of a report's cited URLs that exist in the sandbox corpus (membership, NOT a fetch). Q = verbatim quote overlap vs an evaluator-fetched copy. Neither R nor Q observes whether the agent actually opened a page.">
                  <T en="URL grounding*" zh="URL 接地*" />
                </span>
              </th>
              <th className="w-10 px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((a, i) => {
              const meta = agentMeta(a.id)
              const rank = i + 1
              const gate = groundingGatePct(a)
              const metric = selectedMetric(a, tab)
              return (
                <motion.tr
                  key={a.id}
                  layout
                  layoutId={`row-${a.id}`}
                  className="hairline-b cursor-pointer transition-colors hover:bg-surface-low"
                  whileHover={{ backgroundColor: 'rgba(127,75,243,0.04)' }}
                >
                  <td className="px-4 py-3 text-center">
                    <span className={cn('tnum', rank <= 3 ? 'font-semibold text-ink' : 'text-muted')}>{rank}</span>
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
                      <DeviationBadge deviations={a.deviations} />
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-semibold text-ink tnum">{metric.value}</span>
                    <span className="ml-1.5 text-[11px] text-muted">{metric.detail}</span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="font-semibold text-ink tnum">{Math.round(a.elo)}</span>
                    <span className="ml-1 text-[11px] text-muted tnum">±{a.ci_half}</span>
                  </td>
                  <td className="px-4 py-3 text-center text-muted tnum">{a.n_battles}</td>
                  <td className="px-4 py-3 text-center tnum">
                    <span>{a.wins} / {a.losses} / {a.draws}</span>
                  </td>
                  <td className="px-4 py-3 text-center tnum">
                    {gate != null ? (
                      <span>
                        <span className={`font-semibold ${gate >= 40 ? 'text-good' : gate >= 15 ? 'text-warn' : 'text-bad'}`}>{gate.toFixed(0)}%</span>
                        <span
                          className="ml-1 text-[10px] text-muted"
                          title="R = corpus-URL membership: a cited URL parses and exists in the sandbox corpus (NOT a fetch; a guessed real URL still scores). Q = verbatim quote overlap vs an evaluator-fetched copy (a lexical lower bound, not citation support). Neither witnesses that the agent opened the page."
                        >
                          R{a.reachability_pct!.toFixed(0)} · Q{a.url_veracity_pct!.toFixed(0)}
                        </span>
                      </span>
                    ) : (
                      <span className="text-muted">n/a</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/arena?a=${a.id}`}
                      title="Compare in Arena"
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
          const gate = groundingGatePct(a)
          const metric = selectedMetric(a, tab)
          return (
            <li key={a.id} className="hairline-b px-4 py-3.5 active:bg-surface-low">
              <Link href={`/agents/${a.id}`} className="flex items-center gap-3">
                <span className={cn('w-7 text-center text-sm tnum', rank <= 3 ? 'font-semibold text-ink' : 'text-muted')}>{rank}</span>
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: meta.color }} />
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-1.5 truncate text-sm font-medium text-ink">
                    {meta.display}
                    <DeviationBadge deviations={a.deviations} />
                  </p>
                  <p className="truncate text-xs text-muted">
                    <T
                      en={<>{meta.backbone} · {a.n_battles} battles</>}
                      zh={<>{meta.backbone} · {a.n_battles} 场对战</>}
                    />
                  </p>
                </div>
                <div className="text-right">
                  <p className="tnum text-base font-semibold text-ink">{metric.value}</p>
                  <p className="tnum text-[10px] text-muted">
                    {tab === 'gated' ? <>gate {gate == null ? 'n/a' : `${gate.toFixed(0)}%`}</> : metric.detail}
                  </p>
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
 * Restrained footnote badge disclosing a lane's declared protocol deviations
 * (config/lane_protocol.yaml). Property A / gate G0: a lane that differs from the
 * shared protocol (reads pages off the recording shim, swaps a retriever,
 * truncates context) must be visible on the board, not silently folded into the
 * ranking. Hover shows the one-line disclosures. The tooltip is emitted twice —
 * once per language — and the site's CSS language toggle reveals exactly one,
 * the same mechanism <T> uses (a `title` attribute cannot itself be toggled).
 */
function DeviationBadge({ deviations }: { deviations?: LaneDeviation[] }) {
  if (!deviations || deviations.length === 0) return null
  const n = deviations.length
  const enTitle = deviations.map((d) => `• [${d.kind}] ${d.human_en}`).join('\n')
  const zhTitle = deviations.map((d) => `• [${d.kind}] ${d.human_zh}`).join('\n')
  const cls =
    'cursor-help rounded-pill border border-hairline px-1.5 py-0.5 text-[10px] leading-none text-muted transition-colors hover:border-brand hover:text-brand'
  return (
    <>
      <span data-lang="en" lang="en">
        <span
          className={cls}
          title={enTitle}
          aria-label={`${n} declared protocol deviation${n > 1 ? 's' : ''}; hover for details`}
        >
          ⚑ {n}
        </span>
      </span>
      <span data-lang="zh" lang="zh-CN">
        <span
          className={cls}
          title={zhTitle}
          aria-label={`${n} 项已声明的协议差异,悬停查看`}
        >
          差异 {n}
        </span>
      </span>
    </>
  )
}

function selectedMetric(agent: RankedAgent, tab: TabKey): { value: string; detail: ReactNode } {
  if (tab === 'judge') return { value: fmt(agent.elo), detail: <>±{agent.ci_half}</> }
  if (tab === 'wins') return { value: String(agent.wins), detail: <T en="wins" zh="胜场" /> }
  if (tab === 'precision') return { value: `±${agent.ci_half}`, detail: <T en="CI half-width" zh="置信区间半宽" /> }
  return { value: fmt(truthScore(agent)), detail: <T en={<>judge {fmt(agent.elo)}</>} zh={<>判官 {fmt(agent.elo)}</>} /> }
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
