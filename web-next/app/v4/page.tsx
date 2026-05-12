import { PageTitle, Subnav } from '@/components/page-title';
import { Badge } from '@/components/ui/badge';

export const metadata = { title: 'v4 Multi-pillar' };

export default function V4Page() {
  return (
    <>
      <PageTitle
        subtitle={
          <>
            Adds <strong>four new pillars</strong> on top of the v2 verifiers — atomic factuality, intra-document consistency, perspective balance, and source diversity — and replaces the v2 quality term with an 11-way weighted mix. The reachability gate is preserved, so URL fabrication still zeroes the score.
          </>
        }
      >
        v4 Multi-pillar Leaderboard
      </PageTitle>
      <Subnav
        items={[
          { href: '/', label: 'Intelligence Index' },
          { href: '/v4/', label: 'v4 Multi-pillar', current: true, badge: 'NEW' },
          { href: '/compare/', label: 'Backbones' },
          { href: '/audit/', label: 'Audit' },
          { href: '/how-it-works/', label: 'Methodology' },
        ]}
      />

      <div className="mb-6 flex flex-wrap gap-2">
        <Badge variant="accent">composite_v4 · 11 dimensions</Badge>
        <Badge variant="warn">experimental</Badge>
      </div>

      <section className="mb-8 rounded-lg border bg-card p-6">
        <h2 className="text-[18px] font-semibold tracking-tight">Why v4?</h2>
        <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-foreground/80">
          v2 was overweighted on URL grounding (60% of quality). v4 answers the critique by adding four independent signals:
        </p>
        <ul className="mt-3 max-w-3xl list-disc pl-5 text-[13.5px] text-foreground/80 space-y-1.5">
          <li><strong>Factual exactness</strong> — atomic-fact extraction + NLI against the cited page.</li>
          <li><strong>Internal consistency</strong> — entity clustering + pairwise NLI on the report itself.</li>
          <li><strong>Perspective balance</strong> — sentiment lexicon + LLM judge on viewpoint coverage.</li>
          <li><strong>Source diversity</strong> — deterministic (no LLM) measure of how spread across the three sources.</li>
        </ul>
      </section>

      <section className="mb-8 rounded-lg border bg-card p-6">
        <h2 className="text-[18px] font-semibold tracking-tight">Formula</h2>
        <pre className="mt-3 overflow-x-auto rounded bg-primary p-3 text-[12px] text-primary-foreground">
{`composite_v4 = reach · (
    0.10·url_cov + 0.05·spec + 0.10·checklist
  + 0.10·cit_align + 0.05·qm
  + 0.13·factual_exactness + 0.13·internal_consistency
  + 0.08·perspective_balance + 0.06·source_diversity
  + 0.10·analysis_depth + 0.10·presentation
)`}
        </pre>
      </section>

      <section className="mb-12 rounded-lg border bg-card p-6">
        <h2 className="text-[18px] font-semibold tracking-tight">Status</h2>
        <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-foreground/80">
          v4 runs on a small sample (25 runs / 46 battles) and is in pilot mode. The leaderboard JSON is published at{' '}
          <code className="num-mono">/api/v4.json</code> once the build completes. The headline ranking still uses v2 in
          production because the truth-gate inversion finding is the primary methodological contribution and is cleanest at the v2 scale.
        </p>
        <p className="mt-3 max-w-3xl text-[14px] leading-relaxed text-foreground/80">
          Until the v4 bulk run finishes, the interactive v4 leaderboard view is offline. Check{' '}
          <a className="text-accent hover:underline" href="/audit/">Audit</a> for the latest run status.
        </p>
      </section>
    </>
  );
}
