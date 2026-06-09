import { ArrowRight, BookOpen, Github, Swords } from 'lucide-react'
import Link from 'next/link'
import { T } from '@/components/i18n/t'

interface Stat {
  value: string
  label: string
  zh?: string
}

interface Props {
  stats: Stat[]
}

export function Hero({ stats }: Props) {
  return (
    <section className="relative overflow-hidden">
      {/* Soft dotted backdrop */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 opacity-50"
        style={{
          backgroundImage: 'radial-gradient(circle at 2px 2px, rgba(110,91,255,0.14) 1px, transparent 0)',
          backgroundSize: '24px 24px',
          maskImage: 'radial-gradient(ellipse 80% 60% at 50% 30%, black, transparent)',
        }}
      />

      <div className="container py-16 md:py-24">
        <div className="max-w-3xl">
          <span className="label-caps">
            <T en="2026 · v3.1 · NeurIPS draft" zh="2026 · v3.1 · NeurIPS 草稿" />
          </span>
          <h1 className="mt-4 font-serif text-display text-balance leading-[1.05]">
            <T
              en={
                <>
                  The reproducible Elo benchmark for{' '}
                  <em className="not-italic text-brand">Deep Research</em> agents.
                </>
              }
              zh={
                <>
                  面向 <em className="not-italic text-brand">Deep Research</em> 智能体的可复现 Elo 基准。
                </>
              }
            />
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted md:text-lg">
            <T
              en="Twelve open-source research agents run against the same frozen sandbox. The board separates report quality from evidence quality: every cited URL is fetched, every quoted passage is checked, and the public score only rises when both hold up."
              zh="十二个开源研究智能体在同一套冻结沙箱中运行。榜单把报告质量与证据质量分开：每个引用 URL 都会被抓取，每段引文都会被核对；只有两者都站得住，公开主分才会上升。"
            />
          </p>

          {/* CTAs */}
          <div className="mt-7 flex flex-wrap items-center gap-2.5">
            <Link
              href="#leaderboard"
              className="group inline-flex h-11 items-center gap-2 rounded-tab bg-ink px-5 text-sm font-medium text-white transition-all duration-150 ease-smooth hover:bg-ink-soft"
            >
              <T en="Explore leaderboard" zh="浏览排行榜" />
              <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/arena"
              className="inline-flex h-11 items-center gap-2 rounded-tab border border-hairline bg-white px-5 text-sm font-medium text-ink transition-all duration-150 hover:border-ink/30 hover:shadow-soft"
            >
              <Swords className="h-4 w-4" />
              <T en="Open Arena" zh="打开竞技场" />
            </Link>
            <Link
              href="/methodology"
              className="inline-flex h-11 items-center gap-2 rounded-tab px-3 text-sm text-muted transition-colors hover:text-ink"
            >
              <BookOpen className="h-4 w-4" />
              <T en="Read methodology" zh="阅读方法论" />
            </Link>
            <a
              href="https://github.com/yibol9768-alt/deep-research-arena"
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-11 items-center gap-2 rounded-tab px-3 text-sm text-muted transition-colors hover:text-ink"
            >
              <Github className="h-4 w-4" />
              GitHub
            </a>
          </div>
        </div>

        {/* Stat strip */}
        <dl className="mt-14 grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
          {stats.map((s) => (
            <div
              key={s.label}
              className="card p-5"
            >
              <dt className="label-caps"><T en={s.label} zh={s.zh ?? s.label} /></dt>
              <dd className="mt-1 font-serif text-3xl tnum text-ink md:text-4xl">{s.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}
