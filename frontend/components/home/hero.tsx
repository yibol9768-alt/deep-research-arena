import { ArrowRight, BookOpen, Github, Swords, ArrowDown } from 'lucide-react'
import Link from 'next/link'
import { T } from '@/components/i18n/t'
import { agentMeta } from '@/lib/providers'
import { groundingGatePct } from '@/lib/format'
import type { RankedAgent } from '@/lib/data/types'

interface Stat {
  value: string
  label: string
  zh?: string
}

interface Props {
  stats: Stat[]
  top: RankedAgent[]
  jury: string[]
}

export function Hero({ stats, top, jury }: Props) {
  return (
    <section className="section-night relative overflow-hidden text-white">
      {/* faint grid texture */}
      <div aria-hidden className="night-grid pointer-events-none absolute inset-0" />

      <div className="container relative grid grid-cols-1 items-center gap-12 py-16 md:py-20 lg:grid-cols-[1.1fr_0.9fr] lg:gap-16">
        {/* Copy */}
        <div>
          <span className="inline-flex items-center gap-2 rounded-pill border border-night-line bg-white/5 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.14em] text-night-mist">
            <span className="h-1.5 w-1.5 animate-breathe rounded-full bg-brand-glow" />
            <T en="2026 · v3.1 snapshot · frozen sandbox" zh="2026 · v3.1 快照 · 冻结沙箱" />
          </span>

          <h1 className="mt-6 font-serif text-display text-balance leading-[1.04]">
            <T
              en={
                <>
                  The{' '}
                  <em className="bg-gradient-to-r from-brand-glow to-[#7FB2FF] bg-clip-text italic text-transparent">
                    truth-gated
                  </em>{' '}
                  leaderboard for Deep Research agents.
                </>
              }
              zh={
                <>
                  面向 Deep Research 智能体的
                  <em className="bg-gradient-to-r from-brand-glow to-[#7FB2FF] bg-clip-text not-italic text-transparent">
                    真值门控
                  </em>
                  排行榜。
                </>
              }
            />
          </h1>

          <p className="mt-6 max-w-xl text-base leading-relaxed text-night-mist md:text-lg">
            <T
              en="Open-source research agents run against the same frozen sandbox. Every cited URL is fetched, every quoted passage is checked, and the public score only rises when both the report and its evidence hold up. Fluency is not grounding."
              zh="开源研究智能体在同一套冻结沙箱中运行。每个引用 URL 都会被抓取，每段引文都会被核对；只有报告与证据同时站得住，公开主分才会上升。流畅不等于接地。"
            />
          </p>

          {/* CTAs */}
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="#leaderboard"
              className="group inline-flex h-11 items-center gap-2 rounded-pill bg-white px-6 text-sm font-semibold text-night transition-all duration-150 ease-smooth hover:bg-white/85"
            >
              <T en="Explore the leaderboard" zh="浏览排行榜" />
              <ArrowDown className="h-4 w-4 transition-transform duration-200 group-hover:translate-y-0.5" />
            </Link>
            <Link
              href="/arena"
              className="inline-flex h-11 items-center gap-2 rounded-pill border border-night-line bg-white/5 px-5 text-sm font-medium text-white transition-all duration-150 hover:border-white/30 hover:bg-white/10"
            >
              <Swords className="h-4 w-4" />
              <T en="Open Arena" zh="打开竞技场" />
            </Link>
            <Link
              href="/methodology"
              className="inline-flex h-11 items-center gap-2 rounded-pill px-3 text-sm text-night-mist transition-colors hover:text-white"
            >
              <BookOpen className="h-4 w-4" />
              <T en="Methodology" zh="方法论" />
            </Link>
            <a
              href="https://github.com/yibol9768-alt/deep-research-arena"
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-11 items-center gap-2 rounded-pill px-3 text-sm text-night-mist transition-colors hover:text-white"
            >
              <Github className="h-4 w-4" />
              GitHub
            </a>
          </div>
        </div>

        {/* Live board preview */}
        <MiniBoard top={top.slice(0, 5)} jury={jury} />
      </div>

      {/* Stat strip */}
      <div className="relative border-t border-night-line bg-black/20">
        <dl className="container grid grid-cols-2 lg:grid-cols-5">
          {stats.map((s) => (
            <div
              key={s.label}
              className="border-night-line px-2 py-6 text-center last:col-span-2 lg:border-l lg:first:border-l-0 lg:last:col-span-1"
            >
              <dd className="font-serif text-3xl tnum md:text-4xl">{s.value}</dd>
              <dt className="mt-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-night-faint">
                <T en={s.label} zh={s.zh ?? s.label} />
              </dt>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}

function MiniBoard({ top, jury }: { top: RankedAgent[]; jury: string[] }) {
  const maxScore = Math.max(...top.map((a) => a.gated_score ?? 0), 1)
  return (
    <aside className="glass-card relative p-5 md:p-6">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-tight">
          <T en="Truth-gated top 5" zh="真值门控前五" />
        </h2>
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-night-faint">
          <span className="h-1.5 w-1.5 animate-breathe rounded-full bg-good" />
          <T en="Current snapshot" zh="当前快照" />
        </span>
      </header>

      <ol className="mt-4 space-y-1">
        {top.map((a, i) => {
          const meta = agentMeta(a.id)
          const gate = groundingGatePct(a)
          const score = a.gated_score ?? 0
          return (
            <li key={a.id}>
              <Link
                href={`/agents/${a.id}`}
                className="group relative block overflow-hidden rounded-xl border border-transparent px-3 py-2.5 transition-colors hover:border-night-line hover:bg-white/5"
              >
                {/* score bar wash */}
                <span
                  aria-hidden
                  className="absolute inset-y-0 left-0 rounded-r-full bg-white/[0.045]"
                  style={{ width: `${(score / maxScore) * 100}%` }}
                />
                <span className="relative flex items-center gap-3">
                  <span className="w-4 text-center text-xs font-semibold tnum text-night-faint">{i + 1}</span>
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: meta.color }} />
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{meta.display}</span>
                  {gate != null ? (
                    <span className="hidden text-[11px] tnum text-night-faint sm:inline">
                      <T en={<>gate {gate.toFixed(0)}%</>} zh={<>接地门 {gate.toFixed(0)}%</>} />
                    </span>
                  ) : null}
                  <span className="text-sm font-semibold tnum">{score.toLocaleString('en-US')}</span>
                </span>
              </Link>
            </li>
          )
        })}
      </ol>

      <footer className="mt-4 flex flex-col gap-2 border-t border-night-line pt-3 text-[11px] leading-relaxed text-night-faint">
        {jury.length > 0 ? (
          <p className="tnum">
            <T en={<>Jury: {jury.join(' · ')}</>} zh={<>陪审团：{jury.join(' · ')}</>} />
          </p>
        ) : null}
        <Link href="#leaderboard" className="inline-flex items-center gap-1 font-medium text-night-mist transition-colors hover:text-white">
          <T en="Full leaderboard" zh="完整排行榜" />
          <ArrowRight className="h-3 w-3" />
        </Link>
      </footer>
    </aside>
  )
}
