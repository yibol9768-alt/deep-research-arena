import Link from 'next/link'
import { Swords } from 'lucide-react'
import { T } from '@/components/i18n/t'
import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { rankedAgents } from '@/lib/data/load-leaderboard'
import { agentMeta } from '@/lib/providers'
import { fmt, groundingGatePct, truthScore } from '@/lib/format'

export const dynamic = 'force-static'

export default function ArenaPage({ searchParams }: { searchParams?: { a?: string; b?: string } }) {
  const agents = rankedAgents()
  const left = agents.find((agent) => agent.id === searchParams?.a) ?? agents[0]
  const right = agents.find((agent) => agent.id === searchParams?.b) ?? agents.find((agent) => agent.id !== left.id) ?? agents[1]
  const pair = [left, right].filter(Boolean)

  return (
    <>
      <PageHero
        eyebrow={<T en="Arena" zh="竞技场" />}
        title={<T en="Compare two agents side by side." zh="并排对比两个智能体。" />}
        intro={<T en="Pick any two rows from the leaderboard and inspect the same public signals side by side: truth-gated score, raw judge Elo, grounding, and the global W/L/D record behind each estimate." zh="从榜单中任选两个条目，并排查看同一组公开信号：真值门控主分、裸判官 Elo、接地率，以及支撑每个估计的全局胜/负/平记录。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Candidates" zh="候选智能体" />} value={String(agents.length)} detail={<T en="leaderboard rows available" zh="可对比的榜单条目" />} />
          <MetricCard label={<T en="Shared task pool" zh="共享任务池" />} value="100" detail={<T en="deep cross-site tasks" zh="深度跨站点任务" />} />
          <MetricCard label={<T en="Public axes" zh="公开轴" />} value="2" detail={<T en="judge quality and grounding" zh="判官质量与接地" />} />
          <MetricCard label={<T en="CI" zh="置信区间" />} value="95%" detail={<T en="bootstrap interval on raw judge Elo" zh="裸判官 Elo 的自助法区间" />} />
        </div>
      </PageHero>

      <section className="container">
        <div className="grid grid-cols-1 items-stretch gap-4 lg:grid-cols-[1fr_auto_1fr]">
          <ArenaCard agent={pair[0]} />
          <div className="flex items-center justify-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-ink text-white shadow-hover">
              <Swords className="h-7 w-7" />
            </div>
          </div>
          <ArenaCard agent={pair[1]} />
        </div>
      </section>

      <section className="container mt-10 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card p-6 lg:col-span-2">
          <h2 className="font-serif text-h-sm text-ink"><T en="Public score breakdown" zh="公开主分拆解" /></h2>
          <div className="mt-6 space-y-4">
            {pair.map((agent) => {
              const meta = agentMeta(agent.id)
              const score = truthScore(agent)
              const top = Math.max(...pair.map((row) => truthScore(row)), 1)
              const gate = groundingGatePct(agent)
              return (
                <div key={agent.id}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-ink">{meta.display}</span>
                    <span className="tnum text-muted">{fmt(score)} score · {gate == null ? 'n/a' : `${gate.toFixed(0)}% gate`}</span>
                  </div>
                  <div className="mt-2 h-3 rounded-pill bg-surface-mid">
                    <div className="h-full rounded-pill" style={{ width: `${(score / top) * 100}%`, backgroundColor: meta.color }} />
                  </div>
                  <p className="mt-1 text-xs text-muted tnum">{agent.wins}W / {agent.losses}L / {agent.draws}D · judge {fmt(agent.elo)} ±{agent.ci_half}</p>
                </div>
              )
            })}
          </div>
        </div>
        <div className="card p-6">
          <h2 className="font-serif text-h-sm text-ink"><T en="Try another matchup" zh="换一组对战" /></h2>
          <div className="mt-4 max-h-80 space-y-2 overflow-auto pr-2">
            {agents.slice(0, 10).map((agent) => {
              const meta = agentMeta(agent.id)
              return (
                <Link key={agent.id} href={`/arena?a=${left.id}&b=${agent.id}`} className="flex items-center justify-between rounded-tab border border-hairline bg-white px-3 py-2 text-sm hover:border-brand/40">
                  <span>{meta.display}</span>
                  <span className="tnum text-muted">{fmt(truthScore(agent))}</span>
                </Link>
              )
            })}
          </div>
        </div>
      </section>
    </>
  )
}

function ArenaCard({ agent }: { agent: ReturnType<typeof rankedAgents>[number] }) {
  const meta = agentMeta(agent.id)
  const gate = groundingGatePct(agent)
  return (
    <article className="card relative overflow-hidden p-7">
      <span className="absolute inset-x-0 top-0 h-1" style={{ backgroundColor: meta.color }} />
      <p className="label-caps"><T en={`Rank #${agent.rank}`} zh={`排名 #${agent.rank}`} /></p>
      <h2 className="mt-3 font-serif text-4xl text-ink">{meta.display}</h2>
      <p className="mt-2 text-sm text-muted">{meta.family} · {meta.backbone}</p>
      <div className="mt-8 grid grid-cols-3 gap-3">
        <MetricCard label={<T en="Score" zh="主分" />} value={fmt(truthScore(agent))} detail={<T en="Elo × gate" zh="Elo × 接地门" />} className="shadow-none" />
        <MetricCard label={<T en="Grounding" zh="接地" />} value={gate == null ? 'n/a' : `${gate.toFixed(0)}%`} detail={<T en="reach + quote" zh="可达 + 引文" />} className="shadow-none" />
        <MetricCard label={<T en="Judge Elo" zh="判官 Elo" />} value={fmt(agent.elo)} detail={`CI ${agent.elo_lo.toFixed(0)}-${agent.elo_hi.toFixed(0)}`} className="shadow-none" />
      </div>
    </article>
  )
}
