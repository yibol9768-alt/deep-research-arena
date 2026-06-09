import type { ReactNode } from 'react'
import Link from 'next/link'
import { Database, Filter, Search } from 'lucide-react'
import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'
import { loadTasks, taskStats } from '@/lib/data/tasks'

export const dynamic = 'force-static'

const INTENT_COLORS: Record<string, string> = {
  'market-intelligence': '#7F4BF3',
  recommendation: '#7F4BF3',
  comparison: '#1c7ff8',
  debunking: '#E5484D',
  causal: '#F5B800',
  timeline: '#34A853',
  enumeration: '#FF9900',
  unknown: '#494551',
}

export default function TasksPage() {
  const tasks = loadTasks()
  const stats = taskStats()
  const visibleTasks = tasks
  const intents = Array.from(new Set(tasks.map((task) => task.intentType))).sort()

  return (
    <>
      <PageHero
        eyebrow={<T en="Tasks Explorer" zh="任务浏览器" />}
        title={<T en={`${stats.count} sandbox-grounded research tasks, built to expose citation failure.`} zh={`${stats.count} 个基于沙盒的研究任务，专为暴露引用失败而设计。`} />}
        intro={<T en="Each prompt fixes the same three-site sandbox, expected source coverage, and an audit checklist. The full task set is exposed here so results can be traced back to the exact research demand." zh="每个提示词都固定同一套三站点沙箱、来源覆盖要求和审计清单。这里展示完整任务集，便于把结果追溯到具体研究需求。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Tasks" zh="任务" />} value={String(stats.count)} detail={<T en="cross-site deep research prompts" zh="跨站点深度研究提示" />} />
          <MetricCard label={<T en="Intent types" zh="意图类型" />} value={String(stats.intents)} detail={<T en="market intelligence, comparison, debunking, causal, timeline, enumeration" zh="市场情报、对比、辟谣、因果、时间线、枚举" />} />
          <MetricCard label={<T en="Checklist items" zh="核查清单项" />} value={String(stats.checklistItems)} detail={<T en="human-auditable coverage criteria" zh="可人工审核的覆盖标准" />} />
          <MetricCard label={<T en="Avg difficulty" zh="平均难度" />} value={stats.avgDifficulty.toFixed(1)} detail={<T en="1-5 benchmark scale" zh="1-5 基准量表" />} />
        </div>
      </PageHero>

      <section className="container">
        <div className="card overflow-hidden">
          <div className="flex flex-col gap-4 border-b border-hairline p-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="font-serif text-h-sm text-ink"><T en="Task inventory" zh="任务清单" /></h2>
              <p className="mt-1 text-sm text-muted"><T en="Intent mix, source contract, and checklist size for the frozen benchmark set." zh="冻结基准集的意图分布、来源契约和清单规模。" /></p>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="pill"><Search className="h-3.5 w-3.5" /> <T en={`${stats.count} prompts`} zh={`${stats.count} 个提示词`} /></span>
              <span className="pill"><Filter className="h-3.5 w-3.5" /> <T en={`${stats.intents} intent types`} zh={`${stats.intents} 类意图`} /></span>
              <span className="pill"><Database className="h-3.5 w-3.5" /> <T en="Static JSON + checklists" zh="静态 JSON + 清单" /></span>
            </div>
          </div>
          <div className="grid grid-cols-1 divide-y divide-hairline lg:grid-cols-3 lg:divide-x lg:divide-y-0">
            {intents.map((intent) => {
              const group = tasks.filter((task) => task.intentType === intent)
              return (
                <div key={intent} className="p-5">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="font-serif text-lg capitalize text-ink">{intent}</h3>
                    <span className="rounded-pill px-2 py-0.5 text-xs font-medium text-white" style={{ backgroundColor: INTENT_COLORS[intent] ?? '#7F4BF3' }}>
                      {group.length}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-muted">
                    {group.slice(0, 3).map((task) => task.domain).join(' · ')}
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
                <span className="rounded-pill px-2 py-0.5 text-[11px] font-medium text-white" style={{ backgroundColor: INTENT_COLORS[task.intentType] ?? '#7F4BF3' }}>
                  {task.intentType}
                </span>
              </div>
              <p className="mt-4 line-clamp-3 text-sm leading-relaxed text-muted">{task.prompt}</p>
              <div className="mt-5 grid grid-cols-3 gap-3 text-xs">
                <Stat label={<T en="Sites" zh="站点" />} value={task.sites.length ? task.sites.join('/') : 'n/a'} />
                <Stat label={<T en="URLs" zh="网址" />} value={String(task.requiredUrls)} />
                <Stat label={<T en="Checks" zh="核查项" />} value={String(task.checklistItems)} />
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
