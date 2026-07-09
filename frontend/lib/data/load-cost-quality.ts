import fs from 'node:fs'
import path from 'node:path'

// Cost-per-score snapshot: real per-run token accounting from the proxy usage
// log of one single-backbone lane, joined with the same lane's five-axis truth
// board. Read at build time; the section is omitted when the file is absent.
const COST_QUALITY_JSON = path.join(
  process.cwd(),
  '..',
  'data',
  'results',
  'deep_v3',
  'cost_quality_glm.json',
)

export interface CostQualityAgent {
  agent: string
  n_runs: number
  tokens_per_task_mean: number
  tokens_per_task_median: number
  cost_cny_per_task_mean: number | null
  truth_macro: number | null
  n_scored_tasks: number
}

export interface CostQualitySnapshot {
  backbone: string
  pricing: string
  agents: CostQualityAgent[]
  excluded: { agent: string; reason: string }[]
}

export function loadCostQuality(): CostQualitySnapshot | null {
  try {
    const raw = fs.readFileSync(COST_QUALITY_JSON, 'utf8')
    const doc = JSON.parse(raw) as CostQualitySnapshot
    if (!Array.isArray(doc.agents) || doc.agents.length === 0) return null
    return doc
  } catch {
    return null
  }
}
