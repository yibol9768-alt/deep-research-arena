import fs from 'node:fs'
import path from 'node:path'

// One real report excerpt per featured framework, per backbone, from the
// subset run (all on task dr_cross_deep_0001). excerpt = first ~6000 chars of
// the actual markdown report. Read at build time.
const SAMPLE_JSON = path.join(
  process.cwd(),
  '..',
  'data',
  'results',
  'matrix_subset',
  'sample_reports_20260707.json',
)

export interface SampleReport {
  task: string
  chars_total: number
  excerpt: string
}

// { backbone: { agentId: SampleReport } }
export type SampleReports = Record<string, Record<string, SampleReport>>

export function loadSampleReports(): SampleReports | null {
  try {
    const raw = fs.readFileSync(SAMPLE_JSON, 'utf-8')
    return JSON.parse(raw) as SampleReports
  } catch {
    return null
  }
}
