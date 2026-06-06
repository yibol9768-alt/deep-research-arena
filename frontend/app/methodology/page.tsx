import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

const SECTIONS = [
  {
    id: 'composite',
    title: 'Truth-gated Elo',
    titleZh: '真值门控 Elo',
    body: 'The headline score is the pairwise judge Elo multiplied by the grounding gate (mean of citation reachability and quote verification), so unsupported reports cannot win on fluency alone.',
    bodyZh: '榜单主分 = 成对判官 Elo × 接地门（引用可达率与引文核实率的均值），缺乏支撑的报告无法仅凭文采取胜。',
  },
  {
    id: 'grounding-gate',
    title: 'Grounding gate',
    titleZh: '接地门控',
    body: 'Reachable, markdown-linked sandbox URLs are treated as evidence. Missing or fabricated citations reduce the effective score multiplicatively.',
    bodyZh: '可访问且以 markdown 链接呈现的沙箱 URL 被视为证据。缺失或捏造的引用会以乘性方式降低有效得分。',
  },
  {
    id: 'bradley-terry',
    title: 'Bradley-Terry Elo',
    titleZh: 'Bradley-Terry Elo',
    body: 'Per-task outcomes become pairwise battles. MLE estimates agent strength, and bootstrap resampling gives 95% confidence intervals.',
    bodyZh: '逐任务的结果转化为两两对战。由极大似然估计智能体强度，并通过自助重采样给出 95% 置信区间。',
  },
  {
    id: 'dual-judge',
    title: 'Judge and its limits',
    titleZh: '判官及其局限',
    body: 'Current jury: a 3-judge cross-family PoLL jury (deepseek-v4-flash, qwen3-max, glm-5; arXiv 2404.18796). Every battle is judged by all three, position-debiased (each side swapped), and decided by majority vote. The cross-family jury directly addresses judge self-preference (most agents run on deepseek-v4-flash), and the headline score is still gated by the judge-free grounding check. All 1,553 battles have all three jurors voting; the jury tie rate is 16.9% (down from 50.6% under a single judge).',
    bodyZh: '当前判官：三判官跨家族 PoLL 陪审团（deepseek-v4-flash、qwen3-max、glm-5;arXiv 2404.18796）。每场对战由三家各自评判,位置去偏(交换位次),多数票定胜负。跨家族陪审团直接缓解判官自偏好(多数智能体运行在 deepseek-v4-flash 上),且榜单主分仍乘以不依赖判官的接地门。全部 1,553 场三判官皆投票;陪审团平局率 16.9%(单判官时为 50.6%)。',
  },
  {
    id: 'intent-typology',
    title: 'Intent typology',
    titleZh: '意图类型',
    body: 'Tasks span recommendation, comparison, debunking, causal explanation, timeline, and enumeration. Each intent has task-specific checklists.',
    bodyZh: '任务涵盖推荐、对比、辟谣、因果解释、时间线与枚举等类型。每种意图都配有针对具体任务的核查清单。',
  },
  {
    id: 'ablation',
    title: 'Ablation protocol',
    titleZh: '消融协议',
    body: 'Dropping pillars reveals sensitivity. Truth and citation gates are the highest-impact controls against fluent hallucination.',
    bodyZh: '剔除维度可揭示敏感性。真值门控与引用门控是对抗流畅幻觉影响最大的控制项。',
  },
] as const

export default function MethodologyPage() {
  return (
    <>
      <PageHero
        eyebrow={<T en="Methodology" zh="方法论" />}
        title={<T en="A reproducible scoring stack for reports that cite, synthesize, and survive audit." zh="一套可复现的评分体系，用于评判会引用、能综合且经得起审计的报告。" />}
        intro={<T en="Deep Research Arena avoids a single magic score. It stores the task, source pool, checklist, report, verifier outputs, pairwise outcome, and confidence interval as separate artifacts." zh="Deep Research Arena 不依赖单一的魔法分数。它将任务、来源池、核查清单、报告、验证器输出、两两对战结果与置信区间分别存为独立的产物。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Score axes" zh="评分轴" />} value="2" detail={<T en="grounding (judge-free) and judge Elo" zh="接地（不依赖判官）与判官 Elo" />} />
          <MetricCard label={<T en="Bootstrap" zh="自助重采样" />} value="1000" detail={<T en="confidence interval resamples" zh="置信区间重采样次数" />} />
          <MetricCard label={<T en="Intent classes" zh="意图类别" />} value="6" detail={<T en="task families with separate failure modes" zh="具有不同失败模式的任务族" />} />
          <MetricCard label={<T en="Audit trail" zh="审计轨迹" />} value="Full" detail={<T en="JSON, reports, and verifier outputs" zh="JSON、报告与验证器输出" />} />
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
          </nav>
        </aside>
        <div className="space-y-5">
          {SECTIONS.map((section, i) => (
            <article key={section.id} id={section.id} className="card scroll-mt-24 p-7">
              <span className="label-caps"><T en={`Step ${i + 1}`} zh={`步骤 ${i + 1}`} /></span>
              <h2 className="mt-3 font-serif text-h-sm text-ink md:text-h-md"><T en={section.title} zh={section.titleZh} /></h2>
              <p className="mt-3 text-sm leading-relaxed text-muted"><T en={section.body} zh={section.bodyZh} /></p>
              <div className="mt-6 rounded-tab bg-surface-low p-4 font-mono text-xs leading-relaxed text-muted">
                {'report -> verifiers -> per-task battle -> Bradley-Terry MLE -> bootstrap CI -> leaderboard'}
              </div>
            </article>
          ))}
        </div>
      </section>
    </>
  )
}
