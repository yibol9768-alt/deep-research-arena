import { PageStub } from '@/components/layout/page-stub'

export default function PillarsPage() {
  return (
    <PageStub
      eyebrow="Pillars"
      title="Seven pillars · twenty-nine verifiers."
      intro="Composite v3.1 weighs each report across seven axes. This page will let you inspect each pillar in isolation, see which agent wins where, and read the verifier source code that produces the score."
      upcoming={[
        { label: 'Composite formula', description: 'KaTeX-rendered weighted-sum equation with each weight clickable to pillar detail' },
        { label: 'Pillar cards', description: 'Top-3 agent on each pillar, weight, definition, link to verifier source' },
        { label: 'Correlation heatmap', description: '7×7 matrix showing which pillars covary (high LLM judge ≠ high citation)' },
        { label: 'Mini playground', description: 'Paste a report, get back a per-pillar score breakdown (verifier runs in-browser)' },
      ]}
      related={[
        { href: '/methodology', label: 'Methodology' },
        { href: '/insights', label: 'Findings' },
      ]}
    />
  )
}
