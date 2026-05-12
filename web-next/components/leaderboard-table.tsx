'use client';

import * as React from 'react';
import { ChevronDown, ChevronUp, ArrowUpDown } from 'lucide-react';
import { agentColor } from '@/lib/agent-color';
import { cn, fmtNum } from '@/lib/utils';
import type { LeaderboardData, AgentDrillData } from '@/lib/types';

type SortKey = 'rank' | 'name' | 'elo' | 'coverage' | 'wins' | 'losses' | 'draws';

interface Row {
  rank: number;
  agent: string;
  elo: number;
  eloLo: number;
  eloHi: number;
  eloHalf: number;
  wins: number;
  losses: number;
  draws: number;
  coverage: number;
  tiedAbove: boolean;
}

export function LeaderboardTable({ data }: { data: LeaderboardData }) {
  const baseRows: Row[] = React.useMemo(() => {
    return data.ranked.map(([agent, s], i, arr) => {
      let tied = false;
      if (i > 0) {
        const prev = arr[i - 1][0];
        const key = `${prev}__${agent}`;
        if (data.sig_lookup[key] === false) tied = true;
      }
      return {
        rank: i + 1,
        agent,
        elo: s.elo,
        eloLo: s.elo_lo,
        eloHi: s.elo_hi,
        eloHalf: s.elo_half_width,
        wins: s.wins,
        losses: s.losses,
        draws: s.draws,
        coverage: data.pair_counts[agent] || 0,
        tiedAbove: tied,
      };
    });
  }, [data]);

  const [sortKey, setSortKey] = React.useState<SortKey>('elo');
  const [sortDir, setSortDir] = React.useState<'asc' | 'desc'>('desc');
  const [openAgents, setOpenAgents] = React.useState<Set<string>>(new Set());
  const [drillData, setDrillData] = React.useState<Record<string, AgentDrillData | null>>({});

  const rows = React.useMemo(() => {
    const arr = [...baseRows];
    arr.sort((a, b) => {
      const dir = sortDir === 'asc' ? 1 : -1;
      switch (sortKey) {
        case 'name':
          return a.agent.localeCompare(b.agent) * dir;
        case 'rank':
          return (a.rank - b.rank) * dir;
        case 'elo':
          return (a.elo - b.elo) * dir;
        case 'coverage':
          return (a.coverage - b.coverage) * dir;
        case 'wins':
          return (a.wins - b.wins) * dir;
        case 'losses':
          return (a.losses - b.losses) * dir;
        case 'draws':
          return (a.draws - b.draws) * dir;
      }
    });
    return arr;
  }, [baseRows, sortKey, sortDir]);

  function clickSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'name' || key === 'rank' || key === 'losses' || key === 'draws' ? 'asc' : 'desc');
    }
  }

  async function toggle(agent: string) {
    const next = new Set(openAgents);
    if (next.has(agent)) {
      next.delete(agent);
      setOpenAgents(next);
      return;
    }
    next.add(agent);
    setOpenAgents(next);
    if (drillData[agent] !== undefined) return;
    try {
      const r = await fetch(`/api/agent/${encodeURIComponent(agent)}.json`);
      if (!r.ok) throw new Error(`${r.status}`);
      const d = (await r.json()) as AgentDrillData;
      setDrillData((s) => ({ ...s, [agent]: d }));
    } catch {
      setDrillData((s) => ({ ...s, [agent]: null }));
    }
  }

  return (
    <section className="mb-12">
      <div className="overflow-hidden rounded-lg border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-[13.5px]">
            <colgroup>
              <col style={{ width: 48 }} />
              <col style={{ minWidth: 200 }} />
              <col style={{ width: 86 }} />
              <col style={{ width: 240 }} className="hidden lg:table-column" />
              <col style={{ width: 140 }} />
              <col style={{ width: 56 }} className="hidden md:table-column" />
              <col style={{ width: 56 }} className="hidden md:table-column" />
              <col style={{ width: 56 }} className="hidden md:table-column" />
            </colgroup>
            <thead className="sticky top-12 bg-secondary/60 backdrop-blur supports-[backdrop-filter]:bg-secondary/60">
              <tr className="border-b">
                <Th k="rank" cur={sortKey} dir={sortDir} onClick={clickSort}>#</Th>
                <Th k="name" cur={sortKey} dir={sortDir} onClick={clickSort}>Agent</Th>
                <Th k="elo" cur={sortKey} dir={sortDir} onClick={clickSort} align="right">Elo</Th>
                <th className="hidden lg:table-cell h-9 px-3 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">95% confidence interval</th>
                <Th k="coverage" cur={sortKey} dir={sortDir} onClick={clickSort} align="right">Coverage</Th>
                <Th k="wins" cur={sortKey} dir={sortDir} onClick={clickSort} align="right" hideMobile>W</Th>
                <Th k="losses" cur={sortKey} dir={sortDir} onClick={clickSort} align="right" hideMobile>L</Th>
                <Th k="draws" cur={sortKey} dir={sortDir} onClick={clickSort} align="right" hideMobile>D</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const open = openAgents.has(r.agent);
                const color = agentColor(r.agent);
                const eloSpan = Math.max(1, data.elo_span);
                const markerPct = ((r.elo - data.elo_min) / eloSpan) * 100;
                const loPct = ((r.eloLo - data.elo_min) / eloSpan) * 100;
                const hiPct = ((r.eloHi - data.elo_min) / eloSpan) * 100;
                const covPct = data.n_tasks_target ? (r.coverage / data.n_tasks_target) * 100 : 0;
                const covPartial = r.coverage < 30;
                return (
                  <React.Fragment key={r.agent}>
                    <tr
                      className={cn(
                        'cursor-pointer border-b border-border/40 transition-colors hover:bg-secondary/40',
                        open && 'bg-secondary/40'
                      )}
                      onClick={() => toggle(r.agent)}
                    >
                      <td className="px-3.5 py-2.5 align-middle">
                        <RankCell rank={r.rank} tied={r.tiedAbove} />
                      </td>
                      <td className="py-2.5 px-3 align-middle">
                        <span className="flex items-center gap-2 overflow-hidden">
                          <span
                            className="inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-[9px] font-bold text-white"
                            style={{ backgroundColor: color }}
                          >
                            {r.agent.slice(0, 2).toUpperCase()}
                          </span>
                          <span className="truncate font-medium text-foreground">{r.agent}</span>
                          <ChevronDown
                            className={cn('h-3 w-3 flex-shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')}
                          />
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right align-middle">
                        <span className="num-mono font-semibold text-[14.5px]">{Math.round(r.elo)}</span>
                      </td>
                      <td className="hidden lg:table-cell px-3 py-2 align-middle">
                        <CIBar markerPct={markerPct} loPct={loPct} hiPct={hiPct} />
                        <div className="mt-1 whitespace-nowrap text-[10.5px] num-mono text-muted-foreground">
                          [{Math.round(r.eloLo)}, {Math.round(r.eloHi)}] ±{Math.round(r.eloHalf)}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right align-middle">
                        <CoverageCell cov={r.coverage} target={data.n_tasks_target} pct={covPct} partial={covPartial} />
                      </td>
                      <td className="hidden md:table-cell px-3 py-2.5 text-right align-middle num-mono text-[12.5px]" style={{ color: 'hsl(var(--ok))' }}>
                        {r.wins}
                      </td>
                      <td className="hidden md:table-cell px-3 py-2.5 text-right align-middle num-mono text-[12.5px]" style={{ color: 'hsl(var(--bad))' }}>
                        {r.losses}
                      </td>
                      <td className="hidden md:table-cell px-3 py-2.5 text-right align-middle num-mono text-[12.5px] text-muted-foreground">
                        {r.draws}
                      </td>
                    </tr>
                    {open && (
                      <tr className="border-b">
                        <td colSpan={8} className="bg-secondary/40 p-0">
                          <DrillDown agent={r.agent} data={drillData[r.agent]} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap gap-4 border-t bg-secondary/40 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-muted-foreground">
          <div className="flex-1">
            <strong>Coverage</strong> is how many of the {data.n_tasks_target} tasks each agent has a valid score for.
            Agents with fewer than 30 pairs are marked <span className="inline-flex items-center rounded-full bg-warn/10 px-1.5 py-0.5 text-[10px] font-medium text-warn">partial</span> —
            Elo tightens as more pairs land. A "<span className="num-mono">~</span>" means the gap to the row above is not statistically significant.
          </div>
          <div className="hidden md:block text-right text-muted-foreground/80">95% CI · 1000-iter bootstrap · click row for drill-down</div>
        </div>
      </div>
    </section>
  );
}

function Th({
  k,
  cur,
  dir,
  onClick,
  align,
  hideMobile,
  children,
}: {
  k: SortKey;
  cur: SortKey;
  dir: 'asc' | 'desc';
  onClick: (k: SortKey) => void;
  align?: 'left' | 'right';
  hideMobile?: boolean;
  children: React.ReactNode;
}) {
  const active = cur === k;
  return (
    <th
      onClick={() => onClick(k)}
      aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
      className={cn(
        'h-9 cursor-pointer select-none px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground',
        align === 'right' ? 'text-right' : 'text-left',
        hideMobile && 'hidden md:table-cell'
      )}
    >
      <span className={cn('inline-flex items-center gap-1', align === 'right' && 'justify-end w-full')}>
        {children}
        {active ? (
          dir === 'asc' ? <ChevronUp className="h-3 w-3 text-foreground" /> : <ChevronDown className="h-3 w-3 text-foreground" />
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-30" />
        )}
      </span>
    </th>
  );
}

function RankCell({ rank, tied }: { rank: number; tied: boolean }) {
  if (rank <= 3) {
    const styles: Record<number, React.CSSProperties> = {
      1: { background: '#fef3c7', color: '#92400e' },
      2: { background: '#f3f4f6', color: '#374151' },
      3: { background: '#fed7aa', color: '#9a3412' },
    };
    return (
      <span
        className={cn('inline-flex h-6 w-6 items-center justify-center rounded-md text-[12px] font-semibold tabular-nums', tied && 'opacity-55')}
        style={styles[rank]}
      >
        {rank}
      </span>
    );
  }
  return (
    <span className={cn('tabular-nums text-[13px] text-muted-foreground font-medium', tied && 'opacity-65')}>
      {rank}
      {tied && <span className="ml-0.5 text-[9px] text-muted-foreground/70">~</span>}
    </span>
  );
}

function CIBar({ markerPct, loPct, hiPct }: { markerPct: number; loPct: number; hiPct: number }) {
  return (
    <div className="px-1.5">
      <div className="relative h-2.5">
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-1 rounded-full bg-border" />
        <div
          className="absolute top-1/2 -translate-y-1/2 h-1 rounded-full bg-accent/30"
          style={{ left: `${loPct}%`, width: `${Math.max(0, hiPct - loPct)}%` }}
        />
        <div
          className="absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent ring-2 ring-card"
          style={{ left: `${markerPct}%` }}
        />
      </div>
    </div>
  );
}

function CoverageCell({ cov, target, pct, partial }: { cov: number; target: number; pct: number; partial: boolean }) {
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="flex-none w-14 h-1 rounded-full bg-border overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, background: partial ? 'hsl(var(--warn))' : 'hsl(var(--primary))' }}
        />
      </div>
      <span className={cn('num-mono text-[12px] tabular-nums', partial ? 'text-warn font-semibold' : 'text-foreground/80')}>
        {cov}<span className="text-muted-foreground/60">/</span>{target}
      </span>
    </div>
  );
}

function DrillDown({ agent, data }: { agent: string; data: AgentDrillData | null | undefined }) {
  if (data === undefined) return <div className="p-5 text-[12px] text-muted-foreground">Loading drill-down…</div>;
  if (data === null) return <div className="p-5 text-[12px] text-destructive">Failed to load drill-down.</div>;
  const color = agentColor(agent);
  const pillars: [keyof NonNullable<AgentDrillData['pillar_means']>, string][] = [
    ['url_coverage', 'URL coverage'],
    ['reachability', 'Reachability'],
    ['checklist', 'Checklist pass'],
    ['citation_alignment', 'Citation alignment'],
    ['analysis_depth', 'Analysis depth'],
    ['presentation', 'Presentation'],
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 p-5">
      <div className="md:col-span-1">
        <div className="flex items-center gap-2 mb-2">
          <span className="inline-flex h-5 w-5 items-center justify-center rounded text-[9px] font-bold text-white" style={{ background: color }}>
            {agent.slice(0, 2).toUpperCase()}
          </span>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{agent}</div>
        </div>
        {data.elo_v2 && (
          <div className="text-[12.5px] text-foreground/80 mb-1">
            <span className="num-mono font-semibold">Elo {Math.round(data.elo_v2.elo)}</span>{' '}
            <span className="num-mono text-muted-foreground">[{Math.round(data.elo_v2.elo_lo)}, {Math.round(data.elo_v2.elo_hi)}]</span>{' '}
            · <span>{data.n_pairs} scored pairs</span>
          </div>
        )}
        <div className="mt-1 text-[12px] flex flex-wrap gap-x-2 text-accent">
          {data.github_url && (
            <a className="hover:underline" href={data.github_url} target="_blank" rel="noopener">GitHub ↗</a>
          )}
          {data.paper_url && (
            <a className="hover:underline" href={data.paper_url} target="_blank" rel="noopener">Paper ↗</a>
          )}
        </div>
      </div>
      <div className="md:col-span-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">Per-pillar mean</div>
        <div className="space-y-1">
          {pillars.map(([key, label]) => {
            const v = data.pillar_means?.[key];
            const elo = data.pillar_elo?.[key];
            const pct = typeof v === 'number' ? Math.round(v * 100) : null;
            return (
              <div key={key} className="grid grid-cols-[130px_1fr_50px_50px] items-center gap-2.5 text-[12px]">
                <span className="text-foreground/80">{label}</span>
                <div className="relative h-1.5 rounded-full bg-border overflow-hidden">
                  <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.max(2, Math.min(100, pct ?? 0))}%`, background: color }} />
                </div>
                <span className="text-right tabular-nums text-foreground/80 text-[11.5px]">{pct == null ? '—' : pct + '%'}</span>
                <span className="text-right num-mono text-muted-foreground text-[11px]">{typeof elo === 'number' ? Math.round(elo) : ''}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="md:col-span-3 grid grid-cols-1 md:grid-cols-2 gap-6 mt-1">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'hsl(var(--ok))' }}>Best 3 tasks</div>
          <TaskList rows={data.best_tasks ?? []} />
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'hsl(var(--bad))' }}>Worst 3 tasks</div>
          <TaskList rows={data.worst_tasks ?? []} />
        </div>
      </div>
    </div>
  );
}

function TaskList({ rows }: { rows: NonNullable<AgentDrillData['best_tasks']> }) {
  if (!rows.length) return <div className="text-[12px] text-muted-foreground">No scored tasks yet.</div>;
  return (
    <div className="space-y-1">
      {rows.map((r) => (
        <div key={r.task_id} className="flex items-center gap-2 border-b border-dashed border-border/60 py-1 text-[12px] last:border-0">
          <a href={`/task/${r.task_id}/`} className="text-accent hover:underline">{r.task_id}</a>
          <span className="text-muted-foreground text-[11px]">composite_v2</span>
          <span className="num-mono text-[11.5px]">{r.composite_v2 != null ? r.composite_v2.toFixed(3) : '—'}</span>
          <span className="ml-auto text-muted-foreground text-[11px]">
            cov {r.url_coverage != null ? Math.round(r.url_coverage * 100) : '—'}% / reach {r.reachability != null ? Math.round(r.reachability * 100) : '—'}%
          </span>
        </div>
      ))}
    </div>
  );
}
