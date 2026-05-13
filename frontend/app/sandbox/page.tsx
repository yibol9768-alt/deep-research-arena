import { PageStub } from '@/components/layout/page-stub'

export default function SandboxPage() {
  return (
    <PageStub
      eyebrow="Sandbox"
      title="A reproducible mini-internet — in 3 Docker containers."
      intro="Every benchmark task is solved against a frozen sandbox: Magento (shopping), Postmill (Reddit), and Kiwix (Wikipedia), fronted by a Tavily/Firecrawl-compatible search shim. This page will be an interactive architecture tour."
      upcoming={[
        { label: 'Architecture diagram', description: 'Click each component (sandbox / shim / verifier / arena) to drill into details' },
        { label: 'Magento :7770', description: '2,000+ static product pages with reviews, search, and filters' },
        { label: 'Postmill :9999', description: 'Threaded forum with votes, user histories, and subreddit-style topic feeds' },
        { label: 'Kiwix :8090', description: '49 GB Simple English Wikipedia, served offline' },
        { label: 'Search Shim :8081', description: 'Tavily + Firecrawl + extract endpoints. Zero-code framework integration.' },
        { label: 'DS Proxy :8088', description: 'OpenAI-compat proxy auto-injecting `thinking:disabled` for DeepSeek V4' },
      ]}
      related={[
        { href: '/methodology', label: 'Methodology' },
        { href: '/contribute', label: 'Contribute' },
      ]}
    />
  )
}
