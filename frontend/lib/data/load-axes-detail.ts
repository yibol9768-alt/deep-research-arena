import fs from 'node:fs'
import path from 'node:path'

// Decidable five-axis truth breakdown per framework, per backbone, on the
// 13-task diagnostic subset. Aggregated from the box's truth boards
// (rows[].axes_mean + per_task). No LLM anywhere in this reading.
//   truth = grounding_reach^gamma x
//           (0.35 fact + 0.25 pof + 0.30 completeness + 0.10 spec)
// Read at build time; the dependent section degrades gracefully when absent.
const AXES_JSON = path.join(
  process.cwd(),
  '..',
  'data',
  'results',
  'matrix_subset',
  'axes_detail_20260707.json',
)

export type AxisKey =
  | 'grounding_reach'
  | 'grounding_proof_of_fetch'
  | 'correctness_fact_support'
  | 'completeness'
  | 'spec'

export type AxisMap = Record<AxisKey, number>

export interface AxesPerTask {
  task: string
  truth: number
  axes: AxisMap
}

export interface AxesAgent {
  rank: number
  n_tasks: number
  truth_macro: number
  truth_micro: number
  min_report_truth: number
  axes_mean: AxisMap
  per_task: AxesPerTask[]
}

export interface AxesBackbone {
  gamma: number
  n_answer_keys?: number
  agents: Record<string, AxesAgent>
}

export interface AxesDetail {
  generated_at: string
  task_set: string
  gamma: number
  composition: string
  axes: AxisKey[]
  backbones: Record<string, AxesBackbone>
}

export function loadAxesDetail(): AxesDetail | null {
  try {
    const raw = fs.readFileSync(AXES_JSON, 'utf-8')
    return JSON.parse(raw) as AxesDetail
  } catch {
    return null
  }
}
