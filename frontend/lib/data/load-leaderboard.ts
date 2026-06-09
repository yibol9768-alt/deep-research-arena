import fs from 'node:fs'
import path from 'node:path'
import type { Leaderboard, PerPillarElo, RankedAgent } from './types'

// v3 schema: real per-pillar Elo + per-agent profile. Try this FIRST.
const LEADERBOARD_V3_JSON = path.join(
  process.cwd(),
  '..',
  'data',
  'results',
  'deep_v3',
  'leaderboard_deep_v3.json',
)

// v2 schema fallback: older composite leaderboard.
const LEADERBOARD_V2_JSON = path.join(
  process.cwd(),
  '..',
  'data',
  'results',
  'deep_v3',
  'leaderboard_deep.json',
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

interface PerAgentProfile {
  url_veracity_pct?: number
  depth_avg?: number
  rigor_avg?: number
  style_avg?: number
  checklist_pass_rate?: number
  coverage_pct?: number
  reachability_pct?: number
  synthetic_placeholder?: boolean
}

interface RankSignificance {
  ordered?: string[]
  adjacent_pairs?: Array<{
    higher: string
    lower: string
    gap: number
    p_value: number
    significant: boolean
  }>
}

interface V3FileShape {
  _schema_version?: string
  _dry_run?: boolean
  weights_v3?: Record<string, number>
  composite_formula?: string
  elo_v3_ci: Record<string, EloEntry>
  rank_significance_v3?: RankSignificance
  pillar_elo?: Record<string, PerPillarElo>
  per_agent_profile?: Record<string, PerAgentProfile>
  human_alignment?: Leaderboard['human_alignment']
  n_runs?: number
  permutation?: Leaderboard['permutation']
  drop_stats?: Leaderboard['drop_stats']
  excluded_agents?: Leaderboard['excluded_agents']
}

interface V2FileShape {
  elo_v2_ci: Record<string, EloEntry>
  permutation?: Leaderboard['permutation']
  drop_stats?: Leaderboard['drop_stats']
  excluded_agents?: Leaderboard['excluded_agents']
}

interface NormalizedCache {
  schemaVersion?: string
  isDryRun: boolean
  weights?: Record<string, number>
  compositeFormula?: string
  elo: Record<string, EloEntry>
  pillarElo: Record<string, PerPillarElo>
  perAgentProfile: Record<string, PerAgentProfile>
  rankSignificance: NonNullable<Leaderboard['rank_significance']>
  humanAlignment?: Leaderboard['human_alignment']
  nRuns?: number
  permutation?: Leaderboard['permutation']
  dropStats?: Leaderboard['drop_stats']
  excludedAgents?: Leaderboard['excluded_agents']
  sourcePath: string
  source: 'v3' | 'v2' | 'synthetic'
}

let _cache: NormalizedCache | null = null

function trySafeReadJson<T>(p: string): T | null {
  try {
    if (!fs.existsSync(p)) return null
    const txt = fs.readFileSync(p, 'utf-8')
    return JSON.parse(txt) as T
  } catch {
    return null
  }
}

function isV3Valid(raw: V3FileShape | null): raw is V3FileShape {
  return !!raw && typeof raw === 'object' && !!raw.elo_v3_ci && Object.keys(raw.elo_v3_ci).length > 0
}

function isV2Valid(raw: V2FileShape | null): raw is V2FileShape {
  return !!raw && typeof raw === 'object' && !!raw.elo_v2_ci && Object.keys(raw.elo_v2_ci).length > 0
}

function buildCache(): NormalizedCache {
  // Try v3 first.
  const v3 = trySafeReadJson<V3FileShape>(LEADERBOARD_V3_JSON)
  if (isV3Valid(v3)) {
    const sigList = v3.rank_significance_v3?.adjacent_pairs ?? []
    return {
      schemaVersion: v3._schema_version,
      isDryRun: !!v3._dry_run,
      weights: v3.weights_v3,
      compositeFormula: v3.composite_formula,
      elo: v3.elo_v3_ci,
      pillarElo: v3.pillar_elo ?? {},
      perAgentProfile: v3.per_agent_profile ?? {},
      rankSignificance: sigList,
      humanAlignment: v3.human_alignment,
      nRuns: v3.n_runs,
      permutation: v3.permutation,
      dropStats: v3.drop_stats,
      excludedAgents: v3.excluded_agents,
      sourcePath: LEADERBOARD_V3_JSON,
      source: 'v3',
    }
  }

  // Fallback: v2 file.
  const v2 = trySafeReadJson<V2FileShape>(LEADERBOARD_V2_JSON)
  if (isV2Valid(v2)) {
    return {
      isDryRun: false,
      elo: v2.elo_v2_ci,
      pillarElo: {},
      perAgentProfile: {},
      rankSignificance: [],
      permutation: v2.permutation,
      dropStats: v2.drop_stats,
      excludedAgents: v2.excluded_agents,
      sourcePath: LEADERBOARD_V2_JSON,
      source: 'v2',
    }
  }

  // No valid leaderboard file found. Render EMPTY rather than fabricate a
  // ranking. The previous hardcoded claude-code/opencode/camel-ai seed was a
  // synthetic placeholder that misrepresented real standings, so it was removed.
  return {
    isDryRun: false,
    elo: {},
    pillarElo: {},
    perAgentProfile: {},
    rankSignificance: [],
    sourcePath: LEADERBOARD_V2_JSON,
    source: 'synthetic',
  }
}

function getCache(): NormalizedCache {
  if (!_cache) _cache = buildCache()
  return _cache
}

export function rankedAgents(): RankedAgent[] {
  const c = getCache()
  const rows: RankedAgent[] = Object.entries(c.elo).map(([id, e]) => {
    const prof = c.perAgentProfile[id]
    const pillars = c.pillarElo[id]
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
      url_veracity_pct: prof?.url_veracity_pct,
      depth_avg: prof?.depth_avg,
      rigor_avg: prof?.rigor_avg,
      style_avg: prof?.style_avg,
      checklist_pass_rate: prof?.checklist_pass_rate,
      coverage_pct: prof?.coverage_pct,
      reachability_pct: prof?.reachability_pct,
      per_pillar: pillars,
      schema_version: c.schemaVersion,
      is_dry_run: c.isDryRun,
      synthetic_placeholder: prof?.synthetic_placeholder,
    }
  })
  // Truth-gated score: judge Elo scaled by the grounding gate. A fluent report
  // only counts to the extent its citations are real -- this keeps every agent
  // scored (no exclusion) while preventing a fabricator from topping the board.
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

  // Compute sig_vs_next: highlight rows whose gap to the NEXT-lower agent is significant.
  const sigMap = new Map<string, boolean>()
  for (const pair of c.rankSignificance) {
    if (pair.significant) sigMap.set(pair.higher, true)
  }
  rows.forEach((r) => {
    r.sig_vs_next = sigMap.get(r.id) ?? false
  })

  return rows
}

/** Last-modified timestamp of the underlying leaderboard JSON as an ISO 8601
 *  string. Used by the layout / site header to show "data updated N hours
 *  ago". Returns the current time as a fallback when the file is absent
 *  (synthetic dataset). */
export function leaderboardMtime(): string {
  const c = getCache()
  try {
    return fs.statSync(c.sourcePath).mtime.toISOString()
  } catch {
    return new Date().toISOString()
  }
}

export function loadLeaderboard(): Leaderboard {
  const c = getCache()
  const n_runs = c.nRuns ?? Math.round(Object.values(c.elo).reduce((acc, e) => acc + (e.n_battles || 0), 0) / 2)
  return {
    n_runs,
    permutation: c.permutation,
    rank_significance: c.rankSignificance,
    drop_stats: c.dropStats,
    excluded_agents: c.excludedAgents,
    schema_version: c.schemaVersion,
    is_dry_run: c.isDryRun,
    weights_v3: c.weights,
    composite_formula: c.compositeFormula,
    human_alignment: c.humanAlignment,
  }
}

/** Convenience accessor: true when the loaded leaderboard is the v3 dry-run. */
export function isDryRun(): boolean {
  return getCache().isDryRun
}

/** Convenience accessor: schema version string when available. */
export function schemaVersion(): string | undefined {
  return getCache().schemaVersion
}
