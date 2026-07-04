import type { ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'
import { juryModels } from '@/lib/data/load-leaderboard'

export const dynamic = 'force-static'

const PIPELINE = [
  { en: 'Task brief', zh: '任务简报' },
  { en: 'Sandbox run', zh: '沙箱运行' },
  { en: 'Report + citations', zh: '报告 + 引用' },
  { en: 'Registry reachability', zh: '注册表可达性' },
  { en: 'Quality axes', zh: '质量轴' },
  { en: 'Composed truth', zh: '复合 truth' },
  { en: 'Presentation tie-break', zh: '呈现平局裁决' },
  { en: 'Leaderboard', zh: '排行榜' },
] as const

const INTENTS = [
  { en: 'Market intelligence', zh: '市场情报' },
  { en: 'Comparison', zh: '对比' },
  { en: 'Debunking', zh: '辟谣' },
  { en: 'Causal explanation', zh: '因果解释' },
  { en: 'Timeline', zh: '时间线' },
  { en: 'Enumeration', zh: '枚举' },
  { en: 'Recommendation', zh: '推荐' },
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
  const jury = juryModels()
  const juryLine = jury.length > 0 ? jury.join(' · ') : 'cross-family LLM jury'

  const SECTIONS: Section[] = [
    {
      id: 'composite',
      title: 'Composed truth score',
      titleZh: '复合 truth 分',
      body: 'The v2 headline is a deterministic composite: truth = reachability^γ × (0.35 fact-support + 0.25 proof-of-fetch + 0.30 completeness + 0.10 spec), γ = 1.5. Reachability is an unfloored hard gate, so a fabricated citation collapses the whole score; the four quality axes each carry an ε = 0.05 floor. No LLM judge enters this number.',
      bodyZh: 'v2 主分是确定性的复合值:truth = 可达性^γ ×（0.35 事实支撑 + 0.25 抓取证明 + 0.30 完整度 + 0.10 规格）,γ = 1.5。可达性是无地板的硬门,编造引用会直接压垮总分;四个质量轴各有 ε = 0.05 地板。该数值不经过任何 LLM 判官。',
      artifact: (
        <Mono>
          <span className="text-white">truth</span> = reachability<sup>1.5</sup> × ( 0.35·fact_support + 0.25·proof_of_fetch + 0.30·completeness + 0.10·spec )
        </Mono>
      ),
    },
    {
      id: 'grounding-gate',
      title: 'Registry reachability',
      titleZh: '注册表可达性',
      body: 'Reachability is a closed-world set-membership test, not a network fetch. Every cited URL is canonicalized and checked against an enumerated registry of 232k corpus pages (products, forum submissions, and Bloom-filtered encyclopedia paths); a citation is reachable iff its canonical form is in the corpus, so search pages, redirect laundering, and off-sandbox links all fail by construction with zero HTTP requests.',
      bodyZh: '可达性是闭世界的集合成员判定,而非网络抓取。每个被引 URL 先规范化,再对一个枚举好的 232k 条语料页注册表（商品、论坛帖、以及经 Bloom filter 覆盖的百科路径）做成员查询;引用的规范形式在语料中才算可达,搜索页、重定向洗链、越沙箱链接都因构造而判失败,全程零 HTTP。',
      artifact: (
        <Mono>
          <pre className="whitespace-pre">
{`for url in report.citations:
    key       = canonicalize(url)        # dedup variants, drop tracking
    reachable = key in registry          # 232k enumerated + Bloom wiki, zero HTTP

reachability = mean(reachable)           # unfloored hard gate
# passage / quote checks now feed the proof-of-fetch axis`}
          </pre>
        </Mono>
      ),
    },
    {
      id: 'jury',
      title: 'Presentation panel',
      titleZh: '呈现质量面板',
      body: 'A cross-family PoLL jury (arXiv 2404.18796) scores presentation quality in anonymized A/B pairs with position swaps. Presentation is reported as its own column and may only break ties between reports the decidable truth score cannot separate; it can never override the truth ranking.',
      bodyZh: '跨家族 PoLL 陪审团(arXiv 2404.18796)在匿名 A/B 对（含位置交换）中为呈现质量打分。呈现质量作为独立列展示,仅用于对可判定 truth 分无法区分的报告做平局裁决,永远不能推翻 truth 排序。',
      artifact: (
        <div className="mt-6 flex flex-wrap items-center gap-2">
          {(jury.length > 0 ? jury : ['juror A', 'juror B', 'juror C']).map((j) => (
            <span key={j} className="rounded-pill border border-hairline bg-surface-low px-3 py-1.5 font-mono text-xs text-ink">
              {j}
            </span>
          ))}
          <span className="text-xs text-muted">
            <T en="· anonymized A/B · position swap · tie-break only" zh="· 匿名 A/B · 位置交换 · 仅平局裁决" />
          </span>
        </div>
      ),
    },
    {
      id: 'bradley-terry',
      title: 'Presentation Elo + bootstrap',
      titleZh: '呈现列 Elo 与自助重采样',
      body: 'Within the presentation column, anonymized A/B outcomes are fit with Bradley-Terry to an Elo scale for tie-breaking only. Separately, a two-level bootstrap (battles → refit → per-task grounding) is used to test the honesty of the judge-vs-grounding correlation, not to rank the board.',
      bodyZh: '在呈现质量列内部,匿名 A/B 结果用 Bradley-Terry 拟合到 Elo 尺度,仅用于平局裁决。另外,两级自助重采样（对战 → 重拟合 → 逐任务接地）用于检验判官分与接地分相关性的诚实性,而非用于排榜。',
      artifact: (
        <Mono>
          P(i ≻ j) = 1 / (1 + 10<sup>(R_j − R_i)/400</sup>)
          <span className="ml-4 text-muted-2">· MLE fit (presentation) · two-level bootstrap → correlation honesty</span>
        </Mono>
      ),
    },
    {
      id: 'intent-typology',
      title: 'Intent typology',
      titleZh: '意图类型',
      body: 'The 100 v2 tasks are built from 7 real-question archetypes across 13 tri-source topic clusters (store category + active forum community + encyclopedia article). Coverage quotas are removed from the prompts and compiled into a hidden spec axis; 3,373 typed, decidable checklist items are generated from corpus answer keys with zero manual annotation.',
      bodyZh: '100 道 v2 任务由 7 种真实提问原型、覆盖 13 个三源主题簇（商店类目 + 活跃论坛社区 + 百科文章）构成。覆盖配额已移出题面,编译进隐藏的 spec 轴;3,373 条带类型的可判定核查项由语料答案键生成,零人工标注。',
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
      body: 'Dropping one scoring component at a time and re-fitting the board reveals which controls actually change conclusions. The unfloored reachability gate is the highest-impact control against fluent hallucination: because truth = reachability^1.5 × quality, a report that cites unreachable pages is driven toward zero regardless of fluency (the fabricator-cannot-top property is a checked theorem, verify_gate_theorem.py). Drop the gate and fabricated-but-fluent reports climb.',
      bodyZh: '每次剔除一个计分组件并重新拟合榜单,可以看出哪些控制真正改变结论。无地板的可达性硬门是对抗流畅幻觉影响最大的控制项:由于 truth = 可达性^1.5 × 质量,引用不可达页面的报告无论多流畅都会被压向零（编造者无法登顶已是可验证定理,verify_gate_theorem.py）。移除该门,捏造但流畅的报告便会上爬。',
      artifact: (
        <Mono>
          <span className="text-muted-2">ablation:</span> drop(axis) → recompose truth → compare orderings
        </Mono>
      ),
    },
  ]

  return (
    <>
      <PageHero
        eyebrow={<T en="Methodology" zh="方法论" />}
        title={<T en="How the public score is computed." zh="公开主分如何计算。" />}
        intro={<T en="Deep Research Arena keeps the audit trail explicit: task brief, tri-source corpus, typed decidable checklist, report with citations, registry reachability and the four quality axes, the composed truth score, and a separate presentation column are each kept as distinct artifacts." zh="Deep Research Arena 明确保留审计链路：任务简报、三源语料、带类型的可判定核查清单、带引用的报告、注册表可达性与四个质量轴、复合出的 truth 分,以及独立的呈现质量列,分别作为独立产物保存。" />}
      >
        <div className="mb-6 rounded-xl border border-hairline bg-surface-low p-4">
          <span className="label-caps text-ink"><T en="Protocol v2 · boards still v1" zh="协议 v2 · 榜单仍为 v1" /></span>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            <T
              en="The scoring stack described here is protocol v2 (five decidable axes, registry reachability). The public boards you see today are still the v1 diagnostic metric; they switch to the v2 truth board after the first full v2 run."
              zh="本页描述的是 v2 协议（五个可判定轴、注册表可达性）。当前公开榜仍采用 v1 诊断口径,将在 v2 全量首跑后切换到 v2 真值榜。"
            />
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Score axes" zh="评分轴" />} value="5" detail={<T en="reachability gate + fact, proof-of-fetch, completeness, spec" zh="可达性硬门 + 事实、抓取证明、完整度、规格" />} />
          <MetricCard label={<T en="Presentation panel" zh="呈现质量面板" />} value={String(jury.length || 3)} detail={<T en="cross-family PoLL jury, tie-break only" zh="跨家族 PoLL 陪审团,仅平局裁决" />} />
          <MetricCard label={<T en="Bootstrap" zh="自助重采样" />} value="1,000" detail={<T en="two-level, Elo-vs-grounding honesty" zh="两级,判官-接地相关性检验" />} />
          <MetricCard label={<T en="Archetypes" zh="提问原型" />} value="7" detail={<T en="real-question archetypes across 13 clusters" zh="真实提问原型,覆盖 13 个三源簇" />} />
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
