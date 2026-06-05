import Link from 'next/link'
import { Github } from 'lucide-react'
import { T } from '@/components/i18n/t'

const COLS: { title: string; titleZh: string; links: { href: string; label: string; zh: string }[] }[] = [
  {
    title: 'Explore',
    titleZh: '探索',
    links: [
      { href: '/', label: 'Leaderboard', zh: '排行榜' },
      { href: '/agents', label: 'Agents', zh: '智能体' },
      { href: '/tasks', label: 'Tasks', zh: '任务' },
      { href: '/pillars', label: 'Pillars', zh: '评测维度' },
      { href: '/arena', label: 'Live Arena', zh: '实时竞技场' },
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
      { href: '/methodology', label: 'Paper notes', zh: '论文笔记' },
      { href: 'https://github.com/yibol9768-alt/deep-research-arena', label: 'GitHub', zh: 'GitHub' },
      { href: '/changelog', label: 'Changelog', zh: '更新日志' },
    ],
  },
]

export function SiteFooter({ lastUpdated }: { lastUpdated?: string }) {
  return (
    <footer className="mt-24 bg-brand-footer text-brand-dark">
      <div className="container py-14">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-12">
          {/* Brand + newsletter */}
          <div className="md:col-span-5">
            <h3 className="font-serif text-4xl leading-none">
              Deep Research<br />Arena
            </h3>
            <p className="mt-4 max-w-sm text-sm text-brand-dark/80">
              <T
                en="The first reproducible Elo benchmark for Deep Research agents. Open source. Open data. Open methodology."
                zh="首个可复现的 Deep Research 智能体 Elo 评测基准。开源、开放数据、开放方法论。"
              />
            </p>
          </div>

          {/* Link columns */}
          {COLS.map((col) => (
            <div key={col.title} className="md:col-span-2">
              <h4 className="text-caps uppercase tracking-wider text-brand-dark/70"><T en={col.title} zh={col.titleZh} /></h4>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link
                      href={l.href}
                      className="text-sm text-brand-dark/90 transition-colors hover:text-brand-dark hover:underline underline-offset-4"
                    >
                      <T en={l.label} zh={l.zh} />
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {/* Socials */}
          <div className="md:col-span-1">
            <h4 className="text-caps uppercase tracking-wider text-brand-dark/70"><T en="Follow" zh="关注" /></h4>
            <div className="mt-4 flex gap-3">
              <a href="https://github.com/yibol9768-alt/deep-research-arena" aria-label="GitHub" className="text-brand-dark/80 hover:text-brand-dark"><Github className="h-4 w-4" /></a>
            </div>
          </div>
        </div>

        <div className="mt-12 flex flex-col items-start justify-between gap-3 border-t border-brand-dark/15 pt-6 text-xs text-brand-dark/70 md:flex-row md:items-center">
          <p>© {new Date().getFullYear()} Deep Research Arena. <T en="Trademarks belong to their owners." zh="商标归各自所有者所有。" /></p>
          <p className="tnum">
            {lastUpdated ? <><T en="Last leaderboard rebuild:" zh="上次排行榜重建:" /> <span className="font-medium text-brand-dark">{lastUpdated}</span></> : null}
          </p>
        </div>
      </div>
    </footer>
  )
}
