import { PageStub } from '@/components/layout/page-stub'

export default function TasksPage() {
  return (
    <PageStub
      eyebrow="Tasks"
      title="107 reproducible deep-research tasks."
      intro="An interactive explorer for every task in the benchmark — filterable by intent, domain, difficulty, and sandbox sites. Each task card opens a full-page detail view with the prompt, golden URL pool, agent reports, and per-pillar breakdown."
      upcoming={[
        {
          label: 'Filter rail',
          description: 'Intent (6 types) · Domain (electronics/medical/policy/...) · Sites (shopping/reddit/wiki) · Difficulty (1–5)',
        },
        {
          label: 'Task cards',
          description: 'task_id, intent badge, first 80 chars of prompt, sites used, mini-density plot of agent scores',
        },
        {
          label: 'Per-task detail page',
          description: 'Full prompt, must-cite URL pool by source, 8-agent ranking, per-pillar bars, embedded reports',
        },
        {
          label: 'Citation X-Ray (creative)',
          description: 'Hover any cited URL inside a report to see the actual sandbox page screenshot pop out',
        },
      ]}
      related={[
        { href: '/', label: 'Leaderboard' },
        { href: '/agents', label: 'Agents Hub' },
      ]}
    />
  )
}
