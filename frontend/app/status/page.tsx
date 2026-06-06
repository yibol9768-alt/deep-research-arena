'use client'

import { useEffect, useState } from 'react'
import { Activity, RefreshCw } from 'lucide-react'
import { PageHero } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

interface TaskStatus {
  name: string
  nameZh?: string
  kind?: string
  progress?: number
  total?: number
  state: string
  detail?: string
}

interface BoxStatus {
  ts?: string
  _received?: string
  host?: string
  tasks?: TaskStatus[]
  sandbox?: Record<string, number | string>
  sessions?: string[]
  watchdog_heartbeat?: string
  errors_tail?: string[]
}

const POLL_MS = 30_000

export default function StatusPage() {
  const [st, setSt] = useState<BoxStatus | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [fetchedAt, setFetchedAt] = useState<number>(0)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await fetch('/api/status', { cache: 'no-store' })
        if (!alive) return
        if (!r.ok) {
          setErr(r.status === 404 ? 'no-data' : `http-${r.status}`)
          setSt(null)
          return
        }
        setSt(await r.json())
        setErr(null)
        setFetchedAt(Date.now())
      } catch {
        if (alive) setErr('network')
      }
    }
    load()
    const t = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  const ageMin = st?._received ? (Date.now() - new Date(st._received).getTime()) / 60000 : null
  const stale = ageMin != null && ageMin > 5

  return (
    <>
      <PageHero
        eyebrow={<T en="Live Status" zh="实时状态" />}
        title={<T en="What the eval box is doing right now." zh="评测机此刻在干什么。" />}
        intro={
          <T
            en="The box reports task progress, sandbox health, and watchdog heartbeat every minute. This page refreshes automatically every 30 seconds."
            zh="评测机每分钟上报一次任务进度、沙箱健康与看门狗心跳。本页每 30 秒自动刷新。"
          />
        }
      />

      <section className="container space-y-6 pb-16">
        {/* freshness banner */}
        <div className="card flex items-center gap-3 p-4 text-sm">
          <Activity className={`h-4 w-4 ${stale || err ? 'text-bad' : 'text-good'}`} />
          {err === 'no-data' ? (
            <T en="No status reported yet (reporter or STATUS_TOKEN not configured)." zh="尚无上报数据（上报器或 STATUS_TOKEN 未配置）。" />
          ) : err ? (
            <T en="Could not reach the status API." zh="无法访问状态接口。" />
          ) : stale ? (
            <span className="text-bad">
              <T
                en={<>Last report {ageMin!.toFixed(0)} min ago. The box may be offline or the reporter died.</>}
                zh={<>最后上报于 {ageMin!.toFixed(0)} 分钟前，评测机可能掉线或上报器挂了。</>}
              />
            </span>
          ) : st ? (
            <T
              en={<>Live · last report {ageMin == null ? '?' : ageMin < 1 ? '<1' : ageMin.toFixed(0)} min ago from {st.host ?? 'box'}</>}
              zh={<>在线 · 最后上报于 {ageMin == null ? '?' : ageMin < 1 ? '不到 1' : ageMin.toFixed(0)} 分钟前（{st.host ?? 'box'}）</>}
            />
          ) : (
            <span className="inline-flex items-center gap-2 text-muted">
              <RefreshCw className="h-3.5 w-3.5 animate-spin" /> <T en="Loading" zh="加载中" />
            </span>
          )}
        </div>

        {/* tasks */}
        {st?.tasks?.length ? (
          <div className="card p-6">
            <h2 className="mb-4 font-serif text-h-sm text-ink"><T en="Tasks" zh="任务" /></h2>
            <ul className="space-y-4">
              {st.tasks.map((t) => {
                const pct = t.total ? Math.min(100, Math.round(((t.progress ?? 0) / t.total) * 100)) : null
                const tone =
                  t.state === 'done' ? 'text-good' : t.state === 'running' ? 'text-brand' : 'text-bad'
                return (
                  <li key={t.name}>
                    <div className="flex items-baseline justify-between gap-3 text-sm">
                      <span className="font-medium text-ink">
                        {t.nameZh ? <T en={t.name} zh={t.nameZh} /> : t.name}
                      </span>
                      <span className={`text-xs font-semibold uppercase tracking-wider ${tone}`}>{t.state}</span>
                    </div>
                    {pct != null ? (
                      <div className="mt-1.5 flex items-center gap-3">
                        <div className="h-2 flex-1 overflow-hidden rounded-pill bg-surface-mid">
                          <div
                            className={`h-full rounded-pill ${t.state === 'done' ? 'bg-good' : 'bg-brand'}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="w-28 text-right text-xs text-muted tnum">
                          {t.progress}/{t.total} · {pct}%
                        </span>
                      </div>
                    ) : null}
                    {t.detail ? <p className="mt-1 text-xs text-muted">{t.detail}</p> : null}
                  </li>
                )
              })}
            </ul>
          </div>
        ) : null}

        {/* sandbox + sessions */}
        {st ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="card p-6">
              <h2 className="mb-3 font-serif text-h-sm text-ink"><T en="Sandbox" zh="沙箱" /></h2>
              <ul className="space-y-1.5 text-sm">
                {Object.entries(st.sandbox ?? {}).map(([port, code]) => (
                  <li key={port} className="flex justify-between">
                    <span className="text-muted tnum">:{port}</span>
                    <span className={String(code) === '200' || code === 'up' ? 'text-good' : 'text-bad'}>
                      {String(code)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="card p-6">
              <h2 className="mb-3 font-serif text-h-sm text-ink"><T en="Sessions / Watchdog" zh="会话 / 看门狗" /></h2>
              <p className="text-sm text-muted">{(st.sessions ?? []).join(' · ') || '-'}</p>
              {st.watchdog_heartbeat ? (
                <p className="mt-2 text-xs text-muted">
                  <T en="watchdog heartbeat:" zh="看门狗心跳：" /> <span className="tnum">{st.watchdog_heartbeat}</span>
                </p>
              ) : null}
            </div>
          </div>
        ) : null}

        {/* recent errors */}
        {st?.errors_tail?.length ? (
          <div className="card p-6">
            <h2 className="mb-3 font-serif text-h-sm text-ink"><T en="Recent errors" zh="近期错误" /></h2>
            <pre className="overflow-x-auto rounded-tab bg-surface-low p-3 text-xs leading-relaxed text-muted">
              {st.errors_tail.join('\n')}
            </pre>
          </div>
        ) : null}

        <p className="text-xs text-muted">
          <T
            en={<>Fetched {fetchedAt ? new Date(fetchedAt).toLocaleTimeString() : '-'} · auto-refresh 30s</>}
            zh={<>页面拉取于 {fetchedAt ? new Date(fetchedAt).toLocaleTimeString() : '-'} · 每 30 秒自动刷新</>}
          />
        </p>
      </section>
    </>
  )
}
