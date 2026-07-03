import Link from 'next/link'
import { Github, Activity } from 'lucide-react'
import { T } from '@/components/i18n/t'

const COLS: { title: string; titleZh: string; links: { href: string; label: string; zh: string }[] }[] = [
  {
    title: 'Explore',
    titleZh: '探索',
    links: [
      { href: '/', label: 'Leaderboard', zh: '排行榜' },
      { href: '/models', label: 'Models', zh: '模型榜' },
      { href: '/agents', label: 'Agents', zh: '智能体' },
      { href: '/tasks', label: 'Tasks', zh: '任务' },
      { href: '/arena', label: 'Arena', zh: '竞技场' },
    ],
  },
  {
    title: 'Project',
    titleZh: '项目',
    links: [
      { href: '/methodology', label: 'Methodology', zh: '方法论' },
      { href: '/sandbox', label: 'Sandbox', zh: '沙箱' },
      { href: '/insights', label: 'Findings', zh: '研究发现' },
      { href: '/about', label: 'About', zh: '关于' },
      { href: '/contribute', label: 'Contribute', zh: '贡献' },
    ],
  },
  {
    title: 'Resources',
    titleZh: '资源',
    links: [
      { href: 'https://github.com/yibol9768-alt/deep-research-arena', label: 'GitHub', zh: 'GitHub' },
      { href: '/status', label: 'Benchmark Status', zh: '基准状态' },
      { href: '/changelog', label: 'Changelog', zh: '更新日志' },
      { href: '/annotate', label: 'Annotate', zh: '标注' },
    ],
  },
]

export function SiteFooter({ lastUpdated }: { lastUpdated?: string }) {
  return (
    <footer className="section-night relative mt-24 overflow-hidden text-white">
      {/* glow divider on top */}
      <div className="night-divider-glow absolute inset-x-0 top-0 h-px" />
      <div aria-hidden className="night-grid pointer-events-none absolute inset-0 opacity-60" />

      <div className="container relative py-16">
        <div className="grid grid-cols-1 gap-12 md:grid-cols-12">
          {/* Brand */}
          <div className="md:col-span-5">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-[9px] bg-gradient-to-br from-brand to-brand-glow">
                <Activity className="h-4 w-4 text-white" strokeWidth={2.5} />
              </span>
              <span className="font-serif text-2xl">Deep Research Arena</span>
            </div>
            <p className="mt-5 max-w-sm text-sm leading-relaxed text-night-mist">
              <T
                en="A reproducible benchmark for deep-research agents: frozen tasks, auditable reports, jury decisions, and judge-free citation checks. Fluency is not grounding."
                zh="一项可复现的深度研究智能体基准：冻结任务、可审计报告、陪审团裁决与不依赖判官的引用核验。流畅不等于接地。"
              />
            </p>
            <div className="mt-6 flex gap-3">
              <a
                href="https://github.com/yibol9768-alt/deep-research-arena"
                aria-label="GitHub"
                className="flex h-9 w-9 items-center justify-center rounded-full border border-night-line text-white/70 transition-colors hover:border-white/30 hover:text-white"
              >
                <Github className="h-4 w-4" />
              </a>
            </div>
          </div>

          {/* Link columns */}
          {COLS.map((col) => (
            <div key={col.title} className="md:col-span-2">
              <h4 className="text-caps uppercase tracking-wider text-night-faint">
                <T en={col.title} zh={col.titleZh} />
              </h4>
              <ul className="mt-5 space-y-3">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link
                      href={l.href}
                      className="text-sm text-night-mist transition-colors hover:text-white"
                    >
                      <T en={l.label} zh={l.zh} />
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-14 flex flex-col items-start justify-between gap-3 border-t border-night-line pt-6 text-xs text-night-faint md:flex-row md:items-center">
          <p>© {new Date().getFullYear()} Deep Research Arena. <T en="Trademarks belong to their owners." zh="商标归各自所有者所有。" /></p>
          <p className="tnum">
            {lastUpdated ? (
              <>
                <T en="Last leaderboard rebuild:" zh="上次排行榜重建:" />{' '}
                <span className="font-medium text-night-mist">{lastUpdated}</span>
              </>
            ) : null}
          </p>
        </div>
      </div>
    </footer>
  )
}
