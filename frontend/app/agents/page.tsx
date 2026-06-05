'use client'

import { useState, useMemo } from 'react'
import { Chip } from '@/components/ui/chip'
import { AgentCard } from '@/components/agents/agent-card'
import { allAgents } from '@/lib/providers'
import { useEffect } from 'react'
import { T } from '@/components/i18n/t'
import type { RankedAgent } from '@/lib/data/types'

const FAMILIES = ['All families', 'ReAct', 'Plan-Execute-Report', 'Multi-agent', 'Code-as-Action', 'Graph-based', 'Memory-augmented'] as const

// Chinese labels for the family filter chips. Architectural-family names are a
// technical taxonomy (also used as filter values), so only the catch-all
// 'All families' is translated; the rest stay verbatim.
const FAMILY_ZH: Record<(typeof FAMILIES)[number], string> = {
  'All families': '全部家族',
  ReAct: 'ReAct',
  'Plan-Execute-Report': 'Plan-Execute-Report',
  'Multi-agent': 'Multi-agent',
  'Code-as-Action': 'Code-as-Action',
  'Graph-based': 'Graph-based',
  'Memory-augmented': 'Memory-augmented',
}

// We need the leaderboard data on the client. Since the file lives outside the
// Next.js boundary, we pre-bake it into a JSON fetched at build time via a
// route handler. For now we recompute via the server-side import wrapper: we
// dynamically import the loader and feed result to the client component.

import { useRanked } from './_data'

export default function AgentsHubPage() {
  const all = useRanked()
  const [family, setFamily] = useState<(typeof FAMILIES)[number]>('All families')

  const merged = useMemo(() => {
    const meta = allAgents()
    const metaById = new Map(meta.map((m) => [m.id, m]))
    return all
      .map((a) => {
        const m = metaById.get(a.id)
        // Even if not in providers.ts we still show the row (family will be 'ReAct' fallback)
        return { ...a, family: (m?.family ?? 'ReAct') as string }
      })
      .sort((a, b) => b.elo - a.elo)
  }, [all])

  const filtered = family === 'All families' ? merged : merged.filter((a) => a.family === family)

  return (
    <div className="container py-12 md:py-16">
      <header className="max-w-3xl">
        <span className="label-caps"><T en="Agents" zh="智能体" /></span>
        <h1 className="mt-3 font-serif text-h-md md:text-display-lg leading-tight">
          <T en="Eight frameworks · five families." zh="八种框架 · 五个家族。" />
        </h1>
        <p className="mt-3 text-base leading-relaxed text-muted md:text-lg">
          <T
            en="Each agent runs the same 100 sandbox tasks through the same search shim. The only thing that changes is the framework's planning and citation strategy."
            zh="每个智能体都通过同一套搜索代理层运行相同的 100 个沙箱任务。唯一变化的是框架的规划与引用策略。"
          />
        </p>
      </header>

      {/* Family filter */}
      <div className="no-scrollbar scroll-fade-x mt-8 flex gap-2 overflow-x-auto pb-2">
        {FAMILIES.map((f) => (
          <Chip key={f} active={f === family} tone="brand" onClick={() => setFamily(f)}>
            <T en={f} zh={FAMILY_ZH[f]} />
          </Chip>
        ))}
      </div>

      {/* Cards */}
      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {filtered.map((a) => (
          <AgentCard key={a.id} agent={a} rank={merged.findIndex((m) => m.id === a.id) + 1} />
        ))}
      </div>

      {/* Footnote */}
      <p className="mt-10 text-xs text-muted">
        <T
          en={`Showing ${filtered.length} of ${merged.length} agents · ranks computed from truth-gated Elo (judge Elo × grounding gate).`}
          zh={`显示 ${merged.length} 个智能体中的 ${filtered.length} 个 · 排名依据真值门控 Elo（判官 Elo × 接地门）计算。`}
        />
      </p>

      {filtered.length === 0 && (
        <div className="mt-12 rounded-card border border-dashed border-hairline p-8 text-center text-sm text-muted">
          <T en="No agents in this family — yet. Add one in " zh="该家族暂无智能体。请在以下文件中添加：" />
          <code>lib/providers.ts</code>
          <T en="." zh="" />
        </div>
      )}
    </div>
  )
}
