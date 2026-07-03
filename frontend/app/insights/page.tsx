import Link from 'next/link'
import { ArrowUpRight } from 'lucide-react'
import { PageHero } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

const STORIES = [
  {
    slug: 'judge-vs-grounding',
    title: 'Raw judge Elo and grounded evidence disagree sharply',
    titleZh: '裸判官 Elo 与真实证据出现明显分歧',
    kicker: 'Agent board',
    kickerZh: '智能体榜',
    body: 'GPT-Researcher sits near the top by raw judge Elo (1147), but only 4.3% of its cited URLs resolve and 2.2% of quoted evidence is verified. The truth-gated board drops it to #11, while Claude Code and OpenCode lead because quality and evidence both hold up.',
    bodyZh: 'GPT-Researcher 的裸判官 Elo 很高（1147），但引用可达率只有 4.3%，引文核实率只有 2.2%。真值门控榜将其降到第 11；Claude Code 与 OpenCode 领先，是因为报告质量与证据质量同时成立。',
    href: '/methodology#grounding-gate',
  },
  {
    slug: 'qwen3-cheap-baseline',
    title: 'The minimal qwen3 baseline exposes the cost of citation pressure',
    titleZh: '极简 qwen3 基线暴露了引用压力的代价',
    kicker: 'Model board',
    kickerZh: '模型榜',
    body: 'In the current model board, qwen3-30b-a3b-instruct-2507 runs under the fixed minimal protocol across 24 tasks and 643 clean judge battles. Its grounding gate is about 24%: many answers read coherently, but weak source budgets still push the model toward unreachable or unverifiable citations.',
    bodyZh: '在当前模型榜中，qwen3-30b-a3b-instruct-2507 使用固定极简协议，覆盖 24 个任务与 643 场 clean 判官对战。它的接地门约为 24%：不少回答读起来连贯，但来源预算不足仍会把模型推向不可达或无法核验的引用。',
    href: '/models',
  },
  {
    slug: 'fluent-hallucination',
    title: 'Under judge-only scoring, a fluent report can outrank a grounded one',
    titleZh: '只看判官分时,流畅的报告可以压过有据可依的报告',
    kicker: 'Grounding',
    kickerZh: '接地',
    body: 'The prettiest report can still fabricate unreachable URLs. Composite v3.1 makes citation reachability a first-class ranking signal.',
    bodyZh: '再漂亮的报告也可能捏造无法访问的 URL。Composite v3.1 把引用可达性作为一等排名信号。',
    href: '/methodology#grounding-gate',
  },
  {
    slug: 'dual-judge',
    title: 'Judge family changes the ordering',
    titleZh: '评判模型家族会改变排序',
    kicker: 'Judging',
    kickerZh: '评判',
    body: 'A same-family judge inflates familiar answer styles. The benchmark separates agent and judge families to reduce self-preference.',
    bodyZh: '同家族的评判模型会高估自己熟悉的作答风格。本基准将智能体与评判模型的家族分离，以降低自我偏好。',
    href: '/methodology#dual-judge',
  },
  {
    slug: 'adapter-quality',
    title: 'Adapter quality can beat framework reputation',
    titleZh: '适配器质量可以胜过框架声誉',
    kicker: 'Integration',
    kickerZh: '集成质量',
    body: 'DeerFlow moved sharply after shim and backend fixes, showing that integration quality is part of real-world agent performance.',
    bodyZh: 'DeerFlow 在修复适配层和后端后排名大幅上升，说明集成质量本身就是真实智能体性能的一部分。',
    href: '/sandbox',
  },
  {
    slug: 'length-bias',
    title: 'Long answers are not necessarily grounded answers',
    titleZh: '答案长并不等于答案有据可依',
    kicker: 'Length bias',
    kickerZh: '长度偏置',
    body: 'LLM judges often reward coverage and polish. URL-level verifiers reveal when length hides unsupported claims.',
    bodyZh: 'LLM 评判往往奖励覆盖面与文字打磨。URL 级别的验证器能揭示长度何时掩盖了缺乏支撑的论断。',
    href: '/methodology#bradley-terry',
  },
  {
    slug: 'pareto-front',
    title: 'Only a few agents are cost-quality efficient',
    titleZh: '只有少数智能体在成本与质量上是高效的',
    kicker: 'Efficiency',
    kickerZh: '效率',
    body: 'The efficient frontier is small: most agents are dominated once quality, cost, and dropped runs are considered together.',
    bodyZh: '高效前沿很小：一旦同时考量质量、成本与丢弃的运行，大多数智能体都会被支配。',
    href: '/pillars',
  },
]

export default function InsightsPage() {
  return (
    <>
      <PageHero
        eyebrow={<T en="Insights" zh="洞察" />}
        title={<T en="Findings from the current snapshot." zh="来自当前快照的研究发现。" />}
        intro={<T en={`${STORIES.length} analysis notes on the battle and grounding data: where judge preference and verified evidence disagree, what changed after fixes, and which scoring choices affect the ranking. Each note links to the relevant methodology section or data page.`} zh={`${STORIES.length} 条基于对战与接地数据的分析笔记：判官偏好与可核验证据在哪里出现分歧、修复之后发生了什么变化、哪些计分选择会影响排名。每条笔记都链接到对应的方法论章节或数据页面。`} />}
      />

      <section className="container grid grid-cols-1 gap-4 lg:grid-cols-2">
        {STORIES.map((story, i) => (
          <article key={story.slug} className={i === 0 ? 'card p-7 lg:col-span-2' : 'card card-lift p-6'}>
            <span className="inline-flex rounded-pill border border-hairline bg-surface-low px-2.5 py-1 text-[11px] font-medium text-muted">
              <T en={story.kicker} zh={story.kickerZh} />
            </span>
            <h2 className="mt-3 font-serif text-h-sm text-ink"><T en={story.title} zh={story.titleZh} /></h2>
            <p className="mt-2.5 max-w-3xl text-sm leading-relaxed text-muted"><T en={story.body} zh={story.bodyZh} /></p>
            <Link href={story.href} className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:underline underline-offset-4">
              <T en="Details" zh="查看详情" /> <ArrowUpRight className="h-4 w-4" />
            </Link>
          </article>
        ))}
      </section>
    </>
  )
}
