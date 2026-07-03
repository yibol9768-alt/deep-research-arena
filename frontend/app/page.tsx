import type { ReactNode } from 'react'
import { rankedAgents, loadLeaderboard, juryModels } from '@/lib/data/load-leaderboard'
import { loadChangelog } from '@/lib/data/changelog'
import { agentMeta } from '@/lib/providers'
import { groundingGatePct, fmt } from '@/lib/format'
import { Hero } from '@/components/home/hero'
import { LeaderboardTable } from '@/components/home/leaderboard-table'
import { SectionNav } from '@/components/home/section-nav'
import { DryRunBanner } from '@/components/home/dry-run-banner'
import { RankShift } from '@/components/home/rank-shift'
import { GateScatter } from '@/components/home/gate-scatter'
import { PipelineBand } from '@/components/home/pipeline-band'
import { VBarChart, type VBarRow } from '@/components/home/vbar-chart'
import { Faq } from '@/components/home/faq'
import { CiteBlock } from '@/components/home/cite-block'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

export default function HomePage() {
  const agents = rankedAgents()
  const lb = loadLeaderboard()
  const jury = juryModels()
  const news = loadChangelog().entries.slice(0, 3)

  const stats = [
    { value: String(agents.length), label: 'Agents', zh: '智能体' },
    { value: '100', label: 'Frozen tasks', zh: '冻结任务' },
    { value: fmt(lb.n_runs), label: 'Jury battles', zh: '陪审团对战' },
    { value: String(jury.length || 3), label: 'Jurors', zh: '陪审员' },
    { value: '1,000', label: 'Bootstrap resamples', zh: '自助重采样' },
  ]

  const sections = [
    { id: 'highlights', label: 'Highlights', zh: '亮点图表' },
    { id: 'leaderboard', label: 'Leaderboard', zh: '排行榜' },
    { id: 'rankshift', label: 'What the gate changes', zh: '门控改变了什么' },
    { id: 'scatter', label: 'Fluency vs grounding', zh: '流畅 vs 接地' },
    { id: 'how-it-works', label: 'How it works', zh: '评测流程' },
    { id: 'faq', label: 'FAQ', zh: '常见问题' },
    { id: 'cite', label: 'Cite & reproduce', zh: '引用与复现' },
  ]

  // Chart rows — all straight from the loaded snapshot.
  const row = (id: string, value: number, valueLabel?: string): VBarRow => {
    const meta = agentMeta(id)
    return { id, label: meta.display, color: meta.color, value, valueLabel }
  }
  const byGated: VBarRow[] = [...agents]
    .sort((a, b) => (b.gated_score ?? 0) - (a.gated_score ?? 0))
    .map((a) => row(a.id, a.gated_score ?? 0))
  const byGate: VBarRow[] = [...agents]
    .map((a) => ({ a, gate: groundingGatePct(a) ?? 0 }))
    .sort((p, q) => q.gate - p.gate)
    .map((p) => row(p.a.id, p.gate, `${p.gate.toFixed(0)}%`))
  const byJudge: VBarRow[] = [...agents]
    .sort((a, b) => b.elo - a.elo)
    .map((a) => row(a.id, a.elo))

  const juryLine = jury.length > 0 ? jury.join(' · ') : 'cross-family LLM jury'

  return (
    <>
      <DryRunBanner isDryRun={!!lb.is_dry_run} schemaVersion={lb.schema_version} />
      <Hero stats={stats} news={news} />

      {/* Highlights: AA-style chart cards */}
      <section id="highlights" className="container mt-12 scroll-mt-24">
        <div className="flex items-end justify-between border-b border-hairline pb-3">
          <h2 className="text-sm font-semibold text-ink"><T en="Highlights" zh="亮点图表" /></h2>
          <span className="text-[11px] uppercase tracking-wider text-muted-2">
            <T en="Computed from the current snapshot" zh="基于当前快照计算" />
          </span>
        </div>
        <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <VBarChart
            accent="#6E5BFF"
            title={<T en="Truth-gated Score" zh="真值门控得分" />}
            subtitle={<T en="Judge Elo × grounding gate — the headline ranking" zh="判官 Elo × 接地门 —— 榜单主排序" />}
            rows={byGated}
          />
          <VBarChart
            accent="#34A853"
            title={<T en="Grounding" zh="接地门" />}
            subtitle={<T en="(citation reachability + quote match) / 2 · judge-free" zh="(引用可达率 + 引文核实率)/ 2 · 不依赖判官" />}
            rows={byGate}
          />
          <VBarChart
            accent="#cc785c"
            title={<T en="Judge Elo (raw)" zh="裸判官 Elo" />}
            subtitle={<T en="Pairwise jury preference, blind to citation reality" zh="陪审团成对偏好，看不见引用真假" />}
            rows={byJudge}
          />
        </div>
      </section>

      {/* Two-column body: sticky on-page nav + main */}
      <div className="container mt-16 flex flex-col gap-12 lg:flex-row">
        <SectionNav items={sections} />

        <div className="min-w-0 flex-1 space-y-14">
          {/* Leaderboard table */}
          <div>
            <SectionTitle
              id="leaderboard"
              title={<T en="Leaderboard" zh="排行榜" />}
              caption={
                <T
                  en={`${agents.length} agents · truth-gated Elo (judge Elo × grounding gate) · jury: ${juryLine}`}
                  zh={`${agents.length} 个智能体 · 真值门控 Elo（判官 Elo × 接地门）· 陪审团：${juryLine}`}
                />
              }
            />
            <LeaderboardTable agents={agents} />
          </div>

          {/* Raw vs gated rank movement */}
          <div>
            <SectionTitle
              id="rankshift"
              title={<T en="What the gate changes" zh="门控改变了什么" />}
              caption={
                <T
                  en="Rank by jury preference alone, versus rank after evidence is checked — computed from the same snapshot"
                  zh="仅凭陪审团偏好的排名,对比证据核验之后的排名 —— 均来自同一快照"
                />
              }
            />
            <RankShift agents={agents} />
          </div>

          {/* Scatter: judge Elo vs grounding gate */}
          <div id="scatter" className="scroll-mt-24">
            <GateScatter agents={agents} />
          </div>

          {/* Pipeline explainer (light) */}
          <PipelineBand />

          {/* FAQ + cite */}
          <Faq />
          <CiteBlock />
        </div>
      </div>
    </>
  )
}

function SectionTitle({ id, title, caption }: { id: string; title: ReactNode; caption: ReactNode }) {
  return (
    <header id={id} className="mb-4 scroll-mt-24">
      <div className="flex items-center gap-2.5">
        <span className="aa-square" />
        <h2 className="font-serif text-h-sm text-ink">{title}</h2>
      </div>
      <p className="mt-1 text-xs text-muted">{caption}</p>
    </header>
  )
}
