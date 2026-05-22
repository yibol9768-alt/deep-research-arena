/** Eight per-pillar Elo dimensions from the v3 schema. */
export interface PerPillarElo {
  coverage: number
  depth: number
  rigor: number
  style: number
  checklist: number
  spec: number
  reachability: number
  quote_match: number
}

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

  /** v3 per-agent profile (raw 0-1 scores, optional for graceful degradation). */
  url_veracity_pct?: number
  depth_avg?: number
  rigor_avg?: number
  style_avg?: number
  checklist_pass_rate?: number
  coverage_pct?: number
  reachability_pct?: number
  /** v3 per-pillar Elo (8 dimensions). */
  per_pillar?: PerPillarElo
  /** Schema marker propagated for the dry-run banner / tooltips. */
  schema_version?: string
  is_dry_run?: boolean
  /** True when the per-agent profile is synthetic (dry-run placeholder). */
  synthetic_placeholder?: boolean
  /** True when this agent sits in a statistically significant adjacent-rank gap. */
  sig_vs_next?: boolean
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
  /** v3 adjacent-pair significance test results. */
  rank_significance?: Array<{
    higher: string
    lower: string
    gap: number
    p_value: number
    significant: boolean
  }>
  /** File-counting audit per agent (degenerate / kept / total) */
  drop_stats?: Record<string, { degenerate: number; kept: number; total: number; load_error?: number }>
  /** Agent ids excluded by the drop-degenerate filter */
  excluded_agents?: string[]
  /** v3 schema marker, e.g. "v3-dryrun-2026-05-21". */
  schema_version?: string
  /** True when the leaderboard is a dry-run / synthetic-data preview. */
  is_dry_run?: boolean
  /** Per-pillar composite weights, e.g. {coverage:0.2, ...}. */
  weights_v3?: Record<string, number>
  /** Printable composite formula string for tooltips. */
  composite_formula?: string
  /** Human-alignment block (placeholder until Workstream D). */
  human_alignment?: {
    status?: string
    note?: string
    spearman_v2_vs_v3_dry_run?: number
    n_human_judgements?: number
  }
}
