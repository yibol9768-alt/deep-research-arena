import type { ReactNode } from 'react'
import { rankedAgents, loadLeaderboard } from '@/lib/data/load-leaderboard'
import { Hero } from '@/components/home/hero'
import { HighlightTiles } from '@/components/home/highlight-tiles'
import { CompositeBar } from '@/components/home/composite-bar'
import { QualityCostScatter } from '@/components/home/quality-cost-scatter'
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
    { value: String(agents.length), label: 'Frameworks', zh: '框架' },
    { value: '107', label: 'Sandbox tasks', zh: '沙箱任务' },
    { value: String(lb.n_runs ?? agents.reduce((a, b) => a + b.n_battles, 0)), label: 'Battles', zh: '对战' },
    { value: '7', label: 'Pillars', zh: '评测维度' },
  ]

  const sections = [
    { id: 'highlights', label: 'Highlights', zh: '亮点' },
    { id: 'leaderboard', label: 'Leaderboard', zh: '排行榜' },
    { id: 'composite', label: 'Composite Elo', zh: '综合 Elo' },
    { id: 'pillars', label: 'Per-pillar', zh: '分维度' },
    { id: 'tradeoff', label: 'Quality vs Cost', zh: '质量与成本' },
    { id: 'methodology-cta', label: 'Methodology', zh: '方法论' },
  ]

  // Build synthetic per-pillar projections from win-rate, ci, etc., until pillar_elo is wired.
  const byCitation = [...agents]
    .map((a) => ({ id: a.id, value: (a.wins / a.n_battles) * 100 }))
    .sort((a, b) => b.value - a.value)
  const byDepth = [...agents]
    .map((a) => ({ id: a.id, value: a.elo - a.ci_half }))
    .sort((a, b) => b.value - a.value)
  const byEvidence = [...agents]
    .map((a) => ({ id: a.id, value: ((a.wins + a.draws) / a.n_battles) * 100 }))
    .sort((a, b) => b.value - a.value)
  const byJudge = [...agents]
    .map((a) => ({ id: a.id, value: a.elo }))
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
              caption={<T en={`${agents.length} agents · v3.1 composite scoring`} zh={`${agents.length} 个智能体 · v3.1 综合评分`} />}
            />
            <LeaderboardTable agents={agents} />
          </div>

          {/* Composite Elo bar */}
          <div>
            <SectionTitle
              id="composite"
              title={<T en="Composite Elo" zh="综合 Elo" />}
              caption={<T en="Bradley-Terry MLE · 1000-sample bootstrap · 95% CI" zh="Bradley-Terry 极大似然估计 · 1000 次自助采样 · 95% 置信区间" />}
            />
            <CompositeBar
              agents={agents}
              title={<T en="Composite Elo (v3.1)" zh="综合 Elo (v3.1)" />}
              subtitle={
                <T
                  en="Higher is better. The two | marks bracket each bar's 95% bootstrap confidence interval (not a rendering glitch) — wider spread means fewer battles, so the rank is less certain."
                  zh="数值越高越好。每条柱上的两个 | 标记界定其 95% 自助置信区间（并非渲染异常）；区间越宽说明对战次数越少，排名越不确定。"
                />
              }
            />
          </div>

          {/* Per-pillar grid */}
          <div>
            <SectionTitle
              id="pillars"
              title={<T en="Per-pillar breakdown" zh="分维度拆解" />}
              caption={<T en="Each pillar tells a different story; the leader rotates by metric" zh="每个维度都讲述不同的故事；领先者随指标而变" />}
            />
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <PillarBars
                title={<T en="Citation alignment" zh="引用一致性" />}
                subtitle={<T en="Are claims actually supported by cited URLs? · ALCE substring + NLI" zh="论断是否真的有所引用的 URL 支撑？· ALCE 子串匹配 + 自然语言推理" />}
                accentColor="#7F4BF3"
                rows={byCitation}
                suffix="%"
              />
              <PillarBars
                title={<T en="Analysis depth" zh="分析深度" />}
                subtitle={<T en="Cross-source synthesis · LLM judge + structural heuristics" zh="跨来源综合 · LLM 评审 + 结构启发式" />}
                accentColor="#cc785c"
                rows={byDepth}
              />
              <PillarBars
                title={<T en="Evidence density" zh="证据密度" />}
                subtitle={<T en="Distinct sources cited per claim" zh="每个论断引用的不同来源数量" />}
                accentColor="#1c7ff8"
                rows={byEvidence}
                suffix="%"
              />
              <PillarBars
                title={<T en="LLM judge (RACE)" zh="LLM 评审 (RACE)" />}
                subtitle={<T en="Comprehensiveness · Insight · Instruction-following · Readability" zh="全面性 · 洞察力 · 指令遵循 · 可读性" />}
                accentColor="#34A853"
                rows={byJudge}
              />
            </div>
          </div>

          {/* Quality vs Cost */}
          <div>
            <SectionTitle
              id="tradeoff"
              title={<T en="Quality vs Cost" zh="质量与成本" />}
              caption={<T en="Pareto-optimal agents sit in the top-left wash" zh="帕累托最优的智能体位于左上方的浅色区域" />}
            />
            <QualityCostScatter agents={agents} />
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
                    en="Composite v3.1 weights seven pillars, applies a multiplicative grounding gate, and feeds the per-task pairwise outcomes into a Bradley-Terry MLE with 1000-sample bootstrap CIs and a permutation rank significance test. Judge models are drawn from a different family than the agent under test (Wataoka 2024)."
                    zh="综合 v3.1 对七个维度加权，施加一个乘性接地门控，并将每个任务的两两对战结果输入 Bradley-Terry 极大似然估计，配合 1000 次自助置信区间和置换排名显著性检验。评审模型与受测智能体来自不同的模型家族（Wataoka 2024）。"
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
