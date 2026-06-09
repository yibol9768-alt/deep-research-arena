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
    title: 'Truth-gated leaders',
    titleZh: '真值门控领跑者',
    ofWhich: 'composite',
    blurb: (top) => {
      const a = agentMeta(top[0].id)
      const b = agentMeta(top[1].id)
      return (
        <T
          en={
            <>
              <Inline color={a.color}>{a.display}</Inline>
              <Tnum>{top[0].gated_score ?? 0}</Tnum> and <Inline color={b.color}>{b.display}</Inline>
              <Tnum>{top[1].gated_score ?? 0}</Tnum> lead on truth-gated Elo (judge Elo × grounding gate).
            </>
          }
          zh={
            <>
              <Inline color={a.color}>{a.display}</Inline>
              <Tnum>{top[0].gated_score ?? 0}</Tnum> 与 <Inline color={b.color}>{b.display}</Inline>
              <Tnum>{top[1].gated_score ?? 0}</Tnum> 领跑真值门控 Elo（判官 Elo × 接地门）。
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
    title: 'Most grounded',
    titleZh: '最扎实的接地',
    ofWhich: 'depth',
    blurb: (top) => {
      const candidates = top.filter((a) => typeof a.reachability_pct === 'number')
      if (candidates.length === 0) {
        return (
          <span className="text-muted">
            <T en="Grounding profile not available in this build." zh="此构建版本中暂无接地数据。" />
          </span>
        )
      }
      const sorted = [...candidates].sort((a, b) => (b.reachability_pct ?? 0) - (a.reachability_pct ?? 0))
      const a = agentMeta(sorted[0].id)
      const reach = sorted[0].reachability_pct ?? 0
      return (
        <T
          en={
            <>
              <Inline color={a.color}>{a.display}</Inline> has the most real evidence:{' '}
              <Tnum>{reach.toFixed(0)}%</Tnum> of its cited URLs actually resolve in the sandbox.
            </>
          }
          zh={
            <>
              <Inline color={a.color}>{a.display}</Inline> 的证据最真实：其引用的 URL 有{' '}
              <Tnum>{reach.toFixed(0)}%</Tnum> 在沙箱中真实可达。
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
    title: 'Judge vs grounding',
    titleZh: '判官 vs 接地',
    ofWhich: 'risers',
    blurb: () => (
      <T
        en={
          <>
            A high raw judge score can still hide weak evidence. The public score keeps that visible by
            multiplying judge preference by reachable, verified citations.
          </>
        }
        zh={
          <>
            高裸判官分仍可能掩盖薄弱证据。公开主分把这一点显式保留下来：
            判官偏好必须乘以可达且可核验的引用。
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
            en={<>computed from the current judge and grounding cache</>}
            zh={<>基于当前判官与接地缓存计算</>}
          />
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {TILES.map((tile) => (
          <article
            key={tile.title}
            className="card card-lift p-5"
          >
            <header className="hairline-b pb-2 text-sm font-medium text-ink"><T en={tile.title} zh={tile.titleZh} /></header>
            <p className="mt-3 text-sm leading-relaxed text-muted">{tile.blurb(top)}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
