'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import { Search, Menu, X, Activity } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/cn'

const NAV = [
  { href: '/', label: 'Leaderboard' },
  { href: '/agents', label: 'Agents' },
  { href: '/tasks', label: 'Tasks' },
  { href: '/pillars', label: 'Pillars' },
  { href: '/arena', label: 'Arena' },
  { href: '/insights', label: 'Insights' },
  { href: '/methodology', label: 'Methodology' },
]

export function SiteHeader() {
  const pathname = usePathname() ?? '/'
  const [open, setOpen] = useState(false)

  const isActive = (href: string) => (href === '/' ? pathname === '/' : pathname.startsWith(href))

  return (
    <header className="sticky top-0 z-50 w-full border-b border-hairline bg-bg/85 backdrop-blur-md">
      <div className="container flex h-16 items-center justify-between gap-6">
        {/* Brand */}
        <Link href="/" className="flex shrink-0 items-center gap-2 rounded-pill bg-ink px-4 py-1.5 text-white">
          <Activity className="h-3.5 w-3.5" strokeWidth={2.5} />
          <span className="text-sm font-medium tracking-tight">Deep Research Arena</span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden flex-1 items-center justify-center gap-6 lg:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'text-sm transition-colors duration-150',
                isActive(item.href) ? 'font-medium text-ink' : 'text-muted hover:text-ink',
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        {/* Right cluster */}
        <div className="flex items-center gap-2">
          <button
            className="hidden h-9 w-9 items-center justify-center rounded-tab text-muted transition-colors hover:bg-surface-low hover:text-ink md:inline-flex"
            aria-label="Search"
          >
            <Search className="h-4 w-4" />
          </button>
          <a
            href="https://github.com/"
            target="_blank"
            rel="noreferrer"
            className="hidden text-xs font-medium text-muted hover:text-ink md:inline-flex"
          >
            GitHub
          </a>
          <Button variant="primary" size="sm" className="hidden md:inline-flex">
            Sign in
          </Button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-tab text-ink lg:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-label="Toggle menu"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile drawer */}
      {open && (
        <div className="border-t border-hairline bg-bg/95 backdrop-blur-md lg:hidden">
          <nav className="container flex flex-col py-3">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className={cn(
                  'rounded-tab px-3 py-2.5 text-sm transition-colors',
                  isActive(item.href) ? 'bg-surface-mid font-medium text-ink' : 'text-muted hover:bg-surface-low hover:text-ink',
                )}
              >
                {item.label}
              </Link>
            ))}
            <div className="mt-2 flex items-center gap-2 px-3 pt-3 hairline-t">
              <Button variant="primary" size="sm" className="flex-1">Sign in</Button>
              <a href="https://github.com/" className="text-xs text-muted">GitHub</a>
            </div>
          </nav>
        </div>
      )}

      {/* Live run indicator (1px breathing line) */}
      <div className="h-px w-full bg-gradient-to-r from-transparent via-brand/50 to-transparent animate-breathe" />
    </header>
  )
}
