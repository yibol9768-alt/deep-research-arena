import Link from 'next/link'
import { ArrowUpRight } from 'lucide-react'
import { PageHero, MetricCard } from '@/components/layout/metric-card'

export const dynamic = 'force-static'

const STORIES = [
  {
    slug: 'fluent-hallucination',
    title: 'Fluent hallucination beats naive judges',
    kicker: 'F6',
    body: 'The prettiest report can still fabricate unreachable URLs. Composite v3.1 makes citation reachability a first-class ranking signal.',
  },
  {
    slug: 'dual-judge',
    title: 'Judge family changes the ordering',
    kicker: 'Dual judge',
    body: 'A same-family judge inflates familiar answer styles. The benchmark separates agent and judge families to reduce self-preference.',
  },
  {
    slug: 'adapter-quality',
    title: 'Adapter quality can beat framework reputation',
    kicker: '+162 Elo',
    body: 'DeerFlow moved sharply after shim and backend fixes, showing that integration quality is part of real-world agent performance.',
  },
  {
    slug: 'length-bias',
    title: 'Long answers are not necessarily grounded answers',
    kicker: 'RACE',
    body: 'LLM judges often reward coverage and polish. URL-level verifiers reveal when length hides unsupported claims.',
  },
  {
    slug: 'pareto-front',
    title: 'Only a few agents are cost-quality efficient',
    kicker: 'Pareto',
    body: 'The efficient frontier is small: most agents are dominated once quality, cost, and dropped runs are considered together.',
  },
]

export default function InsightsPage() {
  return (
    <>
      <PageHero
        eyebrow="Findings & Stories"
        title="The leaderboard is the table. These are the reasons behind the table."
        intro="Insights turns raw Elo movement into benchmark lessons: what failed, what improved, and which scoring choices changed conclusions."
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Findings" value={String(STORIES.length)} detail="launch stories" />
          <MetricCard label="Core risk" value="URLs" detail="fabricated or weak citations" />
          <MetricCard label="Lens" value="Elo" detail="pairwise, not average-only" />
          <MetricCard label="Output" value="Paper" detail="NeurIPS-ready narrative" />
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-4 lg:grid-cols-2">
        {STORIES.map((story, i) => (
          <article key={story.slug} className={i === 0 ? 'card p-7 lg:col-span-2' : 'card card-lift p-6'}>
            <span className="label-caps">{story.kicker}</span>
            <h2 className="mt-3 font-serif text-h-sm text-ink md:text-h-md">{story.title}</h2>
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">{story.body}</p>
            <Link href={`/methodology#${story.slug}`} className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-brand">
              Read methodology context <ArrowUpRight className="h-4 w-4" />
            </Link>
          </article>
        ))}
      </section>
    </>
  )
}
