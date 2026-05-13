'use client'

import { useState, useMemo } from 'react'
import { Chip } from '@/components/ui/chip'
import { AgentCard } from '@/components/agents/agent-card'
import { allAgents } from '@/lib/providers'
import { useEffect } from 'react'
import type { RankedAgent } from '@/lib/data/types'

const FAMILIES = ['All families', 'ReAct', 'Plan-Execute-Report', 'Multi-agent', 'Code-as-Action', 'Graph-based', 'Memory-augmented'] as const

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
        <span className="label-caps">Agents</span>
        <h1 className="mt-3 font-serif text-h-md md:text-display-lg leading-tight">Eight frameworks · five families.</h1>
        <p className="mt-3 text-base leading-relaxed text-muted md:text-lg">
          Each agent runs the same 107 sandbox tasks through the same Tavily/Firecrawl shim. The only thing that
          changes is the framework's planning and citation strategy.
        </p>
      </header>

      {/* Family filter */}
      <div className="no-scrollbar scroll-fade-x mt-8 flex gap-2 overflow-x-auto pb-2">
        {FAMILIES.map((f) => (
          <Chip key={f} active={f === family} tone="brand" onClick={() => setFamily(f)}>
            {f}
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
        Showing {filtered.length} of {merged.length} agents · ranks computed from Composite Elo v2.
      </p>

      {filtered.length === 0 && (
        <div className="mt-12 rounded-card border border-dashed border-hairline p-8 text-center text-sm text-muted">
          No agents in this family — yet. Add one in <code>lib/providers.ts</code>.
        </div>
      )}
    </div>
  )
}
