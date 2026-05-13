'use client'

import { motion } from 'motion/react'
import { agentMeta } from '@/lib/providers'
import { fmt } from '@/lib/format'
import type { RankedAgent } from '@/lib/data/types'

export interface PillarRow {
  id: string
  /** display value for the bar (already projected on the server) */
  value: number
}

interface Props {
  title: string
  subtitle: string
  /** Square color before the title */
  accentColor: string
  /** Pre-projected top-N rows (server should sort + project before passing) */
  rows: PillarRow[]
  /** Maximum rows to show */
  limit?: number
  /** Suffix for value (e.g., %, pts) */
  suffix?: string
}

export function PillarBars({ title, subtitle, accentColor, rows, limit = 5, suffix = '' }: Props) {
  const projected = rows.slice(0, limit)
  const max = Math.max(...projected.map((a) => a.value))
  const min = Math.min(...projected.map((a) => a.value))
  const range = max - min || 1
  const scale = (v: number) => 0.18 + 0.82 * ((v - min) / range)

  return (
    <section className="card p-6">
      <header className="mb-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="inline-block h-3 w-3" style={{ backgroundColor: accentColor }} />
            <h3 className="font-serif text-lg leading-tight text-ink">{title}</h3>
          </div>
          <span className="label-caps">DR Arena</span>
        </div>
        <p className="mt-1 text-xs text-muted">{subtitle}</p>
      </header>

      <ul className="hairline-t flex flex-col gap-2.5 pt-4">
        {projected.map((a, i) => {
          const meta = agentMeta(a.id)
          const w = scale(a.value) * 100
          return (
            <li key={a.id} className="flex items-center gap-3">
              <span className="w-28 truncate text-right text-xs text-muted">{meta.display}</span>
              <div className="relative h-6 flex-1 overflow-hidden rounded-r bg-surface-low">
                <motion.div
                  initial={{ width: 0 }}
                  whileInView={{ width: `${w}%` }}
                  viewport={{ once: true, margin: '-50px' }}
                  transition={{ duration: 0.8, delay: i * 0.04, ease: [0.16, 1, 0.3, 1] }}
                  className="flex h-full items-center justify-end pr-2 text-[11px] font-bold text-white"
                  style={{ backgroundColor: meta.color }}
                >
                  <span className="tnum">{fmt(a.value, 0)}{suffix}</span>
                </motion.div>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
