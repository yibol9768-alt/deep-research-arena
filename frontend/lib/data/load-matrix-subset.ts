import fs from 'node:fs'
import path from 'node:path'

// v2 preview: usefulness jury (Bradley-Terry) x five-axis truth on the
// 13-task diagnostic subset, per backbone. Read at build time; the section
// is simply omitted when the snapshot file is absent.
const MATRIX_SUBSET_JSON = path.join(
  process.cwd(),
  '..',
  'data',
  'results',
  'matrix_subset',
  'matrix_subset_20260707.json',
)

export interface MatrixAgentRow {
  id: string
  arena: number
  truth: number
  reach: number
  bt_elo: number
  winrate: number
  winrate_ci95?: [number, number]
  rank_ci95?: [number, number]
  n_battles: number
  tie_rate?: number | null
}

export interface MatrixBackbone {
  fleiss_kappa: number
  n_clean_items: number
  n_items: number
  spearman_truth_vs_usefulness: number
  agents: MatrixAgentRow[]
}

export interface MatrixSubset {
  generated_at: string
  protocol: string
  task_set: string
  judges: string[]
  usefulness_rubric: string[]
  n_judge_records_total: number
  excluded_agents: string[]
  excluded_reason: string
  arena_formula: string
  backbones: Record<string, MatrixBackbone>
}

export function loadMatrixSubset(): MatrixSubset | null {
  try {
    const raw = fs.readFileSync(MATRIX_SUBSET_JSON, 'utf-8')
    return JSON.parse(raw) as MatrixSubset
  } catch {
    return null
  }
}
