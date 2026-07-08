import Link from 'next/link'
import { ArrowUpRight } from 'lucide-react'
import { PageHero } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

const STORIES = [
  {
    slug: 'jury-vs-grounding',
    title: 'The jury favourite is not the Arena leader',
    titleZh: '陪审团最喜欢的,不是 Arena 的第一名',
    kicker: 'Harness board',
    kickerZh: '框架榜',
    body: 'ii-researcher holds the highest jury Elo on both backbones (1381 on Qwen3-8B, 1430 on DS-V4-Flash), but only 27% and 5% of its cited URLs resolve, so its Arena score collapses to 12.5 and 1.0. smolagents on DS-V4-Flash leads instead: 81% reach and an 80% win rate.',
    bodyZh: 'ii-researcher 在两个主干模型上都拿到最高的陪审团 Elo（Qwen3-8B 上 1381,DS-V4-Flash 上 1430）,但引用可达率只有 27% 和 5%,Arena 主分因此塌缩到 12.5 和 1.0。领跑的是 DS-V4-Flash 上的 smolagents：81% 可达率加 80% 胜率。',
    href: '/methodology#grounding-gate',
  },
  {
    slug: 'backbone-sensitivity',
    title: 'The same harness can flip rank when the backbone changes',
    titleZh: '换一个主干模型,同一框架的排名可以完全翻转',
    kicker: 'Backbone board',
    kickerZh: '模型榜',
    body: 'local-deep-research scores 58.3 on Qwen3-8B but 11.8 on DS-V4-Flash — reach stays near-perfect on both, yet its jury win rate collapses from 64% to 12%. smolagents moves the other way. Averaging across backbones is what keeps the headline board honest.',
    bodyZh: 'local-deep-research 在 Qwen3-8B 上拿 58.3,在 DS-V4-Flash 上只有 11.8 —— 两边可达率都接近满分,但陪审团胜率从 64% 跌到 12%。smolagents 则正好相反。这正是主榜要对主干模型取平均的原因。',
    href: '/models',
  },
  {
    slug: 'fluent-hallucination',
    title: 'Under judge-only scoring, a fluent report can outrank a grounded one',
    titleZh: '只看判官分时,流畅的报告可以压过有据可依的报告',
    kicker: 'Grounding',
    kickerZh: '接地',
    body: 'The prettiest report can still fabricate unreachable URLs. The Arena score raises reach to the 1.5 power, so weak grounding is penalised super-linearly before jury preference counts.',
    bodyZh: '再漂亮的报告也可能捏造无法访问的 URL。Arena 主分对可达率取 1.5 次幂,在陪审团偏好起作用之前就对弱接地施加超线性惩罚。',
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
    href: '/models',
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
