import { rankedModelAgents, modelMeta } from '@/lib/data/load-models'
import { LeaderboardTable } from '@/components/home/leaderboard-table'
import { CompositeBar } from '@/components/home/composite-bar'
import { PillarBars } from '@/components/home/pillar-bars'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

export const metadata = {
  title: 'Backbone-LLM Leaderboard — Deep Research Arena',
  description:
    'Same minimal deep-research scaffold, varying only the backbone LLM. Truth-gated Elo with citation reachability and quote verification.',
}

export default function ModelsPage() {
  const agents = rankedModelAgents()
  const meta = modelMeta()

  const byReach = [...agents]
    .map((a) => ({ id: a.id, value: a.reachability_pct ?? 0 }))
    .sort((a, b) => b.value - a.value)
  const byQuote = [...agents]
    .map((a) => ({ id: a.id, value: a.url_veracity_pct ?? 0 }))
    .sort((a, b) => b.value - a.value)

  return (
    <>
      <div className="container pt-12">
        <h1 className="text-[28px] font-semibold tracking-tight md:text-[34px]">
          <T en="Deep-Research by Backbone LLM" zh="按基座大模型对比深度研究" />
        </h1>
        <p className="mt-3 max-w-3xl text-[15px] leading-relaxed opacity-80">
          <T
            en={`The same minimal deep-research scaffold, varying only the backbone LLM — ${agents.length} models over ${meta.n_tasks} cross-site tasks (${meta.n_runs} judge battles). Ranked by truth-gated Elo: pairwise LLM-judge Elo (3-judge PoLL jury) scaled by the grounding gate. Reach% and Quote% are judge-free grounding, so a fluent model that cites unreachable sources cannot top the board.`}
            zh={`同一套最小深度研究脚手架,只替换基座大模型 —— ${agents.length} 个模型,${meta.n_tasks} 个跨站任务(${meta.n_runs} 场判官对战)。按真值门控 Elo 排序:成对 LLM 判官 Elo(三判官 PoLL)再乘以接地门。Reach% / Quote% 是不依赖判官的接地信号,写得再流畅但引用打不开也无法登顶。`}
          />
        </p>
      </div>

      <div className="container mt-10 space-y-12 pb-20">
        <LeaderboardTable agents={agents} />

        <CompositeBar
          agents={agents}
          title={<T en="Judge Elo (raw)" zh="裸判官 Elo" />}
          subtitle={
            <T
              en="Pairwise Bradley-Terry · 3-judge PoLL jury · position-debiased · bootstrap 95% CI · before the grounding gate"
              zh="成对 Bradley-Terry · 三判官 PoLL · 位置去偏 · 自助 95% 置信区间 · 未经接地门控"
            />
          }
        />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <PillarBars
            title={<T en="Citation reachability" zh="引用可达率" />}
            subtitle={
              <T
                en="Share of cited URLs that actually resolve in the sandbox"
                zh="所引用 URL 在沙箱中真实可达的比例"
              />
            }
            accentColor="#7F4BF3"
            rows={byReach}
            suffix="%"
          />
          <PillarBars
            title={<T en="Quote-verified citations" zh="引文核实率" />}
            subtitle={
              <T
                en="Cited page actually contains the quoted evidence"
                zh="被引页面确实包含所引述的证据"
              />
            }
            accentColor="#1c7ff8"
            rows={byQuote}
            suffix="%"
          />
        </div>
      </div>
    </>
  )
}
