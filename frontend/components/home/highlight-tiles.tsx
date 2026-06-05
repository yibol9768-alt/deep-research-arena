'use client'

import { motion } from 'motion/react'
import { agentMeta } from '@/lib/providers'
import type { RankedAgent } from '@/lib/data/types'
import { T } from '@/components/i18n/t'

interface Tile {
  title: string
  titleZh: string
  blurb: (top: RankedAgent[]) => React.ReactNode
  ofWhich: 'composite' | 'wins' | 'efficiency' | 'depth' | 'risers'
}

const TILES: Tile[] = [
  {
    title: 'Composite Elo',
    titleZh: '综合 Elo',
    ofWhich: 'composite',
    blurb: (top) => {
      const a = agentMeta(top[0].id)
      const b = agentMeta(top[1].id)
      return (
        <T
          en={
            <>
              <Inline color={a.color}>{a.display}</Inline>
              <Tnum>{Math.round(top[0].elo)}</Tnum> and <Inline color={b.color}>{b.display}</Inline>
              <Tnum>{Math.round(top[1].elo)}</Tnum> lead the global Bradley-Terry leaderboard.
            </>
          }
          zh={
            <>
              <Inline color={a.color}>{a.display}</Inline>
              <Tnum>{Math.round(top[0].elo)}</Tnum> 与 <Inline color={b.color}>{b.display}</Inline>
              <Tnum>{Math.round(top[1].elo)}</Tnum> 领跑全局 Bradley-Terry 排行榜。
            </>
          }
        />
      )
    },
  },
  {
    title: 'Most decisive wins',
    titleZh: '最具决定性的胜场',
    ofWhich: 'wins',
    blurb: (top) => {
      const sorted = [...top].sort((a, b) => b.wins - a.wins)
      const a = agentMeta(sorted[0].id)
      return (
        <T
          en={
            <>
              <Inline color={a.color}>{a.display}</Inline> took{' '}
              <Tnum>{sorted[0].wins}</Tnum> wins out of {sorted[0].n_battles} battles — the most decisive performer.
            </>
          }
          zh={
            <>
              <Inline color={a.color}>{a.display}</Inline> 在 {sorted[0].n_battles} 场对战中赢下{' '}
              <Tnum>{sorted[0].wins}</Tnum> 场，是最具决定性的选手。
            </>
          }
        />
      )
    },
  },
  {
    title: 'Deepest reports',
    titleZh: '最深入的报告',
    ofWhich: 'depth',
    blurb: (top) => {
      // Find the top agent by depth_avg (v3 per-agent profile field).
      const candidates = top.filter((a) => typeof a.depth_avg === 'number')
      if (candidates.length === 0) {
        return (
          <span className="text-muted">
            <T en="Per-pillar depth scores not available in this build." zh="此构建版本中暂无分维度深度分数。" />
          </span>
        )
      }
      const sorted = [...candidates].sort((a, b) => (b.depth_avg ?? 0) - (a.depth_avg ?? 0))
      const a = agentMeta(sorted[0].id)
      const depth = sorted[0].depth_avg ?? 0
      return (
        <T
          en={
            <>
              <Inline color={a.color}>{a.display}</Inline> writes the deepest cross-source reports{' '}
              (depth_avg <Tnum>{depth.toFixed(2)}</Tnum>) on the v3 scoring pillars.
            </>
          }
          zh={
            <>
              <Inline color={a.color}>{a.display}</Inline> 在 v3 评分维度上写出了最深入的跨来源报告{' '}
              (depth_avg <Tnum>{depth.toFixed(2)}</Tnum>)。
            </>
          }
        />
      )
    },
  },
  {
    title: 'Tightest confidence',
    titleZh: '最窄置信区间',
    ofWhich: 'efficiency',
    blurb: (top) => {
      const sorted = [...top].sort((a, b) => a.ci_half - b.ci_half)
      const a = agentMeta(sorted[0].id)
      return (
        <T
          en={
            <>
              <Inline color={a.color}>{a.display}</Inline> has the narrowest 95% CI{' '}
              (±<Tnum>{sorted[0].ci_half}</Tnum>) — its rank is the most stable across bootstraps.
            </>
          }
          zh={
            <>
              <Inline color={a.color}>{a.display}</Inline> 拥有最窄的 95% 置信区间{' '}
              (±<Tnum>{sorted[0].ci_half}</Tnum>)，其排名在多次自助采样中最为稳定。
            </>
          }
        />
      )
    },
  },
  {
    title: 'Reasoning models',
    titleZh: '推理模型',
    ofWhich: 'risers',
    blurb: () => (
      <T
        en={
          <>
            Reasoning-tuned variants (suffix <code className="rounded bg-surface-mid px-1 py-0.5 text-[11px]">-ds</code>)
            are judged by a <em className="not-italic text-brand">different model family</em> per the
            Wataoka 2024 dual-judge protocol.
          </>
        }
        zh={
          <>
            经过推理微调的变体（后缀 <code className="rounded bg-surface-mid px-1 py-0.5 text-[11px]">-ds</code>）
            依据 Wataoka 2024 双评审协议，由<em className="not-italic text-brand">不同的模型家族</em>进行评判。
          </>
        }
      />
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
        <h2 className="font-serif text-h-sm text-ink"><T en="Highlights" zh="亮点" /></h2>
        <span className="label-caps">
          <T
            en={<>computed from {top[0]?.n_battles ?? 227} dual-judge battles</>}
            zh={<>基于 {top[0]?.n_battles ?? 227} 场双评审对战计算</>}
          />
        </span>
      </div>

      <motion.div
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: '-50px' }}
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.07 } } }}
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
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
            <header className="hairline-b pb-2 text-sm font-medium text-ink"><T en={tile.title} zh={tile.titleZh} /></header>
            <p className="mt-3 text-sm leading-relaxed text-muted">{tile.blurb(top)}</p>
          </motion.article>
        ))}
      </motion.div>
    </section>
  )
}
