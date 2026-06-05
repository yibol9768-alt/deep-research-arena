import type { ReactNode } from 'react'
import { rankedAgents, loadLeaderboard } from '@/lib/data/load-leaderboard'
import { Hero } from '@/components/home/hero'
import { HighlightTiles } from '@/components/home/highlight-tiles'
import { CompositeBar } from '@/components/home/composite-bar'
import { LeaderboardTable } from '@/components/home/leaderboard-table'
import { PillarBars } from '@/components/home/pillar-bars'
import { SectionNav } from '@/components/home/section-nav'
import { DryRunBanner } from '@/components/home/dry-run-banner'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

export default function HomePage() {
  const agents = rankedAgents()
  const lb = loadLeaderboard()

  const stats = [
    { value: String(agents.length), label: 'Agents', zh: '智能体' },
    { value: '100', label: 'Sandbox tasks', zh: '沙箱任务' },
    { value: String(lb.n_runs ?? agents.reduce((a, b) => a + b.n_battles, 0)), label: 'Judge battles', zh: '判官对战' },
    { value: '74', label: 'Judged tasks', zh: '入评任务' },
  ]

  const sections = [
    { id: 'highlights', label: 'Highlights', zh: '亮点' },
    { id: 'leaderboard', label: 'Leaderboard', zh: '排行榜' },
    { id: 'composite', label: 'Judge Elo (raw)', zh: '裸判官 Elo' },
    { id: 'pillars', label: 'Signals', zh: '评分信号' },
    { id: 'methodology-cta', label: 'Methodology', zh: '方法论' },
  ]

  // REAL per-agent signals (no synthetic projections): grounding from the
  // judge-free cache pass, judge Elo from the Bradley-Terry fit, and the
  // truth-gated headline score.
  const byReach = [...agents]
    .map((a) => ({ id: a.id, value: a.reachability_pct ?? 0 }))
    .sort((a, b) => b.value - a.value)
  const byQuote = [...agents]
    .map((a) => ({ id: a.id, value: a.url_veracity_pct ?? 0 }))
    .sort((a, b) => b.value - a.value)
  const byJudge = [...agents]
    .map((a) => ({ id: a.id, value: a.elo }))
    .sort((a, b) => b.value - a.value)
  const byGated = [...agents]
    .map((a) => ({ id: a.id, value: a.gated_score ?? 0 }))
    .sort((a, b) => b.value - a.value)

  return (
    <>
      <DryRunBanner isDryRun={!!lb.is_dry_run} schemaVersion={lb.schema_version} />
      <Hero stats={stats} />

      <div id="highlights" className="container">
        <div className="my-10 h-px w-full bg-hairline" />
      </div>
      <HighlightTiles top={agents.slice(0, 4)} />

      {/* Two-column body: sticky on-page nav + main */}
      <div className="container mt-16 flex flex-col gap-12 lg:flex-row">
        <SectionNav items={sections} />

        <div className="min-w-0 flex-1 space-y-12">
          {/* Leaderboard table */}
          <div>
            <SectionTitle
              id="leaderboard"
              title={<T en="Leaderboard" zh="排行榜" />}
              caption={<T en={`${agents.length} agents · truth-gated Elo (judge Elo × grounding gate) · judge: deepseek-v4-flash`} zh={`${agents.length} 个智能体 · 真值门控 Elo（判官 Elo × 接地门）· 判官：deepseek-v4-flash`} />}
            />
            <LeaderboardTable agents={agents} />
          </div>

          {/* Raw judge Elo bar */}
          <div>
            <SectionTitle
              id="composite"
              title={<T en="Judge Elo (raw component)" zh="裸判官 Elo（组成部分）" />}
              caption={<T en="Pairwise Bradley-Terry · position-debiased · bootstrap 95% CI · before the grounding gate" zh="成对 Bradley-Terry · 位置去偏 · 自助 95% 置信区间 · 未经接地门控" />}
            />
            <CompositeBar
              agents={agents}
              title={<T en="Judge Elo (raw)" zh="裸判官 Elo" />}
              subtitle={
                <T
                  en="Higher is better. The two | marks bracket each bar's 95% bootstrap confidence interval (not a rendering glitch) — wider spread means fewer battles, so the rank is less certain."
                  zh="数值越高越好。每条柱上的两个 | 标记界定其 95% 自助置信区间（并非渲染异常）；区间越宽说明对战次数越少，排名越不确定。"
                />
              }
            />
          </div>

          {/* Real scoring signals */}
          <div>
            <SectionTitle
              id="pillars"
              title={<T en="Scoring signals" zh="评分信号" />}
              caption={<T en="The two grounding signals (judge-free, scored against the frozen sandbox) and the two quality views" zh="两个接地信号（不依赖判官，按冻结沙箱核验）与两个质量视角" />}
            />
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <PillarBars
                title={<T en="Citation reachability" zh="引用可达率" />}
                subtitle={<T en="Share of cited URLs that actually resolve in the sandbox" zh="所引用 URL 在沙箱中真实可达的比例" />}
                accentColor="#7F4BF3"
                rows={byReach}
                suffix="%"
              />
              <PillarBars
                title={<T en="Quote-verified citations" zh="引文核实率" />}
                subtitle={<T en="Cited page actually contains the quoted evidence" zh="被引页面确实包含所引述的证据" />}
                accentColor="#1c7ff8"
                rows={byQuote}
                suffix="%"
              />
              <PillarBars
                title={<T en="Judge Elo (raw)" zh="裸判官 Elo" />}
                subtitle={<T en="Pairwise preference of the LLM judge (deepseek-v4-flash), blind to citation reality" zh="LLM 判官（deepseek-v4-flash）的成对偏好，看不见引用真假" />}
                accentColor="#cc785c"
                rows={byJudge}
              />
              <PillarBars
                title={<T en="Truth-gated score" zh="真值门控得分" />}
                subtitle={<T en="Judge Elo × grounding gate — the headline ranking" zh="判官 Elo × 接地门，即榜单主排序" />}
                accentColor="#34A853"
                rows={byGated}
              />
            </div>
          </div>

          {/* Methodology CTA */}
          <div id="methodology-cta" className="card p-8">
            <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
              <div className="max-w-xl">
                <h3 className="font-serif text-h-sm text-ink">
                  <T en="How are these scores computed?" zh="这些分数是如何计算的？" />
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  <T
                    en="Two independent measurements: GROUNDING (judge-free -- every cited URL is fetched against the frozen sandbox and quotes are verified on the cited page) and QUALITY (1553 pairwise judge battles, position-debiased, Bradley-Terry with bootstrap 95% CIs; judge deepseek-v4-flash). The headline score multiplies judge Elo by the grounding gate, so fluent fabrication cannot top the board."
                    zh="两个相互独立的测量：接地（不依赖判官 -- 每个被引用的 URL 都按冻结沙箱实地核验，引文逐条对照被引页面）与质量（1553 场成对判官对战，位置去偏，Bradley-Terry 拟合并给出自助 95% 置信区间；判官为 deepseek-v4-flash）。榜单主分 = 判官 Elo × 接地门，流畅的编造无法登顶。"
                  />
                </p>
              </div>
              <a
                href="/methodology"
                className="inline-flex h-11 shrink-0 items-center gap-2 rounded-tab bg-ink px-5 text-sm font-medium text-white hover:bg-ink-soft"
              >
                <T en="Read the methodology →" zh="阅读方法论 →" />
              </a>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

function SectionTitle({ id, title, caption }: { id: string; title: ReactNode; caption: ReactNode }) {
  return (
    <header id={id} className="mb-4 scroll-mt-24">
      <h2 className="font-serif text-h-sm text-ink">{title}</h2>
      <p className="mt-1 text-xs text-muted">{caption}</p>
    </header>
  )
}
