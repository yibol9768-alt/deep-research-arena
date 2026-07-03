import { Server, FileText, Scale, ShieldCheck, ArrowRight } from 'lucide-react'
import Link from 'next/link'
import { T } from '@/components/i18n/t'

const STEPS = [
  {
    icon: Server,
    title: 'Frozen sandbox',
    titleZh: '冻结沙箱',
    body: 'Every agent browses the same offline corpus. Every fetch is logged, so "I read this page" is a checkable claim, not an anecdote.',
    bodyZh: '所有智能体浏览同一套离线语料。每次抓取都有日志，"我读过这个页面"是可核查的声明，而非口说无凭。',
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
    body: 'Independently of the jury, every cited URL is re-fetched and every quote is matched against the cited page. Elo × gate = the public score.',
    bodyZh: '在陪审团之外，每个引用 URL 都被重新抓取，每段引文都与被引页面比对。Elo × 接地门 = 公开主分。',
  },
] as const

export function PipelineBand() {
  return (
    <section id="how-it-works" className="section-night relative overflow-hidden py-16 text-white md:py-20">
      <div aria-hidden className="night-grid pointer-events-none absolute inset-0 opacity-70" />

      <div className="container relative">
        <div className="flex flex-col items-start justify-between gap-4 md:flex-row md:items-end">
          <div>
            <span className="label-caps text-night-faint"><T en="How it works" zh="评测流程" /></span>
            <h2 className="mt-3 max-w-xl font-serif text-h-md leading-tight md:text-display-lg">
              <T en="One frozen world. Four checkpoints. No exceptions." zh="一个冻结世界,四道关卡,没有例外。" />
            </h2>
          </div>
          <Link
            href="/methodology"
            className="inline-flex h-10 shrink-0 items-center gap-2 rounded-pill border border-night-line bg-white/5 px-4 text-sm font-medium text-white transition-colors hover:border-white/30 hover:bg-white/10"
          >
            <T en="Full methodology" zh="完整方法论" />
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>

        <ol className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <li key={s.title} className="glass-card relative p-6">
              <span className="absolute right-5 top-5 font-serif text-3xl text-white/10 tnum">0{i + 1}</span>
              <s.icon className="h-5 w-5 text-brand-glow" strokeWidth={1.8} />
              <h3 className="mt-4 text-base font-semibold tracking-tight">
                <T en={s.title} zh={s.titleZh} />
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-night-mist">
                <T en={s.body} zh={s.bodyZh} />
              </p>
            </li>
          ))}
        </ol>

        <div className="mt-8 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border border-night-line bg-black/25 px-5 py-4 font-mono text-xs text-night-mist md:text-sm">
          <span className="text-night-faint"><T en="public score" zh="公开主分" /></span>
          <span>=</span>
          <span className="text-white">judge&nbsp;Elo</span>
          <span>×</span>
          <span className="text-white">(reachability&nbsp;+&nbsp;quote&nbsp;match)&nbsp;/&nbsp;2</span>
          <span className="ml-auto hidden text-night-faint md:inline">
            <T en="judge-free gate · computed against the frozen sandbox" zh="不依赖判官的门控 · 按冻结沙箱核验" />
          </span>
        </div>
      </div>
    </section>
  )
}
