export interface EloStats {
  elo: number;
  elo_lo: number;
  elo_hi: number;
  elo_half_width: number;
  wins: number;
  losses: number;
  draws: number;
}

export interface SigPair {
  higher: string;
  lower: string;
  gap: number;
  p_value: number | string;
  significant: boolean;
}

export interface LeaderboardData {
  n_runs: number;
  n_agents: number;
  n_tasks: number;
  ranked: [string, EloStats][];      // [agent_name, stats]
  elo_min: number;
  elo_max: number;
  elo_span: number;
  sig: SigPair[];
  sig_lookup: Record<string, boolean>;
  pair_counts: Record<string, number>;
  n_tasks_target: number;
  leaderboard_mtime: string | null;
  kpis: {
    total_pairs: number;
    unique_urls: number;
    est_tokens: number;
    judge_calls: number;
    degenerate_filtered: number;
  } | null;
}

export interface AgentDrillRow {
  task_id: string;
  composite_v2: number | null;
  url_coverage: number | null;
  reachability: number | null;
}

export interface AgentDrillData {
  agent: string;
  n_pairs: number;
  elo_v2?: { elo: number; elo_lo: number; elo_hi: number };
  pillar_means?: Record<string, number>;
  pillar_elo?: Record<string, number>;
  best_tasks?: AgentDrillRow[];
  worst_tasks?: AgentDrillRow[];
  github_url?: string;
  paper_url?: string;
}
