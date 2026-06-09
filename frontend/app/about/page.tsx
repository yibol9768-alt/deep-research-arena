import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

const TIMELINE = [
  ['2026-04-15', 'Sandbox and scoring prototype', '沙箱与评分原型'],
  ['2026-04-20', 'First framework inventory and smoke tests', '首次框架盘点与冒烟测试'],
  ['2026-04-27', 'Deep task expansion and Elo plan', '深度任务扩展与 Elo 方案'],
  ['2026-05-06', 'Review pass and analysis artifacts', '复审与分析产出'],
  ['2026-05-13', 'Public frontend and reproducible snapshot', '公开前端与可复现快照'],
]

export default function AboutPage() {
  return (
    <>
      <PageHero
        eyebrow={<T en="About" zh="关于" />}
        title={<T en="A lab notebook became a benchmark because the failures were measurable." zh="一本实验笔记成长为一项基准，因为那些失败是可以被度量的。" />}
        intro={<T en="Deep Research Arena started as a practical question: which open-source deep-research framework is reliable enough to trust? The answer required a frozen web, task-specific checklists, and evidence-level scoring." zh="Deep Research Arena 始于一个务实的问题：哪一个开源深度研究框架可靠到值得信任？要回答它，需要一个冻结的网络、针对任务的检查清单，以及证据级别的评分。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Agents" zh="智能体" />} value="12" detail={<T en="open-source agents and variants" zh="开源智能体及其变体" />} />
          <MetricCard label={<T en="Tasks" zh="任务" />} value="100" detail={<T en="cross-site deep prompts" zh="跨站点的深度提问" />} />
          <MetricCard label={<T en="Battles" zh="对战" />} value="2,615" detail={<T en="pairwise judge decisions in the snapshot" zh="当前快照中的成对判官决策" />} />
          <MetricCard label={<T en="License" zh="许可" />} value="Open" detail={<T en="code, data, and methodology" zh="代码、数据与方法论" />} />
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink"><T en="Project principle" zh="项目原则" /></h2>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            <T
              en="The benchmark rewards reports that can be audited. It does not assume that length, confidence, or polished prose imply truth. Every claim should point back to a reachable sandbox source."
              zh="该基准奖励可被审计的报告。它不会因为篇幅、语气自信或文笔精炼就认定内容为真。每一处论断都应能追溯到可访问的沙箱来源。"
            />
          </p>
        </div>
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink"><T en="Citation" zh="引用" /></h2>
          <pre className="mt-3 overflow-auto rounded-tab bg-surface-low p-4 text-xs text-muted">
{`@misc{deepresearcharena2026,
  title = {Deep Research Arena},
  year = {2026},
  note = {Reproducible Elo benchmark for Deep Research agents}
}`}
          </pre>
        </div>
      </section>

      <section className="container mt-10">
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink"><T en="Timeline" zh="时间线" /></h2>
          <div className="mt-6 space-y-4">
            {TIMELINE.map(([date, event, eventZh]) => (
              <div key={date} className="flex gap-4 border-l border-hairline pl-4">
                <span className="w-28 shrink-0 font-mono text-xs text-brand">{date}</span>
                <p className="text-sm text-muted"><T en={event} zh={eventZh} /></p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  )
}
