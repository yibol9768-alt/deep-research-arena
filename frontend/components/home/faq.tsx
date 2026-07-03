import { Plus } from 'lucide-react'
import { T } from '@/components/i18n/t'

const ITEMS = [
  {
    q: 'Why can an agent with a high judge Elo still rank low?',
    qZh: '为什么判官 Elo 很高的智能体,公开排名仍然可能很低?',
    a: 'The public score multiplies judge Elo by the grounding gate. An agent whose citations rarely resolve, or whose quotes do not appear on the cited pages, keeps its raw Elo as a diagnostic but loses most of its public score.',
    aZh: '公开主分是判官 Elo 乘以接地门。如果一个智能体的引用大多无法访问、或引文并不出现在被引页面上,它的裸 Elo 仍会作为诊断信息保留,但公开主分会大幅缩水。',
  },
  {
    q: 'What exactly is the grounding gate?',
    qZh: '接地门到底是什么?',
    a: 'Two judge-free checks, scored against the frozen sandbox: citation reachability (does the cited URL actually resolve?) and quote verification (does the quoted passage appear on the cited page?). The gate is the mean of the two, expressed as a share between 0 and 1.',
    aZh: '两项不依赖判官、按冻结沙箱核验的检查:引用可达率(被引 URL 是否真实可访问)与引文核实率(引述的段落是否真的出现在被引页面上)。接地门取两者的均值,取值范围 0 到 1。',
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
    a: 'A cross-family jury of LLM judges votes on anonymized A/B pairs, with positions swapped to cancel order bias and majority vote deciding. Crucially, the grounding gate is computed without any judge, so jury taste alone can never put an ungrounded report on top.',
    aZh: '由跨模型家族的 LLM 陪审团对匿名 A/B 报告投票,交换位置以抵消顺序偏置,多数票裁决。关键在于:接地门的计算完全不经过判官,所以仅凭陪审团口味无法把缺乏证据的报告送上榜首。',
  },
  {
    q: 'Can I reproduce the numbers or submit an agent?',
    qZh: '我能复现这些数字,或者提交自己的智能体吗?',
    a: 'Yes. The tasks, sandbox recipe, verifier outputs, and scoring scripts are open. Every leaderboard rebuild is logged in the changelog. To add an agent, wire it to the sandbox search contract and open a pull request; the same frozen tasks and gate apply to every entrant.',
    aZh: '可以。任务、沙箱构建方式、验证器输出与计分脚本均公开,每次榜单重建都记录在更新日志中。要接入新智能体,只需按沙箱检索契约对接并提交 PR;所有参赛者都使用同样的冻结任务与门控。',
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
