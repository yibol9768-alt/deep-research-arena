'use client'

import { useState } from 'react'
import { cn } from '@/lib/cn'
import { T } from '@/components/i18n/t'

export interface ScatterPoint {
  id: string
  label: string
  color: string
  backbone: string
  /** Estimated inference cost per task, CNY. */
  cost: number
  /** Arena Score (reach^1.5 x jury win-rate). */
  score: number
  /** True when the price used is an estimate (qwen3-8b, local run). */
  costEstimated?: boolean
}

interface Props {
  points: ScatterPoint[]
  isPreview?: boolean
}

const W = 860
const H = 460
const M = { top: 26, right: 24, bottom: 52, left: 56 }

type Filter = 'all' | 'deepseek-v4-flash' | 'qwen3-8b'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'Both' },
  { key: 'deepseek-v4-flash', label: 'deepseek-v4-flash' },
  { key: 'qwen3-8b', label: 'qwen3-8b' },
]

/**
 * AA-style quality-vs-price scatter. x = estimated cost per task (log CNY),
 * y = Arena Score. Each framework is a point in its provider color; deepseek
 * runs are filled circles (confirmed price), qwen3-8b runs are hollow
 * (estimated price). A dashed step line marks the cheaper-and-better Pareto
 * frontier. The most attractive quadrant is top-left.
 */
export function QualityPriceScatter({ points, isPreview }: Props) {
  const [filter, setFilter] = useState<Filter>('all')
  const pts = points.filter((p) => p.cost > 0 && (filter === 'all' || p.backbone === filter))

  if (pts.length === 0) {
    return null
  }

  // x: log10(cost). y: linear Arena.
  const logs = pts.map((p) => Math.log10(p.cost))
  const lx0 = Math.floor(Math.min(...logs) * 10) / 10 - 0.15
  const lx1 = Math.ceil(Math.max(...logs) * 10) / 10 + 0.15
  const yMaxRaw = Math.max(...pts.map((p) => p.score), 0.1)
  const yMax = Math.ceil(yMaxRaw * 11) / 10 // ~10% head-room, rounded to 0.1

  const x = (cost: number) => M.left + ((Math.log10(cost) - lx0) / (lx1 - lx0)) * (W - M.left - M.right)
  const y = (score: number) => M.top + (1 - score / yMax) * (H - M.top - M.bottom)

  // x ticks at powers of ten inside the domain.
  const xTicks: number[] = []
  for (let e = Math.ceil(lx0); e <= Math.floor(lx1); e++) xTicks.push(e)
  // y ticks every 0.1.
  const yTicks: number[] = []
  for (let v = 0; v <= yMax + 1e-9; v += 0.1) yTicks.push(Math.round(v * 10) / 10)

  // Pareto frontier: cheaper-and-better (low cost, high score). A point is on
  // the frontier when no other point has cost <= and score >= (one strict).
  const frontier = pts
    .filter((p) => !pts.some((q) => q !== p && q.cost <= p.cost && q.score >= p.score && (q.cost < p.cost || q.score > p.score)))
    .sort((a, b) => a.cost - b.cost)
  // Step path: horizontal then vertical between consecutive frontier points.
  const stepPath = frontier.reduce((acc, p, i) => {
    const px = x(p.cost)
    const py = y(p.score)
    if (i === 0) return `M ${px} ${py}`
    const prev = frontier[i - 1]
    return `${acc} L ${px} ${y(prev.score)} L ${px} ${py}`
  }, '')
  const frontierIds = new Set(frontier.map((p) => p.id + p.backbone))

  const fmtTick = (e: number) => {
    const v = Math.pow(10, e)
    if (v >= 1) return `¥${v}`
    if (v >= 0.1) return `¥${v.toFixed(1)}`
    if (v >= 0.01) return `¥${v.toFixed(2)}`
    return `¥${v.toFixed(3)}`
  }

  return (
    <section id="value" className="container mt-16 scroll-mt-24">
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-3 border-b border-hairline pb-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="aa-square" />
            <h2 className="font-serif text-2xl text-ink sm:text-[28px]">
              <T en="Quality vs price" zh="质量 vs 价格" />
            </h2>
            {isPreview ? (
              <span className="inline-flex items-center rounded-full border border-hairline bg-surface-low px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-2">
                <T en="Preview · 13-task subset" zh="预览 · 13 题子集" />
              </span>
            ) : null}
          </div>
          <p className="mt-1.5 max-w-xl text-xs leading-relaxed text-muted">
            <T
              en="Arena Score against estimated inference cost per task. Frameworks toward the top-left deliver more quality per yuan."
              zh="竞技场得分对每题推理成本估算。越靠左上,单位成本产出的质量越高。"
            />
          </p>
        </div>
        <div className="inline-flex rounded-full border border-hairline p-0.5 text-xs">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                'rounded-full px-3 py-1 transition-colors',
                filter === f.key ? 'bg-surface-mid font-medium text-ink' : 'text-muted hover:text-ink',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="card mt-6 p-5">
        <div className="overflow-x-auto">
          <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[640px]" role="img" aria-label="Scatter plot of Arena Score versus cost per task">
            {/* gridlines */}
            {yTicks.map((v) => (
              <g key={`y${v}`}>
                <line x1={M.left} x2={W - M.right} y1={y(v)} y2={y(v)} stroke="#E5E7EB" strokeDasharray="2 4" />
                <text x={M.left - 8} y={y(v) + 3.5} textAnchor="end" fontSize="11" fill="#8A8F99" className="tnum">
                  {v.toFixed(1)}
                </text>
              </g>
            ))}
            {xTicks.map((e) => (
              <g key={`x${e}`}>
                <line x1={x(Math.pow(10, e))} x2={x(Math.pow(10, e))} y1={M.top} y2={H - M.bottom} stroke="#E5E7EB" strokeDasharray="2 4" />
                <text x={x(Math.pow(10, e))} y={H - M.bottom + 18} textAnchor="middle" fontSize="11" fill="#8A8F99" className="tnum">
                  {fmtTick(e)}
                </text>
              </g>
            ))}

            {/* axis labels */}
            <text x={(M.left + W - M.right) / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="#565B66">
              <T en="Cost per task (CNY, log scale)" zh="每题成本(元,对数刻度)" />
            </text>
            <text x={16} y={M.top - 10} fontSize="11" fill="#565B66">
              <T en="Arena Score" zh="竞技场得分" />
            </text>

            {/* quadrant hint */}
            <text x={M.left + 8} y={M.top + 12} fontSize="11" fill="#C2C6CC">
              <T en="← cheaper · better ↑" zh="← 更便宜 · 更好 ↑" />
            </text>

            {/* Pareto frontier */}
            {frontier.length >= 2 ? (
              <path d={stepPath} fill="none" stroke="#8A8F99" strokeWidth="1.5" strokeDasharray="4 4" />
            ) : null}

            {/* points + labels */}
            {pts.map((p, i) => {
              const cx = x(p.cost)
              const cy = y(p.score)
              const onFrontier = frontierIds.has(p.id + p.backbone)
              const filled = p.backbone === 'deepseek-v4-flash'
              const placeLeft = cx > W - M.right - 120
              return (
                <g key={p.id + p.backbone}>
                  <circle
                    cx={cx}
                    cy={cy}
                    r={onFrontier ? 6 : 5}
                    fill={filled ? p.color : '#ffffff'}
                    stroke={p.color}
                    strokeWidth={filled ? (onFrontier ? 1.5 : 1) : 2}
                  />
                  <text
                    x={placeLeft ? cx - 9 : cx + 9}
                    y={cy + (i % 2 === 0 ? -6 : 12)}
                    textAnchor={placeLeft ? 'end' : 'start'}
                    fontSize="10.5"
                    fontWeight={onFrontier ? '600' : '400'}
                    fill={onFrontier ? '#111318' : '#565B66'}
                  >
                    {p.label}
                    {p.costEstimated ? ' *' : ''}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>

        {/* legend */}
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[11px] text-muted">
          <span className="inline-flex items-center gap-1.5">
            <svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="#565B66" /></svg>
            <T en="deepseek-v4-flash (confirmed price)" zh="deepseek-v4-flash(确认价)" />
          </span>
          <span className="inline-flex items-center gap-1.5">
            <svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="#fff" stroke="#565B66" strokeWidth="2" /></svg>
            <T en="qwen3-8b (estimated price *)" zh="qwen3-8b(估算价 *)" />
          </span>
          <span className="inline-flex items-center gap-1.5">
            <svg width="20" height="8"><line x1="0" y1="4" x2="20" y2="4" stroke="#8A8F99" strokeWidth="1.5" strokeDasharray="4 4" /></svg>
            <T en="Pareto frontier (cheaper & better)" zh="帕累托前沿(更便宜且更好)" />
          </span>
        </div>

        {/* footnote */}
        <p className="mt-3 border-t border-hairline pt-3 text-[11px] leading-relaxed text-muted-2">
          <T
            en="Cost = estimated inference-token spend attributed from the box's LLM gateway usage log, summed over the 13-task subset and divided by task count. deepseek-v4-flash uses the confirmed DashScope/Bailian list price (¥1/M prompt, ¥2/M completion). qwen3-8b (*) ran locally on the 5090 box with no billed API cost; its price (¥0.5/¥1.5 per M) is a Bailian-tier estimate used only to place both backbones on one axis. Judge/jury calls are excluded from framework cost. Preview on 13 tasks."
            zh="成本 = 从箱上 LLM 网关 usage 日志按运行时间窗归属的推理 token 花费,对 13 题子集求和后除以题数。deepseek-v4-flash 用确认的百炼挂牌价(prompt ¥1/M、completion ¥2/M)。qwen3-8b(*)本地在 5090 上运行,未产生 API 费用,其价格(¥0.5/¥1.5 每 M)仅为让两底模同轴可比的百炼档估算。判官/陪审团调用不计入框架成本。13 题预览。"
          />
        </p>
      </div>
    </section>
  )
}
