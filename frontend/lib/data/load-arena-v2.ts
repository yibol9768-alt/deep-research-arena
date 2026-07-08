import { loadMatrixSubset, type MatrixSubset, type MatrixAgentRow } from './load-matrix-subset'

// Arena v2 (uj_v1 protocol): every leaderboard entry is one harness x backbone
// run. Flattened from the matrix_subset snapshot at build time.

export interface ArenaEntry extends MatrixAgentRow {
  /** Unique key: `${id}__${backbone}` */
  key: string
  backbone: string
  /** Backbone-level jury reliability (Fleiss kappa) for context chips. */
  fleiss_kappa: number
  spearman_truth_vs_usefulness: number
}

export interface ArenaSnapshot {
  entries: ArenaEntry[]
  backbones: string[]
  judges: string[]
  arena_formula: string
  task_set: string
  protocol: string
  generated_at: string
  n_judge_records_total: number
  excluded_agents: string[]
  excluded_reason: string
  perBackbone: Record<string, { fleiss_kappa: number; spearman: number; n_clean_items: number; n_items: number }>
}

export { BACKBONE_SHORT, backboneShort } from '../backbones'

export function loadArenaV2(): ArenaSnapshot | null {
  const raw: MatrixSubset | null = loadMatrixSubset()
  if (!raw) return null

  const entries: ArenaEntry[] = []
  const perBackbone: ArenaSnapshot['perBackbone'] = {}
  for (const [backbone, bb] of Object.entries(raw.backbones)) {
    perBackbone[backbone] = {
      fleiss_kappa: bb.fleiss_kappa,
      spearman: bb.spearman_truth_vs_usefulness,
      n_clean_items: bb.n_clean_items,
      n_items: bb.n_items,
    }
    for (const a of bb.agents) {
      entries.push({
        ...a,
        key: `${a.id}__${backbone}`,
        backbone,
        fleiss_kappa: bb.fleiss_kappa,
        spearman_truth_vs_usefulness: bb.spearman_truth_vs_usefulness,
      })
    }
  }
  entries.sort((a, b) => b.arena - a.arena || b.bt_elo - a.bt_elo)

  return {
    entries,
    backbones: Object.keys(raw.backbones),
    judges: raw.judges,
    arena_formula: raw.arena_formula,
    task_set: raw.task_set,
    protocol: raw.protocol,
    generated_at: raw.generated_at,
    n_judge_records_total: raw.n_judge_records_total,
    excluded_agents: raw.excluded_agents,
    excluded_reason: raw.excluded_reason,
    perBackbone,
  }
}
