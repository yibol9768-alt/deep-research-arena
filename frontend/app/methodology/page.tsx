import { PageHero, MetricCard } from '@/components/layout/metric-card'

export const dynamic = 'force-static'

const SECTIONS = [
  ['composite', 'Composite v3.1', 'Seven pillars are weighted into a single task score, then passed through a grounding gate so unsupported reports cannot win on fluency alone.'],
  ['grounding-gate', 'Grounding gate', 'Reachable, markdown-linked sandbox URLs are treated as evidence. Missing or fabricated citations reduce the effective score multiplicatively.'],
  ['bradley-terry', 'Bradley-Terry Elo', 'Per-task outcomes become pairwise battles. MLE estimates agent strength, and bootstrap resampling gives 95% confidence intervals.'],
  ['dual-judge', 'Dual judge design', 'The judging model family is separated from the tested agent family to reduce style preference and self-similarity bias.'],
  ['intent-typology', 'Intent typology', 'Tasks span recommendation, comparison, debunking, causal explanation, timeline, and enumeration. Each intent has task-specific checklists.'],
  ['ablation', 'Ablation protocol', 'Dropping pillars reveals sensitivity. Truth and citation gates are the highest-impact controls against fluent hallucination.'],
]

export default function MethodologyPage() {
  return (
    <>
      <PageHero
        eyebrow="Methodology"
        title="A reproducible scoring stack for reports that cite, synthesize, and survive audit."
        intro="Deep Research Arena avoids a single magic score. It stores the task, source pool, checklist, report, verifier outputs, pairwise outcome, and confidence interval as separate artifacts."
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Score pillars" value="7" detail="truth, evidence, structure, cost" />
          <MetricCard label="Bootstrap" value="1000" detail="confidence interval resamples" />
          <MetricCard label="Intent classes" value="6" detail="task families with separate failure modes" />
          <MetricCard label="Audit trail" value="Full" detail="JSON, reports, and verifier outputs" />
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-8 lg:grid-cols-[280px_1fr]">
        <aside className="hidden lg:block">
          <nav className="sticky top-24 rounded-card border border-hairline bg-white p-3 shadow-soft">
            {SECTIONS.map(([id, title]) => (
              <a key={id} href={`#${id}`} className="block rounded-tab px-3 py-2 text-sm text-muted hover:bg-surface-low hover:text-ink">
                {title}
              </a>
            ))}
          </nav>
        </aside>
        <div className="space-y-5">
          {SECTIONS.map(([id, title, body], i) => (
            <article key={id} id={id} className="card scroll-mt-24 p-7">
              <span className="label-caps">Step {i + 1}</span>
              <h2 className="mt-3 font-serif text-h-sm text-ink md:text-h-md">{title}</h2>
              <p className="mt-3 text-sm leading-relaxed text-muted">{body}</p>
              <div className="mt-6 rounded-tab bg-surface-low p-4 font-mono text-xs leading-relaxed text-muted">
                {'report -> verifiers -> per-task battle -> Bradley-Terry MLE -> bootstrap CI -> leaderboard'}
              </div>
            </article>
          ))}
        </div>
      </section>
    </>
  )
}
