import { cn } from '@/lib/cn'

/**
 * QualityProfile renders a per-agent breakdown of the v3 raw quality pillars
 * (0-1 scores from per_agent_profile). Each row is a label + 10-segment bar
 * + numeric value. Missing values render as a faint placeholder so the
 * component degrades gracefully when v3 fields are absent.
 */
export interface QualityProfileProps {
  /** Optional accent color to tint filled segments. Falls back to brand. */
  accentColor?: string
  /** Whether the data is a synthetic / dry-run placeholder. */
  synthetic?: boolean
  /** Raw 0-1 scores. */
  depth?: number
  rigor?: number
  style?: number
  coverage?: number
  checklist?: number
  urlVeracity?: number
}

interface Row {
  label: string
  value: number | undefined
}

const SEGMENTS = 10

export function QualityProfile({
  accentColor,
  synthetic,
  depth,
  rigor,
  style,
  coverage,
  checklist,
  urlVeracity,
}: QualityProfileProps) {
  const rows: Row[] = [
    { label: 'Depth', value: depth },
    { label: 'Rigor', value: rigor },
    { label: 'Style', value: style },
    { label: 'Coverage', value: coverage },
    { label: 'Checklist', value: checklist },
    { label: 'URL Veracity', value: urlVeracity },
  ]

  const anyValue = rows.some((r) => typeof r.value === 'number')
  const accent = accentColor ?? '#7F4BF3'

  return (
    <section className="card p-6">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="font-serif text-h-sm text-ink">Quality Profile</h2>
          <p className="mt-1 text-xs text-muted">
            Raw per-pillar means on the v3 scoring rubric (0-1 scale).
          </p>
        </div>
        {synthetic ? (
          <span className="rounded-pill bg-warn/10 px-2 py-0.5 text-[11px] font-medium text-warn">
            SYNTHETIC
          </span>
        ) : null}
      </header>

      {!anyValue ? (
        <p className="py-4 text-sm text-muted">
          Quality-pillar data is not available for this agent yet.
        </p>
      ) : (
        <ul className="hairline-t flex flex-col gap-3 pt-4">
          {rows.map((row) => (
            <QualityRow key={row.label} label={row.label} value={row.value} accent={accent} />
          ))}
        </ul>
      )}
    </section>
  )
}

function QualityRow({
  label,
  value,
  accent,
}: {
  label: string
  value: number | undefined
  accent: string
}) {
  const has = typeof value === 'number'
  // Clamp v in [0,1] for segment count; treat NaN as zero.
  const v = has ? Math.max(0, Math.min(1, value as number)) : 0
  const filled = Math.round(v * SEGMENTS)

  return (
    <li className="flex items-center gap-4">
      <span className="w-28 shrink-0 text-xs text-muted">{label}</span>
      <div className="flex flex-1 items-center gap-0.5" aria-hidden={!has}>
        {Array.from({ length: SEGMENTS }).map((_, i) => {
          const on = i < filled
          return (
            <span
              key={i}
              className={cn(
                'h-3 flex-1 rounded-sm',
                on ? '' : 'bg-surface-mid',
              )}
              style={on ? { backgroundColor: accent, opacity: 0.35 + 0.65 * ((i + 1) / SEGMENTS) } : undefined}
            />
          )
        })}
      </div>
      <span
        className={cn(
          'w-12 shrink-0 text-right text-sm tnum',
          has ? 'text-ink' : 'text-muted-2',
        )}
      >
        {has ? (value as number).toFixed(2) : '—'}
      </span>
    </li>
  )
}
