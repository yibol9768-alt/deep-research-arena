'use client'

import { motion } from 'motion/react'
import { agentMeta } from '@/lib/providers'
import type { RankedAgent } from '@/lib/data/types'

interface Tile {
  title: string
  blurb: (top: RankedAgent[]) => React.ReactNode
  ofWhich: 'composite' | 'wins' | 'efficiency' | 'risers'
}

const TILES: Tile[] = [
  {
    title: 'Composite Elo',
    ofWhich: 'composite',
    blurb: (top) => {
      const a = agentMeta(top[0].id)
      const b = agentMeta(top[1].id)
      return (
        <>
          <Inline color={a.color}>{a.display}</Inline>
          <Tnum>{Math.round(top[0].elo)}</Tnum> and <Inline color={b.color}>{b.display}</Inline>
          <Tnum>{Math.round(top[1].elo)}</Tnum> lead the global Bradley-Terry leaderboard.
        </>
      )
    },
  },
  {
    title: 'Most decisive wins',
    ofWhich: 'wins',
    blurb: (top) => {
      const sorted = [...top].sort((a, b) => b.wins - a.wins)
      const a = agentMeta(sorted[0].id)
      return (
        <>
          <Inline color={a.color}>{a.display}</Inline> took{' '}
          <Tnum>{sorted[0].wins}</Tnum> wins out of {sorted[0].n_battles} battles — the most decisive performer.
        </>
      )
    },
  },
  {
    title: 'Tightest confidence',
    ofWhich: 'efficiency',
    blurb: (top) => {
      const sorted = [...top].sort((a, b) => a.ci_half - b.ci_half)
      const a = agentMeta(sorted[0].id)
      return (
        <>
          <Inline color={a.color}>{a.display}</Inline> has the narrowest 95% CI{' '}
          (±<Tnum>{sorted[0].ci_half}</Tnum>) — its rank is the most stable across bootstraps.
        </>
      )
    },
  },
  {
    title: 'Reasoning models',
    ofWhich: 'risers',
    blurb: () => (
      <>
        Reasoning-tuned variants (suffix <code className="rounded bg-surface-mid px-1 py-0.5 text-[11px]">-ds</code>)
        are judged by a <em className="not-italic text-brand">different model family</em> per the
        Wataoka 2024 dual-judge protocol.
      </>
    ),
  },
]

function Inline({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span className="font-medium text-ink">
      <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle" style={{ backgroundColor: color }} />
      {children}
    </span>
  )
}

function Tnum({ children }: { children: React.ReactNode }) {
  return <span className="tnum mx-1 text-ink">({children})</span>
}

export function HighlightTiles({ top }: { top: RankedAgent[] }) {
  return (
    <section className="container">
      <div className="mb-5 flex items-end justify-between">
        <h2 className="font-serif text-h-sm text-ink">Highlights</h2>
        <span className="label-caps">computed from {top[0]?.n_battles ?? 227} dual-judge battles</span>
      </div>

      <motion.div
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: '-50px' }}
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.07 } } }}
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        {TILES.map((tile) => (
          <motion.article
            key={tile.title}
            variants={{
              hidden: { opacity: 0, y: 14 },
              show: { opacity: 1, y: 0, transition: { type: 'spring', damping: 20, stiffness: 200 } },
            }}
            className="card card-lift p-5"
          >
            <header className="hairline-b pb-2 text-sm font-medium text-ink">{tile.title}</header>
            <p className="mt-3 text-sm leading-relaxed text-muted">{tile.blurb(top)}</p>
          </motion.article>
        ))}
      </motion.div>
    </section>
  )
}
