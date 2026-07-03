'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { Menu, X, Activity, ChevronDown } from 'lucide-react'
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
    <header className="sticky top-0 z-50 w-full border-b border-night-line bg-night/90 text-white backdrop-blur-md">
      <div className="container flex h-16 items-center justify-between gap-6">
        {/* Brand */}
        <Link href="/" className="group flex shrink-0 items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-[9px] bg-gradient-to-br from-brand to-brand-glow shadow-[0_0_20px_rgba(110,91,255,0.45)]">
            <Activity className="h-4 w-4 text-white" strokeWidth={2.5} />
          </span>
          <span className="flex flex-col leading-none">
            <span className="text-[15px] font-semibold tracking-tight">Deep Research Arena</span>
            <span className="mt-1 text-[10px] font-medium uppercase tracking-[0.14em] text-night-faint">
              <T en="Truth-gated evaluation" zh="真值门控评测" />
            </span>
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden flex-1 items-center justify-center gap-1 lg:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'relative rounded-pill px-3 py-1.5 text-sm transition-colors duration-150',
                isActive(item.href)
                  ? 'bg-white/10 font-medium text-white'
                  : 'text-white/60 hover:bg-white/5 hover:text-white',
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
                'flex items-center gap-1 rounded-pill px-3 py-1.5 text-sm transition-colors duration-150',
                moreActive || moreOpen
                  ? 'bg-white/10 font-medium text-white'
                  : 'text-white/60 hover:bg-white/5 hover:text-white',
              )}
            >
              <T en="More" zh="更多" />
              <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', moreOpen && 'rotate-180')} />
            </button>
            {moreOpen && (
              <div className="absolute left-1/2 top-full z-50 mt-2 w-48 -translate-x-1/2 rounded-xl border border-night-line bg-night-soft p-1.5 shadow-[0_24px_60px_-16px_rgba(0,0,0,0.8)]">
                {MORE.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMoreOpen(false)}
                    className={cn(
                      'block rounded-lg px-3 py-2 text-sm transition-colors',
                      isActive(item.href) ? 'bg-white/10 font-medium text-white' : 'text-white/65 hover:bg-white/5 hover:text-white',
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
        <div className="flex items-center gap-2.5">
          <LangToggle className="hidden md:inline-flex" />
          <a
            href="https://github.com/yibol9768-alt/deep-research-arena"
            target="_blank"
            rel="noreferrer"
            className="hidden text-xs font-medium text-white/60 hover:text-white md:inline-flex"
          >
            GitHub
          </a>
          <a
            href="/contribute"
            className="hidden h-8 items-center rounded-pill bg-white px-3.5 text-sm font-medium text-night transition-colors hover:bg-white/85 md:inline-flex"
          >
            <T en="Contribute" zh="贡献" />
          </a>
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-tab text-white lg:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-label="Toggle menu"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile drawer */}
      {open && (
        <div className="border-t border-night-line bg-night/95 backdrop-blur-md lg:hidden">
          <nav className="container flex flex-col py-3">
            {[...NAV, ...MORE].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className={cn(
                  'rounded-tab px-3 py-2.5 text-sm transition-colors',
                  isActive(item.href) ? 'bg-white/10 font-medium text-white' : 'text-white/65 hover:bg-white/5 hover:text-white',
                )}
              >
                <T en={item.label} zh={item.zh} />
              </Link>
            ))}
            <div className="mt-2 flex items-center gap-2 border-t border-night-line px-3 pt-3">
              <a href="/contribute" className="inline-flex h-8 flex-1 items-center justify-center rounded-pill bg-white px-3 text-sm font-medium text-night">
                <T en="Contribute" zh="贡献" />
              </a>
              <a href="https://github.com/yibol9768-alt/deep-research-arena" className="text-xs text-white/60">GitHub</a>
              <LangToggle />
            </div>
          </nav>
        </div>
      )}

      {/* Live run indicator (1px breathing line) */}
      <div className="night-divider-glow h-px w-full animate-breathe" />
    </header>
  )
}
