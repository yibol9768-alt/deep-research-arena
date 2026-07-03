import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

const STEPS = [
  {
    n: '1',
    title: 'Implement a runner',
    titleZh: '实现一个 runner',
    body: 'Wrap your framework behind the local runner contract and point it at the search shim.',
    bodyZh: '将你的框架封装在本地 runner 契约之后，并将其指向搜索 shim。',
  },
  {
    n: '2',
    title: 'Run a smoke task',
    titleZh: '运行一个冒烟任务',
    body: 'Use one deep task to verify model calls, search calls, citations, and markdown output.',
    bodyZh: '用一个深度任务来验证模型调用、搜索调用、引用以及 markdown 输出。',
  },
  {
    n: '3',
    title: 'Score locally',
    titleZh: '在本地评分',
    body: 'Run the verifier stack and inspect dropped-run reasons before submitting results.',
    bodyZh: '在提交结果之前，运行校验器栈并检查被丢弃运行的原因。',
  },
  {
    n: '4',
    title: 'Open a PR',
    titleZh: '提交一个 PR',
    body: 'Include runner code, environment notes, score JSON, and a short reproducibility note.',
    bodyZh: '附上 runner 代码、环境说明、评分 JSON，以及一份简短的可复现说明。',
  },
] as const

export default function ContributePage() {
  return (
    <>
      <PageHero
        eyebrow={<T en="Contribute" zh="参与贡献" />}
        title={<T en="Add your agent to the benchmark." zh="把你的智能体接入基准。" />}
        intro={<T en="The benchmark is designed for external agents. Most integrations only need a runner, a model endpoint, and the existing Tavily/Firecrawl-compatible search shim." zh="该基准面向外部智能体设计。多数集成只需要一个 runner、一个模型端点，以及现有的 Tavily/Firecrawl 兼容搜索 shim。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Runner glue" zh="Runner 胶水代码" />} value="<50" detail={<T en="typical lines for simple adapters" zh="简单适配器的典型行数" />} />
          <MetricCard label={<T en="Task schema" zh="任务 schema" />} value="JSON" detail={<T en="frozen prompt and source contract" zh="冻结的提示词与来源契约" />} />
          <MetricCard label={<T en="Smoke" zh="冒烟测试" />} value="1" detail={<T en="minimum task before matrix runs" zh="矩阵运行前的最小任务数" />} />
          <MetricCard label={<T en="PR data" zh="PR 数据" />} value="Score" detail={<T en="reports and verifier JSON" zh="报告与校验器 JSON" />} />
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {STEPS.map((step) => (
          <article key={step.n} className="card card-lift p-6">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-ink font-mono text-sm text-white">{step.n}</span>
            <h2 className="mt-5 font-serif text-h-sm text-ink"><T en={step.title} zh={step.titleZh} /></h2>
            <p className="mt-2 text-sm leading-relaxed text-muted"><T en={step.body} zh={step.bodyZh} /></p>
          </article>
        ))}
      </section>

      <section className="container mt-10 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink"><T en="Runner contract" zh="Runner 契约" /></h2>
          <pre className="mt-4 overflow-auto rounded-tab bg-surface-low p-4 text-xs leading-relaxed text-muted">
{`python scripts/run_deep_task.py \\
  --runner your_agent \\
  --task data/tasks/deep_research/cross_site_deep/dr_cross_deep_0001.json \\
  --out data/results/deep_v3`}
          </pre>
        </div>
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink"><T en="What reviewers need" zh="评审者需要什么" /></h2>
          <ul className="mt-4 space-y-3 text-sm text-muted">
            <li><T en="Exact model and provider configuration." zh="确切的模型与提供方配置。" /></li>
            <li><T en="Runner code with no hidden network dependencies beyond the shim." zh="不含 shim 之外任何隐藏网络依赖的 runner 代码。" /></li>
            <li><T en="Raw reports, matrix score JSON, and dropped-run explanations." zh="原始报告、矩阵评分 JSON，以及被丢弃运行的说明。" /></li>
            <li><T en="A note describing any framework-specific patches." zh="一份描述任何框架专属补丁的说明。" /></li>
          </ul>
        </div>
      </section>
    </>
  )
}
