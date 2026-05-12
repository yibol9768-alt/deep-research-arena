import { PageTitle, Subnav } from '@/components/page-title';
import { Button } from '@/components/ui/button';
import { GITHUB_URL } from '@/lib/constants';

export const metadata = { title: 'Reproduce' };

interface Recipe {
  id: string;
  num: string;
  title: string;
  intro: string;
  steps: { label: string; code?: string; note?: string }[];
}

const RECIPES: Recipe[] = [
  {
    id: 'one-pair',
    num: '1',
    title: 'Run one (agent, task) pair and submit the score',
    intro: 'Fastest way to engage. Pick an existing agent, run it on one task, score the output, open a PR with the resulting JSON. No new code required.',
    steps: [
      {
        label: 'Clone the repo and bring up the sandbox',
        code: `git clone ${GITHUB_URL}.git
cd deep-research-arena
docker compose -f sandbox/docker-compose.yml up -d`,
      },
      {
        label: 'Set up the main venv (used by the scorer + most in-process agents)',
        code: `python -m venv .venv-camel
source .venv-camel/bin/activate
pip install -r requirements.txt`,
      },
      {
        label: 'Pick an agent + task. Easiest: smolagents on task 0001.',
        code: `DS_PROXY_URL=http://localhost:8088/v1 \\
SHIM_URL=http://localhost:8081 \\
.venv-camel/bin/python scripts/run_deep_task.py \\
    --agent smolagents --task dr_cross_deep_0001 \\
    --backbone deepseek-v4-flash --out-suffix matrix`,
      },
      {
        label: 'Score the report',
        code: `JUDGE_BASE_URL=http://localhost:8088/v1 \\
JUDGE_MODEL=deepseek-v4-flash \\
.venv-camel/bin/python scripts/score_deep_answer.py \\
    --task dr_cross_deep_0001 \\
    --answer data/results/deep/smolagents__dr_cross_deep_0001_matrix.md \\
    --out   data/results/deep_v3/smolagents__dr_cross_deep_0001_matrix.score.json`,
      },
      {
        label: 'Rebuild the leaderboard locally to confirm',
        code: `.venv-camel/bin/python scripts/build_deep_leaderboard.py`,
      },
      {
        label: 'Open a PR with both files',
        note: 'CI re-scores the .md from scratch and checks the JSON matches. If the numbers reproduce, the PR merges and the agent\'s Elo updates.',
      },
    ],
  },
  {
    id: 'new-dr',
    num: '2',
    title: 'Add a new DR framework',
    intro: 'A runner is a single Python module that exposes `async def run(intent, model, shim_url, proxy_url) -> str`. The string it returns is the markdown report — that\'s all.',
    steps: [
      {
        label: 'Decide: in-process or subprocess?',
        note: 'If your framework can run in .venv-camel alongside everything else, write an in-process runner. If it needs its own venv, write a subprocess runner.',
      },
      {
        label: 'Drop the runner module at scripts/runners/<your_agent>_runner.py',
        code: `"""scripts/runners/myagent_runner.py"""
AGENT_NAME = "myagent"

async def run(intent: str, model: str, shim_url: str, proxy_url: str) -> str:
    from myagent import Researcher
    r = Researcher(llm_url=proxy_url, search_url=f"{shim_url}/search")
    return await r.research(intent)`,
        note: 'The registry auto-discovers any *_runner.py with an AGENT_NAME constant — no manual registration.',
      },
      {
        label: 'For subprocess agents, add a dedicated venv',
        code: `python -m venv .venv-myagent
.venv-myagent/bin/pip install your-framework`,
      },
      {
        label: 'Smoke-test it',
        code: `.venv-camel/bin/python scripts/run_deep_task.py \\
    --agent myagent --task dr_cross_deep_0001 \\
    --backbone deepseek-v4-flash`,
      },
      {
        label: 'Open a PR with the runner + a few sample score JSONs',
        note: 'CI verifies the runner module is importable and that scoring reproduces.',
      },
    ],
  },
  {
    id: 'reproduce',
    num: '3',
    title: 'Reproduce the whole leaderboard',
    intro: 'Six parallel workers, ~3 hours wall-clock for a fresh 397-pair run. Per-agent runner locks keep subprocess agents from racing on shared driver-script paths.',
    steps: [
      {
        label: 'Bring up the proxy + shim',
        code: `# OpenAI-compat proxy → DeepSeek
OPENAI_PROXY_UPSTREAM=https://api.deepseek.com \\
OPENAI_PROXY_KEY=$DEEPSEEK_API_KEY \\
.venv-camel/bin/uvicorn integrations.ds_proxy.app:app --host 0.0.0.0 --port 8088 &

# Tavily-compatible search shim
.venv-camel/bin/uvicorn integrations.search_shim.app:app --host 0.0.0.0 --port 8081 &`,
      },
      {
        label: 'Generate the queue',
        code: `.venv-camel/bin/python scripts/plan_full_leaderboard.py \\
    --agents deerflow flowsearcher-ds gpt-researcher ii-researcher \\
             langchain-odr ldr qx-agents smolagents storm \\
    --task-range 1-57 \\
    --out data/results/deep_v3/run_queue.tsv`,
      },
      {
        label: 'Launch six parallel workers',
        code: `bash scripts/parallel_bulk_launch.sh 6`,
        note: 'Resumable: pairs whose score JSON already exists are skipped.',
      },
      {
        label: 'Rebuild leaderboard after the run finishes',
        code: `.venv-camel/bin/python scripts/build_deep_leaderboard.py`,
      },
    ],
  },
];

export default function ContributePage() {
  return (
    <>
      <PageTitle subtitle="Three things you can do. Each is a separate, self-contained recipe.">Contribute or reproduce</PageTitle>
      <Subnav
        items={[
          { href: '/', label: 'Leaderboard' },
          { href: '/how-it-works/', label: 'Methodology' },
          { href: '/contribute/', label: 'Reproduce', current: true },
          { href: '/about/', label: 'About' },
        ]}
      />

      <div className="mb-8 flex flex-wrap gap-2">
        {RECIPES.map((r) => (
          <Button key={r.id} asChild variant="outline" size="sm">
            <a href={`#${r.id}`}>
              {r.num}. {r.title.split(' ').slice(0, 4).join(' ')}…
            </a>
          </Button>
        ))}
      </div>

      {RECIPES.map((recipe) => (
        <section key={recipe.id} id={recipe.id} className="mb-8 rounded-lg border bg-card p-6 scroll-mt-20">
          <div className="mb-2 inline-flex items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Recipe {recipe.num}</span>
          </div>
          <h2 className="text-[19px] font-semibold tracking-tight">{recipe.title}</h2>
          <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-foreground/80">{recipe.intro}</p>
          <div className="mt-5 space-y-5">
            {recipe.steps.map((step, i) => (
              <div key={i} className="flex gap-3.5">
                <span className="mt-0.5 inline-flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-accent/15 text-[11px] font-semibold text-accent">{i + 1}</span>
                <div className="flex-1">
                  <div className="text-[13.5px] font-semibold text-foreground">{step.label}</div>
                  {step.code && (
                    <pre className="mt-2 overflow-x-auto rounded bg-primary p-3 text-[12px] text-primary-foreground">{step.code}</pre>
                  )}
                  {step.note && <p className="mt-2 text-[12.5px] text-muted-foreground leading-relaxed">{step.note}</p>}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}

      <p className="mb-10 text-[13px] text-muted-foreground">
        Stuck? Open an issue on{' '}
        <a className="text-accent hover:underline" href={`${GITHUB_URL}/issues`} target="_blank" rel="noopener">GitHub</a>.
      </p>
    </>
  );
}
