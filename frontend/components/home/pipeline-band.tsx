import { Server, FileText, Scale, ShieldCheck, ArrowRight } from 'lucide-react'
import Link from 'next/link'
import { T } from '@/components/i18n/t'

const STEPS = [
  {
    icon: Server,
    title: 'Frozen sandbox',
    titleZh: '冻结沙箱',
    body: 'Every agent browses the same offline corpus of a shopping site, a forum, and an offline Wikipedia. Every fetch is logged.',
    bodyZh: '所有智能体浏览同一套离线语料:购物站、论坛和离线维基百科。每次抓取都有日志。',
  },
  {
    icon: FileText,
    title: 'Identical briefs',
    titleZh: '同题作答',
    body: 'Each agent receives the same task brief and returns a cited research report. Reports and citations are archived verbatim.',
    bodyZh: '每个智能体拿到相同的任务简报，交回带引用的研究报告。报告与引用原样归档。',
  },
  {
    icon: Scale,
    title: 'Jury battles',
    titleZh: '陪审团对战',
    body: 'Reports meet in anonymized A/B battles. A cross-family jury votes with positions swapped to cancel order bias; majority decides.',
    bodyZh: '报告以匿名 A/B 形式对战。跨模型家族的陪审团在交换位置后投票以抵消顺序偏置，多数票裁决。',
  },
  {
    icon: ShieldCheck,
    title: 'Truth gate',
    titleZh: '真值门控',
    body: 'Independently of the jury, every cited URL is checked for membership in the frozen page registry (no network fetch), and every quote is matched against the archived page. Elo × gate = the public score.',
    bodyZh: '在陪审团之外，每个引用 URL 都在冻结页面注册表中做成员查询（不发任何网络请求），每段引文都与归档页面比对。Elo × 接地门 = 公开主分。',
  },
] as const

export function PipelineBand() {
  return (
    <div id="how-it-works" className="scroll-mt-24">
      <header className="mb-4 flex flex-col items-start justify-between gap-3 md:flex-row md:items-end">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="aa-square" />
            <h2 className="font-serif text-h-sm text-ink"><T en="How it works" zh="评测流程" /></h2>
          </div>
          <p className="mt-1 text-xs text-muted">
            <T en="From task brief to public score in four steps" zh="从任务简报到公开主分的四个步骤" />
          </p>
        </div>
        <Link
          href="/methodology"
          className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-pill border border-hairline bg-white px-4 text-sm font-medium text-ink transition-all hover:border-ink/30 hover:bg-surface-low"
        >
          <T en="Full methodology" zh="完整方法论" />
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </header>

      <ol className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((s, i) => (
          <li key={s.title} className="card card-lift relative p-5">
            <span className="absolute right-4 top-4 font-serif text-2xl text-hairline tnum">0{i + 1}</span>
            <s.icon className="h-5 w-5 text-brand" strokeWidth={1.8} />
            <h3 className="mt-3.5 text-sm font-semibold tracking-tight text-ink">
              <T en={s.title} zh={s.titleZh} />
            </h3>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">
              <T en={s.body} zh={s.bodyZh} />
            </p>
          </li>
        ))}
      </ol>

      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-card border border-hairline bg-surface-low px-5 py-3.5 font-mono text-xs text-muted md:text-sm">
        <span className="text-muted-2"><T en="public score" zh="公开主分" /></span>
        <span>=</span>
        <span className="font-semibold text-ink">judge&nbsp;Elo</span>
        <span>×</span>
        <span className="font-semibold text-ink">(reachability&nbsp;+&nbsp;quote&nbsp;match)&nbsp;/&nbsp;2</span>
        <span className="ml-auto hidden text-muted-2 md:inline">
          <T en="judge-free gate · computed against the frozen sandbox" zh="不依赖判官的门控 · 按冻结沙箱核验" />
        </span>
      </div>
    </div>
  )
}
