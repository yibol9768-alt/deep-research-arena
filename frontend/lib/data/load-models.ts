import fs from 'node:fs'
import path from 'node:path'
import type { RankedAgent } from './types'

// Backbone-LLM board: same minimal scaffold, varying only the LLM. Built by
// scripts/build_model_board (V3 schema: elo_v3_ci + per_agent_profile).
const MODELS_JSON = path.join(
  process.cwd(),
  '..',
  'data',
  'results',
  'deep_v3',
  'leaderboard_models_v3.json',
)

interface EloEntry {
  elo: number
  elo_mean?: number
  elo_lo: number
  elo_hi: number
  elo_half_width: number
  n_battles: number
  wins: number
  losses: number
  draws: number
}

interface Prof {
  url_veracity_pct?: number
  reachability_pct?: number
  coverage_pct?: number
}

interface ModelFile {
  elo_v3_ci?: Record<string, EloEntry>
  per_agent_profile?: Record<string, Prof>
  n_battles?: number
  n_tasks?: number
  composite_formula?: string
}

function read(): ModelFile | null {
  try {
    if (!fs.existsSync(MODELS_JSON)) return null
    return JSON.parse(fs.readFileSync(MODELS_JSON, 'utf-8')) as ModelFile
  } catch {
    return null
  }
}

export function rankedModelAgents(): RankedAgent[] {
  const raw = read()
  const elo = raw?.elo_v3_ci ?? {}
  const prof = raw?.per_agent_profile ?? {}
  const rows: RankedAgent[] = Object.entries(elo).map(([key, e]) => {
    const p = prof[key] ?? {}
    // Strip the "eff-" scaffold prefix so the board reads as the model name.
    const id = key.replace(/^eff-/, '')
    return {
      id,
      rank: 0,
      elo: e.elo,
      elo_mean: e.elo_mean,
      ci_lo: e.elo_lo,
      ci_hi: e.elo_hi,
      elo_lo: e.elo_lo,
      elo_hi: e.elo_hi,
      ci_half: e.elo_half_width,
      n_battles: e.n_battles,
      wins: e.wins,
      losses: e.losses,
      draws: e.draws,
      url_veracity_pct: p.url_veracity_pct,
      reachability_pct: p.reachability_pct,
      coverage_pct: p.coverage_pct,
    }
  })
  // Truth-gated score: judge Elo scaled by the grounding gate (same formula as
  // the framework board) so a fluent model citing unreachable sources can't top.
  for (const r of rows) {
    const gate =
      r.reachability_pct != null && r.url_veracity_pct != null
        ? (r.reachability_pct + r.url_veracity_pct) / 200
        : 0
    r.gated_score = Math.round(r.elo * gate)
  }
  rows.sort((a, b) => (b.gated_score ?? 0) - (a.gated_score ?? 0) || b.elo - a.elo)
  rows.forEach((r, i) => {
    r.rank = i + 1
  })
  return rows
}

export function modelMeta(): { n_runs: number; n_tasks: number } {
  const raw = read()
  const n_runs =
    raw?.n_battles ??
    Object.values(raw?.elo_v3_ci ?? {}).reduce((a, e) => a + (e.n_battles || 0), 0)
  return { n_runs, n_tasks: raw?.n_tasks ?? 0 }
}
