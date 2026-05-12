import { PageTitle, Subnav } from '@/components/page-title';
import { Badge } from '@/components/ui/badge';
import { GITHUB_URL } from '@/lib/constants';
import { loadLeaderboard } from '@/lib/data';

export const metadata = { title: 'Compare backbones' };

const ROWS = [
  { llm: 'DeepSeek V4-flash', provider: 'DeepSeek (api.deepseek.com)', status: 'live', note: 'Thinking off. Routed via ds_proxy:8088.', live: true },
  { llm: 'DeepSeek V4-pro', provider: 'DeepSeek (api.deepseek.com)', status: 'queued', note: 'Same proxy, just BACKBONE=deepseek-v4-pro. ~10× more expensive than flash.', live: false },
  { llm: 'GPT-4o-mini', provider: 'OpenAI', status: 'queued', note: 'Needs OpenAI API key + a second ds_proxy on port 8090. Commercial baseline.', live: false },
  { llm: 'Claude Sonnet 4.6', provider: 'Anthropic', status: 'queued', note: 'Needs Anthropic API key + an OpenAI-compat shim. Best on agentic tool-use.', live: false },
  { llm: 'Gemini 2.5 Pro', provider: 'Google', status: 'queued', note: 'Needs Google AI key. Vertex\'s OpenAI-compat endpoint avoids needing a custom shim.', live: false },
  { llm: 'Local Qwen3.5-27b', provider: 'LM Studio (5090)', status: 'queued', note: 'Free local inference once the host GPU is online.', live: false },
];

export default function ComparePage() {
  const lb = loadLeaderboard();
  return (
    <>
      <PageTitle
        subtitle="The Elo on the home page is for one backbone (DeepSeek V4-flash). This page surfaces the agent × LLM matrix once the other backbones are benchmarked. Same tasks, same scoring, just swap the backbone — and see whether your favourite DR framework still wins."
      >
        Compare DR frameworks across LLMs
      </PageTitle>
      <Subnav
        items={[
          { href: '/', label: 'Leaderboard' },
          { href: '/compare/', label: 'Compare backbones', current: true },
          { href: '/v4/', label: 'v4' },
          { href: '/audit/', label: 'Audit' },
        ]}
      />

      <section className="mb-8 overflow-hidden rounded-lg border bg-card">
        <div className="border-b bg-secondary/60 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Backbones tracked
        </div>
        <table className="w-full text-[13.5px]">
          <thead>
            <tr className="border-b text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-2.5">LLM</th>
              <th className="px-3 py-2.5">Provider</th>
              <th className="px-3 py-2.5">Status</th>
              <th className="px-4 py-2.5">Notes</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => (
              <tr key={r.llm} className="border-b border-border/40 last:border-0">
                <td className="px-4 py-2.5 font-medium whitespace-nowrap">{r.llm}</td>
                <td className="px-3 py-2.5 text-foreground/75">{r.provider}</td>
                <td className="px-3 py-2.5">
                  {r.live ? <Badge variant="ok">live</Badge> : <Badge>queued</Badge>}
                </td>
                <td className="px-4 py-2.5 text-foreground/75 text-[13px]">
                  {r.live ? `${lb.n_runs} run-score files. ` : ''}
                  {r.note}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="mb-6 rounded-lg border bg-card p-6">
        <h2 className="text-[18px] font-semibold tracking-tight">How the comparison works</h2>
        <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-foreground/80">
          Same 57 cross-site research tasks, same deterministic scorer, same Bradley-Terry Elo. The only thing that varies is the
          LLM backbone the agent uses internally. We expect to see two effects:
        </p>
        <ul className="mt-3 max-w-3xl list-disc pl-5 text-[13.5px] text-foreground/80 space-y-1.5">
          <li>
            <strong>Universal rank stability</strong> — agents that fabricate URLs under one LLM tend to fabricate under all LLMs.
            The reach gate kills them either way.
          </li>
          <li>
            <strong>Local rank flips</strong> — an agent whose runner uses tool-calling heavily does much better on tool-strong
            models (Claude / GPT-4o) than on weaker ones.
          </li>
        </ul>
        <p className="mt-3 max-w-3xl text-[14px] leading-relaxed text-foreground/80">
          Once two or more backbones land, this page renders an interactive agent × LLM heatmap of <code className="num-mono">composite_v2</code> means plus per-agent "best LLM" annotation.
        </p>
      </section>

      <p className="text-[13px] text-muted-foreground">
        Want a specific LLM added? Open an issue on{' '}
        <a className="text-accent hover:underline" href={`${GITHUB_URL}/issues`} target="_blank" rel="noopener">
          GitHub
        </a>
        .
      </p>
    </>
  );
}
