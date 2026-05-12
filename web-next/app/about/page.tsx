import { PageTitle, Subnav } from '@/components/page-title';
import { loadProjectWriteup } from '@/lib/data';

export const metadata = { title: 'About' };

export default function AboutPage() {
  const doc = loadProjectWriteup();
  return (
    <>
      <PageTitle
        subtitle={
          <>
            What we built, why the sandbox matters, how the seven scoring pillars roll up into <code className="num-mono">composite_v2</code>, and what the Elo ranking actually says about each framework. Source: <code className="num-mono">docs/PROJECT_WRITEUP.md</code>.
          </>
        }
      >
        About this project
      </PageTitle>
      <Subnav
        items={[
          { href: '/', label: 'Leaderboard' },
          { href: '/how-it-works/', label: 'Methodology' },
          { href: '/contribute/', label: 'Reproduce' },
          { href: '/about/', label: 'About', current: true },
        ]}
      />

      {doc ? (
        <section className="rounded-lg border bg-card p-7">
          <div className="mb-3 flex items-baseline justify-end">
            <div className="text-[12px] text-muted-foreground">Updated {doc.mtime}</div>
          </div>
          <pre className="whitespace-pre-wrap text-[13px] leading-[1.65] text-foreground/85" style={{ fontFamily: 'inherit' }}>{doc.text}</pre>
        </section>
      ) : (
        <section className="rounded-lg border bg-card p-6 text-[14px] text-foreground/75">
          <code className="num-mono">docs/PROJECT_WRITEUP.md</code> is missing.
        </section>
      )}
    </>
  );
}
