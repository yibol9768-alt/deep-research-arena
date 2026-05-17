import fs from 'node:fs'
import path from 'node:path'
import type { Leaderboard, RankedAgent } from './types'

const LEADERBOARD_JSON = path.join(
  process.cwd(),
  '..',
  'data',
  'results',
  'deep_v3',
  'leaderboard_deep.json',
)

interface ScoreFileEloEntry {
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

interface ScoreFileShape {
  elo_v2_ci: Record<string, ScoreFileEloEntry>
  permutation?: Leaderboard['permutation']
  drop_stats?: Leaderboard['drop_stats']
  excluded_agents?: Leaderboard['excluded_agents']
}

let _cache: ScoreFileShape | null = null

function readRaw(): ScoreFileShape {
  if (_cache) return _cache
  if (!fs.existsSync(LEADERBOARD_JSON)) {
    // Fallback to a tiny synthetic dataset so the site still renders during
    // local dev when the backend hasn't been built yet.
    _cache = {
      elo_v2_ci: {
        'claude-code': {
          elo: 1352.9, elo_lo: 1282, elo_hi: 1400, elo_half_width: 59,
          n_battles: 49, wins: 48, losses: 1, draws: 0,
        },
        'opencode': {
          elo: 1250.6, elo_lo: 1181, elo_hi: 1319, elo_half_width: 69,
          n_battles: 31, wins: 29, losses: 2, draws: 0,
        },
        'camel-ai': {
          elo: 1188.0, elo_lo: 1111, elo_hi: 1262, elo_half_width: 76,
          n_battles: 36, wins: 29, losses: 5, draws: 2,
        },
      },
    }
    return _cache
  }
  const txt = fs.readFileSync(LEADERBOARD_JSON, 'utf-8')
  _cache = JSON.parse(txt) as ScoreFileShape
  return _cache
}

export function rankedAgents(): RankedAgent[] {
  const raw = readRaw()
  const rows: RankedAgent[] = Object.entries(raw.elo_v2_ci).map(([id, e]) => ({
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
  }))
  rows.sort((a, b) => b.elo - a.elo)
  rows.forEach((r, i) => {
    r.rank = i + 1
  })
  return rows
}

/** Last-modified timestamp of the underlying leaderboard JSON as an ISO 8601
 *  string. Used by the layout / site header to show "data updated N hours
 *  ago". Returns the current time as a fallback when the file is absent
 *  (synthetic dataset). */
export function leaderboardMtime(): string {
  try {
    return fs.statSync(LEADERBOARD_JSON).mtime.toISOString()
  } catch {
    return new Date().toISOString()
  }
}

export function loadLeaderboard(): Leaderboard {
  const raw = readRaw()
  const n_runs = Object.values(raw.elo_v2_ci).reduce((acc, e) => acc + (e.n_battles || 0), 0)
  return {
    n_runs,
    permutation: raw.permutation,
    drop_stats: raw.drop_stats,
    excluded_agents: raw.excluded_agents,
  }
}
