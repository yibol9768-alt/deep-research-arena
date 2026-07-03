import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { loadChangelog } from '@/lib/data/changelog'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

export const metadata = {
  title: 'Changelog — Deep Research Arena',
  description: 'A log of meaningful changes to the Deep Research Arena benchmark, scoring system, and site.',
}

export default function ChangelogPage() {
  const { entries } = loadChangelog()
  const latest = entries[0]
  const versionCount = entries.length
  const latestDate = latest?.date ?? '—'

  return (
    <>
      <PageHero
        eyebrow={<T en="Changelog" zh="更新日志" />}
        title={<T en="Release history." zh="更新记录。" />}
        intro={
          <T
            en="Every meaningful update to the arena — scoring, tasks, sandbox enforcement, the site — lands here before it ships. Newest entries first."
            zh="对竞技场的每一次有意义的更新，包括评分、任务、沙箱约束、网站，都会在上线前记录在这里。最新条目排在最前。"
          />
        }
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Releases" zh="发布版本" />} value={String(versionCount)} detail={<T en="logged updates" zh="已记录的更新" />} />
          <MetricCard label={<T en="Latest" zh="最新" />} value={latestDate} detail={latest?.title ?? <T en="no entries yet" zh="暂无条目" />} />
          <MetricCard label={<T en="Format" zh="格式" />} value="v1" detail="data/changelog.json" />
          <MetricCard label={<T en="Source" zh="来源" />} value="GitHub" detail="yibol9768-alt/deep-research-arena" />
        </div>
      </PageHero>

      <section className="container space-y-12 pb-20">
        {entries.length === 0 ? (
          <p className="text-muted"><T en="No entries yet." zh="暂无条目。" /></p>
        ) : (
          entries.map((entry) => (
            <article key={entry.version} className="card p-6 md:p-8">
              <header className="flex flex-wrap items-baseline gap-x-4 gap-y-2 border-b border-hairline pb-4">
                <span className="label-caps">{entry.version}</span>
                <h2 className="font-serif text-2xl text-ink md:text-3xl">{entry.title}</h2>
                <span className="ml-auto text-sm text-muted tnum">{entry.date}</span>
              </header>

              {entry.tags && entry.tags.length > 0 ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {entry.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-pill bg-surface-low px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider text-muted"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              ) : null}

              <p className="mt-4 max-w-3xl text-base leading-relaxed text-ink/90">{entry.summary}</p>

              <div className="mt-8 space-y-6">
                {entry.sections.map((section) => (
                  <section key={section.heading}>
                    <h3 className="font-serif text-lg text-ink">{section.heading}</h3>
                    <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-ink/85">
                      {section.bullets.map((bullet, i) => (
                        <li key={i}>{bullet}</li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>

              {entry.links && entry.links.length > 0 ? (
                <footer className="mt-8 flex flex-wrap gap-x-5 gap-y-2 border-t border-hairline pt-4 text-sm">
                  {entry.links.map((link) => (
                    <a key={link.href} href={link.href} className="text-muted hover:text-ink">
                      {link.label} &rarr;
                    </a>
                  ))}
                </footer>
              ) : null}
            </article>
          ))
        )}
      </section>
    </>
  )
}
