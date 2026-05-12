'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Github, Menu } from 'lucide-react';
import * as React from 'react';
import { cn } from '@/lib/utils';
import { GITHUB_URL } from '@/lib/constants';

const navItems = [
  { href: '/', label: 'Leaderboard', match: (p: string) => p === '/' },
  { href: '/v4/', label: 'v4', badge: 'NEW', match: (p: string) => p.startsWith('/v4') },
  { href: '/compare/', label: 'Compare', match: (p: string) => p.startsWith('/compare') },
  { href: '/how-it-works/', label: 'Methodology', match: (p: string) => p.startsWith('/how-it-works') },
  { href: '/about/', label: 'About', match: (p: string) => p.startsWith('/about') },
  { href: '/contribute/', label: 'Contribute', match: (p: string) => p.startsWith('/contribute') },
  { href: '/audit/', label: 'Audit', match: (p: string) => p.startsWith('/audit') },
];

export function SiteHeader() {
  const pathname = usePathname() || '/';
  const [open, setOpen] = React.useState(false);
  return (
    <header className="sticky top-0 z-30 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/85">
      <div className="container-page flex h-12 items-center gap-4">
        <Link href="/" className="flex items-center gap-2 font-semibold flex-shrink-0">
          <span className="inline-flex h-6 w-6 items-center justify-center rounded bg-primary text-[10px] font-bold tracking-tight text-primary-foreground">DR</span>
          <span className="text-[14px] tracking-tight">Deep-Research Arena</span>
        </Link>
        <nav className="hidden lg:flex items-center gap-0.5 ml-4" aria-label="Main">
          {navItems.map((item) => {
            const active = item.match(pathname);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'relative inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors',
                  active
                    ? 'text-foreground after:absolute after:bottom-[-13px] after:left-2 after:right-2 after:h-[2px] after:bg-foreground'
                    : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground'
                )}
              >
                {item.label}
                {item.badge && (
                  <span className="ml-0.5 rounded bg-accent/15 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider text-accent">
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener"
            className="hidden lg:inline-flex h-8 items-center gap-1.5 rounded-md border border-input bg-background px-3 text-[12.5px] font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <Github className="h-3.5 w-3.5" />
            GitHub
          </a>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-input lg:hidden"
            aria-label="Open menu"
          >
            <Menu className="h-4 w-4" />
          </button>
        </div>
      </div>
      {open && (
        <div className="lg:hidden border-t bg-background">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'block border-b border-border/60 px-4 py-3 text-sm',
                item.match(pathname) ? 'bg-secondary font-semibold text-foreground' : 'text-muted-foreground'
              )}
              onClick={() => setOpen(false)}
            >
              {item.label}
              {item.badge && (
                <span className="ml-1.5 rounded bg-accent/15 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider text-accent">
                  {item.badge}
                </span>
              )}
            </Link>
          ))}
          <a href={GITHUB_URL} target="_blank" rel="noopener" className="block border-b border-border/60 px-4 py-3 text-sm text-muted-foreground">
            GitHub ↗
          </a>
        </div>
      )}
    </header>
  );
}
