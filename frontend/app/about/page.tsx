import { PageStub } from '@/components/layout/page-stub'

export default function AboutPage() {
  return (
    <PageStub
      eyebrow="About"
      title="A lab notebook turned into a benchmark."
      intro="Deep Research Arena started as a single-week sprint in April 2026 to figure out which open-source DR framework was worth picking up. Twenty-two days later it was a NeurIPS draft."
      upcoming={[
        { label: 'Project history', description: 'A timeline from sandbox up (2026-04-15) to leaderboard frozen (2026-05-06)' },
        { label: 'Team', description: 'Who built what · how to reach us · acknowledgements' },
        { label: 'Citation', description: 'BibTeX block · arXiv link (when published)' },
        { label: 'License', description: 'Apache-2.0 for code · CC-BY-4.0 for data · MIT for the frontend' },
      ]}
      related={[
        { href: '/methodology', label: 'Methodology' },
        { href: '/contribute', label: 'Contribute' },
      ]}
    />
  )
}
