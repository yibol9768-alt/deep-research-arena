import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export function MetricCard({
  label,
  value,
  detail,
  className,
}: {
  label: string
  value: string
  detail?: string
  className?: string
}) {
  return (
    <div className={cn('card p-5', className)}>
      <p className="label-caps">{label}</p>
      <p className="mt-2 font-serif text-4xl leading-none text-ink tnum">{value}</p>
      {detail ? <p className="mt-2 text-xs leading-relaxed text-muted">{detail}</p> : null}
    </div>
  )
}

export function PageHero({
  eyebrow,
  title,
  intro,
  children,
}: {
  eyebrow: string
  title: string
  intro: string
  children?: ReactNode
}) {
  return (
    <header className="container py-12 md:py-16">
      <div className="max-w-4xl">
        <span className="label-caps">{eyebrow}</span>
        <h1 className="mt-3 max-w-4xl font-serif text-h-md leading-tight md:text-display-lg">{title}</h1>
        <p className="mt-4 max-w-3xl text-base leading-relaxed text-muted md:text-lg">{intro}</p>
      </div>
      {children ? <div className="mt-8">{children}</div> : null}
    </header>
  )
}
