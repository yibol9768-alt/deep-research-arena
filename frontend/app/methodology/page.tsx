import { PageStub } from '@/components/layout/page-stub'

export default function MethodologyPage() {
  return (
    <PageStub
      eyebrow="Methodology"
      title="Composite v3.1 · Bradley-Terry · Dual-Judge."
      intro="A long-form, anchor-navigated explanation of every algorithm in the benchmark. KaTeX-rendered formulas, pseudocode, decision rationale, and ablation results."
      upcoming={[
        { label: '#composite', description: 'The 7-pillar weighted-sum, each weight justified against ablation data' },
        { label: '#grounding-gate', description: 'Why we softened the multiplicative truth gate from v2 to max(0.1, reachability)' },
        { label: '#bradley-terry', description: 'MLE derivation · 1000-sample bootstrap · 1000-sample permutation rank test' },
        { label: '#dual-judge', description: 'Why agent and judge come from different model families (Wataoka 2024)' },
        { label: '#intent-typology', description: '6 intent classes (Recommendation / Comparison / Debunking / Causal / Timeline / Enumeration)' },
        { label: '#verifier-inventory', description: 'All 29 verifier files, their pillar assignment, and a code excerpt' },
        { label: '#ablation', description: 'Drop each pillar and watch Kendall τ degrade. Truth gate is decisive (τ 0.92 → 0.40).' },
        { label: '#limitations', description: 'Known issues with each link to the GitHub issue tracking the fix' },
      ]}
      related={[
        { href: '/pillars', label: 'Pillars' },
        { href: '/insights', label: 'Findings' },
      ]}
    />
  )
}
