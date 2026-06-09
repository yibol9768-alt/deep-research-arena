'use client'

import { useMemo, useState } from 'react'
import { Chip } from '@/components/ui/chip'
import { AgentCard } from '@/components/agents/agent-card'
import { agentMeta } from '@/lib/providers'
import { T } from '@/components/i18n/t'
import type { RankedAgent } from '@/lib/data/types'

const FAMILIES = [
  'All families',
  'Code-as-Action',
  'Plan-Execute-Report',
  'Multi-agent',
  'Graph-based',
  'Memory-augmented',
  'ReAct',
] as const

const FAMILY_ZH: Record<(typeof FAMILIES)[number], string> = {
  'All families': '全部家族',
  'Code-as-Action': 'Code-as-Action',
  'Plan-Execute-Report': 'Plan-Execute-Report',
  'Multi-agent': 'Multi-agent',
  'Graph-based': 'Graph-based',
  'Memory-augmented': 'Memory-augmented',
  ReAct: 'ReAct',
}

export function AgentsClient({ agents }: { agents: RankedAgent[] }) {
  const [family, setFamily] = useState<(typeof FAMILIES)[number]>('All families')

  const merged = useMemo(
    () =>
      agents
        .map((agent) => ({ ...agent, family: agentMeta(agent.id).family }))
        .sort((a, b) => a.rank - b.rank),
    [agents],
  )

  const filtered = family === 'All families' ? merged : merged.filter((agent) => agent.family === family)
  const familyCount = new Set(merged.map((agent) => agent.family)).size

  return (
    <div className="container py-12 md:py-16">
      <header className="max-w-3xl">
        <span className="label-caps">
          <T en="Agents" zh="智能体" />
        </span>
        <h1 className="mt-3 font-serif text-h-md leading-tight md:text-display-lg">
          <T
            en={`${merged.length} agents across ${familyCount} architecture families.`}
            zh={`${merged.length} 个智能体，覆盖 ${familyCount} 类架构。`}
          />
        </h1>
        <p className="mt-3 text-base leading-relaxed text-muted md:text-lg">
          <T
            en="Every framework uses the same frozen task set and sandbox search contract. The cards are ordered by the public score: judge Elo multiplied by the grounding gate."
            zh="每个框架都使用同一批冻结任务与同一套沙箱搜索契约。卡片按公开主分排序：判官 Elo 乘以接地门。"
          />
        </p>
      </header>

      <div className="no-scrollbar scroll-fade-x mt-8 flex gap-2 overflow-x-auto pb-2">
        {FAMILIES.map((f) => (
          <Chip key={f} active={f === family} tone="brand" onClick={() => setFamily(f)}>
            <T en={f} zh={FAMILY_ZH[f]} />
          </Chip>
        ))}
      </div>

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {filtered.map((agent) => (
          <AgentCard key={agent.id} agent={agent} rank={agent.rank} />
        ))}
      </div>

      <p className="mt-10 text-xs text-muted">
        <T
          en={`Showing ${filtered.length} of ${merged.length} agents · ranks use truth-gated score, not raw judge Elo.`}
          zh={`显示 ${merged.length} 个智能体中的 ${filtered.length} 个 · 排名使用真值门控得分，而非裸判官 Elo。`}
        />
      </p>

      {filtered.length === 0 && (
        <div className="mt-12 rounded-card border border-dashed border-hairline p-8 text-center text-sm text-muted">
          <T en="No agents match this family filter." zh="没有智能体符合当前家族筛选。" />
        </div>
      )}
    </div>
  )
}
