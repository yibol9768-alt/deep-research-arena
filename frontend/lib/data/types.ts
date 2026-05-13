import { z } from 'zod'

export const EloRowSchema = z.object({
  elo: z.number(),
  elo_mean: z.number().optional(),
  elo_lo: z.number(),
  elo_hi: z.number(),
  elo_half_width: z.number().optional(),
  n_resamples: z.number().optional(),
  confidence: z.number().optional(),
  n_battles: z.number(),
  wins: z.number(),
  losses: z.number(),
  draws: z.number(),
})
export type EloRow = z.infer<typeof EloRowSchema>

export const LeaderboardSchema = z.object({
  elo_v2_ci: z.record(EloRowSchema),
  elo_v1_ci: z.record(EloRowSchema).optional(),
  pillar_elo: z.record(z.record(z.number())).optional(),
  rank_significance_v2: z
    .object({
      ordered: z.array(z.string()),
      adjacent_pairs: z.array(z.any()).optional(),
    })
    .optional(),
  n_runs: z.number().optional(),
  agents: z.array(z.string()).optional(),
  tasks: z.array(z.string()).optional(),
})
export type Leaderboard = z.infer<typeof LeaderboardSchema>

export interface RankedAgent extends EloRow {
  id: string
  rank: number
  /** half_width width for error bar; computed if not present */
  ci_half: number
}
