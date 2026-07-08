import type { ReactNode } from 'react'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft, Github, Swords } from 'lucide-react'
import { rankedAgents } from '@/lib/data/load-leaderboard'
import { agentMeta, allAgents } from '@/lib/providers'
import { MetricCard } from '@/components/layout/metric-card'
import { QualityProfile } from '@/components/agents/quality-profile'
import { ScoreExplainer, type ExplainerBackbone } from '@/components/agents/score-explainer'
import { loadAxesDetail } from '@/lib/data/load-axes-detail'
import { loadMatrixSubset } from '@/lib/data/load-matrix-subset'
import { loadSampleReports } from '@/lib/data/load-sample-reports'
import { T } from '@/components/i18n/t'
import { fmt, groundingGatePct, truthScore } from '@/lib/format'

export const dynamic = 'force-static'

export function generateStaticParams() {
  const ids = new Set([...rankedAgents().map((agent) => agent.id), ...allAgents().map((agent) => agent.id)])
  return Array.from(ids).map((id) => ({ id }))
}

export default function AgentDetailPage({ params }: { params: { id: string } }) {
  const agent = rankedAgents().find((row) => row.id === params.id)
  if (!agent) notFound()
  const meta = agentMeta(agent.id)
  const gate = groundingGatePct(agent)

  // Score-explainer data: decidable five-axis truth, jury stats, sample report.
  // Assembled per backbone; degrades gracefully when a source is missing.
  const axes = loadAxesDetail()
  const matrix = loadMatrixSubset()
  const samples = loadSampleReports()
  const explainerBackbones: ExplainerBackbone[] = ['qwen3-8b', 'deepseek-v4-flash']
    .map((key): ExplainerBackbone | null => {
      const ax = axes?.backbones[key]?.agents[agent.id]
      const mx = matrix?.backbones[key]?.agents.find((a) => a.id === agent.id)
      const sample = samples?.[key]?.[agent.id]
      if (!ax && !mx && !sample) return null
      return {
        key,
        label: key,
        axes: ax?.axes_mean,
        truthMacro: ax?.truth_macro,
        gamma: axes?.backbones[key]?.gamma ?? axes?.gamma,
        arena: mx?.arena,
        reach: mx?.reach,
        winrate: mx?.winrate,
        winrateCi95: mx?.winrate_ci95,
        btElo: mx?.bt_elo,
        nBattles: mx?.n_battles,
        tieRate: mx?.tie_rate,
        sample,
        perTask: ax?.per_task,
      }
    })
    .filter((b): b is ExplainerBackbone => b != null)

  return (
    <div className="container py-12 md:py-16">
      <Link href="/agents" className="inline-flex items-center gap-2 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> <T en="Agents" zh="智能体" />
      </Link>

      <section className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-[1.2fr_.8fr]">
        <div className="card relative overflow-hidden p-8">
          <span className="absolute inset-x-0 top-0 h-1.5" style={{ backgroundColor: meta.color }} />
          <span className="label-caps"><T en="Rank" zh="排名" /> #{agent.rank}</span>
          <h1 className="mt-3 font-serif text-display-lg text-ink">{meta.display}</h1>
          <p className="mt-2 text-base text-muted">{meta.family} · {meta.backbone}</p>
          {meta.blurb ? <p className="mt-5 max-w-2xl text-sm leading-relaxed text-muted">{meta.blurb}</p> : null}
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href={`/arena?a=${agent.id}`} className="inline-flex h-10 items-center gap-2 rounded-tab bg-ink px-4 text-sm font-medium text-white hover:bg-ink-soft">
              <Swords className="h-4 w-4" /> <T en="Challenge" zh="发起对战" />
            </Link>
            {meta.github ? (
              <a href={meta.github} target="_blank" rel="noreferrer" className="inline-flex h-10 items-center gap-2 rounded-tab border border-hairline bg-white px-4 text-sm font-medium text-ink hover:border-ink/30">
                <Github className="h-4 w-4" /> <T en="Source" zh="源码" />
              </a>
            ) : null}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <MetricCard label={<T en="Score" zh="主分" />} value={fmt(truthScore(agent))} detail={<T en="judge Elo × grounding gate" zh="判官 Elo × 接地门" />} />
          <MetricCard label={<T en="Judge Elo" zh="判官 Elo" />} value={fmt(agent.elo)} detail={`95% CI ${agent.elo_lo.toFixed(0)}-${agent.elo_hi.toFixed(0)}`} />
          <MetricCard label={<T en="Battles" zh="对战数" />} value={String(agent.n_battles)} detail={<T en="pairwise outcomes" zh="两两对战结果" />} />
          <MetricCard label={<T en="Grounding" zh="接地" />} value={gate == null ? 'n/a' : `${gate.toFixed(0)}%`} detail={<T en="reachability + quote match" zh="可达率 + 引文核实率" />} />
        </div>
      </section>

      <section className="mt-10 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card p-6 lg:col-span-2">
          <h2 className="font-serif text-h-sm text-ink"><T en="Outcome accounting" zh="结果统计" /></h2>
          <div className="mt-6 space-y-4">
            <Outcome label={<T en="Wins" zh="胜" />} value={agent.wins} total={agent.n_battles} color="#34A853" />
            <Outcome label={<T en="Draws" zh="平" />} value={agent.draws} total={agent.n_battles} color="#FF9900" />
            <Outcome label={<T en="Losses" zh="负" />} value={agent.losses} total={agent.n_battles} color="#E5484D" />
          </div>
        </div>
        <div className="card p-6">
          <h2 className="font-serif text-h-sm text-ink"><T en="Interpretation" zh="解读" /></h2>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            <T
              en="This profile uses the same leaderboard snapshot as the main table. Treat rank, judge Elo, and grounding together: a high judge score is only useful when the cited evidence can be reopened."
              zh="本档案使用与主表相同的排行榜快照。请同时查看排名、判官 Elo 与接地率：只有被引用证据能重新打开时，高判官分才有实际意义。"
            />
          </p>
        </div>
      </section>

      {explainerBackbones.length > 0 ? (
        <ScoreExplainer agentLabel={meta.display} color={meta.color} backbones={explainerBackbones} />
      ) : null}

      <section className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <QualityProfile
            accentColor={meta.color}
            synthetic={agent.synthetic_placeholder}
            depth={agent.depth_avg}
            rigor={agent.rigor_avg}
            style={agent.style_avg}
            coverage={agent.coverage_pct}
            checklist={agent.checklist_pass_rate}
            urlVeracity={agent.url_veracity_pct}
          />
        </div>
      </section>
    </div>
  )
}

function Outcome({ label, value, total, color }: { label: ReactNode; value: number; total: number; color: string }) {
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-ink">{label}</span>
        <span className="tnum text-muted">{value}</span>
      </div>
      <div className="mt-2 h-3 rounded-pill bg-surface-mid">
        <div className="h-full rounded-pill" style={{ width: `${(value / Math.max(1, total)) * 100}%`, backgroundColor: color }} />
      </div>
    </div>
  )
}
