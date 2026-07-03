import Link from 'next/link'
import { agentMeta } from '@/lib/providers'
import { groundingGatePct } from '@/lib/format'
import type { RankedAgent } from '@/lib/data/types'
import { T } from '@/components/i18n/t'

const ROW_H = 44

/**
 * "What the gate changes" — slope chart connecting each agent's raw judge-Elo
 * rank (left) to its truth-gated rank (right). All positions are computed from
 * the loaded snapshot; nothing is hardcoded.
 */
export function RankShift({ agents }: { agents: RankedAgent[] }) {
  // Left column: sorted by raw judge Elo. Right column: existing gated rank order.
  const byRaw = [...agents].sort((a, b) => b.elo - a.elo)
  const byGated = [...agents].sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0))
  const rawIndex = new Map(byRaw.map((a, i) => [a.id, i]))
  const gatedIndex = new Map(byGated.map((a, i) => [a.id, i]))
  const n = agents.length
  const height = n * ROW_H

  const lineColor = (delta: number) => (delta > 0 ? '#34A853' : delta < 0 ? '#E5484D' : '#9AA0AA')

  return (
    <div className="card overflow-hidden">
      <div className="hairline-b flex flex-wrap items-center justify-between gap-2 px-5 py-3.5">
        <p className="text-sm font-medium text-ink">
          <T en="Same agents, two orderings" zh="同一批智能体，两种排序" />
        </p>
        <div className="flex items-center gap-4 text-[11px] text-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded bg-good" />
            <T en="rises after gating" zh="门控后上升" />
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded bg-bad" />
            <T en="drops after gating" zh="门控后下降" />
          </span>
        </div>
      </div>

      {/* Desktop slope chart */}
      <div className="hidden gap-0 px-5 py-5 md:grid md:grid-cols-[1fr_150px_1fr]">
        {/* Left: raw judge rank */}
        <div>
          <p className="label-caps mb-3"><T en="Judge Elo rank (raw)" zh="裸判官 Elo 排名" /></p>
          <ol>
            {byRaw.map((a, i) => {
              const meta = agentMeta(a.id)
              const delta = i - (gatedIndex.get(a.id) ?? i)
              return (
                <li key={a.id} className="flex items-center gap-2.5 pr-2" style={{ height: ROW_H }}>
                  <span className="w-6 text-right text-xs tnum text-muted">{i + 1}</span>
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: meta.color }} />
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{meta.display}</span>
                  <span className="text-xs tnum text-muted">{Math.round(a.elo)}</span>
                  <span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: lineColor(delta) }} />
                </li>
              )
            })}
          </ol>
        </div>

        {/* Middle: connecting slopes */}
        <div className="relative" style={{ marginTop: 28 }}>
          <svg
            width="100%"
            height={height}
            viewBox={`0 0 150 ${height}`}
            preserveAspectRatio="none"
            aria-hidden
          >
            {byRaw.map((a, i) => {
              const j = gatedIndex.get(a.id) ?? i
              const delta = i - j
              const y1 = i * ROW_H + ROW_H / 2
              const y2 = j * ROW_H + ROW_H / 2
              const big = Math.abs(delta) >= 3
              return (
                <path
                  key={a.id}
                  d={`M 0 ${y1} C 60 ${y1}, 90 ${y2}, 150 ${y2}`}
                  fill="none"
                  stroke={lineColor(delta)}
                  strokeWidth={big ? 2.4 : 1.4}
                  strokeOpacity={big ? 0.85 : 0.45}
                />
              )
            })}
          </svg>
        </div>

        {/* Right: truth-gated rank */}
        <div>
          <p className="label-caps mb-3 text-right md:text-left"><T en="Truth-gated rank (public)" zh="真值门控排名（公开）" /></p>
          <ol>
            {byGated.map((a, i) => {
              const meta = agentMeta(a.id)
              const delta = (rawIndex.get(a.id) ?? i) - i
              const gate = groundingGatePct(a)
              return (
                <li key={a.id} className="flex items-center gap-2.5 pl-2" style={{ height: ROW_H }}>
                  <span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: lineColor(delta) }} />
                  <span className="w-6 text-right text-xs tnum text-muted">{i + 1}</span>
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: meta.color }} />
                  <Link href={`/agents/${a.id}`} className="min-w-0 flex-1 truncate text-sm font-medium text-ink hover:text-brand">
                    {meta.display}
                  </Link>
                  <span className="text-xs tnum text-muted">
                    {gate != null ? `${gate.toFixed(0)}%` : 'n/a'}
                  </span>
                  <span className="w-12 text-right text-sm font-semibold tnum text-ink">{(a.gated_score ?? 0).toLocaleString('en-US')}</span>
                </li>
              )
            })}
          </ol>
        </div>
      </div>

      {/* Mobile: compact movement list */}
      <ul className="md:hidden">
        {byGated.map((a, i) => {
          const meta = agentMeta(a.id)
          const raw = rawIndex.get(a.id) ?? i
          const delta = raw - i
          return (
            <li key={a.id} className="hairline-b flex items-center gap-3 px-4 py-3">
              <span className="w-6 text-center text-sm tnum text-muted">{i + 1}</span>
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: meta.color }} />
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{meta.display}</span>
              <span className="text-xs tnum text-muted">
                <T en={<>raw #{raw + 1}</>} zh={<>裸判官 #{raw + 1}</>} />
              </span>
              <span
                className={`w-10 text-right text-xs font-semibold tnum ${delta > 0 ? 'text-good' : delta < 0 ? 'text-bad' : 'text-muted'}`}
              >
                {delta > 0 ? `▲${delta}` : delta < 0 ? `▼${Math.abs(delta)}` : '—'}
              </span>
            </li>
          )
        })}
      </ul>

      <div className="bg-surface-low px-5 py-3.5 text-xs leading-relaxed text-muted">
        <T
          en="Left: how the LLM jury ranks reports on preference alone. Right: the public ranking after each agent's Elo is multiplied by its grounding gate (reachable + quote-verified citations). Thick lines mark moves of 3+ places."
          zh="左侧：LLM 陪审团仅凭偏好给出的排名。右侧:各智能体的 Elo 乘以接地门（引用可达 + 引文核实）后的公开排名。粗线表示移动 3 位及以上。"
        />
      </div>
    </div>
  )
}
