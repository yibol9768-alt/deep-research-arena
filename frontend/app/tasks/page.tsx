import type { ReactNode } from 'react'
import Link from 'next/link'
import { Database, Filter, Search } from 'lucide-react'
import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'
import { loadTasks, taskStats } from '@/lib/data/tasks'

export const dynamic = 'force-static'

// Tri-source clusters are the v2 grouping facet; colors are assigned by the
// cluster's position in the sorted set so the palette stays stable.
const CLUSTER_PALETTE = [
  '#7F4BF3', '#1c7ff8', '#E5484D', '#F5B800', '#34A853', '#FF9900', '#0EA5E9',
  '#8B5CF6', '#EC4899', '#10B981', '#F97316', '#6366F1', '#14B8A6',
]

function clusterColor(cluster: string, all: string[]): string {
  const i = all.indexOf(cluster)
  return CLUSTER_PALETTE[(i < 0 ? 0 : i) % CLUSTER_PALETTE.length]
}

export default function TasksPage() {
  const tasks = loadTasks()
  const stats = taskStats()
  const visibleTasks = tasks
  const clusters = Array.from(new Set(tasks.map((task) => task.domain))).sort()

  return (
    <>
      <PageHero
        eyebrow={<T en="Tasks Explorer" zh="任务浏览器" />}
        title={<T en={`${stats.count} frozen research tasks.`} zh={`${stats.count} 个冻结研究任务。`} />}
        intro={<T en="Each task is a real user's question over the same three-site sandbox (shopping, forums, frozen wiki). The 100 tasks span 13 tri-source clusters and 7 research archetypes; every answer key and checklist is computed from the corpus, not hand-labeled, and coverage requirements live in a hidden spec axis rather than the prompt." zh="每个任务都是真实用户在同一套三站点沙箱(商店、论坛、冻结 wiki)上的提问。100 个任务覆盖 13 个三源簇和 7 种研究原型;答案键与清单全部由语料计算而非人工标注,覆盖要求放在隐藏的 spec 轴而不写进题面。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Tasks" zh="任务" />} value={String(stats.count)} detail={<T en="cross-site deep research prompts" zh="跨站点深度研究提示" />} />
          <MetricCard label={<T en="Archetypes" zh="研究原型" />} value="7" detail={<T en="buying dilemma, use-case fit, claim check, community vs ratings, value question, durability, evolution/explainer" zh="选购两难、场景匹配、断言核查、社区口碑 vs 评分、性价比、耐用/BIFL、演进/科普" />} />
          <MetricCard label={<T en="Typed checks" zh="可判定检查" />} value="3,478" detail={<T en="typed fact nuggets routed to scoring axes" zh="逐条路由到评分轴的带类型事实要点" />} />
          <MetricCard label={<T en="Tri-source clusters" zh="三源簇" />} value={String(clusters.length)} detail={<T en="shop census × forum activity × frozen wiki" zh="商店普查 × 论坛活跃度 × 冻结 wiki" />} />
        </div>
      </PageHero>

      <section className="container">
        <div className="card overflow-hidden">
          <div className="flex flex-col gap-4 border-b border-hairline p-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="font-serif text-h-sm text-ink"><T en="Task inventory" zh="任务清单" /></h2>
              <p className="mt-1 text-sm text-muted"><T en="Tri-source cluster mix and typed-checklist size for the frozen benchmark set." zh="冻结基准集的三源簇分布与可判定清单规模。" /></p>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="pill"><Search className="h-3.5 w-3.5" /> <T en={`${stats.count} prompts`} zh={`${stats.count} 个提示词`} /></span>
              <span className="pill"><Filter className="h-3.5 w-3.5" /> <T en={`${clusters.length} tri-source clusters`} zh={`${clusters.length} 个三源簇`} /></span>
              <span className="pill"><Database className="h-3.5 w-3.5" /> <T en="Static JSON + checklists" zh="静态 JSON + 清单" /></span>
            </div>
          </div>
          <div className="grid grid-cols-1 divide-y divide-hairline lg:grid-cols-3 lg:divide-x lg:divide-y-0">
            {clusters.map((cluster) => {
              const group = tasks.filter((task) => task.domain === cluster)
              return (
                <div key={cluster} className="p-5">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="font-serif text-lg capitalize text-ink">{cluster.replace(/_/g, ' ')}</h3>
                    <span className="rounded-pill px-2 py-0.5 text-xs font-medium text-white" style={{ backgroundColor: clusterColor(cluster, clusters) }}>
                      {group.length}
                    </span>
                  </div>
                  <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted">
                    {group.slice(0, 3).map((task) => task.title).join(' · ')}
                  </p>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <section className="container mt-10">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visibleTasks.map((task) => (
            <Link key={task.id} href={`/tasks/${task.id}`} className="card card-lift block p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="label-caps tnum">{task.id}</p>
                  <h3 className="mt-2 font-serif text-lg leading-snug text-ink">{task.title}</h3>
                </div>
                <span className="shrink-0 rounded-pill px-2 py-0.5 text-[11px] font-medium capitalize text-white" style={{ backgroundColor: clusterColor(task.domain, clusters) }}>
                  {task.domain.replace(/_/g, ' ')}
                </span>
              </div>
              <p className="mt-4 line-clamp-3 text-sm leading-relaxed text-muted">{task.prompt}</p>
              <div className="mt-5 text-xs">
                <Stat label={<T en="Sites" zh="站点" />} value={task.sites.length ? task.sites.join(' · ') : 'n/a'} />
              </div>
            </Link>
          ))}
        </div>
      </section>
    </>
  )
}

function Stat({ label, value }: { label: ReactNode; value: string }) {
  return (
    <div>
      <p className="label-caps">{label}</p>
      <p className="mt-1 truncate font-medium text-ink tnum">{value}</p>
    </div>
  )
}
