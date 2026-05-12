import { PageTitle, Subnav } from '@/components/page-title';
import { Button } from '@/components/ui/button';
import { ArrowRight } from 'lucide-react';
import Link from 'next/link';

export const metadata = { title: 'Methodology' };

const PILLARS = [
  ['URL coverage', 'Did the agent cite the URLs that should be cited? Compares the agent\'s URLs against a hidden golden pool of must-cite + expected-pool URLs per task.'],
  ['URL reachability', 'Do the cited URLs actually resolve in the sandbox? Each URL is HTTP-probed. Hallucinated or fabricated URLs return 4xx/5xx.'],
  ['Quote match', 'When the agent quotes a page, does the page actually contain that text? Fuzzy match against the fetched content.'],
  ['Claim NLI', 'Are the agent\'s factual claims entailed by the cited page rather than contradicted or unrelated? NLI per claim.'],
  ['Checklist (LLM judge)', 'A 21-item task-specific checklist evaluated by an LLM judge. Each item is a yes/no fact the report must contain.'],
  ['Citation alignment', 'For each cited URL, does the linked page actually support the surrounding claim? Per-citation precision/recall.'],
  ['Analysis + presentation', 'Two LLM-judge rubrics: whether the report goes beyond restating sources, and whether it is structured and readable.'],
  ['Spec compliance', 'Hard-rule checks on word count, citation count, and paragraph count. Pass/fail per dimension; final spec score is the pass fraction.'],
];

export default function HowItWorksPage() {
  return (
    <>
      <PageTitle
        subtitle="A short walkthrough — from raw task to final Elo. Every agent answers the same questions on the same sealed data; a deterministic scorer compares answers to a hidden URL/quote pool; pairwise battles become Bradley-Terry Elo."
      >
        How the leaderboard is produced
      </PageTitle>
      <Subnav
        items={[
          { href: '/', label: 'Leaderboard' },
          { href: '/how-it-works/', label: 'Methodology', current: true },
          { href: '/contribute/', label: 'Reproduce' },
          { href: '/about/', label: 'About' },
        ]}
      />

      <section className="mb-10 rounded-lg border bg-card p-6">
        <div className="mb-3 inline-flex h-6 w-6 items-center justify-center rounded-full bg-accent/15 text-[11px] font-semibold text-accent">1</div>
        <h2 className="text-[18px] font-semibold tracking-tight">The agents run on a sealed sandbox</h2>
        <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-foreground/80">
          No agent ever touches the real internet. The sandbox is three local services that look like Amazon, Reddit, and Wikipedia:
        </p>
        <ul className="mt-3 max-w-3xl text-[13.5px] text-foreground/80 space-y-1.5">
          <li>· <strong>Magento</strong> at <code className="num-mono">localhost:7770</code> — ~2,000 product pages.</li>
          <li>· <strong>Postmill</strong> at <code className="num-mono">localhost:9999</code> — Reddit-style forum threads.</li>
          <li>· <strong>Kiwix</strong> at <code className="num-mono">localhost:8090</code> — offline Wikipedia.</li>
        </ul>
        <p className="mt-3 max-w-3xl text-[14px] leading-relaxed text-foreground/80">
          Each task is a one-paragraph research prompt that requires citing ≥120 URLs across all three sources. The agent gets the prompt, nothing else, and writes a markdown report.
        </p>
      </section>

      <section className="mb-10 rounded-lg border bg-card p-6">
        <div className="mb-3 inline-flex h-6 w-6 items-center justify-center rounded-full bg-accent/15 text-[11px] font-semibold text-accent">2</div>
        <h2 className="text-[18px] font-semibold tracking-tight">Every report is scored on 7 pillars</h2>
        <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-foreground/80">
          The scorer reads the markdown report and produces seven sub-scores. Five are deterministic; two are LLM-judged with strict rubrics.
        </p>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          {PILLARS.map(([title, body]) => (
            <div key={title} className="rounded-md bg-secondary p-3.5">
              <div className="font-semibold text-[13.5px] text-foreground">{title}</div>
              <div className="mt-1 text-[12.5px] leading-relaxed text-foreground/75">{body}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-10 rounded-lg border bg-card p-6">
        <div className="mb-3 inline-flex h-6 w-6 items-center justify-center rounded-full bg-accent/15 text-[11px] font-semibold text-accent">3</div>
        <h2 className="text-[18px] font-semibold tracking-tight">The pillars combine into composite_v2</h2>
        <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-foreground/80">The headline number on the leaderboard:</p>
        <pre className="mt-3 max-w-3xl overflow-x-auto rounded bg-primary p-3 text-[12px] text-primary-foreground">
{`composite_v2 = reachability · qm_factor · nli_factor
                 · (0.40·url_coverage + 0.40·checklist + 0.20·spec)`}
        </pre>
        <p className="mt-3 max-w-3xl text-[14px] leading-relaxed text-foreground/80">
          The key idea is the <strong>multiplicative gate</strong>. URL reachability, quote match, and claim NLI all multiply the quality score. If the agent fabricates URLs (reachability=0), the whole score is zero — no matter how fluent the prose. <em>Truthfulness is non-negotiable.</em>
        </p>
      </section>

      <section className="mb-10 rounded-lg border bg-card p-6">
        <div className="mb-3 inline-flex h-6 w-6 items-center justify-center rounded-full bg-accent/15 text-[11px] font-semibold text-accent">4</div>
        <h2 className="text-[18px] font-semibold tracking-tight">Pairwise battles → Bradley-Terry Elo</h2>
        <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-foreground/80">
          For every task where two agents both have a valid score, we record a "battle" — whichever has the higher <code className="num-mono">composite_v2</code> wins. We fit a Bradley-Terry model (same as chess Elo) to the matrix of outcomes. Each agent gets a single Elo plus a 95% bootstrap CI.
        </p>
        <p className="mt-3 max-w-3xl text-[14px] leading-relaxed text-foreground/80">
          Why pairwise instead of averaging the composite? Because composite scores are noisy and task-difficulty-correlated. Pairwise comparisons cancel out the per-task baseline.
        </p>
      </section>

      <div className="flex flex-wrap gap-3">
        <Button asChild variant="accent">
          <Link href="/contribute/">
            Reproduce on your machine
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/">View the leaderboard</Link>
        </Button>
      </div>
    </>
  );
}
