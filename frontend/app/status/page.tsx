import { CheckCircle2, Clock3, Database, FileJson2 } from 'lucide-react'
import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'
import { leaderboardMtime, loadLeaderboard, rankedAgents } from '@/lib/data/load-leaderboard'
import { taskStats } from '@/lib/data/tasks'
import { fmt } from '@/lib/format'

export const dynamic = 'force-static'

const CHECKS = [
  {
    label: 'Leaderboard snapshot',
    labelZh: '排行榜快照',
    detail: 'Deep v3 cache is present and ranked by truth-gated score.',
    detailZh: 'Deep v3 缓存已就绪，并按真值门控主分排名。',
  },
  {
    label: 'Task corpus',
    labelZh: '任务语料',
    detail: 'All 100 task JSON files and their audit checklists are discoverable at build time.',
    detailZh: '100 个任务 JSON 与对应审核清单均可在构建时读取。',
  },
  {
    label: 'Grounding fields',
    labelZh: '接地字段',
    detail: 'Reachability and quote-veracity fields are exposed on agent pages and tables.',
    detailZh: '引用可达率与引文核实率已在智能体页和表格中展示。',
  },
]

const LIMITS = [
  {
    label: 'Static deploy',
    labelZh: '静态部署',
    detail: 'This site is exported as static files. It shows the latest committed snapshot, not a runtime worker dashboard.',
    detailZh: '本站导出为静态文件，展示最近提交的快照，而不是运行时 worker 面板。',
  },
  {
    label: 'Judge dependency',
    labelZh: '判官依赖',
    detail: 'Pairwise quality still depends on the current jury cache; grounding is kept separate to expose unsupported fluency.',
    detailZh: '成对质量仍依赖当前陪审团缓存；接地分单独保留，用于暴露缺乏支撑的流畅回答。',
  },
  {
    label: 'Model board scope',
    labelZh: '模型榜范围',
    detail: 'The model board uses a fixed minimal DR protocol and should not be read as a general chatbot benchmark.',
    detailZh: '模型榜采用固定的最小 DR 协议，不应解读为通用聊天模型基准。',
  },
]

export default function StatusPage() {
  const leaderboard = loadLeaderboard()
  const agents = rankedAgents()
  const stats = taskStats()
  const lastUpdated = new Date(leaderboardMtime()).toLocaleDateString('en-US')

  return (
    <>
      <PageHero
        eyebrow={<T en="Benchmark Status" zh="基准状态" />}
        title={<T en="Current public snapshot." zh="当前公开快照。" />}
        intro={
          <T
            en="A compact health view for the data shipped with this static site: leaderboard cache, task corpus, grounding fields, and known limits."
            zh="这里汇总静态站点随包发布的数据健康状态：排行榜缓存、任务语料、接地字段与已知边界。"
          />
        }
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Agents" zh="智能体" />} value={String(agents.length)} detail={<T en="ranked in the public board" zh="进入公开榜单" />} />
          <MetricCard label={<T en="Tasks" zh="任务" />} value={String(stats.count)} detail={<T en="frozen sandbox prompts" zh="冻结沙盒提示" />} />
          <MetricCard label={<T en="Battles" zh="对战" />} value={fmt(leaderboard.n_runs)} detail={<T en="pairwise judge decisions" zh="成对判官决策" />} />
          <MetricCard label={<T en="Updated" zh="更新" />} value={lastUpdated} detail={<T en="leaderboard cache timestamp" zh="排行榜缓存时间戳" />} />
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-5 lg:grid-cols-[1.05fr_.95fr]">
        <div className="card p-6">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-good" />
            <h2 className="font-serif text-h-sm text-ink"><T en="Published Checks" zh="已发布检查" /></h2>
          </div>
          <div className="mt-5 space-y-4">
            {CHECKS.map((check) => (
              <div key={check.label} className="rounded-tab border border-hairline bg-surface-low p-4">
                <p className="text-sm font-medium text-ink"><T en={check.label} zh={check.labelZh} /></p>
                <p className="mt-1 text-sm leading-relaxed text-muted"><T en={check.detail} zh={check.detailZh} /></p>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-6">
          <div className="flex items-center gap-2">
            <Clock3 className="h-4 w-4 text-brand" />
            <h2 className="font-serif text-h-sm text-ink"><T en="Known Limits" zh="已知边界" /></h2>
          </div>
          <div className="mt-5 space-y-4">
            {LIMITS.map((limit) => (
              <div key={limit.label} className="rounded-tab border border-hairline bg-white p-4">
                <p className="text-sm font-medium text-ink"><T en={limit.label} zh={limit.labelZh} /></p>
                <p className="mt-1 text-sm leading-relaxed text-muted"><T en={limit.detail} zh={limit.detailZh} /></p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="container mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="card flex gap-4 p-5">
          <Database className="mt-1 h-5 w-5 text-brand" />
          <div>
            <h3 className="font-serif text-lg text-ink"><T en="Data contract" zh="数据契约" /></h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              <T
                en="The public pages read from committed JSON artifacts. A rebuild changes the visible site only after the cache and static export are regenerated."
                zh="公开页面读取已提交的 JSON 产物。只有重新生成缓存并导出静态站点后，页面才会显示新的结果。"
              />
            </p>
          </div>
        </div>
        <div className="card flex gap-4 p-5">
          <FileJson2 className="mt-1 h-5 w-5 text-brand" />
          <div>
            <h3 className="font-serif text-lg text-ink"><T en="Audit trail" zh="审计链路" /></h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              <T
                en="Each rank should trace back to a task, report, pairwise decision, bootstrap interval, and citation-verifier fields."
                zh="每个排名都应能追溯到任务、报告、成对判官决策、自助采样区间与引用核验字段。"
              />
            </p>
          </div>
        </div>
      </section>
    </>
  )
}
