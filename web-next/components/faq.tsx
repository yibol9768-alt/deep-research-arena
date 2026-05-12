'use client';

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';

interface FAQItem {
  q: string;
  a: React.ReactNode;
}

const ITEMS: FAQItem[] = [
  {
    q: 'What does composite_v2 measure exactly?',
    a: (
      <>
        <code className="rounded bg-secondary px-1.5 py-0.5 text-[12px] num-mono">
          composite_v2 = reachability · qm_factor · nli_factor · (0.40·url_coverage + 0.40·checklist + 0.20·spec)
        </code>
        <p className="mt-2">
          The first three are multiplicative gates — if reachability is zero (fabricated URLs), the whole score is zero, no matter how
          fluent the prose. The quality part inside parens is a weighted mix of three deterministic signals.
        </p>
      </>
    ),
  },
  {
    q: 'Why pairwise Elo instead of averaging the composite?',
    a: (
      <p>
        Composite scores are noisy and task-difficulty-correlated. If task #5 is hard, every agent scores low on it — averaging is
        misleading. Pairwise cancels out the per-task baseline (the same trick that makes chess Elo work).
      </p>
    ),
  },
  {
    q: 'How is the golden URL pool generated?',
    a: (
      <p>
        For each task, a scraper walks the three sandbox sites and collects 120–130 must-cite URLs. The pool is frozen — committed to{' '}
        <code className="rounded bg-secondary px-1.5 py-0.5 text-[12px] num-mono">data/golden/deep/</code>. URL coverage is the agent's
        recall against this set.
      </p>
    ),
  },
  {
    q: 'What LLM judges the reports?',
    a: (
      <p>
        DeepSeek V4-flash with thinking disabled, served through a local proxy on{' '}
        <code className="rounded bg-secondary px-1.5 py-0.5 text-[12px] num-mono">localhost:8088</code>. Same model, same temperature (0)
        for every report — judging is deterministic.
      </p>
    ),
  },
  {
    q: 'Can I reproduce this on my own machine?',
    a: (
      <p>
        Yes. <code className="rounded bg-secondary px-1.5 py-0.5 text-[12px] num-mono">docker compose up</code> brings up the sandbox; six
        parallel workers complete a fresh 397-pair run in ~3 hours. See <a className="text-accent hover:underline" href="/contribute/">Reproduce</a> for the full recipe.
      </p>
    ),
  },
  {
    q: 'How do I add a new DR framework?',
    a: (
      <p>
        Drop a runner at{' '}
        <code className="rounded bg-secondary px-1.5 py-0.5 text-[12px] num-mono">scripts/runners/&lt;your_agent&gt;_runner.py</code>{' '}
        exposing <code className="rounded bg-secondary px-1.5 py-0.5 text-[12px] num-mono">async def run(intent, model, shim_url, proxy_url) → str</code>.
        The registry auto-discovers it. Full walkthrough on{' '}
        <a className="text-accent hover:underline" href="/contribute/">Reproduce</a>.
      </p>
    ),
  },
];

export function FAQ() {
  return (
    <section className="mb-12">
      <h2 className="mb-1 text-[20px] font-semibold tracking-tight">Frequently asked questions</h2>
      <p className="mb-5 text-[13px] text-muted-foreground">Common questions about the leaderboard, the sandbox, and how scoring works.</p>
      <div className="rounded-lg border bg-card overflow-hidden">
        <Accordion type="multiple" className="w-full">
          {ITEMS.map((it, i) => (
            <AccordionItem key={i} value={`item-${i}`}>
              <AccordionTrigger>{it.q}</AccordionTrigger>
              <AccordionContent>{it.a}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </section>
  );
}
