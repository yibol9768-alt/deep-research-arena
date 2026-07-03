import Link from 'next/link'
import { ArrowUpRight, ArrowDown, Swords, BookOpen } from 'lucide-react'
import { T } from '@/components/i18n/t'
import type { ChangelogEntry } from '@/lib/data/changelog'

interface Stat {
  value: string
  label: string
  zh?: string
}

interface Props {
  stats: Stat[]
  news: ChangelogEntry[]
}

/**
 * Artificial-Analysis-style hero: big serif headline on white, quiet CTAs,
 * a right-hand news rail fed by the changelog, and a hairline stat strip.
 */
export function Hero({ stats, news }: Props) {
  return (
    <section className="border-b border-hairline bg-white">
      <div className="container grid grid-cols-1 gap-12 py-14 md:py-20 lg:grid-cols-[1fr_360px] lg:gap-20">
        {/* Copy */}
        <div>
          <h1 className="font-serif text-display max-w-3xl text-balance leading-[1.04] text-ink">
            <T
              en="Independent, truth-gated analysis of Deep Research agents"
              zh="面向 Deep Research 智能体的独立真值门控评测"
            />
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-relaxed text-muted md:text-lg">
            <T
              en="Open-source research agents run against the same frozen sandbox. Every cited URL is fetched, every quoted passage is checked — the public score only rises when the report and its evidence both hold up."
              zh="开源研究智能体在同一套冻结沙箱中运行。每个引用 URL 都会被抓取、每段引文都会被核对 —— 只有报告与证据同时站得住,公开主分才会上升。"
            />
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-2.5">
            <Link
              href="#leaderboard"
              className="group inline-flex h-10 items-center gap-2 rounded-pill bg-ink px-5 text-sm font-medium text-white transition-colors hover:bg-ink-soft"
            >
              <T en="Explore the leaderboard" zh="浏览排行榜" />
              <ArrowDown className="h-4 w-4 transition-transform duration-200 group-hover:translate-y-0.5" />
            </Link>
            <Link
              href="/arena"
              className="inline-flex h-10 items-center gap-2 rounded-pill border border-hairline bg-white px-4 text-sm font-medium text-ink transition-all hover:border-ink/30 hover:bg-surface-low"
            >
              <Swords className="h-4 w-4" />
              <T en="Open Arena" zh="打开竞技场" />
            </Link>
            <Link
              href="/methodology"
              className="inline-flex h-10 items-center gap-2 rounded-pill border border-hairline bg-white px-4 text-sm font-medium text-ink transition-all hover:border-ink/30 hover:bg-surface-low"
            >
              <BookOpen className="h-4 w-4" />
              <T en="Methodology" zh="方法论" />
            </Link>
          </div>
        </div>

        {/* News rail (from the changelog — real shipped updates) */}
        <aside className="hidden lg:block">
          <div className="divide-y divide-hairline border-t border-hairline">
            {news.map((n) => (
              <Link key={n.version} href="/changelog" className="group block py-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-brand">
                      {(n.tags[0] ?? 'update').toUpperCase()} · <span className="tnum">{n.date}</span>
                    </p>
                    <h3 className="mt-1.5 text-sm font-semibold leading-snug text-ink group-hover:underline underline-offset-4">
                      {n.title}
                    </h3>
                    <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-muted">{n.summary}</p>
                  </div>
                  <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-hairline text-muted transition-colors group-hover:border-ink/30 group-hover:text-ink">
                    <ArrowUpRight className="h-3.5 w-3.5" />
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </aside>
      </div>

      {/* Stat strip */}
      <div className="border-t border-hairline">
        <dl className="container grid grid-cols-2 divide-hairline lg:grid-cols-5 lg:divide-x">
          {stats.map((s) => (
            <div key={s.label} className="px-2 py-5 text-center last:col-span-2 lg:last:col-span-1">
              <dd className="font-serif text-3xl tnum text-ink">{s.value}</dd>
              <dt className="mt-1 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-2">
                <T en={s.label} zh={s.zh ?? s.label} />
              </dt>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}
