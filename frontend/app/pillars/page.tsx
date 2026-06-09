import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { loadLeaderboard, rankedAgents } from '@/lib/data/load-leaderboard'
import { agentMeta } from '@/lib/providers'
import { T } from '@/components/i18n/t'
import { fmt, groundingGatePct, truthScore } from '@/lib/format'

export const dynamic = 'force-static'

const PILLARS = [
  {
    name: 'Citation alignment',
    nameZh: '引用一致性',
    description: 'Claims must be backed by reachable sandbox URLs, not just polished prose.',
    descriptionZh: '论断必须由可访问的沙箱 URL 支撑，而不只是辞藻华丽的行文。',
    weight: 0.22,
  },
  {
    name: 'Evidence density',
    nameZh: '证据密度',
    description: 'Reports should draw from enough distinct sources to support cross-site synthesis.',
    descriptionZh: '报告应引用足够多的不同来源，以支撑跨站点的综合分析。',
    weight: 0.16,
  },
  {
    name: 'Analysis depth',
    nameZh: '分析深度',
    description: 'Judges reward synthesis, contradiction handling, and decision-useful structure.',
    descriptionZh: '评审奖励综合归纳、矛盾处理以及对决策有用的结构。',
    weight: 0.18,
  },
  {
    name: 'Checklist coverage',
    nameZh: '清单覆盖度',
    description: 'Task-specific human criteria prevent generic answers from ranking highly.',
    descriptionZh: '针对具体任务的人工标准可防止泛泛而谈的回答获得高排名。',
    weight: 0.16,
  },
  {
    name: 'Fact graph',
    nameZh: '事实图谱',
    description: 'Entity, claim, and URL triples are checked for consistency across sources.',
    descriptionZh: '对实体、论断与 URL 三元组进行跨来源的一致性校验。',
    weight: 0.10,
  },
  {
    name: 'Markdown integrity',
    nameZh: 'Markdown 完整性',
    description: 'Citations must be parseable markdown links and attached to concrete claims.',
    descriptionZh: '引用必须是可解析的 markdown 链接，并附着于具体论断之上。',
    weight: 0.08,
  },
  {
    name: 'Efficiency',
    nameZh: '效率',
    description: 'Quality is normalized against cost, latency, and dropped runs.',
    descriptionZh: '质量会相对于成本、延迟和失败运行进行归一化。',
    weight: 0.10,
  },
] as const

export default function PillarsPage() {
  const lb = loadLeaderboard()
  const agents = rankedAgents()
  const pillarNames = Object.keys(lb.pillar_elo ?? {})

  return (
    <>
      <PageHero
        eyebrow={<T en="Scoring Pillars" zh="评分维度" />}
        title={<T en="The public score separates judgment from evidence." zh="公开主分把评审质量与证据质量分开。" />}
        intro={<T en="The live leaderboard is intentionally simple: judge Elo measures comparative report quality, while the grounding gate checks whether citations resolve and quotes match. The broader verifier taxonomy below shows where the scoring stack can expand." zh="当前公开榜单刻意保持简单：判官 Elo 衡量报告质量，接地门核验引用是否可达、引文是否匹配。下方的验证器分类展示评分体系可以继续扩展的方向。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Public axes" zh="公开轴" />} value="2" detail={<T en="judge Elo and grounding gate" zh="判官 Elo 与接地门" />} />
          <MetricCard label={<T en="Verifier families" zh="验证器家族" />} value="7" detail={<T en="taxonomy for deeper audits" zh="用于深层审计的分类" />} />
          <MetricCard label={<T en="Bootstrap" zh="自助采样" />} value="1000" detail={<T en="resamples for 95% confidence intervals" zh="次重采样以得到 95% 置信区间" />} />
          <MetricCard label={<T en="Agents" zh="智能体" />} value={String(agents.length)} detail={<T en="ranked under the same scoring contract" zh="在同一评分契约下排名" />} />
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-4 lg:grid-cols-7">
        <div className="card p-6 lg:col-span-3">
          <span className="label-caps"><T en="Composite formula" zh="综合公式" /></span>
          <p className="mt-4 font-serif text-3xl leading-tight text-ink">
            score = judge Elo × grounding gate
          </p>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            <T
              en="The gate is the mean of citation reachability and quote verification. Raw judge Elo remains visible, but it does not decide the public ranking by itself."
              zh="接地门是引用可达率与引文核实率的均值。裸判官 Elo 仍然公开展示，但它不会单独决定公开排名。"
            />
          </p>
        </div>
        <div className="card p-6 lg:col-span-4">
          <span className="label-caps"><T en="Leaders by public score" zh="按公开主分的领先者" /></span>
          <div className="mt-5 space-y-3">
            {agents.slice(0, 5).map((agent) => {
              const meta = agentMeta(agent.id)
              const score = truthScore(agent)
              const gate = groundingGatePct(agent)
              const topScore = truthScore(agents[0])
              return (
                <div key={agent.id}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="font-medium text-ink">{meta.display}</span>
                    <span className="tnum text-muted">{fmt(score)}{gate == null ? '' : ` · gate ${gate.toFixed(0)}%`}</span>
                  </div>
                  <div className="h-2 rounded-pill bg-surface-mid">
                    <div className="h-full rounded-pill" style={{ width: `${Math.min(100, (score / Math.max(1, topScore)) * 100)}%`, backgroundColor: meta.color }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <section className="container mt-10 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {PILLARS.map((pillar, i) => (
          <article key={pillar.name} className="card card-lift p-6">
            <div className="flex items-center justify-between gap-3">
              <span className="label-caps"><T en={`Pillar ${i + 1}`} zh={`维度 ${i + 1}`} /></span>
              <span className="rounded-pill bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand">{Math.round(pillar.weight * 100)}%</span>
            </div>
            <h2 className="mt-4 font-serif text-h-sm text-ink"><T en={pillar.name} zh={pillar.nameZh} /></h2>
            <p className="mt-2 text-sm leading-relaxed text-muted"><T en={pillar.description} zh={pillar.descriptionZh} /></p>
            <div className="mt-5 h-2 rounded-pill bg-surface-mid">
              <div className="h-full rounded-pill bg-brand" style={{ width: `${pillar.weight * 100 * 3.2}%` }} />
            </div>
          </article>
        ))}
      </section>

      {pillarNames.length > 0 ? (
        <section className="container mt-10">
          <div className="card p-6">
            <span className="label-caps"><T en="Available pillar Elo tables" zh="可用的分维度 Elo 表" /></span>
            <div className="mt-4 flex flex-wrap gap-2">
              {pillarNames.map((name) => (
                <span key={name} className="pill capitalize">{name.replaceAll('_', ' ')}</span>
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </>
  )
}
