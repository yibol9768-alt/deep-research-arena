import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { loadLeaderboard, rankedAgents } from '@/lib/data/load-leaderboard'
import { agentMeta } from '@/lib/providers'
import { T } from '@/components/i18n/t'
import { fmt, groundingGatePct, truthScore } from '@/lib/format'

export const dynamic = 'force-static'

// Protocol v2 decidable stack: five axes feed the truth composite, presentation
// is a separate tie-break column with no weight in truth.
const AXES = [
  {
    name: 'Reachability',
    nameZh: '可达性',
    role: 'Hard gate',
    roleZh: '硬门',
    description: 'Every cited page must exist in the frozen URL registry. It is a set-membership check with zero HTTP and acts as a hard gate (exponent 1.5, no floor): fabricated citations collapse the whole score.',
    descriptionZh: '每条引用的页面必须存在于冻结的 URL 注册表中。这是零 HTTP 的集合成员查询，并作为硬门（指数 1.5，无地板）：编造的引用会压垮整体得分。',
  },
  {
    name: 'Fact support',
    nameZh: '事实支持',
    role: 'Weight 0.35',
    roleZh: '权重 0.35',
    description: 'Claims are checked against the corpus-computed answer key, with each factual claim bound to its cited entity.',
    descriptionZh: '论断对照由语料计算的答案键核验，每条事实声明都绑定到其引用实体。',
  },
  {
    name: 'Completeness',
    nameZh: '完整性',
    role: 'Weight 0.30',
    roleZh: '权重 0.30',
    description: 'Coverage of the relevant set and required concept anchors, matched from the hidden answer key rather than a fixed source quota. The answer keys carry 3,478 typed fact nuggets (plus 191 spec requirements and 88 adjudicated contradictions), computed from the corpus with zero human annotation, each routed to a scoring axis.',
    descriptionZh: '对相关集合与所需概念锚的覆盖度，依据隐藏答案键匹配，而非固定的来源配额。答案键含 3,478 条带类型的事实要点（另有 191 条 spec 要求与 88 条经裁决的矛盾项），全部由语料计算、零人工标注，并逐条路由到评分轴。',
  },
  {
    name: 'Proof of fetch',
    nameZh: '抓取证据',
    role: 'Weight 0.25',
    roleZh: '权重 0.25',
    description: 'Reports must show evidence the cited page was actually read; empty context is recorded as a checked-fail. Citation parseability and link precedence are enforced here, not as a separate markdown axis.',
    descriptionZh: '报告必须给出确实读取了引用页面的证据；空上下文记为 checked-fail。引用可解析性与链接优先级在此校验，而非作为单独的 markdown 轴。',
  },
  {
    name: 'Spec',
    nameZh: 'spec',
    role: 'Weight 0.10',
    roleZh: '权重 0.10',
    description: 'Output-contract requirements compiled from the task. Any at-least-N-sources requirement lives in this hidden answer key spec, not in the prompt or a source-count quota.',
    descriptionZh: '从任务输出契约编译的要求。任何“至少 N 个来源”的要求都在隐藏答案键的 spec 轴，而非题面或来源数量配额。',
  },
  {
    name: 'Presentation',
    nameZh: '呈现质量',
    role: 'Tie-break only',
    roleZh: '仅平局裁决',
    description: 'An LLM panel scores presentation quality. It is a separate column used only to break ties when truth cannot separate two reports, and it can never overturn the truth ranking.',
    descriptionZh: '由 LLM 评审团为呈现质量打分。它是独立列，仅在 truth 无法区分两份报告时用于打破平局，永远不能推翻 truth 排序。',
  },
] as const

export default function PillarsPage() {
  const lb = loadLeaderboard()
  const agents = rankedAgents()
  const pillarNames = Object.keys(lb.pillar_elo ?? {})

  return (
    <>
      <PageHero
        eyebrow={<T en="Scoring Pillars" zh="评分维度" />}
        title={<T en="What the public score measures." zh="公开主分衡量什么。" />}
        intro={<T en="The live leaderboard is intentionally simple: the Arena score is reach^1.5 × jury win rate, where reach is judge-free citation reachability. The five decidable axes below are the implemented truth stack behind the truth column shown next to every run." zh="当前公开榜单刻意保持简单：Arena 主分 = 可达率^1.5 × 陪审团胜率,其中可达率是不依赖裁判的引用可达检查。下方五个可判定轴是每条运行旁真值分列背后的评分栈。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Public axes" zh="公开轴" />} value="2" detail={<T en="jury win rate and reach" zh="陪审团胜率与可达率" />} />
          <MetricCard label={<T en="Decidable axes" zh="可判定轴" />} value="5" detail={<T en="plus presentation as a tie-break column" zh="外加作为平局裁决列的呈现质量" />} />
          <MetricCard label={<T en="Weight draws" zh="权重抽样" />} value="2,000" detail={<T en="Dirichlet draws, 91.6% identical ranking" zh="Dirichlet 抽样,91.6% 排名完全一致" />} />
          <MetricCard label={<T en="Agents" zh="智能体" />} value={String(agents.length)} detail={<T en="ranked under the same scoring contract" zh="在同一评分契约下排名" />} />
        </div>
      </PageHero>

      <section className="container grid grid-cols-1 gap-4 lg:grid-cols-7">
        <div className="card p-6 lg:col-span-3">
          <span className="label-caps"><T en="Composite formula" zh="综合公式" /></span>
          <p className="mt-4 font-serif text-3xl leading-tight text-ink">
            arena = reach^1.5 × jury win rate
          </p>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            <T
              en="The gate is the mean of citation reachability and quote verification. Raw judge Elo remains visible, but it does not decide the public ranking by itself."
              zh="可达率是不依赖裁判的引用核验信号。陪审团 Elo 仍然公开展示，但它不会单独决定公开排名。"
            />
          </p>
        </div>
        <div className="card p-6 lg:col-span-4">
          <span className="label-caps"><T en="Leaders by public score" zh="按公开主分的领先者" /></span>
          <div className="mt-5 space-y-3">
            {agents.slice(0, 5).map((agent) => {
              const meta = agentMeta(agent.id)
              const score = truthScore(agent)
              const gate = groundingGatePct(agent)
              const topScore = truthScore(agents[0])
              return (
                <div key={agent.id}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="font-medium text-ink">{meta.display}</span>
                    <span className="tnum text-muted">{fmt(score)}{gate == null ? '' : ` · gate ${gate.toFixed(0)}%`}</span>
                  </div>
                  <div className="h-2 rounded-pill bg-surface-mid">
                    <div className="h-full rounded-pill" style={{ width: `${Math.min(100, (score / Math.max(1, topScore)) * 100)}%`, backgroundColor: meta.color }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <section className="container mt-4">
        <div className="card p-6">
          <span className="label-caps"><T en="Protocol v2 composite (rolling out)" zh="Protocol v2 综合（切换中）" /></span>
          <p className="mt-4 break-words font-serif text-2xl leading-tight text-ink">
            truth = reachability^1.5 × (0.35·fact support + 0.25·proof of fetch + 0.30·completeness + 0.10·spec)
          </p>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            <T
              en="The four quality axes have an epsilon=0.05 floor; reachability has no floor, so a zero-output or fabricated report is capped near the floor constant. This stack is implemented and externally calibrated (proof-of-fetch threshold 0.35; gamma checked by fabrication injection; 2,000 Dirichlet weight draws reproduce the identical ranking 91.6% of the time); the composed truth score is reported as its own column next to every run on the public board."
              zh="四个质量轴有 epsilon=0.05 地板；reachability 无地板，零产出或编造报告的得分被压到地板常数附近。该评分栈已实现并完成外部校准（抓取证明阈值 0.35；γ 经注入编造检验；2,000 组 Dirichlet 权重抽样中 91.6% 复现完全相同排名）；复合出的真值分作为独立列展示在公开榜每条运行旁。"
            />
          </p>
        </div>
      </section>

      <section className="container mt-10 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {AXES.map((axis) => (
          <article key={axis.name} className="card card-lift p-6">
            <span className="label-caps"><T en={axis.role} zh={axis.roleZh} /></span>
            <h2 className="mt-3 font-serif text-h-sm text-ink"><T en={axis.name} zh={axis.nameZh} /></h2>
            <p className="mt-2 text-sm leading-relaxed text-muted"><T en={axis.description} zh={axis.descriptionZh} /></p>
          </article>
        ))}
      </section>

      <section className="container mt-10">
        <div className="card p-6">
          <span className="label-caps"><T en="Contradiction pillar (adjudicated)" zh="矛盾支柱（已裁决）" /></span>
          <h2 className="mt-3 font-serif text-h-sm text-ink"><T en="Adjudicated numeric conflicts in the frozen corpus" zh="冻结语料中经裁决的数值矛盾" /></h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            <T
              en="Round 1 (marketing numbers vs frozen-wiki ceilings): 95 candidates; human adjudication rejected all 3 auto-extracted ceiling references, so gold = 0, an informative negative. Round 2 (intra-page self-contradictions, e.g. one page stating two Bluetooth versions): 90 mined candidates, a local 8B prescreen flagged 23, strong-model adjudication confirmed 11, now attached to 24 tasks as semi-decidable checks. Nothing machine-mined is promoted unreviewed; per-entry rationales ship with the adjudication files."
              zh="第一轮（营销数字对比冻结 wiki 上限）：95 个候选，人工裁决否决了全部 3 条自动抽取的上限引用，gold = 0，是有信息量的阴性结果。第二轮（页内自相矛盾，如同一页面写出两个蓝牙版本）：挖出 90 个候选，本地 8B 初筛标记 23 条，强模型逐条裁决确认 11 条，现已挂接到 24 个任务作为半可判定检查项。机器挖掘的内容一律不经复核不晋升；裁决文件附逐条理由。"
            />
          </p>
        </div>
      </section>

      {pillarNames.length > 0 ? (
        <section className="container mt-10">
          <div className="card p-6">
            <span className="label-caps"><T en="Available pillar Elo tables" zh="可用的分维度 Elo 表" /></span>
            <div className="mt-4 flex flex-wrap gap-2">
              {pillarNames.map((name) => (
                <span key={name} className="pill capitalize">{name.replaceAll('_', ' ')}</span>
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </>
  )
}
