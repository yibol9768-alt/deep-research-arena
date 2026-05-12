import { loadLeaderboard } from '@/lib/data';
import { PageTitle, Subnav } from '@/components/page-title';
import { HighlightTiles, buildLeaderboardTiles } from '@/components/highlight-tiles';
import { FilterStrip } from '@/components/filter-strip';
import { LeaderboardTable } from '@/components/leaderboard-table';
import { ScoreCharts } from '@/components/score-charts';
import { FAQ } from '@/components/faq';
import type { ScatterAgent } from '@/components/scatter-chart';

export default function HomePage() {
  const lb = loadLeaderboard();

  const scatterAgents: ScatterAgent[] = lb.ranked.map(([name, s]) => ({
    name,
    elo: s.elo,
    elo_lo: s.elo_lo,
    elo_hi: s.elo_hi,
    ci_width: s.elo_hi - s.elo_lo,
    wins: s.wins,
    losses: s.losses,
    draws: s.draws,
    coverage: lb.pair_counts[name] || 0,
    n_tasks_target: lb.n_tasks_target,
  }));

  const tiles = lb.kpis
    ? buildLeaderboardTiles({
        nAgents: lb.n_agents,
        nTasks: lb.n_tasks,
        totalPairs: lb.kpis.total_pairs,
        uniqueUrls: lb.kpis.unique_urls,
        estTokens: lb.kpis.est_tokens,
        judgeCalls: lb.kpis.judge_calls,
      })
    : null;

  return (
    <>
      <PageTitle
        subtitle={
          <>
            Independent benchmark of open-source deep-research agents across {lb.n_tasks} cross-site research tasks. Each report
            is scored for URL grounding, judge pass-rate, and presentation, then converted to a Bradley-Terry Elo.{' '}
            <a className="text-accent hover:underline" href="/how-it-works/">See the methodology →</a>
          </>
        }
      >
        Comparison of Deep-Research Agents: Intelligence, Coverage &amp; Reliability
      </PageTitle>

      <Subnav
        items={[
          { href: '/', label: 'Intelligence Index', current: true },
          { href: '/v4/', label: 'v4 Multi-pillar', badge: 'NEW' },
          { href: '/compare/', label: 'Backbones' },
          { href: '/audit/', label: 'Audit' },
          { href: '/how-it-works/', label: 'Methodology' },
        ]}
      />

      {tiles && <HighlightTiles tiles={tiles} />}

      <FilterStrip shownAgents={lb.ranked.length} totalAgents={lb.n_agents} updatedAt={lb.leaderboard_mtime} />

      {lb.ranked.length === 0 ? (
        <div className="rounded-lg border bg-card p-5 text-sm text-destructive mb-12">
          Leaderboard data not found. Run <code className="num-mono">python scripts/build_deep_leaderboard.py</code> first.
        </div>
      ) : (
        <LeaderboardTable data={lb} />
      )}

      {scatterAgents.length >= 2 && <ScoreCharts agents={scatterAgents} />}

      {lb.sig.length > 0 && (
        <section className="mb-12">
          <h2 className="mb-1 text-[20px] font-semibold tracking-tight">Adjacent-rank significance</h2>
          <p className="mb-4 text-[13px] text-muted-foreground">Permutation test · N=1000 iterations</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {lb.sig.map((p, i) => (
              <div key={i} className="flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-[12.5px]">
                <span className="font-medium">{p.higher}</span>
                <span className="text-muted-foreground">›</span>
                <span className="font-medium">{p.lower}</span>
                <span className="ml-auto num-mono text-muted-foreground">Δ{Math.round(p.gap)}</span>
                <span className={'num-mono ' + (p.significant ? 'font-semibold text-accent' : 'text-muted-foreground')}>p={typeof p.p_value === 'number' ? p.p_value.toFixed(3) : p.p_value}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <FAQ />
    </>
  );
}
