'use client'

import { motion } from 'motion/react'
import { agentMeta } from '@/lib/providers'
import { fmt } from '@/lib/format'
import type { RankedAgent } from '@/lib/data/types'

export function CompositeBar({ agents, title, subtitle }: { agents: RankedAgent[]; title: string; subtitle: string }) {
  const max = agents[0]?.elo ?? 1500
  const min = Math.min(...agents.map((a) => a.elo))
  const range = max - min || 1
  const scale = (v: number) => 0.18 + 0.82 * ((v - min) / range)

  return (
    <section className="card p-6">
      <header className="mb-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 bg-brand" />
            <h3 className="font-serif text-lg leading-tight text-ink">{title}</h3>
          </div>
          <span className="label-caps">DR Arena</span>
        </div>
        <p className="mt-1 text-xs text-muted">{subtitle}</p>
      </header>

      <ul className="hairline-t flex flex-col gap-2.5 pt-4">
        {agents.map((a, i) => {
          const meta = agentMeta(a.id)
          const w = scale(a.elo) * 100
          return (
            <li key={a.id} className="flex items-center gap-3">
              <span className="w-32 truncate text-right text-xs text-muted md:w-40">{meta.display}</span>
              <div className="relative h-7 flex-1 overflow-hidden rounded-r bg-surface-low">
                <motion.div
                  initial={{ width: 0 }}
                  whileInView={{ width: `${w}%` }}
                  viewport={{ once: true, margin: '-50px' }}
                  transition={{ duration: 0.9, delay: i * 0.04, ease: [0.16, 1, 0.3, 1] }}
                  className="flex h-full items-center justify-end pr-2 text-[11px] font-bold text-white"
                  style={{ backgroundColor: meta.color }}
                >
                  <span className="tnum">{Math.round(a.elo)}</span>
                </motion.div>
                {/* CI tick */}
                <span
                  aria-hidden
                  className="absolute top-1/2 h-4 w-px -translate-y-1/2 bg-ink/40"
                  style={{ left: `${scale(a.elo - a.ci_half) * 100}%` }}
                />
                <span
                  aria-hidden
                  className="absolute top-1/2 h-4 w-px -translate-y-1/2 bg-ink/40"
                  style={{ left: `${scale(a.elo + a.ci_half) * 100}%` }}
                />
              </div>
              <span className="w-14 text-right text-[11px] text-muted tnum">±{fmt(a.ci_half)}</span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
