'use client';

import * as React from 'react';
import { agentColor } from '@/lib/agent-color';

export interface ScatterAgent {
  name: string;
  elo: number;
  elo_lo: number;
  elo_hi: number;
  ci_width: number;
  wins: number;
  losses: number;
  draws: number;
  coverage: number;
  n_tasks_target: number;
}

interface AxisDef {
  label: string;
  extract: (a: ScatterAgent) => number;
  getMax: (agents: ScatterAgent[]) => number;
  pct?: boolean;
  unit?: string;
}

const AXIS: Record<string, AxisDef> = {
  coverage: {
    label: 'Coverage',
    extract: (a) => a.coverage,
    getMax: (agents) => Math.max(agents[0]?.n_tasks_target ?? 0, ...agents.map((a) => a.coverage)),
  },
  winrate: {
    label: 'Win rate',
    extract: (a) => ((a.wins + a.losses) > 0 ? a.wins / (a.wins + a.losses) : 0),
    getMax: () => 1,
    pct: true,
  },
  ci: {
    label: 'CI width',
    extract: (a) => a.ci_width,
    getMax: (agents) => Math.max(...agents.map((a) => a.ci_width)) * 1.15,
    unit: ' Elo',
  },
};

export function ScatterCard({ agents, axis, title, caption }: { agents: ScatterAgent[]; axis: keyof typeof AXIS; title: string; caption: string }) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const [w, setW] = React.useState(420);
  const [tip, setTip] = React.useState<{ x: number; y: number; agent: ScatterAgent } | null>(null);

  React.useEffect(() => {
    function update() {
      if (containerRef.current) setW(containerRef.current.clientWidth);
    }
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  if (agents.length < 2) {
    return (
      <article className="rounded-lg border bg-card overflow-hidden">
        <header className="border-b px-4 py-3">
          <h3 className="text-[14px] font-semibold">{title}</h3>
          <p className="mt-0.5 text-[11.5px] leading-relaxed text-muted-foreground">{caption}</p>
        </header>
        <div className="p-4 text-[12px] text-muted-foreground">Need 2+ agents to render.</div>
      </article>
    );
  }

  const def = AXIS[axis];
  const W = w || 320;
  const H = 240;
  const M = { l: 48, r: 16, t: 12, b: 38 };
  const innerW = W - M.l - M.r;
  const innerH = H - M.t - M.b;

  const eloLo = Math.min(...agents.map((a) => a.elo_lo));
  const eloHi = Math.max(...agents.map((a) => a.elo_hi));
  const eloPad = (eloHi - eloLo) * 0.06 || 20;
  const xMin = eloLo - eloPad;
  const xMax = eloHi + eloPad;
  const yMax = def.getMax(agents);
  const yMin = 0;
  const targetN = agents[0]?.n_tasks_target ?? 0;

  const sx = (v: number) => M.l + ((v - xMin) / (xMax - xMin)) * innerW;
  const sy = (v: number) => M.t + innerH - ((v - yMin) / (yMax - yMin)) * innerH;

  const yTicks = 4;
  const xTicks = 4;

  const sorted = [...agents].sort((a, b) => b.elo - a.elo);
  const topName = sorted[0]?.name;

  function dotInfo(a: ScatterAgent) {
    const y = def.extract(a);
    let yDisp: string;
    if (def.pct) yDisp = Math.round(y * 100) + '%';
    else if (def.unit) yDisp = Math.round(y) + def.unit;
    else yDisp = `${a.coverage} / ${targetN}`;
    return yDisp;
  }

  return (
    <article className="rounded-lg border bg-card overflow-hidden">
      <header className="border-b px-4 py-3">
        <h3 className="text-[14px] font-semibold">{title}</h3>
        <p className="mt-0.5 text-[11.5px] leading-relaxed text-muted-foreground">{caption}</p>
      </header>
      <div ref={containerRef} className="relative px-1 py-2" style={{ minHeight: 240 }}>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" className="block w-full">
          <rect x={M.l} y={M.t} width={innerW} height={innerH} fill="hsl(var(--secondary) / 0.4)" rx="3" />
          {Array.from({ length: yTicks + 1 }).map((_, i) => {
            const v = yMin + ((yMax - yMin) * i) / yTicks;
            const y = sy(v);
            const lbl = def.pct ? Math.round(v * 100) + '%' : Math.round(v).toString();
            return (
              <g key={`y${i}`}>
                <line x1={M.l} x2={M.l + innerW} y1={y} y2={y} stroke="hsl(var(--border))" strokeDasharray="2 3" />
                <text x={M.l - 6} y={y + 3} textAnchor="end" fontSize="10.5" fill="hsl(var(--muted-foreground))" className="font-mono">{lbl}</text>
              </g>
            );
          })}
          {Array.from({ length: xTicks + 1 }).map((_, i) => {
            const v = xMin + ((xMax - xMin) * i) / xTicks;
            const x = sx(v);
            return (
              <g key={`x${i}`}>
                <line x1={x} x2={x} y1={M.t} y2={M.t + innerH} stroke="hsl(var(--border))" strokeDasharray="2 3" />
                <text x={x} y={M.t + innerH + 14} textAnchor="middle" fontSize="10.5" fill="hsl(var(--muted-foreground))" className="font-mono">{Math.round(v)}</text>
              </g>
            );
          })}
          <text x={M.l + innerW / 2} y={H - 4} textAnchor="middle" fontSize="11" fill="hsl(var(--foreground) / 0.75)" fontWeight={500}>Elo</text>
          {axis === 'coverage' && targetN <= yMax && (
            <line x1={M.l} x2={M.l + innerW} y1={sy(targetN)} y2={sy(targetN)} stroke="hsl(var(--foreground) / 0.55)" strokeWidth="1" strokeDasharray="3 3" />
          )}
          {agents.map((a) => {
            const yVal = def.extract(a);
            const cx = sx(a.elo);
            const cy = sy(yVal);
            return (
              <circle
                key={a.name}
                cx={cx}
                cy={cy}
                r={5}
                fill={agentColor(a.name)}
                stroke="white"
                strokeWidth={1.5}
                onMouseEnter={() => setTip({ x: cx, y: cy, agent: a })}
                onMouseLeave={() => setTip(null)}
                className="cursor-pointer transition-[r]"
                style={{ filter: tip?.agent.name === a.name ? 'brightness(0.85)' : undefined }}
              />
            );
          })}
          {(() => {
            const a = sorted[0];
            if (!a) return null;
            const yVal = def.extract(a);
            const cx = sx(a.elo);
            const cy = sy(yVal);
            const text = a.name.length > 12 ? a.name.slice(0, 11) + '…' : a.name;
            return (
              <g>
                <text x={cx} y={cy - 10} textAnchor="middle" fontSize="9.5" fontWeight={600} stroke="white" strokeWidth="2.5" strokeLinejoin="round" paintOrder="stroke">{text}</text>
                <text x={cx} y={cy - 10} textAnchor="middle" fontSize="9.5" fontWeight={600} fill="hsl(var(--foreground))">{text}</text>
              </g>
            );
          })()}
        </svg>
        {tip && (
          <div
            className="pointer-events-none absolute z-10 min-w-[140px] rounded-md bg-primary px-2.5 py-2 text-[11px] leading-tight text-primary-foreground shadow-lg"
            style={{
              left: `${(tip.x / W) * 100}%`,
              top: `${(tip.y / H) * 100}%`,
              transform: 'translate(-50%, calc(-100% - 10px))',
            }}
          >
            <strong className="block mb-1 text-[12px]">{tip.agent.name}</strong>
            <div className="flex justify-between gap-3 num-mono"><span className="opacity-65">Elo</span><span>{Math.round(tip.agent.elo)}</span></div>
            <div className="flex justify-between gap-3 num-mono"><span className="opacity-65">{def.label}</span><span>{dotInfo(tip.agent)}</span></div>
            <div className="flex justify-between gap-3 num-mono"><span className="opacity-65">W · L</span><span>{tip.agent.wins} · {tip.agent.losses}</span></div>
          </div>
        )}
      </div>
    </article>
  );
}
