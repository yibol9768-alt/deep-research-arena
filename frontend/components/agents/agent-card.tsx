import Link from 'next/link'
import { ArrowUpRight, Swords } from 'lucide-react'
import { agentMeta, AgentMeta } from '@/lib/providers'
import { fmt, groundingGatePct, truthScore } from '@/lib/format'
import { T } from '@/components/i18n/t'
import type { ReactNode } from 'react'
import type { RankedAgent } from '@/lib/data/types'

export function AgentCard({ agent, rank }: { agent: RankedAgent; rank: number }) {
  const meta: AgentMeta = agentMeta(agent.id)
  const winRate = agent.wins / Math.max(1, agent.n_battles)
  const gate = groundingGatePct(agent)
  const score = truthScore(agent)
  const bars = [
    { label: 'Reach', value: agent.reachability_pct, color: '#7F4BF3' },
    { label: 'Quote', value: agent.url_veracity_pct, color: '#1c7ff8' },
    { label: 'Judge', value: Math.min(100, Math.max(0, (agent.elo / 1200) * 100)), color: meta.color },
  ]

  return (
    <article className="card relative overflow-hidden p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-hover">
      {/* brand-color accent stripe */}
      <span aria-hidden className="absolute left-0 top-0 h-full w-1" style={{ backgroundColor: meta.color }} />

      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted tnum">#{rank}</span>
            <Link href={`/agents/${meta.id}`} className="text-base font-semibold text-ink hover:text-brand">
              {meta.display}
            </Link>
          </div>
          <p className="mt-0.5 text-xs text-muted">{meta.family}</p>
        </div>
        <div className="flex shrink-0 gap-1">
          <Link
            href={`/agents/${meta.id}`}
            className="inline-flex h-8 w-8 items-center justify-center rounded-tab text-muted hover:bg-surface-low hover:text-ink"
            aria-label="Detail"
          >
            <ArrowUpRight className="h-4 w-4" />
          </Link>
          <Link
            href={`/arena?a=${meta.id}`}
            className="inline-flex h-8 w-8 items-center justify-center rounded-tab text-muted hover:bg-brand/10 hover:text-brand"
            aria-label="Challenge"
          >
            <Swords className="h-4 w-4" />
          </Link>
        </div>
      </header>

      <p className="mt-1.5 inline-block rounded-pill bg-surface-mid px-2 py-0.5 text-[11px] font-medium text-muted">
        <T en="Backbone" zh="主干模型" /> · {meta.backbone}
      </p>

      <div className="mt-5 grid grid-cols-3 gap-3">
        <Stat label={<T en="Score" zh="主分" />} value={fmt(score)} accent />
        <Stat label={<T en="Grounding" zh="接地" />} value={gate == null ? 'n/a' : `${gate.toFixed(0)}%`} />
        <Stat label={<T en="Judge Elo" zh="判官 Elo" />} value={fmt(agent.elo)} />
      </div>

      <div className="mt-5 space-y-2">
        {bars.map((bar) => (
          <div key={bar.label}>
            <div className="mb-1 flex justify-between text-[10px] font-semibold uppercase tracking-wider text-muted">
              <span>{bar.label}</span>
              <span className="tnum">{bar.value == null ? 'n/a' : `${Math.round(bar.value)}%`}</span>
            </div>
            <div className="h-1.5 rounded-pill bg-surface-mid">
              <div
                className="h-full rounded-pill"
                style={{ width: `${Math.max(0, Math.min(100, bar.value ?? 0))}%`, backgroundColor: bar.color }}
              />
            </div>
          </div>
        ))}
      </div>

      <p className="mt-4 text-xs leading-relaxed text-muted">
        {meta.blurb ?? (
          <T
            en={`${agent.wins}/${agent.losses}/${agent.draws} W/L/D across ${agent.n_battles} agent-side records; win rate ${(winRate * 100).toFixed(0)}%.`}
            zh={`${agent.n_battles} 条单边记录中胜/负/平为 ${agent.wins}/${agent.losses}/${agent.draws}；胜率 ${(winRate * 100).toFixed(0)}%。`}
          />
        )}
      </p>
    </article>
  )
}

function Stat({ label, value, accent }: { label: ReactNode; value: string; accent?: boolean }) {
  return (
    <div>
      <p className="label-caps">{label}</p>
      <p className={`mt-0.5 text-lg font-semibold tnum ${accent ? 'text-ink' : 'text-muted'}`}>{value}</p>
    </div>
  )
}
