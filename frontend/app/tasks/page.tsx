import Link from 'next/link'
import { Database, Filter, Search } from 'lucide-react'
import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { loadTasks, taskStats } from '@/lib/data/tasks'

export const dynamic = 'force-static'

const INTENT_COLORS: Record<string, string> = {
  recommendation: '#7F4BF3',
  comparison: '#1c7ff8',
  debunking: '#E5484D',
  causal: '#F5B800',
  timeline: '#34A853',
  enumeration: '#FF9900',
}

export default function TasksPage() {
  const tasks = loadTasks()
  const stats = taskStats()
  const featured = tasks.slice(0, 18)
  const intents = Array.from(new Set(tasks.map((task) => task.intentType))).sort()

  return (
    <>
      <PageHero
        eyebrow="Tasks Explorer"
        title="100 sandbox-grounded research tasks, built to expose citation failure."
        intro="Every task is frozen against the same shopping, forum, and Wikipedia-style sandbox. The cards below are static and shareable today; the full filter UI can hydrate on top of the same data contract."
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Tasks" value={String(stats.count)} detail="cross-site deep research prompts" />
          <MetricCard label="Intent types" value={String(stats.intents)} detail="recommendation, comparison, debunking, causal, timeline, enumeration" />
          <MetricCard label="Checklist items" value={String(stats.checklistItems)} detail="human-auditable coverage criteria" />
          <MetricCard label="Avg difficulty" value={stats.avgDifficulty.toFixed(1)} detail="1-5 benchmark scale" />
        </div>
      </PageHero>

      <section className="container">
        <div className="card overflow-hidden">
          <div className="flex flex-col gap-4 border-b border-hairline p-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="font-serif text-h-sm text-ink">Task inventory</h2>
              <p className="mt-1 text-sm text-muted">A high-density browse surface for the benchmark set.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="pill"><Search className="h-3.5 w-3.5" /> Search-ready</span>
              <span className="pill"><Filter className="h-3.5 w-3.5" /> Filter schema</span>
              <span className="pill"><Database className="h-3.5 w-3.5" /> Static JSON</span>
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
          {featured.map((task) => (
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
                <Stat label="Sites" value={task.sites.length ? task.sites.join('/') : 'n/a'} />
                <Stat label="URLs" value={String(task.requiredUrls)} />
                <Stat label="Checks" value={String(task.checklistItems)} />
              </div>
            </Link>
          ))}
        </div>
      </section>
    </>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="label-caps">{label}</p>
      <p className="mt-1 truncate font-medium text-ink tnum">{value}</p>
    </div>
  )
}
