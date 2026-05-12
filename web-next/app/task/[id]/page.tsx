import { notFound } from 'next/navigation';
import { listTaskIds, loadTask } from '@/lib/data';
import { PageTitle } from '@/components/page-title';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';

function stringify(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v);
  try { return JSON.stringify(v); } catch { return String(v); }
}

export function generateStaticParams() {
  return listTaskIds().map((id) => ({ id }));
}

export const dynamicParams = false;

export default function TaskPage({ params }: { params: { id: string } }) {
  const { cfg } = loadTask(params.id);
  if (!cfg) notFound();

  const c = cfg as Record<string, any>;

  return (
    <>
      <div className="mb-4 flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
        <Link href="/" className="hover:text-accent">Leaderboard</Link>
        <span className="opacity-50">›</span>
        <span className="num-mono text-foreground">{params.id}</span>
      </div>
      <h1 className="mb-3 text-[28px] font-bold leading-tight tracking-tight">
        Task{' '}
        <span className="rounded-md border bg-secondary px-2.5 py-0.5 text-[18px] font-medium num-mono align-middle">
          {params.id}
        </span>
      </h1>
      <div className="mb-7 flex flex-wrap items-center gap-2 text-[12.5px]">
        {c.intent_type && <Badge variant="accent">{c.intent_type}</Badge>}
        {c.domain && <Badge>{c.domain}</Badge>}
        {c.tier && <Badge>tier: {c.tier}</Badge>}
        {typeof c.difficulty === 'number' && <Badge>difficulty: {c.difficulty}/5</Badge>}
        {Array.isArray(c.sites) && <Badge>{c.sites.join(' + ')}</Badge>}
      </div>

      <section className="mb-6 rounded-lg border bg-card p-5">
        <div className="mb-3 flex items-baseline justify-between">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Task prompt</div>
          <div className="text-[11px] text-muted-foreground">The exact text the agent receives.</div>
        </div>
        {c.intent ? (
          <pre className="whitespace-pre-wrap text-[13px] leading-[1.65] text-foreground num-mono rounded bg-secondary p-4 max-h-[560px] overflow-y-auto">{typeof c.intent === 'string' ? c.intent : stringify(c.intent)}</pre>
        ) : (
          <div className="text-[13px] text-muted-foreground">No intent text in the task config.</div>
        )}
      </section>

      {(c.markdown_spec || c.synthesis_requirements || c.citation_policy) && (
        <section className="mb-6 rounded-lg border bg-card p-5">
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Hard constraints</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 text-[12.5px]">
            {c.markdown_spec && (
              <div>
                <div className="mb-1.5 text-[13px] font-semibold">Markdown spec</div>
                <ul className="space-y-1 text-foreground/80">
                  {typeof c.markdown_spec.min_words === 'number' && <li>≥ <span className="num-mono">{c.markdown_spec.min_words}</span> words</li>}
                  {typeof c.markdown_spec.max_words === 'number' && <li>≤ <span className="num-mono">{c.markdown_spec.max_words}</span> words</li>}
                  {typeof c.markdown_spec.min_paragraphs === 'number' && <li>≥ <span className="num-mono">{c.markdown_spec.min_paragraphs}</span> paragraphs</li>}
                  {typeof c.markdown_spec.min_citations === 'number' && <li>≥ <span className="num-mono">{c.markdown_spec.min_citations}</span> citations</li>}
                  {typeof c.markdown_spec.min_pages_browsed === 'number' && <li>≥ <span className="num-mono">{c.markdown_spec.min_pages_browsed}</span> distinct URLs cited</li>}
                </ul>
              </div>
            )}
            {c.citation_policy && (
              <div>
                <div className="mb-1.5 text-[13px] font-semibold">Citation policy</div>
                <ul className="space-y-1 text-foreground/80">
                  {typeof c.citation_policy.min_distinct_sources === 'number' && <li>≥ <span className="num-mono">{c.citation_policy.min_distinct_sources}</span> distinct sources</li>}
                  {typeof c.citation_policy.min_distinct_domains === 'number' && <li>≥ <span className="num-mono">{c.citation_policy.min_distinct_domains}</span> distinct domains</li>}
                  {c.citation_policy.per_domain_minimum && Object.entries(c.citation_policy.per_domain_minimum).map(([k, v]) => (
                    <li key={k}><span className="num-mono">{k}</span>: ≥ {stringify(v)}</li>
                  ))}
                </ul>
              </div>
            )}
            {c.synthesis_requirements && (
              <div>
                <div className="mb-1.5 text-[13px] font-semibold">Synthesis requirements</div>
                <ul className="space-y-1 text-foreground/80">
                  {Object.entries(c.synthesis_requirements as Record<string, unknown>).map(([k, v]) => (
                    <li key={k}><span className="num-mono">{k}</span>: {stringify(v)}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}

      <section className="text-[12.5px] text-muted-foreground">
        Raw config: <code className="num-mono">data/tasks/deep_research/cross_site_deep/{params.id}.json</code>
      </section>
    </>
  );
}
