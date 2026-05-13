import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { loadLeaderboard, rankedAgents } from '@/lib/data/load-leaderboard'
import { agentMeta } from '@/lib/providers'

export const dynamic = 'force-static'

const PILLARS = [
  ['Citation alignment', 'Claims must be backed by reachable sandbox URLs, not just polished prose.', 0.22],
  ['Evidence density', 'Reports should draw from enough distinct sources to support cross-site synthesis.', 0.16],
  ['Analysis depth', 'Judges reward synthesis, contradiction handling, and decision-useful structure.', 0.18],
  ['Checklist coverage', 'Task-specific human criteria prevent generic answers from ranking highly.', 0.16],
  ['Fact graph', 'Entity, claim, and URL triples are checked for consistency across sources.', 0.10],
  ['Markdown integrity', 'Citations must be parseable markdown links and attached to concrete claims.', 0.08],
  ['Efficiency', 'Quality is normalized against cost, latency, and dropped runs.', 0.10],
] as const

export default function PillarsPage() {
  const lb = loadLeaderboard()
  const agents = rankedAgents()
  const pillarNames = Object.keys(lb.pillar_elo ?? {})

  return (
    <>
      <PageHero
        eyebrow="Scoring Pillars"
        title="Seven verifier families decide the leaderboard, not one opaque judge score."
        intro="Composite v3.1 is intentionally plural: citation reachability, evidence breadth, checklist coverage, LLM-judge quality, formatting integrity, and efficiency all pull rank in different directions."
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Pillars" value="7" detail="weighted into composite v3.1" />
          <MetricCard label="Verifier files" value="29" detail="URL, markdown, judge, and task coverage checks" />
          <MetricCard label="Bootstrap" value="1000" detail="resamples for 95% confidence intervals" />
          <MetricCard label="Agents" value={String(agents.length)} detail="ranked under the same scoring contract" />
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-4 lg:grid-cols-7">
        <div className="card p-6 lg:col-span-3">
          <span className="label-caps">Composite formula</span>
          <p className="mt-4 font-serif text-3xl leading-tight text-ink">
            score = weighted pillars x grounding gate
          </p>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            The truth gate keeps fluent but unsupported reports from winning on style. Bradley-Terry then converts
            per-task pairwise outcomes into Elo with bootstrap confidence intervals.
          </p>
        </div>
        <div className="card p-6 lg:col-span-4">
          <span className="label-caps">Live leaders by composite</span>
          <div className="mt-5 space-y-3">
            {agents.slice(0, 5).map((agent) => {
              const meta = agentMeta(agent.id)
              return (
                <div key={agent.id}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="font-medium text-ink">{meta.display}</span>
                    <span className="tnum text-muted">{agent.elo.toFixed(1)}</span>
                  </div>
                  <div className="h-2 rounded-pill bg-surface-mid">
                    <div className="h-full rounded-pill" style={{ width: `${Math.min(100, (agent.elo / agents[0].elo) * 100)}%`, backgroundColor: meta.color }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <section className="container mt-10 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {PILLARS.map(([name, description, weight], i) => (
          <article key={name} className="card card-lift p-6">
            <div className="flex items-center justify-between gap-3">
              <span className="label-caps">Pillar {i + 1}</span>
              <span className="rounded-pill bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand">{Math.round(weight * 100)}%</span>
            </div>
            <h2 className="mt-4 font-serif text-h-sm text-ink">{name}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{description}</p>
            <div className="mt-5 h-2 rounded-pill bg-surface-mid">
              <div className="h-full rounded-pill bg-brand" style={{ width: `${weight * 100 * 3.2}%` }} />
            </div>
          </article>
        ))}
      </section>

      {pillarNames.length > 0 ? (
        <section className="container mt-10">
          <div className="card p-6">
            <span className="label-caps">Available pillar Elo tables</span>
            <div className="mt-4 flex flex-wrap gap-2">
              {pillarNames.map((name) => (
                <span key={name} className="pill capitalize">{name.replaceAll('_', ' ')}</span>
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </>
  )
}
