import Link from 'next/link'
import { ArrowUpRight, Swords } from 'lucide-react'
import { agentMeta, AgentMeta } from '@/lib/providers'
import { backboneShort } from '@/lib/backbones'
import { T } from '@/components/i18n/t'
import type { ReactNode } from 'react'
import type { HarnessAgg } from '@/lib/data/load-arena-v2'

export function AgentCard({ harness, rank }: { harness: HarnessAgg; rank: number }) {
  const meta: AgentMeta = agentMeta(harness.id)
  const topArena = Math.max(...harness.runs.map((r) => r.arena), 0.0001)

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

      <div className="mt-4 grid grid-cols-3 gap-3">
        <Stat label={<T en="Arena (avg)" zh="Arena 平均" />} value={(harness.arena * 100).toFixed(1)} accent />
        <Stat label={<T en="Reach" zh="可达" />} value={`${(harness.reach * 100).toFixed(0)}%`} />
        <Stat label={<T en="Jury Elo" zh="陪审团 Elo" />} value={String(Math.round(harness.bt_elo))} />
      </div>

      {/* One row per backbone LLM */}
      <div className="mt-5 space-y-2">
        {harness.runs.map((r) => (
          <Link key={r.key} href={`/agents/${harness.id}#run-${r.backbone}`} className="block">
            <div className="mb-1 flex justify-between text-[10px] font-semibold uppercase tracking-wider text-muted">
              <span>{backboneShort(r.backbone)}</span>
              <span className="tnum">{(r.arena * 100).toFixed(1)}</span>
            </div>
            <div className="h-1.5 rounded-pill bg-surface-mid">
              <div
                className="h-full rounded-pill"
                style={{ width: `${(r.arena / topArena) * 100}%`, backgroundColor: meta.color }}
              />
            </div>
          </Link>
        ))}
      </div>

      <p className="mt-4 text-xs leading-relaxed text-muted">
        {meta.blurb ?? (
          <T
            en={`${harness.n_battles} jury battles across ${harness.runs.length} backbone LLMs.`}
            zh={`${harness.runs.length} 个主干模型上共 ${harness.n_battles} 场陪审团对战。`}
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
