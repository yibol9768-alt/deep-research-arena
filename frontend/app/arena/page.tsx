import { T } from '@/components/i18n/t'
import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { loadArenaV2 } from '@/lib/data/load-arena-v2'
import { ArenaClient } from './arena-client'
import { fmt } from '@/lib/format'

export const dynamic = 'force-static'

export default function ArenaPage() {
  const arena = loadArenaV2()
  if (!arena) {
    return <div className="container py-20 text-sm text-muted">Arena snapshot missing.</div>
  }

  return (
    <>
      <PageHero
        eyebrow={<T en="Arena" zh="竞技场" />}
        title={<T en="Compare any two runs side by side." zh="任选两条运行并排对比。" />}
        intro={
          <T
            en="Pick any two harness × LLM runs and inspect the same public signals side by side: Arena score, jury Elo, win rate, grounding, and the decidable truth score."
            zh="任选两条「框架 × 主干模型」运行,并排查看同一组公开信号：Arena 主分、陪审团 Elo、胜率、接地率与可判定真值分。"
          />
        }
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Candidates" zh="候选运行" />} value={String(arena.entries.length)} detail={<T en="harness × LLM runs" zh="框架 × 主干模型运行" />} />
          <MetricCard label={<T en="Task set" zh="任务集" />} value={arena.task_set.match(/\d+/)?.[0] ?? '13'} detail={<T en="frozen diagnostic tasks" zh="冻结诊断任务" />} />
          <MetricCard label={<T en="Jury records" zh="陪审团判例" />} value={fmt(arena.n_judge_records_total)} detail={arena.judges.join(' · ')} />
          <MetricCard label={<T en="CI" zh="置信区间" />} value="95%" detail={<T en="bootstrap interval on win rate" zh="胜率自助法区间" />} />
        </div>
      </PageHero>

      <ArenaClient entries={arena.entries} />
    </>
  )
}
