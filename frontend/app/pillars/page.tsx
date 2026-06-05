import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { loadLeaderboard, rankedAgents } from '@/lib/data/load-leaderboard'
import { agentMeta } from '@/lib/providers'
import { T } from '@/components/i18n/t'

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
        title={<T en="Seven verifier families decide the leaderboard, not one opaque judge score." zh="决定排行榜的是七类验证器家族，而非单一不透明的评审分数。" />}
        intro={<T en="Composite v3.1 is intentionally plural: citation reachability, evidence breadth, checklist coverage, LLM-judge quality, formatting integrity, and efficiency all pull rank in different directions." zh="综合分 v3.1 刻意采用多元设计：引用可达性、证据广度、清单覆盖度、LLM 评审质量、格式完整性与效率会从不同方向影响排名。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Pillars" zh="维度数" />} value="7" detail={<T en="weighted into composite v3.1" zh="加权计入综合分 v3.1" />} />
          <MetricCard label={<T en="Verifier files" zh="验证器文件" />} value="29" detail={<T en="URL, markdown, judge, and task coverage checks" zh="URL、markdown、评审与任务覆盖度检查" />} />
          <MetricCard label={<T en="Bootstrap" zh="自助采样" />} value="1000" detail={<T en="resamples for 95% confidence intervals" zh="次重采样以得到 95% 置信区间" />} />
          <MetricCard label={<T en="Agents" zh="智能体" />} value={String(agents.length)} detail={<T en="ranked under the same scoring contract" zh="在同一评分契约下排名" />} />
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-4 lg:grid-cols-7">
        <div className="card p-6 lg:col-span-3">
          <span className="label-caps"><T en="Composite formula" zh="综合公式" /></span>
          <p className="mt-4 font-serif text-3xl leading-tight text-ink">
            score = weighted pillars x grounding gate
          </p>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            <T
              en="The truth gate keeps fluent but unsupported reports from winning on style. Bradley-Terry then converts per-task pairwise outcomes into Elo with bootstrap confidence intervals."
              zh="真值门控可阻止行文流畅却缺乏支撑的报告仅凭文采取胜。随后由 Bradley-Terry 将逐任务的两两对战结果转换为带有自助置信区间的 Elo。"
            />
          </p>
        </div>
        <div className="card p-6 lg:col-span-4">
          <span className="label-caps"><T en="Live leaders by composite" zh="按综合得分的实时领先者" /></span>
          <div className="mt-5 space-y-3">
            {agents.slice(0, 5).map((agent) => {
              const meta = agentMeta(agent.id)
              return (
                <div key={agent.id}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="font-medium text-ink">{meta.display}</span>
                    <span className="tnum text-muted">{agent.elo.toFixed(1)}</span>
                  </div>
                  <div className="h-2 rounded-pill bg-surface-mid">
                    <div className="h-full rounded-pill" style={{ width: `${Math.min(100, (agent.elo / agents[0].elo) * 100)}%`, backgroundColor: meta.color }} />
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
