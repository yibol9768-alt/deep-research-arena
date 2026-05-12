import { PageTitle, Subnav } from '@/components/page-title';
import { loadLatestAudit } from '@/lib/data';

export const metadata = { title: 'Audit log' };

export default function AuditPage() {
  const doc = loadLatestAudit();
  return (
    <>
      <PageTitle
        subtitle={
          <>
            Read-only render of the latest <code className="num-mono">DR_SCORE_AUDIT_*.md</code> in{' '}
            <code className="num-mono">data/results/audit/</code>. Lists which agents were excluded from Elo and why — runner placeholders, infra failures, judge-error storms.
          </>
        }
      >
        Score-file audit
      </PageTitle>
      <Subnav
        items={[
          { href: '/', label: 'Leaderboard' },
          { href: '/how-it-works/', label: 'Methodology' },
          { href: '/audit/', label: 'Audit', current: true },
          { href: '/v4/', label: 'v4' },
        ]}
      />

      {doc ? (
        <section className="rounded-lg border bg-card p-6">
          <div className="mb-3 flex items-baseline justify-between">
            <div className="text-[12.5px] text-muted-foreground num-mono">{doc.filename}</div>
            <div className="text-[12px] text-muted-foreground">Updated {doc.mtime}</div>
          </div>
          <pre className="whitespace-pre-wrap text-[12.5px] leading-[1.55] text-foreground/85 num-mono" style={{ fontFamily: 'inherit' }}>{doc.text}</pre>
        </section>
      ) : (
        <section className="rounded-lg border bg-card p-6 text-[14px] text-foreground/75">
          No audit reports yet. Run <code className="num-mono">python scripts/audit_dr_scores.py</code> to generate one.
        </section>
      )}
    </>
  );
}
