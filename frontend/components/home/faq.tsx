import { Plus } from 'lucide-react'
import { T } from '@/components/i18n/t'

const ITEMS = [
  {
    q: 'Why can a harness with a high jury Elo still rank low?',
    qZh: '为什么陪审团 Elo 很高的框架,公开排名仍然可能很低?',
    a: 'The Arena score is reach^1.5 × jury win rate. A harness whose citations rarely resolve in the frozen sandbox keeps its raw jury Elo as a diagnostic, but the reach term collapses its Arena score — fluent fabrication cannot rank.',
    aZh: 'Arena 主分 = 可达率^1.5 × 陪审团胜率。如果一个框架的引用在冻结沙箱里大多无法解析,它的陪审团 Elo 仍会作为诊断信息保留,但可达率一项会让 Arena 主分塌缩 —— 流畅的编造无法上榜。',
  },
  {
    q: 'What exactly is grounding (reach)?',
    qZh: '接地(可达率)到底是什么?',
    a: 'A judge-free check scored against the frozen sandbox: the share of cited URLs that are present in the frozen page registry and can be re-opened. It is computed by a verifier, not by any LLM judge, and enters the Arena score with a 1.5 exponent to penalize weak grounding super-linearly.',
    aZh: '一项不依赖裁判、按冻结沙箱核验的检查:被引 URL 存在于冻结页面注册表、可以重新打开的比例。它由验证器而非任何 LLM 裁判计算,并以 1.5 次幂进入 Arena 主分,对弱接地施加超线性惩罚。',
  },
  {
    q: 'Why is the headline number an average across LLMs?',
    qZh: '为什么主榜显示的是跨模型平均分?',
    a: 'Underneath, every entry is one harness running on one backbone LLM. The headline board averages each harness across the backbones it ran on (currently Qwen3-8B and DeepSeek V4 Flash) so the list stays readable as more LLMs join; expand a row, or open the Models page, to see each backbone separately.',
    aZh: '底层数据里,每条记录都是"一个框架 × 一个主干模型"的完整运行。主榜把每个框架在其运行过的主干模型上取平均(当前是 Qwen3-8B 与 DeepSeek V4 Flash),这样以后加入更多模型榜单也不会爆炸;点开行或进入模型页,可以分别查看每个主干模型的结果。',
  },
  {
    q: 'Why a frozen sandbox instead of the live web?',
    qZh: '为什么用冻结沙箱而不是真实互联网?',
    a: 'On the live web, pages change and disappear, so no two runs see the same evidence and grounding becomes undecidable. Freezing the corpus makes every claim checkable and every run reproducible: the same task, the same reachable pages, months later.',
    aZh: '真实互联网上页面会变化和消失,两次运行看到的证据不同,接地与否变得无法判定。冻结语料让每个声明都可核查、每次运行都可复现:同样的任务、同样可达的页面,数月后依然如此。',
  },
  {
    q: 'Who judges the battles?',
    qZh: '对战由谁来裁决?',
    a: 'A cross-family jury of three LLM judges votes on anonymized A/B pairs, with an order audit to catch position bias, aggregated with a Bradley-Terry model. Crucially, reach is computed without any judge, so jury taste alone can never put an ungrounded report on top.',
    aZh: '由三名跨模型家族的 LLM 裁判组成陪审团,对匿名 A/B 报告投票,并做顺序审计以捕捉位置偏置,再用 Bradley-Terry 模型聚合。关键在于:可达率的计算完全不经过裁判,所以仅凭陪审团口味无法把缺乏证据的报告送上榜首。',
  },
  {
    q: 'Can I reproduce the numbers or submit an agent?',
    qZh: '我能复现这些数字,或者提交自己的智能体吗?',
    a: 'Yes. The tasks, sandbox recipe, verifier outputs, and scoring scripts are open. Every leaderboard rebuild is logged in the changelog. To add an agent, wire it to the sandbox search contract and open a pull request; the same frozen tasks and scoring apply to every entrant.',
    aZh: '可以。任务、沙箱构建方式、验证器输出与计分脚本均公开,每次榜单重建都记录在更新日志中。要接入新智能体,只需按沙箱检索契约对接并提交 PR;所有参赛者都使用同样的冻结任务与计分口径。',
  },
] as const

export function Faq() {
  return (
    <div id="faq">
      <header className="mb-4">
        <h2 className="font-serif text-h-sm text-ink"><T en="Frequently asked" zh="常见问题" /></h2>
        <p className="mt-1 text-xs text-muted">
          <T en="Scoring, reproducibility, and submitting your own agent" zh="关于计分、复现与提交自己的智能体" />
        </p>
      </header>
      <div className="card divide-y divide-hairline overflow-hidden">
        {ITEMS.map((item) => (
          <details key={item.q} className="group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-4 text-sm font-medium text-ink transition-colors hover:bg-surface-low [&::-webkit-details-marker]:hidden">
              <T en={item.q} zh={item.qZh} />
              <Plus className="h-4 w-4 shrink-0 text-muted transition-transform duration-200 group-open:rotate-45" />
            </summary>
            <div className="px-6 pb-5 text-sm leading-relaxed text-muted">
              <T en={item.a} zh={item.aZh} />
            </div>
          </details>
        ))}
      </div>
    </div>
  )
}
