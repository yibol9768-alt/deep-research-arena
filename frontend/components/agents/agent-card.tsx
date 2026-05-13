'use client'

import { motion } from 'motion/react'
import Link from 'next/link'
import { ArrowUpRight, Swords } from 'lucide-react'
import { agentMeta, AgentMeta } from '@/lib/providers'
import { fmt } from '@/lib/format'
import type { RankedAgent } from '@/lib/data/types'

export function AgentCard({ agent, rank }: { agent: RankedAgent; rank: number }) {
  const meta: AgentMeta = agentMeta(agent.id)
  const winRate = agent.wins / Math.max(1, agent.n_battles)
  const heights = [60, 88, 70, 52, 80, 64, 92].map((v, i) => Math.max(20, v - ((i * 11) % 20)))

  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-50px' }}
      transition={{ type: 'spring', damping: 18, stiffness: 200 }}
      whileHover={{ y: -3 }}
      className="card relative overflow-hidden p-5 transition-shadow duration-200 hover:shadow-hover"
    >
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
        Backbone · {meta.backbone}
      </p>

      <div className="mt-5 grid grid-cols-3 gap-3">
        <Stat label="Composite Elo" value={fmt(agent.elo)} accent />
        <Stat label="W / L / D" value={`${agent.wins}/${agent.losses}/${agent.draws}`} />
        <Stat label="Win rate" value={`${(winRate * 100).toFixed(0)}%`} />
      </div>

      {/* Mini pillar bars */}
      <div className="mt-5 flex h-10 items-end gap-1.5">
        {heights.map((h, i) => (
          <div
            key={i}
            className="flex-1 rounded-t-sm transition-colors"
            style={{
              height: `${h}%`,
              backgroundColor: i === 3 ? meta.color : 'rgb(229,229,224)',
              opacity: i === 3 ? 0.95 : 0.85,
            }}
          />
        ))}
      </div>

      {meta.blurb && <p className="mt-4 text-xs leading-relaxed text-muted">{meta.blurb}</p>}
    </motion.article>
  )
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <p className="label-caps">{label}</p>
      <p className={`mt-0.5 text-lg font-semibold tnum ${accent ? 'text-ink' : 'text-muted'}`}>{value}</p>
    </div>
  )
}
