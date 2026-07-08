'use client'

import { useMemo, useState } from 'react'
import { Chip } from '@/components/ui/chip'
import { AgentCard } from '@/components/agents/agent-card'
import { agentMeta } from '@/lib/providers'
import { T } from '@/components/i18n/t'
import type { HarnessAgg } from '@/lib/data/load-arena-v2'

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

export function AgentsClient({ harnesses, nBackbones }: { harnesses: HarnessAgg[]; nBackbones: number }) {
  const [family, setFamily] = useState<(typeof FAMILIES)[number]>('All families')

  const merged = useMemo(
    () => harnesses.map((h, i) => ({ ...h, rank: i + 1, family: agentMeta(h.id).family })),
    [harnesses],
  )

  const filtered = family === 'All families' ? merged : merged.filter((h) => h.family === family)
  const familyCount = new Set(merged.map((h) => h.family)).size

  return (
    <div className="container py-12 md:py-16">
      <header className="max-w-3xl">
        <span className="label-caps">
          <T en="Harnesses" zh="框架" />
        </span>
        <h1 className="mt-3 font-serif text-h-md leading-tight md:text-display-lg">
          <T
            en={`${merged.length} research harnesses across ${familyCount} architecture families.`}
            zh={`${merged.length} 个研究框架，覆盖 ${familyCount} 类架构。`}
          />
        </h1>
        <p className="mt-3 text-base leading-relaxed text-muted md:text-lg">
          <T
            en={`Every harness runs the same frozen tasks on ${nBackbones} backbone LLMs under the same sandbox search contract. Cards are ordered by the Arena score (reach^1.5 × jury win rate), averaged across backbones; the bars inside each card show the per-LLM scores.`}
            zh={`每个框架都在 ${nBackbones} 个主干模型上运行同一批冻结任务、使用同一套沙箱搜索契约。卡片按跨模型平均的 Arena 主分（可达率^1.5 × 陪审团胜率）排序,卡片内的条形是各模型的单独得分。`}
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
        {filtered.map((h) => (
          <AgentCard key={h.id} harness={h} rank={h.rank} />
        ))}
      </div>

      <p className="mt-10 text-xs text-muted">
        <T
          en={`Showing ${filtered.length} of ${merged.length} harnesses · ranks use the cross-LLM average Arena score.`}
          zh={`显示 ${merged.length} 个框架中的 ${filtered.length} 个 · 排名使用跨模型平均 Arena 主分。`}
        />
      </p>

      {filtered.length === 0 && (
        <div className="mt-12 rounded-card border border-dashed border-hairline p-8 text-center text-sm text-muted">
          <T en="No harnesses match this family filter." zh="没有框架符合当前家族筛选。" />
        </div>
      )}
    </div>
  )
}
