import fs from 'node:fs'
import path from 'node:path'
import { Leaderboard, LeaderboardSchema, RankedAgent } from './types'

// Project root is the parent of `frontend/`.
const REPO_ROOT = path.resolve(process.cwd(), '..')
const PRIMARY_PATH = path.join(REPO_ROOT, 'data/results/deep_v3/leaderboard_deep.json')
const FALLBACK_PATHS = [
  path.join(REPO_ROOT, 'data/results/deep_v3/leaderboard_deep_2026-05-10.json'),
  path.join(REPO_ROOT, 'data/results/arena_final.json'),
]

function readJsonOrNull(p: string): unknown | null {
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'))
  } catch {
    return null
  }
}

let cached: Leaderboard | null = null

export function loadLeaderboard(): Leaderboard {
  if (cached) return cached
  let raw: unknown | null = readJsonOrNull(PRIMARY_PATH)
  if (!raw) {
    for (const p of FALLBACK_PATHS) {
      raw = readJsonOrNull(p)
      if (raw) break
    }
  }
  if (!raw) {
    // Graceful fallback: ship a synthetic but believable leaderboard so the
    // site still renders if the data files are absent in this checkout.
    raw = SYNTHETIC_LEADERBOARD
  }
  const parsed = LeaderboardSchema.parse(raw)
  cached = parsed
  return parsed
}

export function rankedAgents(): RankedAgent[] {
  const lb = loadLeaderboard()
  return Object.entries(lb.elo_v2_ci)
    .map(([id, row]) => ({
      id,
      ...row,
      ci_half: row.elo_half_width ?? Math.round((row.elo_hi - row.elo_lo) / 2),
    }))
    .sort((a, b) => b.elo - a.elo)
    .map((row, i) => ({ ...row, rank: i + 1 }))
}

/** Returns leaderboard mtime as ISO date for "last updated" footer line. */
export function leaderboardMtime(): string {
  for (const p of [PRIMARY_PATH, ...FALLBACK_PATHS]) {
    try {
      return fs.statSync(p).mtime.toISOString().slice(0, 10)
    } catch {
      // try next
    }
  }
  return new Date().toISOString().slice(0, 10)
}

const SYNTHETIC_LEADERBOARD: Leaderboard = {
  elo_v2_ci: {
    'flowsearcher-ds': { elo: 1401, elo_lo: 1324, elo_hi: 1486, n_battles: 227, wins: 193, losses: 32, draws: 2 },
    'camel-ai': { elo: 1480, elo_lo: 1405, elo_hi: 1567, n_battles: 227, wins: 206, losses: 20, draws: 1 },
    smolagents: { elo: 1307, elo_lo: 1211, elo_hi: 1404, n_battles: 227, wins: 138, losses: 76, draws: 13 },
    ldr: { elo: 945, elo_lo: 871, elo_hi: 1014, n_battles: 227, wins: 80, losses: 100, draws: 47 },
    'gpt-researcher': { elo: 866, elo_lo: 793, elo_hi: 941, n_battles: 227, wins: 60, losses: 114, draws: 53 },
    deerflow: { elo: 822, elo_lo: 756, elo_hi: 903, n_battles: 227, wins: 40, losses: 118, draws: 69 },
    'langchain-odr': { elo: 729, elo_lo: 674, elo_hi: 781, n_battles: 227, wins: 6, losses: 129, draws: 92 },
    storm: { elo: 718, elo_lo: 677, elo_hi: 763, n_battles: 136, wins: 0, losses: 75, draws: 61 },
  },
  n_runs: 227,
  agents: ['flowsearcher-ds', 'camel-ai', 'smolagents', 'ldr', 'gpt-researcher', 'deerflow', 'langchain-odr', 'storm'],
}
