'use client'

import { useState, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { T } from '@/components/i18n/t'
import type { AxisKey, AxisMap, AxesPerTask } from '@/lib/data/load-axes-detail'

export interface ExplainerBackbone {
  key: string
  label: string
  /** Decidable five-axis means (0..1). */
  axes?: AxisMap
  truthMacro?: number
  gamma?: number
  /** Jury side. */
  arena?: number
  reach?: number
  winrate?: number
  winrateCi95?: [number, number]
  btElo?: number
  nBattles?: number
  tieRate?: number | null
  /** One real report excerpt. */
  sample?: { task: string; chars_total: number; excerpt: string }
  perTask?: AxesPerTask[]
}

interface Props {
  agentLabel: string
  color: string
  backbones: ExplainerBackbone[]
}

const AXIS_ORDER: AxisKey[] = [
  'grounding_reach',
  'correctness_fact_support',
  'grounding_proof_of_fetch',
  'completeness',
  'spec',
]

const AXIS_META: Record<AxisKey, { name: ReactNode; role: ReactNode; tag: ReactNode }> = {
  grounding_reach: {
    name: <T en="Grounding reach" zh="接地可达" />,
    role: (
      <T
        en="Share of cited URLs that reopen in the frozen sandbox. Multiplicative gate — fabricated citations zero the whole score."
        zh="被引用 URL 在冻结沙箱中可重新打开的比例。乘性门 —— 编造的引用会让总分归零。"
      />
    ),
    tag: <T en="gate ^1.5" zh="门 ^1.5" />,
  },
  correctness_fact_support: {
    name: <T en="Fact support" zh="事实支撑" />,
    role: (
      <T
        en="Claims are actually backed by the cited evidence. Defends against confident hallucinations."
        zh="论断确实有被引用证据支撑。防止自信的幻觉。"
      />
    ),
    tag: <T en="weight 0.35" zh="权重 0.35" />,
  },
  grounding_proof_of_fetch: {
    name: <T en="Proof of fetch" zh="取证核实" />,
    role: (
      <T
        en="The quoted snippet really appears on the fetched page. Defends against citing a real URL but misquoting it."
        zh="引文片段确实出现在抓取到的页面上。防止引用真实 URL 却错误引述。"
      />
    ),
    tag: <T en="weight 0.25" zh="权重 0.25" />,
  },
  completeness: {
    name: <T en="Completeness" zh="完整度" />,
    role: (
      <T
        en="Coverage of the task's required sub-questions and answer-key items."
        zh="对任务要求的子问题与答案要点的覆盖程度。"
      />
    ),
    tag: <T en="weight 0.30" zh="权重 0.30" />,
  },
  spec: {
    name: <T en="Spec adherence" zh="规范遵循" />,
    role: (
      <T
        en="Follows the task's requested format and constraints."
        zh="遵循任务要求的格式与约束。"
      />
    ),
    tag: <T en="weight 0.10" zh="权重 0.10" />,
  },
}

export function ScoreExplainer({ agentLabel, color, backbones }: Props) {
  const [active, setActive] = useState(
    Math.max(0, backbones.findIndex((b) => b.key === 'deepseek-v4-flash')),
  )
  const [reportOpen, setReportOpen] = useState(false)
  if (backbones.length === 0) return null
  const bb = backbones[active] ?? backbones[0]

  return (
    <section className="mt-10">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-hairline pb-3">
        <div className="flex items-center gap-2.5">
          <span className="aa-square" />
          <h2 className="font-serif text-h-sm text-ink">
            <T en="How the score is computed" zh="分数是怎么算的" />
          </h2>
          <span className="inline-flex items-center rounded-full border border-hairline bg-surface-low px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-2">
            <T en="Preview · 13-task subset" zh="预览 · 13 题子集" />
          </span>
        </div>
        {backbones.length > 1 ? (
          <div className="inline-flex rounded-full border border-hairline p-0.5 text-xs">
            {backbones.map((b, i) => (
              <button
                key={b.key}
                onClick={() => {
                  setActive(i)
                  setReportOpen(false)
                }}
                className={cn(
                  'rounded-full px-3 py-1 transition-colors',
                  i === active ? 'bg-surface-mid font-medium text-ink' : 'text-muted hover:text-ink',
                )}
              >
                {b.label}
              </button>
            ))}
          </div>
        ) : (
          <span className="text-[11px] text-muted-2">{bb.label}</span>
        )}
      </div>

      {/* Formula cards */}
      <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <FormulaCard
          title={<T en="Arena Score" zh="竞技场得分" />}
          value={bb.arena != null ? (bb.arena * 100).toFixed(1) : '—'}
          suffix="×100"
          formula={<span className="font-mono">reach<sup>1.5</sup> × jury BT win-rate</span>}
          rows={[
            bb.reach != null ? { k: <T en="grounding reach" zh="接地可达" />, v: bb.reach.toFixed(3) } : null,
            bb.winrate != null
              ? {
                  k: <T en="jury win-rate" zh="陪审团胜率" />,
                  v:
                    bb.winrateCi95
                      ? `${(bb.winrate * 100).toFixed(1)}%  (95% CI ${(bb.winrateCi95[0] * 100).toFixed(0)}–${(bb.winrateCi95[1] * 100).toFixed(0)}%)`
                      : `${(bb.winrate * 100).toFixed(1)}%`,
                }
              : null,
            bb.btElo != null ? { k: <T en="Bradley-Terry Elo" zh="Bradley-Terry Elo" />, v: String(Math.round(bb.btElo)) } : null,
            bb.nBattles != null ? { k: <T en="battles" zh="对战数" />, v: String(bb.nBattles) } : null,
          ]}
        />
        <FormulaCard
          title={<T en="Decidable truth (judge-free)" zh="可判定 truth(无判官)" />}
          value={bb.truthMacro != null ? (bb.truthMacro * 100).toFixed(1) : '—'}
          suffix="×100"
          formula={
            <span className="font-mono">
              reach<sup>1.5</sup> × (0.35 fact + 0.25 pof + 0.30 compl + 0.10 spec)
            </span>
          }
          rows={[
            {
              k: <T en="what it is" zh="它是什么" />,
              v: '',
              note: (
                <T
                  en="A separate, fully decidable reading with no LLM in the loop. The grounding gate is the same reach term as Arena."
                  zh="一条独立、完全可判定的读数,全程无 LLM。接地门与 Arena 使用同一 reach 项。"
                />
              ),
            },
          ]}
        />
      </div>

      {/* Five-axis breakdown */}
      {bb.axes ? (
        <div className="card mt-4 p-6">
          <h3 className="font-serif text-xl text-ink">
            <T en="Five-axis breakdown" zh="五轴分解" />
          </h3>
          <p className="mt-1 text-xs text-muted">
            <T
              en={`Mean over 13 tasks on ${bb.label}. Grounding reach is a multiplicative gate; the other four are weighted additively.`}
              zh={`基于 ${bb.label} 的 13 题均值。接地可达是乘性门,其余四项按权重相加。`}
            />
          </p>
          <div className="mt-5 space-y-5">
            {AXIS_ORDER.map((key) => (
              <AxisBar key={key} axisKey={key} value={bb.axes![key]} color={color} />
            ))}
          </div>
        </div>
      ) : null}

      {/* Sample report */}
      {bb.sample ? (
        <div className="card mt-4 p-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-serif text-xl text-ink">
              <T en="Sample report" zh="样例报告" />
            </h3>
            <span className="text-[11px] text-muted-2 tnum">
              <T
                en={`task ${bb.sample.task} · ${bb.sample.chars_total.toLocaleString()} chars · ${bb.label}`}
                zh={`任务 ${bb.sample.task} · ${bb.sample.chars_total.toLocaleString()} 字符 · ${bb.label}`}
              />
            </span>
          </div>
          <p className="mt-1 text-xs text-muted">
            <T
              en="The framework's real output for this task, verbatim. Excerpt only — expand to read the opening."
              zh="该框架在此任务上的真实输出原文。仅节选 —— 展开可阅读开头部分。"
            />
          </p>
          <button
            onClick={() => setReportOpen((v) => !v)}
            className="mt-3 inline-flex items-center rounded-tab border border-hairline bg-surface-low px-3 py-1.5 text-xs font-medium text-ink hover:border-ink/30"
          >
            {reportOpen ? <T en="Hide excerpt" zh="收起节选" /> : <T en="Show excerpt" zh="展开节选" />}
          </button>
          {reportOpen ? (
            <div className="mt-3 max-h-[420px] overflow-auto rounded-card border border-hairline bg-surface-low p-4">
              <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-ink">
                {bb.sample.excerpt}
              </pre>
              <p className="mt-3 border-t border-hairline pt-2 text-[10px] uppercase tracking-wider text-muted-2">
                <T
                  en={`Excerpt · first ${bb.sample.excerpt.length.toLocaleString()} of ${bb.sample.chars_total.toLocaleString()} characters`}
                  zh={`节选 · 全文 ${bb.sample.chars_total.toLocaleString()} 字符中的前 ${bb.sample.excerpt.length.toLocaleString()} 字符`}
                />
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

function AxisBar({ axisKey, value, color }: { axisKey: AxisKey; value: number; color: string }) {
  const meta = AXIS_META[axisKey]
  const v = Math.max(0, Math.min(1, value))
  const zero = v === 0
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-ink">{meta.name}</span>
          <span className="rounded border border-hairline bg-surface-low px-1.5 py-0.5 text-[10px] text-muted-2">{meta.tag}</span>
        </div>
        <span className={cn('text-sm tnum', zero ? 'font-semibold text-bad' : 'text-ink')}>{value.toFixed(3)}</span>
      </div>
      <div className="mt-1.5 h-2.5 rounded-pill bg-surface-mid">
        <div className="h-full rounded-pill" style={{ width: `${Math.max(v * 100, zero ? 0 : 1.5)}%`, backgroundColor: zero ? '#E5484D' : color }} />
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-muted">{meta.role}</p>
    </div>
  )
}

function FormulaCard({
  title,
  value,
  suffix,
  formula,
  rows,
}: {
  title: ReactNode
  value: string
  suffix?: string
  formula: ReactNode
  rows: (({ k: ReactNode; v: string; note?: ReactNode } | null))[]
}) {
  return (
    <div className="card p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="font-serif text-xl text-ink">{title}</h3>
        <span className="tnum text-2xl font-semibold text-ink">
          {value}
          {suffix ? <span className="ml-1 text-xs font-normal text-muted-2">{suffix}</span> : null}
        </span>
      </div>
      <p className="mt-2 text-xs text-muted">{formula}</p>
      <dl className="mt-4 space-y-2">
        {rows.filter(Boolean).map((r, i) => {
          const row = r as { k: ReactNode; v: string; note?: ReactNode }
          return (
            <div key={i} className="text-xs">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">{row.k}</dt>
                {row.v ? <dd className="tnum text-ink">{row.v}</dd> : null}
              </div>
              {row.note ? <p className="mt-1 leading-relaxed text-muted-2">{row.note}</p> : null}
            </div>
          )
        })}
      </dl>
    </div>
  )
}
