import Link from 'next/link'
import { Swords } from 'lucide-react'
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
        eyebrow="Live Arena"
        title="Challenge two agents without hiding the uncertainty."
        intro="This static build renders a deterministic head-to-head snapshot from the leaderboard. The deploy-ready version preserves shareable URLs; the next interactive layer can add client-side selectors and report diffs."
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Candidates" value={String(agents.length)} detail="agents available for pairwise views" />
          <MetricCard label="Shared task pool" value="100" detail="deep cross-site tasks" />
          <MetricCard label="Pillars" value="7" detail="margin chart dimensions" />
          <MetricCard label="CI" value="95%" detail="bootstrap interval shown for each side" />
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
          <h2 className="font-serif text-h-sm text-ink">Pairwise margin</h2>
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
          <h2 className="font-serif text-h-sm text-ink">Try another matchup</h2>
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
      <p className="label-caps">Rank #{agent.rank}</p>
      <h2 className="mt-3 font-serif text-4xl text-ink">{meta.display}</h2>
      <p className="mt-2 text-sm text-muted">{meta.family} · {meta.backbone}</p>
      <div className="mt-8 grid grid-cols-3 gap-3">
        <MetricCard label="Elo" value={agent.elo.toFixed(0)} detail={`CI ${agent.elo_lo.toFixed(0)}-${agent.elo_hi.toFixed(0)}`} className="shadow-none" />
        <MetricCard label="Wins" value={String(agent.wins)} detail="pairwise wins" className="shadow-none" />
        <MetricCard label="Draws" value={String(agent.draws)} detail="ties retained" className="shadow-none" />
      </div>
    </article>
  )
}
