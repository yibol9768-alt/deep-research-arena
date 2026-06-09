import type { RankedAgent } from './data/types'

export function fmt(n: number, digits = 0): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function pct(n: number, digits = 0): string {
  return `${(n * 100).toFixed(digits)}%`
}

export function signed(n: number, digits = 0): string {
  const sign = n > 0 ? '+' : n < 0 ? '−' : ''
  return `${sign}${Math.abs(n).toFixed(digits)}`
}

export function rankMedal(rank: number): string {
  if (rank === 1) return '🥇'
  if (rank === 2) return '🥈'
  if (rank === 3) return '🥉'
  return ''
}

export function groundingGatePct(agent: Pick<RankedAgent, 'reachability_pct' | 'url_veracity_pct'>): number | undefined {
  if (agent.reachability_pct == null || agent.url_veracity_pct == null) return undefined
  return (agent.reachability_pct + agent.url_veracity_pct) / 2
}

export function truthScore(agent: Pick<RankedAgent, 'gated_score' | 'elo' | 'reachability_pct' | 'url_veracity_pct'>): number {
  if (agent.gated_score != null) return agent.gated_score
  const gate = groundingGatePct(agent)
  return Math.round(agent.elo * ((gate ?? 0) / 100))
}

export function totalPairwiseBattles(agents: Pick<RankedAgent, 'n_battles'>[]): number {
  return Math.round(agents.reduce((acc, agent) => acc + agent.n_battles, 0) / 2)
}
