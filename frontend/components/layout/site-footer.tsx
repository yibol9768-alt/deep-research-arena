import Link from 'next/link'
import { Github, Twitter, Linkedin, MessageCircle } from 'lucide-react'

const COLS: { title: string; links: { href: string; label: string }[] }[] = [
  {
    title: 'Explore',
    links: [
      { href: '/', label: 'Leaderboard' },
      { href: '/agents', label: 'Agents' },
      { href: '/tasks', label: 'Tasks' },
      { href: '/pillars', label: 'Pillars' },
      { href: '/arena', label: 'Live Arena' },
    ],
  },
  {
    title: 'Project',
    links: [
      { href: '/methodology', label: 'Methodology' },
      { href: '/sandbox', label: 'Sandbox' },
      { href: '/insights', label: 'Findings' },
      { href: '/about', label: 'About' },
      { href: '/contribute', label: 'Contribute' },
    ],
  },
  {
    title: 'Resources',
    links: [
      { href: '/methodology', label: 'Paper notes' },
      { href: 'https://github.com/yibol9768-alt/deep-research-arena', label: 'GitHub' },
      { href: '/api/leaderboard', label: 'API' },
      { href: '/changelog', label: 'Changelog' },
    ],
  },
]

export function SiteFooter({ lastUpdated }: { lastUpdated?: string }) {
  return (
    <footer className="mt-24 bg-brand-footer text-brand-dark">
      <div className="container py-14">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-12">
          {/* Brand + newsletter */}
          <div className="md:col-span-5">
            <h3 className="font-serif text-4xl leading-none">
              Deep Research<br />Arena
            </h3>
            <p className="mt-4 max-w-sm text-sm text-brand-dark/80">
              The first reproducible Elo benchmark for Deep Research agents. Open source. Open data. Open methodology.
            </p>
            <form className="mt-6 flex w-full max-w-md gap-2 rounded-tab border border-brand-dark/20 bg-white/30 p-1.5 backdrop-blur-sm">
              <input
                type="email"
                placeholder="Subscribe to research updates"
                className="flex-1 bg-transparent px-3 py-2 text-sm placeholder:text-brand-dark/60 focus:outline-none"
              />
              <button className="rounded-tab bg-brand-dark px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white hover:bg-brand-dark/90">
                Subscribe
              </button>
            </form>
          </div>

          {/* Link columns */}
          {COLS.map((col) => (
            <div key={col.title} className="md:col-span-2">
              <h4 className="text-caps uppercase tracking-wider text-brand-dark/70">{col.title}</h4>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link
                      href={l.href}
                      className="text-sm text-brand-dark/90 transition-colors hover:text-brand-dark hover:underline underline-offset-4"
                    >
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {/* Socials */}
          <div className="md:col-span-1">
            <h4 className="text-caps uppercase tracking-wider text-brand-dark/70">Follow</h4>
            <div className="mt-4 flex gap-3">
              <a href="https://github.com/yibol9768-alt/deep-research-arena" aria-label="GitHub" className="text-brand-dark/80 hover:text-brand-dark"><Github className="h-4 w-4" /></a>
              <a href="#" aria-label="Twitter" className="text-brand-dark/80 hover:text-brand-dark"><Twitter className="h-4 w-4" /></a>
              <a href="#" aria-label="LinkedIn" className="text-brand-dark/80 hover:text-brand-dark"><Linkedin className="h-4 w-4" /></a>
              <a href="#" aria-label="Discord" className="text-brand-dark/80 hover:text-brand-dark"><MessageCircle className="h-4 w-4" /></a>
            </div>
          </div>
        </div>

        <div className="mt-12 flex flex-col items-start justify-between gap-3 border-t border-brand-dark/15 pt-6 text-xs text-brand-dark/70 md:flex-row md:items-center">
          <p>© {new Date().getFullYear()} Deep Research Arena. Trademarks belong to their owners.</p>
          <p className="tnum">
            {lastUpdated ? <>Last leaderboard rebuild: <span className="font-medium text-brand-dark">{lastUpdated}</span></> : null}
          </p>
        </div>
      </div>
    </footer>
  )
}
