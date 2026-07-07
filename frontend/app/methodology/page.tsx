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
      body: 'Reachability is a closed-world set-membership test, not a network fetch. Every cited URL is canonicalized and checked against an enumerated registry of 232k corpus pages (104k products + 127k forum submissions), plus a Bloom filter over the full 19.0M-key encyclopedia enumeration (0.5% FPR, no false negatives); a citation is reachable iff its canonical form is in the corpus, so search pages, redirect laundering, and off-sandbox links all fail by construction with zero HTTP requests.',
      bodyZh: '可达性是闭世界的集合成员判定,而非网络抓取。每个被引 URL 先规范化,再对一个枚举好的 232k 条语料页注册表（104k 商品 + 127k 论坛帖）做成员查询,百科则用覆盖全量 1,900 万条路径枚举的 Bloom filter（假阳率 0.5%,无假阴性）;引用的规范形式在语料中才算可达,搜索页、重定向洗链、越沙箱链接都因构造而判失败,全程零 HTTP。',
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
      title: 'LLM jury',
      titleZh: 'LLM 陪审团',
      body: 'A cross-family 3-judge PoLL jury (arXiv 2404.18796) compares reports in anonymized A/B pairs with position swaps and majority vote. On the current truth-gated Elo board the jury Elo is the quality signal, always scaled by the grounding gate so it can never rescue fabricated citations. Once the five-axis truth board goes live, the jury demotes to a presentation-only column that may break ties between reports the decidable truth score cannot separate, and can never override the truth ranking.',
      bodyZh: '跨家族 3 判官 PoLL 陪审团(arXiv 2404.18796)在匿名 A/B 对（含位置交换、多数票）中比较报告。在当前的 truth-gated Elo 榜上,陪审团 Elo 是质量信号,但始终乘以接地门,因此永远救不回编造引用。五轴 truth 榜上线后,陪审团降级为仅呈现质量列,只用于对可判定 truth 分无法区分的报告做平局裁决,永远不能推翻 truth 排序。',
      artifact: (
        <div className="mt-6 flex flex-wrap items-center gap-2">
          {(jury.length > 0 ? jury : ['juror A', 'juror B', 'juror C']).map((j) => (
            <span key={j} className="rounded-pill border border-hairline bg-surface-low px-3 py-1.5 font-mono text-xs text-ink">
              {j}
            </span>
          ))}
          <span className="text-xs text-muted">
            <T en="· anonymized A/B · position swap · majority vote · gated by grounding" zh="· 匿名 A/B · 位置交换 · 多数票 · 受接地门约束" />
          </span>
        </div>
      ),
    },
    {
      id: 'bradley-terry',
      title: 'Truth-gated Elo (current board)',
      titleZh: 'Truth-gated Elo（当前榜）',
      body: 'The public board today ranks by truth-gated Elo: anonymized jury A/B outcomes are fit with Bradley-Terry to an Elo scale, then multiplied by the grounding gate (the mean of citation reachability and quote verification). Raw judge Elo stays visible as its own tab but never decides the public ranking alone; bootstrap confidence intervals over the battle set accompany each rating.',
      bodyZh: '当前公开榜按 truth-gated Elo 排名:匿名陪审团 A/B 结果用 Bradley-Terry 拟合到 Elo 尺度,再乘以接地门（引用可达率与引文核实率的均值）。裸判官 Elo 作为独立 tab 保留展示,但永远不单独决定公开排名;每个评分附带对战集自助重采样的置信区间。',
      artifact: (
        <Mono>
          score = Elo × gate,&nbsp;&nbsp;P(i ≻ j) = 1 / (1 + 10<sup>(R_j − R_i)/400</sup>)
          <span className="ml-4 text-muted-2">· BT MLE fit · gate = mean(reachability, quote-verified) · bootstrap CIs</span>
        </Mono>
      ),
    },
    {
      id: 'calibration',
      title: 'Calibration + sensitivity',
      titleZh: '校准与敏感性',
      body: 'The free parameters of the composite are calibrated externally, never fitted on the eval panel. The proof-of-fetch threshold (0.35) was set on 640 verbatim-positive and fabricated/cross-page-negative snippets plus a paraphrase side-class: TPR 1.000, fabricated FPR 0.000, cross-page FPR 0.6%, flat across the 0.15-0.60 grid. γ = 1.5 is checked by fabrication injection: truth must decrease monotonically as injected fabrication rises through {0, 0.1, 0.25, 0.5}. Weight robustness: across 2,000 Dirichlet weight draws, 91.6% reproduce the identical full ranking and the top 2 never change.',
      bodyZh: '复合分的自由参数全部在外部校准,绝不在评测面板上拟合。抓取证明阈值（0.35）在 640 条原文正例与编造/跨页负例外加一组转写侧类上标定:TPR 1.000,编造假阳率 0.000,跨页假阳率 0.6%,且在 0.15-0.60 网格上平坦。γ = 1.5 用注入编造法检验:注入编造率经过 {0, 0.1, 0.25, 0.5} 时 truth 必须单调下降。权重稳健性:2,000 组 Dirichlet 权重抽样中 91.6% 复现完全相同的全排名,前 2 名从未改变。',
      artifact: (
        <Mono>
          <span className="text-muted-2">pof_threshold=0.35 · TPR 1.000 / FPR 0.000 (fabricated) · γ=1.5 monotone under injection · 2,000 weight draws → 91.6% identical ranking</span>
        </Mono>
      ),
    },
    {
      id: 'lane-fairness',
      title: 'Lane fairness',
      titleZh: '通道公平性',
      body: 'The harness never ghostwrites: if a framework fails, its lane emits an explicit error stub instead of a synthesized report, and a lane is marked lane_failed when stubs plus missing records exceed half its runs. A full fairness audit removed every harness-side grounding manufacture (post-hoc citation grafting, prior-run memory seeding) and repaired every adapter defect, and all LLM traffic flows through one policy gateway with per-run usage accounting.',
      bodyZh: '评测框架绝不代笔:框架失败时,其通道输出显式错误存根而非合成报告;当存根加缺失记录超过该通道一半时标记 lane_failed。一次完整的公平性审计移除了所有评测侧的接地制造行为（事后引用嫁接、跨次运行记忆种子）,并修复了每个适配器缺陷;全部 LLM 流量经由统一策略网关,逐次运行记账 token 用量。',
      artifact: (
        <Mono>
          <span className="text-muted-2">framework failure → (lane error: phase: reason) stub · stubs + missing &gt; 50% → lane_failed · unified LLM gateway, per-run usage log</span>
        </Mono>
      ),
    },
    {
      id: 'intent-typology',
      title: 'Intent typology',
      titleZh: '意图类型',
      body: 'The 100 v2 tasks are built from 7 real-question archetypes across 13 tri-source topic clusters (store category + active forum community + encyclopedia article). Coverage quotas are removed from the prompts and compiled into a hidden spec axis; the answer keys carry 3,478 typed fact nuggets plus 191 spec requirements and 88 adjudicated contradictions, all generated from the corpus with zero manual annotation.',
      bodyZh: '100 道 v2 任务由 7 种真实提问原型、覆盖 13 个三源主题簇（商店类目 + 活跃论坛社区 + 百科文章）构成。覆盖配额已移出题面,编译进隐藏的 spec 轴;答案键含 3,478 条带类型的事实要点、191 条 spec 要求与 88 条经裁决的矛盾项,全部由语料生成,零人工标注。',
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
          <span className="label-caps text-ink"><T en="Five-axis protocol · boards on truth-gated Elo" zh="五轴协议 · 当前榜为 truth-gated Elo" /></span>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            <T
              en="The scoring stack described here is the five-axis decidable protocol (registry reachability gate over four quality axes). The public boards you see today rank by truth-gated Elo (jury Elo × grounding gate); they switch to the five-axis truth board after the first full run under the new protocol completes."
              zh="本页描述的是五轴可判定协议（注册表可达性硬门叠加四个质量轴）。当前公开榜按 truth-gated Elo（陪审团 Elo × 接地门）排名,待新协议下的首次全量运行完成后切换到五轴真值榜。"
            />
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Score axes" zh="评分轴" />} value="5" detail={<T en="reachability gate + fact, proof-of-fetch, completeness, spec" zh="可达性硬门 + 事实、抓取证明、完整度、规格" />} />
          <MetricCard label={<T en="LLM jury" zh="LLM 陪审团" />} value={String(jury.length || 3)} detail={<T en="cross-family PoLL jury, always gated by grounding" zh="跨家族 PoLL 陪审团,始终受接地门约束" />} />
          <MetricCard label={<T en="Weight draws" zh="权重抽样" />} value="2,000" detail={<T en="Dirichlet draws, 91.6% identical ranking" zh="Dirichlet 抽样,91.6% 排名完全一致" />} />
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
