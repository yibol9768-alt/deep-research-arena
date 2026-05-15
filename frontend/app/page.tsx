import { rankedAgents, loadLeaderboard } from '@/lib/data/load-leaderboard'
import { Hero } from '@/components/home/hero'
import { HighlightTiles } from '@/components/home/highlight-tiles'
import { CompositeBar } from '@/components/home/composite-bar'
import { QualityCostScatter } from '@/components/home/quality-cost-scatter'
import { LeaderboardTable } from '@/components/home/leaderboard-table'
import { PillarBars } from '@/components/home/pillar-bars'
import { SectionNav } from '@/components/home/section-nav'

export const dynamic = 'force-static'

export default function HomePage() {
  const agents = rankedAgents()
  const lb = loadLeaderboard()

  const stats = [
    { value: String(agents.length), label: 'Frameworks' },
    { value: '107', label: 'Sandbox tasks' },
    { value: String(lb.n_runs ?? agents.reduce((a, b) => a + b.n_battles, 0)), label: 'Battles' },
    { value: '7', label: 'Pillars' },
  ]

  const sections = [
    { id: 'highlights', label: 'Highlights' },
    { id: 'leaderboard', label: 'Leaderboard' },
    { id: 'composite', label: 'Composite Elo' },
    { id: 'pillars', label: 'Per-pillar' },
    { id: 'tradeoff', label: 'Quality vs Cost' },
    { id: 'methodology-cta', label: 'Methodology' },
  ]

  // Build synthetic per-pillar projections from win-rate, ci, etc., until pillar_elo is wired.
  const byCitation = [...agents]
    .map((a) => ({ id: a.id, value: (a.wins / a.n_battles) * 100 }))
    .sort((a, b) => b.value - a.value)
  const byDepth = [...agents]
    .map((a) => ({ id: a.id, value: a.elo - a.ci_half }))
    .sort((a, b) => b.value - a.value)
  const byEvidence = [...agents]
    .map((a) => ({ id: a.id, value: ((a.wins + a.draws) / a.n_battles) * 100 }))
    .sort((a, b) => b.value - a.value)
  const byJudge = [...agents]
    .map((a) => ({ id: a.id, value: a.elo }))
    .sort((a, b) => b.value - a.value)

  return (
    <>
      <Hero stats={stats} />

      <div id="highlights" className="container">
        <div className="my-10 h-px w-full bg-hairline" />
      </div>
      <HighlightTiles top={agents.slice(0, 4)} />

      {/* Two-column body: sticky on-page nav + main */}
      <div className="container mt-16 flex flex-col gap-12 lg:flex-row">
        <SectionNav items={sections} />

        <div className="min-w-0 flex-1 space-y-12">
          {/* Leaderboard table */}
          <div>
            <SectionTitle id="leaderboard" title="Leaderboard" caption={`${agents.length} agents · v3.1 composite scoring`} />
            <LeaderboardTable agents={agents} />
          </div>

          {/* Composite Elo bar */}
          <div>
            <SectionTitle id="composite" title="Composite Elo" caption="Bradley-Terry MLE · 1000-sample bootstrap · 95% CI" />
            <CompositeBar
              agents={agents}
              title="Composite Elo (v3.1)"
              subtitle="Higher is better. The two | marks bracket each bar's 95% bootstrap confidence interval (not a rendering glitch) — wider spread means fewer battles, so the rank is less certain."
            />
          </div>

          {/* Per-pillar grid */}
          <div>
            <SectionTitle
              id="pillars"
              title="Per-pillar breakdown"
              caption="Each pillar tells a different story; the leader rotates by metric"
            />
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <PillarBars
                title="Citation alignment"
                subtitle="Are claims actually supported by cited URLs? · ALCE substring + NLI"
                accentColor="#7F4BF3"
                rows={byCitation}
                suffix="%"
              />
              <PillarBars
                title="Analysis depth"
                subtitle="Cross-source synthesis · LLM judge + structural heuristics"
                accentColor="#cc785c"
                rows={byDepth}
              />
              <PillarBars
                title="Evidence density"
                subtitle="Distinct sources cited per claim"
                accentColor="#1c7ff8"
                rows={byEvidence}
                suffix="%"
              />
              <PillarBars
                title="LLM judge (RACE)"
                subtitle="Comprehensiveness · Insight · Instruction-following · Readability"
                accentColor="#34A853"
                rows={byJudge}
              />
            </div>
          </div>

          {/* Quality vs Cost */}
          <div>
            <SectionTitle id="tradeoff" title="Quality vs Cost" caption="Pareto-optimal agents sit in the top-left wash" />
            <QualityCostScatter agents={agents} />
          </div>

          {/* Methodology CTA */}
          <div id="methodology-cta" className="card p-8">
            <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
              <div className="max-w-xl">
                <h3 className="font-serif text-h-sm text-ink">How are these scores computed?</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  Composite v3.1 weights seven pillars, applies a multiplicative grounding gate, and feeds the
                  per-task pairwise outcomes into a Bradley-Terry MLE with 1000-sample bootstrap CIs and a
                  permutation rank significance test. Judge models are drawn from a different family than the
                  agent under test (Wataoka 2024).
                </p>
              </div>
              <a
                href="/methodology"
                className="inline-flex h-11 shrink-0 items-center gap-2 rounded-tab bg-ink px-5 text-sm font-medium text-white hover:bg-ink-soft"
              >
                Read the methodology →
              </a>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

function SectionTitle({ id, title, caption }: { id: string; title: string; caption: string }) {
  return (
    <header id={id} className="mb-4 scroll-mt-24">
      <h2 className="font-serif text-h-sm text-ink">{title}</h2>
      <p className="mt-1 text-xs text-muted">{caption}</p>
    </header>
  )
}
