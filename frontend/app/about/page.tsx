import { PageHero, MetricCard } from '@/components/layout/metric-card'

export const dynamic = 'force-static'

const TIMELINE = [
  ['2026-04-15', 'Sandbox and scoring prototype'],
  ['2026-04-20', 'First framework inventory and smoke tests'],
  ['2026-04-27', 'Deep task expansion and Elo plan'],
  ['2026-05-06', 'Review pass and analysis artifacts'],
  ['2026-05-13', 'Public frontend and deployable static build'],
]

export default function AboutPage() {
  return (
    <>
      <PageHero
        eyebrow="About"
        title="A lab notebook became a benchmark because the failures were measurable."
        intro="Deep Research Arena started as a practical question: which open-source deep-research framework is reliable enough to trust? The answer required a frozen web, task-specific checklists, and evidence-level scoring."
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Frameworks" value="8+" detail="open-source agents and variants" />
          <MetricCard label="Tasks" value="100" detail="cross-site deep prompts" />
          <MetricCard label="Reports" value="200+" detail="scored runs in the current snapshot" />
          <MetricCard label="License" value="Open" detail="code, data, and methodology" />
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink">Project principle</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            The benchmark rewards reports that can be audited. It does not assume that length, confidence, or
            polished prose imply truth. Every claim should point back to a reachable sandbox source.
          </p>
        </div>
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink">Citation</h2>
          <pre className="mt-3 overflow-auto rounded-tab bg-surface-low p-4 text-xs text-muted">
{`@misc{deepresearcharena2026,
  title = {Deep Research Arena},
  year = {2026},
  note = {Reproducible Elo benchmark for Deep Research agents}
}`}
          </pre>
        </div>
      </section>

      <section className="container mt-10">
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink">Timeline</h2>
          <div className="mt-6 space-y-4">
            {TIMELINE.map(([date, event]) => (
              <div key={date} className="flex gap-4 border-l border-hairline pl-4">
                <span className="w-28 shrink-0 font-mono text-xs text-brand">{date}</span>
                <p className="text-sm text-muted">{event}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  )
}
