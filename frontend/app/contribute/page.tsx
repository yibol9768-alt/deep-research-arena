import { PageStub } from '@/components/layout/page-stub'

export default function ContributePage() {
  return (
    <PageStub
      eyebrow="Contribute"
      title="Add a framework. Add a task. Improve a verifier."
      intro="If you've built a Deep Research framework — or designed a task you think will trip these eight up — we want to integrate it. Most frameworks need <50 lines of glue thanks to the Tavily shim."
      upcoming={[
        { label: 'Add a framework', description: 'Implement runner → register in RUNNERS → run smoke test → submit PR. Code template included.' },
        { label: 'Add a task', description: 'Schema spec for sandbox-grounded tasks · golden URL scraper guide · author_notes convention' },
        { label: 'Reproduce in 5 minutes', description: 'Single docker compose command brings up the entire sandbox + shim + ds-proxy stack' },
        { label: 'Code of conduct', description: 'Standard contributor covenant · maintainers · governance' },
      ]}
      related={[
        { href: '/sandbox', label: 'Sandbox' },
        { href: '/methodology', label: 'Methodology' },
      ]}
    />
  )
}
