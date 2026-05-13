import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft } from 'lucide-react'
import { getTask, loadChecklists, loadTasks } from '@/lib/data/tasks'
import { MetricCard } from '@/components/layout/metric-card'

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
        <ArrowLeft className="h-4 w-4" /> Tasks
      </Link>

      <header className="mt-6 max-w-4xl">
        <span className="label-caps tnum">{task.id}</span>
        <h1 className="mt-3 font-serif text-h-md leading-tight text-ink md:text-display-lg">{task.title}</h1>
        <p className="mt-4 text-sm leading-relaxed text-muted">{task.domain} · {task.intentType}</p>
      </header>

      <section className="mt-8 grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Difficulty" value={String(task.difficulty)} detail="1-5 scale" />
        <MetricCard label="Steps" value={String(task.expectedSteps)} detail="expected browser/search actions" />
        <MetricCard label="Sites" value={String(task.sites.length)} detail={task.sites.join(', ')} />
        <MetricCard label="Checklist" value={String(task.checklistItems)} detail="auditable requirements" />
      </section>

      <section className="mt-10 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
        <article className="card p-7">
          <h2 className="font-serif text-h-sm text-ink">Prompt</h2>
          <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-muted">{task.prompt}</p>
        </article>
        <aside className="card p-6">
          <h2 className="font-serif text-h-sm text-ink">Audit checklist</h2>
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
