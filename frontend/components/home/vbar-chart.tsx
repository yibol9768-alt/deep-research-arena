import type { ReactNode } from 'react'
import { T } from '@/components/i18n/t'

export interface VBarRow {
  id: string
  label: string
  color: string
  value: number
  /** Formatted value shown above the bar (defaults to rounded value). */
  valueLabel?: string
}

interface Props {
  /** Small colored square next to the title (AA-style section marker). */
  accent: string
  title: ReactNode
  subtitle: ReactNode
  rows: VBarRow[]
  /** Optional pill badge next to the title. */
  badge?: ReactNode
}

/**
 * Artificial-Analysis-style vertical bar chart: one saturated color per agent,
 * value labels above the bars, dotted gridlines, rotated labels underneath.
 * Pure CSS — renders on the server, no client JS.
 */
export function VBarChart({ accent, title, subtitle, rows, badge }: Props) {
  const max = Math.max(...rows.map((r) => r.value), 1)

  return (
    <article className="card p-5">
      <header className="flex items-center gap-2.5">
        <span className="h-3.5 w-3.5 shrink-0 rounded-[2px]" style={{ backgroundColor: accent }} />
        <h3 className="font-serif text-xl text-ink">{title}</h3>
        {badge}
      </header>
      <p className="mt-1.5 text-xs text-muted">{subtitle}</p>

      {/* Plot area */}
      <div className="relative mt-5 h-48">
        {/* dotted gridlines at 25/50/75/100% */}
        {[0, 25, 50, 75].map((p) => (
          <div
            key={p}
            aria-hidden
            className="absolute inset-x-0 border-t border-dotted border-hairline"
            style={{ top: `${p}%` }}
          />
        ))}
        <div className="absolute inset-0 flex items-end justify-between gap-1.5 sm:gap-2">
          {rows.map((r) => {
            // Cap at 86% so the value label above the tallest bar stays inside
            // the plot area.
            const h = Math.max((r.value / max) * 86, 1.5)
            return (
              <div key={r.id} className="group flex h-full min-w-0 flex-1 flex-col items-center justify-end">
                <span className="mb-1 text-[10px] font-semibold tnum leading-none text-ink">
                  {r.valueLabel ?? String(Math.round(r.value))}
                </span>
                <div
                  className="w-full max-w-[40px] rounded-t-[3px] transition-opacity group-hover:opacity-80"
                  style={{ height: `${h}%`, backgroundColor: r.color }}
                  title={`${r.label}: ${r.valueLabel ?? r.value}`}
                />
              </div>
            )
          })}
        </div>
      </div>

      {/* Rotated labels */}
      <div className="mt-1.5 flex justify-between gap-1.5 border-t border-hairline pt-1 sm:gap-2">
        {rows.map((r) => (
          <div key={r.id} className="relative h-[72px] min-w-0 flex-1">
            <span
              className="absolute left-1/2 top-1.5 origin-top-left -rotate-45 whitespace-nowrap text-[10px] leading-none text-muted"
              style={{ transform: 'translateX(-2px) rotate(-45deg)', transformOrigin: 'top right', right: '50%', left: 'auto' }}
            >
              {r.label}
            </span>
          </div>
        ))}
      </div>

      <p className="mt-1 text-right text-[10px] uppercase tracking-wider text-muted-2">
        <T en="Higher is better" zh="越高越好" />
      </p>
    </article>
  )
}
