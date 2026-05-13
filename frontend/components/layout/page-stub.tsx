import Link from 'next/link'
import { ArrowRight, Construction } from 'lucide-react'
import { cn } from '@/lib/cn'

interface Props {
  eyebrow: string
  title: string
  intro: string
  /** Bullet-list of what the page WILL contain when fully built */
  upcoming: { label: string; description: string }[]
  /** Where related complete content lives */
  related?: { href: string; label: string }[]
}

export function PageStub({ eyebrow, title, intro, upcoming, related = [] }: Props) {
  return (
    <div className="container py-12 md:py-16">
      <div className="max-w-3xl">
        <div className="flex items-center gap-2">
          <span className="label-caps">{eyebrow}</span>
          <span className="rounded-pill bg-warn/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-warn">
            <Construction className="mr-1 inline h-3 w-3" />
            Under construction
          </span>
        </div>
        <h1 className="mt-3 font-serif text-h-md md:text-display-lg leading-tight">{title}</h1>
        <p className="mt-3 text-base leading-relaxed text-muted md:text-lg">{intro}</p>
      </div>

      <div className="mt-10 grid grid-cols-1 gap-3 md:grid-cols-2">
        {upcoming.map((u, i) => (
          <article
            key={u.label}
            className={cn(
              'card p-5 transition-all hover:shadow-soft',
              i === 0 && 'border-brand/30 bg-brand/[0.03]',
            )}
          >
            <h3 className="font-serif text-base text-ink">{u.label}</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">{u.description}</p>
          </article>
        ))}
      </div>

      {related.length > 0 && (
        <div className="mt-12 border-t border-hairline pt-8">
          <h2 className="text-caps uppercase tracking-wider text-muted">Already shipped</h2>
          <ul className="mt-4 flex flex-wrap gap-3">
            {related.map((r) => (
              <li key={r.href}>
                <Link
                  href={r.href}
                  className="inline-flex items-center gap-1.5 rounded-pill border border-hairline bg-white px-3 py-1.5 text-sm text-ink transition-all hover:border-ink/30 hover:shadow-soft"
                >
                  {r.label}
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
