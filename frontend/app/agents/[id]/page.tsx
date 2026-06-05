import type { ReactNode } from 'react'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft, Github, Swords } from 'lucide-react'
import { rankedAgents } from '@/lib/data/load-leaderboard'
import { agentMeta, allAgents } from '@/lib/providers'
import { MetricCard } from '@/components/layout/metric-card'
import { QualityProfile } from '@/components/agents/quality-profile'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

export function generateStaticParams() {
  const ids = new Set([...rankedAgents().map((agent) => agent.id), ...allAgents().map((agent) => agent.id)])
  return Array.from(ids).map((id) => ({ id }))
}

export default function AgentDetailPage({ params }: { params: { id: string } }) {
  const agent = rankedAgents().find((row) => row.id === params.id)
  if (!agent) notFound()
  const meta = agentMeta(agent.id)
  const winRate = (agent.wins / Math.max(1, agent.n_battles)) * 100
  const nonLoss = ((agent.wins + agent.draws) / Math.max(1, agent.n_battles)) * 100

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
          <MetricCard label={<T en="Composite Elo" zh="综合 Elo" />} value={agent.elo.toFixed(0)} detail={`95% CI ${agent.elo_lo.toFixed(0)}-${agent.elo_hi.toFixed(0)}`} />
          <MetricCard label={<T en="Battles" zh="对战数" />} value={String(agent.n_battles)} detail={<T en="pairwise outcomes" zh="两两对战结果" />} />
          <MetricCard label={<T en="Win rate" zh="胜率" />} value={`${winRate.toFixed(0)}%`} detail={`${agent.wins} wins`} />
          <MetricCard label={<T en="Non-loss" zh="不败率" />} value={`${nonLoss.toFixed(0)}%`} detail={`${agent.draws} draws retained`} />
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
              en="This page is static and deploy-safe: it is generated from the same leaderboard JSON as the home table. Per-task report drill-down can be added without changing the URL contract."
              zh="本页面为静态页面、可安全部署：它由与首页表格相同的排行榜 JSON 生成。可在不改变 URL 约定的前提下加入逐任务报告的下钻视图。"
            />
          </p>
        </div>
      </section>

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
