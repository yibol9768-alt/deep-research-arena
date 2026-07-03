import Link from 'next/link'
import { Github } from 'lucide-react'
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
    <footer className="mt-24 border-t border-hairline bg-white">
      <div className="container py-14">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-12">
          {/* Brand */}
          <div className="md:col-span-5">
            <h3 className="font-serif text-3xl leading-none text-ink">
              Deep Research Arena
            </h3>
            <p className="mt-4 max-w-sm text-sm leading-relaxed text-muted">
              <T
                en="A reproducible benchmark for deep-research agents: frozen tasks, auditable reports, jury decisions, and judge-free citation checks."
                zh="一项可复现的深度研究智能体基准：冻结任务、可审计报告、陪审团裁决与不依赖判官的引用核验。"
              />
            </p>
            <div className="mt-5 flex gap-3">
              <a
                href="https://github.com/yibol9768-alt/deep-research-arena"
                aria-label="GitHub"
                className="flex h-9 w-9 items-center justify-center rounded-pill border border-hairline text-muted transition-colors hover:border-ink/30 hover:text-ink"
              >
                <Github className="h-4 w-4" />
              </a>
            </div>
          </div>

          {/* Link columns */}
          {COLS.map((col) => (
            <div key={col.title} className="md:col-span-2">
              <h4 className="text-caps uppercase tracking-wider text-muted-2">
                <T en={col.title} zh={col.titleZh} />
              </h4>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link
                      href={l.href}
                      className="text-sm text-muted transition-colors hover:text-ink hover:underline underline-offset-4"
                    >
                      <T en={l.label} zh={l.zh} />
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col items-start justify-between gap-3 border-t border-hairline pt-6 text-xs text-muted-2 md:flex-row md:items-center">
          <p>© {new Date().getFullYear()} Deep Research Arena. <T en="Trademarks belong to their owners." zh="商标归各自所有者所有。" /></p>
          <p className="tnum">
            {lastUpdated ? (
              <>
                <T en="Last leaderboard rebuild:" zh="上次排行榜重建:" />{' '}
                <span className="font-medium text-muted">{lastUpdated}</span>
              </>
            ) : null}
          </p>
        </div>
      </div>
    </footer>
  )
}
