import type { ReactNode } from 'react'
import { loadArenaV2, backboneShort } from '@/lib/data/load-arena-v2'
import { loadChangelog } from '@/lib/data/changelog'
import { agentMeta } from '@/lib/providers'
import { fmt } from '@/lib/format'
import { Hero } from '@/components/home/hero'
import { ArenaTable } from '@/components/home/arena-table'
import { SectionNav } from '@/components/home/section-nav'
import { PipelineBand } from '@/components/home/pipeline-band'
import { VBarChart, type VBarRow } from '@/components/home/vbar-chart'
import { Faq } from '@/components/home/faq'
import { CiteBlock } from '@/components/home/cite-block'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

export default function HomePage() {
  const arena = loadArenaV2()
  const news = loadChangelog().entries.slice(0, 3)

  if (!arena) {
    return (
      <div className="container py-20 text-sm text-muted">
        Arena snapshot missing: data/results/matrix_subset/matrix_subset_20260707.json
      </div>
    )
  }

  const entries = arena.entries
  const harnessCount = new Set(entries.map((e) => e.id)).size

  const stats = [
    { value: String(harnessCount), label: 'Harnesses', zh: '框架' },
    { value: String(arena.backbones.length), label: 'Backbone LLMs', zh: '主干模型' },
    { value: String(entries.length), label: 'Runs on the board', zh: '在榜记录' },
    { value: fmt(arena.n_judge_records_total), label: 'Jury records', zh: '陪审团判例' },
    { value: String(arena.judges.length), label: 'Jurors', zh: '陪审员' },
  ]

  const sections = [
    { id: 'arena-chart', label: 'Arena score', zh: 'Arena 主分' },
    { id: 'leaderboard', label: 'Leaderboard', zh: '排行榜' },
    { id: 'axes', label: 'Grounding & jury Elo', zh: '接地与陪审团 Elo' },
    { id: 'how-it-works', label: 'How it works', zh: '评测流程' },
    { id: 'faq', label: 'FAQ', zh: '常见问题' },
    { id: 'cite', label: 'Cite & reproduce', zh: '引用与复现' },
  ]

  // One bar per harness x backbone run. Same hue per harness; the second
  // backbone is rendered at reduced alpha so pairs read as a family.
  const secondBackbone = arena.backbones[1]
  const row = (e: (typeof entries)[number], value: number, valueLabel?: string): VBarRow => {
    const meta = agentMeta(e.id)
    return {
      id: e.key,
      label: meta.display,
      sublabel: backboneShort(e.backbone),
      color: e.backbone === secondBackbone ? `${meta.color}8C` : meta.color,
      value,
      valueLabel,
      href: `/agents/${e.id}#run-${e.backbone}`,
    }
  }

  const byArena: VBarRow[] = [...entries]
    .sort((a, b) => b.arena - a.arena)
    .map((e) => row(e, e.arena * 100, (e.arena * 100).toFixed(1)))
  const byReach: VBarRow[] = [...entries]
    .sort((a, b) => b.reach - a.reach)
    .map((e) => row(e, e.reach * 100, `${(e.reach * 100).toFixed(0)}%`))
  const byElo: VBarRow[] = [...entries]
    .sort((a, b) => b.bt_elo - a.bt_elo)
    .map((e) => row(e, e.bt_elo, String(Math.round(e.bt_elo))))

  const juryLine = arena.judges.join(' · ')
  const kappaLine = arena.backbones
    .map((bb) => `${backboneShort(bb)} κ=${arena.perBackbone[bb].fleiss_kappa.toFixed(2)}`)
    .join(' · ')

  return (
    <>
      <Hero stats={stats} news={news} />

      {/* Flagship chart: every harness x backbone run, ranked by Arena score */}
      <section id="arena-chart" className="container mt-12 scroll-mt-24">
        <div className="flex items-end justify-between border-b border-hairline pb-3">
          <h2 className="text-sm font-semibold text-ink"><T en="Arena score" zh="Arena 主分" /></h2>
          <span className="text-[11px] uppercase tracking-wider text-muted-2">
            <T
              en={`${arena.task_set} · jury: ${juryLine}`}
              zh={`${arena.task_set} · 陪审团：${juryLine}`}
            />
          </span>
        </div>
        <div className="mt-6">
          <VBarChart
            accent="#6E5BFF"
            title={<T en="Deep Research Arena — harness × LLM" zh="Deep Research Arena —— 框架 × 主干模型" />}
            subtitle={
              <T
                en={`arena = reach^1.5 × jury win rate (×100). Every bar is one harness run on one backbone — click it for the full breakdown. ${kappaLine}.`}
                zh={`arena = 引用可达率^1.5 × 陪审团胜率（×100）。每根竖条是一个框架在一个主干模型上的完整运行,点击查看详细分数。${kappaLine}。`}
              />
            }
            rows={byArena}
          />
        </div>
        {arena.excluded_agents.length > 0 ? (
          <p className="mt-2 text-[11px] text-muted-2">
            <T
              en={`Excluded: ${arena.excluded_agents.map((id) => agentMeta(id).display).join(', ')} — ${arena.excluded_reason}`}
              zh={`暂未上榜：${arena.excluded_agents.map((id) => agentMeta(id).display).join('、')} —— ${arena.excluded_reason}`}
            />
          </p>
        ) : null}
      </section>

      {/* Two-column body: sticky on-page nav + main */}
      <div className="container mt-16 flex flex-col gap-12 lg:flex-row">
        <SectionNav items={sections} />

        <div className="min-w-0 flex-1 space-y-14">
          {/* Leaderboard table */}
          <div>
            <SectionTitle
              id="leaderboard"
              title={<T en="Leaderboard" zh="排行榜" />}
              caption={
                <T
                  en={`${entries.length} harness × LLM runs · arena = reach^1.5 × Bradley-Terry win rate · ${arena.judges.length}-judge jury: ${juryLine}`}
                  zh={`${entries.length} 条框架 × 主干模型记录 · arena = 可达率^1.5 × Bradley-Terry 胜率 · ${arena.judges.length} 裁判陪审团：${juryLine}`}
                />
              }
            />
            <ArenaTable entries={entries} />
          </div>

          {/* Secondary axes: grounding + raw jury Elo */}
          <div id="axes" className="scroll-mt-24">
            <SectionTitle
              id="axes-title"
              title={<T en="Grounding & jury Elo" zh="接地与陪审团 Elo" />}
              caption={
                <T
                  en="The two ingredients behind the Arena score, shown separately — grounding is judge-free, jury Elo is blind to citation reality"
                  zh="Arena 主分的两个组成部分分开展示 —— 接地不依赖裁判,陪审团 Elo 则看不见引用真假"
                />
              }
            />
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <VBarChart
                accent="#34A853"
                title={<T en="Grounding (reach)" zh="接地（引用可达率）" />}
                subtitle={<T en="Share of cited URLs that resolve inside the frozen sandbox" zh="引用 URL 在冻结沙箱内可重新打开的比例" />}
                rows={byReach}
              />
              <VBarChart
                accent="#cc785c"
                title={<T en="Jury Elo (Bradley-Terry)" zh="陪审团 Elo（Bradley-Terry）" />}
                subtitle={<T en="Pairwise usefulness preference from the 3-judge jury, order-audited" zh="三裁判陪审团的成对有用性偏好,含顺序审计" />}
                rows={byElo}
              />
            </div>
          </div>

          {/* Pipeline explainer (light) */}
          <PipelineBand />

          {/* FAQ + cite */}
          <Faq />
          <CiteBlock />
        </div>
      </div>
    </>
  )
}

function SectionTitle({ id, title, caption }: { id: string; title: ReactNode; caption: ReactNode }) {
  return (
    <header id={id} className="mb-4 scroll-mt-24">
      <div className="flex items-center gap-2.5">
        <span className="aa-square" />
        <h2 className="font-serif text-h-sm text-ink">{title}</h2>
      </div>
      <p className="mt-1 text-xs text-muted">{caption}</p>
    </header>
  )
}
