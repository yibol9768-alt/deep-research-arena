import Link from 'next/link'
import { ArrowUpRight } from 'lucide-react'
import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

const STORIES = [
  {
    slug: 'judge-vs-grounding',
    title: 'Raw judge Elo and grounded evidence disagree sharply',
    titleZh: '裸判官 Elo 与真实证据出现明显分歧',
    kicker: '2615 battles',
    kickerZh: '2615 场对战',
    body: 'GPT-Researcher sits near the top by raw judge Elo (1147), but only 4.3% of its cited URLs resolve and 2.2% of quoted evidence is verified. The truth-gated board drops it to #11, while Claude Code and OpenCode lead because quality and evidence both hold up.',
    bodyZh: 'GPT-Researcher 的裸判官 Elo 很高（1147），但引用可达率只有 4.3%，引文核实率只有 2.2%。真值门控榜将其降到第 11；Claude Code 与 OpenCode 领先，是因为报告质量与证据质量同时成立。',
    href: '/methodology#grounding-gate',
  },
  {
    slug: 'qwen3-cheap-baseline',
    title: 'The minimal qwen3 baseline exposes the cost of citation pressure',
    titleZh: '极简 qwen3 基线暴露了引用压力的代价',
    kicker: '24 model tasks',
    kickerZh: '24 个模型任务',
    body: 'In the current model board, qwen3-30b-a3b-instruct-2507 runs under the fixed minimal protocol across 24 tasks and 643 clean judge battles. Its grounding gate is about 24%: many answers read coherently, but weak source budgets still push the model toward unreachable or unverifiable citations.',
    bodyZh: '在当前模型榜中，qwen3-30b-a3b-instruct-2507 使用固定极简协议，覆盖 24 个任务与 643 场 clean 判官对战。它的接地门约为 24%：不少回答读起来连贯，但来源预算不足仍会把模型推向不可达或无法核验的引用。',
    href: '/models',
  },
  {
    slug: 'fluent-hallucination',
    title: 'Fluent hallucination beats naive judges',
    titleZh: '流畅的幻觉能骗过粗糙的评判',
    kicker: 'F6',
    kickerZh: 'F6',
    body: 'The prettiest report can still fabricate unreachable URLs. Composite v3.1 makes citation reachability a first-class ranking signal.',
    bodyZh: '再漂亮的报告也可能捏造无法访问的 URL。Composite v3.1 把引用可达性作为一等排名信号。',
    href: '/methodology#grounding-gate',
  },
  {
    slug: 'dual-judge',
    title: 'Judge family changes the ordering',
    titleZh: '评判模型家族会改变排序',
    kicker: 'Dual judge',
    kickerZh: '双评判',
    body: 'A same-family judge inflates familiar answer styles. The benchmark separates agent and judge families to reduce self-preference.',
    bodyZh: '同家族的评判模型会高估自己熟悉的作答风格。本基准将智能体与评判模型的家族分离，以降低自我偏好。',
    href: '/methodology#dual-judge',
  },
  {
    slug: 'adapter-quality',
    title: 'Adapter quality can beat framework reputation',
    titleZh: '适配器质量可以胜过框架声誉',
    kicker: '+162 Elo',
    kickerZh: '+162 Elo',
    body: 'DeerFlow moved sharply after shim and backend fixes, showing that integration quality is part of real-world agent performance.',
    bodyZh: 'DeerFlow 在修复适配层和后端后排名大幅上升，说明集成质量本身就是真实智能体性能的一部分。',
    href: '/sandbox',
  },
  {
    slug: 'length-bias',
    title: 'Long answers are not necessarily grounded answers',
    titleZh: '答案长并不等于答案有据可依',
    kicker: 'RACE',
    kickerZh: 'RACE',
    body: 'LLM judges often reward coverage and polish. URL-level verifiers reveal when length hides unsupported claims.',
    bodyZh: 'LLM 评判往往奖励覆盖面与文字打磨。URL 级别的验证器能揭示长度何时掩盖了缺乏支撑的论断。',
    href: '/methodology#bradley-terry',
  },
  {
    slug: 'pareto-front',
    title: 'Only a few agents are cost-quality efficient',
    titleZh: '只有少数智能体在成本与质量上是高效的',
    kicker: 'Pareto',
    kickerZh: 'Pareto',
    body: 'The efficient frontier is small: most agents are dominated once quality, cost, and dropped runs are considered together.',
    bodyZh: '高效前沿很小：一旦同时考量质量、成本与丢弃的运行，大多数智能体都会被支配。',
    href: '/pillars',
  },
]

export default function InsightsPage() {
  return (
    <>
      <PageHero
        eyebrow={<T en="Findings & Stories" zh="发现与故事" />}
        title={<T en="The leaderboard is the table. These are the reasons behind the table." zh="排行榜只是结果，这些才是结果背后的原因。" />}
        intro={<T en="Insights turns raw Elo movement into benchmark lessons: what failed, what improved, and which scoring choices changed conclusions." zh="洞察把原始的 Elo 变动转化为基准层面的经验：什么失败了、什么改进了，以及哪些评分选择改变了结论。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Findings" zh="发现" />} value={String(STORIES.length)} detail={<T en="launch stories" zh="首发故事" />} />
          <MetricCard label={<T en="Core risk" zh="核心风险" />} value="URLs" detail={<T en="fabricated or weak citations" zh="捏造或薄弱的引用" />} />
          <MetricCard label={<T en="Lens" zh="视角" />} value="Elo" detail={<T en="pairwise, not average-only" zh="基于两两对比，而非仅看平均分" />} />
          <MetricCard label={<T en="Output" zh="产出" />} value="Paper" detail={<T en="NeurIPS-ready narrative" zh="可投 NeurIPS 的论述" />} />
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-4 lg:grid-cols-2">
        {STORIES.map((story, i) => (
          <article key={story.slug} className={i === 0 ? 'card p-7 lg:col-span-2' : 'card card-lift p-6'}>
            <span className="label-caps"><T en={story.kicker} zh={story.kickerZh} /></span>
            <h2 className="mt-3 font-serif text-h-sm text-ink md:text-h-md"><T en={story.title} zh={story.titleZh} /></h2>
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted"><T en={story.body} zh={story.bodyZh} /></p>
            <Link href={story.href} className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-brand">
              <T en="Open supporting context" zh="查看相关背景" /> <ArrowUpRight className="h-4 w-4" />
            </Link>
          </article>
        ))}
      </section>
    </>
  )
}
