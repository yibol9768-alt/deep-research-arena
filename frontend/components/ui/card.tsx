import { forwardRef, type HTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

interface Props extends HTMLAttributes<HTMLDivElement> {
  lift?: boolean
}

export const Card = forwardRef<HTMLDivElement, Props>(function Card({ className, lift = false, ...rest }, ref) {
  return <div ref={ref} className={cn('card', lift && 'card-lift', className)} {...rest} />
})

export function CardHeader({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('px-5 pt-5 pb-3', className)} {...rest} />
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('px-5 pb-5', className)} {...rest} />
}

export function CardTitle({ className, ...rest }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn('font-serif text-lg leading-tight text-ink', className)} {...rest} />
}

export function CardSubtitle({ className, ...rest }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('mt-0.5 text-xs text-muted', className)} {...rest} />
}
