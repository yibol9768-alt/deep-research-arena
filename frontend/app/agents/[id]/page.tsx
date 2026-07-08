import type { ReactNode } from 'react'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft, Github, Swords } from 'lucide-react'
import { rankedAgents } from '@/lib/data/load-leaderboard'
import { loadArenaV2, backboneShort, type ArenaEntry } from '@/lib/data/load-arena-v2'
import { agentMeta, allAgents } from '@/lib/providers'
import { MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'
import { fmt, groundingGatePct, truthScore } from '@/lib/format'

export const dynamic = 'force-static'

export function generateStaticParams() {
  const ids = new Set([
    ...rankedAgents().map((agent) => agent.id),
    ...allAgents().map((agent) => agent.id),
    ...(loadArenaV2()?.entries.map((e) => e.id) ?? []),
  ])
  return Array.from(ids).map((id) => ({ id }))
}

export default function AgentDetailPage({ params }: { params: { id: string } }) {
  const arena = loadArenaV2()
  const runs = arena?.entries.filter((e) => e.id === params.id) ?? []
  const legacy = rankedAgents().find((row) => row.id === params.id)
  if (runs.length === 0 && !legacy) notFound()
  const meta = agentMeta(params.id)
  const bestRank = runs.length > 0 ? Math.min(...runs.map((e) => arena!.entries.indexOf(e))) + 1 : null

  return (
    <div className="container py-12 md:py-16">
      <Link href="/agents" className="inline-flex items-center gap-2 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> <T en="Agents" zh="智能体" />
      </Link>

      {/* Header card */}
      <section className="mt-6">
        <div className="card relative overflow-hidden p-8">
          <span className="absolute inset-x-0 top-0 h-1.5" style={{ backgroundColor: meta.color }} />
          {bestRank != null ? (
            <span className="label-caps"><T en="Best rank" zh="最佳排名" /> #{bestRank}</span>
          ) : null}
          <h1 className="mt-3 font-serif text-display-lg text-ink">{meta.display}</h1>
          <p className="mt-2 text-base text-muted">
            {meta.family}
            {runs.length > 0 ? <> · {runs.map((r) => backboneShort(r.backbone)).join(' · ')}</> : <> · {meta.backbone}</>}
          </p>
          {meta.blurb ? <p className="mt-5 max-w-2xl text-sm leading-relaxed text-muted">{meta.blurb}</p> : null}
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href={`/arena?a=${params.id}`} className="inline-flex h-10 items-center gap-2 rounded-tab bg-ink px-4 text-sm font-medium text-white hover:bg-ink-soft">
              <Swords className="h-4 w-4" /> <T en="Challenge" zh="发起对战" />
            </Link>
            {meta.github ? (
              <a href={meta.github} target="_blank" rel="noreferrer" className="inline-flex h-10 items-center gap-2 rounded-tab border border-hairline bg-white px-4 text-sm font-medium text-ink hover:border-ink/30">
                <Github className="h-4 w-4" /> <T en="Source" zh="源码" />
              </a>
            ) : null}
          </div>
        </div>
      </section>

      {/* One card per backbone run (Arena v2, uj_v1 protocol) */}
      {runs.map((run) => (
        <RunCard
          key={run.key}
          run={run}
          rank={arena!.entries.indexOf(run) + 1}
          total={arena!.entries.length}
          judges={arena!.judges}
        />
      ))}

      {/* Legacy v1 snapshot, kept for provenance */}
      {legacy ? (
        <section className="mt-10">
          <header className="mb-3 flex items-center gap-2.5">
            <h2 className="font-serif text-h-sm text-muted"><T en="v1 snapshot (archived)" zh="v1 快照（已归档）" /></h2>
            <span className="rounded-pill bg-surface-mid px-2 py-0.5 text-[11px] text-muted">
              <T en="old protocol · superseded by the runs above" zh="旧口径 · 已被上方结果取代" />
            </span>
          </header>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <MetricCard label={<T en="Score" zh="主分" />} value={fmt(truthScore(legacy))} detail={<T en="judge Elo × grounding gate" zh="判官 Elo × 接地门" />} />
            <MetricCard label={<T en="Judge Elo" zh="判官 Elo" />} value={fmt(legacy.elo)} detail={`95% CI ${legacy.elo_lo.toFixed(0)}-${legacy.elo_hi.toFixed(0)}`} />
            <MetricCard label={<T en="Battles" zh="对战数" />} value={String(legacy.n_battles)} detail={<T en="pairwise outcomes" zh="两两对战结果" />} />
            <MetricCard
              label={<T en="Grounding" zh="接地" />}
              value={groundingGatePct(legacy) == null ? 'n/a' : `${groundingGatePct(legacy)!.toFixed(0)}%`}
              detail={<T en="reachability + quote match" zh="可达率 + 引文核实率" />}
            />
          </div>
        </section>
      ) : null}
    </div>
  )
}

function RunCard({ run, rank, total, judges }: { run: ArenaEntry; rank: number; total: number; judges: string[] }) {
  const reachPct = run.reach * 100
  return (
    <section id={`run-${run.backbone}`} className="mt-10 scroll-mt-24">
      <header className="mb-3 flex flex-wrap items-center gap-2.5">
        <span className="aa-square" />
        <h2 className="font-serif text-h-sm text-ink">
          <T en={`Run on ${backboneShort(run.backbone)}`} zh={`${backboneShort(run.backbone)} 上的运行`} />
        </h2>
        <span className="rounded-pill bg-surface-mid px-2 py-0.5 text-[11px] text-muted tnum">
          <T en={`rank #${rank} / ${total}`} zh={`排名 #${rank} / ${total}`} />
        </span>
        {run.rank_ci95 ? (
          <span className="text-[11px] text-muted-2 tnum">
            <T en={`rank CI95 [${run.rank_ci95[0]}, ${run.rank_ci95[1]}]`} zh={`排名 95% 区间 [${run.rank_ci95[0]}, ${run.rank_ci95[1]}]`} />
          </span>
        ) : null}
      </header>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard
          label={<T en="Arena score" zh="Arena 主分" />}
          value={(run.arena * 100).toFixed(1)}
          detail={<T en="reach^1.5 × jury win rate" zh="可达率^1.5 × 陪审团胜率" />}
        />
        <MetricCard
          label={<T en="Jury Elo (BT)" zh="陪审团 Elo（BT）" />}
          value={String(Math.round(run.bt_elo))}
          detail={<T en={`${judges.length}-judge jury`} zh={`${judges.length} 裁判陪审团`} />}
        />
        <MetricCard
          label={<T en="Win rate" zh="胜率" />}
          value={`${(run.winrate * 100).toFixed(1)}%`}
          detail={
            run.winrate_ci95
              ? `95% CI ${(run.winrate_ci95[0] * 100).toFixed(0)}–${(run.winrate_ci95[1] * 100).toFixed(0)}%`
              : undefined
          }
        />
        <MetricCard
          label={<T en="Grounding (reach)" zh="接地（可达）" />}
          value={`${reachPct.toFixed(0)}%`}
          detail={<T en="cited URLs re-opened in sandbox" zh="引用 URL 沙箱内可重开比例" />}
        />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard label={<T en="Truth score" zh="真值分" />} value={run.truth.toFixed(3)} detail={<T en="five-axis verifier composite" zh="五轴验证器综合" />} />
        <MetricCard label={<T en="Battles" zh="对战数" />} value={String(run.n_battles)} detail={<T en="pairwise jury outcomes" zh="陪审团两两对战" />} />
        <MetricCard
          label={<T en="Tie rate" zh="平局率" />}
          value={run.tie_rate != null ? `${(run.tie_rate * 100).toFixed(1)}%` : 'n/a'}
          detail={<T en="jury declared tie" zh="陪审团判平" />}
        />
        <MetricCard
          label={<T en="Jury agreement" zh="陪审团一致性" />}
          value={`κ ${run.fleiss_kappa.toFixed(2)}`}
          detail={<T en={`Fleiss κ on ${backboneShort(run.backbone)}`} zh={`${backboneShort(run.backbone)} 上的 Fleiss κ`} />}
        />
      </div>
    </section>
  )
}
