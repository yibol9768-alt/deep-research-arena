import type { ReactNode } from 'react'
import { loadArenaV2, harnessAggregates, backboneShort, type HarnessAgg } from '@/lib/data/load-arena-v2'
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
  const harnesses = harnessAggregates(arena)
  const harnessCount = harnesses.length

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

  // One bar per harness: the bar is the cross-LLM average, the small dots
  // mark each backbone's individual value. Click lands on the harness page.
  const row = (h: HarnessAgg, value: number, valueLabel: string, markerValue: (r: HarnessAgg['runs'][number]) => number): VBarRow => {
    const meta = agentMeta(h.id)
    return {
      id: h.id,
      label: meta.display,
      color: meta.color,
      value,
      valueLabel,
      href: `/agents/${h.id}`,
      markers: h.runs.map((r) => ({ value: markerValue(r), label: backboneShort(r.backbone) })),
    }
  }

  const byArena: VBarRow[] = [...harnesses]
    .sort((a, b) => b.arena - a.arena)
    .map((h) => row(h, h.arena * 100, (h.arena * 100).toFixed(1), (r) => r.arena * 100))
  const byReach: VBarRow[] = [...harnesses]
    .sort((a, b) => b.reach - a.reach)
    .map((h) => row(h, h.reach * 100, `${(h.reach * 100).toFixed(0)}%`, (r) => r.reach * 100))
  const byElo: VBarRow[] = [...harnesses]
    .sort((a, b) => b.bt_elo - a.bt_elo)
    .map((h) => row(h, h.bt_elo, String(Math.round(h.bt_elo)), (r) => r.bt_elo))

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
            title={<T en="Deep Research Arena — harness average" zh="Deep Research Arena —— 框架平均分" />}
            subtitle={
              <T
                en={`arena = reach^1.5 × jury win rate (×100), averaged over ${arena.backbones.length} backbone LLMs. Dots mark each LLM's individual score — click a bar for the per-LLM breakdown. ${kappaLine}.`}
                zh={`arena = 引用可达率^1.5 × 陪审团胜率（×100）,对 ${arena.backbones.length} 个主干模型取平均。小圆点是各模型的单独得分,点击竖条查看分模型明细。${kappaLine}。`}
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
                  en={`${harnessCount} harnesses averaged over ${arena.backbones.length} LLMs (${entries.length} runs) · arena = reach^1.5 × Bradley-Terry win rate · jury: ${juryLine} · click a row to expand per-LLM results`}
                  zh={`${harnessCount} 个框架,对 ${arena.backbones.length} 个模型取平均(共 ${entries.length} 条运行)· arena = 可达率^1.5 × Bradley-Terry 胜率 · 陪审团：${juryLine} · 点击行展开分模型结果`}
                />
              }
            />
            <ArenaTable harnesses={harnesses} />
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
                subtitle={<T en="Share of cited URLs that resolve inside the frozen sandbox · cross-LLM average, dots per LLM" zh="引用 URL 在冻结沙箱内可重新打开的比例 · 跨模型平均,圆点为各模型" />}
                rows={byReach}
              />
              <VBarChart
                accent="#cc785c"
                title={<T en="Jury Elo (Bradley-Terry)" zh="陪审团 Elo（Bradley-Terry）" />}
                subtitle={<T en="Pairwise usefulness preference from the 3-judge jury · cross-LLM average, dots per LLM" zh="三裁判陪审团的成对有用性偏好 · 跨模型平均,圆点为各模型" />}
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
