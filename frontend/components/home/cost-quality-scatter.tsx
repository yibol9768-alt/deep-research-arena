import { agentMeta } from '@/lib/providers'
import type { CostQualitySnapshot } from '@/lib/data/load-cost-quality'
import { T } from '@/components/i18n/t'

const W = 860
const H = 460
const M = { top: 28, right: 40, bottom: 50, left: 58 }

/**
 * AA-style cost-per-score scatter: five-axis truth (y) against real cost per
 * task (x, log scale). One point per harness on a single backbone lane, so the
 * cost and the score come from the same runs. Server-rendered SVG.
 */
export function CostQualityScatter({ data }: { data: CostQualitySnapshot }) {
  const pts = data.agents.filter(
    (a) => a.truth_macro != null && a.cost_cny_per_task_mean != null && a.cost_cny_per_task_mean > 0,
  )
  if (pts.length === 0) return null

  const costs = pts.map((p) => p.cost_cny_per_task_mean as number)
  const truths = pts.map((p) => (p.truth_macro as number) * 100)

  // Log-x domain snapped to decade-friendly bounds around the data.
  const xMin = Math.min(0.02, Math.min(...costs))
  const xMax = Math.max(0.5, Math.max(...costs))
  const lx = (c: number) => (Math.log10(c) - Math.log10(xMin)) / (Math.log10(xMax) - Math.log10(xMin))
  const x = (c: number) => M.left + lx(c) * (W - M.left - M.right)

  const yMax = Math.max(20, Math.ceil(Math.max(...truths) / 5) * 5)
  const y = (t: number) => M.top + (1 - t / yMax) * (H - M.top - M.bottom)

  const xTicks = [0.02, 0.05, 0.1, 0.2, 0.5].filter((v) => v >= xMin && v <= xMax)
  const yTicks: number[] = []
  for (let v = 0; v <= yMax; v += 5) yTicks.push(v)

  const sorted = [...pts].sort((p, q) => (q.truth_macro as number) - (p.truth_macro as number))
  const skipped = data.agents.filter((a) => a.truth_macro == null).map((a) => a.agent)

  // Greedy label placement: try right-above / right-below / left-above /
  // left-below of each dot, keeping the first slot that hits neither a placed
  // label nor any dot. Rects are approximated from the 11px font.
  const dots = sorted.map((p) => ({ cx: x(p.cost_cny_per_task_mean as number), cy: y((p.truth_macro as number) * 100) }))
  const placedRects: { x1: number; y1: number; x2: number; y2: number }[] = []
  const collides = (r: { x1: number; y1: number; x2: number; y2: number }) =>
    placedRects.some((o) => r.x1 < o.x2 && r.x2 > o.x1 && r.y1 < o.y2 && r.y2 > o.y1) ||
    dots.some((d) => d.cx > r.x1 - 6 && d.cx < r.x2 + 6 && d.cy > r.y1 - 6 && d.cy < r.y2 + 6)
  const labelPos = sorted.map((p, i) => {
    const name = agentMeta(p.agent).display
    const w = name.length * 6.6
    const { cx, cy } = dots[i]
    const slots = [
      { x: cx + 8, y: cy - 9, anchor: 'start' as const },
      { x: cx + 8, y: cy + 15, anchor: 'start' as const },
      { x: cx - 8, y: cy - 9, anchor: 'end' as const },
      { x: cx - 8, y: cy + 15, anchor: 'end' as const },
      { x: cx + 8, y: cy - 25, anchor: 'start' as const },
      { x: cx + 8, y: cy + 31, anchor: 'start' as const },
      { x: cx - 8, y: cy - 25, anchor: 'end' as const },
      { x: cx - 8, y: cy + 31, anchor: 'end' as const },
    ]
    const rectFor = (s: (typeof slots)[number]) =>
      s.anchor === 'start'
        ? { x1: s.x, y1: s.y - 10, x2: s.x + w, y2: s.y + 4 }
        : { x1: s.x - w, y1: s.y - 10, x2: s.x, y2: s.y + 4 }
    for (const s of slots) {
      const r = rectFor(s)
      if (!collides(r)) {
        placedRects.push(r)
        return s
      }
    }
    const s = slots[i % 2]
    placedRects.push(rectFor(s))
    return s
  })

  return (
    <article className="card p-5">
      <header className="flex items-center gap-2.5">
        <span className="aa-square" />
        <h3 className="font-serif text-xl text-ink">
          <T en="Truth per yuan — cost vs score" zh="性价比 —— 成本 vs 真值分" />
        </h3>
      </header>
      <p className="mt-1.5 text-xs text-muted">
        <T
          en={`Five-axis truth score against measured cost per task on the ${data.backbone} lane (log scale). Tokens are metered per run by the proxy; money is stated at the paid list price of the same model. Up-left is better.`}
          zh={`五轴 truth 分对 ${data.backbone} 车道实测的每任务成本（对数轴）。token 由代理逐次运行计量,金额按同模型付费档列表价折算。左上更优。`}
        />
      </p>

      <div className="mt-4 overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[640px]" role="img" aria-label="Scatter plot of truth score versus cost per task">
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
                ¥{v}
              </text>
            </g>
          ))}

          {/* quadrant hints */}
          <text x={M.left + 10} y={M.top + 14} fontSize="11" fill="#C2C6CC">
            <T en="cheap and true" zh="低耗高真" />
          </text>
          <text x={W - M.right - 10} y={H - M.bottom - 10} fontSize="11" fill="#C2C6CC" textAnchor="end">
            <T en="expensive and wrong" zh="高耗低真" />
          </text>

          {/* axis labels */}
          <text x={(M.left + W - M.right) / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="#565B66">
            <T en="Cost per task, CNY at list price (log scale)" zh="每任务成本,人民币列表价（对数轴）" />
          </text>
          <text x={14} y={M.top - 10} fontSize="11" fill="#565B66">
            <T en="Five-axis truth (×100)" zh="五轴 truth 分（×100）" />
          </text>

          {sorted.map((p, i) => {
            const meta = agentMeta(p.agent)
            const { cx, cy } = dots[i]
            const lp = labelPos[i]
            const mtok = (p.tokens_per_task_mean / 1000).toFixed(0)
            return (
              <g key={p.agent}>
                <title>
                  {`${meta.display} · truth ${((p.truth_macro as number) * 100).toFixed(1)} · ¥${(p.cost_cny_per_task_mean as number).toFixed(3)}/task · ${mtok}k tok/task · ${p.n_runs} runs`}
                </title>
                <circle cx={cx} cy={cy} r="5.5" fill={meta.color} stroke="#fff" strokeWidth="1.5" />
                <text x={lp.x} y={lp.y} textAnchor={lp.anchor} fontSize="11" fontWeight="600" fill="#111318">
                  {meta.display}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-muted-2">
        <T
          en={`Partial diagnostic lane: truth from ${pts[0]?.n_scored_tasks ?? 7} scored tasks per harness; cost averaged over all metered runs so far. ${data.pricing}. The lane actually ran on the free tier (actual spend ¥0); list price is shown so the axis survives pricing changes. ${skipped.length > 0 ? `Not shown (no truth score yet): ${skipped.map((s) => agentMeta(s).display).join(', ')}.` : ''} More lanes join as their usage accounting lands.`
          }
          zh={`部分诊断车道:truth 来自每框架 ${pts[0]?.n_scored_tasks ?? 7} 个已判分任务;成本为迄今全部计量运行的均值。${data.pricing}。该车道实际使用免费档（实付 ¥0）,图中按列表价折算以保证口径稳定。${skipped.length > 0 ? `暂未展示（尚无 truth 分）：${skipped.map((s) => agentMeta(s).display).join('、')}。` : ''}其余车道的用量记账落地后将陆续加入。`}
        />
      </p>
    </article>
  )
}
