import { PageStub } from '@/components/layout/page-stub'

export default function ArenaPage() {
  return (
    <PageStub
      eyebrow="Live Arena · Beta"
      title="Pick two agents. See who wins."
      intro="An interactive 1v1 page that recomputes Bradley-Terry Elo, win-rate, and per-pillar margins on just the two agents you select. Their reports for any shared task render side-by-side with citation differences highlighted."
      upcoming={[
        { label: 'Mirror selectors', description: 'Two large agent cards facing each other, with a glowing ⚔️ VS in the middle' },
        { label: 'Head-to-head matrix', description: 'Win count on the 107 tasks · 7-pillar margin chart · local Bradley-Terry with p-value' },
        { label: 'Side-by-side reports', description: 'Pick a task both agents tackled · synchronized scrolling · diff-highlighted citations' },
        { label: 'Shareable URLs', description: '/arena?a=react-qwen35plus&b=gpt-researcher hydrates a snapshot you can share or screenshot' },
      ]}
      related={[
        { href: '/', label: 'Leaderboard' },
        { href: '/agents', label: 'Agents Hub' },
      ]}
    />
  )
}
