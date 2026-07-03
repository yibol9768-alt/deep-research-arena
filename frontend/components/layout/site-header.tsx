'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { Menu, X, Activity, ChevronDown, Github } from 'lucide-react'
import { cn } from '@/lib/cn'
import { T } from '@/components/i18n/t'
import { LangToggle } from '@/components/i18n/lang-toggle'

const NAV = [
  { href: '/', label: 'Leaderboard', zh: '排行榜' },
  { href: '/models', label: 'Models', zh: '模型榜' },
  { href: '/agents', label: 'Agents', zh: '智能体' },
  { href: '/tasks', label: 'Tasks', zh: '任务' },
  { href: '/arena', label: 'Arena', zh: '竞技场' },
  { href: '/insights', label: 'Insights', zh: '洞察' },
  { href: '/methodology', label: 'Methodology', zh: '方法论' },
]

const MORE = [
  { href: '/pillars', label: 'Pillars', zh: '评测维度' },
  { href: '/sandbox', label: 'Sandbox', zh: '沙箱' },
  { href: '/annotate', label: 'Annotate', zh: '标注' },
  { href: '/status', label: 'Status', zh: '基准状态' },
  { href: '/changelog', label: 'Changelog', zh: '更新日志' },
  { href: '/about', label: 'About', zh: '关于' },
]

export function SiteHeader() {
  const pathname = usePathname() ?? '/'
  const [open, setOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const moreRef = useRef<HTMLDivElement>(null)

  const isActive = (href: string) => (href === '/' ? pathname === '/' : pathname.startsWith(href))
  const moreActive = MORE.some((m) => isActive(m.href))

  // Close the "More" panel on outside click.
  useEffect(() => {
    if (!moreOpen) return
    const onDown = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) setMoreOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [moreOpen])

  return (
    <header className="sticky top-0 z-50 w-full border-b border-hairline bg-white/90 backdrop-blur-md">
      <div className="container flex h-16 items-center justify-between gap-4">
        {/* Brand: black pill, AA-style */}
        <Link href="/" className="flex shrink-0 items-center gap-2 rounded-pill bg-ink px-4 py-2 text-white transition-colors hover:bg-ink-soft">
          <Activity className="h-3.5 w-3.5" strokeWidth={2.5} />
          <span className="text-sm font-semibold tracking-tight">Deep Research Arena</span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden flex-1 items-center justify-center gap-1 lg:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'rounded-pill px-3.5 py-2 text-sm transition-colors duration-150',
                isActive(item.href)
                  ? 'bg-surface-mid font-medium text-ink'
                  : 'text-muted hover:bg-surface-low hover:text-ink',
              )}
            >
              <T en={item.label} zh={item.zh} />
            </Link>
          ))}
          {/* More */}
          <div ref={moreRef} className="relative">
            <button
              onClick={() => setMoreOpen((v) => !v)}
              className={cn(
                'flex items-center gap-1 rounded-pill px-3.5 py-2 text-sm transition-colors duration-150',
                moreActive || moreOpen
                  ? 'bg-surface-mid font-medium text-ink'
                  : 'text-muted hover:bg-surface-low hover:text-ink',
              )}
            >
              <T en="More" zh="更多" />
              <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', moreOpen && 'rotate-180')} />
            </button>
            {moreOpen && (
              <div className="absolute left-1/2 top-full z-50 mt-2 w-48 -translate-x-1/2 rounded-xl border border-hairline bg-white p-1.5 shadow-lift">
                {MORE.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMoreOpen(false)}
                    className={cn(
                      'block rounded-lg px-3 py-2 text-sm transition-colors',
                      isActive(item.href) ? 'bg-surface-mid font-medium text-ink' : 'text-muted hover:bg-surface-low hover:text-ink',
                    )}
                  >
                    <T en={item.label} zh={item.zh} />
                  </Link>
                ))}
              </div>
            )}
          </div>
        </nav>

        {/* Right cluster */}
        <div className="flex items-center gap-2">
          <LangToggle className="hidden md:inline-flex" />
          <a
            href="https://github.com/yibol9768-alt/deep-research-arena"
            target="_blank"
            rel="noreferrer"
            aria-label="GitHub"
            className="hidden h-9 w-9 items-center justify-center rounded-pill text-muted transition-colors hover:bg-surface-low hover:text-ink md:inline-flex"
          >
            <Github className="h-4 w-4" />
          </a>
          <a
            href="/contribute"
            className="hidden h-9 items-center rounded-pill bg-ink px-4 text-sm font-medium text-white transition-colors hover:bg-ink-soft md:inline-flex"
          >
            <T en="Contribute" zh="贡献" />
          </a>
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
        <div className="border-t border-hairline bg-white/95 backdrop-blur-md lg:hidden">
          <nav className="container flex flex-col py-3">
            {[...NAV, ...MORE].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className={cn(
                  'rounded-tab px-3 py-2.5 text-sm transition-colors',
                  isActive(item.href) ? 'bg-surface-mid font-medium text-ink' : 'text-muted hover:bg-surface-low hover:text-ink',
                )}
              >
                <T en={item.label} zh={item.zh} />
              </Link>
            ))}
            <div className="mt-2 flex items-center gap-2 border-t border-hairline px-3 pt-3">
              <a href="/contribute" className="inline-flex h-9 flex-1 items-center justify-center rounded-pill bg-ink px-3 text-sm font-medium text-white">
                <T en="Contribute" zh="贡献" />
              </a>
              <a href="https://github.com/yibol9768-alt/deep-research-arena" aria-label="GitHub" className="p-2 text-muted"><Github className="h-4 w-4" /></a>
              <LangToggle />
            </div>
          </nav>
        </div>
      )}
    </header>
  )
}
