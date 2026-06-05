'use client'

import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { agentMeta } from '@/lib/providers'
import { fmt } from '@/lib/format'
import type { RankedAgent } from '@/lib/data/types'
import { T } from '@/components/i18n/t'

/**
 * Forest plot of the RAW judge Elo: one CI whisker + center dot per agent on a
 * domain clipped to the main cluster, so the 1017-1207 spread is actually
 * readable. Non-overlapping intervals = statistically separable; that is the
 * honest way to show who really differs. Far-off outliers (e.g. an agent at
 * Elo 139) are pinned at the left edge with an off-scale marker instead of
 * being allowed to crush the axis.
 */
export function CompositeBar({ agents, title, subtitle }: { agents: RankedAgent[]; title: ReactNode; subtitle: ReactNode }) {
  // Sort by raw judge Elo: this section is the raw-judge view.
  const sorted = [...agents].sort((a, b) => b.elo - a.elo)

  // Main cluster = agents within 400 Elo of the median; outliers get pinned.
  const elos = sorted.map((a) => a.elo)
  const median = elos[Math.floor(elos.length / 2)] ?? 1000
  const main = sorted.filter((a) => Math.abs(a.elo - median) <= 400)
  const lo = Math.min(...main.map((a) => a.elo - a.ci_half)) - 15
  const hi = Math.max(...main.map((a) => a.elo + a.ci_half)) + 15
  const span = hi - lo || 1
  const x = (v: number) => Math.min(100, Math.max(0, ((v - lo) / span) * 100))

  // Axis ticks at round numbers inside the domain.
  const tickStep = span > 400 ? 100 : 50
  const ticks: number[] = []
  for (let t = Math.ceil(lo / tickStep) * tickStep; t <= hi; t += tickStep) ticks.push(t)

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

      {/* Axis */}
      <div className="relative ml-32 mr-16 hidden h-5 md:block md:ml-40">
        {ticks.map((t) => (
          <span key={t} className="absolute -translate-x-1/2 text-[10px] text-muted-2 tnum" style={{ left: `${x(t)}%` }}>
            {t}
          </span>
        ))}
      </div>

      <ul className="hairline-t flex flex-col gap-3 pt-4">
        {sorted.map((a, i) => {
          const meta = agentMeta(a.id)
          const offScale = a.elo < lo
          return (
            <li key={a.id} className="flex items-center gap-3">
              <span className="w-32 truncate text-right text-xs text-muted md:w-40">{meta.display}</span>
              <div className="relative h-7 flex-1">
                {/* gridlines */}
                {ticks.map((t) => (
                  <span key={t} aria-hidden className="absolute top-0 h-full w-px bg-hairline" style={{ left: `${x(t)}%` }} />
                ))}
                {offScale ? (
                  <span className="absolute top-1/2 -translate-y-1/2 text-[11px] text-muted">
                    ◂ <span className="tnum font-medium text-ink">{Math.round(a.elo)}</span>{' '}
                    <T en="(off scale)" zh="（超出量程）" />
                  </span>
                ) : (
                  <>
                    {/* CI whisker */}
                    <motion.span
                      initial={{ opacity: 0 }}
                      whileInView={{ opacity: 1 }}
                      viewport={{ once: true, margin: '-50px' }}
                      transition={{ duration: 0.5, delay: i * 0.05 }}
                      aria-hidden
                      className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-pill"
                      style={{
                        left: `${x(a.elo - a.ci_half)}%`,
                        width: `${Math.max(0.5, x(a.elo + a.ci_half) - x(a.elo - a.ci_half))}%`,
                        backgroundColor: `${meta.color}55`,
                      }}
                    />
                    {/* center dot */}
                    <motion.span
                      initial={{ scale: 0 }}
                      whileInView={{ scale: 1 }}
                      viewport={{ once: true, margin: '-50px' }}
                      transition={{ duration: 0.4, delay: 0.15 + i * 0.05 }}
                      className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white"
                      style={{ left: `${x(a.elo)}%`, backgroundColor: meta.color }}
                    />
                    <span
                      className="absolute top-1/2 -translate-y-1/2 text-[11px] font-semibold text-ink tnum"
                      style={{ left: `calc(${x(Math.min(a.elo + a.ci_half, hi))}% + 8px)` }}
                    >
                      {Math.round(a.elo)}
                    </span>
                  </>
                )}
              </div>
              <span className="w-14 text-right text-[11px] text-muted tnum">±{fmt(a.ci_half)}</span>
            </li>
          )
        })}
      </ul>

      <p className="mt-4 text-[11px] leading-relaxed text-muted">
        <T
          en="Whiskers are 95% bootstrap CIs on a clipped axis: non-overlapping whiskers mean the judge separates the two agents reliably. The judge draws ~50% of battles, which compresses raw Elo -- the grounding gate, not the judge, is what spreads the headline ranking."
          zh="须线为 95% 自助置信区间（坐标轴已裁剪到主簇）：须线不重叠即表示判官能可靠区分两者。判官约 50% 的对战判为平局，因此裸 Elo 本身偏紧 -- 真正拉开主榜差距的是接地门，而不是判官。"
        />
      </p>
    </section>
  )
}
