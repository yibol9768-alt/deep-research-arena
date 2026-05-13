import { PageHero, MetricCard } from '@/components/layout/metric-card'

export const dynamic = 'force-static'

const SYSTEMS = [
  ['Magento shopping', ':7770', 'Product pages, prices, ratings, reviews, and marketing claims for evidence-heavy recommendation tasks.'],
  ['Postmill forum', ':9999', 'Threaded community discussions with scores, comments, sub-forums, and sentiment signals.'],
  ['Kiwix Wikipedia', ':8090', 'Offline encyclopedia pages used to check definitions, timelines, and technical background.'],
  ['Search shim', ':8081', 'Tavily and Firecrawl-compatible endpoints so external frameworks can run with minimal adapter code.'],
  ['DeepSeek proxy', ':8088', 'OpenAI-compatible proxy that normalizes backend quirks for long-report generation.'],
  ['Verifier arena', 'local', 'Markdown, URL, checklist, fact graph, and judge outputs collected into pairwise battles.'],
]

export default function SandboxPage() {
  return (
    <>
      <PageHero
        eyebrow="Sandbox"
        title="A frozen mini-internet makes deep research reproducible."
        intro="Agents browse a controlled stack instead of the live web. That makes every task rerunnable, every source reachable, and every citation audit possible."
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Containers" value="3+" detail="shopping, forum, wiki, plus shims" />
          <MetricCard label="Sites" value="3" detail="cross-site evidence by design" />
          <MetricCard label="API shape" value="OpenAI" detail="compatible model backend" />
          <MetricCard label="Search" value="Tavily" detail="drop-in shim contract" />
        </div>
      </PageHero>

      <section className="container">
        <div className="card p-6">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-6">
            {SYSTEMS.map(([name, port, body], i) => (
              <article key={name} className="rounded-card border border-hairline bg-white p-5">
                <div className="flex items-center justify-between">
                  <span className="label-caps">Node {i + 1}</span>
                  <span className="font-mono text-xs text-brand">{port}</span>
                </div>
                <h2 className="mt-4 font-serif text-lg text-ink">{name}</h2>
                <p className="mt-2 text-xs leading-relaxed text-muted">{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="container mt-10 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink">Why not the live web?</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            Live pages drift, search results personalize, and citations disappear. The sandbox trades breadth for
            auditability: each agent sees the same world, and each verifier can re-open the cited evidence.
          </p>
        </div>
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink">Why keep web-shaped APIs?</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            Most deep-research frameworks already know Tavily, Firecrawl, and OpenAI-compatible chat endpoints.
            The shim lets them run against the benchmark with adapter code measured in dozens of lines.
          </p>
        </div>
      </section>
    </>
  )
}
