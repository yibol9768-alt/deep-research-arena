import fs from 'node:fs'
import path from 'node:path'

// Per-framework inference cost on the 13-task diagnostic subset, per backbone.
// Attributed from the box's LLM gateway usage log (one line per call:
// model/prompt_tokens/completion_tokens/ts) by matching each call to a run's
// time window. deepseek-v4-flash pricing is confirmed (¥1/¥2 per M); qwen3-8b
// pricing is an ESTIMATE (local 5090 run, no billed API cost). Read at build
// time; the dependent chart is omitted when the file is absent.
const COST_JSON = path.join(
  process.cwd(),
  '..',
  'data',
  'results',
  'matrix_subset',
  'cost_per_framework_20260707.json',
)

export interface CostPricing {
  prompt_cny_per_M: number
  completion_cny_per_M: number
  confirmed: boolean
}

export interface CostCell {
  total_prompt_tokens: number
  total_completion_tokens: number
  n_tasks_attributed: number
  n_runs_in_tsv: number
  n_runs_pass: number
  records_attributed: number
  llm_calls_delta_sum: number
  ambiguous_fraction: number
  pricing: CostPricing
  est_cost_cny_total: number
  est_cost_cny_per_task: number
  tokens_per_task_M: number
}

export interface CostData {
  generated_at: string
  task_set: string
  backbones: string[]
  frameworks: Record<string, Record<string, CostCell>>
}

export function loadCost(): CostData | null {
  try {
    const raw = fs.readFileSync(COST_JSON, 'utf-8')
    return JSON.parse(raw) as CostData
  } catch {
    return null
  }
}
