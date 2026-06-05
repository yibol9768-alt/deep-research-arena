import Link from 'next/link'
import { Swords } from 'lucide-react'
import { T } from '@/components/i18n/t'
import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { rankedAgents } from '@/lib/data/load-leaderboard'
import { agentMeta } from '@/lib/providers'

export const dynamic = 'force-static'

export default function ArenaPage({ searchParams }: { searchParams?: { a?: string; b?: string } }) {
  const agents = rankedAgents()
  const left = agents.find((agent) => agent.id === searchParams?.a) ?? agents[0]
  const right = agents.find((agent) => agent.id === searchParams?.b) ?? agents.find((agent) => agent.id !== left.id) ?? agents[1]
  const pair = [left, right].filter(Boolean)

  return (
    <>
      <PageHero
        eyebrow={<T en="Live Arena" zh="实时竞技场" />}
        title={<T en="Challenge two agents without hiding the uncertainty." zh="对比两个智能体，同时不掩盖不确定性。" />}
        intro={<T en="This static build renders a deterministic head-to-head snapshot from the leaderboard. The deploy-ready version preserves shareable URLs; the next interactive layer can add client-side selectors and report diffs." zh="此静态构建从排行榜渲染出一份确定性的对战快照。可部署版本保留可分享的链接，下一个交互层可加入客户端选择器和报告对比。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Candidates" zh="候选智能体" />} value={String(agents.length)} detail={<T en="agents available for pairwise views" zh="可用于两两对比的智能体" />} />
          <MetricCard label={<T en="Shared task pool" zh="共享任务池" />} value="100" detail={<T en="deep cross-site tasks" zh="深度跨站点任务" />} />
          <MetricCard label={<T en="Pillars" zh="评分维度" />} value="7" detail={<T en="margin chart dimensions" zh="胜率差距图维度" />} />
          <MetricCard label={<T en="CI" zh="置信区间" />} value="95%" detail={<T en="bootstrap interval shown for each side" zh="每一方展示的自助法区间" />} />
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
          <h2 className="font-serif text-h-sm text-ink"><T en="Pairwise margin" zh="对战胜率差距" /></h2>
          <div className="mt-6 space-y-4">
            {pair.map((agent) => {
              const meta = agentMeta(agent.id)
              return (
                <div key={agent.id}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-ink">{meta.display}</span>
                    <span className="tnum text-muted">{agent.wins}W / {agent.losses}L / {agent.draws}D</span>
                  </div>
                  <div className="mt-2 h-3 rounded-pill bg-surface-mid">
                    <div className="h-full rounded-pill" style={{ width: `${(agent.wins / Math.max(1, agent.n_battles)) * 100}%`, backgroundColor: meta.color }} />
                  </div>
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
                  <span className="tnum text-muted">{agent.elo.toFixed(0)}</span>
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
  return (
    <article className="card relative overflow-hidden p-7">
      <span className="absolute inset-x-0 top-0 h-1" style={{ backgroundColor: meta.color }} />
      <p className="label-caps"><T en={`Rank #${agent.rank}`} zh={`排名 #${agent.rank}`} /></p>
      <h2 className="mt-3 font-serif text-4xl text-ink">{meta.display}</h2>
      <p className="mt-2 text-sm text-muted">{meta.family} · {meta.backbone}</p>
      <div className="mt-8 grid grid-cols-3 gap-3">
        <MetricCard label="Elo" value={agent.elo.toFixed(0)} detail={`CI ${agent.elo_lo.toFixed(0)}-${agent.elo_hi.toFixed(0)}`} className="shadow-none" />
        <MetricCard label={<T en="Wins" zh="胜场" />} value={String(agent.wins)} detail={<T en="pairwise wins" zh="两两对战胜场" />} className="shadow-none" />
        <MetricCard label={<T en="Draws" zh="平局" />} value={String(agent.draws)} detail={<T en="ties retained" zh="保留的平局" />} className="shadow-none" />
      </div>
    </article>
  )
}
