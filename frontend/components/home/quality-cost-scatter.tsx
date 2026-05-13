'use client'

import { motion } from 'motion/react'
import { agentMeta } from '@/lib/providers'
import type { RankedAgent } from '@/lib/data/types'

// Synthetic cost-per-run estimates (USD) until real data lands.
const COST: Record<string, number> = {
  'flowsearcher-ds': 0.42,
  'camel-ai': 1.85,
  smolagents: 0.18,
  ldr: 0.55,
  'gpt-researcher': 0.62,
  deerflow: 1.20,
  'langchain-odr': 0.95,
  storm: 1.45,
}

export function QualityCostScatter({ agents }: { agents: RankedAgent[] }) {
  const eloMin = Math.min(...agents.map((a) => a.elo))
  const eloMax = Math.max(...agents.map((a) => a.elo))
  const costMax = 2.0

  return (
    <section className="card p-6">
      <header className="mb-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 bg-brand-dark" />
            <h3 className="font-serif text-lg leading-tight text-ink">Quality vs Cost</h3>
          </div>
          <span className="label-caps">DR Arena</span>
        </div>
        <p className="mt-1 text-xs text-muted">Top-left quadrant indicates Pareto-optimal trade-off.</p>
      </header>

      <div className="relative ml-10 mt-6 h-[260px] border-b border-l border-hairline">
        {/* Axis labels */}
        <span className="absolute -left-8 top-1/2 -translate-y-1/2 -rotate-90 text-[10px] text-muted whitespace-nowrap">
          Composite Elo →
        </span>
        <span className="absolute -bottom-6 left-1/2 -translate-x-1/2 text-[10px] text-muted whitespace-nowrap">
          Cost per run (USD) →
        </span>
        {/* Pareto wash */}
        <div className="pareto-wash pointer-events-none absolute left-0 top-0 h-2/3 w-2/3 rounded-bl-[60%]" />

        {/* Points */}
        {agents.map((a, i) => {
          const meta = agentMeta(a.id)
          const cost = COST[a.id] ?? 0.5
          const x = Math.min(0.96, cost / costMax)
          const y = 1 - (a.elo - eloMin) / (eloMax - eloMin || 1)
          return (
            <motion.div
              key={a.id}
              initial={{ opacity: 0, scale: 0 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: 0.15 + i * 0.05, type: 'spring', damping: 18 }}
              className="group absolute -translate-x-1/2 -translate-y-1/2"
              style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
            >
              <span
                className="block h-3 w-3 rounded-full ring-4 ring-white transition-transform duration-200 group-hover:scale-150"
                style={{ backgroundColor: meta.color }}
              />
              <span
                className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 whitespace-nowrap rounded bg-white/80 px-1 py-0.5 text-[10px] font-medium text-ink opacity-0 backdrop-blur-sm transition-opacity duration-150 group-hover:opacity-100"
              >
                {meta.display} · {Math.round(a.elo)} · ${cost.toFixed(2)}
              </span>
            </motion.div>
          )
        })}
      </div>
      <p className="mt-8 text-[11px] text-muted">
        ⓘ Cost estimates are illustrative; replace with measured values from <code>meta.cost_estimate</code> when wired.
      </p>
    </section>
  )
}
