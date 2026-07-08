import { agentMeta } from '@/lib/providers'
import type { MatrixBackbone, MatrixSubset } from '@/lib/data/load-matrix-subset'
import { T } from '@/components/i18n/t'

/**
 * v2 preview: framework x backbone matrix on the 13-task diagnostic subset.
 * Arena Score = grounding reach^1.5 (decidable, judge-free) x Bradley-Terry
 * usefulness winrate (cross-family jury). Clearly badged as a preview: the
 * headline board above stays authoritative until the first full run lands.
 * Server-rendered, AA-style white cards.
 */
export function MatrixPreview({ data }: { data: MatrixSubset }) {
  const backbones = Object.entries(data.backbones)
  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-2 border-b border-hairline pb-3">
        <div className="flex items-center gap-2.5">
          <h2 className="font-serif text-2xl text-ink">
            <T en="Matrix preview: truth x usefulness" zh="矩阵预览:真值 × 有用性" />
          </h2>
          <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-700">
            <T en="v2 preview - 13-task subset" zh="v2 预览 · 13 题子集" />
          </span>
        </div>
        <span className="text-[11px] uppercase tracking-wider text-muted-2">
          <T
            en={`${data.n_judge_records_total.toLocaleString()} judge records - jury: ${data.judges.join(' / ')}`}
            zh={`${data.n_judge_records_total.toLocaleString()} 条判官记录 · 陪审团:${data.judges.join(' / ')}`}
          />
        </span>
      </div>

      <p className="mt-3 max-w-3xl text-xs leading-relaxed text-muted">
        <T
          en="Two independent readings per system: a decidable five-axis truth score (no LLM anywhere in the loop), and a usefulness winrate from a cross-family Bradley-Terry jury. Arena Score multiplies the grounding gate into the winrate, so a fabricator can never rank by fluency alone. This is a diagnostic preview on 13 tasks; the headline leaderboard above remains authoritative until the first full run."
          zh="每个系统两条独立读数:可判定五轴 truth 分(全程无 LLM)与跨家族陪审团的 Bradley-Terry 有用性胜率。Arena Score 把接地门乘进胜率,编造者无法只靠流利度上榜。本节为 13 题诊断预览,正式榜以上方主榜为准,待首次全量跑后切换。"
        />
      </p>

      <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        {backbones.map(([backbone, bb]) => (
          <BackboneCard key={backbone} backbone={backbone} bb={bb} />
        ))}
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-muted-2">
        <T
          en={`Arena = reach^1.5 x BT winrate. 95% CIs from a 200-resample task-level cluster bootstrap; overlapping rank CIs mean a statistical tie at this task count. claude-code is excluded (${data.excluded_reason}).`}
          zh={`Arena = reach^1.5 × BT 胜率。CI95 来自 200 次任务级 cluster bootstrap;名次 CI 重叠即在该题量下统计并列。claude-code 暂不上榜(车道路由事故已于 2026-07-07 修复,增量对战待补)。`}
        />
      </p>
    </div>
  )
}

function BackboneCard({ backbone, bb }: { backbone: string; bb: MatrixBackbone }) {
  return (
    <article className="card p-5">
      <header className="flex flex-wrap items-center gap-2.5">
        <span className="aa-square" />
        <h3 className="font-serif text-xl text-ink">{backbone}</h3>
        <span className="ml-auto flex gap-2 text-[10px] uppercase tracking-wider text-muted-2">
          <Chip label={<T en="judge agreement" zh="判官一致性" />} value={`κ ${bb.fleiss_kappa.toFixed(2)}`} />
          <Chip
            label={<T en="truth vs usefulness" zh="真值 × 有用性" />}
            value={`ρ ${bb.spearman_truth_vs_usefulness.toFixed(2)}`}
          />
        </span>
      </header>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[520px] border-collapse text-xs">
          <thead>
            <tr className="border-b border-hairline text-left text-[10px] uppercase tracking-wider text-muted-2">
              <th className="py-1.5 pr-2 font-medium">#</th>
              <th className="py-1.5 pr-3 font-medium">
                <T en="System" zh="系统" />
              </th>
              <th className="py-1.5 pr-3 text-right font-medium">Arena</th>
              <th className="py-1.5 pr-3 text-right font-medium">truth</th>
              <th className="py-1.5 pr-3 text-right font-medium">reach</th>
              <th className="py-1.5 pr-3 text-right font-medium">
                <T en="Judge win" zh="判官胜率" />
              </th>
              <th className="py-1.5 pr-3 text-right font-medium">CI95</th>
              <th className="py-1.5 text-right font-medium">Elo</th>
            </tr>
          </thead>
          <tbody>
            {bb.agents.map((a, i) => {
              const meta = agentMeta(a.id)
              const gateZero = a.reach === 0
              return (
                <tr key={a.id} className="border-b border-hairline/60 last:border-0">
                  <td className="py-1.5 pr-2 text-muted-2 tnum">{i + 1}</td>
                  <td className="py-1.5 pr-3">
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        className="h-2 w-2 shrink-0 rounded-[2px]"
                        style={{ backgroundColor: meta.color }}
                      />
                      <span className="text-ink">{meta.display}</span>
                    </span>
                  </td>
                  <td className="py-1.5 pr-3 text-right font-semibold text-ink tnum">
                    {a.arena.toFixed(3)}
                  </td>
                  <td className="py-1.5 pr-3 text-right text-muted tnum">{a.truth.toFixed(3)}</td>
                  <td
                    className={`py-1.5 pr-3 text-right tnum ${gateZero ? 'font-semibold text-red-600' : 'text-muted'}`}
                  >
                    {a.reach.toFixed(2)}
                  </td>
                  <td className="py-1.5 pr-3 text-right text-muted tnum">{a.winrate.toFixed(3)}</td>
                  <td className="py-1.5 pr-3 text-right text-muted-2 tnum">
                    {a.winrate_ci95
                      ? `${a.winrate_ci95[0].toFixed(2)}-${a.winrate_ci95[1].toFixed(2)}`
                      : '-'}
                  </td>
                  <td className="py-1.5 text-right text-muted tnum">{Math.round(a.bt_elo)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-muted-2">
        <T
          en={`Fleiss κ over ${bb.n_clean_items}/${bb.n_items} clean items. Red reach = every citation fabricated: the jury may still like the prose (see Elo), the gate zeroes the score.`}
          zh={`Fleiss κ 基于 ${bb.n_clean_items}/${bb.n_items} 个三判官齐票场次。红色 reach = 引用全部编造:陪审团可能仍喜欢其行文(见 Elo 列),但门将总分归零。`}
        />
      </p>
    </article>
  )
}

function Chip({ label, value }: { label: React.ReactNode; value: string }) {
  return (
    <span className="rounded border border-hairline bg-surface-low px-1.5 py-0.5">
      {label}: <span className="tnum font-semibold text-ink">{value}</span>
    </span>
  )
}
