import { type HTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

interface Props extends HTMLAttributes<HTMLSpanElement> {
  active?: boolean
  tone?: 'default' | 'brand'
}

export function Chip({ className, active, tone = 'default', ...rest }: Props) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-pill border px-3 py-1 text-xs font-medium transition-colors duration-150 cursor-pointer select-none',
        active && tone === 'brand' && 'bg-brand text-white border-brand',
        active && tone === 'default' && 'bg-ink text-white border-ink',
        !active && 'bg-white text-ink border-hairline hover:border-ink/30',
        className,
      )}
      {...rest}
    />
  )
}
