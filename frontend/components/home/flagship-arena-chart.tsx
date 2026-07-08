'use client'

import { useState } from 'react'
import Link from 'next/link'
import { cn } from '@/lib/cn'
import { T } from '@/components/i18n/t'

export interface FlagshipRow {
  id: string
  label: string
  backbone: string
  color: string
  arena: number
  arenaLo?: number
  arenaHi?: number
  winrate: number
  reach: number
  bt_elo: number
  n_battles: number
}

export interface FlagshipBackbone {
  key: string
  label: string
  note?: string
  rows: FlagshipRow[]
}

interface Props {
  backbones: FlagshipBackbone[]
  updatedAt: string
  formula: string
  isPreview?: boolean
}

/**
 * Flagship AA-style Intelligence-Index chart: one wide column per framework,
 * ranked high-to-low, colored by provider, value labels above the bars, and a
 * CI whisker at each bar top. A backbone tab switches the whole board. Each
 * bar links to that framework's /agents/[id] detail page.
 *
 * Arena Score is shown x100 for readability; the underlying value is
 * reach^1.5 x jury Bradley-Terry win-rate on the 13-task diagnostic subset.
 */
export function FlagshipArenaChart({ backbones, updatedAt, formula, isPreview }: Props) {
  const [active, setActive] = useState(
    Math.max(0, backbones.findIndex((b) => b.key === 'deepseek-v4-flash')),
  )
  const bb = backbones[active] ?? backbones[0]
  const rows = [...bb.rows].sort((a, b) => b.arena - a.arena)
  const max = Math.max(...rows.map((r) => r.arenaHi ?? r.arena), 0.01)
  // Leave head-room above the tallest bar for the value label.
  const scale = 82
  const h = (v: number) => Math.max((v / max) * scale, 0)

  return (
    <section id="arena" className="container mt-14 scroll-mt-24">
      {/* Header: title + preview pill on the left, backbone tabs + meta on the right */}
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-3 border-b border-hairline pb-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="aa-square" />
            <h2 className="font-serif text-2xl text-ink sm:text-[28px]">
              <T en="Arena Score" zh="竞技场得分" />
            </h2>
            {isPreview ? <PreviewPill /> : null}
          </div>
          <p className="mt-1.5 max-w-xl text-xs leading-relaxed text-muted">
            <T
              en={<>Arena = reach<sup>1.5</sup> &times; jury Bradley&#8209;Terry win&#8209;rate. The grounding gate is multiplied in, so fluent-but-fabricated reports cannot top the board. </>}
              zh={<>Arena = reach<sup>1.5</sup> &times; 陪审团 Bradley&#8209;Terry 胜率。接地门乘入总分,流畅但编造引用的报告无法登顶。</>}
            />
            <Link href="/methodology" className="text-brand hover:underline">
              <T en="Methodology" zh="方法学" /> &rarr;
            </Link>
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="inline-flex rounded-full border border-hairline p-0.5 text-xs">
            {backbones.map((b, i) => (
              <button
                key={b.key}
                onClick={() => setActive(i)}
                className={cn(
                  'rounded-full px-3 py-1 transition-colors',
                  i === active ? 'bg-surface-mid font-medium text-ink' : 'text-muted hover:text-ink',
                )}
              >
                {b.label}
              </button>
            ))}
          </div>
          <span className="text-[11px] text-muted-2">
            <T
              en={`${rows.length} open-source frameworks · updated ${updatedAt}`}
              zh={`${rows.length} 个开源框架 · 更新于 ${updatedAt}`}
            />
          </span>
        </div>
      </div>

      {/* Plot */}
      <div className="card mt-6 p-5 sm:p-7">
        <div className="relative h-[320px] sm:h-[380px]">
          {/* dotted gridlines at 25/50/75/100% of scale */}
          {[0, 25, 50, 75].map((p) => (
            <div
              key={p}
              aria-hidden
              className="absolute inset-x-0 border-t border-dotted border-hairline"
              style={{ top: `${p * (scale / 100)}%` }}
            />
          ))}
          <div className="absolute inset-0 flex items-end justify-between gap-2 sm:gap-3">
            {rows.map((r) => {
              const barH = h(r.arena)
              const showCi = r.arenaLo != null && r.arenaHi != null && r.arenaHi > r.arenaLo
              const loH = showCi ? h(r.arenaLo as number) : 0
              const hiH = showCi ? h(r.arenaHi as number) : 0
              const labelBottom = Math.max(barH, hiH)
              return (
                <div key={r.id} className="group relative flex h-full min-w-0 flex-1 flex-col justify-end">
                  {/* value label */}
                  <span
                    className="pointer-events-none absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-[11px] font-semibold leading-none tnum text-ink"
                    style={{ bottom: `calc(${labelBottom}% + 4px)` }}
                  >
                    {(r.arena * 100).toFixed(1)}
                  </span>
                  {/* bar (clickable) */}
                  <Link
                    href={`/agents/${r.id}`}
                    aria-label={`View ${r.label} detail`}
                    title={`${r.label} · Arena ${(r.arena * 100).toFixed(1)} · click for detail`}
                    className="relative mx-auto block w-[68%] max-w-[62px] cursor-pointer rounded-t-[3px] transition-opacity group-hover:opacity-80"
                    style={{ height: `${Math.max(barH, 1.2)}%`, backgroundColor: r.color }}
                  >
                    <span aria-hidden className="absolute inset-0 rounded-t-[3px] ring-brand/40 transition-shadow group-hover:ring-2" />
                  </Link>
                  {/* CI whisker */}
                  {showCi ? (
                    <div
                      aria-hidden
                      className="pointer-events-none absolute left-1/2 w-2 -translate-x-1/2"
                      style={{ bottom: `${loH}%`, height: `${Math.max(hiH - loH, 0.4)}%` }}
                    >
                      <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-ink/45" />
                      <span className="absolute left-0 right-0 top-0 h-px bg-ink/45" />
                      <span className="absolute bottom-0 left-0 right-0 h-px bg-ink/45" />
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        </div>

        {/* x-axis labels */}
        <div className="mt-2 flex justify-between gap-2 border-t border-hairline pt-2 sm:gap-3">
          {rows.map((r) => (
            <Link
              key={r.id}
              href={`/agents/${r.id}`}
              className="group min-w-0 flex-1 text-center"
              title={`View ${r.label} detail`}
            >
              <span className="flex items-center justify-center gap-1">
                <span className="h-2 w-2 shrink-0 rounded-[2px]" style={{ backgroundColor: r.color }} />
                <span className="truncate text-[10px] font-medium leading-tight text-ink group-hover:text-brand sm:text-[11px]">
                  {r.label}
                </span>
              </span>
            </Link>
          ))}
        </div>

        {/* footer */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-hairline pt-3 text-[11px] text-muted-2">
          <span className="tnum">
            <T en="Arena Score x100 · " zh="竞技场得分 x100 · " />
            <span className="font-mono">{formula}</span>
          </span>
          <span className="uppercase tracking-wider">
            <T en="Higher is better · whisker = 95% CI" zh="越高越好 · 须线 = 95% 置信区间" />
          </span>
        </div>
      </div>
    </section>
  )
}

function PreviewPill() {
  return (
    <span className="inline-flex items-center rounded-full border border-hairline bg-surface-low px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-2">
      <T en="Preview · 13-task subset" zh="预览 · 13 题子集" />
    </span>
  )
}
