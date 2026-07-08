import { loadArenaV2, backboneAggregates } from '@/lib/data/load-arena-v2'
import { backboneShort } from '@/lib/backbones'
import { agentMeta } from '@/lib/providers'
import { MetricCard } from '@/components/layout/metric-card'
import { VBarChart, type VBarRow } from '@/components/home/vbar-chart'
import { fmt } from '@/lib/format'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

export const metadata = {
  title: 'Backbone LLMs — Deep Research Arena',
  description:
    'The same research harnesses, compared across backbone LLMs. Arena score = reach^1.5 × Bradley-Terry jury win rate.',
}

export default function ModelsPage() {
  const arena = loadArenaV2()
  if (!arena) {
    return <div className="container py-20 text-sm text-muted">Arena snapshot missing.</div>
  }
  const backbones = backboneAggregates(arena)

  return (
    <>
      <div className="container pt-12">
        <h1 className="font-serif text-h-md leading-tight md:text-display-lg">
          <T en="Deep research by backbone LLM" zh="按主干模型看深度研究" />
        </h1>
        <p className="mt-3 max-w-3xl text-[15px] leading-relaxed text-muted">
          <T
            en={`The same ${new Set(arena.entries.map((e) => e.id)).size} harnesses, the same frozen tasks — only the backbone LLM changes. Each panel below is one backbone: the average across harnesses summarises what the model brings, and the bars show every harness run on it (click a bar for the full breakdown). Jury: ${arena.judges.join(' · ')}.`}
            zh={`同样的 ${new Set(arena.entries.map((e) => e.id)).size} 个框架、同一批冻结任务,只更换主干模型。下面每个面板对应一个主干模型:跨框架平均值概括模型本身的贡献,条形图展示它上面的每个框架运行(点击竖条看完整明细)。陪审团：${arena.judges.join(' · ')}。`}
          />
        </p>
      </div>

      <div className="container mt-10 space-y-12 pb-20">
        {backbones.map((bb) => {
          const rows: VBarRow[] = bb.runs.map((r) => {
            const meta = agentMeta(r.id)
            return {
              id: r.key,
              label: meta.display,
              color: meta.color,
              value: r.arena * 100,
              valueLabel: (r.arena * 100).toFixed(1),
              href: `/agents/${r.id}#run-${r.backbone}`,
            }
          })
          return (
            <section key={bb.backbone} id={bb.backbone} className="scroll-mt-24">
              <header className="mb-4 flex flex-wrap items-center gap-2.5 border-b border-hairline pb-3">
                <span className="aa-square" />
                <h2 className="font-serif text-h-sm text-ink">{backboneShort(bb.backbone)}</h2>
                <span className="rounded-pill bg-surface-mid px-2 py-0.5 text-[11px] text-muted">
                  <T en={`${bb.runs.length} harnesses`} zh={`${bb.runs.length} 个框架`} />
                </span>
              </header>

              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <MetricCard
                  label={<T en="Arena (avg over harnesses)" zh="Arena（跨框架平均）" />}
                  value={(bb.arena * 100).toFixed(1)}
                  detail={<T en="reach^1.5 × jury win rate" zh="可达率^1.5 × 陪审团胜率" />}
                />
                <MetricCard
                  label={<T en="Grounding (avg reach)" zh="接地（平均可达率）" />}
                  value={`${(bb.reach * 100).toFixed(0)}%`}
                  detail={<T en="cited URLs re-opened in sandbox" zh="引用 URL 沙箱内可重开" />}
                />
                <MetricCard
                  label={<T en="Jury agreement" zh="陪审团一致性" />}
                  value={`κ ${bb.fleiss_kappa.toFixed(2)}`}
                  detail={<T en={`Fleiss κ · ρ(truth) ${bb.spearman.toFixed(2)}`} zh={`Fleiss κ · 与真值分相关 ρ ${bb.spearman.toFixed(2)}`} />}
                />
                <MetricCard
                  label={<T en="Battles" zh="对战数" />}
                  value={fmt(bb.n_battles)}
                  detail={<T en="pairwise jury outcomes" zh="陪审团两两对战" />}
                />
              </div>

              <div className="mt-4">
                <VBarChart
                  accent="#6E5BFF"
                  title={<T en={`Arena score on ${backboneShort(bb.backbone)}`} zh={`${backboneShort(bb.backbone)} 上的 Arena 主分`} />}
                  subtitle={<T en="One bar per harness · click for the full breakdown" zh="每根竖条为一个框架 · 点击查看完整明细" />}
                  rows={rows}
                />
              </div>
            </section>
          )
        })}
      </div>
    </>
  )
}
