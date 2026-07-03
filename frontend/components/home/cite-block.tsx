import Link from 'next/link'
import { Github, BookOpen, History } from 'lucide-react'
import { T } from '@/components/i18n/t'

const BIBTEX = `@misc{deepresearcharena2026,
  title = {Deep Research Arena},
  year  = {2026},
  note  = {Reproducible truth-gated Elo benchmark
           for Deep Research agents},
  url   = {https://www.deepresearcharena.com}
}`

export function CiteBlock() {
  return (
    <div id="cite" className="card overflow-hidden">
      <div className="grid grid-cols-1 lg:grid-cols-2">
        <div className="p-7 md:p-8">
          <span className="label-caps"><T en="Use the benchmark" zh="使用本基准" /></span>
          <h2 className="mt-3 font-serif text-h-sm text-ink md:text-h-md">
            <T en="Open data, open scoring, citable snapshots." zh="开放数据、开放计分、可引用的快照。" />
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            <T
              en="Task set, sandbox recipe, verifier outputs, jury decisions, and scoring scripts are public. Every rebuild of the board is versioned in the changelog, so a citation pins an exact snapshot."
              zh="任务集、沙箱构建方式、验证器输出、陪审团裁决与计分脚本全部公开。榜单的每次重建都在更新日志中留有版本记录,因此引用即锁定一个确切快照。"
            />
          </p>
          <div className="mt-6 flex flex-wrap gap-2.5">
            <a
              href="https://github.com/yibol9768-alt/deep-research-arena"
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-10 items-center gap-2 rounded-pill bg-ink px-4 text-sm font-medium text-white transition-colors hover:bg-ink-soft"
            >
              <Github className="h-4 w-4" />
              GitHub
            </a>
            <Link
              href="/methodology"
              className="inline-flex h-10 items-center gap-2 rounded-pill border border-hairline bg-white px-4 text-sm font-medium text-ink transition-all hover:border-ink/30 hover:shadow-soft"
            >
              <BookOpen className="h-4 w-4" />
              <T en="Methodology" zh="方法论" />
            </Link>
            <Link
              href="/changelog"
              className="inline-flex h-10 items-center gap-2 rounded-pill border border-hairline bg-white px-4 text-sm font-medium text-ink transition-all hover:border-ink/30 hover:shadow-soft"
            >
              <History className="h-4 w-4" />
              <T en="Changelog" zh="更新日志" />
            </Link>
          </div>
        </div>
        <div className="flex items-center bg-night p-7 md:p-8">
          <pre className="w-full overflow-x-auto rounded-xl border border-night-line bg-black/30 p-5 font-mono text-xs leading-relaxed text-night-mist">
            {BIBTEX}
          </pre>
        </div>
      </div>
    </div>
  )
}
