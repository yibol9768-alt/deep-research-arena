import { loadLeaderboardModels } from '@/lib/data';
import { PageTitle, Subnav } from '@/components/page-title';
import { FilterStrip } from '@/components/filter-strip';
import { LeaderboardTable } from '@/components/leaderboard-table';
import { ScoreCharts } from '@/components/score-charts';
import type { ScatterAgent } from '@/components/scatter-chart';

export const metadata = {
  title: 'Model Leaderboard — Deep-Research by Backbone LLM',
};

export default function ModelsPage() {
  const lb = loadLeaderboardModels();

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

  return (
    <>
      <PageTitle
        subtitle={
          <>
            Same minimal deep-research scaffold, varying <strong>only the backbone LLM</strong>, across {lb.n_tasks}{' '}
            cross-site research tasks. Headline is pairwise LLM-judge Bradley-Terry Elo; <strong>Reach%</strong> and{' '}
            <strong>Quote%</strong> are judge-free grounding (fraction of cited sandbox URLs that resolve, and quoted
            snippets verified against the fetched page), so a fluent model that cites unreachable sources is visible.{' '}
            <a className="text-accent hover:underline" href="/how-it-works/">See the methodology →</a>
          </>
        }
      >
        Deep-Research by Backbone LLM
      </PageTitle>

      <Subnav
        items={[
          { href: '/', label: 'Frameworks (Intelligence Index)' },
          { href: '/models/', label: 'Backbone LLMs', current: true },
          { href: '/how-it-works/', label: 'Methodology' },
        ]}
      />

      <FilterStrip shownAgents={lb.ranked.length} totalAgents={lb.n_agents} updatedAt={lb.leaderboard_mtime} />

      {lb.ranked.length === 0 ? (
        <div className="rounded-lg border bg-card p-5 text-sm text-destructive mb-12">
          Model leaderboard data not found.
        </div>
      ) : (
        <LeaderboardTable data={lb} />
      )}

      {scatterAgents.length >= 2 && <ScoreCharts agents={scatterAgents} />}
    </>
  );
}
