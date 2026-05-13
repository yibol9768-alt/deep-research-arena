'use client'

import { useEffect, useState } from 'react'
import { cn } from '@/lib/cn'

interface Item {
  id: string
  label: string
}

export function SectionNav({ items }: { items: Item[] }) {
  const [active, setActive] = useState(items[0]?.id)

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) setActive(e.target.id)
        })
      },
      { rootMargin: '-30% 0px -55% 0px' },
    )
    items.forEach((i) => {
      const el = document.getElementById(i.id)
      if (el) observer.observe(el)
    })
    return () => observer.disconnect()
  }, [items])

  return (
    <aside className="hidden w-56 shrink-0 lg:block">
      <div className="sticky top-24 flex flex-col gap-1 border-r border-hairline pr-6">
        <h3 className="px-2 pb-3 text-caps uppercase tracking-wider text-muted">On this page</h3>
        {items.map((i) => (
          <a
            key={i.id}
            href={`#${i.id}`}
            className={cn(
              'group flex items-center gap-2.5 rounded-tab px-2 py-2 text-sm transition-colors',
              active === i.id ? 'text-ink' : 'text-muted hover:text-ink',
            )}
          >
            <span
              className={cn(
                'inline-block h-2 w-2 transition-all',
                active === i.id ? 'bg-brand' : 'bg-hairline group-hover:bg-muted',
              )}
            />
            <span className={cn(active === i.id ? 'font-medium' : '')}>{i.label}</span>
          </a>
        ))}
      </div>
    </aside>
  )
}
