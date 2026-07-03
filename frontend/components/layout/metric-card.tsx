import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export function MetricCard({
  label,
  value,
  detail,
  className,
}: {
  label: ReactNode
  value: string
  detail?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('card px-4 py-3.5', className)}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-2">{label}</p>
      <p className="mt-1 font-serif text-2xl leading-none text-ink tnum">{value}</p>
      {detail ? <p className="mt-1 text-[11px] leading-snug text-muted">{detail}</p> : null}
    </div>
  )
}

export function PageHero({
  eyebrow,
  title,
  intro,
  children,
}: {
  eyebrow: ReactNode
  title: ReactNode
  intro: ReactNode
  children?: ReactNode
}) {
  return (
    <header className="mb-8 border-b border-hairline bg-white">
      <div className="container py-8 md:py-10">
        <div className="max-w-4xl">
          <span className="flex items-center gap-2">
            <span className="aa-square !h-2.5 !w-2.5" />
            <span className="label-caps">{eyebrow}</span>
          </span>
          <h1 className="mt-2.5 max-w-3xl font-serif text-h-sm leading-tight md:text-h-md">{title}</h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted md:text-base">{intro}</p>
        </div>
        {children ? <div className="mt-6">{children}</div> : null}
      </div>
    </header>
  )
}
