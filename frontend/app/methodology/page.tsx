import type { ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'
import { taskStats } from '@/lib/data/tasks'
import { juryModels } from '@/lib/data/load-leaderboard'

export const dynamic = 'force-static'

const PIPELINE = [
  { en: 'Task brief', zh: '任务简报' },
  { en: 'Sandbox run', zh: '沙箱运行' },
  { en: 'Report + citations', zh: '报告 + 引用' },
  { en: 'Grounding verifiers', zh: '接地验证器' },
  { en: 'Jury battles', zh: '陪审团对战' },
  { en: 'Bradley-Terry fit', zh: 'Bradley-Terry 拟合' },
  { en: 'Truth gate', zh: '真值门控' },
  { en: 'Leaderboard', zh: '排行榜' },
] as const

const INTENTS = [
  { en: 'Market intelligence', zh: '市场情报' },
  { en: 'Comparison', zh: '对比' },
  { en: 'Debunking', zh: '辟谣' },
  { en: 'Causal explanation', zh: '因果解释' },
  { en: 'Timeline', zh: '时间线' },
  { en: 'Enumeration', zh: '枚举' },
] as const

interface Section {
  id: string
  title: string
  titleZh: string
  body: string
  bodyZh: string
  /** Distinct per-step artifact rendered below the prose. */
  artifact: ReactNode
}

function Mono({ children }: { children: ReactNode }) {
  return (
    <div className="mt-6 overflow-x-auto rounded-xl border border-hairline bg-surface-low p-5 font-mono text-xs leading-relaxed text-muted md:text-[13px]">
      {children}
    </div>
  )
}

export default function MethodologyPage() {
  const stats = taskStats()
  const jury = juryModels()
  const juryLine = jury.length > 0 ? jury.join(' · ') : 'cross-family LLM jury'

  const SECTIONS: Section[] = [
    {
      id: 'composite',
      title: 'Truth-gated Elo',
      titleZh: '真值门控 Elo',
      body: 'The headline score is the pairwise judge Elo multiplied by the grounding gate (mean of citation reachability and quote verification), so unsupported reports cannot win on fluency alone. Raw judge Elo stays visible as a diagnostic tab; the gate decides the public order.',
      bodyZh: '榜单主分 = 成对判官 Elo × 接地门（引用可达率与引文核实率的均值），缺乏支撑的报告无法仅凭文采取胜。裸判官 Elo 作为诊断视图保留,公开排序由门控决定。',
      artifact: (
        <Mono>
          <span className="text-white">public_score</span> = round( judge_elo × (reachability_pct + quote_match_pct) / 200 )
        </Mono>
      ),
    },
    {
      id: 'grounding-gate',
      title: 'Grounding gate',
      titleZh: '接地门控',
      body: 'The gate is judge-free. Every markdown-linked URL in a report is re-fetched inside the frozen sandbox; a citation only counts as evidence if the page resolves, and a quote only counts if the quoted passage appears on that page. Missing or fabricated citations reduce the effective score multiplicatively.',
      bodyZh: '门控不依赖判官。报告中每个以 markdown 链接呈现的 URL 都会在冻结沙箱内被重新抓取;页面可达,引用才算证据;引述段落出现在该页面上,引文才算核实。缺失或捏造的引用会以乘性方式降低有效得分。',
      artifact: (
        <Mono>
          <pre className="whitespace-pre">
{`for (url, quote) in report.citations:
    page      = sandbox.fetch(url)        # frozen corpus, every fetch logged
    reachable = page is not None
    verified  = reachable and quote in page.text

reachability  = mean(reachable)
quote_match   = mean(verified)
gate          = (reachability + quote_match) / 2   # in [0, 1]`}
          </pre>
        </Mono>
      ),
    },
    {
      id: 'jury',
      title: 'Jury battles',
      titleZh: '陪审团对战',
      body: 'Reports meet in anonymized A/B battles per task. A cross-family PoLL jury (arXiv 2404.18796) votes on each pair; positions are swapped to cancel order bias and the majority decides. Because the grounding gate is computed without any judge, jury taste alone can never rank an ungrounded report first.',
      bodyZh: '报告按任务进行匿名 A/B 对战。跨模型家族的 PoLL 陪审团(arXiv 2404.18796)对每一对报告投票;交换位置以抵消顺序偏置,多数票裁决。由于接地门的计算完全不经过判官,仅凭陪审团口味无法让缺乏证据的报告登顶。',
      artifact: (
        <div className="mt-6 flex flex-wrap items-center gap-2">
          {(jury.length > 0 ? jury : ['juror A', 'juror B', 'juror C']).map((j) => (
            <span key={j} className="rounded-pill border border-hairline bg-surface-low px-3 py-1.5 font-mono text-xs text-ink">
              {j}
            </span>
          ))}
          <span className="text-xs text-muted">
            <T en="· anonymized A/B · position swap · majority vote" zh="· 匿名 A/B · 位置交换 · 多数票" />
          </span>
        </div>
      ),
    },
    {
      id: 'bradley-terry',
      title: 'Bradley-Terry Elo + bootstrap CI',
      titleZh: 'Bradley-Terry Elo 与自助置信区间',
      body: 'Per-task jury outcomes become pairwise battles. Maximum-likelihood estimation under the Bradley-Terry model turns win/loss records into agent strengths on an Elo scale, and resampling battles 1,000 times yields a 95% confidence interval per agent. Wide intervals mean fewer battles and a less certain rank.',
      bodyZh: '逐任务的陪审团结果转化为两两对战。在 Bradley-Terry 模型下用极大似然估计把胜负记录变成 Elo 尺度上的强度,并对对战重采样 1,000 次,给出每个智能体的 95% 置信区间。区间越宽,对战越少,排名越不确定。',
      artifact: (
        <Mono>
          P(i ≻ j) = 1 / (1 + 10<sup>(R_j − R_i)/400</sup>)
          <span className="ml-4 text-muted-2">· MLE fit · 1,000 bootstrap resamples → 95% CI</span>
        </Mono>
      ),
    },
    {
      id: 'intent-typology',
      title: 'Intent typology',
      titleZh: '意图类型',
      body: 'Tasks span six intent families, each with its own failure modes and task-specific checklists. A leaderboard built on one intent family would reward one research style; mixing them keeps the ranking honest across genres.',
      bodyZh: '任务涵盖六个意图族,每族有各自的失败模式与针对性核查清单。只用一种意图构建榜单会偏向单一研究风格;混合意图让排名在不同题型间保持公平。',
      artifact: (
        <div className="mt-6 flex flex-wrap gap-2">
          {INTENTS.map((it) => (
            <span key={it.en} className="rounded-pill border border-hairline bg-surface-low px-3 py-1.5 text-xs font-medium text-ink">
              <T en={it.en} zh={it.zh} />
            </span>
          ))}
        </div>
      ),
    },
    {
      id: 'ablation',
      title: 'Ablation protocol',
      titleZh: '消融协议',
      body: 'Dropping one scoring component at a time and re-fitting the board reveals which controls actually change conclusions. The truth and citation gates are the highest-impact controls against fluent hallucination: remove them and fabricated-but-fluent reports climb the board.',
      bodyZh: '每次剔除一个计分组件并重新拟合榜单,可以看出哪些控制真正改变结论。真值门控与引用门控是对抗流畅幻觉影响最大的控制项:一旦移除,捏造但流畅的报告就会爬上榜单。',
      artifact: (
        <Mono>
          <span className="text-muted-2">ablation:</span> drop(component) → refit Bradley-Terry → compare orderings
        </Mono>
      ),
    },
  ]

  return (
    <>
      <PageHero
        eyebrow={<T en="Methodology" zh="方法论" />}
        title={<T en="How the public score is computed." zh="公开主分如何计算。" />}
        intro={<T en="Deep Research Arena keeps the audit trail explicit: task, source pool, checklist, report, grounding checks, pairwise jury outcome, and confidence interval are separate artifacts." zh="Deep Research Arena 明确保留审计链路：任务、来源池、核查清单、报告、接地核验、两两陪审结果和置信区间分别作为独立产物保存。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Score axes" zh="评分轴" />} value="2" detail={<T en="grounding (judge-free) and judge Elo" zh="接地（不依赖判官）与判官 Elo" />} />
          <MetricCard label={<T en="Jurors" zh="陪审员" />} value={String(jury.length || 3)} detail={<T en="cross-family PoLL jury, majority vote" zh="跨家族 PoLL 陪审团,多数票" />} />
          <MetricCard label={<T en="Bootstrap" zh="自助重采样" />} value="1,000" detail={<T en="confidence interval resamples" zh="置信区间重采样次数" />} />
          <MetricCard label={<T en="Intent families" zh="意图族" />} value={String(stats.intents)} detail={<T en="task families with separate failure modes" zh="具有不同失败模式的任务族" />} />
        </div>

        {/* Pipeline strip */}
        <div className="no-scrollbar mt-6 overflow-x-auto">
          <ol className="flex min-w-max items-center gap-1.5 rounded-2xl border border-hairline bg-white p-3 shadow-soft">
            {PIPELINE.map((step, i) => (
              <li key={step.en} className="flex items-center gap-1.5">
                <span
                  className={
                    i === PIPELINE.length - 1
                      ? 'rounded-pill bg-ink px-3 py-1.5 text-xs font-medium text-white'
                      : 'rounded-pill bg-surface-low px-3 py-1.5 text-xs font-medium text-ink'
                  }
                >
                  <T en={step.en} zh={step.zh} />
                </span>
                {i < PIPELINE.length - 1 ? <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-2" /> : null}
              </li>
            ))}
          </ol>
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-8 lg:grid-cols-[280px_1fr]">
        <aside className="hidden lg:block">
          <nav className="sticky top-24 rounded-card border border-hairline bg-white p-3 shadow-soft">
            {SECTIONS.map((section) => (
              <a key={section.id} href={`#${section.id}`} className="block rounded-tab px-3 py-2 text-sm text-muted hover:bg-surface-low hover:text-ink">
                <T en={section.title} zh={section.titleZh} />
              </a>
            ))}
            <a href="#references" className="block rounded-tab px-3 py-2 text-sm text-muted hover:bg-surface-low hover:text-ink">
              <T en="References" zh="参考文献" />
            </a>
          </nav>
        </aside>
        <div className="space-y-5">
          {SECTIONS.map((section, i) => (
            <article key={section.id} id={section.id} className="card scroll-mt-24 p-7">
              <span className="label-caps"><T en={`Step ${i + 1}`} zh={`步骤 ${i + 1}`} /></span>
              <h2 className="mt-3 font-serif text-h-sm text-ink md:text-h-md"><T en={section.title} zh={section.titleZh} /></h2>
              <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted"><T en={section.body} zh={section.bodyZh} /></p>
              {section.artifact}
            </article>
          ))}

          {/* References */}
          <article id="references" className="card scroll-mt-24 p-7">
            <span className="label-caps"><T en="References" zh="参考文献" /></span>
            <h2 className="mt-3 font-serif text-h-sm text-ink"><T en="References" zh="参考文献" /></h2>
            <ul className="mt-4 space-y-3 text-sm leading-relaxed text-muted">
              <li>
                <span className="font-medium text-ink">PoLL — Panel of LLM evaluators.</span>{' '}
                <T en="Cross-family juries reduce single-judge self-preference." zh="跨家族陪审团可降低单判官的自我偏好。" />{' '}
                <a href="https://arxiv.org/abs/2404.18796" target="_blank" rel="noreferrer" className="text-brand hover:underline">
                  arXiv:2404.18796
                </a>
              </li>
              <li>
                <span className="font-medium text-ink">Bradley &amp; Terry (1952).</span>{' '}
                <T en="Rank analysis of incomplete block designs — the pairwise-comparison model behind the Elo fit." zh="不完全区组设计的秩分析 —— Elo 拟合背后的成对比较模型。" />
              </li>
              <li>
                <span className="font-medium text-ink">Efron (1979).</span>{' '}
                <T en="Bootstrap methods — the resampling scheme behind every 95% confidence interval on the board." zh="Bootstrap 方法 —— 榜单上所有 95% 置信区间背后的重采样方案。" />
              </li>
            </ul>
          </article>
        </div>
      </section>
    </>
  )
}
