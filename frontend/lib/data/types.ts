export interface RankedAgent {
  /** Canonical agent id (matches providers.ts) */
  id: string
  /** Final rank by Elo (1-indexed) */
  rank: number
  /** Bradley-Terry Elo on composite_v2_truthful (deterministic gate + judge + spec) */
  elo: number
  /** Bootstrap mean Elo (paired with ci_lo/hi) */
  elo_mean?: number
  /** 95% CI lower bound */
  ci_lo: number
  /** 95% CI upper bound */
  ci_hi: number
  /** Aliases for ci_lo / ci_hi (older pages use these names) */
  elo_lo: number
  elo_hi: number
  /** Half-width of the 95% CI */
  ci_half: number
  /** Total head-to-head battles aggregated for this agent */
  n_battles: number
  wins: number
  losses: number
  draws: number
}

export interface PillarEloRow {
  /** Pillar / dimension name (e.g., url_coverage, judge_pass, spec) */
  pillar: string
  /** Per-agent Elo on this pillar */
  by_agent: Record<string, number>
}

export interface Leaderboard {
  /** Total runs aggregated across all agents */
  n_runs: number
  /** Per-pillar Elo (computed only when scripts populate it; may be missing) */
  pillar_elo?: PillarEloRow[]
  /** Permutation test results between adjacent ranks (optional) */
  permutation?: Array<{
    higher: string
    lower: string
    gap_elo: number
    p_value: number
  }>
  /** File-counting audit per agent (degenerate / kept / total) */
  drop_stats?: Record<string, { degenerate: number; kept: number; total: number; load_error?: number }>
  /** Agent ids excluded by the drop-degenerate filter */
  excluded_agents?: string[]
}
