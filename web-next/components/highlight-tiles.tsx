import { fmtNum, fmtCount } from '@/lib/utils';

interface Tile {
  label: string;
  value: string | number;
  meta: string;
  isMono?: boolean;
}

export function HighlightTiles({ tiles }: { tiles: Tile[] }) {
  return (
    <section className="mb-5">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Highlights</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-lg border bg-card p-3.5">
            <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{t.label}</div>
            <div className={`mt-1 text-xl font-bold leading-tight tracking-tight text-foreground ${t.isMono ? 'num-mono' : ''}`}>
              {t.value}
            </div>
            <div className="mt-0.5 text-[11.5px] text-muted-foreground">{t.meta}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function buildLeaderboardTiles(args: {
  nAgents: number;
  nTasks: number;
  totalPairs: number;
  uniqueUrls: number;
  estTokens: number;
  judgeCalls: number;
}): Tile[] {
  return [
    { label: 'Agents', value: args.nAgents, meta: 'open-source frameworks' },
    { label: 'Pairwise battles', value: fmtNum(args.totalPairs), meta: `across ${args.nTasks} tasks`, isMono: true },
    { label: 'Unique URLs cited', value: fmtNum(args.uniqueUrls), meta: 'distinct sandbox pages', isMono: true },
    { label: 'Tokens consumed', value: fmtCount(args.estTokens), meta: `${fmtNum(args.judgeCalls)} judge + agent calls`, isMono: true },
  ];
}
