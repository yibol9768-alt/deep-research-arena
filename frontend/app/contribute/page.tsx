import { PageHero, MetricCard } from '@/components/layout/metric-card'

export const dynamic = 'force-static'

const STEPS = [
  ['1', 'Implement a runner', 'Wrap your framework behind the local runner contract and point it at the search shim.'],
  ['2', 'Run a smoke task', 'Use one deep task to verify model calls, search calls, citations, and markdown output.'],
  ['3', 'Score locally', 'Run the verifier stack and inspect dropped-run reasons before submitting results.'],
  ['4', 'Open a PR', 'Include runner code, environment notes, score JSON, and a short reproducibility note.'],
]

export default function ContributePage() {
  return (
    <>
      <PageHero
        eyebrow="Contribute"
        title="Add a framework, add a task, or harden a verifier."
        intro="The benchmark is designed for external agents. Most integrations only need a runner, a model endpoint, and the existing Tavily/Firecrawl-compatible search shim."
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Runner glue" value="<50" detail="typical lines for simple adapters" />
          <MetricCard label="Task schema" value="JSON" detail="frozen prompt and source contract" />
          <MetricCard label="Smoke" value="1" detail="minimum task before matrix runs" />
          <MetricCard label="PR data" value="Score" detail="reports and verifier JSON" />
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {STEPS.map(([n, title, body]) => (
          <article key={n} className="card card-lift p-6">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-ink font-mono text-sm text-white">{n}</span>
            <h2 className="mt-5 font-serif text-h-sm text-ink">{title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{body}</p>
          </article>
        ))}
      </section>

      <section className="container mt-10 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink">Runner contract</h2>
          <pre className="mt-4 overflow-auto rounded-tab bg-surface-low p-4 text-xs leading-relaxed text-muted">
{`python scripts/run_deep_task.py \\
  --runner your_agent \\
  --task data/tasks/deep_research/cross_site_deep/dr_cross_deep_0001.json \\
  --out data/results/deep_v3`}
          </pre>
        </div>
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink">What reviewers need</h2>
          <ul className="mt-4 space-y-3 text-sm text-muted">
            <li>Exact model and provider configuration.</li>
            <li>Runner code with no hidden network dependencies beyond the shim.</li>
            <li>Raw reports, matrix score JSON, and dropped-run explanations.</li>
            <li>A note describing any framework-specific patches.</li>
          </ul>
        </div>
      </section>
    </>
  )
}
