import { PageStub } from '@/components/layout/page-stub'

export default function InsightsPage() {
  return (
    <PageStub
      eyebrow="Findings & Stories"
      title="Five findings that change how you benchmark Deep Research."
      intro="Long-form scrollytelling pieces. Each finding is a self-contained article with GSAP-pinned scroll narratives, embedded data viz, and pull-quotes from real agent reports."
      upcoming={[
        {
          label: 'F6 · Fluent Hallucination',
          description: 'gpt-researcher writes the most beautiful prose — and fakes 97% of its URLs',
        },
        { label: 'Dual-Judge Effect', description: 'Switch the judge model family and 5 agents move ±150 Elo' },
        { label: 'Adapter Quality > Framework Reputation', description: 'DeerFlow gained +162 Elo without changing a line of core code' },
        { label: 'Length-Bias in LLM Judges', description: 'smolagents ranks #1 on RACE judge, #9 on truth — judges love long answers' },
        { label: 'Pareto Front', description: 'Only four agents are Pareto-optimal across quality and cost; the rest are dominated' },
      ]}
      related={[
        { href: '/methodology', label: 'Methodology' },
        { href: '/pillars', label: 'Pillar inventory' },
      ]}
    />
  )
}
