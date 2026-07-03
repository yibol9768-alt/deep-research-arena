import { agentMeta } from '@/lib/providers'
import { groundingGatePct } from '@/lib/format'
import type { RankedAgent } from '@/lib/data/types'
import { T } from '@/components/i18n/t'

const W = 860
const H = 460
const M = { top: 28, right: 30, bottom: 46, left: 58 }

/**
 * AA-style scatter: judge preference (raw Elo, y) against the judge-free
 * grounding gate (x). The top-left quadrant is exactly the failure mode the
 * benchmark exists to expose: fluent but ungrounded. Server-rendered SVG.
 */
export function GateScatter({ agents }: { agents: RankedAgent[] }) {
  const pts = agents
    .map((a) => ({ a, gate: groundingGatePct(a) }))
    .filter((p): p is { a: RankedAgent; gate: number } => p.gate != null)

  // Domain follows the point estimates, not the CI extremes — one agent with a
  // huge interval (few battles) must not squash everyone else into a corner.
  const elos = pts.map((p) => p.a.elo)
  const yMin = Math.floor((Math.min(...elos) - 60) / 100) * 100
  const yMax = Math.ceil((Math.max(...elos) + 60) / 100) * 100

  const x = (gate: number) => M.left + (gate / 100) * (W - M.left - M.right)
  const y = (elo: number) => M.top + (1 - (elo - yMin) / (yMax - yMin)) * (H - M.top - M.bottom)

  const yStep = yMax - yMin > 600 ? 200 : 100
  const yTicks: number[] = []
  for (let v = yMin; v <= yMax; v += yStep) yTicks.push(v)
  const xTicks = [0, 20, 40, 60, 80, 100]
  const clampY = (elo: number) => Math.max(yMin, Math.min(yMax, elo))

  // Nudge label vertical offsets for near-collisions (simple pass).
  const sorted = [...pts].sort((p, q) => q.a.elo - p.a.elo)

  return (
    <article className="card p-5">
      <header className="flex items-center gap-2.5">
        <span className="aa-square" />
        <h3 className="font-serif text-xl text-ink">
          <T en="Judge preference vs grounding" zh="判官偏好 vs 接地" />
        </h3>
      </header>
      <p className="mt-1.5 text-xs text-muted">
        <T
          en="Raw jury Elo (with 95% CI whiskers) against the judge-free grounding gate. Top-left is the failure mode this benchmark exposes: fluent but ungrounded."
          zh="裸陪审团 Elo(含 95% 置信区间须线)对不依赖判官的接地门。左上角正是本基准要暴露的失败模式:流畅但不接地。"
        />
      </p>

      <div className="mt-4 overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[640px]" role="img" aria-label="Scatter plot of judge Elo versus grounding gate">
          {/* gridlines */}
          {yTicks.map((v) => (
            <g key={`y${v}`}>
              <line x1={M.left} x2={W - M.right} y1={y(v)} y2={y(v)} stroke="#E5E7EB" strokeDasharray="2 4" />
              <text x={M.left - 8} y={y(v) + 3.5} textAnchor="end" fontSize="11" fill="#8A8F99" className="tnum">
                {v}
              </text>
            </g>
          ))}
          {xTicks.map((v) => (
            <g key={`x${v}`}>
              <line x1={x(v)} x2={x(v)} y1={M.top} y2={H - M.bottom} stroke="#E5E7EB" strokeDasharray="2 4" />
              <text x={x(v)} y={H - M.bottom + 18} textAnchor="middle" fontSize="11" fill="#8A8F99" className="tnum">
                {v}%
              </text>
            </g>
          ))}

          {/* quadrant hints */}
          <text x={M.left + 10} y={M.top + 14} fontSize="11" fill="#C2C6CC">
            <T en="fluent but ungrounded" zh="流畅但不接地" />
          </text>
          <text x={W - M.right - 10} y={M.top + 14} fontSize="11" fill="#C2C6CC" textAnchor="end">
            <T en="fluent and grounded" zh="流畅且接地" />
          </text>

          {/* axis labels */}
          <text x={(M.left + W - M.right) / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="#565B66">
            <T en="Grounding gate — (reachability + quote match) / 2, %" zh="接地门 —(可达率 + 引文核实率)/ 2,%" />
          </text>
          <text x={14} y={M.top - 10} fontSize="11" fill="#565B66">
            <T en="Judge Elo (raw)" zh="裸判官 Elo" />
          </text>

          {/* CI whiskers + points + labels */}
          {sorted.map((p, i) => {
            const meta = agentMeta(p.a.id)
            const cx = x(p.gate)
            const cy = y(p.a.elo)
            const labelAbove = i % 2 === 0
            return (
              <g key={p.a.id}>
                <line x1={cx} x2={cx} y1={y(clampY(p.a.ci_lo))} y2={y(clampY(p.a.ci_hi))} stroke={meta.color} strokeOpacity="0.35" strokeWidth="2" />
                <circle cx={cx} cy={cy} r="5.5" fill={meta.color} stroke="#fff" strokeWidth="1.5" />
                <text
                  x={cx + 8}
                  y={labelAbove ? cy - 7 : cy + 15}
                  fontSize="11"
                  fontWeight="600"
                  fill="#111318"
                >
                  {meta.display}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    </article>
  )
}
