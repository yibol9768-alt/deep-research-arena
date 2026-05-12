'use client';

import { ScatterCard, ScatterAgent } from './scatter-chart';

export function ScoreCharts({ agents }: { agents: ScatterAgent[] }) {
  return (
    <section id="charts" className="mb-12">
      <h2 className="mb-1 text-[20px] font-semibold tracking-tight">Score landscape</h2>
      <p className="mb-6 text-[13px] text-muted-foreground" style={{ maxWidth: '66ch' }}>
        Elo on the X-axis across three different vertical dimensions. Top-right is better.
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3.5">
        <ScatterCard
          agents={agents}
          axis="coverage"
          title="Elo vs Coverage"
          caption={`How many of the ${agents[0]?.n_tasks_target ?? 30} tasks each agent has scored.`}
        />
        <ScatterCard
          agents={agents}
          axis="winrate"
          title="Elo vs Win rate"
          caption="Fraction of pairwise battles won (excluding draws)."
        />
        <ScatterCard
          agents={agents}
          axis="ci"
          title="Elo vs Confidence width"
          caption="Narrower CI = more certain. Lower is better."
        />
      </div>
    </section>
  );
}
