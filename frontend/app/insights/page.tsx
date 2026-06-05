import Link from 'next/link'
import { ArrowUpRight } from 'lucide-react'
import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

const STORIES = [
  {
    slug: 'judge-vs-grounding',
    title: 'The judge crowns a fabricator: Elo #1 has 4% reachable citations',
    titleZh: '判官把伪造者捧上榜首:Elo 第一名的引用只有 4% 真实可达',
    kicker: '1553 battles',
    kickerZh: '1553 场对战',
    body: 'With every agent scored and no grounding gate, the pairwise LLM judge ranks GPT-Researcher #1 (Elo 1207) while only 4.3% of its citations resolve. The most grounded agents (camel-ai 60%, DeerFlow 60%) rank mid-table. The leaderboard now shows grounding next to Elo so the divergence is visible, not hidden.',
    bodyZh: '在全员计分、不设接地门槛的情况下,成对 LLM 判官把 GPT-Researcher 排到第一(Elo 1207),而它的引用只有 4.3% 真实可达。接地最扎实的 camel-ai(60%)和 DeerFlow(60%)只排中游。排行榜现在把接地列放在 Elo 旁边,让这种分歧直接可见。',
  },
  {
    slug: 'qwen3-cheap-baseline',
    title: 'A $0.003-per-task qwen3 baseline lands mid-field on grounding',
    titleZh: '每任务 0.003 美元的 qwen3 基线,接地分落在中游',
    kicker: '$0.33 total',
    kickerZh: '总共 $0.33',
    body: 'qwen3-30b-a3b-instruct-2507 under a fixed minimal protocol (2 model calls, 8 sources) ran all 94 tasks for $0.33 total and reached grounding 0.24, tied with ii-researcher and above several full frameworks. Caveat: given only 8 real sources but pressure to cite dozens, it fabricated the remainder in valid URL format despite explicit instructions.',
    bodyZh: 'qwen3-30b-a3b-instruct-2507 在固定极简协议下(2 次模型调用、8 个来源)跑完 94 个任务总花费 $0.33,接地 0.24,与 ii-researcher 持平并高于多个完整框架。注意:在只有 8 个真实来源却被要求引用几十条的压力下,它无视明确指令,按正确 URL 格式编造了其余引用。',
  },
  {
    slug: 'fluent-hallucination',
    title: 'Fluent hallucination beats naive judges',
    titleZh: '流畅的幻觉能骗过粗糙的评判',
    kicker: 'F6',
    kickerZh: 'F6',
    body: 'The prettiest report can still fabricate unreachable URLs. Composite v3.1 makes citation reachability a first-class ranking signal.',
    bodyZh: '再漂亮的报告也可能捏造无法访问的 URL。Composite v3.1 把引用可达性作为一等排名信号。',
  },
  {
    slug: 'dual-judge',
    title: 'Judge family changes the ordering',
    titleZh: '评判模型家族会改变排序',
    kicker: 'Dual judge',
    kickerZh: '双评判',
    body: 'A same-family judge inflates familiar answer styles. The benchmark separates agent and judge families to reduce self-preference.',
    bodyZh: '同家族的评判模型会高估自己熟悉的作答风格。本基准将智能体与评判模型的家族分离，以降低自我偏好。',
  },
  {
    slug: 'adapter-quality',
    title: 'Adapter quality can beat framework reputation',
    titleZh: '适配器质量可以胜过框架声誉',
    kicker: '+162 Elo',
    kickerZh: '+162 Elo',
    body: 'DeerFlow moved sharply after shim and backend fixes, showing that integration quality is part of real-world agent performance.',
    bodyZh: 'DeerFlow 在修复适配层和后端后排名大幅上升，说明集成质量本身就是真实智能体性能的一部分。',
  },
  {
    slug: 'length-bias',
    title: 'Long answers are not necessarily grounded answers',
    titleZh: '答案长并不等于答案有据可依',
    kicker: 'RACE',
    kickerZh: 'RACE',
    body: 'LLM judges often reward coverage and polish. URL-level verifiers reveal when length hides unsupported claims.',
    bodyZh: 'LLM 评判往往奖励覆盖面与文字打磨。URL 级别的验证器能揭示长度何时掩盖了缺乏支撑的论断。',
  },
  {
    slug: 'pareto-front',
    title: 'Only a few agents are cost-quality efficient',
    titleZh: '只有少数智能体在成本与质量上是高效的',
    kicker: 'Pareto',
    kickerZh: 'Pareto',
    body: 'The efficient frontier is small: most agents are dominated once quality, cost, and dropped runs are considered together.',
    bodyZh: '高效前沿很小：一旦同时考量质量、成本与丢弃的运行，大多数智能体都会被支配。',
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
            <Link href={`/methodology#${story.slug}`} className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-brand">
              <T en="Read methodology context" zh="阅读方法学背景" /> <ArrowUpRight className="h-4 w-4" />
            </Link>
          </article>
        ))}
      </section>
    </>
  )
}
