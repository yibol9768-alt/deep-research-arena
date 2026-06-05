import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft } from 'lucide-react'
import { getTask, loadChecklists, loadTasks } from '@/lib/data/tasks'
import { MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

export function generateStaticParams() {
  return loadTasks().map((task) => ({ id: task.id }))
}

export default function TaskDetailPage({ params }: { params: { id: string } }) {
  const task = getTask(params.id)
  if (!task) notFound()
  const checklist = loadChecklists()[task.id] ?? []

  return (
    <div className="container py-12 md:py-16">
      <Link href="/tasks" className="inline-flex items-center gap-2 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> <T en="Tasks" zh="任务" />
      </Link>

      <header className="mt-6 max-w-4xl">
        <span className="label-caps tnum">{task.id}</span>
        <h1 className="mt-3 font-serif text-h-md leading-tight text-ink md:text-display-lg">{task.title}</h1>
        <p className="mt-4 text-sm leading-relaxed text-muted">{task.domain} · {task.intentType}</p>
      </header>

      <section className="mt-8 grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label={<T en="Difficulty" zh="难度" />} value={String(task.difficulty)} detail={<T en="1-5 scale" zh="1-5 分制" />} />
        <MetricCard label={<T en="Steps" zh="步骤数" />} value={String(task.expectedSteps)} detail={<T en="expected browser/search actions" zh="预期的浏览/搜索操作" />} />
        <MetricCard label={<T en="Sites" zh="站点" />} value={String(task.sites.length)} detail={task.sites.join(', ')} />
        <MetricCard label={<T en="Checklist" zh="清单" />} value={String(task.checklistItems)} detail={<T en="auditable requirements" zh="可审计的需求项" />} />
      </section>

      <section className="mt-10 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
        <article className="card p-7">
          <h2 className="font-serif text-h-sm text-ink"><T en="Prompt" zh="提示词" /></h2>
          <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-muted">{task.prompt}</p>
        </article>
        <aside className="card p-6">
          <h2 className="font-serif text-h-sm text-ink"><T en="Audit checklist" zh="审计清单" /></h2>
          <ol className="mt-4 max-h-[620px] space-y-3 overflow-auto pr-2">
            {checklist.slice(0, 18).map((item, i) => (
              <li key={item} className="flex gap-3 text-sm leading-relaxed text-muted">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-mid text-xs font-medium text-ink tnum">{i + 1}</span>
                <span>{item}</span>
              </li>
            ))}
          </ol>
        </aside>
      </section>
    </div>
  )
}
